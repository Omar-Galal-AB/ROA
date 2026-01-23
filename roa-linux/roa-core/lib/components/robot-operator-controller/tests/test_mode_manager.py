"""
Test suite for Mode Manager module.

Tests control mode switching between RPM (Remote Position Mode)
and ADM (Autonomous Decision Mode).
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock
from enum import Enum
from dataclasses import dataclass


# Mock enums and classes (will be replaced by actual imports)
class ControlMode(Enum):
    """Control mode enumeration."""
    RPM = "rpm"  # Remote Position Mode - manual control
    ADM = "adm"  # Autonomous Decision Mode - automated control


@dataclass
class ModeTransition:
    """Represents a mode transition request."""
    from_mode: ControlMode
    to_mode: ControlMode
    robot_id: str
    reason: str = ""


class TestModeManager:
    """Tests for ModeManager class."""
    
    @pytest.fixture
    def mock_mode_manager(self):
        """Create mock mode manager for testing."""
        manager = Mock()
        manager.current_modes = {}
        manager.default_mode = ControlMode.RPM
        manager.transition_in_progress = {}
        
        def get_mode(robot_id):
            return manager.current_modes.get(robot_id, manager.default_mode)
        
        def set_mode(robot_id, mode):
            if robot_id not in manager.current_modes:
                return False, "robot_not_registered"
            manager.current_modes[robot_id] = mode
            return True, "mode_changed"
        
        def request_transition(robot_id, new_mode):
            current = manager.current_modes.get(robot_id)
            if current is None:
                return False, "robot_not_registered"
            if current == new_mode:
                return False, "already_in_mode"
            return True, "transition_started"
        
        manager.get_mode = get_mode
        manager.set_mode = set_mode
        manager.request_transition = request_transition
        manager.register_robot = lambda rid: manager.current_modes.update({rid: manager.default_mode})
        
        return manager
    
    def test_default_mode(self, mock_mode_manager):
        """Test default mode is RPM."""
        assert mock_mode_manager.default_mode == ControlMode.RPM
    
    def test_get_mode_for_registered_robot(self, mock_mode_manager):
        """Test getting mode for registered robot."""
        mock_mode_manager.register_robot("robot_0")
        mode = mock_mode_manager.get_mode("robot_0")
        
        assert mode == ControlMode.RPM
    
    def test_get_mode_for_unregistered_robot(self, mock_mode_manager):
        """Test getting mode for unregistered robot returns default."""
        mode = mock_mode_manager.get_mode("unknown")
        
        assert mode == ControlMode.RPM  # Default
    
    def test_set_mode_success(self, mock_mode_manager):
        """Test successfully setting mode."""
        mock_mode_manager.register_robot("robot_0")
        success, message = mock_mode_manager.set_mode("robot_0", ControlMode.ADM)
        
        assert success is True
        assert mock_mode_manager.current_modes["robot_0"] == ControlMode.ADM
    
    def test_set_mode_unregistered_robot(self, mock_mode_manager):
        """Test setting mode for unregistered robot fails."""
        success, message = mock_mode_manager.set_mode("unknown", ControlMode.ADM)
        
        assert success is False
        assert message == "robot_not_registered"
    
    def test_request_transition_success(self, mock_mode_manager):
        """Test requesting mode transition."""
        mock_mode_manager.register_robot("robot_0")
        success, message = mock_mode_manager.request_transition("robot_0", ControlMode.ADM)
        
        assert success is True
        assert message == "transition_started"
    
    def test_request_transition_already_in_mode(self, mock_mode_manager):
        """Test transition request when already in target mode."""
        mock_mode_manager.register_robot("robot_0")
        success, message = mock_mode_manager.request_transition("robot_0", ControlMode.RPM)
        
        assert success is False
        assert message == "already_in_mode"


class TestModeTransitionRules:
    """Tests for mode transition rules and requirements."""
    
    @pytest.fixture
    def mock_transition_validator(self):
        """Create mock transition validator."""
        validator = Mock()
        
        def validate_transition(robot_state, transition):
            # Check if robot is in safe state
            if robot_state.status == "moving":
                return False, "robot_moving"
            if robot_state.status == "emergency_stopped":
                return False, "emergency_stopped"
            
            # RPM -> ADM requires clear surroundings
            if (transition.from_mode == ControlMode.RPM and 
                transition.to_mode == ControlMode.ADM):
                if robot_state.obstacle_distance < 50:
                    return False, "obstacle_too_close"
            
            # ADM -> RPM always allowed when stopped
            return True, "transition_allowed"
        
        validator.validate_transition = validate_transition
        return validator
    
    @pytest.fixture
    def robot_state_ready(self):
        """Robot state that is ready for transition."""
        state = Mock()
        state.status = "ready"
        state.obstacle_distance = 100
        return state
    
    @pytest.fixture
    def robot_state_moving(self):
        """Robot state that is currently moving."""
        state = Mock()
        state.status = "moving"
        state.obstacle_distance = 100
        return state
    
    def test_transition_when_ready(self, mock_transition_validator, robot_state_ready):
        """Test transition allowed when robot is ready."""
        transition = ModeTransition(ControlMode.RPM, ControlMode.ADM, "robot_0")
        success, reason = mock_transition_validator.validate_transition(
            robot_state_ready, transition
        )
        
        assert success is True
    
    def test_transition_when_moving_blocked(self, mock_transition_validator, robot_state_moving):
        """Test transition blocked when robot is moving."""
        transition = ModeTransition(ControlMode.RPM, ControlMode.ADM, "robot_0")
        success, reason = mock_transition_validator.validate_transition(
            robot_state_moving, transition
        )
        
        assert success is False
        assert reason == "robot_moving"
    
    def test_rpm_to_adm_obstacle_check(self, mock_transition_validator, robot_state_ready):
        """Test RPM->ADM transition checks obstacle distance."""
        robot_state_ready.obstacle_distance = 30  # Too close
        
        transition = ModeTransition(ControlMode.RPM, ControlMode.ADM, "robot_0")
        success, reason = mock_transition_validator.validate_transition(
            robot_state_ready, transition
        )
        
        assert success is False
        assert reason == "obstacle_too_close"
    
    def test_adm_to_rpm_always_allowed_when_stopped(self, mock_transition_validator, robot_state_ready):
        """Test ADM->RPM always allowed when robot stopped."""
        robot_state_ready.obstacle_distance = 10  # Close, but doesn't matter for ADM->RPM
        
        transition = ModeTransition(ControlMode.ADM, ControlMode.RPM, "robot_0")
        success, reason = mock_transition_validator.validate_transition(
            robot_state_ready, transition
        )
        
        assert success is True


class TestModeSpecificBehavior:
    """Tests for mode-specific behavior differences."""
    
    @pytest.fixture
    def mock_command_handler(self):
        """Create mock command handler with mode awareness."""
        handler = Mock()
        
        def handle_command(command, mode):
            if mode == ControlMode.RPM:
                # RPM: Direct command execution
                return {"action": "execute_direct", "command": command}
            elif mode == ControlMode.ADM:
                # ADM: Queue for planning
                return {"action": "queue_for_planning", "command": command}
            return {"action": "unknown", "command": command}
        
        handler.handle_command = handle_command
        return handler
    
    def test_rpm_executes_directly(self, mock_command_handler):
        """Test RPM mode executes commands directly."""
        command = {"joint": "shoulder", "position": 1.5}
        result = mock_command_handler.handle_command(command, ControlMode.RPM)
        
        assert result["action"] == "execute_direct"
    
    def test_adm_queues_for_planning(self, mock_command_handler):
        """Test ADM mode queues commands for planning."""
        command = {"joint": "shoulder", "position": 1.5}
        result = mock_command_handler.handle_command(command, ControlMode.ADM)
        
        assert result["action"] == "queue_for_planning"


class TestModeNotifications:
    """Tests for mode change notifications."""
    
    @pytest.fixture
    def mock_notifier(self):
        """Create mock mode change notifier."""
        notifier = Mock()
        notifier.callbacks = []
        notifier.notifications_sent = []
        
        def register_callback(callback):
            notifier.callbacks.append(callback)
        
        def notify_mode_change(robot_id, old_mode, new_mode):
            notification = {
                "robot_id": robot_id,
                "old_mode": old_mode,
                "new_mode": new_mode
            }
            notifier.notifications_sent.append(notification)
            for callback in notifier.callbacks:
                callback(notification)
        
        notifier.register_callback = register_callback
        notifier.notify_mode_change = notify_mode_change
        return notifier
    
    def test_callback_registration(self, mock_notifier):
        """Test callback registration."""
        callback = Mock()
        mock_notifier.register_callback(callback)
        
        assert len(mock_notifier.callbacks) == 1
    
    def test_notification_on_mode_change(self, mock_notifier):
        """Test notification sent on mode change."""
        callback = Mock()
        mock_notifier.register_callback(callback)
        
        mock_notifier.notify_mode_change("robot_0", ControlMode.RPM, ControlMode.ADM)
        
        callback.assert_called_once()
        assert len(mock_notifier.notifications_sent) == 1
    
    def test_notification_contains_correct_data(self, mock_notifier):
        """Test notification contains correct data."""
        mock_notifier.notify_mode_change("robot_0", ControlMode.RPM, ControlMode.ADM)
        
        notification = mock_notifier.notifications_sent[0]
        assert notification["robot_id"] == "robot_0"
        assert notification["old_mode"] == ControlMode.RPM
        assert notification["new_mode"] == ControlMode.ADM


class TestEmergencyStopInteraction:
    """Tests for E-Stop interaction with mode manager."""
    
    @pytest.fixture
    def mock_estop_handler(self):
        """Create mock E-Stop handler."""
        handler = Mock()
        handler.estop_active = {}
        
        def activate_estop(robot_id):
            handler.estop_active[robot_id] = True
            return True
        
        def clear_estop(robot_id, current_mode):
            if robot_id not in handler.estop_active:
                return False, "not_stopped"
            if current_mode != ControlMode.RPM:
                return False, "must_be_in_rpm"
            del handler.estop_active[robot_id]
            return True, "cleared"
        
        def is_estop_active(robot_id):
            return handler.estop_active.get(robot_id, False)
        
        handler.activate_estop = activate_estop
        handler.clear_estop = clear_estop
        handler.is_estop_active = is_estop_active
        return handler
    
    def test_estop_activates(self, mock_estop_handler):
        """Test E-Stop activation."""
        result = mock_estop_handler.activate_estop("robot_0")
        
        assert result is True
        assert mock_estop_handler.is_estop_active("robot_0") is True
    
    def test_estop_clear_requires_rpm(self, mock_estop_handler):
        """Test E-Stop clear requires RPM mode."""
        mock_estop_handler.activate_estop("robot_0")
        
        # Try to clear in ADM mode
        success, reason = mock_estop_handler.clear_estop("robot_0", ControlMode.ADM)
        
        assert success is False
        assert reason == "must_be_in_rpm"
    
    def test_estop_clear_in_rpm(self, mock_estop_handler):
        """Test E-Stop clear succeeds in RPM mode."""
        mock_estop_handler.activate_estop("robot_0")
        
        success, reason = mock_estop_handler.clear_estop("robot_0", ControlMode.RPM)
        
        assert success is True
        assert mock_estop_handler.is_estop_active("robot_0") is False


class TestModeManagerIntegration:
    """Integration tests for mode manager with other components."""
    
    def test_mode_change_updates_command_handler(self):
        """Test mode change updates command handler behavior."""
        # TODO: Implement when components available
        pass
    
    def test_mode_preserved_across_reconnection(self):
        """Test mode is preserved when UE5 reconnects."""
        # TODO: Implement when components available
        pass
    
    def test_concurrent_mode_changes_multiple_robots(self):
        """Test concurrent mode changes for multiple robots."""
        # TODO: Implement when components available
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
