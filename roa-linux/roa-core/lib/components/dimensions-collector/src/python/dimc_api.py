"""
DIMC API v2.0 - Public Interface for ROA Components

This module provides the stable public API for interacting with DIMC.
Other ROA components (FTI, ROC, Webthread, COMC) should use this API
rather than accessing dimc_core directly.

Architecture:
    ROA Component → DIMC_API → DimensionsCollector → C++ Plugin

Usage:
    from dimc_api import DIMC_API
    
    dimc = DIMC_API()
    dimc.initialize()
    
    # ROC usage
    position = dimc.get_robot_position('robot_1')
    
    # Webthread/Evade usage
    recommendation = dimc.evade.get_recommendation('robot_1')
    if recommendation.action == 'emergency_stop':
        robot.stop()
"""

from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import logging

# Import core implementation
from .dimc_core import (
    DimensionsCollector,
    RobotType,
    RobotDimensions,
    RobotInfo,
    CollisionRisk,
)
from .sensor_simulation import (
    LidarScanData,
    ObstacleData,
    ObstacleType,
    SensorType,
)


# ============================================================================
# API DATA TYPES
# ============================================================================

@dataclass
class EvadeRecommendation:
    """Evade action recommendation for autonomous navigation"""
    robot_id: str
    risk_level: CollisionRisk
    action: str  # 'emergency_stop', 'slow_stop', 'reduce_speed', 'caution', 'continue'
    slowdown_factor: float  # 0.0 to 1.0
    reason: str
    nearest_obstacle_distance_m: Optional[float]
    robot_obstacles_count: int
    timestamp: float


@dataclass
class EnvironmentScan:
    """Complete environment scan for ADM navigation"""
    robot_id: str
    timestamp: float
    position: Tuple[float, float, float]
    orientation: Tuple[float, float, float, float]
    velocity: Tuple[float, float, float]
    obstacles: List[ObstacleData]
    lidar_available: bool
    lidar_ray_count: int
    collision_risk_level: CollisionRisk
    safe_to_move: bool


@dataclass
class CalibrationResult:
    """Evade subsystem calibration result"""
    robot_id: str
    detection_range_m: float
    update_rate_hz: float
    safety_zones: List[Dict[str, Any]]
    sensors_active: bool
    calibration_status: str  # 'success', 'warning', 'failed'
    timestamp: float


# ============================================================================
# EVADE SUBSYSTEM API
# ============================================================================

class EvadeAPI:
    """
    API for Evade subsystem (Webthread)
    
    Provides obstacle detection and collision avoidance interface
    for autonomous navigation in ADM mode.
    """
    
    def __init__(self, core: DimensionsCollector):
        self._core = core
        self._logger = logging.getLogger('DIMC.EvadeAPI')
    
    def calibrate(self, robot_id: str) -> CalibrationResult:
        """
        Calibrate obstacle detection for a robot
        
        Call this during Webthread startup to configure Evade subsystem.
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            CalibrationResult with configuration details
            
        Raises:
            RobotNotFoundError: If robot not registered
        """
        result = self._core.calibrate_evade_subsystem(robot_id)
        return CalibrationResult(
            robot_id=result['robot_id'],
            detection_range_m=result['detection_range_m'],
            update_rate_hz=result['update_rate_hz'],
            safety_zones=result['safety_zones'],
            sensors_active=result['sensors_active'],
            calibration_status=result['calibration_status'],
            timestamp=result['timestamp']
        )
    
    def get_recommendation(self, robot_id: str) -> EvadeRecommendation:
        """
        Get Evade action recommendation based on current obstacles
        
        This is the primary method for Evade decision making.
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            EvadeRecommendation with action, slowdown factor, and reason
            
        Example:
            rec = dimc.evade.get_recommendation('robot_1')
            if rec.action == 'emergency_stop':
                robot.emergency_stop()
            elif rec.action == 'reduce_speed':
                robot.set_speed(robot.speed * rec.slowdown_factor)
        """
        result = self._core.get_evade_recommendation(robot_id)
        return EvadeRecommendation(
            robot_id=result['robot_id'],
            risk_level=self._core.get_collision_risk(robot_id),
            action=result['action'],
            slowdown_factor=result['slowdown_factor'],
            reason=result['reason'],
            nearest_obstacle_distance_m=result['nearest_obstacle_distance_m'],
            robot_obstacles_count=result['robot_obstacles_count'],
            timestamp=result['timestamp']
        )
    
    def get_collision_risk(self, robot_id: str) -> CollisionRisk:
        """
        Get current collision risk level
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            CollisionRisk enum (CRITICAL, HIGH, MEDIUM, LOW, NONE)
        """
        return self._core.get_collision_risk(robot_id)
    
    def is_path_clear(
        self,
        robot_id: str,
        direction: Tuple[float, float, float],
        distance_m: float
    ) -> bool:
        """
        Check if path is clear in given direction
        
        Args:
            robot_id: Robot identifier
            direction: Normalized direction vector (x, y, z)
            distance_m: Distance to check in meters
            
        Returns:
            True if path is clear (no high/critical risk obstacles)
        """
        return self._core.is_path_clear(robot_id, direction, distance_m)
    
    def get_obstacles(self, robot_id: str) -> List[ObstacleData]:
        """
        Get all detected obstacles for a robot
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            List of ObstacleData sorted by distance
        """
        return self._core.get_obstacles(robot_id)
    
    def get_environment_scan(self, robot_id: str) -> EnvironmentScan:
        """
        Get comprehensive environment scan
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            EnvironmentScan with obstacles, LIDAR status, and safety info
        """
        scan = self._core.get_environment_scan(robot_id)
        return EnvironmentScan(
            robot_id=scan['robot_id'],
            timestamp=scan['timestamp'],
            position=scan['position'],
            orientation=scan['orientation'],
            velocity=scan['velocity'],
            obstacles=[
                ObstacleData(
                    obstacle_id=o['id'],
                    position=o['position'],
                    distance=o['distance'],
                    relative_velocity=(0, 0, 0),  # Not in scan dict
                    obstacle_type=ObstacleType(o['type']) if isinstance(o['type'], str) else o['type'],
                    collision_risk=o['collision_risk'],
                    actor_name='',
                    associated_robot_id='',
                    timestamp=scan['timestamp']
                )
                for o in scan['obstacles']
            ],
            lidar_available=scan['lidar_available'],
            lidar_ray_count=scan['lidar_ray_count'],
            collision_risk_level=CollisionRisk(scan['collision_risk_level']),
            safe_to_move=scan['safe_to_move']
        )


# ============================================================================
# TRACKING API
# ============================================================================

class TrackingAPI:
    """
    API for robot tracking queries (ROC, COMC)
    
    Provides position, orientation, velocity, and dimension queries.
    Supports COMC requirements (Section 2.1).
    """
    
    def __init__(self, core: DimensionsCollector):
        self._core = core
        self._logger = logging.getLogger('DIMC.TrackingAPI')
    
    def get_position(self, robot_id: str) -> Optional[Tuple[float, float, float]]:
        """
        Get robot position in meters
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            (x, y, z) tuple in meters, or None if not found
        """
        return self._core.get_position(robot_id)
    
    def get_orientation(self, robot_id: str) -> Optional[Tuple[float, float, float, float]]:
        """
        Get robot orientation as quaternion
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            (x, y, z, w) quaternion, or None if not found
        """
        return self._core.get_orientation(robot_id)
    
    def get_velocity(self, robot_id: str) -> Optional[Tuple[float, float, float]]:
        """
        Get robot linear velocity in m/s
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            (vx, vy, vz) tuple in m/s, or None if not found
        """
        return self._core.get_velocity(robot_id)
    
    def get_angular_velocity(self, robot_id: str) -> Optional[Tuple[float, float, float]]:
        """
        Get robot angular velocity in rad/s (COMC requirement)
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            (wx, wy, wz) tuple in rad/s, or None if not found
        """
        if robot_id in self._core.robots and 'current_state' in self._core.robots[robot_id]:
            return self._core.robots[robot_id]['current_state'].get('angular_velocity', (0, 0, 0))
        return None
    
    def get_full_velocity(self, robot_id: str) -> Optional[Dict]:
        """
        Get complete velocity data for COMC (linear + angular)
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            Dict with linear_x, linear_y, linear_z, angular_z
        """
        linear = self.get_velocity(robot_id)
        angular = self.get_angular_velocity(robot_id)
        
        if linear is None:
            return None
        
        return {
            'linear_x': linear[0],
            'linear_y': linear[1],
            'linear_z': linear[2],
            'angular_z': angular[2] if angular else 0.0
        }
    
    def get_dimensions(self, robot_id: str) -> Optional[RobotDimensions]:
        """
        Get robot dimensions
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            RobotDimensions object, or None if not found
        """
        return self._core.get_dimensions(robot_id)
    
    def get_robot_info(self, robot_id: str) -> Optional[RobotInfo]:
        """
        Get complete robot information
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            RobotInfo with all tracking data, or None if not found
        """
        return self._core.get_robot_info(robot_id)
    
    def get_all_robots(self) -> List[str]:
        """
        Get list of all registered robot IDs
        
        Returns:
            List of robot ID strings
        """
        return self._core.get_all_robots()


# ============================================================================
# COORDINATION API
# ============================================================================

# COMC proximity thresholds (meters) - loaded from config but with defaults
PROXIMITY_CRITICAL = 0.5
PROXIMITY_CAUTION = 1.0
PROXIMITY_WARNING = 2.0


@dataclass
class ProximityAlert:
    """Proximity alert for COMC (Section 2.3)"""
    robot_a: str
    robot_b: str
    distance: float
    alert_level: str  # 'critical', 'caution', 'warning', 'safe'


@dataclass
class FleetPositionData:
    """Fleet-wide position data for COMC (Section 2.5)"""
    timestamp: float
    robots: List[Dict[str, Any]]


@dataclass 
class FleetDistanceData:
    """Fleet-wide distance data for COMC (Section 2.3)"""
    timestamp: float
    distances: Dict[str, float]  # "robot_a:robot_b" -> distance
    proximity_alerts: List[ProximityAlert]


class CoordinationAPI:
    """
    API for multi-robot coordination (COMC)
    
    Provides inter-robot distance queries and proximity checking.
    Supports COMC requirements (Section 2).
    """
    
    def __init__(self, core: DimensionsCollector):
        self._core = core
        self._logger = logging.getLogger('DIMC.CoordinationAPI')
        
        # Load proximity thresholds from config
        proximity_cfg = core.config.get('proximity', {})
        self._proximity_critical = proximity_cfg.get('critical_m', PROXIMITY_CRITICAL)
        self._proximity_caution = proximity_cfg.get('caution_m', PROXIMITY_CAUTION)
        self._proximity_warning = proximity_cfg.get('warning_m', PROXIMITY_WARNING)
    
    def get_distance(self, robot_id_1: str, robot_id_2: str) -> Optional[float]:
        """
        Get distance between two robots in meters
        
        Args:
            robot_id_1: First robot identifier
            robot_id_2: Second robot identifier
            
        Returns:
            Distance in meters, or None if robots not found
        """
        return self._core.get_distance(robot_id_1, robot_id_2)
    
    def get_all_distances(self) -> Dict[Tuple[str, str], float]:
        """
        Get distances between all robot pairs
        
        Returns:
            Dictionary mapping (robot_id_1, robot_id_2) -> distance in meters
        """
        robots = self._core.get_all_robots()
        distances = {}
        
        for i, robot_a in enumerate(robots):
            for robot_b in robots[i+1:]:
                dist = self.get_distance(robot_a, robot_b)
                if dist is not None:
                    distances[(robot_a, robot_b)] = dist
        
        return distances
    
    def get_robots_in_proximity(
        self,
        robot_id: str,
        max_distance_m: float = 2.0
    ) -> List[Tuple[str, float]]:
        """
        Get other robots within specified distance
        
        Args:
            robot_id: Robot identifier
            max_distance_m: Maximum distance in meters
            
        Returns:
            List of (other_robot_id, distance) tuples
        """
        result = []
        all_robots = self._core.get_all_robots()
        
        for other_id in all_robots:
            if other_id == robot_id:
                continue
            
            dist = self.get_distance(robot_id, other_id)
            if dist is not None and dist <= max_distance_m:
                result.append((other_id, dist))
        
        # Sort by distance
        result.sort(key=lambda x: x[1])
        return result
    
    # ========================================================================
    # COMC-SPECIFIC METHODS (Section 2)
    # ========================================================================
    
    def get_fleet_positions(self) -> FleetPositionData:
        """
        Get all robot positions in COMC format (Section 2.5)
        
        Returns:
            FleetPositionData with all robot positions, orientations, velocities
        """
        import time
        
        robots = []
        for robot_id in self._core.get_all_robots():
            info = self._core.get_robot_info(robot_id)
            if info:
                angular_vel = (0, 0, 0)
                if robot_id in self._core.robots and 'current_state' in self._core.robots[robot_id]:
                    angular_vel = self._core.robots[robot_id]['current_state'].get('angular_velocity', (0, 0, 0))
                
                robots.append({
                    'robot_id': robot_id,
                    'position': {
                        'x': info.position[0],
                        'y': info.position[1],
                        'z': info.position[2]
                    },
                    'orientation': {
                        'x': info.orientation[0],
                        'y': info.orientation[1],
                        'z': info.orientation[2],
                        'w': info.orientation[3]
                    },
                    'velocity': {
                        'linear_x': info.velocity[0],
                        'linear_y': info.velocity[1],
                        'linear_z': info.velocity[2],
                        'angular_z': angular_vel[2]
                    }
                })
        
        return FleetPositionData(
            timestamp=time.time(),
            robots=robots
        )
    
    def get_fleet_distances(self) -> FleetDistanceData:
        """
        Get all inter-robot distances with proximity alerts (Section 2.3)
        
        Returns:
            FleetDistanceData with distances and alerts
        """
        import time
        
        all_distances = self.get_all_distances()
        
        # Convert to COMC format
        distances_dict = {}
        alerts = []
        
        for (robot_a, robot_b), distance in all_distances.items():
            key = f"{robot_a}:{robot_b}"
            distances_dict[key] = distance
            
            # Generate alerts
            alert_level = self._get_alert_level(distance)
            if alert_level != 'safe':
                alerts.append(ProximityAlert(
                    robot_a=robot_a,
                    robot_b=robot_b,
                    distance=distance,
                    alert_level=alert_level
                ))
        
        return FleetDistanceData(
            timestamp=time.time(),
            distances=distances_dict,
            proximity_alerts=alerts
        )
    
    def _get_alert_level(self, distance: float) -> str:
        """Determine proximity alert level based on configurable distance thresholds."""
        if distance < self._proximity_critical:
            return 'critical'
        elif distance < self._proximity_caution:
            return 'caution'
        elif distance < self._proximity_warning:
            return 'warning'
        return 'safe'
    
    def get_proximity_alerts(self) -> List[ProximityAlert]:
        """
        Get all active proximity alerts
        
        Returns:
            List of ProximityAlert objects for robots in proximity
        """
        return self.get_fleet_distances().proximity_alerts
    
    def has_critical_proximity(self) -> bool:
        """
        Check if any robots are in critical proximity
        
        Returns:
            True if any robots are < 0.5m apart
        """
        alerts = self.get_proximity_alerts()
        return any(a.alert_level == 'critical' for a in alerts)
    
    def get_obstacles(self) -> List[Dict[str, Any]]:
        """
        Get all detected obstacles for COMC (Section 2.2)
        
        Returns:
            List of obstacle data dictionaries in COMC format
        """
        all_obstacles = []
        
        for robot_id in self._core.get_all_robots():
            obstacles = self._core.get_obstacles(robot_id)
            for obs in obstacles:
                all_obstacles.append({
                    'obstacle_id': obs.obstacle_id,
                    'type': obs.obstacle_type.value,
                    'position': {
                        'x': obs.position[0],
                        'y': obs.position[1],
                        'z': obs.position[2]
                    },
                    'dimensions': {
                        'width': obs.dimensions.width,
                        'height': obs.dimensions.height,
                        'depth': obs.dimensions.depth
                    },
                    'velocity': {
                        'linear_x': obs.relative_velocity[0],
                        'linear_y': obs.relative_velocity[1],
                        'linear_z': obs.relative_velocity[2]
                    },
                    'collision_risk': obs.collision_risk,
                    'timestamp': obs.timestamp
                })
        
        return all_obstacles


# ============================================================================
# SENSOR API
# ============================================================================

class SensorAPI:
    """
    API for sensor data access
    
    Provides access to LIDAR scans and raw sensor data.
    """
    
    def __init__(self, core: DimensionsCollector):
        self._core = core
        self._logger = logging.getLogger('DIMC.SensorAPI')
    
    def get_lidar_scan(
        self,
        robot_id: str,
        sensor_name: str = "DefaultLidar"
    ) -> Optional[LidarScanData]:
        """
        Get latest LIDAR scan for a robot
        
        Args:
            robot_id: Robot identifier
            sensor_name: Sensor name (default: "DefaultLidar")
            
        Returns:
            LidarScanData with ranges and hit points, or None
        """
        return self._core.get_lidar_scan(robot_id, sensor_name)


# ============================================================================
# MAIN API CLASS
# ============================================================================

class DIMC_API:
    """
    Main DIMC API for ROA Components
    
    This is the primary interface for interacting with DIMC.
    Provides namespaced sub-APIs for different use cases:
    
    - tracking: Position/velocity queries (ROC)
    - coordination: Multi-robot distance queries (COMC)
    - evade: Obstacle avoidance (Webthread)
    - sensor: Raw sensor data access
    
    Example Usage:
        # Initialization
        dimc = DIMC_API()
        dimc.initialize()
        
        # ROC: Query robot state
        pos = dimc.tracking.get_position('robot_1')
        info = dimc.tracking.get_robot_info('robot_1')
        
        # COMC: Check inter-robot distances
        dist = dimc.coordination.get_distance('robot_1', 'robot_2')
        nearby = dimc.coordination.get_robots_in_proximity('robot_1', 1.5)
        
        # Webthread: Evade subsystem
        dimc.evade.calibrate('robot_1')
        rec = dimc.evade.get_recommendation('robot_1')
        if rec.action == 'emergency_stop':
            robot.stop()
        
        # Raw sensor access
        scan = dimc.sensor.get_lidar_scan('robot_1')
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize DIMC API
        
        Args:
            config_path: Optional path to configuration directory
        """
        self._logger = logging.getLogger('DIMC.API')
        self._core = DimensionsCollector(config_path=config_path)
        
        # Initialize sub-APIs
        self.tracking = TrackingAPI(self._core)
        self.coordination = CoordinationAPI(self._core)
        self.evade = EvadeAPI(self._core)
        self.sensor = SensorAPI(self._core)
        
        self._logger.info("DIMC API v2.0 initialized")
    
    # ========================================================================
    # LIFECYCLE METHODS
    # ========================================================================
    
    def initialize(self) -> bool:
        """
        Initialize DIMC and all subsystems
        
        Call this before using any DIMC functionality.
        
        Returns:
            True if initialization successful
        """
        return self._core.initialize()
    
    def start(self) -> None:
        """Start DIMC with observability"""
        self._core.start()
    
    def stop(self) -> None:
        """Stop DIMC"""
        self._core.stop()
    
    def shutdown(self) -> None:
        """Shutdown DIMC and cleanup resources"""
        self._core.shutdown()
    
    # ========================================================================
    # REGISTRATION METHODS (Called by FTI via Bridge)
    # ========================================================================
    
    def register_robot(self, robot_id: str, actor_data: Dict[str, Any]) -> bool:
        """
        Register a robot (called by FTI via ROA Bridge)
        
        Args:
            robot_id: Unique robot identifier
            actor_data: Robot configuration from FTI
            
        Returns:
            True if registration successful
        """
        return self._core.register_robot(robot_id, actor_data)
    
    def unregister_robot(self, robot_id: str) -> bool:
        """
        Unregister a robot
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            True if unregistration successful
        """
        return self._core.unregister_robot(robot_id)
    
    # ========================================================================
    # UPDATE METHOD (Called by ROA Bridge)
    # ========================================================================
    
    def update(self, current_time: float, robot_data: Dict[str, Dict]) -> None:
        """
        Update DIMC with data from C++ plugin
        
        This is called by ROA Bridge at ~60Hz with tracking data
        and sensor data from the UE5 C++ plugin.
        
        Args:
            current_time: Current timestamp in seconds
            robot_data: Dictionary of robot_id -> state data
        """
        self._core.update(current_time, robot_data)
    
    # ========================================================================
    # EXPORT METHODS
    # ========================================================================
    
    def export_to_rosbag(self, filename: str) -> bool:
        """Export tracking data to ROS bag file"""
        return self._core.export_to_rosbag(filename)
    
    def export_to_json(self, filename: str) -> bool:
        """Export tracking data to JSON file"""
        return self._core.export_to_json(filename)
    
    def export_to_csv(self, filename: str) -> bool:
        """Export tracking data to CSV file"""
        return self._core.export_to_csv(filename)
    
    # ========================================================================
    # STATUS & DIAGNOSTICS API
    # ========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get overall DIMC status for health monitoring
        
        Returns:
            Status dictionary with:
            - overall_health: 'healthy', 'degraded', 'unhealthy'
            - subsystems: Health of each subsystem
            - statistics: Message counts, uptime
            - resources: CPU/memory usage if available
        """
        return self._core.get_status()
    
    def get_diagnostics(self) -> Dict[str, Any]:
        """
        Get comprehensive diagnostic data for debugging
        
        Returns:
            Diagnostics dictionary with:
            - status: Current health status
            - performance: Timing data for critical paths
            - data_quality: Message validation rates, latency
            - alerts: Recent alerts
            - subsystem_details: Detailed state of each subsystem
        """
        return self._core.get_diagnostics()
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get performance statistics
        
        Returns:
            Statistics dictionary with message counts, timing, etc.
        """
        return self._core.get_statistics()
    
    def get_alerts(self, severity: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get monitoring alerts
        
        Args:
            severity: Filter by severity ('info', 'warning', 'error', 'critical')
            limit: Maximum number of alerts to return
            
        Returns:
            List of alert dictionaries
        """
        return self._core.get_alerts(severity, limit)
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """
        Acknowledge an alert
        
        Args:
            alert_id: Alert identifier
            
        Returns:
            True if alert was found and acknowledged
        """
        return self._core.acknowledge_alert(alert_id)
    
    def is_healthy(self) -> bool:
        """
        Quick health check
        
        Returns:
            True if DIMC is healthy
        """
        return self._core.is_healthy()
    
    def get_bridge_status(self) -> Dict[str, Any]:
        """
        Get UE5 Bridge connection status
        
        Returns:
            Bridge status dictionary
        """
        return self._core.get_bridge_status()
    
    def get_heartbeat_status(self) -> Dict[str, Any]:
        """
        Get Heartbeat agent status
        
        Returns:
            Heartbeat status dictionary
        """
        return self._core.get_heartbeat_status()
    
    # ========================================================================
    # ROC INTEGRATION - Data DIMC needs FROM ROC
    # ========================================================================
    
    def set_robot_status(self, robot_id: str, status: str) -> None:
        """
        Receive robot operational status from ROC
        
        DIMC needs this to:
        - Skip tracking for inactive robots
        - Adjust update rates based on status
        - Handle emergency stop situations
        
        Args:
            robot_id: Robot identifier
            status: One of 'ACTIVE', 'PAUSED', 'STOPPED', 'ESTOPPED', 'UNKNOWN'
        """
        if robot_id in self._core.robots:
            self._core.robots[robot_id]['roc_status'] = status
            
            # If e-stopped, mark velocity as zero
            if status == 'ESTOPPED':
                if 'current_state' in self._core.robots[robot_id]:
                    self._core.robots[robot_id]['current_state']['velocity'] = (0, 0, 0)
                    self._core.robots[robot_id]['current_state']['angular_velocity'] = (0, 0, 0)
            
            self._logger.debug(f"Robot {robot_id} status updated to {status}")
    
    def set_control_mode(self, robot_id: str, mode: str) -> None:
        """
        Receive control mode from ROC
        
        DIMC needs this to:
        - Enable/disable Evade subsystem (only needed in ADM mode)
        - Adjust sensor update rates
        
        Args:
            robot_id: Robot identifier
            mode: One of 'ADM', 'MANUAL', 'REMOTE'
        """
        if robot_id in self._core.robots:
            self._core.robots[robot_id]['control_mode'] = mode
            
            # ADM mode requires more frequent Evade updates
            if mode == 'ADM':
                self._core.obstacle_detection.set_update_rate(robot_id, 30)  # 30 Hz
            else:
                self._core.obstacle_detection.set_update_rate(robot_id, 10)  # 10 Hz
            
            self._logger.debug(f"Robot {robot_id} control mode set to {mode}")
    
    def on_emergency_stop(self, robot_id: str, triggered: bool) -> None:
        """
        Receive emergency stop event from ROC
        
        DIMC needs this to:
        - Immediately update robot state
        - Pause obstacle detection (robot can't move anyway)
        - Log for safety auditing
        
        Args:
            robot_id: Robot identifier
            triggered: True if e-stop triggered, False if released
        """
        if robot_id in self._core.robots:
            self._core.robots[robot_id]['estopped'] = triggered
            self._core.robots[robot_id]['roc_status'] = 'ESTOPPED' if triggered else 'ACTIVE'
            
            if triggered:
                self._logger.warning(f"EMERGENCY STOP triggered for {robot_id}")
                # Zero out velocities
                if 'current_state' in self._core.robots[robot_id]:
                    self._core.robots[robot_id]['current_state']['velocity'] = (0, 0, 0)
                    self._core.robots[robot_id]['current_state']['angular_velocity'] = (0, 0, 0)
            else:
                self._logger.info(f"Emergency stop released for {robot_id}")
    
    def update_joint_states(self, robot_id: str, joint_states: Dict[str, Dict]) -> None:
        """
        Receive joint states from ROC (for arm robots)
        
        DIMC needs this to:
        - Calculate end-effector position for collision detection
        - Track arm workspace for safety zone computation
        
        Args:
            robot_id: Robot identifier
            joint_states: Dictionary of joint_name -> {position, velocity, at_limit}
        """
        if robot_id in self._core.robots:
            self._core.robots[robot_id]['joint_states'] = joint_states
            self._core.robots[robot_id]['joint_states_timestamp'] = self._core.last_update_time
    
    # ========================================================================
    # COMC INTEGRATION - Data DIMC needs FROM COMC
    # ========================================================================
    
    def set_robot_priority(self, robot_id: str, priority: int) -> None:
        """
        Receive robot priority from COMC
        
        DIMC needs this to:
        - Prioritize sensing for higher priority robots
        - Allocate more compute resources to critical robots
        
        Args:
            robot_id: Robot identifier
            priority: Priority level (1=highest, 10=lowest)
        """
        if robot_id in self._core.robots:
            self._core.robots[robot_id]['comc_priority'] = priority
            self._logger.debug(f"Robot {robot_id} priority set to {priority}")
    
    def set_monitoring_zone(self, zone_id: str, bounds: Dict, enhanced: bool = False) -> None:
        """
        Receive monitoring zone definition from COMC
        
        DIMC needs this to:
        - Enable enhanced obstacle detection in critical zones
        - Increase sensing frequency in coordination zones
        
        Args:
            zone_id: Unique zone identifier
            bounds: Zone bounds {min_x, max_x, min_y, max_y, min_z, max_z}
            enhanced: If True, use higher sensing rate in this zone
        """
        if not hasattr(self._core, 'monitoring_zones'):
            self._core.monitoring_zones = {}
        
        self._core.monitoring_zones[zone_id] = {
            'bounds': bounds,
            'enhanced': enhanced
        }
        self._logger.info(f"Monitoring zone {zone_id} configured (enhanced={enhanced})")
    
    def on_robot_added_to_fleet(self, robot_id: str, fleet_id: str) -> None:
        """
        Notification from COMC when robot is added to coordinated fleet
        
        DIMC needs this to:
        - Enable inter-robot distance tracking for this robot
        - Include in fleet-wide publishing
        
        Args:
            robot_id: Robot identifier
            fleet_id: Fleet/group identifier
        """
        if robot_id in self._core.robots:
            self._core.robots[robot_id]['fleet_id'] = fleet_id
            self._core.robots[robot_id]['in_coordinated_fleet'] = True
            self._logger.info(f"Robot {robot_id} added to fleet {fleet_id}")
    
    def on_robot_removed_from_fleet(self, robot_id: str) -> None:
        """
        Notification from COMC when robot is removed from coordinated fleet
        
        Args:
            robot_id: Robot identifier
        """
        if robot_id in self._core.robots:
            self._core.robots[robot_id]['fleet_id'] = None
            self._core.robots[robot_id]['in_coordinated_fleet'] = False
            self._logger.info(f"Robot {robot_id} removed from fleet")
    
    # ========================================================================
    # CONVENIENCE METHODS (Quick access without sub-API)
    # ========================================================================
    
    def get_robot_position(self, robot_id: str) -> Optional[Tuple[float, float, float]]:
        """Convenience: Get robot position in meters"""
        return self.tracking.get_position(robot_id)
    
    def get_robot_info(self, robot_id: str) -> Optional[RobotInfo]:
        """Convenience: Get complete robot information"""
        return self.tracking.get_robot_info(robot_id)
    
    def get_all_robots(self) -> List[str]:
        """Convenience: Get list of all robot IDs"""
        return self.tracking.get_all_robots()


# ============================================================================
# SINGLETON ACCESS (Optional, thread-safe)
# ============================================================================

import threading

_global_dimc_instance: Optional[DIMC_API] = None
_instance_lock = threading.Lock()

def get_dimc_instance(config_path: Optional[Path] = None) -> DIMC_API:
    """
    Get global DIMC instance (singleton pattern, thread-safe).
    
    This provides a convenient way to access DIMC from anywhere
    in the ROA system without passing the instance around.
    
    Args:
        config_path: Optional config path (only used on first call).
                    If provided on subsequent calls with a different path,
                    a warning is logged but the existing instance is returned.
        
    Returns:
        Global DIMC_API instance
        
    Example:
        from dimc_api import get_dimc_instance
        
        dimc = get_dimc_instance()
        position = dimc.get_robot_position('robot_1')
    """
    global _global_dimc_instance
    
    # Double-checked locking pattern for thread-safe singleton
    if _global_dimc_instance is None:
        with _instance_lock:
            if _global_dimc_instance is None:
                _global_dimc_instance = DIMC_API(config_path=config_path)
            elif config_path is not None:
                # Instance exists but different config requested
                logging.getLogger('DIMC.API').warning(
                    f"DIMC instance already exists, ignoring new config_path: {config_path}"
                )
    
    return _global_dimc_instance


def reset_dimc_instance() -> None:
    """
    Reset global DIMC instance (thread-safe).
    
    Useful for testing or reinitialization.
    """
    global _global_dimc_instance
    
    with _instance_lock:
        if _global_dimc_instance is not None:
            _global_dimc_instance.shutdown()
            _global_dimc_instance = None

