"""
Arm Controller - Control for robotic manipulator arms

Handles position, velocity, and force control for multi-DOF arms.
Supports articulated, SCARA, delta, and other arm types.

Author: ROA Development Team
Date: 2025-11-16
"""

from typing import Dict, Any, List
import numpy as np
from .base_controller import BaseController, ControlType


class ArmController(BaseController):
    """
    Controller for robotic manipulator arms
    
    Supports:
    - Multi-DOF joint control
    - Forward/inverse kinematics
    - Joint limit enforcement
    - Velocity and acceleration limits
    """
    
    def __init__(self, controller_id: str, part_name: str, num_joints: int = 6):
        """
        Initialize arm controller
        
        Args:
            controller_id: Unique identifier
            part_name: Name of arm part
            num_joints: Number of joints/DOF
        """
        super().__init__(controller_id, part_name)
        
        self.num_joints = num_joints
        
        # Joint states
        self.joint_positions = np.zeros(num_joints)
        self.joint_velocities = np.zeros(num_joints)
        self.joint_targets = np.zeros(num_joints)
        
        # Joint limits (radians or meters)
        self.joint_limits_min = np.full(num_joints, -np.pi)
        self.joint_limits_max = np.full(num_joints, np.pi)
        
        # Velocity limits (rad/s or m/s)
        self.velocity_limits = np.full(num_joints, 1.0)
        
        # Acceleration limits (rad/s² or m/s²)
        self.acceleration_limits = np.full(num_joints, 2.0)
        
        # Support position, velocity, and torque control
        self.supported_control_types = [
            ControlType.POSITION,
            ControlType.VELOCITY,
            ControlType.TORQUE
        ]
    
    def configure_from_specs(self, joint_specs: List[Dict[str, Any]]):
        """
        Configure from robot specifications (from FTI)
        
        Args:
            joint_specs: List of joint specifications
        """
        self.num_joints = len(joint_specs)
        self.joint_positions = np.zeros(self.num_joints)
        self.joint_velocities = np.zeros(self.num_joints)
        self.joint_targets = np.zeros(self.num_joints)
        
        # Extract limits from specs
        self.joint_limits_min = np.array([
            spec.get('limits', [-np.pi, np.pi])[0]
            for spec in joint_specs
        ])
        self.joint_limits_max = np.array([
            spec.get('limits', [-np.pi, np.pi])[1]
            for spec in joint_specs
        ])
        
        # Set velocity limits (default or from specs)
        self.velocity_limits = np.array([
            spec.get('max_velocity', 1.0)
            for spec in joint_specs
        ])
        
        # Set acceleration limits
        self.acceleration_limits = np.array([
            spec.get('max_acceleration', 2.0)
            for spec in joint_specs
        ])
    
    def set_joint_targets(self, targets: np.ndarray):
        """
        Set target positions for all joints
        
        Args:
            targets: Target joint positions
        """
        if len(targets) != self.num_joints:
            return False
        
        # Apply limits with safety margin
        safe_min = self.joint_limits_min + (self.joint_limits_max - self.joint_limits_min) * self.safety_margin
        safe_max = self.joint_limits_max - (self.joint_limits_max - self.joint_limits_min) * self.safety_margin
        
        self.joint_targets = np.clip(targets, safe_min, safe_max)
        return True
    
    def update_joint_states(self, positions: np.ndarray, velocities: np.ndarray = None):
        """
        Update current joint states from feedback
        
        Args:
            positions: Current joint positions
            velocities: Current joint velocities (optional)
        """
        if len(positions) == self.num_joints:
            self.joint_positions = positions
        
        if velocities is not None and len(velocities) == self.num_joints:
            self.joint_velocities = velocities
    
    def compute_command(self) -> Dict[str, Any]:
        """
        Compute control command for arm
        
        Returns:
            Control command with joint commands
        """
        if self.control_type == ControlType.POSITION:
            return {
                'type': 'position',
                'joint_commands': self.joint_targets * self.speed_multiplier,
                'num_joints': self.num_joints
            }
        
        elif self.control_type == ControlType.VELOCITY:
            # Compute velocities toward target
            error = self.joint_targets - self.joint_positions
            velocities = np.clip(
                error * 2.0,  # Proportional gain
                -self.velocity_limits * self.speed_multiplier,
                self.velocity_limits * self.speed_multiplier
            )
            return {
                'type': 'velocity',
                'joint_commands': velocities,
                'num_joints': self.num_joints
            }
        
        elif self.control_type == ControlType.TORQUE:
            # Simple PD controller
            error = self.joint_targets - self.joint_positions
            d_error = -self.joint_velocities
            
            kp = 10.0  # Proportional gain
            kd = 2.0   # Derivative gain
            
            torques = kp * error + kd * d_error
            return {
                'type': 'torque',
                'joint_commands': torques * self.speed_multiplier,
                'num_joints': self.num_joints
            }
        
        return {}
    
    def validate_capabilities(self, robot_spec: Dict[str, Any]) -> bool:
        """
        Validate compatibility with robot specs
        
        Args:
            robot_spec: Robot specification from FTI
            
        Returns:
            True if compatible
        """
        # Check if robot has arm joints
        joints = robot_spec.get('joints', [])
        arm_joints = [j for j in joints if j.get('type') in ['revolute', 'prismatic']]
        
        return len(arm_joints) > 0
    
    def get_joint_info(self) -> Dict[str, Any]:
        """Get detailed joint information"""
        return {
            'num_joints': self.num_joints,
            'positions': self.joint_positions.tolist(),
            'velocities': self.joint_velocities.tolist(),
            'targets': self.joint_targets.tolist(),
            'limits_min': self.joint_limits_min.tolist(),
            'limits_max': self.joint_limits_max.tolist(),
            'velocity_limits': self.velocity_limits.tolist()
        }
