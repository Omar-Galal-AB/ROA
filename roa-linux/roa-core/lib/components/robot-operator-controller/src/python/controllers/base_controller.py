"""
Base Controller - Abstract Base Class for All Controllers

Provides common functionality for all robot part controllers.
All specific controllers (arm, gripper, mobile, etc.) inherit from this.

Author: ROA Development Team
Date: 2025-11-16
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np


class ControlType(Enum):
    """Types of control available"""

    POSITION = "position"
    VELOCITY = "velocity"
    TORQUE = "torque"
    EFFORT = "effort"


class ControllerState(Enum):
    """Controller states"""

    DISABLED = "disabled"
    ENABLED = "enabled"
    ACTIVE = "active"
    ERROR = "error"


class BaseController(ABC):
    """
    Abstract base class for all robot part controllers.

    Provides common functionality:
    - State management
    - Control type switching
    - Safety boundary checking
    - Command validation
    - Status reporting
    """

    def __init__(self, controller_id: str, part_name: str):
        """
        Initialize base controller

        Args:
            controller_id: Unique identifier for this controller
            part_name: Name of the robot part being controlled
        """
        self.controller_id = controller_id
        self.part_name = part_name
        self.state = ControllerState.DISABLED

        # Control parameters
        self.control_type = ControlType.POSITION
        self.current_value = 0.0
        self.target_value = 0.0

        # Limits and boundaries
        self.min_limit = -1.0
        self.max_limit = 1.0
        self.safety_margin = 0.05  # 5% margin by default

        # Safety settings
        self.safety_level = "Standard"
        self.speed_multiplier = 1.0
        self.collision_detected = False

        # Capabilities
        self.supported_control_types = [ControlType.POSITION]
        self.capabilities = {}

    def enable(self) -> bool:
        """
        Enable the controller

        Returns:
            True if successfully enabled
        """
        if self.state == ControllerState.ERROR:
            return False

        self.state = ControllerState.ENABLED
        return True

    def disable(self):
        """Disable the controller"""
        self.state = ControllerState.DISABLED
        self.target_value = self.current_value

    def set_control_type(self, control_type: ControlType) -> bool:
        """
        Set the control type

        Args:
            control_type: Desired control type

        Returns:
            True if control type is supported and set successfully
        """
        if control_type not in self.supported_control_types:
            return False

        self.control_type = control_type
        return True

    def set_limits(self, min_limit: float, max_limit: float):
        """
        Set control limits

        Args:
            min_limit: Minimum allowed value
            max_limit: Maximum allowed value
        """
        self.min_limit = min_limit
        self.max_limit = max_limit

    def set_safety_level(self, level: str):
        """
        Set safety level

        Args:
            level: Safety level ("Fragile", "Standard", "Robust")
        """
        self.safety_level = level

        # Adjust parameters based on safety level
        if level == "Fragile":
            self.speed_multiplier = 0.6
            self.safety_margin = 0.10  # 10% margin
        elif level == "Standard":
            self.speed_multiplier = 1.0
            self.safety_margin = 0.05  # 5% margin
        elif level == "Robust":
            self.speed_multiplier = 1.2
            self.safety_margin = 0.02  # 2% margin

    def set_target(self, value: float) -> bool:
        """
        Set target value with safety checking

        Args:
            value: Target value

        Returns:
            True if target is valid and set
        """
        # Apply safety margin
        safe_min = self.min_limit + (self.max_limit - self.min_limit) * self.safety_margin
        safe_max = self.max_limit - (self.max_limit - self.min_limit) * self.safety_margin

        # Clamp to safe limits
        clamped_value = np.clip(value, safe_min, safe_max)

        if clamped_value != value:
            # Value was clamped - may indicate safety issue
            return False

        self.target_value = clamped_value
        self.state = ControllerState.ACTIVE
        return True

    def update_current_value(self, value: float):
        """
        Update current value from sensor feedback

        Args:
            value: Current measured value
        """
        self.current_value = value

    def check_safety(self) -> bool:
        """
        Check if current state is safe

        Returns:
            True if safe, False if safety violation
        """
        # Check limits
        if self.current_value < self.min_limit or self.current_value > self.max_limit:
            return False

        # Check collision
        if self.collision_detected:
            return False

        return True

    def set_collision_detected(self, detected: bool):
        """
        Set collision detection status

        Args:
            detected: True if collision detected
        """
        self.collision_detected = detected

        if detected:
            # Stop movement on collision
            self.target_value = self.current_value

    def get_status(self) -> Dict[str, Any]:
        """
        Get controller status

        Returns:
            Dictionary with controller status information
        """
        return {
            "controller_id": self.controller_id,
            "part_name": self.part_name,
            "state": self.state.value,
            "control_type": self.control_type.value,
            "current_value": self.current_value,
            "target_value": self.target_value,
            "limits": {"min": self.min_limit, "max": self.max_limit},
            "safety": {
                "level": self.safety_level,
                "margin": self.safety_margin,
                "speed_multiplier": self.speed_multiplier,
                "collision_detected": self.collision_detected,
            },
        }

    @abstractmethod
    def compute_command(self) -> Any:
        """
        Compute control command for this timestep

        Must be implemented by specific controller classes.

        Returns:
            Control command specific to the controller type
        """
        pass

    @abstractmethod
    def validate_capabilities(self, robot_spec: Dict[str, Any]) -> bool:
        """
        Validate that this controller is compatible with robot specs

        Args:
            robot_spec: Robot specification from FTI

        Returns:
            True if compatible
        """
        pass

    def emergency_stop(self):
        """Emergency stop - immediately halt motion"""
        self.target_value = self.current_value
        self.state = ControllerState.ENABLED

    def reset(self):
        """Reset controller to initial state"""
        self.state = ControllerState.DISABLED
        self.target_value = 0.0
        self.current_value = 0.0
        self.collision_detected = False
