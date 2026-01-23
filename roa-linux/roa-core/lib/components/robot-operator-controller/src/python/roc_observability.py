"""
ROC (Robot Operator Controller) Observability Integration
==========================================================
Instrumentation for robot control, path planning, and safety systems

Enhanced with robotics-specific metrics for:
- Joint state monitoring (position, velocity, effort, torque)
- Control loop performance (frequency, jitter, latency)
- Path execution tracking with deviation monitoring
- PID/controller tuning metrics
- Emergency stop and recovery tracking
- Action server metrics
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

    def trace_ros2_callback(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def trace_ros2_timer(*args, **kwargs):
        def decorator(func):
            return func

        return decorator


class ROCMetrics:
    """ROC-specific metrics with comprehensive robot control instrumentation"""

    def __init__(self, base_metrics: "ROAMetrics"):
        self.base = base_metrics

        # ==================== Command Queue Metrics ====================
        self.commands_queued = base_metrics.register_counter(
            "commands_queued_total",
            "Total commands added to queue",
            ["command_type", "priority"],
        )

        self.commands_executed = base_metrics.register_counter(
            "commands_executed_total",
            "Total commands executed",
            ["command_type", "status"],
        )

        self.command_queue_size = base_metrics.register_gauge(
            "command_queue_size",
            "Current command queue size",
        )

        self.command_execution_time = base_metrics.register_histogram(
            "command_execution_time_seconds",
            "Command execution time",
            ["command_type"],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0],
        )

        self.command_latency = base_metrics.register_histogram(
            "command_latency_seconds",
            "Time from command received to execution start",
            ["command_type"],
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5],
        )

        # ==================== Control Mode Metrics ====================
        self.control_mode = base_metrics.register_gauge(
            "control_mode",
            "Current control mode (0=manual, 1=auto, 2=semi-auto, 3=estop)",
        )

        self.control_mode_changes = base_metrics.register_counter(
            "control_mode_changes_total",
            "Control mode changes",
            ["from_mode", "to_mode"],
        )

        self.control_mode_duration = base_metrics.register_histogram(
            "control_mode_duration_seconds",
            "Duration spent in control mode",
            ["mode"],
            buckets=[1, 5, 30, 60, 300, 600, 1800, 3600],
        )

        # ==================== Joint State Metrics ====================
        self.joint_position = base_metrics.register_gauge(
            "joint_position_rad",
            "Joint position in radians",
            ["joint_name"],
        )

        self.joint_velocity = base_metrics.register_gauge(
            "joint_velocity_rad_s",
            "Joint velocity in rad/s",
            ["joint_name"],
        )

        self.joint_effort = base_metrics.register_gauge(
            "joint_effort",
            "Joint effort/torque",
            ["joint_name"],
        )

        self.joint_temperature = base_metrics.register_gauge(
            "joint_temperature_celsius",
            "Joint motor temperature",
            ["joint_name"],
        )

        self.joint_limits_reached = base_metrics.register_counter(
            "joint_limits_reached_total",
            "Joint limit events",
            [
                "joint_name",
                "limit_type",
            ],  # position_min, position_max, velocity, effort
        )

        # ==================== Path Planning Metrics ====================
        self.paths_planned = base_metrics.register_counter(
            "paths_planned_total",
            "Total paths planned",
            ["algorithm", "status"],
        )

        self.path_planning_duration = base_metrics.register_histogram(
            "path_planning_duration_seconds",
            "Path planning computation time",
            ["algorithm"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
        )

        self.path_length_meters = base_metrics.register_histogram(
            "path_length_meters",
            "Planned path length",
            buckets=[1, 5, 10, 25, 50, 100, 250, 500],
        )

        self.path_waypoints = base_metrics.register_histogram(
            "path_waypoints",
            "Number of waypoints in path",
            buckets=[2, 5, 10, 25, 50, 100],
        )

        self.path_replanning = base_metrics.register_counter(
            "path_replanning_total",
            "Path replanning events",
            ["reason"],  # obstacle, goal_change, timeout
        )

        # ==================== Path Execution Metrics ====================
        self.path_progress = base_metrics.register_gauge(
            "path_progress_percent",
            "Current path execution progress (0-100)",
        )

        self.path_deviation = base_metrics.register_gauge(
            "path_deviation_meters",
            "Current deviation from planned path",
        )

        self.waypoint_reached = base_metrics.register_counter(
            "waypoints_reached_total",
            "Waypoints successfully reached",
        )

        self.path_execution_time = base_metrics.register_histogram(
            "path_execution_time_seconds",
            "Total path execution time",
            buckets=[1, 5, 10, 30, 60, 120, 300, 600],
        )

        # ==================== Motion Control Metrics ====================
        self.velocity_current = base_metrics.register_gauge(
            "velocity_current_mps",
            "Current velocity in m/s",
            ["axis"],  # x, y, z, angular
        )

        self.velocity_commanded = base_metrics.register_gauge(
            "velocity_commanded_mps",
            "Commanded velocity in m/s",
            ["axis"],
        )

        self.position_current = base_metrics.register_gauge(
            "position_current_meters",
            "Current position",
            ["axis"],
        )

        self.position_target = base_metrics.register_gauge(
            "position_target_meters",
            "Target position",
            ["axis"],
        )

        self.position_error = base_metrics.register_gauge(
            "position_error_meters",
            "Position error (target - current)",
            ["axis"],
        )

        self.motion_commands = base_metrics.register_counter(
            "motion_commands_total",
            "Motion commands sent",
            ["command_type"],
        )

        self.acceleration = base_metrics.register_gauge(
            "acceleration_mps2",
            "Current acceleration",
            ["axis"],
        )

        # ==================== Controller Metrics ====================
        self.controller_output = base_metrics.register_gauge(
            "controller_output",
            "Controller output signal",
            ["controller_name", "output_type"],
        )

        self.controller_error = base_metrics.register_gauge(
            "controller_error",
            "Controller error signal",
            ["controller_name"],
        )

        self.controller_gains = base_metrics.register_gauge(
            "controller_gains",
            "Controller gain values",
            ["controller_name", "gain_type"],  # p, i, d, ff
        )

        # ==================== Safety Metrics ====================
        self.safety_stops = base_metrics.register_counter(
            "safety_stops_total",
            "Safety stop events",
            ["reason"],
        )

        self.safety_violations = base_metrics.register_counter(
            "safety_violations_total",
            "Safety violations detected",
            ["violation_type", "severity"],
        )

        self.safety_zone_status = base_metrics.register_gauge(
            "safety_zone_status",
            "Safety zone status (0=clear, 1=warning, 2=danger)",
            ["zone"],
        )

        self.estop_status = base_metrics.register_gauge(
            "estop_status",
            "Emergency stop status (0=released, 1=engaged)",
        )

        self.recovery_attempts = base_metrics.register_counter(
            "recovery_attempts_total",
            "Recovery attempts from error/stop state",
            ["recovery_type", "status"],
        )

        # ==================== Action Server Metrics ====================
        self.action_goals_received = base_metrics.register_counter(
            "action_goals_received_total",
            "Action goals received",
            ["action_name"],
        )

        self.action_goals_succeeded = base_metrics.register_counter(
            "action_goals_succeeded_total",
            "Action goals completed successfully",
            ["action_name"],
        )

        self.action_goals_aborted = base_metrics.register_counter(
            "action_goals_aborted_total",
            "Action goals aborted",
            ["action_name", "reason"],
        )

        self.action_goals_canceled = base_metrics.register_counter(
            "action_goals_canceled_total",
            "Action goals canceled",
            ["action_name"],
        )

        self.action_execution_time = base_metrics.register_histogram(
            "action_execution_time_seconds",
            "Action execution duration",
            ["action_name"],
            buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120],
        )

        # ==================== Performance Metrics ====================
        self.control_loop_frequency = base_metrics.register_gauge(
            "control_loop_frequency_hz",
            "Control loop execution frequency",
        )

        self.control_loop_jitter = base_metrics.register_histogram(
            "control_loop_jitter_ms",
            "Control loop timing jitter",
            buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
        )

        self.control_loop_overruns = base_metrics.register_counter(
            "control_loop_overruns_total",
            "Control loop deadline overruns",
        )

        self.cpu_usage = base_metrics.register_gauge(
            "roc_cpu_usage_percent",
            "ROC CPU usage percentage",
        )


class ROCObservability:
    """
    ROC Observability wrapper with comprehensive robot control instrumentation

    Provides detailed robot control monitoring with:
    - Joint state tracking (position, velocity, effort, temperature)
    - Control loop performance metrics
    - Path planning and execution tracking
    - Safety and emergency stop monitoring
    - Action server metrics
    - Built-in tracing for control operations

    Usage:
        obs = ROCObservability()
        obs.start()

        # Track joint states
        obs.set_joint_state('joint_1', position=1.57, velocity=0.1, effort=5.0)

        # Control loop with tracing
        with obs.trace_control_loop():
            compute_control()

        # Path planning with metrics
        with obs.trace_path_planning('rrt_star') as planner:
            path = plan_path()
            planner.set_result(path_length=25.5, waypoints=15)

        # Action execution
        with obs.trace_action('move_to_pose', goal_id='123'):
            execute_action()
    """

    def __init__(self, config: Optional[Dict] = None):
        self._obs: Optional[ROAObservability] = None
        self._metrics: Optional[ROCMetrics] = None
        self._control_loop_tracer: Optional["ControlLoopTracer"] = None
        self._control_mode_start: float = 0
        self._current_mode: str = "manual"

        if OBSERVABILITY_AVAILABLE:
            self._obs = ROAObservability(
                component_name="roc",
                service_version=config.get("version", "1.0.0") if config else "1.0.0",
            )
            self._metrics = ROCMetrics(self._obs.metrics)

            # Control loop tracer for high-frequency control (1% sample rate)
            self._control_loop_tracer = ControlLoopTracer(
                self._obs.tracer,
                loop_name="control_loop",
                sample_rate=0.01,
            )
            self._control_mode_start = time.time()

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
    def metrics(self) -> Optional[ROCMetrics]:
        return self._metrics

    @property
    def tracer(self):
        """Access tracer for custom tracing"""
        return self._obs.tracer if self._obs else None

    # ==================== Command Metrics ====================

    def record_command_queued(self, command_type: str, priority: str = "normal"):
        """Record command added to queue"""
        if self._metrics:
            self._metrics.commands_queued.labels(
                command_type=command_type,
                priority=priority,
            ).inc()

    def record_command_executed(
        self,
        command_type: str,
        status: str,
        duration: float = None,
        latency: float = None,
    ):
        """Record command execution"""
        if self._metrics:
            self._metrics.commands_executed.labels(
                command_type=command_type,
                status=status,
            ).inc()

            if duration is not None:
                self._metrics.command_execution_time.labels(
                    command_type=command_type,
                ).observe(duration)

            if latency is not None:
                self._metrics.command_latency.labels(
                    command_type=command_type,
                ).observe(latency)

    def set_queue_size(self, size: int):
        """Set current queue size"""
        if self._metrics:
            self._metrics.command_queue_size.set(size)

    @contextmanager
    def trace_command(self, command_type: str, command_id: str = None):
        """Context manager for tracing command execution"""
        start_time = time.perf_counter()
        try:
            if self._obs and self._obs.tracer:
                with self._obs.tracer.start_span(
                    f"command.{command_type}",
                    attributes={
                        "command.type": command_type,
                        "command.id": command_id or "",
                        "component": "roc",
                    },
                ):
                    yield
            else:
                yield
        finally:
            if self._metrics:
                duration = time.perf_counter() - start_time
                self._metrics.command_execution_time.labels(command_type=command_type).observe(
                    duration
                )

    # ==================== Control Mode Metrics ====================

    def set_control_mode(self, mode: str, from_mode: str = None):
        """
        Set current control mode

        Args:
            mode: 'manual', 'auto', 'semi_auto', or 'estop'
            from_mode: Previous mode (auto-detected if not provided)
        """
        mode_map = {"manual": 0, "auto": 1, "semi_auto": 2, "estop": 3}

        if self._metrics and mode in mode_map:
            # Record duration in previous mode
            if self._control_mode_start > 0:
                duration = time.time() - self._control_mode_start
                self._metrics.control_mode_duration.labels(mode=self._current_mode).observe(
                    duration
                )

            # Record mode change
            actual_from = from_mode or self._current_mode
            if actual_from != mode:
                self._metrics.control_mode_changes.labels(
                    from_mode=actual_from,
                    to_mode=mode,
                ).inc()

                # Also record to base metrics
                self._obs.metrics.set_control_mode(mode)

            self._metrics.control_mode.set(mode_map[mode])
            self._current_mode = mode
            self._control_mode_start = time.time()

    # ==================== Joint State Metrics ====================

    def set_joint_state(
        self,
        joint_name: str,
        position: float = None,
        velocity: float = None,
        effort: float = None,
        temperature: float = None,
    ):
        """Set joint state metrics"""
        if self._metrics:
            if position is not None:
                self._metrics.joint_position.labels(joint_name=joint_name).set(position)
            if velocity is not None:
                self._metrics.joint_velocity.labels(joint_name=joint_name).set(velocity)
            if effort is not None:
                self._metrics.joint_effort.labels(joint_name=joint_name).set(effort)
            if temperature is not None:
                self._metrics.joint_temperature.labels(joint_name=joint_name).set(temperature)

            # Also record to base metrics
            self._obs.metrics.set_joint_state(
                joint_name=joint_name,
                position=position,
                velocity=velocity,
                effort=effort,
            )

    def set_all_joint_states(self, joint_states: Dict[str, Dict]):
        """
        Set multiple joint states at once

        Args:
            joint_states: Dict mapping joint names to state dicts
                         {'joint_1': {'position': 1.0, 'velocity': 0.1, ...}}
        """
        for joint_name, state in joint_states.items():
            self.set_joint_state(
                joint_name,
                position=state.get("position"),
                velocity=state.get("velocity"),
                effort=state.get("effort"),
                temperature=state.get("temperature"),
            )

    def record_joint_limit(self, joint_name: str, limit_type: str):
        """Record joint limit reached event"""
        if self._metrics:
            self._metrics.joint_limits_reached.labels(
                joint_name=joint_name,
                limit_type=limit_type,
            ).inc()

    # ==================== Path Planning Metrics ====================

    def record_path_planned(
        self,
        algorithm: str,
        status: str = "success",
        path_length: float = None,
        waypoints: int = None,
        duration: float = None,
    ):
        """Record path planning"""
        if self._metrics:
            self._metrics.paths_planned.labels(
                algorithm=algorithm,
                status=status,
            ).inc()

            if duration is not None:
                self._metrics.path_planning_duration.labels(
                    algorithm=algorithm,
                ).observe(duration)

                # Also record to base metrics
                self._obs.metrics.record_path_planned(
                    algorithm=algorithm,
                    duration=duration,
                )

            if path_length is not None:
                self._metrics.path_length_meters.observe(path_length)

            if waypoints is not None:
                self._metrics.path_waypoints.observe(waypoints)

    def record_path_replan(self, reason: str):
        """Record path replanning event"""
        if self._metrics:
            self._metrics.path_replanning.labels(reason=reason).inc()

    @contextmanager
    def trace_path_planning(self, algorithm: str):
        """Context manager for tracing path planning with result tracking"""
        start_time = time.perf_counter()
        result_data = {"path_length": None, "waypoints": None, "status": "success"}

        class PlannerResult:
            def set_result(self, path_length: float = None, waypoints: int = None):
                result_data["path_length"] = path_length
                result_data["waypoints"] = waypoints

            def set_failed(self, reason: str = ""):
                result_data["status"] = "failed"

        try:
            if self._obs and self._obs.tracer:
                with self._obs.tracer.start_span(
                    f"path_planning.{algorithm}",
                    attributes={
                        "planning.algorithm": algorithm,
                        "component": "roc",
                    },
                ):
                    yield PlannerResult()
            else:
                yield PlannerResult()
        finally:
            duration = time.perf_counter() - start_time
            self.record_path_planned(
                algorithm=algorithm,
                status=result_data["status"],
                path_length=result_data["path_length"],
                waypoints=result_data["waypoints"],
                duration=duration,
            )

    # ==================== Path Execution Metrics ====================

    def set_path_progress(self, progress_percent: float, deviation: float = None):
        """Set current path execution progress"""
        if self._metrics:
            self._metrics.path_progress.set(progress_percent)
            if deviation is not None:
                self._metrics.path_deviation.set(deviation)

    def record_waypoint_reached(self):
        """Record waypoint reached"""
        if self._metrics:
            self._metrics.waypoint_reached.inc()

    def record_path_completed(self, execution_time: float):
        """Record path execution completed"""
        if self._metrics:
            self._metrics.path_execution_time.observe(execution_time)

    # ==================== Motion Metrics ====================

    def set_velocity(
        self,
        x: float = None,
        y: float = None,
        z: float = None,
        angular: float = None,
        commanded: bool = False,
    ):
        """Set current or commanded velocity"""
        if self._metrics:
            gauge = (
                self._metrics.velocity_commanded if commanded else self._metrics.velocity_current
            )
            if x is not None:
                gauge.labels(axis="x").set(x)
            if y is not None:
                gauge.labels(axis="y").set(y)
            if z is not None:
                gauge.labels(axis="z").set(z)
            if angular is not None:
                gauge.labels(axis="angular").set(angular)

            # Record to base metrics (current only)
            if not commanded:
                magnitude = ((x or 0) ** 2 + (y or 0) ** 2 + (z or 0) ** 2) ** 0.5
                self._obs.metrics.set_robot_velocity(
                    linear_x=x or 0,
                    linear_y=y or 0,
                    linear_z=z or 0,
                    angular_z=angular or 0,
                )

    def set_position(
        self,
        x: float = None,
        y: float = None,
        z: float = None,
        target: bool = False,
    ):
        """Set current or target position"""
        if self._metrics:
            gauge = self._metrics.position_target if target else self._metrics.position_current
            if x is not None:
                gauge.labels(axis="x").set(x)
            if y is not None:
                gauge.labels(axis="y").set(y)
            if z is not None:
                gauge.labels(axis="z").set(z)

    def set_position_error(self, x: float = None, y: float = None, z: float = None):
        """Set position tracking error"""
        if self._metrics:
            if x is not None:
                self._metrics.position_error.labels(axis="x").set(x)
            if y is not None:
                self._metrics.position_error.labels(axis="y").set(y)
            if z is not None:
                self._metrics.position_error.labels(axis="z").set(z)

    def set_acceleration(self, x: float = None, y: float = None, z: float = None):
        """Set current acceleration"""
        if self._metrics:
            if x is not None:
                self._metrics.acceleration.labels(axis="x").set(x)
            if y is not None:
                self._metrics.acceleration.labels(axis="y").set(y)
            if z is not None:
                self._metrics.acceleration.labels(axis="z").set(z)

    # ==================== Controller Metrics ====================

    def set_controller_output(
        self, controller_name: str, output: float, output_type: str = "command"
    ):
        """Set controller output signal"""
        if self._metrics:
            self._metrics.controller_output.labels(
                controller_name=controller_name,
                output_type=output_type,
            ).set(output)

    def set_controller_error(self, controller_name: str, error: float):
        """Set controller error signal"""
        if self._metrics:
            self._metrics.controller_error.labels(controller_name=controller_name).set(error)

    def set_controller_gains(
        self,
        controller_name: str,
        p: float = None,
        i: float = None,
        d: float = None,
        ff: float = None,
    ):
        """Set controller gain values"""
        if self._metrics:
            if p is not None:
                self._metrics.controller_gains.labels(
                    controller_name=controller_name, gain_type="p"
                ).set(p)
            if i is not None:
                self._metrics.controller_gains.labels(
                    controller_name=controller_name, gain_type="i"
                ).set(i)
            if d is not None:
                self._metrics.controller_gains.labels(
                    controller_name=controller_name, gain_type="d"
                ).set(d)
            if ff is not None:
                self._metrics.controller_gains.labels(
                    controller_name=controller_name, gain_type="ff"
                ).set(ff)

    # ==================== Safety Metrics ====================

    def record_safety_stop(self, reason: str):
        """Record safety stop event"""
        if self._metrics:
            self._metrics.safety_stops.labels(reason=reason).inc()

        if self._obs:
            self._obs.logger.warning(f"Safety stop triggered: {reason}")
            self._obs.recorder.record_event("safety_stop", {"reason": reason})

    def record_safety_violation(self, violation_type: str, severity: str):
        """Record safety violation"""
        if self._metrics:
            self._metrics.safety_violations.labels(
                violation_type=violation_type,
                severity=severity,
            ).inc()

            # Record to base metrics
            self._obs.metrics.record_safety_violation(
                zone_id="roc",
                violation_type=violation_type,
            )

        if self._obs:
            self._obs.record_error(
                f"safety_violation_{violation_type}",
                f"Safety violation: {violation_type} ({severity})",
            )

    def set_safety_zone_status(self, zone: str, status: str):
        """Set safety zone status: 'clear', 'warning', or 'danger'"""
        status_map = {"clear": 0, "warning": 1, "danger": 2}
        if self._metrics and status in status_map:
            self._metrics.safety_zone_status.labels(zone=zone).set(status_map[status])

    def set_estop_status(self, engaged: bool):
        """Set emergency stop status"""
        if self._metrics:
            self._metrics.estop_status.set(1 if engaged else 0)
            if engaged:
                self.set_control_mode("estop")

    def record_recovery_attempt(self, recovery_type: str, status: str):
        """Record recovery attempt: status is 'success' or 'failed'"""
        if self._metrics:
            self._metrics.recovery_attempts.labels(
                recovery_type=recovery_type,
                status=status,
            ).inc()

    # ==================== Action Server Metrics ====================

    def record_action_goal(self, action_name: str, goal_id: str = None):
        """Record action goal received"""
        if self._metrics:
            self._metrics.action_goals_received.labels(action_name=action_name).inc()

            # Record to base metrics
            self._obs.metrics.record_ros2_action(
                action_name=action_name,
                result="received",
            )

    def record_action_result(
        self,
        action_name: str,
        status: str,
        execution_time: float = None,
        abort_reason: str = None,
    ):
        """Record action result: status is 'succeeded', 'aborted', or 'canceled'"""
        if self._metrics:
            if status == "succeeded":
                self._metrics.action_goals_succeeded.labels(action_name=action_name).inc()
            elif status == "aborted":
                self._metrics.action_goals_aborted.labels(
                    action_name=action_name,
                    reason=abort_reason or "unknown",
                ).inc()
            elif status == "canceled":
                self._metrics.action_goals_canceled.labels(action_name=action_name).inc()

            if execution_time is not None:
                self._metrics.action_execution_time.labels(action_name=action_name).observe(
                    execution_time
                )

            # Record to base metrics
            self._obs.metrics.record_ros2_action(
                action_name=action_name,
                result=status,
            )

    @contextmanager
    def trace_action(self, action_name: str, goal_id: str = None):
        """Context manager for tracing action execution"""
        start_time = time.perf_counter()
        self.record_action_goal(action_name, goal_id)
        result_status = {"status": "succeeded", "reason": None}

        class ActionResult:
            def abort(self, reason: str = None):
                result_status["status"] = "aborted"
                result_status["reason"] = reason

            def cancel(self):
                result_status["status"] = "canceled"

        try:
            if self._obs and self._obs.tracer:
                with self._obs.tracer.start_span(
                    f"action.{action_name}",
                    attributes={
                        "action.name": action_name,
                        "action.goal_id": goal_id or "",
                        "component": "roc",
                    },
                ):
                    yield ActionResult()
            else:
                yield ActionResult()
        finally:
            execution_time = time.perf_counter() - start_time
            self.record_action_result(
                action_name,
                status=result_status["status"],
                execution_time=execution_time,
                abort_reason=result_status["reason"],
            )

    # ==================== Performance Metrics ====================

    def set_control_loop_frequency(self, frequency_hz: float):
        """Set control loop frequency"""
        if self._metrics:
            self._metrics.control_loop_frequency.set(frequency_hz)

    def record_control_loop_jitter(self, jitter_ms: float):
        """Record control loop jitter"""
        if self._metrics:
            self._metrics.control_loop_jitter.observe(jitter_ms)

    def record_control_loop_overrun(self):
        """Record control loop deadline overrun"""
        if self._metrics:
            self._metrics.control_loop_overruns.inc()

    def set_cpu_usage(self, usage_percent: float):
        """Set CPU usage"""
        if self._metrics:
            self._metrics.cpu_usage.set(usage_percent)

    @contextmanager
    def trace_control_loop(self):
        """
        Context manager for high-frequency control loop iterations.
        Uses sampling to avoid overwhelming trace storage.
        """
        if self._control_loop_tracer:
            with self._control_loop_tracer.trace_iteration():
                yield
        else:
            yield

    # ==================== Decorator Helpers ====================

    def traced_callback(self, name: str = None):
        """
        Decorator for tracing ROS2 callbacks

        Usage:
            @obs.traced_callback('joint_state')
            def joint_state_callback(msg):
                ...
        """

        def decorator(func):
            callback_name = name or func.__name__

            @wraps(func)
            def wrapper(*args, **kwargs):
                if self._obs and self._obs.tracer:
                    with self._obs.tracer.start_span(
                        f"callback.{callback_name}",
                        attributes={"component": "roc", "callback": callback_name},
                    ):
                        return func(*args, **kwargs)
                return func(*args, **kwargs)

            return wrapper

        return decorator
