"""
Proximity Monitor

Real-time monitoring of distances between robots for collision avoidance.
Enhanced with Time-to-Collision (TTC) calculation and dynamic thresholds.
"""

import math
import time
from dataclasses import dataclass
from typing import Dict, NamedTuple, Optional, Tuple

import rclpy
from geometry_msgs.msg import Point
from rclpy.node import Node


@dataclass
class TTCResult:
    """Time-to-Collision calculation result"""

    time_to_collision: float  # Seconds until collision (inf if no collision)
    collision_point: Optional[Tuple[float, float, float]]  # Predicted collision location
    min_separation: float  # Minimum predicted separation distance
    is_approaching: bool  # True if robots are approaching each other
    braking_distance_required: float  # Distance needed to stop at current speed


@dataclass
class ProximityAlert:
    """Enhanced proximity alert with TTC data"""

    robot_id: str
    distance: float
    approach_velocity: float
    severity: str
    ttc: TTCResult
    recommended_action: str  # "none", "slow", "stop", "evade"


class ProximityMonitor:
    """
    Monitors proximity between robots and generates alerts.
    Enhanced with Time-to-Collision (TTC) for predictive collision avoidance.
    """

    # Alert thresholds in meters
    THRESHOLD_WARNING = 0.5  # Yellow alert
    THRESHOLD_CAUTION = 0.3  # Orange alert
    THRESHOLD_CRITICAL = 0.1  # Red alert

    # TTC thresholds in seconds
    TTC_WARNING = 5.0  # 5 seconds to collision - warning
    TTC_CAUTION = 3.0  # 3 seconds to collision - slow down
    TTC_CRITICAL = 1.5  # 1.5 seconds to collision - stop/evade
    TTC_EMERGENCY = 0.5  # 0.5 seconds - emergency stop

    # Robot physical parameters (configurable)
    ROBOT_RADIUS = 0.3  # meters
    MAX_DECEL = 1.0  # m/s^2 - maximum safe deceleration
    SAFETY_MARGIN = 0.1  # meters - extra safety buffer

    def __init__(self, node: Node):
        """
        Initialize the proximity monitor.

        Args:
            node: ROS2 node instance
        """
        self.node = node
        self.robot_positions: Dict[str, Point] = {}
        self.robot_velocities: Dict[str, Point] = {}
        self.robot_last_seen: Dict[str, float] = {}  # Timestamp of last update
        self.own_robot_id: Optional[str] = None

        # Emergency stop callback (connected to EmergencyStopSystem)
        self._emergency_stop_callback = None

    def set_robot_id(self, robot_id: str):
        """Set the robot ID for this instance."""
        self.own_robot_id = robot_id

    def set_emergency_stop_callback(self, callback):
        """Set callback for triggering emergency stop"""
        self._emergency_stop_callback = callback

    def update_robot_position(self, robot_id: str, position: Point):
        """
        Update position for a robot.

        Args:
            robot_id: ID of the robot
            position: Current position
        """
        self.robot_positions[robot_id] = position
        self.robot_last_seen[robot_id] = time.time()

    def update_robot_velocity(self, robot_id: str, velocity: Point):
        """
        Update velocity for a robot.

        Args:
            robot_id: ID of the robot
            velocity: Current velocity vector
        """
        self.robot_velocities[robot_id] = velocity

    def calculate_distance(self, pos1: Point, pos2: Point) -> float:
        """
        Calculate Euclidean distance between two points.

        Args:
            pos1: First position
            pos2: Second position

        Returns:
            Distance in meters
        """
        dx = pos1.x - pos2.x
        dy = pos1.y - pos2.y
        dz = pos1.z - pos2.z
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def get_robot_speed(self, robot_id: str) -> float:
        """Get the speed (magnitude of velocity) for a robot"""
        vel = self.robot_velocities.get(robot_id)
        if not vel:
            return 0.0
        return math.sqrt(vel.x**2 + vel.y**2 + vel.z**2)

    def calculate_braking_distance(self, speed: float) -> float:
        """
        Calculate distance required to stop at given speed.
        Uses kinematic equation: d = v^2 / (2*a)

        Args:
            speed: Current speed in m/s

        Returns:
            Braking distance in meters
        """
        if speed <= 0:
            return 0.0
        return (speed**2) / (2 * self.MAX_DECEL) + self.SAFETY_MARGIN

    def calculate_time_to_collision(self, robot_id: str) -> TTCResult:
        """
        Calculate Time-to-Collision (TTC) with another robot.

        Uses relative position and velocity to predict if/when collision occurs.
        Treats robots as spheres with ROBOT_RADIUS.

        Args:
            robot_id: ID of the other robot

        Returns:
            TTCResult with collision prediction data
        """
        # Default result for no collision
        no_collision = TTCResult(
            time_to_collision=float("inf"),
            collision_point=None,
            min_separation=float("inf"),
            is_approaching=False,
            braking_distance_required=0.0,
        )

        if self.own_robot_id not in self.robot_positions or robot_id not in self.robot_positions:
            return no_collision

        own_pos = self.robot_positions[self.own_robot_id]
        other_pos = self.robot_positions[robot_id]
        own_vel = self.robot_velocities.get(self.own_robot_id, Point())
        other_vel = self.robot_velocities.get(robot_id, Point())

        # Relative position (other relative to self)
        rx = other_pos.x - own_pos.x
        ry = other_pos.y - own_pos.y
        rz = other_pos.z - own_pos.z

        # Relative velocity (other relative to self)
        vx = other_vel.x - own_vel.x
        vy = other_vel.y - own_vel.y
        vz = other_vel.z - own_vel.z

        # Calculate approach velocity (positive = approaching)
        rel_pos_mag = math.sqrt(rx * rx + ry * ry + rz * rz)
        rel_vel_mag = math.sqrt(vx * vx + vy * vy + vz * vz)

        if rel_pos_mag < 0.001:
            # Already colliding
            return TTCResult(
                time_to_collision=0.0,
                collision_point=(own_pos.x, own_pos.y, own_pos.z),
                min_separation=0.0,
                is_approaching=True,
                braking_distance_required=0.0,
            )

        # Dot product of relative position and velocity
        # Negative means approaching
        dot_rv = rx * vx + ry * vy + rz * vz
        is_approaching = dot_rv < 0

        if not is_approaching:
            # Moving apart - no collision predicted
            return TTCResult(
                time_to_collision=float("inf"),
                collision_point=None,
                min_separation=rel_pos_mag,  # Current distance is minimum
                is_approaching=False,
                braking_distance_required=0.0,
            )

        # Combined radius (collision distance)
        combined_radius = 2 * self.ROBOT_RADIUS + self.SAFETY_MARGIN

        # Solve quadratic for time when |r + v*t| = combined_radius
        # |r + v*t|^2 = combined_radius^2
        # |r|^2 + 2*t*(r·v) + t^2*|v|^2 = combined_radius^2

        a = vx * vx + vy * vy + vz * vz
        b = 2 * (rx * vx + ry * vy + rz * vz)
        c = rx * rx + ry * ry + rz * rz - combined_radius * combined_radius

        if a < 0.0001:
            # Essentially stationary relative to each other
            min_sep = rel_pos_mag - combined_radius
            return TTCResult(
                time_to_collision=float("inf"),
                collision_point=None,
                min_separation=max(0, min_sep),
                is_approaching=is_approaching,
                braking_distance_required=0.0,
            )

        discriminant = b * b - 4 * a * c

        if discriminant < 0:
            # No collision - paths don't intersect within collision radius
            # Find time of closest approach: t = -b/(2a)
            t_closest = -b / (2 * a) if a > 0.0001 else 0

            if t_closest > 0:
                # Calculate minimum separation at closest approach
                px = rx + vx * t_closest
                py = ry + vy * t_closest
                pz = rz + vz * t_closest
                min_sep = math.sqrt(px * px + py * py + pz * pz)
            else:
                min_sep = rel_pos_mag

            return TTCResult(
                time_to_collision=float("inf"),
                collision_point=None,
                min_separation=max(0, min_sep - combined_radius),
                is_approaching=is_approaching,
                braking_distance_required=0.0,
            )

        # Collision will occur - find earliest time
        sqrt_disc = math.sqrt(discriminant)
        t1 = (-b - sqrt_disc) / (2 * a)
        t2 = (-b + sqrt_disc) / (2 * a)

        # Take the earliest positive time
        if t1 > 0:
            ttc = t1
        elif t2 > 0:
            ttc = t2
        else:
            # Collision in past
            return no_collision

        # Calculate collision point
        col_x = own_pos.x + own_vel.x * ttc
        col_y = own_pos.y + own_vel.y * ttc
        col_z = own_pos.z + own_vel.z * ttc

        # Calculate braking distance required
        own_speed = self.get_robot_speed(self.own_robot_id)
        braking_dist = self.calculate_braking_distance(own_speed)

        return TTCResult(
            time_to_collision=ttc,
            collision_point=(col_x, col_y, col_z),
            min_separation=0.0,  # Will collide
            is_approaching=True,
            braking_distance_required=braking_dist,
        )

    def calculate_approach_velocity(self, robot_id: str) -> float:
        """
        Calculate approach velocity towards another robot.
        Positive = approaching, negative = moving away

        Args:
            robot_id: ID of the other robot

        Returns:
            Approach velocity in m/s
        """
        if (
            self.own_robot_id not in self.robot_positions
            or robot_id not in self.robot_positions
            or self.own_robot_id not in self.robot_velocities
            or robot_id not in self.robot_velocities
        ):
            return 0.0

        own_pos = self.robot_positions[self.own_robot_id]
        other_pos = self.robot_positions[robot_id]
        own_vel = self.robot_velocities.get(self.own_robot_id, Point())
        other_vel = self.robot_velocities.get(robot_id, Point())

        # Calculate relative position vector
        dx = other_pos.x - own_pos.x
        dy = other_pos.y - own_pos.y
        dz = other_pos.z - own_pos.z
        distance = math.sqrt(dx * dx + dy * dy + dz * dz)

        if distance < 0.001:  # Avoid division by zero
            return 0.0

        # Normalize direction vector
        dir_x = dx / distance
        dir_y = dy / distance
        dir_z = dz / distance

        # Calculate relative velocity
        rel_vel_x = other_vel.x - own_vel.x
        rel_vel_y = other_vel.y - own_vel.y
        rel_vel_z = other_vel.z - own_vel.z

        # Project relative velocity onto direction vector
        approach_vel = -(rel_vel_x * dir_x + rel_vel_y * dir_y + rel_vel_z * dir_z)

        return approach_vel

    def get_dynamic_threshold(self, ttc: TTCResult, base_threshold: float) -> float:
        """
        Calculate dynamic threshold based on TTC and speed.
        Increases threshold when approaching fast.

        Args:
            ttc: Time-to-collision result
            base_threshold: Static threshold value

        Returns:
            Adjusted threshold in meters
        """
        if not ttc.is_approaching:
            return base_threshold

        # Increase threshold based on braking distance
        return max(base_threshold, ttc.braking_distance_required)

    def determine_recommended_action(self, distance: float, ttc: TTCResult) -> str:
        """
        Determine recommended action based on distance and TTC.

        Args:
            distance: Current distance to other robot
            ttc: Time-to-collision result

        Returns:
            Recommended action: "none", "slow", "stop", "evade"
        """
        # Check TTC-based thresholds first (predictive)
        if ttc.time_to_collision < self.TTC_EMERGENCY:
            return "evade"
        elif ttc.time_to_collision < self.TTC_CRITICAL:
            return "stop"
        elif ttc.time_to_collision < self.TTC_CAUTION:
            return "slow"

        # Check distance-based thresholds (reactive)
        if distance < self.THRESHOLD_CRITICAL:
            return "stop"
        elif distance < self.THRESHOLD_CAUTION:
            return "slow"

        return "none"

    def get_proximity_alert(self, robot_id: str) -> Optional[ProximityAlert]:
        """
        Check if a proximity alert should be generated for a robot.
        Enhanced with TTC and recommended actions.

        Args:
            robot_id: ID of the robot to check

        Returns:
            ProximityAlert or None if no alert needed
        """
        if self.own_robot_id not in self.robot_positions or robot_id not in self.robot_positions:
            return None

        distance = self.calculate_distance(
            self.robot_positions[self.own_robot_id], self.robot_positions[robot_id]
        )

        approach_velocity = self.calculate_approach_velocity(robot_id)
        ttc = self.calculate_time_to_collision(robot_id)

        # Get dynamic thresholds
        warning_thresh = self.get_dynamic_threshold(ttc, self.THRESHOLD_WARNING)
        caution_thresh = self.get_dynamic_threshold(ttc, self.THRESHOLD_CAUTION)
        critical_thresh = self.get_dynamic_threshold(ttc, self.THRESHOLD_CRITICAL)

        # Determine severity based on distance and TTC
        if distance < critical_thresh or ttc.time_to_collision < self.TTC_CRITICAL:
            severity = "critical"
        elif distance < caution_thresh or ttc.time_to_collision < self.TTC_CAUTION:
            severity = "caution"
        elif distance < warning_thresh or ttc.time_to_collision < self.TTC_WARNING:
            severity = "warning"
        else:
            return None  # No alert needed

        action = self.determine_recommended_action(distance, ttc)

        # Trigger emergency stop if needed
        if action == "evade" and self._emergency_stop_callback:
            self._emergency_stop_callback(robot_id, "proximity", "emergency")

        return ProximityAlert(
            robot_id=robot_id,
            distance=distance,
            approach_velocity=approach_velocity,
            severity=severity,
            ttc=ttc,
            recommended_action=action,
        )

    def get_all_proximity_alerts(self) -> list:
        """
        Get proximity alerts for all nearby robots.

        Returns:
            List of tuples (robot_id, distance, approach_velocity, severity)
            Note: Returns legacy format for backward compatibility
        """
        alerts = []

        if not self.own_robot_id or self.own_robot_id not in self.robot_positions:
            return alerts

        for robot_id in self.robot_positions.keys():
            if robot_id != self.own_robot_id:
                alert = self.get_proximity_alert(robot_id)
                if alert:
                    # Legacy format for backward compatibility
                    alerts.append(
                        (
                            robot_id,
                            alert.distance,
                            alert.approach_velocity,
                            alert.severity,
                        )
                    )

        return alerts

    def get_all_proximity_alerts_enhanced(self) -> list:
        """
        Get enhanced proximity alerts with TTC for all nearby robots.

        Returns:
            List of ProximityAlert objects
        """
        alerts = []

        if not self.own_robot_id or self.own_robot_id not in self.robot_positions:
            return alerts

        for robot_id in self.robot_positions.keys():
            if robot_id != self.own_robot_id:
                alert = self.get_proximity_alert(robot_id)
                if alert:
                    alerts.append(alert)

        return alerts

    def get_distances_to_all(self) -> Dict[str, float]:
        """
        Get distances to all other robots.

        Returns:
            Dictionary mapping robot_id to distance in meters
        """
        distances = {}

        if not self.own_robot_id or self.own_robot_id not in self.robot_positions:
            return distances

        own_pos = self.robot_positions[self.own_robot_id]

        for robot_id, position in self.robot_positions.items():
            if robot_id != self.own_robot_id:
                distances[robot_id] = self.calculate_distance(own_pos, position)

        return distances

    def cleanup_stale_robots(self, max_age_seconds: float = 5.0):
        """
        Remove robots that haven't been seen recently.

        Args:
            max_age_seconds: Maximum time since last update
        """
        current_time = time.time()
        stale_robots = []

        for robot_id, last_seen in self.robot_last_seen.items():
            if robot_id != self.own_robot_id and current_time - last_seen > max_age_seconds:
                stale_robots.append(robot_id)

        for robot_id in stale_robots:
            if robot_id in self.robot_positions:
                del self.robot_positions[robot_id]
            if robot_id in self.robot_velocities:
                del self.robot_velocities[robot_id]
            if robot_id in self.robot_last_seen:
                del self.robot_last_seen[robot_id]

            if self.node:
                self.node.get_logger().debug(f"Removed stale robot: {robot_id}")
