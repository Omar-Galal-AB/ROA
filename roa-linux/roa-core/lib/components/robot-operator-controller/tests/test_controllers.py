"""
Test suite for ROC controllers (arm, gripper, mobile, base)
Tests cover initialization, control commands, safety checks, and state management
"""

import os
import sys
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "python"))

from controllers.arm_controller import ArmController
from controllers.base_controller import BaseController
from controllers.gripper_controller import GripperController
from controllers.mobile_controller import MobileController


class TestBaseController:
    """Test suite for BaseController (25 tests total for all controllers)"""

    def test_base_controller_initialization(self):
        """Test 1: Base controller initializes correctly"""
        controller = BaseController()
        assert controller is not None
        assert hasattr(controller, "enabled")
        assert controller.enabled == False

    def test_base_controller_enable(self):
        """Test 2: Base controller can be enabled"""
        controller = BaseController()
        controller.enable()
        assert controller.enabled == True

    def test_base_controller_disable(self):
        """Test 3: Base controller can be disabled"""
        controller = BaseController()
        controller.enable()
        controller.disable()
        assert controller.enabled == False

    def test_base_controller_command_when_disabled(self):
        """Test 4: Commands rejected when controller disabled"""
        controller = BaseController()
        result = controller.execute_command({"type": "test"})
        assert result == False  # Should reject command when disabled


class TestArmController:
    """Test suite for ArmController"""

    def test_arm_controller_initialization(self):
        """Test 5: Arm controller initializes with joint configuration"""
        joint_config = {
            "num_joints": 6,
            "joint_names": [
                "shoulder_pan",
                "shoulder_lift",
                "elbow",
                "wrist_1",
                "wrist_2",
                "wrist_3",
            ],
            "joint_limits": [(-np.pi, np.pi)] * 6,
        }
        controller = ArmController(joint_config)
        assert controller.num_joints == 6
        assert len(controller.joint_positions) == 6

    def test_arm_controller_position_command(self):
        """Test 6: Arm controller accepts position commands"""
        joint_config = {
            "num_joints": 6,
            "joint_names": ["j1", "j2", "j3", "j4", "j5", "j6"],
        }
        controller = ArmController(joint_config)
        controller.enable()

        positions = [0.0, 0.5, 1.0, 0.5, 0.0, -0.5]
        result = controller.set_joint_positions(positions)
        assert result == True

    def test_arm_controller_velocity_command(self):
        """Test 7: Arm controller accepts velocity commands"""
        joint_config = {
            "num_joints": 6,
            "joint_names": ["j1", "j2", "j3", "j4", "j5", "j6"],
        }
        controller = ArmController(joint_config)
        controller.enable()

        velocities = [0.1, 0.2, 0.3, 0.2, 0.1, 0.0]
        result = controller.set_joint_velocities(velocities)
        assert result == True

    def test_arm_controller_torque_command(self):
        """Test 8: Arm controller accepts torque commands"""
        joint_config = {
            "num_joints": 6,
            "joint_names": ["j1", "j2", "j3", "j4", "j5", "j6"],
        }
        controller = ArmController(joint_config)
        controller.enable()

        torques = [10.0, 15.0, 20.0, 15.0, 10.0, 5.0]
        result = controller.set_joint_torques(torques)
        assert result == True

    def test_arm_controller_joint_limit_enforcement(self):
        """Test 9: Arm controller enforces joint limits"""
        joint_config = {
            "num_joints": 2,
            "joint_names": ["j1", "j2"],
            "joint_limits": [(-1.0, 1.0), (-1.0, 1.0)],
        }
        controller = ArmController(joint_config)
        controller.enable()

        # Try to exceed limits
        positions = [2.0, -2.0]  # Outside limits
        result = controller.set_joint_positions(positions)
        # Should clamp or reject
        if result:
            # If accepted, should be clamped
            assert abs(controller.joint_positions[0]) <= 1.0
            assert abs(controller.joint_positions[1]) <= 1.0

    def test_arm_controller_get_state(self):
        """Test 10: Arm controller returns current state"""
        joint_config = {"num_joints": 3, "joint_names": ["j1", "j2", "j3"]}
        controller = ArmController(joint_config)

        state = controller.get_state()
        assert "positions" in state
        assert "velocities" in state
        assert len(state["positions"]) == 3


class TestGripperController:
    """Test suite for GripperController"""

    def test_gripper_initialization(self):
        """Test 11: Gripper controller initializes correctly"""
        gripper_config = {
            "type": "parallel_jaw",
            "max_force": 100.0,
            "max_opening": 0.085,
        }
        controller = GripperController(gripper_config)
        assert controller.max_force == 100.0
        assert controller.max_opening == 0.085

    def test_gripper_open_command(self):
        """Test 12: Gripper can open"""
        gripper_config = {
            "type": "parallel_jaw",
            "max_force": 100.0,
            "max_opening": 0.085,
        }
        controller = GripperController(gripper_config)
        controller.enable()

        result = controller.open_gripper()
        assert result == True
        assert controller.position >= 0

    def test_gripper_close_command(self):
        """Test 13: Gripper can close"""
        gripper_config = {
            "type": "parallel_jaw",
            "max_force": 100.0,
            "max_opening": 0.085,
        }
        controller = GripperController(gripper_config)
        controller.enable()

        result = controller.close_gripper()
        assert result == True

    def test_gripper_position_control(self):
        """Test 14: Gripper accepts specific position"""
        gripper_config = {
            "type": "parallel_jaw",
            "max_force": 100.0,
            "max_opening": 0.085,
        }
        controller = GripperController(gripper_config)
        controller.enable()

        target_position = 0.04  # Half open
        result = controller.set_position(target_position)
        assert result == True

    def test_gripper_force_control(self):
        """Test 15: Gripper accepts force commands"""
        gripper_config = {
            "type": "parallel_jaw",
            "max_force": 100.0,
            "max_opening": 0.085,
        }
        controller = GripperController(gripper_config)
        controller.enable()

        target_force = 50.0  # 50% of max force
        result = controller.set_force(target_force)
        assert result == True

    def test_gripper_force_limit(self):
        """Test 16: Gripper enforces max force limit"""
        gripper_config = {
            "type": "parallel_jaw",
            "max_force": 100.0,
            "max_opening": 0.085,
        }
        controller = GripperController(gripper_config)
        controller.enable()

        excessive_force = 150.0  # Exceeds max_force
        result = controller.set_force(excessive_force)
        # Should clamp or reject
        if result:
            assert controller.current_force <= 100.0


class TestMobileController:
    """Test suite for MobileController"""

    def test_mobile_controller_differential_drive(self):
        """Test 17: Mobile controller handles differential drive"""
        mobile_config = {
            "type": "differential",
            "wheel_separation": 0.5,
            "wheel_radius": 0.1,
        }
        controller = MobileController(mobile_config)
        controller.enable()

        linear_velocity = 1.0  # m/s
        angular_velocity = 0.5  # rad/s
        result = controller.set_velocity(linear_velocity, angular_velocity)
        assert result == True

    def test_mobile_controller_omnidirectional(self):
        """Test 18: Mobile controller handles omnidirectional drive"""
        mobile_config = {"type": "omnidirectional", "num_wheels": 4}
        controller = MobileController(mobile_config)
        controller.enable()

        vx = 1.0  # Forward
        vy = 0.5  # Sideways
        omega = 0.2  # Rotation
        result = controller.set_velocity_omnidirectional(vx, vy, omega)
        assert result == True

    def test_mobile_controller_position_command(self):
        """Test 19: Mobile controller accepts position goals"""
        mobile_config = {"type": "differential"}
        controller = MobileController(mobile_config)
        controller.enable()

        target_x = 5.0
        target_y = 3.0
        target_theta = 1.57  # 90 degrees
        result = controller.set_position_goal(target_x, target_y, target_theta)
        assert result == True

    def test_mobile_controller_velocity_limits(self):
        """Test 20: Mobile controller enforces velocity limits"""
        mobile_config = {
            "type": "differential",
            "max_linear_velocity": 2.0,
            "max_angular_velocity": 1.0,
        }
        controller = MobileController(mobile_config)
        controller.enable()

        # Try to exceed limits
        excessive_linear = 5.0
        excessive_angular = 3.0
        result = controller.set_velocity(excessive_linear, excessive_angular)
        # Should clamp or reject
        if result:
            assert abs(controller.current_linear_velocity) <= 2.0
            assert abs(controller.current_angular_velocity) <= 1.0

    def test_mobile_controller_get_odometry(self):
        """Test 21: Mobile controller provides odometry"""
        mobile_config = {"type": "differential"}
        controller = MobileController(mobile_config)

        odom = controller.get_odometry()
        assert "x" in odom
        assert "y" in odom
        assert "theta" in odom


class TestControllerIntegration:
    """Integration tests for controller coordination"""

    def test_multiple_controllers_coordination(self):
        """Test 22: Multiple controllers can operate simultaneously"""
        arm_config = {
            "num_joints": 6,
            "joint_names": ["j1", "j2", "j3", "j4", "j5", "j6"],
        }
        gripper_config = {
            "type": "parallel_jaw",
            "max_force": 100.0,
            "max_opening": 0.085,
        }
        mobile_config = {"type": "differential"}

        arm = ArmController(arm_config)
        gripper = GripperController(gripper_config)
        mobile = MobileController(mobile_config)

        arm.enable()
        gripper.enable()
        mobile.enable()

        assert arm.enabled and gripper.enabled and mobile.enabled

    def test_controller_state_persistence(self):
        """Test 23: Controllers maintain state across commands"""
        arm_config = {"num_joints": 3, "joint_names": ["j1", "j2", "j3"]}
        controller = ArmController(arm_config)
        controller.enable()

        positions1 = [0.5, 0.5, 0.5]
        controller.set_joint_positions(positions1)
        state1 = controller.get_state()

        positions2 = [1.0, 1.0, 1.0]
        controller.set_joint_positions(positions2)
        state2 = controller.get_state()

        # State should have changed
        assert not np.array_equal(state1["positions"], state2["positions"])

    def test_controller_safety_stop(self):
        """Test 24: All controllers can emergency stop"""
        arm_config = {
            "num_joints": 6,
            "joint_names": ["j1", "j2", "j3", "j4", "j5", "j6"],
        }
        gripper_config = {"type": "parallel_jaw", "max_force": 100.0}
        mobile_config = {"type": "differential"}

        controllers = [
            ArmController(arm_config),
            GripperController(gripper_config),
            MobileController(mobile_config),
        ]

        for controller in controllers:
            controller.enable()
            result = controller.emergency_stop()
            assert result == True
            assert controller.enabled == False  # Should disable on e-stop

    def test_controller_status_reporting(self):
        """Test 25: All controllers report status correctly"""
        arm_config = {"num_joints": 3, "joint_names": ["j1", "j2", "j3"]}
        controller = ArmController(arm_config)

        status = controller.get_status()
        assert "enabled" in status
        assert "controller_type" in status
        assert "health" in status


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
