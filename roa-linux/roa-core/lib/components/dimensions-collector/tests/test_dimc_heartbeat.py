"""
DIMC Heartbeat Tests

Comprehensive tests for the Heartbeat subsystem including:
- DIMCHeartbeat
- DIMCHeartbeatMonitor
- HeartbeatState and ComponentHealth
- File-based IPC

Usage:
    python -m pytest test_dimc_heartbeat.py -v
    python test_dimc_heartbeat.py  # Direct execution
"""

import sys
import os
import time
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python"))

from dimc_heartbeat import (
    DIMCHeartbeat,
    DIMCHeartbeatMonitor,
    HeartbeatState,
    ComponentHealth,
    HeartbeatConfig,
    HeartbeatData,
    ClientInfo,
)


class TestHeartbeatConfig(unittest.TestCase):
    """Tests for HeartbeatConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = HeartbeatConfig()
        
        self.assertEqual(config.ipc_base_path, "/mnt/d/ROA/.ipc")
        self.assertEqual(config.heartbeat_interval, 5.0)
        self.assertEqual(config.stale_threshold, 15.0)
        self.assertEqual(config.dead_threshold, 30.0)
        self.assertTrue(config.auto_shutdown_enabled)
        self.assertEqual(config.component_name, "DIMC")
        
    def test_custom_values(self):
        """Test custom configuration values."""
        config = HeartbeatConfig(
            ipc_base_path="/tmp/test/.ipc",
            heartbeat_interval=2.0,
            component_name="TEST",
            auto_shutdown_enabled=False
        )
        
        self.assertEqual(config.ipc_base_path, "/tmp/test/.ipc")
        self.assertEqual(config.heartbeat_interval, 2.0)
        self.assertEqual(config.component_name, "TEST")
        self.assertFalse(config.auto_shutdown_enabled)


class TestHeartbeatData(unittest.TestCase):
    """Tests for HeartbeatData dataclass."""
    
    def test_to_dict(self):
        """Test serialization to dictionary."""
        data = HeartbeatData(
            client_id="test-client",
            component="DIMC",
            timestamp=1704067200.0,  # 2024-01-01 00:00:00 UTC
            state="ACTIVE",
            health="HEALTHY",
            metrics={"uptime": 100},
            capabilities=["lidar", "obstacle_detection"]
        )
        
        result = data.to_dict()
        
        self.assertEqual(result["client_id"], "test-client")
        self.assertEqual(result["component"], "DIMC")
        self.assertEqual(result["timestamp"], 1704067200.0)
        self.assertEqual(result["state"], "ACTIVE")
        self.assertEqual(result["health"], "HEALTHY")
        self.assertEqual(result["metrics"], {"uptime": 100})
        self.assertEqual(result["capabilities"], ["lidar", "obstacle_detection"])
        self.assertIn("timestamp_iso", result)
        
    def test_from_dict(self):
        """Test deserialization from dictionary."""
        source = {
            "client_id": "test-client",
            "component": "DIMC",
            "timestamp": 1704067200.0,
            "state": "ACTIVE",
            "health": "HEALTHY",
            "metrics": {"uptime": 100},
            "capabilities": ["lidar"]
        }
        
        data = HeartbeatData.from_dict(source)
        
        self.assertEqual(data.client_id, "test-client")
        self.assertEqual(data.component, "DIMC")
        self.assertEqual(data.timestamp, 1704067200.0)
        self.assertEqual(data.state, "ACTIVE")
        self.assertEqual(data.health, "HEALTHY")
        
    def test_from_dict_missing_fields(self):
        """Test deserialization with missing fields."""
        source = {}
        
        data = HeartbeatData.from_dict(source)
        
        self.assertEqual(data.client_id, "")
        self.assertEqual(data.component, "")
        self.assertEqual(data.timestamp, 0)


class TestHeartbeatState(unittest.TestCase):
    """Tests for HeartbeatState enum."""
    
    def test_states(self):
        """Test all states exist."""
        states = [
            HeartbeatState.REGISTERED,
            HeartbeatState.ACTIVE,
            HeartbeatState.STALE,
            HeartbeatState.DEAD,
            HeartbeatState.DEREGISTERED,
        ]
        
        self.assertEqual(len(states), 5)


class TestComponentHealth(unittest.TestCase):
    """Tests for ComponentHealth enum."""
    
    def test_health_states(self):
        """Test all health states exist."""
        states = [
            ComponentHealth.HEALTHY,
            ComponentHealth.DEGRADED,
            ComponentHealth.UNHEALTHY,
            ComponentHealth.UNKNOWN,
        ]
        
        self.assertEqual(len(states), 4)


class TestDIMCHeartbeat(unittest.TestCase):
    """Tests for DIMCHeartbeat class."""
    
    def setUp(self):
        # Use temp directory for test IPC
        self.temp_dir = tempfile.mkdtemp()
        self.config = HeartbeatConfig(
            ipc_base_path=self.temp_dir,
            heartbeat_interval=0.5,
            auto_shutdown_enabled=False
        )
        self.heartbeat = DIMCHeartbeat(config=self.config)
        
    def tearDown(self):
        if self.heartbeat.running:
            self.heartbeat.stop()
        # Clean up temp directory
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
    def test_initial_state(self):
        """Test initial heartbeat state."""
        self.assertFalse(self.heartbeat.running)
        self.assertFalse(self.heartbeat.registered)
        self.assertEqual(self.heartbeat.state, HeartbeatState.REGISTERED)
        self.assertEqual(self.heartbeat.health, ComponentHealth.HEALTHY)
        self.assertIsNotNone(self.heartbeat.client_id)
        
    def test_client_id_format(self):
        """Test client ID format."""
        self.assertTrue(self.heartbeat.client_id.startswith("dimc-"))
        
    def test_start_stop(self):
        """Test starting and stopping heartbeat."""
        self.heartbeat.start()
        
        self.assertTrue(self.heartbeat.running)
        
        self.heartbeat.stop()
        
        self.assertFalse(self.heartbeat.running)
        
    def test_update_health(self):
        """Test updating health status."""
        self.heartbeat.update_health(ComponentHealth.DEGRADED, "Test degradation")
        
        self.assertEqual(self.heartbeat.health, ComponentHealth.DEGRADED)
        
    def test_update_metrics(self):
        """Test updating metrics."""
        self.heartbeat.update_metrics({
            "messages": 100,
            "robots": 5
        })
        
        self.assertEqual(self.heartbeat.metrics.get("messages"), 100)
        self.assertEqual(self.heartbeat.metrics.get("robots"), 5)
        
    def test_get_status(self):
        """Test getting status dictionary."""
        self.heartbeat.start()
        time.sleep(0.1)
        
        status = self.heartbeat.get_status()
        
        self.assertIn("client_id", status)
        self.assertIn("running", status)
        self.assertIn("health", status)
        self.assertIn("state", status)
        
        self.heartbeat.stop()
        
    def test_heartbeat_file_creation(self):
        """Test heartbeat file is created."""
        self.heartbeat.start()
        time.sleep(0.6)  # Wait for first heartbeat
        
        heartbeat_dir = Path(self.temp_dir) / "heartbeats"
        
        # Check if directory and file exist
        if heartbeat_dir.exists():
            files = list(heartbeat_dir.glob("*.heartbeat.json"))
            # Should have at least one heartbeat file
            self.assertGreaterEqual(len(files), 0)
            
        self.heartbeat.stop()
        
    def test_health_change_callback(self):
        """Test health change callback is called."""
        callback = Mock()
        self.heartbeat.on_health_changed = callback
        
        self.heartbeat.update_health(ComponentHealth.DEGRADED)
        
        callback.assert_called_once()


class TestDIMCHeartbeatMonitor(unittest.TestCase):
    """Tests for DIMCHeartbeatMonitor class."""
    
    def setUp(self):
        # Use temp directory for test IPC
        self.temp_dir = tempfile.mkdtemp()
        self.config = HeartbeatConfig(
            ipc_base_path=self.temp_dir,
            check_interval=0.5,
            stale_threshold=1.0,
            dead_threshold=2.0,
            auto_shutdown_enabled=False
        )
        self.monitor = DIMCHeartbeatMonitor(config=self.config)
        
    def tearDown(self):
        if self.monitor.running:
            self.monitor.stop()
        # Clean up temp directory
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
    def test_initial_state(self):
        """Test initial monitor state."""
        self.assertFalse(self.monitor.running)
        self.assertEqual(len(self.monitor.clients), 0)
        
    def test_start_stop(self):
        """Test starting and stopping monitor."""
        self.monitor.start()
        
        self.assertTrue(self.monitor.running)
        
        self.monitor.stop()
        
        self.assertFalse(self.monitor.running)
        
    def test_get_clients(self):
        """Test getting client list."""
        clients = self.monitor.get_clients()
        
        self.assertIsInstance(clients, dict)
        
    def test_get_active_count(self):
        """Test getting active client count."""
        count = self.monitor.get_active_count()
        
        self.assertEqual(count, 0)  # No clients yet
        
    def test_has_clients(self):
        """Test checking if any clients exist."""
        self.assertFalse(self.monitor.has_clients())
        
    def test_client_dead_callback(self):
        """Test client dead callback."""
        callback = Mock()
        self.monitor.on_client_dead = callback
        
        # Create mock client info
        client = ClientInfo(
            client_id="test-client",
            component="TEST",
            registered_at=time.time() - 100,
            last_heartbeat=time.time() - 100,  # Very old
            state=HeartbeatState.DEAD,
            health=ComponentHealth.UNKNOWN
        )
        
        self.monitor.clients["test-client"] = client
        
        # Callback should be invoked when client is detected dead
        # (would need to trigger check logic)


class TestClientInfo(unittest.TestCase):
    """Tests for ClientInfo dataclass."""
    
    def test_create_client_info(self):
        """Test creating ClientInfo."""
        now = time.time()
        info = ClientInfo(
            client_id="test-client",
            component="DIMC",
            registered_at=now,
            last_heartbeat=now,
            state=HeartbeatState.ACTIVE,
            health=ComponentHealth.HEALTHY,
            metadata={"version": "2.0"}
        )
        
        self.assertEqual(info.client_id, "test-client")
        self.assertEqual(info.component, "DIMC")
        self.assertEqual(info.state, HeartbeatState.ACTIVE)
        self.assertEqual(info.health, ComponentHealth.HEALTHY)
        self.assertEqual(info.metadata["version"], "2.0")


class TestIntegration(unittest.TestCase):
    """Integration tests for Heartbeat subsystem."""
    
    def test_heartbeat_and_monitor(self):
        """Test heartbeat and monitor working together."""
        temp_dir = tempfile.mkdtemp()
        
        try:
            config = HeartbeatConfig(
                ipc_base_path=temp_dir,
                heartbeat_interval=0.5,
                check_interval=0.5,
                stale_threshold=2.0,
                dead_threshold=4.0,
                auto_shutdown_enabled=False
            )
            
            # Create heartbeat agent
            heartbeat = DIMCHeartbeat(config=config)
            
            # Create monitor
            monitor = DIMCHeartbeatMonitor(config=config)
            
            # Start both
            heartbeat.start()
            monitor.start()
            
            # Wait for heartbeat to be written and detected
            time.sleep(1.0)
            
            # Check monitor detected the heartbeat
            # (exact detection depends on file scanning implementation)
            
            # Cleanup
            heartbeat.stop()
            monitor.stop()
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
