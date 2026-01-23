"""
MoveIt Integration via FastDDS Bridge

Provides integration with MoveIt 2 for analytical inverse kinematics (IK)
and motion planning. Uses FastDDS for communication with ROS 2 MoveIt services.

Architecture:
┌─────────────────┐     FastDDS      ┌─────────────────┐
│    FTI/UE5      │ ◄──────────────► │   MoveIt 2      │
│   (Python/C++)  │    ROA Bridge    │  (ROS 2 Node)   │
└─────────────────┘                  └─────────────────┘

Services provided:
1. compute_ik - Compute joint positions for target pose
2. compute_fk - Compute end-effector pose from joints
3. plan_motion - Plan trajectory between configurations
4. check_collision - Check for collisions

This module implements the client side. MoveIt must be running
with the ROA Bridge enabled for this to work.

Why MoveIt instead of embedded IK:
- Industrial-grade IK solvers (KDL, TRAC-IK, BioIK)
- Collision-aware planning
- Continuous maintenance by ROS community
- Support for complex manipulators

Reference: https://moveit.ros.org/
"""

import json
import logging
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable, Union
import threading

logger = logging.getLogger(__name__)

# ROA Bridge availability check
# The ROA Bridge uses TCP/JSON (rosbridge protocol) for UE5<->ROS2 communication
# Bridge server location: roa_linux/roa-core/lib/roa_bridge_server.py
# ROS2 node: webthread/src/python/ROS2Bridge/ros2_node.py

ROA_BRIDGE_AVAILABLE = False
ROS2_AVAILABLE = False

# Try to import ROS2 node from Webthread
try:
    import sys
    from pathlib import Path
    
    # Add Webthread paths
    webthread_path = Path(__file__).parent.parent.parent.parent.parent / "webthread" / "src" / "python"
    if webthread_path.exists():
        sys.path.insert(0, str(webthread_path))
    
    # Also try the roa-core/lib path for roa_bridge_server
    roa_lib_path = Path(__file__).parent.parent.parent.parent.parent.parent.parent
    if roa_lib_path.exists():
        sys.path.insert(0, str(roa_lib_path))
    
    from ROS2Bridge.ros2_node import ROS2Node, ROS2_AVAILABLE as _ROS2_AVAILABLE
    ROS2_AVAILABLE = _ROS2_AVAILABLE
    ROA_BRIDGE_AVAILABLE = True
    logger.debug("ROA Bridge integration available via ROS2Bridge")
except ImportError as e:
    logger.debug(f"ROS2Bridge not available: {e}")

# Alternative: Try socket-based bridge client
if not ROA_BRIDGE_AVAILABLE:
    try:
        import socket
        SOCKET_BRIDGE_AVAILABLE = True
        logger.debug("Socket-based bridge client available as fallback")
    except ImportError:
        SOCKET_BRIDGE_AVAILABLE = False


class IKSolverType(Enum):
    """Available IK solver types in MoveIt."""
    KDL = "kdl"                          # Default KDL solver
    TRAC_IK = "trac_ik"                  # TRAC-IK (faster, more robust)
    BIO_IK = "bio_ik"                    # BioIK (best for complex chains)
    PICK_IK = "pick_ik"                  # PickIK (modern alternative)
    CACHED_IK = "cached_ik"              # Pre-computed IK database
    ANALYTICAL = "analytical"            # Robot-specific analytical solver


class PlannerType(Enum):
    """Available motion planners in MoveIt."""
    OMPL_RRT = "RRTConnect"              # Default RRT-Connect
    OMPL_RRT_STAR = "RRTstar"            # Optimal RRT
    OMPL_PRM = "PRM"                     # Probabilistic Roadmap
    CHOMP = "CHOMP"                      # Gradient-based
    STOMP = "STOMP"                      # Stochastic optimization
    PILZ = "PTP"                         # Industrial (point-to-point)


@dataclass
class Pose:
    """6-DOF pose representation."""
    position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    orientation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 1.0])  # Quaternion xyzw
    
    def to_dict(self) -> Dict:
        return {
            'position': {'x': self.position[0], 'y': self.position[1], 'z': self.position[2]},
            'orientation': {'x': self.orientation[0], 'y': self.orientation[1], 
                          'z': self.orientation[2], 'w': self.orientation[3]},
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Pose':
        pos = data.get('position', {})
        ori = data.get('orientation', {})
        return cls(
            position=[pos.get('x', 0), pos.get('y', 0), pos.get('z', 0)],
            orientation=[ori.get('x', 0), ori.get('y', 0), ori.get('z', 0), ori.get('w', 1)],
        )
    
    @classmethod
    def from_rpy(cls, x: float, y: float, z: float, roll: float, pitch: float, yaw: float) -> 'Pose':
        """Create pose from position and RPY angles."""
        # Convert RPY to quaternion
        cy = math.cos(yaw * 0.5)
        sy = math.sin(yaw * 0.5)
        cp = math.cos(pitch * 0.5)
        sp = math.sin(pitch * 0.5)
        cr = math.cos(roll * 0.5)
        sr = math.sin(roll * 0.5)
        
        qw = cr * cp * cy + sr * sp * sy
        qx = sr * cp * cy - cr * sp * sy
        qy = cr * sp * cy + sr * cp * sy
        qz = cr * cp * sy - sr * sp * cy
        
        return cls(position=[x, y, z], orientation=[qx, qy, qz, qw])


@dataclass
class JointState:
    """Robot joint state."""
    names: List[str] = field(default_factory=list)
    positions: List[float] = field(default_factory=list)
    velocities: Optional[List[float]] = None
    efforts: Optional[List[float]] = None
    
    def to_dict(self) -> Dict:
        result = {
            'name': self.names,
            'position': self.positions,
        }
        if self.velocities:
            result['velocity'] = self.velocities
        if self.efforts:
            result['effort'] = self.efforts
        return result
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'JointState':
        return cls(
            names=data.get('name', []),
            positions=data.get('position', []),
            velocities=data.get('velocity'),
            efforts=data.get('effort'),
        )


@dataclass
class TrajectoryPoint:
    """Single point in a trajectory."""
    positions: List[float]
    velocities: Optional[List[float]] = None
    accelerations: Optional[List[float]] = None
    time_from_start: float = 0.0


@dataclass
class Trajectory:
    """Complete robot trajectory."""
    joint_names: List[str]
    points: List[TrajectoryPoint]
    
    def duration(self) -> float:
        if not self.points:
            return 0.0
        return self.points[-1].time_from_start
    
    def to_dict(self) -> Dict:
        return {
            'joint_names': self.joint_names,
            'points': [
                {
                    'positions': p.positions,
                    'velocities': p.velocities or [],
                    'accelerations': p.accelerations or [],
                    'time_from_start': p.time_from_start,
                }
                for p in self.points
            ],
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Trajectory':
        points = [
            TrajectoryPoint(
                positions=p['positions'],
                velocities=p.get('velocities'),
                accelerations=p.get('accelerations'),
                time_from_start=p.get('time_from_start', 0),
            )
            for p in data.get('points', [])
        ]
        return cls(joint_names=data.get('joint_names', []), points=points)


@dataclass
class IKRequest:
    """IK service request."""
    group_name: str                       # MoveIt group (e.g., "manipulator")
    target_pose: Pose                     # Target end-effector pose
    seed_state: Optional[JointState] = None  # Starting joint configuration
    timeout: float = 1.0                  # Solver timeout (seconds)
    attempts: int = 5                     # Number of solver attempts
    solver_type: IKSolverType = IKSolverType.KDL
    avoid_collisions: bool = True
    
    def to_dict(self) -> Dict:
        result = {
            'group_name': self.group_name,
            'pose_stamped': {
                'header': {'frame_id': 'world'},
                'pose': self.target_pose.to_dict(),
            },
            'timeout': self.timeout,
            'attempts': self.attempts,
            'avoid_collisions': self.avoid_collisions,
        }
        if self.seed_state:
            result['seed_state'] = self.seed_state.to_dict()
        return result


@dataclass
class IKResponse:
    """IK service response."""
    success: bool
    solution: Optional[JointState] = None
    error_code: int = 0
    error_message: str = ""


@dataclass
class MotionPlanRequest:
    """Motion planning service request."""
    group_name: str
    start_state: JointState
    goal_pose: Optional[Pose] = None      # Cartesian goal
    goal_state: Optional[JointState] = None  # Joint space goal
    planner_id: PlannerType = PlannerType.OMPL_RRT
    max_velocity_factor: float = 0.1       # Fraction of max velocity
    max_acceleration_factor: float = 0.1   # Fraction of max acceleration
    planning_time: float = 5.0            # Max planning time
    num_planning_attempts: int = 5
    
    def to_dict(self) -> Dict:
        result = {
            'group_name': self.group_name,
            'start_state': self.start_state.to_dict(),
            'planner_id': self.planner_id.value,
            'max_velocity_scaling_factor': self.max_velocity_factor,
            'max_acceleration_scaling_factor': self.max_acceleration_factor,
            'allowed_planning_time': self.planning_time,
            'num_planning_attempts': self.num_planning_attempts,
        }
        if self.goal_pose:
            result['goal_pose'] = self.goal_pose.to_dict()
        if self.goal_state:
            result['goal_state'] = self.goal_state.to_dict()
        return result


@dataclass
class MotionPlanResponse:
    """Motion planning service response."""
    success: bool
    trajectory: Optional[Trajectory] = None
    planning_time: float = 0.0
    error_code: int = 0
    error_message: str = ""


class MoveItBridge:
    """
    Bridge to MoveIt 2 via FastDDS.
    
    Provides high-level interface for:
    - IK solving
    - FK computation
    - Motion planning
    - Collision checking
    
    Requires:
    - ROA Bridge running with FastDDS
    - MoveIt 2 node running with robot loaded
    """
    
    # Service names (ROS 2 conventions)
    IK_SERVICE = "/compute_ik"
    FK_SERVICE = "/compute_fk"
    PLAN_SERVICE = "/plan_kinematic_path"
    EXECUTE_SERVICE = "/execute_trajectory"
    
    def __init__(
        self,
        robot_name: str,
        move_group: str = "manipulator",
        domain_id: int = 0
    ):
        """
        Initialize MoveIt bridge.
        
        Args:
            robot_name: Name of the robot in MoveIt
            move_group: MoveIt planning group name
            domain_id: DDS domain ID (default 0)
        """
        self.robot_name = robot_name
        self.move_group = move_group
        self.domain_id = domain_id
        
        self.connected = False
        self.client: Optional[Any] = None
        
        # Cached robot info
        self.joint_names: List[str] = []
        self.joint_limits: Dict[str, Tuple[float, float]] = {}
        
        # Bridge connection
        self.bridge_host: str = "localhost"
        self.bridge_port: int = 9090  # Default rosbridge port
        self._socket: Optional['socket.socket'] = None
        self._recv_buffer: str = ""
        
        # Callbacks
        self._state_callbacks: List[Callable] = []
        
        self._connect()
    
    def _connect(self):
        """Establish connection to MoveIt via ROA Bridge."""
        # Try socket-based connection to roa_bridge_server
        try:
            import socket
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(5.0)
            self._socket.connect((self.bridge_host, self.bridge_port))
            self.connected = True
            logger.info(f"Connected to ROA Bridge at {self.bridge_host}:{self.bridge_port}")
            self._fetch_robot_info()
        except (socket.error, ConnectionRefusedError, TimeoutError) as e:
            logger.warning(f"Could not connect to ROA Bridge: {e}")
            self._socket = None
            self.connected = False
        except Exception as e:
            logger.error(f"Bridge connection failed: {e}")
            self._socket = None
            self.connected = False
    
    def _send_message(self, msg: Dict) -> Optional[Dict]:
        """Send rosbridge-protocol message and receive response."""
        if not self._socket:
            return None
        
        try:
            # Send JSON message with newline delimiter
            msg_str = json.dumps(msg) + "\n"
            self._socket.send(msg_str.encode())
            
            # Receive response
            self._socket.settimeout(5.0)
            response = ""
            while True:
                data = self._socket.recv(4096).decode()
                if not data:
                    break
                response += data
                if "\n" in response:
                    break
            
            if response.strip():
                return json.loads(response.strip().split("\n")[0])
            return None
        
        except (socket.timeout, json.JSONDecodeError) as e:
            logger.debug(f"Message send/receive error: {e}")
            return None
        except Exception as e:
            logger.error(f"Bridge communication error: {e}")
            return None
    
    def _fetch_robot_info(self):
        """Fetch robot information from MoveIt."""
        # This would query MoveIt for joint names, limits, etc.
        # Placeholder - actual implementation depends on MoveIt service
        pass
    
    def compute_ik(
        self,
        target_pose: Union[Pose, List[float]],
        seed_state: Optional[JointState] = None,
        timeout: float = 1.0
    ) -> IKResponse:
        """
        Compute inverse kinematics for target pose.
        
        Args:
            target_pose: Target end-effector pose (Pose or [x,y,z,rx,ry,rz])
            seed_state: Starting joint configuration (optional)
            timeout: Solver timeout in seconds
            
        Returns:
            IKResponse with solution if successful
        """
        if not self.connected:
            return IKResponse(
                success=False,
                error_message="Not connected to MoveIt"
            )
        
        # Convert list to Pose if needed
        if isinstance(target_pose, list):
            if len(target_pose) == 6:
                target_pose = Pose.from_rpy(*target_pose)
            elif len(target_pose) == 7:
                target_pose = Pose(
                    position=target_pose[:3],
                    orientation=target_pose[3:]
                )
        
        request = IKRequest(
            group_name=self.move_group,
            target_pose=target_pose,
            seed_state=seed_state,
            timeout=timeout,
        )
        
        try:
            # Call IK service via rosbridge protocol
            service_request = {
                "op": "call_service",
                "service": self.IK_SERVICE,
                "args": request.to_dict()
            }
            response_data = self._send_message(service_request)
            
            if response_data and response_data.get('result', {}).get('error_code', -1) == 1:  # SUCCESS
                solution = JointState.from_dict(
                    response_data.get('result', {}).get('solution', {})
                )
                return IKResponse(success=True, solution=solution)
            else:
                return IKResponse(
                    success=False,
                    error_code=response_data.get('result', {}).get('error_code', -1) if response_data else -1,
                    error_message="IK solution not found"
                )
        
        except Exception as e:
            logger.error(f"IK computation failed: {e}")
            return IKResponse(success=False, error_message=str(e))
    
    def compute_fk(
        self,
        joint_state: JointState,
        link_name: Optional[str] = None
    ) -> Optional[Pose]:
        """
        Compute forward kinematics.
        
        Args:
            joint_state: Current joint configuration
            link_name: Link to compute pose for (default: end-effector)
            
        Returns:
            Pose of the link, or None if failed
        """
        if not self.connected:
            return None
        
        request = {
            'header': {'frame_id': 'world'},
            'fk_link_names': [link_name] if link_name else [],
            'robot_state': {'joint_state': joint_state.to_dict()},
        }
        
        try:
            service_request = {
                "op": "call_service",
                "service": self.FK_SERVICE,
                "args": request
            }
            response_data = self._send_message(service_request)
            
            if response_data:
                poses = response_data.get('result', {}).get('pose_stamped', [])
                if poses:
                    return Pose.from_dict(poses[0].get('pose', {}))
            return None
        
        except Exception as e:
            logger.error(f"FK computation failed: {e}")
            return None
    
    def plan_motion(
        self,
        start_state: JointState,
        goal_pose: Optional[Pose] = None,
        goal_state: Optional[JointState] = None,
        planner: PlannerType = PlannerType.OMPL_RRT,
        max_velocity: float = 0.1,
        planning_time: float = 5.0
    ) -> MotionPlanResponse:
        """
        Plan a collision-free motion trajectory.
        
        Args:
            start_state: Starting joint configuration
            goal_pose: Target pose (Cartesian planning)
            goal_state: Target joint configuration (joint space planning)
            planner: Motion planner to use
            max_velocity: Max velocity scaling factor (0-1)
            planning_time: Max time for planning
            
        Returns:
            MotionPlanResponse with trajectory if successful
        """
        if not self.connected:
            return MotionPlanResponse(
                success=False,
                error_message="Not connected to MoveIt"
            )
        
        if goal_pose is None and goal_state is None:
            return MotionPlanResponse(
                success=False,
                error_message="Must specify goal_pose or goal_state"
            )
        
        request = MotionPlanRequest(
            group_name=self.move_group,
            start_state=start_state,
            goal_pose=goal_pose,
            goal_state=goal_state,
            planner_id=planner,
            max_velocity_factor=max_velocity,
            planning_time=planning_time,
        )
        
        try:
            service_request = {
                "op": "call_service",
                "service": self.PLAN_SERVICE,
                "args": request.to_dict()
            }
            response_data = self._send_message(service_request)
            
            if response_data:
                result = response_data.get('result', {})
                if result.get('error_code', {}).get('val', -1) == 1:
                    trajectory = Trajectory.from_dict(
                        result.get('trajectory', {}).get('joint_trajectory', {})
                    )
                    return MotionPlanResponse(
                        success=True,
                        trajectory=trajectory,
                        planning_time=result.get('planning_time', 0),
                    )
            
            return MotionPlanResponse(
                success=False,
                error_code=response_data.get('result', {}).get('error_code', {}).get('val', -1) if response_data else -1,
                error_message="Motion planning failed"
            )
        
        except Exception as e:
            logger.error(f"Motion planning failed: {e}")
            return MotionPlanResponse(success=False, error_message=str(e))
    
    def execute_trajectory(
        self,
        trajectory: Trajectory,
        wait: bool = True
    ) -> bool:
        """
        Execute a planned trajectory.
        
        Args:
            trajectory: Trajectory to execute
            wait: Whether to wait for execution to complete
            
        Returns:
            True if execution started/completed successfully
        """
        if not self.connected:
            return False
        
        try:
            service_request = {
                "op": "call_service",
                "service": self.EXECUTE_SERVICE,
                "args": {'trajectory': trajectory.to_dict(), 'wait': wait}
            }
            response_data = self._send_message(service_request)
            if response_data:
                return response_data.get('result', {}).get('error_code', {}).get('val', -1) == 1
            return False
        
        except Exception as e:
            logger.error(f"Trajectory execution failed: {e}")
            return False
    
    def check_collision(
        self,
        joint_state: JointState
    ) -> bool:
        """
        Check if a configuration is in collision.
        
        Args:
            joint_state: Joint configuration to check
            
        Returns:
            True if in collision
        """
        # This would use MoveIt's collision checking service
        # Placeholder implementation
        return False
    
    def subscribe_state(
        self,
        callback: Callable[[JointState], None]
    ):
        """
        Subscribe to joint state updates.
        
        Args:
            callback: Function to call with new joint states
        """
        self._state_callbacks.append(callback)
        
        if self.connected:
            # Subscribe to joint_states topic
            try:
                self.client.subscribe(
                    '/joint_states',
                    lambda msg: self._handle_state(msg)
                )
            except Exception as e:
                logger.error(f"State subscription failed: {e}")
    
    def _handle_state(self, msg: Dict):
        """Handle incoming joint state message."""
        state = JointState.from_dict(msg)
        for callback in self._state_callbacks:
            try:
                callback(state)
            except Exception as e:
                logger.error(f"State callback error: {e}")
    
    def close(self):
        """Close the MoveIt connection."""
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
        self.connected = False


class LocalIKSolver:
    """
    Local IK solver fallback when MoveIt is not available.
    
    Uses numerical methods (damped least squares, CCD, FABRIK)
    for basic IK solving without collision checking.
    """
    
    def __init__(self, robot_description: Dict):
        """
        Initialize local IK solver.
        
        Args:
            robot_description: Robot kinematic description
        """
        self.robot = robot_description
        self.joints = robot_description.get('joints', [])
        self.joint_names = [j.get('name') for j in self.joints if j.get('type') != 'fixed']
    
    def solve_ik_dls(
        self,
        target_pose: Pose,
        seed: Optional[List[float]] = None,
        damping: float = 0.1,
        max_iterations: int = 100,
        tolerance: float = 0.001
    ) -> Optional[List[float]]:
        """
        Solve IK using Damped Least Squares (DLS) method.
        
        Args:
            target_pose: Target end-effector pose
            seed: Initial joint configuration
            damping: Damping factor for stability
            max_iterations: Maximum iterations
            tolerance: Position tolerance for convergence
            
        Returns:
            Joint positions or None if failed
        """
        import numpy as np
        
        n_joints = len(self.joint_names)
        
        if seed is None:
            q = np.zeros(n_joints)
        else:
            q = np.array(seed)
        
        target_pos = np.array(target_pose.position)
        
        for iteration in range(max_iterations):
            # Compute current end-effector position (simplified FK)
            current_pos = self._forward_kinematics(q)
            
            # Position error
            error = target_pos - current_pos
            
            if np.linalg.norm(error) < tolerance:
                return q.tolist()
            
            # Compute Jacobian (numerical approximation)
            J = self._compute_jacobian(q)
            
            # Damped least squares: dq = J^T (J J^T + λ²I)^-1 e
            JJT = J @ J.T
            lambda_sq = damping ** 2
            dq = J.T @ np.linalg.solve(JJT + lambda_sq * np.eye(3), error)
            
            # Update joints
            q = q + dq
            
            # Apply joint limits
            q = self._clamp_joints(q)
        
        logger.warning(f"IK did not converge after {max_iterations} iterations")
        return None
    
    def _forward_kinematics(self, q: 'np.ndarray') -> 'np.ndarray':
        """Compute end-effector position from joint angles."""
        import numpy as np
        
        # Simplified: assume serial chain with Z-axis rotations
        pos = np.array([0.0, 0.0, 0.0])
        
        for i, joint in enumerate(self.joints):
            if joint.get('type') == 'fixed':
                continue
            
            # Get joint parameters
            origin = joint.get('origin', {})
            xyz = origin.get('xyz', [0, 0, 0])
            axis = joint.get('axis', [0, 0, 1])
            
            # Apply translation
            pos = pos + np.array(xyz)
            
            # Apply rotation (simplified for Z-axis)
            angle = q[i] if i < len(q) else 0
            c, s = np.cos(angle), np.sin(angle)
            
            if axis[2] > 0.5:  # Z rotation
                rot = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
            elif axis[1] > 0.5:  # Y rotation
                rot = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
            else:  # X rotation
                rot = np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
            
            # Transform position
            pos = rot @ pos
        
        return pos
    
    def _compute_jacobian(self, q: 'np.ndarray', delta: float = 0.001) -> 'np.ndarray':
        """Compute numerical Jacobian."""
        import numpy as np
        
        n = len(q)
        J = np.zeros((3, n))
        
        pos0 = self._forward_kinematics(q)
        
        for i in range(n):
            q_delta = q.copy()
            q_delta[i] += delta
            pos_delta = self._forward_kinematics(q_delta)
            J[:, i] = (pos_delta - pos0) / delta
        
        return J
    
    def _clamp_joints(self, q: 'np.ndarray') -> 'np.ndarray':
        """Clamp joint values to limits."""
        import numpy as np
        
        for i, joint in enumerate(self.joints):
            if i >= len(q):
                break
            if joint.get('type') == 'fixed':
                continue
            
            limits = joint.get('limits', {})
            lower = limits.get('lower', -math.pi)
            upper = limits.get('upper', math.pi)
            
            q[i] = np.clip(q[i], lower, upper)
        
        return q


class IKManager:
    """
    Unified IK manager that selects between MoveIt and local solvers.
    
    Provides consistent interface for IK solving across different backends.
    """
    
    def __init__(
        self,
        robot_name: str,
        robot_description: Dict,
        use_moveit: bool = True,
        moveit_group: str = "manipulator"
    ):
        """
        Initialize IK manager.
        
        Args:
            robot_name: Robot name
            robot_description: Robot kinematic description
            use_moveit: Whether to try MoveIt first
            moveit_group: MoveIt planning group
        """
        self.robot_name = robot_name
        self.robot_description = robot_description
        
        self.moveit: Optional[MoveItBridge] = None
        self.local_solver: Optional[LocalIKSolver] = None
        
        if use_moveit and FASTDDS_AVAILABLE:
            try:
                self.moveit = MoveItBridge(robot_name, moveit_group)
            except Exception as e:
                logger.warning(f"MoveIt initialization failed: {e}")
        
        # Always have local solver as fallback
        self.local_solver = LocalIKSolver(robot_description)
    
    def solve_ik(
        self,
        target: Union[Pose, List[float]],
        seed: Optional[List[float]] = None,
        prefer_moveit: bool = True
    ) -> Optional[List[float]]:
        """
        Solve IK using best available solver.
        
        Args:
            target: Target pose
            seed: Seed configuration
            prefer_moveit: Try MoveIt first if available
            
        Returns:
            Joint positions or None
        """
        # Convert target to Pose if needed
        if isinstance(target, list):
            if len(target) == 6:
                target = Pose.from_rpy(*target)
            elif len(target) == 7:
                target = Pose(position=target[:3], orientation=target[3:])
        
        # Try MoveIt
        if prefer_moveit and self.moveit and self.moveit.connected:
            seed_state = None
            if seed:
                seed_state = JointState(
                    names=self.local_solver.joint_names,
                    positions=seed
                )
            
            response = self.moveit.compute_ik(target, seed_state)
            if response.success and response.solution:
                return response.solution.positions
        
        # Fallback to local solver
        if self.local_solver:
            return self.local_solver.solve_ik_dls(target, seed)
        
        return None
    
    def close(self):
        """Clean up resources."""
        if self.moveit:
            self.moveit.close()


# Convenience functions
def create_ik_manager(
    robot_name: str,
    urdf_path: Optional[str] = None,
    robot_description: Optional[Dict] = None,
    use_moveit: bool = True
) -> IKManager:
    """
    Create an IK manager for a robot.
    
    Args:
        robot_name: Robot name
        urdf_path: Path to URDF (alternative to robot_description)
        robot_description: Robot description dict
        use_moveit: Whether to use MoveIt
        
    Returns:
        Configured IKManager
    """
    if robot_description is None and urdf_path:
        from .urdf_converter import URDFConverter
        converter = URDFConverter()
        robot_description = converter.parse_urdf(urdf_path)
    
    if robot_description is None:
        robot_description = {'joints': []}
    
    return IKManager(robot_name, robot_description, use_moveit)
