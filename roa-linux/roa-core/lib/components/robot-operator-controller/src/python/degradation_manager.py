"""
Degradation Manager - Graceful degradation orchestration for ROC.

Manages capability degradation when dependencies fail:
- DIMC failure: Disable ADM, force RPM mode
- COMC failure: Disable evasion, stay on current path
- FTI failure: Reject new robot registrations
- UE5 failure: Queue commands for reconnect

Based on ROC_CRITICAL_ANALYSIS.md Gap #5.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set

from .control_modes.mode_manager import ControlMode


class DegradationLevel(Enum):
    """System degradation levels."""

    NOMINAL = auto()  # All systems operational
    DEGRADED = auto()  # Some non-critical features disabled
    LIMITED = auto()  # Only essential features available
    MINIMAL = auto()  # Safety-only mode
    EMERGENCY = auto()  # E-Stop triggered, no operations


class Capability(Enum):
    """System capabilities that can be degraded."""

    ADM_MODE = "adm_mode"  # Autonomous driving mode
    EVASION = "evasion"  # Multi-robot evasion paths
    PATH_PLANNING = "path_planning"  # Advanced path planning
    NEW_ROBOTS = "new_robots"  # New robot registration
    UE5_COMMANDS = "ue5_commands"  # Live command execution
    SPATIAL_DATA = "spatial_data"  # Obstacle/boundary data
    MULTI_ROBOT = "multi_robot"  # Fleet coordination
    TELEMETRY = "telemetry"  # External reporting


@dataclass
class DegradationRule:
    """Rule for degrading capability on dependency failure."""

    dependency: str  # e.g., "dimc", "comc"
    capability: Capability  # Capability to disable
    fallback_action: Optional[str]  # Action to take (e.g., "force_rpm")
    restore_delay_s: float = 5.0  # Delay before re-enabling after recovery
    critical: bool = False  # If True, trigger higher degradation


@dataclass
class DependencyState:
    """State of a monitored dependency."""

    name: str
    healthy: bool = True
    last_healthy: float = 0.0
    failure_count: int = 0
    in_recovery: bool = False


@dataclass
class DegradationManagerConfig:
    """Configuration for DegradationManager."""

    # Degradation rules
    rules: List[DegradationRule] = field(default_factory=list)

    # Recovery settings
    recovery_check_interval_s: float = 1.0
    max_recovery_attempts: int = 3
    recovery_backoff_s: float = 5.0

    # Safety settings
    force_rpm_on_critical: bool = True
    queue_commands_on_ue5_failure: bool = True
    max_queued_commands: int = 100


DegradationCallback = Callable[[Capability, bool], None]  # capability, enabled
LevelChangeCallback = Callable[[DegradationLevel, DegradationLevel], None]


class DegradationManager:
    """
    Orchestrates graceful degradation when dependencies fail.

    Responsibilities:
    - Track dependency health status
    - Apply degradation rules when dependencies fail
    - Manage capability enable/disable
    - Queue commands during outages
    - Coordinate recovery when dependencies return

    Usage:
        manager = DegradationManager()

        # Register callbacks
        manager.on_capability_change(handle_capability_change)

        # Report dependency failure
        manager.on_dependency_failure("dimc")
        # -> ADM mode disabled, force RPM

        # Report recovery
        manager.on_dependency_recovered("dimc")
        # -> After delay, ADM mode re-enabled
    """

    # Default degradation rules
    DEFAULT_RULES = [
        DegradationRule(
            dependency="dimc",
            capability=Capability.ADM_MODE,
            fallback_action="force_rpm",
            restore_delay_s=5.0,
            critical=True,
        ),
        DegradationRule(
            dependency="dimc",
            capability=Capability.SPATIAL_DATA,
            fallback_action=None,
            restore_delay_s=2.0,
            critical=True,
        ),
        DegradationRule(
            dependency="comc",
            capability=Capability.EVASION,
            fallback_action="use_local_path",
            restore_delay_s=5.0,
            critical=False,
        ),
        DegradationRule(
            dependency="comc",
            capability=Capability.MULTI_ROBOT,
            fallback_action=None,
            restore_delay_s=5.0,
            critical=False,
        ),
        DegradationRule(
            dependency="fti",
            capability=Capability.NEW_ROBOTS,
            fallback_action=None,
            restore_delay_s=10.0,
            critical=False,
        ),
        DegradationRule(
            dependency="ue5",
            capability=Capability.UE5_COMMANDS,
            fallback_action="queue_commands",
            restore_delay_s=2.0,
            critical=True,
        ),
    ]

    def __init__(
        self,
        config: Optional[DegradationManagerConfig] = None,
        mode_manager: Optional[Any] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize DegradationManager.

        Args:
            config: Manager configuration
            mode_manager: Reference to ModeManager for forcing RPM
            logger: Logger instance
        """
        self.config = config or DegradationManagerConfig()
        self.mode_manager = mode_manager
        self.logger = logger or logging.getLogger(__name__)

        # Use default rules if not specified
        if not self.config.rules:
            self.config.rules = self.DEFAULT_RULES.copy()

        # Current state
        self._level = DegradationLevel.NOMINAL
        self._capabilities: Dict[Capability, bool] = {cap: True for cap in Capability}
        self._dependencies: Dict[str, DependencyState] = {}

        # Command queue for UE5 outages
        self._command_queue: List[Dict[str, Any]] = []

        # Callbacks
        self._capability_callbacks: List[DegradationCallback] = []
        self._level_callbacks: List[LevelChangeCallback] = []

        # Recovery tasks
        self._recovery_tasks: Dict[str, asyncio.Task] = {}

        # Statistics
        self._stats = {
            "degradations_triggered": 0,
            "recoveries_completed": 0,
            "commands_queued": 0,
            "commands_flushed": 0,
            "fallback_actions_taken": 0,
        }

        self.logger.info("DegradationManager initialized")

    # =========================================================================
    # DEPENDENCY FAILURE HANDLING
    # =========================================================================

    def on_dependency_failure(self, dependency: str):
        """
        Handle dependency failure notification.

        Applies all rules for the failed dependency.

        Args:
            dependency: Name of failed dependency (e.g., "dimc", "comc")
        """
        self.logger.warning(f"Dependency failure: {dependency}")

        # Update dependency state
        if dependency not in self._dependencies:
            self._dependencies[dependency] = DependencyState(name=dependency)

        dep_state = self._dependencies[dependency]
        dep_state.healthy = False
        dep_state.failure_count += 1

        # Cancel any pending recovery
        if dependency in self._recovery_tasks:
            self._recovery_tasks[dependency].cancel()
            del self._recovery_tasks[dependency]

        # Apply degradation rules
        critical_failure = False

        for rule in self.config.rules:
            if rule.dependency != dependency:
                continue

            # Disable capability
            if self._capabilities.get(rule.capability, False):
                self._disable_capability(rule.capability)
                self._stats["degradations_triggered"] += 1

            # Execute fallback action
            if rule.fallback_action:
                self._execute_fallback(rule.fallback_action, dependency)

            if rule.critical:
                critical_failure = True

        # Update degradation level
        self._update_degradation_level(critical_failure)

    def on_dependency_recovered(self, dependency: str):
        """
        Handle dependency recovery notification.

        Schedules capability restoration after delay.

        Args:
            dependency: Name of recovered dependency
        """
        self.logger.info(f"Dependency recovered: {dependency}")

        if dependency not in self._dependencies:
            return

        dep_state = self._dependencies[dependency]
        dep_state.healthy = True
        dep_state.last_healthy = time.time()
        dep_state.in_recovery = True

        # Schedule delayed restoration
        self._recovery_tasks[dependency] = asyncio.create_task(self._delayed_restore(dependency))

    async def _delayed_restore(self, dependency: str):
        """Restore capabilities after recovery delay."""
        try:
            # Find max delay for this dependency
            max_delay = 0.0
            for rule in self.config.rules:
                if rule.dependency == dependency:
                    max_delay = max(max_delay, rule.restore_delay_s)

            self.logger.info(f"Waiting {max_delay}s before restoring {dependency} capabilities")
            await asyncio.sleep(max_delay)

            # Check dependency still healthy
            dep_state = self._dependencies.get(dependency)
            if not dep_state or not dep_state.healthy:
                self.logger.warning(f"Dependency {dependency} failed again during recovery")
                return

            # Restore capabilities
            for rule in self.config.rules:
                if rule.dependency == dependency:
                    self._enable_capability(rule.capability)

            dep_state.in_recovery = False
            dep_state.failure_count = 0
            self._stats["recoveries_completed"] += 1

            # Update degradation level
            self._update_degradation_level(False)

            # Flush queued commands if UE5 recovered
            if dependency == "ue5" and self._command_queue:
                await self._flush_command_queue()

        except asyncio.CancelledError:
            self.logger.info(f"Recovery cancelled for {dependency}")

    # =========================================================================
    # CAPABILITY MANAGEMENT
    # =========================================================================

    def _disable_capability(self, capability: Capability):
        """Disable a capability and notify callbacks."""
        if not self._capabilities.get(capability, False):
            return  # Already disabled

        self.logger.warning(f"Disabling capability: {capability.value}")
        self._capabilities[capability] = False

        for callback in self._capability_callbacks:
            try:
                callback(capability, False)
            except Exception as e:
                self.logger.error(f"Capability callback error: {e}")

    def _enable_capability(self, capability: Capability):
        """Enable a capability and notify callbacks."""
        if self._capabilities.get(capability, False):
            return  # Already enabled

        self.logger.info(f"Enabling capability: {capability.value}")
        self._capabilities[capability] = True

        for callback in self._capability_callbacks:
            try:
                callback(capability, True)
            except Exception as e:
                self.logger.error(f"Capability callback error: {e}")

    def is_capability_available(self, capability: Capability) -> bool:
        """Check if capability is currently available."""
        return self._capabilities.get(capability, False)

    def get_available_capabilities(self) -> Set[Capability]:
        """Get set of currently available capabilities."""
        return {cap for cap, enabled in self._capabilities.items() if enabled}

    def get_disabled_capabilities(self) -> Set[Capability]:
        """Get set of currently disabled capabilities."""
        return {cap for cap, enabled in self._capabilities.items() if not enabled}

    # =========================================================================
    # FALLBACK ACTIONS
    # =========================================================================

    def _execute_fallback(self, action: str, dependency: str):
        """Execute a fallback action."""
        self.logger.info(f"Executing fallback action: {action}")
        self._stats["fallback_actions_taken"] += 1

        if action == "force_rpm":
            self._force_rpm_mode()
        elif action == "use_local_path":
            self._use_local_path()
        elif action == "queue_commands":
            pass  # Queue mode enabled by disabling UE5_COMMANDS capability
        else:
            self.logger.warning(f"Unknown fallback action: {action}")

    def _force_rpm_mode(self):
        """Force all robots to RPM mode."""
        if self.mode_manager:
            try:
                # Get all robots and force RPM
                for robot_id in self.mode_manager.list_robots():
                    self.mode_manager.force_mode(robot_id, ControlMode.RPM)
                self.logger.warning("Forced all robots to RPM mode")
            except Exception as e:
                self.logger.error(f"Failed to force RPM mode: {e}")
        else:
            self.logger.warning("Cannot force RPM mode - mode_manager not available")

    def _use_local_path(self):
        """Switch to local path planning (no COMC coordination)."""
        # This would integrate with path planning module
        self.logger.info("Switched to local path planning")

    # =========================================================================
    # COMMAND QUEUE
    # =========================================================================

    def queue_command(self, command: Dict[str, Any]) -> bool:
        """
        Queue a command for later execution.

        Used when UE5 connection is down.

        Args:
            command: Command data to queue

        Returns:
            True if queued, False if queue full
        """
        if len(self._command_queue) >= self.config.max_queued_commands:
            self.logger.warning("Command queue full, dropping command")
            return False

        command["queued_at"] = time.time()
        self._command_queue.append(command)
        self._stats["commands_queued"] += 1
        return True

    async def _flush_command_queue(self):
        """Flush queued commands after UE5 recovery."""
        if not self._command_queue:
            return

        self.logger.info(f"Flushing {len(self._command_queue)} queued commands")

        # This would integrate with IPC handler
        flushed = len(self._command_queue)
        self._command_queue.clear()
        self._stats["commands_flushed"] += flushed

    def get_queue_depth(self) -> int:
        """Get current command queue depth."""
        return len(self._command_queue)

    # =========================================================================
    # DEGRADATION LEVEL
    # =========================================================================

    def _update_degradation_level(self, critical_failure: bool):
        """Update overall degradation level."""
        old_level = self._level

        # Count disabled capabilities
        disabled_count = len(self.get_disabled_capabilities())
        critical_disabled = not self._capabilities.get(
            Capability.ADM_MODE, True
        ) or not self._capabilities.get(Capability.SPATIAL_DATA, True)

        # Determine new level
        if disabled_count == 0:
            new_level = DegradationLevel.NOMINAL
        elif disabled_count <= 2 and not critical_disabled:
            new_level = DegradationLevel.DEGRADED
        elif disabled_count <= 4 or critical_disabled:
            new_level = DegradationLevel.LIMITED
        else:
            new_level = DegradationLevel.MINIMAL

        if new_level != old_level:
            self._level = new_level
            self.logger.warning(f"Degradation level changed: {old_level.name} -> {new_level.name}")

            for callback in self._level_callbacks:
                try:
                    callback(old_level, new_level)
                except Exception as e:
                    self.logger.error(f"Level change callback error: {e}")

    @property
    def degradation_level(self) -> DegradationLevel:
        """Get current degradation level."""
        return self._level

    def is_nominal(self) -> bool:
        """Check if system is in nominal state."""
        return self._level == DegradationLevel.NOMINAL

    # =========================================================================
    # CALLBACKS
    # =========================================================================

    def on_capability_change(self, callback: DegradationCallback):
        """Register capability change callback."""
        self._capability_callbacks.append(callback)

    def on_level_change(self, callback: LevelChangeCallback):
        """Register level change callback."""
        self._level_callbacks.append(callback)

    def set_mode_manager(self, mode_manager: Any):
        """Set mode manager reference for RPM forcing."""
        self.mode_manager = mode_manager

    # =========================================================================
    # STATUS
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get current degradation status."""
        return {
            "level": self._level.name,
            "is_nominal": self.is_nominal(),
            "capabilities": {cap.value: enabled for cap, enabled in self._capabilities.items()},
            "disabled_capabilities": [cap.value for cap in self.get_disabled_capabilities()],
            "dependencies": {
                name: {
                    "healthy": state.healthy,
                    "failure_count": state.failure_count,
                    "in_recovery": state.in_recovery,
                }
                for name, state in self._dependencies.items()
            },
            "command_queue_depth": len(self._command_queue),
            "stats": self._stats,
        }

    def get_health_report(self) -> Dict[str, Any]:
        """Get health report for Webthread."""
        return {
            "degradation_level": self._level.name,
            "available_capabilities": len(self.get_available_capabilities()),
            "total_capabilities": len(Capability),
            "failed_dependencies": [
                name for name, state in self._dependencies.items() if not state.healthy
            ],
            "queue_depth": len(self._command_queue),
        }
