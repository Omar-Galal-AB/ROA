#!/usr/bin/env python3
"""
Demo: Using Mock ROS2 and Mock UE5 together to test ROA components
This demonstrates how to test the system without ROS2 or UE5 installed
"""

import sys
import os
import time
import numpy as np

# Add mock systems to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'components', 'mock_ros2', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'components', 'mock_ue5', 'src'))

from mock_ros2 import MockNode, ControlCommand, SpatialData, MockROS2System
from mock_ue5 import MockWorld, MockRobot


def main():
    print("="*60)
    print("ROA Simulation Demo - Mock ROS2 + Mock UE5")
    print("="*60)
    print()
    
    # Step 1: Create Mock UE5 World
    print("[1] Creating Mock UE5 World...")
    world = MockWorld()
    
    # Spawn robot
    robot = world.spawn_robot("robot_001", num_joints=6, location=np.array([0.0, 0.0, 0.0]))
    print(f"   ✓ Spawned robot: {robot.name}")
    print(f"   - Position: {robot.get_location()}")
    print(f"   - Joints: {robot.num_joints}")
    
    # Add obstacles
    world.add_obstacle(np.array([2.0, 2.0, 0.0]), 0.5)
    world.add_obstacle(np.array([-2.0, -2.0, 0.0]), 0.3)
    print(f"   ✓ Added {len(world.obstacles)} obstacles")
    print()
    
    # Step 2: Create Mock ROS2 Nodes
    print("[2] Creating Mock ROS2 Nodes...")
    
    # Simulated DIMC node (publishes spatial data)
    dimc_node = MockNode('dimc_simulator')
    spatial_pub = dimc_node.create_publisher(SpatialData, '/dimc/spatial_data', 10)
    print("   ✓ Created DIMC node with spatial data publisher")
    
    # Simulated ROC node (subscribes to spatial data, publishes commands)
    roc_node = MockNode('roc_simulator')
    command_pub = roc_node.create_publisher(ControlCommand, '/roc/commands', 10)
    print("   ✓ Created ROC node with command publisher")
    
    # Track received messages
    received_spatial_data = []
    received_commands = []
    
    def spatial_data_callback(msg):
        received_spatial_data.append(msg)
        print(f"   → ROC received spatial data: robot={msg.robot_id}, pos={msg.position}")
    
    def command_callback(msg):
        received_commands.append(msg)
        print(f"   → UE5 received command: robot={msg.robot_id}, type={msg.command_type}")
        
        # Apply command to robot in UE5
        if msg.command_type == "position":
            robot = world.get_robot_by_name(msg.robot_id)
            if robot:
                robot.set_joint_positions(msg.joint_values)
    
    # Create subscriptions
    roc_spatial_sub = roc_node.create_subscription(
        SpatialData, '/dimc/spatial_data', spatial_data_callback, 10
    )
    
    ue5_command_sub = MockNode('ue5_simulator').create_subscription(
        ControlCommand, '/roc/commands', command_callback, 10
    )
    print("   ✓ Created subscriptions")
    print()
    
    # Step 3: Run Simulation Loop
    print("[3] Running Simulation (5 seconds)...")
    print()
    
    start_time = time.time()
    iteration = 0
    
    while time.time() - start_time < 5.0:
        iteration += 1
        
        # Update UE5 world
        world.tick(0.1)  # 10 Hz update
        
        # Get robot state from UE5
        robot = world.get_robot_by_name("robot_001")
        
        # DIMC publishes spatial data
        spatial_msg = SpatialData()
        spatial_msg.robot_id = "robot_001"
        spatial_msg.position = robot.get_location().tolist()
        spatial_msg.orientation = [0.0, 0.0, 0.0, 1.0]
        spatial_msg.velocity = robot.velocity.tolist()
        spatial_pub.publish(spatial_msg)
        
        # ROC publishes control command every other iteration
        if iteration % 2 == 0:
            command_msg = ControlCommand()
            command_msg.robot_id = "robot_001"
            command_msg.command_type = "position"
            # Gradually move joints
            command_msg.joint_values = [
                np.sin(iteration * 0.1) * 0.5,  # Joint 1
                np.cos(iteration * 0.1) * 0.5,  # Joint 2
                0.0,
                0.5,
                0.0,
                0.0
            ]
            command_pub.publish(command_msg)
        
        # Check for collisions
        collision, min_distance = world.check_robot_collision("robot_001")
        if collision:
            print(f"   ⚠️  Collision detected! Distance: {min_distance:.2f}m")
        
        # Process ROS2 callbacks
        roc_node.spin_once(0.01)
        
        time.sleep(0.1)
    
    print()
    print("="*60)
    print("Simulation Complete!")
    print("="*60)
    print()
    
    # Step 4: Show Results
    print("[4] Results:")
    print(f"   Total iterations: {iteration}")
    print(f"   Spatial data messages: {len(received_spatial_data)}")
    print(f"   Command messages: {len(received_commands)}")
    print(f"   Final robot position: {robot.get_location()}")
    print(f"   Final joint positions: {robot.joint_positions}")
    print(f"   End effector position: {robot.get_end_effector_position()}")
    print()
    
    # Show topic statistics
    print("[5] ROS2 Topic Statistics:")
    for topic in MockROS2System.list_topics():
        info = MockROS2System.get_topic_info(topic)
        print(f"   {topic}")
        print(f"      Publishers: {info['num_publishers']}")
        print(f"      Subscribers: {info['num_subscribers']}")
    print()
    
    print("✅ Demo completed successfully!")
    print()
    print("This demonstrates:")
    print("  ✓ Mock ROS2 pub/sub working")
    print("  ✓ Mock UE5 world simulation working")
    print("  ✓ Integration between components")
    print("  ✓ No external dependencies needed")
    print()


if __name__ == '__main__':
    main()
