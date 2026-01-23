"""
ROC Data Types - Shared data types for Robot Operator Controller.

Contains common enums, dataclasses, and type definitions used across
all ROC modules.
"""

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

# =============================================================================
# Enumerations
# =============================================================================


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


class SafetyLevel(Enum):
    """Safety level enumeration."""

    NORMAL = auto()
    WARNING = auto()
    CRITICAL = auto()
    EMERGENCY = auto()


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# =============================================================================
# Joint Data Types
# =============================================================================


@dataclass
class JointLimits:
    """Complete limits for a joint."""

    lower: float = -3.14159
    upper: float = 3.14159
    velocity: float = 2.0
    effort: float = 100.0

    def clamp(self, value: float) -> float:
        """Clamp value to limits."""
        return max(self.lower, min(self.upper, value))

    def contains(self, value: float, margin: float = 0.0) -> bool:
        """Check if value is within limits."""
        return (self.lower + margin) <= value <= (self.upper - margin)

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary."""
        return {
            "lower": self.lower,
            "upper": self.upper,
            "velocity": self.velocity,
            "effort": self.effort,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JointLimits":
        """Create from dictionary."""
        return cls(
            lower=data.get("lower", -3.14159),
            upper=data.get("upper", 3.14159),
            velocity=data.get("velocity", 2.0),
            effort=data.get("effort", 100.0),
        )


@dataclass
class JointInfo:
    """Static joint information from FTI."""

    name: str
    joint_type: JointType = JointType.REVOLUTE
    limits: JointLimits = field(default_factory=JointLimits)
    parent_link: str = ""
    child_link: str = ""
    ue5_constraint_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "type": self.joint_type.value,
            "limits": self.limits.to_dict(),
            "parent_link": self.parent_link,
            "child_link": self.child_link,
            "ue5_constraint_name": self.ue5_constraint_name,
        }

    @classmethod
    def from_fti(cls, data: Dict[str, Any]) -> "JointInfo":
        """Create from FTI joint data."""
        try:
            joint_type = JointType(data.get("type", "revolute"))
        except ValueError:
            joint_type = JointType.REVOLUTE

        limits_data = data.get("limits", {})

        return cls(
            name=data.get("name", "unknown"),
            joint_type=joint_type,
            limits=JointLimits.from_dict(limits_data),
            parent_link=data.get("parent_link", ""),
            child_link=data.get("child_link", ""),
            ue5_constraint_name=data.get("ue5_constraint_name", ""),
        )


@dataclass
class JointState:
    """Dynamic joint state from DIMC."""

    name: str
    position: float = 0.0
    velocity: float = 0.0
    effort: float = 0.0
    target_position: Optional[float] = None
    is_moving: bool = False
    at_limit: bool = False
    has_error: bool = False
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "position": self.position,
            "velocity": self.velocity,
            "effort": self.effort,
            "target_position": self.target_position,
            "is_moving": self.is_moving,
            "at_limit": self.at_limit,
            "has_error": self.has_error,
        }


# =============================================================================
# Command Data Types
# =============================================================================


@dataclass
class JointCommand:
    """Joint movement command."""

    joint_name: str
    target_position: float
    velocity_limit: float = 0.0
    command_id: str = ""
    source: str = "rpm"
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "joint_name": self.joint_name,
            "target_position": self.target_position,
            "velocity_limit": self.velocity_limit,
            "command_id": self.command_id,
            "source": self.source,
            "timestamp": self.timestamp,
        }


@dataclass
class CommandResult:
    """Result of command validation/execution."""

    approved: bool
    command: JointCommand
    modified_position: Optional[float] = None
    modified_velocity: Optional[float] = None
    rejection_reason: str = ""
    message: str = ""

    @property
    def final_position(self) -> float:
        """Get final position (modified or original)."""
        return (
            self.modified_position
            if self.modified_position is not None
            else self.command.target_position
        )

    @property
    def final_velocity(self) -> float:
        """Get final velocity (modified or original)."""
        return (
            self.modified_velocity
            if self.modified_velocity is not None
            else self.command.velocity_limit
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for IPC."""
        result = {
            "command_id": self.command.command_id,
            "joint_name": self.command.joint_name,
            "approved": self.approved,
        }

        if self.approved:
            result["target_position"] = self.final_position
            result["velocity_limit"] = self.final_velocity
        else:
            result["reason"] = self.rejection_reason
            result["message"] = self.message

        return result


# =============================================================================
# Safety Data Types
# =============================================================================


@dataclass
class ObstacleInfo:
    """Information about a detected obstacle."""

    obstacle_id: str
    distance_cm: float
    direction: Tuple[float, float, float] = (0.0, 0.0, 0.0)
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
    """Aggregated safety status."""

    all_limits_ok: bool = True
    obstacle_distance: float = float("inf")
    within_bounds: bool = True
    estop_active: bool = False
    safety_level: SafetyLevel = SafetyLevel.NORMAL
    obstacles: List[ObstacleInfo] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for IPC."""
        return {
            "all_limits_ok": self.all_limits_ok,
            "obstacle_distance": self.obstacle_distance,
            "within_bounds": self.within_bounds,
            "estop_active": self.estop_active,
            "safety_level": self.safety_level.name.lower(),
        }


@dataclass
class SafetyAlert:
    """Safety alert message."""

    robot_id: str
    alert_type: str
    severity: AlertSeverity
    message: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for IPC."""
        return {
            "type": "safety_alert",
            "robot_id": self.robot_id,
            "alert_type": self.alert_type,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp,
        }


# =============================================================================
# Robot Data Types
# =============================================================================


@dataclass
class RobotCapabilities:
    """Robot capabilities from FTI."""

    has_gripper: bool = False
    max_payload_kg: float = 0.0
    reach_cm: float = 0.0
    dof: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "has_gripper": self.has_gripper,
            "max_payload_kg": self.max_payload_kg,
            "reach_cm": self.reach_cm,
            "dof": self.dof,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RobotCapabilities":
        """Create from dictionary."""
        return cls(
            has_gripper=data.get("has_gripper", False),
            max_payload_kg=data.get("max_payload_kg", 0.0),
            reach_cm=data.get("reach_cm", 0.0),
            dof=data.get("dof", 0),
        )


@dataclass
class RobotSummary:
    """Summary of robot state for UI/IPC."""

    robot_id: str
    robot_name: str
    mode: ControlMode
    status: RobotStatus
    joint_count: int
    safety_status: SafetyStatus

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "robot_id": self.robot_id,
            "robot_name": self.robot_name,
            "mode": self.mode.value,
            "status": self.status.name.lower(),
            "joint_count": self.joint_count,
            "safety_status": self.safety_status.to_dict(),
        }


# =============================================================================
# IPC Message Types
# =============================================================================


class IPCMessageType(Enum):
    """IPC message types."""

    # UE5 -> Linux
    JOINT_COMMAND_REQUEST = "joint_command_request"
    EMERGENCY_STOP = "emergency_stop"
    MODE_CHANGE = "mode_change"
    ROBOT_REGISTERED = "robot_registered"
    HEARTBEAT = "heartbeat"

    # Linux -> UE5
    COMMAND_APPROVED = "command_approved"
    COMMAND_REJECTED = "command_rejected"
    SAFETY_ALERT = "safety_alert"
    STATE_UPDATE = "state_update"
    HEARTBEAT_ACK = "heartbeat_ack"
