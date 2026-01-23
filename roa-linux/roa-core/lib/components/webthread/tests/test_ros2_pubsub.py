"""
test_ros2_pubsub.py
ROA - Robot Operations & Automation
Tests for ROS2 publisher/subscriber implementation
"""

import pytest
import sys
import os
import time
from unittest.mock import Mock, MagicMock

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

from ROS2Bridge.ros2_node import ROS2Node
from ROS2Bridge.topic_manager import TopicManager, MockPublisher, MockSubscriber


class TestROS2NodeInitialization:
    """Test ROS2Node initialization"""
    
    def test_node_creation(self):
        """Test basic node creation"""
        node = ROS2Node("test_node")
        assert node.node_name == "test_node"
        assert node.namespace == ""
        assert not node.initialized
    
    def test_node_with_namespace(self):
        """Test node creation with namespace"""
        node = ROS2Node("test_node", namespace="/test")
        assert node.node_name == "test_node"
        assert node.namespace == "/test"
    
    def test_node_initialization(self):
        """Test node initialization"""
        node = ROS2Node("test_node")
        result = node.initialize()
        assert result is True
        assert node.initialized is True
        node.shutdown()
    
    def test_node_is_alive(self):
        """Test node alive check"""
        node = ROS2Node("test_node")
        assert not node.is_alive()
        
        node.initialize()
        assert node.is_alive()
        
        node.shutdown()
        assert not node.is_alive()
    
    def test_qos_profiles(self):
        """Test QoS profile initialization"""
        node = ROS2Node("test_node")
        node.initialize()
        
        # Should have QoS profiles
        assert node.qos_profiles is not None
        
        # Should be able to get profiles
        qos = node.get_qos_profile('default')
        assert qos is not None
        
        node.shutdown()


class TestMockPublisher:
    """Test MockPublisher for non-ROS2 environments"""
    
    def test_mock_publisher_creation(self):
        """Test creating mock publisher"""
        pub = MockPublisher("/test/topic", str)
        assert pub.topic_name == "/test/topic"
        assert pub.msg_type == str
        assert pub.publish_count == 0
    
    def test_mock_publisher_publish(self):
        """Test publishing with mock publisher"""
        pub = MockPublisher("/test/topic", str)
        pub.publish("test message")
        
        assert pub.publish_count == 1
        assert pub.last_message == "test message"
        
        pub.publish("another message")
        assert pub.publish_count == 2
        assert pub.last_message == "another message"


class TestMockSubscriber:
    """Test MockSubscriber for non-ROS2 environments"""
    
    def test_mock_subscriber_creation(self):
        """Test creating mock subscriber"""
        callback = Mock()
        sub = MockSubscriber("/test/topic", str, callback)
        
        assert sub.topic_name == "/test/topic"
        assert sub.msg_type == str
        assert sub.callback == callback
        assert sub.message_count == 0


class TestTopicManager:
    """Test TopicManager functionality"""
    
    def test_topic_manager_creation(self):
        """Test creating topic manager"""
        node = ROS2Node("test_node")
        node.initialize()
        
        manager = TopicManager(node)
        assert manager.ros2_node == node
        assert len(manager.publishers) == 0
        assert len(manager.subscribers) == 0
        
        node.shutdown()
    
    def test_create_publisher(self):
        """Test creating a publisher"""
        node = ROS2Node("test_node")
        node.initialize()
        manager = TopicManager(node)
        
        result = manager.create_publisher("/test/topic", str)
        assert result is True
        assert manager.has_publisher("/test/topic")
        assert len(manager.publishers) == 1
        
        # Check statistics
        stats = manager.get_stats()
        assert "/test/topic" in stats
        assert stats["/test/topic"]['type'] == 'publisher'
        
        node.shutdown()
    
    def test_create_subscriber(self):
        """Test creating a subscriber"""
        node = ROS2Node("test_node")
        node.initialize()
        manager = TopicManager(node)
        
        def callback(msg):
            pass
        
        result = manager.create_subscriber("/test/topic", str, callback)
        assert result is True
        assert manager.has_subscriber("/test/topic")
        assert len(manager.subscribers) == 1
        
        # Check statistics
        stats = manager.get_stats()
        assert "/test/topic" in stats
        assert stats["/test/topic"]['type'] == 'subscriber'
        
        node.shutdown()
    
    def test_publish_message(self):
        """Test publishing a message"""
        node = ROS2Node("test_node")
        node.initialize()
        manager = TopicManager(node)
        
        manager.create_publisher("/test/topic", str)
        manager.publish("/test/topic", "test message")
        
        # In mock mode, check the mock publisher
        pub = manager.publishers["/test/topic"]
        assert pub.publish_count == 1
        assert pub.last_message == "test message"
        
        # Check statistics updated
        stats = manager.get_stats()
        assert stats["/test/topic"]['publish_count'] == 1
        
        node.shutdown()
    
    def test_publish_without_publisher(self):
        """Test publishing to non-existent topic"""
        node = ROS2Node("test_node")
        node.initialize()
        manager = TopicManager(node)
        
        # Should not raise error, just log warning
        manager.publish("/test/topic", "test message")
        
        node.shutdown()
    
    def test_destroy_publisher(self):
        """Test destroying a publisher"""
        node = ROS2Node("test_node")
        node.initialize()
        manager = TopicManager(node)
        
        manager.create_publisher("/test/topic", str)
        assert manager.has_publisher("/test/topic")
        
        manager.destroy_publisher("/test/topic")
        assert not manager.has_publisher("/test/topic")
        assert len(manager.publishers) == 0
        
        node.shutdown()
    
    def test_destroy_subscriber(self):
        """Test destroying a subscriber"""
        node = ROS2Node("test_node")
        node.initialize()
        manager = TopicManager(node)
        
        def callback(msg):
            pass
        
        manager.create_subscriber("/test/topic", str, callback)
        assert manager.has_subscriber("/test/topic")
        
        manager.destroy_subscriber("/test/topic")
        assert not manager.has_subscriber("/test/topic")
        assert len(manager.subscribers) == 0
        
        node.shutdown()
    
    def test_multiple_publishers(self):
        """Test creating multiple publishers"""
        node = ROS2Node("test_node")
        node.initialize()
        manager = TopicManager(node)
        
        manager.create_publisher("/topic1", str)
        manager.create_publisher("/topic2", int)
        manager.create_publisher("/topic3", float)
        
        assert len(manager.publishers) == 3
        assert manager.has_publisher("/topic1")
        assert manager.has_publisher("/topic2")
        assert manager.has_publisher("/topic3")
        
        pubs = manager.get_publishers()
        assert len(pubs) == 3
        
        node.shutdown()
    
    def test_qos_profile_variations(self):
        """Test different QoS profile specifications"""
        node = ROS2Node("test_node")
        node.initialize()
        manager = TopicManager(node)
        
        # String name
        result1 = manager.create_publisher("/topic1", str, 'reliable')
        assert result1 is True
        
        # Integer depth
        result2 = manager.create_publisher("/topic2", str, 20)
        assert result2 is True
        
        # Default
        result3 = manager.create_publisher("/topic3", str)
        assert result3 is True
        
        assert len(manager.publishers) == 3
        
        node.shutdown()


class TestIntegration:
    """Integration tests for ROS2 pub/sub"""
    
    def test_pubsub_workflow(self):
        """Test complete pub/sub workflow"""
        node = ROS2Node("test_node")
        node.initialize()
        manager = TopicManager(node)
        
        # Create publisher
        manager.create_publisher("/robot/commands", str, 'reliable')
        
        # Create subscriber
        received_messages = []
        def callback(msg):
            received_messages.append(msg)
        
        manager.create_subscriber("/robot/status", str, callback, 'sensor')
        
        # Publish messages
        for i in range(5):
            manager.publish("/robot/commands", f"command_{i}")
        
        # Verify
        pub = manager.publishers["/robot/commands"]
        assert pub.publish_count == 5
        
        # Check statistics
        stats = manager.get_stats()
        assert stats["/robot/commands"]['publish_count'] == 5
        
        # Cleanup
        manager.destroy_publisher("/robot/commands")
        manager.destroy_subscriber("/robot/status")
        
        assert len(manager.publishers) == 0
        assert len(manager.subscribers) == 0
        
        node.shutdown()
    
    def test_multiple_nodes(self):
        """Test multiple ROS2 nodes"""
        node1 = ROS2Node("node1")
        node2 = ROS2Node("node2")
        
        node1.initialize()
        node2.initialize()
        
        manager1 = TopicManager(node1)
        manager2 = TopicManager(node2)
        
        # Create publishers on different nodes
        manager1.create_publisher("/shared/topic", str)
        manager2.create_publisher("/other/topic", str)
        
        assert manager1.has_publisher("/shared/topic")
        assert manager2.has_publisher("/other/topic")
        
        node1.shutdown()
        node2.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
