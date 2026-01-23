"""
Integration tests for Webthread component
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "python"))

from ROS2Bridge.ros2_node import ROS2Node
from UE5Bridge.ue5_connector import UE5Connector
from webthread_core import WebthreadCore
from webthread_initializer import WebthreadInitializer


class TestWebthreadIntegration:
    """Integration tests for Webthread"""

    def test_full_initialization_flow(self):
        """Test complete initialization flow"""
        # This test validates the initialization sequence
        # without requiring actual ROS2/UE5 connections

        initializer = WebthreadInitializer()

        # Pre-checks phase
        result = initializer.run_prechecks()
        assert "version_check" in result

    def test_ros2_ue5_bridge_integration(self):
        """Test ROS2 to UE5 data bridge"""
        # Create ROS2 node
        ros2_node = ROS2Node("integration_test_node")
        ros2_node.initialize()

        # Create UE5 connector
        ue5_connector = UE5Connector()
        ue5_connector.connect()

        # Both should be initialized
        assert ros2_node.initialized is True
        assert ue5_connector.connected is True

        # Cleanup
        ros2_node.shutdown()
        ue5_connector.disconnect()

    def test_component_coordination(self):
        """Test component startup coordination"""
        core = WebthreadCore()
        core.start()

        # All components should be registered
        assert "FTI" in core.components
        assert "DIMC" in core.components
        assert "ROC" in core.components
        assert "COMC" in core.components
        assert "ROS2Bridge" in core.components
        assert "UE5Bridge" in core.components

        core.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
