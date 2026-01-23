"""
DIMC (Dimensions Collector) Observability Integration
======================================================
Instrumentation for sensor data collection and dimension tracking

Enhanced with robotics-specific metrics for:
- LiDAR, camera, and depth sensor tracking
- Obstacle detection and safety zone monitoring
- Point cloud processing metrics
- Sensor fusion and calibration tracking
"""

import os
import sys
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple

_current_dir = os.path.dirname(os.path.abspath(__file__))
_shared_path = os.path.abspath(os.path.join(_current_dir, "..", "..", "..", "..", "shared"))
if _shared_path not in sys.path:
    sys.path.insert(0, _shared_path)

try:
    from observability import (
        ControlLoopTracer,
        ROAMetrics,
        ROAObservability,
        ROS2TracingMixin,
        trace_ros2_callback,
        trace_ros2_timer,
    )

    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False

    # Provide dummy decorators when observability not available
    def trace_ros2_callback(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def trace_ros2_timer(*args, **kwargs):
        def decorator(func):
            return func

        return decorator


class DIMCMetrics:
    """DIMC-specific metrics with enhanced robotics instrumentation"""

    def __init__(self, base_metrics: "ROAMetrics"):
        self.base = base_metrics

        # ==================== Sensor Data Metrics ====================
        self.sensor_readings = base_metrics.register_counter(
            "sensor_readings_total",
            "Total sensor readings collected",
            ["sensor_type", "sensor_id"],
        )

        self.sensor_reading_rate = base_metrics.register_gauge(
            "sensor_reading_rate_hz",
            "Sensor reading rate in Hz",
            ["sensor_type"],
        )

        self.sensor_latency = base_metrics.register_histogram(
            "sensor_latency_seconds",
            "Sensor data latency",
            ["sensor_type"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1],
        )

        self.sensor_errors = base_metrics.register_counter(
            "sensor_errors_total",
            "Sensor error count",
            ["sensor_type", "sensor_id", "error_type"],
        )

        self.sensor_health = base_metrics.register_gauge(
            "sensor_health_status",
            "Sensor health (0=error, 1=degraded, 2=healthy)",
            ["sensor_type", "sensor_id"],
        )

        # ==================== Point Cloud Metrics ====================
        self.pointcloud_points = base_metrics.register_gauge(
            "pointcloud_points",
            "Number of points in point cloud",
            ["source"],
        )

        self.pointcloud_processing_time = base_metrics.register_histogram(
            "pointcloud_processing_seconds",
            "Point cloud processing duration",
            ["operation"],  # filtering, segmentation, clustering, etc.
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25],
        )

        self.pointcloud_density = base_metrics.register_gauge(
            "pointcloud_density_points_per_m3",
            "Point cloud density",
            ["region"],
        )

        # ==================== Dimension Tracking Metrics ====================
        self.dimensions_tracked = base_metrics.register_gauge(
            "dimensions_tracked",
            "Number of dimensions being tracked",
        )

        self.dimension_updates = base_metrics.register_counter(
            "dimension_updates_total",
            "Dimension updates",
            ["dimension_type"],
        )

        self.dimension_accuracy = base_metrics.register_histogram(
            "dimension_accuracy",
            "Dimension measurement accuracy",
            ["dimension_type"],
            buckets=[0.5, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0],
        )

        # ==================== Obstacle Detection Metrics ====================
        self.obstacles_detected = base_metrics.register_gauge(
            "obstacles_detected",
            "Current number of detected obstacles",
        )

        self.obstacle_events = base_metrics.register_counter(
            "obstacle_events_total",
            "Obstacle detection events",
            ["event_type"],  # detected, updated, cleared
        )

        self.closest_obstacle_distance = base_metrics.register_gauge(
            "closest_obstacle_distance_meters",
            "Distance to closest obstacle",
        )

        self.obstacle_by_type = base_metrics.register_gauge(
            "obstacles_by_type",
            "Obstacles grouped by type",
            ["obstacle_type"],  # static, dynamic, unknown
        )

        self.obstacle_velocity = base_metrics.register_gauge(
            "obstacle_velocity_m_s",
            "Detected obstacle velocity",
            ["obstacle_id"],
        )

        # ==================== Safety Zone Metrics ====================
        self.safety_zone_status = base_metrics.register_gauge(
            "safety_zone_status",
            "Safety zone status (0=clear, 1=warning, 2=critical)",
            ["zone_id"],
        )

        self.safety_zone_intrusions = base_metrics.register_counter(
            "safety_zone_intrusions_total",
            "Safety zone intrusion events",
            ["zone_id", "severity"],
        )

        self.time_to_collision = base_metrics.register_gauge(
            "time_to_collision_seconds",
            "Estimated time to collision with nearest obstacle",
        )

        # ==================== Sensor Fusion Metrics ====================
        self.fusion_inputs = base_metrics.register_gauge(
            "sensor_fusion_inputs",
            "Number of active sensor inputs for fusion",
        )

        self.fusion_latency = base_metrics.register_histogram(
            "sensor_fusion_latency_seconds",
            "Sensor fusion processing latency",
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05],
        )

        self.fusion_confidence = base_metrics.register_gauge(
            "sensor_fusion_confidence",
            "Sensor fusion confidence score (0-1)",
        )

        # ==================== Calibration Metrics ====================
        self.calibration_status = base_metrics.register_gauge(
            "sensor_calibration_status",
            "Calibration status (0=uncalibrated, 1=calibrating, 2=calibrated)",
            ["sensor_id"],
        )

        self.calibration_drift = base_metrics.register_gauge(
            "sensor_calibration_drift",
            "Calibration drift from reference",
            ["sensor_id", "axis"],
        )

        self.calibration_events = base_metrics.register_counter(
            "calibration_events_total",
            "Calibration events",
            ["sensor_id", "event_type"],  # started, completed, failed
        )

        # ==================== Measurement Metrics ====================
        self.measurements_taken = base_metrics.register_counter(
            "measurements_taken_total",
            "Total measurements taken",
            ["measurement_type"],
        )

        self.measurement_accuracy = base_metrics.register_histogram(
            "measurement_accuracy",
            "Measurement accuracy (0-1)",
            ["measurement_type"],
            buckets=[0.5, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0],
        )

        # ==================== Export Metrics ====================
        self.data_exports = base_metrics.register_counter(
            "data_exports_total",
            "Data exports to ROS2/other systems",
            ["destination", "data_type"],
        )

        self.export_latency = base_metrics.register_histogram(
            "data_export_latency_seconds",
            "Data export latency",
            ["destination"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1],
        )


class DIMCObservability:
    """
    DIMC Observability wrapper with enhanced robotics instrumentation

    Provides comprehensive sensor and obstacle monitoring with:
    - Automatic sensor health tracking
    - Point cloud processing metrics
    - Safety zone monitoring
    - Sensor fusion quality metrics
    - Built-in tracing for ROS2 callbacks

    Usage:
        obs = DIMCObservability()
        obs.start()

        # Record sensor readings with tracing
        with obs.trace_sensor_read('lidar', 'front_lidar'):
            data = read_lidar_data()
        obs.record_sensor_reading('lidar', 'front_lidar', latency=0.005)

        # Track obstacles with safety zones
        obs.record_obstacle_detected(distance=2.5, obstacle_type='dynamic')
        obs.update_safety_zone('zone_1', status='warning')

        # Point cloud processing
        with obs.trace_pointcloud_processing('filtering'):
            filtered = filter_pointcloud(raw)
        obs.set_pointcloud_stats('front_lidar', num_points=50000)
    """

    def __init__(self, config: Optional[Dict] = None):
        self._obs: Optional[ROAObservability] = None
        self._metrics: Optional[DIMCMetrics] = None
        self._control_loop_tracer: Optional["ControlLoopTracer"] = None

        if OBSERVABILITY_AVAILABLE:
            self._obs = ROAObservability(
                component_name="dimc",
                service_version=config.get("version", "1.0.0") if config else "1.0.0",
            )
            self._metrics = DIMCMetrics(self._obs.metrics)

            # Control loop tracer for high-frequency sensor loops (1% sample rate)
            self._control_loop_tracer = ControlLoopTracer(
                self._obs.tracer,
                loop_name="sensor_loop",
                sample_rate=0.01,
            )

    def start(self):
        if self._obs:
            self._obs.start()
            self._obs.set_ready()

    def stop(self):
        if self._obs:
            self._obs.stop()

    @property
    def logger(self):
        return self._obs.logger if self._obs else None

    @property
    def metrics(self) -> Optional[DIMCMetrics]:
        return self._metrics

    @property
    def tracer(self):
        """Access tracer for custom tracing"""
        return self._obs.tracer if self._obs else None

    # ==================== Sensor Reading Methods ====================

    def record_sensor_reading(
        self,
        sensor_type: str,
        sensor_id: str,
        latency: float = None,
        value: float = None,
    ):
        """Record a sensor reading with optional latency tracking"""
        if self._metrics:
            self._metrics.sensor_readings.labels(
                sensor_type=sensor_type,
                sensor_id=sensor_id,
            ).inc()

            if latency is not None:
                self._metrics.sensor_latency.labels(
                    sensor_type=sensor_type,
                ).observe(latency)

            # Also record to base robotics metrics
            self._obs.metrics.record_sensor_reading(
                sensor_type=sensor_type,
                latency=latency,
                value=value,
            )

    def set_sensor_rate(self, sensor_type: str, rate_hz: float):
        """Set current sensor reading rate"""
        if self._metrics:
            self._metrics.sensor_reading_rate.labels(
                sensor_type=sensor_type,
            ).set(rate_hz)

    def record_sensor_error(self, sensor_type: str, sensor_id: str, error_type: str):
        """Record sensor error"""
        if self._metrics:
            self._metrics.sensor_errors.labels(
                sensor_type=sensor_type,
                sensor_id=sensor_id,
                error_type=error_type,
            ).inc()

    def set_sensor_health(self, sensor_type: str, sensor_id: str, health: str):
        """Set sensor health status: 'healthy', 'degraded', or 'error'"""
        health_map = {"error": 0, "degraded": 1, "healthy": 2}
        if self._metrics and health in health_map:
            self._metrics.sensor_health.labels(
                sensor_type=sensor_type,
                sensor_id=sensor_id,
            ).set(health_map[health])

    @contextmanager
    def trace_sensor_read(self, sensor_type: str, sensor_id: str):
        """Context manager for tracing sensor read operations"""
        if self._obs and self._obs.tracer:
            with self._obs.tracer.start_span(
                f"sensor_read.{sensor_type}.{sensor_id}",
                attributes={
                    "sensor.type": sensor_type,
                    "sensor.id": sensor_id,
                    "component": "dimc",
                },
            ):
                yield
        else:
            yield

    # ==================== Point Cloud Methods ====================

    def set_pointcloud_stats(self, source: str, num_points: int, density: float = None):
        """Record point cloud statistics"""
        if self._metrics:
            self._metrics.pointcloud_points.labels(source=source).set(num_points)
            if density is not None:
                self._metrics.pointcloud_density.labels(region=source).set(density)

    @contextmanager
    def trace_pointcloud_processing(self, operation: str):
        """Context manager for tracing and timing point cloud processing"""
        start_time = time.perf_counter()
        try:
            if self._obs and self._obs.tracer:
                with self._obs.tracer.start_span(
                    f"pointcloud.{operation}",
                    attributes={
                        "pointcloud.operation": operation,
                        "component": "dimc",
                    },
                ):
                    yield
            else:
                yield
        finally:
            if self._metrics:
                duration = time.perf_counter() - start_time
                self._metrics.pointcloud_processing_time.labels(operation=operation).observe(
                    duration
                )

    # ==================== Obstacle Detection Methods ====================

    def record_obstacle_detected(
        self,
        distance: float,
        obstacle_type: str = "unknown",
        obstacle_id: str = None,
        velocity: float = None,
    ):
        """Record obstacle detection with type and optional velocity"""
        if self._metrics:
            self._metrics.obstacle_events.labels(event_type="detected").inc()
            self._metrics.closest_obstacle_distance.set(distance)

            # Track by type
            current = (
                self._metrics.obstacle_by_type.labels(obstacle_type=obstacle_type)._value.get() or 0
            )
            self._metrics.obstacle_by_type.labels(obstacle_type=obstacle_type).set(current + 1)

            if obstacle_id and velocity is not None:
                self._metrics.obstacle_velocity.labels(obstacle_id=obstacle_id).set(velocity)

            # Record to base metrics
            self._obs.metrics.record_obstacle_detected(obstacle_type=obstacle_type)
            self._obs.metrics.set_obstacle_distance(obstacle_id or "nearest", distance)

    def clear_obstacle(self, obstacle_type: str = "unknown"):
        """Record obstacle cleared"""
        if self._metrics:
            self._metrics.obstacle_events.labels(event_type="cleared").inc()
            current = (
                self._metrics.obstacle_by_type.labels(obstacle_type=obstacle_type)._value.get() or 0
            )
            self._metrics.obstacle_by_type.labels(obstacle_type=obstacle_type).set(
                max(0, current - 1)
            )

    def set_obstacle_count(self, count: int):
        """Set current obstacle count"""
        if self._metrics:
            self._metrics.obstacles_detected.set(count)

    def set_time_to_collision(self, ttc: float):
        """Set estimated time to collision in seconds"""
        if self._metrics:
            self._metrics.time_to_collision.set(ttc)

    # ==================== Safety Zone Methods ====================

    def update_safety_zone(self, zone_id: str, status: str, intrusion_severity: str = None):
        """
        Update safety zone status

        Args:
            zone_id: Zone identifier
            status: 'clear', 'warning', or 'critical'
            intrusion_severity: If set, also record intrusion event
        """
        status_map = {"clear": 0, "warning": 1, "critical": 2}
        if self._metrics and status in status_map:
            self._metrics.safety_zone_status.labels(zone_id=zone_id).set(status_map[status])

            if intrusion_severity:
                self._metrics.safety_zone_intrusions.labels(
                    zone_id=zone_id,
                    severity=intrusion_severity,
                ).inc()

                # Also record to base safety metrics
                self._obs.metrics.record_safety_violation(
                    zone_id=zone_id,
                    violation_type=f"intrusion_{intrusion_severity}",
                )

    # ==================== Sensor Fusion Methods ====================

    def update_fusion_status(self, num_inputs: int, confidence: float, latency: float = None):
        """Update sensor fusion metrics"""
        if self._metrics:
            self._metrics.fusion_inputs.set(num_inputs)
            self._metrics.fusion_confidence.set(confidence)
            if latency is not None:
                self._metrics.fusion_latency.observe(latency)

    @contextmanager
    def trace_fusion_cycle(self):
        """Context manager for tracing sensor fusion cycle"""
        start_time = time.perf_counter()
        try:
            if self._obs and self._obs.tracer:
                with self._obs.tracer.start_span(
                    "sensor_fusion.cycle", attributes={"component": "dimc"}
                ):
                    yield
            else:
                yield
        finally:
            if self._metrics:
                duration = time.perf_counter() - start_time
                self._metrics.fusion_latency.observe(duration)

    # ==================== Calibration Methods ====================

    def set_calibration_status(self, sensor_id: str, status: str):
        """Set calibration status: 'uncalibrated', 'calibrating', or 'calibrated'"""
        status_map = {"uncalibrated": 0, "calibrating": 1, "calibrated": 2}
        if self._metrics and status in status_map:
            self._metrics.calibration_status.labels(sensor_id=sensor_id).set(status_map[status])

    def set_calibration_drift(self, sensor_id: str, axis: str, drift: float):
        """Record calibration drift for a sensor axis"""
        if self._metrics:
            self._metrics.calibration_drift.labels(
                sensor_id=sensor_id,
                axis=axis,
            ).set(drift)

    def record_calibration_event(self, sensor_id: str, event_type: str):
        """Record calibration event: 'started', 'completed', or 'failed'"""
        if self._metrics:
            self._metrics.calibration_events.labels(
                sensor_id=sensor_id,
                event_type=event_type,
            ).inc()

    # ==================== Measurement Methods ====================

    def record_measurement(self, measurement_type: str, accuracy: float = None):
        """Record a measurement"""
        if self._metrics:
            self._metrics.measurements_taken.labels(
                measurement_type=measurement_type,
            ).inc()

            if accuracy is not None:
                self._metrics.measurement_accuracy.labels(
                    measurement_type=measurement_type,
                ).observe(accuracy)

    def update_dimensions(self, dimension_type: str, count: int = None, accuracy: float = None):
        """Record dimension update"""
        if self._metrics:
            self._metrics.dimension_updates.labels(dimension_type=dimension_type).inc()

            if count is not None:
                self._metrics.dimensions_tracked.set(count)

            if accuracy is not None:
                self._metrics.dimension_accuracy.labels(dimension_type=dimension_type).observe(
                    accuracy
                )

    # ==================== Export Methods ====================

    def record_data_export(self, destination: str, data_type: str, latency: float = None):
        """Record data export to external system"""
        if self._metrics:
            self._metrics.data_exports.labels(
                destination=destination,
                data_type=data_type,
            ).inc()

            if latency is not None:
                self._metrics.export_latency.labels(destination=destination).observe(latency)

    @contextmanager
    def trace_export(self, destination: str, data_type: str):
        """Context manager for tracing data export operations"""
        start_time = time.perf_counter()
        try:
            if self._obs and self._obs.tracer:
                with self._obs.tracer.start_span(
                    f"export.{destination}",
                    attributes={
                        "export.destination": destination,
                        "export.data_type": data_type,
                        "component": "dimc",
                    },
                ):
                    yield
            else:
                yield
        finally:
            if self._metrics:
                latency = time.perf_counter() - start_time
                self._metrics.export_latency.labels(destination=destination).observe(latency)

    # ==================== High-Frequency Loop Support ====================

    @contextmanager
    def sensor_loop_iteration(self):
        """
        Context manager for high-frequency sensor loop iterations.
        Uses sampling to avoid overwhelming trace storage.
        """
        if self._control_loop_tracer:
            with self._control_loop_tracer.trace_iteration():
                yield
        else:
            yield

    # ==================== Decorator Helpers ====================

    def traced_sensor_callback(self, sensor_type: str):
        """
        Decorator for tracing sensor callback functions

        Usage:
            @obs.traced_sensor_callback('lidar')
            def process_lidar_scan(msg):
                ...
        """

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                with self.trace_sensor_read(sensor_type, func.__name__):
                    return func(*args, **kwargs)

            return wrapper

        return decorator
