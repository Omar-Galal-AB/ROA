"""
Bridge Health Agent - UE5 Bridge monitoring and auto-recovery.

Monitors the health of the dual-port TCP bridge between ROC and UE5:
- Tracks connection status on both ports (9876, 9877)
- Monitors message latency and throughput
- Detects bridge degradation
- Auto-reconnects on failures
- Reports bridge health to Webthread

Based on the dual-port architecture in DUAL_PORT_SOLUTION.md.
"""

import asyncio
import json
import logging
import socket
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Deque, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .ue5_bridge.ipc_handler import UE5IPCHandler


class BridgeStatus(Enum):
    """Overall bridge health status."""
    UNKNOWN = auto()
    HEALTHY = auto()
    DEGRADED = auto()
    FAILED = auto()
    RECONNECTING = auto()


@dataclass
class BridgeMetrics:
    """Bridge performance metrics."""
    # Connection status
    receive_port_open: bool = False  # Port 9876
    send_port_open: bool = False  # Port 9877
    socat_running: bool = False
    connection_state: str = "disconnected"
    
    # Performance
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    messages_sent: int = 0
    messages_received: int = 0
    messages_dropped: int = 0
    
    # Heartbeat
    last_heartbeat_age_s: float = float('inf')
    heartbeat_healthy: bool = False
    
    # Reconnection
    reconnect_attempts: int = 0
    last_reconnect_time: float = 0.0
    
    # Timestamp
    timestamp: float = field(default_factory=time.time)


@dataclass
class BridgeHealthAgentConfig:
    """Configuration for BridgeHealthAgent."""
    # Health check settings
    health_check_rate_hz: float = 1.0  # 1Hz health checks
    
    # Port configuration
    receive_port: int = 9876  # UE5 -> Linux
    send_port: int = 9877  # Linux -> UE5
    ue5_host: str = "localhost"  # Or Windows IP for cross-network
    
    # Thresholds
    latency_warning_ms: float = 100.0
    latency_critical_ms: float = 500.0
    heartbeat_timeout_ms: float = 3000.0  # 3 missed at 1Hz
    
    # Auto-recovery
    auto_reconnect: bool = True
    max_reconnect_attempts: int = 3
    reconnect_delay_s: float = 2.0
    reconnect_backoff_multiplier: float = 1.5
    
    # Socat relay (for WSL->Windows)
    check_socat: bool = True
    socat_process_name: str = "socat"
    
    # Latency tracking
    latency_history_size: int = 100
    
    # Reporting
    report_to_webthread: bool = True


class BridgeHealthAgent:
    """
    Monitors and manages UE5 Bridge health.
    
    Responsibilities:
    - Monitor dual-port connection status (9876, 9877)
    - Track bridge performance metrics (latency, throughput)
    - Auto-reconnect on failures
    - Report bridge health to Webthread
    - Detect and alert on degradation
    
    Works with UE5IPCHandler to provide comprehensive bridge monitoring.
    """
    
    def __init__(
        self,
        ipc_handler: 'UE5IPCHandler',
        config: Optional[BridgeHealthAgentConfig] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize BridgeHealthAgent.
        
        Args:
            ipc_handler: UE5 IPC handler to monitor
            config: Agent configuration
            logger: Logger instance
        """
        self.ipc = ipc_handler
        self.config = config or BridgeHealthAgentConfig()
        self.logger = logger or logging.getLogger(__name__)
        
        # State
        self._running = False
        self._health_check_task: Optional[asyncio.Task] = None
        self._status = BridgeStatus.UNKNOWN
        self._metrics = BridgeMetrics()
        
        # Latency tracking
        self._latency_history: Deque[float] = deque(
            maxlen=self.config.latency_history_size
        )
        
        # Message tracking (for throughput calculation)
        self._last_msg_count = 0
        self._last_msg_time = time.time()
        self._messages_per_second = 0.0
        
        # Reconnection state
        self._reconnect_count = 0
        self._last_reconnect_attempt = 0.0
        self._consecutive_failures = 0
        
        # Callbacks
        self._status_change_callbacks: List[Callable[[BridgeStatus], None]] = []
        self._health_report_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        
        self.logger.info("BridgeHealthAgent initialized")
    
    # =========================================================================
    # Lifecycle
    # =========================================================================
    
    async def start(self) -> bool:
        """
        Start the bridge health agent.
        
        Returns:
            True if started successfully.
        """
        self.logger.info("Starting BridgeHealthAgent")
        
        self._running = True
        self._status = BridgeStatus.UNKNOWN
        
        # Initial health check
        await self._perform_health_check()
        
        # Start monitoring loop
        interval = 1.0 / self.config.health_check_rate_hz
        self._health_check_task = asyncio.create_task(
            self._health_check_loop(interval)
        )
        
        self.logger.info("BridgeHealthAgent started")
        return True
    
    async def stop(self):
        """Stop the bridge health agent."""
        self.logger.info("Stopping BridgeHealthAgent")
        
        self._running = False
        
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("BridgeHealthAgent stopped")
    
    # =========================================================================
    # Health Checking
    # =========================================================================
    
    async def _health_check_loop(self, interval: float):
        """Background loop for health checks."""
        while self._running:
            try:
                await self._perform_health_check()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in health check loop: {e}")
                await asyncio.sleep(interval)
    
    async def _perform_health_check(self):
        """Perform comprehensive bridge health check."""
        old_status = self._status
        
        # Check port availability
        receive_open = self._check_port_open(self.config.receive_port)
        send_open = self._check_port_open(self.config.send_port)
        
        # Check socat relay (if enabled)
        socat_running = False
        if self.config.check_socat:
            socat_running = self._check_socat_running()
        
        # Get IPC handler stats
        ipc_stats = self.ipc.get_statistics()
        connection_state = ipc_stats.get("state", "DISCONNECTED")
        
        # Check heartbeat
        heartbeat_healthy = self.ipc.heartbeat_healthy
        last_heartbeat = ipc_stats.get("last_heartbeat", 0)
        heartbeat_age = time.time() - last_heartbeat if last_heartbeat > 0 else float('inf')
        
        # Calculate latency metrics
        avg_latency, max_latency = self._calculate_latency_metrics()
        
        # Update metrics
        self._metrics = BridgeMetrics(
            receive_port_open=receive_open,
            send_port_open=send_open,
            socat_running=socat_running,
            connection_state=connection_state,
            avg_latency_ms=avg_latency,
            max_latency_ms=max_latency,
            messages_sent=ipc_stats.get("messages_sent", 0),
            messages_received=ipc_stats.get("messages_received", 0),
            messages_dropped=0,  # Would need to track this in IPC handler
            last_heartbeat_age_s=heartbeat_age,
            heartbeat_healthy=heartbeat_healthy,
            reconnect_attempts=self._reconnect_count,
            last_reconnect_time=self._last_reconnect_attempt,
            timestamp=time.time()
        )
        
        # Determine overall status
        new_status = self._determine_status()
        
        if new_status != old_status:
            self._status = new_status
            self.logger.info(f"Bridge status changed: {old_status.name} -> {new_status.name}")
            await self._notify_status_change(new_status)
        
        # Handle failures
        if new_status == BridgeStatus.FAILED:
            self._consecutive_failures += 1
            
            if self.config.auto_reconnect:
                await self._attempt_reconnect()
        else:
            self._consecutive_failures = 0
        
        # Check for degradation warnings
        self._check_degradation_warnings()
    
    def _determine_status(self) -> BridgeStatus:
        """Determine overall bridge status from metrics."""
        m = self._metrics
        
        # Failed: No connection at all
        if not m.receive_port_open and not m.send_port_open:
            return BridgeStatus.FAILED
        
        if m.connection_state == "DISCONNECTED":
            return BridgeStatus.FAILED
        
        if m.connection_state == "ERROR":
            return BridgeStatus.FAILED
        
        if m.connection_state == "RECONNECTING":
            return BridgeStatus.RECONNECTING
        
        # Degraded: Connection exists but with issues
        if not m.heartbeat_healthy:
            return BridgeStatus.DEGRADED
        
        if m.avg_latency_ms > self.config.latency_critical_ms:
            return BridgeStatus.DEGRADED
        
        if not m.receive_port_open or not m.send_port_open:
            return BridgeStatus.DEGRADED
        
        if self.config.check_socat and not m.socat_running:
            return BridgeStatus.DEGRADED
        
        # Healthy
        if m.connection_state == "CONNECTED" and m.heartbeat_healthy:
            return BridgeStatus.HEALTHY
        
        return BridgeStatus.UNKNOWN
    
    def _check_degradation_warnings(self):
        """Log warnings for degraded conditions."""
        m = self._metrics
        
        if m.avg_latency_ms > self.config.latency_warning_ms:
            self.logger.warning(
                f"Bridge latency elevated: {m.avg_latency_ms:.1f}ms "
                f"(warning threshold: {self.config.latency_warning_ms}ms)"
            )
        
        if m.last_heartbeat_age_s > self.config.heartbeat_timeout_ms / 1000:
            self.logger.warning(
                f"Bridge heartbeat stale: {m.last_heartbeat_age_s:.1f}s since last heartbeat"
            )
    
    # =========================================================================
    # Port and Process Checks
    # =========================================================================
    
    def _check_port_open(self, port: int) -> bool:
        """
        Check if a port is open/listening.
        
        Args:
            port: Port number to check
            
        Returns:
            True if port is open
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.1)
                result = sock.connect_ex(('localhost', port))
                return result == 0
        except Exception:
            return False
    
    def _check_socat_running(self) -> bool:
        """
        Check if socat relay process is running.
        
        Returns:
            True if socat process found
        """
        try:
            result = subprocess.run(
                ["pgrep", "-f", self.config.socat_process_name],
                capture_output=True,
                timeout=1.0
            )
            return result.returncode == 0
        except Exception:
            return False
    
    # =========================================================================
    # Latency Tracking
    # =========================================================================
    
    def record_message_latency(self, latency_ms: float):
        """
        Record message round-trip latency.
        
        Args:
            latency_ms: Latency in milliseconds
        """
        self._latency_history.append(latency_ms)
    
    def _calculate_latency_metrics(self) -> tuple:
        """
        Calculate average and max latency from history.
        
        Returns:
            (avg_latency_ms, max_latency_ms)
        """
        if not self._latency_history:
            return 0.0, 0.0
        
        avg = sum(self._latency_history) / len(self._latency_history)
        max_val = max(self._latency_history)
        
        return round(avg, 2), round(max_val, 2)
    
    # =========================================================================
    # Auto-Reconnect
    # =========================================================================
    
    async def _attempt_reconnect(self):
        """Attempt to reconnect the bridge."""
        # Check if we've exceeded max attempts
        if self._reconnect_count >= self.config.max_reconnect_attempts:
            self.logger.error(
                f"Bridge reconnect failed after {self._reconnect_count} attempts, "
                "manual intervention required"
            )
            return
        
        # Check reconnect delay (with exponential backoff)
        time_since_last = time.time() - self._last_reconnect_attempt
        delay = self.config.reconnect_delay_s * (
            self.config.reconnect_backoff_multiplier ** self._reconnect_count
        )
        
        if time_since_last < delay:
            return  # Too soon
        
        self._reconnect_count += 1
        self._last_reconnect_attempt = time.time()
        self._status = BridgeStatus.RECONNECTING
        
        self.logger.info(
            f"Attempting bridge reconnect ({self._reconnect_count}/{self.config.max_reconnect_attempts})"
        )
        
        try:
            # Disconnect first
            await self.ipc.disconnect()
            
            # Wait a moment
            await asyncio.sleep(0.5)
            
            # Reconnect
            success = await self.ipc.connect()
            
            if success:
                self.logger.info("Bridge reconnect successful")
                self._reconnect_count = 0  # Reset on success
            else:
                self.logger.warning("Bridge reconnect failed")
                
        except Exception as e:
            self.logger.error(f"Error during bridge reconnect: {e}")
    
    def reset_reconnect_counter(self):
        """Reset reconnect counter (call after manual intervention)."""
        self._reconnect_count = 0
        self._consecutive_failures = 0
    
    # =========================================================================
    # Health Reporting
    # =========================================================================
    
    def get_health_report(self) -> Dict[str, Any]:
        """
        Get comprehensive bridge health report.
        
        Returns:
            Full health report for Webthread
        """
        return {
            "component": "ROC_Bridge",
            "timestamp": time.time(),
            "status": self._status.name.lower(),
            "metrics": {
                "receive_port_open": self._metrics.receive_port_open,
                "send_port_open": self._metrics.send_port_open,
                "socat_running": self._metrics.socat_running,
                "connection_state": self._metrics.connection_state,
                "avg_latency_ms": self._metrics.avg_latency_ms,
                "max_latency_ms": self._metrics.max_latency_ms,
                "messages_sent": self._metrics.messages_sent,
                "messages_received": self._metrics.messages_received,
                "heartbeat_healthy": self._metrics.heartbeat_healthy,
                "last_heartbeat_age_s": self._metrics.last_heartbeat_age_s
            },
            "reconnect_info": {
                "attempts": self._reconnect_count,
                "max_attempts": self.config.max_reconnect_attempts,
                "auto_reconnect_enabled": self.config.auto_reconnect
            }
        }
    
    async def _notify_status_change(self, new_status: BridgeStatus):
        """Notify callbacks of status change."""
        for callback in self._status_change_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(new_status)
                else:
                    callback(new_status)
            except Exception as e:
                self.logger.error(f"Error in status change callback: {e}")
    
    # =========================================================================
    # Callbacks
    # =========================================================================
    
    def on_status_change(self, callback: Callable[[BridgeStatus], None]):
        """
        Register callback for status changes.
        
        Args:
            callback: Function(new_status) called on status change
        """
        self._status_change_callbacks.append(callback)
    
    def on_health_report(self, callback: Callable[[Dict[str, Any]], None]):
        """
        Register callback for health reports.
        
        Args:
            callback: Function(health_report) called periodically
        """
        self._health_report_callbacks.append(callback)
    
    # =========================================================================
    # Properties
    # =========================================================================
    
    @property
    def status(self) -> BridgeStatus:
        """Get current bridge status."""
        return self._status
    
    @property
    def is_healthy(self) -> bool:
        """Check if bridge is healthy."""
        return self._status == BridgeStatus.HEALTHY
    
    @property
    def is_connected(self) -> bool:
        """Check if bridge is connected (healthy or degraded)."""
        return self._status in (BridgeStatus.HEALTHY, BridgeStatus.DEGRADED)
    
    @property
    def metrics(self) -> BridgeMetrics:
        """Get current metrics."""
        return self._metrics
    
    @property
    def consecutive_failures(self) -> int:
        """Get number of consecutive health check failures."""
        return self._consecutive_failures
