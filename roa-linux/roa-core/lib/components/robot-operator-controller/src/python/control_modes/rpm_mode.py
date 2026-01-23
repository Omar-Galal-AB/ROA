"""
RPM Mode - Role Playing Mode Implementation

Direct manual control mode with real-time keyboard/mouse input.
Provides precision control for manual robot operation.

Author: ROA Development Team
Date: 2025-11-16
"""

from typing import Dict, Any, Optional
from enum import Enum


class RPMMode:
    """
    Role Playing Mode - Direct manual control
    
    Features:
    - Real-time keyboard/mouse input
    - Slider-based control interface
    - Immediate command execution
    - Visual feedback
    - Safety monitoring
    """
    
    def __init__(self):
        """Initialize RPM mode"""
        self.active = False
        self.robot_id = None
        
        # Current input state
        self.movement_input = {'forward': 0.0, 'strafe': 0.0, 'rotation': 0.0}
        self.gripper_arm_input = {'vertical': 0.0, 'horizontal': 0.0}
        self.gripper_input = {'close': False, 'open': False}
        
        # Control parameters
        self.speed_multiplier = 1.0
        self.sensitivity = 1.0
        
    def activate(self, robot_id: str):
        """
        Activate RPM mode for a robot
        
        Args:
            robot_id: Robot to control
        """
        self.active = True
        self.robot_id = robot_id
        self._reset_inputs()
    
    def deactivate(self):
        """Deactivate RPM mode"""
        self.active = False
        self.robot_id = None
        self._reset_inputs()
    
    def _reset_inputs(self):
        """Reset all input states to zero"""
        self.movement_input = {'forward': 0.0, 'strafe': 0.0, 'rotation': 0.0}
        self.gripper_arm_input = {'vertical': 0.0, 'horizontal': 0.0}
        self.gripper_input = {'close': False, 'open': False}
    
    def process_keyboard_input(self, key: str, pressed: bool):
        """
        Process keyboard input
        
        Args:
            key: Key identifier
            pressed: True if pressed, False if released
        """
        if not self.active:
            return
        
        # Movement keys (WASD)
        if key == 'W':
            self.movement_input['forward'] = 1.0 if pressed else 0.0
        elif key == 'S':
            self.movement_input['forward'] = -1.0 if pressed else 0.0
        elif key == 'A':
            self.movement_input['strafe'] = -1.0 if pressed else 0.0
        elif key == 'D':
            self.movement_input['strafe'] = 1.0 if pressed else 0.0
        
        # Gripper arm keys (Arrows)
        elif key == 'Up':
            self.gripper_arm_input['vertical'] = 1.0 if pressed else 0.0
        elif key == 'Down':
            self.gripper_arm_input['vertical'] = -1.0 if pressed else 0.0
        elif key == 'Left':
            self.gripper_arm_input['horizontal'] = -1.0 if pressed else 0.0
        elif key == 'Right':
            self.gripper_arm_input['horizontal'] = 1.0 if pressed else 0.0
        
        # Gripper operations
        elif key == 'C' and pressed:
            self.gripper_input['close'] = True
        elif key == 'V' and pressed:
            self.gripper_input['open'] = True
    
    def process_mouse_input(self, button: str, x: float, y: float, pressed: bool):
        """
        Process mouse input
        
        Args:
            button: Mouse button ('left', 'right', 'middle')
            x: Mouse X position
            y: Mouse Y position
            pressed: True if pressed, False if released
        """
        if not self.active:
            return
        
        # TODO: Implement mouse control
        # - Left click: Select target
        # - Right click: 6-DOF gripper freedom
        # - Middle click: Pan camera
        pass
    
    def compute_control_commands(self) -> Dict[str, Any]:
        """
        Compute control commands from current inputs
        
        Returns:
            Dictionary of control commands
        """
        if not self.active:
            return {}
        
        # Apply speed multiplier
        movement_scaled = {
            k: v * self.speed_multiplier
            for k, v in self.movement_input.items()
        }
        
        gripper_arm_scaled = {
            k: v * self.speed_multiplier
            for k, v in self.gripper_arm_input.items()
        }
        
        return {
            'robot_id': self.robot_id,
            'movement': movement_scaled,
            'gripper_arm': gripper_arm_scaled,
            'gripper': self.gripper_input.copy()
        }
    
    def set_speed_multiplier(self, multiplier: float):
        """
        Set speed multiplier (from safety level)
        
        Args:
            multiplier: Speed multiplier (0.0-2.0)
        """
        self.speed_multiplier = max(0.0, min(2.0, multiplier))
    
    def emergency_stop(self):
        """Emergency stop - zero all inputs"""
        self._reset_inputs()
