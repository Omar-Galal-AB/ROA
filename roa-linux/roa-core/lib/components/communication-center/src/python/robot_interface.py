"""
Robot Interface Layer

Per-robot action clients, publishers, and subscribers for multi-robot coordination.
Based on REMROC coordinator pattern - provides unified interface for controlling
multiple robots through Nav2 action servers and direct velocity commands.

Key Features:
- Action clients for NavigateToPose, FollowPath, ComputePathToPose
- Direct cmd_vel publishers for emergency stop override
- State subscribers for odometry, laser scans, robot state
- Per-robot state tracking dictionary
"""

import rclpy
from geometry_msgs.msg import Point, Pose, PoseStamped, Quaternion, Twist
from nav_msgs.msg import Odometry, Path
from rclpy.action import ActionClient
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Header

# Nav2 action types
try:
    from nav2_msgs.action import ComputePathToPose, FollowPath, NavigateToPose

    NAV2_AVAILABLE = True
except ImportError:
    NAV2_AVAILABLE = False

import logging
import math
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


class RobotState(Enum):
    """Robot operational states"""

    UNKNOWN = "unknown"
    IDLE = "idle"
    NAVIGATING = "navigating"
    EXECUTING_PATH = "executing_path"
    EMERGENCY_STOP = "emergency_stop"
    EVADING = "evading"
    WAITING = "waiting"
    ERROR = "error"


@dataclass
class RobotData:
    """Complete state data for a single robot"""

    robot_id: str
    state: RobotState = RobotState.UNKNOWN

    # Position and velocity
    position: Optional[Point] = None
    orientation: Optional[Quaternion] = None
    linear_velocity: Optional[Point] = None
    angular_velocity: Optional[Point] = None

    # Sensor data
    laser_ranges: Optional[List[float]] = None
    laser_min_range: float = float("inf")
    laser_timestamp: float = 0.0

    # Path data
    current_path: Optional[List[PoseStamped]] = None
    path_progress: float = 0.0  # 0.0 to 1.0
    goal_pose: Optional[PoseStamped] = None

    # Timing
    last_odom_update: float = 0.0
    last_laser_update: float = 0.0
    last_state_update: float = 0.0

    # Metrics
    total_distance_traveled: float = 0.0
    last_position_for_distance: Optional[Point] = None


class RobotActionClient:
    """
    Action client wrapper for a single robot.
    Provides async navigation and path following capabilities.
    """

    def __init__(self, node: Node, robot_id: str, callback_group=None):
        self.node = node
        self.robot_id = robot_id
        self.callback_group = callback_group or ReentrantCallbackGroup()
        self.logger = node.get_logger()

        # Action clients (created lazily when Nav2 is available)
        self._navigate_client: Optional[ActionClient] = None
        self._follow_path_client: Optional[ActionClient] = None
        self._compute_path_client: Optional[ActionClient] = None

        # Goal handles for cancellation
        self._current_navigate_goal = None
        self._current_follow_path_goal = None

        # Callbacks
        self._navigate_result_callback: Optional[Callable] = None
        self._follow_path_result_callback: Optional[Callable] = None

        if NAV2_AVAILABLE:
            self._create_action_clients()
        else:
            self.logger.warn(f"Nav2 not available, action clients disabled for {robot_id}")

    def _create_action_clients(self):
        """Create Nav2 action clients for this robot"""
        self._navigate_client = ActionClient(
            self.node,
            NavigateToPose,
            f"/{self.robot_id}/navigate_to_pose",
            callback_group=self.callback_group,
        )

        self._follow_path_client = ActionClient(
            self.node,
            FollowPath,
            f"/{self.robot_id}/follow_path",
            callback_group=self.callback_group,
        )

        self._compute_path_client = ActionClient(
            self.node,
            ComputePathToPose,
            f"/{self.robot_id}/compute_path_to_pose",
            callback_group=self.callback_group,
        )

        self.logger.info(f"Created action clients for robot {self.robot_id}")

    def navigate_to_pose(
        self,
        goal_pose: PoseStamped,
        result_callback: Optional[Callable] = None,
        timeout_sec: float = 5.0,
    ) -> bool:
        """
        Send NavigateToPose goal to robot.

        Args:
            goal_pose: Target pose for navigation
            result_callback: Callback for result (success, result)
            timeout_sec: Timeout for server connection

        Returns:
            True if goal was sent successfully
        """
        if not NAV2_AVAILABLE or not self._navigate_client:
            self.logger.error(f"Navigate client not available for {self.robot_id}")
            return False

        if not self._navigate_client.wait_for_server(timeout_sec=timeout_sec):
            self.logger.error(f"Navigate server not available for {self.robot_id}")
            return False

        goal = NavigateToPose.Goal()
        goal.pose = goal_pose

        self._navigate_result_callback = result_callback

        future = self._navigate_client.send_goal_async(
            goal, feedback_callback=self._navigate_feedback_callback
        )
        future.add_done_callback(self._navigate_goal_response_callback)

        self.logger.info(
            f"Sent navigate goal to {self.robot_id}: "
            f"({goal_pose.pose.position.x:.2f}, {goal_pose.pose.position.y:.2f})"
        )
        return True

    def _navigate_goal_response_callback(self, future):
        """Handle navigate goal acceptance"""
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.logger.warn(f"Navigate goal rejected for {self.robot_id}")
            return

        self._current_navigate_goal = goal_handle
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._navigate_result_callback_internal)

    def _navigate_feedback_callback(self, feedback_msg):
        """Handle navigate feedback"""
        # Can be extended to track progress
        pass

    def _navigate_result_callback_internal(self, future):
        """Handle navigate result"""
        result = future.result().result
        status = future.result().status

        success = status == 4  # SUCCEEDED

        if self._navigate_result_callback:
            self._navigate_result_callback(success, result)

        self._current_navigate_goal = None

    def follow_path(
        self,
        path: Path,
        result_callback: Optional[Callable] = None,
        timeout_sec: float = 5.0,
    ) -> bool:
        """
        Send FollowPath goal to robot.

        Args:
            path: Path to follow
            result_callback: Callback for result
            timeout_sec: Server timeout

        Returns:
            True if goal was sent successfully
        """
        if not NAV2_AVAILABLE or not self._follow_path_client:
            self.logger.error(f"FollowPath client not available for {self.robot_id}")
            return False

        if not self._follow_path_client.wait_for_server(timeout_sec=timeout_sec):
            self.logger.error(f"FollowPath server not available for {self.robot_id}")
            return False

        goal = FollowPath.Goal()
        goal.path = path

        self._follow_path_result_callback = result_callback

        future = self._follow_path_client.send_goal_async(goal)
        future.add_done_callback(self._follow_path_goal_response_callback)

        self.logger.info(
            f"Sent follow_path goal to {self.robot_id} with {len(path.poses)} waypoints"
        )
        return True

    def _follow_path_goal_response_callback(self, future):
        """Handle follow_path goal acceptance"""
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.logger.warn(f"FollowPath goal rejected for {self.robot_id}")
            return

        self._current_follow_path_goal = goal_handle
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._follow_path_result_callback_internal)

    def _follow_path_result_callback_internal(self, future):
        """Handle follow_path result"""
        result = future.result().result
        status = future.result().status

        success = status == 4  # SUCCEEDED

        if self._follow_path_result_callback:
            self._follow_path_result_callback(success, result)

        self._current_follow_path_goal = None

    def compute_path_to_pose(
        self, start: PoseStamped, goal: PoseStamped, timeout_sec: float = 10.0
    ) -> Optional[Path]:
        """
        Compute path from start to goal (synchronous).

        Args:
            start: Start pose
            goal: Goal pose
            timeout_sec: Computation timeout

        Returns:
            Computed path or None
        """
        if not NAV2_AVAILABLE or not self._compute_path_client:
            self.logger.error(f"ComputePath client not available for {self.robot_id}")
            return None

        if not self._compute_path_client.wait_for_server(timeout_sec=5.0):
            self.logger.error(f"ComputePath server not available for {self.robot_id}")
            return None

        goal_msg = ComputePathToPose.Goal()
        goal_msg.start = start
        goal_msg.goal = goal
        goal_msg.use_start = True

        future = self._compute_path_client.send_goal_async(goal_msg)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=timeout_sec)

        if not future.done():
            self.logger.error(f"ComputePath timed out for {self.robot_id}")
            return None

        goal_handle = future.result()
        if not goal_handle.accepted:
            self.logger.warn(f"ComputePath goal rejected for {self.robot_id}")
            return None

        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self.node, result_future, timeout_sec=timeout_sec)

        if not result_future.done():
            self.logger.error(f"ComputePath result timed out for {self.robot_id}")
            return None

        result = result_future.result().result
        return result.path

    def cancel_navigation(self) -> bool:
        """Cancel current navigation goal"""
        if self._current_navigate_goal:
            self._current_navigate_goal.cancel_goal_async()
            self._current_navigate_goal = None
            self.logger.info(f"Cancelled navigation for {self.robot_id}")
            return True
        return False

    def cancel_follow_path(self) -> bool:
        """Cancel current follow_path goal"""
        if self._current_follow_path_goal:
            self._current_follow_path_goal.cancel_goal_async()
            self._current_follow_path_goal = None
            self.logger.info(f"Cancelled follow_path for {self.robot_id}")
            return True
        return False

    def cancel_all(self) -> None:
        """Cancel all active goals"""
        self.cancel_navigation()
        self.cancel_follow_path()


class RobotInterface:
    """
    Unified interface for managing multiple robots.

    Provides:
    - Per-robot action clients (Nav2)
    - Per-robot cmd_vel publishers
    - Per-robot state subscribers (odom, laser)
    - Centralized robot state tracking

    Based on REMROC coordinator pattern.
    """

    def __init__(self, node: Node):
        self.node = node
        self.logger = node.get_logger()

        # Per-robot data
        self.robot_data: Dict[str, RobotData] = {}
        self.action_clients: Dict[str, RobotActionClient] = {}
        self.cmd_vel_publishers: Dict[str, Any] = {}  # rclpy Publisher

        # Subscribers (stored for cleanup)
        self._odom_subs: Dict[str, Any] = {}
        self._laser_subs: Dict[str, Any] = {}
        self._state_subs: Dict[str, Any] = {}

        # Callbacks
        self._state_change_callbacks: List[Callable] = []
        self._proximity_callbacks: List[Callable] = []

        # Callback groups
        self._sub_callback_group = ReentrantCallbackGroup()
        self._action_callback_group = ReentrantCallbackGroup()

        # Lock for thread safety
        self._lock = threading.RLock()

        self.logger.info("RobotInterface initialized")

    def register_robot(self, robot_id: str) -> None:
        """
        Register a robot and create all its interfaces.

        Args:
            robot_id: Unique robot identifier
        """
        with self._lock:
            if robot_id in self.robot_data:
                self.logger.warn(f"Robot {robot_id} already registered")
                return

            # Create robot data
            self.robot_data[robot_id] = RobotData(robot_id=robot_id)

            # Create action client
            self.action_clients[robot_id] = RobotActionClient(
                self.node, robot_id, self._action_callback_group
            )

            # Create cmd_vel publisher
            self.cmd_vel_publishers[robot_id] = self.node.create_publisher(
                Twist, f"/{robot_id}/cmd_vel", 10
            )

            # Create subscribers
            self._create_subscribers(robot_id)

            self.logger.info(f"Registered robot: {robot_id}")

    def _create_subscribers(self, robot_id: str) -> None:
        """Create state subscribers for a robot"""

        # Odometry subscriber
        self._odom_subs[robot_id] = self.node.create_subscription(
            Odometry,
            f"/{robot_id}/odom",
            lambda msg, rid=robot_id: self._odom_callback(rid, msg),
            10,
            callback_group=self._sub_callback_group,
        )

        # Alternative: odometry/filtered for better estimates
        self.node.create_subscription(
            Odometry,
            f"/{robot_id}/odometry/filtered",
            lambda msg, rid=robot_id: self._odom_callback(rid, msg),
            10,
            callback_group=self._sub_callback_group,
        )

        # Laser scan subscriber
        self._laser_subs[robot_id] = self.node.create_subscription(
            LaserScan,
            f"/{robot_id}/scan",
            lambda msg, rid=robot_id: self._laser_callback(rid, msg),
            10,
            callback_group=self._sub_callback_group,
        )

        # Alternative laser topic
        self.node.create_subscription(
            LaserScan,
            f"/{robot_id}/laser_scan",
            lambda msg, rid=robot_id: self._laser_callback(rid, msg),
            10,
            callback_group=self._sub_callback_group,
        )

    def _odom_callback(self, robot_id: str, msg: Odometry) -> None:
        """Handle odometry update for a robot"""
        with self._lock:
            if robot_id not in self.robot_data:
                return

            data = self.robot_data[robot_id]
            current_time = time.time()

            # Update position
            new_position = Point(
                x=msg.pose.pose.position.x,
                y=msg.pose.pose.position.y,
                z=msg.pose.pose.position.z,
            )

            # Calculate distance traveled
            if data.position is not None:
                dx = new_position.x - data.position.x
                dy = new_position.y - data.position.y
                dz = new_position.z - data.position.z
                distance = math.sqrt(dx * dx + dy * dy + dz * dz)
                data.total_distance_traveled += distance

            data.position = new_position
            data.orientation = msg.pose.pose.orientation

            # Update velocity
            data.linear_velocity = Point(
                x=msg.twist.twist.linear.x,
                y=msg.twist.twist.linear.y,
                z=msg.twist.twist.linear.z,
            )
            data.angular_velocity = Point(
                x=msg.twist.twist.angular.x,
                y=msg.twist.twist.angular.y,
                z=msg.twist.twist.angular.z,
            )

            data.last_odom_update = current_time

    def _laser_callback(self, robot_id: str, msg: LaserScan) -> None:
        """Handle laser scan update for a robot"""
        with self._lock:
            if robot_id not in self.robot_data:
                return

            data = self.robot_data[robot_id]

            # Store ranges and compute min
            data.laser_ranges = list(msg.ranges)
            valid_ranges = [r for r in msg.ranges if msg.range_min <= r <= msg.range_max]
            data.laser_min_range = min(valid_ranges) if valid_ranges else float("inf")
            data.laser_timestamp = time.time()
            data.last_laser_update = data.laser_timestamp

    def unregister_robot(self, robot_id: str) -> None:
        """Unregister a robot and cleanup its interfaces"""
        with self._lock:
            if robot_id not in self.robot_data:
                return

            # Cancel any active goals
            if robot_id in self.action_clients:
                self.action_clients[robot_id].cancel_all()
                del self.action_clients[robot_id]

            # Remove publishers (subscribers are managed by node)
            if robot_id in self.cmd_vel_publishers:
                del self.cmd_vel_publishers[robot_id]

            # Remove data
            del self.robot_data[robot_id]

            self.logger.info(f"Unregistered robot: {robot_id}")

    def get_robot_ids(self) -> List[str]:
        """Get list of registered robot IDs"""
        with self._lock:
            return list(self.robot_data.keys())

    def get_robot_data(self, robot_id: str) -> Optional[RobotData]:
        """Get robot data by ID"""
        with self._lock:
            return self.robot_data.get(robot_id)

    def get_all_robot_data(self) -> Dict[str, RobotData]:
        """Get all robot data"""
        with self._lock:
            return dict(self.robot_data)

    def get_robot_position(self, robot_id: str) -> Optional[Point]:
        """Get robot position"""
        with self._lock:
            data = self.robot_data.get(robot_id)
            return data.position if data else None

    def get_all_positions(self) -> Dict[str, Point]:
        """Get positions of all robots"""
        with self._lock:
            return {
                rid: data.position
                for rid, data in self.robot_data.items()
                if data.position is not None
            }

    # === Robot Control Methods ===

    def send_velocity(
        self,
        robot_id: str,
        linear_x: float = 0.0,
        linear_y: float = 0.0,
        angular_z: float = 0.0,
    ) -> bool:
        """
        Send velocity command to robot.

        Args:
            robot_id: Target robot
            linear_x: Forward velocity (m/s)
            linear_y: Lateral velocity (m/s)
            angular_z: Angular velocity (rad/s)

        Returns:
            True if command was sent
        """
        with self._lock:
            if robot_id not in self.cmd_vel_publishers:
                self.logger.error(f"No cmd_vel publisher for {robot_id}")
                return False

            twist = Twist()
            twist.linear.x = linear_x
            twist.linear.y = linear_y
            twist.angular.z = angular_z

            self.cmd_vel_publishers[robot_id].publish(twist)
            return True

    def emergency_stop(self, robot_id: str) -> bool:
        """
        Send emergency stop to robot (zero velocity + cancel goals).

        Args:
            robot_id: Target robot

        Returns:
            True if stop was sent
        """
        with self._lock:
            # Cancel any active navigation goals
            if robot_id in self.action_clients:
                self.action_clients[robot_id].cancel_all()

            # Send zero velocity
            success = self.send_velocity(robot_id, 0.0, 0.0, 0.0)

            # Update state
            if robot_id in self.robot_data:
                self.robot_data[robot_id].state = RobotState.EMERGENCY_STOP

            self.logger.warn(f"Emergency stop sent to {robot_id}")
            return success

    def emergency_stop_all(self) -> None:
        """Send emergency stop to all registered robots"""
        for robot_id in self.get_robot_ids():
            self.emergency_stop(robot_id)
        self.logger.warn("Emergency stop sent to ALL robots")

    def navigate_to_pose(
        self,
        robot_id: str,
        x: float,
        y: float,
        yaw: float = 0.0,
        frame_id: str = "map",
        result_callback: Optional[Callable] = None,
    ) -> bool:
        """
        Navigate robot to pose.

        Args:
            robot_id: Target robot
            x, y: Target position
            yaw: Target orientation
            frame_id: Coordinate frame
            result_callback: Callback for result

        Returns:
            True if goal was sent
        """
        with self._lock:
            if robot_id not in self.action_clients:
                self.logger.error(f"No action client for {robot_id}")
                return False

            goal_pose = PoseStamped()
            goal_pose.header.frame_id = frame_id
            goal_pose.header.stamp = self.node.get_clock().now().to_msg()
            goal_pose.pose.position.x = x
            goal_pose.pose.position.y = y
            goal_pose.pose.position.z = 0.0

            # Convert yaw to quaternion
            goal_pose.pose.orientation.z = math.sin(yaw / 2.0)
            goal_pose.pose.orientation.w = math.cos(yaw / 2.0)

            # Store goal
            if robot_id in self.robot_data:
                self.robot_data[robot_id].goal_pose = goal_pose
                self.robot_data[robot_id].state = RobotState.NAVIGATING

            return self.action_clients[robot_id].navigate_to_pose(goal_pose, result_callback)

    def follow_path(
        self,
        robot_id: str,
        waypoints: List[Tuple[float, float]],
        frame_id: str = "map",
        result_callback: Optional[Callable] = None,
    ) -> bool:
        """
        Make robot follow a path.

        Args:
            robot_id: Target robot
            waypoints: List of (x, y) waypoints
            frame_id: Coordinate frame
            result_callback: Callback for result

        Returns:
            True if goal was sent
        """
        with self._lock:
            if robot_id not in self.action_clients:
                self.logger.error(f"No action client for {robot_id}")
                return False

            path = Path()
            path.header.frame_id = frame_id
            path.header.stamp = self.node.get_clock().now().to_msg()

            for x, y in waypoints:
                pose = PoseStamped()
                pose.header = path.header
                pose.pose.position.x = x
                pose.pose.position.y = y
                pose.pose.position.z = 0.0
                pose.pose.orientation.w = 1.0
                path.poses.append(pose)

            # Store path
            if robot_id in self.robot_data:
                self.robot_data[robot_id].current_path = path.poses
                self.robot_data[robot_id].state = RobotState.EXECUTING_PATH

            return self.action_clients[robot_id].follow_path(path, result_callback)

    def compute_path(
        self,
        robot_id: str,
        start_x: float,
        start_y: float,
        goal_x: float,
        goal_y: float,
        frame_id: str = "map",
    ) -> Optional[List[Tuple[float, float]]]:
        """
        Compute path from start to goal.

        Args:
            robot_id: Robot to use for path computation
            start_x, start_y: Start position
            goal_x, goal_y: Goal position
            frame_id: Coordinate frame

        Returns:
            List of (x, y) waypoints or None
        """
        if robot_id not in self.action_clients:
            self.logger.error(f"No action client for {robot_id}")
            return None

        start = PoseStamped()
        start.header.frame_id = frame_id
        start.pose.position.x = start_x
        start.pose.position.y = start_y
        start.pose.orientation.w = 1.0

        goal = PoseStamped()
        goal.header.frame_id = frame_id
        goal.pose.position.x = goal_x
        goal.pose.position.y = goal_y
        goal.pose.orientation.w = 1.0

        path = self.action_clients[robot_id].compute_path_to_pose(start, goal)

        if path is None:
            return None

        return [(pose.pose.position.x, pose.pose.position.y) for pose in path.poses]

    def set_robot_state(self, robot_id: str, state: RobotState) -> None:
        """Set robot operational state"""
        with self._lock:
            if robot_id in self.robot_data:
                old_state = self.robot_data[robot_id].state
                self.robot_data[robot_id].state = state
                self.robot_data[robot_id].last_state_update = time.time()

                # Notify callbacks
                for callback in self._state_change_callbacks:
                    try:
                        callback(robot_id, old_state, state)
                    except Exception as e:
                        self.logger.error(f"State callback error: {e}")

    def register_state_callback(self, callback: Callable) -> None:
        """Register callback for state changes"""
        self._state_change_callbacks.append(callback)

    def get_stale_robots(self, timeout_sec: float = 5.0) -> List[str]:
        """Get robots that haven't updated recently"""
        current_time = time.time()
        stale = []

        with self._lock:
            for robot_id, data in self.robot_data.items():
                if current_time - data.last_odom_update > timeout_sec:
                    stale.append(robot_id)

        return stale
