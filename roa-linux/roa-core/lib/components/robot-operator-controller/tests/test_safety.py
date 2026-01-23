"""
Test suite for ROC safety system
Tests cover safety levels, collision detection, emergency stops, and boundary checking
"""

import os
import sys
from unittest.mock import MagicMock, Mock

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "python"))

from safety.safety_manager import SafetyLevel, SafetyManager, SafetyViolation


class TestSafetyManager:
    """Test suite for SafetyManager (18 tests)"""

    def test_safety_manager_initialization(self):
        """Test 1: Safety manager initializes with default settings"""
        manager = SafetyManager()
        assert manager is not None
        assert manager.current_level == SafetyLevel.STANDARD
        assert manager.emergency_stop_active == False

    def test_safety_level_fragile(self):
        """Test 2: Fragile safety level has strictest settings"""
        manager = SafetyManager()
        manager.set_safety_level(SafetyLevel.FRAGILE)

        assert manager.current_level == SafetyLevel.FRAGILE
        assert manager.speed_multiplier < 1.0  # Reduced speed
        assert manager.auto_stop_distance > 0  # Larger safety margin

    def test_safety_level_standard(self):
        """Test 3: Standard safety level has balanced settings"""
        manager = SafetyManager()
        manager.set_safety_level(SafetyLevel.STANDARD)

        assert manager.current_level == SafetyLevel.STANDARD
        assert manager.speed_multiplier == 1.0

    def test_safety_level_robust(self):
        """Test 4: Robust safety level allows higher speeds"""
        manager = SafetyManager()
        manager.set_safety_level(SafetyLevel.ROBUST)

        assert manager.current_level == SafetyLevel.ROBUST
        assert manager.speed_multiplier >= 1.0  # May allow higher speeds

    def test_collision_detection(self):
        """Test 5: Safety manager detects collisions"""
        manager = SafetyManager()

        # Simulate obstacle very close
        obstacle_distance = 0.01  # 1cm - within auto-stop distance
        collision_detected = manager.check_collision(obstacle_distance)

        assert collision_detected == True

    def test_warning_distance(self):
        """Test 6: Safety manager issues warnings before collision"""
        manager = SafetyManager()

        # Obstacle within warning distance but not collision distance
        obstacle_distance = 0.05  # 5cm
        warning_issued = manager.check_warning_distance(obstacle_distance)

        assert warning_issued == True

    def test_safe_distance(self):
        """Test 7: No warning when obstacle is far"""
        manager = SafetyManager()

        # Obstacle far away
        obstacle_distance = 1.0  # 1 meter
        warning_issued = manager.check_warning_distance(obstacle_distance)

        assert warning_issued == False

    def test_emergency_stop_activation(self):
        """Test 8: Emergency stop can be activated"""
        manager = SafetyManager()

        result = manager.activate_emergency_stop()
        assert result == True
        assert manager.emergency_stop_active == True

    def test_emergency_stop_deactivation(self):
        """Test 9: Emergency stop can be deactivated"""
        manager = SafetyManager()
        manager.activate_emergency_stop()

        result = manager.deactivate_emergency_stop()
        assert result == True
        assert manager.emergency_stop_active == False

    def test_boundary_checking(self):
        """Test 10: Safety manager enforces workspace boundaries"""
        manager = SafetyManager()

        # Set workspace boundaries
        boundaries = {
            "x_min": -1.0,
            "x_max": 1.0,
            "y_min": -1.0,
            "y_max": 1.0,
            "z_min": 0.0,
            "z_max": 2.0,
        }
        manager.set_boundaries(boundaries)

        # Test point inside boundaries
        inside_point = [0.5, 0.5, 1.0]
        assert manager.check_within_boundaries(inside_point) == True

        # Test point outside boundaries
        outside_point = [2.0, 0.5, 1.0]
        assert manager.check_within_boundaries(outside_point) == False

    def test_violation_logging(self):
        """Test 11: Safety violations are logged"""
        manager = SafetyManager()

        violation = {
            "type": SafetyViolation.COLLISION,
            "distance": 0.01,
            "timestamp": "2025-12-13T14:00:00",
        }
        manager.log_violation(violation)

        assert len(manager.violations) == 1
        assert manager.violations[0]["type"] == SafetyViolation.COLLISION

    def test_violation_history_limit(self):
        """Test 12: Violation history has size limit"""
        manager = SafetyManager()
        manager.max_history = 10

        # Add more violations than limit
        for i in range(15):
            manager.log_violation({"type": SafetyViolation.COLLISION, "id": i})

        # Should only keep last 10
        assert len(manager.violation_history) <= 10

    def test_speed_limiting_on_warning(self):
        """Test 13: Speed is reduced when warning detected"""
        manager = SafetyManager()
        original_speed = 1.0

        # Trigger warning
        manager.check_warning_distance(0.06)

        adjusted_speed = manager.get_adjusted_speed(original_speed)
        assert adjusted_speed < original_speed

    def test_auto_stop_on_collision(self):
        """Test 14: Robot stops automatically on collision"""
        manager = SafetyManager()

        # Simulate collision
        manager.check_collision(0.01)  # Very close obstacle

        # Should trigger auto-stop
        assert manager.should_stop() == True

    def test_multi_robot_safety_zone(self):
        """Test 15: Safety zones between multiple robots"""
        manager = SafetyManager()

        robot1_position = [0.0, 0.0, 0.0]
        robot2_position = [0.5, 0.0, 0.0]  # 0.5m away

        safety_zone = 1.0  # 1 meter minimum distance
        violation = manager.check_inter_robot_distance(
            robot1_position, robot2_position, safety_zone
        )

        assert violation == True  # Too close!

    def test_velocity_limit_enforcement(self):
        """Test 16: Velocity limits are enforced"""
        manager = SafetyManager()
        manager.set_safety_level(SafetyLevel.FRAGILE)

        requested_velocity = 2.0  # m/s
        max_velocity = 1.0  # m/s for fragile

        enforced_velocity = manager.enforce_velocity_limit(requested_velocity, max_velocity)
        assert enforced_velocity <= max_velocity

    def test_torque_limit_enforcement(self):
        """Test 17: Torque limits are enforced"""
        manager = SafetyManager()

        requested_torques = [100.0, 150.0, 200.0]  # N·m
        max_torques = [80.0, 120.0, 150.0]  # N·m

        enforced_torques = manager.enforce_torque_limits(requested_torques, max_torques)
        for i, torque in enumerate(enforced_torques):
            assert torque <= max_torques[i]

    def test_safety_override_authorization(self):
        """Test 18: Safety overrides require authorization"""
        manager = SafetyManager()

        # Try to override without authorization
        result = manager.override_safety_check(authorized=False)
        assert result == False

        # Try with authorization
        result = manager.override_safety_check(authorized=True)
        assert result == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
