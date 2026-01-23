"""
ROA Prometheus Metrics
======================
Prometheus metrics collection and exposition

Features:
- Pre-defined ROA metrics (heartbeat, component health, requests, etc.)
- Custom metric registration
- HTTP metrics server
- Push gateway support
- Metric decorators for automatic instrumentation
"""

import time
import threading
import functools
from typing import Optional, Dict, Any, Callable, List, Union
from dataclasses import dataclass
from enum import Enum
from http.server import HTTPServer, BaseHTTPRequestHandler
import socket

try:
    from prometheus_client import (
        Counter, Gauge, Histogram, Summary, Info,
        CollectorRegistry, REGISTRY,
        generate_latest, CONTENT_TYPE_LATEST,
        push_to_gateway, delete_from_gateway,
        multiprocess, CollectorRegistry as MultiRegistry,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Stub classes for when prometheus_client is not installed
    class Counter:
        def __init__(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def inc(self, *args, **kwargs): pass
    class Gauge:
        def __init__(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def set(self, *args, **kwargs): pass
        def inc(self, *args, **kwargs): pass
        def dec(self, *args, **kwargs): pass
    class Histogram:
        def __init__(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def observe(self, *args, **kwargs): pass
        def time(self): return _TimerStub()
    class Summary:
        def __init__(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def observe(self, *args, **kwargs): pass
    class Info:
        def __init__(self, *args, **kwargs): pass
        def info(self, *args, **kwargs): pass
    class _TimerStub:
        def __enter__(self): return self
        def __exit__(self, *args): pass
    REGISTRY = None

from .config import ObservabilityConfig, MetricsConfig


class MetricType(Enum):
    """Metric types"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"
    INFO = "info"


@dataclass
class MetricDefinition:
    """Definition for a custom metric"""
    name: str
    type: MetricType
    description: str
    labels: List[str] = None
    buckets: List[float] = None  # For histograms


class ROAMetrics:
    """
    ROA Metrics Collection
    
    Provides pre-defined metrics for ROA components and allows
    custom metric registration.
    
    Usage:
        metrics = ROAMetrics("webthread")
        
        # Use pre-defined metrics
        metrics.heartbeat_total.labels(component="webthread").inc()
        metrics.request_duration.labels(method="process").observe(0.5)
        
        # Register custom metrics
        metrics.register_counter("custom_events", "Custom event count", ["event_type"])
        metrics.custom_events.labels(event_type="foo").inc()
    """
    
    # Default histogram buckets for request durations (in seconds)
    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)
    
    def __init__(
        self,
        component_name: str,
        config: Optional[Union[ObservabilityConfig, MetricsConfig]] = None,
        registry: 'CollectorRegistry' = None,
    ):
        self.component_name = component_name
        
        # Extract metrics config
        if isinstance(config, ObservabilityConfig):
            self.config = config.metrics
            self.service_version = config.service_version
        elif isinstance(config, MetricsConfig):
            self.config = config
            self.service_version = "1.0.0"
        else:
            self.config = MetricsConfig()
            self.service_version = "1.0.0"
        
        self.namespace = self.config.namespace
        self.subsystem = self.config.subsystem or component_name
        self.registry = registry or (REGISTRY if PROMETHEUS_AVAILABLE else None)
        
        self._custom_metrics: Dict[str, Any] = {}
        self._lock = threading.Lock()
        
        # Initialize pre-defined metrics
        self._init_core_metrics()
    
    def _metric_name(self, name: str) -> str:
        """Generate full metric name with namespace and subsystem"""
        parts = [p for p in [self.namespace, self.subsystem, name] if p]
        return "_".join(parts)
    
    def _init_core_metrics(self):
        """Initialize core ROA metrics"""
        
        if not PROMETHEUS_AVAILABLE:
            # Create stubs
            self.info = Info('', '')
            self.heartbeat_total = Counter('', '')
            self.heartbeat_latency = Histogram('', '')
            self.component_status = Gauge('', '')
            self.component_health = Gauge('', '')
            self.request_total = Counter('', '')
            self.request_duration = Histogram('', '')
            self.request_in_progress = Gauge('', '')
            self.errors_total = Counter('', '')
            self.connections_active = Gauge('', '')
            self.messages_sent = Counter('', '')
            self.messages_received = Counter('', '')
            self.message_size = Histogram('', '')
            self.cpu_usage = Gauge('', '')
            self.memory_usage = Gauge('', '')
            self.uptime = Gauge('', '')
            return
        
        # Component info
        self.info = Info(
            self._metric_name('info'),
            'Component information',
            registry=self.registry,
        )
        self.info.info({
            'version': self.service_version,
            'component': self.component_name,
        })
        
        # ─── Heartbeat Metrics ─────────────────────────────────
        self.heartbeat_total = Counter(
            self._metric_name('heartbeat_total'),
            'Total heartbeats sent',
            ['component', 'target'],
            registry=self.registry,
        )
        
        self.heartbeat_latency = Histogram(
            self._metric_name('heartbeat_latency_seconds'),
            'Heartbeat round-trip latency',
            ['component', 'target'],
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
            registry=self.registry,
        )
        
        # ─── Component Status Metrics ──────────────────────────
        self.component_status = Gauge(
            self._metric_name('component_status'),
            'Component status (0=unknown, 1=initializing, 2=running, 3=degraded, 4=error, 5=stopped)',
            ['component'],
            registry=self.registry,
        )
        
        self.component_health = Gauge(
            self._metric_name('component_health'),
            'Component health score (0-100)',
            ['component'],
            registry=self.registry,
        )
        
        # ─── Request Metrics ───────────────────────────────────
        self.request_total = Counter(
            self._metric_name('request_total'),
            'Total requests processed',
            ['method', 'status', 'source'],
            registry=self.registry,
        )
        
        self.request_duration = Histogram(
            self._metric_name('request_duration_seconds'),
            'Request duration in seconds',
            ['method', 'source'],
            buckets=self.DEFAULT_BUCKETS,
            registry=self.registry,
        )
        
        self.request_in_progress = Gauge(
            self._metric_name('request_in_progress'),
            'Number of requests currently being processed',
            ['method'],
            registry=self.registry,
        )
        
        # ─── Error Metrics ─────────────────────────────────────
        self.errors_total = Counter(
            self._metric_name('errors_total'),
            'Total errors',
            ['error_type', 'severity'],
            registry=self.registry,
        )
        
        # ─── Connection Metrics ────────────────────────────────
        self.connections_active = Gauge(
            self._metric_name('connections_active'),
            'Number of active connections',
            ['connection_type', 'target'],
            registry=self.registry,
        )
        
        # ─── Message Metrics ───────────────────────────────────
        self.messages_sent = Counter(
            self._metric_name('messages_sent_total'),
            'Total messages sent',
            ['message_type', 'destination'],
            registry=self.registry,
        )
        
        self.messages_received = Counter(
            self._metric_name('messages_received_total'),
            'Total messages received',
            ['message_type', 'source'],
            registry=self.registry,
        )
        
        self.message_size = Histogram(
            self._metric_name('message_size_bytes'),
            'Message size in bytes',
            ['message_type', 'direction'],
            buckets=(64, 256, 1024, 4096, 16384, 65536, 262144, 1048576),
            registry=self.registry,
        )
        
        # ─── Resource Metrics ──────────────────────────────────
        self.cpu_usage = Gauge(
            self._metric_name('cpu_usage_percent'),
            'CPU usage percentage',
            registry=self.registry,
        )
        
        self.memory_usage = Gauge(
            self._metric_name('memory_usage_bytes'),
            'Memory usage in bytes',
            ['type'],  # rss, vms, shared
            registry=self.registry,
        )
        
        # ─── Robotics-Specific Metrics ─────────────────────────
        self._init_robotics_metrics()
    
    def _init_robotics_metrics(self):
        """Initialize robotics-specific metrics for ROA"""
        
        if not PROMETHEUS_AVAILABLE:
            # Create stubs
            self.robot_pose_updates = Counter('', '')
            self.robot_velocity = Gauge('', '')
            self.joint_position = Gauge('', '')
            self.joint_velocity = Gauge('', '')
            self.joint_effort = Gauge('', '')
            self.sensor_readings = Counter('', '')
            self.sensor_latency = Histogram('', '')
            self.obstacle_distance = Gauge('', '')
            self.obstacles_detected = Counter('', '')
            self.safety_zone_violations = Counter('', '')
            self.safety_mode = Gauge('', '')
            self.control_loop_duration = Histogram('', '')
            self.control_mode = Gauge('', '')
            self.path_planning_duration = Histogram('', '')
            self.paths_planned = Counter('', '')
            self.evade_maneuvers = Counter('', '')
            self.ros2_messages_published = Counter('', '')
            self.ros2_messages_subscribed = Counter('', '')
            self.ros2_service_calls = Counter('', '')
            self.ros2_action_goals = Counter('', '')
            return
        
        # ─── Robot Pose & Motion Metrics ───────────────────────
        self.robot_pose_updates = Counter(
            self._metric_name('robot_pose_updates_total'),
            'Total robot pose updates received',
            ['robot_id', 'source'],
            registry=self.registry,
        )
        
        self.robot_velocity = Gauge(
            self._metric_name('robot_velocity'),
            'Robot velocity (m/s or rad/s)',
            ['robot_id', 'axis'],  # axis: x, y, z, roll, pitch, yaw
            registry=self.registry,
        )
        
        # ─── Joint Metrics ─────────────────────────────────────
        self.joint_position = Gauge(
            self._metric_name('joint_position'),
            'Joint position (radians or meters)',
            ['robot_id', 'joint_name'],
            registry=self.registry,
        )
        
        self.joint_velocity = Gauge(
            self._metric_name('joint_velocity'),
            'Joint velocity',
            ['robot_id', 'joint_name'],
            registry=self.registry,
        )
        
        self.joint_effort = Gauge(
            self._metric_name('joint_effort'),
            'Joint effort/torque',
            ['robot_id', 'joint_name'],
            registry=self.registry,
        )
        
        # ─── Sensor Metrics ────────────────────────────────────
        self.sensor_readings = Counter(
            self._metric_name('sensor_readings_total'),
            'Total sensor readings',
            ['robot_id', 'sensor_type', 'sensor_id'],
            registry=self.registry,
        )
        
        self.sensor_latency = Histogram(
            self._metric_name('sensor_latency_seconds'),
            'Sensor reading latency',
            ['sensor_type'],
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1),
            registry=self.registry,
        )
        
        # ─── Obstacle & Safety Metrics ─────────────────────────
        self.obstacle_distance = Gauge(
            self._metric_name('obstacle_distance_meters'),
            'Distance to nearest obstacle',
            ['robot_id', 'direction'],  # direction: front, back, left, right
            registry=self.registry,
        )
        
        self.obstacles_detected = Counter(
            self._metric_name('obstacles_detected_total'),
            'Total obstacles detected',
            ['robot_id', 'severity'],  # severity: info, warning, critical
            registry=self.registry,
        )
        
        self.safety_zone_violations = Counter(
            self._metric_name('safety_zone_violations_total'),
            'Safety zone violations',
            ['robot_id', 'zone_type'],  # zone_type: personal, work, restricted
            registry=self.registry,
        )
        
        self.safety_mode = Gauge(
            self._metric_name('safety_mode'),
            'Current safety mode (0=fragile, 1=standard, 2=robust)',
            ['robot_id'],
            registry=self.registry,
        )
        
        # ─── Control Metrics ───────────────────────────────────
        self.control_loop_duration = Histogram(
            self._metric_name('control_loop_duration_seconds'),
            'Control loop execution time',
            ['robot_id', 'controller'],
            buckets=(0.001, 0.002, 0.005, 0.01, 0.016, 0.02, 0.05),  # Targeting ~60Hz
            registry=self.registry,
        )
        
        self.control_mode = Gauge(
            self._metric_name('control_mode'),
            'Control mode (0=RPM, 1=ADM)',
            ['robot_id'],
            registry=self.registry,
        )
        
        # ─── Path Planning & Evade Metrics ─────────────────────
        self.path_planning_duration = Histogram(
            self._metric_name('path_planning_duration_seconds'),
            'Path planning computation time',
            ['robot_id', 'algorithm'],  # algorithm: astar, rrt, rrt_star
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
            registry=self.registry,
        )
        
        self.paths_planned = Counter(
            self._metric_name('paths_planned_total'),
            'Total paths planned',
            ['robot_id', 'algorithm', 'status'],
            registry=self.registry,
        )
        
        self.evade_maneuvers = Counter(
            self._metric_name('evade_maneuvers_total'),
            'Total evade maneuvers executed',
            ['robot_id', 'trigger', 'result'],  # trigger: obstacle, proximity, command
            registry=self.registry,
        )
        
        # ─── ROS2 Integration Metrics ──────────────────────────
        self.ros2_messages_published = Counter(
            self._metric_name('ros2_messages_published_total'),
            'ROS2 messages published',
            ['topic', 'message_type'],
            registry=self.registry,
        )
        
        self.ros2_messages_subscribed = Counter(
            self._metric_name('ros2_messages_subscribed_total'),
            'ROS2 messages received via subscription',
            ['topic', 'message_type'],
            registry=self.registry,
        )
        
        self.ros2_service_calls = Counter(
            self._metric_name('ros2_service_calls_total'),
            'ROS2 service calls',
            ['service', 'status'],
            registry=self.registry,
        )
        
        self.ros2_action_goals = Counter(
            self._metric_name('ros2_action_goals_total'),
            'ROS2 action goals',
            ['action', 'status'],
            registry=self.registry,
        )
        self.uptime = Gauge(
            self._metric_name('uptime_seconds'),
            'Component uptime in seconds',
            registry=self.registry,
        )
    
    # ─── Custom Metric Registration ────────────────────────────
    
    def register_counter(
        self,
        name: str,
        description: str,
        labels: List[str] = None,
    ) -> Counter:
        """Register a custom counter metric"""
        with self._lock:
            if name in self._custom_metrics:
                return self._custom_metrics[name]
            
            if PROMETHEUS_AVAILABLE:
                metric = Counter(
                    self._metric_name(name),
                    description,
                    labels or [],
                    registry=self.registry,
                )
            else:
                metric = Counter()
            
            self._custom_metrics[name] = metric
            setattr(self, name, metric)
            return metric
    
    def register_gauge(
        self,
        name: str,
        description: str,
        labels: List[str] = None,
    ) -> Gauge:
        """Register a custom gauge metric"""
        with self._lock:
            if name in self._custom_metrics:
                return self._custom_metrics[name]
            
            if PROMETHEUS_AVAILABLE:
                metric = Gauge(
                    self._metric_name(name),
                    description,
                    labels or [],
                    registry=self.registry,
                )
            else:
                metric = Gauge()
            
            self._custom_metrics[name] = metric
            setattr(self, name, metric)
            return metric
    
    def register_histogram(
        self,
        name: str,
        description: str,
        labels: List[str] = None,
        buckets: List[float] = None,
    ) -> Histogram:
        """Register a custom histogram metric"""
        with self._lock:
            if name in self._custom_metrics:
                return self._custom_metrics[name]
            
            if PROMETHEUS_AVAILABLE:
                metric = Histogram(
                    self._metric_name(name),
                    description,
                    labels or [],
                    buckets=buckets or self.DEFAULT_BUCKETS,
                    registry=self.registry,
                )
            else:
                metric = Histogram()
            
            self._custom_metrics[name] = metric
            setattr(self, name, metric)
            return metric
    
    def register_summary(
        self,
        name: str,
        description: str,
        labels: List[str] = None,
    ) -> Summary:
        """Register a custom summary metric"""
        with self._lock:
            if name in self._custom_metrics:
                return self._custom_metrics[name]
            
            if PROMETHEUS_AVAILABLE:
                metric = Summary(
                    self._metric_name(name),
                    description,
                    labels or [],
                    registry=self.registry,
                )
            else:
                metric = Summary()
            
            self._custom_metrics[name] = metric
            setattr(self, name, metric)
            return metric
    
    # ─── Convenience Methods ───────────────────────────────────
    
    def set_status(self, status: int, component: str = None):
        """Set component status"""
        self.component_status.labels(component=component or self.component_name).set(status)
    
    def set_health(self, health: float, component: str = None):
        """Set component health score (0-100)"""
        self.component_health.labels(component=component or self.component_name).set(health)
    
    def record_heartbeat(self, target: str, latency: float = None):
        """Record a heartbeat"""
        self.heartbeat_total.labels(
            component=self.component_name,
            target=target
        ).inc()
        
        if latency is not None:
            self.heartbeat_latency.labels(
                component=self.component_name,
                target=target
            ).observe(latency)
    
    def record_request(
        self,
        method: str,
        status: str,
        source: str,
        duration: float = None,
    ):
        """Record a request"""
        self.request_total.labels(
            method=method,
            status=status,
            source=source,
        ).inc()
        
        if duration is not None:
            self.request_duration.labels(
                method=method,
                source=source,
            ).observe(duration)
    
    def record_error(self, error_type: str, severity: str = "error"):
        """Record an error"""
        self.errors_total.labels(
            error_type=error_type,
            severity=severity,
        ).inc()
    
    def time_request(self, method: str, source: str = "unknown"):
        """Context manager for timing requests"""
        return _RequestTimer(self, method, source)
    
    # ─── Robotics Convenience Methods ──────────────────────────
    
    def record_robot_pose(self, robot_id: str, source: str = "dimc"):
        """Record a robot pose update"""
        self.robot_pose_updates.labels(robot_id=robot_id, source=source).inc()
    
    def set_robot_velocity(self, robot_id: str, vx: float, vy: float, vz: float, 
                           roll: float = 0, pitch: float = 0, yaw: float = 0):
        """Set robot velocity components"""
        self.robot_velocity.labels(robot_id=robot_id, axis='x').set(vx)
        self.robot_velocity.labels(robot_id=robot_id, axis='y').set(vy)
        self.robot_velocity.labels(robot_id=robot_id, axis='z').set(vz)
        self.robot_velocity.labels(robot_id=robot_id, axis='roll').set(roll)
        self.robot_velocity.labels(robot_id=robot_id, axis='pitch').set(pitch)
        self.robot_velocity.labels(robot_id=robot_id, axis='yaw').set(yaw)
    
    def set_joint_state(self, robot_id: str, joint_name: str, 
                        position: float, velocity: float = None, effort: float = None):
        """Set joint state metrics"""
        self.joint_position.labels(robot_id=robot_id, joint_name=joint_name).set(position)
        if velocity is not None:
            self.joint_velocity.labels(robot_id=robot_id, joint_name=joint_name).set(velocity)
        if effort is not None:
            self.joint_effort.labels(robot_id=robot_id, joint_name=joint_name).set(effort)
    
    def record_sensor_reading(self, robot_id: str, sensor_type: str, 
                               sensor_id: str, latency: float = None):
        """Record a sensor reading"""
        self.sensor_readings.labels(
            robot_id=robot_id, sensor_type=sensor_type, sensor_id=sensor_id
        ).inc()
        if latency is not None:
            self.sensor_latency.labels(sensor_type=sensor_type).observe(latency)
    
    def set_obstacle_distance(self, robot_id: str, direction: str, distance: float):
        """Set distance to obstacle in a direction"""
        self.obstacle_distance.labels(robot_id=robot_id, direction=direction).set(distance)
    
    def record_obstacle_detected(self, robot_id: str, severity: str = "warning"):
        """Record an obstacle detection event"""
        self.obstacles_detected.labels(robot_id=robot_id, severity=severity).inc()
    
    def record_safety_violation(self, robot_id: str, zone_type: str):
        """Record a safety zone violation"""
        self.safety_zone_violations.labels(robot_id=robot_id, zone_type=zone_type).inc()
    
    def set_safety_mode(self, robot_id: str, mode: int):
        """Set safety mode (0=fragile, 1=standard, 2=robust)"""
        self.safety_mode.labels(robot_id=robot_id).set(mode)
    
    def record_control_loop(self, robot_id: str, controller: str, duration: float):
        """Record control loop execution"""
        self.control_loop_duration.labels(robot_id=robot_id, controller=controller).observe(duration)
    
    def set_control_mode(self, robot_id: str, mode: int):
        """Set control mode (0=RPM, 1=ADM)"""
        self.control_mode.labels(robot_id=robot_id).set(mode)
    
    def record_path_planned(self, robot_id: str, algorithm: str, status: str, duration: float):
        """Record path planning execution"""
        self.paths_planned.labels(robot_id=robot_id, algorithm=algorithm, status=status).inc()
        self.path_planning_duration.labels(robot_id=robot_id, algorithm=algorithm).observe(duration)
    
    def record_evade_maneuver(self, robot_id: str, trigger: str, result: str):
        """Record an evade maneuver"""
        self.evade_maneuvers.labels(robot_id=robot_id, trigger=trigger, result=result).inc()
    
    def record_ros2_publish(self, topic: str, message_type: str):
        """Record ROS2 message publication"""
        self.ros2_messages_published.labels(topic=topic, message_type=message_type).inc()
    
    def record_ros2_subscribe(self, topic: str, message_type: str):
        """Record ROS2 message subscription callback"""
        self.ros2_messages_subscribed.labels(topic=topic, message_type=message_type).inc()
    
    def record_ros2_service(self, service: str, status: str):
        """Record ROS2 service call"""
        self.ros2_service_calls.labels(service=service, status=status).inc()
    
    def record_ros2_action(self, action: str, status: str):
        """Record ROS2 action goal"""
        self.ros2_action_goals.labels(action=action, status=status).inc()
    
    # ─── Push Gateway ──────────────────────────────────────────
    
    def push_metrics(self, job: str = None):
        """Push metrics to push gateway"""
        if self.config.pushgateway_url and PROMETHEUS_AVAILABLE:
            push_to_gateway(
                self.config.pushgateway_url,
                job=job or self.component_name,
                registry=self.registry,
            )
    
    def delete_metrics(self, job: str = None):
        """Delete metrics from push gateway"""
        if self.config.pushgateway_url and PROMETHEUS_AVAILABLE:
            delete_from_gateway(
                self.config.pushgateway_url,
                job=job or self.component_name,
            )


class _RequestTimer:
    """Context manager for timing requests"""
    
    def __init__(self, metrics: ROAMetrics, method: str, source: str):
        self.metrics = metrics
        self.method = method
        self.source = source
        self.start_time = None
        self.status = "success"
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        self.metrics.request_in_progress.labels(method=self.method).inc()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.perf_counter() - self.start_time
        self.metrics.request_in_progress.labels(method=self.method).dec()
        
        if exc_type is not None:
            self.status = "error"
        
        self.metrics.record_request(
            method=self.method,
            status=self.status,
            source=self.source,
            duration=duration,
        )
        
        return False  # Don't suppress exceptions


# ─── Metric Decorators ─────────────────────────────────────────

def timed(
    metric: Union[Histogram, Summary] = None,
    method_name: str = None,
    labels: Dict[str, str] = None,
):
    """
    Decorator to time function execution
    
    Usage:
        @timed(metrics.request_duration, method_name="process")
        def process_data():
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            name = method_name or func.__name__
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.perf_counter() - start
                if metric is not None:
                    if labels:
                        metric.labels(**labels).observe(duration)
                    else:
                        metric.observe(duration)
        return wrapper
    return decorator


def counted(
    metric: Counter = None,
    labels: Dict[str, str] = None,
):
    """
    Decorator to count function calls
    
    Usage:
        @counted(metrics.request_total, labels={"method": "process"})
        def process_data():
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if metric is not None:
                if labels:
                    metric.labels(**labels).inc()
                else:
                    metric.inc()
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ─── HTTP Metrics Server ───────────────────────────────────────

class MetricsHandler(BaseHTTPRequestHandler):
    """
    HTTP handler for /metrics endpoint
    
    Supports:
    - GET /metrics - Prometheus metrics in text exposition format
    - GET / - Same as /metrics (convenience)
    - GET /health - Health check endpoint
    - Proper HTTP status codes and headers
    - CORS support for web dashboards
    - Gzip compression for large metric payloads
    """
    
    registry = None
    enable_compression = True
    enable_cors = True
    
    def do_GET(self):
        """Handle GET requests"""
        try:
            if self.path == '/metrics' or self.path == '/':
                self._serve_metrics()
            elif self.path == '/health':
                self._serve_health()
            elif self.path.startswith('/metrics?'):
                # Support query params (e.g., ?name[]=metric_name)
                self._serve_metrics()
            else:
                self._send_error(404, "Not Found", f"Path {self.path} not found")
        except Exception as e:
            self._send_error(500, "Internal Server Error", str(e))
    
    def do_HEAD(self):
        """Handle HEAD requests (for health checks)"""
        if self.path in ('/metrics', '/', '/health'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_OPTIONS(self):
        """Handle OPTIONS requests (for CORS preflight)"""
        self.send_response(200)
        self._add_cors_headers()
        self.send_header('Allow', 'GET, HEAD, OPTIONS')
        self.end_headers()
    
    def _serve_metrics(self):
        """Serve Prometheus metrics"""
        if not PROMETHEUS_AVAILABLE:
            self._send_error(503, "Service Unavailable", "prometheus_client not installed")
            return
        
        try:
            # Generate metrics
            output = generate_latest(self.registry or REGISTRY)
            
            # Check for gzip compression support
            accept_encoding = self.headers.get('Accept-Encoding', '')
            use_gzip = (
                self.enable_compression and
                'gzip' in accept_encoding and
                len(output) > 1024  # Only compress if >1KB
            )
            
            if use_gzip:
                import gzip
                import io
                buf = io.BytesIO()
                with gzip.GzipFile(fileobj=buf, mode='wb') as f:
                    f.write(output)
                output = buf.getvalue()
                content_encoding = 'gzip'
            else:
                content_encoding = None
            
            # Send response
            self.send_response(200)
            self.send_header('Content-Type', CONTENT_TYPE_LATEST)
            self.send_header('Content-Length', str(len(output)))
            if content_encoding:
                self.send_header('Content-Encoding', content_encoding)
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self._add_cors_headers()
            self.end_headers()
            self.wfile.write(output)
            
        except Exception as e:
            self._send_error(500, "Internal Server Error", f"Failed to generate metrics: {e}")
    
    def _serve_health(self):
        """Serve health check endpoint"""
        health_status = {
            'status': 'healthy',
            'prometheus_available': PROMETHEUS_AVAILABLE,
            'registry': 'custom' if self.registry else 'default',
        }
        
        import json
        output = json.dumps(health_status).encode('utf-8')
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(output)))
        self.send_header('Cache-Control', 'no-cache')
        self._add_cors_headers()
        self.end_headers()
        self.wfile.write(output)
    
    def _add_cors_headers(self):
        """Add CORS headers for web dashboard access"""
        if self.enable_cors:
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
            self.send_header('Access-Control-Max-Age', '3600')
    
    def _send_error(self, code: int, message: str, details: str = None):
        """Send error response with JSON body"""
        import json
        error_body = {
            'error': message,
            'code': code,
        }
        if details:
            error_body['details'] = details
        
        output = json.dumps(error_body).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(output)))
        self._add_cors_headers()
        self.end_headers()
        self.wfile.write(output)
    
    def log_message(self, format, *args):
        """Suppress default logging (use structured logging instead)"""
        pass


class MetricsServer:
    """
    HTTP server for Prometheus metrics endpoint
    
    Provides a /metrics endpoint for Prometheus scraping with:
    - Automatic gzip compression for large payloads
    - CORS support for web dashboards
    - Health check endpoint at /health
    - Graceful shutdown
    - Thread-safe operation
    
    Usage:
        # Basic usage
        server = MetricsServer(port=9090)
        server.start()  # Non-blocking
        
        # With custom registry
        registry = CollectorRegistry()
        server = MetricsServer(port=9090, registry=registry)
        server.start()
        
        # Context manager
        with MetricsServer(port=9090) as server:
            # Server runs in background
            time.sleep(60)
        # Server automatically stopped
        
        # Configure features
        server = MetricsServer(
            port=9090,
            host="127.0.0.1",  # Localhost only
            registry=custom_registry,
            enable_compression=True,
            enable_cors=False,  # Disable CORS
        )
    
    Example Prometheus scrape_config:
        scrape_configs:
          - job_name: 'roa-webthread'
            static_configs:
              - targets: ['localhost:9090']
            scrape_interval: 15s
            scrape_timeout: 10s
    """
    
    def __init__(
        self,
        port: int = 9090,
        host: str = "0.0.0.0",
        registry: 'CollectorRegistry' = None,
        enable_compression: bool = True,
        enable_cors: bool = True,
    ):
        """
        Initialize metrics server
        
        Args:
            port: Port to listen on (default: 9090)
            host: Host to bind to (default: 0.0.0.0 for all interfaces)
            registry: Custom Prometheus registry (default: global REGISTRY)
            enable_compression: Enable gzip compression for large responses
            enable_cors: Enable CORS headers for web dashboard access
        """
        self.port = port
        self.host = host
        self.registry = registry
        self.enable_compression = enable_compression
        self.enable_cors = enable_cors
        self._server = None
        self._thread = None
    
    def start(self):
        """
        Start metrics server in background thread
        
        Raises:
            RuntimeError: If server fails to start (port in use, etc.)
        """
        if self._server is not None:
            return
        
        # Configure handler class
        handler = MetricsHandler
        handler.registry = self.registry
        handler.enable_compression = self.enable_compression
        handler.enable_cors = self.enable_cors
        
        try:
            self._server = HTTPServer((self.host, self.port), handler)
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                daemon=True,
                name=f"metrics-server-{self.port}",
            )
            self._thread.start()
        except socket.error as e:
            if e.errno == 48 or e.errno == 98:  # Address already in use
                raise RuntimeError(
                    f"Port {self.port} is already in use. "
                    f"Is another metrics server running? "
                    f"Try a different port or stop the conflicting process."
                ) from e
            else:
                raise RuntimeError(
                    f"Failed to start metrics server on {self.host}:{self.port}: {e}"
                ) from e
    
    def stop(self):
        """Stop metrics server gracefully"""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            if self._thread is not None:
                self._thread.join(timeout=5.0)
            self._server = None
            self._thread = None
    
    def is_running(self) -> bool:
        """Check if server is currently running"""
        return self._server is not None
    
    def get_url(self) -> str:
        """Get the metrics endpoint URL"""
        return f"http://{self.host}:{self.port}/metrics"
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, *args):
        self.stop()
    
    def __repr__(self):
        status = "running" if self.is_running() else "stopped"
        return f"<MetricsServer {self.host}:{self.port} ({status})>"


# ─── Resource Collector ────────────────────────────────────────

class ResourceCollector:
    """
    Collect system resource metrics
    
    Updates CPU, memory, and uptime metrics periodically
    """
    
    def __init__(self, metrics: ROAMetrics, interval: float = 5.0):
        self.metrics = metrics
        self.interval = interval
        self._start_time = time.time()
        self._running = False
        self._thread = None
    
    def start(self):
        """Start collecting resource metrics"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(
            target=self._collect_loop,
            daemon=True,
            name="resource-collector",
        )
        self._thread.start()
    
    def stop(self):
        """Stop collecting resource metrics"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=self.interval + 1)
    
    def _collect_loop(self):
        """Background collection loop"""
        while self._running:
            self._collect()
            time.sleep(self.interval)
    
    def _collect(self):
        """Collect current resource metrics"""
        try:
            import psutil
            
            process = psutil.Process()
            
            # CPU
            self.metrics.cpu_usage.set(process.cpu_percent())
            
            # Memory
            mem_info = process.memory_info()
            self.metrics.memory_usage.labels(type='rss').set(mem_info.rss)
            self.metrics.memory_usage.labels(type='vms').set(mem_info.vms)
            
        except ImportError:
            pass
        except Exception:
            pass
        
        # Uptime (always available)
        self.metrics.uptime.set(time.time() - self._start_time)
