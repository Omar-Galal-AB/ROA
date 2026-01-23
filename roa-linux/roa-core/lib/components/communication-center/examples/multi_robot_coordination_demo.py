#!/usr/bin/env python3
"""
Multi-Robot Coordination Demo

Example demonstrating COMC usage for coordinating multiple robots.
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Point, Vector3
from std_msgs.msg import String
import json
import time


class MultiRobotDemo(Node):
    """Demo node showing COMC coordination."""
    
    def __init__(self):
        super().__init__('multi_robot_demo')
        
        # Simulate 2 robots
        self.robot_1_pos = Point(x=0.0, y=0.0, z=0.0)
        self.robot_2_pos = Point(x=5.0, y=5.0, z=0.0)
        
        # Publishers for robot positions (simulating DIMC)
        self.pos_pub_1 = self.create_publisher(String, '/robot/robot_1/pose', 10)
        self.pos_pub_2 = self.create_publisher(String, '/robot/robot_2/pose', 10)
        
        # Subscriber for proximity alerts
        self.alert_sub = self.create_subscription(
            String,
            '/robots/proximity_alert',
            self.alert_callback,
            10
        )
        
        # Timer to simulate robot movement
        self.timer = self.create_timer(0.1, self.simulate_movement)
        
        self.get_logger().info('Multi-robot coordination demo started')
        
    def alert_callback(self, msg):
        """Handle proximity alerts."""
        try:
            data = json.loads(msg.data)
            severity = data.get('severity')
            distance = data.get('current_distance')
            source = data.get('source_robot_id')
            target = data.get('target_robot_id')
            
            if severity == 'critical':
                self.get_logger().error(
                    f'CRITICAL ALERT: {source} and {target} at {distance:.2f}m'
                )
            elif severity == 'caution':
                self.get_logger().warn(
                    f'CAUTION: {source} and {target} at {distance:.2f}m'
                )
            else:
                self.get_logger().info(
                    f'Warning: {source} and {target} at {distance:.2f}m'
                )
        except json.JSONDecodeError:
            pass
            
    def simulate_movement(self):
        """Simulate robots moving closer together."""
        # Move robot 2 towards robot 1
        if self.robot_2_pos.x > 0.1:
            self.robot_2_pos.x -= 0.1
            self.robot_2_pos.y -= 0.1
            
        # Publish positions
        msg1 = String()
        msg1.data = json.dumps({
            'robot_id': 'robot_1',
            'x': self.robot_1_pos.x,
            'y': self.robot_1_pos.y,
            'z': self.robot_1_pos.z,
            'vx': 0.0,
            'vy': 0.0,
            'vz': 0.0
        })
        self.pos_pub_1.publish(msg1)
        
        msg2 = String()
        msg2.data = json.dumps({
            'robot_id': 'robot_2',
            'x': self.robot_2_pos.x,
            'y': self.robot_2_pos.y,
            'z': self.robot_2_pos.z,
            'vx': -1.0,
            'vy': -1.0,
            'vz': 0.0
        })
        self.pos_pub_2.publish(msg2)


def main():
    """Run the demo."""
    rclpy.init()
    
    try:
        demo = MultiRobotDemo()
        rclpy.spin(demo)
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()
