"""
ROC Integration Handlers

Handles integration with other ROA components:
- FTI (Files Type Importer) - Robot specifications
- DIMC (Dimensions Collector) - Spatial data and obstacles
- COMC (Communication Center) - Multi-robot coordination
- Webthread - System coordination and configuration

Author: ROA Development Team
Date: 2025-11-16
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import Point
import json
import time
from typing import Dict, Optional, Callable, Any


class FTIIntegrationHandler:
    """
    Handles integration with FTI (Files Type Importer).
    Receives robot specifications after import.
    """
    
    def __init__(self, node: Node, on_robot_specs_callback: Callable):
        """
        Initialize FTI integration.
        
        Args:
            node: ROS2 node instance
            on_robot_specs_callback: Callback when robot specs are received
        """
        self.node = node
        self.on_robot_specs_callback = on_robot_specs_callback
        
        # Subscribe to FTI robot specifications
        self.robot_specs_sub = self.node.create_subscription(
            String,
            '/fti/robot_specs',
            self.robot_specs_callback,
            10
        )
        
        # Subscribe to FTI import results
        self.import_result_sub = self.node.create_subscription(
            String,
            '/fti/import_result',
            self.import_result_callback,
            10
        )
        
        self.node.get_logger().info("FTI integration handler initialized")
        
    def robot_specs_callback(self, msg: String):
        """
        Handle robot specifications from FTI.
        
        Args:
            msg: Robot specs message (JSON format)
        """
        try:
            data = json.loads(msg.data)
            
            robot_id = data.get('robot_id')
            robot_name = data.get('robot_name')
            joints = data.get('joints', [])
            capabilities = data.get('capabilities', {})
            
            robot_spec = {
                'robot_id': robot_id,
                'robot_name': robot_name,
                'joints': joints,
                'capabilities': capabilities,
                'has_gripper': capabilities.get('has_gripper', False),
                'has_mobile_base': capabilities.get('has_mobile_base', False),
                'dof': len(joints)
            }
            
            self.node.get_logger().info(
                f"Received robot specs from FTI: {robot_name} ({robot_id})"
            )
            
            # Call the callback with robot specs
            self.on_robot_specs_callback(robot_spec)
            
        except json.JSONDecodeError as e:
            self.node.get_logger().error(f'Failed to parse FTI robot specs: {e}')
            
    def import_result_callback(self, msg: String):
        """
        Handle import result from FTI.
        
        Args:
            msg: Import result message (JSON format)
        """
        try:
            data = json.loads(msg.data)
            
            success = data.get('success', False)
            robot_name = data.get('robot_name')
            
            if success:
                self.node.get_logger().info(
                    f"FTI successfully imported robot: {robot_name}"
                )
            else:
                error = data.get('error', 'Unknown error')
                self.node.get_logger().error(
                    f"FTI import failed for {robot_name}: {error}"
                )
                
        except json.JSONDecodeError as e:
            self.node.get_logger().error(f'Failed to parse FTI import result: {e}')


class DIMCIntegrationHandler:
    """
    Handles integration with DIMC (Dimensions Collector).
    Receives spatial data, boundaries, and obstacle information.
    """
    
    def __init__(
        self,
        node: Node,
        on_spatial_data_callback: Callable,
        on_obstacle_callback: Callable
    ):
        """
        Initialize DIMC integration.
        
        Args:
            node: ROS2 node instance
            on_spatial_data_callback: Callback for spatial data updates
            on_obstacle_callback: Callback for obstacle detection
        """
        self.node = node
        self.on_spatial_data_callback = on_spatial_data_callback
        self.on_obstacle_callback = on_obstacle_callback
        
        # Subscribe to DIMC spatial data (60Hz)
        self.spatial_data_sub = self.node.create_subscription(
            String,
            '/dimc/spatial_data',
            self.spatial_data_callback,
            10
        )
        
        # Subscribe to DIMC obstacles
        self.obstacle_sub = self.node.create_subscription(
            String,
            '/dimc/obstacles',
            self.obstacle_callback,
            10
        )
        
        # Publisher for target positions (for collision prediction)
        self.target_position_pub = self.node.create_publisher(
            String,
            '/roc/target_positions',
            10
        )
        
        self.node.get_logger().info("DIMC integration handler initialized")
        
    def spatial_data_callback(self, msg: String):
        """
        Handle spatial data from DIMC.
        
        Args:
            msg: Spatial data message (JSON format)
        """
        try:
            data = json.loads(msg.data)
            
            robot_id = data.get('robot_id')
            position = data.get('position', {})
            orientation = data.get('orientation', {})
            boundaries = data.get('boundaries', {})
            
            spatial_info = {
                'robot_id': robot_id,
                'position': {
                    'x': position.get('x', 0.0),
                    'y': position.get('y', 0.0),
                    'z': position.get('z', 0.0)
                },
                'orientation': {
                    'roll': orientation.get('roll', 0.0),
                    'pitch': orientation.get('pitch', 0.0),
                    'yaw': orientation.get('yaw', 0.0)
                },
                'boundaries': boundaries,
                'timestamp': time.time()
            }
            
            # Call the callback with spatial info
            self.on_spatial_data_callback(spatial_info)
            
        except json.JSONDecodeError as e:
            self.node.get_logger().error(f'Failed to parse DIMC spatial data: {e}')
            
    def obstacle_callback(self, msg: String):
        """
        Handle obstacle detection from DIMC.
        
        Args:
            msg: Obstacle message (JSON format)
        """
        try:
            data = json.loads(msg.data)
            
            robot_id = data.get('robot_id')
            obstacle_distance = data.get('distance', float('inf'))
            obstacle_position = data.get('position', {})
            
            obstacle_info = {
                'robot_id': robot_id,
                'distance': obstacle_distance,
                'position': {
                    'x': obstacle_position.get('x', 0.0),
                    'y': obstacle_position.get('y', 0.0),
                    'z': obstacle_position.get('z', 0.0)
                },
                'timestamp': time.time()
            }
            
            # Call the callback with obstacle info
            self.on_obstacle_callback(obstacle_info)
            
        except json.JSONDecodeError as e:
            self.node.get_logger().error(f'Failed to parse DIMC obstacle data: {e}')
            
    def publish_target_position(self, robot_id: str, target_pos: Dict[str, float]):
        """
        Publish target position to DIMC for collision prediction.
        
        Args:
            robot_id: Robot identifier
            target_pos: Target position {'x', 'y', 'z'}
        """
        msg_data = {
            'robot_id': robot_id,
            'target_position': target_pos,
            'timestamp': time.time()
        }
        
        msg = String()
        msg.data = json.dumps(msg_data)
        self.target_position_pub.publish(msg)


class COMCIntegrationHandler:
    """
    Handles integration with COMC (Communication Center).
    Handles multi-robot coordination and evasion responses.
    """
    
    def __init__(
        self,
        node: Node,
        on_evasion_response_callback: Callable,
        on_coordination_update_callback: Callable
    ):
        """
        Initialize COMC integration.
        
        Args:
            node: ROS2 node instance
            on_evasion_response_callback: Callback for evasion responses
            on_coordination_update_callback: Callback for coordination updates
        """
        self.node = node
        self.on_evasion_response_callback = on_evasion_response_callback
        self.on_coordination_update_callback = on_coordination_update_callback
        
        # Publisher for evasion requests
        self.evasion_request_pub = self.node.create_publisher(
            String,
            '/roc/evasion_request',
            10
        )
        
        # Subscribe to COMC evasion responses
        self.evasion_response_sub = self.node.create_subscription(
            String,
            '/comc/evasion_response',
            self.evasion_response_callback,
            10
        )
        
        # Subscribe to COMC work area broadcasts
        self.work_area_sub = self.node.create_subscription(
            String,
            '/comc/work_areas',
            self.work_area_callback,
            10
        )
        
        # Publisher for robot intentions
        self.intention_pub = self.node.create_publisher(
            String,
            '/roc/robot_intentions',
            10
        )
        
        self.node.get_logger().info("COMC integration handler initialized")
        
    def request_evasion_path(
        self,
        robot_id: str,
        current_pos: Dict[str, float],
        target_pos: Dict[str, float],
        robot_type: str = 'ground',
        priority: int = 2
    ):
        """
        Request evasion path from COMC.
        
        Args:
            robot_id: Robot identifier
            current_pos: Current position {'x', 'y', 'z'}
            target_pos: Target position {'x', 'y', 'z'}
            robot_type: Type of robot (ground, aerial, etc.)
            priority: Priority level (1-5)
        """
        msg_data = {
            'robot_id': robot_id,
            'current_x': current_pos['x'],
            'current_y': current_pos['y'],
            'current_z': current_pos['z'],
            'target_x': target_pos['x'],
            'target_y': target_pos['y'],
            'target_z': target_pos['z'],
            'robot_type': robot_type,
            'priority': priority,
            'timestamp': time.time()
        }
        
        msg = String()
        msg.data = json.dumps(msg_data)
        self.evasion_request_pub.publish(msg)
        
        self.node.get_logger().info(f"Requested evasion path for {robot_id}")
        
    def evasion_response_callback(self, msg: String):
        """
        Handle evasion response from COMC.
        
        Args:
            msg: Evasion response message (JSON format)
        """
        try:
            data = json.loads(msg.data)
            
            robot_id = data.get('robot_id')
            approved = data.get('approved', False)
            path = data.get('path', [])
            
            evasion_response = {
                'robot_id': robot_id,
                'approved': approved,
                'path': path,
                'timestamp': data.get('timestamp', time.time())
            }
            
            self.node.get_logger().info(
                f"Received evasion response for {robot_id}: "
                f"{'approved' if approved else 'denied'}"
            )
            
            # Call the callback with evasion response
            self.on_evasion_response_callback(evasion_response)
            
        except json.JSONDecodeError as e:
            self.node.get_logger().error(f'Failed to parse COMC evasion response: {e}')
            
    def work_area_callback(self, msg: String):
        """
        Handle work area broadcasts from COMC.
        
        Args:
            msg: Work area message (JSON format)
        """
        try:
            data = json.loads(msg.data)
            
            # Call the callback with coordination update
            self.on_coordination_update_callback(data)
            
        except json.JSONDecodeError as e:
            self.node.get_logger().error(f'Failed to parse COMC work area: {e}')
            
    def publish_robot_intention(
        self,
        robot_id: str,
        intention: str,
        target_area: Optional[Dict] = None
    ):
        """
        Publish robot intention for coordination.
        
        Args:
            robot_id: Robot identifier
            intention: Intention description (e.g., 'moving_to', 'working_at')
            target_area: Optional target area information
        """
        msg_data = {
            'robot_id': robot_id,
            'intention': intention,
            'timestamp': time.time()
        }
        
        if target_area:
            msg_data['target_area'] = target_area
            
        msg = String()
        msg.data = json.dumps(msg_data)
        self.intention_pub.publish(msg)


class WebthreadIntegrationHandler:
    """
    Handles integration with Webthread (Central Integration Hub).
    Manages component status, configuration updates, and error reporting.
    """
    
    def __init__(
        self,
        node: Node,
        on_config_update_callback: Callable
    ):
        """
        Initialize Webthread integration.
        
        Args:
            node: ROS2 node instance
            on_config_update_callback: Callback for configuration updates
        """
        self.node = node
        self.on_config_update_callback = on_config_update_callback
        
        # Publisher for component status (1 Hz)
        self.status_pub = self.node.create_publisher(
            String,
            '/roc/status',
            10
        )
        
        # Publisher for command history/logging
        self.command_history_pub = self.node.create_publisher(
            String,
            '/roc/command_history',
            10
        )
        
        # Publisher for error reports
        self.error_pub = self.node.create_publisher(
            String,
            '/roc/errors',
            10
        )
        
        # Subscribe to Webthread configuration updates
        self.config_sub = self.node.create_subscription(
            String,
            '/webthread/config_update',
            self.config_update_callback,
            10
        )
        
        # Subscribe to Webthread commands
        self.command_sub = self.node.create_subscription(
            String,
            '/webthread/commands/roc',
            self.command_callback,
            10
        )
        
        self.node.get_logger().info("Webthread integration handler initialized")
        
    def publish_status(
        self,
        state: str,
        mode: str,
        robot_count: int,
        safety_level: str,
        additional_info: Optional[Dict] = None
    ):
        """
        Publish component status to Webthread.
        
        Args:
            state: Current state
            mode: Control mode (RPM/ADM)
            robot_count: Number of robots
            safety_level: Active safety level
            additional_info: Optional additional information
        """
        status_data = {
            'component': 'ROC',
            'state': state,
            'mode': mode,
            'robot_count': robot_count,
            'safety_level': safety_level,
            'timestamp': time.time()
        }
        
        if additional_info:
            status_data.update(additional_info)
            
        msg = String()
        msg.data = json.dumps(status_data)
        self.status_pub.publish(msg)
        
    def publish_command_history(self, command: Dict[str, Any]):
        """
        Publish command to history log.
        
        Args:
            command: Command information
        """
        msg = String()
        msg.data = json.dumps(command)
        self.command_history_pub.publish(msg)
        
    def publish_error(self, error_type: str, details: str, robot_id: Optional[str] = None):
        """
        Publish error report to Webthread.
        
        Args:
            error_type: Type of error
            details: Error details
            robot_id: Optional robot identifier
        """
        error_data = {
            'component': 'ROC',
            'error_type': error_type,
            'details': details,
            'timestamp': time.time()
        }
        
        if robot_id:
            error_data['robot_id'] = robot_id
            
        msg = String()
        msg.data = json.dumps(error_data)
        self.error_pub.publish(msg)
        
        self.node.get_logger().error(f"ROC Error: {error_type} - {details}")
        
    def config_update_callback(self, msg: String):
        """
        Handle configuration update from Webthread.
        
        Args:
            msg: Configuration update message (JSON format)
        """
        try:
            data = json.loads(msg.data)
            
            self.node.get_logger().info("Received configuration update from Webthread")
            
            # Call the callback with config update
            self.on_config_update_callback(data)
            
        except json.JSONDecodeError as e:
            self.node.get_logger().error(f'Failed to parse Webthread config update: {e}')
            
    def command_callback(self, msg: String):
        """
        Handle command from Webthread.
        
        Args:
            msg: Command message (JSON format)
        """
        try:
            data = json.loads(msg.data)
            command = data.get('command')
            
            if command == 'restart':
                self.node.get_logger().info('Restart command received from Webthread')
            elif command == 'status':
                self.node.get_logger().info('Status query received from Webthread')
            elif command == 'emergency_stop':
                self.node.get_logger().warn('Emergency stop command from Webthread')
            else:
                self.node.get_logger().warn(f'Unknown command from Webthread: {command}')
                
        except json.JSONDecodeError as e:
            self.node.get_logger().error(f'Failed to parse Webthread command: {e}')
