"""
Enhanced State Tracker

Centralized robot state tracking with health monitoring,
coordination status, and fleet-wide awareness.

Based on REMROC's per-robot state dictionary pattern and
Open-RMF's fleet adapter state management.

Key Features:
- Per-robot operational states
- Health monitoring and stale detection
- Coordination state (waiting, yielding, etc.)
- Fleet-wide status aggregation
- State change events and callbacks
"""

import json
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import rclpy
from geometry_msgs.msg import Point, Pose, Twist
from rclpy.node import Node


class OperationalState(Enum):
    """High-level robot operational state"""

    UNKNOWN = "unknown"
    OFFLINE = "offline"
    INITIALIZING = "initializing"
    IDLE = "idle"
    NAVIGATING = "navigating"
    EXECUTING_TASK = "executing_task"
    WAITING = "waiting"
    EMERGENCY_STOP = "emergency_stop"
    ERROR = "error"
    MAINTENANCE = "maintenance"


class CoordinationState(Enum):
    """Robot's coordination status with other robots"""

    NONE = "none"
    YIELDING = "yielding"  # Giving way to another robot
    WAITING_FOR_CLEARANCE = "waiting_for_clearance"
    WAITING_AT_CRITICAL_SECTION = "waiting_at_critical_section"
    EVADING = "evading"
    FOLLOWING = "following"  # Following another robot


class HealthStatus(Enum):
    """Robot health status"""

    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"  # Some issues but operational
    UNHEALTHY = "unhealthy"  # Major issues
    CRITICAL = "critical"  # Needs immediate attention


@dataclass
class Position2D:
    """2D position with orientation"""

    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0

    def distance_to(self, other: "Position2D") -> float:
        """Calculate distance to another position"""
        import math

        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)


@dataclass
class Velocity2D:
    """2D velocity"""

    linear_x: float = 0.0
    linear_y: float = 0.0
    angular_z: float = 0.0

    @property
    def speed(self) -> float:
        """Total linear speed"""
        import math

        return math.sqrt(self.linear_x**2 + self.linear_y**2)


@dataclass
class BatteryState:
    """Robot battery state"""

    percentage: float = 100.0
    voltage: float = 0.0
    is_charging: bool = False
    estimated_runtime_sec: float = 0.0


@dataclass
class SensorState:
    """Summary of sensor states"""

    laser_ok: bool = True
    camera_ok: bool = True
    imu_ok: bool = True
    odometry_ok: bool = True
    last_laser_time: float = 0.0
    min_obstacle_distance: float = float("inf")


@dataclass
class TaskState:
    """Current task information"""

    task_id: Optional[str] = None
    task_type: str = ""
    progress: float = 0.0  # 0.0 to 1.0
    goal_x: float = 0.0
    goal_y: float = 0.0
    started_at: float = 0.0


@dataclass
class RobotFullState:
    """
    Complete state of a single robot.
    Based on REMROC's robot_states dictionary.
    """

    robot_id: str

    # Operational
    operational_state: OperationalState = OperationalState.UNKNOWN
    coordination_state: CoordinationState = CoordinationState.NONE
    health_status: HealthStatus = HealthStatus.UNKNOWN

    # Position & Velocity
    position: Position2D = field(default_factory=Position2D)
    velocity: Velocity2D = field(default_factory=Velocity2D)

    # Subsystems
    battery: BatteryState = field(default_factory=BatteryState)
    sensors: SensorState = field(default_factory=SensorState)
    task: TaskState = field(default_factory=TaskState)

    # Coordination info
    waiting_for_robot: Optional[str] = None  # Robot we're waiting for
    yielding_to_robot: Optional[str] = None  # Robot we're yielding to
    in_critical_section: bool = False
    critical_section_id: Optional[str] = None

    # Path info
    current_path: Optional[List[Tuple[float, float]]] = None
    path_progress: float = 0.0

    # Timing
    last_update: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    uptime_sec: float = 0.0
    startup_time: float = field(default_factory=time.time)

    # Metadata
    robot_type: str = ""
    capabilities: List[str] = field(default_factory=list)
    custom_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "robot_id": self.robot_id,
            "operational_state": self.operational_state.value,
            "coordination_state": self.coordination_state.value,
            "health_status": self.health_status.value,
            "position": {
                "x": self.position.x,
                "y": self.position.y,
                "yaw": self.position.yaw,
            },
            "velocity": {
                "linear_x": self.velocity.linear_x,
                "linear_y": self.velocity.linear_y,
                "angular_z": self.velocity.angular_z,
            },
            "battery": {
                "percentage": self.battery.percentage,
                "is_charging": self.battery.is_charging,
            },
            "task": {
                "task_id": self.task.task_id,
                "task_type": self.task.task_type,
                "progress": self.task.progress,
            },
            "waiting_for_robot": self.waiting_for_robot,
            "yielding_to_robot": self.yielding_to_robot,
            "in_critical_section": self.in_critical_section,
            "last_update": self.last_update,
            "uptime_sec": self.uptime_sec,
        }


class StateChangeEvent:
    """Event for state changes"""

    def __init__(self, robot_id: str, field_name: str, old_value: Any, new_value: Any):
        self.robot_id = robot_id
        self.field_name = field_name
        self.old_value = old_value
        self.new_value = new_value
        self.timestamp = time.time()


class EnhancedStateTracker:
    """
    Centralized state tracking for all robots.

    Features:
    - Real-time state updates
    - Stale detection
    - State change notifications
    - Fleet-wide queries
    - Coordination state management
    """

    # Configuration
    STALE_THRESHOLD = 5.0  # seconds without update
    HEARTBEAT_TIMEOUT = 10.0  # seconds without heartbeat
    POSITION_UPDATE_THRESHOLD = 0.01  # meters

    def __init__(self, logger=None):
        self.logger = logger

        # Per-robot states (REMROC pattern)
        self.robot_states: Dict[str, RobotFullState] = {}

        # Callbacks
        self.state_change_callbacks: List[Callable[[StateChangeEvent], None]] = []
        self.robot_added_callbacks: List[Callable[[str], None]] = []
        self.robot_removed_callbacks: List[Callable[[str], None]] = []
        self.health_change_callbacks: List[Callable[[str, HealthStatus], None]] = []

        # Lock
        self._lock = threading.RLock()

        # Health monitoring
        self._running = True
        self._monitor_thread = threading.Thread(target=self._health_monitor_loop, daemon=True)
        self._monitor_thread.start()

    def register_robot(
        self,
        robot_id: str,
        robot_type: str = "",
        capabilities: Optional[List[str]] = None,
    ) -> None:
        """Register a new robot"""
        with self._lock:
            if robot_id in self.robot_states:
                if self.logger:
                    self.logger.warn(f"Robot {robot_id} already registered")
                return

            state = RobotFullState(
                robot_id=robot_id,
                robot_type=robot_type,
                capabilities=capabilities or [],
                operational_state=OperationalState.INITIALIZING,
            )

            self.robot_states[robot_id] = state

        # Notify callbacks
        for callback in self.robot_added_callbacks:
            try:
                callback(robot_id)
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Robot added callback error: {e}")

        if self.logger:
            self.logger.info(f"Registered robot: {robot_id} (type: {robot_type})")

    def unregister_robot(self, robot_id: str) -> None:
        """Unregister a robot"""
        with self._lock:
            if robot_id not in self.robot_states:
                return

            del self.robot_states[robot_id]

        # Notify callbacks
        for callback in self.robot_removed_callbacks:
            try:
                callback(robot_id)
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Robot removed callback error: {e}")

        if self.logger:
            self.logger.info(f"Unregistered robot: {robot_id}")

    def get_state(self, robot_id: str) -> Optional[RobotFullState]:
        """Get state for a robot"""
        with self._lock:
            return self.robot_states.get(robot_id)

    def get_all_states(self) -> Dict[str, RobotFullState]:
        """Get all robot states"""
        with self._lock:
            return dict(self.robot_states)

    def get_robot_ids(self) -> List[str]:
        """Get all registered robot IDs"""
        with self._lock:
            return list(self.robot_states.keys())

    # === State Updates ===

    def update_position(self, robot_id: str, x: float, y: float, yaw: float = 0.0) -> None:
        """Update robot position"""
        with self._lock:
            if robot_id not in self.robot_states:
                return

            state = self.robot_states[robot_id]
            old_pos = state.position

            # Only update if significant change
            import math

            distance = math.sqrt((x - old_pos.x) ** 2 + (y - old_pos.y) ** 2)

            if distance > self.POSITION_UPDATE_THRESHOLD or abs(yaw - old_pos.yaw) > 0.01:
                state.position = Position2D(x=x, y=y, yaw=yaw)
                state.last_update = time.time()

                self._emit_change(robot_id, "position", old_pos, state.position)

    def update_velocity(
        self,
        robot_id: str,
        linear_x: float,
        linear_y: float = 0.0,
        angular_z: float = 0.0,
    ) -> None:
        """Update robot velocity"""
        with self._lock:
            if robot_id not in self.robot_states:
                return

            state = self.robot_states[robot_id]
            state.velocity = Velocity2D(linear_x=linear_x, linear_y=linear_y, angular_z=angular_z)
            state.last_update = time.time()

    def update_operational_state(self, robot_id: str, new_state: OperationalState) -> None:
        """Update operational state"""
        with self._lock:
            if robot_id not in self.robot_states:
                return

            state = self.robot_states[robot_id]
            old_state = state.operational_state

            if new_state != old_state:
                state.operational_state = new_state
                state.last_update = time.time()

                self._emit_change(robot_id, "operational_state", old_state, new_state)

                if self.logger:
                    self.logger.info(f"Robot {robot_id}: {old_state.value} -> {new_state.value}")

    def update_coordination_state(
        self,
        robot_id: str,
        new_state: CoordinationState,
        related_robot: Optional[str] = None,
    ) -> None:
        """Update coordination state"""
        with self._lock:
            if robot_id not in self.robot_states:
                return

            state = self.robot_states[robot_id]
            old_state = state.coordination_state

            state.coordination_state = new_state

            if new_state == CoordinationState.YIELDING:
                state.yielding_to_robot = related_robot
            elif new_state == CoordinationState.WAITING_FOR_CLEARANCE:
                state.waiting_for_robot = related_robot
            else:
                state.yielding_to_robot = None
                state.waiting_for_robot = None

            state.last_update = time.time()

            if new_state != old_state:
                self._emit_change(robot_id, "coordination_state", old_state, new_state)

    def update_task_state(
        self,
        robot_id: str,
        task_id: str,
        task_type: str,
        progress: float,
        goal_x: float = 0.0,
        goal_y: float = 0.0,
    ) -> None:
        """Update current task state"""
        with self._lock:
            if robot_id not in self.robot_states:
                return

            state = self.robot_states[robot_id]

            # New task
            if task_id != state.task.task_id:
                state.task = TaskState(
                    task_id=task_id,
                    task_type=task_type,
                    progress=progress,
                    goal_x=goal_x,
                    goal_y=goal_y,
                    started_at=time.time(),
                )
            else:
                state.task.progress = progress

            state.last_update = time.time()

    def clear_task(self, robot_id: str) -> None:
        """Clear current task"""
        with self._lock:
            if robot_id not in self.robot_states:
                return

            state = self.robot_states[robot_id]
            state.task = TaskState()
            state.last_update = time.time()

    def update_battery(
        self,
        robot_id: str,
        percentage: float,
        is_charging: bool = False,
        voltage: float = 0.0,
    ) -> None:
        """Update battery state"""
        with self._lock:
            if robot_id not in self.robot_states:
                return

            state = self.robot_states[robot_id]
            state.battery.percentage = percentage
            state.battery.is_charging = is_charging
            state.battery.voltage = voltage
            state.last_update = time.time()

    def update_sensor_state(
        self,
        robot_id: str,
        laser_ok: bool = True,
        min_obstacle_distance: float = float("inf"),
    ) -> None:
        """Update sensor state"""
        with self._lock:
            if robot_id not in self.robot_states:
                return

            state = self.robot_states[robot_id]
            state.sensors.laser_ok = laser_ok
            state.sensors.min_obstacle_distance = min_obstacle_distance
            state.sensors.last_laser_time = time.time()
            state.last_update = time.time()

    def update_path(
        self, robot_id: str, path: List[Tuple[float, float]], progress: float = 0.0
    ) -> None:
        """Update current path"""
        with self._lock:
            if robot_id not in self.robot_states:
                return

            state = self.robot_states[robot_id]
            state.current_path = path
            state.path_progress = progress
            state.last_update = time.time()

    def set_critical_section(
        self, robot_id: str, in_section: bool, section_id: Optional[str] = None
    ) -> None:
        """Mark robot as in/out of critical section"""
        with self._lock:
            if robot_id not in self.robot_states:
                return

            state = self.robot_states[robot_id]
            state.in_critical_section = in_section
            state.critical_section_id = section_id if in_section else None
            state.last_update = time.time()

    def heartbeat(self, robot_id: str) -> None:
        """Update heartbeat timestamp"""
        with self._lock:
            if robot_id not in self.robot_states:
                return

            state = self.robot_states[robot_id]
            state.last_heartbeat = time.time()
            state.uptime_sec = state.last_heartbeat - state.startup_time

    # === Fleet Queries ===

    def get_robots_by_state(self, state: OperationalState) -> List[str]:
        """Get robots in a specific operational state"""
        with self._lock:
            return [rid for rid, s in self.robot_states.items() if s.operational_state == state]

    def get_idle_robots(self) -> List[str]:
        """Get all idle robots"""
        return self.get_robots_by_state(OperationalState.IDLE)

    def get_navigating_robots(self) -> List[str]:
        """Get all navigating robots"""
        return self.get_robots_by_state(OperationalState.NAVIGATING)

    def get_robots_in_area(self, x: float, y: float, radius: float) -> List[str]:
        """Get robots within a circular area"""
        import math

        with self._lock:
            result = []
            for rid, state in self.robot_states.items():
                distance = math.sqrt((state.position.x - x) ** 2 + (state.position.y - y) ** 2)
                if distance <= radius:
                    result.append(rid)
            return result

    def get_closest_robot_to(
        self, x: float, y: float, exclude: Optional[Set[str]] = None
    ) -> Optional[Tuple[str, float]]:
        """Get closest robot to a position"""
        import math

        exclude = exclude or set()

        with self._lock:
            closest = None
            min_dist = float("inf")

            for rid, state in self.robot_states.items():
                if rid in exclude:
                    continue

                distance = math.sqrt((state.position.x - x) ** 2 + (state.position.y - y) ** 2)

                if distance < min_dist:
                    min_dist = distance
                    closest = rid

            return (closest, min_dist) if closest else None

    def get_robots_with_low_battery(self, threshold: float = 20.0) -> List[str]:
        """Get robots with battery below threshold"""
        with self._lock:
            return [
                rid
                for rid, state in self.robot_states.items()
                if state.battery.percentage < threshold
            ]

    def get_stale_robots(self) -> List[str]:
        """Get robots that haven't updated recently"""
        current_time = time.time()

        with self._lock:
            return [
                rid
                for rid, state in self.robot_states.items()
                if current_time - state.last_update > self.STALE_THRESHOLD
            ]

    def get_offline_robots(self) -> List[str]:
        """Get robots that missed heartbeat"""
        current_time = time.time()

        with self._lock:
            return [
                rid
                for rid, state in self.robot_states.items()
                if current_time - state.last_heartbeat > self.HEARTBEAT_TIMEOUT
            ]

    def get_robots_in_critical_section(self) -> List[str]:
        """Get robots currently in critical sections"""
        with self._lock:
            return [rid for rid, state in self.robot_states.items() if state.in_critical_section]

    def get_robots_waiting(self) -> Dict[str, str]:
        """Get robots that are waiting and what they're waiting for"""
        with self._lock:
            return {
                rid: state.waiting_for_robot or "unknown"
                for rid, state in self.robot_states.items()
                if state.coordination_state == CoordinationState.WAITING_FOR_CLEARANCE
            }

    def get_all_positions(self) -> Dict[str, Tuple[float, float]]:
        """Get positions of all robots"""
        with self._lock:
            return {
                rid: (state.position.x, state.position.y)
                for rid, state in self.robot_states.items()
            }

    def get_fleet_summary(self) -> Dict[str, Any]:
        """Get summary of fleet status"""
        with self._lock:
            total = len(self.robot_states)

            states = {}
            for state in OperationalState:
                count = sum(1 for s in self.robot_states.values() if s.operational_state == state)
                if count > 0:
                    states[state.value] = count

            health = {}
            for h in HealthStatus:
                count = sum(1 for s in self.robot_states.values() if s.health_status == h)
                if count > 0:
                    health[h.value] = count

            return {
                "total_robots": total,
                "by_state": states,
                "by_health": health,
                "stale_count": len(self.get_stale_robots()),
                "offline_count": len(self.get_offline_robots()),
                "in_critical_sections": len(self.get_robots_in_critical_section()),
                "low_battery_count": len(self.get_robots_with_low_battery()),
            }

    # === Health Monitoring ===

    def _health_monitor_loop(self) -> None:
        """Background thread for health monitoring"""
        while self._running:
            time.sleep(1.0)
            self._check_health()

    def _check_health(self) -> None:
        """Check health of all robots"""
        current_time = time.time()

        with self._lock:
            for robot_id, state in self.robot_states.items():
                old_health = state.health_status
                new_health = self._determine_health(state, current_time)

                if new_health != old_health:
                    state.health_status = new_health

                    # Notify callbacks
                    for callback in self.health_change_callbacks:
                        try:
                            callback(robot_id, new_health)
                        except Exception as e:
                            if self.logger:
                                self.logger.error(f"Health callback error: {e}")

                    if self.logger:
                        self.logger.warn(
                            f"Robot {robot_id} health: " f"{old_health.value} -> {new_health.value}"
                        )

    def _determine_health(self, state: RobotFullState, current_time: float) -> HealthStatus:
        """Determine health status based on state"""

        # Check heartbeat
        heartbeat_age = current_time - state.last_heartbeat
        if heartbeat_age > self.HEARTBEAT_TIMEOUT * 2:
            return HealthStatus.CRITICAL
        elif heartbeat_age > self.HEARTBEAT_TIMEOUT:
            return HealthStatus.UNHEALTHY

        # Check update freshness
        update_age = current_time - state.last_update
        if update_age > self.STALE_THRESHOLD * 2:
            return HealthStatus.UNHEALTHY
        elif update_age > self.STALE_THRESHOLD:
            return HealthStatus.DEGRADED

        # Check battery
        if state.battery.percentage < 5:
            return HealthStatus.CRITICAL
        elif state.battery.percentage < 15:
            return HealthStatus.UNHEALTHY
        elif state.battery.percentage < 25:
            return HealthStatus.DEGRADED

        # Check sensors
        if not state.sensors.laser_ok or not state.sensors.odometry_ok:
            return HealthStatus.DEGRADED

        # Check operational state
        if state.operational_state == OperationalState.ERROR:
            return HealthStatus.UNHEALTHY
        elif state.operational_state == OperationalState.EMERGENCY_STOP:
            return HealthStatus.DEGRADED

        return HealthStatus.HEALTHY

    # === Callbacks ===

    def _emit_change(self, robot_id: str, field_name: str, old_value: Any, new_value: Any) -> None:
        """Emit state change event"""
        event = StateChangeEvent(robot_id, field_name, old_value, new_value)

        for callback in self.state_change_callbacks:
            try:
                callback(event)
            except Exception as e:
                if self.logger:
                    self.logger.error(f"State change callback error: {e}")

    def register_state_change_callback(self, callback: Callable[[StateChangeEvent], None]) -> None:
        """Register callback for state changes"""
        self.state_change_callbacks.append(callback)

    def register_robot_added_callback(self, callback: Callable[[str], None]) -> None:
        """Register callback for robot additions"""
        self.robot_added_callbacks.append(callback)

    def register_robot_removed_callback(self, callback: Callable[[str], None]) -> None:
        """Register callback for robot removals"""
        self.robot_removed_callbacks.append(callback)

    def register_health_callback(self, callback: Callable[[str, HealthStatus], None]) -> None:
        """Register callback for health changes"""
        self.health_change_callbacks.append(callback)

    def shutdown(self) -> None:
        """Shutdown the state tracker"""
        self._running = False
        if self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)
