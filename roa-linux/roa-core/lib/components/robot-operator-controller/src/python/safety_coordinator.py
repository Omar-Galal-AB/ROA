"""
Safety Coordinator - Integrates all safety subsystems for ROC.

Bridges:
- SafetyManager (safety levels, violations)
- LimitChecker (joint limits)
- EStopRecoveryManager (E-Stop recovery)
- Obstacle/boundary monitoring from DIMC

This was identified as a critical gap - SafetyManager existed but was orphaned.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

from .safety.safety_manager import SafetyManager, SafetyLevel, SafetyViolation
from .safety.limit_checker import LimitChecker, LimitCheckResult, LimitStatus
from .estop_recovery import EStopRecoveryManager, EStopType, RecoveryPhase, RecoveryConfig


class SafetyState(Enum):
    """Overall safety system state."""
    NOMINAL = auto()          # All systems normal
    WARNING = auto()          # Warning conditions present
    VIOLATION = auto()        # Safety violation detected
    ESTOP_ACTIVE = auto()     # Emergency stop active
    RECOVERING = auto()       # Recovery in progress
    DEGRADED = auto()         # Operating in degraded mode


@dataclass
class SafetyStatus:
    """Aggregated safety status for a robot."""
    robot_id: str
    state: SafetyState
    safety_level: SafetyLevel
    estop_active: bool
    obstacles_clear: bool
    limits_ok: bool
    within_bounds: bool
    closest_obstacle_cm: float
    active_violations: List[str]
    warning_count: int
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "robot_id": self.robot_id,
            "state": self.state.name,
            "safety_level": self.safety_level.value,
            "estop_active": self.estop_active,
            "obstacles_clear": self.obstacles_clear,
            "limits_ok": self.limits_ok,
            "within_bounds": self.within_bounds,
            "closest_obstacle_cm": self.closest_obstacle_cm,
            "active_violations": self.active_violations,
            "warning_count": self.warning_count,
            "timestamp": self.timestamp
        }


@dataclass
class SafetyCoordinatorConfig:
    """Configuration for safety coordinator."""
    # Obstacle thresholds (cm)
    obstacle_warning_distance: float = 100.0
    obstacle_slow_distance: float = 50.0
    obstacle_stop_distance: float = 10.0
    
    # Boundary margin (cm)
    boundary_warning_margin: float = 20.0
    boundary_stop_margin: float = 5.0
    
    # Velocity reduction for obstacles
    obstacle_velocity_reduction: Dict[float, float] = field(default_factory=lambda: {
        100.0: 0.8,  # At 100cm: 80% velocity
        50.0: 0.5,   # At 50cm: 50% velocity
        25.0: 0.2,   # At 25cm: 20% velocity
        10.0: 0.0,   # At 10cm: stop
    })
    
    # Auto E-Stop triggers
    auto_estop_on_collision: bool = True
    auto_estop_on_limit_exceed: bool = True
    auto_estop_on_boundary_violation: bool = True
    
    # Monitoring rate
    safety_check_rate_hz: float = 60.0
    
    # Recovery configuration
    recovery: RecoveryConfig = field(default_factory=RecoveryConfig)


class SafetyCoordinator:
    """
    Coordinates all safety subsystems for ROC.
    
    Responsibilities:
    - Aggregate safety status from all sources
    - Trigger E-Stops on violations
    - Manage recovery process
    - Calculate velocity reductions
    - Report safety status to coordinator
    """
    
    def __init__(
        self,
        limit_checker: LimitChecker,
        config: Optional[SafetyCoordinatorConfig] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize safety coordinator.
        
        Args:
            limit_checker: Limit checker instance
            config: Configuration
            logger: Logger instance
        """
        self.config = config or SafetyCoordinatorConfig()
        self.logger = logger or logging.getLogger(__name__)
        
        # Subsystems
        self.limit_checker = limit_checker
        self.safety_manager = SafetyManager()
        self.recovery_manager = EStopRecoveryManager(
            config=self.config.recovery,
            logger=self.logger
        )
        
        # Per-robot state
        self._robot_safety: Dict[str, SafetyStatus] = {}
        self._obstacle_data: Dict[str, Dict] = {}
        self._boundary_data: Dict[str, Dict] = {}
        
        # Global state
        self._state = SafetyState.NOMINAL
        self._running = False
        self._safety_check_task: Optional[asyncio.Task] = None
        
        # Callbacks
        self._on_estop_triggered: List[Callable[[str, EStopType], None]] = []
        self._on_violation: List[Callable[[str, SafetyViolation, str], None]] = []
        self._on_safety_state_change: List[Callable[[str, SafetyState], None]] = []
        
        # Statistics
        self._total_violations = 0
        self._total_estops = 0
        self._total_recoveries = 0
        
        # Wire up recovery callbacks
        self.recovery_manager.on_phase_change(self._on_recovery_phase_change)
        self.recovery_manager.on_recovery_complete(self._on_recovery_complete)
        
        self.logger.info("SafetyCoordinator initialized")
    
    # =========================================================================
    # Lifecycle
    # =========================================================================
    
    async def start(self):
        """Start safety monitoring."""
        self._running = True
        
        interval = 1.0 / self.config.safety_check_rate_hz
        self._safety_check_task = asyncio.create_task(
            self._safety_check_loop(interval)
        )
        
        self.logger.info("SafetyCoordinator started")
    
    async def stop(self):
        """Stop safety monitoring."""
        self._running = False
        
        if self._safety_check_task:
            self._safety_check_task.cancel()
            try:
                await self._safety_check_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("SafetyCoordinator stopped")
    
    async def _safety_check_loop(self, interval: float):
        """Periodic safety check loop."""
        while self._running:
            try:
                for robot_id in list(self._robot_safety.keys()):
                    await self._check_robot_safety(robot_id)
                
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Safety check error: {e}")
                await asyncio.sleep(interval)
    
    # =========================================================================
    # Robot Registration
    # =========================================================================
    
    def register_robot(self, robot_id: str):
        """Register a robot for safety monitoring."""
        self._robot_safety[robot_id] = SafetyStatus(
            robot_id=robot_id,
            state=SafetyState.NOMINAL,
            safety_level=self.safety_manager.current_level,
            estop_active=False,
            obstacles_clear=True,
            limits_ok=True,
            within_bounds=True,
            closest_obstacle_cm=float('inf'),
            active_violations=[],
            warning_count=0
        )
        
        self.logger.info(f"Registered robot for safety: {robot_id}")
    
    def unregister_robot(self, robot_id: str):
        """Unregister a robot."""
        self._robot_safety.pop(robot_id, None)
        self._obstacle_data.pop(robot_id, None)
        self._boundary_data.pop(robot_id, None)
    
    # =========================================================================
    # Safety Checking
    # =========================================================================
    
    async def _check_robot_safety(self, robot_id: str):
        """Check safety for a single robot."""
        status = self._robot_safety.get(robot_id)
        if not status:
            return
        
        violations = []
        
        # Check obstacles
        obstacle_data = self._obstacle_data.get(robot_id, {})
        closest = obstacle_data.get("closest_distance_cm", float('inf'))
        status.closest_obstacle_cm = closest
        
        if closest < self.config.obstacle_stop_distance:
            status.obstacles_clear = False
            violations.append(f"Obstacle at {closest:.1f}cm")
            
            if self.config.auto_estop_on_collision:
                await self._trigger_estop(
                    robot_id,
                    EStopType.COLLISION_IMMINENT,
                    "obstacle_detection",
                    obstacle_distance=closest
                )
        elif closest < self.config.obstacle_warning_distance:
            status.obstacles_clear = True  # Not blocking, just warning
            status.warning_count += 1
        else:
            status.obstacles_clear = True
        
        # Check boundaries
        boundary_data = self._boundary_data.get(robot_id, {})
        within_bounds = boundary_data.get("within_bounds", True)
        boundary_margin = boundary_data.get("margin_cm", float('inf'))
        
        if not within_bounds:
            status.within_bounds = False
            violations.append("Boundary violation")
            
            if self.config.auto_estop_on_boundary_violation:
                await self._trigger_estop(
                    robot_id,
                    EStopType.LIMIT_EXCEEDED,
                    "boundary_check"
                )
        elif boundary_margin < self.config.boundary_warning_margin:
            status.within_bounds = True
            status.warning_count += 1
        else:
            status.within_bounds = True
        
        # Update status
        status.active_violations = violations
        status.timestamp = time.time()
        
        # Determine overall state
        old_state = status.state
        
        if status.estop_active:
            status.state = SafetyState.ESTOP_ACTIVE
        elif self.recovery_manager.is_estop_active(robot_id):
            status.state = SafetyState.RECOVERING
        elif violations:
            status.state = SafetyState.VIOLATION
        elif status.warning_count > 0:
            status.state = SafetyState.WARNING
        else:
            status.state = SafetyState.NOMINAL
        
        if status.state != old_state:
            self._notify_state_change(robot_id, status.state)
    
    # =========================================================================
    # E-Stop Management
    # =========================================================================
    
    async def _trigger_estop(
        self,
        robot_id: str,
        estop_type: EStopType,
        trigger_source: str,
        obstacle_distance: Optional[float] = None
    ):
        """Trigger E-Stop for a robot."""
        status = self._robot_safety.get(robot_id)
        if not status:
            return
        
        if status.estop_active:
            return  # Already stopped
        
        status.estop_active = True
        status.state = SafetyState.ESTOP_ACTIVE
        self._total_estops += 1
        
        # Record in recovery manager
        self.recovery_manager.trigger_estop(
            robot_id=robot_id,
            estop_type=estop_type,
            trigger_source=trigger_source,
            obstacle_distance=obstacle_distance
        )
        
        # Notify callbacks
        for callback in self._on_estop_triggered:
            try:
                callback(robot_id, estop_type)
            except Exception as e:
                self.logger.error(f"E-Stop callback error: {e}")
        
        self.logger.warning(f"E-Stop triggered for {robot_id}: {estop_type.name}")
    
    def trigger_user_estop(self, robot_id: str, reason: str = "user_requested"):
        """Trigger E-Stop from user/operator request."""
        asyncio.create_task(
            self._trigger_estop(robot_id, EStopType.USER_REQUESTED, reason)
        )
    
    def trigger_global_estop(self, reason: str = "user_requested"):
        """Trigger E-Stop for all robots."""
        for robot_id in self._robot_safety:
            self.trigger_user_estop(robot_id, reason)
    
    async def start_recovery(self, robot_id: str) -> bool:
        """Start E-Stop recovery for a robot."""
        success = await self.recovery_manager.start_recovery(robot_id)
        
        if success:
            self._total_recoveries += 1
        
        return success
    
    def acknowledge_estop(self, robot_id: str):
        """Operator acknowledges E-Stop."""
        self.recovery_manager.acknowledge_estop(robot_id)
    
    # =========================================================================
    # External Updates
    # =========================================================================
    
    def update_obstacle_data(self, robot_id: str, obstacle_data: Dict):
        """
        Update obstacle data from DIMC.
        
        Args:
            robot_id: Robot identifier
            obstacle_data: Dict with closest_distance_cm, obstacles list, etc.
        """
        self._obstacle_data[robot_id] = obstacle_data
        
        # Update safety status
        if robot_id in self._robot_safety:
            closest = obstacle_data.get("closest_distance_cm", float('inf'))
            self._robot_safety[robot_id].closest_obstacle_cm = closest
    
    def update_boundary_data(self, robot_id: str, boundary_data: Dict):
        """
        Update boundary data from DIMC.
        
        Args:
            robot_id: Robot identifier
            boundary_data: Dict with within_bounds, margin_cm, etc.
        """
        self._boundary_data[robot_id] = boundary_data
        
        if robot_id in self._robot_safety:
            within = boundary_data.get("within_bounds", True)
            self._robot_safety[robot_id].within_bounds = within
    
    def check_joint_command(
        self,
        robot_id: str,
        joint_name: str,
        target_position: float
    ) -> LimitCheckResult:
        """
        Check if joint command is within limits.
        
        Args:
            robot_id: Robot identifier
            joint_name: Joint name
            target_position: Target position
            
        Returns:
            LimitCheckResult
        """
        result = self.limit_checker.check_position(robot_id, joint_name, target_position)
        
        if result.status == LimitStatus.EXCEEDED:
            self._total_violations += 1
            
            if self.config.auto_estop_on_limit_exceed:
                asyncio.create_task(
                    self._trigger_estop(
                        robot_id,
                        EStopType.LIMIT_EXCEEDED,
                        f"joint_{joint_name}_limit"
                    )
                )
        
        return result
    
    # =========================================================================
    # Velocity Reduction
    # =========================================================================
    
    def get_velocity_multiplier(self, robot_id: str) -> float:
        """
        Get velocity multiplier based on obstacle proximity.
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            Velocity multiplier (0.0 to 1.0)
        """
        status = self._robot_safety.get(robot_id)
        if not status:
            return 1.0
        
        if status.estop_active:
            return 0.0
        
        closest = status.closest_obstacle_cm
        
        # Get safety level multiplier
        base_mult = self.safety_manager.speed_multiplier
        
        # Apply obstacle-based reduction
        for distance_threshold, velocity_mult in sorted(
            self.config.obstacle_velocity_reduction.items(),
            reverse=True
        ):
            if closest <= distance_threshold:
                return base_mult * velocity_mult
        
        return base_mult
    
    # =========================================================================
    # Safety Level Management
    # =========================================================================
    
    def set_safety_level(self, level: SafetyLevel) -> bool:
        """
        Set safety level for all robots.
        
        Args:
            level: Safety level to set
            
        Returns:
            True if set successfully
        """
        result = self.safety_manager.set_safety_level(level)
        
        if result:
            for status in self._robot_safety.values():
                status.safety_level = level
        
        return result
    
    def get_safety_level(self) -> SafetyLevel:
        """Get current safety level."""
        return self.safety_manager.current_level
    
    # =========================================================================
    # Callbacks
    # =========================================================================
    
    def _on_recovery_phase_change(self, robot_id: str, phase: RecoveryPhase):
        """Handle recovery phase change."""
        if phase == RecoveryPhase.RECOVERED:
            if robot_id in self._robot_safety:
                self._robot_safety[robot_id].estop_active = False
                self._robot_safety[robot_id].state = SafetyState.NOMINAL
    
    def _on_recovery_complete(self, robot_id: str, success: bool):
        """Handle recovery completion."""
        if success:
            self.logger.info(f"Recovery complete for {robot_id}")
            if robot_id in self._robot_safety:
                self._robot_safety[robot_id].estop_active = False
                self._robot_safety[robot_id].state = SafetyState.NOMINAL
        else:
            self.logger.error(f"Recovery failed for {robot_id}")
    
    def _notify_state_change(self, robot_id: str, state: SafetyState):
        """Notify safety state change callbacks."""
        for callback in self._on_safety_state_change:
            try:
                callback(robot_id, state)
            except Exception as e:
                self.logger.error(f"State change callback error: {e}")
    
    # =========================================================================
    # Callback Registration
    # =========================================================================
    
    def on_estop_triggered(self, callback: Callable[[str, EStopType], None]):
        """Register E-Stop triggered callback."""
        self._on_estop_triggered.append(callback)
    
    def on_violation(self, callback: Callable[[str, SafetyViolation, str], None]):
        """Register violation callback."""
        self._on_violation.append(callback)
    
    def on_safety_state_change(self, callback: Callable[[str, SafetyState], None]):
        """Register state change callback."""
        self._on_safety_state_change.append(callback)
    
    # =========================================================================
    # Status
    # =========================================================================
    
    def get_robot_safety_status(self, robot_id: str) -> Optional[SafetyStatus]:
        """Get safety status for a robot."""
        return self._robot_safety.get(robot_id)
    
    def get_all_safety_status(self) -> Dict[str, SafetyStatus]:
        """Get safety status for all robots."""
        return dict(self._robot_safety)
    
    def is_safe_to_operate(self, robot_id: str) -> bool:
        """Check if robot is safe to operate."""
        status = self._robot_safety.get(robot_id)
        if not status:
            return False
        
        return status.state in (SafetyState.NOMINAL, SafetyState.WARNING)
    
    def get_status(self) -> Dict[str, Any]:
        """Get coordinator status."""
        return {
            "state": self._state.name,
            "safety_level": self.safety_manager.current_level.value,
            "robots": {
                rid: status.to_dict()
                for rid, status in self._robot_safety.items()
            },
            "recovery_manager": self.recovery_manager.get_status(),
            "statistics": {
                "total_violations": self._total_violations,
                "total_estops": self._total_estops,
                "total_recoveries": self._total_recoveries
            }
        }
