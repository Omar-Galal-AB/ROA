"""
ros2_node.py
ROA - Robot Operations & Automation
Main ROS2 node for Webthread integration
"""

import logging
from typing import Optional, Dict, List
import threading

# Try to import ROS2, fall back to mock if not available
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy
    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    # Mock classes for when ROS2 is not installed
    class Node:
        pass
    class MultiThreadedExecutor:
        pass


class ROS2Node:
    """
    Main ROS2 node for Webthread integration
    
    Manages the ROS2 node lifecycle and provides interface
    for topic, service, and action communication.
    
    Features:
    - Automatic fallback to mock mode when ROS2 not available
    - Thread-safe executor for async operations
    - Configurable QoS profiles
    - Health monitoring
    """

    def __init__(self, node_name: str = "roa_webthread", namespace: str = ""):
        """
        Initialize ROS2 node
        
        Args:
            node_name: Name of the ROS2 node
            namespace: Namespace for the node
        """
        self.logger = logging.getLogger(__name__)
        self.node_name = node_name
        self.namespace = namespace
        self.node = None
        self.executor = None
        self.executor_thread = None
        self.initialized = False
        self.ros2_available = ROS2_AVAILABLE
        
        # QoS profiles
        self.qos_profiles = self._init_qos_profiles()
        
        if not self.ros2_available:
            self.logger.warning(
                "ROS2 (rclpy) not available - running in MOCK mode. "
                "Install ROS2 and rclpy for full functionality."
            )
        
        self.logger.info(f"ROS2Node created: {node_name} (ROS2: {self.ros2_available})")

    def _init_qos_profiles(self) -> Dict[str, any]:
        """Initialize common QoS profiles"""
        profiles = {}
        
        if self.ros2_available:
            # Reliable profile for critical data
            profiles['reliable'] = QoSProfile(
                reliability=QoSReliabilityPolicy.RELIABLE,
                durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
                depth=10
            )
            
            # Best effort profile for sensor data
            profiles['sensor'] = QoSProfile(
                reliability=QoSReliabilityPolicy.BEST_EFFORT,
                durability=QoSDurabilityPolicy.VOLATILE,
                depth=1
            )
            
            # System default
            profiles['default'] = QoSProfile(depth=10)
        
        return profiles

    def initialize(self) -> bool:
        """
        Initialize the ROS2 node
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if self.ros2_available:
                # Initialize ROS2
                if not rclpy.ok():
                    rclpy.init()
                
                # Create node
                if self.namespace:
                    self.node = Node(self.node_name, namespace=self.namespace)
                else:
                    self.node = Node(self.node_name)
                
                # Create multithreaded executor
                self.executor = MultiThreadedExecutor()
                self.executor.add_node(self.node)
                
                # Start executor in separate thread
                self.executor_thread = threading.Thread(
                    target=self._spin_executor,
                    daemon=True
                )
                self.executor_thread.start()
                
                self.logger.info(
                    f"ROS2 node '{self.node_name}' initialized with multithreaded executor"
                )
            else:
                # Mock mode initialization
                self.node = type('MockNode', (), {
                    'get_name': lambda: self.node_name,
                    'get_namespace': lambda: self.namespace
                })()
                self.logger.info(
                    f"ROS2 node '{self.node_name}' initialized in MOCK mode"
                )
            
            self.initialized = True
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize ROS2 node: {e}")
            return False

    def _spin_executor(self):
        """Spin the executor (runs in separate thread)"""
        try:
            self.executor.spin()
        except Exception as e:
            self.logger.error(f"Executor error: {e}")

    def shutdown(self):
        """Shutdown the ROS2 node"""
        if self.initialized:
            try:
                if self.ros2_available and self.node:
                    # Stop executor
                    if self.executor:
                        self.executor.shutdown()
                        if self.executor_thread and self.executor_thread.is_alive():
                            self.executor_thread.join(timeout=2.0)
                    
                    # Destroy node
                    self.node.destroy_node()
                    
                    # Shutdown rclpy if no other nodes
                    try:
                        rclpy.shutdown()
                    except:
                        pass  # Might already be shutdown
                
                self.initialized = False
                self.logger.info(f"ROS2 node '{self.node_name}' shutdown")
                
            except Exception as e:
                self.logger.error(f"Error during ROS2 node shutdown: {e}")

    def spin_once(self, timeout_sec: float = 0.1):
        """
        Spin the node once to process callbacks
        
        Note: When using multithreaded executor, this is handled automatically.
        This method is for compatibility/testing.
        
        Args:
            timeout_sec: Timeout in seconds
        """
        if not self.ros2_available:
            return
            
        if self.initialized and self.node and not self.executor:
            # Only needed if not using executor
            try:
                rclpy.spin_once(self.node, timeout_sec=timeout_sec)
            except Exception as e:
                self.logger.error(f"Error in spin_once: {e}")

    def is_alive(self) -> bool:
        """
        Check if node is alive
        
        Returns:
            True if node is running, False otherwise
        """
        if not self.initialized:
            return False
            
        if self.ros2_available:
            return self.node is not None and rclpy.ok()
        else:
            return self.node is not None
    
    def get_qos_profile(self, profile_name: str = 'default'):
        """
        Get a QoS profile by name
        
        Args:
            profile_name: Name of profile ('reliable', 'sensor', 'default')
            
        Returns:
            QoS profile or depth value for mock mode
        """
        if self.ros2_available:
            return self.qos_profiles.get(profile_name, self.qos_profiles['default'])
        else:
            # Return depth value for mock mode
            return 10
