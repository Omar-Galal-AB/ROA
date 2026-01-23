"""
Unit tests for DistanceCalculator
"""

import pytest
from src.python.Tracking.distance_calculator import DistanceCalculator


def test_distance_calculator_init():
    """Test DistanceCalculator initialization"""
    calculator = DistanceCalculator()
    assert calculator is not None
    assert calculator.update_rate == 20
    assert calculator.max_distance == 100.0


def test_calculate_distance():
    """Test basic distance calculation"""
    calculator = DistanceCalculator()

    pos1 = (0.0, 0.0, 0.0)
    pos2 = (3.0, 4.0, 0.0)

    distance = calculator.calculate_distance(pos1, pos2)

    assert abs(distance - 5.0) < 0.001  # 3-4-5 triangle


def test_calculate_distance_3d():
    """Test 3D distance calculation"""
    calculator = DistanceCalculator()

    pos1 = (0.0, 0.0, 0.0)
    pos2 = (1.0, 1.0, 1.0)

    distance = calculator.calculate_distance(pos1, pos2)

    expected = 3**0.5  # sqrt(3)
    assert abs(distance - expected) < 0.001


def test_calculate_all_distances():
    """Test calculating distances for multiple robots"""
    calculator = DistanceCalculator()

    robot_positions = {
        "robot_1": (0.0, 0.0, 0.0),
        "robot_2": (1.0, 0.0, 0.0),
        "robot_3": (0.0, 1.0, 0.0),
    }

    distances = calculator.calculate_all_distances(robot_positions)

    # Should have 6 entries (3 pairs × 2 orderings)
    assert len(distances) == 6
    assert abs(distances[("robot_1", "robot_2")] - 1.0) < 0.001
    assert abs(distances[("robot_1", "robot_3")] - 1.0) < 0.001
    assert abs(distances[("robot_2", "robot_3")] - 2**0.5) < 0.001


def test_get_cached_distance():
    """Test retrieving cached distance"""
    calculator = DistanceCalculator()

    robot_positions = {"robot_1": (0.0, 0.0, 0.0), "robot_2": (5.0, 0.0, 0.0)}

    calculator.calculate_all_distances(robot_positions)

    cached_distance = calculator.get_distance("robot_1", "robot_2")
    assert abs(cached_distance - 5.0) < 0.001


def test_get_nearest_robot():
    """Test finding nearest robot"""
    calculator = DistanceCalculator()

    robot_positions = {
        "robot_1": (0.0, 0.0, 0.0),
        "robot_2": (5.0, 0.0, 0.0),
        "robot_3": (2.0, 0.0, 0.0),
    }

    nearest = calculator.get_nearest_robot("robot_1", robot_positions)

    assert nearest is not None
    assert nearest[0] == "robot_3"  # Closest is robot_3 at distance 2.0
    assert abs(nearest[1] - 2.0) < 0.001


def test_max_distance_filtering():
    """Test that distances beyond max_distance are not stored"""
    calculator = DistanceCalculator({"max_distance": 5.0})

    robot_positions = {
        "robot_1": (0.0, 0.0, 0.0),
        "robot_2": (10.0, 0.0, 0.0),  # Beyond max_distance
    }

    distances = calculator.calculate_all_distances(robot_positions)

    # Should be empty because distance exceeds max_distance
    assert len(distances) == 0
