"""
Unit tests for Proximity Monitor
"""

import unittest
from geometry_msgs.msg import Point
import rclpy
from rclpy.node import Node
import sys
import os
import math

# Add the src/python directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

from proximity_monitor import ProximityMonitor


class TestProximityMonitor(unittest.TestCase):
    """Test cases for ProximityMonitor."""
    
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
        self.monitor = ProximityMonitor(self.node)
        self.monitor.set_robot_id('robot_1')
        
    def tearDown(self):
        """Clean up after each test."""
        self.node.destroy_node()
        
    def test_set_robot_id(self):
        """Test setting robot ID."""
        self.assertEqual(self.monitor.own_robot_id, 'robot_1')
        
    def test_update_robot_position(self):
        """Test updating robot position."""
        pos = Point(x=1.0, y=2.0, z=3.0)
        self.monitor.update_robot_position('robot_1', pos)
        
        self.assertIn('robot_1', self.monitor.robot_positions)
        self.assertEqual(self.monitor.robot_positions['robot_1'].x, 1.0)
        
    def test_calculate_distance(self):
        """Test distance calculation."""
        pos1 = Point(x=0.0, y=0.0, z=0.0)
        pos2 = Point(x=3.0, y=4.0, z=0.0)
        
        distance = self.monitor.calculate_distance(pos1, pos2)
        self.assertAlmostEqual(distance, 5.0, places=5)  # 3-4-5 triangle
        
    def test_no_alert_distant_robots(self):
        """Test no alert when robots are far apart."""
        self.monitor.update_robot_position('robot_1', Point(x=0.0, y=0.0, z=0.0))
        self.monitor.update_robot_position('robot_2', Point(x=10.0, y=10.0, z=0.0))
        
        alert = self.monitor.get_proximity_alert('robot_2')
        self.assertIsNone(alert)
        
    def test_warning_alert(self):
        """Test warning alert at appropriate distance."""
        self.monitor.update_robot_position('robot_1', Point(x=0.0, y=0.0, z=0.0))
        self.monitor.update_robot_position('robot_2', Point(x=0.4, y=0.0, z=0.0))
        
        alert = self.monitor.get_proximity_alert('robot_2')
        self.assertIsNotNone(alert)
        distance, velocity, severity = alert
        self.assertAlmostEqual(distance, 0.4, places=2)
        self.assertEqual(severity, 'warning')
        
    def test_caution_alert(self):
        """Test caution alert at close distance."""
        self.monitor.update_robot_position('robot_1', Point(x=0.0, y=0.0, z=0.0))
        self.monitor.update_robot_position('robot_2', Point(x=0.2, y=0.0, z=0.0))
        
        alert = self.monitor.get_proximity_alert('robot_2')
        self.assertIsNotNone(alert)
        distance, velocity, severity = alert
        self.assertAlmostEqual(distance, 0.2, places=2)
        self.assertEqual(severity, 'caution')
        
    def test_critical_alert(self):
        """Test critical alert at very close distance."""
        self.monitor.update_robot_position('robot_1', Point(x=0.0, y=0.0, z=0.0))
        self.monitor.update_robot_position('robot_2', Point(x=0.05, y=0.0, z=0.0))
        
        alert = self.monitor.get_proximity_alert('robot_2')
        self.assertIsNotNone(alert)
        distance, velocity, severity = alert
        self.assertAlmostEqual(distance, 0.05, places=2)
        self.assertEqual(severity, 'critical')
        
    def test_get_all_proximity_alerts(self):
        """Test getting alerts for all robots."""
        self.monitor.update_robot_position('robot_1', Point(x=0.0, y=0.0, z=0.0))
        self.monitor.update_robot_position('robot_2', Point(x=0.4, y=0.0, z=0.0))  # Warning
        self.monitor.update_robot_position('robot_3', Point(x=0.2, y=0.0, z=0.0))  # Caution
        self.monitor.update_robot_position('robot_4', Point(x=10.0, y=0.0, z=0.0))  # No alert
        
        alerts = self.monitor.get_all_proximity_alerts()
        self.assertEqual(len(alerts), 2)  # Only robot_2 and robot_3
        
    def test_get_distances_to_all(self):
        """Test getting distances to all robots."""
        self.monitor.update_robot_position('robot_1', Point(x=0.0, y=0.0, z=0.0))
        self.monitor.update_robot_position('robot_2', Point(x=3.0, y=0.0, z=0.0))
        self.monitor.update_robot_position('robot_3', Point(x=0.0, y=4.0, z=0.0))
        
        distances = self.monitor.get_distances_to_all()
        self.assertEqual(len(distances), 2)
        self.assertAlmostEqual(distances['robot_2'], 3.0, places=2)
        self.assertAlmostEqual(distances['robot_3'], 4.0, places=2)


if __name__ == '__main__':
    unittest.main()
