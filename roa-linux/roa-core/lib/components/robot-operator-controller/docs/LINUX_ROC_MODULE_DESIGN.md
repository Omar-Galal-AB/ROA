# Linux ROC Module Design

## Overview

This document defines the Python module architecture for the Linux-side ROC component. The Linux side handles safety validation, path planning, ADM task execution, and ROS2 integration.

**Version**: 1.0  
**Date**: 2026-01-13  
**Status**: Design Phase (NOT IMPLEMENTED)

---

## Module Structure

```
robot-operator-controller/src/python/
├── roc_ros2_node.py           # Main ROS2 node (EXISTING - needs enhancement)
├── integration_handlers.py    # FTI/DIMC/COMC handlers (EXISTING - needs enhancement)
├── command_queue.py           # Command queue (EXISTING)
├── input_handler.py           # Input processing (EXISTING)
│
├── ue5_bridge/                # NEW: UE5 IPC communication
│   ├── __init__.py
│   ├── ipc_handler.py         # TCP/IPC message handling
│   ├── message_types.py       # Message definitions
│   └── command_validator.py   # Pre-send validation
│
├── robot_registry/            # NEW: Robot state management
│   ├── __init__.py
│   ├── robot_state.py         # Per-robot state tracking
│   ├── joint_state.py         # Joint state management
│   └── robot_manager.py       # Multi-robot coordination
│
├── control_modes/             # EXISTING - needs enhancement
│   ├── __init__.py
│   ├── rpm_mode.py            # Role Playing Mode
│   ├── adm_mode.py            # Auto Driven Mode
│   └── mode_manager.py        # NEW: Mode switching logic
│
├── safety/                    # EXISTING - needs enhancement
│   ├── __init__.py
│   ├── safety_manager.py      # Main safety coordinator
│   ├── limit_checker.py       # NEW: Joint limit validation
│   ├── collision_checker.py   # NEW: Collision prediction
│   └── evade_controller.py    # NEW: Emergency evasion
│
├── controllers/               # EXISTING
│   ├── __init__.py
│   ├── base_controller.py
│   ├── arm_controller.py
│   ├── gripper_controller.py
│   └── mobile_controller.py
│
└── path_planning/             # EXISTING
    ├── __init__.py
    ├── a_star.py
    └── rrt.py
```

---

## New Modules

### 1. UE5 Bridge - IPC Handler

**Purpose**: Manage TCP communication with UE5 plugin.

```python
# ue5_bridge/ipc_handler.py
"""
UE5 IPC Handler - Manages TCP communication with UE5 ROC Plugin.

Handles:
- Incoming joint commands from UE5 (for safety validation)
- Outgoing approved/rejected responses
- State synchronization
"""

import asyncio
import json
import socket
import threading
from dataclasses import dataclass, asdict
from typing import Dict, Optional, Callable, List
from enum import Enum
import logging


class MessageType(Enum):
    """IPC Message Types"""
    # UE5 -> Linux
    JOINT_COMMAND_REQUEST = "joint_command_request"
    EMERGENCY_STOP = "emergency_stop"
    MODE_CHANGE = "mode_change"
    ROBOT_REGISTERED = "robot_registered"
    HEARTBEAT = "heartbeat"
    
    # Linux -> UE5
    COMMAND_APPROVED = "command_approved"
    COMMAND_REJECTED = "command_rejected"
    STATE_UPDATE = "state_update"
    SAFETY_ALERT = "safety_alert"
    HEARTBEAT_ACK = "heartbeat_ack"


@dataclass
class JointCommand:
    """Joint command from UE5"""
    joint_name: str
    target_position: float
    velocity_limit: float = 0.0
    command_id: str = ""


@dataclass
class CommandResponse:
    """Response to UE5 for joint command"""
    command_id: str
    approved: bool
    joint_name: str
    target_position: float
    reason: str = ""


class UE5IPCHandler:
    """
    Handles IPC communication with UE5 ROC Plugin.
    
    Uses existing ROA dual-port TCP bridge:
    - Port 9876: UE5 -> Linux (receive commands)
    - Port 9877: Linux -> UE5 (send responses)
    """
    
    def __init__(
        self,
        receive_port: int = 9876,
        send_port: int = 9877,
        ue5_host: str = "localhost"
    ):
        self.receive_port = receive_port
        self.send_port = send_port
        self.ue5_host = ue5_host
        
        self.logger = logging.getLogger("ROC.UE5Bridge")
        
        # Callbacks for different message types
        self._callbacks: Dict[MessageType, List[Callable]] = {
            msg_type: [] for msg_type in MessageType
        }
        
        # Connection state
        self._running = False
        self._receive_thread: Optional[threading.Thread] = None
        self._send_socket: Optional[socket.socket] = None
        
        # Message queue for outgoing messages
        self._send_queue: asyncio.Queue = asyncio.Queue()
        
    def register_callback(self, msg_type: MessageType, callback: Callable):
        """Register callback for specific message type"""
        self._callbacks[msg_type].append(callback)
        
    def start(self):
        """Start IPC handler"""
        self._running = True
        self._receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._receive_thread.start()
        self.logger.info(f"UE5 IPC Handler started on ports {self.receive_port}/{self.send_port}")
        
    def stop(self):
        """Stop IPC handler"""
        self._running = False
        if self._receive_thread:
            self._receive_thread.join(timeout=2.0)
        if self._send_socket:
            self._send_socket.close()
        self.logger.info("UE5 IPC Handler stopped")
        
    def send_command_response(self, response: CommandResponse):
        """Send command approval/rejection to UE5"""
        msg = {
            "type": MessageType.COMMAND_APPROVED.value if response.approved else MessageType.COMMAND_REJECTED.value,
            "command_id": response.command_id,
            "joint_name": response.joint_name,
            "target_position": response.target_position,
            "approved": response.approved,
            "reason": response.reason,
            "timestamp": self._get_timestamp()
        }
        self._send_message(msg)
        
    def send_safety_alert(self, robot_id: str, alert_type: str, message: str):
        """Send safety alert to UE5"""
        msg = {
            "type": MessageType.SAFETY_ALERT.value,
            "robot_id": robot_id,
            "alert_type": alert_type,
            "message": message,
            "timestamp": self._get_timestamp()
        }
        self._send_message(msg)
        
    def _receive_loop(self):
        """Main receive loop - runs in separate thread"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('0.0.0.0', self.receive_port))
            sock.listen(1)
            sock.settimeout(1.0)  # Allow periodic check of _running flag
            
            while self._running:
                try:
                    conn, addr = sock.accept()
                    self.logger.info(f"UE5 connected from {addr}")
                    self._handle_connection(conn)
                except socket.timeout:
                    continue
                except Exception as e:
                    self.logger.error(f"Receive error: {e}")
                    
    def _handle_connection(self, conn: socket.socket):
        """Handle incoming connection from UE5"""
        buffer = ""
        conn.settimeout(0.1)
        
        while self._running:
            try:
                data = conn.recv(4096).decode('utf-8')
                if not data:
                    break
                    
                buffer += data
                
                # Process complete JSON messages
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        self._process_message(line.strip())
                        
            except socket.timeout:
                continue
            except Exception as e:
                self.logger.error(f"Connection error: {e}")
                break
                
        conn.close()
        
    def _process_message(self, message: str):
        """Process incoming JSON message"""
        try:
            data = json.loads(message)
            msg_type_str = data.get("type", "")
            
            try:
                msg_type = MessageType(msg_type_str)
            except ValueError:
                self.logger.warning(f"Unknown message type: {msg_type_str}")
                return
                
            # Call registered callbacks
            for callback in self._callbacks[msg_type]:
                try:
                    callback(data)
                except Exception as e:
                    self.logger.error(f"Callback error for {msg_type}: {e}")
                    
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error: {e}")
            
    def _send_message(self, msg: dict):
        """Send message to UE5"""
        try:
            if not self._send_socket:
                self._send_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._send_socket.connect((self.ue5_host, self.send_port))
                
            json_str = json.dumps(msg) + '\n'
            self._send_socket.sendall(json_str.encode('utf-8'))
            
        except Exception as e:
            self.logger.error(f"Send error: {e}")
            self._send_socket = None  # Reset for reconnection
            
    def _get_timestamp(self) -> float:
        """Get current timestamp"""
        import time
        return time.time()
```

---

### 2. Robot Registry - Robot State

**Purpose**: Track state for each registered robot.

```python
# robot_registry/robot_state.py
"""
Robot State - Tracks complete state for a single robot.

Receives data from:
- FTI: Robot specification (joints, capabilities)
- DIMC: Real-time joint positions, obstacles
- UE5: Command execution status
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum
import time


class RobotStatus(Enum):
    """Robot operational status"""
    INITIALIZING = "initializing"
    READY = "ready"
    MOVING = "moving"
    EMERGENCY_STOPPED = "emergency_stopped"
    ERROR = "error"
    DISCONNECTED = "disconnected"


@dataclass
class JointSpec:
    """Joint specification from FTI"""
    name: str
    joint_type: str  # revolute, prismatic, continuous, fixed
    parent_link: str
    child_link: str
    axis: tuple = (0, 0, 1)
    lower_limit: float = -3.14159
    upper_limit: float = 3.14159
    velocity_limit: float = 2.0
    effort_limit: float = 100.0
    ue5_constraint_name: str = ""


@dataclass
class JointState:
    """Current state of a joint"""
    name: str
    position: float = 0.0
    velocity: float = 0.0
    effort: float = 0.0
    target_position: float = 0.0
    is_moving: bool = False
    at_limit: bool = False
    timestamp: float = 0.0


@dataclass
class RobotCapabilities:
    """Robot capabilities from FTI"""
    has_gripper: bool = False
    gripper_joint_name: str = ""
    has_mobile_base: bool = False
    max_payload_kg: float = 5.0
    max_reach_m: float = 1.0


@dataclass
class RobotPose:
    """Robot world pose from DIMC"""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    qx: float = 0.0
    qy: float = 0.0
    qz: float = 0.0
    qw: float = 1.0


class RobotState:
    """
    Complete state tracking for a single robot.
    
    Aggregates data from FTI (spec), DIMC (positions), and ROC commands.
    """
    
    def __init__(self, robot_id: str, robot_name: str):
        self.robot_id = robot_id
        self.robot_name = robot_name
        
        # Status
        self.status = RobotStatus.INITIALIZING
        self.error_message = ""
        
        # Specification (from FTI)
        self.joint_specs: Dict[str, JointSpec] = {}
        self.capabilities = RobotCapabilities()
        self.kinematic_chain: List[str] = []
        
        # Current state (from DIMC)
        self.joint_states: Dict[str, JointState] = {}
        self.pose = RobotPose()
        
        # Safety
        self.nearest_obstacle_distance: float = float('inf')
        self.within_bounds: bool = True
        self.emergency_stop_active: bool = False
        
        # Timing
        self.last_update_time: float = 0.0
        self.registration_time: float = time.time()
        
    def initialize_from_fti_spec(self, fti_data: dict) -> bool:
        """
        Initialize robot from FTI specification.
        
        Args:
            fti_data: Robot specification from FTI
            
        Returns:
            True if initialization successful
        """
        try:
            # Parse joints
            for joint_data in fti_data.get('joints', []):
                spec = JointSpec(
                    name=joint_data['name'],
                    joint_type=joint_data.get('joint_type', 'revolute'),
                    parent_link=joint_data.get('parent_link', ''),
                    child_link=joint_data.get('child_link', ''),
                    axis=tuple(joint_data.get('axis', [0, 0, 1])),
                    lower_limit=joint_data.get('limits', {}).get('lower', -3.14159),
                    upper_limit=joint_data.get('limits', {}).get('upper', 3.14159),
                    velocity_limit=joint_data.get('limits', {}).get('velocity', 2.0),
                    effort_limit=joint_data.get('limits', {}).get('effort', 100.0),
                    ue5_constraint_name=joint_data.get('ue5_constraint_name', f"Constraint_{joint_data['name']}")
                )
                self.joint_specs[spec.name] = spec
                
                # Initialize joint state
                self.joint_states[spec.name] = JointState(name=spec.name)
                
            # Parse capabilities
            caps_data = fti_data.get('capabilities', {})
            self.capabilities = RobotCapabilities(
                has_gripper=caps_data.get('has_gripper', False),
                gripper_joint_name=caps_data.get('gripper_joint_name', ''),
                has_mobile_base=caps_data.get('has_mobile_base', False),
                max_payload_kg=caps_data.get('max_payload_kg', 5.0),
                max_reach_m=caps_data.get('max_reach_m', 1.0)
            )
            
            # Parse kinematic chain
            hierarchy = fti_data.get('control_hierarchy', {})
            self.kinematic_chain = hierarchy.get('kinematic_chain', [])
            
            self.status = RobotStatus.READY
            return True
            
        except Exception as e:
            self.status = RobotStatus.ERROR
            self.error_message = f"FTI initialization failed: {e}"
            return False
            
    def update_from_dimc(self, dimc_data: dict):
        """
        Update state from DIMC spatial data.
        
        Args:
            dimc_data: Spatial data from DIMC
        """
        # Update joint states
        for joint_state_data in dimc_data.get('joint_states', []):
            joint_name = joint_state_data.get('name')
            if joint_name in self.joint_states:
                state = self.joint_states[joint_name]
                state.position = joint_state_data.get('position', state.position)
                state.velocity = joint_state_data.get('velocity', state.velocity)
                state.effort = joint_state_data.get('effort', state.effort)
                state.timestamp = dimc_data.get('timestamp', time.time())
                
                # Check if at limit
                if joint_name in self.joint_specs:
                    spec = self.joint_specs[joint_name]
                    state.at_limit = (
                        state.position <= spec.lower_limit + 0.01 or
                        state.position >= spec.upper_limit - 0.01
                    )
                    
        # Update pose
        pose_data = dimc_data.get('pose', {})
        if pose_data:
            pos = pose_data.get('position', {})
            ori = pose_data.get('orientation', {})
            self.pose = RobotPose(
                x=pos.get('x', 0.0),
                y=pos.get('y', 0.0),
                z=pos.get('z', 0.0),
                qx=ori.get('x', 0.0),
                qy=ori.get('y', 0.0),
                qz=ori.get('z', 0.0),
                qw=ori.get('w', 1.0)
            )
            
        # Update safety info
        safety = dimc_data.get('safety', {})
        self.nearest_obstacle_distance = safety.get('nearest_obstacle_distance', float('inf'))
        self.within_bounds = safety.get('within_bounds', True)
        
        self.last_update_time = time.time()
        
    def get_joint_position(self, joint_name: str) -> Optional[float]:
        """Get current position of a joint"""
        if joint_name in self.joint_states:
            return self.joint_states[joint_name].position
        return None
        
    def get_all_joint_positions(self) -> Dict[str, float]:
        """Get positions of all joints"""
        return {name: state.position for name, state in self.joint_states.items()}
        
    def is_joint_within_limits(self, joint_name: str, target: float) -> bool:
        """Check if target position is within joint limits"""
        if joint_name not in self.joint_specs:
            return False
        spec = self.joint_specs[joint_name]
        return spec.lower_limit <= target <= spec.upper_limit
        
    def get_controllable_joints(self) -> List[str]:
        """Get list of controllable joint names"""
        return [
            name for name, spec in self.joint_specs.items()
            if spec.joint_type != 'fixed'
        ]
        
    def set_emergency_stop(self, active: bool):
        """Set emergency stop state"""
        self.emergency_stop_active = active
        if active:
            self.status = RobotStatus.EMERGENCY_STOPPED
        elif self.status == RobotStatus.EMERGENCY_STOPPED:
            self.status = RobotStatus.READY
```

---

### 3. Robot Registry - Robot Manager

**Purpose**: Manage multiple robots.

```python
# robot_registry/robot_manager.py
"""
Robot Manager - Coordinates multiple robots.

Handles:
- Robot registration from FTI
- State updates from DIMC
- Multi-robot coordination
"""

from typing import Dict, Optional, List, Callable
from .robot_state import RobotState, RobotStatus
import logging
import threading


class RobotManager:
    """
    Central manager for all registered robots.
    
    Thread-safe for multi-robot updates.
    """
    
    def __init__(self):
        self.logger = logging.getLogger("ROC.RobotManager")
        
        # Robot states by ID
        self._robots: Dict[str, RobotState] = {}
        self._lock = threading.RLock()
        
        # Currently selected robot for UI control
        self._selected_robot_id: Optional[str] = None
        
        # Callbacks
        self._on_robot_registered: List[Callable[[str], None]] = []
        self._on_robot_unregistered: List[Callable[[str], None]] = []
        self._on_selection_changed: List[Callable[[str], None]] = []
        
    def register_robot(self, fti_spec: dict) -> bool:
        """
        Register a new robot from FTI specification.
        
        Args:
            fti_spec: Robot specification from FTI
            
        Returns:
            True if registration successful
        """
        robot_id = fti_spec.get('robot_id')
        robot_name = fti_spec.get('robot_name', robot_id)
        
        if not robot_id:
            self.logger.error("Cannot register robot without robot_id")
            return False
            
        with self._lock:
            if robot_id in self._robots:
                self.logger.warning(f"Robot {robot_id} already registered, updating")
                
            robot = RobotState(robot_id, robot_name)
            if robot.initialize_from_fti_spec(fti_spec):
                self._robots[robot_id] = robot
                
                # Auto-select if first robot
                if self._selected_robot_id is None:
                    self._selected_robot_id = robot_id
                    
                self.logger.info(f"Registered robot: {robot_name} ({robot_id}) with {len(robot.joint_specs)} joints")
                
                # Notify callbacks
                for callback in self._on_robot_registered:
                    try:
                        callback(robot_id)
                    except Exception as e:
                        self.logger.error(f"Callback error: {e}")
                        
                return True
            else:
                self.logger.error(f"Failed to register robot {robot_id}: {robot.error_message}")
                return False
                
    def unregister_robot(self, robot_id: str):
        """Remove a robot from the registry"""
        with self._lock:
            if robot_id in self._robots:
                del self._robots[robot_id]
                
                # Update selection if needed
                if self._selected_robot_id == robot_id:
                    self._selected_robot_id = next(iter(self._robots), None)
                    
                self.logger.info(f"Unregistered robot: {robot_id}")
                
                for callback in self._on_robot_unregistered:
                    try:
                        callback(robot_id)
                    except Exception as e:
                        self.logger.error(f"Callback error: {e}")
                        
    def get_robot(self, robot_id: str) -> Optional[RobotState]:
        """Get robot state by ID"""
        with self._lock:
            return self._robots.get(robot_id)
            
    def get_selected_robot(self) -> Optional[RobotState]:
        """Get currently selected robot"""
        with self._lock:
            if self._selected_robot_id:
                return self._robots.get(self._selected_robot_id)
            return None
            
    def set_selected_robot(self, robot_id: str) -> bool:
        """Set the currently selected robot"""
        with self._lock:
            if robot_id in self._robots:
                old_id = self._selected_robot_id
                self._selected_robot_id = robot_id
                
                if old_id != robot_id:
                    for callback in self._on_selection_changed:
                        try:
                            callback(robot_id)
                        except Exception as e:
                            self.logger.error(f"Callback error: {e}")
                            
                return True
            return False
            
    def get_all_robot_ids(self) -> List[str]:
        """Get list of all registered robot IDs"""
        with self._lock:
            return list(self._robots.keys())
            
    def get_robot_count(self) -> int:
        """Get number of registered robots"""
        with self._lock:
            return len(self._robots)
            
    def update_from_dimc(self, robot_id: str, dimc_data: dict):
        """Update robot state from DIMC data"""
        with self._lock:
            robot = self._robots.get(robot_id)
            if robot:
                robot.update_from_dimc(dimc_data)
                
    def emergency_stop_all(self):
        """Trigger emergency stop on all robots"""
        with self._lock:
            for robot in self._robots.values():
                robot.set_emergency_stop(True)
        self.logger.warning("Emergency stop activated for all robots")
        
    def reset_emergency_stop(self, robot_id: str):
        """Reset emergency stop for a robot"""
        with self._lock:
            robot = self._robots.get(robot_id)
            if robot:
                robot.set_emergency_stop(False)
                
    # Callback registration
    def on_robot_registered(self, callback: Callable[[str], None]):
        """Register callback for robot registration"""
        self._on_robot_registered.append(callback)
        
    def on_robot_unregistered(self, callback: Callable[[str], None]):
        """Register callback for robot unregistration"""
        self._on_robot_unregistered.append(callback)
        
    def on_selection_changed(self, callback: Callable[[str], None]):
        """Register callback for selection changes"""
        self._on_selection_changed.append(callback)
```

---

### 4. Safety - Limit Checker

**Purpose**: Validate joint commands against limits.

```python
# safety/limit_checker.py
"""
Limit Checker - Validates joint commands against physical limits.

Checks:
- Position within joint limits
- Velocity within velocity limits
- Effort within effort limits
"""

from dataclasses import dataclass
from typing import Optional, Tuple
from ..robot_registry.robot_state import RobotState, JointSpec


@dataclass
class LimitCheckResult:
    """Result of limit check"""
    valid: bool
    original_target: float
    clamped_target: float
    violation_type: Optional[str] = None
    violation_amount: float = 0.0
    message: str = ""


class LimitChecker:
    """
    Validates joint commands against physical limits.
    
    Provides both hard rejection and soft clamping options.
    """
    
    def __init__(self, safety_margin: float = 0.05):
        """
        Initialize limit checker.
        
        Args:
            safety_margin: Additional margin from limits (radians or meters)
        """
        self.safety_margin = safety_margin
        
    def check_position_limit(
        self,
        joint_spec: JointSpec,
        target_position: float,
        clamp: bool = True
    ) -> LimitCheckResult:
        """
        Check if target position is within limits.
        
        Args:
            joint_spec: Joint specification with limits
            target_position: Desired target position
            clamp: If True, clamp to limits instead of rejecting
            
        Returns:
            LimitCheckResult with validation details
        """
        lower = joint_spec.lower_limit + self.safety_margin
        upper = joint_spec.upper_limit - self.safety_margin
        
        if lower <= target_position <= upper:
            return LimitCheckResult(
                valid=True,
                original_target=target_position,
                clamped_target=target_position
            )
            
        # Determine violation
        if target_position < lower:
            violation_type = "below_lower_limit"
            violation_amount = lower - target_position
            clamped = lower if clamp else target_position
        else:
            violation_type = "above_upper_limit"
            violation_amount = target_position - upper
            clamped = upper if clamp else target_position
            
        return LimitCheckResult(
            valid=clamp,  # Valid if clamping, invalid if not
            original_target=target_position,
            clamped_target=clamped,
            violation_type=violation_type,
            violation_amount=violation_amount,
            message=f"Joint {joint_spec.name}: target {target_position:.4f} {violation_type} by {violation_amount:.4f}"
        )
        
    def check_velocity_limit(
        self,
        joint_spec: JointSpec,
        current_position: float,
        target_position: float,
        time_delta: float
    ) -> LimitCheckResult:
        """
        Check if motion would exceed velocity limits.
        
        Args:
            joint_spec: Joint specification
            current_position: Current position
            target_position: Target position
            time_delta: Time to reach target (seconds)
            
        Returns:
            LimitCheckResult with adjusted velocity if needed
        """
        if time_delta <= 0:
            return LimitCheckResult(
                valid=False,
                original_target=target_position,
                clamped_target=current_position,
                violation_type="invalid_time_delta",
                message="Time delta must be positive"
            )
            
        required_velocity = abs(target_position - current_position) / time_delta
        max_velocity = joint_spec.velocity_limit * 0.9  # 10% safety margin
        
        if required_velocity <= max_velocity:
            return LimitCheckResult(
                valid=True,
                original_target=target_position,
                clamped_target=target_position
            )
            
        # Calculate achievable target in given time
        max_delta = max_velocity * time_delta
        if target_position > current_position:
            clamped_target = current_position + max_delta
        else:
            clamped_target = current_position - max_delta
            
        return LimitCheckResult(
            valid=True,  # Valid but clamped
            original_target=target_position,
            clamped_target=clamped_target,
            violation_type="velocity_limited",
            violation_amount=required_velocity - max_velocity,
            message=f"Velocity limited: requested {required_velocity:.2f}, max {max_velocity:.2f}"
        )
        
    def validate_command(
        self,
        robot: RobotState,
        joint_name: str,
        target_position: float,
        velocity_limit: float = 0.0
    ) -> Tuple[bool, float, str]:
        """
        Validate a joint command against all limits.
        
        Args:
            robot: Robot state
            joint_name: Name of joint
            target_position: Desired target
            velocity_limit: Optional velocity limit (0 = use default)
            
        Returns:
            Tuple of (approved, adjusted_target, message)
        """
        if joint_name not in robot.joint_specs:
            return False, 0.0, f"Unknown joint: {joint_name}"
            
        spec = robot.joint_specs[joint_name]
        
        # Check position limits
        pos_result = self.check_position_limit(spec, target_position, clamp=True)
        if not pos_result.valid:
            return False, pos_result.clamped_target, pos_result.message
            
        # Apply velocity limit if specified
        if velocity_limit > 0 and velocity_limit < spec.velocity_limit:
            spec.velocity_limit = velocity_limit
            
        return True, pos_result.clamped_target, "Command validated"
```

---

### 5. Safety - Command Validator

**Purpose**: Complete command validation pipeline.

```python
# ue5_bridge/command_validator.py
"""
Command Validator - Central validation for UE5 commands.

Orchestrates:
- Limit checking
- Collision checking (via DIMC)
- Safety level enforcement
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
from enum import Enum
import logging

from ..robot_registry.robot_state import RobotState
from ..safety.limit_checker import LimitChecker


class CommandValidationStatus(Enum):
    """Validation result status"""
    APPROVED = "approved"
    APPROVED_MODIFIED = "approved_modified"
    REJECTED_LIMIT = "rejected_limit"
    REJECTED_COLLISION = "rejected_collision"
    REJECTED_EMERGENCY = "rejected_emergency"
    REJECTED_UNKNOWN_JOINT = "rejected_unknown_joint"
    REJECTED_UNKNOWN_ROBOT = "rejected_unknown_robot"


@dataclass
class JointCommandRequest:
    """Incoming joint command request from UE5"""
    command_id: str
    joint_name: str
    target_position: float
    velocity_limit: float = 0.0
    source: str = "rpm"  # rpm or adm


@dataclass
class ValidationResult:
    """Result of command validation"""
    status: CommandValidationStatus
    original_target: float
    approved_target: float
    message: str
    command_id: str
    joint_name: str


class CommandValidator:
    """
    Central command validation service.
    
    All commands from UE5 pass through here before execution approval.
    """
    
    def __init__(self):
        self.logger = logging.getLogger("ROC.CommandValidator")
        self.limit_checker = LimitChecker(safety_margin=0.05)
        
        # Safety thresholds
        self.obstacle_stop_distance = 10.0  # cm - emergency stop
        self.obstacle_slow_distance = 50.0  # cm - reduce speed
        
    def validate_command(
        self,
        robot: RobotState,
        command: JointCommandRequest
    ) -> ValidationResult:
        """
        Validate a single joint command.
        
        Args:
            robot: Robot state (from RobotManager)
            command: Command to validate
            
        Returns:
            ValidationResult with approval status
        """
        # Check emergency stop
        if robot.emergency_stop_active:
            return ValidationResult(
                status=CommandValidationStatus.REJECTED_EMERGENCY,
                original_target=command.target_position,
                approved_target=0.0,
                message="Robot in emergency stop",
                command_id=command.command_id,
                joint_name=command.joint_name
            )
            
        # Check joint exists
        if command.joint_name not in robot.joint_specs:
            return ValidationResult(
                status=CommandValidationStatus.REJECTED_UNKNOWN_JOINT,
                original_target=command.target_position,
                approved_target=0.0,
                message=f"Unknown joint: {command.joint_name}",
                command_id=command.command_id,
                joint_name=command.joint_name
            )
            
        # Check position limits
        approved, adjusted_target, message = self.limit_checker.validate_command(
            robot=robot,
            joint_name=command.joint_name,
            target_position=command.target_position,
            velocity_limit=command.velocity_limit
        )
        
        if not approved:
            return ValidationResult(
                status=CommandValidationStatus.REJECTED_LIMIT,
                original_target=command.target_position,
                approved_target=adjusted_target,
                message=message,
                command_id=command.command_id,
                joint_name=command.joint_name
            )
            
        # Check obstacle distance
        if robot.nearest_obstacle_distance < self.obstacle_stop_distance:
            return ValidationResult(
                status=CommandValidationStatus.REJECTED_COLLISION,
                original_target=command.target_position,
                approved_target=robot.get_joint_position(command.joint_name) or 0.0,
                message=f"Obstacle too close: {robot.nearest_obstacle_distance:.1f}cm",
                command_id=command.command_id,
                joint_name=command.joint_name
            )
            
        # Determine if target was modified
        if abs(adjusted_target - command.target_position) > 0.001:
            status = CommandValidationStatus.APPROVED_MODIFIED
            message = f"Approved with modification: {message}"
        else:
            status = CommandValidationStatus.APPROVED
            message = "Approved"
            
        return ValidationResult(
            status=status,
            original_target=command.target_position,
            approved_target=adjusted_target,
            message=message,
            command_id=command.command_id,
            joint_name=command.joint_name
        )
        
    def validate_batch(
        self,
        robot: RobotState,
        commands: List[JointCommandRequest]
    ) -> List[ValidationResult]:
        """
        Validate a batch of commands.
        
        Args:
            robot: Robot state
            commands: List of commands to validate
            
        Returns:
            List of validation results (same order as input)
        """
        return [self.validate_command(robot, cmd) for cmd in commands]
        
    def is_approved(self, status: CommandValidationStatus) -> bool:
        """Check if status indicates approval"""
        return status in (
            CommandValidationStatus.APPROVED,
            CommandValidationStatus.APPROVED_MODIFIED
        )
```

---

### 6. Mode Manager

**Purpose**: Handle control mode transitions.

```python
# control_modes/mode_manager.py
"""
Mode Manager - Handles transitions between RPM and ADM modes.

Manages:
- Mode switching logic
- State preservation during switches
- Mode-specific behaviors
"""

from enum import Enum
from typing import Optional, Callable, List
import logging


class ControlMode(Enum):
    """Control mode enumeration"""
    RPM = "rpm"  # Role Playing Mode - manual control
    ADM = "adm"  # Auto Driven Mode - autonomous control


class ModeTransitionError(Exception):
    """Raised when mode transition is not allowed"""
    pass


class ModeManager:
    """
    Manages control mode transitions.
    
    Ensures safe transitions between manual (RPM) and autonomous (ADM) modes.
    """
    
    def __init__(self):
        self.logger = logging.getLogger("ROC.ModeManager")
        
        self._current_mode = ControlMode.RPM
        self._transition_in_progress = False
        
        # Callbacks
        self._on_mode_changed: List[Callable[[ControlMode, ControlMode], None]] = []
        self._on_transition_blocked: List[Callable[[str], None]] = []
        
    @property
    def current_mode(self) -> ControlMode:
        """Get current control mode"""
        return self._current_mode
        
    @property
    def is_rpm_mode(self) -> bool:
        """Check if in manual mode"""
        return self._current_mode == ControlMode.RPM
        
    @property
    def is_adm_mode(self) -> bool:
        """Check if in autonomous mode"""
        return self._current_mode == ControlMode.ADM
        
    def can_switch_to(self, new_mode: ControlMode) -> tuple[bool, str]:
        """
        Check if switching to new mode is allowed.
        
        Args:
            new_mode: Target mode
            
        Returns:
            Tuple of (allowed, reason)
        """
        if self._transition_in_progress:
            return False, "Transition already in progress"
            
        if new_mode == self._current_mode:
            return False, "Already in requested mode"
            
        # Mode-specific checks
        if new_mode == ControlMode.ADM:
            # Check if ADM prerequisites are met
            # (e.g., path planning ready, no errors)
            pass
            
        return True, "Transition allowed"
        
    def switch_mode(self, new_mode: ControlMode) -> bool:
        """
        Switch to new control mode.
        
        Args:
            new_mode: Target mode
            
        Returns:
            True if switch successful
        """
        can_switch, reason = self.can_switch_to(new_mode)
        
        if not can_switch:
            self.logger.warning(f"Mode switch blocked: {reason}")
            for callback in self._on_transition_blocked:
                try:
                    callback(reason)
                except Exception as e:
                    self.logger.error(f"Callback error: {e}")
            return False
            
        old_mode = self._current_mode
        self._transition_in_progress = True
        
        try:
            # Perform transition
            self._current_mode = new_mode
            self.logger.info(f"Mode switched: {old_mode.value} -> {new_mode.value}")
            
            # Notify callbacks
            for callback in self._on_mode_changed:
                try:
                    callback(old_mode, new_mode)
                except Exception as e:
                    self.logger.error(f"Callback error: {e}")
                    
            return True
            
        finally:
            self._transition_in_progress = False
            
    def toggle_mode(self) -> ControlMode:
        """Toggle between RPM and ADM modes"""
        new_mode = ControlMode.ADM if self._current_mode == ControlMode.RPM else ControlMode.RPM
        self.switch_mode(new_mode)
        return self._current_mode
        
    def on_mode_changed(self, callback: Callable[[ControlMode, ControlMode], None]):
        """Register callback for mode changes"""
        self._on_mode_changed.append(callback)
        
    def on_transition_blocked(self, callback: Callable[[str], None]):
        """Register callback for blocked transitions"""
        self._on_transition_blocked.append(callback)
```

---

## Module Summary

| Module | Purpose | New/Existing |
|--------|---------|--------------|
| `ue5_bridge/ipc_handler.py` | TCP communication with UE5 | NEW |
| `ue5_bridge/message_types.py` | Message definitions | NEW |
| `ue5_bridge/command_validator.py` | Command validation pipeline | NEW |
| `robot_registry/robot_state.py` | Per-robot state tracking | NEW |
| `robot_registry/joint_state.py` | Joint state management | NEW |
| `robot_registry/robot_manager.py` | Multi-robot coordination | NEW |
| `safety/limit_checker.py` | Joint limit validation | NEW |
| `control_modes/mode_manager.py` | Mode switching logic | NEW |

---

## Integration Points

### With Existing Modules

| Existing Module | Integration |
|----------------|-------------|
| `roc_ros2_node.py` | Uses RobotManager, ModeManager |
| `integration_handlers.py` | Feeds FTI data to RobotManager |
| `safety_manager.py` | Uses LimitChecker, CommandValidator |
| `rpm_mode.py` | Uses ModeManager, IPC handler |
| `adm_mode.py` | Uses ModeManager, IPC handler |

### With External Components

| Component | Data Flow |
|-----------|-----------|
| FTI | Robot specs → RobotManager |
| DIMC | Joint states → RobotState |
| UE5 | Commands → IPC Handler → CommandValidator |
| COMC | Multi-robot coordination (future) |

---

## Status

**Current Status**: Design Complete, NOT IMPLEMENTED  
**Next Step**: Wait for implementation approval
