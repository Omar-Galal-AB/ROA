"""
Integration Handlers

Handles integration with existing ROA components:
- DIMC (Dimensions Collector)
- FTI (Files Type Importer)
- Webthread (Central Integration Hub)
- ROC (Robot Operator Controller)
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
from typing import Dict, Optional
from geometry_msgs.msg import Point


class DIMCIntegrationHandler:
    """
    Handles integration with DIMC (Dimensions Collector).
    Subscribes to robot positions, velocities, and obstacle data.
    """
    
    def __init__(self, node: Node, proximity_monitor, evade_coordinator):
        """
        Initialize DIMC integration.
        
        Args:
            node: ROS2 node instance
            proximity_monitor: ProximityMonitor instance
            evade_coordinator: EvadeCoordinator instance
        """
        self.node = node
        self.proximity_monitor = proximity_monitor
        self.evade_coordinator = evade_coordinator
        
        # Subscribe to DIMC position broadcasts
        self.position_subs: Dict[str, any] = {}
        
        # Subscribe to DIMC obstacle detection (for Evade subsystem)
        self.obstacle_sub = self.node.create_subscription(
            String,
            '/dimc/obstacles',
            self.obstacle_callback,
            10
        )
        
    def subscribe_to_robot_position(self, robot_id: str):
        """
        Subscribe to a specific robot's position data from DIMC.
        
        Args:
            robot_id: ID of the robot
        """
        topic_name = f'/robot/{robot_id}/pose'
        
        if robot_id not in self.position_subs:
            sub = self.node.create_subscription(
                String,
                topic_name,
                lambda msg: self.position_callback(msg, robot_id),
                10
            )
            self.position_subs[robot_id] = sub
            self.node.get_logger().info(f"Subscribed to {topic_name}")
            
    def position_callback(self, msg: String, robot_id: str):
        """
        Handle position updates from DIMC.
        
        Args:
            msg: Position message (JSON format)
            robot_id: ID of the robot
        """
        try:
            data = json.loads(msg.data)
            
            position = Point()
            position.x = data.get('x', 0.0)
            position.y = data.get('y', 0.0)
            position.z = data.get('z', 0.0)
            
            # Update proximity monitor
            self.proximity_monitor.update_robot_position(robot_id, position)
            
            # Update velocity if available
            if 'vx' in data:
                velocity = Point()
                velocity.x = data.get('vx', 0.0)
                velocity.y = data.get('vy', 0.0)
                velocity.z = data.get('vz', 0.0)
                self.proximity_monitor.update_robot_velocity(robot_id, velocity)
                
        except json.JSONDecodeError as e:
            self.node.get_logger().error(f'Failed to parse DIMC position: {e}')
            
    def obstacle_callback(self, msg: String):
        """
        Handle obstacle detection data from DIMC (for Evade subsystem).
        
        Args:
            msg: Obstacle message (JSON format)
        """
        try:
            data = json.loads(msg.data)
            obstacle_id = data.get('obstacle_id')
            
            position = Point()
            position.x = data.get('x', 0.0)
            position.y = data.get('y', 0.0)
            position.z = data.get('z', 0.0)
            
            dimensions = (
                data.get('width', 0.0),
                data.get('height', 0.0),
                data.get('depth', 0.0)
            )
            
            obstacle_type = data.get('type', 'unknown')
            
            # Update evade coordinator
            self.evade_coordinator.update_obstacle(
                obstacle_id, position, dimensions, obstacle_type
            )
            
        except json.JSONDecodeError as e:
            self.node.get_logger().error(f'Failed to parse obstacle data: {e}')


class WebthreadIntegrationHandler:
    """
    Handles integration with Webthread (Central Integration Hub).
    Reports health status and handles component coordination.
    """
    
    def __init__(self, node: Node):
        """
        Initialize Webthread integration.
        
        Args:
            node: ROS2 node instance
        """
        self.node = node
        self.robot_id = node.get_parameter('robot_id').value
        
        # Publisher for health status
        self.health_pub = self.node.create_publisher(
            String,
            f'/comc/{self.robot_id}/status',
            10
        )
        
        # Subscribe to Webthread commands
        self.command_sub = self.node.create_subscription(
            String,
            f'/webthread/commands/{self.robot_id}',
            self.command_callback,
            10
        )
        
    def publish_health_status(
        self,
        status: str,
        active_robots: int,
        conflicts: int,
        additional_info: Optional[Dict] = None
    ):
        """
        Publish health status to Webthread.
        
        Args:
            status: Component status (HEALTHY, DEGRADED, ERROR)
            active_robots: Number of active robots
            conflicts: Number of conflicts detected
            additional_info: Optional additional information
        """
        import time
        
        status_data = {
            'component': 'COMC',
            'robot_id': self.robot_id,
            'status': status,
            'timestamp': time.time(),
            'active_robots': active_robots,
            'conflicts': conflicts
        }
        
        if additional_info:
            status_data.update(additional_info)
            
        msg = String()
        msg.data = json.dumps(status_data)
        self.health_pub.publish(msg)
        
    def command_callback(self, msg: String):
        """
        Handle commands from Webthread.
        
        Args:
            msg: Command message (JSON format)
        """
        try:
            data = json.loads(msg.data)
            command = data.get('command')
            
            if command == 'restart':
                self.node.get_logger().info('Restart command received from Webthread')
                # Handle restart logic
            elif command == 'status':
                self.node.get_logger().info('Status query received from Webthread')
                # Respond with current status
            else:
                self.node.get_logger().warn(f'Unknown command: {command}')
                
        except json.JSONDecodeError as e:
            self.node.get_logger().error(f'Failed to parse command: {e}')


class ROCIntegrationHandler:
    """
    Handles integration with ROC (Robot Operator Controller).
    Receives evasion requests and sends coordination updates.
    """
    
    def __init__(self, node: Node, evade_coordinator):
        """
        Initialize ROC integration.
        
        Args:
            node: ROS2 node instance
            evade_coordinator: EvadeCoordinator instance
        """
        self.node = node
        self.evade_coordinator = evade_coordinator
        
        # Subscribe to ROC evasion requests
        self.evasion_request_sub = self.node.create_subscription(
            String,
            '/roc/evasion_request',
            self.evasion_request_callback,
            10
        )
        
        # Publisher for evasion responses
        self.evasion_response_pub = self.node.create_publisher(
            String,
            '/comc/evasion_response',
            10
        )
        
    def evasion_request_callback(self, msg: String):
        """
        Handle evasion request from ROC.
        
        Args:
            msg: Evasion request message (JSON format)
        """
        try:
            data = json.loads(msg.data)
            robot_id = data.get('robot_id')
            
            current_pos = Point()
            current_pos.x = data.get('current_x', 0.0)
            current_pos.y = data.get('current_y', 0.0)
            current_pos.z = data.get('current_z', 0.0)
            
            target_pos = Point()
            target_pos.x = data.get('target_x', 0.0)
            target_pos.y = data.get('target_y', 0.0)
            target_pos.z = data.get('target_z', 0.0)
            
            robot_type = data.get('robot_type', 'ground')
            priority = data.get('priority', 2)
            
            # Calculate detour path
            detour_path = self.evade_coordinator.calculate_detour_path(
                robot_id, current_pos, target_pos, robot_type
            )
            
            if detour_path:
                # Broadcast evasion intent
                approved = self.evade_coordinator.broadcast_evasion_intent(
                    robot_id, current_pos, target_pos, detour_path, priority
                )
                
                # Send response to ROC
                self._send_evasion_response(robot_id, approved, detour_path)
            else:
                # No path found
                self._send_evasion_response(robot_id, False, None)
                
        except json.JSONDecodeError as e:
            self.node.get_logger().error(f'Failed to parse evasion request: {e}')
            
    def _send_evasion_response(
        self,
        robot_id: str,
        approved: bool,
        path: Optional[list]
    ):
        """
        Send evasion response to ROC.
        
        Args:
            robot_id: ID of the robot
            approved: Whether evasion was approved
            path: Alternative path (if approved)
        """
        import time
        
        response_data = {
            'robot_id': robot_id,
            'approved': approved,
            'timestamp': time.time()
        }
        
        if approved and path:
            response_data['path'] = [
                {'x': p.x, 'y': p.y, 'z': p.z}
                for p in path
            ]
            
        msg = String()
        msg.data = json.dumps(response_data)
        self.evasion_response_pub.publish(msg)
        
        self.node.get_logger().info(
            f"Sent evasion response for {robot_id}: {'approved' if approved else 'denied'}"
        )


class FTIIntegrationHandler:
    """
    Handles integration with FTI (Files Type Importer).
    Receives notifications when new robots are imported.
    """
    
    def __init__(self, node: Node):
        """
        Initialize FTI integration.
        
        Args:
            node: ROS2 node instance
        """
        self.node = node
        
        # Subscribe to FTI robot import notifications
        self.robot_import_sub = self.node.create_subscription(
            String,
            '/fti/robot_imported',
            self.robot_import_callback,
            10
        )
        
    def robot_import_callback(self, msg: String):
        """
        Handle robot import notification from FTI.
        
        Args:
            msg: Robot import notification (JSON format)
        """
        try:
            data = json.loads(msg.data)
            robot_id = data.get('robot_id')
            robot_type = data.get('robot_type')
            
            self.node.get_logger().info(
                f"New robot imported: {robot_id} (type: {robot_type})"
            )
            
            # COMC will automatically handle the new robot once it starts
            # publishing position data via DIMC
            
        except json.JSONDecodeError as e:
            self.node.get_logger().error(f'Failed to parse import notification: {e}')
