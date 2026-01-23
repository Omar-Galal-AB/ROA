"""
ROA OpenTelemetry Tracing
=========================
Distributed tracing with Tempo integration

Features:
- Automatic trace context propagation
- Span creation and management
- Method decorators for automatic instrumentation
- W3C Trace Context support
- Baggage propagation
- Request/Response span hierarchy
- Span links for relating traces
- HTTP/gRPC/WebSocket protocol tracing
- Database and cache operation spans
- Async span context management
"""

import functools
import asyncio
import threading
import time
import uuid
from typing import Optional, Dict, Any, Callable, Union, List, Tuple
from contextlib import contextmanager, asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider, Span
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
        SimpleSpanProcessor,
    )
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
    from opentelemetry.trace import Status, StatusCode, SpanKind, Link
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    from opentelemetry.baggage.propagation import W3CBaggagePropagator
    from opentelemetry.baggage import set_baggage, get_baggage, get_all as get_all_baggage
    from opentelemetry.propagators.composite import CompositePropagator
    from opentelemetry.propagate import set_global_textmap, get_global_textmap, inject, extract
    from opentelemetry.context import Context, attach, detach, get_current
    
    # OTLP exporter
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        OTLP_AVAILABLE = True
    except ImportError:
        OTLP_AVAILABLE = False
    
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    
    # Stubs for when opentelemetry is not installed
    class Span:
        def set_attribute(self, *args, **kwargs): pass
        def set_status(self, *args, **kwargs): pass
        def record_exception(self, *args, **kwargs): pass
        def add_event(self, *args, **kwargs): pass
        def end(self, *args, **kwargs): pass
        def is_recording(self): return False
        def get_span_context(self): return _SpanContextStub()
        def __enter__(self): return self
        def __exit__(self, *args): pass
    
    class _SpanContextStub:
        trace_id = 0
        span_id = 0
        trace_flags = 0
    
    class SpanKind:
        INTERNAL = 0
        SERVER = 1
        CLIENT = 2
        PRODUCER = 3
        CONSUMER = 4
    
    class StatusCode:
        UNSET = 0
        OK = 1
        ERROR = 2
    
    class Link:
        pass
    
    def set_baggage(*args, **kwargs): pass
    def get_baggage(*args, **kwargs): return None
    def get_all_baggage(*args, **kwargs): return {}
    def attach(*args): return None
    def detach(*args): pass
    def get_current(): return None
    
    OTLP_AVAILABLE = False

from .config import ObservabilityConfig, TracingConfig, ExporterType


# ─── Request Tracking Enums ────────────────────────────────────

class RequestType(Enum):
    """Types of requests for span categorization"""
    HTTP = "http"
    GRPC = "grpc"
    WEBSOCKET = "websocket"
    ROS2_TOPIC = "ros2_topic"
    ROS2_SERVICE = "ros2_service"
    ROS2_ACTION = "ros2_action"
    UE5_COMMAND = "ue5_command"
    INTERNAL = "internal"
    DATABASE = "database"
    CACHE = "cache"


class ErrorCategory(Enum):
    """Error categories for span error classification"""
    VALIDATION = "validation_error"
    TIMEOUT = "timeout_error"
    CONNECTION = "connection_error"
    AUTHENTICATION = "authentication_error"
    AUTHORIZATION = "authorization_error"
    NOT_FOUND = "not_found_error"
    RATE_LIMITED = "rate_limited_error"
    INTERNAL = "internal_error"
    EXTERNAL = "external_error"
    CANCELLED = "cancelled_error"


@dataclass
class SpanContext:
    """Extracted span context"""
    trace_id: str
    span_id: str
    trace_flags: int = 0
    is_remote: bool = True


@dataclass
class RequestContext:
    """
    Context for request tracking across spans
    
    Holds request metadata that should be propagated through the trace.
    """
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    request_type: RequestType = RequestType.INTERNAL
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    correlation_id: Optional[str] = None
    parent_request_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_attributes(self) -> Dict[str, Any]:
        """Convert to span attributes"""
        attrs = {
            "request.id": self.request_id,
            "request.type": self.request_type.value,
            "request.start_time": self.start_time,
        }
        if self.user_id:
            attrs["user.id"] = self.user_id
        if self.session_id:
            attrs["session.id"] = self.session_id
        if self.client_ip:
            attrs["client.ip"] = self.client_ip
        if self.user_agent:
            attrs["client.user_agent"] = self.user_agent
        if self.correlation_id:
            attrs["correlation.id"] = self.correlation_id
        if self.parent_request_id:
            attrs["request.parent_id"] = self.parent_request_id
        return attrs
    
    def to_baggage(self) -> Dict[str, str]:
        """Convert to baggage items for propagation"""
        baggage = {
            "request_id": self.request_id,
            "request_type": self.request_type.value,
        }
        if self.user_id:
            baggage["user_id"] = self.user_id
        if self.session_id:
            baggage["session_id"] = self.session_id
        if self.correlation_id:
            baggage["correlation_id"] = self.correlation_id
        return baggage


class ROATracer:
    """
    ROA Distributed Tracer
    
    Provides OpenTelemetry tracing with Tempo integration.
    
    Usage:
        tracer = ROATracer("webthread")
        
        # Create a span
        with tracer.start_span("process_request") as span:
            span.set_attribute("request_id", "123")
            do_work()
        
        # Use decorator
        @tracer.trace
        def my_function():
            pass
    """
    
    _tracers: Dict[str, 'ROATracer'] = {}
    _lock = threading.Lock()
    _provider_initialized = False
    
    def __init__(
        self,
        component_name: str,
        config: Optional[Union[ObservabilityConfig, TracingConfig]] = None,
    ):
        self.component_name = component_name
        
        # Extract tracing config
        if isinstance(config, ObservabilityConfig):
            self.config = config.tracing
            self.service_version = config.service_version
        elif isinstance(config, TracingConfig):
            self.config = config
            self.service_version = "1.0.0"
        else:
            self.config = TracingConfig()
            self.service_version = "1.0.0"
        
        self._tracer = None
        self._propagator = None
        
        if OTEL_AVAILABLE and self.config.enabled:
            self._init_tracer()
    
    def _init_tracer(self):
        """Initialize OpenTelemetry tracer"""
        
        # Initialize provider once globally
        if not ROATracer._provider_initialized:
            resource = Resource.create({
                SERVICE_NAME: f"roa-{self.component_name}",
                SERVICE_VERSION: self.service_version,
                "deployment.environment": self.config.deployment_environment,
                "service.namespace": self.config.service_namespace,
            })
            
            provider = TracerProvider(resource=resource)
            
            # Configure exporter based on config
            if self.config.exporter == ExporterType.OTLP and OTLP_AVAILABLE:
                exporter = OTLPSpanExporter(
                    endpoint=self.config.otlp_endpoint,
                    insecure=self.config.otlp_insecure,
                )
                processor = BatchSpanProcessor(exporter)
            elif self.config.exporter == ExporterType.CONSOLE:
                processor = SimpleSpanProcessor(ConsoleSpanExporter())
            else:
                # No exporter - spans are still created but not exported
                processor = None
            
            if processor:
                provider.add_span_processor(processor)
            
            trace.set_tracer_provider(provider)
            
            # Set up propagators
            propagator = CompositePropagator([
                TraceContextTextMapPropagator(),
                W3CBaggagePropagator(),
            ])
            set_global_textmap(propagator)
            
            ROATracer._provider_initialized = True
        
        # Get tracer for this component
        self._tracer = trace.get_tracer(
            f"roa.{self.component_name}",
            self.service_version,
        )
        self._propagator = get_global_textmap()
    
    # ─── Span Creation ─────────────────────────────────────────
    
    @contextmanager
    def start_span(
        self,
        name: str,
        kind: 'SpanKind' = None,
        attributes: Dict[str, Any] = None,
        parent: Optional['Span'] = None,
    ):
        """
        Create a new span
        
        Args:
            name: Span name
            kind: Span kind (SERVER, CLIENT, INTERNAL, etc.)
            attributes: Initial span attributes
            parent: Parent span (uses current span if not provided)
        
        Usage:
            with tracer.start_span("operation") as span:
                span.set_attribute("key", "value")
                do_work()
        """
        if not OTEL_AVAILABLE or not self._tracer:
            yield _NoOpSpan()
            return
        
        if kind is None:
            kind = SpanKind.INTERNAL
        
        with self._tracer.start_as_current_span(
            name,
            kind=kind,
            attributes=attributes or {},
        ) as span:
            try:
                yield span
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
    
    def start_span_no_context(
        self,
        name: str,
        kind: 'SpanKind' = None,
        attributes: Dict[str, Any] = None,
    ) -> 'Span':
        """
        Create a new span without context manager
        
        Caller is responsible for calling span.end()
        
        Usage:
            span = tracer.start_span_no_context("operation")
            try:
                do_work()
            finally:
                span.end()
        """
        if not OTEL_AVAILABLE or not self._tracer:
            return _NoOpSpan()
        
        if kind is None:
            kind = SpanKind.INTERNAL
        
        return self._tracer.start_span(
            name,
            kind=kind,
            attributes=attributes or {},
        )
    
    def get_current_span(self) -> Optional['Span']:
        """Get the current active span"""
        if not OTEL_AVAILABLE:
            return None
        return trace.get_current_span()
    
    # ─── Context Propagation ───────────────────────────────────
    
    def inject_context(self, carrier: Dict[str, str]) -> Dict[str, str]:
        """
        Inject trace context into carrier (e.g., HTTP headers)
        
        Args:
            carrier: Dictionary to inject context into
            
        Returns:
            The carrier with trace context
        """
        if OTEL_AVAILABLE and self._propagator:
            inject(carrier)
        return carrier
    
    def extract_context(self, carrier: Dict[str, str]) -> Optional['Context']:
        """
        Extract trace context from carrier
        
        Args:
            carrier: Dictionary containing trace context
            
        Returns:
            OpenTelemetry Context
        """
        if OTEL_AVAILABLE and self._propagator:
            return extract(carrier)
        return None
    
    def get_trace_context(self) -> Optional[SpanContext]:
        """Get current trace context as SpanContext"""
        if not OTEL_AVAILABLE:
            return None
        
        span = trace.get_current_span()
        if span and span.is_recording():
            ctx = span.get_span_context()
            return SpanContext(
                trace_id=format(ctx.trace_id, '032x'),
                span_id=format(ctx.span_id, '016x'),
                trace_flags=ctx.trace_flags,
            )
        return None
    
    # ─── Decorators ────────────────────────────────────────────
    
    def trace(
        self,
        name: str = None,
        kind: 'SpanKind' = None,
        attributes: Dict[str, Any] = None,
    ):
        """
        Decorator to trace a function
        
        Usage:
            @tracer.trace("my_operation")
            def my_function(arg1, arg2):
                pass
            
            # Or use default name (function name)
            @tracer.trace()
            def my_function():
                pass
        """
        def decorator(func: Callable):
            span_name = name or f"{self.component_name}.{func.__name__}"
            
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                with self.start_span(span_name, kind=kind, attributes=attributes) as span:
                    # Add function arguments as attributes
                    span.set_attribute("function.name", func.__name__)
                    span.set_attribute("function.module", func.__module__)
                    
                    return func(*args, **kwargs)
            
            return wrapper
        return decorator
    
    def trace_async(
        self,
        name: str = None,
        kind: 'SpanKind' = None,
        attributes: Dict[str, Any] = None,
    ):
        """
        Decorator to trace an async function
        
        Usage:
            @tracer.trace_async("my_operation")
            async def my_async_function():
                pass
        """
        def decorator(func: Callable):
            span_name = name or f"{self.component_name}.{func.__name__}"
            
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                with self.start_span(span_name, kind=kind, attributes=attributes) as span:
                    span.set_attribute("function.name", func.__name__)
                    span.set_attribute("function.module", func.__module__)
                    
                    return await func(*args, **kwargs)
            
            return wrapper
        return decorator
    
    # ─── Utility Methods ───────────────────────────────────────
    
    def add_event(self, name: str, attributes: Dict[str, Any] = None):
        """Add an event to the current span"""
        span = self.get_current_span()
        if span and span.is_recording():
            span.add_event(name, attributes=attributes or {})
    
    def set_attribute(self, key: str, value: Any):
        """Set an attribute on the current span"""
        span = self.get_current_span()
        if span and span.is_recording():
            span.set_attribute(key, value)
    
    def set_error(self, error: Exception):
        """Mark current span as error and record exception"""
        span = self.get_current_span()
        if span and span.is_recording():
            span.set_status(Status(StatusCode.ERROR, str(error)))
            span.record_exception(error)
    
    def set_ok(self):
        """Mark current span as OK"""
        span = self.get_current_span()
        if span and span.is_recording():
            span.set_status(Status(StatusCode.OK))
    
    def set_error_category(self, error: Exception, category: ErrorCategory):
        """Mark current span as error with category classification"""
        span = self.get_current_span()
        if span and span.is_recording():
            span.set_status(Status(StatusCode.ERROR, str(error)))
            span.set_attribute("error.category", category.value)
            span.set_attribute("error.type", type(error).__name__)
            span.record_exception(error)
    
    # ─── Request Context Tracking ──────────────────────────────
    
    @contextmanager
    def start_request_span(
        self,
        name: str,
        request_context: RequestContext,
        kind: 'SpanKind' = None,
        links: List[Tuple[str, str]] = None,
    ):
        """
        Start a span with full request context
        
        Args:
            name: Span name
            request_context: Request context with metadata
            kind: Span kind
            links: List of (trace_id, span_id) tuples to link to
        
        Usage:
            ctx = RequestContext(request_id="123", user_id="user_1")
            with tracer.start_request_span("handle_request", ctx) as span:
                process_request()
        """
        if not OTEL_AVAILABLE or not self._tracer:
            yield _NoOpSpan()
            return
        
        if kind is None:
            kind = SpanKind.SERVER
        
        # Build attributes from request context
        attributes = request_context.to_attributes()
        attributes["component"] = self.component_name
        
        # Build span links
        span_links = []
        if links:
            for trace_id, span_id in links:
                try:
                    link_context = trace.SpanContext(
                        trace_id=int(trace_id, 16),
                        span_id=int(span_id, 16),
                        is_remote=True,
                        trace_flags=trace.TraceFlags.SAMPLED,
                    )
                    span_links.append(Link(link_context))
                except (ValueError, TypeError):
                    pass
        
        # Set baggage for downstream propagation
        if OTEL_AVAILABLE:
            for key, value in request_context.to_baggage().items():
                set_baggage(key, value)
        
        with self._tracer.start_as_current_span(
            name,
            kind=kind,
            attributes=attributes,
            links=span_links if span_links else None,
        ) as span:
            try:
                yield span
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
    
    @asynccontextmanager
    async def start_request_span_async(
        self,
        name: str,
        request_context: RequestContext,
        kind: 'SpanKind' = None,
    ):
        """Async version of start_request_span"""
        if not OTEL_AVAILABLE or not self._tracer:
            yield _NoOpSpan()
            return
        
        if kind is None:
            kind = SpanKind.SERVER
        
        attributes = request_context.to_attributes()
        attributes["component"] = self.component_name
        
        with self._tracer.start_as_current_span(
            name,
            kind=kind,
            attributes=attributes,
        ) as span:
            try:
                yield span
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
    
    def get_request_id_from_baggage(self) -> Optional[str]:
        """Get request ID from current baggage"""
        if OTEL_AVAILABLE:
            return get_baggage("request_id")
        return None
    
    def get_all_baggage_items(self) -> Dict[str, str]:
        """Get all baggage items"""
        if OTEL_AVAILABLE:
            return dict(get_all_baggage())
        return {}
    
    # ─── Child Span Creation ───────────────────────────────────
    
    @contextmanager
    def start_child_span(
        self,
        name: str,
        kind: 'SpanKind' = None,
        attributes: Dict[str, Any] = None,
    ):
        """
        Start a child span under the current span
        
        Automatically inherits request context from parent.
        """
        if not OTEL_AVAILABLE or not self._tracer:
            yield _NoOpSpan()
            return
        
        # Inherit request context from baggage
        inherited_attrs = {}
        request_id = self.get_request_id_from_baggage()
        if request_id:
            inherited_attrs["request.id"] = request_id
        
        combined_attrs = {**inherited_attrs, **(attributes or {})}
        
        with self.start_span(name, kind=kind, attributes=combined_attrs) as span:
            yield span
    
    # ─── Span Builder ──────────────────────────────────────────
    
    def span_builder(self, name: str) -> 'SpanBuilder':
        """
        Create a fluent span builder
        
        Usage:
            with tracer.span_builder("process_request") \
                .with_kind(SpanKind.SERVER) \
                .with_attribute("http.method", "GET") \
                .with_request_context(request_ctx) \
                .start() as span:
                    process()
        """
        return SpanBuilder(self, name)

    @classmethod
    def get_tracer(cls, component_name: str) -> 'ROATracer':
        """Get or create a tracer for a component"""
        with cls._lock:
            if component_name not in cls._tracers:
                cls._tracers[component_name] = cls(component_name)
            return cls._tracers[component_name]


class _NoOpSpan:
    """No-op span for when tracing is disabled"""
    
    def set_attribute(self, key: str, value: Any):
        pass
    
    def set_status(self, status):
        pass
    
    def record_exception(self, exception: Exception):
        pass
    
    def add_event(self, name: str, attributes: Dict[str, Any] = None):
        pass
    
    def end(self, end_time: int = None):
        pass
    
    def is_recording(self) -> bool:
        return False
    
    def get_span_context(self):
        return _NoOpSpanContext()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass


class _NoOpSpanContext:
    """No-op span context"""
    trace_id = 0
    span_id = 0
    trace_flags = 0


# ─── Span Builder ──────────────────────────────────────────────

class SpanBuilder:
    """
    Fluent builder for creating spans with complex configuration
    
    Usage:
        with tracer.span_builder("process_request") \
            .with_kind(SpanKind.SERVER) \
            .with_attribute("http.method", "GET") \
            .with_request_context(request_ctx) \
            .with_link("abc123", "def456") \
            .start() as span:
                process()
    """
    
    def __init__(self, tracer: ROATracer, name: str):
        self._tracer = tracer
        self._name = name
        self._kind: Optional['SpanKind'] = None
        self._attributes: Dict[str, Any] = {}
        self._request_context: Optional[RequestContext] = None
        self._links: List[Tuple[str, str]] = []
        self._parent_context: Optional['Context'] = None
    
    def with_kind(self, kind: 'SpanKind') -> 'SpanBuilder':
        """Set span kind"""
        self._kind = kind
        return self
    
    def with_attribute(self, key: str, value: Any) -> 'SpanBuilder':
        """Add a single attribute"""
        self._attributes[key] = value
        return self
    
    def with_attributes(self, attributes: Dict[str, Any]) -> 'SpanBuilder':
        """Add multiple attributes"""
        self._attributes.update(attributes)
        return self
    
    def with_request_context(self, ctx: RequestContext) -> 'SpanBuilder':
        """Set request context"""
        self._request_context = ctx
        return self
    
    def with_link(self, trace_id: str, span_id: str) -> 'SpanBuilder':
        """Add a span link"""
        self._links.append((trace_id, span_id))
        return self
    
    def with_parent(self, carrier: Dict[str, str]) -> 'SpanBuilder':
        """Extract parent context from carrier"""
        if OTEL_AVAILABLE:
            self._parent_context = extract(carrier)
        return self
    
    @contextmanager
    def start(self):
        """Start the span with all configured options"""
        if self._request_context:
            self._attributes.update(self._request_context.to_attributes())
        
        # Build links
        span_links = []
        if OTEL_AVAILABLE and self._links:
            for trace_id, span_id in self._links:
                try:
                    link_context = trace.SpanContext(
                        trace_id=int(trace_id, 16),
                        span_id=int(span_id, 16),
                        is_remote=True,
                        trace_flags=trace.TraceFlags.SAMPLED,
                    )
                    span_links.append(Link(link_context))
                except (ValueError, TypeError):
                    pass
        
        with self._tracer.start_span(
            self._name,
            kind=self._kind,
            attributes=self._attributes,
        ) as span:
            yield span
    
    @asynccontextmanager
    async def start_async(self):
        """Start the span asynchronously"""
        if self._request_context:
            self._attributes.update(self._request_context.to_attributes())
        
        with self._tracer.start_span(
            self._name,
            kind=self._kind,
            attributes=self._attributes,
        ) as span:
            yield span


# ─── HTTP Request Span ─────────────────────────────────────────

@dataclass
class HTTPSpanAttributes:
    """HTTP semantic convention attributes"""
    method: str
    url: str
    target: str = ""
    host: str = ""
    scheme: str = "http"
    status_code: Optional[int] = None
    request_content_length: Optional[int] = None
    response_content_length: Optional[int] = None
    user_agent: str = ""
    client_ip: str = ""
    server_name: str = ""
    route: str = ""
    
    def to_attributes(self) -> Dict[str, Any]:
        attrs = {
            "http.method": self.method,
            "http.url": self.url,
            "http.scheme": self.scheme,
        }
        if self.target:
            attrs["http.target"] = self.target
        if self.host:
            attrs["http.host"] = self.host
        if self.status_code is not None:
            attrs["http.status_code"] = self.status_code
        if self.request_content_length is not None:
            attrs["http.request_content_length"] = self.request_content_length
        if self.response_content_length is not None:
            attrs["http.response_content_length"] = self.response_content_length
        if self.user_agent:
            attrs["http.user_agent"] = self.user_agent
        if self.client_ip:
            attrs["net.peer.ip"] = self.client_ip
        if self.server_name:
            attrs["http.server_name"] = self.server_name
        if self.route:
            attrs["http.route"] = self.route
        return attrs


@contextmanager
def http_server_span(
    tracer: ROATracer,
    method: str,
    url: str,
    headers: Dict[str, str] = None,
    route: str = "",
    request_context: RequestContext = None,
):
    """
    Create an HTTP server span with semantic conventions
    
    Usage:
        with http_server_span(tracer, "GET", "/api/robots", headers) as span:
            response = handle_request()
            span.set_attribute("http.status_code", response.status_code)
    """
    # Extract parent context from headers
    parent_ctx = None
    if OTEL_AVAILABLE and headers:
        parent_ctx = extract(headers)
    
    # Build attributes
    attrs = HTTPSpanAttributes(
        method=method,
        url=url,
        route=route,
        user_agent=headers.get("User-Agent", "") if headers else "",
        client_ip=headers.get("X-Forwarded-For", "") if headers else "",
    )
    
    all_attrs = attrs.to_attributes()
    all_attrs["request.type"] = RequestType.HTTP.value
    
    if request_context:
        all_attrs.update(request_context.to_attributes())
    
    with tracer.start_span(
        f"HTTP {method} {route or url}",
        kind=SpanKind.SERVER if OTEL_AVAILABLE else None,
        attributes=all_attrs,
    ) as span:
        yield span


@contextmanager
def http_client_span(
    tracer: ROATracer,
    method: str,
    url: str,
):
    """
    Create an HTTP client span with semantic conventions
    
    Usage:
        with http_client_span(tracer, "POST", "http://api.example.com/data") as span:
            response = requests.post(url, data=payload)
            span.set_attribute("http.status_code", response.status_code)
    """
    attrs = HTTPSpanAttributes(method=method, url=url)
    all_attrs = attrs.to_attributes()
    all_attrs["request.type"] = RequestType.HTTP.value
    
    with tracer.start_span(
        f"HTTP {method}",
        kind=SpanKind.CLIENT if OTEL_AVAILABLE else None,
        attributes=all_attrs,
    ) as span:
        yield span


# ─── gRPC Span ─────────────────────────────────────────────────

@dataclass
class GRPCSpanAttributes:
    """gRPC semantic convention attributes"""
    system: str = "grpc"
    service: str = ""
    method: str = ""
    status_code: Optional[int] = None
    
    def to_attributes(self) -> Dict[str, Any]:
        attrs = {
            "rpc.system": self.system,
        }
        if self.service:
            attrs["rpc.service"] = self.service
        if self.method:
            attrs["rpc.method"] = self.method
        if self.status_code is not None:
            attrs["rpc.grpc.status_code"] = self.status_code
        return attrs


@contextmanager
def grpc_server_span(
    tracer: ROATracer,
    service: str,
    method: str,
    metadata: Dict[str, str] = None,
):
    """
    Create a gRPC server span with semantic conventions
    
    Usage:
        with grpc_server_span(tracer, "RobotService", "MoveArm", context.invocation_metadata()) as span:
            result = handle_grpc_call()
    """
    # Extract parent context
    if OTEL_AVAILABLE and metadata:
        extract(metadata)
    
    attrs = GRPCSpanAttributes(service=service, method=method)
    all_attrs = attrs.to_attributes()
    all_attrs["request.type"] = RequestType.GRPC.value
    
    with tracer.start_span(
        f"gRPC {service}/{method}",
        kind=SpanKind.SERVER if OTEL_AVAILABLE else None,
        attributes=all_attrs,
    ) as span:
        yield span


@contextmanager
def grpc_client_span(
    tracer: ROATracer,
    service: str,
    method: str,
):
    """
    Create a gRPC client span with semantic conventions
    """
    attrs = GRPCSpanAttributes(service=service, method=method)
    all_attrs = attrs.to_attributes()
    all_attrs["request.type"] = RequestType.GRPC.value
    
    with tracer.start_span(
        f"gRPC {service}/{method}",
        kind=SpanKind.CLIENT if OTEL_AVAILABLE else None,
        attributes=all_attrs,
    ) as span:
        yield span


# ─── WebSocket Span ────────────────────────────────────────────

@dataclass
class WebSocketSpanAttributes:
    """WebSocket semantic convention attributes"""
    url: str
    message_type: str = ""  # text, binary
    direction: str = ""     # send, receive
    message_size: Optional[int] = None
    
    def to_attributes(self) -> Dict[str, Any]:
        attrs = {
            "websocket.url": self.url,
            "request.type": RequestType.WEBSOCKET.value,
        }
        if self.message_type:
            attrs["websocket.message_type"] = self.message_type
        if self.direction:
            attrs["websocket.direction"] = self.direction
        if self.message_size is not None:
            attrs["websocket.message_size"] = self.message_size
        return attrs


@contextmanager
def websocket_span(
    tracer: ROATracer,
    url: str,
    direction: str,
    message_type: str = "text",
):
    """
    Create a WebSocket message span
    
    Usage:
        with websocket_span(tracer, "/ws/robots", "receive", "text") as span:
            message = await ws.receive()
            span.set_attribute("websocket.message_size", len(message))
    """
    attrs = WebSocketSpanAttributes(
        url=url,
        direction=direction,
        message_type=message_type,
    )
    
    with tracer.start_span(
        f"WS {direction} {url}",
        kind=SpanKind.CONSUMER if direction == "receive" else SpanKind.PRODUCER if OTEL_AVAILABLE else None,
        attributes=attrs.to_attributes(),
    ) as span:
        yield span


# ─── Database Span ─────────────────────────────────────────────

@dataclass
class DatabaseSpanAttributes:
    """Database semantic convention attributes"""
    system: str          # postgresql, mysql, mongodb, redis
    name: str            # database name
    statement: str = ""  # SQL or query
    operation: str = ""  # SELECT, INSERT, GET, SET
    table: str = ""
    
    def to_attributes(self) -> Dict[str, Any]:
        attrs = {
            "db.system": self.system,
            "db.name": self.name,
            "request.type": RequestType.DATABASE.value,
        }
        if self.statement:
            attrs["db.statement"] = self.statement
        if self.operation:
            attrs["db.operation"] = self.operation
        if self.table:
            attrs["db.sql.table"] = self.table
        return attrs


@contextmanager
def database_span(
    tracer: ROATracer,
    system: str,
    database: str,
    operation: str,
    statement: str = "",
    table: str = "",
):
    """
    Create a database operation span
    
    Usage:
        with database_span(tracer, "postgresql", "robots_db", "SELECT", table="robots") as span:
            result = cursor.execute("SELECT * FROM robots")
    """
    attrs = DatabaseSpanAttributes(
        system=system,
        name=database,
        operation=operation,
        statement=statement,
        table=table,
    )
    
    with tracer.start_span(
        f"DB {operation} {table}" if table else f"DB {operation}",
        kind=SpanKind.CLIENT if OTEL_AVAILABLE else None,
        attributes=attrs.to_attributes(),
    ) as span:
        yield span


# ─── Cache Span ────────────────────────────────────────────────

@dataclass
class CacheSpanAttributes:
    """Cache semantic convention attributes"""
    system: str          # redis, memcached, local
    operation: str       # GET, SET, DELETE
    key: str = ""
    hit: Optional[bool] = None
    ttl: Optional[int] = None
    
    def to_attributes(self) -> Dict[str, Any]:
        attrs = {
            "cache.system": self.system,
            "cache.operation": self.operation,
            "request.type": RequestType.CACHE.value,
        }
        if self.key:
            attrs["cache.key"] = self.key
        if self.hit is not None:
            attrs["cache.hit"] = self.hit
        if self.ttl is not None:
            attrs["cache.ttl"] = self.ttl
        return attrs


@contextmanager
def cache_span(
    tracer: ROATracer,
    system: str,
    operation: str,
    key: str = "",
):
    """
    Create a cache operation span
    
    Usage:
        with cache_span(tracer, "redis", "GET", key="robot:1") as span:
            result = redis_client.get("robot:1")
            span.set_attribute("cache.hit", result is not None)
    """
    attrs = CacheSpanAttributes(
        system=system,
        operation=operation,
        key=key,
    )
    
    with tracer.start_span(
        f"CACHE {operation}" + (f" {key}" if key else ""),
        kind=SpanKind.CLIENT if OTEL_AVAILABLE else None,
        attributes=attrs.to_attributes(),
    ) as span:
        yield span


# ─── Convenience Decorators ────────────────────────────────────

def trace_method(
    name: str = None,
    component: str = "roa",
    kind: 'SpanKind' = None,
):
    """
    Standalone decorator to trace a method
    
    Usage:
        @trace_method("my_operation", component="webthread")
        def my_function():
            pass
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tracer = ROATracer.get_tracer(component)
            span_name = name or func.__name__
            
            with tracer.start_span(span_name, kind=kind):
                return func(*args, **kwargs)
        
        return wrapper
    return decorator


def trace_async_method(
    name: str = None,
    component: str = "roa",
    kind: 'SpanKind' = None,
):
    """
    Standalone decorator to trace an async method
    
    Usage:
        @trace_async_method("my_operation", component="webthread")
        async def my_async_function():
            pass
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = ROATracer.get_tracer(component)
            span_name = name or func.__name__
            
            with tracer.start_span(span_name, kind=kind):
                return await func(*args, **kwargs)
        
        return wrapper
    return decorator


# ─── Context Helpers ───────────────────────────────────────────

class TraceContextMiddleware:
    """
    Middleware for propagating trace context in HTTP requests
    
    Can be used with any ASGI/WSGI framework
    """
    
    def __init__(self, tracer: ROATracer):
        self.tracer = tracer
    
    def extract_from_headers(self, headers: Dict[str, str]) -> Optional['Context']:
        """Extract trace context from HTTP headers"""
        return self.tracer.extract_context(headers)
    
    def inject_to_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Inject trace context into HTTP headers"""
        return self.tracer.inject_context(headers)


def get_trace_id() -> Optional[str]:
    """Get current trace ID"""
    if not OTEL_AVAILABLE:
        return None
    
    span = trace.get_current_span()
    if span and span.is_recording():
        return format(span.get_span_context().trace_id, '032x')
    return None


def get_span_id() -> Optional[str]:
    """Get current span ID"""
    if not OTEL_AVAILABLE:
        return None
    
    span = trace.get_current_span()
    if span and span.is_recording():
        return format(span.get_span_context().span_id, '016x')
    return None


# ─── ROS2 Integration ──────────────────────────────────────────

class ROS2TracingMixin:
    """
    Mixin class for ROS2 nodes to add automatic tracing
    
    Usage:
        class MyNode(Node, ROS2TracingMixin):
            def __init__(self):
                super().__init__('my_node')
                self.init_tracing('my_node')
                
                # Create traced subscription
                self.traced_subscription(
                    String, '/topic', self.callback, 10
                )
    """
    
    _tracer: ROATracer = None
    
    def init_tracing(self, component_name: str):
        """Initialize tracing for ROS2 node"""
        self._tracer = ROATracer.get_tracer(component_name)
    
    def traced_subscription(self, msg_type, topic: str, callback, qos_profile):
        """
        Create a subscription with automatic tracing
        
        Wraps the callback in a span that tracks message processing
        """
        def traced_callback(msg):
            span_name = f"ros2.subscribe.{topic.replace('/', '_').lstrip('_')}"
            with self._tracer.start_span(span_name, kind=SpanKind.CONSUMER if OTEL_AVAILABLE else None) as span:
                span.set_attribute("ros2.topic", topic)
                span.set_attribute("ros2.message_type", msg_type.__name__ if hasattr(msg_type, '__name__') else str(msg_type))
                return callback(msg)
        
        return self.create_subscription(msg_type, topic, traced_callback, qos_profile)
    
    def traced_publish(self, publisher, msg, topic: str = None):
        """
        Publish a message with automatic tracing
        
        Creates a span for the publish operation
        """
        topic_name = topic or getattr(publisher, 'topic_name', 'unknown')
        span_name = f"ros2.publish.{topic_name.replace('/', '_').lstrip('_')}"
        
        with self._tracer.start_span(span_name, kind=SpanKind.PRODUCER if OTEL_AVAILABLE else None) as span:
            span.set_attribute("ros2.topic", topic_name)
            span.set_attribute("ros2.message_type", type(msg).__name__)
            publisher.publish(msg)
    
    def traced_service_call(self, client, request, service_name: str = None):
        """
        Call a service with automatic tracing
        
        Creates a span for the service call
        """
        svc_name = service_name or getattr(client, 'srv_name', 'unknown')
        span_name = f"ros2.service.{svc_name.replace('/', '_').lstrip('_')}"
        
        with self._tracer.start_span(span_name, kind=SpanKind.CLIENT if OTEL_AVAILABLE else None) as span:
            span.set_attribute("ros2.service", svc_name)
            span.set_attribute("ros2.request_type", type(request).__name__)
            return client.call(request)
    
    async def traced_service_call_async(self, client, request, service_name: str = None):
        """Async version of traced_service_call"""
        svc_name = service_name or getattr(client, 'srv_name', 'unknown')
        span_name = f"ros2.service.{svc_name.replace('/', '_').lstrip('_')}"
        
        with self._tracer.start_span(span_name, kind=SpanKind.CLIENT if OTEL_AVAILABLE else None) as span:
            span.set_attribute("ros2.service", svc_name)
            span.set_attribute("ros2.request_type", type(request).__name__)
            return await client.call_async(request)


def trace_ros2_callback(topic: str, component: str = "roa"):
    """
    Decorator to trace ROS2 subscription callbacks
    
    Usage:
        @trace_ros2_callback('/robot/pose', 'dimc')
        def pose_callback(self, msg):
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tracer = ROATracer.get_tracer(component)
            span_name = f"ros2.callback.{topic.replace('/', '_').lstrip('_')}"
            
            with tracer.start_span(span_name, kind=SpanKind.CONSUMER if OTEL_AVAILABLE else None) as span:
                span.set_attribute("ros2.topic", topic)
                span.set_attribute("ros2.callback", func.__name__)
                return func(*args, **kwargs)
        
        return wrapper
    return decorator


def trace_ros2_timer(timer_name: str, component: str = "roa"):
    """
    Decorator to trace ROS2 timer callbacks
    
    Usage:
        @trace_ros2_timer('control_loop', 'roc')
        def control_timer_callback(self):
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tracer = ROATracer.get_tracer(component)
            span_name = f"ros2.timer.{timer_name}"
            
            with tracer.start_span(span_name) as span:
                span.set_attribute("ros2.timer", timer_name)
                return func(*args, **kwargs)
        
        return wrapper
    return decorator


# ─── UE5 Bridge Tracing ────────────────────────────────────────

class UE5TracingContext:
    """
    Context for tracing UE5 bridge operations
    
    Usage:
        ue5_ctx = UE5TracingContext(tracer)
        
        with ue5_ctx.trace_command('spawn_actor', actor_type='robot'):
            ue5_bridge.spawn_actor(...)
    """
    
    def __init__(self, tracer: ROATracer):
        self.tracer = tracer
    
    @contextmanager
    def trace_command(self, command: str, **attributes):
        """Trace a UE5 command"""
        span_name = f"ue5.command.{command}"
        
        with self.tracer.start_span(span_name, kind=SpanKind.CLIENT if OTEL_AVAILABLE else None) as span:
            span.set_attribute("ue5.command", command)
            for key, value in attributes.items():
                span.set_attribute(f"ue5.{key}", value)
            yield span
    
    @contextmanager
    def trace_data_sync(self, sync_type: str, **attributes):
        """Trace UE5 data synchronization"""
        span_name = f"ue5.sync.{sync_type}"
        
        with self.tracer.start_span(span_name) as span:
            span.set_attribute("ue5.sync_type", sync_type)
            for key, value in attributes.items():
                span.set_attribute(f"ue5.{key}", value)
            yield span


# ─── Control Loop Tracing ──────────────────────────────────────

class ControlLoopTracer:
    """
    Specialized tracer for high-frequency control loops
    
    Designed for 60Hz+ control loops with minimal overhead.
    Uses sampling to reduce trace volume.
    
    Usage:
        loop_tracer = ControlLoopTracer(tracer, sample_rate=0.01)  # 1% sampling
        
        while running:
            with loop_tracer.trace_iteration() as span:
                if span:  # May be None if not sampled
                    span.set_attribute("robot_id", "robot_1")
                execute_control()
    """
    
    def __init__(self, tracer: ROATracer, sample_rate: float = 0.01, loop_name: str = "control_loop"):
        self.tracer = tracer
        self.sample_rate = sample_rate
        self.loop_name = loop_name
        self._iteration_count = 0
        self._sample_interval = max(1, int(1.0 / sample_rate)) if sample_rate > 0 else 0
    
    @contextmanager
    def trace_iteration(self):
        """
        Trace a control loop iteration
        
        Only creates a span based on sample_rate
        """
        self._iteration_count += 1
        
        # Check if this iteration should be sampled
        if self._sample_interval > 0 and (self._iteration_count % self._sample_interval) == 0:
            with self.tracer.start_span(f"control.{self.loop_name}") as span:
                span.set_attribute("control.iteration", self._iteration_count)
                yield span
        else:
            yield None
    
    def reset_counter(self):
        """Reset iteration counter"""
        self._iteration_count = 0
