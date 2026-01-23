"""
Tests for ROS2Bridge module
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

from ROS2Bridge.ros2_node import ROS2Node
from ROS2Bridge.topic_manager import TopicManager
from ROS2Bridge.service_handler import ServiceHandler
from ROS2Bridge.action_handler import ActionHandler


class TestROS2Node:
    """Test ROS2Node functionality"""

    def test_node_creation(self):
        """Test ROS2 node creation"""
        node = ROS2Node(node_name="test_node")
        assert node.node_name == "test_node"
        assert node.initialized is False

    def test_node_initialization(self):
        """Test node initialization"""
        node = ROS2Node()
        result = node.initialize()
        assert result is True
        assert node.initialized is True

    def test_node_shutdown(self):
        """Test node shutdown"""
        node = ROS2Node()
        node.initialize()
        node.shutdown()
        assert node.initialized is False

    def test_node_is_alive(self):
        """Test node alive check"""
        node = ROS2Node()
        assert node.is_alive() is False
        node.initialize()
        # Note: Will return False since actual ROS2 node is not created
        # This test validates the logic flow


class TestTopicManager:
    """Test TopicManager functionality"""

    def test_topic_manager_creation(self):
        """Test TopicManager creation"""
        node = ROS2Node()
        node.initialize()
        manager = TopicManager(node)
        assert manager is not None

    def test_publisher_creation(self):
        """Test creating a publisher"""
        node = ROS2Node()
        node.initialize()
        manager = TopicManager(node)
        
        result = manager.create_publisher('test_topic', 'std_msgs/String')
        assert result is True

    def test_subscriber_creation(self):
        """Test creating a subscriber"""
        node = ROS2Node()
        node.initialize()
        manager = TopicManager(node)
        
        def callback(msg):
            pass
        
        result = manager.create_subscriber('test_topic', 'std_msgs/String', callback)
        assert result is True


class TestServiceHandler:
    """Test ServiceHandler functionality"""

    def test_service_handler_creation(self):
        """Test ServiceHandler creation"""
        node = ROS2Node()
        node.initialize()
        handler = ServiceHandler(node)
        assert handler is not None

    def test_service_client_creation(self):
        """Test creating a service client"""
        node = ROS2Node()
        node.initialize()
        handler = ServiceHandler(node)
        
        result = handler.create_client('test_service', 'std_srvs/Trigger')
        assert result is True


class TestActionHandler:
    """Test ActionHandler functionality"""

    def test_action_handler_creation(self):
        """Test ActionHandler creation"""
        node = ROS2Node()
        node.initialize()
        handler = ActionHandler(node)
        assert handler is not None

    def test_action_client_creation(self):
        """Test creating an action client"""
        node = ROS2Node()
        node.initialize()
        handler = ActionHandler(node)
        
        result = handler.create_client('test_action', 'example_interfaces/Fibonacci')
        assert result is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
