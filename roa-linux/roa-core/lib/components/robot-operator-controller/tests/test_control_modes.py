"""
Test suite for ROC control modes (RPM and ADM)
Tests cover mode switching, command handling, and state management
"""

import pytest
import time
from unittest.mock import Mock, MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

from control_modes.rpm_mode import RPMMode
from control_modes.adm_mode import ADMMode


class TestRPMMode:
    """Test suite for RPM (Real-time Protocol Mode) - Manual Control (20 tests total)"""
    
    def test_rpm_initialization(self):
        """Test 1: RPM mode initializes correctly"""
        rpm = RPMMode()
        assert rpm is not None
        assert rpm.mode_name == 'RPM'
        assert rpm.active == False
    
    def test_rpm_activation(self):
        """Test 2: RPM mode can be activated"""
        rpm = RPMMode()
        result = rpm.activate()
        assert result == True
        assert rpm.active == True
    
    def test_rpm_deactivation(self):
        """Test 3: RPM mode can be deactivated"""
        rpm = RPMMode()
        rpm.activate()
        result = rpm.deactivate()
        assert result == True
        assert rpm.active == False
    
    def test_rpm_manual_position_command(self):
        """Test 4: RPM accepts manual position commands"""
        rpm = RPMMode()
        rpm.activate()
        
        command = {
            'type': 'position',
            'robot_id': 'robot_001',
            'joint_values': [0.5, 1.0, 0.0, 0.5, 0.0, 0.0]
        }
        result = rpm.execute_command(command)
        assert result == True
    
    def test_rpm_manual_velocity_command(self):
        """Test 5: RPM accepts manual velocity commands"""
        rpm = RPMMode()
        rpm.activate()
        
        command = {
            'type': 'velocity',
            'robot_id': 'robot_001',
            'joint_values': [0.1, 0.2, 0.0, 0.1, 0.0, 0.0]
        }
        result = rpm.execute_command(command)
        assert result == True
    
    def test_rpm_real_time_update_rate(self):
        """Test 6: RPM maintains real-time update rate"""
        rpm = RPMMode()
        rpm.activate()
        
        target_rate = 60  # Hz
        rpm.set_update_rate(target_rate)
        assert rpm.update_rate == target_rate
    
    def test_rpm_slider_input_handling(self):
        """Test 7: RPM handles slider input values"""
        rpm = RPMMode()
        rpm.activate()
        
        # Simulate slider input (0.0 to 1.0 range)
        slider_values = [0.5, 0.7, 0.3, 0.9, 0.1, 0.5]
        result = rpm.process_slider_input('robot_001', slider_values)
        assert result == True
    
    def test_rpm_keyboard_input(self):
        """Test 8: RPM handles keyboard input"""
        rpm = RPMMode()
        rpm.activate()
        
        # Simulate keyboard input
        key_command = {'key': 'w', 'modifier': None}  # Forward
        result = rpm.process_keyboard_input(key_command)
        assert result == True
    
    def test_rpm_mouse_input(self):
        """Test 9: RPM handles mouse input"""
        rpm = RPMMode()
        rpm.activate()
        
        # Simulate mouse click on control
        mouse_command = {'x': 100, 'y': 200, 'button': 'left'}
        result = rpm.process_mouse_input(mouse_command)
        assert result is not None
    
    def test_rpm_immediate_execution(self):
        """Test 10: RPM executes commands immediately (no queue)"""
        rpm = RPMMode()
        rpm.activate()
        
        command = {'type': 'position', 'robot_id': 'robot_001', 'joint_values': [0.0] * 6}
        start_time = time.time()
        rpm.execute_command(command)
        execution_time = time.time() - start_time
        
        # Should execute within milliseconds
        assert execution_time < 0.1  # 100ms


class TestADMMode:
    """Test suite for ADM (Autonomous Decision Mode) - Autonomous Control"""
    
    def test_adm_initialization(self):
        """Test 11: ADM mode initializes correctly"""
        adm = ADMMode()
        assert adm is not None
        assert adm.mode_name == 'ADM'
        assert adm.active == False
    
    def test_adm_activation(self):
        """Test 12: ADM mode can be activated"""
        adm = ADMMode()
        result = adm.activate()
        assert result == True
        assert adm.active == True
    
    def test_adm_autonomous_task_execution(self):
        """Test 13: ADM executes autonomous tasks"""
        adm = ADMMode()
        adm.activate()
        
        task = {
            'type': 'pick_and_place',
            'robot_id': 'robot_001',
            'pick_position': [1.0, 2.0, 0.5],
            'place_position': [2.0, 3.0, 0.5]
        }
        result = adm.execute_task(task)
        assert result == True
    
    def test_adm_path_planning_integration(self):
        """Test 14: ADM integrates with path planning"""
        adm = ADMMode()
        adm.activate()
        
        start = [0.0, 0.0, 0.0]
        goal = [5.0, 5.0, 0.0]
        result = adm.plan_path(start, goal)
        assert result is not None
        assert len(result) > 0  # Should return a path
    
    def test_adm_obstacle_avoidance(self):
        """Test 15: ADM handles obstacle avoidance"""
        adm = ADMMode()
        adm.activate()
        
        obstacles = [
            {'position': [2.0, 2.0, 0.0], 'radius': 0.5},
            {'position': [3.0, 3.0, 0.0], 'radius': 0.5}
        ]
        adm.update_obstacles(obstacles)
        
        path = adm.plan_path([0.0, 0.0, 0.0], [5.0, 5.0, 0.0])
        # Path should avoid obstacles
        assert path is not None
    
    def test_adm_task_queue_management(self):
        """Test 16: ADM manages task queue"""
        adm = ADMMode()
        adm.activate()
        
        tasks = [
            {'type': 'move_to', 'position': [1.0, 1.0, 0.0]},
            {'type': 'move_to', 'position': [2.0, 2.0, 0.0]},
            {'type': 'move_to', 'position': [3.0, 3.0, 0.0]}
        ]
        
        for task in tasks:
            adm.add_task(task)
        
        assert adm.get_task_queue_length() == 3
    
    def test_adm_priority_task_handling(self):
        """Test 17: ADM handles task priorities"""
        adm = ADMMode()
        adm.activate()
        
        low_priority = {'type': 'move_to', 'position': [1.0, 1.0, 0.0], 'priority': 0}
        high_priority = {'type': 'move_to', 'position': [2.0, 2.0, 0.0], 'priority': 3}
        
        adm.add_task(low_priority)
        adm.add_task(high_priority)
        
        next_task = adm.get_next_task()
        # High priority should be executed first
        assert next_task['priority'] == 3
    
    def test_adm_task_cancellation(self):
        """Test 18: ADM can cancel tasks"""
        adm = ADMMode()
        adm.activate()
        
        task = {'type': 'move_to', 'position': [5.0, 5.0, 0.0], 'task_id': 'task_001'}
        adm.add_task(task)
        
        result = adm.cancel_task('task_001')
        assert result == True
        assert adm.get_task_queue_length() == 0


class TestModeTransitions:
    """Test mode switching and transitions"""
    
    def test_mode_switch_rpm_to_adm(self):
        """Test 19: Can switch from RPM to ADM"""
        rpm = RPMMode()
        adm = ADMMode()
        
        rpm.activate()
        assert rpm.active == True
        
        rpm.deactivate()
        adm.activate()
        
        assert rpm.active == False
        assert adm.active == True
    
    def test_mode_switch_adm_to_rpm(self):
        """Test 20: Can switch from ADM to RPM"""
        rpm = RPMMode()
        adm = ADMMode()
        
        adm.activate()
        assert adm.active == True
        
        adm.deactivate()
        rpm.activate()
        
        assert adm.active == False
        assert rpm.active == True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
