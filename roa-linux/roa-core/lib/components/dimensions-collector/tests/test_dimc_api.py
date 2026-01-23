#!/usr/bin/env python3
"""
DIMC API Tests

Tests for the main DIMC_API interface and singleton pattern.
"""

import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

# Add source path
src_path = Path(__file__).parent.parent / "src" / "python"
sys.path.insert(0, str(src_path))

from dimc_api import (
    DIMC_API,
    CoordinationAPI,
    EvadeAPI,
    SensorAPI,
    TrackingAPI,
    get_dimc_instance,
    reset_dimc_instance,
)


class TestDIMCAPI(unittest.TestCase):
    """Test DIMC_API class."""

    def setUp(self):
        """Set up test fixtures."""
        self.config_path = Path(__file__).parent.parent / "Config"

    def tearDown(self):
        """Clean up after tests."""
        # Reset singleton for clean state
        reset_dimc_instance()

    def test_api_initialization(self):
        """Test API initializes with all sub-APIs."""
        api = DIMC_API(config_path=self.config_path)

        self.assertIsInstance(api.tracking, TrackingAPI)
        self.assertIsInstance(api.coordination, CoordinationAPI)
        self.assertIsInstance(api.evade, EvadeAPI)
        self.assertIsInstance(api.sensor, SensorAPI)

        api.shutdown()

    def test_initialize_and_start(self):
        """Test API lifecycle methods."""
        api = DIMC_API(config_path=self.config_path)

        # Initialize
        result = api.initialize()
        self.assertTrue(result)

        # Start
        api.start()

        # Stop and shutdown
        api.stop()
        api.shutdown()


class TestSingletonPattern(unittest.TestCase):
    """Test singleton access pattern."""

    def tearDown(self):
        """Clean up after tests."""
        reset_dimc_instance()

    def test_singleton_returns_same_instance(self):
        """Test get_dimc_instance returns same instance."""
        instance1 = get_dimc_instance()
        instance2 = get_dimc_instance()

        self.assertIs(instance1, instance2)

    def test_singleton_thread_safety(self):
        """Test singleton is thread-safe."""
        instances = []
        threads = []

        def get_instance():
            instance = get_dimc_instance()
            instances.append(instance)

        # Create multiple threads trying to get instance
        for _ in range(10):
            t = threading.Thread(target=get_instance)
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # All instances should be the same object
        first_instance = instances[0]
        for instance in instances[1:]:
            self.assertIs(instance, first_instance)

    def test_reset_singleton(self):
        """Test reset_dimc_instance clears singleton."""
        instance1 = get_dimc_instance()
        reset_dimc_instance()
        instance2 = get_dimc_instance()

        self.assertIsNot(instance1, instance2)

    def test_singleton_ignores_second_config(self):
        """Test singleton ignores config on subsequent calls."""
        config1 = Path("/path/1")
        config2 = Path("/path/2")

        # First call with config1
        instance1 = get_dimc_instance(config_path=config1)

        # Second call with config2 (should be ignored)
        with self.assertLogs("DIMC.API", level="WARNING") as cm:
            instance2 = get_dimc_instance(config_path=config2)

        # Should return same instance
        self.assertIs(instance1, instance2)

        # Should have logged warning
        self.assertTrue(any("ignoring new config_path" in msg.lower() for msg in cm.output))


class TestCoordinationAPI(unittest.TestCase):
    """Test CoordinationAPI with configurable proximity thresholds."""

    def setUp(self):
        """Set up test fixtures."""
        self.config_path = Path(__file__).parent.parent / "Config"
        self.api = DIMC_API(config_path=self.config_path)
        self.api.initialize()

    def tearDown(self):
        """Clean up after tests."""
        if hasattr(self, "api"):
            self.api.shutdown()

    def test_proximity_thresholds_from_config(self):
        """Test proximity thresholds loaded from config."""
        coord = self.api.coordination

        # Check thresholds were loaded
        self.assertIsNotNone(coord._proximity_critical)
        self.assertIsNotNone(coord._proximity_caution)
        self.assertIsNotNone(coord._proximity_warning)

        # Should have reasonable values
        self.assertGreater(coord._proximity_warning, coord._proximity_caution)
        self.assertGreater(coord._proximity_caution, coord._proximity_critical)

    def test_alert_level_uses_configured_thresholds(self):
        """Test alert level uses configured thresholds."""
        coord = self.api.coordination

        # Test each level
        critical_distance = coord._proximity_critical - 0.1
        caution_distance = coord._proximity_caution - 0.1
        warning_distance = coord._proximity_warning - 0.1
        safe_distance = coord._proximity_warning + 1.0

        self.assertEqual(coord._get_alert_level(critical_distance), "critical")
        self.assertEqual(coord._get_alert_level(caution_distance), "caution")
        self.assertEqual(coord._get_alert_level(warning_distance), "warning")
        self.assertEqual(coord._get_alert_level(safe_distance), "safe")


class TestTrackingAPI(unittest.TestCase):
    """Test TrackingAPI."""

    def setUp(self):
        """Set up test fixtures."""
        self.config_path = Path(__file__).parent.parent / "Config"
        self.api = DIMC_API(config_path=self.config_path)
        self.api.initialize()

    def tearDown(self):
        """Clean up after tests."""
        if hasattr(self, "api"):
            self.api.shutdown()

    def test_get_all_robots_initially_empty(self):
        """Test get_all_robots returns empty list initially."""
        robots = self.api.tracking.get_all_robots()
        self.assertEqual(robots, [])

    def test_get_position_for_unregistered_robot(self):
        """Test get_position returns None for unregistered robot."""
        pos = self.api.tracking.get_position("unknown_robot")
        self.assertIsNone(pos)


if __name__ == "__main__":
    unittest.main()
