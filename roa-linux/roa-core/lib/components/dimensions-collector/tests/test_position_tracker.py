"""
Unit tests for PositionTracker
"""

import pytest
from src.python.Tracking.position_tracker import PositionTracker


def test_position_tracker_init():
    """Test PositionTracker initialization"""
    tracker = PositionTracker()
    assert tracker is not None
    assert tracker.update_rate == 60
    assert tracker.precision == 0.001


def test_add_robot():
    """Test adding a robot to tracker"""
    tracker = PositionTracker()
    initial_pos = (0.0, 0.0, 0.0)

    tracker.add_robot("robot_1", initial_pos)

    assert "robot_1" in tracker.positions
    assert tracker.get_position("robot_1") == initial_pos


def test_update_position():
    """Test updating robot position"""
    tracker = PositionTracker()
    tracker.add_robot("robot_1", (0.0, 0.0, 0.0))

    new_pos = (1.0, 2.0, 3.0)
    tracker.update("robot_1", new_pos, timestamp=1.0)

    assert tracker.get_position("robot_1") == new_pos


def test_position_history():
    """Test position history tracking"""
    tracker = PositionTracker({"history_size": 5})
    tracker.add_robot("robot_1", (0.0, 0.0, 0.0))

    # Add 3 position updates
    for i in range(1, 4):
        tracker.update("robot_1", (float(i), float(i), float(i)), timestamp=float(i))

    history = tracker.get_position_history("robot_1")
    assert len(history) == 4  # Initial + 3 updates


def test_total_distance_traveled():
    """Test total distance calculation"""
    tracker = PositionTracker()
    tracker.add_robot("robot_1", (0.0, 0.0, 0.0))

    # Move 1 meter in X direction
    tracker.update("robot_1", (1.0, 0.0, 0.0), timestamp=1.0)

    distance = tracker.get_total_distance_traveled("robot_1")
    assert abs(distance - 1.0) < 0.001


def test_displacement_from_start():
    """Test displacement from starting position"""
    tracker = PositionTracker()
    tracker.add_robot("robot_1", (0.0, 0.0, 0.0))

    # Move in a square pattern
    tracker.update("robot_1", (1.0, 0.0, 0.0), timestamp=1.0)
    tracker.update("robot_1", (1.0, 1.0, 0.0), timestamp=2.0)
    tracker.update("robot_1", (0.0, 1.0, 0.0), timestamp=3.0)
    tracker.update("robot_1", (0.0, 0.0, 0.0), timestamp=4.0)

    # Should be back at starting position
    displacement = tracker.get_displacement_from_start("robot_1")
    assert abs(displacement) < 0.001


def test_remove_robot():
    """Test removing a robot from tracker"""
    tracker = PositionTracker()
    tracker.add_robot("robot_1", (0.0, 0.0, 0.0))

    tracker.remove_robot("robot_1")

    assert tracker.get_position("robot_1") is None


def test_clear_history():
    """Test clearing position history"""
    tracker = PositionTracker()
    tracker.add_robot("robot_1", (0.0, 0.0, 0.0))

    # Add some history
    for i in range(5):
        tracker.update("robot_1", (float(i), 0.0, 0.0), timestamp=float(i))

    # Clear history
    tracker.clear_history("robot_1")

    history = tracker.get_position_history("robot_1")
    assert len(history) == 1  # Only current position remains
    assert tracker.get_total_distance_traveled("robot_1") == 0.0
