"""
Mobile Controller - Control for mobile robot bases

Handles holonomic and non-holonomic mobile platforms.
Supports wheeled, tracked, and omnidirectional bases.

Author: ROA Development Team
Date: 2025-11-16
"""

from typing import Any, Dict

import numpy as np

from .base_controller import BaseController, ControlType


class MobileController(BaseController):
    """
    Controller for mobile robot bases

    Supports:
    - Differential drive (2-wheel)
    - Omnidirectional (mecanum, omni-wheel)
    - Ackermann steering
    - Tracked vehicles
    """

    def __init__(self, controller_id: str, part_name: str, mobility_type: str = "differential"):
        """
        Initialize mobile controller

        Args:
            controller_id: Unique identifier
            part_name: Name of mobile base
            mobility_type: Type of mobility (differential, omnidirectional, ackermann, tracked)
        """
        super().__init__(controller_id, part_name)

        self.mobility_type = mobility_type

        # Current state
        self.linear_velocity = np.array([0.0, 0.0, 0.0])  # x, y, z
        self.angular_velocity = np.array([0.0, 0.0, 0.0])  # roll, pitch, yaw

        # Target velocities
        self.target_linear = np.array([0.0, 0.0, 0.0])
        self.target_angular = np.array([0.0, 0.0, 0.0])

        # Velocity limits
        self.max_linear_velocity = 1.0  # m/s
        self.max_angular_velocity = 1.0  # rad/s

        # Acceleration limits
        self.max_linear_acceleration = 0.5  # m/s²
        self.max_angular_acceleration = 0.5  # rad/s²

        # Holonomic capability
        self.is_holonomic = mobility_type in ["omnidirectional", "mecanum"]

        # Support velocity control primarily
        self.supported_control_types = [ControlType.VELOCITY]

    def configure_from_specs(self, base_spec: Dict[str, Any]):
        """
        Configure from base specifications

        Args:
            base_spec: Base specification from FTI
        """
        self.mobility_type = base_spec.get("mobility_type", "differential")
        self.is_holonomic = base_spec.get("holonomic", False)

        self.max_linear_velocity = base_spec.get("max_linear_velocity", 1.0)
        self.max_angular_velocity = base_spec.get("max_angular_velocity", 1.0)

        self.max_linear_acceleration = base_spec.get("max_linear_acceleration", 0.5)
        self.max_angular_acceleration = base_spec.get("max_angular_acceleration", 0.5)

    def set_velocity(self, linear_x: float = 0.0, linear_y: float = 0.0, angular_z: float = 0.0):
        """
        Set target velocity

        Args:
            linear_x: Forward/backward velocity (m/s)
            linear_y: Left/right velocity (m/s, holonomic only)
            angular_z: Rotational velocity (rad/s)
        """
        # Apply limits
        self.target_linear[0] = np.clip(
            linear_x, -self.max_linear_velocity, self.max_linear_velocity
        )

        # Lateral movement only for holonomic platforms
        if self.is_holonomic:
            self.target_linear[1] = np.clip(
                linear_y, -self.max_linear_velocity, self.max_linear_velocity
            )
        else:
            self.target_linear[1] = 0.0

        self.target_angular[2] = np.clip(
            angular_z, -self.max_angular_velocity, self.max_angular_velocity
        )

    def set_velocity_from_direction(self, direction: Dict[str, float], speed: float = 0.5):
        """
        Set velocity from direction vector

        Args:
            direction: Direction vector {x, y, z}
            speed: Desired speed (0-1)
        """
        # Normalize direction
        dx = direction.get("x", 0.0)
        dy = direction.get("y", 0.0)
        magnitude = np.sqrt(dx**2 + dy**2)

        if magnitude > 0:
            dx /= magnitude
            dy /= magnitude

        # Scale by speed
        linear_x = dx * speed * self.max_linear_velocity
        linear_y = dy * speed * self.max_linear_velocity if self.is_holonomic else 0.0

        self.set_velocity(linear_x, linear_y, 0.0)

    def stop(self):
        """Stop the mobile base"""
        self.target_linear = np.zeros(3)
        self.target_angular = np.zeros(3)

    def update_velocity_state(self, linear_velocity: np.ndarray, angular_velocity: np.ndarray):
        """
        Update current velocity from feedback

        Args:
            linear_velocity: Current linear velocity [x, y, z]
            angular_velocity: Current angular velocity [roll, pitch, yaw]
        """
        self.linear_velocity = linear_velocity
        self.angular_velocity = angular_velocity

        # Update base controller current value (use forward velocity magnitude)
        self.current_value = np.linalg.norm(linear_velocity)

    def compute_command(self) -> Dict[str, Any]:
        """
        Compute control command for mobile base

        Returns:
            Control command with velocities
        """
        # Apply safety multiplier
        cmd_linear = self.target_linear * self.speed_multiplier
        cmd_angular = self.target_angular * self.speed_multiplier

        if self.mobility_type == "differential":
            # Convert to wheel velocities for differential drive
            wheel_base = 0.5  # meters (should come from specs)
            left_vel = cmd_linear[0] - (cmd_angular[2] * wheel_base / 2.0)
            right_vel = cmd_linear[0] + (cmd_angular[2] * wheel_base / 2.0)

            return {
                "type": "differential",
                "left_wheel_velocity": left_vel,
                "right_wheel_velocity": right_vel,
            }

        elif self.mobility_type in ["omnidirectional", "mecanum"]:
            return {
                "type": "omnidirectional",
                "linear_x": cmd_linear[0],
                "linear_y": cmd_linear[1],
                "angular_z": cmd_angular[2],
            }

        elif self.mobility_type == "ackermann":
            # Simplified Ackermann steering
            return {
                "type": "ackermann",
                "speed": cmd_linear[0],
                "steering_angle": cmd_angular[2],  # Simplified
            }

        else:
            # Generic velocity command
            return {
                "type": "velocity",
                "linear": cmd_linear.tolist(),
                "angular": cmd_angular.tolist(),
            }

    def validate_capabilities(self, robot_spec: Dict[str, Any]) -> bool:
        """
        Validate compatibility with robot specs

        Args:
            robot_spec: Robot specification from FTI

        Returns:
            True if compatible
        """
        # Check if robot has mobile base capability
        capabilities = robot_spec.get("capabilities", {})
        return capabilities.get("has_mobile_base", False)

    def get_mobile_info(self) -> Dict[str, Any]:
        """Get detailed mobile base information"""
        return {
            "mobility_type": self.mobility_type,
            "is_holonomic": self.is_holonomic,
            "linear_velocity": self.linear_velocity.tolist(),
            "angular_velocity": self.angular_velocity.tolist(),
            "target_linear": self.target_linear.tolist(),
            "target_angular": self.target_angular.tolist(),
            "max_linear_velocity": self.max_linear_velocity,
            "max_angular_velocity": self.max_angular_velocity,
        }
