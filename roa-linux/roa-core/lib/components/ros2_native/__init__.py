"""
ROA v0.2 - Native ROS2 Integration Module

This module provides native ROS2 DDS communication for ROA,
replacing the v0.1 TCP bridge with direct rclpy integration.
"""

from .ros2_node import ROABridgeNode

__all__ = ['ROABridgeNode']
