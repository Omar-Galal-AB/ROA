"""
Position Tracker - Tracks robot positions in local and global coordinates
"""

from typing import Dict, Tuple, Optional, List
from collections import deque
import logging


class PositionTracker:
    """
    Tracks robot positions over time
    
    Maintains position history for velocity calculation and analysis
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize position tracker
        
        Args:
            config: Configuration dictionary with tracking parameters
        """
        self.config = config or {}
        self.logger = logging.getLogger('DIMC.PositionTracker')
        
        # Tracking parameters
        self.update_rate = self.config.get('update_rate', 60)  # Hz
        self.precision = self.config.get('precision', 0.001)  # meters
        self.coordinate_system = self.config.get('coordinate_system', 'world')
        self.history_size = self.config.get('history_size', 300)  # 5 seconds at 60Hz
        
        # Robot positions
        # {robot_id: {'current': (x, y, z), 'history': deque, 'first_position': (x, y, z)}}
        self.positions: Dict[str, Dict] = {}
        
        self.logger.info(f"PositionTracker initialized (rate: {self.update_rate}Hz, precision: {self.precision}m)")
    
    def add_robot(self, robot_id: str, initial_position: Tuple[float, float, float]) -> None:
        """
        Add a robot to track
        
        Args:
            robot_id: Unique robot identifier
            initial_position: Initial (x, y, z) position
        """
        self.positions[robot_id] = {
            'current': initial_position,
            'history': deque(maxlen=self.history_size),
            'first_position': initial_position,
            'total_distance': 0.0
        }
        
        # Add initial position to history
        self.positions[robot_id]['history'].append({
            'position': initial_position,
            'timestamp': 0.0
        })
        
        self.logger.info(f"Robot {robot_id} added to position tracking at {initial_position}")
    
    def remove_robot(self, robot_id: str) -> None:
        """
        Remove a robot from tracking
        
        Args:
            robot_id: Robot identifier to remove
        """
        if robot_id in self.positions:
            del self.positions[robot_id]
            self.logger.info(f"Robot {robot_id} removed from position tracking")
    
    def update(self, robot_id: str, position: Tuple[float, float, float], timestamp: float) -> None:
        """
        Update robot position
        
        Args:
            robot_id: Robot identifier
            position: New (x, y, z) position
            timestamp: Current timestamp in seconds
        """
        if robot_id not in self.positions:
            self.logger.warning(f"Robot {robot_id} not registered for position tracking")
            return
        
        # Calculate distance moved since last update
        old_position = self.positions[robot_id]['current']
        distance_moved = self._calculate_distance(old_position, position)
        
        # Update current position
        self.positions[robot_id]['current'] = position
        self.positions[robot_id]['total_distance'] += distance_moved
        
        # Add to history
        self.positions[robot_id]['history'].append({
            'position': position,
            'timestamp': timestamp
        })
    
    def get_position(self, robot_id: str) -> Optional[Tuple[float, float, float]]:
        """
        Get current position of a robot
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            (x, y, z) position tuple or None if not found
        """
        if robot_id in self.positions:
            return self.positions[robot_id]['current']
        return None
    
    def get_position_history(
        self,
        robot_id: str,
        num_samples: Optional[int] = None
    ) -> Optional[List[Dict]]:
        """
        Get position history for a robot
        
        Args:
            robot_id: Robot identifier
            num_samples: Number of recent samples to return (None = all)
            
        Returns:
            List of position history entries or None if not found
        """
        if robot_id not in self.positions:
            return None
        
        history = list(self.positions[robot_id]['history'])
        
        if num_samples:
            return history[-num_samples:]
        return history
    
    def get_total_distance_traveled(self, robot_id: str) -> Optional[float]:
        """
        Get total distance traveled by robot since tracking started
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            Total distance in meters or None if not found
        """
        if robot_id in self.positions:
            return self.positions[robot_id]['total_distance']
        return None
    
    def get_displacement_from_start(self, robot_id: str) -> Optional[float]:
        """
        Get straight-line distance from starting position
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            Displacement in meters or None if not found
        """
        if robot_id not in self.positions:
            return None
        
        first_pos = self.positions[robot_id]['first_position']
        current_pos = self.positions[robot_id]['current']
        
        return self._calculate_distance(first_pos, current_pos)
    
    def _calculate_distance(
        self,
        pos1: Tuple[float, float, float],
        pos2: Tuple[float, float, float]
    ) -> float:
        """
        Calculate Euclidean distance between two positions
        
        Args:
            pos1: First position (x, y, z)
            pos2: Second position (x, y, z)
            
        Returns:
            Distance in meters
        """
        dx = pos2[0] - pos1[0]
        dy = pos2[1] - pos1[1]
        dz = pos2[2] - pos1[2]
        
        return (dx**2 + dy**2 + dz**2) ** 0.5
    
    def clear_history(self, robot_id: str) -> bool:
        """
        Clear position history for a robot
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            True if successful, False if robot not found
        """
        if robot_id in self.positions:
            self.positions[robot_id]['history'].clear()
            self.positions[robot_id]['total_distance'] = 0.0
            # Keep current position
            current = self.positions[robot_id]['current']
            self.positions[robot_id]['history'].append({
                'position': current,
                'timestamp': 0.0
            })
            return True
        return False
