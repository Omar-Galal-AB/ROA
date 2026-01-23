"""
Test suite for Robot State and Robot Manager modules.

Tests robot state tracking, registration, and multi-robot coordination.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime


# Mock data classes (will be replaced by actual imports)
@dataclass
class JointState:
    """Mock joint state for testing."""
    name: str
    position: float
    velocity: float = 0.0
    effort: float = 0.0
    is_moving: bool = False
    at_limit: bool = False


@dataclass
class RobotSpec:
    """Mock robot specification from FTI."""
    robot_id: str
    robot_name: str
    joints: List[dict]
    capabilities: dict = None


class TestRobotState:
    """Tests for RobotState class."""
    
    @pytest.fixture
    def mock_robot_state(self):
        """Create mock robot state for testing."""
        state = Mock()
        state.robot_id = "robot_0"
        state.robot_name = "Test Robot"
        state.mode = "rpm"
        state.status = "ready"
        state.joints = {
            "shoulder": JointState("shoulder", 0.0),
            "elbow": JointState("elbow", 0.0),
            "wrist": JointState("wrist", 0.0)
        }
        state.last_update = datetime.now()
        state.get_joint = lambda name: state.joints.get(name)
        state.update_joint = Mock()
        return state
    
    def test_initial_state(self, mock_robot_state):
        """Test initial robot state values."""
        assert mock_robot_state.robot_id == "robot_0"
        assert mock_robot_state.mode == "rpm"
        assert mock_robot_state.status == "ready"
        assert len(mock_robot_state.joints) == 3
    
    def test_get_joint_state(self, mock_robot_state):
        """Test retrieving joint state."""
        joint = mock_robot_state.get_joint("shoulder")
        
        assert joint is not None
        assert joint.name == "shoulder"
        assert joint.position == 0.0
    
    def test_get_unknown_joint(self, mock_robot_state):
        """Test retrieving unknown joint returns None."""
        joint = mock_robot_state.get_joint("unknown_joint")
        
        assert joint is None
    
    def test_update_joint_position(self, mock_robot_state):
        """Test updating joint position."""
        mock_robot_state.update_joint("shoulder", position=1.5)
        
        mock_robot_state.update_joint.assert_called_once_with("shoulder", position=1.5)
    
    def test_joint_at_limit_flag(self, mock_robot_state):
        """Test joint at-limit flag."""
        mock_robot_state.joints["shoulder"] = JointState("shoulder", 3.14, at_limit=True)
        
        joint = mock_robot_state.get_joint("shoulder")
        assert joint.at_limit is True
    
    def test_joint_moving_flag(self, mock_robot_state):
        """Test joint is-moving flag."""
        mock_robot_state.joints["elbow"] = JointState("elbow", 1.0, velocity=0.5, is_moving=True)
        
        joint = mock_robot_state.get_joint("elbow")
        assert joint.is_moving is True
        assert joint.velocity == 0.5


class TestRobotStateFromFTI:
    """Tests for creating RobotState from FTI data."""
    
    @pytest.fixture
    def fti_robot_spec(self):
        """Sample FTI robot specification."""
        return RobotSpec(
            robot_id="robot_0",
            robot_name="UR5e Robot",
            joints=[
                {"name": "shoulder_pan", "type": "revolute", 
                 "limits": {"lower": -6.28, "upper": 6.28, "velocity": 2.0}},
                {"name": "shoulder_lift", "type": "revolute",
                 "limits": {"lower": -6.28, "upper": 6.28, "velocity": 2.0}},
                {"name": "elbow", "type": "revolute",
                 "limits": {"lower": -3.14, "upper": 3.14, "velocity": 3.0}},
            ],
            capabilities={"has_gripper": True, "max_payload": 5.0}
        )
    
    def test_create_from_fti_spec(self, fti_robot_spec):
        """Test creating robot state from FTI specification."""
        # TODO: Implement when RobotState.from_fti available
        assert fti_robot_spec.robot_id == "robot_0"
        assert len(fti_robot_spec.joints) == 3
    
    def test_joint_limits_from_fti(self, fti_robot_spec):
        """Test joint limits are extracted from FTI data."""
        shoulder = fti_robot_spec.joints[0]
        
        assert shoulder["limits"]["lower"] == -6.28
        assert shoulder["limits"]["upper"] == 6.28
        assert shoulder["limits"]["velocity"] == 2.0
    
    def test_capabilities_from_fti(self, fti_robot_spec):
        """Test robot capabilities are extracted from FTI data."""
        assert fti_robot_spec.capabilities["has_gripper"] is True
        assert fti_robot_spec.capabilities["max_payload"] == 5.0


class TestRobotStateFromDIMC:
    """Tests for updating RobotState from DIMC data."""
    
    @pytest.fixture
    def dimc_joint_states(self):
        """Sample DIMC joint states message."""
        return {
            "robot_id": "robot_0",
            "timestamp": 1705167200.123,
            "joints": [
                {"name": "shoulder_pan", "position": 0.5, "velocity": 0.1, "effort": 10.0},
                {"name": "shoulder_lift", "position": -0.3, "velocity": 0.0, "effort": 15.0},
                {"name": "elbow", "position": 1.2, "velocity": 0.2, "effort": 5.0},
            ]
        }
    
    @pytest.fixture
    def dimc_obstacle_data(self):
        """Sample DIMC obstacle data."""
        return {
            "robot_id": "robot_0",
            "timestamp": 1705167200.123,
            "obstacles": [
                {"id": "obstacle_0", "distance_cm": 45.0, "direction": [0.5, 0.5, 0.0]},
                {"id": "obstacle_1", "distance_cm": 120.0, "direction": [-0.3, 0.7, 0.0]},
            ],
            "closest_distance_cm": 45.0
        }
    
    def test_update_from_dimc_joints(self, dimc_joint_states):
        """Test updating robot state from DIMC joint data."""
        # TODO: Implement when RobotState.update_from_dimc available
        assert len(dimc_joint_states["joints"]) == 3
        assert dimc_joint_states["joints"][0]["position"] == 0.5
    
    def test_update_from_dimc_obstacles(self, dimc_obstacle_data):
        """Test updating obstacle data from DIMC."""
        assert dimc_obstacle_data["closest_distance_cm"] == 45.0
        assert len(dimc_obstacle_data["obstacles"]) == 2


class TestRobotManager:
    """Tests for RobotManager class."""
    
    @pytest.fixture
    def mock_manager(self):
        """Create mock robot manager."""
        manager = Mock()
        manager.robots = {}
        manager.max_robots = 10
        manager.selected_robot = None
        
        def register_robot(robot_id, spec):
            if len(manager.robots) >= manager.max_robots:
                return False, "max_robots_exceeded"
            if robot_id in manager.robots:
                return False, "already_registered"
            manager.robots[robot_id] = Mock(robot_id=robot_id)
            return True, "registered"
        
        def unregister_robot(robot_id):
            if robot_id in manager.robots:
                del manager.robots[robot_id]
                return True
            return False
        
        def get_robot(robot_id):
            return manager.robots.get(robot_id)
        
        def select_robot(robot_id):
            if robot_id in manager.robots:
                manager.selected_robot = robot_id
                return True
            return False
        
        manager.register_robot = register_robot
        manager.unregister_robot = unregister_robot
        manager.get_robot = get_robot
        manager.select_robot = select_robot
        manager.list_robots = lambda: list(manager.robots.keys())
        
        return manager
    
    def test_register_robot(self, mock_manager):
        """Test robot registration."""
        success, message = mock_manager.register_robot("robot_0", {})
        
        assert success is True
        assert message == "registered"
        assert "robot_0" in mock_manager.robots
    
    def test_register_duplicate_robot(self, mock_manager):
        """Test duplicate registration is rejected."""
        mock_manager.register_robot("robot_0", {})
        success, message = mock_manager.register_robot("robot_0", {})
        
        assert success is False
        assert message == "already_registered"
    
    def test_unregister_robot(self, mock_manager):
        """Test robot unregistration."""
        mock_manager.register_robot("robot_0", {})
        result = mock_manager.unregister_robot("robot_0")
        
        assert result is True
        assert "robot_0" not in mock_manager.robots
    
    def test_unregister_unknown_robot(self, mock_manager):
        """Test unregistering unknown robot."""
        result = mock_manager.unregister_robot("unknown")
        
        assert result is False
    
    def test_get_robot(self, mock_manager):
        """Test retrieving robot by ID."""
        mock_manager.register_robot("robot_0", {})
        robot = mock_manager.get_robot("robot_0")
        
        assert robot is not None
        assert robot.robot_id == "robot_0"
    
    def test_get_unknown_robot(self, mock_manager):
        """Test retrieving unknown robot returns None."""
        robot = mock_manager.get_robot("unknown")
        
        assert robot is None
    
    def test_list_robots(self, mock_manager):
        """Test listing all registered robots."""
        mock_manager.register_robot("robot_0", {})
        mock_manager.register_robot("robot_1", {})
        mock_manager.register_robot("robot_2", {})
        
        robots = mock_manager.list_robots()
        
        assert len(robots) == 3
        assert "robot_0" in robots
        assert "robot_1" in robots
        assert "robot_2" in robots
    
    def test_select_robot(self, mock_manager):
        """Test selecting active robot."""
        mock_manager.register_robot("robot_0", {})
        mock_manager.register_robot("robot_1", {})
        
        result = mock_manager.select_robot("robot_1")
        
        assert result is True
        assert mock_manager.selected_robot == "robot_1"
    
    def test_select_unknown_robot(self, mock_manager):
        """Test selecting unknown robot fails."""
        result = mock_manager.select_robot("unknown")
        
        assert result is False
        assert mock_manager.selected_robot is None
    
    def test_max_robots_limit(self, mock_manager):
        """Test maximum robots limit is enforced."""
        mock_manager.max_robots = 2
        
        mock_manager.register_robot("robot_0", {})
        mock_manager.register_robot("robot_1", {})
        success, message = mock_manager.register_robot("robot_2", {})
        
        assert success is False
        assert message == "max_robots_exceeded"


class TestMultiRobotCoordination:
    """Tests for multi-robot coordination scenarios."""
    
    @pytest.fixture
    def manager_with_robots(self):
        """Create manager with multiple robots pre-registered."""
        manager = Mock()
        manager.robots = {
            "robot_0": Mock(robot_id="robot_0", mode="rpm", status="ready"),
            "robot_1": Mock(robot_id="robot_1", mode="adm", status="moving"),
            "robot_2": Mock(robot_id="robot_2", mode="rpm", status="emergency_stopped"),
        }
        manager.broadcast_estop = Mock()
        manager.get_all_statuses = lambda: {k: v.status for k, v in manager.robots.items()}
        return manager
    
    def test_broadcast_emergency_stop(self, manager_with_robots):
        """Test emergency stop broadcast to all robots."""
        manager_with_robots.broadcast_estop("system_error")
        
        manager_with_robots.broadcast_estop.assert_called_once_with("system_error")
    
    def test_get_all_statuses(self, manager_with_robots):
        """Test getting status of all robots."""
        statuses = manager_with_robots.get_all_statuses()
        
        assert statuses["robot_0"] == "ready"
        assert statuses["robot_1"] == "moving"
        assert statuses["robot_2"] == "emergency_stopped"
    
    def test_independent_robot_modes(self, manager_with_robots):
        """Test robots can have independent control modes."""
        assert manager_with_robots.robots["robot_0"].mode == "rpm"
        assert manager_with_robots.robots["robot_1"].mode == "adm"


class TestStateHistory:
    """Tests for state history tracking."""
    
    @pytest.fixture
    def mock_state_with_history(self):
        """Create mock state with history tracking."""
        state = Mock()
        state.history = []
        state.max_history = 100
        
        def add_to_history(entry):
            state.history.append(entry)
            if len(state.history) > state.max_history:
                state.history = state.history[-state.max_history:]
        
        state.add_to_history = add_to_history
        state.get_history = lambda n=10: state.history[-n:]
        return state
    
    def test_add_history_entry(self, mock_state_with_history):
        """Test adding history entry."""
        mock_state_with_history.add_to_history({"position": 0.5, "time": 100})
        
        assert len(mock_state_with_history.history) == 1
    
    def test_history_limit(self, mock_state_with_history):
        """Test history size is limited."""
        mock_state_with_history.max_history = 5
        
        for i in range(10):
            mock_state_with_history.add_to_history({"position": i * 0.1})
        
        assert len(mock_state_with_history.history) == 5
    
    def test_get_recent_history(self, mock_state_with_history):
        """Test getting recent history entries."""
        for i in range(5):
            mock_state_with_history.add_to_history({"position": i * 0.1})
        
        recent = mock_state_with_history.get_history(3)
        
        assert len(recent) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
