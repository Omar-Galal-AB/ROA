"""
Service Handlers

ROS2 service implementations for COMC.
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
from typing import Optional
from geometry_msgs.msg import Point, Vector3


class ServiceHandlers:
    """
    Handles ROS2 service requests for COMC.
    """
    
    def __init__(self, node: Node, task_coordinator, work_area_manager, proximity_monitor):
        """
        Initialize service handlers.
        
        Args:
            node: ROS2 node instance
            task_coordinator: TaskCoordinator instance
            work_area_manager: WorkAreaManager instance
            proximity_monitor: ProximityMonitor instance
        """
        self.node = node
        self.task_coordinator = task_coordinator
        self.work_area_manager = work_area_manager
        self.proximity_monitor = proximity_monitor
        
        # Create services (using String for now until custom services are built)
        self.coordinate_task_srv = self.node.create_service(
            String,
            '/comc/coordinate_task',
            self.handle_coordinate_task
        )
        
        self.reserve_area_srv = self.node.create_service(
            String,
            '/comc/reserve_area',
            self.handle_reserve_area
        )
        
        self.query_proximity_srv = self.node.create_service(
            String,
            '/comc/query_proximity',
            self.handle_query_proximity
        )
        
        self.node.get_logger().info("Service handlers initialized")
        
    def handle_coordinate_task(self, request, response):
        """
        Handle task coordination service request.
        
        Args:
            request: Service request (JSON in String.data)
            response: Service response
            
        Returns:
            Response with coordination result
        """
        try:
            data = json.loads(request.data)
            
            robot_id = data.get('requesting_robot_id')
            task_type = data.get('task_type')
            required_resources = data.get('required_resources', [])
            priority = data.get('priority', 2)
            
            # Request coordination
            approved, conflicts, suggestion = self.task_coordinator.request_task_coordination(
                robot_id, task_type, required_resources, priority
            )
            
            # Prepare response
            response_data = {
                'approved': approved,
                'conflicting_robots': conflicts,
                'alternative_suggestion': suggestion
            }
            
            response.data = json.dumps(response_data)
            
        except Exception as e:
            self.node.get_logger().error(f"Error in coordinate_task service: {e}")
            response.data = json.dumps({
                'approved': False,
                'conflicting_robots': [],
                'alternative_suggestion': f'Service error: {str(e)}'
            })
            
        return response
        
    def handle_reserve_area(self, request, response):
        """
        Handle area reservation service request.
        
        Args:
            request: Service request (JSON in String.data)
            response: Service response
            
        Returns:
            Response with reservation result
        """
        try:
            data = json.loads(request.data)
            
            robot_id = data.get('robot_id')
            center = Point()
            center.x = data.get('center_x', 0.0)
            center.y = data.get('center_y', 0.0)
            center.z = data.get('center_z', 0.0)
            
            dimensions = Vector3()
            dimensions.x = data.get('width', 1.0)
            dimensions.y = data.get('height', 1.0)
            dimensions.z = data.get('depth', 1.0)
            
            duration = data.get('duration', 0.0)
            
            # Check for conflicts
            conflicts = self.work_area_manager.get_all_conflicts()
            
            if conflicts:
                approved = False
                message = f"Area conflicts with robots: {', '.join(conflicts)}"
            else:
                approved = True
                message = "Area reserved successfully"
                # Note: Actual reservation would be tracked separately
                
            response_data = {
                'approved': approved,
                'message': message
            }
            
            response.data = json.dumps(response_data)
            
        except Exception as e:
            self.node.get_logger().error(f"Error in reserve_area service: {e}")
            response.data = json.dumps({
                'approved': False,
                'message': f'Service error: {str(e)}'
            })
            
        return response
        
    def handle_query_proximity(self, request, response):
        """
        Handle proximity query service request.
        
        Args:
            request: Service request (JSON in String.data)
            response: Service response
            
        Returns:
            Response with proximity information
        """
        try:
            data = json.loads(request.data)
            robot_id = data.get('robot_id')
            
            # Get distances to all robots
            distances = self.proximity_monitor.get_distances_to_all()
            
            # Filter for the requesting robot
            if robot_id in self.proximity_monitor.robot_positions:
                # Get distances from this robot's perspective
                nearby_robots = []
                nearby_distances = []
                
                for other_robot_id, distance in distances.items():
                    if other_robot_id != robot_id:
                        nearby_robots.append(other_robot_id)
                        nearby_distances.append(distance)
                        
                response_data = {
                    'nearby_robot_ids': nearby_robots,
                    'distances': nearby_distances
                }
            else:
                response_data = {
                    'nearby_robot_ids': [],
                    'distances': []
                }
                
            response.data = json.dumps(response_data)
            
        except Exception as e:
            self.node.get_logger().error(f"Error in query_proximity service: {e}")
            response.data = json.dumps({
                'nearby_robot_ids': [],
                'distances': []
            })
            
        return response
