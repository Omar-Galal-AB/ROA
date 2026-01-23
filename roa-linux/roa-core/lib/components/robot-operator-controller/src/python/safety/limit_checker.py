"""
Limit Checker - Joint limit validation for ROC safety system.

Provides:
- Joint position limit checking
- Joint velocity limit checking
- Safety margin enforcement
- Per-robot limit tracking from FTI
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple


class LimitStatus(Enum):
    """Result of limit check."""

    OK = auto()  # Within limits
    WARNING = auto()  # Near limit
    CLAMPED = auto()  # Value was clamped
    EXCEEDED = auto()  # Exceeds limits
    UNKNOWN_JOINT = auto()  # Joint not found


@dataclass
class JointLimits:
    """Complete limits for a joint."""

    name: str
    joint_type: str = "revolute"  # revolute or prismatic

    # Position limits
    position_lower: float = -3.14159
    position_upper: float = 3.14159

    # Velocity limit
    max_velocity: float = 2.0

    # Effort/torque limit
    max_effort: float = 100.0

    # UE5 mapping
    ue5_constraint_name: str = ""

    @property
    def position_range(self) -> float:
        """Get total position range."""
        return self.position_upper - self.position_lower

    def contains_position(self, position: float, margin: float = 0.0) -> bool:
        """Check if position is within limits (with optional margin)."""
        lower = self.position_lower + margin
        upper = self.position_upper - margin
        return lower <= position <= upper

    def clamp_position(self, position: float, margin: float = 0.0) -> float:
        """Clamp position to limits."""
        lower = self.position_lower + margin
        upper = self.position_upper - margin
        return max(lower, min(upper, position))

    def distance_to_limit(self, position: float) -> Tuple[float, str]:
        """
        Get distance to nearest limit.

        Returns:
            Tuple of (distance, limit_name) where limit_name is 'lower' or 'upper'.
        """
        to_lower = position - self.position_lower
        to_upper = self.position_upper - position

        if to_lower < to_upper:
            return (to_lower, "lower")
        else:
            return (to_upper, "upper")

    @classmethod
    def from_fti(cls, joint_data: Dict[str, Any]) -> "JointLimits":
        """Create from FTI joint specification."""
        limits_data = joint_data.get("limits", {})

        return cls(
            name=joint_data.get("name", "unknown"),
            joint_type=joint_data.get("type", "revolute"),
            position_lower=limits_data.get("lower", -3.14159),
            position_upper=limits_data.get("upper", 3.14159),
            max_velocity=limits_data.get("velocity", 2.0),
            max_effort=limits_data.get("effort", 100.0),
            ue5_constraint_name=joint_data.get("ue5_constraint_name", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "type": self.joint_type,
            "position_lower": self.position_lower,
            "position_upper": self.position_upper,
            "max_velocity": self.max_velocity,
            "max_effort": self.max_effort,
            "ue5_constraint_name": self.ue5_constraint_name,
        }


@dataclass
class LimitCheckResult:
    """Result of a limit check operation."""

    status: LimitStatus
    joint_name: str
    original_value: float
    final_value: float
    message: str = ""
    distance_to_limit: float = float("inf")
    limit_name: str = ""  # 'lower' or 'upper'

    @property
    def ok(self) -> bool:
        """Check if value is OK (not exceeded)."""
        return self.status in (LimitStatus.OK, LimitStatus.WARNING, LimitStatus.CLAMPED)

    @property
    def modified(self) -> bool:
        """Check if value was modified."""
        return self.status == LimitStatus.CLAMPED

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status.name,
            "joint_name": self.joint_name,
            "original_value": self.original_value,
            "final_value": self.final_value,
            "message": self.message,
            "distance_to_limit": self.distance_to_limit,
            "limit_name": self.limit_name,
        }


@dataclass
class LimitCheckerConfig:
    """Configuration for LimitChecker."""

    # Safety margin from physical limits (radians/meters)
    safety_margin: float = 0.05

    # Warning threshold (distance from limit to trigger warning)
    warning_threshold: float = 0.1

    # Velocity safety multiplier
    velocity_multiplier: float = 0.9

    # Behavior on limit exceeded
    clamp_on_exceed: bool = True

    # Log limit violations
    log_violations: bool = True


class LimitChecker:
    """
    Validates joint positions and velocities against limits.

    Maintains per-robot limit data from FTI and provides
    limit checking for commands before execution.
    """

    def __init__(self, config: Optional[LimitCheckerConfig] = None):
        """
        Initialize limit checker.

        Args:
            config: Checker configuration.
        """
        self.config = config or LimitCheckerConfig()
        self.logger = logging.getLogger(__name__)

        # Per-robot, per-joint limits
        self._limits: Dict[str, Dict[str, JointLimits]] = {}

        # Statistics
        self._checks_performed = 0
        self._warnings_issued = 0
        self._clamps_performed = 0
        self._violations_detected = 0

    def register_robot_limits(self, robot_id: str, fti_spec: Dict[str, Any]):
        """
        Register joint limits for a robot from FTI specification.

        Args:
            robot_id: Robot identifier.
            fti_spec: FTI robot specification.
        """
        joints_data = fti_spec.get("joints", [])

        robot_limits: Dict[str, JointLimits] = {}
        for joint_data in joints_data:
            limits = JointLimits.from_fti(joint_data)
            robot_limits[limits.name] = limits

        self._limits[robot_id] = robot_limits
        self.logger.info(f"Registered limits for {robot_id}: {len(robot_limits)} joints")

    def unregister_robot(self, robot_id: str):
        """Remove limits for a robot."""
        if robot_id in self._limits:
            del self._limits[robot_id]
            self.logger.info(f"Unregistered limits for {robot_id}")

    def get_limits(self, robot_id: str, joint_name: str) -> Optional[JointLimits]:
        """
        Get limits for a specific joint.

        Args:
            robot_id: Robot identifier.
            joint_name: Joint name.

        Returns:
            JointLimits or None if not found.
        """
        robot_limits = self._limits.get(robot_id, {})
        return robot_limits.get(joint_name)

    def get_robot_limits(self, robot_id: str) -> Dict[str, JointLimits]:
        """Get all limits for a robot."""
        return self._limits.get(robot_id, {})

    def check_position(self, robot_id: str, joint_name: str, position: float) -> LimitCheckResult:
        """
        Check if a position is within limits.

        Args:
            robot_id: Robot identifier.
            joint_name: Joint name.
            position: Target position to check.

        Returns:
            LimitCheckResult with status and any modifications.
        """
        self._checks_performed += 1

        # Get limits
        limits = self.get_limits(robot_id, joint_name)
        if limits is None:
            return LimitCheckResult(
                status=LimitStatus.UNKNOWN_JOINT,
                joint_name=joint_name,
                original_value=position,
                final_value=position,
                message=f"No limits found for joint {joint_name}",
            )

        margin = self.config.safety_margin
        distance, limit_name = limits.distance_to_limit(position)

        # Check if within limits (with margin)
        if limits.contains_position(position, margin):
            # Check if near warning threshold
            if distance < self.config.warning_threshold:
                self._warnings_issued += 1
                return LimitCheckResult(
                    status=LimitStatus.WARNING,
                    joint_name=joint_name,
                    original_value=position,
                    final_value=position,
                    message=f"Near {limit_name} limit ({distance:.3f} away)",
                    distance_to_limit=distance,
                    limit_name=limit_name,
                )

            return LimitCheckResult(
                status=LimitStatus.OK,
                joint_name=joint_name,
                original_value=position,
                final_value=position,
                distance_to_limit=distance,
                limit_name=limit_name,
            )

        # Position exceeds limits
        if self.config.clamp_on_exceed:
            clamped = limits.clamp_position(position, margin)
            self._clamps_performed += 1

            if self.config.log_violations:
                self.logger.warning(
                    f"Position clamped for {joint_name}: " f"{position:.3f} -> {clamped:.3f}"
                )

            return LimitCheckResult(
                status=LimitStatus.CLAMPED,
                joint_name=joint_name,
                original_value=position,
                final_value=clamped,
                message=f"Position clamped from {position:.3f} to {clamped:.3f}",
                distance_to_limit=0.0,
                limit_name=limit_name,
            )

        # Reject without clamping
        self._violations_detected += 1

        if self.config.log_violations:
            self.logger.error(f"Position limit exceeded for {joint_name}: {position:.3f}")

        return LimitCheckResult(
            status=LimitStatus.EXCEEDED,
            joint_name=joint_name,
            original_value=position,
            final_value=position,
            message=f"Position {position:.3f} exceeds {limit_name} limit",
            distance_to_limit=distance,
            limit_name=limit_name,
        )

    def check_velocity(
        self,
        robot_id: str,
        joint_name: str,
        velocity: float,
        reduction_multiplier: float = 1.0,
    ) -> LimitCheckResult:
        """
        Check if a velocity is within limits.

        Args:
            robot_id: Robot identifier.
            joint_name: Joint name.
            velocity: Target velocity to check.
            reduction_multiplier: Additional reduction factor (e.g., from obstacle proximity).

        Returns:
            LimitCheckResult with status and any modifications.
        """
        self._checks_performed += 1

        limits = self.get_limits(robot_id, joint_name)
        if limits is None:
            return LimitCheckResult(
                status=LimitStatus.UNKNOWN_JOINT,
                joint_name=joint_name,
                original_value=velocity,
                final_value=velocity,
                message=f"No limits found for joint {joint_name}",
            )

        # Calculate effective max velocity
        effective_max = limits.max_velocity * self.config.velocity_multiplier * reduction_multiplier

        if velocity <= effective_max:
            return LimitCheckResult(
                status=LimitStatus.OK,
                joint_name=joint_name,
                original_value=velocity,
                final_value=velocity,
                distance_to_limit=effective_max - velocity,
            )

        # Velocity exceeds limit
        if self.config.clamp_on_exceed:
            self._clamps_performed += 1
            return LimitCheckResult(
                status=LimitStatus.CLAMPED,
                joint_name=joint_name,
                original_value=velocity,
                final_value=effective_max,
                message=f"Velocity clamped from {velocity:.2f} to {effective_max:.2f}",
            )

        self._violations_detected += 1
        return LimitCheckResult(
            status=LimitStatus.EXCEEDED,
            joint_name=joint_name,
            original_value=velocity,
            final_value=velocity,
            message=f"Velocity {velocity:.2f} exceeds limit {effective_max:.2f}",
        )

    def check_all_positions(
        self, robot_id: str, positions: Dict[str, float]
    ) -> Dict[str, LimitCheckResult]:
        """
        Check all joint positions at once.

        Args:
            robot_id: Robot identifier.
            positions: Map of joint name to position.

        Returns:
            Map of joint name to check result.
        """
        results = {}
        for joint_name, position in positions.items():
            results[joint_name] = self.check_position(robot_id, joint_name, position)
        return results

    def are_all_within_limits(self, robot_id: str, positions: Dict[str, float]) -> bool:
        """Check if all positions are within limits."""
        results = self.check_all_positions(robot_id, positions)
        return all(result.ok for result in results.values())

    def get_distances_to_limits(
        self, robot_id: str, positions: Dict[str, float]
    ) -> Dict[str, Tuple[float, str]]:
        """
        Get distance to nearest limit for each joint.

        Returns:
            Map of joint name to (distance, limit_name).
        """
        distances = {}
        robot_limits = self._limits.get(robot_id, {})

        for joint_name, position in positions.items():
            limits = robot_limits.get(joint_name)
            if limits:
                distances[joint_name] = limits.distance_to_limit(position)

        return distances

    def get_joint_at_limit(
        self, robot_id: str, positions: Dict[str, float], threshold: float = 0.05
    ) -> List[str]:
        """
        Get joints that are at or near their limits.

        Args:
            robot_id: Robot identifier.
            positions: Current positions.
            threshold: Distance threshold for "at limit".

        Returns:
            List of joint names at limit.
        """
        at_limit = []
        distances = self.get_distances_to_limits(robot_id, positions)

        for joint_name, (distance, _) in distances.items():
            if distance < threshold:
                at_limit.append(joint_name)

        return at_limit

    def get_statistics(self) -> Dict[str, Any]:
        """Get limit checker statistics."""
        return {
            "checks_performed": self._checks_performed,
            "warnings_issued": self._warnings_issued,
            "clamps_performed": self._clamps_performed,
            "violations_detected": self._violations_detected,
            "robots_tracked": len(self._limits),
            "total_joints": sum(len(j) for j in self._limits.values()),
        }

    def reset_statistics(self):
        """Reset statistics counters."""
        self._checks_performed = 0
        self._warnings_issued = 0
        self._clamps_performed = 0
        self._violations_detected = 0
