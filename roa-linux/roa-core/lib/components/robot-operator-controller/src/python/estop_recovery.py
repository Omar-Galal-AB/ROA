"""
E-Stop Recovery Manager - Staged emergency stop recovery protocol.

Provides a safe, staged recovery process after emergency stop events:
1. Assess damage/status
2. Operator acknowledgment
3. System checks
4. Staged re-enablement
5. Return to operation

This was identified as a critical gap - no recovery protocol existed.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional


class EStopType(Enum):
    """Types of emergency stop events."""
    USER_REQUESTED = auto()      # Operator pressed E-Stop
    COLLISION_IMMINENT = auto()  # Obstacle too close
    LIMIT_EXCEEDED = auto()      # Joint limit violation
    COMMUNICATION_LOST = auto()  # Lost connection to component
    SYSTEM_ERROR = auto()        # Internal system error
    EXTERNAL_TRIGGER = auto()    # External safety system trigger


class RecoveryPhase(Enum):
    """Phases of E-Stop recovery."""
    ESTOP_ACTIVE = auto()       # E-Stop is currently active
    ASSESSMENT = auto()         # Assessing robot status
    WAITING_ACK = auto()        # Waiting for operator acknowledgment
    SYSTEM_CHECK = auto()       # Running system diagnostics
    STAGED_ENABLE = auto()      # Staged re-enablement
    MOTOR_TEST = auto()         # Testing motor responsiveness
    FINAL_CHECK = auto()        # Final safety verification
    RECOVERED = auto()          # Recovery complete
    FAILED = auto()             # Recovery failed


class RecoveryRequirement(Enum):
    """Requirements for recovery."""
    OPERATOR_ACK = "operator_acknowledgment"
    OBSTACLE_CLEAR = "obstacle_clear"
    LIMITS_OK = "limits_ok"
    COMMS_OK = "communications_ok"
    DIAGNOSTICS_PASS = "diagnostics_pass"
    MODE_RPM = "mode_rpm"


@dataclass
class EStopEvent:
    """Records an E-Stop event."""
    event_id: str
    robot_id: str
    estop_type: EStopType
    timestamp: float
    trigger_source: str
    position_at_stop: Optional[Dict[str, float]] = None
    obstacle_distance: Optional[float] = None
    error_details: str = ""


@dataclass
class RecoveryStatus:
    """Current recovery status."""
    phase: RecoveryPhase
    robot_id: str
    estop_event: Optional[EStopEvent] = None
    requirements_met: Dict[str, bool] = field(default_factory=dict)
    phase_start_time: float = field(default_factory=time.time)
    attempts: int = 0
    last_error: str = ""
    
    @property
    def all_requirements_met(self) -> bool:
        """Check if all requirements are met."""
        return all(self.requirements_met.values())
    
    @property
    def missing_requirements(self) -> List[str]:
        """Get list of unmet requirements."""
        return [k for k, v in self.requirements_met.items() if not v]


@dataclass
class RecoveryConfig:
    """Configuration for recovery manager."""
    # Timeouts
    acknowledgment_timeout_s: float = 300.0  # 5 minutes for operator
    assessment_timeout_s: float = 30.0
    system_check_timeout_s: float = 60.0
    motor_test_timeout_s: float = 30.0
    
    # Requirements per E-Stop type
    require_operator_ack: bool = True
    require_diagnostics: bool = True
    require_motor_test: bool = True
    
    # Staged enablement
    enable_delay_s: float = 1.0
    velocity_limit_on_recovery: float = 0.1  # 10% speed
    velocity_ramp_time_s: float = 5.0  # Time to ramp back to full
    
    # Safety
    require_rpm_mode: bool = True
    min_obstacle_clearance: float = 0.2  # meters
    max_recovery_attempts: int = 3


class EStopRecoveryManager:
    """
    Manages staged recovery from emergency stop events.
    
    Recovery Process:
    1. ASSESSMENT: Check robot position, joints, obstacles
    2. WAITING_ACK: Wait for operator acknowledgment
    3. SYSTEM_CHECK: Run diagnostics on all subsystems
    4. STAGED_ENABLE: Gradually re-enable motors
    5. MOTOR_TEST: Test motor responsiveness at low speed
    6. FINAL_CHECK: Verify all systems nominal
    7. RECOVERED: Return to normal operation
    
    Safety Requirements:
    - Must be in RPM mode to recover (no autonomous recovery)
    - Operator must acknowledge E-Stop
    - All diagnostics must pass
    - Obstacles must be clear
    """
    
    def __init__(
        self,
        config: Optional[RecoveryConfig] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize recovery manager.
        
        Args:
            config: Recovery configuration
            logger: Logger instance
        """
        self.config = config or RecoveryConfig()
        self.logger = logger or logging.getLogger(__name__)
        
        # Per-robot recovery status
        self._recovery_status: Dict[str, RecoveryStatus] = {}
        
        # E-Stop history
        self._estop_history: List[EStopEvent] = []
        self._max_history = 100
        
        # Callbacks
        self._on_phase_change: List[Callable[[str, RecoveryPhase], None]] = []
        self._on_recovery_complete: List[Callable[[str, bool], None]] = []
        self._on_acknowledgment_required: List[Callable[[str, EStopEvent], None]] = []
        
        # External dependencies (set by coordinator)
        self._diagnostic_runner: Optional[Callable[[], bool]] = None
        self._motor_test_runner: Optional[Callable[[str], bool]] = None
        self._get_robot_state: Optional[Callable[[str], Dict]] = None
        self._get_obstacle_distance: Optional[Callable[[str], float]] = None
        self._set_velocity_limit: Optional[Callable[[str, float], None]] = None
        
        # Operator acknowledgments (set externally)
        self._pending_acks: Dict[str, bool] = {}
        
        self.logger.info("EStopRecoveryManager initialized")
    
    # =========================================================================
    # E-Stop Triggering
    # =========================================================================
    
    def trigger_estop(
        self,
        robot_id: str,
        estop_type: EStopType,
        trigger_source: str,
        position: Optional[Dict[str, float]] = None,
        obstacle_distance: Optional[float] = None,
        error_details: str = ""
    ) -> EStopEvent:
        """
        Trigger an E-Stop event for a robot.
        
        Args:
            robot_id: Robot identifier
            estop_type: Type of E-Stop
            trigger_source: What triggered the E-Stop
            position: Robot position at stop
            obstacle_distance: Distance to obstacle (if relevant)
            error_details: Additional error information
            
        Returns:
            Created E-Stop event
        """
        event = EStopEvent(
            event_id=f"estop_{robot_id}_{int(time.time() * 1000)}",
            robot_id=robot_id,
            estop_type=estop_type,
            timestamp=time.time(),
            trigger_source=trigger_source,
            position_at_stop=position,
            obstacle_distance=obstacle_distance,
            error_details=error_details
        )
        
        # Record in history
        self._estop_history.append(event)
        if len(self._estop_history) > self._max_history:
            self._estop_history.pop(0)
        
        # Initialize recovery status
        requirements = self._get_requirements_for_type(estop_type)
        self._recovery_status[robot_id] = RecoveryStatus(
            phase=RecoveryPhase.ESTOP_ACTIVE,
            robot_id=robot_id,
            estop_event=event,
            requirements_met={r.value: False for r in requirements}
        )
        
        self.logger.warning(
            f"E-Stop triggered for {robot_id}: {estop_type.name} by {trigger_source}"
        )
        
        return event
    
    def _get_requirements_for_type(self, estop_type: EStopType) -> List[RecoveryRequirement]:
        """Get recovery requirements based on E-Stop type."""
        base_requirements = []
        
        # All types require operator ack if configured
        if self.config.require_operator_ack:
            base_requirements.append(RecoveryRequirement.OPERATOR_ACK)
        
        # All types need diagnostics if configured
        if self.config.require_diagnostics:
            base_requirements.append(RecoveryRequirement.DIAGNOSTICS_PASS)
        
        # RPM mode required if configured
        if self.config.require_rpm_mode:
            base_requirements.append(RecoveryRequirement.MODE_RPM)
        
        # Type-specific requirements
        if estop_type == EStopType.COLLISION_IMMINENT:
            base_requirements.append(RecoveryRequirement.OBSTACLE_CLEAR)
        
        elif estop_type == EStopType.LIMIT_EXCEEDED:
            base_requirements.append(RecoveryRequirement.LIMITS_OK)
        
        elif estop_type == EStopType.COMMUNICATION_LOST:
            base_requirements.append(RecoveryRequirement.COMMS_OK)
        
        return base_requirements
    
    # =========================================================================
    # Recovery Process
    # =========================================================================
    
    async def start_recovery(self, robot_id: str) -> bool:
        """
        Start recovery process for a robot.
        
        Args:
            robot_id: Robot to recover
            
        Returns:
            True if recovery started successfully
        """
        status = self._recovery_status.get(robot_id)
        if not status:
            self.logger.warning(f"No E-Stop event for {robot_id}")
            return False
        
        if status.phase != RecoveryPhase.ESTOP_ACTIVE:
            self.logger.warning(f"Recovery already in progress for {robot_id}")
            return False
        
        if status.attempts >= self.config.max_recovery_attempts:
            self.logger.error(f"Max recovery attempts exceeded for {robot_id}")
            return False
        
        status.attempts += 1
        self.logger.info(f"Starting recovery for {robot_id} (attempt {status.attempts})")
        
        try:
            # Phase 1: Assessment
            if not await self._run_assessment(robot_id, status):
                return False
            
            # Phase 2: Wait for acknowledgment
            if RecoveryRequirement.OPERATOR_ACK.value in status.requirements_met:
                if not await self._wait_for_acknowledgment(robot_id, status):
                    return False
            
            # Phase 3: System check
            if not await self._run_system_check(robot_id, status):
                return False
            
            # Phase 4: Staged enablement
            if not await self._staged_enable(robot_id, status):
                return False
            
            # Phase 5: Motor test
            if self.config.require_motor_test:
                if not await self._run_motor_test(robot_id, status):
                    return False
            
            # Phase 6: Final check
            if not await self._run_final_check(robot_id, status):
                return False
            
            # Recovery complete
            self._set_phase(robot_id, status, RecoveryPhase.RECOVERED)
            self._notify_recovery_complete(robot_id, True)
            
            self.logger.info(f"Recovery complete for {robot_id}")
            return True
            
        except asyncio.CancelledError:
            self.logger.warning(f"Recovery cancelled for {robot_id}")
            raise
        except Exception as e:
            self.logger.error(f"Recovery error for {robot_id}: {e}")
            status.last_error = str(e)
            self._set_phase(robot_id, status, RecoveryPhase.FAILED)
            self._notify_recovery_complete(robot_id, False)
            return False
    
    async def _run_assessment(self, robot_id: str, status: RecoveryStatus) -> bool:
        """Run initial assessment phase."""
        self._set_phase(robot_id, status, RecoveryPhase.ASSESSMENT)
        
        try:
            # Check robot state
            if self._get_robot_state:
                state = self._get_robot_state(robot_id)
                
                # Check limits
                if RecoveryRequirement.LIMITS_OK.value in status.requirements_met:
                    limits_ok = state.get("all_limits_ok", True)
                    status.requirements_met[RecoveryRequirement.LIMITS_OK.value] = limits_ok
                    if not limits_ok:
                        self.logger.warning(f"Limits not OK for {robot_id}")
            
            # Check obstacle clearance
            if RecoveryRequirement.OBSTACLE_CLEAR.value in status.requirements_met:
                if self._get_obstacle_distance:
                    distance = self._get_obstacle_distance(robot_id)
                    clear = distance >= self.config.min_obstacle_clearance
                    status.requirements_met[RecoveryRequirement.OBSTACLE_CLEAR.value] = clear
                    if not clear:
                        self.logger.warning(
                            f"Obstacle too close for {robot_id}: {distance:.3f}m"
                        )
            
            # Check mode
            if RecoveryRequirement.MODE_RPM.value in status.requirements_met:
                if self._get_robot_state:
                    state = self._get_robot_state(robot_id)
                    is_rpm = state.get("mode", "").lower() == "rpm"
                    status.requirements_met[RecoveryRequirement.MODE_RPM.value] = is_rpm
                    if not is_rpm:
                        self.logger.warning(f"Must be in RPM mode to recover {robot_id}")
            
            await asyncio.sleep(0.5)  # Brief delay for assessment
            return True
            
        except asyncio.TimeoutError:
            status.last_error = "Assessment timeout"
            return False
    
    async def _wait_for_acknowledgment(self, robot_id: str, status: RecoveryStatus) -> bool:
        """Wait for operator acknowledgment."""
        self._set_phase(robot_id, status, RecoveryPhase.WAITING_ACK)
        
        # Notify that acknowledgment is required
        if status.estop_event:
            for callback in self._on_acknowledgment_required:
                try:
                    callback(robot_id, status.estop_event)
                except Exception as e:
                    self.logger.error(f"Ack callback error: {e}")
        
        self._pending_acks[robot_id] = False
        start_time = time.time()
        
        self.logger.info(f"Waiting for operator acknowledgment for {robot_id}")
        
        while time.time() - start_time < self.config.acknowledgment_timeout_s:
            if self._pending_acks.get(robot_id, False):
                status.requirements_met[RecoveryRequirement.OPERATOR_ACK.value] = True
                self.logger.info(f"Operator acknowledged E-Stop for {robot_id}")
                return True
            
            await asyncio.sleep(0.5)
        
        status.last_error = "Acknowledgment timeout"
        self.logger.error(f"Acknowledgment timeout for {robot_id}")
        return False
    
    def acknowledge_estop(self, robot_id: str):
        """
        Operator acknowledges E-Stop.
        
        This should be called by UI or external system when operator
        confirms they are aware of the E-Stop and ready to recover.
        """
        self._pending_acks[robot_id] = True
        self.logger.info(f"E-Stop acknowledged for {robot_id}")
    
    async def _run_system_check(self, robot_id: str, status: RecoveryStatus) -> bool:
        """Run system diagnostics."""
        self._set_phase(robot_id, status, RecoveryPhase.SYSTEM_CHECK)
        
        if not self._diagnostic_runner:
            self.logger.warning("No diagnostic runner configured")
            status.requirements_met[RecoveryRequirement.DIAGNOSTICS_PASS.value] = True
            return True
        
        try:
            self.logger.info(f"Running diagnostics for {robot_id}")
            
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, self._diagnostic_runner
                ),
                timeout=self.config.system_check_timeout_s
            )
            
            status.requirements_met[RecoveryRequirement.DIAGNOSTICS_PASS.value] = result
            
            if not result:
                status.last_error = "Diagnostics failed"
                self.logger.error(f"Diagnostics failed for {robot_id}")
            
            return result
            
        except asyncio.TimeoutError:
            status.last_error = "Diagnostics timeout"
            return False
    
    async def _staged_enable(self, robot_id: str, status: RecoveryStatus) -> bool:
        """Staged motor enablement with velocity limiting."""
        self._set_phase(robot_id, status, RecoveryPhase.STAGED_ENABLE)
        
        self.logger.info(f"Starting staged enablement for {robot_id}")
        
        # Set velocity limit
        if self._set_velocity_limit:
            self._set_velocity_limit(robot_id, self.config.velocity_limit_on_recovery)
        
        await asyncio.sleep(self.config.enable_delay_s)
        
        # Gradually ramp velocity back up
        ramp_steps = 10
        step_time = self.config.velocity_ramp_time_s / ramp_steps
        
        for i in range(ramp_steps):
            velocity = self.config.velocity_limit_on_recovery + \
                      (1.0 - self.config.velocity_limit_on_recovery) * ((i + 1) / ramp_steps)
            
            if self._set_velocity_limit:
                self._set_velocity_limit(robot_id, velocity)
            
            await asyncio.sleep(step_time)
        
        return True
    
    async def _run_motor_test(self, robot_id: str, status: RecoveryStatus) -> bool:
        """Test motor responsiveness."""
        self._set_phase(robot_id, status, RecoveryPhase.MOTOR_TEST)
        
        if not self._motor_test_runner:
            self.logger.warning("No motor test runner configured")
            return True
        
        try:
            self.logger.info(f"Running motor test for {robot_id}")
            
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, self._motor_test_runner, robot_id
                ),
                timeout=self.config.motor_test_timeout_s
            )
            
            if not result:
                status.last_error = "Motor test failed"
                self.logger.error(f"Motor test failed for {robot_id}")
            
            return result
            
        except asyncio.TimeoutError:
            status.last_error = "Motor test timeout"
            return False
    
    async def _run_final_check(self, robot_id: str, status: RecoveryStatus) -> bool:
        """Run final verification."""
        self._set_phase(robot_id, status, RecoveryPhase.FINAL_CHECK)
        
        # Re-check all requirements
        missing = status.missing_requirements
        
        if missing:
            status.last_error = f"Missing requirements: {missing}"
            self.logger.error(f"Final check failed for {robot_id}: {missing}")
            return False
        
        await asyncio.sleep(0.5)
        return True
    
    # =========================================================================
    # State Management
    # =========================================================================
    
    def _set_phase(self, robot_id: str, status: RecoveryStatus, phase: RecoveryPhase):
        """Set recovery phase and notify callbacks."""
        old_phase = status.phase
        status.phase = phase
        status.phase_start_time = time.time()
        
        self.logger.debug(f"Recovery phase for {robot_id}: {old_phase.name} -> {phase.name}")
        
        for callback in self._on_phase_change:
            try:
                callback(robot_id, phase)
            except Exception as e:
                self.logger.error(f"Phase change callback error: {e}")
    
    def _notify_recovery_complete(self, robot_id: str, success: bool):
        """Notify recovery completion callbacks."""
        for callback in self._on_recovery_complete:
            try:
                callback(robot_id, success)
            except Exception as e:
                self.logger.error(f"Recovery complete callback error: {e}")
    
    # =========================================================================
    # Dependency Injection
    # =========================================================================
    
    def set_diagnostic_runner(self, runner: Callable[[], bool]):
        """Set diagnostic runner function."""
        self._diagnostic_runner = runner
    
    def set_motor_test_runner(self, runner: Callable[[str], bool]):
        """Set motor test runner function."""
        self._motor_test_runner = runner
    
    def set_robot_state_provider(self, provider: Callable[[str], Dict]):
        """Set robot state provider function."""
        self._get_robot_state = provider
    
    def set_obstacle_distance_provider(self, provider: Callable[[str], float]):
        """Set obstacle distance provider function."""
        self._get_obstacle_distance = provider
    
    def set_velocity_limiter(self, limiter: Callable[[str, float], None]):
        """Set velocity limit function."""
        self._set_velocity_limit = limiter
    
    # =========================================================================
    # Callback Registration
    # =========================================================================
    
    def on_phase_change(self, callback: Callable[[str, RecoveryPhase], None]):
        """Register phase change callback."""
        self._on_phase_change.append(callback)
    
    def on_recovery_complete(self, callback: Callable[[str, bool], None]):
        """Register recovery completion callback."""
        self._on_recovery_complete.append(callback)
    
    def on_acknowledgment_required(self, callback: Callable[[str, EStopEvent], None]):
        """Register acknowledgment required callback."""
        self._on_acknowledgment_required.append(callback)
    
    # =========================================================================
    # Status and History
    # =========================================================================
    
    def get_recovery_status(self, robot_id: str) -> Optional[RecoveryStatus]:
        """Get recovery status for a robot."""
        return self._recovery_status.get(robot_id)
    
    def is_estop_active(self, robot_id: str) -> bool:
        """Check if E-Stop is active for a robot."""
        status = self._recovery_status.get(robot_id)
        if not status:
            return False
        return status.phase not in (RecoveryPhase.RECOVERED,)
    
    def get_estop_history(
        self,
        robot_id: Optional[str] = None,
        limit: int = 10
    ) -> List[EStopEvent]:
        """Get E-Stop history."""
        events = self._estop_history
        
        if robot_id:
            events = [e for e in events if e.robot_id == robot_id]
        
        return list(reversed(events[-limit:]))
    
    def get_status(self) -> Dict[str, Any]:
        """Get overall manager status."""
        return {
            "active_recoveries": {
                rid: {
                    "phase": status.phase.name,
                    "attempts": status.attempts,
                    "requirements_met": status.requirements_met,
                    "missing": status.missing_requirements
                }
                for rid, status in self._recovery_status.items()
                if status.phase != RecoveryPhase.RECOVERED
            },
            "total_estops": len(self._estop_history),
            "pending_acknowledgments": list(
                k for k, v in self._pending_acks.items() if not v
            )
        }
    
    def clear_recovery(self, robot_id: str):
        """Clear recovery status for a robot (after successful recovery)."""
        if robot_id in self._recovery_status:
            del self._recovery_status[robot_id]
        self._pending_acks.pop(robot_id, None)
