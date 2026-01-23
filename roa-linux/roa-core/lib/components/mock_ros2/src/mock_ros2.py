"""
Mock ROS2 System for Testing ROA Components
Simulates ROS2 pub/sub without requiring ROS2 installation
"""

import time
import threading
from typing import Dict, List, Callable, Any, Optional
from collections import defaultdict
import json
from dataclasses import dataclass, asdict


class MockMessage:
    """Base class for all mock ROS2 messages"""
    
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
    
    def to_dict(self):
        return self.__dict__
    
    def from_dict(self, data):
        self.__dict__.update(data)
        return self


class MockPublisher:
    """Simulates ROS2 publisher"""
    
    def __init__(self, topic_name: str, message_type: type):
        self.topic_name = topic_name
        self.message_type = message_type
        self.subscribers = []
        self.message_count = 0
    
    def publish(self, message: MockMessage):
        """Publish message to all subscribers"""
        self.message_count += 1
        for callback in self.subscribers:
            try:
                callback(message)
            except Exception as e:
                print(f"Error in subscriber callback: {e}")
    
    def add_subscriber(self, callback: Callable):
        """Add subscriber callback"""
        self.subscribers.append(callback)
    
    def get_num_subscribers(self) -> int:
        """Get number of subscribers"""
        return len(self.subscribers)


class MockSubscriber:
    """Simulates ROS2 subscriber"""
    
    def __init__(self, topic_name: str, message_type: type, callback: Callable):
        self.topic_name = topic_name
        self.message_type = message_type
        self.callback = callback
        self.message_count = 0
    
    def process_message(self, message: MockMessage):
        """Process received message"""
        self.message_count += 1
        self.callback(message)


class MockNode:
    """Simulates ROS2 node"""
    
    def __init__(self, name: str):
        self.name = name
        self.publishers = {}
        self.subscribers = {}
        self.services = {}
        self.running = True
    
    def create_publisher(self, message_type: type, topic_name: str, qos: int = 10):
        """Create publisher"""
        publisher = MockPublisher(topic_name, message_type)
        self.publishers[topic_name] = publisher
        
        # Register with global topic registry
        MockROS2System.register_publisher(topic_name, publisher)
        
        return publisher
    
    def create_subscription(self, message_type: type, topic_name: str, 
                          callback: Callable, qos: int = 10):
        """Create subscription"""
        subscriber = MockSubscriber(topic_name, message_type, callback)
        self.subscribers[topic_name] = subscriber
        
        # Register with global topic registry
        MockROS2System.register_subscriber(topic_name, subscriber)
        
        return subscriber
    
    def create_service(self, service_type: type, service_name: str, callback: Callable):
        """Create service"""
        self.services[service_name] = callback
        MockROS2System.register_service(service_name, callback)
        return service_name
    
    def create_client(self, service_type: type, service_name: str):
        """Create service client"""
        return MockServiceClient(service_name)
    
    def spin_once(self, timeout: float = 0.0):
        """Process one round of callbacks"""
        time.sleep(timeout)
    
    def spin(self):
        """Spin continuously"""
        while self.running:
            self.spin_once(0.01)
    
    def destroy_node(self):
        """Clean up node resources"""
        self.running = False
        self.publishers.clear()
        self.subscribers.clear()


class MockServiceClient:
    """Mock service client"""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
    
    def call(self, request):
        """Call service"""
        handler = MockROS2System.get_service(self.service_name)
        if handler:
            return handler(request)
        return None


class MockROS2System:
    """Global ROS2 system simulator"""
    
    topics = defaultdict(lambda: {'publishers': [], 'subscribers': []})
    services = {}
    _lock = threading.Lock()
    
    @classmethod
    def register_publisher(cls, topic_name: str, publisher: MockPublisher):
        """Register publisher with system"""
        with cls._lock:
            cls.topics[topic_name]['publishers'].append(publisher)
            
            # Connect to existing subscribers
            for subscriber in cls.topics[topic_name]['subscribers']:
                publisher.add_subscriber(subscriber.callback)
    
    @classmethod
    def register_subscriber(cls, topic_name: str, subscriber: MockSubscriber):
        """Register subscriber with system"""
        with cls._lock:
            cls.topics[topic_name]['subscribers'].append(subscriber)
            
            # Connect to existing publishers
            for publisher in cls.topics[topic_name]['publishers']:
                publisher.add_subscriber(subscriber.callback)
    
    @classmethod
    def register_service(cls, service_name: str, handler: Callable):
        """Register service"""
        with cls._lock:
            cls.services[service_name] = handler
    
    @classmethod
    def get_service(cls, service_name: str):
        """Get service handler"""
        return cls.services.get(service_name)
    
    @classmethod
    def get_topic_info(cls, topic_name: str) -> Dict:
        """Get topic information"""
        with cls._lock:
            info = cls.topics[topic_name]
            return {
                'num_publishers': len(info['publishers']),
                'num_subscribers': len(info['subscribers'])
            }
    
    @classmethod
    def list_topics(cls) -> List[str]:
        """List all topics"""
        with cls._lock:
            return list(cls.topics.keys())
    
    @classmethod
    def clear(cls):
        """Clear all topics (for testing)"""
        with cls._lock:
            cls.topics.clear()
            cls.services.clear()


# Mock ROS2 message types for ROA
class JointState(MockMessage):
    """Mock sensor_msgs/JointState"""
    
    def __init__(self):
        super().__init__(
            header={},
            name=[],
            position=[],
            velocity=[],
            effort=[]
        )


class SpatialData(MockMessage):
    """Mock dimc_interfaces/SpatialData"""
    
    def __init__(self):
        super().__init__(
            robot_id="",
            position=[0.0, 0.0, 0.0],
            orientation=[0.0, 0.0, 0.0, 1.0],
            velocity=[0.0, 0.0, 0.0],
            dimensions=[0.0, 0.0, 0.0]
        )


class ControlCommand(MockMessage):
    """Mock roc_interfaces/ControlCommand"""
    
    def __init__(self):
        super().__init__(
            robot_id="",
            command_type="",
            joint_values=[],
            priority=0,
            timestamp=0.0
        )


class RobotSpecs(MockMessage):
    """Mock fti_interfaces/RobotSpecs"""
    
    def __init__(self):
        super().__init__(
            robot_id="",
            robot_type="",
            num_joints=0,
            joint_names=[],
            joint_limits=[],
            gripper_config={}
        )


class ProximityAlert(MockMessage):
    """Mock comc_interfaces/ProximityAlert"""
    
    def __init__(self):
        super().__init__(
            robot_id="",
            other_robot_id="",
            distance=0.0,
            severity="",
            timestamp=0.0
        )


class SystemStatus(MockMessage):
    """Mock webthread_interfaces/SystemStatus"""
    
    def __init__(self):
        super().__init__(
            component_name="",
            health_status=0,
            cpu_usage=0.0,
            memory_usage=0.0,
            uptime_seconds=0,
            errors=[]
        )


# Mock rclpy functions
def init(args=None):
    """Mock rclpy.init"""
    pass


def shutdown():
    """Mock rclpy.shutdown"""
    MockROS2System.clear()


def spin_once(node, timeout_sec=None):
    """Mock rclpy.spin_once"""
    node.spin_once(timeout_sec or 0.0)


def spin(node):
    """Mock rclpy.spin"""
    node.spin()


def create_node(name):
    """Mock rclpy.create_node"""
    return MockNode(name)
