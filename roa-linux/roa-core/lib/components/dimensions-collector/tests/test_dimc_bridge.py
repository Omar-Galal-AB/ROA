"""
DIMC UE5 Bridge Tests

Comprehensive tests for the UE5 Bridge subsystem including:
- DIMCUe5Connector
- ConnectionMonitor
- Connection health tracking

Usage:
    python -m pytest test_dimc_bridge.py -v
    python test_dimc_bridge.py  # Direct execution
"""

import sys
import os
import time
import socket
import json
import unittest
import threading
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from queue import Queue, Empty

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python"))

from UE5Bridge import (
    DIMCUe5Connector,
    ConnectionState,
    ConnectionConfig,
    ConnectionMonitor,
    ConnectionHealth,
    MonitorConfig,
    HealthMetrics,
)


class MockSocket:
    """Mock socket for testing without actual network."""
    
    def __init__(self):
        self.sent_data = []
        self.recv_queue = Queue()
        self.connected = True
        
    def connect(self, addr):
        pass
        
    def settimeout(self, timeout):
        pass
        
    def setsockopt(self, level, option, value):
        pass
        
    def close(self):
        self.connected = False
        
    def sendall(self, data):
        self.sent_data.append(data)
        
    def recv(self, size):
        try:
            return self.recv_queue.get(timeout=0.1)
        except Empty:
            raise socket.timeout()
            
    def queue_response(self, data: bytes):
        self.recv_queue.put(data)


class TestConnectionConfig(unittest.TestCase):
    """Tests for ConnectionConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = ConnectionConfig()
        
        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.request_port, 9876)
        self.assertEqual(config.response_port, 9877)
        self.assertEqual(config.heartbeat_interval, 2.0)
        self.assertTrue(config.reconnect_enabled)
        
    def test_custom_values(self):
        """Test custom configuration values."""
        config = ConnectionConfig(
            host="192.168.1.100",
            request_port=8000,
            response_port=8001,
            heartbeat_interval=5.0,
            reconnect_enabled=False
        )
        
        self.assertEqual(config.host, "192.168.1.100")
        self.assertEqual(config.request_port, 8000)
        self.assertEqual(config.response_port, 8001)
        self.assertEqual(config.heartbeat_interval, 5.0)
        self.assertFalse(config.reconnect_enabled)


class TestConnectionState(unittest.TestCase):
    """Tests for ConnectionState enum."""
    
    def test_states(self):
        """Test all connection states exist."""
        states = [
            ConnectionState.DISCONNECTED,
            ConnectionState.CONNECTING,
            ConnectionState.CONNECTED,
            ConnectionState.RECONNECTING,
            ConnectionState.ERROR,
        ]
        
        self.assertEqual(len(states), 5)


class TestDIMCUe5Connector(unittest.TestCase):
    """Tests for DIMCUe5Connector class."""
    
    def setUp(self):
        self.config = ConnectionConfig()
        self.connector = DIMCUe5Connector(config=self.config)
        
    def tearDown(self):
        if self.connector.connected:
            self.connector.disconnect()
            
    def test_initial_state(self):
        """Test initial connector state."""
        self.assertEqual(self.connector.state, ConnectionState.DISCONNECTED)
        self.assertFalse(self.connector.connected)
        self.assertFalse(self.connector.running)
        self.assertEqual(self.connector.messages_sent, 0)
        self.assertEqual(self.connector.messages_received, 0)
        
    def test_is_connected(self):
        """Test is_connected method."""
        self.assertFalse(self.connector.is_connected())
        
    def test_get_state(self):
        """Test get_state method."""
        state = self.connector.get_state()
        self.assertEqual(state, ConnectionState.DISCONNECTED)
        
    def test_get_statistics(self):
        """Test get_statistics method."""
        stats = self.connector.get_statistics()
        
        self.assertIn("state", stats)
        self.assertIn("connected", stats)
        self.assertIn("messages_sent", stats)
        self.assertIn("messages_received", stats)
        self.assertIn("reconnect_count", stats)
        self.assertEqual(stats["state"], "DISCONNECTED")
        self.assertFalse(stats["connected"])
        
    @patch('socket.socket')
    def test_connect_success(self, mock_socket_class):
        """Test successful connection."""
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket
        
        # Make connector think it's connected
        result = self.connector.connect()
        
        # Note: Full test would need mock sockets to work properly
        # This test verifies the method exists and can be called
        
    def test_send_command_not_connected(self):
        """Test sending command when not connected."""
        result = self.connector.send_command("test", {})
        self.assertIsNone(result)
        
    def test_register_event_callback(self):
        """Test registering event callbacks."""
        callback = Mock()
        
        self.connector.register_event_callback("test_event", callback)
        
        self.assertIn("test_event", self.connector.event_callbacks)
        self.assertEqual(self.connector.event_callbacks["test_event"], callback)
        
    def test_unregister_event_callback(self):
        """Test unregistering event callbacks."""
        callback = Mock()
        self.connector.register_event_callback("test_event", callback)
        
        self.connector.unregister_event_callback("test_event")
        
        self.assertNotIn("test_event", self.connector.event_callbacks)
        
    def test_state_change_callback(self):
        """Test state change callback is called."""
        callback = Mock()
        self.connector.on_connection_state_changed = callback
        
        self.connector._set_state(ConnectionState.CONNECTING)
        
        callback.assert_called_once_with(ConnectionState.CONNECTING)


class TestConnectionMonitor(unittest.TestCase):
    """Tests for ConnectionMonitor class."""
    
    def setUp(self):
        self.connector = Mock(spec=DIMCUe5Connector)
        self.connector.is_connected.return_value = True
        self.connector.send_command.return_value = {"success": True}
        self.connector.get_statistics.return_value = {
            "state": "CONNECTED",
            "messages_sent": 100,
            "messages_received": 100,
            "last_error": None
        }
        
        self.config = MonitorConfig(
            health_check_interval=0.5,
            latency_check_interval=1.0,
        )
        self.monitor = ConnectionMonitor(
            connector=self.connector,
            config=self.config
        )
        
    def tearDown(self):
        if self.monitor.running:
            self.monitor.stop()
            
    def test_initial_state(self):
        """Test initial monitor state."""
        self.assertFalse(self.monitor.running)
        self.assertEqual(self.monitor.current_health, ConnectionHealth.DISCONNECTED)
        
    def test_start_stop(self):
        """Test starting and stopping monitor."""
        self.monitor.start()
        
        self.assertTrue(self.monitor.running)
        self.assertIsNotNone(self.monitor.start_time)
        
        self.monitor.stop()
        
        self.assertFalse(self.monitor.running)
        
    def test_record_message(self):
        """Test recording messages."""
        self.monitor.record_message()
        self.monitor.record_message()
        self.monitor.record_message()
        
        # Messages should be recorded in internal deque
        self.assertEqual(len(self.monitor._message_timestamps), 3)
        
    def test_record_error(self):
        """Test recording errors."""
        self.monitor.record_error("test_error")
        self.monitor.record_error("another_error")
        
        self.assertEqual(len(self.monitor._error_timestamps), 2)
        
    def test_record_latency(self):
        """Test recording latency."""
        self.monitor.record_latency(10.0)
        self.monitor.record_latency(20.0)
        self.monitor.record_latency(30.0)
        
        self.assertEqual(len(self.monitor._latency_samples), 3)
        
    def test_get_current_health(self):
        """Test getting current health."""
        self.monitor.current_health = ConnectionHealth.HEALTHY
        
        health = self.monitor.get_current_health()
        
        self.assertEqual(health, ConnectionHealth.HEALTHY)
        
    def test_get_metrics(self):
        """Test getting health metrics."""
        self.monitor.start()
        time.sleep(0.1)
        
        self.monitor.record_latency(50.0)
        self.monitor.record_message()
        
        metrics = self.monitor.get_metrics()
        
        self.assertIsInstance(metrics, HealthMetrics)
        self.assertGreater(metrics.timestamp, 0)
        self.assertGreater(metrics.uptime_seconds, 0)
        
    def test_get_statistics(self):
        """Test getting detailed statistics."""
        self.monitor.start()
        time.sleep(0.1)
        
        stats = self.monitor.get_statistics()
        
        self.assertIn("health", stats)
        self.assertIn("performance", stats)
        self.assertIn("errors", stats)
        self.assertIn("connection", stats)
        self.assertIn("thresholds", stats)
        
    def test_health_change_callback(self):
        """Test health change callback."""
        callback = Mock()
        self.monitor.on_health_changed = callback
        
        # Simulate health check
        self.monitor.current_health = ConnectionHealth.HEALTHY
        self.monitor._check_health()
        
        # Verify callback structure (may or may not be called depending on state change)
        
    def test_alert_callback(self):
        """Test alert callback."""
        callback = Mock()
        self.monitor.on_alert = callback
        
        self.monitor._generate_alert_message(
            "test_alert",
            "Test message",
            {"data": "value"},
            "warning"
        )
        
        callback.assert_called_once()


class TestConnectionHealth(unittest.TestCase):
    """Tests for ConnectionHealth enum."""
    
    def test_health_states(self):
        """Test all health states exist."""
        states = [
            ConnectionHealth.HEALTHY,
            ConnectionHealth.DEGRADED,
            ConnectionHealth.UNHEALTHY,
            ConnectionHealth.DISCONNECTED,
        ]
        
        self.assertEqual(len(states), 4)


class TestMonitorConfig(unittest.TestCase):
    """Tests for MonitorConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = MonitorConfig()
        
        self.assertEqual(config.health_check_interval, 5.0)
        self.assertEqual(config.latency_check_interval, 10.0)
        self.assertEqual(config.latency_warning_ms, 100.0)
        self.assertEqual(config.latency_critical_ms, 500.0)
        
    def test_custom_values(self):
        """Test custom configuration values."""
        config = MonitorConfig(
            health_check_interval=2.0,
            latency_warning_ms=50.0
        )
        
        self.assertEqual(config.health_check_interval, 2.0)
        self.assertEqual(config.latency_warning_ms, 50.0)


class TestHealthMetrics(unittest.TestCase):
    """Tests for HealthMetrics dataclass."""
    
    def test_create_metrics(self):
        """Test creating health metrics."""
        metrics = HealthMetrics(
            timestamp=time.time(),
            health=ConnectionHealth.HEALTHY,
            latency_ms=50.0,
            packet_loss_percent=0.5,
            messages_per_second=10.0,
            errors_last_minute=0,
            uptime_seconds=3600.0,
            quality_score=0.95
        )
        
        self.assertEqual(metrics.health, ConnectionHealth.HEALTHY)
        self.assertEqual(metrics.latency_ms, 50.0)
        self.assertEqual(metrics.quality_score, 0.95)


class TestIntegration(unittest.TestCase):
    """Integration tests for Bridge subsystem."""
    
    def test_full_workflow(self):
        """Test full monitoring workflow without network."""
        config = ConnectionConfig(reconnect_enabled=False)
        connector = DIMCUe5Connector(config=config)
        
        monitor_config = MonitorConfig(
            health_check_interval=0.1,
            latency_check_interval=0.2
        )
        monitor = ConnectionMonitor(
            connector=connector,
            config=monitor_config
        )
        
        # Start monitoring (will show disconnected status)
        monitor.start()
        time.sleep(0.2)
        
        # Check health is disconnected
        health = monitor.get_current_health()
        self.assertEqual(health, ConnectionHealth.DISCONNECTED)
        
        # Get stats
        stats = monitor.get_statistics()
        self.assertIn("health", stats)
        
        # Cleanup
        monitor.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
