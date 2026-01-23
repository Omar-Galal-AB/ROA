"""
Input Handler Module

Captures keyboard and mouse input for RPM mode robot control.
Provides context-sensitive input mapping and state management.

Author: ROA Development Team
Date: 2025-11-16
"""

from typing import Dict, Set, Optional, Callable
from enum import Enum
import time


class InputMode(Enum):
    """Input context mode"""
    RPM = "rpm"
    ADM = "adm"
    MENU = "menu"


class InputHandler:
    """
    Input handler for keyboard and mouse
    
    Features:
    - Context-sensitive input mapping
    - Input state tracking
    - Latency monitoring (<10ms keyboard, <15ms mouse target)
    - Conflict detection
    - Custom keybinding support
    
    Note: This is a framework. Actual keyboard/mouse capture would use:
    - pynput library for cross-platform input
    - pygame for game-style input
    - ROS2 joy/teleop for joystick support
    """
    
    def __init__(self, polling_rate: int = 120):
        """
        Initialize input handler
        
        Args:
            polling_rate: Input polling rate in Hz (default 120)
        """
        self.polling_rate = polling_rate
        self.polling_interval = 1.0 / polling_rate
        
        # Current mode
        self.mode = InputMode.RPM
        
        # Input state
        self.keys_pressed: Set[str] = set()
        self.keys_just_pressed: Set[str] = set()
        self.keys_just_released: Set[str] = set()
        
        # Mouse state
        self.mouse_position = (0, 0)
        self.mouse_delta = (0, 0)
        self.mouse_buttons_pressed: Set[int] = set()  # 0=left, 1=right, 2=middle
        self.mouse_wheel_delta = 0
        
        # Input callbacks
        self.key_callbacks: Dict[str, Callable] = {}
        self.mouse_callbacks: Dict[str, Callable] = {}
        
        # Latency tracking
        self.last_input_time = 0
        self.input_latencies = []
        self.max_latency_samples = 100
        
        # Keybindings (default mappings)
        self.keybindings = self._load_default_keybindings()
        
        # Last update time
        self.last_update_time = time.time()
    
    def _load_default_keybindings(self) -> Dict[str, Dict[str, str]]:
        """Load default keybinding configuration"""
        return {
            'rpm': {
                # Movement (WASD)
                'w': 'move_forward',
                'a': 'move_left',
                's': 'move_backward',
                'd': 'move_right',
                
                # Gripper arm (Arrows)
                'up': 'arm_up',
                'down': 'arm_down',
                'left': 'arm_left',
                'right': 'arm_right',
                
                # Gripper operations
                'c': 'gripper_close',
                'v': 'gripper_open',
                'e': 'arm_extend',
                'q': 'arm_retract',
                'y': 'arm_rotate_left',
                'u': 'arm_rotate_right',
                
                # Quick actions
                'r': 'return_origin',
                't': 'toggle_mode',
                'space': 'emergency_stop',
                'tab': 'switch_robot',
                
                # Safety levels
                '1': 'safety_fragile',
                '2': 'safety_standard',
                '3': 'safety_robust',
                
                # View controls
                'f': 'focus_robot',
                'esc': 'deselect',
                
                # UI toggles
                'f1': 'toggle_shortcuts',
                'f2': 'toggle_transparency',
                'f3': 'cycle_position',
                'f12': 'toggle_help'
            },
            'adm': {
                # Camera movement
                'w': 'camera_forward',
                'a': 'camera_left',
                's': 'camera_backward',
                'd': 'camera_right',
                
                # Robot selection (Arrows)
                'up': 'select_up',
                'down': 'select_down',
                'left': 'select_left',
                'right': 'select_right',
                
                # Command hotkeys
                'm': 'command_move',
                'p': 'command_pick',
                'l': 'command_place',
                'f': 'command_follow',
                'g': 'command_goto',
                'r': 'command_return',
                'h': 'command_halt',
                
                # Multi-select modifiers
                'shift': 'multi_select_add',
                'ctrl': 'multi_select_toggle',
                'alt': 'multi_select_remove',
                
                # Other
                'space': 'emergency_stop',
                'esc': 'cancel_command',
                'enter': 'confirm_command',
                'tab': 'cycle_selection'
            }
        }
    
    def update(self):
        """
        Update input state (call at polling rate)
        
        This would be called in the main control loop to:
        1. Poll input devices
        2. Update state
        3. Trigger callbacks
        4. Measure latency
        """
        current_time = time.time()
        dt = current_time - self.last_update_time
        
        # Update input state (placeholder - actual implementation would use input library)
        self._update_keyboard_state()
        self._update_mouse_state()
        
        # Process input events
        self._process_input_events()
        
        # Measure latency
        if self.last_input_time > 0:
            latency = (current_time - self.last_input_time) * 1000  # ms
            self.input_latencies.append(latency)
            if len(self.input_latencies) > self.max_latency_samples:
                self.input_latencies.pop(0)
        
        # Clear just pressed/released
        self.keys_just_pressed.clear()
        self.keys_just_released.clear()
        
        self.last_update_time = current_time
    
    def _update_keyboard_state(self):
        """Update keyboard state (placeholder for actual implementation)"""
        # In real implementation, would use:
        # - pynput.keyboard.Listener
        # - pygame.key.get_pressed()
        # - ROS2 keyboard node
        pass
    
    def _update_mouse_state(self):
        """Update mouse state (placeholder for actual implementation)"""
        # In real implementation, would use:
        # - pynput.mouse.Listener
        # - pygame.mouse.get_pos(), get_pressed()
        # - ROS2 mouse node
        pass
    
    def _process_input_events(self):
        """Process input events and trigger callbacks"""
        mode_bindings = self.keybindings.get(self.mode.value, {})
        
        # Process just pressed keys
        for key in self.keys_just_pressed:
            if key in mode_bindings:
                action = mode_bindings[key]
                if action in self.key_callbacks:
                    self.key_callbacks[action]()
    
    def register_key_callback(self, action: str, callback: Callable):
        """
        Register callback for key action
        
        Args:
            action: Action name (e.g., 'move_forward')
            callback: Function to call when action triggered
        """
        self.key_callbacks[action] = callback
    
    def register_mouse_callback(self, event: str, callback: Callable):
        """
        Register callback for mouse event
        
        Args:
            event: Event name (e.g., 'left_click', 'right_click', 'wheel')
            callback: Function to call when event occurs
        """
        self.mouse_callbacks[event] = callback
    
    def is_key_pressed(self, key: str) -> bool:
        """Check if key is currently pressed"""
        return key in self.keys_pressed
    
    def is_key_just_pressed(self, key: str) -> bool:
        """Check if key was just pressed this frame"""
        return key in self.keys_just_pressed
    
    def is_key_just_released(self, key: str) -> bool:
        """Check if key was just released this frame"""
        return key in self.keys_just_released
    
    def is_action_active(self, action: str) -> bool:
        """
        Check if action is currently active
        
        Args:
            action: Action name (e.g., 'move_forward')
            
        Returns:
            True if key bound to action is pressed
        """
        mode_bindings = self.keybindings.get(self.mode.value, {})
        
        for key, bound_action in mode_bindings.items():
            if bound_action == action and key in self.keys_pressed:
                return True
        
        return False
    
    def get_movement_vector(self) -> Dict[str, float]:
        """
        Get movement vector from WASD keys (RPM mode)
        
        Returns:
            Movement vector {x, y} normalized
        """
        x = 0.0
        y = 0.0
        
        if self.mode == InputMode.RPM:
            if self.is_action_active('move_forward'):
                y += 1.0
            if self.is_action_active('move_backward'):
                y -= 1.0
            if self.is_action_active('move_left'):
                x -= 1.0
            if self.is_action_active('move_right'):
                x += 1.0
        
        # Normalize diagonal movement
        magnitude = (x**2 + y**2)**0.5
        if magnitude > 1.0:
            x /= magnitude
            y /= magnitude
        
        return {'x': x, 'y': y}
    
    def get_arm_control(self) -> Dict[str, float]:
        """
        Get arm control from arrow keys (RPM mode)
        
        Returns:
            Arm movement {x, y} normalized
        """
        x = 0.0
        y = 0.0
        
        if self.mode == InputMode.RPM:
            if self.is_action_active('arm_up'):
                y += 1.0
            if self.is_action_active('arm_down'):
                y -= 1.0
            if self.is_action_active('arm_left'):
                x -= 1.0
            if self.is_action_active('arm_right'):
                x += 1.0
        
        return {'x': x, 'y': y}
    
    def get_gripper_state(self) -> Optional[str]:
        """
        Get gripper state from keys
        
        Returns:
            'open', 'close', or None
        """
        if self.is_action_active('gripper_close'):
            return 'close'
        elif self.is_action_active('gripper_open'):
            return 'open'
        return None
    
    def set_mode(self, mode: InputMode):
        """
        Set input mode
        
        Args:
            mode: Input mode (RPM, ADM, MENU)
        """
        self.mode = mode
        # Clear input state on mode change
        self.keys_pressed.clear()
        self.keys_just_pressed.clear()
        self.keys_just_released.clear()
    
    def get_latency_stats(self) -> Dict[str, float]:
        """Get input latency statistics"""
        if not self.input_latencies:
            return {
                'avg_ms': 0.0,
                'max_ms': 0.0,
                'min_ms': 0.0,
                'current_ms': 0.0
            }
        
        return {
            'avg_ms': sum(self.input_latencies) / len(self.input_latencies),
            'max_ms': max(self.input_latencies),
            'min_ms': min(self.input_latencies),
            'current_ms': self.input_latencies[-1] if self.input_latencies else 0.0
        }
    
    def load_custom_keybindings(self, profile_name: str):
        """
        Load custom keybinding profile
        
        Args:
            profile_name: Name of profile to load
        """
        # In real implementation, would load from config file
        # For now, just a placeholder
        pass
    
    def detect_conflicts(self) -> List[str]:
        """
        Detect keybinding conflicts
        
        Returns:
            List of conflict descriptions
        """
        conflicts = []
        
        for mode_name, bindings in self.keybindings.items():
            # Check for duplicate key assignments
            seen_keys = {}
            for key, action in bindings.items():
                if key in seen_keys:
                    conflicts.append(
                        f"{mode_name.upper()}: Key '{key}' assigned to both "
                        f"'{seen_keys[key]}' and '{action}'"
                    )
                else:
                    seen_keys[key] = action
        
        return conflicts
