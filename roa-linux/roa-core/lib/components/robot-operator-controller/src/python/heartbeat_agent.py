"""
Heartbeat Agent - ROC component health and dependency monitoring.

Manages ROC heartbeat lifecycle:
- Writes ROC heartbeat files to advertise health
- Monitors dependency heartbeats (FTI, DIMC, COMC, UE5)
- Reports health metrics (CPU, memory, uptime)
- Detects component timeouts and triggers graceful degradation

Based on FTI IPC Service heartbeat pattern and COMC HealthMonitor.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


@dataclass
class DependencyConfig:
    """Configuration for a monitored dependency."""
    name: str
    pattern: str  # Glob pattern for heartbeat files
    timeout: float  # Seconds before considered dead
    critical: bool  # If True, triggers graceful degradation on failure
    last_seen: float = 0.0
    healthy: bool = True
    last_file: str = ""


@dataclass
class HeartbeatAgentConfig:
    """Configuration for HeartbeatAgent."""
    # Heartbeat settings
    heartbeat_dir: str = "/mnt/d/ROA/.ipc/heartbeats"
    heartbeat_rate_hz: float = 2.0  # 500ms interval (Webthread standard)
    client_type: str = "roc_component"
    
    # Dependency monitoring
    monitor_dependencies: bool = True
    fti_timeout: float = 30.0  # FTI only needed on import
    dimc_timeout: float = 1.5  # 3 missed at 2Hz = critical
    comc_timeout: float = 1.5  # 3 missed at 2Hz
    ue5_timeout: float = 30.0  # UE5 writes every 10-20s
    
    # Health reporting
    report_to_webthread: bool = True
    webthread_report_rate_hz: float = 1.0  # 1Hz status reports
    
    # Graceful degradation
    enable_degradation: bool = True
    
    # Cleanup
    remove_heartbeat_on_shutdown: bool = True


class HeartbeatAgent:
    """
    Manages ROC heartbeat and monitors component dependencies.
    
    Responsibilities:
    - Write ROC heartbeat files (advertise we're alive)
    - Monitor dependency heartbeats (FTI, DIMC, COMC, UE5)
    - Detect component timeouts
    - Report health metrics to Webthread
    - Trigger graceful degradation on critical failures
    
    Follows the heartbeat lifecycle pattern from:
    - FTI IPC Service (file-based heartbeat)
    - COMC HealthMonitor (metrics collection)
    """
    
    def __init__(
        self, 
        config: Optional[HeartbeatAgentConfig] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize HeartbeatAgent.
        
        Args:
            config: Agent configuration
            logger: Logger instance
        """
        self.config = config or HeartbeatAgentConfig()
        self.logger = logger or logging.getLogger(__name__)
        
        # Generate unique client ID
        self.client_id = f"roc_{uuid.uuid4().hex[:8]}"
        
        # Heartbeat directory and file
        self.heartbeat_dir = Path(self.config.heartbeat_dir)
        self.heartbeat_file = self.heartbeat_dir / f"{self.client_id}.heartbeat.json"
        
        # Dependencies to monitor
        self.dependencies: Dict[str, DependencyConfig] = {}
        self._init_dependencies()
        
        # State
        self._running = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._dependency_task: Optional[asyncio.Task] = None
        self.start_time = time.time()
        
        # Metrics (updated by coordinator)
        self._active_robots: int = 0
        self._commands_processed: int = 0
        self._current_mode: str = "rpm"
        self._ipc_connected: bool = False
        
        # Health status
        self._health_status: str = "starting"
        self._degraded_components: List[str] = []
        
        # Callbacks
        self._dependency_failure_callbacks: List[Callable[[str, bool], None]] = []
        self._health_status_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        
        # Process for metrics
        self._process = psutil.Process() if PSUTIL_AVAILABLE else None
        
        self.logger.info(f"HeartbeatAgent initialized with client_id: {self.client_id}")
    
    def _init_dependencies(self):
        """Initialize dependency configurations."""
        if not self.config.monitor_dependencies:
            return
        
        self.dependencies = {
            'fti_service': DependencyConfig(
                name='fti_service',
                pattern='fti_*.heartbeat.json',
                timeout=self.config.fti_timeout,
                critical=False  # FTI only needed during import
            ),
            'dimc': DependencyConfig(
                name='dimc',
                pattern='dimc_*.heartbeat.json',
                timeout=self.config.dimc_timeout,
                critical=True  # DIMC provides spatial data
            ),
            'comc': DependencyConfig(
                name='comc',
                pattern='comc_*.heartbeat.json',
                timeout=self.config.comc_timeout,
                critical=False  # COMC only for multi-robot
            ),
            'ue5_plugin': DependencyConfig(
                name='ue5_plugin',
                pattern='ue5_*.heartbeat.json',
                timeout=self.config.ue5_timeout,
                critical=True  # UE5 plugin is essential
            )
        }
    
    # =========================================================================
    # Lifecycle
    # =========================================================================
    
    async def start(self) -> bool:
        """
        Start the heartbeat agent.
        
        Returns:
            True if started successfully.
        """
        self.logger.info("Starting HeartbeatAgent")
        
        # Ensure heartbeat directory exists
        try:
            self.heartbeat_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.logger.error(f"Failed to create heartbeat directory: {e}")
            return False
        
        self._running = True
        self.start_time = time.time()
        self._health_status = "active"
        
        # Write initial heartbeat
        self._write_heartbeat()
        
        # Start heartbeat loop
        interval = 1.0 / self.config.heartbeat_rate_hz
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(interval)
        )
        
        # Start dependency monitoring
        if self.config.monitor_dependencies:
            self._dependency_task = asyncio.create_task(
                self._dependency_monitor_loop()
            )
        
        self.logger.info("HeartbeatAgent started")
        return True
    
    async def stop(self):
        """Stop the heartbeat agent."""
        self.logger.info("Stopping HeartbeatAgent")
        
        self._running = False
        self._health_status = "stopping"
        
        # Cancel tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        if self._dependency_task:
            self._dependency_task.cancel()
            try:
                await self._dependency_task
            except asyncio.CancelledError:
                pass
        
        # Clean up heartbeat file
        if self.config.remove_heartbeat_on_shutdown:
            self._remove_heartbeat()
        
        self.logger.info("HeartbeatAgent stopped")
    
    # =========================================================================
    # Heartbeat Writing
    # =========================================================================
    
    def _write_heartbeat(self):
        """Write ROC heartbeat file with health metrics."""
        try:
            data = {
                "client_id": self.client_id,
                "type": self.config.client_type,
                "timestamp": time.time(),
                "last_activity": datetime.now().isoformat(),
                "health_status": self._health_status,
                "metrics": self._get_health_metrics(),
                "dependencies": self._get_dependency_status_summary()
            }
            
            # Write atomically (write to temp, then rename)
            temp_file = self.heartbeat_file.with_suffix('.tmp')
            temp_file.write_text(json.dumps(data, indent=2))
            temp_file.rename(self.heartbeat_file)
            
        except Exception as e:
            self.logger.error(f"Failed to write heartbeat: {e}")
    
    def _remove_heartbeat(self):
        """Remove heartbeat file on shutdown."""
        try:
            if self.heartbeat_file.exists():
                self.heartbeat_file.unlink()
                self.logger.info(f"Removed heartbeat file: {self.heartbeat_file}")
        except Exception as e:
            self.logger.error(f"Failed to remove heartbeat file: {e}")
    
    async def _heartbeat_loop(self, interval: float):
        """Background loop to write heartbeat."""
        while self._running:
            try:
                self._write_heartbeat()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in heartbeat loop: {e}")
                await asyncio.sleep(interval)
    
    # =========================================================================
    # Dependency Monitoring
    # =========================================================================
    
    def _check_dependency(self, dep: DependencyConfig) -> bool:
        """
        Check if a dependency is healthy via its heartbeat file.
        
        Args:
            dep: Dependency configuration
            
        Returns:
            True if dependency is healthy (heartbeat within timeout)
        """
        try:
            # Find matching heartbeat files
            files = list(self.heartbeat_dir.glob(dep.pattern))
            
            if not files:
                # No heartbeat file found - might not be running
                dep.healthy = False
                return False
            
            # Use most recently modified file
            latest_file = max(files, key=lambda f: f.stat().st_mtime)
            
            # Read heartbeat
            data = json.loads(latest_file.read_text())
            timestamp = data.get('timestamp', 0)
            
            # Check timeout
            elapsed = time.time() - timestamp
            healthy = elapsed < dep.timeout
            
            # Update dependency state
            dep.last_seen = timestamp
            dep.last_file = str(latest_file)
            dep.healthy = healthy
            
            return healthy
            
        except json.JSONDecodeError as e:
            self.logger.warning(f"Invalid JSON in {dep.name} heartbeat: {e}")
            dep.healthy = False
            return False
        except Exception as e:
            self.logger.error(f"Error checking {dep.name} heartbeat: {e}")
            dep.healthy = False
            return False
    
    def check_all_dependencies(self) -> Dict[str, bool]:
        """
        Check health of all dependencies.
        
        Returns:
            Dict of dependency_name -> is_healthy
        """
        status = {}
        
        for dep_name, dep in self.dependencies.items():
            status[dep_name] = self._check_dependency(dep)
        
        return status
    
    async def _dependency_monitor_loop(self):
        """Background loop to monitor dependency health."""
        check_interval = 1.0  # 1Hz dependency check
        
        while self._running:
            try:
                status = self.check_all_dependencies()
                
                # Check for failures
                for dep_name, healthy in status.items():
                    dep = self.dependencies[dep_name]
                    
                    if not healthy:
                        if dep.critical:
                            # Critical dependency failed
                            if dep_name not in self._degraded_components:
                                self._degraded_components.append(dep_name)
                                self._health_status = "degraded"
                                
                                self.logger.error(
                                    f"Critical dependency {dep_name} heartbeat timeout "
                                    f"(>{dep.timeout}s since last heartbeat)"
                                )
                                
                                # Notify callbacks
                                await self._notify_dependency_failure(dep_name, True)
                                
                                # Trigger graceful degradation
                                if self.config.enable_degradation:
                                    await self._handle_dependency_failure(dep_name)
                        else:
                            # Non-critical dependency timeout
                            self.logger.warning(
                                f"Non-critical dependency {dep_name} heartbeat timeout"
                            )
                    else:
                        # Dependency recovered
                        if dep_name in self._degraded_components:
                            self._degraded_components.remove(dep_name)
                            
                            self.logger.info(f"Dependency {dep_name} recovered")
                            
                            # Notify recovery
                            await self._notify_dependency_failure(dep_name, False)
                            
                            # Update health status
                            if not self._degraded_components:
                                self._health_status = "active"
                
                await asyncio.sleep(check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in dependency monitor: {e}")
                await asyncio.sleep(check_interval)
    
    async def _handle_dependency_failure(self, component: str):
        """
        Handle failure of a dependency component.
        
        Args:
            component: Name of failed component
        """
        if component == 'dimc':
            # DIMC provides spatial data - can't do safe motion without it
            self.logger.warning(
                "DIMC timeout - robot spatial data unavailable, "
                "consider pausing autonomous operations"
            )
        
        elif component == 'ue5_plugin':
            # UE5 plugin is the visualization/control interface
            self.logger.warning(
                "UE5 plugin timeout - UE5 connection may be lost, "
                "consider reconnecting"
            )
        
        elif component == 'fti_service':
            # FTI is only needed for imports
            self.logger.info(
                "FTI service not running - robot imports unavailable"
            )
        
        elif component == 'comc':
            # COMC is for multi-robot coordination
            self.logger.info(
                "COMC timeout - multi-robot coordination unavailable, "
                "single-robot mode still functional"
            )
    
    async def _notify_dependency_failure(self, component: str, failed: bool):
        """Notify registered callbacks of dependency status change."""
        for callback in self._dependency_failure_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(component, failed)
                else:
                    callback(component, failed)
            except Exception as e:
                self.logger.error(f"Error in dependency failure callback: {e}")
    
    # =========================================================================
    # Health Metrics
    # =========================================================================
    
    def _get_health_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive health metrics.
        
        Returns:
            Dict with CPU, memory, uptime, and ROC-specific metrics
        """
        metrics = {
            "uptime_seconds": round(time.time() - self.start_time, 2),
            "active_robots": self._active_robots,
            "commands_processed": self._commands_processed,
            "current_mode": self._current_mode,
            "ipc_connected": self._ipc_connected
        }
        
        # Add system metrics if psutil available
        if self._process and PSUTIL_AVAILABLE:
            try:
                metrics["cpu_usage"] = round(self._process.cpu_percent(interval=0.1), 2)
                memory_info = self._process.memory_info()
                metrics["memory_mb"] = round(memory_info.rss / (1024 * 1024), 2)
            except Exception:
                metrics["cpu_usage"] = 0.0
                metrics["memory_mb"] = 0.0
        
        return metrics
    
    def _get_dependency_status_summary(self) -> Dict[str, Any]:
        """Get summary of dependency health status."""
        summary = {}
        
        for dep_name, dep in self.dependencies.items():
            summary[dep_name] = {
                "healthy": dep.healthy,
                "last_seen": dep.last_seen,
                "timeout": dep.timeout,
                "critical": dep.critical
            }
        
        return summary
    
    def get_health_report(self) -> Dict[str, Any]:
        """
        Get comprehensive health report for Webthread.
        
        Returns:
            Full health report including metrics and dependency status
        """
        return {
            "component": "ROC",
            "client_id": self.client_id,
            "timestamp": time.time(),
            "health_status": self._health_status,
            "degraded_components": list(self._degraded_components),
            "metrics": self._get_health_metrics(),
            "dependencies": self._get_dependency_status_summary()
        }
    
    # =========================================================================
    # External Updates
    # =========================================================================
    
    def update_metrics(
        self,
        active_robots: Optional[int] = None,
        commands_processed: Optional[int] = None,
        current_mode: Optional[str] = None,
        ipc_connected: Optional[bool] = None
    ):
        """
        Update metrics from coordinator.
        
        Args:
            active_robots: Number of registered robots
            commands_processed: Total commands processed
            current_mode: Current control mode
            ipc_connected: IPC connection status
        """
        if active_robots is not None:
            self._active_robots = active_robots
        if commands_processed is not None:
            self._commands_processed = commands_processed
        if current_mode is not None:
            self._current_mode = current_mode
        if ipc_connected is not None:
            self._ipc_connected = ipc_connected
    
    def on_dependency_failure(self, callback: Callable[[str, bool], None]):
        """
        Register callback for dependency failures.
        
        Args:
            callback: Function(component_name, is_failed) called on status change
        """
        self._dependency_failure_callbacks.append(callback)
    
    def on_health_status_change(self, callback: Callable[[Dict[str, Any]], None]):
        """
        Register callback for health status changes.
        
        Args:
            callback: Function(health_report) called on status change
        """
        self._health_status_callbacks.append(callback)
    
    # =========================================================================
    # Properties
    # =========================================================================
    
    @property
    def is_running(self) -> bool:
        """Check if agent is running."""
        return self._running
    
    @property
    def health_status(self) -> str:
        """Get current health status."""
        return self._health_status
    
    @property
    def is_degraded(self) -> bool:
        """Check if system is in degraded state."""
        return len(self._degraded_components) > 0
    
    @property
    def degraded_components(self) -> List[str]:
        """Get list of failed critical dependencies."""
        return list(self._degraded_components)
    
    def is_dependency_healthy(self, component: str) -> bool:
        """
        Check if a specific dependency is healthy.
        
        Args:
            component: Dependency name
            
        Returns:
            True if dependency is healthy
        """
        if component in self.dependencies:
            return self.dependencies[component].healthy
        return True  # Unknown dependencies assumed healthy
