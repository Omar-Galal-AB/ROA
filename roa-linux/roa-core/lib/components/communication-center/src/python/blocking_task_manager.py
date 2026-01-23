"""
Blocking Task Manager

Manages navigation and coordination tasks with blocking semantics.
Based on Karelics Task Manager pattern - ensures only one navigation
task runs per robot at a time.

Key Features:
- Blocking task execution (waits for completion)
- Reentrant task support (can be interrupted by higher priority)
- Task queuing and prioritization
- Mission combining (sequence of tasks)
- Cancellation and preemption
"""

import rclpy
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.action import ActionClient

from geometry_msgs.msg import PoseStamped

from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import time
import threading
import uuid


class TaskType(Enum):
    """Types of tasks"""
    NAVIGATE_TO_POSE = "navigate_to_pose"
    FOLLOW_PATH = "follow_path"
    WAIT = "wait"
    DOCK = "dock"
    UNDOCK = "undock"
    CUSTOM = "custom"


class TaskState(Enum):
    """Task execution states"""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PREEMPTED = "preempted"


class TaskPriority(Enum):
    """Task priority levels"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4
    EMERGENCY = 5


@dataclass
class Task:
    """Single task definition"""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_type: TaskType = TaskType.CUSTOM
    robot_id: str = ""
    
    # Task parameters
    goal_pose: Optional[PoseStamped] = None
    path_waypoints: Optional[List[Tuple[float, float]]] = None
    wait_duration: float = 0.0
    custom_data: Dict[str, Any] = field(default_factory=dict)
    
    # Execution
    state: TaskState = TaskState.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    is_blocking: bool = True
    is_reentrant: bool = False  # Can be interrupted
    
    # Timing
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0
    
    # Callbacks
    on_complete: Optional[Callable] = None
    on_fail: Optional[Callable] = None
    on_progress: Optional[Callable] = None
    
    # Result
    success: bool = False
    error_message: str = ""
    
    def __hash__(self):
        return hash(self.task_id)


@dataclass
class Mission:
    """
    A mission is a sequence of tasks to be executed in order.
    """
    mission_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    robot_id: str = ""
    
    tasks: List[Task] = field(default_factory=list)
    current_task_index: int = 0
    
    state: TaskState = TaskState.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    
    # Options
    stop_on_failure: bool = True
    retry_on_failure: bool = False
    max_retries: int = 3
    
    created_at: float = field(default_factory=time.time)
    on_complete: Optional[Callable] = None
    on_fail: Optional[Callable] = None


class TaskQueue:
    """
    Priority queue for tasks.
    Higher priority tasks are executed first.
    """
    
    def __init__(self):
        self._queues: Dict[TaskPriority, deque] = {
            priority: deque() for priority in TaskPriority
        }
        self._lock = threading.Lock()
    
    def push(self, task: Task) -> None:
        """Add task to queue"""
        with self._lock:
            task.state = TaskState.QUEUED
            self._queues[task.priority].append(task)
    
    def pop(self) -> Optional[Task]:
        """Get highest priority task"""
        with self._lock:
            # Check priorities from highest to lowest
            for priority in reversed(TaskPriority):
                queue = self._queues[priority]
                if queue:
                    return queue.popleft()
            return None
    
    def peek(self) -> Optional[Task]:
        """Look at next task without removing"""
        with self._lock:
            for priority in reversed(TaskPriority):
                queue = self._queues[priority]
                if queue:
                    return queue[0]
            return None
    
    def remove(self, task_id: str) -> bool:
        """Remove specific task from queue"""
        with self._lock:
            for priority in TaskPriority:
                queue = self._queues[priority]
                for i, task in enumerate(queue):
                    if task.task_id == task_id:
                        del queue[i]
                        return True
            return False
    
    def clear(self) -> None:
        """Clear all tasks"""
        with self._lock:
            for queue in self._queues.values():
                queue.clear()
    
    def get_all(self) -> List[Task]:
        """Get all queued tasks"""
        with self._lock:
            result = []
            for priority in reversed(TaskPriority):
                result.extend(list(self._queues[priority]))
            return result
    
    def size(self) -> int:
        """Get total queue size"""
        with self._lock:
            return sum(len(q) for q in self._queues.values())


class BlockingTaskManager:
    """
    Manages task execution with blocking semantics.
    
    Key Features:
    - One active task per robot at a time
    - Task queuing with priorities
    - Blocking wait for completion
    - Mission (task sequence) support
    - Preemption for higher priority tasks
    """
    
    def __init__(self, robot_interface=None, logger=None):
        """
        Args:
            robot_interface: RobotInterface instance for navigation
            logger: ROS2 logger
        """
        self.robot_interface = robot_interface
        self.logger = logger
        
        # Per-robot task queues
        self.task_queues: Dict[str, TaskQueue] = {}
        
        # Active tasks (one per robot)
        self.active_tasks: Dict[str, Task] = {}
        
        # Active missions
        self.active_missions: Dict[str, Mission] = {}
        
        # Task history
        self.completed_tasks: Dict[str, List[Task]] = {}  # robot_id -> tasks
        
        # Execution events
        self._task_complete_events: Dict[str, threading.Event] = {}
        
        # Callbacks
        self.task_callbacks: List[Callable] = []  # (task, state)
        
        # Lock
        self._lock = threading.RLock()
        
        # Background executor
        self._running = True
        self._executor_thread = threading.Thread(target=self._executor_loop, daemon=True)
        self._executor_thread.start()
    
    def register_robot(self, robot_id: str) -> None:
        """Register a robot for task management"""
        with self._lock:
            if robot_id not in self.task_queues:
                self.task_queues[robot_id] = TaskQueue()
                self.completed_tasks[robot_id] = []
    
    def unregister_robot(self, robot_id: str) -> None:
        """Unregister a robot"""
        with self._lock:
            if robot_id in self.task_queues:
                self.task_queues[robot_id].clear()
                del self.task_queues[robot_id]
            if robot_id in self.active_tasks:
                del self.active_tasks[robot_id]
    
    def submit_task(self, task: Task, blocking: bool = True,
                    timeout: Optional[float] = None) -> Tuple[bool, str]:
        """
        Submit a task for execution.
        
        Args:
            task: Task to execute
            blocking: Wait for completion
            timeout: Timeout for blocking wait (None = infinite)
            
        Returns:
            (success, message) tuple
        """
        with self._lock:
            robot_id = task.robot_id
            
            if robot_id not in self.task_queues:
                self.register_robot(robot_id)
            
            # Check if should preempt current task
            if robot_id in self.active_tasks:
                active = self.active_tasks[robot_id]
                
                if task.priority.value > active.priority.value:
                    if active.is_reentrant:
                        # Preempt current task
                        self._preempt_task(robot_id, active)
                    else:
                        # Queue for later
                        self.task_queues[robot_id].push(task)
                        return True, f"Task {task.task_id} queued (active task not reentrant)"
                else:
                    # Lower/equal priority - queue it
                    self.task_queues[robot_id].push(task)
                    return True, f"Task {task.task_id} queued"
            
            # No active task - set this one as active
            self.active_tasks[robot_id] = task
            task.state = TaskState.RUNNING
            task.started_at = time.time()
        
        # Start execution
        self._start_task_execution(task)
        
        if blocking:
            # Wait for completion
            event_key = f"{robot_id}:{task.task_id}"
            self._task_complete_events[event_key] = threading.Event()
            
            completed = self._task_complete_events[event_key].wait(timeout=timeout)
            
            del self._task_complete_events[event_key]
            
            if not completed:
                return False, "Task timed out"
            
            return task.success, task.error_message or "Completed"
        
        return True, f"Task {task.task_id} started"
    
    def submit_navigate(self, robot_id: str, x: float, y: float, yaw: float = 0.0,
                        priority: TaskPriority = TaskPriority.NORMAL,
                        blocking: bool = True,
                        timeout: Optional[float] = None) -> Tuple[bool, str]:
        """
        Submit a navigate-to-pose task.
        
        Args:
            robot_id: Target robot
            x, y: Goal position
            yaw: Goal orientation
            priority: Task priority
            blocking: Wait for completion
            timeout: Timeout for blocking
            
        Returns:
            (success, message) tuple
        """
        task = Task(
            task_type=TaskType.NAVIGATE_TO_POSE,
            robot_id=robot_id,
            priority=priority,
            is_blocking=blocking,
            custom_data={'x': x, 'y': y, 'yaw': yaw}
        )
        
        return self.submit_task(task, blocking=blocking, timeout=timeout)
    
    def submit_follow_path(self, robot_id: str, 
                           waypoints: List[Tuple[float, float]],
                           priority: TaskPriority = TaskPriority.NORMAL,
                           blocking: bool = True,
                           timeout: Optional[float] = None) -> Tuple[bool, str]:
        """
        Submit a follow-path task.
        
        Args:
            robot_id: Target robot
            waypoints: List of (x, y) waypoints
            priority: Task priority
            blocking: Wait for completion
            timeout: Timeout for blocking
            
        Returns:
            (success, message) tuple
        """
        task = Task(
            task_type=TaskType.FOLLOW_PATH,
            robot_id=robot_id,
            path_waypoints=waypoints,
            priority=priority,
            is_blocking=blocking
        )
        
        return self.submit_task(task, blocking=blocking, timeout=timeout)
    
    def submit_wait(self, robot_id: str, duration: float,
                    blocking: bool = True) -> Tuple[bool, str]:
        """
        Submit a wait task.
        
        Args:
            robot_id: Target robot
            duration: Wait duration in seconds
            blocking: Wait for completion
            
        Returns:
            (success, message) tuple
        """
        task = Task(
            task_type=TaskType.WAIT,
            robot_id=robot_id,
            wait_duration=duration,
            priority=TaskPriority.LOW,
            is_blocking=blocking,
            is_reentrant=True  # Wait tasks can be interrupted
        )
        
        return self.submit_task(task, blocking=blocking, timeout=duration + 5.0)
    
    def submit_mission(self, mission: Mission, blocking: bool = True,
                       timeout: Optional[float] = None) -> Tuple[bool, str]:
        """
        Submit a mission (sequence of tasks).
        
        Args:
            mission: Mission to execute
            blocking: Wait for completion
            timeout: Total timeout
            
        Returns:
            (success, message) tuple
        """
        with self._lock:
            if not mission.tasks:
                return False, "Empty mission"
            
            robot_id = mission.robot_id
            self.active_missions[mission.mission_id] = mission
            mission.state = TaskState.RUNNING
        
        # Execute tasks sequentially
        success = True
        for i, task in enumerate(mission.tasks):
            mission.current_task_index = i
            task.robot_id = robot_id
            task.priority = mission.priority
            
            task_success, msg = self.submit_task(task, blocking=True, timeout=timeout)
            
            if not task_success:
                if mission.stop_on_failure:
                    success = False
                    mission.state = TaskState.FAILED
                    if mission.on_fail:
                        mission.on_fail(mission, msg)
                    break
        
        if success:
            mission.state = TaskState.COMPLETED
            if mission.on_complete:
                mission.on_complete(mission)
        
        del self.active_missions[mission.mission_id]
        
        return success, f"Mission {mission.mission_id} {'completed' if success else 'failed'}"
    
    def _start_task_execution(self, task: Task) -> None:
        """Start executing a task"""
        if self.logger:
            self.logger.info(f"Starting task {task.task_id} ({task.task_type.value}) for {task.robot_id}")
        
        if task.task_type == TaskType.NAVIGATE_TO_POSE:
            self._execute_navigate(task)
        elif task.task_type == TaskType.FOLLOW_PATH:
            self._execute_follow_path(task)
        elif task.task_type == TaskType.WAIT:
            self._execute_wait(task)
        else:
            self._execute_custom(task)
    
    def _execute_navigate(self, task: Task) -> None:
        """Execute navigate to pose task"""
        if not self.robot_interface:
            self._complete_task(task, False, "No robot interface")
            return
        
        x = task.custom_data.get('x', 0.0)
        y = task.custom_data.get('y', 0.0)
        yaw = task.custom_data.get('yaw', 0.0)
        
        def on_result(success, result):
            self._complete_task(task, success, "" if success else "Navigation failed")
        
        success = self.robot_interface.navigate_to_pose(
            task.robot_id, x, y, yaw,
            result_callback=on_result
        )
        
        if not success:
            self._complete_task(task, False, "Failed to send navigation goal")
    
    def _execute_follow_path(self, task: Task) -> None:
        """Execute follow path task"""
        if not self.robot_interface:
            self._complete_task(task, False, "No robot interface")
            return
        
        if not task.path_waypoints:
            self._complete_task(task, False, "No waypoints")
            return
        
        def on_result(success, result):
            self._complete_task(task, success, "" if success else "Path following failed")
        
        success = self.robot_interface.follow_path(
            task.robot_id, task.path_waypoints,
            result_callback=on_result
        )
        
        if not success:
            self._complete_task(task, False, "Failed to send path goal")
    
    def _execute_wait(self, task: Task) -> None:
        """Execute wait task"""
        def wait_thread():
            time.sleep(task.wait_duration)
            self._complete_task(task, True, "")
        
        threading.Thread(target=wait_thread, daemon=True).start()
    
    def _execute_custom(self, task: Task) -> None:
        """Execute custom task - subclass can override"""
        self._complete_task(task, True, "Custom task completed")
    
    def _complete_task(self, task: Task, success: bool, error_message: str) -> None:
        """Mark task as completed"""
        with self._lock:
            task.state = TaskState.COMPLETED if success else TaskState.FAILED
            task.success = success
            task.error_message = error_message
            task.completed_at = time.time()
            
            robot_id = task.robot_id
            
            # Remove from active
            if robot_id in self.active_tasks:
                if self.active_tasks[robot_id].task_id == task.task_id:
                    del self.active_tasks[robot_id]
            
            # Add to history
            if robot_id in self.completed_tasks:
                self.completed_tasks[robot_id].append(task)
                # Keep only last 100
                if len(self.completed_tasks[robot_id]) > 100:
                    self.completed_tasks[robot_id] = self.completed_tasks[robot_id][-100:]
        
        # Callbacks
        if success and task.on_complete:
            task.on_complete(task)
        elif not success and task.on_fail:
            task.on_fail(task, error_message)
        
        for callback in self.task_callbacks:
            try:
                callback(task, task.state)
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Task callback error: {e}")
        
        # Signal completion event
        event_key = f"{task.robot_id}:{task.task_id}"
        if event_key in self._task_complete_events:
            self._task_complete_events[event_key].set()
        
        if self.logger:
            status = "completed" if success else f"failed: {error_message}"
            self.logger.info(f"Task {task.task_id} {status}")
    
    def _preempt_task(self, robot_id: str, task: Task) -> None:
        """Preempt a running task"""
        task.state = TaskState.PREEMPTED
        
        # Cancel navigation if running
        if self.robot_interface and robot_id in self.robot_interface.action_clients:
            self.robot_interface.action_clients[robot_id].cancel_all()
        
        # Re-queue if needed
        if task.is_reentrant:
            self.task_queues[robot_id].push(task)
        
        if self.logger:
            self.logger.info(f"Preempted task {task.task_id}")
    
    def _executor_loop(self) -> None:
        """Background thread to process queued tasks"""
        while self._running:
            time.sleep(0.1)
            
            with self._lock:
                for robot_id, queue in self.task_queues.items():
                    # Skip if robot has active task
                    if robot_id in self.active_tasks:
                        continue
                    
                    # Get next task
                    task = queue.pop()
                    if task:
                        self.active_tasks[robot_id] = task
                        task.state = TaskState.RUNNING
                        task.started_at = time.time()
                        
                        # Start execution (outside lock)
                        threading.Thread(
                            target=self._start_task_execution,
                            args=(task,),
                            daemon=True
                        ).start()
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task by ID"""
        with self._lock:
            # Check active tasks
            for robot_id, task in list(self.active_tasks.items()):
                if task.task_id == task_id:
                    self._complete_task(task, False, "Cancelled")
                    
                    if self.robot_interface:
                        self.robot_interface.action_clients[robot_id].cancel_all()
                    
                    return True
            
            # Check queues
            for queue in self.task_queues.values():
                if queue.remove(task_id):
                    return True
        
        return False
    
    def cancel_all_for_robot(self, robot_id: str) -> None:
        """Cancel all tasks for a robot"""
        with self._lock:
            # Cancel active task
            if robot_id in self.active_tasks:
                task = self.active_tasks[robot_id]
                self._complete_task(task, False, "Cancelled")
            
            # Clear queue
            if robot_id in self.task_queues:
                self.task_queues[robot_id].clear()
            
            # Cancel navigation
            if self.robot_interface and robot_id in self.robot_interface.action_clients:
                self.robot_interface.action_clients[robot_id].cancel_all()
    
    def get_active_task(self, robot_id: str) -> Optional[Task]:
        """Get active task for robot"""
        with self._lock:
            return self.active_tasks.get(robot_id)
    
    def get_queued_tasks(self, robot_id: str) -> List[Task]:
        """Get queued tasks for robot"""
        with self._lock:
            if robot_id in self.task_queues:
                return self.task_queues[robot_id].get_all()
            return []
    
    def get_queue_size(self, robot_id: str) -> int:
        """Get queue size for robot"""
        with self._lock:
            if robot_id in self.task_queues:
                return self.task_queues[robot_id].size()
            return 0
    
    def register_task_callback(self, callback: Callable) -> None:
        """Register callback for task state changes: callback(task, state)"""
        self.task_callbacks.append(callback)
    
    def shutdown(self) -> None:
        """Shutdown the task manager"""
        self._running = False
        if self._executor_thread.is_alive():
            self._executor_thread.join(timeout=1.0)
