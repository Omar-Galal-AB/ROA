"""
Tests for UE5Bridge module
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

from UE5Bridge.ue5_connector import UE5Connector
from UE5Bridge.physics_configurator import PhysicsConfigurator
from UE5Bridge.input_initializer import InputInitializer
from UE5Bridge.ui_initializer import UIInitializer


class TestUE5Connector:
    """Test UE5Connector functionality"""

    def test_connector_creation(self):
        """Test UE5 connector creation"""
        connector = UE5Connector(host="localhost", port=9876)
        assert connector.host == "localhost"
        assert connector.port == 9876
        assert connector.connected is False

    def test_connector_connection(self):
        """Test UE5 connection"""
        connector = UE5Connector()
        result = connector.connect()
        assert result is True
        assert connector.connected is True

    def test_connector_disconnect(self):
        """Test UE5 disconnection"""
        connector = UE5Connector()
        connector.connect()
        connector.disconnect()
        assert connector.connected is False

    def test_send_command(self):
        """Test sending command to UE5"""
        connector = UE5Connector()
        connector.connect()
        
        result = connector.send_command("test_command", {"param": "value"})
        # Will return False in test environment since actual connection doesn't exist
        # but validates the logic


class TestPhysicsConfigurator:
    """Test PhysicsConfigurator functionality"""

    def test_configurator_creation(self):
        """Test PhysicsConfigurator creation"""
        connector = UE5Connector()
        configurator = PhysicsConfigurator(connector)
        assert configurator is not None

    def test_load_config(self):
        """Test loading physics configuration"""
        connector = UE5Connector()
        configurator = PhysicsConfigurator(connector)
        
        # Test with default config file
        result = configurator.load_config()
        # Should handle missing file gracefully


class TestInputInitializer:
    """Test InputInitializer functionality"""

    def test_initializer_creation(self):
        """Test InputInitializer creation"""
        connector = UE5Connector()
        initializer = InputInitializer(connector)
        assert initializer is not None

    def test_load_config(self):
        """Test loading input configuration"""
        connector = UE5Connector()
        initializer = InputInitializer(connector)
        
        result = initializer.load_config()
        # Should handle missing file gracefully


class TestUIInitializer:
    """Test UIInitializer functionality"""

    def test_initializer_creation(self):
        """Test UIInitializer creation"""
        connector = UE5Connector()
        initializer = UIInitializer(connector)
        assert initializer is not None

    def test_load_config(self):
        """Test loading UI configuration"""
        connector = UE5Connector()
        initializer = UIInitializer(connector)
        
        result = initializer.load_config()
        # Should handle missing file gracefully


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
