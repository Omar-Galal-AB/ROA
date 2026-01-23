"""
DIMC Connection Monitor - Health monitoring for UE5 Bridge connection

This module provides continuous health monitoring for the DIMC ↔ UE5 bridge,
tracking connection quality, latency, and triggering alerts on issues.

Features:
- Periodic health checks
- Latency measurement
- Connection quality scoring
- Alert generation for degraded connections
- Statistics collection for observability
"""

import time
import threading
import logging
from enum import Enum, auto
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime


class ConnectionHealth(Enum):
    """Connection health status."""
    HEALTHY = auto()      # All metrics normal
    DEGRADED = auto()     # Some issues but functional
    UNHEALTHY = auto()    # Significant issues
    DISCONNECTED = auto() # Not connected


@dataclass
class HealthMetrics:
    """Health metrics snapshot."""
    timestamp: float
    health: ConnectionHealth
    latency_ms: float
    packet_loss_percent: float
    messages_per_second: float
    errors_last_minute: int
    uptime_seconds: float
    quality_score: float  # 0.0 to 1.0


@dataclass
class MonitorConfig:
    """Connection monitor configuration."""
    # Check intervals
    health_check_interval: float = 5.0  # Check every 5 seconds
    latency_check_interval: float = 10.0  # Ping every 10 seconds
    stats_window_seconds: int = 60  # Rolling window for stats
    
    # Thresholds
    latency_warning_ms: float = 100.0
    latency_critical_ms: float = 500.0
    packet_loss_warning_percent: float = 5.0
    packet_loss_critical_percent: float = 20.0
    min_messages_per_second: float = 1.0
    
    # Alerting
    alert_cooldown_seconds: float = 60.0  # Min time between alerts


class ConnectionMonitor:
    """
    Monitor for DIMC UE5 bridge connection health.
    
    Provides continuous monitoring of the connection between DIMC and UE5,
    tracking key health metrics and generating alerts when issues occur.
    """
    
    def __init__(self, connector, config: Optional[MonitorConfig] = None,
                 logger: Optional[logging.Logger] = None):
        """
        Initialize the connection monitor.
        
        Args:
            connector: DIMCUe5Connector instance to monitor
            config: Monitor configuration
            logger: Logger instance
        """
        self.connector = connector
        self.config = config or MonitorConfig()
        self.logger = logger or logging.getLogger(__name__)
        
        # State
        self.running = False
        self.current_health = ConnectionHealth.DISCONNECTED
        self.start_time: Optional[float] = None
        
        # Metrics collection
        self._latency_samples: deque = deque(maxlen=100)
        self._message_timestamps: deque = deque(maxlen=1000)
        self._error_timestamps: deque = deque(maxlen=100)
        self._ping_results: deque = deque(maxlen=20)
        
        # Threading
        self._monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        
        # Callbacks
        self.on_health_changed: Optional[Callable[[ConnectionHealth, ConnectionHealth], None]] = None
        self.on_alert: Optional[Callable[[str, str, Dict], None]] = None
        
        # Alert tracking
        self._last_alert_time: Dict[str, float] = {}
        
    def start(self):
        """Start the connection monitor."""
        if self.running:
            return
            
        self.running = True
        self.start_time = time.time()
        
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        
        self.logger.info("Connection monitor started")
        
    def stop(self):
        """Stop the connection monitor."""
        self.running = False
        
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
            
        self.logger.info("Connection monitor stopped")
        
    def record_message(self):
        """Record that a message was sent/received."""
        with self._lock:
            self._message_timestamps.append(time.time())
            
    def record_error(self, error_type: str = "unknown"):
        """Record an error occurrence."""
        with self._lock:
            self._error_timestamps.append((time.time(), error_type))
            
    def record_latency(self, latency_ms: float):
        """Record a latency measurement."""
        with self._lock:
            self._latency_samples.append((time.time(), latency_ms))
            
    def get_current_health(self) -> ConnectionHealth:
        """Get current connection health status."""
        return self.current_health
        
    def get_metrics(self) -> HealthMetrics:
        """Get current health metrics snapshot."""
        now = time.time()
        
        with self._lock:
            # Calculate latency
            recent_latencies = [
                lat for ts, lat in self._latency_samples
                if now - ts < self.config.stats_window_seconds
            ]
            avg_latency = sum(recent_latencies) / len(recent_latencies) if recent_latencies else 0
            
            # Calculate message rate
            recent_messages = [
                ts for ts in self._message_timestamps
                if now - ts < self.config.stats_window_seconds
            ]
            msg_per_sec = len(recent_messages) / self.config.stats_window_seconds
            
            # Calculate error rate
            recent_errors = [
                ts for ts, _ in self._error_timestamps
                if now - ts < 60  # Last minute
            ]
            
            # Calculate packet loss from ping results
            if self._ping_results:
                successful = sum(1 for success in self._ping_results if success)
                packet_loss = (1 - successful / len(self._ping_results)) * 100
            else:
                packet_loss = 0
                
            # Calculate uptime
            uptime = now - self.start_time if self.start_time else 0
            
            # Calculate quality score
            quality_score = self._calculate_quality_score(
                avg_latency, packet_loss, msg_per_sec, len(recent_errors)
            )
            
        return HealthMetrics(
            timestamp=now,
            health=self.current_health,
            latency_ms=avg_latency,
            packet_loss_percent=packet_loss,
            messages_per_second=msg_per_sec,
            errors_last_minute=len(recent_errors),
            uptime_seconds=uptime,
            quality_score=quality_score
        )
        
    def get_statistics(self) -> Dict[str, Any]:
        """Get detailed connection statistics."""
        metrics = self.get_metrics()
        connector_stats = self.connector.get_statistics()
        
        return {
            "health": {
                "status": self.current_health.name,
                "quality_score": metrics.quality_score,
                "uptime_seconds": metrics.uptime_seconds
            },
            "performance": {
                "latency_ms": metrics.latency_ms,
                "messages_per_second": metrics.messages_per_second,
                "packet_loss_percent": metrics.packet_loss_percent
            },
            "errors": {
                "errors_last_minute": metrics.errors_last_minute,
                "last_error": connector_stats.get("last_error")
            },
            "connection": connector_stats,
            "thresholds": {
                "latency_warning_ms": self.config.latency_warning_ms,
                "latency_critical_ms": self.config.latency_critical_ms,
                "packet_loss_warning_percent": self.config.packet_loss_warning_percent
            }
        }
        
    def _monitor_loop(self):
        """Main monitoring loop."""
        last_health_check = 0
        last_latency_check = 0
        
        while self.running:
            now = time.time()
            
            try:
                # Periodic health check
                if now - last_health_check >= self.config.health_check_interval:
                    self._check_health()
                    last_health_check = now
                    
                # Periodic latency check
                if now - last_latency_check >= self.config.latency_check_interval:
                    self._check_latency()
                    last_latency_check = now
                    
            except Exception as e:
                self.logger.error(f"Monitor loop error: {e}")
                self.record_error("monitor_error")
                
            time.sleep(1.0)
            
    def _check_health(self):
        """Perform health check and update status."""
        old_health = self.current_health
        
        # Check if connected
        if not self.connector.is_connected():
            new_health = ConnectionHealth.DISCONNECTED
        else:
            # Get current metrics
            metrics = self.get_metrics()
            
            # Determine health based on metrics
            if (metrics.latency_ms > self.config.latency_critical_ms or
                metrics.packet_loss_percent > self.config.packet_loss_critical_percent or
                metrics.errors_last_minute > 10):
                new_health = ConnectionHealth.UNHEALTHY
                
            elif (metrics.latency_ms > self.config.latency_warning_ms or
                  metrics.packet_loss_percent > self.config.packet_loss_warning_percent or
                  metrics.errors_last_minute > 3):
                new_health = ConnectionHealth.DEGRADED
                
            else:
                new_health = ConnectionHealth.HEALTHY
                
        # Update health status
        self.current_health = new_health
        
        # Notify if changed
        if old_health != new_health:
            self.logger.info(f"Connection health changed: {old_health.name} -> {new_health.name}")
            
            if self.on_health_changed:
                try:
                    self.on_health_changed(old_health, new_health)
                except Exception as e:
                    self.logger.error(f"Health change callback error: {e}")
                    
            # Generate alerts for degraded/unhealthy states
            if new_health in (ConnectionHealth.DEGRADED, ConnectionHealth.UNHEALTHY):
                self._generate_alert(new_health)
                
    def _check_latency(self):
        """Check connection latency via ping."""
        if not self.connector.is_connected():
            return
            
        try:
            start = time.time()
            
            # Send ping command
            response = self.connector.send_command("ping", {"timestamp": start}, timeout=5.0)
            
            if response:
                latency_ms = (time.time() - start) * 1000
                self.record_latency(latency_ms)
                self._ping_results.append(True)
                
                # Alert on high latency
                if latency_ms > self.config.latency_critical_ms:
                    self._generate_alert_message(
                        "high_latency",
                        f"Connection latency critical: {latency_ms:.1f}ms",
                        {"latency_ms": latency_ms}
                    )
            else:
                self._ping_results.append(False)
                self.record_error("ping_timeout")
                
        except Exception as e:
            self._ping_results.append(False)
            self.record_error("ping_error")
            self.logger.debug(f"Latency check failed: {e}")
            
    def _calculate_quality_score(self, latency_ms: float, packet_loss: float,
                                  msg_rate: float, errors: int) -> float:
        """Calculate overall connection quality score (0.0 to 1.0)."""
        score = 1.0
        
        # Latency penalty
        if latency_ms > self.config.latency_critical_ms:
            score -= 0.4
        elif latency_ms > self.config.latency_warning_ms:
            score -= 0.2
            
        # Packet loss penalty
        if packet_loss > self.config.packet_loss_critical_percent:
            score -= 0.3
        elif packet_loss > self.config.packet_loss_warning_percent:
            score -= 0.15
            
        # Low message rate penalty
        if msg_rate < self.config.min_messages_per_second:
            score -= 0.1
            
        # Error penalty
        if errors > 10:
            score -= 0.2
        elif errors > 3:
            score -= 0.1
            
        return max(0.0, min(1.0, score))
        
    def _generate_alert(self, health: ConnectionHealth):
        """Generate alert for health status change."""
        severity = "warning" if health == ConnectionHealth.DEGRADED else "critical"
        metrics = self.get_metrics()
        
        self._generate_alert_message(
            f"health_{health.name.lower()}",
            f"UE5 Bridge connection {health.name.lower()}",
            {
                "health": health.name,
                "latency_ms": metrics.latency_ms,
                "packet_loss_percent": metrics.packet_loss_percent,
                "quality_score": metrics.quality_score
            },
            severity
        )
        
    def _generate_alert_message(self, alert_type: str, message: str,
                                 data: Dict[str, Any], severity: str = "warning"):
        """Generate an alert with cooldown checking."""
        now = time.time()
        
        # Check cooldown
        last_alert = self._last_alert_time.get(alert_type, 0)
        if now - last_alert < self.config.alert_cooldown_seconds:
            return
            
        self._last_alert_time[alert_type] = now
        
        self.logger.warning(f"ALERT [{severity}] {message}")
        
        if self.on_alert:
            try:
                self.on_alert(alert_type, message, {
                    "severity": severity,
                    "timestamp": now,
                    **data
                })
            except Exception as e:
                self.logger.error(f"Alert callback error: {e}")
