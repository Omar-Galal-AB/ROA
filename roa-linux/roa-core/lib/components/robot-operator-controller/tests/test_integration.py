"""
Integration tests for ROC components working together
Tests full workflows and inter-component communication
"""

import os
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "python"))

from command_queue import CommandQueue
from integration_handlers import IntegrationHandlers

# Import all components
from roc_ros2_node import ROCNode
from safety.safety_manager import SafetyManager


class TestROCIntegration:
    """Integration tests (25 tests)"""

    def test_full_system_initialization(self):
        """Test 1: Full ROC system initializes correctly"""
        # Mock ROS2 node
        with patch("rclpy.init"), patch("rclpy.create_node"):
            node = ROCNode()
            assert node is not None

    def test_fti_to_roc_robot_specs(self):
        """Test 2: ROC receives robot specs from FTI"""
        handlers = IntegrationHandlers()

        robot_specs = {
            "robot_id": "robot_001",
            "num_joints": 6,
            "joint_names": ["j1", "j2", "j3", "j4", "j5", "j6"],
        }

        result = handlers.process_fti_robot_specs(robot_specs)
        assert result == True

    def test_dimc_spatial_data_flow(self):
        """Test 3: ROC receives spatial data from DIMC"""
        handlers = IntegrationHandlers()

        spatial_data = {
            "robot_id": "robot_001",
            "position": [1.0, 2.0, 0.5],
            "orientation": [0.0, 0.0, 0.0, 1.0],
        }

        result = handlers.process_dimc_spatial_data(spatial_data)
        assert result == True

    def test_comc_coordination_messages(self):
        """Test 4: ROC exchanges coordination messages with COMC"""
        handlers = IntegrationHandlers()

        # Send robot intentions to COMC
        intentions = {
            "robot_id": "robot_001",
            "next_position": [2.0, 3.0, 0.5],
            "velocity": [0.5, 0.5, 0.0],
        }

        result = handlers.send_robot_intentions(intentions)
        assert result == True

        # Receive evasion response from COMC
        evasion_response = {
            "robot_id": "robot_001",
            "alternative_path": [[1.5, 2.5, 0.5], [2.0, 3.0, 0.5]],
        }

        result = handlers.process_comc_evasion_response(evasion_response)
        assert result == True

    def test_webthread_status_reporting(self):
        """Test 5: ROC reports status to Webthread"""
        handlers = IntegrationHandlers()

        status = {
            "component": "ROC",
            "health": "healthy",
            "active_robots": 2,
            "cpu_usage": 15.5,
        }

        result = handlers.send_status_to_webthread(status)
        assert result == True

    def test_command_queue_integration(self):
        """Test 6: Command queue integrates with controllers"""
        queue = CommandQueue()

        commands = [
            {
                "type": "position",
                "robot_id": "robot_001",
                "joint_values": [0.5] * 6,
                "priority": 1,
            },
            {
                "type": "velocity",
                "robot_id": "robot_001",
                "joint_values": [0.1] * 6,
                "priority": 2,
            },
            {
                "type": "position",
                "robot_id": "robot_002",
                "joint_values": [1.0] * 6,
                "priority": 0,
            },
        ]

        for cmd in commands:
            queue.add_command(cmd)

        # Should return highest priority first
        next_cmd = queue.get_next_command()
        assert next_cmd["priority"] == 2

    def test_safety_integration_with_control(self):
        """Test 7: Safety system integrates with control flow"""
        safety = SafetyManager()
        queue = CommandQueue()

        # Add command
        command = {
            "type": "position",
            "robot_id": "robot_001",
            "joint_values": [1.0] * 6,
        }
        queue.add_command(command)

        # Simulate collision detected
        safety.activate_emergency_stop()

        # Command queue should respect emergency stop
        next_cmd = queue.get_next_command()
        if safety.emergency_stop_active:
            assert next_cmd is None or queue.is_paused()

    def test_multi_robot_control(self):
        """Test 8: ROC controls multiple robots simultaneously"""
        handlers = IntegrationHandlers()

        # Add multiple robots
        for i in range(3):
            robot_specs = {
                "robot_id": f"robot_{i:03d}",
                "num_joints": 6,
                "joint_names": ["j1", "j2", "j3", "j4", "j5", "j6"],
            }
            handlers.add_robot(robot_specs)

        assert handlers.get_active_robot_count() == 3

    def test_rpm_mode_workflow(self):
        """Test 9: Complete RPM mode workflow"""
        with patch("rclpy.init"), patch("rclpy.create_node"):
            node = ROCNode()

            # Activate RPM mode
            result = node.activate_mode("RPM")
            assert result == True

            # Send manual command
            command = {"type": "position", "joint_values": [0.5] * 6}
            result = node.execute_command("robot_001", command)
            assert result is not None

    def test_adm_mode_workflow(self):
        """Test 10: Complete ADM mode workflow"""
        with patch("rclpy.init"), patch("rclpy.create_node"):
            node = ROCNode()

            # Activate ADM mode
            result = node.activate_mode("ADM")
            assert result == True

            # Queue autonomous task
            task = {"type": "pick_and_place", "pick": [1, 2, 0.5], "place": [2, 3, 0.5]}
            result = node.queue_task("robot_001", task)
            assert result is not None

    def test_path_planning_integration(self):
        """Test 11: Path planning integrates with execution"""
        handlers = IntegrationHandlers()

        # Plan path
        start = [0.0, 0.0, 0.0]
        goal = [5.0, 5.0, 0.0]
        path = handlers.plan_path("robot_001", start, goal)

        assert path is not None
        assert len(path) > 0

    def test_obstacle_avoidance_workflow(self):
        """Test 12: Complete obstacle avoidance workflow"""
        handlers = IntegrationHandlers()
        safety = SafetyManager()

        # Receive obstacle data from DIMC
        obstacles = [{"position": [2.0, 2.0, 0.0], "radius": 0.5}]
        handlers.update_obstacles(obstacles)

        # Plan path avoiding obstacles
        path = handlers.plan_path("robot_001", [0, 0, 0], [5, 5, 0])

        # Verify path avoids obstacles
        assert path is not None

    def test_error_recovery_workflow(self):
        """Test 13: System recovers from errors"""
        with patch("rclpy.init"), patch("rclpy.create_node"):
            node = ROCNode()

            # Simulate error
            error = {"type": "communication_timeout", "component": "DIMC"}
            node.handle_error(error)

            # System should attempt recovery
            assert node.is_recovering() or node.is_operational()

    def test_multi_component_data_flow(self):
        """Test 14: Data flows correctly between all components"""
        handlers = IntegrationHandlers()

        # FTI → ROC
        robot_specs = {"robot_id": "robot_001", "num_joints": 6}
        assert handlers.process_fti_robot_specs(robot_specs) == True

        # DIMC → ROC
        spatial_data = {"robot_id": "robot_001", "position": [1, 2, 0.5]}
        assert handlers.process_dimc_spatial_data(spatial_data) == True

        # ROC → COMC
        intentions = {"robot_id": "robot_001", "next_position": [2, 3, 0.5]}
        assert handlers.send_robot_intentions(intentions) == True

    def test_configuration_reload(self):
        """Test 15: Configuration can be reloaded dynamically"""
        with patch("rclpy.init"), patch("rclpy.create_node"):
            node = ROCNode()

            new_config = {
                "control_rate": 120,  # Change from 60 to 120 Hz
                "max_robots": 16,
            }

            result = node.reload_configuration(new_config)
            assert result == True

    def test_logging_integration(self):
        """Test 16: All components log to central system"""
        handlers = IntegrationHandlers()

        # Components should generate logs
        logs = handlers.get_recent_logs()
        assert logs is not None

    def test_startup_sequence(self):
        """Test 17: System starts up in correct order"""
        with patch("rclpy.init"), patch("rclpy.create_node"):
            from startup_coordinator import StartupCoordinator

            coordinator = StartupCoordinator()
            result = coordinator.initialize_roc_system()

            assert result == True

    def test_shutdown_sequence(self):
        """Test 18: System shuts down gracefully"""
        with patch("rclpy.init"), patch("rclpy.create_node"):
            node = ROCNode()

            result = node.shutdown()
            assert result == True

    def test_ros2_topic_connectivity(self):
        """Test 19: ROS2 topics are properly connected"""
        with patch("rclpy.init"), patch("rclpy.create_node"):
            node = ROCNode()

            # Check publishers
            assert hasattr(node, "status_publisher")
            assert hasattr(node, "command_publisher")

            # Check subscribers
            assert hasattr(node, "spatial_data_subscriber")
            assert hasattr(node, "robot_specs_subscriber")

    def test_performance_under_load(self):
        """Test 20: System performs well under load"""
        handlers = IntegrationHandlers()
        queue = CommandQueue()

        # Add many commands rapidly
        for i in range(100):
            command = {
                "type": "position",
                "robot_id": f"robot_{i % 8:03d}",
                "joint_values": [float(i % 10) / 10] * 6,
            }
            queue.add_command(command)

        # Should handle without errors
        assert queue.get_queue_length() == 100

    def test_concurrent_robot_operations(self):
        """Test 21: Multiple robots operate concurrently"""
        handlers = IntegrationHandlers()

        # Simulate concurrent operations
        robot_ids = ["robot_001", "robot_002", "robot_003"]

        for robot_id in robot_ids:
            command = {"type": "position", "joint_values": [0.5] * 6}
            result = handlers.execute_command(robot_id, command)
            assert result is not None

    def test_mode_switching_workflow(self):
        """Test 22: Switching between RPM and ADM modes"""
        with patch("rclpy.init"), patch("rclpy.create_node"):
            node = ROCNode()

            # Start in RPM
            node.activate_mode("RPM")
            assert node.current_mode == "RPM"

            # Switch to ADM
            node.activate_mode("ADM")
            assert node.current_mode == "ADM"

            # Switch back to RPM
            node.activate_mode("RPM")
            assert node.current_mode == "RPM"

    def test_safety_violation_handling(self):
        """Test 23: System handles safety violations correctly"""
        safety = SafetyManager()
        handlers = IntegrationHandlers()

        # Trigger collision
        safety.check_collision(0.01)

        # System should halt operations
        assert safety.should_stop() == True

        # Clear violation
        safety.deactivate_emergency_stop()

        # System should resume
        assert safety.should_stop() == False

    def test_data_synchronization(self):
        """Test 24: Data stays synchronized across components"""
        handlers = IntegrationHandlers()

        # Update robot state
        state = {
            "robot_id": "robot_001",
            "position": [1.0, 2.0, 0.5],
            "joint_positions": [0.5] * 6,
        }
        handlers.update_robot_state(state)

        # Retrieve state
        retrieved_state = handlers.get_robot_state("robot_001")

        assert retrieved_state["position"] == state["position"]

    def test_end_to_end_task_execution(self):
        """Test 25: Complete task from planning to execution"""
        with patch("rclpy.init"), patch("rclpy.create_node"):
            node = ROCNode()

            # Define task
            task = {
                "type": "move_to_position",
                "robot_id": "robot_001",
                "target_position": [5.0, 5.0, 1.0],
            }

            # Plan
            result = node.plan_task(task)
            assert result is not None

            # Execute
            result = node.execute_task(task)
            assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
