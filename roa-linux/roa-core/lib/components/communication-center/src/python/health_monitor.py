"""
Health Monitor

Monitors component health including CPU, memory, and performance metrics.
Enhanced with advanced monitoring capabilities.
"""

import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import psutil


class HealthLevel(Enum):
    """Health levels for component status"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"


@dataclass
class PerformanceMetrics:
    """Performance metrics with history"""

    response_times_ms: deque = field(default_factory=lambda: deque(maxlen=100))
    operation_counts: Dict[str, int] = field(default_factory=dict)
    error_counts: Dict[str, int] = field(default_factory=dict)

    @property
    def avg_response_time_ms(self) -> float:
        if not self.response_times_ms:
            return 0.0
        return sum(self.response_times_ms) / len(self.response_times_ms)

    @property
    def p95_response_time_ms(self) -> float:
        if len(self.response_times_ms) < 2:
            return 0.0
        sorted_times = sorted(self.response_times_ms)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[min(idx, len(sorted_times) - 1)]


class HealthMonitor:
    """
    Monitors COMC component health and system resources.

    Enhanced with:
    - CPU/Memory/Disk monitoring
    - Performance metrics tracking
    - Thread monitoring
    - Health trend analysis
    - Configurable thresholds
    """

    # Health thresholds
    THRESHOLDS = {
        "cpu_warning": 70.0,
        "cpu_critical": 90.0,
        "memory_warning": 80.0,
        "memory_critical": 95.0,
        "disk_warning": 85.0,
        "disk_critical": 95.0,
        "heartbeat_warning": 1.0,  # seconds
        "heartbeat_critical": 3.0,
        "response_time_warning": 50.0,  # ms
        "response_time_critical": 200.0,
    }

    def __init__(self):
        """Initialize health monitor."""
        self.process = psutil.Process()
        self.start_time = time.time()
        self.heartbeat_count = 0
        self.last_heartbeat_time = time.time()
        self.missed_heartbeats = 0

        # Performance tracking
        self.performance = PerformanceMetrics()

        # Health history
        self._health_history: deque = deque(maxlen=60)  # Last 60 samples
        self._cpu_history: deque = deque(maxlen=60)
        self._memory_history: deque = deque(maxlen=60)

        # Current health level
        self._health_level = HealthLevel.HEALTHY
        self._health_reasons: List[str] = []

        # Lock for thread safety
        self._lock = threading.RLock()

        # Additional tracking
        self._error_streak = 0
        self._last_health_check = 0.0
        self._component_health: Dict[str, HealthLevel] = {}

    def get_health_metrics(self) -> Dict:
        """
        Get current health metrics.

        Returns:
            Dictionary with health metrics
        """
        with self._lock:
            try:
                # CPU usage (percentage)
                cpu_percent = self.process.cpu_percent(interval=0.1)
                self._cpu_history.append(cpu_percent)

                # Memory usage (MB)
                memory_info = self.process.memory_info()
                memory_mb = memory_info.rss / (1024 * 1024)  # Convert bytes to MB
                memory_percent = self.process.memory_percent()
                self._memory_history.append(memory_percent)

                # Uptime
                uptime = time.time() - self.start_time

                # Thread count
                thread_count = self.process.num_threads()

                # Open file descriptors (Linux)
                try:
                    open_fds = self.process.num_fds()
                except (AttributeError, psutil.AccessDenied):
                    open_fds = -1

                # Disk usage
                try:
                    disk_usage = psutil.disk_usage("/")
                    disk_percent = disk_usage.percent
                except Exception:
                    disk_percent = 0.0

                # Calculate health level
                self._update_health_level(cpu_percent, memory_percent, disk_percent)

                return {
                    "cpu_usage": round(cpu_percent, 2),
                    "cpu_avg": round(sum(self._cpu_history) / max(1, len(self._cpu_history)), 2),
                    "memory_mb": round(memory_mb, 2),
                    "memory_percent": round(memory_percent, 2),
                    "memory_avg": round(
                        sum(self._memory_history) / max(1, len(self._memory_history)), 2
                    ),
                    "disk_percent": round(disk_percent, 2),
                    "uptime_seconds": round(uptime, 2),
                    "heartbeat_count": self.heartbeat_count,
                    "missed_heartbeats": self.missed_heartbeats,
                    "thread_count": thread_count,
                    "open_fds": open_fds,
                    "health_level": self._health_level.value,
                    "health_reasons": self._health_reasons.copy(),
                    "avg_response_time_ms": round(self.performance.avg_response_time_ms, 2),
                    "p95_response_time_ms": round(self.performance.p95_response_time_ms, 2),
                    "error_streak": self._error_streak,
                }
            except Exception as e:
                # Return minimal metrics on error
                return {
                    "cpu_usage": 0.0,
                    "memory_mb": 0.0,
                    "uptime_seconds": 0.0,
                    "heartbeat_count": self.heartbeat_count,
                    "missed_heartbeats": self.missed_heartbeats,
                    "health_level": "unknown",
                    "error": str(e),
                }

    def _update_health_level(self, cpu: float, memory: float, disk: float):
        """Update health level based on current metrics."""
        self._health_reasons = []

        # Check CPU
        if cpu >= self.THRESHOLDS["cpu_critical"]:
            self._health_reasons.append(f"CPU critical: {cpu:.1f}%")
        elif cpu >= self.THRESHOLDS["cpu_warning"]:
            self._health_reasons.append(f"CPU high: {cpu:.1f}%")

        # Check memory
        if memory >= self.THRESHOLDS["memory_critical"]:
            self._health_reasons.append(f"Memory critical: {memory:.1f}%")
        elif memory >= self.THRESHOLDS["memory_warning"]:
            self._health_reasons.append(f"Memory high: {memory:.1f}%")

        # Check disk
        if disk >= self.THRESHOLDS["disk_critical"]:
            self._health_reasons.append(f"Disk critical: {disk:.1f}%")
        elif disk >= self.THRESHOLDS["disk_warning"]:
            self._health_reasons.append(f"Disk high: {disk:.1f}%")

        # Check heartbeat
        time_since_hb = self.get_time_since_last_heartbeat()
        if time_since_hb > self.THRESHOLDS["heartbeat_critical"]:
            self._health_reasons.append(f"Heartbeat timeout: {time_since_hb:.1f}s")
        elif time_since_hb > self.THRESHOLDS["heartbeat_warning"]:
            self._health_reasons.append(f"Heartbeat delayed: {time_since_hb:.1f}s")

        # Check response time
        avg_rt = self.performance.avg_response_time_ms
        if avg_rt > self.THRESHOLDS["response_time_critical"]:
            self._health_reasons.append(f"Response time critical: {avg_rt:.1f}ms")
        elif avg_rt > self.THRESHOLDS["response_time_warning"]:
            self._health_reasons.append(f"Response time high: {avg_rt:.1f}ms")

        # Check error streak
        if self._error_streak >= 5:
            self._health_reasons.append(f"Error streak: {self._error_streak}")

        # Determine overall health level
        critical_count = sum(1 for r in self._health_reasons if "critical" in r.lower())
        warning_count = len(self._health_reasons) - critical_count

        if critical_count > 0 or self._error_streak >= 10:
            self._health_level = HealthLevel.CRITICAL
        elif warning_count >= 3 or self._error_streak >= 5:
            self._health_level = HealthLevel.UNHEALTHY
        elif warning_count > 0 or self._error_streak >= 2:
            self._health_level = HealthLevel.DEGRADED
        else:
            self._health_level = HealthLevel.HEALTHY
            self._error_streak = 0  # Reset on healthy

    def record_heartbeat(self):
        """Record a successful heartbeat."""
        with self._lock:
            self.heartbeat_count += 1
            self.last_heartbeat_time = time.time()
            self.missed_heartbeats = 0

    def record_missed_heartbeat(self):
        """Record a missed heartbeat."""
        with self._lock:
            self.missed_heartbeats += 1

    def get_time_since_last_heartbeat(self) -> float:
        """Get time since last heartbeat in seconds."""
        return time.time() - self.last_heartbeat_time

    def is_heartbeat_timeout(self, timeout_seconds: float = 1.5) -> bool:
        """
        Check if heartbeat has timed out.

        Args:
            timeout_seconds: Timeout threshold (default 1.5s = 3 missed heartbeats at 2Hz)

        Returns:
            True if timeout exceeded
        """
        return self.get_time_since_last_heartbeat() > timeout_seconds

    def record_response_time(self, duration_ms: float):
        """
        Record a response time for performance tracking.

        Args:
            duration_ms: Response time in milliseconds
        """
        with self._lock:
            self.performance.response_times_ms.append(duration_ms)

    def record_operation(self, operation_type: str, success: bool = True):
        """
        Record an operation for statistics.

        Args:
            operation_type: Type of operation
            success: Whether operation succeeded
        """
        with self._lock:
            if operation_type not in self.performance.operation_counts:
                self.performance.operation_counts[operation_type] = 0
            self.performance.operation_counts[operation_type] += 1

            if not success:
                if operation_type not in self.performance.error_counts:
                    self.performance.error_counts[operation_type] = 0
                self.performance.error_counts[operation_type] += 1
                self._error_streak += 1
            else:
                self._error_streak = 0

    def record_error(self, error_type: str = "general"):
        """Record an error occurrence."""
        with self._lock:
            if error_type not in self.performance.error_counts:
                self.performance.error_counts[error_type] = 0
            self.performance.error_counts[error_type] += 1
            self._error_streak += 1

    def set_component_health(self, component: str, health: HealthLevel):
        """
        Set health status of a sub-component.

        Args:
            component: Component name
            health: Health level
        """
        with self._lock:
            self._component_health[component] = health

    def get_component_health(self) -> Dict[str, str]:
        """Get health status of all tracked components."""
        with self._lock:
            return {k: v.value for k, v in self._component_health.items()}

    def get_health_level(self) -> HealthLevel:
        """Get current overall health level."""
        return self._health_level

    def is_healthy(self) -> bool:
        """Check if component is healthy."""
        return self._health_level in [HealthLevel.HEALTHY, HealthLevel.DEGRADED]

    def get_health_summary(self) -> Dict[str, Any]:
        """Get comprehensive health summary."""
        metrics = self.get_health_metrics()
        return {
            "level": self._health_level.value,
            "is_healthy": self.is_healthy(),
            "reasons": self._health_reasons.copy(),
            "metrics": metrics,
            "components": self.get_component_health(),
            "performance": {
                "operations": dict(self.performance.operation_counts),
                "errors": dict(self.performance.error_counts),
                "avg_response_ms": round(self.performance.avg_response_time_ms, 2),
                "p95_response_ms": round(self.performance.p95_response_time_ms, 2),
            },
        }
