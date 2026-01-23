"""
Obstacle Detection Module for DIMC v2.0

Processes obstacle data received from UE5 C++ plugin.
Provides real-time obstacle information for the Evade subsystem in ADM mode.

ARCHITECTURE NOTE:
- Obstacle detection and classification happens in UE5/C++ plugin
- This Python layer receives processed data via ROA Bridge
- Provides API for Evade subsystem and path planning
"""

from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import logging
import time

# Import from sensor_simulation for data structures
from .sensor_simulation import ObstacleType, ObstacleData, SensorDataReceiver


class CollisionRisk(Enum):
    """Collision risk levels for Evade subsystem"""
    CRITICAL = "critical"  # Immediate stop required
    HIGH = "high"         # Emergency slowdown
    MEDIUM = "medium"     # Proceed with caution
    LOW = "low"           # Safe to proceed
    NONE = "none"         # No obstacles nearby


@dataclass
class SafetyZone:
    """Safety zone configuration for a robot"""
    name: str = ""
    warning_radius_m: float = 0.5
    stop_radius_m: float = 0.3
    color: str = "#FFFF00"


@dataclass
class RobotSafetyConfig:
    """Safety configuration for a tracked robot"""
    robot_id: str = ""
    safety_zones: List[SafetyZone] = field(default_factory=list)
    max_velocity_mps: float = 1.0
    emergency_stop_enabled: bool = True


class ObstacleDetection:
    """
    Obstacle detection processor for Evade subsystem
    
    Receives obstacle data from C++ plugin via SensorDataReceiver.
    Provides real-time obstacle information for autonomous path planning.
    """
    
    def __init__(self, config: Dict = None, sensor_receiver: Optional[SensorDataReceiver] = None):
        """
        Initialize obstacle detection
        
        Args:
            config: Configuration dictionary
            sensor_receiver: SensorDataReceiver instance (for receiving C++ data)
        """
        self.config = config or {}
        self.logger = logging.getLogger('DIMC.ObstacleDetection')
        
        # Link to sensor data receiver
        self.sensor_receiver = sensor_receiver or SensorDataReceiver(config)
        
        # Detection parameters
        self.enabled = self.config.get('obstacle_detection', True)
        self.detection_range_m = self.config.get('detection_range', 5.0)
        self.update_rate_hz = self.config.get('update_rate_hz', 30)
        
        # Collision risk thresholds (configurable from config)
        collision_cfg = self.config.get('collision', {})
        self.risk_critical_threshold = collision_cfg.get('critical_threshold', 0.9)
        self.risk_high_threshold = collision_cfg.get('high_threshold', 0.7)
        self.risk_medium_threshold = collision_cfg.get('medium_threshold', 0.4)
        
        # Robot tracking
        self.known_robots: Set[str] = set()
        self.robot_safety_configs: Dict[str, RobotSafetyConfig] = {}
        self.robot_positions: Dict[str, Tuple[float, float, float]] = {}
        
        # Obstacle tracking
        self.obstacle_history: Dict[str, List[Tuple[float, List[ObstacleData]]]] = {}
        self.max_history_entries = 100
        
        self.logger.info(f"ObstacleDetection initialized (range: {self.detection_range_m}m)")
        
        # Per-robot update rates (can be adjusted by ROC based on control mode)
        self.robot_update_rates: Dict[str, float] = {}
    
    def set_update_rate(self, robot_id: str, rate_hz: float) -> None:
        """
        Set obstacle detection update rate for a robot
        
        Called by DIMC when ROC reports control mode change.
        ADM mode requires higher update rate for Evade subsystem.
        
        Args:
            robot_id: Robot identifier
            rate_hz: Update rate in Hz (e.g., 30 for ADM, 10 for manual)
        """
        self.robot_update_rates[robot_id] = rate_hz
        self.logger.debug(f"Set update rate for {robot_id} to {rate_hz} Hz")
    
    def get_update_rate(self, robot_id: str) -> float:
        """Get configured update rate for a robot"""
        return self.robot_update_rates.get(robot_id, self.update_rate_hz)
    
    def register_robot(
        self, 
        robot_id: str,
        safety_zones: List[Dict] = None
    ) -> None:
        """
        Register a robot for obstacle detection
        
        Args:
            robot_id: Robot identifier
            safety_zones: Safety zone configurations (from C++ or config)
        """
        self.known_robots.add(robot_id)
        self.obstacle_history[robot_id] = []
        
        # Create safety config
        config = RobotSafetyConfig(robot_id=robot_id)
        if safety_zones:
            for zone in safety_zones:
                # Convert cm to meters
                config.safety_zones.append(SafetyZone(
                    name=zone.get('name', 'Zone'),
                    warning_radius_m=zone.get('warning_radius_cm', 50.0) / 100.0,
                    stop_radius_m=zone.get('stop_radius_cm', 30.0) / 100.0,
                    color=zone.get('color', '#FFFF00')
                ))
        
        self.robot_safety_configs[robot_id] = config
        self.logger.info(f"Registered robot {robot_id} for obstacle detection")
    
    def unregister_robot(self, robot_id: str) -> None:
        """Remove robot from tracking"""
        self.known_robots.discard(robot_id)
        self.robot_safety_configs.pop(robot_id, None)
        self.robot_positions.pop(robot_id, None)
        self.obstacle_history.pop(robot_id, None)
        self.logger.debug(f"Unregistered robot {robot_id}")
    
    def update_robot_position(
        self, 
        robot_id: str, 
        position: Tuple[float, float, float]
    ) -> None:
        """Update known position of a robot (for robot-obstacle classification)"""
        self.robot_positions[robot_id] = position
    
    def receive_obstacle_data(
        self, 
        robot_id: str, 
        cpp_obstacles: List[Dict]
    ) -> List[ObstacleData]:
        """
        Receive obstacle data from C++ plugin
        
        Args:
            robot_id: Robot that detected obstacles
            cpp_obstacles: Raw obstacle data from C++ DetectObstacles
            
        Returns:
            Processed obstacle list
        """
        # Forward to sensor receiver
        obstacles = self.sensor_receiver.receive_obstacles(robot_id, cpp_obstacles)
        
        # Add to history
        timestamp = time.time()
        self.obstacle_history.setdefault(robot_id, []).append((timestamp, obstacles.copy()))
        
        # Trim history
        if len(self.obstacle_history[robot_id]) > self.max_history_entries:
            self.obstacle_history[robot_id] = self.obstacle_history[robot_id][-self.max_history_entries:]
        
        return obstacles
    
    def get_current_obstacles(self, robot_id: str) -> List[ObstacleData]:
        """Get current detected obstacles for a robot"""
        return self.sensor_receiver.get_latest_obstacles(robot_id)
    
    def get_collision_risk_level(self, robot_id: str) -> CollisionRisk:
        """
        Get collision risk level for a robot using configurable thresholds.
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            Collision risk level for Evade subsystem
        """
        risk_value = self.sensor_receiver.get_collision_risk(robot_id)
        
        if risk_value >= self.risk_critical_threshold:
            return CollisionRisk.CRITICAL
        elif risk_value >= self.risk_high_threshold:
            return CollisionRisk.HIGH
        elif risk_value >= self.risk_medium_threshold:
            return CollisionRisk.MEDIUM
        elif risk_value > 0.0:
            return CollisionRisk.LOW
        else:
            return CollisionRisk.NONE
    
    def get_nearest_obstacle(
        self,
        robot_id: str,
        obstacle_type: Optional[ObstacleType] = None
    ) -> Optional[ObstacleData]:
        """
        Get nearest obstacle to robot
        
        Args:
            robot_id: Robot identifier
            obstacle_type: Filter by type (None = all types)
            
        Returns:
            Nearest obstacle or None
        """
        if obstacle_type:
            obstacles = self.sensor_receiver.get_obstacles_by_type(robot_id, obstacle_type)
            if not obstacles:
                return None
            return min(obstacles, key=lambda o: o.distance)
        else:
            return self.sensor_receiver.get_nearest_obstacle(robot_id)
    
    def get_robot_obstacles(self, robot_id: str) -> List[ObstacleData]:
        """Get obstacles that are other robots"""
        return self.sensor_receiver.get_robot_obstacles(robot_id)
    
    def get_obstacles_in_direction(
        self,
        robot_id: str,
        direction: Tuple[float, float, float],
        max_distance_m: float = 2.0,
        cone_angle_deg: float = 45.0
    ) -> List[ObstacleData]:
        """
        Get obstacles in a specific direction
        
        Useful for path planning - check if path is clear in given direction.
        
        Args:
            robot_id: Robot identifier
            direction: Normalized direction vector
            max_distance_m: Maximum distance to check
            cone_angle_deg: Cone angle for direction filtering
            
        Returns:
            List of obstacles in that direction within distance
        """
        import math
        
        obstacles = self.get_current_obstacles(robot_id)
        robot_pos = self.robot_positions.get(robot_id, (0, 0, 0))
        
        # Normalize direction
        dir_mag = math.sqrt(direction[0]**2 + direction[1]**2 + direction[2]**2)
        if dir_mag < 0.001:
            return []
        dir_norm = (direction[0]/dir_mag, direction[1]/dir_mag, direction[2]/dir_mag)
        
        # Calculate cone threshold
        cone_threshold = math.cos(math.radians(cone_angle_deg))
        
        obstacles_in_direction = []
        for obs in obstacles:
            if obs.distance > max_distance_m:
                continue
            
            # Calculate direction to obstacle
            dx = obs.position[0] - robot_pos[0]
            dy = obs.position[1] - robot_pos[1]
            dz = obs.position[2] - robot_pos[2]
            dist = math.sqrt(dx**2 + dy**2 + dz**2)
            
            if dist < 0.001:
                continue
            
            obs_dir = (dx/dist, dy/dist, dz/dist)
            
            # Dot product for angle check
            dot = dir_norm[0]*obs_dir[0] + dir_norm[1]*obs_dir[1] + dir_norm[2]*obs_dir[2]
            
            if dot >= cone_threshold:
                obstacles_in_direction.append(obs)
        
        return obstacles_in_direction
    
    def is_path_clear(
        self,
        robot_id: str,
        direction: Tuple[float, float, float],
        distance_m: float
    ) -> bool:
        """
        Check if path is clear in given direction for given distance
        
        Args:
            robot_id: Robot identifier
            direction: Direction to check
            distance_m: Distance to check
            
        Returns:
            True if path is clear (no high/critical risk obstacles)
        """
        obstacles = self.get_obstacles_in_direction(robot_id, direction, distance_m)
        
        for obs in obstacles:
            if obs.collision_risk >= 0.7:  # HIGH or CRITICAL
                return False
        
        return True
    
    def calibrate_for_evade(self, robot_id: str) -> Dict:
        """
        Calibrate obstacle detection for Evade subsystem
        
        Called during Webthread startup to configure for path planning.
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            Calibration results
        """
        self.logger.info(f"Calibrating obstacle detection for Evade (robot: {robot_id})")
        
        safety_config = self.robot_safety_configs.get(robot_id)
        
        calibration_results = {
            'robot_id': robot_id,
            'detection_range_m': self.detection_range_m,
            'update_rate_hz': self.update_rate_hz,
            'safety_zones': [
                {'name': z.name, 'warning_m': z.warning_radius_m, 'stop_m': z.stop_radius_m}
                for z in (safety_config.safety_zones if safety_config else [])
            ],
            'sensors_active': True,
            'calibration_status': 'success',
            'timestamp': time.time()
        }
        
        self.logger.info(f"Evade calibration complete for {robot_id}")
        return calibration_results
    
    def get_detection_stats(self, robot_id: str) -> Dict:
        """Get obstacle detection statistics for a robot"""
        obstacles = self.get_current_obstacles(robot_id)
        
        stats = {
            'total_obstacles': len(obstacles),
            'by_type': {},
            'by_risk_level': {},
            'nearest_distance_m': min(o.distance for o in obstacles) if obstacles else None,
            'max_collision_risk': max(o.collision_risk for o in obstacles) if obstacles else 0.0,
            'detection_active': self.enabled,
            'timestamp': time.time()
        }
        
        # Count by type
        for obs in obstacles:
            type_name = obs.obstacle_type.value
            stats['by_type'][type_name] = stats['by_type'].get(type_name, 0) + 1
            
            # Count by risk level
            if obs.collision_risk >= 0.9:
                level = 'critical'
            elif obs.collision_risk >= 0.7:
                level = 'high'
            elif obs.collision_risk >= 0.4:
                level = 'medium'
            else:
                level = 'low'
            stats['by_risk_level'][level] = stats['by_risk_level'].get(level, 0) + 1
        
        return stats
    
    def get_evade_recommendation(self, robot_id: str) -> Dict:
        """
        Get Evade action recommendation based on current obstacles
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            Recommendation for Evade subsystem
        """
        risk_level = self.get_collision_risk_level(robot_id)
        nearest = self.get_nearest_obstacle(robot_id)
        robot_obstacles = self.get_robot_obstacles(robot_id)
        
        recommendation = {
            'robot_id': robot_id,
            'risk_level': risk_level.value,
            'action': 'continue',
            'slowdown_factor': 1.0,
            'reason': '',
            'nearest_obstacle_distance_m': nearest.distance if nearest else None,
            'robot_obstacles_count': len(robot_obstacles),
            'timestamp': time.time()
        }
        
        if risk_level == CollisionRisk.CRITICAL:
            recommendation['action'] = 'emergency_stop'
            recommendation['slowdown_factor'] = 0.0
            recommendation['reason'] = 'Critical obstacle proximity'
        elif risk_level == CollisionRisk.HIGH:
            recommendation['action'] = 'slow_stop'
            recommendation['slowdown_factor'] = 0.2
            recommendation['reason'] = 'High collision risk detected'
        elif risk_level == CollisionRisk.MEDIUM:
            recommendation['action'] = 'reduce_speed'
            recommendation['slowdown_factor'] = 0.5
            recommendation['reason'] = 'Obstacle in proximity'
        elif risk_level == CollisionRisk.LOW:
            recommendation['action'] = 'caution'
            recommendation['slowdown_factor'] = 0.8
            recommendation['reason'] = 'Minor obstacle detected'
        
        return recommendation
    
    def shutdown(self) -> None:
        """Shutdown obstacle detection"""
        self.logger.info("Shutting down obstacle detection")
        self.known_robots.clear()
        self.robot_safety_configs.clear()
        self.obstacle_history.clear()
