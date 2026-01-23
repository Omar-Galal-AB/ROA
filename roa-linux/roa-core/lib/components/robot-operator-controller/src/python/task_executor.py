"""
ADM Task Executor - Autonomous task execution engine for ROC.

Bridges ADM Mode with Path Planning and Robot Controllers.
Executes high-level tasks through waypoint navigation and motion control.

This was identified as a critical gap - ADM mode exists but had no
execution engine to run planned paths.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

# Import ADM mode
from .control_modes.adm_mode import ADMMode, Task, TaskPriority, TaskStatus

# Import path planners
from .path_planning.a_star import AStarPlanner
from .path_planning.rrt import RRTPlanner


class PlannerType(Enum):
    """Path planner types."""

    A_STAR = auto()
    RRT = auto()
    RRT_STAR = auto()


class ExecutionState(Enum):
    """Task execution state."""

    IDLE = auto()
    PLANNING = auto()
    EXECUTING = auto()
    WAYPOINT_REACHED = auto()
    REPLANNING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    FAILED = auto()


@dataclass
class WaypointProgress:
    """Progress through waypoints."""

    waypoints: List[Dict[str, float]] = field(default_factory=list)
    current_index: int = 0
    total_distance: float = 0.0
    distance_traveled: float = 0.0

    @property
    def current_waypoint(self) -> Optional[Dict[str, float]]:
        """Get current target waypoint."""
        if 0 <= self.current_index < len(self.waypoints):
            return self.waypoints[self.current_index]
        return None

    @property
    def progress_percent(self) -> float:
        """Get progress percentage."""
        if not self.waypoints:
            return 0.0
        return (self.current_index / len(self.waypoints)) * 100

    @property
    def is_complete(self) -> bool:
        """Check if all waypoints reached."""
        return self.current_index >= len(self.waypoints)


@dataclass
class ExecutorConfig:
    """Configuration for task executor."""

    # Planner selection
    default_planner: PlannerType = PlannerType.A_STAR

    # Waypoint navigation
    waypoint_tolerance: float = 0.05  # meters
    orientation_tolerance: float = 0.1  # radians

    # Replanning
    replan_on_obstacle: bool = True
    replan_rate_hz: float = 2.0
    max_replan_attempts: int = 5

    # Timeouts
    planning_timeout_s: float = 5.0
    waypoint_timeout_s: float = 30.0
    task_timeout_s: float = 300.0

    # Motion control
    approach_speed_multiplier: float = 0.5  # Slow down near waypoint
    approach_distance: float = 0.2  # Distance to start slowing

    # Safety
    min_obstacle_distance: float = 0.1  # meters
    pause_on_close_obstacle: bool = True


class TaskExecutor:
    """
    Executes ADM tasks through path planning and motion control.

    Responsibilities:
    - Plan paths using A* or RRT
    - Navigate through waypoints
    - Handle replanning on obstacles
    - Report progress and status
    - Coordinate with safety system
    """

    def __init__(
        self,
        config: Optional[ExecutorConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize task executor.

        Args:
            config: Executor configuration
            logger: Logger instance
        """
        self.config = config or ExecutorConfig()
        self.logger = logger or logging.getLogger(__name__)

        # Initialize planners
        self._init_planners()

        # Execution state
        self._state = ExecutionState.IDLE
        self._current_task: Optional[Task] = None
        self._progress = WaypointProgress()
        self._replan_count = 0

        # Position tracking
        self._current_position: Dict[str, float] = {"x": 0, "y": 0, "z": 0}
        self._current_orientation: Dict[str, float] = {"roll": 0, "pitch": 0, "yaw": 0}

        # Obstacle tracking
        self._obstacles: List[Dict] = []
        self._closest_obstacle_distance: float = float("inf")

        # Callbacks
        self._on_state_change: List[Callable[[ExecutionState], None]] = []
        self._on_waypoint_reached: List[Callable[[int, Dict], None]] = []
        self._on_task_complete: List[Callable[[Task, bool], None]] = []
        self._motion_command_callback: Optional[Callable[[str, Dict], None]] = None

        # Async task
        self._execution_task: Optional[asyncio.Task] = None
        self._running = False

        # Statistics
        self._tasks_executed = 0
        self._tasks_completed = 0
        self._tasks_failed = 0
        self._total_distance = 0.0
        self._total_replan_count = 0

        self.logger.info("TaskExecutor initialized")

    def _init_planners(self):
        """Initialize path planners."""
        self._a_star = AStarPlanner(
            grid_resolution=0.1, obstacle_padding=self.config.min_obstacle_distance
        )

        self._rrt = RRTPlanner(
            max_iterations=5000,
            step_size=0.5,
            obstacle_padding=self.config.min_obstacle_distance,
            use_rrt_star=False,
        )

        self._rrt_star = RRTPlanner(
            max_iterations=5000,
            step_size=0.5,
            obstacle_padding=self.config.min_obstacle_distance,
            use_rrt_star=True,
        )

    @property
    def state(self) -> ExecutionState:
        """Get current execution state."""
        return self._state

    @property
    def current_task(self) -> Optional[Task]:
        """Get current task being executed."""
        return self._current_task

    @property
    def progress(self) -> WaypointProgress:
        """Get waypoint progress."""
        return self._progress

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self):
        """Start the executor."""
        self._running = True
        self.logger.info("TaskExecutor started")

    async def stop(self):
        """Stop the executor."""
        self._running = False

        # Cancel current execution
        if self._execution_task and not self._execution_task.done():
            self._execution_task.cancel()
            try:
                await self._execution_task
            except asyncio.CancelledError:
                pass

        self._set_state(ExecutionState.IDLE)
        self.logger.info("TaskExecutor stopped")

    # =========================================================================
    # Task Execution
    # =========================================================================

    async def execute_task(self, task: Task) -> bool:
        """
        Execute a task asynchronously.

        Args:
            task: Task to execute

        Returns:
            True if task completed successfully
        """
        if self._state not in (
            ExecutionState.IDLE,
            ExecutionState.COMPLETED,
            ExecutionState.FAILED,
        ):
            self.logger.warning(f"Cannot start task - executor in state {self._state}")
            return False

        self._current_task = task
        self._tasks_executed += 1
        self._replan_count = 0

        task.start()
        self.logger.info(f"Starting task: {task.task_id} type={task.task_type}")

        try:
            # Phase 1: Planning
            self._set_state(ExecutionState.PLANNING)
            path = await self._plan_path(task)

            if not path:
                self.logger.error(f"Failed to plan path for task {task.task_id}")
                task.status = TaskStatus.FAILED
                task.error_message = "Path planning failed"
                self._tasks_failed += 1
                self._set_state(ExecutionState.FAILED)
                self._notify_task_complete(task, False)
                return False

            # Set waypoints
            self._progress = WaypointProgress(
                waypoints=path,
                current_index=0,
                total_distance=self._calculate_path_distance(path),
            )

            # Phase 2: Execution
            self._set_state(ExecutionState.EXECUTING)
            success = await self._execute_path()

            if success:
                task.status = TaskStatus.COMPLETED
                self._tasks_completed += 1
                self._total_distance += self._progress.total_distance
                self._set_state(ExecutionState.COMPLETED)
                self.logger.info(f"Task {task.task_id} completed successfully")
            else:
                task.status = TaskStatus.FAILED
                self._tasks_failed += 1
                self._set_state(ExecutionState.FAILED)
                self.logger.warning(f"Task {task.task_id} failed during execution")

            self._notify_task_complete(task, success)
            return success

        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            self._set_state(ExecutionState.IDLE)
            raise
        except Exception as e:
            self.logger.error(f"Task execution error: {e}")
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            self._tasks_failed += 1
            self._set_state(ExecutionState.FAILED)
            self._notify_task_complete(task, False)
            return False

    async def _plan_path(self, task: Task) -> Optional[List[Dict[str, float]]]:
        """Plan path for task."""
        start = self._current_position.copy()
        goal = task.target_position

        planner_type = self.config.default_planner

        try:
            # Run planning with timeout
            path = await asyncio.wait_for(
                self._run_planner(planner_type, start, goal, self._obstacles),
                timeout=self.config.planning_timeout_s,
            )

            if path:
                self.logger.info(f"Planned path with {len(path)} waypoints")

            return path

        except asyncio.TimeoutError:
            self.logger.error("Path planning timeout")
            return None

    async def _run_planner(
        self,
        planner_type: PlannerType,
        start: Dict[str, float],
        goal: Dict[str, float],
        obstacles: List[Dict],
    ) -> Optional[List[Dict[str, float]]]:
        """Run path planner in executor."""
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()

        if planner_type == PlannerType.A_STAR:
            return await loop.run_in_executor(None, self._a_star.plan, start, goal, obstacles)
        elif planner_type == PlannerType.RRT:
            return await loop.run_in_executor(None, self._rrt.plan, start, goal, obstacles, None)
        elif planner_type == PlannerType.RRT_STAR:
            return await loop.run_in_executor(
                None, self._rrt_star.plan, start, goal, obstacles, None
            )

        return None

    async def _execute_path(self) -> bool:
        """Execute planned path through waypoints."""
        start_time = time.time()

        while not self._progress.is_complete and self._running:
            # Check task timeout
            if time.time() - start_time > self.config.task_timeout_s:
                self.logger.error("Task execution timeout")
                return False

            # Check for close obstacles
            if self._should_pause_for_obstacle():
                self._set_state(ExecutionState.PAUSED)
                await asyncio.sleep(0.5)
                continue

            # Get current waypoint
            waypoint = self._progress.current_waypoint
            if not waypoint:
                break

            # Move toward waypoint
            if self._motion_command_callback:
                velocity_mult = self._calculate_approach_velocity()
                self._motion_command_callback(
                    "move_to",
                    {"target": waypoint, "velocity_multiplier": velocity_mult},
                )

            # Check if reached waypoint
            if self._is_at_waypoint(waypoint):
                self._progress.current_index += 1
                self._notify_waypoint_reached()
                self._set_state(ExecutionState.WAYPOINT_REACHED)

                # Brief pause between waypoints
                await asyncio.sleep(0.05)
                self._set_state(ExecutionState.EXECUTING)

            # Check for replanning need
            if self._needs_replanning():
                success = await self._replan()
                if not success:
                    return False

            await asyncio.sleep(0.02)  # 50Hz control loop

        return self._progress.is_complete

    async def _replan(self) -> bool:
        """Replan path due to obstacles."""
        if self._replan_count >= self.config.max_replan_attempts:
            self.logger.error("Max replan attempts exceeded")
            return False

        self._replan_count += 1
        self._total_replan_count += 1
        self._set_state(ExecutionState.REPLANNING)

        self.logger.info(f"Replanning path (attempt {self._replan_count})")

        # Plan from current position to goal
        new_path = await self._plan_path(self._current_task)

        if new_path:
            self._progress = WaypointProgress(waypoints=new_path, current_index=0)
            self._set_state(ExecutionState.EXECUTING)
            return True

        return False

    # =========================================================================
    # Position and Obstacle Updates
    # =========================================================================

    def update_position(
        self, position: Dict[str, float], orientation: Optional[Dict[str, float]] = None
    ):
        """Update current robot position."""
        self._current_position = position
        if orientation:
            self._current_orientation = orientation

    def update_obstacles(self, obstacles: List[Dict]):
        """Update obstacle list."""
        self._obstacles = obstacles

        # Calculate closest obstacle
        if obstacles:
            self._closest_obstacle_distance = min(
                o.get("distance", float("inf")) for o in obstacles
            )
        else:
            self._closest_obstacle_distance = float("inf")

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _is_at_waypoint(self, waypoint: Dict[str, float]) -> bool:
        """Check if robot is at waypoint."""
        dx = self._current_position.get("x", 0) - waypoint.get("x", 0)
        dy = self._current_position.get("y", 0) - waypoint.get("y", 0)
        dz = self._current_position.get("z", 0) - waypoint.get("z", 0)

        distance = (dx**2 + dy**2 + dz**2) ** 0.5
        return distance < self.config.waypoint_tolerance

    def _should_pause_for_obstacle(self) -> bool:
        """Check if should pause due to close obstacle."""
        if not self.config.pause_on_close_obstacle:
            return False
        return self._closest_obstacle_distance < self.config.min_obstacle_distance

    def _needs_replanning(self) -> bool:
        """Check if replanning is needed."""
        if not self.config.replan_on_obstacle:
            return False
        # Replan if obstacle appeared on path
        # This is a simplified check - real implementation would check path collision
        return self._closest_obstacle_distance < self.config.min_obstacle_distance * 2

    def _calculate_approach_velocity(self) -> float:
        """Calculate velocity multiplier based on distance to waypoint."""
        waypoint = self._progress.current_waypoint
        if not waypoint:
            return 1.0

        dx = self._current_position.get("x", 0) - waypoint.get("x", 0)
        dy = self._current_position.get("y", 0) - waypoint.get("y", 0)
        dz = self._current_position.get("z", 0) - waypoint.get("z", 0)
        distance = (dx**2 + dy**2 + dz**2) ** 0.5

        if distance < self.config.approach_distance:
            # Linear interpolation to slow down
            ratio = distance / self.config.approach_distance
            return (
                self.config.approach_speed_multiplier
                + (1 - self.config.approach_speed_multiplier) * ratio
            )

        return 1.0

    def _calculate_path_distance(self, path: List[Dict[str, float]]) -> float:
        """Calculate total path distance."""
        if len(path) < 2:
            return 0.0

        total = 0.0
        for i in range(len(path) - 1):
            dx = path[i + 1].get("x", 0) - path[i].get("x", 0)
            dy = path[i + 1].get("y", 0) - path[i].get("y", 0)
            dz = path[i + 1].get("z", 0) - path[i].get("z", 0)
            total += (dx**2 + dy**2 + dz**2) ** 0.5

        return total

    def _set_state(self, new_state: ExecutionState):
        """Set execution state and notify callbacks."""
        if new_state != self._state:
            old_state = self._state
            self._state = new_state
            self.logger.debug(f"State: {old_state.name} -> {new_state.name}")

            for callback in self._on_state_change:
                try:
                    callback(new_state)
                except Exception as e:
                    self.logger.error(f"State change callback error: {e}")

    def _notify_waypoint_reached(self):
        """Notify waypoint reached callbacks."""
        idx = self._progress.current_index - 1
        if idx >= 0 and idx < len(self._progress.waypoints):
            waypoint = self._progress.waypoints[idx]
            for callback in self._on_waypoint_reached:
                try:
                    callback(idx, waypoint)
                except Exception as e:
                    self.logger.error(f"Waypoint callback error: {e}")

    def _notify_task_complete(self, task: Task, success: bool):
        """Notify task completion callbacks."""
        for callback in self._on_task_complete:
            try:
                callback(task, success)
            except Exception as e:
                self.logger.error(f"Task complete callback error: {e}")

    # =========================================================================
    # Callback Registration
    # =========================================================================

    def on_state_change(self, callback: Callable[[ExecutionState], None]):
        """Register state change callback."""
        self._on_state_change.append(callback)

    def on_waypoint_reached(self, callback: Callable[[int, Dict], None]):
        """Register waypoint reached callback."""
        self._on_waypoint_reached.append(callback)

    def on_task_complete(self, callback: Callable[[Task, bool], None]):
        """Register task completion callback."""
        self._on_task_complete.append(callback)

    def set_motion_command_callback(self, callback: Callable[[str, Dict], None]):
        """Set callback for motion commands."""
        self._motion_command_callback = callback

    # =========================================================================
    # Control
    # =========================================================================

    def pause(self):
        """Pause execution."""
        if self._state == ExecutionState.EXECUTING:
            self._set_state(ExecutionState.PAUSED)

    def resume(self):
        """Resume execution."""
        if self._state == ExecutionState.PAUSED:
            self._set_state(ExecutionState.EXECUTING)

    def cancel(self):
        """Cancel current task."""
        if self._execution_task and not self._execution_task.done():
            self._execution_task.cancel()

        if self._current_task:
            self._current_task.status = TaskStatus.CANCELLED

        self._set_state(ExecutionState.IDLE)

    # =========================================================================
    # Status
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get executor status."""
        return {
            "state": self._state.name,
            "running": self._running,
            "current_task": self._current_task.task_id if self._current_task else None,
            "progress": {
                "waypoint_index": self._progress.current_index,
                "total_waypoints": len(self._progress.waypoints),
                "percent": self._progress.progress_percent,
            },
            "position": self._current_position,
            "closest_obstacle": self._closest_obstacle_distance,
            "replan_count": self._replan_count,
            "statistics": {
                "tasks_executed": self._tasks_executed,
                "tasks_completed": self._tasks_completed,
                "tasks_failed": self._tasks_failed,
                "total_distance": self._total_distance,
                "total_replans": self._total_replan_count,
            },
        }
