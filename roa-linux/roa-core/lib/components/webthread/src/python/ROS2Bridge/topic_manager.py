"""
topic_manager.py
ROA - Robot Operations & Automation
ROS2 topic management for publishers and subscribers
"""

import logging
from typing import Optional, Callable, Any, Dict, Union
import time


class MockPublisher:
    """Mock publisher for when ROS2 is not available"""
    def __init__(self, topic_name: str, msg_type: Any):
        self.topic_name = topic_name
        self.msg_type = msg_type
        self.publish_count = 0
        self.last_message = None
    
    def publish(self, message: Any):
        """Mock publish"""
        self.last_message = message
        self.publish_count += 1


class MockSubscriber:
    """Mock subscriber for when ROS2 is not available"""
    def __init__(self, topic_name: str, msg_type: Any, callback: Callable):
        self.topic_name = topic_name
        self.msg_type = msg_type
        self.callback = callback
        self.message_count = 0


class TopicManager:
    """
    Manages ROS2 topics for publishing and subscribing
    
    Features:
    - Automatic detection of ROS2 availability
    - Mock mode for testing without ROS2
    - Support for named and custom QoS profiles
    - Topic statistics tracking
    """

    def __init__(self, ros2_node):
        """
        Initialize TopicManager
        
        Args:
            ros2_node: ROS2Node instance
        """
        self.logger = logging.getLogger(__name__)
        self.ros2_node = ros2_node
        self.publishers: Dict[str, Any] = {}
        self.subscribers: Dict[str, Any] = {}
        self.stats: Dict[str, Dict] = {}
        
        self.logger.info(
            f"TopicManager initialized (ROS2: {self.ros2_node.ros2_available})"
        )

    def create_publisher(self, topic_name: str, msg_type: Any, 
                        qos_profile: Union[str, Any, int] = 'default'):
        """
        Create a publisher for a topic
        
        Args:
            topic_name: Name of the topic
            msg_type: Message type class
            qos_profile: QoS profile (name string, profile object, or depth int)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if self.ros2_node.ros2_available and self.ros2_node.node:
                # Get QoS profile
                if isinstance(qos_profile, str):
                    qos = self.ros2_node.get_qos_profile(qos_profile)
                elif isinstance(qos_profile, int):
                    from rclpy.qos import QoSProfile
                    qos = QoSProfile(depth=qos_profile)
                else:
                    qos = qos_profile
                
                # Create actual ROS2 publisher
                publisher = self.ros2_node.node.create_publisher(
                    msg_type, topic_name, qos
                )
                self.publishers[topic_name] = publisher
                self.logger.info(
                    f"ROS2 publisher created for topic: {topic_name}"
                )
            else:
                # Create mock publisher
                publisher = MockPublisher(topic_name, msg_type)
                self.publishers[topic_name] = publisher
                self.logger.info(
                    f"Mock publisher created for topic: {topic_name}"
                )
            
            # Initialize statistics
            self.stats[topic_name] = {
                'type': 'publisher',
                'msg_type': msg_type.__name__ if hasattr(msg_type, '__name__') else str(msg_type),
                'publish_count': 0,
                'created_at': time.time()
            }
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create publisher for {topic_name}: {e}")
            return False

    def create_subscriber(self, topic_name: str, msg_type: Any, 
                         callback: Callable, qos_profile: Union[str, Any, int] = 'default'):
        """
        Create a subscriber for a topic
        
        Args:
            topic_name: Name of the topic
            msg_type: Message type class
            callback: Callback function for received messages
            qos_profile: QoS profile (name string, profile object, or depth int)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if self.ros2_node.ros2_available and self.ros2_node.node:
                # Get QoS profile
                if isinstance(qos_profile, str):
                    qos = self.ros2_node.get_qos_profile(qos_profile)
                elif isinstance(qos_profile, int):
                    from rclpy.qos import QoSProfile
                    qos = QoSProfile(depth=qos_profile)
                else:
                    qos = qos_profile
                
                # Create actual ROS2 subscriber
                subscriber = self.ros2_node.node.create_subscription(
                    msg_type, topic_name, callback, qos
                )
                self.subscribers[topic_name] = subscriber
                self.logger.info(
                    f"ROS2 subscriber created for topic: {topic_name}"
                )
            else:
                # Create mock subscriber
                subscriber = MockSubscriber(topic_name, msg_type, callback)
                self.subscribers[topic_name] = subscriber
                self.logger.info(
                    f"Mock subscriber created for topic: {topic_name}"
                )
            
            # Initialize statistics
            self.stats[topic_name] = {
                'type': 'subscriber',
                'msg_type': msg_type.__name__ if hasattr(msg_type, '__name__') else str(msg_type),
                'message_count': 0,
                'created_at': time.time()
            }
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create subscriber for {topic_name}: {e}")
            return False

    def publish(self, topic_name: str, message: Any):
        """
        Publish a message to a topic
        
        Args:
            topic_name: Name of the topic
            message: Message to publish
        """
        if topic_name not in self.publishers:
            self.logger.warning(f"No publisher found for topic: {topic_name}")
            return
        
        try:
            publisher = self.publishers[topic_name]
            publisher.publish(message)
            
            # Update statistics
            if topic_name in self.stats:
                self.stats[topic_name]['publish_count'] += 1
                self.stats[topic_name]['last_publish'] = time.time()
            
            self.logger.debug(f"Published to {topic_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to publish to {topic_name}: {e}")

    def destroy_publisher(self, topic_name: str):
        """Destroy a publisher"""
        if topic_name not in self.publishers:
            self.logger.warning(f"Publisher not found for topic: {topic_name}")
            return
        
        try:
            if self.ros2_node.ros2_available and self.ros2_node.node:
                # Destroy ROS2 publisher
                self.ros2_node.node.destroy_publisher(self.publishers[topic_name])
            
            del self.publishers[topic_name]
            
            # Remove statistics
            if topic_name in self.stats:
                del self.stats[topic_name]
            
            self.logger.info(f"Publisher destroyed for topic: {topic_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to destroy publisher for {topic_name}: {e}")

    def destroy_subscriber(self, topic_name: str):
        """Destroy a subscriber"""
        if topic_name not in self.subscribers:
            self.logger.warning(f"Subscriber not found for topic: {topic_name}")
            return
        
        try:
            if self.ros2_node.ros2_available and self.ros2_node.node:
                # Destroy ROS2 subscriber
                self.ros2_node.node.destroy_subscription(self.subscribers[topic_name])
            
            del self.subscribers[topic_name]
            
            # Remove statistics
            if topic_name in self.stats:
                del self.stats[topic_name]
            
            self.logger.info(f"Subscriber destroyed for topic: {topic_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to destroy subscriber for {topic_name}: {e}")
    
    def get_publishers(self) -> Dict[str, Any]:
        """Get all active publishers"""
        return self.publishers.copy()
    
    def get_subscribers(self) -> Dict[str, Any]:
        """Get all active subscribers"""
        return self.subscribers.copy()
    
    def get_stats(self) -> Dict[str, Dict]:
        """Get topic statistics"""
        return self.stats.copy()
    
    def has_publisher(self, topic_name: str) -> bool:
        """Check if publisher exists for topic"""
        return topic_name in self.publishers
    
    def has_subscriber(self, topic_name: str) -> bool:
        """Check if subscriber exists for topic"""
        return topic_name in self.subscribers
