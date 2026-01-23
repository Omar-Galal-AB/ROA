"""
ROS2 Publisher for DIMC

Handles all ROS2 topic publishing for robot tracking data.
Supports COMC requirements with fleet-wide topics.
"""

import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

# ROS2 imports will be added when integrated
# For now, this is a placeholder implementation
try:
    import rclpy
    from geometry_msgs.msg import Point, PoseStamped, TwistStamped
    from rclpy.node import Node
    from std_msgs.msg import Header, String

    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    logging.warning("ROS2 not available - DIMC will run without ROS2 publishing")


class ProximityAlertLevel(Enum):
    """Alert level for proximity warnings (COMC requirement)"""

    CRITICAL = "critical"  # < 0.5m
    CAUTION = "caution"  # < 1.0m
    WARNING = "warning"  # < 2.0m
    SAFE = "safe"  # >= 2.0m


@dataclass
class ProximityAlert:
    """Proximity alert for COMC (Section 2.3)"""

    robot_a: str
    robot_b: str
    distance: float
    alert_level: ProximityAlertLevel
    timestamp: float


class DIMCPublisher:
    """
    ROS2 Publisher for Dimensions Collector

    Publishes robot tracking data to ROS2 topics at specified rates.
    Supports COMC requirements (Section 2.5):
      - /dimc/fleet/positions (10 Hz) - All robot positions
      - /dimc/fleet/distances (5 Hz) - Inter-robot distances + alerts
    """

    # COMC proximity thresholds (meters)
    PROXIMITY_CRITICAL = 0.5
    PROXIMITY_CAUTION = 1.0
    PROXIMITY_WARNING = 2.0

    def __init__(self, config: Dict):
        """
        Initialize ROS2 publisher

        Args:
            config: DIMC configuration dictionary
        """
        self.logger = logging.getLogger("DIMC.ROS2Publisher")
        self.config = config
        self.node: Optional[Node] = None
        self.publishers: Dict[str, any] = {}

        # Fleet-wide publishers (COMC requirements)
        self._fleet_positions_pub = None
        self._fleet_distances_pub = None
        self._obstacles_pub = None

        # Publishing rates
        self._fleet_positions_interval = 0.1  # 10 Hz
        self._fleet_distances_interval = 0.2  # 5 Hz
        self._obstacles_interval = 0.1  # 10 Hz

        # Last publish times
        self._last_fleet_positions_time = 0.0
        self._last_fleet_distances_time = 0.0
        self._last_obstacles_time = 0.0

        if ROS2_AVAILABLE:
            self._initialize_ros2()
        else:
            self.logger.warning("ROS2 not available - running in standalone mode")

    def _initialize_ros2(self) -> None:
        """Initialize ROS2 node and publishers"""
        try:
            # Initialize ROS2 if not already initialized
            if not rclpy.ok():
                rclpy.init()

            # Create node
            self.node = Node("dimc_publisher")

            # Create fleet-wide publishers (COMC requirements)
            self._fleet_positions_pub = self.node.create_publisher(
                String, "/dimc/fleet/positions", 10
            )
            self._fleet_distances_pub = self.node.create_publisher(
                String, "/dimc/fleet/distances", 10
            )
            self._obstacles_pub = self.node.create_publisher(String, "/dimc/obstacles", 10)

            self.logger.info("ROS2 publisher initialized with fleet topics")

        except Exception as e:
            self.logger.error(f"Failed to initialize ROS2: {e}")
            self.node = None

    def _get_or_create_publisher(self, robot_id: str, topic_suffix: str, msg_type):
        """
        Get or create a publisher for a specific robot topic

        Args:
            robot_id: Robot identifier
            topic_suffix: Topic suffix (e.g., 'pose', 'velocity')
            msg_type: ROS2 message type

        Returns:
            ROS2 publisher
        """
        if not self.node:
            return None

        topic_key = f"{robot_id}/{topic_suffix}"

        if topic_key not in self.publishers:
            topic_name = f"/dimc/robot/{robot_id}/{topic_suffix}"
            self.publishers[topic_key] = self.node.create_publisher(
                msg_type, topic_name, 10  # Queue size
            )
            self.logger.debug(f"Created publisher for {topic_name}")

        return self.publishers[topic_key]

    def publish_pose(
        self,
        robot_id: str,
        position: Tuple[float, float, float],
        orientation: Tuple[float, float, float, float],
        timestamp: float,
    ) -> None:
        """
        Publish robot pose (position + orientation)

        Args:
            robot_id: Robot identifier
            position: (x, y, z) position tuple
            orientation: (x, y, z, w) quaternion tuple
            timestamp: Timestamp in seconds
        """
        if not ROS2_AVAILABLE or not self.node:
            return

        try:
            # Create PoseStamped message
            msg = PoseStamped()
            msg.header = Header()
            msg.header.stamp = self.node.get_clock().now().to_msg()
            msg.header.frame_id = "world"

            # Position
            msg.pose.position.x = position[0]
            msg.pose.position.y = position[1]
            msg.pose.position.z = position[2]

            # Orientation (quaternion)
            msg.pose.orientation.x = orientation[0]
            msg.pose.orientation.y = orientation[1]
            msg.pose.orientation.z = orientation[2]
            msg.pose.orientation.w = orientation[3]

            # Publish
            publisher = self._get_or_create_publisher(robot_id, "pose", PoseStamped)
            if publisher:
                publisher.publish(msg)

        except Exception as e:
            self.logger.error(f"Failed to publish pose for {robot_id}: {e}")

    def publish_velocity(
        self,
        robot_id: str,
        velocity: Tuple[float, float, float],
        timestamp: float,
        angular_velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> None:
        """
        Publish robot velocity (COMC requirement: includes angular_z)

        Args:
            robot_id: Robot identifier
            velocity: (vx, vy, vz) linear velocity tuple in m/s
            timestamp: Timestamp in seconds
            angular_velocity: (wx, wy, wz) angular velocity tuple in rad/s
        """
        if not ROS2_AVAILABLE or not self.node:
            return

        try:
            # Create TwistStamped message
            msg = TwistStamped()
            msg.header = Header()
            msg.header.stamp = self.node.get_clock().now().to_msg()
            msg.header.frame_id = "world"

            # Linear velocity
            msg.twist.linear.x = velocity[0]
            msg.twist.linear.y = velocity[1]
            msg.twist.linear.z = velocity[2]

            # Angular velocity (COMC requirement)
            msg.twist.angular.x = angular_velocity[0]
            msg.twist.angular.y = angular_velocity[1]
            msg.twist.angular.z = angular_velocity[2]

            # Publish
            publisher = self._get_or_create_publisher(robot_id, "velocity", TwistStamped)
            if publisher:
                publisher.publish(msg)

        except Exception as e:
            self.logger.error(f"Failed to publish velocity for {robot_id}: {e}")

    def publish_dimensions(self, robot_id: str, dimensions: Dict[str, float]) -> None:
        """
        Publish robot dimensions

        Args:
            robot_id: Robot identifier
            dimensions: Dictionary with width, height, length, radius
        """
        if not ROS2_AVAILABLE or not self.node:
            return

        # TODO: Create custom message type for RobotDimensions
        # For now, log the dimensions
        self.logger.debug(f"Robot {robot_id} dimensions: {dimensions}")

    def publish_distances(self, distances: Dict[Tuple[str, str], float], timestamp: float) -> None:
        """
        Publish inter-robot distances (COMC requirement Section 2.3)

        Args:
            distances: Dictionary of (robot_id_1, robot_id_2) -> distance
            timestamp: Timestamp in seconds
        """
        if not ROS2_AVAILABLE or not self.node:
            return

        # Rate limit to 5 Hz
        if (timestamp - self._last_fleet_distances_time) < self._fleet_distances_interval:
            return
        self._last_fleet_distances_time = timestamp

        try:
            # Generate proximity alerts
            alerts = []
            for (robot_a, robot_b), distance in distances.items():
                alert_level = self._get_alert_level(distance)
                if alert_level != ProximityAlertLevel.SAFE:
                    alerts.append(
                        {
                            "robot_a": robot_a,
                            "robot_b": robot_b,
                            "distance": distance,
                            "alert_level": alert_level.value,
                        }
                    )

            # Build COMC-format message (Section 2.3)
            fleet_distances = {
                "timestamp": timestamp,
                "distances": {f"{ra}:{rb}": dist for (ra, rb), dist in distances.items()},
                "proximity_alerts": alerts,
            }

            msg = String()
            msg.data = json.dumps(fleet_distances)

            if self._fleet_distances_pub:
                self._fleet_distances_pub.publish(msg)

        except Exception as e:
            self.logger.error(f"Failed to publish fleet distances: {e}")

    def _get_alert_level(self, distance: float) -> ProximityAlertLevel:
        """Determine proximity alert level based on distance"""
        if distance < self.PROXIMITY_CRITICAL:
            return ProximityAlertLevel.CRITICAL
        elif distance < self.PROXIMITY_CAUTION:
            return ProximityAlertLevel.CAUTION
        elif distance < self.PROXIMITY_WARNING:
            return ProximityAlertLevel.WARNING
        return ProximityAlertLevel.SAFE

    def publish_fleet_positions(self, robots: Dict[str, Dict], timestamp: float) -> None:
        """
        Publish all robot positions in a single message (COMC requirement Section 2.5)

        Topic: /dimc/fleet/positions @ 10 Hz

        Args:
            robots: Dictionary of robot_id -> robot state data
            timestamp: Current timestamp in seconds
        """
        if not ROS2_AVAILABLE or not self.node:
            return

        # Rate limit to 10 Hz
        if (timestamp - self._last_fleet_positions_time) < self._fleet_positions_interval:
            return
        self._last_fleet_positions_time = timestamp

        try:
            # Build COMC-format message (Section 2.1)
            fleet_data = {"timestamp": timestamp, "robots": []}

            for robot_id, robot_info in robots.items():
                state = robot_info.get("current_state", {})
                position = state.get("position", (0, 0, 0))
                orientation = state.get("orientation", (0, 0, 0, 1))
                velocity = state.get("velocity", (0, 0, 0))
                angular_velocity = state.get("angular_velocity", (0, 0, 0))

                fleet_data["robots"].append(
                    {
                        "robot_id": robot_id,
                        "position": {
                            "x": position[0],
                            "y": position[1],
                            "z": position[2],
                        },
                        "orientation": {
                            "x": orientation[0],
                            "y": orientation[1],
                            "z": orientation[2],
                            "w": orientation[3],
                        },
                        "velocity": {
                            "linear_x": velocity[0],
                            "linear_y": velocity[1],
                            "linear_z": velocity[2],
                            "angular_z": (
                                angular_velocity[2] if len(angular_velocity) > 2 else 0.0
                            ),
                        },
                    }
                )

            msg = String()
            msg.data = json.dumps(fleet_data)

            if self._fleet_positions_pub:
                self._fleet_positions_pub.publish(msg)

        except Exception as e:
            self.logger.error(f"Failed to publish fleet positions: {e}")

    def publish_obstacles(self, obstacles: List[Dict], timestamp: float) -> None:
        """
        Publish obstacle detection data (COMC requirement Section 2.2)

        Topic: /dimc/obstacles @ 10 Hz

        Args:
            obstacles: List of obstacle data dictionaries
            timestamp: Current timestamp in seconds
        """
        if not ROS2_AVAILABLE or not self.node:
            return

        # Rate limit to 10 Hz
        if (timestamp - self._last_obstacles_time) < self._obstacles_interval:
            return
        self._last_obstacles_time = timestamp

        try:
            # Build COMC-format message (Section 2.2)
            obstacles_msg = {"timestamp": timestamp, "obstacles": []}

            for obs in obstacles:
                obstacles_msg["obstacles"].append(
                    {
                        "obstacle_id": obs.get("obstacle_id", ""),
                        "type": obs.get("type", "unknown"),
                        "position": {
                            "x": obs.get("position", (0, 0, 0))[0],
                            "y": obs.get("position", (0, 0, 0))[1],
                            "z": obs.get("position", (0, 0, 0))[2],
                        },
                        "dimensions": {
                            "width": obs.get("dimensions", {}).get("width", 0),
                            "height": obs.get("dimensions", {}).get("height", 0),
                            "depth": obs.get("dimensions", {}).get("depth", 0),
                        },
                        "velocity": {
                            "linear_x": obs.get("velocity", (0, 0, 0))[0],
                            "linear_y": obs.get("velocity", (0, 0, 0))[1],
                            "linear_z": obs.get("velocity", (0, 0, 0))[2],
                        },
                        "collision_risk": obs.get("collision_risk", 0.0),
                    }
                )

            msg = String()
            msg.data = json.dumps(obstacles_msg)

            if self._obstacles_pub:
                self._obstacles_pub.publish(msg)

        except Exception as e:
            self.logger.error(f"Failed to publish obstacles: {e}")

    def publish_robot_registration(self, robot_id: str, dimensions: Dict[str, float]) -> None:
        """
        Publish robot registration event

        Args:
            robot_id: Robot identifier
            dimensions: Initial dimensions
        """
        self.logger.info(f"Publishing registration for robot: {robot_id}")
        # TODO: Publish to /dimc/events topic

    def shutdown(self) -> None:
        """Shutdown ROS2 publisher and cleanup"""
        if self.node:
            self.logger.info("Shutting down ROS2 publisher")
            self.node.destroy_node()

        if ROS2_AVAILABLE and rclpy.ok():
            rclpy.shutdown()
