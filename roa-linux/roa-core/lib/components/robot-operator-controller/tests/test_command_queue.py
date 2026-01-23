"""
Test suite for ROC command queue system
Tests command queueing, prioritization, and execution
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

from command_queue import CommandQueue


class TestCommandQueue:
    """Command queue tests (22 tests) - Part of integration tests count"""
    
    def test_queue_initialization(self):
        """Test 1: Queue initializes correctly"""
        queue = CommandQueue()
        assert queue is not None
        assert queue.get_queue_length() == 0
    
    def test_add_command(self):
        """Test 2: Commands can be added to queue"""
        queue = CommandQueue()
        command = {'type': 'position', 'robot_id': 'robot_001', 'joint_values': [0.5] * 6}
        
        result = queue.add_command(command)
        assert result == True
        assert queue.get_queue_length() == 1
    
    def test_priority_ordering(self):
        """Test 3: Commands are ordered by priority"""
        queue = CommandQueue()
        
        commands = [
            {'type': 'position', 'priority': 1, 'id': 'cmd1'},
            {'type': 'position', 'priority': 3, 'id': 'cmd2'},
            {'type': 'position', 'priority': 0, 'id': 'cmd3'},
            {'type': 'position', 'priority': 2, 'id': 'cmd4'}
        ]
        
        for cmd in commands:
            queue.add_command(cmd)
        
        # Should return highest priority first
        first = queue.get_next_command()
        assert first['id'] == 'cmd2'  # Priority 3
    
    def test_fifo_within_same_priority(self):
        """Test 4: FIFO ordering within same priority"""
        queue = CommandQueue()
        
        commands = [
            {'type': 'position', 'priority': 1, 'id': 'first'},
            {'type': 'position', 'priority': 1, 'id': 'second'},
            {'type': 'position', 'priority': 1, 'id': 'third'}
        ]
        
        for cmd in commands:
            queue.add_command(cmd)
        
        assert queue.get_next_command()['id'] == 'first'
        assert queue.get_next_command()['id'] == 'second'
        assert queue.get_next_command()['id'] == 'third'
    
    def test_clear_queue(self):
        """Test 5: Queue can be cleared"""
        queue = CommandQueue()
        
        for i in range(10):
            queue.add_command({'type': 'position', 'id': i})
        
        assert queue.get_queue_length() == 10
        
        queue.clear()
        assert queue.get_queue_length() == 0
    
    def test_remove_specific_command(self):
        """Test 6: Specific commands can be removed"""
        queue = CommandQueue()
        
        commands = [
            {'type': 'position', 'id': 'cmd1'},
            {'type': 'position', 'id': 'cmd2'},
            {'type': 'position', 'id': 'cmd3'}
        ]
        
        for cmd in commands:
            queue.add_command(cmd)
        
        result = queue.remove_command('cmd2')
        assert result == True
        assert queue.get_queue_length() == 2
    
    def test_queue_pause_resume(self):
        """Test 7: Queue can be paused and resumed"""
        queue = CommandQueue()
        
        queue.add_command({'type': 'position'})
        
        queue.pause()
        assert queue.is_paused() == True
        
        # Should not return commands when paused
        cmd = queue.get_next_command()
        assert cmd is None
        
        queue.resume()
        assert queue.is_paused() == False
        
        # Should return commands when resumed
        cmd = queue.get_next_command()
        assert cmd is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
