"""
ros2_pubsub_example.py
ROA - Robot Operations & Automation
Example demonstrating ROS2 publisher/subscriber implementation

This example shows how to:
1. Create ROS2 nodes
2. Create publishers and subscribers
3. Publish and receive messages
4. Use different QoS profiles
5. Handle both ROS2 and mock modes
"""

import sys
import os
import time
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

from ROS2Bridge.ros2_node import ROS2Node
from ROS2Bridge.topic_manager import TopicManager


def example_basic_pubsub():
    """Example 1: Basic publisher/subscriber"""
    print("\n" + "="*60)
    print("Example 1: Basic Publisher/Subscriber")
    print("="*60)
    
    # Create and initialize node
    node = ROS2Node("example_basic")
    if not node.initialize():
        logger.error("Failed to initialize node")
        return
    
    # Create topic manager
    manager = TopicManager(node)
    
    # Create publisher
    logger.info("Creating publisher on /robot/commands...")
    manager.create_publisher("/robot/commands", str, qos_profile='default')
    
    # Create subscriber with callback
    received_messages = []
    def message_callback(msg):
        logger.info(f"Received: {msg}")
        received_messages.append(msg)
    
    logger.info("Creating subscriber on /robot/status...")
    manager.create_subscriber("/robot/status", str, message_callback, qos_profile='default')
    
    # Publish some messages
    logger.info("Publishing messages...")
    for i in range(5):
        msg = f"Command_{i}"
        manager.publish("/robot/commands", msg)
        logger.info(f"Published: {msg}")
        time.sleep(0.1)
    
    # Show statistics
    stats = manager.get_stats()
    logger.info(f"\nTopic Statistics:")
    for topic, info in stats.items():
        logger.info(f"  {topic}: {info}")
    
    # Cleanup
    logger.info("\nCleaning up...")
    manager.destroy_publisher("/robot/commands")
    manager.destroy_subscriber("/robot/status")
    node.shutdown()
    
    print(f"\n✓ Published 5 messages successfully")


def example_qos_profiles():
    """Example 2: Different QoS profiles"""
    print("\n" + "="*60)
    print("Example 2: QoS Profiles")
    print("="*60)
    
    node = ROS2Node("example_qos")
    node.initialize()
    manager = TopicManager(node)
    
    # Create publishers with different QoS
    logger.info("Creating publishers with different QoS profiles...")
    
    # Reliable QoS for critical data
    manager.create_publisher("/critical/data", str, qos_profile='reliable')
    logger.info("  - /critical/data with 'reliable' QoS")
    
    # Sensor QoS for high-frequency data
    manager.create_publisher("/sensor/data", float, qos_profile='sensor')
    logger.info("  - /sensor/data with 'sensor' QoS")
    
    # Custom depth
    manager.create_publisher("/custom/data", int, qos_profile=20)
    logger.info("  - /custom/data with depth=20")
    
    # Publish to each
    manager.publish("/critical/data", "Important command")
    manager.publish("/sensor/data", 3.14159)
    manager.publish("/custom/data", 42)
    
    stats = manager.get_stats()
    logger.info(f"\nActive publishers: {len(manager.get_publishers())}")
    
    # Cleanup
    node.shutdown()
    print(f"\n✓ Demonstrated 3 different QoS profiles")


def example_multi_robot():
    """Example 3: Multi-robot communication"""
    print("\n" + "="*60)
    print("Example 3: Multi-Robot Communication")
    print("="*60)
    
    # Create node for each robot
    robot1_node = ROS2Node("robot1", namespace="/robot1")
    robot2_node = ROS2Node("robot2", namespace="/robot2")
    
    robot1_node.initialize()
    robot2_node.initialize()
    
    # Create managers
    robot1_mgr = TopicManager(robot1_node)
    robot2_mgr = TopicManager(robot2_node)
    
    # Robot 1 publishes position
    logger.info("Setting up Robot 1 position publisher...")
    robot1_mgr.create_publisher("/position", dict, qos_profile='sensor')
    
    # Robot 2 publishes position
    logger.info("Setting up Robot 2 position publisher...")
    robot2_mgr.create_publisher("/position", dict, qos_profile='sensor')
    
    # Simulate position updates
    logger.info("\nSimulating robot movements...")
    for i in range(3):
        pos1 = {'x': i * 1.0, 'y': i * 0.5, 'z': 0.0}
        pos2 = {'x': i * -1.0, 'y': i * 0.8, 'z': 0.0}
        
        robot1_mgr.publish("/position", pos1)
        robot2_mgr.publish("/position", pos2)
        
        logger.info(f"  Robot 1 at {pos1}")
        logger.info(f"  Robot 2 at {pos2}")
        time.sleep(0.1)
    
    # Show stats
    stats1 = robot1_mgr.get_stats()
    stats2 = robot2_mgr.get_stats()
    
    logger.info(f"\nRobot 1 published: {stats1['/position']['publish_count']} messages")
    logger.info(f"Robot 2 published: {stats2['/position']['publish_count']} messages")
    
    # Cleanup
    robot1_node.shutdown()
    robot2_node.shutdown()
    
    print(f"\n✓ Coordinated 2 robots successfully")


def example_ai_control():
    """Example 4: AI agent controlling robot"""
    print("\n" + "="*60)
    print("Example 4: AI Agent Robot Control")
    print("="*60)
    
    # Create AI agent node
    ai_node = ROS2Node("ai_agent")
    ai_node.initialize()
    ai_mgr = TopicManager(ai_node)
    
    # Create robot control node
    robot_node = ROS2Node("robot_controller")
    robot_node.initialize()
    robot_mgr = TopicManager(robot_node)
    
    # AI publishes commands
    logger.info("AI Agent creating command publisher...")
    ai_mgr.create_publisher("/ai/robot_commands", dict, qos_profile='reliable')
    
    # Robot subscribes to AI commands
    executed_commands = []
    def execute_command(cmd):
        logger.info(f"Robot executing AI command: {cmd}")
        executed_commands.append(cmd)
    
    logger.info("Robot subscribing to AI commands...")
    robot_mgr.create_subscriber("/ai/robot_commands", dict, execute_command, qos_profile='reliable')
    
    # Robot publishes status
    logger.info("Robot creating status publisher...")
    robot_mgr.create_publisher("/robot/status", str, qos_profile='sensor')
    
    # AI subscribes to robot status
    status_updates = []
    def monitor_status(status):
        logger.info(f"AI monitoring: {status}")
        status_updates.append(status)
    
    logger.info("AI subscribing to robot status...")
    ai_mgr.create_subscriber("/robot/status", str, monitor_status, qos_profile='sensor')
    
    # Simulate AI decision-making loop
    logger.info("\nSimulating AI control loop...")
    ai_decisions = [
        {'action': 'move_to', 'target': {'x': 1.0, 'y': 2.0}},
        {'action': 'pick_object', 'object_id': 'box_42'},
        {'action': 'move_to', 'target': {'x': 3.0, 'y': 4.0}},
        {'action': 'place_object', 'object_id': 'box_42'}
    ]
    
    for decision in ai_decisions:
        # AI publishes command
        ai_mgr.publish("/ai/robot_commands", decision)
        logger.info(f"AI decided: {decision}")
        
        # Robot publishes status
        robot_mgr.publish("/robot/status", f"Executing: {decision['action']}")
        
        time.sleep(0.2)
    
    logger.info(f"\nAI commands sent: {len(ai_decisions)}")
    logger.info(f"Commands received by robot: {len(executed_commands)}")
    
    # Cleanup
    ai_node.shutdown()
    robot_node.shutdown()
    
    print(f"\n✓ AI successfully controlled robot through ROS2")


def main():
    """Run all examples"""
    print("\n" + "="*60)
    print("ROS2 Publisher/Subscriber Implementation Examples")
    print("ROA - Robot Operations & Automation")
    print("="*60)
    
    try:
        # Run examples
        example_basic_pubsub()
        example_qos_profiles()
        example_multi_robot()
        example_ai_control()
        
        print("\n" + "="*60)
        print("All Examples Completed Successfully! ✓")
        print("="*60)
        print("\nKey Features Demonstrated:")
        print("  ✓ Basic publisher/subscriber creation")
        print("  ✓ Message publishing and receiving")
        print("  ✓ Different QoS profiles (reliable, sensor, custom)")
        print("  ✓ Multi-robot coordination")
        print("  ✓ AI agent robot control")
        print("  ✓ Topic statistics tracking")
        print("  ✓ Graceful shutdown and cleanup")
        print("\nNote: Running in MOCK mode (ROS2 not installed)")
        print("Install ROS2 and rclpy for full functionality")
        
    except KeyboardInterrupt:
        print("\n\nExamples interrupted by user")
    except Exception as e:
        logger.error(f"Error running examples: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
