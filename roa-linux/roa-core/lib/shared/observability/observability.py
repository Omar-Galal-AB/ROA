"""
ROA Observability
=================
Unified observability for ROA components

This module provides a single entry point for all observability features:
- Structured logging (Fluent Bit/Loki)
- Prometheus metrics
- OpenTelemetry tracing (Tempo)
- Health checks
- MCAP recording

Usage:
    from roa_observability import ROAObservability

    # Initialize
    obs = ROAObservability("webthread", "1.0.0")
    obs.start()

    # Use logging
    obs.logger.info("Processing request", extra={"request_id": "123"})

    # Use metrics
    with obs.metrics.time_request("process", "api"):
        process_data()

    # Use tracing
    with obs.tracer.start_span("process_request"):
        obs.tracer.set_attribute("request_id", "123")
        process_data()

    # Record events
    obs.recorder.record_event("data_processed", {"count": 100})

    # Cleanup
    obs.stop()
"""

import threading
from typing import Optional

from .config import ObservabilityConfig, get_component_config
from .health import HealthCheck, HealthStatus
from .mcap_recorder import MCAPRecorder, ROAEventRecorder
from .metrics import MetricsServer, ResourceCollector, ROAMetrics
from .structured_logger import ROALogger
from .tracing import ROATracer


class ROAObservability:
    """
    Unified ROA Observability

    Provides a single entry point for all observability features.
    Manages lifecycle of all observability components.

    Example:
        obs = ROAObservability("webthread")
        obs.start()

        try:
            obs.logger.info("Component started")
            obs.health.set_healthy()

            # Your component logic
            with obs.tracer.start_span("main_loop"):
                while running:
                    with obs.metrics.time_request("process", "internal"):
                        process()
        finally:
            obs.stop()
    """

    def __init__(
        self,
        component_name: str,
        service_version: str = "1.0.0",
        config: Optional[ObservabilityConfig] = None,
        auto_start: bool = False,
    ):
        """
        Initialize observability

        Args:
            component_name: Name of the component (webthread, fti, etc.)
            service_version: Version of the component
            config: Configuration (uses defaults if not provided)
            auto_start: Start servers automatically
        """
        self.component_name = component_name
        self.service_version = service_version

        # Get or create config
        if config is None:
            self.config = get_component_config(component_name)
            self.config.service_version = service_version
        else:
            self.config = config

        # Initialize components
        self._init_components()

        # Track running state
        self._started = False
        self._lock = threading.Lock()

        if auto_start:
            self.start()

    def _init_components(self):
        """Initialize all observability components"""

        # Logging
        self.logger = ROALogger(
            component_name=self.component_name,
            config=self.config,
        )

        # Metrics
        self.metrics = ROAMetrics(
            component_name=self.component_name,
            config=self.config,
        )

        self._metrics_server: Optional[MetricsServer] = None
        self._resource_collector: Optional[ResourceCollector] = None

        # Tracing
        self.tracer = ROATracer(
            component_name=self.component_name,
            config=self.config,
        )

        # Health
        self.health = HealthCheck(
            component_name=self.component_name,
            config=self.config.health,
            version=self.service_version,
        )

        # MCAP Recorder
        self.recorder = ROAEventRecorder(
            component_name=self.component_name,
            config=self.config.mcap,
        )

    # ─── Lifecycle ─────────────────────────────────────────────

    def start(
        self,
        start_metrics_server: bool = True,
        start_health_server: bool = True,
        start_resource_collector: bool = True,
        start_recording: bool = False,
    ):
        """
        Start observability services

        Args:
            start_metrics_server: Start Prometheus metrics server
            start_health_server: Start health check server
            start_resource_collector: Start CPU/memory collector
            start_recording: Start MCAP recording
        """
        with self._lock:
            if self._started:
                return

            self.logger.info(
                f"Starting observability for {self.component_name}",
                extra={"version": self.service_version},
            )

            # Start metrics server
            if start_metrics_server and self.config.metrics.enabled:
                self._metrics_server = MetricsServer(
                    port=self.config.metrics.port,
                    host=self.config.metrics.host,
                )
                try:
                    self._metrics_server.start()
                    self.logger.info(f"Metrics server started on port {self.config.metrics.port}")
                except Exception as e:
                    self.logger.warning(f"Failed to start metrics server: {e}")

            # Start resource collector
            if start_resource_collector and self.config.metrics.enabled:
                self._resource_collector = ResourceCollector(self.metrics)
                self._resource_collector.start()

            # Start health server
            if start_health_server and self.config.health.enabled:
                try:
                    self.health.start_server(
                        port=self.config.health.port,
                    )
                    self.health.start_background_checker()
                    self.logger.info(f"Health server started on port {self.config.health.port}")
                except Exception as e:
                    self.logger.warning(f"Failed to start health server: {e}")

            # Start recording
            if start_recording and self.config.mcap.enabled:
                try:
                    filepath = self.recorder.start()
                    self.logger.info(f"Recording started: {filepath}")
                except Exception as e:
                    self.logger.warning(f"Failed to start recording: {e}")

            # Set initial status
            self.health.set_initializing()
            self.metrics.set_status(1, self.component_name)  # initializing

            self._started = True

    def stop(self):
        """Stop observability services"""
        with self._lock:
            if not self._started:
                return

            self.logger.info(f"Stopping observability for {self.component_name}")

            # Update status
            self.health.set_stopped()
            self.metrics.set_status(5, self.component_name)  # stopped

            # Stop recording
            try:
                stats = self.recorder.stop()
                if stats.messages_written > 0:
                    self.logger.info(
                        f"Recording stopped: {stats.messages_written} messages, "
                        f"{stats.bytes_written} bytes"
                    )
            except Exception:
                pass

            # Stop health
            try:
                self.health.stop_background_checker()
                self.health.stop_server()
            except Exception:
                pass

            # Stop resource collector
            if self._resource_collector:
                self._resource_collector.stop()
                self._resource_collector = None

            # Stop metrics server
            if self._metrics_server:
                self._metrics_server.stop()
                self._metrics_server = None

            self._started = False

    # ─── Status Updates ────────────────────────────────────────

    def set_ready(self):
        """Mark component as ready/healthy"""
        self.health.set_healthy()
        self.metrics.set_status(2, self.component_name)  # running
        self.metrics.set_health(100, self.component_name)
        self.logger.info("Component ready")
        self.recorder.record_state_change("initializing", "running")

    def set_degraded(self, reason: str = None):
        """Mark component as degraded"""
        self.health.set_degraded(reason)
        self.metrics.set_status(3, self.component_name)  # degraded
        self.metrics.set_health(50, self.component_name)
        self.logger.warning(f"Component degraded: {reason}")
        self.recorder.record_state_change("running", "degraded", reason)

    def set_unhealthy(self, reason: str = None):
        """Mark component as unhealthy"""
        self.health.set_unhealthy(reason)
        self.metrics.set_status(4, self.component_name)  # error
        self.metrics.set_health(0, self.component_name)
        self.logger.error(f"Component unhealthy: {reason}")
        self.recorder.record_state_change("running", "error", reason)

    # ─── Convenience Methods ───────────────────────────────────

    def record_heartbeat(self, target: str, latency: float):
        """Record a heartbeat with metrics and recording"""
        self.metrics.record_heartbeat(target, latency)
        self.recorder.record_heartbeat(target, latency * 1000)  # Convert to ms

    def record_error(self, error_type: str, message: str, exception: Exception = None):
        """Record an error across all channels"""
        self.metrics.record_error(error_type)
        self.logger.error(f"{error_type}: {message}", exc_info=exception)
        self.recorder.record_error(
            error_type,
            message,
            {
                "exception": str(exception) if exception else None,
            },
        )

        if exception:
            self.tracer.set_error(exception)

    def record_request(
        self,
        method: str,
        source: str,
        status: str = "success",
        duration: float = None,
    ):
        """Record a request across metrics"""
        self.metrics.record_request(method, status, source, duration)

    # ─── Context Managers ──────────────────────────────────────

    def span(self, name: str, **attributes):
        """Create a traced span"""
        return self.tracer.start_span(name, attributes=attributes)

    def timed_request(self, method: str, source: str = "unknown"):
        """Time a request with metrics"""
        return self.metrics.time_request(method, source)

    # ─── Dependency Registration ───────────────────────────────

    def add_dependency(self, name: str):
        """Add a component dependency"""
        self.health.add_dependency(name)

    def update_dependency_status(self, name: str, healthy: bool):
        """Update dependency status"""
        status = HealthStatus.HEALTHY if healthy else HealthStatus.UNHEALTHY
        self.health.update_dependency(name, status)

    # ─── Context Manager ───────────────────────────────────────

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.record_error(
                exc_type.__name__,
                str(exc_val),
                exc_val,
            )
        self.stop()
        return False


# ─── Factory Function ──────────────────────────────────────────


def create_observability(
    component_name: str,
    service_version: str = "1.0.0",
    **config_overrides,
) -> ROAObservability:
    """
    Factory function to create observability

    Args:
        component_name: Component name
        service_version: Service version
        **config_overrides: Configuration overrides

    Returns:
        ROAObservability instance
    """
    config = get_component_config(component_name)
    config.service_version = service_version

    # Apply overrides
    for key, value in config_overrides.items():
        if hasattr(config, key):
            setattr(config, key, value)

    return ROAObservability(component_name, service_version, config)


# ─── Quick Setup ───────────────────────────────────────────────


def setup_observability(component_name: str, version: str = "1.0.0") -> ROAObservability:
    """
    Quick setup for observability

    Creates and starts observability with default configuration.

    Usage:
        obs = setup_observability("webthread", "1.0.0")
        obs.set_ready()

        # Use obs.logger, obs.metrics, obs.tracer, etc.
    """
    obs = ROAObservability(component_name, version, auto_start=True)
    return obs
