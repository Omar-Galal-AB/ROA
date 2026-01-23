"""
Robot State - Per-robot state tracking for ROC.

Maintains comprehensive state for each robot including:
- Joint positions, velocities, and efforts
- Control mode (RPM/ADM)
- Status (ready, moving, stopped, error)
- Safety information (obstacles, boundaries)
- FTI robot specification data
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple


class RobotStatus(Enum):
    """Robot operational status."""

    INITIALIZING = auto()
    READY = auto()
    MOVING = auto()
    EMERGENCY_STOPPED = auto()
    ERROR = auto()
    DISCONNECTED = auto()


class ControlMode(Enum):
    """Control mode enumeration."""

    RPM = "rpm"  # Remote Position Mode - manual control
    ADM = "adm"  # Autonomous Decision Mode - automated control


class JointType(Enum):
    """Joint type enumeration."""

    REVOLUTE = "revolute"
    PRISMATIC = "prismatic"
    CONTINUOUS = "continuous"
    FIXED = "fixed"


@dataclass
class JointLimits:
    """Joint movement limits."""

    lower: float
    upper: float
    velocity: float
    effort: float = 100.0

    def contains(self, position: float) -> bool:
        """Check if position is within limits."""
        return self.lower <= position <= self.upper

    def clamp(self, position: float) -> float:
        """Clamp position to limits."""
        return max(self.lower, min(self.upper, position))


@dataclass
class JointState:
    """State of a single joint."""

    name: str
    joint_type: JointType = JointType.REVOLUTE

    # Current state
    position: float = 0.0
    velocity: float = 0.0
    effort: float = 0.0

    # Target state
    target_position: Optional[float] = None

    # Limits
    limits: Optional[JointLimits] = None

    # UE5 mapping
    ue5_constraint_name: str = ""

    # Status flags
    is_moving: bool = False
    at_limit: bool = False
    has_error: bool = False
    error_message: str = ""

    # Timestamp of last update
    last_update: float = field(default_factory=time.time)

    def update_from_dimc(self, position: float, velocity: float = 0.0, effort: float = 0.0):
        """Update joint state from DIMC data."""
        self.position = position
        self.velocity = velocity
        self.effort = effort
        self.is_moving = abs(velocity) > 0.001
        self.last_update = time.time()

        # Check if at limit
        if self.limits:
            margin = 0.01  # 1cm or 0.01 rad
            self.at_limit = (
                position <= self.limits.lower + margin or position >= self.limits.upper - margin
            )

    def set_target(self, position: float) -> bool:
        """
        Set target position for joint.

        Returns:
            True if target is valid, False if outside limits.
        """
        if self.limits and not self.limits.contains(position):
            return False
        self.target_position = position
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "type": self.joint_type.value,
            "position": self.position,
            "velocity": self.velocity,
            "effort": self.effort,
            "target_position": self.target_position,
            "is_moving": self.is_moving,
            "at_limit": self.at_limit,
            "has_error": self.has_error,
        }


@dataclass
class ObstacleInfo:
    """Information about a detected obstacle."""

    obstacle_id: str
    distance_cm: float
    direction: Tuple[float, float, float]  # Unit vector
    obstacle_type: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.obstacle_id,
            "distance_cm": self.distance_cm,
            "direction": list(self.direction),
            "type": self.obstacle_type,
        }


@dataclass
class SafetyStatus:
    """Aggregated safety status for a robot."""

    all_limits_ok: bool = True
    obstacle_distance: float = float("inf")
    within_bounds: bool = True
    estop_active: bool = False
    obstacles: List[ObstacleInfo] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for IPC."""
        return {
            "all_limits_ok": self.all_limits_ok,
            "obstacle_distance": self.obstacle_distance,
            "within_bounds": self.within_bounds,
            "estop_active": self.estop_active,
        }


class RobotState:
    """
    Comprehensive state tracking for a single robot.

    Aggregates data from:
    - FTI: Robot specification, joint configuration
    - DIMC: Real-time joint states, obstacle detection
    - UE5: Control mode, commands
    """

    def __init__(self, robot_id: str, robot_name: str = ""):
        """
        Initialize robot state.

        Args:
            robot_id: Unique robot identifier.
            robot_name: Human-readable robot name.
        """
        self.robot_id = robot_id
        self.robot_name = robot_name or robot_id
        self.logger = logging.getLogger(f"{__name__}.{robot_id}")

        # Control state
        self.mode = ControlMode.RPM
        self.status = RobotStatus.INITIALIZING

        # Joint tracking
        self.joints: Dict[str, JointState] = {}
        self.joint_order: List[str] = []  # Kinematic chain order

        # Safety tracking
        self.safety = SafetyStatus()

        # Capabilities from FTI
        self.capabilities: Dict[str, Any] = {}

        # Timestamps
        self.created_at = time.time()
        self.last_joint_update: float = 0.0
        self.last_obstacle_update: float = 0.0

        # History tracking
        self._position_history: List[Dict[str, float]] = []
        self._max_history = 1000

    @classmethod
    def from_fti_spec(cls, spec: Dict[str, Any]) -> "RobotState":
        """
        Create RobotState from FTI robot specification.

        Args:
            spec: FTI robot specification dictionary.

        Returns:
            New RobotState instance.
        """
        robot_id = spec.get("robot_id", "unknown")
        robot_name = spec.get("robot_name", robot_id)

        state = cls(robot_id, robot_name)

        # Parse joints
        joints_data = spec.get("joints", [])
        for joint_data in joints_data:
            joint = state._parse_joint_from_fti(joint_data)
            state.joints[joint.name] = joint
            state.joint_order.append(joint.name)

        # Parse capabilities
        state.capabilities = spec.get("robot_capabilities", {})

        state.status = RobotStatus.READY
        state.logger.info(f"Created from FTI spec with {len(state.joints)} joints")

        return state

    def _parse_joint_from_fti(self, data: Dict[str, Any]) -> JointState:
        """Parse joint data from FTI specification."""
        joint_type_str = data.get("type", "revolute")
        try:
            joint_type = JointType(joint_type_str)
        except ValueError:
            joint_type = JointType.REVOLUTE

        limits_data = data.get("limits", {})
        limits = JointLimits(
            lower=limits_data.get("lower", -3.14159),
            upper=limits_data.get("upper", 3.14159),
            velocity=limits_data.get("velocity", 2.0),
            effort=limits_data.get("effort", 100.0),
        )

        return JointState(
            name=data.get("name", "unknown"),
            joint_type=joint_type,
            limits=limits,
            ue5_constraint_name=data.get("ue5_constraint_name", ""),
        )

    def update_from_dimc_joints(self, joint_states: Dict[str, Any]):
        """
        Update joint states from DIMC message.

        Args:
            joint_states: DIMC joint states message.
        """
        joints_data = joint_states.get("joints", [])

        for joint_data in joints_data:
            name = joint_data.get("name")
            if name and name in self.joints:
                self.joints[name].update_from_dimc(
                    position=joint_data.get("position", 0.0),
                    velocity=joint_data.get("velocity", 0.0),
                    effort=joint_data.get("effort", 0.0),
                )

        self.last_joint_update = time.time()
        self._update_status()
        self._record_position_history()

    def update_from_dimc_obstacles(self, obstacle_data: Dict[str, Any]):
        """
        Update obstacle information from DIMC message.

        Args:
            obstacle_data: DIMC obstacle detection message.
        """
        obstacles = []
        for obs in obstacle_data.get("obstacles", []):
            obstacles.append(
                ObstacleInfo(
                    obstacle_id=obs.get("id", "unknown"),
                    distance_cm=obs.get("distance_cm", float("inf")),
                    direction=tuple(obs.get("direction", [0, 0, 0])),
                    obstacle_type=obs.get("type", "unknown"),
                )
            )

        self.safety.obstacles = obstacles
        self.safety.obstacle_distance = obstacle_data.get("closest_distance_cm", float("inf"))

        self.last_obstacle_update = time.time()

    def update_from_dimc_boundaries(self, boundary_data: Dict[str, Any]):
        """
        Update boundary status from DIMC message.

        Args:
            boundary_data: DIMC boundary status message.
        """
        self.safety.within_bounds = boundary_data.get("within_bounds", True)

    def _update_status(self):
        """Update robot status based on current state."""
        if self.safety.estop_active:
            self.status = RobotStatus.EMERGENCY_STOPPED
            return

        # Check if any joint is moving
        any_moving = any(j.is_moving for j in self.joints.values())
        if any_moving:
            self.status = RobotStatus.MOVING
        elif self.status == RobotStatus.MOVING:
            self.status = RobotStatus.READY

        # Check for errors
        any_error = any(j.has_error for j in self.joints.values())
        if any_error:
            self.status = RobotStatus.ERROR

        # Update limits OK flag
        self.safety.all_limits_ok = not any(j.at_limit for j in self.joints.values())

    def _record_position_history(self):
        """Record current positions to history."""
        positions = {name: joint.position for name, joint in self.joints.items()}
        positions["timestamp"] = time.time()

        self._position_history.append(positions)

        # Trim history
        if len(self._position_history) > self._max_history:
            self._position_history = self._position_history[-self._max_history :]

    def get_joint(self, name: str) -> Optional[JointState]:
        """Get joint state by name."""
        return self.joints.get(name)

    def get_all_positions(self) -> Dict[str, float]:
        """Get all joint positions."""
        return {name: j.position for name, j in self.joints.items()}

    def set_mode(self, mode: ControlMode):
        """Set control mode."""
        old_mode = self.mode
        self.mode = mode
        self.logger.info(f"Mode changed: {old_mode.value} -> {mode.value}")

    def set_estop(self, active: bool):
        """Set emergency stop state."""
        self.safety.estop_active = active
        if active:
            self.status = RobotStatus.EMERGENCY_STOPPED
        self._update_status()

    def is_data_stale(self, threshold_ms: float = 200) -> bool:
        """Check if joint data is stale."""
        if self.last_joint_update == 0:
            return True
        elapsed_ms = (time.time() - self.last_joint_update) * 1000
        return elapsed_ms > threshold_ms

    def get_state_summary(self) -> Dict[str, Any]:
        """Get summary of robot state for IPC."""
        return {
            "robot_id": self.robot_id,
            "robot_name": self.robot_name,
            "mode": self.mode.value,
            "status": self.status.name.lower(),
            "joint_count": len(self.joints),
            "safety_status": self.safety.to_dict(),
            "data_stale": self.is_data_stale(),
        }

    def get_position_history(self, count: int = 100) -> List[Dict[str, float]]:
        """Get recent position history."""
        return self._position_history[-count:]

    def to_dict(self) -> Dict[str, Any]:
        """Convert full state to dictionary."""
        return {
            "robot_id": self.robot_id,
            "robot_name": self.robot_name,
            "mode": self.mode.value,
            "status": self.status.name,
            "joints": {name: j.to_dict() for name, j in self.joints.items()},
            "joint_order": self.joint_order,
            "safety": self.safety.to_dict(),
            "capabilities": self.capabilities,
            "last_joint_update": self.last_joint_update,
            "last_obstacle_update": self.last_obstacle_update,
        }
