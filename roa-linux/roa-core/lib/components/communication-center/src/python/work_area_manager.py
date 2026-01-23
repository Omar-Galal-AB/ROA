"""
Work Area Manager

Handles broadcasting and subscription of robot work areas to prevent
operational interference between robots.
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Point, Vector3
from std_msgs.msg import Header
from typing import Dict, Optional
import time


class WorkAreaManager:
    """
    Manages work area broadcasting and tracking for multi-robot coordination.
    """
    
    def __init__(self, node: Node):
        """
        Initialize the work area manager.
        
        Args:
            node: ROS2 node instance
        """
        self.node = node
        self.work_areas: Dict[str, dict] = {}  # robot_id -> work_area_data
        self.own_robot_id: Optional[str] = None
        self.own_work_area: Optional[dict] = None
        
    def set_robot_id(self, robot_id: str):
        """Set the robot ID for this instance."""
        self.own_robot_id = robot_id
        
    def update_work_area(self, center: Point, dimensions: Vector3, priority: float = 2.0):
        """
        Update this robot's work area.
        
        Args:
            center: Center point of work area
            dimensions: Width, height, depth in meters
            priority: Task priority (0=lowest, 4=highest)
        """
        if not self.own_robot_id:
            self.node.get_logger().warn("Robot ID not set, cannot update work area")
            return
            
        self.own_work_area = {
            'robot_id': self.own_robot_id,
            'center': center,
            'dimensions': dimensions,
            'priority': priority,
            'timestamp': time.time()
        }
        
    def get_work_area(self, robot_id: str) -> Optional[dict]:
        """
        Get work area for a specific robot.
        
        Args:
            robot_id: ID of the robot
            
        Returns:
            Work area data or None if not found
        """
        return self.work_areas.get(robot_id)
        
    def update_robot_work_area(self, robot_id: str, center: Point, dimensions: Vector3, 
                                priority: float, timestamp: float):
        """
        Update work area for another robot (from subscription).
        
        Args:
            robot_id: ID of the robot
            center: Center point of work area
            dimensions: Work area dimensions
            priority: Task priority
            timestamp: Message timestamp
        """
        self.work_areas[robot_id] = {
            'robot_id': robot_id,
            'center': center,
            'dimensions': dimensions,
            'priority': priority,
            'timestamp': timestamp
        }
        
    def check_conflict(self, robot_id: str) -> bool:
        """
        Check if a robot's work area conflicts with ours.
        
        Args:
            robot_id: ID of the robot to check
            
        Returns:
            True if there's a spatial conflict
        """
        if not self.own_work_area or robot_id not in self.work_areas:
            return False
            
        other_area = self.work_areas[robot_id]
        
        # Simple AABB (Axis-Aligned Bounding Box) collision detection
        own_center = self.own_work_area['center']
        own_dims = self.own_work_area['dimensions']
        other_center = other_area['center']
        other_dims = other_area['dimensions']
        
        # Calculate half extents
        own_half_x = own_dims.x / 2
        own_half_y = own_dims.y / 2
        own_half_z = own_dims.z / 2
        
        other_half_x = other_dims.x / 2
        other_half_y = other_dims.y / 2
        other_half_z = other_dims.z / 2
        
        # Check for overlap in all three axes
        overlap_x = abs(own_center.x - other_center.x) < (own_half_x + other_half_x)
        overlap_y = abs(own_center.y - other_center.y) < (own_half_y + other_half_y)
        overlap_z = abs(own_center.z - other_center.z) < (own_half_z + other_half_z)
        
        return overlap_x and overlap_y and overlap_z
        
    def get_all_conflicts(self) -> list:
        """
        Get list of all robots with conflicting work areas.
        
        Returns:
            List of robot IDs with conflicts
        """
        conflicts = []
        for robot_id in self.work_areas.keys():
            if robot_id != self.own_robot_id and self.check_conflict(robot_id):
                conflicts.append(robot_id)
        return conflicts
        
    def cleanup_stale_areas(self, max_age_seconds: float = 5.0):
        """
        Remove work areas that haven't been updated recently.
        
        Args:
            max_age_seconds: Maximum age before considering stale
        """
        current_time = time.time()
        stale_robots = []
        
        for robot_id, area in self.work_areas.items():
            if current_time - area['timestamp'] > max_age_seconds:
                stale_robots.append(robot_id)
                
        for robot_id in stale_robots:
            self.node.get_logger().info(f"Removing stale work area for {robot_id}")
            del self.work_areas[robot_id]
