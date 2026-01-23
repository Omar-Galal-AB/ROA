"""
Unit tests for SizeMeasurer
"""

import pytest
from src.python.Measurement.size_measurer import SizeMeasurer


def test_size_measurer_init():
    """Test SizeMeasurer initialization"""
    measurer = SizeMeasurer()
    assert measurer is not None
    assert measurer.use_visual_mesh == True
    assert measurer.use_collision_mesh == True


def test_measure_with_bounds():
    """Test measuring dimensions from bounds data"""
    measurer = SizeMeasurer()

    mesh_data = {
        "bounds": {
            "min_x": -1.0,
            "max_x": 1.0,
            "min_y": -0.5,
            "max_y": 0.5,
            "min_z": 0.0,
            "max_z": 2.0,
        }
    }

    dimensions = measurer.measure(mesh_data)

    # Width = X axis: 1.0 - (-1.0) = 2.0
    # Height = Y axis: 0.5 - (-0.5) = 1.0
    # Length = Z axis: 2.0 - 0.0 = 2.0
    assert dimensions["width"] == 2.0
    assert dimensions["height"] == 1.0
    assert dimensions["length"] == 2.0
    assert dimensions["radius"] == 1.0  # max(2.0, 1.0, 2.0) / 2 = 1.0


def test_measure_without_bounds():
    """Test measuring with no bounds data"""
    measurer = SizeMeasurer()

    mesh_data = {}
    dimensions = measurer.measure(mesh_data)

    assert dimensions["width"] == 0.0
    assert dimensions["height"] == 0.0
    assert dimensions["length"] == 0.0
    assert dimensions["radius"] == 0.0


def test_measure_component():
    """Test measuring a single component"""
    measurer = SizeMeasurer()

    component_mesh = {
        "bounds": {
            "min_x": 0.0,
            "max_x": 0.5,
            "min_y": 0.0,
            "max_y": 0.5,
            "min_z": 0.0,
            "max_z": 0.5,
        }
    }

    dimensions = measurer.measure_component(component_mesh)

    assert dimensions["width"] == 0.5
    assert dimensions["height"] == 0.5
    assert dimensions["length"] == 0.5
