"""
COMC (Communication Center) Observability Integration
======================================================
Instrumentation for inter-component communication, evade coordination,
and state machine transitions

Enhanced with:
- ROS2 topic/service/action tracking with full metrics
- UE5 bridge communication monitoring
- Multi-robot coordination metrics
- Network health and latency monitoring
- Message serialization/deserialization tracking
"""

import os
import sys
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Dict, List, Optional

_current_dir = os.path.dirname(os.path.abspath(__file__))
_shared_path = os.path.abspath(os.path.join(_current_dir, "..", "..", "..", "..", "shared"))
if _shared_path not in sys.path:
    sys.path.insert(0, _shared_path)

try:
    from observability import (
        ROAMetrics,
        ROAObservability,
        ROS2TracingMixin,
        UE5TracingContext,
        trace_ros2_callback,
        trace_ros2_timer,
    )

    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False

    def trace_ros2_callback(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def trace_ros2_timer(*args, **kwargs):
        def decorator(func):
            return func

        return decorator


class COMCMetrics:
    """COMC-specific metrics with comprehensive communication instrumentation"""

    def __init__(self, base_metrics: "ROAMetrics"):
        self.base = base_metrics

        # ==================== ROS2 Topic Metrics ====================
        self.messages_published = base_metrics.register_counter(
            "messages_published_total",
            "Messages published",
            ["topic", "message_type"],
        )

        self.messages_subscribed = base_metrics.register_counter(
            "messages_subscribed_total",
            "Messages received via subscription",
            ["topic", "message_type"],
        )

        self.message_latency = base_metrics.register_histogram(
            "message_latency_seconds",
            "End-to-end message latency",
            ["topic"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25],
        )

        self.message_queue_size = base_metrics.register_gauge(
            "message_queue_size",
            "Current message queue size",
            ["queue_name"],
        )

        self.message_size_bytes = base_metrics.register_histogram(
            "message_size_bytes",
            "Message size in bytes",
            ["topic"],
            buckets=[64, 256, 1024, 4096, 16384, 65536, 262144],
        )

        self.message_drops = base_metrics.register_counter(
            "message_drops_total",
            "Dropped messages",
            ["topic", "reason"],  # queue_full, timeout, deserialization_error
        )

        self.topic_frequency = base_metrics.register_gauge(
            "topic_frequency_hz",
            "Topic publish frequency",
            ["topic"],
        )

        # ==================== ROS2 Service Metrics ====================
        self.service_calls = base_metrics.register_counter(
            "service_calls_total",
            "Service calls made",
            ["service", "status"],
        )

        self.service_call_duration = base_metrics.register_histogram(
            "service_call_duration_seconds",
            "Service call duration",
            ["service"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
        )

        self.service_timeouts = base_metrics.register_counter(
            "service_timeouts_total",
            "Service call timeouts",
            ["service"],
        )

        self.services_available = base_metrics.register_gauge(
            "services_available",
            "Number of available services",
        )

        # ==================== ROS2 Action Metrics ====================
        self.action_goals_sent = base_metrics.register_counter(
            "action_goals_sent_total",
            "Action goals sent",
            ["action", "status"],
        )

        self.action_feedback_received = base_metrics.register_counter(
            "action_feedback_received_total",
            "Action feedback messages received",
            ["action"],
        )

        self.action_result_latency = base_metrics.register_histogram(
            "action_result_latency_seconds",
            "Time from goal send to result",
            ["action"],
            buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120],
        )

        # ==================== UE5 Bridge Metrics ====================
        self.ue5_commands_sent = base_metrics.register_counter(
            "ue5_commands_sent_total",
            "Commands sent to UE5",
            ["command_type", "status"],
        )

        self.ue5_data_received = base_metrics.register_counter(
            "ue5_data_received_total",
            "Data packets received from UE5",
            ["data_type"],
        )

        self.ue5_bridge_latency = base_metrics.register_histogram(
            "ue5_bridge_latency_seconds",
            "UE5 bridge communication latency",
            ["direction"],  # to_ue5, from_ue5
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1],
        )

        self.ue5_connection_status = base_metrics.register_gauge(
            "ue5_connection_status",
            "UE5 bridge connection (0=disconnected, 1=connecting, 2=connected)",
        )

        self.ue5_sync_errors = base_metrics.register_counter(
            "ue5_sync_errors_total",
            "UE5 synchronization errors",
            ["error_type"],
        )

        self.ue5_frame_sync = base_metrics.register_gauge(
            "ue5_frame_sync_delta",
            "Frame synchronization delta (ROS2 vs UE5)",
        )

        # ==================== State Machine Metrics ====================
        self.state_transitions = base_metrics.register_counter(
            "state_transitions_total",
            "State machine transitions",
            ["from_state", "to_state", "trigger"],
        )

        self.current_state = base_metrics.register_gauge(
            "current_state",
            "Current state machine state (encoded as int)",
            ["state_machine"],
        )

        self.state_duration = base_metrics.register_histogram(
            "state_duration_seconds",
            "Time spent in each state",
            ["state"],
            buckets=[0.1, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0],
        )

        # ==================== Evade Coordination Metrics ====================
        self.evade_events = base_metrics.register_counter(
            "evade_events_total",
            "Evade maneuver events",
            ["event_type", "reason"],
        )

        self.evade_duration = base_metrics.register_histogram(
            "evade_duration_seconds",
            "Duration of evade maneuvers",
            buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
        )

        self.proximity_alerts = base_metrics.register_counter(
            "proximity_alerts_total",
            "Proximity alerts triggered",
            ["severity", "zone"],
        )

        self.evade_success_rate = base_metrics.register_gauge(
            "evade_success_rate",
            "Evade maneuver success rate (0-1)",
        )

        # ==================== Multi-Robot Coordination ====================
        self.robots_connected = base_metrics.register_gauge(
            "robots_connected",
            "Number of connected robots",
        )

        self.robot_sync_latency = base_metrics.register_histogram(
            "robot_sync_latency_seconds",
            "Multi-robot synchronization latency",
            ["robot_id"],
            buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5],
        )

        self.coordination_messages = base_metrics.register_counter(
            "coordination_messages_total",
            "Multi-robot coordination messages",
            ["message_type", "direction"],  # sent, received
        )

        # ==================== Task Coordination Metrics ====================
        self.tasks_created = base_metrics.register_counter(
            "tasks_created_total",
            "Tasks created",
            ["task_type", "priority"],
        )

        self.tasks_completed = base_metrics.register_counter(
            "tasks_completed_total",
            "Tasks completed",
            ["task_type", "status"],
        )

        self.task_duration = base_metrics.register_histogram(
            "task_duration_seconds",
            "Task execution duration",
            ["task_type"],
            buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0],
        )

        self.active_tasks = base_metrics.register_gauge(
            "active_tasks",
            "Number of active tasks",
            ["task_type"],
        )

        # ==================== Work Area Management ====================
        self.work_areas_active = base_metrics.register_gauge(
            "work_areas_active",
            "Number of active work areas",
        )

        self.work_area_violations = base_metrics.register_counter(
            "work_area_violations_total",
            "Work area boundary violations",
            ["area", "violation_type"],
        )

        # ==================== Network Health Metrics ====================
        self.network_latency = base_metrics.register_histogram(
            "network_latency_seconds",
            "Network round-trip latency",
            ["destination"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25],
        )

        self.network_errors = base_metrics.register_counter(
            "network_errors_total",
            "Network errors",
            ["error_type", "destination"],
        )

        self.bandwidth_usage = base_metrics.register_gauge(
            "bandwidth_usage_bytes_per_sec",
            "Network bandwidth usage",
            ["direction"],  # inbound, outbound
        )

        # ==================== Health Monitor Metrics ====================
        self.component_health_checks = base_metrics.register_counter(
            "component_health_checks_total",
            "Health checks performed",
            ["component", "result"],
        )

        self.component_heartbeats = base_metrics.register_counter(
            "component_heartbeats_total",
            "Heartbeats received",
            ["component"],
        )

        self.heartbeat_missed = base_metrics.register_counter(
            "heartbeat_missed_total",
            "Missed heartbeats",
            ["component"],
        )

        # ==================== QoS Metrics ====================
        self.qos_violations = base_metrics.register_counter(
            "qos_violations_total",
            "QoS policy violations",
            ["topic", "violation_type"],
        )

        self.qos_profile = base_metrics.register_gauge(
            "qos_profile_active",
            "Active QoS profile (encoded)",
            ["topic"],
        )


class COMCObservability:
    """
    COMC Observability wrapper with comprehensive communication instrumentation

    Provides detailed communication monitoring with:
    - ROS2 topic/service/action tracking
    - UE5 bridge monitoring
    - Multi-robot coordination
    - Network health monitoring
    - State machine tracing

    Usage:
        obs = COMCObservability()
        obs.start()

        # Track ROS2 messages
        obs.record_message_published('/cmd_vel', 'Twist', size_bytes=256)

        # UE5 bridge with tracing
        with obs.trace_ue5_command('spawn_robot'):
            send_to_ue5(command)

        # Service calls with metrics
        with obs.trace_service_call('/get_plan'):
            result = call_service()
    """

    def __init__(self, config: Optional[Dict] = None):
        self._obs: Optional[ROAObservability] = None
        self._metrics: Optional[COMCMetrics] = None
        self._ue5_context: Optional["UE5TracingContext"] = None
        self._state_entry_time: Dict[str, float] = {}
        self._evade_stats = {"success": 0, "total": 0}

        if OBSERVABILITY_AVAILABLE:
            self._obs = ROAObservability(
                component_name="comc",
                service_version=config.get("version", "1.0.0") if config else "1.0.0",
            )
            self._metrics = COMCMetrics(self._obs.metrics)

            # UE5 tracing context
            self._ue5_context = UE5TracingContext(self._obs.tracer)

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
    def metrics(self) -> Optional[COMCMetrics]:
        return self._metrics

    @property
    def tracer(self):
        """Access tracer for custom tracing"""
        return self._obs.tracer if self._obs else None

    # ==================== ROS2 Topic Metrics ====================

    def record_message_published(
        self,
        topic: str,
        message_type: str,
        size_bytes: int = None,
    ):
        """Record message publication"""
        if self._metrics:
            self._metrics.messages_published.labels(
                topic=topic,
                message_type=message_type,
            ).inc()

            if size_bytes:
                self._metrics.message_size_bytes.labels(topic=topic).observe(size_bytes)

            # Record to base metrics
            self._obs.metrics.record_ros2_publish(topic=topic)

    def record_message_received(
        self,
        topic: str,
        message_type: str,
        latency: float = None,
        size_bytes: int = None,
    ):
        """Record message subscription"""
        if self._metrics:
            self._metrics.messages_subscribed.labels(
                topic=topic,
                message_type=message_type,
            ).inc()

            if latency is not None:
                self._metrics.message_latency.labels(topic=topic).observe(latency)

            if size_bytes:
                self._metrics.message_size_bytes.labels(topic=topic).observe(size_bytes)

            # Record to base metrics
            self._obs.metrics.record_ros2_subscribe(topic=topic)

    def record_message_drop(self, topic: str, reason: str):
        """Record dropped message"""
        if self._metrics:
            self._metrics.message_drops.labels(topic=topic, reason=reason).inc()

    def set_topic_frequency(self, topic: str, frequency_hz: float):
        """Set topic publish frequency"""
        if self._metrics:
            self._metrics.topic_frequency.labels(topic=topic).set(frequency_hz)

    def set_queue_size(self, queue_name: str, size: int):
        """Set message queue size"""
        if self._metrics:
            self._metrics.message_queue_size.labels(queue_name=queue_name).set(size)

    @contextmanager
    def trace_publish(self, topic: str, message_type: str):
        """Context manager for tracing message publication"""
        start_time = time.perf_counter()
        try:
            if self._obs and self._obs.tracer:
                with self._obs.tracer.start_span(
                    f"ros2.publish.{topic}",
                    attributes={
                        "ros2.topic": topic,
                        "ros2.message_type": message_type,
                        "component": "comc",
                    },
                ):
                    yield
            else:
                yield
        finally:
            if self._metrics:
                latency = time.perf_counter() - start_time
                self._metrics.message_latency.labels(topic=topic).observe(latency)

    # ==================== ROS2 Service Metrics ====================

    def record_service_call(
        self,
        service: str,
        status: str,
        duration: float = None,
    ):
        """Record service call"""
        if self._metrics:
            self._metrics.service_calls.labels(
                service=service,
                status=status,
            ).inc()

            if duration is not None:
                self._metrics.service_call_duration.labels(service=service).observe(duration)

            if status == "timeout":
                self._metrics.service_timeouts.labels(service=service).inc()

            # Record to base metrics
            self._obs.metrics.record_ros2_service(
                service_name=service,
                success=(status == "success"),
            )

    def set_services_available(self, count: int):
        """Set number of available services"""
        if self._metrics:
            self._metrics.services_available.set(count)

    @contextmanager
    def trace_service_call(self, service: str):
        """Context manager for tracing service calls"""
        start_time = time.perf_counter()
        result_status = {"status": "success"}

        class ServiceResult:
            def set_failed(self, reason: str = "error"):
                result_status["status"] = reason

            def set_timeout(self):
                result_status["status"] = "timeout"

        try:
            if self._obs and self._obs.tracer:
                with self._obs.tracer.start_span(
                    f"ros2.service.{service}",
                    attributes={
                        "ros2.service": service,
                        "component": "comc",
                    },
                ):
                    yield ServiceResult()
            else:
                yield ServiceResult()
        finally:
            duration = time.perf_counter() - start_time
            self.record_service_call(service, result_status["status"], duration)

    # ==================== ROS2 Action Metrics ====================

    def record_action_goal_sent(self, action: str, status: str = "sent"):
        """Record action goal sent"""
        if self._metrics:
            self._metrics.action_goals_sent.labels(action=action, status=status).inc()

    def record_action_feedback(self, action: str):
        """Record action feedback received"""
        if self._metrics:
            self._metrics.action_feedback_received.labels(action=action).inc()

    def record_action_result(self, action: str, latency: float):
        """Record action result with latency"""
        if self._metrics:
            self._metrics.action_result_latency.labels(action=action).observe(latency)

    @contextmanager
    def trace_action_client(self, action: str, goal_id: str = None):
        """Context manager for tracing action client calls"""
        start_time = time.perf_counter()
        self.record_action_goal_sent(action)

        try:
            if self._obs and self._obs.tracer:
                with self._obs.tracer.start_span(
                    f"ros2.action.{action}",
                    attributes={
                        "ros2.action": action,
                        "ros2.goal_id": goal_id or "",
                        "component": "comc",
                    },
                ):
                    yield
            else:
                yield
        finally:
            latency = time.perf_counter() - start_time
            self.record_action_result(action, latency)

    # ==================== UE5 Bridge Metrics ====================

    def record_ue5_command(self, command_type: str, status: str = "success", latency: float = None):
        """Record UE5 command sent"""
        if self._metrics:
            self._metrics.ue5_commands_sent.labels(
                command_type=command_type,
                status=status,
            ).inc()

            if latency is not None:
                self._metrics.ue5_bridge_latency.labels(direction="to_ue5").observe(latency)

    def record_ue5_data(self, data_type: str, latency: float = None):
        """Record UE5 data received"""
        if self._metrics:
            self._metrics.ue5_data_received.labels(data_type=data_type).inc()

            if latency is not None:
                self._metrics.ue5_bridge_latency.labels(direction="from_ue5").observe(latency)

    def set_ue5_connection_status(self, status: str):
        """Set UE5 connection status: 'disconnected', 'connecting', or 'connected'"""
        status_map = {"disconnected": 0, "connecting": 1, "connected": 2}
        if self._metrics and status in status_map:
            self._metrics.ue5_connection_status.set(status_map[status])

    def record_ue5_sync_error(self, error_type: str):
        """Record UE5 synchronization error"""
        if self._metrics:
            self._metrics.ue5_sync_errors.labels(error_type=error_type).inc()

    def set_ue5_frame_sync(self, delta: float):
        """Set frame synchronization delta"""
        if self._metrics:
            self._metrics.ue5_frame_sync.set(delta)

    @contextmanager
    def trace_ue5_command(self, command_type: str):
        """Context manager for tracing UE5 commands"""
        if self._ue5_context:
            with self._ue5_context.trace_command(command_type) as ctx:
                yield ctx
        else:
            start_time = time.perf_counter()
            try:
                yield None
            finally:
                latency = time.perf_counter() - start_time
                self.record_ue5_command(command_type, latency=latency)

    @contextmanager
    def trace_ue5_data_sync(self, data_type: str):
        """Context manager for tracing UE5 data sync"""
        if self._ue5_context:
            with self._ue5_context.trace_data_sync(data_type):
                yield
        else:
            yield

    # ==================== State Machine Metrics ====================

    def record_state_transition(self, from_state: str, to_state: str, trigger: str):
        """Record state transition"""
        if self._metrics:
            self._metrics.state_transitions.labels(
                from_state=from_state,
                to_state=to_state,
                trigger=trigger,
            ).inc()

            # Record duration in previous state
            if from_state in self._state_entry_time:
                duration = time.time() - self._state_entry_time[from_state]
                self._metrics.state_duration.labels(state=from_state).observe(duration)

            # Track entry time for new state
            self._state_entry_time[to_state] = time.time()

        if self._obs:
            self._obs.recorder.record_state_change(from_state, to_state, trigger)

    def set_current_state(self, state_machine: str, state_value: int, state_name: str = None):
        """Set current state as numeric value"""
        if self._metrics:
            self._metrics.current_state.labels(state_machine=state_machine).set(state_value)

            if state_name:
                self._state_entry_time[state_name] = time.time()

    def record_state_duration(self, state: str, duration: float):
        """Record time spent in a state"""
        if self._metrics:
            self._metrics.state_duration.labels(state=state).observe(duration)

    @contextmanager
    def trace_state(self, state_name: str):
        """Context manager for tracing state execution"""
        start_time = time.perf_counter()
        try:
            if self._obs and self._obs.tracer:
                with self._obs.tracer.start_span(
                    f"state.{state_name}",
                    attributes={"state.name": state_name, "component": "comc"},
                ):
                    yield
            else:
                yield
        finally:
            if self._metrics:
                duration = time.perf_counter() - start_time
                self._metrics.state_duration.labels(state=state_name).observe(duration)

    # ==================== Evade Coordination Metrics ====================

    def record_evade_event(
        self,
        event_type: str,
        reason: str,
        duration: float = None,
        success: bool = True,
    ):
        """Record evade maneuver event"""
        if self._metrics:
            self._metrics.evade_events.labels(
                event_type=event_type,
                reason=reason,
            ).inc()

            if duration is not None:
                self._metrics.evade_duration.observe(duration)

            # Update success rate
            self._evade_stats["total"] += 1
            if success:
                self._evade_stats["success"] += 1
            rate = self._evade_stats["success"] / self._evade_stats["total"]
            self._metrics.evade_success_rate.set(rate)

            # Record to base metrics
            self._obs.metrics.record_evade_maneuver(reason=reason)

        if self._obs:
            self._obs.recorder.record_event(
                "evade",
                {
                    "event_type": event_type,
                    "reason": reason,
                    "duration": duration,
                    "success": success,
                },
            )

    def record_proximity_alert(self, severity: str, zone: str):
        """Record proximity alert"""
        if self._metrics:
            self._metrics.proximity_alerts.labels(
                severity=severity,
                zone=zone,
            ).inc()

    @contextmanager
    def trace_evade_maneuver(self, reason: str):
        """Context manager for tracing evade maneuver"""
        start_time = time.perf_counter()
        result = {"success": True}

        class EvadeResult:
            def set_failed(self):
                result["success"] = False

        try:
            if self._obs and self._obs.tracer:
                with self._obs.tracer.start_span(
                    "evade_maneuver",
                    attributes={"evade.reason": reason, "component": "comc"},
                ):
                    yield EvadeResult()
            else:
                yield EvadeResult()
        finally:
            duration = time.perf_counter() - start_time
            self.record_evade_event(
                "completed" if result["success"] else "failed",
                reason,
                duration=duration,
                success=result["success"],
            )

    # ==================== Multi-Robot Coordination ====================

    def set_robots_connected(self, count: int):
        """Set number of connected robots"""
        if self._metrics:
            self._metrics.robots_connected.set(count)

    def record_robot_sync_latency(self, robot_id: str, latency: float):
        """Record multi-robot sync latency"""
        if self._metrics:
            self._metrics.robot_sync_latency.labels(robot_id=robot_id).observe(latency)

    def record_coordination_message(self, message_type: str, direction: str):
        """Record coordination message: direction is 'sent' or 'received'"""
        if self._metrics:
            self._metrics.coordination_messages.labels(
                message_type=message_type,
                direction=direction,
            ).inc()

    # ==================== Task Coordination Metrics ====================

    def record_task_created(self, task_type: str, priority: str = "normal"):
        """Record task creation"""
        if self._metrics:
            self._metrics.tasks_created.labels(
                task_type=task_type,
                priority=priority,
            ).inc()

    def record_task_completed(self, task_type: str, status: str, duration: float = None):
        """Record task completion"""
        if self._metrics:
            self._metrics.tasks_completed.labels(
                task_type=task_type,
                status=status,
            ).inc()

            if duration is not None:
                self._metrics.task_duration.labels(task_type=task_type).observe(duration)

    def set_active_tasks(self, task_type: str, count: int):
        """Set active task count"""
        if self._metrics:
            self._metrics.active_tasks.labels(task_type=task_type).set(count)

    @contextmanager
    def trace_task(self, task_type: str, task_id: str = None):
        """Context manager for tracing task execution"""
        start_time = time.perf_counter()
        result_status = {"status": "success"}

        class TaskResult:
            def set_failed(self):
                result_status["status"] = "failed"

            def set_canceled(self):
                result_status["status"] = "canceled"

        try:
            if self._obs and self._obs.tracer:
                with self._obs.tracer.start_span(
                    f"task.{task_type}",
                    attributes={
                        "task.type": task_type,
                        "task.id": task_id or "",
                        "component": "comc",
                    },
                ):
                    yield TaskResult()
            else:
                yield TaskResult()
        finally:
            duration = time.perf_counter() - start_time
            self.record_task_completed(task_type, result_status["status"], duration)

    # ==================== Work Area Metrics ====================

    def set_active_work_areas(self, count: int):
        """Set number of active work areas"""
        if self._metrics:
            self._metrics.work_areas_active.set(count)

    def record_work_area_violation(self, area: str, violation_type: str):
        """Record work area violation"""
        if self._metrics:
            self._metrics.work_area_violations.labels(
                area=area,
                violation_type=violation_type,
            ).inc()

    # ==================== Network Health Metrics ====================

    def record_network_latency(self, destination: str, latency: float):
        """Record network latency"""
        if self._metrics:
            self._metrics.network_latency.labels(destination=destination).observe(latency)

    def record_network_error(self, error_type: str, destination: str):
        """Record network error"""
        if self._metrics:
            self._metrics.network_errors.labels(
                error_type=error_type,
                destination=destination,
            ).inc()

    def set_bandwidth_usage(self, inbound: float = None, outbound: float = None):
        """Set bandwidth usage in bytes/sec"""
        if self._metrics:
            if inbound is not None:
                self._metrics.bandwidth_usage.labels(direction="inbound").set(inbound)
            if outbound is not None:
                self._metrics.bandwidth_usage.labels(direction="outbound").set(outbound)

    # ==================== Health Monitor Metrics ====================

    def record_health_check(self, component: str, result: str):
        """Record component health check"""
        if self._metrics:
            self._metrics.component_health_checks.labels(
                component=component,
                result=result,
            ).inc()

    def record_heartbeat(self, component: str):
        """Record heartbeat received"""
        if self._metrics:
            self._metrics.component_heartbeats.labels(component=component).inc()

    def record_heartbeat_missed(self, component: str):
        """Record missed heartbeat"""
        if self._metrics:
            self._metrics.heartbeat_missed.labels(component=component).inc()

    # ==================== QoS Metrics ====================

    def record_qos_violation(self, topic: str, violation_type: str):
        """Record QoS violation"""
        if self._metrics:
            self._metrics.qos_violations.labels(
                topic=topic,
                violation_type=violation_type,
            ).inc()

        if self._obs:
            self._obs.logger.warning(f"QoS violation on {topic}: {violation_type}")

    # ==================== Decorator Helpers ====================

    def traced_callback(self, topic: str):
        """
        Decorator for tracing ROS2 topic callbacks

        Usage:
            @obs.traced_callback('/cmd_vel')
            def cmd_vel_callback(msg):
                ...
        """

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                if self._obs and self._obs.tracer:
                    with self._obs.tracer.start_span(
                        f"callback.{topic}",
                        attributes={"ros2.topic": topic, "component": "comc"},
                    ):
                        return func(*args, **kwargs)
                return func(*args, **kwargs)

            return wrapper

        return decorator
