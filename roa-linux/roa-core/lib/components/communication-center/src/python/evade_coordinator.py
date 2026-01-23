"""
Evade Coordinator

Handles autonomous obstacle avoidance coordination for robots in ADM mode.
Integrates with DIMC for obstacle detection and COMC for multi-robot path coordination.

Enhanced with:
- MAPF solver integration for optimal path planning
- Path conflict detector integration
- Timer-based path reservation timeout
- Improved safety margin handling
"""

import math
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

import rclpy
from geometry_msgs.msg import Point
from rclpy.node import Node


class PathReservation:
    """Path reservation with expiration"""

    def __init__(self, robot_id: str, path: List[Point], duration: float):
        self.robot_id = robot_id
        self.path = path
        self.created_at = time.time()
        self.expires_at = time.time() + duration
        self.duration = duration

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def remaining_time(self) -> float:
        return max(0, self.expires_at - time.time())


class EvadeCoordinator:
    """
    Coordinates obstacle avoidance maneuvers between multiple robots.
    Works with DIMC for obstacle detection and COMC for path coordination.

    Enhanced with MAPF solver integration for optimal multi-robot path planning.
    """

    # Increased safety margin (P3 Gap Fix)
    DEFAULT_SAFETY_MARGIN = 0.3  # meters (was 0.1)

    def __init__(self, node: Node):
        """
        Initialize the evade coordinator.

        Args:
            node: ROS2 node instance
        """
        self.node = node
        self.evasion_intents: Dict[str, dict] = {}  # robot_id -> evasion_intent
        self.reserved_paths: Dict[str, PathReservation] = {}  # robot_id -> PathReservation
        self.obstacle_database: Dict[str, dict] = {}  # obstacle_id -> obstacle_info

        # Configuration
        self.max_detour_distance = 2.0  # meters (default)
        self.safety_margin = self.DEFAULT_SAFETY_MARGIN  # meters (increased)
        self.replan_timeout = 5.0  # seconds
        self.fallback_threshold = 3  # consecutive failures
        self.default_reservation_duration = 10.0  # seconds

        # Per-robot failure tracking
        self.evasion_failures: Dict[str, int] = {}  # robot_id -> failure_count

        # MAPF Solver integration (P0 Gap Fix)
        self._mapf_solver = None
        self._path_conflict_detector = None

        # Path reservation cleanup timer (P2 Gap Fix)
        self._cleanup_lock = threading.Lock()
        self._running = True
        self._cleanup_thread = threading.Thread(
            target=self._path_cleanup_loop,
            daemon=True,
            name="EvadeCoordinator-PathCleanup",
        )
        self._cleanup_thread.start()

        # Callbacks
        self._on_path_expired: Optional[Callable[[str], None]] = None
        self._on_conflict_detected: Optional[Callable[[str, str], None]] = None

    def set_mapf_solver(self, solver):
        """
        Set MAPF solver for path planning.

        Args:
            solver: MAPFSolver instance
        """
        self._mapf_solver = solver
        self.node.get_logger().info("MAPF Solver connected to EvadeCoordinator")

    def set_path_conflict_detector(self, detector):
        """
        Set path conflict detector.

        Args:
            detector: PathConflictDetector instance
        """
        self._path_conflict_detector = detector
        self.node.get_logger().info("PathConflictDetector connected to EvadeCoordinator")

    def set_on_path_expired_callback(self, callback: Callable[[str], None]):
        """Set callback for when a path reservation expires"""
        self._on_path_expired = callback

    def set_on_conflict_detected_callback(self, callback: Callable[[str, str], None]):
        """Set callback for when a path conflict is detected"""
        self._on_conflict_detected = callback

    def _path_cleanup_loop(self):
        """Background thread for cleaning up expired path reservations"""
        while self._running:
            time.sleep(1.0)  # Check every second
            self._cleanup_expired_paths()

    def _cleanup_expired_paths(self):
        """Remove expired path reservations"""
        with self._cleanup_lock:
            expired = []
            for robot_id, reservation in self.reserved_paths.items():
                if reservation.is_expired:
                    expired.append(robot_id)

            for robot_id in expired:
                self.node.get_logger().info(f"Path reservation expired for {robot_id}")
                del self.reserved_paths[robot_id]

                if robot_id in self.evasion_intents:
                    del self.evasion_intents[robot_id]

                # Notify callback
                if self._on_path_expired:
                    try:
                        self._on_path_expired(robot_id)
                    except Exception as e:
                        self.node.get_logger().error(f"Path expired callback error: {e}")

    def stop(self):
        """Stop the cleanup thread"""
        self._running = False
        if self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=2.0)

    def broadcast_evasion_intent(
        self,
        robot_id: str,
        current_pos: Point,
        target_pos: Point,
        alternative_path: List[Point],
        priority: int,
    ) -> bool:
        """
        Broadcast intention to perform evasion maneuver to all robots.

        Args:
            robot_id: ID of the evading robot
            current_pos: Current position
            target_pos: Target position
            alternative_path: Proposed alternative path
            priority: Task priority

        Returns:
            True if path is approved, False if conflicts detected
        """
        intent = {
            "robot_id": robot_id,
            "current_pos": current_pos,
            "target_pos": target_pos,
            "alternative_path": alternative_path,
            "priority": priority,
            "timestamp": time.time(),
            "status": "requested",
        }

        # Use path conflict detector if available
        if self._path_conflict_detector:
            path_tuples = [(p.x, p.y) for p in alternative_path]
            conflicts = self._path_conflict_detector.set_path(robot_id, path_tuples)
            if conflicts:
                for conflict in conflicts:
                    self.node.get_logger().warn(
                        f"Path conflict: {robot_id} vs {conflict.robot2_id} at "
                        f"({conflict.intersection_points})"
                    )
                    if self._on_conflict_detected:
                        self._on_conflict_detected(robot_id, conflict.robot2_id)

                # Check if we should deny based on priority
                for conflict in conflicts:
                    if conflict.priority_robot != robot_id:
                        return False
        else:
            # Fallback to simple conflict check
            if self._check_path_conflicts(robot_id, alternative_path, priority):
                self.node.get_logger().warn(
                    f"Path conflict detected for {robot_id}, denying evasion intent"
                )
                return False

        # Reserve the path with expiration
        self.reserved_paths[robot_id] = PathReservation(
            robot_id=robot_id,
            path=alternative_path,
            duration=self.default_reservation_duration,
        )
        self.evasion_intents[robot_id] = intent
        intent["status"] = "approved"

        self.node.get_logger().info(
            f"Evasion intent approved for {robot_id} (expires in {self.default_reservation_duration}s)"
        )
        return True

    def request_mapf_path(
        self,
        robot_id: str,
        start: Point,
        goal: Point,
        other_robots: Dict[str, Tuple[Point, Point]] = None,
    ) -> Optional[List[Point]]:
        """
        Request optimal path from MAPF solver.

        Args:
            robot_id: ID of the requesting robot
            start: Start position
            goal: Goal position
            other_robots: Dict of other robot_id -> (start, goal)

        Returns:
            List of waypoints or None if no solution
        """
        if not self._mapf_solver:
            self.node.get_logger().debug("MAPF solver not available, using simple path")
            return self.calculate_detour_path(robot_id, start, goal)

        try:
            # Build MAPF request
            robot_starts = {robot_id: (start.x, start.y)}
            robot_goals = {robot_id: (goal.x, goal.y)}

            if other_robots:
                for rid, (s, g) in other_robots.items():
                    robot_starts[rid] = (s.x, s.y)
                    robot_goals[rid] = (g.x, g.y)

            # Get solution from MAPF solver
            from .mapf_solver import MAPFRequest

            request = MAPFRequest(
                robot_starts=robot_starts,
                robot_goals=robot_goals,
                robot_radius=self.safety_margin,
            )

            solution = self._mapf_solver.solve(request)

            if solution.success and robot_id in solution.paths:
                # Convert timed path to Point list
                timed_path = solution.paths[robot_id]
                path = [Point(x=wp.x, y=wp.y, z=start.z) for wp in timed_path.waypoints]
                return path
            else:
                self.node.get_logger().warn(f"MAPF solver failed: {solution.message}")
                return None

        except Exception as e:
            self.node.get_logger().error(f"MAPF request failed: {e}")
            return None

    def _check_path_conflicts(self, robot_id: str, path: List[Point], priority: int) -> bool:
        """
        Check if proposed path conflicts with other reserved paths.

        Args:
            robot_id: ID of the requesting robot
            path: Proposed path
            priority: Task priority

        Returns:
            True if conflict exists, False otherwise
        """
        with self._cleanup_lock:
            for other_robot_id, reservation in self.reserved_paths.items():
                if other_robot_id == robot_id:
                    continue

                # Skip expired reservations
                if reservation.is_expired:
                    continue

                # Check if paths intersect
                if self._paths_intersect(path, reservation.path):
                    # Check priority
                    other_intent = self.evasion_intents.get(other_robot_id)
                    if other_intent and other_intent["priority"] >= priority:
                        return True  # Conflict with higher/equal priority

        return False

    def _paths_intersect(self, path1: List[Point], path2: List[Point]) -> bool:
        """
        Check if two paths intersect (simple proximity check).

        Args:
            path1: First path
            path2: Second path

        Returns:
            True if paths come within safety margin
        """
        for p1 in path1:
            for p2 in path2:
                distance = math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2 + (p1.z - p2.z) ** 2)
                if distance < self.safety_margin:
                    return True

        return False

    def reserve_alternative_path(self, robot_id: str, path: List[Point], duration: float = None):
        """
        Reserve a path space for evasion maneuver.

        Args:
            robot_id: ID of the robot
            path: Path to reserve
            duration: How long to reserve (seconds), uses default if None
        """
        if duration is None:
            duration = self.default_reservation_duration

        with self._cleanup_lock:
            self.reserved_paths[robot_id] = PathReservation(
                robot_id=robot_id, path=path, duration=duration
            )

        self.node.get_logger().info(f"Reserved path for {robot_id} (expires in {duration}s)")

    def extend_path_reservation(self, robot_id: str, additional_time: float):
        """
        Extend an existing path reservation.

        Args:
            robot_id: Robot ID
            additional_time: Additional seconds to reserve
        """
        with self._cleanup_lock:
            if robot_id in self.reserved_paths:
                old_res = self.reserved_paths[robot_id]
                new_duration = old_res.remaining_time + additional_time
                self.reserved_paths[robot_id] = PathReservation(
                    robot_id=robot_id, path=old_res.path, duration=new_duration
                )
                self.node.get_logger().info(
                    f"Extended path reservation for {robot_id} by {additional_time}s"
                )

    def release_path_reservation(self, robot_id: str):
        """
        Release a reserved path.

        Args:
            robot_id: ID of the robot
        """
        with self._cleanup_lock:
            if robot_id in self.reserved_paths:
                del self.reserved_paths[robot_id]
                self.node.get_logger().info(f"Released path for {robot_id}")

            if robot_id in self.evasion_intents:
                del self.evasion_intents[robot_id]

    def get_reservation_status(self, robot_id: str) -> Optional[dict]:
        """
        Get status of a path reservation.

        Args:
            robot_id: Robot ID

        Returns:
            Dict with reservation info or None
        """
        with self._cleanup_lock:
            if robot_id in self.reserved_paths:
                res = self.reserved_paths[robot_id]
                return {
                    "robot_id": robot_id,
                    "remaining_time": res.remaining_time,
                    "is_expired": res.is_expired,
                    "path_length": len(res.path),
                }
        return None

    def update_obstacle(
        self,
        obstacle_id: str,
        position: Point,
        dimensions: Tuple[float, float, float],
        obstacle_type: str,
    ):
        """
        Update obstacle information from DIMC.

        Args:
            obstacle_id: ID of the obstacle
            position: Position of obstacle
            dimensions: (width, height, depth) in meters
            obstacle_type: Type (static, dynamic, robot, boundary)
        """
        self.obstacle_database[obstacle_id] = {
            "position": position,
            "dimensions": dimensions,
            "type": obstacle_type,
            "timestamp": time.time(),
        }

    def calculate_detour_path(
        self,
        robot_id: str,
        current_pos: Point,
        target_pos: Point,
        robot_type: str = "ground",
    ) -> Optional[List[Point]]:
        """
        Calculate a safe detour path avoiding obstacles.

        Args:
            robot_id: ID of the robot
            current_pos: Current position
            target_pos: Target position
            robot_type: Type of robot (ground, aerial, manipulator)

        Returns:
            List of waypoints or None if no path found
        """
        # Try MAPF solver first if available
        if self._mapf_solver:
            mapf_path = self.request_mapf_path(robot_id, current_pos, target_pos)
            if mapf_path:
                return mapf_path

        # Fallback to simple path planning
        max_detour = self._get_max_detour_for_type(robot_type)

        # Check direct path first
        if self._is_path_clear(current_pos, target_pos):
            return [current_pos, target_pos]

        # Try simple arc detour
        midpoint = Point()
        midpoint.x = (current_pos.x + target_pos.x) / 2
        midpoint.y = (current_pos.y + target_pos.y) / 2
        midpoint.z = (current_pos.z + target_pos.z) / 2

        # Offset perpendicular to direct line
        detour_path = [current_pos, midpoint, target_pos]

        if self._is_path_clear_multipoint(detour_path):
            return detour_path

        # No clear path found
        self._record_evasion_failure(robot_id)
        return None

    def _get_max_detour_for_type(self, robot_type: str) -> float:
        """Get maximum detour distance based on robot type."""
        type_limits = {
            "aerial": 5.0,  # Drones more maneuverable
            "ground": 2.0,  # Ground robots limited
            "manipulator": 0.5,  # Manipulators workspace constrained
        }
        return type_limits.get(robot_type, 2.0)

    def _is_path_clear(self, start: Point, end: Point) -> bool:
        """Check if a straight path is clear of obstacles."""
        # Simple collision check against all obstacles
        for obstacle_id, obstacle in self.obstacle_database.items():
            obs_pos = obstacle["position"]
            obs_dims = obstacle["dimensions"]

            # Check if line segment intersects obstacle bounding box
            if self._line_intersects_box(start, end, obs_pos, obs_dims):
                return False

        return True

    def _is_path_clear_multipoint(self, path: List[Point]) -> bool:
        """Check if a multi-segment path is clear."""
        for i in range(len(path) - 1):
            if not self._is_path_clear(path[i], path[i + 1]):
                return False
        return True

    def _line_intersects_box(
        self,
        start: Point,
        end: Point,
        box_center: Point,
        box_dims: Tuple[float, float, float],
    ) -> bool:
        """
        Check if line segment intersects axis-aligned bounding box.
        Simplified intersection test.
        """
        # Add safety margin to box
        margin = self.safety_margin
        half_x = box_dims[0] / 2 + margin
        half_y = box_dims[1] / 2 + margin
        half_z = box_dims[2] / 2 + margin

        # Check if line passes through expanded box
        # (Simplified - just check endpoints and midpoint)
        points_to_check = [
            start,
            end,
            Point(
                x=(start.x + end.x) / 2,
                y=(start.y + end.y) / 2,
                z=(start.z + end.z) / 2,
            ),
        ]

        for point in points_to_check:
            if (
                abs(point.x - box_center.x) < half_x
                and abs(point.y - box_center.y) < half_y
                and abs(point.z - box_center.z) < half_z
            ):
                return True

        return False

    def _record_evasion_failure(self, robot_id: str):
        """Record evasion failure for a robot."""
        if robot_id not in self.evasion_failures:
            self.evasion_failures[robot_id] = 0

        self.evasion_failures[robot_id] += 1

        if self.evasion_failures[robot_id] >= self.fallback_threshold:
            self.node.get_logger().error(
                f"Robot {robot_id} reached evasion failure threshold ({self.fallback_threshold})"
            )
            # Trigger user notification

    def reset_evasion_failures(self, robot_id: str):
        """Reset evasion failure count for a robot."""
        if robot_id in self.evasion_failures:
            self.evasion_failures[robot_id] = 0

    def handle_deadlock(self, robot_ids: List[str]):
        """
        Handle deadlock situation where robots are blocking each other.

        Args:
            robot_ids: List of robots involved in deadlock
        """
        # Simple resolution: lowest priority robot backs off
        if len(robot_ids) < 2:
            return

        # Get priorities
        priorities = {}
        for robot_id in robot_ids:
            intent = self.evasion_intents.get(robot_id)
            priorities[robot_id] = intent["priority"] if intent else 0

        # Find lowest priority robot
        lowest_priority_robot = min(priorities.keys(), key=lambda r: priorities[r])

        # Cancel that robot's evasion
        self.release_path_reservation(lowest_priority_robot)

        self.node.get_logger().warn(f"Deadlock resolved: {lowest_priority_robot} backs off")

    def handle_collision(self, robot1: str, robot2: str, collision_data: dict):
        """
        Handle collision event from UE5 or other source.

        Args:
            robot1: First robot ID
            robot2: Second robot ID
            collision_data: Collision details
        """
        self.node.get_logger().error(f"COLLISION: {robot1} and {robot2}")

        # Release both reservations to allow replanning
        self.release_path_reservation(robot1)
        self.release_path_reservation(robot2)

        # Reset failure counts - new situation
        self.reset_evasion_failures(robot1)
        self.reset_evasion_failures(robot2)

    def get_evasion_status(self, robot_id: str) -> Optional[str]:
        """Get evasion status for a robot."""
        intent = self.evasion_intents.get(robot_id)
        return intent["status"] if intent else None
