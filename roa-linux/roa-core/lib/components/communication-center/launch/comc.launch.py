#!/usr/bin/env python3
"""
COMC Launch File

Launches the Communication Center node for multi-robot coordination.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """Generate launch description for COMC node."""
    
    # Declare launch arguments
    robot_id_arg = DeclareLaunchArgument(
        'robot_id',
        default_value='robot_1',
        description='Unique identifier for this robot'
    )
    
    work_area_rate_arg = DeclareLaunchArgument(
        'work_area_update_rate',
        default_value='20.0',
        description='Work area broadcast rate in Hz'
    )
    
    proximity_rate_arg = DeclareLaunchArgument(
        'proximity_update_rate',
        default_value='60.0',
        description='Proximity monitoring rate in Hz'
    )
    
    # COMC node
    comc_node = Node(
        package='communication_center',
        executable='comc_node',
        name='communication_center',
        output='screen',
        parameters=[{
            'robot_id': LaunchConfiguration('robot_id'),
            'work_area_update_rate': LaunchConfiguration('work_area_update_rate'),
            'proximity_update_rate': LaunchConfiguration('proximity_update_rate'),
            'health_check_rate': 2.0
        }]
    )
    
    return LaunchDescription([
        robot_id_arg,
        work_area_rate_arg,
        proximity_rate_arg,
        comc_node
    ])
