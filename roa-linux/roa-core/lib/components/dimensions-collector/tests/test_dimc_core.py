#!/usr/bin/env python3
"""
DIMC Core Tests

Tests for the main DimensionsCollector coordinator class.
Covers thread safety, input validation, and core functionality.
"""

import sys
import unittest
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add source path
src_path = Path(__file__).parent.parent / "src" / "python"
sys.path.insert(0, str(src_path))

from dimc_core import DimensionsCollector, RobotType, RobotDimensions, CollisionRisk


class TestDIMCCoreInitialization(unittest.TestCase):
    """Test DIMC initialization and configuration."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config_path = Path(__file__).parent.parent / "Config"
    
    def test_initialization(self):
        """Test basic initialization."""
        dimc = DimensionsCollector(config_path=self.config_path, enable_obs=False)
        
        self.assertIsNotNone(dimc)
        self.assertFalse(dimc.initialized)
        self.assertEqual(dimc.update_rate, 60)  # Default
        self.assertIsNotNone(dimc._robots_lock)
    
    def test_configuration_validation(self):
        """Test configuration validation and defaults."""
        dimc = DimensionsCollector(config_path=self.config_path, enable_obs=False)
        
        # Check defaults were applied
        self.assertIn('proximity', dimc.config)
        self.assertIn('collision', dimc.config)
        self.assertEqual(dimc.config['max_robots'], 10)
    
    def test_initialize(self):
        """Test initialize method."""
        dimc = DimensionsCollector(config_path=self.config_path, enable_obs=False)
        
        result = dimc.initialize()
        
        self.assertTrue(result)
        self.assertTrue(dimc.initialized)


class TestDIMCThreadSafety(unittest.TestCase):
    """Test thread safety of DIMC operations."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config_path = Path(__file__).parent.parent / "Config"
        self.dimc = DimensionsCollector(config_path=self.config_path, enable_obs=False)
        self.dimc.initialize()
    
    def tearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'dimc'):
            self.dimc.shutdown()
    
    def test_concurrent_robot_registration(self):
        """Test thread-safe robot registration."""
        robot_count = 5
        threads = []
        results = []
        
        def register_robot(robot_id):
            actor_data = {
                'position': (0, 0, 0),
                'orientation': (0, 0, 0, 1),
                'robot_type': 'Generic',
                'dimensions': {'width': 1.0, 'height': 1.0, 'length': 1.0},
                'data_flags': {}
            }
            result = self.dimc.register_robot(robot_id, actor_data)
            results.append(result)
        
        # Register robots concurrently
        for i in range(robot_count):
            t = threading.Thread(target=register_robot, args=(f"robot_{i}",))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # All registrations should succeed
        self.assertEqual(sum(results), robot_count)
        self.assertEqual(len(self.dimc.get_all_robots()), robot_count)
    
    def test_concurrent_update_and_read(self):
        """Test thread-safe concurrent updates and reads."""
        # Register a robot
        self.dimc.register_robot('test_robot', {
            'position': (0, 0, 0),
            'orientation': (0, 0, 0, 1),
            'robot_type': 'Generic',
            'dimensions': {'width': 1.0, 'height': 1.0, 'length': 1.0},
            'data_flags': {}
        })
        
        stop_flag = threading.Event()
        exceptions = []
        
        def updater():
            try:
                while not stop_flag.is_set():
                    self.dimc.update(time.time(), {
                        'test_robot': {
                            'position': (1.0, 2.0, 3.0),
                            'orientation': (0, 0, 0, 1),
                            'velocity': (0.1, 0.2, 0.3)
                        }
                    })
                    time.sleep(0.001)
            except Exception as e:
                exceptions.append(e)
        
        def reader():
            try:
                while not stop_flag.is_set():
                    pos = self.dimc.get_position('test_robot')
                    info = self.dimc.get_robot_info('test_robot')
                    time.sleep(0.001)
            except Exception as e:
                exceptions.append(e)
        
        # Start threads
        update_thread = threading.Thread(target=updater)
        read_threads = [threading.Thread(target=reader) for _ in range(3)]
        
        update_thread.start()
        for t in read_threads:
            t.start()
        
        # Run for a short time
        time.sleep(0.1)
        stop_flag.set()
        
        # Wait for completion
        update_thread.join()
        for t in read_threads:
            t.join()
        
        # No exceptions should have occurred
        self.assertEqual(len(exceptions), 0)


class TestDIMCInputValidation(unittest.TestCase):
    """Test input validation."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config_path = Path(__file__).parent.parent / "Config"
        self.dimc = DimensionsCollector(config_path=self.config_path, enable_obs=False)
        self.dimc.initialize()
    
    def tearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'dimc'):
            self.dimc.shutdown()
    
    def test_validate_position_nan(self):
        """Test position validation rejects NaN."""
        result = self.dimc._validate_position((float('nan'), 0, 0))
        self.assertIsNone(result)
    
    def test_validate_position_infinity(self):
        """Test position validation rejects Infinity."""
        result = self.dimc._validate_position((float('inf'), 0, 0))
        self.assertIsNone(result)
    
    def test_validate_position_out_of_bounds(self):
        """Test position validation rejects out-of-bounds values."""
        result = self.dimc._validate_position((2000, 0, 0))  # > 1000m
        self.assertIsNone(result)
    
    def test_validate_position_valid(self):
        """Test position validation accepts valid values."""
        result = self.dimc._validate_position((1.0, 2.0, 3.0))
        self.assertEqual(result, (1.0, 2.0, 3.0))
    
    def test_validate_orientation_normalizes(self):
        """Test orientation validation normalizes quaternions."""
        # Non-normalized quaternion
        result = self.dimc._validate_orientation((0, 0, 0, 2.0))
        self.assertIsNotNone(result)
        
        # Check it's normalized
        x, y, z, w = result
        magnitude = (x*x + y*y + z*z + w*w) ** 0.5
        self.assertAlmostEqual(magnitude, 1.0, places=5)
    
    def test_validate_velocity_clamps(self):
        """Test velocity validation clamps extreme values."""
        result = self.dimc._validate_velocity((200, 0, 0))  # > 100 m/s
        vx, vy, vz = result
        self.assertLessEqual(abs(vx), 100.0)
    
    def test_update_with_invalid_data(self):
        """Test update with invalid robot data."""
        # Register robot
        self.dimc.register_robot('test_robot', {
            'position': (0, 0, 0),
            'orientation': (0, 0, 0, 1),
            'robot_type': 'Generic',
            'dimensions': {'width': 1.0, 'height': 1.0, 'length': 1.0},
            'data_flags': {}
        })
        
        initial_failures = self.dimc._stats['validation_failures']
        
        # Send invalid position (NaN)
        self.dimc.update(time.time(), {
            'test_robot': {
                'position': (float('nan'), 0, 0),
                'orientation': (0, 0, 0, 1)
            }
        })
        
        # Validation failure should be recorded
        self.assertGreater(self.dimc._stats['validation_failures'], initial_failures)


class TestDIMCRobotManagement(unittest.TestCase):
    """Test robot registration and management."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config_path = Path(__file__).parent.parent / "Config"
        self.dimc = DimensionsCollector(config_path=self.config_path, enable_obs=False)
        self.dimc.initialize()
    
    def tearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'dimc'):
            self.dimc.shutdown()
    
    def test_register_robot(self):
        """Test robot registration."""
        actor_data = {
            'position': (1.0, 2.0, 3.0),
            'orientation': (0, 0, 0, 1),
            'robot_type': 'MobileRobot',
            'dimensions': {
                'width': 0.5,
                'height': 1.0,
                'length': 0.8,
                'radius': 0.3
            },
            'data_flags': {'has_dimensions': True}
        }
        
        result = self.dimc.register_robot('robot_1', actor_data)
        
        self.assertTrue(result)
        self.assertIn('robot_1', self.dimc.get_all_robots())
    
    def test_register_robot_max_limit(self):
        """Test robot registration respects max limit."""
        # Set max to 2 for testing
        self.dimc.config['max_robots'] = 2
        
        # Register 2 robots (should succeed)
        for i in range(2):
            result = self.dimc.register_robot(f'robot_{i}', {
                'position': (0, 0, 0),
                'orientation': (0, 0, 0, 1),
                'robot_type': 'Generic',
                'dimensions': {'width': 1.0},
                'data_flags': {}
            })
            self.assertTrue(result)
        
        # Try to register 3rd robot (should fail)
        result = self.dimc.register_robot('robot_3', {
            'position': (0, 0, 0),
            'orientation': (0, 0, 0, 1),
            'robot_type': 'Generic',
            'dimensions': {'width': 1.0},
            'data_flags': {}
        })
        self.assertFalse(result)
    
    def test_unregister_robot(self):
        """Test robot unregistration with complete cleanup."""
        # Register robot
        self.dimc.register_robot('robot_1', {
            'position': (0, 0, 0),
            'orientation': (0, 0, 0, 1),
            'robot_type': 'Generic',
            'dimensions': {'width': 1.0},
            'data_flags': {}
        })
        
        # Unregister
        result = self.dimc.unregister_robot('robot_1')
        
        self.assertTrue(result)
        self.assertNotIn('robot_1', self.dimc.get_all_robots())
        
        # Verify cleanup
        self.assertIsNone(self.dimc.get_position('robot_1'))


class TestDIMCDegradation(unittest.TestCase):
    """Test graceful degradation."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config_path = Path(__file__).parent.parent / "Config"
        self.dimc = DimensionsCollector(config_path=self.config_path, enable_obs=False)
        self.dimc.initialize()
    
    def tearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'dimc'):
            self.dimc.shutdown()
    
    def test_degradation_detection(self):
        """Test degradation state is tracked."""
        # Initially not degraded
        self.assertFalse(self.dimc.is_degraded())
        self.assertIsNone(self.dimc.get_degradation_reason())
        
        # Simulate bridge disconnect
        from dimc_core import ConnectionState
        if hasattr(ConnectionState, 'DISCONNECTED'):
            mock_state = Mock()
            mock_state.name = 'DISCONNECTED'
            self.dimc._on_bridge_connection_changed(mock_state)
            
            # Should be degraded now
            self.assertTrue(self.dimc.is_degraded())
            self.assertIsNotNone(self.dimc.get_degradation_reason())
    
    def test_status_includes_degradation(self):
        """Test get_status includes degradation info."""
        status = self.dimc.get_status()
        
        self.assertIn('degraded', status)
        self.assertIn('degradation_reason', status)


class TestDIMCMetrics(unittest.TestCase):
    """Test metrics and statistics."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config_path = Path(__file__).parent.parent / "Config"
        self.dimc = DimensionsCollector(config_path=self.config_path, enable_obs=False)
        self.dimc.initialize()
    
    def tearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'dimc'):
            self.dimc.shutdown()
    
    def test_statistics_tracking(self):
        """Test statistics are tracked correctly."""
        initial_stats = self.dimc.get_statistics()
        
        # Register a robot
        self.dimc.register_robot('robot_1', {
            'position': (0, 0, 0),
            'orientation': (0, 0, 0, 1),
            'robot_type': 'Generic',
            'dimensions': {'width': 1.0},
            'data_flags': {}
        })
        
        # Update
        self.dimc.update(time.time(), {
            'robot_1': {
                'position': (1, 2, 3),
                'orientation': (0, 0, 0, 1)
            }
        })
        
        stats = self.dimc.get_statistics()
        
        # Updates should have increased
        self.assertGreater(stats['updates']['total'], initial_stats['updates']['total'])


if __name__ == '__main__':
    unittest.main()
