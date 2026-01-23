"""
ROA Health Check
================
Health monitoring and status reporting

Features:
- Health check endpoints
- Component dependency tracking
- Liveness and readiness probes
- Health aggregation
"""

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum, IntEnum
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Dict, List, Optional

from .config import HealthConfig, ObservabilityConfig


class HealthStatus(IntEnum):
    """Health status values"""

    UNKNOWN = 0
    INITIALIZING = 1
    HEALTHY = 2
    DEGRADED = 3
    UNHEALTHY = 4
    STOPPED = 5


class ComponentHealth(Enum):
    """Component health for metrics"""

    UNKNOWN = "unknown"
    INITIALIZING = "initializing"
    RUNNING = "running"
    DEGRADED = "degraded"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class HealthCheckResult:
    """Result of a health check"""

    name: str
    status: HealthStatus
    message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.name,
            "status_code": int(self.status),
            "message": self.message,
            "details": self.details,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
        }


@dataclass
class ComponentStatus:
    """Overall component status"""

    component: str
    status: HealthStatus
    version: str = "1.0.0"
    uptime_seconds: float = 0.0
    checks: List[HealthCheckResult] = field(default_factory=list)
    dependencies: Dict[str, HealthStatus] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "component": self.component,
            "status": self.status.name,
            "status_code": int(self.status),
            "version": self.version,
            "uptime_seconds": self.uptime_seconds,
            "checks": [c.to_dict() for c in self.checks],
            "dependencies": {k: v.name for k, v in self.dependencies.items()},
            "healthy": self.status in (HealthStatus.HEALTHY, HealthStatus.INITIALIZING),
        }


class HealthCheck:
    """
    Health Check Manager

    Manages health checks and dependencies for a component.

    Usage:
        health = HealthCheck("webthread")

        # Register checks
        health.register_check("database", db_check_function)
        health.register_check("redis", redis_check_function)

        # Mark dependencies
        health.add_dependency("fti")
        health.add_dependency("dimc")

        # Get status
        status = health.get_status()

        # Start HTTP server
        health.start_server(port=8080)
    """

    def __init__(
        self,
        component_name: str,
        config: Optional[HealthConfig] = None,
        version: str = "1.0.0",
    ):
        self.component_name = component_name
        self.config = config or HealthConfig()
        self.version = version

        self._start_time = time.time()
        self._status = HealthStatus.INITIALIZING
        self._checks: Dict[str, Callable[[], HealthCheckResult]] = {}
        self._dependencies: Dict[str, HealthStatus] = {}
        self._last_results: Dict[str, HealthCheckResult] = {}
        self._server = None
        self._lock = threading.RLock()

        # Background checker
        self._checker_running = False
        self._checker_thread = None

    # ─── Status Management ─────────────────────────────────────

    def set_status(self, status: HealthStatus):
        """Set component status"""
        with self._lock:
            self._status = status

    def set_healthy(self):
        """Mark component as healthy"""
        self.set_status(HealthStatus.HEALTHY)

    def set_degraded(self, reason: str = None):
        """Mark component as degraded"""
        self.set_status(HealthStatus.DEGRADED)

    def set_unhealthy(self, reason: str = None):
        """Mark component as unhealthy"""
        self.set_status(HealthStatus.UNHEALTHY)

    def set_initializing(self):
        """Mark component as initializing"""
        self.set_status(HealthStatus.INITIALIZING)

    def set_stopped(self):
        """Mark component as stopped"""
        self.set_status(HealthStatus.STOPPED)

    # ─── Health Checks ─────────────────────────────────────────

    def register_check(
        self,
        name: str,
        check_func: Callable[[], HealthCheckResult],
    ):
        """
        Register a health check function

        Args:
            name: Check name
            check_func: Function that returns HealthCheckResult
        """
        with self._lock:
            self._checks[name] = check_func

    def register_simple_check(
        self,
        name: str,
        check_func: Callable[[], bool],
        healthy_message: str = "OK",
        unhealthy_message: str = "Failed",
    ):
        """
        Register a simple boolean health check

        Args:
            name: Check name
            check_func: Function that returns True if healthy
        """

        def wrapper() -> HealthCheckResult:
            start = time.time()
            try:
                is_healthy = check_func()
                duration = (time.time() - start) * 1000
                return HealthCheckResult(
                    name=name,
                    status=(HealthStatus.HEALTHY if is_healthy else HealthStatus.UNHEALTHY),
                    message=healthy_message if is_healthy else unhealthy_message,
                    duration_ms=duration,
                )
            except Exception as e:
                duration = (time.time() - start) * 1000
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=str(e),
                    duration_ms=duration,
                )

        self.register_check(name, wrapper)

    def unregister_check(self, name: str):
        """Remove a health check"""
        with self._lock:
            self._checks.pop(name, None)
            self._last_results.pop(name, None)

    def run_check(self, name: str) -> Optional[HealthCheckResult]:
        """Run a specific health check"""
        with self._lock:
            check_func = self._checks.get(name)

        if not check_func:
            return None

        try:
            result = check_func()
        except Exception as e:
            result = HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed: {e}",
            )

        with self._lock:
            self._last_results[name] = result

        return result

    def run_all_checks(self) -> List[HealthCheckResult]:
        """Run all registered health checks"""
        results = []

        with self._lock:
            check_names = list(self._checks.keys())

        for name in check_names:
            result = self.run_check(name)
            if result:
                results.append(result)

        return results

    # ─── Dependencies ──────────────────────────────────────────

    def add_dependency(self, name: str, initial_status: HealthStatus = HealthStatus.UNKNOWN):
        """Add a dependency"""
        with self._lock:
            self._dependencies[name] = initial_status

    def remove_dependency(self, name: str):
        """Remove a dependency"""
        with self._lock:
            self._dependencies.pop(name, None)

    def update_dependency(self, name: str, status: HealthStatus):
        """Update dependency status"""
        with self._lock:
            if name in self._dependencies:
                self._dependencies[name] = status

    # ─── Status Aggregation ────────────────────────────────────

    def get_status(self) -> ComponentStatus:
        """Get aggregated component status"""
        with self._lock:
            uptime = time.time() - self._start_time
            checks = list(self._last_results.values())
            dependencies = dict(self._dependencies)

            # Aggregate status from checks
            if not checks:
                aggregated = self._status
            else:
                worst = max(
                    (r.status for r in checks),
                    key=lambda s: s.value,
                    default=HealthStatus.UNKNOWN,
                )

                # Component status overrides if worse
                if self._status.value > worst.value:
                    aggregated = self._status
                else:
                    aggregated = worst

            # Check dependencies
            for dep_status in dependencies.values():
                if dep_status == HealthStatus.UNHEALTHY:
                    aggregated = max(aggregated, HealthStatus.DEGRADED)
                    break

            return ComponentStatus(
                component=self.component_name,
                status=aggregated,
                version=self.version,
                uptime_seconds=uptime,
                checks=checks,
                dependencies=dependencies,
            )

    def is_healthy(self) -> bool:
        """Check if component is healthy"""
        status = self.get_status()
        return status.status in (HealthStatus.HEALTHY, HealthStatus.INITIALIZING)

    def is_ready(self) -> bool:
        """Check if component is ready (for readiness probe)"""
        status = self.get_status()
        return status.status == HealthStatus.HEALTHY

    def is_live(self) -> bool:
        """Check if component is live (for liveness probe)"""
        status = self.get_status()
        return status.status not in (HealthStatus.STOPPED, HealthStatus.UNHEALTHY)

    # ─── Background Checker ────────────────────────────────────

    def start_background_checker(self, interval: float = None):
        """Start background health check loop"""
        if self._checker_running:
            return

        interval = interval or self.config.check_interval_seconds
        self._checker_running = True
        self._checker_thread = threading.Thread(
            target=self._checker_loop,
            args=(interval,),
            daemon=True,
            name=f"health-checker-{self.component_name}",
        )
        self._checker_thread.start()

    def stop_background_checker(self):
        """Stop background health check loop"""
        self._checker_running = False
        if self._checker_thread:
            self._checker_thread.join(timeout=5.0)

    def _checker_loop(self, interval: float):
        """Background check loop"""
        while self._checker_running:
            try:
                self.run_all_checks()
            except Exception:
                pass
            time.sleep(interval)

    # ─── HTTP Server ───────────────────────────────────────────

    def start_server(self, port: int = None, host: str = "0.0.0.0"):
        """Start health check HTTP server"""
        if self._server:
            return

        port = port or self.config.port

        handler = _create_health_handler(self)

        try:
            self._server = HTTPServer((host, port), handler)
            thread = threading.Thread(
                target=self._server.serve_forever,
                daemon=True,
                name=f"health-server-{self.component_name}",
            )
            thread.start()
        except Exception as e:
            raise RuntimeError(f"Failed to start health server on {host}:{port}: {e}")

    def stop_server(self):
        """Stop health check HTTP server"""
        if self._server:
            self._server.shutdown()
            self._server = None


def _create_health_handler(health_check: HealthCheck):
    """Create HTTP handler for health endpoints"""

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health" or self.path == "/":
                self._handle_health()
            elif self.path == "/health/live" or self.path == "/livez":
                self._handle_liveness()
            elif self.path == "/health/ready" or self.path == "/readyz":
                self._handle_readiness()
            else:
                self.send_response(404)
                self.end_headers()

        def _handle_health(self):
            status = health_check.get_status()
            http_code = (
                200
                if status.status
                in (
                    HealthStatus.HEALTHY,
                    HealthStatus.INITIALIZING,
                    HealthStatus.DEGRADED,
                )
                else 503
            )

            body = json.dumps(status.to_dict(), indent=2)

            self.send_response(http_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body.encode())

        def _handle_liveness(self):
            is_live = health_check.is_live()
            http_code = 200 if is_live else 503
            body = json.dumps({"live": is_live})

            self.send_response(http_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body.encode())

        def _handle_readiness(self):
            is_ready = health_check.is_ready()
            http_code = 200 if is_ready else 503
            body = json.dumps({"ready": is_ready})

            self.send_response(http_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, format, *args):
            """Suppress default logging"""
            pass

    return HealthHandler


# ─── Pre-built Health Checks ───────────────────────────────────


def create_memory_check(threshold_mb: float = 1000) -> Callable[[], HealthCheckResult]:
    """Create a memory usage health check"""

    def check() -> HealthCheckResult:
        try:
            import psutil

            process = psutil.Process()
            mem_mb = process.memory_info().rss / 1024 / 1024

            if mem_mb < threshold_mb:
                return HealthCheckResult(
                    name="memory",
                    status=HealthStatus.HEALTHY,
                    message=f"Memory usage: {mem_mb:.1f}MB",
                    details={"usage_mb": mem_mb, "threshold_mb": threshold_mb},
                )
            else:
                return HealthCheckResult(
                    name="memory",
                    status=HealthStatus.DEGRADED,
                    message=f"High memory usage: {mem_mb:.1f}MB (threshold: {threshold_mb}MB)",
                    details={"usage_mb": mem_mb, "threshold_mb": threshold_mb},
                )
        except ImportError:
            return HealthCheckResult(
                name="memory",
                status=HealthStatus.UNKNOWN,
                message="psutil not available",
            )

    return check


def create_disk_check(
    path: str = "/", threshold_percent: float = 90
) -> Callable[[], HealthCheckResult]:
    """Create a disk usage health check"""

    def check() -> HealthCheckResult:
        try:
            import psutil

            usage = psutil.disk_usage(path)

            if usage.percent < threshold_percent:
                return HealthCheckResult(
                    name="disk",
                    status=HealthStatus.HEALTHY,
                    message=f"Disk usage: {usage.percent:.1f}%",
                    details={
                        "path": path,
                        "usage_percent": usage.percent,
                        "free_gb": usage.free / 1024 / 1024 / 1024,
                    },
                )
            else:
                return HealthCheckResult(
                    name="disk",
                    status=HealthStatus.DEGRADED,
                    message=f"High disk usage: {usage.percent:.1f}%",
                    details={
                        "path": path,
                        "usage_percent": usage.percent,
                        "free_gb": usage.free / 1024 / 1024 / 1024,
                    },
                )
        except ImportError:
            return HealthCheckResult(
                name="disk",
                status=HealthStatus.UNKNOWN,
                message="psutil not available",
            )

    return check


def create_connection_check(
    host: str,
    port: int,
    timeout: float = 5.0,
    name: str = None,
) -> Callable[[], HealthCheckResult]:
    """Create a TCP connection health check"""
    import socket

    check_name = name or f"connection_{host}_{port}"

    def check() -> HealthCheckResult:
        start = time.time()
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            duration = (time.time() - start) * 1000

            return HealthCheckResult(
                name=check_name,
                status=HealthStatus.HEALTHY,
                message=f"Connected to {host}:{port}",
                duration_ms=duration,
                details={"host": host, "port": port},
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return HealthCheckResult(
                name=check_name,
                status=HealthStatus.UNHEALTHY,
                message=f"Failed to connect to {host}:{port}: {e}",
                duration_ms=duration,
                details={"host": host, "port": port, "error": str(e)},
            )

    return check
