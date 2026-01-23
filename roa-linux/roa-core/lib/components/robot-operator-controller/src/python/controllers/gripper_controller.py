"""
Gripper Controller - Control for end-effector grippers

Handles gripper open/close, force control, and object manipulation.
Supports parallel jaw, vacuum, and multi-finger grippers.

Author: ROA Development Team
Date: 2025-11-16
"""

from typing import Dict, Any
from .base_controller import BaseController, ControlType


class GripperController(BaseController):
    """
    Controller for end-effector grippers
    
    Supports:
    - Open/close control
    - Force/torque control
    - Position control (for multi-DOF grippers)
    - Object detection
    """
    
    def __init__(self, controller_id: str, part_name: str):
        """
        Initialize gripper controller
        
        Args:
            controller_id: Unique identifier
            part_name: Name of gripper part
        """
        super().__init__(controller_id, part_name)
        
        # Gripper state
        self.gripper_position = 0.0  # 0.0 = fully open, 1.0 = fully closed
        self.gripper_force = 0.0     # Current grip force
        self.target_position = 0.0
        self.target_force = 0.5      # Target grip force (0-1)
        
        # Gripper type
        self.gripper_type = 'parallel_jaw'  # parallel_jaw, vacuum, multi_finger
        
        # Limits
        self.max_force = 100.0  # Newtons
        self.min_position = 0.0
        self.max_position = 0.1  # meters (fully open to fully closed)
        
        # Object detection
        self.object_detected = False
        
        # Support position and torque (force) control
        self.supported_control_types = [
            ControlType.POSITION,
            ControlType.TORQUE  # Used for force control
        ]
    
    def configure_from_specs(self, gripper_spec: Dict[str, Any]):
        """
        Configure from gripper specifications
        
        Args:
            gripper_spec: Gripper specification from FTI
        """
        self.gripper_type = gripper_spec.get('type', 'parallel_jaw')
        self.max_force = gripper_spec.get('max_force', 100.0)
        self.max_position = gripper_spec.get('max_opening', 0.1)
        
        # Set limits
        self.min_limit = 0.0
        self.max_limit = 1.0  # Normalized (0 = open, 1 = closed)
    
    def open_gripper(self, speed: float = 1.0):
        """
        Open gripper
        
        Args:
            speed: Opening speed (0-1)
        """
        self.target_position = 0.0
        self.target_force = 0.0
    
    def close_gripper(self, force: float = 0.5):
        """
        Close gripper with specified force
        
        Args:
            force: Grip force (0-1)
        """
        self.target_position = 1.0
        self.target_force = max(0.0, min(1.0, force))
    
    def set_position(self, position: float):
        """
        Set gripper to specific position
        
        Args:
            position: Target position (0-1, 0=open, 1=closed)
        """
        self.target_position = max(0.0, min(1.0, position))
    
    def set_force(self, force: float):
        """
        Set grip force
        
        Args:
            force: Target force (0-1)
        """
        self.target_force = max(0.0, min(1.0, force))
    
    def update_gripper_state(
        self,
        position: float,
        force: float,
        object_detected: bool = False
    ):
        """
        Update gripper state from feedback
        
        Args:
            position: Current position (0-1)
            force: Current force (0-1)
            object_detected: Whether object is detected
        """
        self.gripper_position = position
        self.gripper_force = force
        self.object_detected = object_detected
        
        # Update base controller current value
        self.current_value = position
    
    def compute_command(self) -> Dict[str, Any]:
        """
        Compute control command for gripper
        
        Returns:
            Control command for gripper
        """
        if self.control_type == ControlType.POSITION:
            return {
                'type': 'gripper_position',
                'position': self.target_position,
                'speed': self.speed_multiplier
            }
        
        elif self.control_type == ControlType.TORQUE:
            # Force control
            return {
                'type': 'gripper_force',
                'force': self.target_force * self.max_force * self.speed_multiplier,
                'max_force': self.max_force
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
        # Check if robot has gripper capability
        capabilities = robot_spec.get('capabilities', {})
        return capabilities.get('has_gripper', False)
    
    def is_object_grasped(self) -> bool:
        """Check if object is currently grasped"""
        return self.object_detected and self.gripper_force > 0.1
    
    def get_gripper_info(self) -> Dict[str, Any]:
        """Get detailed gripper information"""
        return {
            'gripper_type': self.gripper_type,
            'position': self.gripper_position,
            'target_position': self.target_position,
            'force': self.gripper_force,
            'target_force': self.target_force,
            'max_force': self.max_force,
            'object_detected': self.object_detected,
            'object_grasped': self.is_object_grasped()
        }
