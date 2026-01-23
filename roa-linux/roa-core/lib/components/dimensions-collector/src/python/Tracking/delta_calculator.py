"""
Delta Calculator - Calculates movement deltas and velocities
"""

from typing import Dict, Tuple, Optional
from collections import deque
import logging


class DeltaCalculator:
    """
    Calculates movement deltas and velocities from position changes
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize delta calculator
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.logger = logging.getLogger('DIMC.DeltaCalculator')
        
        self.update_rate = self.config.get('update_rate', 60)  # Hz
        self.window_size = self.config.get('window_size', 10)  # samples for smoothing
        
        # Robot velocity history
        # {robot_id: {'last_position': (x,y,z), 'last_time': float, 'velocities': deque}}
        self.robot_data: Dict[str, Dict] = {}
        
        self.logger.info(f"DeltaCalculator initialized (window: {self.window_size} samples)")
    
    def add_robot(self, robot_id: str) -> None:
        """Add a robot to track"""
        self.robot_data[robot_id] = {
            'last_position': None,
            'last_time': None,
            'velocities': deque(maxlen=self.window_size)
        }
    
    def remove_robot(self, robot_id: str) -> None:
        """Remove a robot from tracking"""
        if robot_id in self.robot_data:
            del self.robot_data[robot_id]
    
    def calculate(
        self,
        robot_id: str,
        position: Tuple[float, float, float],
        timestamp: float
    ) -> Tuple[float, float, float]:
        """
        Calculate velocity from position change
        
        Args:
            robot_id: Robot identifier
            position: Current position (x, y, z)
            timestamp: Current timestamp
            
        Returns:
            Velocity (vx, vy, vz) in m/s
        """
        if robot_id not in self.robot_data:
            return (0.0, 0.0, 0.0)
        
        data = self.robot_data[robot_id]
        
        # First update - no velocity yet
        if data['last_position'] is None:
            data['last_position'] = position
            data['last_time'] = timestamp
            return (0.0, 0.0, 0.0)
        
        # Calculate time delta
        dt = timestamp - data['last_time']
        if dt <= 0:
            return (0.0, 0.0, 0.0)
        
        # Calculate velocity
        dx = position[0] - data['last_position'][0]
        dy = position[1] - data['last_position'][1]
        dz = position[2] - data['last_position'][2]
        
        vx = dx / dt
        vy = dy / dt
        vz = dz / dt
        
        # Add to history
        data['velocities'].append((vx, vy, vz))
        
        # Update last values
        data['last_position'] = position
        data['last_time'] = timestamp
        
        # Return smoothed velocity (average of window)
        return self._smooth_velocity(robot_id)
    
    def _smooth_velocity(self, robot_id: str) -> Tuple[float, float, float]:
        """
        Calculate smoothed velocity from history window
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            Smoothed velocity (vx, vy, vz)
        """
        velocities = self.robot_data[robot_id]['velocities']
        
        if not velocities:
            return (0.0, 0.0, 0.0)
        
        # Calculate average
        vx_sum = sum(v[0] for v in velocities)
        vy_sum = sum(v[1] for v in velocities)
        vz_sum = sum(v[2] for v in velocities)
        
        n = len(velocities)
        return (vx_sum / n, vy_sum / n, vz_sum / n)
    
    def get_speed(self, robot_id: str) -> Optional[float]:
        """
        Get current speed (magnitude of velocity)
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            Speed in m/s or None
        """
        velocity = self._smooth_velocity(robot_id)
        if velocity:
            vx, vy, vz = velocity
            return (vx**2 + vy**2 + vz**2) ** 0.5
        return None
