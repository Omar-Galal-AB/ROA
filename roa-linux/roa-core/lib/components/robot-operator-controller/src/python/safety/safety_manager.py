"""
Safety Manager - Central Safety Management for ROC

Manages all safety-related functionality including:
- Safety level enforcement
- Collision detection coordination
- Boundary checking
- Emergency stop handling

Author: ROA Development Team
Date: 2025-11-16
"""

from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class SafetyLevel(Enum):
    """Safety levels"""

    FRAGILE = "Fragile"
    STANDARD = "Standard"
    ROBUST = "Robust"


class SafetyViolation(Enum):
    """Types of safety violations"""

    COLLISION = "collision"
    BOUNDARY = "boundary"
    LIMIT_EXCEEDED = "limit_exceeded"
    TIMEOUT = "timeout"


class SafetyManager:
    """
    Central safety management system

    Responsibilities:
    - Enforce safety levels
    - Monitor for violations
    - Trigger emergency stops
    - Coordinate with collision detection
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize safety manager

        Args:
            config_path: Path to safety_levels.yaml configuration
        """
        self.current_level = SafetyLevel.STANDARD
        self.safety_config = self._load_safety_config(config_path)

        # Violation tracking
        self.violations = []
        self.violation_history = []
        self.max_history = 100

        # Emergency stop state
        self.emergency_stop_active = False

        # Safety parameters (loaded from config)
        self.speed_multiplier = 1.0
        self.safety_margin = 0.005  # meters
        self.auto_stop_distance = 0.03  # meters
        self.warning_distance = 0.08  # meters

        self._apply_safety_level(SafetyLevel.STANDARD)

    def _load_safety_config(self, config_path: Optional[Path]) -> Dict:
        """Load safety configuration from YAML"""
        if config_path is None:
            config_path = (
                Path(__file__).parent.parent.parent.parent / "Config" / "safety_levels.yaml"
            )

        if config_path.exists():
            with open(config_path, "r") as f:
                return yaml.safe_load(f)
        else:
            return self._default_safety_config()

    def _default_safety_config(self) -> Dict:
        """Default safety configuration"""
        return {
            "safety_levels": {
                "Fragile": {
                    "speed_multiplier": 0.6,
                    "safety_margin": 0.01,
                    "auto_stop_distance": 0.05,
                    "warning_distance": 0.10,
                },
                "Standard": {
                    "speed_multiplier": 1.0,
                    "safety_margin": 0.005,
                    "auto_stop_distance": 0.03,
                    "warning_distance": 0.08,
                },
                "Robust": {
                    "speed_multiplier": 1.2,
                    "safety_margin": 0.002,
                    "auto_stop_distance": 0.02,
                    "warning_distance": 0.05,
                },
            }
        }

    def set_safety_level(self, level: SafetyLevel) -> bool:
        """
        Set safety level

        Args:
            level: Safety level to set

        Returns:
            True if set successfully
        """
        if self.emergency_stop_active:
            return False

        self.current_level = level
        self._apply_safety_level(level)
        return True

    def _apply_safety_level(self, level: SafetyLevel):
        """Apply safety level parameters"""
        config = self.safety_config.get("safety_levels", {}).get(level.value, {})

        self.speed_multiplier = config.get("speed_multiplier", 1.0)
        self.safety_margin = config.get("safety_margin", 0.005)
        self.auto_stop_distance = config.get("auto_stop_distance", 0.03)
        self.warning_distance = config.get("warning_distance", 0.08)

    def check_collision(self, robot_id: str, obstacle_distance: float) -> bool:
        """
        Check if obstacle is within safety distance

        Args:
            robot_id: Robot to check
            obstacle_distance: Distance to nearest obstacle (meters)

        Returns:
            True if collision imminent (auto-stop triggered)
        """
        if obstacle_distance < self.auto_stop_distance:
            # Collision imminent - trigger auto-stop
            self._report_violation(
                SafetyViolation.COLLISION,
                robot_id,
                f"Obstacle at {obstacle_distance:.3f}m (limit: {self.auto_stop_distance:.3f}m)",
            )
            return True

        return False

    def check_boundary(
        self, robot_id: str, position: List[float], boundaries: Dict[str, List[float]]
    ) -> bool:
        """
        Check if robot is within workspace boundaries

        Args:
            robot_id: Robot to check
            position: Current position [x, y, z]
            boundaries: Workspace boundaries {'min': [x,y,z], 'max': [x,y,z]}

        Returns:
            True if boundary violated
        """
        min_bounds = boundaries.get("min", [-float("inf")] * 3)
        max_bounds = boundaries.get("max", [float("inf")] * 3)

        for i, (pos, min_b, max_b) in enumerate(zip(position, min_bounds, max_bounds)):
            if pos < min_b or pos > max_b:
                self._report_violation(
                    SafetyViolation.BOUNDARY,
                    robot_id,
                    f"Position {['x','y','z'][i]}={pos:.3f} outside bounds [{min_b:.3f}, {max_b:.3f}]",
                )
                return True

        return False

    def check_limits(
        self,
        robot_id: str,
        joint_id: str,
        value: float,
        min_limit: float,
        max_limit: float,
    ) -> bool:
        """
        Check if joint value is within limits

        Args:
            robot_id: Robot to check
            joint_id: Joint identifier
            value: Current joint value
            min_limit: Minimum allowed value
            max_limit: Maximum allowed value

        Returns:
            True if limit violated
        """
        if value < min_limit or value > max_limit:
            self._report_violation(
                SafetyViolation.LIMIT_EXCEEDED,
                robot_id,
                f"Joint {joint_id} value {value:.3f} outside limits [{min_limit:.3f}, {max_limit:.3f}]",
            )
            return True

        return False

    def should_show_warning(self, obstacle_distance: float) -> bool:
        """
        Check if warning should be shown for obstacle distance

        Args:
            obstacle_distance: Distance to nearest obstacle

        Returns:
            True if warning should be shown
        """
        return obstacle_distance < self.warning_distance

    def trigger_emergency_stop(self, reason: str):
        """
        Trigger emergency stop

        Args:
            reason: Reason for emergency stop
        """
        self.emergency_stop_active = True
        self._report_violation(SafetyViolation.COLLISION, "all", f"Emergency stop: {reason}")

    def release_emergency_stop(self):
        """Release emergency stop"""
        self.emergency_stop_active = False
        self.violations.clear()

    def _report_violation(self, violation_type: SafetyViolation, robot_id: str, details: str):
        """
        Report safety violation

        Args:
            violation_type: Type of violation
            robot_id: Affected robot
            details: Violation details
        """
        violation = {
            "type": violation_type,
            "robot_id": robot_id,
            "details": details,
            "level": self.current_level.value,
        }

        self.violations.append(violation)
        self.violation_history.append(violation)

        # Trim history
        if len(self.violation_history) > self.max_history:
            self.violation_history = self.violation_history[-self.max_history :]

    def get_active_violations(self) -> List[Dict]:
        """Get list of active violations"""
        return self.violations.copy()

    def clear_violations(self):
        """Clear active violations"""
        self.violations.clear()

    def get_safety_parameters(self) -> Dict[str, Any]:
        """
        Get current safety parameters

        Returns:
            Dictionary of safety parameters
        """
        return {
            "level": self.current_level.value,
            "speed_multiplier": self.speed_multiplier,
            "safety_margin": self.safety_margin,
            "auto_stop_distance": self.auto_stop_distance,
            "warning_distance": self.warning_distance,
            "emergency_stop_active": self.emergency_stop_active,
            "active_violations": len(self.violations),
        }
