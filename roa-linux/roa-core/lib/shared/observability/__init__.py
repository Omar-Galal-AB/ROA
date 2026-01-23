"""
ROA Observability Package
=========================
Complete observability stack integration for Robot Operations & Automation

Includes:
- Structured JSON Logging (Fluent Bit/Loki)
- Prometheus Metrics
- OpenTelemetry Tracing (Tempo)
- MCAP Recording Integration
- HTTP Metrics Server

Usage:
    from roa_observability import ROAObservability

    obs = ROAObservability(
        component_name="webthread",
        service_version="1.0.0"
    )

    # Use logging
    obs.logger.info("Starting component", extra={"status": "initializing"})

    # Use metrics
    obs.metrics.request_count.labels(method="process").inc()

    # Use tracing
    with obs.tracer.start_span("operation_name"):
        do_work()
"""

__version__ = "1.0.0"
__author__ = "ROA Team"

from .config import ObservabilityConfig, get_component_config
from .health import ComponentHealth, HealthCheck, HealthStatus
from .mcap_recorder import MCAPRecorder, ROAEventRecorder
from .metrics import MetricsServer, ResourceCollector, ROAMetrics, counted, timed
from .observability import ROAObservability
from .structured_logger import ROALogger, get_logger
from .tracing import (  # Request tracking types; Protocol-specific spans
    CacheSpanAttributes,
    ControlLoopTracer,
    DatabaseSpanAttributes,
    ErrorCategory,
    GRPCSpanAttributes,
    HTTPSpanAttributes,
    RequestContext,
    RequestType,
    ROATracer,
    ROS2TracingMixin,
    SpanBuilder,
    SpanContext,
    TraceContextMiddleware,
    UE5TracingContext,
    WebSocketSpanAttributes,
    cache_span,
    database_span,
    get_span_id,
    get_trace_id,
    grpc_client_span,
    grpc_server_span,
    http_client_span,
    http_server_span,
    trace_async_method,
    trace_method,
    trace_ros2_callback,
    trace_ros2_timer,
    websocket_span,
)

__all__ = [
    # Main entry point
    "ROAObservability",
    # Configuration
    "ObservabilityConfig",
    "get_component_config",
    # Logging
    "ROALogger",
    "get_logger",
    # Metrics
    "ROAMetrics",
    "MetricsServer",
    "ResourceCollector",
    "timed",
    "counted",
    # Tracing
    "ROATracer",
    "trace_method",
    "trace_async_method",
    "ROS2TracingMixin",
    "trace_ros2_callback",
    "trace_ros2_timer",
    "UE5TracingContext",
    "ControlLoopTracer",
    "get_trace_id",
    "get_span_id",
    "TraceContextMiddleware",
    # Request tracking
    "RequestType",
    "ErrorCategory",
    "RequestContext",
    "SpanBuilder",
    "SpanContext",
    # Protocol-specific spans
    "HTTPSpanAttributes",
    "http_server_span",
    "http_client_span",
    "GRPCSpanAttributes",
    "grpc_server_span",
    "grpc_client_span",
    "WebSocketSpanAttributes",
    "websocket_span",
    "DatabaseSpanAttributes",
    "database_span",
    "CacheSpanAttributes",
    "cache_span",
    # Health
    "HealthCheck",
    "HealthStatus",
    "ComponentHealth",
    # Recording
    "MCAPRecorder",
    "ROAEventRecorder",
]
