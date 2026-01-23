"""
ADM Mode - Auto Driven Mode Implementation

Strategic autonomous control mode with RTS-style high-level commands.
Provides path planning, task execution, and autonomous navigation.

Author: ROA Development Team
Date: 2025-11-16
"""

import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class TaskPriority(Enum):
    """Task priority levels"""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class TaskStatus(Enum):
    """Task execution status"""

    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task:
    """High-level task for ADM mode"""

    def __init__(
        self,
        task_id: str,
        task_type: str,
        target_position: Dict[str, float],
        priority: TaskPriority = TaskPriority.NORMAL,
        timeout: float = 60.0,
    ):
        self.task_id = task_id
        self.task_type = task_type  # move, pick, place, assemble, etc.
        self.target_position = target_position
        self.priority = priority
        self.timeout = timeout
        self.status = TaskStatus.PENDING
        self.start_time = None
        self.path = []
        self.error_message = None

    def start(self):
        """Mark task as started"""
        self.start_time = time.time()

    def is_timeout(self) -> bool:
        """Check if task has timed out"""
        if self.start_time is None:
            return False
        return (time.time() - self.start_time) > self.timeout


class ADMMode:
    """
    Auto Driven Mode - Strategic autonomous control

    Features:
    - High-level task commands
    - Autonomous path planning
    - Multi-step task execution
    - Automatic re-planning on obstacles
    - Multi-robot coordination
    """

    def __init__(self, path_planner=None):
        """
        Initialize ADM mode

        Args:
            path_planner: Path planning module (A* or RRT)
        """
        self.active = False
        self.robot_id = None
        self.path_planner = path_planner

        # Task queue
        self.task_queue: List[Task] = []
        self.current_task: Optional[Task] = None

        # Execution state
        self.current_path = []
        self.current_waypoint_index = 0

        # Configuration
        self.waypoint_tolerance = 0.01  # meters
        self.replanning_rate = 2.0  # Hz
        self.last_replan_time = 0

        # Statistics
        self.tasks_completed = 0
        self.tasks_failed = 0

    def activate(self, robot_id: str):
        """
        Activate ADM mode for a robot

        Args:
            robot_id: Robot to control
        """
        self.active = True
        self.robot_id = robot_id

    def deactivate(self):
        """Deactivate ADM mode"""
        self.active = False
        self.robot_id = None

        # Cancel current task
        if self.current_task:
            self.current_task.status = TaskStatus.CANCELLED
            self.current_task = None

        # Clear queue
        for task in self.task_queue:
            task.status = TaskStatus.CANCELLED
        self.task_queue.clear()

    def add_task(
        self,
        task_type: str,
        target_position: Dict[str, float],
        priority: TaskPriority = TaskPriority.NORMAL,
        timeout: float = 60.0,
    ) -> str:
        """
        Add a task to the queue

        Args:
            task_type: Type of task (move, pick, place, etc.)
            target_position: Target position {x, y, z}
            priority: Task priority
            timeout: Max execution time

        Returns:
            Task ID
        """
        task_id = f"{self.robot_id}_task_{int(time.time() * 1000)}"
        task = Task(task_id, task_type, target_position, priority, timeout)

        # Insert based on priority
        inserted = False
        for i, existing_task in enumerate(self.task_queue):
            if task.priority.value > existing_task.priority.value:
                self.task_queue.insert(i, task)
                inserted = True
                break

        if not inserted:
            self.task_queue.append(task)

        return task_id

    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a task

        Args:
            task_id: Task to cancel

        Returns:
            True if cancelled
        """
        # Check if it's the current task
        if self.current_task and self.current_task.task_id == task_id:
            self.current_task.status = TaskStatus.CANCELLED
            self.current_task = None
            return True

        # Check queue
        for task in self.task_queue:
            if task.task_id == task_id:
                task.status = TaskStatus.CANCELLED
                self.task_queue.remove(task)
                return True

        return False

    def get_next_task(self) -> Optional[Task]:
        """Get next task from queue"""
        if not self.task_queue:
            return None
        return self.task_queue.pop(0)

    def execute_task(
        self, current_position: Dict[str, float], obstacles: List[Dict]
    ) -> Optional[Dict[str, Any]]:
        """
        Execute current task

        Args:
            current_position: Current robot position
            obstacles: List of obstacles

        Returns:
            Control command or None
        """
        if not self.active:
            return None

        # Start new task if none active
        if self.current_task is None:
            self.current_task = self.get_next_task()
            if self.current_task is None:
                return None

            self.current_task.start()
            self.current_task.status = TaskStatus.PLANNING

        # Check timeout
        if self.current_task.is_timeout():
            self.current_task.status = TaskStatus.FAILED
            self.current_task.error_message = "Task timeout"
            self.tasks_failed += 1
            self.current_task = None
            return None

        # Plan path if needed
        if self.current_task.status == TaskStatus.PLANNING:
            if self.path_planner:
                path = self.path_planner.plan(
                    current_position, self.current_task.target_position, obstacles
                )

                if path:
                    self.current_path = path
                    self.current_waypoint_index = 0
                    self.current_task.status = TaskStatus.EXECUTING
                else:
                    self.current_task.status = TaskStatus.FAILED
                    self.current_task.error_message = "No path found"
                    self.tasks_failed += 1
                    self.current_task = None
                    return None

        # Execute path
        if self.current_task.status == TaskStatus.EXECUTING:
            # Check if we need to replan
            current_time = time.time()
            if current_time - self.last_replan_time > 1.0 / self.replanning_rate:
                self.last_replan_time = current_time

                # Re-plan if obstacles changed
                if self.path_planner and obstacles:
                    new_path = self.path_planner.plan(
                        current_position, self.current_task.target_position, obstacles
                    )
                    if new_path:
                        self.current_path = new_path
                        self.current_waypoint_index = 0

            # Get current waypoint
            if self.current_waypoint_index < len(self.current_path):
                waypoint = self.current_path[self.current_waypoint_index]

                # Check if reached waypoint
                distance = self._calculate_distance(current_position, waypoint)
                if distance < self.waypoint_tolerance:
                    self.current_waypoint_index += 1

                    # Check if reached final target
                    if self.current_waypoint_index >= len(self.current_path):
                        self.current_task.status = TaskStatus.COMPLETED
                        self.tasks_completed += 1
                        self.current_task = None
                        return None

                # Generate movement command toward waypoint
                return self._generate_movement_command(current_position, waypoint)

        return None

    def _calculate_distance(self, pos1: Dict[str, float], pos2: Dict[str, float]) -> float:
        """Calculate distance between two positions"""
        dx = pos2["x"] - pos1["x"]
        dy = pos2["y"] - pos1["y"]
        dz = pos2.get("z", 0.0) - pos1.get("z", 0.0)
        return (dx**2 + dy**2 + dz**2) ** 0.5

    def _generate_movement_command(
        self, current_pos: Dict[str, float], target_pos: Dict[str, float]
    ) -> Dict[str, Any]:
        """Generate movement command toward target"""
        # Calculate direction vector
        dx = target_pos["x"] - current_pos["x"]
        dy = target_pos["y"] - current_pos["y"]
        dz = target_pos.get("z", 0.0) - current_pos.get("z", 0.0)

        # Normalize
        distance = (dx**2 + dy**2 + dz**2) ** 0.5
        if distance > 0:
            dx /= distance
            dy /= distance
            dz /= distance

        return {
            "robot_id": self.robot_id,
            "type": "move",
            "direction": {"x": dx, "y": dy, "z": dz},
            "target": target_pos,
            "task_id": self.current_task.task_id if self.current_task else None,
        }

    def get_status(self) -> Dict[str, Any]:
        """Get ADM mode status"""
        return {
            "active": self.active,
            "robot_id": self.robot_id,
            "current_task": (
                {
                    "task_id": self.current_task.task_id,
                    "type": self.current_task.task_type,
                    "status": self.current_task.status.value,
                    "progress": (
                        self.current_waypoint_index / len(self.current_path)
                        if self.current_path
                        else 0
                    ),
                }
                if self.current_task
                else None
            ),
            "queue_length": len(self.task_queue),
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
        }

    def emergency_stop(self):
        """Emergency stop - cancel all tasks"""
        if self.current_task:
            self.current_task.status = TaskStatus.CANCELLED
            self.current_task = None

        for task in self.task_queue:
            task.status = TaskStatus.CANCELLED
        self.task_queue.clear()
