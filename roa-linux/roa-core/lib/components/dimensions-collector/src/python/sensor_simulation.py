"""
Sensor Simulation Layer for DIMC v2.0

Receives sensor data from UE5 C++ plugin (CPU Raycast LIDAR).
Provides data for obstacle detection, Evade subsystem, and safety systems.

ARCHITECTURE NOTE:
- All sensor simulation (raycasting) happens in UE5/C++
- This Python layer receives processed data from C++ via ROA Bridge
- ROS2 publishing happens on Linux side only
"""

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class SensorType(Enum):
    """Sensor type enumeration - matches C++ ESensorType"""

    LIDAR = "lidar"
    DEPTH_CAMERA = "depth_camera"
    ULTRASONIC = "ultrasonic"
    IMU = "imu"
    ENCODER = "encoder"
    PROXIMITY_SENSOR = "proximity_sensor"
    CONTACT_SENSOR = "contact_sensor"


class ObstacleType(Enum):
    """Obstacle classification - matches C++ EObstacleType"""

    STATIC = "static"
    DYNAMIC = "dynamic"
    ROBOT = "robot"
    BOUNDARY = "boundary"
    UNKNOWN = "unknown"


@dataclass
class LidarScanData:
    """Structured LIDAR scan data from C++ plugin"""

    timestamp: float = 0.0
    ranges: List[float] = field(default_factory=list)
    intensities: List[float] = field(default_factory=list)
    hit_points: List[Tuple[float, float, float]] = field(default_factory=list)
    hit_actor_names: List[str] = field(default_factory=list)
    angle_min: float = -3.14159
    angle_max: float = 3.14159
    angle_increment: float = 0.01745
    range_min: float = 0.05  # 5cm in meters
    range_max: float = 10.0  # 10m

    @classmethod
    def from_cpp_result(cls, cpp_data: Dict) -> "LidarScanData":
        """Create from C++ FLidarScanResult data"""
        # Convert cm to meters for ROS2 compatibility
        ranges_m = [r / 100.0 for r in cpp_data.get("ranges", [])]
        hit_points_m = [
            (p[0] / 100.0, p[1] / 100.0, p[2] / 100.0) for p in cpp_data.get("hit_points", [])
        ]

        return cls(
            timestamp=cpp_data.get("timestamp", time.time()),
            ranges=ranges_m,
            intensities=cpp_data.get("intensities", []),
            hit_points=hit_points_m,
            hit_actor_names=cpp_data.get("hit_actor_names", []),
            angle_min=cpp_data.get("angle_min", -3.14159),
            angle_max=cpp_data.get("angle_max", 3.14159),
            angle_increment=cpp_data.get("angle_increment", 0.01745),
            range_min=cpp_data.get("range_min", 5.0) / 100.0,
            range_max=cpp_data.get("range_max", 1000.0) / 100.0,
        )


@dataclass
class ObstacleDimensions:
    """Obstacle dimensions for COMC path planning"""

    width: float = 0.0
    height: float = 0.0
    depth: float = 0.0
    radius: float = 0.0  # For spherical approximation


@dataclass
class ObstacleData:
    """Structured obstacle data from C++ plugin"""

    obstacle_id: str = ""
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    distance: float = 0.0
    relative_velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    obstacle_type: ObstacleType = ObstacleType.UNKNOWN
    collision_risk: float = 0.0
    actor_name: str = ""
    associated_robot_id: str = ""
    timestamp: float = 0.0
    # COMC requirements: obstacle dimensions for path planning
    dimensions: ObstacleDimensions = field(default_factory=ObstacleDimensions)

    @classmethod
    def from_cpp_result(cls, cpp_data: Dict) -> "ObstacleData":
        """Create from C++ FObstacleInfo data"""
        # Convert cm to meters
        pos = cpp_data.get("position", (0, 0, 0))
        vel = cpp_data.get("relative_velocity", (0, 0, 0))

        # Map C++ obstacle type to Python enum
        type_map = {
            0: ObstacleType.STATIC,
            1: ObstacleType.DYNAMIC,
            2: ObstacleType.ROBOT,
            3: ObstacleType.BOUNDARY,
            4: ObstacleType.UNKNOWN,
            "Static": ObstacleType.STATIC,
            "Dynamic": ObstacleType.DYNAMIC,
            "Robot": ObstacleType.ROBOT,
            "Boundary": ObstacleType.BOUNDARY,
        }
        obs_type = type_map.get(cpp_data.get("type", 4), ObstacleType.UNKNOWN)

        # Parse dimensions (COMC requirement)
        dims = cpp_data.get("dimensions", {})
        dimensions = ObstacleDimensions(
            width=dims.get("width", 0.0) / 100.0,  # cm to m
            height=dims.get("height", 0.0) / 100.0,
            depth=dims.get("depth", 0.0) / 100.0,
            radius=dims.get("radius", 0.0) / 100.0,
        )

        return cls(
            obstacle_id=cpp_data.get("obstacle_id", ""),
            position=(pos[0] / 100.0, pos[1] / 100.0, pos[2] / 100.0),
            distance=cpp_data.get("distance", 0.0) / 100.0,
            relative_velocity=(vel[0] / 100.0, vel[1] / 100.0, vel[2] / 100.0),
            obstacle_type=obs_type,
            collision_risk=cpp_data.get("collision_risk", 0.0),
            actor_name=cpp_data.get("actor_name", ""),
            associated_robot_id=cpp_data.get("associated_robot_id", ""),
            timestamp=cpp_data.get("timestamp", time.time()),
            dimensions=dimensions,
        )


class SensorDataReceiver:
    """
    Receives sensor data from UE5 C++ plugin via ROA Bridge

    This replaces the old simulation approach - all raycasting
    now happens in C++ and we just receive the results.
    """

    def __init__(self, config: Dict = None):
        """
        Initialize sensor data receiver

        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.logger = logging.getLogger("DIMC.SensorDataReceiver")

        # Data storage
        self.latest_lidar_scans: Dict[str, LidarScanData] = {}
        self.latest_obstacles: Dict[str, List[ObstacleData]] = {}
        self.registered_sensors: Dict[str, Dict] = {}

        # Load default profiles
        self._load_default_profiles()

        self.logger.info("SensorDataReceiver initialized")

    def _load_default_profiles(self):
        """Load default sensor profiles from config file"""
        config_path = (
            Path(__file__).parent.parent.parent / "config" / "default_sensor_profiles.json"
        )
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    self.default_profiles = json.load(f)
                self.logger.info(f"Loaded default profiles from {config_path}")
            except Exception as e:
                self.logger.warning(f"Failed to load default profiles: {e}")
                self.default_profiles = {}
        else:
            self.logger.warning(f"Default profiles not found at {config_path}")
            self.default_profiles = {}

    def receive_lidar_scan(self, robot_id: str, sensor_name: str, cpp_data: Dict) -> LidarScanData:
        """
        Receive LIDAR scan data from C++ plugin

        Args:
            robot_id: Robot identifier
            sensor_name: Sensor name
            cpp_data: Raw data from C++ FLidarScanResult

        Returns:
            Processed LidarScanData
        """
        scan = LidarScanData.from_cpp_result(cpp_data)
        key = f"{robot_id}_{sensor_name}"
        self.latest_lidar_scans[key] = scan

        self.logger.debug(f"Received LIDAR scan for {key}: {len(scan.ranges)} rays")
        return scan

    def receive_obstacles(self, robot_id: str, cpp_obstacles: List[Dict]) -> List[ObstacleData]:
        """
        Receive obstacle detection results from C++ plugin

        Args:
            robot_id: Robot identifier
            cpp_obstacles: List of raw data from C++ FObstacleInfo

        Returns:
            List of processed ObstacleData
        """
        obstacles = [ObstacleData.from_cpp_result(o) for o in cpp_obstacles]
        self.latest_obstacles[robot_id] = obstacles

        self.logger.debug(f"Received {len(obstacles)} obstacles for {robot_id}")
        return obstacles

    def get_latest_lidar_scan(
        self, robot_id: str, sensor_name: str = "DefaultLidar"
    ) -> Optional[LidarScanData]:
        """Get the most recent LIDAR scan for a robot"""
        key = f"{robot_id}_{sensor_name}"
        return self.latest_lidar_scans.get(key)

    def get_latest_obstacles(self, robot_id: str) -> List[ObstacleData]:
        """Get the most recent obstacle list for a robot"""
        return self.latest_obstacles.get(robot_id, [])

    def get_nearest_obstacle(self, robot_id: str) -> Optional[ObstacleData]:
        """Get the nearest obstacle to a robot"""
        obstacles = self.get_latest_obstacles(robot_id)
        if not obstacles:
            return None
        return min(obstacles, key=lambda o: o.distance)

    def get_collision_risk(self, robot_id: str) -> float:
        """Get the highest collision risk for a robot"""
        obstacles = self.get_latest_obstacles(robot_id)
        if not obstacles:
            return 0.0
        return max(o.collision_risk for o in obstacles)

    def get_obstacles_by_type(
        self, robot_id: str, obstacle_type: ObstacleType
    ) -> List[ObstacleData]:
        """Get obstacles of a specific type"""
        return [o for o in self.get_latest_obstacles(robot_id) if o.obstacle_type == obstacle_type]

    def get_robot_obstacles(self, robot_id: str) -> List[ObstacleData]:
        """Get obstacles that are other robots"""
        return self.get_obstacles_by_type(robot_id, ObstacleType.ROBOT)


# Keep backward compatibility alias
SensorSimulation = SensorDataReceiver
