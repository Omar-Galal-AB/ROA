"""
Test configuration for ROC component tests.

Provides shared fixtures and test utilities for all ROC test modules.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

# ============================================================================
# Test Data Fixtures
# ============================================================================


@pytest.fixture
def sample_robot_spec():
    """Sample robot specification from FTI."""
    return {
        "robot_id": "robot_0",
        "robot_name": "UR5e Test Robot",
        "joints": [
            {
                "name": "shoulder_pan_joint",
                "type": "revolute",
                "parent_link": "base_link",
                "child_link": "shoulder_link",
                "ue5_constraint_name": "PC_shoulder_pan",
                "limits": {
                    "lower": -6.28318,
                    "upper": 6.28318,
                    "velocity": 2.09,
                    "effort": 150.0,
                },
            },
            {
                "name": "shoulder_lift_joint",
                "type": "revolute",
                "parent_link": "shoulder_link",
                "child_link": "upper_arm_link",
                "ue5_constraint_name": "PC_shoulder_lift",
                "limits": {
                    "lower": -6.28318,
                    "upper": 6.28318,
                    "velocity": 2.09,
                    "effort": 150.0,
                },
            },
            {
                "name": "elbow_joint",
                "type": "revolute",
                "parent_link": "upper_arm_link",
                "child_link": "forearm_link",
                "ue5_constraint_name": "PC_elbow",
                "limits": {
                    "lower": -3.14159,
                    "upper": 3.14159,
                    "velocity": 3.14,
                    "effort": 150.0,
                },
            },
            {
                "name": "wrist_1_joint",
                "type": "revolute",
                "parent_link": "forearm_link",
                "child_link": "wrist_1_link",
                "ue5_constraint_name": "PC_wrist_1",
                "limits": {
                    "lower": -6.28318,
                    "upper": 6.28318,
                    "velocity": 3.14,
                    "effort": 28.0,
                },
            },
            {
                "name": "wrist_2_joint",
                "type": "revolute",
                "parent_link": "wrist_1_link",
                "child_link": "wrist_2_link",
                "ue5_constraint_name": "PC_wrist_2",
                "limits": {
                    "lower": -6.28318,
                    "upper": 6.28318,
                    "velocity": 3.14,
                    "effort": 28.0,
                },
            },
            {
                "name": "wrist_3_joint",
                "type": "revolute",
                "parent_link": "wrist_2_link",
                "child_link": "wrist_3_link",
                "ue5_constraint_name": "PC_wrist_3",
                "limits": {
                    "lower": -6.28318,
                    "upper": 6.28318,
                    "velocity": 3.14,
                    "effort": 28.0,
                },
            },
        ],
        "robot_capabilities": {
            "has_gripper": True,
            "max_payload_kg": 5.0,
            "reach_cm": 85.0,
        },
        "kinematic_chain": {
            "root_link": "base_link",
            "tip_link": "wrist_3_link",
            "total_links": 7,
        },
    }


@pytest.fixture
def sample_joint_states():
    """Sample joint states from DIMC."""
    return {
        "robot_id": "robot_0",
        "timestamp": 1705167200.123,
        "sequence": 1234,
        "joints": [
            {
                "name": "shoulder_pan_joint",
                "position": 0.0,
                "velocity": 0.0,
                "effort": 0.0,
            },
            {
                "name": "shoulder_lift_joint",
                "position": -1.57,
                "velocity": 0.0,
                "effort": 12.5,
            },
            {"name": "elbow_joint", "position": 1.57, "velocity": 0.1, "effort": 5.0},
            {"name": "wrist_1_joint", "position": 0.0, "velocity": 0.0, "effort": 0.0},
            {"name": "wrist_2_joint", "position": 1.57, "velocity": 0.0, "effort": 0.0},
            {"name": "wrist_3_joint", "position": 0.0, "velocity": 0.0, "effort": 0.0},
        ],
    }


@pytest.fixture
def sample_obstacle_data():
    """Sample obstacle data from DIMC."""
    return {
        "robot_id": "robot_0",
        "timestamp": 1705167200.123,
        "obstacles": [
            {
                "id": "obstacle_001",
                "type": "static",
                "distance_cm": 45.5,
                "direction": [0.707, 0.707, 0.0],
                "bounding_box": {"min": [10, 10, 0], "max": [50, 50, 100]},
            }
        ],
        "closest_distance_cm": 45.5,
        "zone_status": "warning",
    }


@pytest.fixture
def sample_ipc_messages():
    """Sample IPC messages for testing."""
    return {
        "joint_command_request": {
            "type": "joint_command_request",
            "robot_id": "robot_0",
            "commands": [
                {
                    "joint_name": "shoulder_pan_joint",
                    "target_position": 1.5708,
                    "velocity_limit": 1.0,
                    "command_id": "cmd_001",
                }
            ],
            "source": "rpm",
            "timestamp": 1705167200.123,
        },
        "emergency_stop": {
            "type": "emergency_stop",
            "robot_id": "robot_0",
            "reason": "user_requested",
            "timestamp": 1705167200.456,
        },
        "mode_change": {
            "type": "mode_change",
            "robot_id": "robot_0",
            "new_mode": "adm",
            "timestamp": 1705167200.789,
        },
        "heartbeat": {
            "type": "heartbeat",
            "source": "ue5",
            "timestamp": 1705167200.000,
        },
    }


# ============================================================================
# Mock Component Fixtures
# ============================================================================


@pytest.fixture
def mock_ipc_handler():
    """Mock IPC handler for testing."""
    handler = Mock()
    handler.connected = False
    handler.connect = AsyncMock(return_value=True)
    handler.disconnect = AsyncMock()
    handler.send_message = AsyncMock(return_value=True)
    handler.receive_message = AsyncMock(return_value={"type": "heartbeat"})
    handler.is_connected = Mock(return_value=False)
    handler.callbacks = {}

    def register_callback(msg_type, callback):
        handler.callbacks[msg_type] = callback

    handler.register_callback = register_callback
    return handler


@pytest.fixture
def mock_robot_manager():
    """Mock robot manager for testing."""
    manager = Mock()
    manager.robots = {}
    manager.selected_robot = None

    def register_robot(robot_id, spec):
        manager.robots[robot_id] = Mock(robot_id=robot_id, spec=spec, mode="rpm", status="ready")
        return True, "registered"

    def get_robot(robot_id):
        return manager.robots.get(robot_id)

    manager.register_robot = register_robot
    manager.get_robot = get_robot
    manager.list_robots = lambda: list(manager.robots.keys())
    return manager


@pytest.fixture
def mock_command_validator():
    """Mock command validator for testing."""
    validator = Mock()
    validator.validate_command = Mock(return_value=(True, None))
    validator.check_position_limits = Mock(return_value=True)
    validator.check_velocity_limits = Mock(return_value=True)
    validator.check_collision = Mock(return_value=True)
    return validator


@pytest.fixture
def mock_mode_manager():
    """Mock mode manager for testing."""
    manager = Mock()
    manager.modes = {}

    def get_mode(robot_id):
        return manager.modes.get(robot_id, "rpm")

    def set_mode(robot_id, mode):
        manager.modes[robot_id] = mode
        return True

    manager.get_mode = get_mode
    manager.set_mode = set_mode
    return manager


# ============================================================================
# Configuration Fixtures
# ============================================================================


@pytest.fixture
def config_dir(tmp_path):
    """Create temporary config directory with test configs."""
    config_path = tmp_path / "Config"
    config_path.mkdir()

    # Create test IPC config
    ipc_config = {
        "receive_port": 9876,
        "send_port": 9877,
        "ue5_host": "localhost",
        "connection_timeout_ms": 5000,
    }
    (config_path / "ipc_config.json").write_text(json.dumps(ipc_config))

    # Create test validation config
    validation_config = {
        "safety_margin": 0.05,
        "stop_distance": 10.0,
        "slow_distance": 50.0,
    }
    (config_path / "validation_config.json").write_text(json.dumps(validation_config))

    return config_path


# ============================================================================
# Async Test Utilities
# ============================================================================


@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Test Categories Markers
# ============================================================================


def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "requires_ue5: Requires UE5 connection")


# ============================================================================
# Test Utilities
# ============================================================================


def assert_valid_joint_command(command: dict):
    """Assert that a joint command has valid structure."""
    assert "type" in command
    assert command["type"] == "joint_command_request"
    assert "robot_id" in command
    assert "commands" in command
    assert isinstance(command["commands"], list)
    for cmd in command["commands"]:
        assert "joint_name" in cmd
        assert "target_position" in cmd


def assert_valid_response(response: dict):
    """Assert that a response message has valid structure."""
    assert "type" in response
    assert "timestamp" in response
    assert response["type"] in [
        "command_approved",
        "command_rejected",
        "safety_alert",
        "state_update",
        "heartbeat_ack",
    ]


def create_joint_command(
    robot_id: str, joint_name: str, position: float, velocity: float = 1.0
) -> dict:
    """Helper to create joint command message."""
    return {
        "type": "joint_command_request",
        "robot_id": robot_id,
        "commands": [
            {
                "joint_name": joint_name,
                "target_position": position,
                "velocity_limit": velocity,
                "command_id": f"cmd_{datetime.now().timestamp()}",
            }
        ],
        "source": "rpm",
        "timestamp": datetime.now().timestamp(),
    }
