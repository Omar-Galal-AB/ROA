"""
Task Coordinator

Handles multi-robot task coordination, resource reservation, and deadlock prevention.

Enhanced with:
- Actual priority preemption (P1 Gap Fix)
- Robot capability matching (P3 Gap Fix)
- Distributed resource locking support
"""

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Set, Tuple

import rclpy
from rclpy.node import Node


class TaskPriority(Enum):
    """Task priority levels."""

    LOWEST = 0
    LOW = 1
    NORMAL = 2
    HIGH = 3
    HIGHEST = 4


class TaskStatus(Enum):
    """Task execution status."""

    REQUESTED = "requested"
    QUEUED = "queued"  # Waiting for resources
    APPROVED = "approved"
    EXECUTING = "executing"
    PREEMPTED = "preempted"  # Preempted by higher priority
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RobotCapability(Enum):
    """Robot capabilities for task matching"""

    NAVIGATION = "navigation"
    MANIPULATION = "manipulation"
    PAYLOAD_TRANSPORT = "payload_transport"
    INSPECTION = "inspection"
    CHARGING = "charging"
    HEAVY_LIFT = "heavy_lift"
    PRECISION_WORK = "precision_work"
    OUTDOOR = "outdoor"
    INDOOR = "indoor"


@dataclass
class Task:
    """Task information."""

    task_id: str
    robot_id: str
    task_type: str
    required_resources: List[str]
    priority: TaskPriority
    status: TaskStatus
    timestamp: float
    deadline: Optional[float] = None
    required_capabilities: List[RobotCapability] = field(default_factory=list)
    preempted_by: Optional[str] = None  # task_id that preempted this


@dataclass
class RobotProfile:
    """Robot capability profile for task matching"""

    robot_id: str
    capabilities: Set[RobotCapability] = field(default_factory=set)
    max_payload_kg: float = 0.0
    battery_level: float = 100.0
    is_available: bool = True
    current_task_id: Optional[str] = None

    def can_perform(self, required_caps: List[RobotCapability]) -> bool:
        """Check if robot can perform task with required capabilities"""
        return all(cap in self.capabilities for cap in required_caps)


class TaskCoordinator:
    """
    Coordinates multi-robot tasks to prevent conflicts and resource collisions.

    Enhanced with:
    - Actual priority preemption implementation
    - Robot capability matching
    - Distributed resource locking support
    """

    def __init__(self, node: Node):
        """
        Initialize the task coordinator.

        Args:
            node: ROS2 node instance
        """
        self.node = node
        self.tasks: Dict[str, Task] = {}  # task_id -> Task
        self.robot_tasks: Dict[str, List[str]] = {}  # robot_id -> [task_ids]
        self.resource_locks: Dict[str, str] = {}  # resource -> robot_id
        self.resource_lock_times: Dict[str, float] = {}  # resource -> lock_time
        self.max_wait_time = 10.0  # seconds for deadlock timeout
        self.lock_timeout = 60.0  # seconds before lock expires

        # Robot capability registry (P3 Gap Fix)
        self.robot_profiles: Dict[str, RobotProfile] = {}

        # Queued tasks waiting for resources
        self.task_queue: List[str] = []  # task_ids in priority order

        # Callbacks for preemption
        self._preemption_callbacks: List[Callable[[str, str], None]] = (
            []
        )  # (preempted_task, preempting_task)

        # Lock for thread safety
        self._lock = threading.RLock()

    def register_preemption_callback(self, callback: Callable[[str, str], None]):
        """Register callback for when a task is preempted"""
        self._preemption_callbacks.append(callback)

    # =========================================================================
    # Robot Capability Management (P3 Gap Fix)
    # =========================================================================

    def register_robot(
        self,
        robot_id: str,
        capabilities: List[RobotCapability] = None,
        max_payload_kg: float = 0.0,
    ):
        """
        Register a robot with its capabilities.

        Args:
            robot_id: Robot identifier
            capabilities: List of robot capabilities
            max_payload_kg: Maximum payload capacity
        """
        with self._lock:
            self.robot_profiles[robot_id] = RobotProfile(
                robot_id=robot_id,
                capabilities=set(capabilities or []),
                max_payload_kg=max_payload_kg,
            )
            self.node.get_logger().info(
                f"Registered robot {robot_id} with capabilities: "
                f"{[c.value for c in (capabilities or [])]}"
            )

    def update_robot_status(
        self, robot_id: str, battery_level: float = None, is_available: bool = None
    ):
        """Update robot status"""
        with self._lock:
            if robot_id in self.robot_profiles:
                profile = self.robot_profiles[robot_id]
                if battery_level is not None:
                    profile.battery_level = battery_level
                if is_available is not None:
                    profile.is_available = is_available

    def find_capable_robots(
        self, required_capabilities: List[RobotCapability], min_battery: float = 20.0
    ) -> List[str]:
        """
        Find robots capable of performing a task.

        Args:
            required_capabilities: Required capabilities
            min_battery: Minimum battery level required

        Returns:
            List of capable robot IDs
        """
        with self._lock:
            capable = []
            for robot_id, profile in self.robot_profiles.items():
                if (
                    profile.is_available
                    and profile.battery_level >= min_battery
                    and profile.can_perform(required_capabilities)
                ):
                    capable.append(robot_id)
            return capable

    def get_best_robot_for_task(
        self,
        required_capabilities: List[RobotCapability],
        preferred_robots: List[str] = None,
    ) -> Optional[str]:
        """
        Find the best robot for a task based on capabilities and availability.

        Args:
            required_capabilities: Required capabilities
            preferred_robots: Preferred robot IDs (checked first)

        Returns:
            Best robot ID or None
        """
        capable = self.find_capable_robots(required_capabilities)

        if not capable:
            return None

        # Check preferred robots first
        if preferred_robots:
            for robot_id in preferred_robots:
                if robot_id in capable:
                    return robot_id

        # Return robot with highest battery
        with self._lock:
            return max(capable, key=lambda r: self.robot_profiles[r].battery_level)

    # =========================================================================
    # Task Coordination with Preemption (P1 Gap Fix)
    # =========================================================================

    def request_task_coordination(
        self,
        robot_id: str,
        task_type: str,
        required_resources: List[str],
        priority: int,
        required_capabilities: List[RobotCapability] = None,
    ) -> Tuple[bool, List[str], str]:
        """
        Request coordination for a new task.

        Args:
            robot_id: ID of requesting robot
            task_type: Type of task to perform
            required_resources: List of resources needed
            priority: Task priority (0-4)
            required_capabilities: Optional required robot capabilities

        Returns:
            Tuple of (approved, conflicting_robots, alternative_suggestion)
        """
        with self._lock:
            # Check robot capability if specified
            if required_capabilities and robot_id in self.robot_profiles:
                profile = self.robot_profiles[robot_id]
                if not profile.can_perform(required_capabilities):
                    missing = [
                        c.value for c in required_capabilities if c not in profile.capabilities
                    ]
                    return (False, [], f"Robot lacks capabilities: {missing}")

            # Create task ID
            task_id = f"{robot_id}_{task_type}_{int(time.time() * 1000)}"

            # Create task
            task = Task(
                task_id=task_id,
                robot_id=robot_id,
                task_type=task_type,
                required_resources=required_resources,
                priority=TaskPriority(priority),
                status=TaskStatus.REQUESTED,
                timestamp=time.time(),
                required_capabilities=required_capabilities or [],
            )

            # Check resource availability and potential preemption
            conflicts, can_preempt = self._check_resource_conflicts_with_preemption(
                required_resources, robot_id, priority
            )

            if not conflicts:
                # No conflicts - approve immediately
                return self._approve_task(task)

            elif can_preempt:
                # Can preempt lower priority tasks
                preempted = self._execute_preemption(task, conflicts)
                if preempted:
                    return self._approve_task(task)

            # Cannot approve - queue or reject
            conflicting_robots = list(conflicts.keys())
            suggestion = self._generate_alternative_suggestion(
                robot_id, required_resources, set(conflicting_robots)
            )

            # Queue the task
            task.status = TaskStatus.QUEUED
            self.tasks[task_id] = task
            self._add_to_queue(task_id)

            self.node.get_logger().warn(
                f"Task {task_id} queued for {robot_id} due to conflicts with {conflicting_robots}"
            )
            return (False, conflicting_robots, suggestion)

    def _check_resource_conflicts_with_preemption(
        self, resources: List[str], requesting_robot: str, priority: int
    ) -> Tuple[Dict[str, Task], bool]:
        """
        Check resource conflicts and determine if preemption is possible.

        Returns:
            Tuple of (conflicts dict {robot_id: task}, can_preempt_all)
        """
        conflicts = {}
        can_preempt_all = True

        for resource in resources:
            if resource in self.resource_locks:
                locking_robot = self.resource_locks[resource]

                if locking_robot != requesting_robot:
                    locking_task = self._get_robot_active_task(locking_robot)

                    if locking_task:
                        conflicts[locking_robot] = locking_task

                        # Check if we can preempt
                        if locking_task.priority.value >= priority:
                            can_preempt_all = False
                    else:
                        # Lock exists but no active task - check for stale lock
                        if self._is_lock_stale(resource):
                            self._release_stale_lock(resource)
                        else:
                            can_preempt_all = False

        return conflicts, can_preempt_all and len(conflicts) > 0

    def _is_lock_stale(self, resource: str) -> bool:
        """Check if a resource lock has expired"""
        if resource not in self.resource_lock_times:
            return True
        return time.time() - self.resource_lock_times[resource] > self.lock_timeout

    def _release_stale_lock(self, resource: str):
        """Release a stale resource lock"""
        if resource in self.resource_locks:
            robot_id = self.resource_locks[resource]
            del self.resource_locks[resource]
            if resource in self.resource_lock_times:
                del self.resource_lock_times[resource]
            self.node.get_logger().warn(
                f"Released stale lock on {resource} (was held by {robot_id})"
            )

    def _execute_preemption(self, new_task: Task, conflicts: Dict[str, Task]) -> bool:
        """
        Execute preemption of lower priority tasks.

        Args:
            new_task: The new higher-priority task
            conflicts: Dict of robot_id -> task to preempt

        Returns:
            True if preemption succeeded
        """
        preempted_tasks = []

        for robot_id, task in conflicts.items():
            if task.priority.value < new_task.priority.value:
                # Preempt this task
                old_status = task.status
                task.status = TaskStatus.PREEMPTED
                task.preempted_by = new_task.task_id

                # Release resources
                self._release_task_resources(task)

                preempted_tasks.append(task)

                self.node.get_logger().warn(
                    f"PREEMPTION: Task {task.task_id} (priority {task.priority.value}) "
                    f"preempted by {new_task.task_id} (priority {new_task.priority.value})"
                )

                # Notify callbacks
                for callback in self._preemption_callbacks:
                    try:
                        callback(task.task_id, new_task.task_id)
                    except Exception as e:
                        self.node.get_logger().error(f"Preemption callback error: {e}")

        return len(preempted_tasks) == len(conflicts)

    def _approve_task(self, task: Task) -> Tuple[bool, List[str], str]:
        """Approve a task and reserve resources"""
        task.status = TaskStatus.APPROVED
        self.tasks[task.task_id] = task

        # Track robot tasks
        if task.robot_id not in self.robot_tasks:
            self.robot_tasks[task.robot_id] = []
        self.robot_tasks[task.robot_id].append(task.task_id)

        # Update robot profile
        if task.robot_id in self.robot_profiles:
            self.robot_profiles[task.robot_id].current_task_id = task.task_id

        # Reserve resources with timestamp
        for resource in task.required_resources:
            self.resource_locks[resource] = task.robot_id
            self.resource_lock_times[resource] = time.time()

        self.node.get_logger().info(f"Task {task.task_id} approved for {task.robot_id}")
        return (True, [], "")

    def _add_to_queue(self, task_id: str):
        """Add task to priority queue"""
        self.task_queue.append(task_id)
        # Sort by priority (highest first)
        self.task_queue.sort(
            key=lambda tid: self.tasks[tid].priority.value if tid in self.tasks else 0,
            reverse=True,
        )

    def process_queue(self):
        """
        Process queued tasks, approving any that can now proceed.
        Should be called periodically.
        """
        with self._lock:
            approved = []

            for task_id in list(self.task_queue):
                if task_id not in self.tasks:
                    self.task_queue.remove(task_id)
                    continue

                task = self.tasks[task_id]

                # Check if resources are now available
                conflicts, can_preempt = self._check_resource_conflicts_with_preemption(
                    task.required_resources, task.robot_id, task.priority.value
                )

                if not conflicts:
                    # Approve the queued task
                    self._approve_task(task)
                    approved.append(task_id)
                    self.task_queue.remove(task_id)
                    self.node.get_logger().info(f"Queued task {task_id} now approved")

            return approved

    def _check_resource_conflicts(
        self, resources: List[str], requesting_robot: str, priority: int
    ) -> Set[str]:
        """Legacy method - now wraps the new implementation"""
        conflicts, _ = self._check_resource_conflicts_with_preemption(
            resources, requesting_robot, priority
        )
        return set(conflicts.keys())

    def _get_robot_active_task(self, robot_id: str) -> Optional[Task]:
        """Get the currently active task for a robot."""
        if robot_id not in self.robot_tasks:
            return None

        for task_id in self.robot_tasks[robot_id]:
            task = self.tasks.get(task_id)
            if task and task.status in [TaskStatus.APPROVED, TaskStatus.EXECUTING]:
                return task

        return None

    def _generate_alternative_suggestion(
        self, robot_id: str, resources: List[str], conflicts: Set[str]
    ) -> str:
        """
        Generate an alternative suggestion when task cannot be approved.
        """
        if not conflicts:
            return ""

        conflicting_robot = list(conflicts)[0]
        locking_task = self._get_robot_active_task(conflicting_robot)

        if locking_task:
            # Estimate wait time
            if locking_task.deadline:
                wait_time = locking_task.deadline - time.time()
                return f"Task queued. Estimated wait: {wait_time:.0f}s for {conflicting_robot}"
            return f"Task queued. Waiting for {conflicting_robot} to complete"
        else:
            return "Task queued. Retry request shortly"

    def update_task_status(self, task_id: str, status: TaskStatus):
        """Update the status of a task."""
        with self._lock:
            if task_id not in self.tasks:
                self.node.get_logger().warn(f"Task {task_id} not found")
                return

            task = self.tasks[task_id]
            old_status = task.status
            task.status = status

            # Release resources if task is completed or failed
            if status in [
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
                TaskStatus.PREEMPTED,
            ]:
                self._release_task_resources(task)

                # Update robot profile
                if task.robot_id in self.robot_profiles:
                    self.robot_profiles[task.robot_id].current_task_id = None

                # Process queue - may unblock waiting tasks
                self.process_queue()

            self.node.get_logger().info(
                f"Task {task_id} status: {old_status.value} -> {status.value}"
            )

    def _release_task_resources(self, task: Task):
        """Release resources locked by a task."""
        for resource in task.required_resources:
            if resource in self.resource_locks and self.resource_locks[resource] == task.robot_id:
                del self.resource_locks[resource]
                if resource in self.resource_lock_times:
                    del self.resource_lock_times[resource]
                self.node.get_logger().info(f"Released resource: {resource}")

    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """Get the status of a task."""
        task = self.tasks.get(task_id)
        return task.status if task else None

    def cancel_task(self, task_id: str):
        """Cancel a task and release its resources."""
        if task_id in self.tasks:
            self.update_task_status(task_id, TaskStatus.CANCELLED)
        if task_id in self.task_queue:
            self.task_queue.remove(task_id)

    def get_robot_tasks(self, robot_id: str) -> List[Task]:
        """Get all tasks for a robot."""
        with self._lock:
            if robot_id not in self.robot_tasks:
                return []

            return [
                self.tasks[task_id]
                for task_id in self.robot_tasks[robot_id]
                if task_id in self.tasks
            ]

    def get_queue_status(self) -> List[dict]:
        """Get status of all queued tasks"""
        with self._lock:
            return [
                {
                    "task_id": tid,
                    "robot_id": self.tasks[tid].robot_id,
                    "priority": self.tasks[tid].priority.value,
                    "wait_time": time.time() - self.tasks[tid].timestamp,
                }
                for tid in self.task_queue
                if tid in self.tasks
            ]

    def check_deadlock(self) -> List[str]:
        """Check for potential deadlocks in task coordination."""
        with self._lock:
            deadlocked_robots = []
            current_time = time.time()

            for task_id, task in self.tasks.items():
                if task.status in [TaskStatus.REQUESTED, TaskStatus.QUEUED]:
                    wait_time = current_time - task.timestamp
                    if wait_time > self.max_wait_time:
                        deadlocked_robots.append(task.robot_id)
                        self.node.get_logger().error(
                            f"Deadlock detected: {task.robot_id} waiting {wait_time:.1f}s for task {task_id}"
                        )

            return deadlocked_robots

    def resolve_deadlock(self, robot_ids: List[str]):
        """Attempt to resolve deadlock by cancelling lower priority tasks."""
        with self._lock:
            for robot_id in robot_ids:
                tasks = self.get_robot_tasks(robot_id)
                if tasks:
                    pending_tasks = [
                        t for t in tasks if t.status in [TaskStatus.REQUESTED, TaskStatus.QUEUED]
                    ]

                    if pending_tasks:
                        lowest_priority_task = min(pending_tasks, key=lambda t: t.priority.value)
                        self.cancel_task(lowest_priority_task.task_id)
                        self.node.get_logger().warn(
                            f"Cancelled task {lowest_priority_task.task_id} to resolve deadlock"
                        )
