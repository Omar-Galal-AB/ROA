"""
Unit tests for Work Area Manager
"""

import unittest
from geometry_msgs.msg import Point, Vector3
import rclpy
from rclpy.node import Node
import sys
import os

# Add the src/python directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

from work_area_manager import WorkAreaManager


class TestWorkAreaManager(unittest.TestCase):
    """Test cases for WorkAreaManager."""
    
    @classmethod
    def setUpClass(cls):
        """Set up ROS2 for all tests."""
        rclpy.init()
        
    @classmethod
    def tearDownClass(cls):
        """Tear down ROS2 after all tests."""
        rclpy.shutdown()
        
    def setUp(self):
        """Set up for each test."""
        self.node = Node('test_node')
        self.manager = WorkAreaManager(self.node)
        self.manager.set_robot_id('robot_1')
        
    def tearDown(self):
        """Clean up after each test."""
        self.node.destroy_node()
        
    def test_set_robot_id(self):
        """Test setting robot ID."""
        self.assertEqual(self.manager.own_robot_id, 'robot_1')
        
    def test_update_work_area(self):
        """Test updating own work area."""
        center = Point(x=1.0, y=2.0, z=0.5)
        dimensions = Vector3(x=2.0, y=2.0, z=1.0)
        
        self.manager.update_work_area(center, dimensions, priority=3.0)
        
        self.assertIsNotNone(self.manager.own_work_area)
        self.assertEqual(self.manager.own_work_area['robot_id'], 'robot_1')
        self.assertEqual(self.manager.own_work_area['center'].x, 1.0)
        self.assertEqual(self.manager.own_work_area['priority'], 3.0)
        
    def test_update_robot_work_area(self):
        """Test updating work area for another robot."""
        center = Point(x=5.0, y=5.0, z=0.5)
        dimensions = Vector3(x=1.0, y=1.0, z=1.0)
        
        self.manager.update_robot_work_area('robot_2', center, dimensions, 2.0, 123456.0)
        
        area = self.manager.get_work_area('robot_2')
        self.assertIsNotNone(area)
        self.assertEqual(area['robot_id'], 'robot_2')
        self.assertEqual(area['center'].x, 5.0)
        
    def test_no_conflict_distant_robots(self):
        """Test no conflict when robots are far apart."""
        # Set own work area
        center1 = Point(x=0.0, y=0.0, z=0.0)
        dims1 = Vector3(x=1.0, y=1.0, z=1.0)
        self.manager.update_work_area(center1, dims1)
        
        # Set other robot's work area (far away)
        center2 = Point(x=10.0, y=10.0, z=0.0)
        dims2 = Vector3(x=1.0, y=1.0, z=1.0)
        self.manager.update_robot_work_area('robot_2', center2, dims2, 2.0, 123456.0)
        
        self.assertFalse(self.manager.check_conflict('robot_2'))
        
    def test_conflict_overlapping_robots(self):
        """Test conflict detection when robots' work areas overlap."""
        # Set own work area
        center1 = Point(x=0.0, y=0.0, z=0.0)
        dims1 = Vector3(x=2.0, y=2.0, z=2.0)
        self.manager.update_work_area(center1, dims1)
        
        # Set other robot's work area (overlapping)
        center2 = Point(x=1.0, y=1.0, z=0.0)
        dims2 = Vector3(x=2.0, y=2.0, z=2.0)
        self.manager.update_robot_work_area('robot_2', center2, dims2, 2.0, 123456.0)
        
        self.assertTrue(self.manager.check_conflict('robot_2'))
        
    def test_get_all_conflicts(self):
        """Test getting all conflicts."""
        # Set own work area
        center = Point(x=0.0, y=0.0, z=0.0)
        dims = Vector3(x=2.0, y=2.0, z=2.0)
        self.manager.update_work_area(center, dims)
        
        # Add overlapping robot
        center2 = Point(x=1.0, y=1.0, z=0.0)
        dims2 = Vector3(x=2.0, y=2.0, z=2.0)
        self.manager.update_robot_work_area('robot_2', center2, dims2, 2.0, 123456.0)
        
        # Add non-overlapping robot
        center3 = Point(x=10.0, y=10.0, z=0.0)
        dims3 = Vector3(x=1.0, y=1.0, z=1.0)
        self.manager.update_robot_work_area('robot_3', center3, dims3, 2.0, 123456.0)
        
        conflicts = self.manager.get_all_conflicts()
        self.assertEqual(len(conflicts), 1)
        self.assertIn('robot_2', conflicts)
        self.assertNotIn('robot_3', conflicts)


if __name__ == '__main__':
    unittest.main()
