"""
ROC State Tracker - State transition tracking and auditing.

Provides:
- State transition history per robot
- Time-in-state tracking
- Stale state detection
- Audit trail for debugging
- State change callbacks

Based on COMC's EnhancedStateTracker pattern.
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from .control_modes.mode_manager import ControlMode
from .robot_registry.robot_state import RobotStatus


class RobotOperationalState(Enum):
    """High-level robot operational state."""

    UNKNOWN = "unknown"
    OFFLINE = "offline"
    INITIALIZING = "initializing"
    IDLE = "idle"
    EXECUTING = "executing"
    PAUSED = "paused"
    ESTOPPED = "estopped"
    ERROR = "error"
    MAINTENANCE = "maintenance"


@dataclass
class StateTransition:
    """Record of a state transition."""

    robot_id: str
    timestamp: float
    from_state: str
    to_state: str
    state_type: str  # "operational", "mode", "status"
    duration_in_previous_s: float
    reason: Optional[str] = None
    triggered_by: Optional[str] = None  # "user", "system", "safety"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "robot_id": self.robot_id,
            "timestamp": self.timestamp,
            "timestamp_iso": datetime.fromtimestamp(self.timestamp).isoformat(),
            "from_state": self.from_state,
            "to_state": self.to_state,
            "state_type": self.state_type,
            "duration_s": round(self.duration_in_previous_s, 3),
            "reason": self.reason,
            "triggered_by": self.triggered_by,
        }


@dataclass
class RobotStateSnapshot:
    """Complete state snapshot for a robot."""

    robot_id: str
    operational_state: RobotOperationalState
    control_mode: ControlMode
    robot_status: RobotStatus
    last_update: float
    state_entry_time: float  # When entered current operational state
    mode_entry_time: float  # When entered current mode

    # Health indicators
    is_stale: bool = False
    stale_since: Optional[float] = None

    # Activity
    last_command_time: Optional[float] = None
    commands_since_state_change: int = 0

    def time_in_state_s(self) -> float:
        """Get time in current operational state."""
        return time.time() - self.state_entry_time

    def time_in_mode_s(self) -> float:
        """Get time in current control mode."""
        return time.time() - self.mode_entry_time

    def time_since_update_s(self) -> float:
        """Get time since last state update."""
        return time.time() - self.last_update


@dataclass
class StateTrackerConfig:
    """Configuration for StateTracker."""

    # History settings
    max_transitions_per_robot: int = 500
    max_global_transitions: int = 5000

    # Stale detection
    stale_threshold_s: float = 5.0  # Robot state is stale after 5s
    stale_check_interval_s: float = 1.0

    # Audit settings
    track_mode_changes: bool = True
    track_status_changes: bool = True
    track_operational_changes: bool = True


StateChangeCallback = Callable[[str, StateTransition], None]  # robot_id, transition


class ROCStateTracker:
    """
    Tracks robot state transitions for auditing and debugging.

    Responsibilities:
    - Maintain state history per robot
    - Track time spent in each state
    - Detect stale/hung robots
    - Provide audit trail queries
    - Notify on state changes

    Usage:
        tracker = ROCStateTracker()

        # Track state changes
        tracker.update_operational_state("robot_0", RobotOperationalState.EXECUTING)
        tracker.update_mode("robot_0", ControlMode.ADM, reason="user_request")

        # Query history
        transitions = tracker.get_transitions("robot_0", limit=10)

        # Check for stale robots
        stale_robots = tracker.get_stale_robots()
    """

    def __init__(
        self,
        config: Optional[StateTrackerConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize StateTracker.

        Args:
            config: Tracker configuration
            logger: Logger instance
        """
        self.config = config or StateTrackerConfig()
        self.logger = logger or logging.getLogger(__name__)

        # Current state per robot
        self._robot_states: Dict[str, RobotStateSnapshot] = {}

        # Transition history
        self._transitions: Deque[StateTransition] = deque(maxlen=self.config.max_global_transitions)
        self._robot_transitions: Dict[str, Deque[StateTransition]] = {}

        # Callbacks
        self._state_change_callbacks: List[StateChangeCallback] = []

        # Statistics
        self._stats = {
            "total_transitions": 0,
            "transitions_by_type": {"operational": 0, "mode": 0, "status": 0},
            "stale_detections": 0,
        }

        # Time-in-state aggregates
        self._time_in_state: Dict[str, Dict[str, float]] = {}  # robot -> state -> seconds

        self.logger.info("ROCStateTracker initialized")

    # =========================================================================
    # ROBOT REGISTRATION
    # =========================================================================

    def register_robot(self, robot_id: str):
        """
        Register a robot for state tracking.

        Args:
            robot_id: Robot identifier
        """
        if robot_id in self._robot_states:
            return

        current_time = time.time()

        self._robot_states[robot_id] = RobotStateSnapshot(
            robot_id=robot_id,
            operational_state=RobotOperationalState.INITIALIZING,
            control_mode=ControlMode.RPM,
            robot_status=RobotStatus.INITIALIZING,
            last_update=current_time,
            state_entry_time=current_time,
            mode_entry_time=current_time,
        )

        self._robot_transitions[robot_id] = deque(maxlen=self.config.max_transitions_per_robot)

        self._time_in_state[robot_id] = {}

        self.logger.info(f"Registered robot for tracking: {robot_id}")

    def unregister_robot(self, robot_id: str):
        """
        Unregister a robot from state tracking.

        Args:
            robot_id: Robot identifier
        """
        if robot_id in self._robot_states:
            # Record final state duration
            snapshot = self._robot_states[robot_id]
            self._accumulate_time_in_state(
                robot_id, snapshot.operational_state.value, snapshot.time_in_state_s()
            )

            del self._robot_states[robot_id]
            self.logger.info(f"Unregistered robot from tracking: {robot_id}")

    # =========================================================================
    # STATE UPDATES
    # =========================================================================

    def update_operational_state(
        self,
        robot_id: str,
        new_state: RobotOperationalState,
        reason: Optional[str] = None,
        triggered_by: str = "system",
    ):
        """
        Update robot's operational state.

        Args:
            robot_id: Robot identifier
            new_state: New operational state
            reason: Reason for state change
            triggered_by: What triggered the change
        """
        if not self.config.track_operational_changes:
            return

        if robot_id not in self._robot_states:
            self.register_robot(robot_id)

        snapshot = self._robot_states[robot_id]
        old_state = snapshot.operational_state

        if old_state == new_state:
            # Just update timestamp
            snapshot.last_update = time.time()
            return

        # Record transition
        current_time = time.time()
        duration = current_time - snapshot.state_entry_time

        transition = StateTransition(
            robot_id=robot_id,
            timestamp=current_time,
            from_state=old_state.value,
            to_state=new_state.value,
            state_type="operational",
            duration_in_previous_s=duration,
            reason=reason,
            triggered_by=triggered_by,
        )

        self._record_transition(robot_id, transition)

        # Update time-in-state
        self._accumulate_time_in_state(robot_id, old_state.value, duration)

        # Update snapshot
        snapshot.operational_state = new_state
        snapshot.state_entry_time = current_time
        snapshot.last_update = current_time
        snapshot.commands_since_state_change = 0

        self.logger.info(f"State change: {robot_id} {old_state.value} -> {new_state.value}")

    def update_mode(
        self,
        robot_id: str,
        new_mode: ControlMode,
        reason: Optional[str] = None,
        triggered_by: str = "system",
    ):
        """
        Update robot's control mode.

        Args:
            robot_id: Robot identifier
            new_mode: New control mode
            reason: Reason for mode change
            triggered_by: What triggered the change
        """
        if not self.config.track_mode_changes:
            return

        if robot_id not in self._robot_states:
            self.register_robot(robot_id)

        snapshot = self._robot_states[robot_id]
        old_mode = snapshot.control_mode

        if old_mode == new_mode:
            snapshot.last_update = time.time()
            return

        current_time = time.time()
        duration = current_time - snapshot.mode_entry_time

        transition = StateTransition(
            robot_id=robot_id,
            timestamp=current_time,
            from_state=old_mode.value,
            to_state=new_mode.value,
            state_type="mode",
            duration_in_previous_s=duration,
            reason=reason,
            triggered_by=triggered_by,
        )

        self._record_transition(robot_id, transition)

        # Update snapshot
        snapshot.control_mode = new_mode
        snapshot.mode_entry_time = current_time
        snapshot.last_update = current_time

        self.logger.info(f"Mode change: {robot_id} {old_mode.value} -> {new_mode.value}")

    def update_status(self, robot_id: str, new_status: RobotStatus, reason: Optional[str] = None):
        """
        Update robot's status.

        Args:
            robot_id: Robot identifier
            new_status: New robot status
            reason: Reason for status change
        """
        if not self.config.track_status_changes:
            return

        if robot_id not in self._robot_states:
            self.register_robot(robot_id)

        snapshot = self._robot_states[robot_id]
        old_status = snapshot.robot_status

        if old_status == new_status:
            snapshot.last_update = time.time()
            return

        current_time = time.time()

        transition = StateTransition(
            robot_id=robot_id,
            timestamp=current_time,
            from_state=old_status.name,
            to_state=new_status.name,
            state_type="status",
            duration_in_previous_s=0,  # Not tracking status duration
            reason=reason,
            triggered_by="system",
        )

        self._record_transition(robot_id, transition)

        snapshot.robot_status = new_status
        snapshot.last_update = current_time

    def record_heartbeat(self, robot_id: str):
        """
        Record robot heartbeat to prevent stale detection.

        Args:
            robot_id: Robot identifier
        """
        if robot_id not in self._robot_states:
            return

        snapshot = self._robot_states[robot_id]
        snapshot.last_update = time.time()

        # Clear stale flag if set
        if snapshot.is_stale:
            snapshot.is_stale = False
            snapshot.stale_since = None
            self.logger.info(f"Robot {robot_id} no longer stale")

    def record_command(self, robot_id: str):
        """
        Record that a command was received for a robot.

        Args:
            robot_id: Robot identifier
        """
        if robot_id not in self._robot_states:
            return

        snapshot = self._robot_states[robot_id]
        snapshot.last_command_time = time.time()
        snapshot.commands_since_state_change += 1
        snapshot.last_update = time.time()

    # =========================================================================
    # TRANSITION MANAGEMENT
    # =========================================================================

    def _record_transition(self, robot_id: str, transition: StateTransition):
        """Record a state transition."""
        # Add to global history
        self._transitions.append(transition)

        # Add to robot-specific history
        if robot_id in self._robot_transitions:
            self._robot_transitions[robot_id].append(transition)

        # Update stats
        self._stats["total_transitions"] += 1
        self._stats["transitions_by_type"][transition.state_type] += 1

        # Notify callbacks
        for callback in self._state_change_callbacks:
            try:
                callback(robot_id, transition)
            except Exception as e:
                self.logger.error(f"State change callback error: {e}")

    def _accumulate_time_in_state(self, robot_id: str, state: str, duration: float):
        """Accumulate time spent in a state."""
        if robot_id not in self._time_in_state:
            self._time_in_state[robot_id] = {}

        current = self._time_in_state[robot_id].get(state, 0.0)
        self._time_in_state[robot_id][state] = current + duration

    # =========================================================================
    # STALE DETECTION
    # =========================================================================

    def check_stale_robots(self) -> List[str]:
        """
        Check for and mark stale robots.

        Returns:
            List of newly stale robot IDs
        """
        current_time = time.time()
        newly_stale = []

        for robot_id, snapshot in self._robot_states.items():
            elapsed = current_time - snapshot.last_update

            if elapsed > self.config.stale_threshold_s:
                if not snapshot.is_stale:
                    snapshot.is_stale = True
                    snapshot.stale_since = current_time
                    newly_stale.append(robot_id)
                    self._stats["stale_detections"] += 1

                    self.logger.warning(
                        f"Robot {robot_id} is stale " f"(no update for {elapsed:.1f}s)"
                    )

        return newly_stale

    def get_stale_robots(self) -> List[str]:
        """Get list of currently stale robots."""
        return [robot_id for robot_id, snapshot in self._robot_states.items() if snapshot.is_stale]

    def is_robot_stale(self, robot_id: str) -> bool:
        """Check if a specific robot is stale."""
        if robot_id not in self._robot_states:
            return True  # Unknown robot is considered stale
        return self._robot_states[robot_id].is_stale

    # =========================================================================
    # QUERY METHODS
    # =========================================================================

    def get_robot_state(self, robot_id: str) -> Optional[RobotStateSnapshot]:
        """Get current state snapshot for a robot."""
        return self._robot_states.get(robot_id)

    def get_all_robot_states(self) -> Dict[str, RobotStateSnapshot]:
        """Get state snapshots for all robots."""
        return self._robot_states.copy()

    def get_transitions(
        self,
        robot_id: Optional[str] = None,
        state_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[StateTransition]:
        """
        Get state transitions.

        Args:
            robot_id: Filter by robot (None for all)
            state_type: Filter by type ("operational", "mode", "status")
            limit: Maximum results

        Returns:
            List of transitions (newest first)
        """
        if robot_id and robot_id in self._robot_transitions:
            source = self._robot_transitions[robot_id]
        else:
            source = self._transitions

        results = []
        for transition in reversed(list(source)):
            if len(results) >= limit:
                break

            if robot_id and transition.robot_id != robot_id:
                continue
            if state_type and transition.state_type != state_type:
                continue

            results.append(transition)

        return results

    def get_time_in_state(self, robot_id: str) -> Dict[str, float]:
        """
        Get accumulated time in each state for a robot.

        Args:
            robot_id: Robot identifier

        Returns:
            Dict mapping state names to seconds spent
        """
        result = self._time_in_state.get(robot_id, {}).copy()

        # Add current state time
        if robot_id in self._robot_states:
            snapshot = self._robot_states[robot_id]
            current_state = snapshot.operational_state.value
            current_time = snapshot.time_in_state_s()
            result[current_state] = result.get(current_state, 0.0) + current_time

        return result

    def get_transition_summary(
        self, robot_id: Optional[str] = None, since: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Get transition summary statistics.

        Args:
            robot_id: Filter by robot
            since: Only transitions after this timestamp

        Returns:
            Summary statistics
        """
        transitions = self.get_transitions(robot_id, limit=10000)

        if since:
            transitions = [t for t in transitions if t.timestamp >= since]

        # Aggregate
        by_type = {"operational": 0, "mode": 0, "status": 0}
        by_state = {}
        total_duration = 0.0

        for t in transitions:
            by_type[t.state_type] += 1
            by_state[t.to_state] = by_state.get(t.to_state, 0) + 1
            total_duration += t.duration_in_previous_s

        return {
            "total_transitions": len(transitions),
            "by_type": by_type,
            "by_state": by_state,
            "total_duration_tracked_s": round(total_duration, 2),
        }

    # =========================================================================
    # CALLBACKS
    # =========================================================================

    def on_state_change(self, callback: StateChangeCallback):
        """Register state change callback."""
        self._state_change_callbacks.append(callback)

    # =========================================================================
    # STATUS
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get tracker status."""
        return {
            "tracked_robots": len(self._robot_states),
            "total_transitions": len(self._transitions),
            "stale_robots": self.get_stale_robots(),
            "robot_states": {
                robot_id: {
                    "operational": snapshot.operational_state.value,
                    "mode": snapshot.control_mode.value,
                    "status": snapshot.robot_status.name,
                    "time_in_state_s": round(snapshot.time_in_state_s(), 1),
                    "is_stale": snapshot.is_stale,
                }
                for robot_id, snapshot in self._robot_states.items()
            },
            "stats": self._stats.copy(),
        }

    def get_health_report(self) -> Dict[str, Any]:
        """Get health report for Webthread."""
        stale_robots = self.get_stale_robots()

        return {
            "healthy": len(stale_robots) == 0,
            "tracked_robots": len(self._robot_states),
            "stale_robot_count": len(stale_robots),
            "stale_robots": stale_robots,
            "total_transitions": self._stats["total_transitions"],
        }
