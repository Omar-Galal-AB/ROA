"""
Mode Manager - Control mode switching for ROC.

Manages transitions between:
- RPM (Remote Position Mode): Manual control via UI/sliders
- ADM (Autonomous Decision Mode): Automated control via planning

Enforces transition rules and safety requirements.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple


class ControlMode(Enum):
    """Control mode enumeration."""

    RPM = "rpm"  # Remote Position Mode - manual control
    ADM = "adm"  # Autonomous Decision Mode - automated control


class TransitionStatus(Enum):
    """Mode transition result status."""

    SUCCESS = auto()
    ALREADY_IN_MODE = auto()
    ROBOT_NOT_FOUND = auto()
    ROBOT_MOVING = auto()
    EMERGENCY_STOPPED = auto()
    OBSTACLE_TOO_CLOSE = auto()
    TRANSITION_IN_PROGRESS = auto()
    INVALID_TRANSITION = auto()
    SAFETY_CHECK_FAILED = auto()


@dataclass
class ModeTransitionResult:
    """Result of a mode transition attempt."""

    status: TransitionStatus
    robot_id: str
    from_mode: Optional[ControlMode]
    to_mode: ControlMode
    message: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def success(self) -> bool:
        """Check if transition was successful."""
        return self.status == TransitionStatus.SUCCESS

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "status": self.status.name,
            "robot_id": self.robot_id,
            "from_mode": self.from_mode.value if self.from_mode else None,
            "to_mode": self.to_mode.value,
            "message": self.message,
            "timestamp": self.timestamp,
        }


@dataclass
class ModeManagerConfig:
    """Configuration for ModeManager."""

    # Default mode for new robots
    default_mode: ControlMode = ControlMode.RPM

    # Transition requirements
    require_stop_for_transition: bool = True
    min_obstacle_distance_for_adm: float = 50.0  # cm

    # Timeout for transition completion
    transition_timeout_ms: int = 5000

    # E-Stop requirements
    require_rpm_for_estop_clear: bool = True


ModeCallback = Callable[[str, ControlMode, ControlMode], None]


class ModeManager:
    """
    Manages control modes for robots.

    Provides:
    - Mode tracking per robot
    - Mode transition validation
    - Transition callbacks
    - E-Stop interaction
    """

    def __init__(self, config: Optional[ModeManagerConfig] = None):
        """
        Initialize mode manager.

        Args:
            config: Manager configuration.
        """
        self.config = config or ModeManagerConfig()
        self.logger = logging.getLogger(__name__)

        # Per-robot mode tracking
        self._modes: Dict[str, ControlMode] = {}

        # Per-robot E-Stop state
        self._estop_active: Dict[str, bool] = {}

        # Transitions in progress
        self._transitions_in_progress: Dict[str, float] = {}

        # Callbacks
        self._on_mode_change_callbacks: List[ModeCallback] = []

        # Robot state provider (for checking if robot is moving, etc.)
        self._robot_state_provider: Optional[Callable[[str], Dict[str, Any]]] = None

        # Statistics
        self._total_transitions = 0
        self._failed_transitions = 0

    def set_robot_state_provider(self, provider: Callable[[str], Dict[str, Any]]):
        """
        Set the robot state provider function.

        Args:
            provider: Function that returns robot state dict given robot_id.
        """
        self._robot_state_provider = provider

    def register_robot(self, robot_id: str, initial_mode: Optional[ControlMode] = None):
        """
        Register a robot with initial mode.

        Args:
            robot_id: Robot identifier.
            initial_mode: Initial control mode (uses default if None).
        """
        mode = initial_mode or self.config.default_mode
        self._modes[robot_id] = mode
        self._estop_active[robot_id] = False
        self.logger.info(f"Registered robot {robot_id} with mode {mode.value}")

    def unregister_robot(self, robot_id: str):
        """Unregister a robot."""
        self._modes.pop(robot_id, None)
        self._estop_active.pop(robot_id, None)
        self._transitions_in_progress.pop(robot_id, None)

    def get_mode(self, robot_id: str) -> Optional[ControlMode]:
        """
        Get current mode for a robot.

        Args:
            robot_id: Robot identifier.

        Returns:
            Current mode or None if robot not registered.
        """
        return self._modes.get(robot_id)

    def get_all_modes(self) -> Dict[str, ControlMode]:
        """Get modes for all robots."""
        return dict(self._modes)

    def request_transition(
        self, robot_id: str, new_mode: ControlMode, force: bool = False
    ) -> ModeTransitionResult:
        """
        Request a mode transition for a robot.

        Args:
            robot_id: Robot identifier.
            new_mode: Target control mode.
            force: If True, bypass some safety checks.

        Returns:
            ModeTransitionResult with status.
        """
        # Check robot exists
        current_mode = self._modes.get(robot_id)
        if current_mode is None:
            return ModeTransitionResult(
                status=TransitionStatus.ROBOT_NOT_FOUND,
                robot_id=robot_id,
                from_mode=None,
                to_mode=new_mode,
                message=f"Robot {robot_id} not registered",
            )

        # Check if already in mode
        if current_mode == new_mode:
            return ModeTransitionResult(
                status=TransitionStatus.ALREADY_IN_MODE,
                robot_id=robot_id,
                from_mode=current_mode,
                to_mode=new_mode,
                message=f"Already in {new_mode.value} mode",
            )

        # Check if transition in progress
        if robot_id in self._transitions_in_progress:
            elapsed = time.time() - self._transitions_in_progress[robot_id]
            if elapsed < self.config.transition_timeout_ms / 1000:
                return ModeTransitionResult(
                    status=TransitionStatus.TRANSITION_IN_PROGRESS,
                    robot_id=robot_id,
                    from_mode=current_mode,
                    to_mode=new_mode,
                    message="Transition already in progress",
                )
            else:
                # Timeout, clear it
                del self._transitions_in_progress[robot_id]

        # Check E-Stop
        if self._estop_active.get(robot_id, False):
            return ModeTransitionResult(
                status=TransitionStatus.EMERGENCY_STOPPED,
                robot_id=robot_id,
                from_mode=current_mode,
                to_mode=new_mode,
                message="Cannot change mode while E-Stop active",
            )

        # Check robot state if provider available
        if not force and self._robot_state_provider:
            state = self._robot_state_provider(robot_id)

            # Check if robot is moving
            if self.config.require_stop_for_transition:
                if state.get("is_moving", False):
                    self._failed_transitions += 1
                    return ModeTransitionResult(
                        status=TransitionStatus.ROBOT_MOVING,
                        robot_id=robot_id,
                        from_mode=current_mode,
                        to_mode=new_mode,
                        message="Robot must be stopped for mode change",
                    )

            # Check obstacle distance for RPM -> ADM
            if current_mode == ControlMode.RPM and new_mode == ControlMode.ADM:
                obstacle_distance = state.get("obstacle_distance", float("inf"))
                if obstacle_distance < self.config.min_obstacle_distance_for_adm:
                    self._failed_transitions += 1
                    return ModeTransitionResult(
                        status=TransitionStatus.OBSTACLE_TOO_CLOSE,
                        robot_id=robot_id,
                        from_mode=current_mode,
                        to_mode=new_mode,
                        message=f"Obstacle too close for ADM ({obstacle_distance:.1f}cm)",
                    )

        # Perform transition
        self._modes[robot_id] = new_mode
        self._total_transitions += 1

        self.logger.info(
            f"Mode transition for {robot_id}: " f"{current_mode.value} -> {new_mode.value}"
        )

        # Notify callbacks
        for callback in self._on_mode_change_callbacks:
            try:
                callback(robot_id, current_mode, new_mode)
            except Exception as e:
                self.logger.error(f"Mode change callback error: {e}")

        return ModeTransitionResult(
            status=TransitionStatus.SUCCESS,
            robot_id=robot_id,
            from_mode=current_mode,
            to_mode=new_mode,
            message=f"Transitioned to {new_mode.value}",
        )

    def toggle_mode(self, robot_id: str) -> ModeTransitionResult:
        """
        Toggle between RPM and ADM modes.

        Args:
            robot_id: Robot identifier.

        Returns:
            ModeTransitionResult with status.
        """
        current = self._modes.get(robot_id)
        if current is None:
            return ModeTransitionResult(
                status=TransitionStatus.ROBOT_NOT_FOUND,
                robot_id=robot_id,
                from_mode=None,
                to_mode=ControlMode.RPM,
                message=f"Robot {robot_id} not registered",
            )

        new_mode = ControlMode.ADM if current == ControlMode.RPM else ControlMode.RPM
        return self.request_transition(robot_id, new_mode)

    def set_estop(self, robot_id: str, active: bool) -> bool:
        """
        Set E-Stop state for a robot.

        Args:
            robot_id: Robot identifier.
            active: Whether E-Stop is active.

        Returns:
            True if state changed, False if robot not found.
        """
        if robot_id not in self._modes:
            return False

        self._estop_active[robot_id] = active

        if active:
            self.logger.warning(f"E-STOP activated for {robot_id}")
        else:
            self.logger.info(f"E-STOP cleared for {robot_id}")

        return True

    def clear_estop(self, robot_id: str) -> ModeTransitionResult:
        """
        Clear E-Stop for a robot.

        Args:
            robot_id: Robot identifier.

        Returns:
            ModeTransitionResult (transitions to RPM if configured).
        """
        if robot_id not in self._modes:
            return ModeTransitionResult(
                status=TransitionStatus.ROBOT_NOT_FOUND,
                robot_id=robot_id,
                from_mode=None,
                to_mode=ControlMode.RPM,
                message=f"Robot {robot_id} not registered",
            )

        current_mode = self._modes[robot_id]

        # Check if need to be in RPM
        if self.config.require_rpm_for_estop_clear and current_mode != ControlMode.RPM:
            return ModeTransitionResult(
                status=TransitionStatus.INVALID_TRANSITION,
                robot_id=robot_id,
                from_mode=current_mode,
                to_mode=ControlMode.RPM,
                message="Must be in RPM mode to clear E-STOP",
            )

        self._estop_active[robot_id] = False
        self.logger.info(f"E-STOP cleared for {robot_id}")

        return ModeTransitionResult(
            status=TransitionStatus.SUCCESS,
            robot_id=robot_id,
            from_mode=current_mode,
            to_mode=current_mode,
            message="E-STOP cleared",
        )

    def is_estop_active(self, robot_id: str) -> bool:
        """Check if E-Stop is active for a robot."""
        return self._estop_active.get(robot_id, False)

    def get_robots_in_mode(self, mode: ControlMode) -> List[str]:
        """Get list of robots in a specific mode."""
        return [rid for rid, m in self._modes.items() if m == mode]

    def get_rpm_robots(self) -> List[str]:
        """Get list of robots in RPM mode."""
        return self.get_robots_in_mode(ControlMode.RPM)

    def get_adm_robots(self) -> List[str]:
        """Get list of robots in ADM mode."""
        return self.get_robots_in_mode(ControlMode.ADM)

    def on_mode_change(self, callback: ModeCallback):
        """Register callback for mode change events."""
        self._on_mode_change_callbacks.append(callback)

    def get_statistics(self) -> Dict[str, Any]:
        """Get mode manager statistics."""
        return {
            "total_robots": len(self._modes),
            "rpm_robots": len(self.get_rpm_robots()),
            "adm_robots": len(self.get_adm_robots()),
            "estop_active": sum(1 for v in self._estop_active.values() if v),
            "total_transitions": self._total_transitions,
            "failed_transitions": self._failed_transitions,
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get summary for IPC."""
        return {
            "modes": {rid: m.value for rid, m in self._modes.items()},
            "estop": {rid: v for rid, v in self._estop_active.items() if v},
        }
