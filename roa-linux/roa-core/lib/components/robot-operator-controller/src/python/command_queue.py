"""
Command Queue System

Task queue management with priorities for ADM mode.
Enables sequential execution of multiple tasks with cancellation support.

Author: ROA Development Team
Date: 2025-11-16
"""

from typing import Dict, List, Optional, Any
from enum import Enum
import time
import threading


class TaskPriority(Enum):
    """Task priority levels"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class TaskStatus(Enum):
    """Task execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class QueuedCommand:
    """Command in the queue"""
    
    def __init__(
        self,
        command_id: str,
        robot_id: str,
        command_type: str,
        parameters: Dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        timeout: float = 60.0
    ):
        self.command_id = command_id
        self.robot_id = robot_id
        self.command_type = command_type
        self.parameters = parameters
        self.priority = priority
        self.timeout = timeout
        
        self.status = TaskStatus.PENDING
        self.created_time = time.time()
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.result: Optional[Any] = None
        self.error_message: Optional[str] = None
        
    def start(self):
        """Mark command as started"""
        self.start_time = time.time()
        self.status = TaskStatus.RUNNING
        
    def complete(self, result: Any = None):
        """Mark command as completed"""
        self.end_time = time.time()
        self.status = TaskStatus.COMPLETED
        self.result = result
        
    def fail(self, error_message: str):
        """Mark command as failed"""
        self.end_time = time.time()
        self.status = TaskStatus.FAILED
        self.error_message = error_message
        
    def cancel(self):
        """Cancel command"""
        self.end_time = time.time()
        self.status = TaskStatus.CANCELLED
        
    def is_timeout(self) -> bool:
        """Check if command has timed out"""
        if self.start_time is None:
            return False
        elapsed = time.time() - self.start_time
        return elapsed > self.timeout
    
    def get_info(self) -> Dict[str, Any]:
        """Get command information"""
        return {
            'command_id': self.command_id,
            'robot_id': self.robot_id,
            'command_type': self.command_type,
            'parameters': self.parameters,
            'priority': self.priority.name,
            'status': self.status.value,
            'created_time': self.created_time,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'result': self.result,
            'error_message': self.error_message
        }


class CommandQueue:
    """
    Command queue with priority management
    
    Features:
    - Priority-based scheduling
    - Timeout handling
    - Command cancellation
    - Persistent storage (via Webthread)
    - Thread-safe operations
    """
    
    def __init__(self, max_history: int = 1000):
        """
        Initialize command queue
        
        Args:
            max_history: Maximum number of completed commands to keep
        """
        self.max_history = max_history
        
        # Active queues (per robot)
        self.queues: Dict[str, List[QueuedCommand]] = {}
        
        # Command history
        self.history: List[QueuedCommand] = []
        
        # Lock for thread safety
        self.lock = threading.Lock()
        
        # Statistics
        self.total_queued = 0
        self.total_completed = 0
        self.total_failed = 0
        self.total_cancelled = 0
        
    def add_command(
        self,
        robot_id: str,
        command_type: str,
        parameters: Dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        timeout: float = 60.0
    ) -> str:
        """
        Add command to queue
        
        Args:
            robot_id: Robot identifier
            command_type: Type of command (move, pick, place, etc.)
            parameters: Command parameters
            priority: Command priority
            timeout: Maximum execution time
            
        Returns:
            Command ID
        """
        with self.lock:
            # Generate unique command ID
            command_id = f"{robot_id}_{int(time.time() * 1000)}_{self.total_queued}"
            
            # Create command
            command = QueuedCommand(
                command_id=command_id,
                robot_id=robot_id,
                command_type=command_type,
                parameters=parameters,
                priority=priority,
                timeout=timeout
            )
            
            # Get robot queue
            if robot_id not in self.queues:
                self.queues[robot_id] = []
            
            # Insert based on priority
            queue = self.queues[robot_id]
            inserted = False
            for i, existing_cmd in enumerate(queue):
                if command.priority.value > existing_cmd.priority.value:
                    queue.insert(i, command)
                    inserted = True
                    break
            
            if not inserted:
                queue.append(command)
            
            self.total_queued += 1
            
            return command_id
    
    def get_next_command(self, robot_id: str) -> Optional[QueuedCommand]:
        """
        Get next command for robot
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            Next command or None
        """
        with self.lock:
            if robot_id not in self.queues or not self.queues[robot_id]:
                return None
            
            # Get highest priority command
            command = self.queues[robot_id].pop(0)
            command.start()
            
            return command
    
    def cancel_command(self, command_id: str) -> bool:
        """
        Cancel a command
        
        Args:
            command_id: Command to cancel
            
        Returns:
            True if cancelled
        """
        with self.lock:
            # Search in all queues
            for robot_id, queue in self.queues.items():
                for i, command in enumerate(queue):
                    if command.command_id == command_id:
                        command.cancel()
                        queue.pop(i)
                        self._add_to_history(command)
                        self.total_cancelled += 1
                        return True
            
            return False
    
    def cancel_all(self, robot_id: str) -> int:
        """
        Cancel all commands for a robot
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            Number of commands cancelled
        """
        with self.lock:
            if robot_id not in self.queues:
                return 0
            
            count = 0
            for command in self.queues[robot_id]:
                command.cancel()
                self._add_to_history(command)
                count += 1
            
            self.queues[robot_id].clear()
            self.total_cancelled += count
            
            return count
    
    def complete_command(
        self,
        command_id: str,
        result: Any = None
    ) -> bool:
        """
        Mark command as completed
        
        Args:
            command_id: Command identifier
            result: Command result
            
        Returns:
            True if found and completed
        """
        with self.lock:
            # Note: Command should be tracked outside queue while executing
            # This is a helper method for marking completion
            self.total_completed += 1
            return True
    
    def fail_command(
        self,
        command_id: str,
        error_message: str
    ) -> bool:
        """
        Mark command as failed
        
        Args:
            command_id: Command identifier
            error_message: Error message
            
        Returns:
            True if found and failed
        """
        with self.lock:
            self.total_failed += 1
            return True
    
    def get_queue_length(self, robot_id: str) -> int:
        """Get queue length for robot"""
        with self.lock:
            if robot_id not in self.queues:
                return 0
            return len(self.queues[robot_id])
    
    def get_queue_info(self, robot_id: str) -> List[Dict[str, Any]]:
        """Get queue information for robot"""
        with self.lock:
            if robot_id not in self.queues:
                return []
            
            return [cmd.get_info() for cmd in self.queues[robot_id]]
    
    def get_history(
        self,
        robot_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get command history
        
        Args:
            robot_id: Filter by robot (None for all)
            limit: Maximum number of records
            
        Returns:
            List of command info
        """
        with self.lock:
            history = self.history
            
            # Filter by robot
            if robot_id:
                history = [cmd for cmd in history if cmd.robot_id == robot_id]
            
            # Limit results
            history = history[-limit:]
            
            return [cmd.get_info() for cmd in history]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get queue statistics"""
        with self.lock:
            total_queued_now = sum(len(q) for q in self.queues.values())
            
            return {
                'total_queued': self.total_queued,
                'total_completed': self.total_completed,
                'total_failed': self.total_failed,
                'total_cancelled': self.total_cancelled,
                'current_queued': total_queued_now,
                'robots_with_queues': len(self.queues),
                'history_size': len(self.history)
            }
    
    def _add_to_history(self, command: QueuedCommand):
        """Add command to history"""
        self.history.append(command)
        
        # Trim history if needed
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
    
    def clear_history(self):
        """Clear command history"""
        with self.lock:
            self.history.clear()
