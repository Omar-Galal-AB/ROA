"""
Orientation Tracker - Tracks robot orientations (quaternions and Euler angles)
"""

from typing import Dict, Tuple, Optional
import logging
import math


class OrientationTracker:
    """
    Tracks robot orientations over time
    
    Supports both quaternion and Euler angle representations
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize orientation tracker
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.logger = logging.getLogger('DIMC.OrientationTracker')
        
        self.update_rate = self.config.get('update_rate', 60)  # Hz
        self.format = self.config.get('format', 'quaternion')  # or 'euler'
        
        # Robot orientations
        # {robot_id: {'quaternion': (x, y, z, w), 'euler': (roll, pitch, yaw)}}
        self.orientations: Dict[str, Dict] = {}
        
        self.logger.info(f"OrientationTracker initialized (rate: {self.update_rate}Hz, format: {self.format})")
    
    def add_robot(self, robot_id: str, initial_orientation: Tuple[float, float, float, float]) -> None:
        """
        Add a robot to track
        
        Args:
            robot_id: Unique robot identifier
            initial_orientation: Initial quaternion (x, y, z, w)
        """
        euler = self._quaternion_to_euler(initial_orientation)
        
        self.orientations[robot_id] = {
            'quaternion': initial_orientation,
            'euler': euler
        }
        
        self.logger.info(f"Robot {robot_id} added to orientation tracking")
    
    def remove_robot(self, robot_id: str) -> None:
        """Remove a robot from tracking"""
        if robot_id in self.orientations:
            del self.orientations[robot_id]
    
    def update(
        self,
        robot_id: str,
        orientation: Tuple[float, float, float, float],
        timestamp: float
    ) -> None:
        """
        Update robot orientation
        
        Args:
            robot_id: Robot identifier
            orientation: Quaternion (x, y, z, w)
            timestamp: Current timestamp
        """
        if robot_id not in self.orientations:
            return
        
        euler = self._quaternion_to_euler(orientation)
        
        self.orientations[robot_id]['quaternion'] = orientation
        self.orientations[robot_id]['euler'] = euler
    
    def get_orientation(self, robot_id: str) -> Optional[Tuple[float, float, float, float]]:
        """
        Get current orientation as quaternion
        
        Returns:
            (x, y, z, w) quaternion or None
        """
        if robot_id in self.orientations:
            return self.orientations[robot_id]['quaternion']
        return None
    
    def get_euler_angles(self, robot_id: str) -> Optional[Tuple[float, float, float]]:
        """
        Get current orientation as Euler angles
        
        Returns:
            (roll, pitch, yaw) in radians or None
        """
        if robot_id in self.orientations:
            return self.orientations[robot_id]['euler']
        return None
    
    def _quaternion_to_euler(self, q: Tuple[float, float, float, float]) -> Tuple[float, float, float]:
        """
        Convert quaternion to Euler angles (roll, pitch, yaw)
        
        Args:
            q: Quaternion (x, y, z, w)
            
        Returns:
            (roll, pitch, yaw) in radians
        """
        x, y, z, w = q
        
        # Roll (x-axis rotation)
        sinr_cosp = 2 * (w * x + y * z)
        cosr_cosp = 1 - 2 * (x * x + y * y)
        roll = math.atan2(sinr_cosp, cosr_cosp)
        
        # Pitch (y-axis rotation)
        sinp = 2 * (w * y - z * x)
        if abs(sinp) >= 1:
            pitch = math.copysign(math.pi / 2, sinp)  # Use 90 degrees if out of range
        else:
            pitch = math.asin(sinp)
        
        # Yaw (z-axis rotation)
        siny_cosp = 2 * (w * z + x * y)
        cosy_cosp = 1 - 2 * (y * y + z * z)
        yaw = math.atan2(siny_cosp, cosy_cosp)
        
        return (roll, pitch, yaw)
