"""
Webthread Observability Integration
====================================
Instrumentation for the Webthread component

Enhanced with:
- HTTP request/response tracking with latency histograms
- WebSocket connection and message metrics
- REST API endpoint monitoring
- Request tracing with trace context propagation
- Rate limiting and circuit breaker metrics

This module adds observability to WebthreadCore without modifying
the original class structure. Use the WebthreadObservability class
to wrap WebthreadCore with full observability support.

Usage:
    from webthread_observability import create_instrumented_webthread
    
    webthread = create_instrumented_webthread(config)
    webthread.start()
"""

import time
import functools
from typing import Optional, Dict, Any, Callable
from contextlib import contextmanager

# Add shared observability to path
import os
import sys
_current_dir = os.path.dirname(os.path.abspath(__file__))
_shared_path = os.path.abspath(os.path.join(_current_dir, '..', '..', '..', '..', 'shared'))
if _shared_path not in sys.path:
    sys.path.insert(0, _shared_path)

try:
    from observability import (
        ROAObservability,
        ROAMetrics,
        ROATracer,
        ROALogger,
        HealthCheck,
        HealthStatus,
        ROAEventRecorder,
        TraceContextMiddleware,
    )
    OBSERVABILITY_AVAILABLE = True
except ImportError as e:
    print(f"Observability not available: {e}")
    OBSERVABILITY_AVAILABLE = False

from .webthread_core import WebthreadCore, ComponentHealth, HealthStatus as WTHealthStatus


class WebthreadMetrics:
    """
    Webthread-specific metrics
    
    Extends ROAMetrics with comprehensive HTTP/WebSocket/API metrics.
    """
    
    def __init__(self, base_metrics: 'ROAMetrics'):
        self.base = base_metrics
        
        # ==================== HTTP Request Metrics ====================
        self.http_requests_total = base_metrics.register_counter(
            'http_requests_total',
            'Total HTTP requests',
            ['method', 'endpoint', 'status_code'],
        )
        
        self.http_request_duration = base_metrics.register_histogram(
            'http_request_duration_seconds',
            'HTTP request duration',
            ['method', 'endpoint'],
            buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
        )
        
        self.http_request_size = base_metrics.register_histogram(
            'http_request_size_bytes',
            'HTTP request body size',
            ['method', 'endpoint'],
            buckets=[64, 256, 1024, 4096, 16384, 65536, 262144, 1048576],
        )
        
        self.http_response_size = base_metrics.register_histogram(
            'http_response_size_bytes',
            'HTTP response body size',
            ['method', 'endpoint'],
            buckets=[64, 256, 1024, 4096, 16384, 65536, 262144, 1048576],
        )
        
        self.http_active_requests = base_metrics.register_gauge(
            'http_active_requests',
            'Currently active HTTP requests',
        )
        
        self.http_errors = base_metrics.register_counter(
            'http_errors_total',
            'HTTP errors by type',
            ['endpoint', 'error_type'],
        )
        
        # ==================== WebSocket Metrics ====================
        self.ws_connections_total = base_metrics.register_counter(
            'ws_connections_total',
            'Total WebSocket connections',
            ['endpoint', 'status'],  # opened, closed, error
        )
        
        self.ws_active_connections = base_metrics.register_gauge(
            'ws_active_connections',
            'Currently active WebSocket connections',
            ['endpoint'],
        )
        
        self.ws_messages_sent = base_metrics.register_counter(
            'ws_messages_sent_total',
            'WebSocket messages sent',
            ['endpoint', 'message_type'],
        )
        
        self.ws_messages_received = base_metrics.register_counter(
            'ws_messages_received_total',
            'WebSocket messages received',
            ['endpoint', 'message_type'],
        )
        
        self.ws_message_size = base_metrics.register_histogram(
            'ws_message_size_bytes',
            'WebSocket message size',
            ['endpoint', 'direction'],  # sent, received
            buckets=[64, 256, 1024, 4096, 16384, 65536],
        )
        
        self.ws_connection_duration = base_metrics.register_histogram(
            'ws_connection_duration_seconds',
            'WebSocket connection duration',
            ['endpoint'],
            buckets=[1, 5, 30, 60, 300, 600, 1800, 3600],
        )
        
        self.ws_ping_latency = base_metrics.register_histogram(
            'ws_ping_latency_seconds',
            'WebSocket ping/pong latency',
            ['endpoint'],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1],
        )
        
        # ==================== REST API Metrics ====================
        self.api_requests_total = base_metrics.register_counter(
            'api_requests_total',
            'Total API requests',
            ['api_version', 'resource', 'operation'],
        )
        
        self.api_latency = base_metrics.register_histogram(
            'api_latency_seconds',
            'API endpoint latency',
            ['api_version', 'resource', 'operation'],
            buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
        )
        
        self.api_rate_limited = base_metrics.register_counter(
            'api_rate_limited_total',
            'Rate limited API requests',
            ['endpoint', 'client_id'],
        )
        
        self.api_auth_attempts = base_metrics.register_counter(
            'api_auth_attempts_total',
            'API authentication attempts',
            ['method', 'status'],  # success, failed, expired
        )
        
        # ==================== HB Subsystem Metrics ====================
        self.hb_heartbeats_received = base_metrics.register_counter(
            'hb_heartbeats_received_total',
            'Total heartbeats received by component',
            ['component', 'source'],
        )
        
        self.hb_heartbeats_missed = base_metrics.register_counter(
            'hb_heartbeats_missed_total',
            'Total missed heartbeats by component',
            ['component'],
        )
        
        self.hb_latency = base_metrics.register_histogram(
            'hb_latency_seconds',
            'Heartbeat round-trip latency',
            ['component', 'target'],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
        )
        
        self.hb_circuit_breaker_state = base_metrics.register_gauge(
            'hb_circuit_breaker_state',
            'Circuit breaker state (0=closed, 1=half-open, 2=open)',
            ['component'],
        )
        
        self.hb_recovery_attempts = base_metrics.register_counter(
            'hb_recovery_attempts_total',
            'Total recovery attempts',
            ['component', 'action', 'success'],
        )
        
        # ==================== UE5 Bridge Metrics ====================
        self.ue5_connected = base_metrics.register_gauge(
            'ue5_connected',
            'UE5 connection status (0=disconnected, 1=connected)',
        )
        
        self.ue5_messages_sent = base_metrics.register_counter(
            'ue5_messages_sent_total',
            'Total messages sent to UE5',
            ['message_type'],
        )
        
        self.ue5_messages_received = base_metrics.register_counter(
            'ue5_messages_received_total',
            'Total messages received from UE5',
            ['message_type'],
        )
        
        self.ue5_reconnect_attempts = base_metrics.register_counter(
            'ue5_reconnect_attempts_total',
            'Total UE5 reconnection attempts',
            ['success'],
        )
        
        self.ue5_latency = base_metrics.register_histogram(
            'ue5_latency_seconds',
            'UE5 message round-trip latency',
            ['message_type'],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1],
        )
        
        # ==================== Component Management Metrics ====================
        self.registered_components = base_metrics.register_gauge(
            'registered_components',
            'Number of registered components',
        )
        
        self.health_checks_total = base_metrics.register_counter(
            'health_checks_total',
            'Total health checks performed',
            ['component', 'status'],
        )
        
        self.health_check_duration = base_metrics.register_histogram(
            'health_check_duration_seconds',
            'Health check duration',
            ['component'],
        )
        
        # ==================== Session Metrics ====================
        self.active_sessions = base_metrics.register_gauge(
            'active_sessions',
            'Number of active user sessions',
        )
        
        self.session_events = base_metrics.register_counter(
            'session_events_total',
            'Session lifecycle events',
            ['event_type'],  # created, expired, invalidated
        )
        
        # ==================== Rate Limiting Metrics ====================
        self.rate_limit_remaining = base_metrics.register_gauge(
            'rate_limit_remaining',
            'Remaining rate limit quota',
            ['endpoint', 'client_id'],
        )
        
        self.rate_limit_resets = base_metrics.register_counter(
            'rate_limit_resets_total',
            'Rate limit reset events',
            ['endpoint'],
        )


class InstrumentedWebthreadCore(WebthreadCore):
    """
    WebthreadCore with full observability instrumentation
    
    This class extends WebthreadCore to add:
    - Structured logging
    - Prometheus metrics
    - OpenTelemetry tracing
    - Health endpoints
    - MCAP recording
    """
    
    def __init__(self, config: Optional[Dict] = None):
        # Initialize observability first
        self._init_observability(config)
        
        # Call parent init
        super().__init__(config)
        
        # Initialize Webthread-specific metrics
        if self._obs:
            self._wt_metrics = WebthreadMetrics(self._obs.metrics)
            
            # Register component dependencies
            self._obs.add_dependency('FTI')
            self._obs.add_dependency('DIMC')
            self._obs.add_dependency('ROC')
            self._obs.add_dependency('COMC')
    
    def _init_observability(self, config: Optional[Dict] = None):
        """Initialize observability components"""
        self._obs: Optional[ROAObservability] = None
        self._wt_metrics: Optional[WebthreadMetrics] = None
        
        if not OBSERVABILITY_AVAILABLE:
            return
        
        try:
            obs_config = config.get('observability', {}) if config else {}
            
            self._obs = ROAObservability(
                component_name='webthread',
                service_version=obs_config.get('version', '1.0.0'),
            )
            
            # Override logger to use observability logger
            self.logger = self._obs.logger
            
        except Exception as e:
            print(f"Failed to initialize observability: {e}")
    
    def start(self):
        """Start with observability"""
        if self._obs:
            with self._obs.tracer.start_span('webthread.start') as span:
                span.set_attribute('hb_enabled', self._hb_enabled)
                
                self._obs.start(start_recording=True)
                self._obs.recorder.record_event('component_starting', {
                    'hb_enabled': self._hb_enabled,
                    'ue5_host': self.ue5_host,
                    'ue5_port': self.ue5_port,
                })
                
                # Call parent start
                super().start()
                
                # Set ready after successful start
                self._obs.set_ready()
                
                # Update metrics
                self._wt_metrics.registered_components.set(len(self.components))
                self._wt_metrics.ue5_connected.set(1 if self.ue5_connected else 0)
        else:
            super().start()
    
    def stop(self):
        """Stop with observability cleanup"""
        if self._obs:
            with self._obs.tracer.start_span('webthread.stop'):
                self._obs.recorder.record_state_change('running', 'stopping')
                super().stop()
                self._obs.stop()
        else:
            super().stop()
    
    def shutdown(self):
        """Shutdown with observability"""
        if self._obs:
            with self._obs.tracer.start_span('webthread.shutdown'):
                self._obs.recorder.record_event('component_shutdown')
                super().shutdown()
                self._obs.stop()
        else:
            super().shutdown()
    
    def monitor_health(self):
        """Monitor health with metrics and tracing"""
        if self._obs and self._wt_metrics:
            with self._obs.tracer.start_span('webthread.monitor_health'):
                start = time.time()
                
                # Call parent monitor
                super().monitor_health()
                
                duration = time.time() - start
                
                # Record metrics for each component
                for name, status in self.component_health.items():
                    self._wt_metrics.health_checks_total.labels(
                        component=name,
                        status=status.status.value,
                    ).inc()
                    
                    self._wt_metrics.health_check_duration.labels(
                        component=name,
                    ).observe(duration)
                    
                    # Update dependency status
                    self._obs.update_dependency_status(
                        name,
                        status.status == ComponentHealth.HEALTHY
                    )
        else:
            super().monitor_health()
    
    def register_component(self, component_name: str, component_instance):
        """Register component with observability"""
        if self._obs:
            with self._obs.tracer.start_span('webthread.register_component') as span:
                span.set_attribute('component_name', component_name)
                
                self._obs.logger.info(
                    f"Registering component: {component_name}",
                    extra={'component': component_name}
                )
                
                super().register_component(component_name, component_instance)
                
                # Update metrics
                if self._wt_metrics:
                    self._wt_metrics.registered_components.set(len(self.components))
                
                # Add as dependency
                self._obs.add_dependency(component_name)
                
                self._obs.recorder.record_event('component_registered', {
                    'component': component_name,
                })
        else:
            super().register_component(component_name, component_instance)
    
    def handle_component_failure(self, component_name: str, error: Exception):
        """Handle failure with observability"""
        if self._obs:
            with self._obs.tracer.start_span('webthread.handle_failure') as span:
                span.set_attribute('component_name', component_name)
                span.set_attribute('error_type', type(error).__name__)
                
                # Record error
                self._obs.record_error(
                    f'component_failure_{component_name}',
                    str(error),
                    error,
                )
                
                super().handle_component_failure(component_name, error)
                
                # Check if we should degrade
                failed_count = sum(
                    1 for s in self.component_health.values()
                    if s.status == ComponentHealth.FAILED
                )
                
                if failed_count > 1:
                    self._obs.set_degraded(f"{failed_count} components failed")
        else:
            super().handle_component_failure(component_name, error)
    
    def reconnect_ue5(self) -> bool:
        """Reconnect with observability"""
        if self._obs and self._wt_metrics:
            with self._obs.tracer.start_span('webthread.reconnect_ue5') as span:
                result = super().reconnect_ue5()
                
                span.set_attribute('success', result)
                self._wt_metrics.ue5_reconnect_attempts.labels(
                    success=str(result).lower()
                ).inc()
                self._wt_metrics.ue5_connected.set(1 if result else 0)
                
                self._obs.recorder.record_event('ue5_reconnect', {
                    'success': result,
                })
                
                return result
        else:
            return super().reconnect_ue5()
    
    # ─── HB Subsystem Instrumentation ──────────────────────────
    
    def _on_hb_health_change(self, component_name: str, status):
        """Handle health change with metrics"""
        if self._obs and self._wt_metrics:
            self._obs.logger.debug(
                f"HB health change: {component_name}",
                extra={
                    'component': component_name,
                    'health': status.health.value if hasattr(status, 'health') else 'unknown',
                }
            )
        
        super()._on_hb_health_change(component_name, status)
    
    def _on_hb_critical_failure(self, component_name: str, failure):
        """Handle critical failure with full observability"""
        if self._obs:
            self._obs.record_error(
                f'hb_critical_failure',
                failure.details if hasattr(failure, 'details') else str(failure),
            )
            
            if self._wt_metrics:
                self._wt_metrics.hb_heartbeats_missed.labels(
                    component=component_name
                ).inc()
        
        super()._on_hb_critical_failure(component_name, failure)
    
    def _execute_restart_recovery(self, component_name: str) -> bool:
        """Execute restart with metrics"""
        if self._obs:
            with self._obs.tracer.start_span('webthread.recovery.restart') as span:
                span.set_attribute('component', component_name)
                
                result = super()._execute_restart_recovery(component_name)
                
                span.set_attribute('success', result)
                
                if self._wt_metrics:
                    self._wt_metrics.hb_recovery_attempts.labels(
                        component=component_name,
                        action='restart',
                        success=str(result).lower(),
                    ).inc()
                
                return result
        else:
            return super()._execute_restart_recovery(component_name)
    
    # ─── Observability Access ──────────────────────────────────
    
    def get_observability(self) -> Optional[ROAObservability]:
        """Get the observability instance"""
        return self._obs
    
    def get_wt_metrics(self) -> Optional[WebthreadMetrics]:
        """Get Webthread-specific metrics"""
        return self._wt_metrics
    
    # ==================== HTTP Request Instrumentation ====================
    
    def record_http_request(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration: float = None,
        request_size: int = None,
        response_size: int = None,
    ):
        """Record HTTP request metrics"""
        if self._wt_metrics:
            self._wt_metrics.http_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status_code=str(status_code),
            ).inc()
            
            if duration is not None:
                self._wt_metrics.http_request_duration.labels(
                    method=method,
                    endpoint=endpoint,
                ).observe(duration)
            
            if request_size is not None:
                self._wt_metrics.http_request_size.labels(
                    method=method,
                    endpoint=endpoint,
                ).observe(request_size)
            
            if response_size is not None:
                self._wt_metrics.http_response_size.labels(
                    method=method,
                    endpoint=endpoint,
                ).observe(response_size)
    
    def record_http_error(self, endpoint: str, error_type: str):
        """Record HTTP error"""
        if self._wt_metrics:
            self._wt_metrics.http_errors.labels(
                endpoint=endpoint,
                error_type=error_type,
            ).inc()
    
    @contextmanager
    def trace_http_request(self, method: str, endpoint: str, request_id: str = None):
        """
        Context manager for tracing HTTP requests
        
        Usage:
            with webthread.trace_http_request('GET', '/api/v1/status') as ctx:
                response = handle_request()
                ctx.set_status(200)
                ctx.set_response_size(len(response))
        """
        start_time = time.perf_counter()
        result = {'status_code': 200, 'response_size': None, 'request_size': None}
        
        class RequestContext:
            def set_status(self, code: int):
                result['status_code'] = code
            
            def set_response_size(self, size: int):
                result['response_size'] = size
            
            def set_request_size(self, size: int):
                result['request_size'] = size
        
        if self._wt_metrics:
            self._wt_metrics.http_active_requests.inc()
        
        try:
            if self._obs:
                with self._obs.tracer.start_span(
                    f'http.{method}.{endpoint}',
                    attributes={
                        'http.method': method,
                        'http.endpoint': endpoint,
                        'http.request_id': request_id or '',
                        'component': 'webthread',
                    }
                ):
                    yield RequestContext()
            else:
                yield RequestContext()
        finally:
            if self._wt_metrics:
                self._wt_metrics.http_active_requests.dec()
            
            duration = time.perf_counter() - start_time
            self.record_http_request(
                method, endpoint, result['status_code'],
                duration=duration,
                request_size=result['request_size'],
                response_size=result['response_size'],
            )
    
    # ==================== WebSocket Instrumentation ====================
    
    def record_ws_connection(self, endpoint: str, status: str):
        """Record WebSocket connection event: status is 'opened', 'closed', or 'error'"""
        if self._wt_metrics:
            self._wt_metrics.ws_connections_total.labels(
                endpoint=endpoint,
                status=status,
            ).inc()
            
            if status == 'opened':
                current = self._wt_metrics.ws_active_connections.labels(
                    endpoint=endpoint
                )._value.get() or 0
                self._wt_metrics.ws_active_connections.labels(endpoint=endpoint).set(current + 1)
            elif status in ('closed', 'error'):
                current = self._wt_metrics.ws_active_connections.labels(
                    endpoint=endpoint
                )._value.get() or 0
                self._wt_metrics.ws_active_connections.labels(endpoint=endpoint).set(max(0, current - 1))
    
    def record_ws_message(
        self,
        endpoint: str,
        direction: str,
        message_type: str,
        size: int = None,
    ):
        """Record WebSocket message: direction is 'sent' or 'received'"""
        if self._wt_metrics:
            if direction == 'sent':
                self._wt_metrics.ws_messages_sent.labels(
                    endpoint=endpoint,
                    message_type=message_type,
                ).inc()
            else:
                self._wt_metrics.ws_messages_received.labels(
                    endpoint=endpoint,
                    message_type=message_type,
                ).inc()
            
            if size is not None:
                self._wt_metrics.ws_message_size.labels(
                    endpoint=endpoint,
                    direction=direction,
                ).observe(size)
    
    def record_ws_ping_latency(self, endpoint: str, latency: float):
        """Record WebSocket ping/pong latency"""
        if self._wt_metrics:
            self._wt_metrics.ws_ping_latency.labels(endpoint=endpoint).observe(latency)
    
    @contextmanager
    def trace_ws_connection(self, endpoint: str, connection_id: str = None):
        """
        Context manager for tracing WebSocket connection lifecycle
        
        Usage:
            with webthread.trace_ws_connection('/ws/robot') as conn:
                handle_connection()
        """
        start_time = time.perf_counter()
        self.record_ws_connection(endpoint, 'opened')
        
        try:
            if self._obs:
                with self._obs.tracer.start_span(
                    f'ws.connection.{endpoint}',
                    attributes={
                        'ws.endpoint': endpoint,
                        'ws.connection_id': connection_id or '',
                        'component': 'webthread',
                    }
                ):
                    yield
            else:
                yield
        except Exception:
            self.record_ws_connection(endpoint, 'error')
            raise
        finally:
            self.record_ws_connection(endpoint, 'closed')
            duration = time.perf_counter() - start_time
            if self._wt_metrics:
                self._wt_metrics.ws_connection_duration.labels(
                    endpoint=endpoint
                ).observe(duration)
    
    # ==================== REST API Instrumentation ====================
    
    def record_api_request(
        self,
        api_version: str,
        resource: str,
        operation: str,
        latency: float = None,
    ):
        """Record REST API request"""
        if self._wt_metrics:
            self._wt_metrics.api_requests_total.labels(
                api_version=api_version,
                resource=resource,
                operation=operation,
            ).inc()
            
            if latency is not None:
                self._wt_metrics.api_latency.labels(
                    api_version=api_version,
                    resource=resource,
                    operation=operation,
                ).observe(latency)
    
    def record_api_rate_limited(self, endpoint: str, client_id: str):
        """Record rate limited request"""
        if self._wt_metrics:
            self._wt_metrics.api_rate_limited.labels(
                endpoint=endpoint,
                client_id=client_id,
            ).inc()
    
    def record_auth_attempt(self, method: str, status: str):
        """Record authentication attempt: status is 'success', 'failed', or 'expired'"""
        if self._wt_metrics:
            self._wt_metrics.api_auth_attempts.labels(
                method=method,
                status=status,
            ).inc()
    
    @contextmanager
    def trace_api_request(
        self,
        api_version: str,
        resource: str,
        operation: str,
        request_id: str = None,
    ):
        """
        Context manager for tracing REST API requests
        
        Usage:
            with webthread.trace_api_request('v1', 'robot', 'get_status'):
                return get_robot_status()
        """
        start_time = time.perf_counter()
        
        try:
            if self._obs:
                with self._obs.tracer.start_span(
                    f'api.{api_version}.{resource}.{operation}',
                    attributes={
                        'api.version': api_version,
                        'api.resource': resource,
                        'api.operation': operation,
                        'api.request_id': request_id or '',
                        'component': 'webthread',
                    }
                ):
                    yield
            else:
                yield
        finally:
            latency = time.perf_counter() - start_time
            self.record_api_request(api_version, resource, operation, latency)
    
    # ==================== Session Management ====================
    
    def set_active_sessions(self, count: int):
        """Set number of active sessions"""
        if self._wt_metrics:
            self._wt_metrics.active_sessions.set(count)
    
    def record_session_event(self, event_type: str):
        """Record session event: 'created', 'expired', or 'invalidated'"""
        if self._wt_metrics:
            self._wt_metrics.session_events.labels(event_type=event_type).inc()
    
    # ==================== UE5 Bridge Enhanced Instrumentation ====================
    
    def record_ue5_message(
        self,
        message_type: str,
        direction: str,
        latency: float = None,
    ):
        """Record UE5 message: direction is 'sent' or 'received'"""
        if self._wt_metrics:
            if direction == 'sent':
                self._wt_metrics.ue5_messages_sent.labels(message_type=message_type).inc()
            else:
                self._wt_metrics.ue5_messages_received.labels(message_type=message_type).inc()
            
            if latency is not None:
                self._wt_metrics.ue5_latency.labels(message_type=message_type).observe(latency)
    
    @contextmanager
    def trace_ue5_message(self, message_type: str, message_id: str = None):
        """Context manager for tracing UE5 messages"""
        start_time = time.perf_counter()
        
        try:
            if self._obs:
                with self._obs.tracer.start_span(
                    f'ue5.message.{message_type}',
                    attributes={
                        'ue5.message_type': message_type,
                        'ue5.message_id': message_id or '',
                        'component': 'webthread',
                    }
                ):
                    yield
            else:
                yield
        finally:
            latency = time.perf_counter() - start_time
            self.record_ue5_message(message_type, 'sent', latency)


def create_instrumented_webthread(config: Optional[Dict] = None) -> InstrumentedWebthreadCore:
    """
    Factory function to create an instrumented WebthreadCore
    
    Args:
        config: Configuration dictionary
        
    Returns:
        InstrumentedWebthreadCore instance
    """
    return InstrumentedWebthreadCore(config)


# ─── Decorators for existing functions ─────────────────────────

def traced(tracer: 'ROATracer'):
    """
    Decorator to add tracing to a function
    
    Usage:
        @traced(obs.tracer)
        def my_function():
            pass
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with tracer.start_span(func.__name__):
                return func(*args, **kwargs)
        return wrapper
    return decorator


def metered(metrics: 'ROAMetrics', method_name: str = None):
    """
    Decorator to add metrics to a function
    
    Usage:
        @metered(obs.metrics, "process_request")
        def my_function():
            pass
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            name = method_name or func.__name__
            with metrics.time_request(name, 'internal'):
                return func(*args, **kwargs)
        return wrapper
    return decorator
