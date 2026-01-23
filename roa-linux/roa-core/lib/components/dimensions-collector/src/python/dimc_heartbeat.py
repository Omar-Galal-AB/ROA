"""
DIMC Heartbeat Agent - Health Status and Lifecycle Management

This module implements the Heartbeat (HB) subsystem for the Dimensions Collector,
providing health monitoring, client lifecycle management, and auto-shutdown capabilities.

Architecture:
- File-based heartbeat: .ipc/heartbeats/{client_id}.heartbeat.json
- Client lifecycle: Register → Heartbeat → Deregister
- Auto-shutdown: Component shuts down after configurable delay with no clients
- Integration with DIMC observability for metrics

Based on the FTI heartbeat pattern but adapted for DIMC-specific needs.
"""

import os
import sys
import json
import time
import atexit
import signal
import logging
import threading
from pathlib import Path
from enum import Enum, auto
from typing import Dict, Any, Optional, Callable, List, Set
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid


class HeartbeatState(Enum):
    """Heartbeat client state."""
    REGISTERED = auto()
    ACTIVE = auto()
    STALE = auto()
    DEAD = auto()
    DEREGISTERED = auto()


class ComponentHealth(Enum):
    """Component health status."""
    HEALTHY = auto()
    DEGRADED = auto()
    UNHEALTHY = auto()
    UNKNOWN = auto()


@dataclass
class HeartbeatConfig:
    """Heartbeat configuration."""
    # IPC paths
    ipc_base_path: str = "/mnt/d/ROA/.ipc"
    heartbeat_dir: str = "heartbeats"
    
    # Timing
    heartbeat_interval: float = 5.0      # Send heartbeat every 5 seconds
    stale_threshold: float = 15.0        # Client considered stale after 15s
    dead_threshold: float = 30.0         # Client considered dead after 30s
    check_interval: float = 10.0         # Check clients every 10s
    
    # Auto-shutdown
    auto_shutdown_enabled: bool = True
    auto_shutdown_delay: float = 60.0    # Shutdown after 60s with no clients
    
    # Component identification
    component_name: str = "DIMC"
    component_version: str = "2.0"
    
    # Status file
    status_file_name: str = "dimc.status.json"


@dataclass
class HeartbeatData:
    """Heartbeat data structure."""
    client_id: str
    component: str
    timestamp: float
    state: str
    health: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    capabilities: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "client_id": self.client_id,
            "component": self.component,
            "timestamp": self.timestamp,
            "timestamp_iso": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "state": self.state,
            "health": self.health,
            "metrics": self.metrics,
            "capabilities": self.capabilities
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HeartbeatData':
        """Create from dictionary."""
        return cls(
            client_id=data.get("client_id", ""),
            component=data.get("component", ""),
            timestamp=data.get("timestamp", 0),
            state=data.get("state", "UNKNOWN"),
            health=data.get("health", "UNKNOWN"),
            metrics=data.get("metrics", {}),
            capabilities=data.get("capabilities", [])
        )


@dataclass
class ClientInfo:
    """Information about a registered client."""
    client_id: str
    component: str
    registered_at: float
    last_heartbeat: float
    state: HeartbeatState
    health: ComponentHealth
    metadata: Dict[str, Any] = field(default_factory=dict)


class DIMCHeartbeat:
    """
    DIMC Heartbeat Agent - Manages component health and lifecycle.
    
    This class provides:
    - Self-registration as a heartbeat client
    - Periodic heartbeat broadcasting
    - Health status reporting
    - Integration with other ROA components
    """
    
    def __init__(self, config: Optional[HeartbeatConfig] = None,
                 logger: Optional[logging.Logger] = None):
        """Initialize the heartbeat agent."""
        self.config = config or HeartbeatConfig()
        self.logger = logger or logging.getLogger(__name__)
        
        # Client identity
        self.client_id = f"dimc-{uuid.uuid4().hex[:8]}"
        
        # State
        self.running = False
        self.registered = False
        self.state = HeartbeatState.REGISTERED
        self.health = ComponentHealth.HEALTHY
        
        # Metrics (populated externally)
        self._metrics: Dict[str, Any] = {}
        self._capabilities: List[str] = [
            "lidar_scanning",
            "obstacle_detection",
            "proximity_monitoring",
            "fleet_coordination",
            "evade_api"
        ]
        
        # Path setup
        self._heartbeat_dir = Path(self.config.ipc_base_path) / self.config.heartbeat_dir
        self._status_file = Path(self.config.ipc_base_path) / self.config.status_file_name
        self._heartbeat_file: Optional[Path] = None
        
        # Threading
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        
        # Callbacks
        self.on_health_changed: Optional[Callable[[ComponentHealth, ComponentHealth], None]] = None
        self.on_shutdown_requested: Optional[Callable[[], None]] = None
        
        # Statistics
        self.heartbeats_sent: int = 0
        self.start_time: Optional[float] = None
        self.last_heartbeat_time: float = 0
        
    def start(self) -> bool:
        """
        Start the heartbeat agent.
        
        Returns:
            True if started successfully.
        """
        if self.running:
            self.logger.warning("Heartbeat agent already running")
            return True
            
        try:
            # Ensure heartbeat directory exists
            self._ensure_directories()
            
            # Register as client
            self._register()
            
            # Start heartbeat thread
            self.running = True
            self.start_time = time.time()
            
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                daemon=True,
                name="DIMC-Heartbeat"
            )
            self._heartbeat_thread.start()
            
            # Register cleanup on exit
            atexit.register(self.stop)
            
            self.logger.info(f"Heartbeat agent started (client_id: {self.client_id})")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start heartbeat agent: {e}")
            return False
            
    def stop(self):
        """Stop the heartbeat agent and deregister."""
        if not self.running:
            return
            
        self.logger.info("Stopping heartbeat agent...")
        
        self.running = False
        
        # Wait for thread
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2.0)
            
        # Deregister
        self._deregister()
        
        # Remove from atexit
        try:
            atexit.unregister(self.stop)
        except:
            pass
            
        self.logger.info("Heartbeat agent stopped")
        
    def update_health(self, health: ComponentHealth, reason: str = ""):
        """
        Update component health status.
        
        Args:
            health: New health status
            reason: Optional reason for health change
        """
        old_health = self.health
        
        with self._lock:
            self.health = health
            
        if old_health != health:
            self.logger.info(f"Health changed: {old_health.name} -> {health.name}"
                           f"{f' ({reason})' if reason else ''}")
            
            if self.on_health_changed:
                try:
                    self.on_health_changed(old_health, health)
                except Exception as e:
                    self.logger.error(f"Health change callback error: {e}")
                    
    def update_metrics(self, metrics: Dict[str, Any]):
        """
        Update component metrics to include in heartbeat.
        
        Args:
            metrics: Dictionary of metric name -> value
        """
        with self._lock:
            self._metrics.update(metrics)
            
    def set_metrics(self, metrics: Dict[str, Any]):
        """
        Replace all metrics.
        
        Args:
            metrics: Complete metrics dictionary
        """
        with self._lock:
            self._metrics = metrics.copy()
            
    def get_status(self) -> Dict[str, Any]:
        """
        Get current heartbeat status.
        
        Returns:
            Status dictionary.
        """
        return {
            "client_id": self.client_id,
            "component": self.config.component_name,
            "version": self.config.component_version,
            "running": self.running,
            "registered": self.registered,
            "state": self.state.name,
            "health": self.health.name,
            "start_time": self.start_time,
            "uptime_seconds": time.time() - self.start_time if self.start_time else 0,
            "heartbeats_sent": self.heartbeats_sent,
            "last_heartbeat": self.last_heartbeat_time,
            "capabilities": self._capabilities
        }
        
    def is_healthy(self) -> bool:
        """Check if component is healthy."""
        return self.health == ComponentHealth.HEALTHY
        
    # =========================================================================
    # Private Methods
    # =========================================================================
    
    def _ensure_directories(self):
        """Ensure heartbeat directories exist."""
        try:
            self._heartbeat_dir.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Heartbeat directory ready: {self._heartbeat_dir}")
        except Exception as e:
            self.logger.warning(f"Could not create heartbeat directory: {e}")
            # Fall back to local directory
            self._heartbeat_dir = Path.cwd() / ".dimc" / "heartbeats"
            self._heartbeat_dir.mkdir(parents=True, exist_ok=True)
            self._status_file = Path.cwd() / ".dimc" / self.config.status_file_name
            
    def _register(self):
        """Register as a heartbeat client."""
        self._heartbeat_file = self._heartbeat_dir / f"{self.client_id}.heartbeat.json"
        
        # Create initial heartbeat file
        heartbeat_data = HeartbeatData(
            client_id=self.client_id,
            component=self.config.component_name,
            timestamp=time.time(),
            state=HeartbeatState.REGISTERED.name,
            health=self.health.name,
            metrics=self._metrics,
            capabilities=self._capabilities
        )
        
        self._write_heartbeat(heartbeat_data)
        self._write_status("STARTING")
        
        self.registered = True
        self.state = HeartbeatState.REGISTERED
        
        self.logger.info(f"Registered heartbeat client: {self.client_id}")
        
    def _deregister(self):
        """Deregister as a heartbeat client."""
        if not self.registered:
            return
            
        # Write final heartbeat with DEREGISTERED state
        heartbeat_data = HeartbeatData(
            client_id=self.client_id,
            component=self.config.component_name,
            timestamp=time.time(),
            state=HeartbeatState.DEREGISTERED.name,
            health=self.health.name,
            metrics=self._metrics,
            capabilities=self._capabilities
        )
        
        self._write_heartbeat(heartbeat_data)
        self._write_status("STOPPED")
        
        # Remove heartbeat file after short delay (so watchers can see deregistration)
        time.sleep(0.5)
        
        if self._heartbeat_file and self._heartbeat_file.exists():
            try:
                self._heartbeat_file.unlink()
                self.logger.debug(f"Removed heartbeat file: {self._heartbeat_file}")
            except Exception as e:
                self.logger.warning(f"Could not remove heartbeat file: {e}")
                
        self.registered = False
        self.state = HeartbeatState.DEREGISTERED
        
        self.logger.info(f"Deregistered heartbeat client: {self.client_id}")
        
    def _heartbeat_loop(self):
        """Main heartbeat loop."""
        while self.running:
            try:
                self._send_heartbeat()
            except Exception as e:
                self.logger.error(f"Heartbeat error: {e}")
                
            # Wait for next interval
            time.sleep(self.config.heartbeat_interval)
            
    def _send_heartbeat(self):
        """Send a heartbeat."""
        now = time.time()
        
        with self._lock:
            # Update state to ACTIVE
            self.state = HeartbeatState.ACTIVE
            
            # Build heartbeat data
            heartbeat_data = HeartbeatData(
                client_id=self.client_id,
                component=self.config.component_name,
                timestamp=now,
                state=self.state.name,
                health=self.health.name,
                metrics=self._get_current_metrics(),
                capabilities=self._capabilities
            )
            
        # Write heartbeat file
        self._write_heartbeat(heartbeat_data)
        
        # Update status file
        self._write_status("RUNNING")
        
        self.last_heartbeat_time = now
        self.heartbeats_sent += 1
        
        self.logger.debug(f"Heartbeat sent (#{self.heartbeats_sent})")
        
    def _write_heartbeat(self, data: HeartbeatData):
        """Write heartbeat data to file atomically."""
        if not self._heartbeat_file:
            return
            
        try:
            # Write to temp file first (atomic write)
            temp_file = self._heartbeat_file.with_suffix('.tmp')
            
            with open(temp_file, 'w') as f:
                json.dump(data.to_dict(), f, indent=2)
                
            # Atomic rename
            temp_file.rename(self._heartbeat_file)
            
        except Exception as e:
            self.logger.error(f"Failed to write heartbeat: {e}")
            
    def _write_status(self, status: str):
        """Write component status file."""
        try:
            status_data = {
                "component": self.config.component_name,
                "version": self.config.component_version,
                "status": status,
                "client_id": self.client_id,
                "timestamp": time.time(),
                "timestamp_iso": datetime.now(timezone.utc).isoformat(),
                "health": self.health.name,
                "uptime_seconds": time.time() - self.start_time if self.start_time else 0,
                "pid": os.getpid()
            }
            
            # Write atomically
            temp_file = self._status_file.with_suffix('.tmp')
            
            with open(temp_file, 'w') as f:
                json.dump(status_data, f, indent=2)
                
            temp_file.rename(self._status_file)
            
        except Exception as e:
            self.logger.debug(f"Could not write status file: {e}")
            
    def _get_current_metrics(self) -> Dict[str, Any]:
        """Get current metrics for heartbeat."""
        # Base metrics
        metrics = {
            "uptime_seconds": time.time() - self.start_time if self.start_time else 0,
            "heartbeats_sent": self.heartbeats_sent,
            "pid": os.getpid()
        }
        
        # Add custom metrics
        metrics.update(self._metrics)
        
        return metrics


class DIMCHeartbeatMonitor:
    """
    Monitor for tracking other components' heartbeats.
    
    This class watches the heartbeat directory for other ROA components
    and tracks their health status for coordination.
    """
    
    def __init__(self, config: Optional[HeartbeatConfig] = None,
                 logger: Optional[logging.Logger] = None):
        """Initialize the heartbeat monitor."""
        self.config = config or HeartbeatConfig()
        self.logger = logger or logging.getLogger(__name__)
        
        self._heartbeat_dir = Path(self.config.ipc_base_path) / self.config.heartbeat_dir
        
        # Tracked clients
        self._clients: Dict[str, ClientInfo] = {}
        self._lock = threading.RLock()
        
        # Threading
        self.running = False
        self._monitor_thread: Optional[threading.Thread] = None
        
        # Callbacks
        self.on_client_registered: Optional[Callable[[ClientInfo], None]] = None
        self.on_client_dead: Optional[Callable[[ClientInfo], None]] = None
        self.on_client_health_changed: Optional[Callable[[ClientInfo, ComponentHealth], None]] = None
        
    def start(self):
        """Start monitoring other components."""
        if self.running:
            return
            
        self.running = True
        
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="DIMC-HeartbeatMonitor"
        )
        self._monitor_thread.start()
        
        self.logger.info("Heartbeat monitor started")
        
    def stop(self):
        """Stop monitoring."""
        self.running = False
        
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
            
        self.logger.info("Heartbeat monitor stopped")
        
    def get_clients(self) -> Dict[str, ClientInfo]:
        """Get all tracked clients."""
        with self._lock:
            return self._clients.copy()
            
    def get_client(self, client_id: str) -> Optional[ClientInfo]:
        """Get specific client info."""
        with self._lock:
            return self._clients.get(client_id)
            
    def get_healthy_clients(self) -> List[ClientInfo]:
        """Get all healthy clients."""
        with self._lock:
            return [c for c in self._clients.values() 
                   if c.state == HeartbeatState.ACTIVE and c.health == ComponentHealth.HEALTHY]
                   
    def is_component_alive(self, component_name: str) -> bool:
        """Check if a specific component is alive."""
        with self._lock:
            for client in self._clients.values():
                if client.component == component_name and client.state == HeartbeatState.ACTIVE:
                    return True
            return False
            
    def _monitor_loop(self):
        """Main monitoring loop."""
        while self.running:
            try:
                self._scan_heartbeats()
                self._check_client_health()
            except Exception as e:
                self.logger.error(f"Monitor loop error: {e}")
                
            time.sleep(self.config.check_interval)
            
    def _scan_heartbeats(self):
        """Scan heartbeat directory for clients."""
        if not self._heartbeat_dir.exists():
            return
            
        try:
            # Get all heartbeat files
            heartbeat_files = list(self._heartbeat_dir.glob("*.heartbeat.json"))
            
            seen_clients: Set[str] = set()
            
            for hb_file in heartbeat_files:
                try:
                    with open(hb_file, 'r') as f:
                        data = json.load(f)
                        
                    heartbeat = HeartbeatData.from_dict(data)
                    seen_clients.add(heartbeat.client_id)
                    
                    self._update_client(heartbeat, hb_file.stat().st_mtime)
                    
                except Exception as e:
                    self.logger.debug(f"Could not read heartbeat file {hb_file}: {e}")
                    
            # Mark unseen clients as dead
            with self._lock:
                for client_id in list(self._clients.keys()):
                    if client_id not in seen_clients:
                        client = self._clients[client_id]
                        if client.state != HeartbeatState.DEAD:
                            client.state = HeartbeatState.DEAD
                            self.logger.info(f"Client marked dead (file removed): {client_id}")
                            
                            if self.on_client_dead:
                                self.on_client_dead(client)
                                
        except Exception as e:
            self.logger.error(f"Error scanning heartbeats: {e}")
            
    def _update_client(self, heartbeat: HeartbeatData, file_mtime: float):
        """Update client info from heartbeat data."""
        now = time.time()
        
        with self._lock:
            if heartbeat.client_id not in self._clients:
                # New client
                client = ClientInfo(
                    client_id=heartbeat.client_id,
                    component=heartbeat.component,
                    registered_at=now,
                    last_heartbeat=heartbeat.timestamp,
                    state=HeartbeatState[heartbeat.state] if heartbeat.state in HeartbeatState.__members__ else HeartbeatState.ACTIVE,
                    health=ComponentHealth[heartbeat.health] if heartbeat.health in ComponentHealth.__members__ else ComponentHealth.UNKNOWN,
                    metadata=heartbeat.metrics
                )
                
                self._clients[heartbeat.client_id] = client
                self.logger.info(f"New client registered: {heartbeat.client_id} ({heartbeat.component})")
                
                if self.on_client_registered:
                    self.on_client_registered(client)
                    
            else:
                # Update existing client
                client = self._clients[heartbeat.client_id]
                old_health = client.health
                
                client.last_heartbeat = heartbeat.timestamp
                client.state = HeartbeatState[heartbeat.state] if heartbeat.state in HeartbeatState.__members__ else client.state
                client.health = ComponentHealth[heartbeat.health] if heartbeat.health in ComponentHealth.__members__ else client.health
                client.metadata = heartbeat.metrics
                
                # Notify on health change
                if old_health != client.health and self.on_client_health_changed:
                    self.on_client_health_changed(client, old_health)
                    
    def _check_client_health(self):
        """Check client health based on heartbeat timing."""
        now = time.time()
        
        with self._lock:
            for client in self._clients.values():
                if client.state == HeartbeatState.DEAD:
                    continue
                    
                time_since_heartbeat = now - client.last_heartbeat
                
                if time_since_heartbeat > self.config.dead_threshold:
                    if client.state != HeartbeatState.DEAD:
                        client.state = HeartbeatState.DEAD
                        self.logger.warning(f"Client dead (timeout): {client.client_id}")
                        
                        if self.on_client_dead:
                            self.on_client_dead(client)
                            
                elif time_since_heartbeat > self.config.stale_threshold:
                    if client.state != HeartbeatState.STALE:
                        client.state = HeartbeatState.STALE
                        self.logger.warning(f"Client stale: {client.client_id}")
