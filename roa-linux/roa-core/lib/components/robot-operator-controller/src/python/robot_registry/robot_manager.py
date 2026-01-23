"""
Robot Manager - Multi-robot coordination and registry for ROC.

Manages:
- Robot registration and lifecycle
- Multi-robot selection and coordination
- Broadcast operations (e.g., emergency stop all)
- Robot discovery integration with FTI
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from .robot_state import ControlMode, RobotState, RobotStatus


class RegistrationResult(Enum):
    """Result of robot registration attempt."""

    SUCCESS = auto()
    ALREADY_REGISTERED = auto()
    MAX_ROBOTS_EXCEEDED = auto()
    INVALID_SPEC = auto()
    REGISTRATION_FAILED = auto()


@dataclass
class ManagerConfig:
    """Configuration for RobotManager."""

    max_robots: int = 10
    registration_timeout_ms: int = 30000
    stale_data_threshold_ms: float = 200
    auto_register: bool = True


RobotCallback = Callable[[str, RobotState], None]


class RobotManager:
    """
    Manages multiple robots for the ROC system.

    Provides:
    - Robot registration and unregistration
    - Robot selection (active robot)
    - Multi-robot state queries
    - Broadcast operations
    - Event callbacks for registration changes
    """

    def __init__(self, config: Optional[ManagerConfig] = None):
        """
        Initialize robot manager.

        Args:
            config: Manager configuration.
        """
        self.config = config or ManagerConfig()
        self.logger = logging.getLogger(__name__)

        # Robot storage
        self._robots: Dict[str, RobotState] = {}
        self._selected_robot: Optional[str] = None

        # Pending registrations (waiting for full spec)
        self._pending: Dict[str, float] = {}

        # Callbacks
        self._on_register_callbacks: List[RobotCallback] = []
        self._on_unregister_callbacks: List[RobotCallback] = []
        self._on_select_callbacks: List[RobotCallback] = []

        # Statistics
        self._total_registrations = 0
        self._total_unregistrations = 0

    @property
    def robot_count(self) -> int:
        """Get number of registered robots."""
        return len(self._robots)

    @property
    def selected_robot(self) -> Optional[RobotState]:
        """Get currently selected robot."""
        if self._selected_robot:
            return self._robots.get(self._selected_robot)
        return None

    @property
    def selected_robot_id(self) -> Optional[str]:
        """Get ID of currently selected robot."""
        return self._selected_robot

    def register_robot(
        self, robot_id: str, spec: Optional[Dict[str, Any]] = None
    ) -> Tuple[RegistrationResult, str]:
        """
        Register a new robot.

        Args:
            robot_id: Unique robot identifier.
            spec: FTI robot specification (optional, can be added later).

        Returns:
            Tuple of (result, message).
        """
        # Check if already registered
        if robot_id in self._robots:
            return (
                RegistrationResult.ALREADY_REGISTERED,
                f"Robot {robot_id} is already registered",
            )

        # Check max robots
        if len(self._robots) >= self.config.max_robots:
            return (
                RegistrationResult.MAX_ROBOTS_EXCEEDED,
                f"Maximum robots ({self.config.max_robots}) exceeded",
            )

        # Create robot state
        try:
            if spec:
                robot = RobotState.from_fti_spec(spec)
            else:
                robot = RobotState(robot_id)
                # Mark as pending full spec
                self._pending[robot_id] = time.time()
        except Exception as e:
            self.logger.error(f"Failed to create robot state: {e}")
            return (RegistrationResult.INVALID_SPEC, f"Invalid specification: {e}")

        # Add to registry
        self._robots[robot_id] = robot
        self._total_registrations += 1

        # Auto-select if first robot
        if self._selected_robot is None:
            self._selected_robot = robot_id

        # Notify callbacks
        for callback in self._on_register_callbacks:
            try:
                callback(robot_id, robot)
            except Exception as e:
                self.logger.error(f"Register callback error: {e}")

        self.logger.info(f"Registered robot: {robot_id}")
        return (RegistrationResult.SUCCESS, f"Robot {robot_id} registered")

    def update_robot_spec(self, robot_id: str, spec: Dict[str, Any]) -> bool:
        """
        Update robot with full FTI specification.

        Args:
            robot_id: Robot identifier.
            spec: FTI robot specification.

        Returns:
            True if updated successfully.
        """
        if robot_id not in self._robots:
            # Auto-register if enabled
            if self.config.auto_register:
                result, _ = self.register_robot(robot_id, spec)
                return result == RegistrationResult.SUCCESS
            return False

        # Replace with full-spec robot
        try:
            robot = RobotState.from_fti_spec(spec)
            self._robots[robot_id] = robot

            # Remove from pending
            self._pending.pop(robot_id, None)

            self.logger.info(f"Updated spec for robot: {robot_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to update robot spec: {e}")
            return False

    def unregister_robot(self, robot_id: str) -> bool:
        """
        Unregister a robot.

        Args:
            robot_id: Robot identifier.

        Returns:
            True if unregistered, False if not found.
        """
        if robot_id not in self._robots:
            return False

        robot = self._robots.pop(robot_id)
        self._pending.pop(robot_id, None)
        self._total_unregistrations += 1

        # Update selection if needed
        if self._selected_robot == robot_id:
            self._selected_robot = next(iter(self._robots), None)

        # Notify callbacks
        for callback in self._on_unregister_callbacks:
            try:
                callback(robot_id, robot)
            except Exception as e:
                self.logger.error(f"Unregister callback error: {e}")

        self.logger.info(f"Unregistered robot: {robot_id}")
        return True

    def get_robot(self, robot_id: str) -> Optional[RobotState]:
        """
        Get robot state by ID.

        Args:
            robot_id: Robot identifier.

        Returns:
            RobotState or None if not found.
        """
        return self._robots.get(robot_id)

    def select_robot(self, robot_id: str) -> bool:
        """
        Select a robot as the active robot.

        Args:
            robot_id: Robot identifier.

        Returns:
            True if selected, False if not found.
        """
        if robot_id not in self._robots:
            return False

        old_selection = self._selected_robot
        self._selected_robot = robot_id

        robot = self._robots[robot_id]

        # Notify callbacks
        for callback in self._on_select_callbacks:
            try:
                callback(robot_id, robot)
            except Exception as e:
                self.logger.error(f"Select callback error: {e}")

        self.logger.info(f"Selected robot: {robot_id} (was: {old_selection})")
        return True

    def list_robots(self) -> List[str]:
        """Get list of registered robot IDs."""
        return list(self._robots.keys())

    def get_all_robots(self) -> Dict[str, RobotState]:
        """Get all registered robots."""
        return dict(self._robots)

    def get_all_statuses(self) -> Dict[str, RobotStatus]:
        """Get status of all robots."""
        return {rid: r.status for rid, r in self._robots.items()}

    def get_all_modes(self) -> Dict[str, ControlMode]:
        """Get control mode of all robots."""
        return {rid: r.mode for rid, r in self._robots.items()}

    def broadcast_estop(self, reason: str = "user_requested"):
        """
        Activate emergency stop on all robots.

        Args:
            reason: Reason for emergency stop.
        """
        self.logger.warning(f"Broadcasting E-STOP to all robots: {reason}")

        for robot_id, robot in self._robots.items():
            robot.set_estop(True)
            self.logger.info(f"E-STOP activated on {robot_id}")

    def broadcast_estop_clear(self) -> List[str]:
        """
        Clear emergency stop on all robots.

        Returns:
            List of robot IDs that were cleared.
        """
        cleared = []

        for robot_id, robot in self._robots.items():
            if robot.safety.estop_active:
                robot.set_estop(False)
                cleared.append(robot_id)
                self.logger.info(f"E-STOP cleared on {robot_id}")

        return cleared

    def update_joint_states(self, robot_id: str, joint_states: Dict[str, Any]) -> bool:
        """
        Update joint states for a robot from DIMC.

        Args:
            robot_id: Robot identifier.
            joint_states: DIMC joint states message.

        Returns:
            True if updated, False if robot not found.
        """
        robot = self._robots.get(robot_id)
        if not robot:
            return False

        robot.update_from_dimc_joints(joint_states)
        return True

    def update_obstacles(self, robot_id: str, obstacle_data: Dict[str, Any]) -> bool:
        """
        Update obstacle information for a robot from DIMC.

        Args:
            robot_id: Robot identifier.
            obstacle_data: DIMC obstacle data.

        Returns:
            True if updated, False if robot not found.
        """
        robot = self._robots.get(robot_id)
        if not robot:
            return False

        robot.update_from_dimc_obstacles(obstacle_data)
        return True

    def update_boundaries(self, robot_id: str, boundary_data: Dict[str, Any]) -> bool:
        """
        Update boundary status for a robot from DIMC.

        Args:
            robot_id: Robot identifier.
            boundary_data: DIMC boundary data.

        Returns:
            True if updated, False if robot not found.
        """
        robot = self._robots.get(robot_id)
        if not robot:
            return False

        robot.update_from_dimc_boundaries(boundary_data)
        return True

    def get_robots_by_status(self, status: RobotStatus) -> List[str]:
        """Get robot IDs with specific status."""
        return [rid for rid, robot in self._robots.items() if robot.status == status]

    def get_robots_by_mode(self, mode: ControlMode) -> List[str]:
        """Get robot IDs with specific control mode."""
        return [rid for rid, robot in self._robots.items() if robot.mode == mode]

    def get_stale_robots(self) -> List[str]:
        """Get robot IDs with stale data."""
        threshold = self.config.stale_data_threshold_ms
        return [rid for rid, robot in self._robots.items() if robot.is_data_stale(threshold)]

    def cleanup_pending(self):
        """Remove pending registrations that have timed out."""
        timeout = self.config.registration_timeout_ms / 1000
        now = time.time()

        expired = [rid for rid, timestamp in self._pending.items() if now - timestamp > timeout]

        for robot_id in expired:
            self.logger.warning(f"Pending registration timed out: {robot_id}")
            self.unregister_robot(robot_id)

    def on_register(self, callback: RobotCallback):
        """Register callback for robot registration events."""
        self._on_register_callbacks.append(callback)

    def on_unregister(self, callback: RobotCallback):
        """Register callback for robot unregistration events."""
        self._on_unregister_callbacks.append(callback)

    def on_select(self, callback: RobotCallback):
        """Register callback for robot selection events."""
        self._on_select_callbacks.append(callback)

    def get_statistics(self) -> Dict[str, Any]:
        """Get manager statistics."""
        return {
            "registered_robots": len(self._robots),
            "pending_robots": len(self._pending),
            "max_robots": self.config.max_robots,
            "selected_robot": self._selected_robot,
            "total_registrations": self._total_registrations,
            "total_unregistrations": self._total_unregistrations,
            "stale_robots": len(self.get_stale_robots()),
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get summary for IPC state updates."""
        return {
            "robot_count": len(self._robots),
            "selected_robot": self._selected_robot,
            "robots": [robot.get_state_summary() for robot in self._robots.values()],
        }
