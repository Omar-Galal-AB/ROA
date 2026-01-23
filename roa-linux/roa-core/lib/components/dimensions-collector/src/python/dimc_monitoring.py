"""
DIMC Monitoring System - Comprehensive Health and Performance Monitoring

This module provides a complete monitoring solution for DIMC including:
- System resource monitoring (CPU, memory, threads)
- Subsystem health tracking (Bridge, Heartbeat, Sensors)
- Performance profiling and timing
- Data quality monitoring
- Alert generation and escalation
- Diagnostic data collection

Integrates with DIMC Observability for metrics and the Heartbeat agent for health status.
"""

import json
import logging
import os
import sys
import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

# Try to import psutil for system metrics
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class SubsystemStatus(Enum):
    """Status of a DIMC subsystem."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertCategory(Enum):
    """Alert categories for classification."""

    PERFORMANCE = "performance"
    CONNECTION = "connection"
    DATA_QUALITY = "data_quality"
    RESOURCE = "resource"
    SUBSYSTEM = "subsystem"
    SAFETY = "safety"


@dataclass
class Alert:
    """Alert data structure."""

    alert_id: str
    timestamp: float
    severity: AlertSeverity
    category: AlertCategory
    source: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False
    resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "timestamp": self.timestamp,
            "timestamp_iso": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "severity": self.severity.value,
            "category": self.category.value,
            "source": self.source,
            "message": self.message,
            "data": self.data,
            "acknowledged": self.acknowledged,
            "resolved": self.resolved,
        }


@dataclass
class SubsystemHealth:
    """Health status of a subsystem."""

    name: str
    status: SubsystemStatus
    last_check: float
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class SystemResources:
    """System resource snapshot."""

    timestamp: float
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    thread_count: int
    open_files: int
    network_connections: int


@dataclass
class PerformanceStats:
    """Performance statistics."""

    name: str
    call_count: int
    total_time_ms: float
    avg_time_ms: float
    min_time_ms: float
    max_time_ms: float
    p95_time_ms: float
    last_call_time: float


@dataclass
class DataQualityMetrics:
    """Data quality metrics."""

    source: str
    messages_received: int
    messages_valid: int
    messages_invalid: int
    validation_rate: float
    last_message_time: float
    data_gap_count: int
    avg_latency_ms: float
    stale_count: int


@dataclass
class MonitoringConfig:
    """Monitoring system configuration."""

    # Check intervals
    health_check_interval: float = 5.0
    resource_check_interval: float = 10.0
    performance_report_interval: float = 60.0

    # Thresholds
    cpu_warning_percent: float = 70.0
    cpu_critical_percent: float = 90.0
    memory_warning_percent: float = 70.0
    memory_critical_percent: float = 85.0
    thread_warning_count: int = 50
    thread_critical_count: int = 100

    # Data quality thresholds
    data_staleness_threshold_ms: float = 1000.0
    validation_warning_rate: float = 0.95
    validation_critical_rate: float = 0.80

    # Performance thresholds
    latency_warning_ms: float = 50.0
    latency_critical_ms: float = 200.0

    # Alert settings
    alert_cooldown_seconds: float = 60.0
    max_alerts_stored: int = 1000

    # Rate limiting
    max_messages_per_second: int = 1000
    rate_limit_window_seconds: float = 1.0


class PerformanceProfiler:
    """
    Performance profiler for timing critical code paths.

    Usage:
        profiler = PerformanceProfiler()

        with profiler.profile("update_loop"):
            # do work
            pass

        stats = profiler.get_stats("update_loop")
    """

    def __init__(self):
        self._timings: Dict[str, deque] = {}
        self._call_counts: Dict[str, int] = {}
        self._lock = threading.RLock()
        self._max_samples = 1000

    def profile(self, name: str):
        """Context manager for profiling a code section."""
        return _ProfileContext(self, name)

    def record_timing(self, name: str, duration_ms: float):
        """Record a timing measurement."""
        with self._lock:
            if name not in self._timings:
                self._timings[name] = deque(maxlen=self._max_samples)
                self._call_counts[name] = 0

            self._timings[name].append((time.time(), duration_ms))
            self._call_counts[name] += 1

    def get_stats(self, name: str) -> Optional[PerformanceStats]:
        """Get performance statistics for a named operation."""
        with self._lock:
            if name not in self._timings or not self._timings[name]:
                return None

            timings = [t[1] for t in self._timings[name]]
            sorted_timings = sorted(timings)

            return PerformanceStats(
                name=name,
                call_count=self._call_counts[name],
                total_time_ms=sum(timings),
                avg_time_ms=sum(timings) / len(timings),
                min_time_ms=min(timings),
                max_time_ms=max(timings),
                p95_time_ms=(
                    sorted_timings[int(len(sorted_timings) * 0.95)]
                    if len(sorted_timings) > 20
                    else max(timings)
                ),
                last_call_time=self._timings[name][-1][0],
            )

    def get_all_stats(self) -> Dict[str, PerformanceStats]:
        """Get all performance statistics."""
        with self._lock:
            result = {}
            for name in self._timings:
                stats = self.get_stats(name)
                if stats:
                    result[name] = stats
            return result

    def reset(self, name: str = None):
        """Reset statistics for a specific operation or all operations."""
        with self._lock:
            if name:
                self._timings.pop(name, None)
                self._call_counts.pop(name, None)
            else:
                self._timings.clear()
                self._call_counts.clear()


class _ProfileContext:
    """Context manager for profiling."""

    def __init__(self, profiler: PerformanceProfiler, name: str):
        self._profiler = profiler
        self._name = name
        self._start = 0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.perf_counter() - self._start) * 1000
        self._profiler.record_timing(self._name, duration_ms)
        return False


class DataQualityMonitor:
    """
    Monitor data quality from various sources.

    Tracks message validity, latency, staleness, and gaps.
    """

    def __init__(self, config: MonitoringConfig):
        self.config = config
        self._sources: Dict[str, DataQualityMetrics] = {}
        self._lock = threading.RLock()
        self._latency_samples: Dict[str, deque] = {}

    def record_message(self, source: str, valid: bool, latency_ms: float = 0):
        """Record a message from a data source."""
        now = time.time()

        with self._lock:
            if source not in self._sources:
                self._sources[source] = DataQualityMetrics(
                    source=source,
                    messages_received=0,
                    messages_valid=0,
                    messages_invalid=0,
                    validation_rate=1.0,
                    last_message_time=0,
                    data_gap_count=0,
                    avg_latency_ms=0,
                    stale_count=0,
                )
                self._latency_samples[source] = deque(maxlen=100)

            metrics = self._sources[source]
            metrics.messages_received += 1

            if valid:
                metrics.messages_valid += 1
            else:
                metrics.messages_invalid += 1

            # Check for data gap
            if metrics.last_message_time > 0:
                gap_ms = (now - metrics.last_message_time) * 1000
                if gap_ms > self.config.data_staleness_threshold_ms:
                    metrics.data_gap_count += 1

            metrics.last_message_time = now

            # Track latency
            if latency_ms > 0:
                self._latency_samples[source].append(latency_ms)
                samples = list(self._latency_samples[source])
                metrics.avg_latency_ms = sum(samples) / len(samples)

            # Update validation rate
            if metrics.messages_received > 0:
                metrics.validation_rate = metrics.messages_valid / metrics.messages_received

            # Check for stale data
            if latency_ms > self.config.data_staleness_threshold_ms:
                metrics.stale_count += 1

    def get_metrics(self, source: str) -> Optional[DataQualityMetrics]:
        """Get quality metrics for a source."""
        with self._lock:
            return self._sources.get(source)

    def get_all_metrics(self) -> Dict[str, DataQualityMetrics]:
        """Get all quality metrics."""
        with self._lock:
            return self._sources.copy()

    def check_quality(self, source: str) -> Tuple[SubsystemStatus, str]:
        """Check data quality for a source and return status."""
        metrics = self.get_metrics(source)

        if not metrics:
            return SubsystemStatus.UNKNOWN, "No data received"

        now = time.time()
        since_last = now - metrics.last_message_time

        # Check for no recent data
        if since_last > self.config.data_staleness_threshold_ms / 1000 * 5:
            return SubsystemStatus.OFFLINE, f"No data for {since_last:.1f}s"

        # Check validation rate
        if metrics.validation_rate < self.config.validation_critical_rate:
            return (
                SubsystemStatus.UNHEALTHY,
                f"Low validation rate: {metrics.validation_rate:.1%}",
            )

        if metrics.validation_rate < self.config.validation_warning_rate:
            return (
                SubsystemStatus.DEGRADED,
                f"Validation rate warning: {metrics.validation_rate:.1%}",
            )

        # Check latency
        if metrics.avg_latency_ms > self.config.latency_critical_ms:
            return (
                SubsystemStatus.DEGRADED,
                f"High latency: {metrics.avg_latency_ms:.1f}ms",
            )

        return SubsystemStatus.HEALTHY, "OK"


class RateLimiter:
    """
    Rate limiter to protect against data flooding.

    Uses sliding window algorithm.
    """

    def __init__(self, max_per_second: int = 1000, window_seconds: float = 1.0):
        self.max_per_second = max_per_second
        self.window_seconds = window_seconds
        self._timestamps: deque = deque()
        self._lock = threading.RLock()
        self._dropped_count = 0

    def allow(self) -> bool:
        """Check if a message should be allowed."""
        now = time.time()

        with self._lock:
            # Remove old timestamps
            cutoff = now - self.window_seconds
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()

            # Check rate
            if len(self._timestamps) >= self.max_per_second:
                self._dropped_count += 1
                return False

            self._timestamps.append(now)
            return True

    def get_current_rate(self) -> float:
        """Get current message rate per second."""
        now = time.time()

        with self._lock:
            cutoff = now - self.window_seconds
            count = sum(1 for t in self._timestamps if t >= cutoff)
            return count / self.window_seconds

    def get_dropped_count(self) -> int:
        """Get total dropped message count."""
        return self._dropped_count


class DIMCMonitoringSystem:
    """
    Comprehensive monitoring system for DIMC.

    Provides:
    - Subsystem health monitoring
    - System resource tracking
    - Performance profiling
    - Data quality monitoring
    - Alert generation
    - Diagnostic data collection
    """

    def __init__(
        self,
        config: Optional[MonitoringConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize the monitoring system."""
        self.config = config or MonitoringConfig()
        self.logger = logger or logging.getLogger(__name__)

        # Subsystem tracking
        self._subsystem_health: Dict[str, SubsystemHealth] = {}
        self._overall_status = SubsystemStatus.UNKNOWN

        # Components
        self.profiler = PerformanceProfiler()
        self.data_quality = DataQualityMonitor(self.config)
        self.rate_limiters: Dict[str, RateLimiter] = {}

        # Resource tracking
        self._resource_history: deque = deque(maxlen=100)
        self._process = psutil.Process() if PSUTIL_AVAILABLE else None

        # Alerts
        self._alerts: deque = deque(maxlen=self.config.max_alerts_stored)
        self._alert_cooldowns: Dict[str, float] = {}
        self._alert_counter = 0

        # Threading
        self.running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        # Callbacks
        self.on_alert: Optional[Callable[[Alert], None]] = None
        self.on_status_change: Optional[Callable[[SubsystemStatus, SubsystemStatus], None]] = None

        # Statistics
        self.start_time: Optional[float] = None

    def start(self):
        """Start the monitoring system."""
        if self.running:
            return

        self.running = True
        self.start_time = time.time()

        # Initialize subsystems
        self._init_subsystems()

        # Start monitoring thread
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="DIMC-Monitoring"
        )
        self._monitor_thread.start()

        self.logger.info("DIMC Monitoring System started")

    def stop(self):
        """Stop the monitoring system."""
        self.running = False

        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)

        self.logger.info("DIMC Monitoring System stopped")

    def _init_subsystems(self):
        """Initialize subsystem health tracking."""
        subsystems = [
            "bridge",
            "heartbeat",
            "sensor_receiver",
            "obstacle_detection",
            "ros2_publisher",
            "tracking",
            "measurement",
        ]

        for name in subsystems:
            self._subsystem_health[name] = SubsystemHealth(
                name=name, status=SubsystemStatus.UNKNOWN, last_check=0
            )

    def _monitor_loop(self):
        """Main monitoring loop."""
        last_health_check = 0
        last_resource_check = 0
        last_performance_report = 0

        while self.running:
            now = time.time()

            try:
                # Health checks
                if now - last_health_check >= self.config.health_check_interval:
                    self._check_subsystems()
                    last_health_check = now

                # Resource monitoring
                if now - last_resource_check >= self.config.resource_check_interval:
                    self._check_resources()
                    last_resource_check = now

                # Performance reports
                if now - last_performance_report >= self.config.performance_report_interval:
                    self._log_performance_report()
                    last_performance_report = now

            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")

            time.sleep(1.0)

    def _check_subsystems(self):
        """Check all subsystem health."""
        old_overall = self._overall_status

        unhealthy_count = 0
        degraded_count = 0

        for name, health in self._subsystem_health.items():
            # Check each subsystem
            status, details = self._check_subsystem(name)

            health.status = status
            health.last_check = time.time()
            health.details = {"message": details}

            if status == SubsystemStatus.UNHEALTHY or status == SubsystemStatus.OFFLINE:
                unhealthy_count += 1
            elif status == SubsystemStatus.DEGRADED:
                degraded_count += 1

        # Determine overall status
        if unhealthy_count > 0:
            self._overall_status = SubsystemStatus.UNHEALTHY
        elif degraded_count > 0:
            self._overall_status = SubsystemStatus.DEGRADED
        else:
            self._overall_status = SubsystemStatus.HEALTHY

        # Notify on change
        if old_overall != self._overall_status and self.on_status_change:
            try:
                self.on_status_change(old_overall, self._overall_status)
            except Exception as e:
                self.logger.error(f"Status change callback error: {e}")

    def _check_subsystem(self, name: str) -> Tuple[SubsystemStatus, str]:
        """Check a specific subsystem's health."""
        # Check data quality for data-producing subsystems
        if name in ["bridge", "sensor_receiver"]:
            return self.data_quality.check_quality(name)

        # Default: check if subsystem is registered as healthy
        health = self._subsystem_health.get(name)
        if health and health.status != SubsystemStatus.UNKNOWN:
            return health.status, health.details.get("message", "OK")

        return SubsystemStatus.UNKNOWN, "Not checked"

    def _check_resources(self):
        """Check system resources."""
        if not PSUTIL_AVAILABLE or not self._process:
            return

        try:
            resources = SystemResources(
                timestamp=time.time(),
                cpu_percent=self._process.cpu_percent(),
                memory_percent=self._process.memory_percent(),
                memory_used_mb=self._process.memory_info().rss / 1024 / 1024,
                thread_count=self._process.num_threads(),
                open_files=len(self._process.open_files()),
                network_connections=len(self._process.connections()),
            )

            self._resource_history.append(resources)

            # Check thresholds and generate alerts
            if resources.cpu_percent > self.config.cpu_critical_percent:
                self._generate_alert(
                    AlertSeverity.CRITICAL,
                    AlertCategory.RESOURCE,
                    "cpu_critical",
                    f"CPU usage critical: {resources.cpu_percent:.1f}%",
                    {"cpu_percent": resources.cpu_percent},
                )
            elif resources.cpu_percent > self.config.cpu_warning_percent:
                self._generate_alert(
                    AlertSeverity.WARNING,
                    AlertCategory.RESOURCE,
                    "cpu_warning",
                    f"CPU usage warning: {resources.cpu_percent:.1f}%",
                    {"cpu_percent": resources.cpu_percent},
                )

            if resources.memory_percent > self.config.memory_critical_percent:
                self._generate_alert(
                    AlertSeverity.CRITICAL,
                    AlertCategory.RESOURCE,
                    "memory_critical",
                    f"Memory usage critical: {resources.memory_percent:.1f}%",
                    {
                        "memory_percent": resources.memory_percent,
                        "memory_mb": resources.memory_used_mb,
                    },
                )
            elif resources.memory_percent > self.config.memory_warning_percent:
                self._generate_alert(
                    AlertSeverity.WARNING,
                    AlertCategory.RESOURCE,
                    "memory_warning",
                    f"Memory usage warning: {resources.memory_percent:.1f}%",
                    {
                        "memory_percent": resources.memory_percent,
                        "memory_mb": resources.memory_used_mb,
                    },
                )

            if resources.thread_count > self.config.thread_critical_count:
                self._generate_alert(
                    AlertSeverity.ERROR,
                    AlertCategory.RESOURCE,
                    "threads_critical",
                    f"Thread count critical: {resources.thread_count}",
                    {"thread_count": resources.thread_count},
                )

        except Exception as e:
            self.logger.debug(f"Resource check error: {e}")

    def _log_performance_report(self):
        """Log performance report."""
        stats = self.profiler.get_all_stats()
        if not stats:
            return

        self.logger.info("=== DIMC Performance Report ===")
        for name, s in stats.items():
            self.logger.info(
                f"  {name}: calls={s.call_count}, avg={s.avg_time_ms:.2f}ms, "
                f"p95={s.p95_time_ms:.2f}ms, max={s.max_time_ms:.2f}ms"
            )

    def _generate_alert(
        self,
        severity: AlertSeverity,
        category: AlertCategory,
        alert_type: str,
        message: str,
        data: Dict[str, Any] = None,
    ):
        """Generate an alert with cooldown."""
        now = time.time()

        # Check cooldown
        cooldown_key = f"{category.value}:{alert_type}"
        last_alert = self._alert_cooldowns.get(cooldown_key, 0)

        if now - last_alert < self.config.alert_cooldown_seconds:
            return

        self._alert_cooldowns[cooldown_key] = now

        # Create alert
        self._alert_counter += 1
        alert = Alert(
            alert_id=f"DIMC-{self._alert_counter:06d}",
            timestamp=now,
            severity=severity,
            category=category,
            source="monitoring",
            message=message,
            data=data or {},
        )

        with self._lock:
            self._alerts.append(alert)

        # Log alert
        log_method = {
            AlertSeverity.INFO: self.logger.info,
            AlertSeverity.WARNING: self.logger.warning,
            AlertSeverity.ERROR: self.logger.error,
            AlertSeverity.CRITICAL: self.logger.critical,
        }.get(severity, self.logger.warning)

        log_method(f"ALERT [{alert.alert_id}] {message}")

        # Notify callback
        if self.on_alert:
            try:
                self.on_alert(alert)
            except Exception as e:
                self.logger.error(f"Alert callback error: {e}")

    # =========================================================================
    # Public API
    # =========================================================================

    def update_subsystem_health(
        self,
        name: str,
        status: SubsystemStatus,
        details: Dict[str, Any] = None,
        error: str = None,
    ):
        """
        Update health status of a subsystem.

        Call this from subsystem code to report health.
        """
        with self._lock:
            if name not in self._subsystem_health:
                self._subsystem_health[name] = SubsystemHealth(
                    name=name, status=status, last_check=time.time()
                )
            else:
                self._subsystem_health[name].status = status
                self._subsystem_health[name].last_check = time.time()
                self._subsystem_health[name].details = details or {}
                self._subsystem_health[name].error = error

    def get_rate_limiter(self, source: str) -> RateLimiter:
        """Get or create a rate limiter for a data source."""
        if source not in self.rate_limiters:
            self.rate_limiters[source] = RateLimiter(
                max_per_second=self.config.max_messages_per_second,
                window_seconds=self.config.rate_limit_window_seconds,
            )
        return self.rate_limiters[source]

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status report."""
        return {
            "overall_status": self._overall_status.value,
            "uptime_seconds": time.time() - self.start_time if self.start_time else 0,
            "subsystems": {
                name: {
                    "status": health.status.value,
                    "last_check": health.last_check,
                    "details": health.details,
                    "error": health.error,
                }
                for name, health in self._subsystem_health.items()
            },
            "resources": self._get_latest_resources(),
            "alerts": {
                "total": len(self._alerts),
                "unacknowledged": sum(1 for a in self._alerts if not a.acknowledged),
                "unresolved": sum(1 for a in self._alerts if not a.resolved),
            },
        }

    def _get_latest_resources(self) -> Optional[Dict[str, Any]]:
        """Get latest resource snapshot."""
        if not self._resource_history:
            return None

        r = self._resource_history[-1]
        return {
            "timestamp": r.timestamp,
            "cpu_percent": r.cpu_percent,
            "memory_percent": r.memory_percent,
            "memory_used_mb": r.memory_used_mb,
            "thread_count": r.thread_count,
            "open_files": r.open_files,
            "network_connections": r.network_connections,
        }

    def get_alerts(
        self,
        severity: AlertSeverity = None,
        unacknowledged_only: bool = False,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get alerts with optional filtering."""
        with self._lock:
            alerts = list(self._alerts)

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        if unacknowledged_only:
            alerts = [a for a in alerts if not a.acknowledged]

        # Sort by timestamp descending
        alerts.sort(key=lambda a: a.timestamp, reverse=True)

        return [a.to_dict() for a in alerts[:limit]]

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        with self._lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id:
                    alert.acknowledged = True
                    return True
        return False

    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert."""
        with self._lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id:
                    alert.resolved = True
                    return True
        return False

    def get_diagnostics(self) -> Dict[str, Any]:
        """Get comprehensive diagnostic data."""
        return {
            "status": self.get_status(),
            "performance": {
                name: {
                    "call_count": s.call_count,
                    "avg_time_ms": s.avg_time_ms,
                    "p95_time_ms": s.p95_time_ms,
                    "max_time_ms": s.max_time_ms,
                }
                for name, s in self.profiler.get_all_stats().items()
            },
            "data_quality": {
                name: {
                    "messages_received": m.messages_received,
                    "validation_rate": m.validation_rate,
                    "avg_latency_ms": m.avg_latency_ms,
                    "data_gap_count": m.data_gap_count,
                    "stale_count": m.stale_count,
                }
                for name, m in self.data_quality.get_all_metrics().items()
            },
            "rate_limiters": {
                name: {
                    "current_rate": rl.get_current_rate(),
                    "dropped_count": rl.get_dropped_count(),
                }
                for name, rl in self.rate_limiters.items()
            },
            "recent_alerts": self.get_alerts(limit=10),
        }

    def generate_alert(
        self,
        severity: str,
        category: str,
        source: str,
        message: str,
        data: Dict[str, Any] = None,
    ):
        """
        Generate a custom alert from external code.

        Args:
            severity: "info", "warning", "error", "critical"
            category: "performance", "connection", "data_quality", "resource", "subsystem", "safety"
            source: Source identifier
            message: Alert message
            data: Additional data
        """
        sev = (
            AlertSeverity(severity)
            if severity in [s.value for s in AlertSeverity]
            else AlertSeverity.WARNING
        )
        cat = (
            AlertCategory(category)
            if category in [c.value for c in AlertCategory]
            else AlertCategory.SUBSYSTEM
        )

        self._generate_alert(sev, cat, f"{source}_{category}", message, data)
