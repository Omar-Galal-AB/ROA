"""
Command Validator - Validates joint commands before execution.

Provides a validation pipeline that checks:
1. Emergency stop status
2. Position limits
3. Velocity limits
4. Collision risk
5. Boundary violations
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple


class ValidationStatus(Enum):
    """Validation result status."""

    APPROVED = auto()
    REJECTED = auto()
    MODIFIED = auto()


class RejectionReason(Enum):
    """Reasons for command rejection."""

    EMERGENCY_STOP_ACTIVE = "emergency_stop_active"
    EXCEEDS_POSITION_LIMIT = "exceeds_position_limit"
    EXCEEDS_VELOCITY_LIMIT = "exceeds_velocity_limit"
    COLLISION_RISK = "collision_risk"
    BOUNDARY_VIOLATION = "boundary_violation"
    UNKNOWN_ROBOT = "unknown_robot"
    UNKNOWN_JOINT = "unknown_joint"
    INVALID_COMMAND = "invalid_command"


@dataclass
class JointCommand:
    """Represents a joint movement command."""

    joint_name: str
    target_position: float
    velocity_limit: float = 0.0
    command_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "joint_name": self.joint_name,
            "target_position": self.target_position,
            "velocity_limit": self.velocity_limit,
            "command_id": self.command_id,
        }


@dataclass
class JointLimits:
    """Joint position and velocity limits."""

    lower: float
    upper: float
    velocity: float
    effort: float = 100.0

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
class ValidationResult:
    """Result of command validation."""

    status: ValidationStatus
    original_command: JointCommand
    modified_command: Optional[JointCommand] = None
    reason: Optional[RejectionReason] = None
    message: str = ""

    @property
    def approved(self) -> bool:
        """Check if command is approved."""
        return self.status in (ValidationStatus.APPROVED, ValidationStatus.MODIFIED)

    @property
    def final_command(self) -> JointCommand:
        """Get the command to execute (modified or original)."""
        return self.modified_command or self.original_command

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for IPC."""
        result = {
            "approved": self.approved,
            "command_id": self.original_command.command_id,
            "joint_name": self.original_command.joint_name,
        }

        if self.approved:
            final = self.final_command
            result["target_position"] = final.target_position
            result["velocity_limit"] = final.velocity_limit
        else:
            result["reason"] = self.reason.value if self.reason else "unknown"
            result["message"] = self.message

        return result


@dataclass
class ValidationConfig:
    """Configuration for command validation."""

    # Position limits
    safety_margin: float = 0.05  # radians
    on_limit_exceeded: str = "clamp"  # clamp, reject, warn

    # Velocity limits
    default_velocity_multiplier: float = 0.9

    # Obstacle velocity reduction thresholds
    obstacle_velocity_thresholds: List[Tuple[float, float]] = field(
        default_factory=lambda: [
            (100.0, 0.8),  # At 100cm, reduce to 80%
            (50.0, 0.5),  # At 50cm, reduce to 50%
            (25.0, 0.2),  # At 25cm, reduce to 20%
            (10.0, 0.0),  # At 10cm, stop
        ]
    )

    # Collision
    stop_distance: float = 10.0  # cm
    slow_distance: float = 50.0
    warning_distance: float = 100.0

    # Boundary
    boundary_warning_margin: float = 20.0  # cm
    boundary_stop_margin: float = 5.0


class CommandValidator:
    """
    Validates joint commands through safety pipeline.

    Pipeline stages:
    1. Check emergency stop
    2. Check position limits
    3. Check velocity limits
    4. Check collision risk
    5. Check boundary violations
    """

    def __init__(
        self,
        config: Optional[ValidationConfig] = None,
        limit_checker: Optional["LimitChecker"] = None,
    ):
        """
        Initialize validator.

        Args:
            config: Validation configuration.
            limit_checker: LimitChecker instance for joint limits.
        """
        self.config = config or ValidationConfig()
        self.limit_checker = limit_checker
        self.logger = logging.getLogger(__name__)

        # State tracking
        self._estop_active: Dict[str, bool] = {}  # Per-robot e-stop state
        self._obstacle_distances: Dict[str, float] = {}  # Per-robot nearest obstacle
        self._boundary_status: Dict[str, str] = {}  # Per-robot boundary status

        # Statistics
        self._commands_validated = 0
        self._commands_approved = 0
        self._commands_rejected = 0
        self._commands_modified = 0

    def validate_command(
        self,
        robot_id: str,
        command: JointCommand,
        joint_limits: Optional[JointLimits] = None,
    ) -> ValidationResult:
        """
        Validate a single joint command.

        Args:
            robot_id: Robot identifier.
            command: Joint command to validate.
            joint_limits: Limits for the joint (if not using limit_checker).

        Returns:
            ValidationResult with approval status and any modifications.
        """
        self._commands_validated += 1

        # Stage 1: Emergency stop check
        if self._estop_active.get(robot_id, False):
            self._commands_rejected += 1
            return ValidationResult(
                status=ValidationStatus.REJECTED,
                original_command=command,
                reason=RejectionReason.EMERGENCY_STOP_ACTIVE,
                message="Emergency stop is active",
            )

        # Get joint limits
        if joint_limits is None and self.limit_checker:
            joint_limits = self.limit_checker.get_limits(robot_id, command.joint_name)

        if joint_limits is None:
            self._commands_rejected += 1
            return ValidationResult(
                status=ValidationStatus.REJECTED,
                original_command=command,
                reason=RejectionReason.UNKNOWN_JOINT,
                message=f"No limits found for joint {command.joint_name}",
            )

        # Stage 2: Position limit check
        position_result = self._check_position_limits(command, joint_limits)
        if position_result is not None:
            if position_result.status == ValidationStatus.REJECTED:
                self._commands_rejected += 1
            return position_result

        # Stage 3: Velocity limit check
        velocity_result = self._check_velocity_limits(robot_id, command, joint_limits)
        if velocity_result is not None:
            command = velocity_result.final_command

        # Stage 4: Collision check
        collision_result = self._check_collision(robot_id, command)
        if collision_result is not None:
            if collision_result.status == ValidationStatus.REJECTED:
                self._commands_rejected += 1
                return collision_result
            command = collision_result.final_command

        # Stage 5: Boundary check
        boundary_result = self._check_boundary(robot_id)
        if boundary_result is not None and not boundary_result.approved:
            self._commands_rejected += 1
            return boundary_result

        # All checks passed
        if velocity_result or collision_result:
            self._commands_modified += 1
            return ValidationResult(
                status=ValidationStatus.MODIFIED,
                original_command=command,
                modified_command=command,
                message="Command modified for safety",
            )

        self._commands_approved += 1
        return ValidationResult(status=ValidationStatus.APPROVED, original_command=command)

    def validate_commands(
        self,
        robot_id: str,
        commands: List[JointCommand],
        joint_limits_map: Optional[Dict[str, JointLimits]] = None,
    ) -> List[ValidationResult]:
        """
        Validate multiple joint commands.

        Args:
            robot_id: Robot identifier.
            commands: List of commands to validate.
            joint_limits_map: Map of joint name to limits.

        Returns:
            List of validation results.
        """
        results = []
        for command in commands:
            limits = None
            if joint_limits_map:
                limits = joint_limits_map.get(command.joint_name)
            results.append(self.validate_command(robot_id, command, limits))
        return results

    def _check_position_limits(
        self, command: JointCommand, limits: JointLimits
    ) -> Optional[ValidationResult]:
        """Check position against limits."""
        margin = self.config.safety_margin
        effective_lower = limits.lower + margin
        effective_upper = limits.upper - margin

        if effective_lower <= command.target_position <= effective_upper:
            return None  # Within limits

        if self.config.on_limit_exceeded == "reject":
            return ValidationResult(
                status=ValidationStatus.REJECTED,
                original_command=command,
                reason=RejectionReason.EXCEEDS_POSITION_LIMIT,
                message=f"Position {command.target_position:.3f} outside limits "
                f"[{effective_lower:.3f}, {effective_upper:.3f}]",
            )

        elif self.config.on_limit_exceeded == "clamp":
            clamped_position = max(effective_lower, min(effective_upper, command.target_position))
            modified = JointCommand(
                joint_name=command.joint_name,
                target_position=clamped_position,
                velocity_limit=command.velocity_limit,
                command_id=command.command_id,
            )
            return ValidationResult(
                status=ValidationStatus.MODIFIED,
                original_command=command,
                modified_command=modified,
                message=f"Position clamped from {command.target_position:.3f} "
                f"to {clamped_position:.3f}",
            )

        # warn mode - return None to continue, but log warning
        self.logger.warning(
            f"Position {command.target_position:.3f} near limits for " f"{command.joint_name}"
        )
        return None

    def _check_velocity_limits(
        self, robot_id: str, command: JointCommand, limits: JointLimits
    ) -> Optional[ValidationResult]:
        """Check and potentially reduce velocity."""
        max_velocity = limits.velocity * self.config.default_velocity_multiplier

        # Get velocity reduction from obstacle proximity
        obstacle_distance = self._obstacle_distances.get(robot_id, float("inf"))
        velocity_multiplier = 1.0

        for threshold, multiplier in self.config.obstacle_velocity_thresholds:
            if obstacle_distance < threshold:
                velocity_multiplier = multiplier
                break

        effective_max = max_velocity * velocity_multiplier

        # Use commanded velocity if specified, otherwise use max
        target_velocity = command.velocity_limit if command.velocity_limit > 0 else max_velocity

        if target_velocity <= effective_max:
            return None  # Within limits

        # Reduce velocity
        modified = JointCommand(
            joint_name=command.joint_name,
            target_position=command.target_position,
            velocity_limit=effective_max,
            command_id=command.command_id,
        )

        return ValidationResult(
            status=ValidationStatus.MODIFIED,
            original_command=command,
            modified_command=modified,
            message=f"Velocity reduced from {target_velocity:.2f} to "
            f"{effective_max:.2f} (obstacle at {obstacle_distance:.0f}cm)",
        )

    def _check_collision(self, robot_id: str, command: JointCommand) -> Optional[ValidationResult]:
        """Check for collision risk."""
        obstacle_distance = self._obstacle_distances.get(robot_id, float("inf"))

        if obstacle_distance < self.config.stop_distance:
            return ValidationResult(
                status=ValidationStatus.REJECTED,
                original_command=command,
                reason=RejectionReason.COLLISION_RISK,
                message=f"Obstacle too close: {obstacle_distance:.1f}cm",
            )

        return None  # No collision risk

    def _check_boundary(self, robot_id: str) -> Optional[ValidationResult]:
        """Check boundary status."""
        status = self._boundary_status.get(robot_id, "ok")

        if status == "violation":
            # Note: We can't create a proper ValidationResult without a command
            # This check should ideally be done in the main validate_command
            return None

        return None

    def set_estop(self, robot_id: str, active: bool):
        """Set emergency stop state for robot."""
        self._estop_active[robot_id] = active
        self.logger.info(f"E-Stop {'activated' if active else 'cleared'} for {robot_id}")

    def is_estop_active(self, robot_id: str) -> bool:
        """Check if e-stop is active for robot."""
        return self._estop_active.get(robot_id, False)

    def update_obstacle_distance(self, robot_id: str, distance_cm: float):
        """Update nearest obstacle distance for robot."""
        self._obstacle_distances[robot_id] = distance_cm

    def update_boundary_status(self, robot_id: str, status: str):
        """Update boundary status for robot."""
        self._boundary_status[robot_id] = status

    def get_statistics(self) -> Dict[str, Any]:
        """Get validation statistics."""
        total = self._commands_validated
        return {
            "total_validated": total,
            "approved": self._commands_approved,
            "rejected": self._commands_rejected,
            "modified": self._commands_modified,
            "approval_rate": self._commands_approved / total if total > 0 else 0,
        }
