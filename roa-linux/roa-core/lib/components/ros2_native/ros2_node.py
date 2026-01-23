#!/usr/bin/env python3
"""
ROA v0.2 - Native ROS2 Bridge Node

This node provides native DDS communication between UE5 and ROS2 ecosystem.
Replaces the v0.1 TCP server with direct rclpy pub/sub for <5ms latency.

Topics:
  Subscribers:
    - /robot/{robot_id}/joint_states (sensor_msgs/JointState) - From UE5

  Publishers:
    - /robot/{robot_id}/joint_commands (trajectory_msgs/JointTrajectory) - To UE5

Author: ROA Development Team
Version: 0.2.0-alpha
"""

import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import JointState
from std_msgs.msg import Header
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint


class ROABridgeNode(Node):
    """
    ROS2 node for bridging UE5 robot simulation with ROS2 ecosystem.

    Provides native DDS communication for joint states, commands, and sensors.
    Designed for multi-robot scenarios with per-robot topic namespacing.
    """

    def __init__(self, robot_id: str = "robot_0", enable_logging: bool = True):
        """
        Initialize ROA Bridge Node.

        Args:
            robot_id: Unique robot identifier for topic namespacing
            enable_logging: Enable detailed logging for debugging
        """
        super().__init__(f"roa_bridge_{robot_id}")

        self.robot_id = robot_id
        self.enable_logging = enable_logging

        # QoS Profile for real-time control (low latency)
        self.control_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        # QoS Profile for sensor data (best effort, higher throughput)
        self.sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
        )

        # Joint state tracking
        self.last_joint_state = None
        self.joint_state_count = 0
        self.command_count = 0

        # Setup subscribers
        self._setup_subscribers()

        # Setup publishers
        self._setup_publishers()

        # Statistics timer (1 Hz)
        self.stats_timer = self.create_timer(1.0, self._print_statistics)

        self.get_logger().info(f"ROA Bridge Node initialized for robot: {robot_id}")
        self.get_logger().info(f"  - Listening: /robot/{robot_id}/joint_states")
        self.get_logger().info(f"  - Publishing: /robot/{robot_id}/joint_commands")

    def _setup_subscribers(self):
        """Create ROS2 subscribers for UE5 data."""
        # Joint states from UE5
        self.joint_state_sub = self.create_subscription(
            JointState,
            f"/robot/{self.robot_id}/joint_states",
            self._joint_state_callback,
            self.sensor_qos,
        )

    def _setup_publishers(self):
        """Create ROS2 publishers for sending commands to UE5."""
        # Joint commands to UE5
        self.joint_cmd_pub = self.create_publisher(
            JointTrajectory, f"/robot/{self.robot_id}/joint_commands", self.control_qos
        )

    def _joint_state_callback(self, msg: JointState):
        """
        Handle incoming joint states from UE5.

        Args:
            msg: JointState message with current robot configuration
        """
        self.last_joint_state = msg
        self.joint_state_count += 1

        if self.enable_logging and self.joint_state_count % 30 == 0:
            self.get_logger().info(
                f"Joint states received: {len(msg.name)} joints, "
                f"positions={msg.position[:3] if len(msg.position) >= 3 else msg.position}"
            )

    def send_joint_command(
        self,
        joint_names: list,
        positions: list,
        velocities: list = None,
        time_from_start: float = 1.0,
    ):
        """
        Send joint trajectory command to UE5.

        Args:
            joint_names: List of joint names to control
            positions: Target positions for each joint
            velocities: Target velocities (optional)
            time_from_start: Duration to reach target (seconds)
        """
        if len(joint_names) != len(positions):
            self.get_logger().error("Joint names and positions length mismatch")
            return

        # Create trajectory message
        traj = JointTrajectory()
        traj.header = Header()
        traj.header.stamp = self.get_clock().now().to_msg()
        traj.joint_names = joint_names

        # Create trajectory point
        point = JointTrajectoryPoint()
        point.positions = positions

        if velocities:
            point.velocities = velocities
        else:
            point.velocities = [0.0] * len(positions)

        point.time_from_start.sec = int(time_from_start)
        point.time_from_start.nanosec = int((time_from_start % 1.0) * 1e9)

        traj.points = [point]

        # Publish
        self.joint_cmd_pub.publish(traj)
        self.command_count += 1

        if self.enable_logging:
            self.get_logger().info(f"Sent joint command: {len(joint_names)} joints")

    def get_current_joint_state(self) -> JointState:
        """
        Get the last received joint state.

        Returns:
            Latest JointState message or None
        """
        return self.last_joint_state

    def _print_statistics(self):
        """Print communication statistics (called at 1 Hz)."""
        if self.enable_logging:
            self.get_logger().info(
                f"Stats - Received: {self.joint_state_count} states, "
                f"Sent: {self.command_count} commands"
            )


class ROABridgeManager:
    """
    Manager for multiple ROA bridge nodes (multi-robot support).
    """

    def __init__(self):
        self.nodes = {}
        self.executor = None
        self.spin_thread = None

    def add_robot(self, robot_id: str, enable_logging: bool = True):
        """
        Add a robot to the bridge.

        Args:
            robot_id: Unique robot identifier
            enable_logging: Enable logging for this robot
        """
        if robot_id in self.nodes:
            print(f"Warning: Robot {robot_id} already exists")
            return

        node = ROABridgeNode(robot_id=robot_id, enable_logging=enable_logging)
        self.nodes[robot_id] = node
        print(f"Added robot: {robot_id}")

    def start(self):
        """Start the ROS2 executor in a background thread."""
        if self.executor is not None:
            print("Warning: Bridge manager already started")
            return

        rclpy.init()

        from rclpy.executors import MultiThreadedExecutor

        self.executor = MultiThreadedExecutor()

        for node in self.nodes.values():
            self.executor.add_node(node)

        self.spin_thread = threading.Thread(target=self.executor.spin, daemon=True)
        self.spin_thread.start()

        print(f"ROA Bridge Manager started with {len(self.nodes)} robots")

    def stop(self):
        """Stop the executor and cleanup."""
        if self.executor:
            self.executor.shutdown()

        for node in self.nodes.values():
            node.destroy_node()

        rclpy.shutdown()
        print("ROA Bridge Manager stopped")

    def get_node(self, robot_id: str) -> ROABridgeNode:
        """Get node for specific robot."""
        return self.nodes.get(robot_id)


def main():
    """
    Standalone entry point for testing.
    """
    print("ROA v0.2 - Native ROS2 Bridge Node")
    print("==================================")

    # Initialize ROS2
    rclpy.init()

    # Create bridge node
    node = ROABridgeNode(robot_id="robot_0", enable_logging=True)

    try:
        print("Node running... Press Ctrl+C to exit")
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
