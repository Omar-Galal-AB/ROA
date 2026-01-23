"""
ROC Coordinator - Main orchestrator for Robot Operator Controller.

Integrates all ROC subsystems:
- UE5 Bridge (IPC Handler, Command Validator)
- Robot Registry (Robot State, Robot Manager)
- Safety (Limit Checker)
- Control Modes (Mode Manager)

This is the main entry point for the Linux-side ROC system.

DIMC Integration (per DIMC-Requirement-ROC.md):
- Notifies DIMC of robot status changes (P0)
- Notifies DIMC of control mode changes (P1)
- Notifies DIMC of emergency stop events (P0)
- Sends joint states to DIMC for arm robots (P2)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable

# DIMC Integration - Import the DIMC API
try:
    import sys
    from pathlib import Path
    # Add DIMC to path if needed
    _dimc_path = Path(__file__).parent.parent.parent.parent / "dimensions-collector" / "src" / "python"
    if str(_dimc_path) not in sys.path:
        sys.path.insert(0, str(_dimc_path))
    from dimc_api import get_dimc_instance, DIMC_API
    DIMC_AVAILABLE = True
except ImportError:
    DIMC_AVAILABLE = False
    DIMC_API = None

# Import ROC subsystems
from .ue5_bridge import UE5IPCHandler, CommandValidator, ValidationResult
from .ue5_bridge.ipc_handler import IPCConfig, IPCMessage
from .ue5_bridge.command_validator import JointCommand, ValidationConfig
from .robot_registry import RobotState, RobotManager
from .robot_registry.robot_manager import ManagerConfig
from .safety import LimitChecker
from .safety.limit_checker import LimitCheckerConfig
from .control_modes import ModeManager, ControlMode
from .control_modes.mode_manager import ModeManagerConfig

# Agent subsystems - Bridge and Heartbeat
from .heartbeat_agent import HeartbeatAgent, HeartbeatAgentConfig
from .bridge_health_agent import BridgeHealthAgent, BridgeHealthAgentConfig, BridgeStatus

# Monitoring and resilience subsystems
from .roc_event_recorder import ROCEventRecorder, EventRecorderConfig, EventSeverity, EventCategory
from .degradation_manager import DegradationManager, DegradationManagerConfig, Capability, DegradationLevel
from .watchdog_manager import WatchdogManager, WatchdogManagerConfig, WatchdogAction
from .roc_state_tracker import ROCStateTracker, StateTrackerConfig, RobotOperationalState
from .diagnostic_manager import DiagnosticManager, DiagnosticManagerConfig
from .rate_limiter import RateLimiter, RateLimiterConfig, CommandPriority, RateLimitResult

# NEW: Task Execution, Safety Coordination, Controller Coordination
from .task_executor import TaskExecutor, TaskExecutorConfig, Task, TaskType, ExecutionState
from .estop_recovery import EStopRecoveryManager, RecoveryConfig, EStopType, RecoveryPhase
from .safety_coordinator import SafetyCoordinator, SafetyCoordinatorConfig, SafetyState
from .controller_coordinator import ControllerCoordinator, ControllerCoordinatorConfig, ControllerType


@dataclass
class ROCConfig:
    """Configuration for ROC Coordinator."""
    # IPC settings
    ipc: IPCConfig = field(default_factory=IPCConfig)
    
    # Validation settings
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    
    # Robot manager settings
    manager: ManagerConfig = field(default_factory=ManagerConfig)
    
    # Limit checker settings
    limits: LimitCheckerConfig = field(default_factory=LimitCheckerConfig)
    
    # Mode manager settings
    modes: ModeManagerConfig = field(default_factory=ModeManagerConfig)
    
    # State update rate (Hz)
    state_update_rate: float = 10.0
    
    # Joint state update rate for DIMC (Hz) - P2 requirement
    joint_state_dimc_rate: float = 20.0
    
    # Enable DIMC integration
    enable_dimc_integration: bool = True
    
    # Enable detailed logging
    debug_logging: bool = False
    
    # Heartbeat Agent settings
    enable_heartbeat_agent: bool = True
    heartbeat: HeartbeatAgentConfig = field(default_factory=HeartbeatAgentConfig)
    
    # Bridge Health Agent settings
    enable_bridge_health_agent: bool = True
    bridge_health: BridgeHealthAgentConfig = field(default_factory=BridgeHealthAgentConfig)
    
    # Event Recorder settings
    enable_event_recorder: bool = True
    events: EventRecorderConfig = field(default_factory=EventRecorderConfig)
    
    # Degradation Manager settings
    enable_degradation_manager: bool = True
    degradation: DegradationManagerConfig = field(default_factory=DegradationManagerConfig)
    
    # Watchdog Manager settings
    enable_watchdog: bool = True
    watchdog: WatchdogManagerConfig = field(default_factory=WatchdogManagerConfig)
    
    # State Tracker settings
    enable_state_tracker: bool = True
    state_tracker: StateTrackerConfig = field(default_factory=StateTrackerConfig)
    
    # Diagnostic Manager settings
    enable_diagnostics: bool = True
    diagnostics: DiagnosticManagerConfig = field(default_factory=DiagnosticManagerConfig)
    
    # Rate Limiter settings
    enable_rate_limiter: bool = True
    rate_limiter: RateLimiterConfig = field(default_factory=RateLimiterConfig)
    
    # NEW: Task Executor settings
    enable_task_executor: bool = True
    task_executor: TaskExecutorConfig = field(default_factory=TaskExecutorConfig)
    
    # NEW: Safety Coordinator settings
    enable_safety_coordinator: bool = True
    safety_coordinator: SafetyCoordinatorConfig = field(default_factory=SafetyCoordinatorConfig)
    
    # NEW: Controller Coordinator settings
    enable_controller_coordinator: bool = True
    controller_coordinator: ControllerCoordinatorConfig = field(default_factory=ControllerCoordinatorConfig)


class ROCCoordinator:
    """
    Main coordinator for the ROC system.
    
    Orchestrates all subsystems and handles:
    - Incoming commands from UE5
    - Robot registration and state management
    - Command validation and safety checking
    - Mode management
    - State updates to UE5
    """
    
    def __init__(self, config: Optional[ROCConfig] = None):
        """
        Initialize ROC Coordinator.
        
        Args:
            config: ROC configuration.
        """
        self.config = config or ROCConfig()
        self.logger = logging.getLogger(__name__)
        
        if self.config.debug_logging:
            logging.getLogger("robot-operator-controller").setLevel(logging.DEBUG)
        
        # Initialize subsystems
        self._init_subsystems()
        
        # Initialize DIMC integration
        self._init_dimc_integration()
        
        # Initialize agent subsystems (Bridge and Heartbeat)
        self._init_agent_subsystems()
        
        # Initialize monitoring subsystems
        self._init_monitoring_subsystems()
        
        # Running state
        self._running = False
        self._state_update_task: Optional[asyncio.Task] = None
        self._joint_state_dimc_task: Optional[asyncio.Task] = None
        
        # Statistics
        self._commands_processed = 0
        self._start_time: float = 0
    
    def _init_subsystems(self):
        """Initialize all ROC subsystems."""
        # IPC Handler
        self.ipc = UE5IPCHandler(self.config.ipc)
        
        # Limit Checker
        self.limit_checker = LimitChecker(self.config.limits)
        
        # Command Validator
        self.validator = CommandValidator(
            self.config.validation,
            self.limit_checker
        )
        
        # Robot Manager
        self.robot_manager = RobotManager(self.config.manager)
        
        # Mode Manager
        self.mode_manager = ModeManager(self.config.modes)
        
        # Wire up mode manager state provider
        self.mode_manager.set_robot_state_provider(self._get_robot_state_for_mode)
        
        # NEW: Safety Coordinator
        self.safety_coordinator: Optional[SafetyCoordinator] = None
        if self.config.enable_safety_coordinator:
            try:
                self.safety_coordinator = SafetyCoordinator(
                    limit_checker=self.limit_checker,
                    config=self.config.safety_coordinator,
                    logger=self.logger
                )
                # Register callbacks
                self.safety_coordinator.on_estop_triggered(self._on_safety_estop)
                self.safety_coordinator.on_safety_state_change(self._on_safety_state_change)
                self.logger.info("SafetyCoordinator initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize SafetyCoordinator: {e}")
        
        # NEW: Controller Coordinator
        self.controller_coordinator: Optional[ControllerCoordinator] = None
        if self.config.enable_controller_coordinator:
            try:
                self.controller_coordinator = ControllerCoordinator(
                    config=self.config.controller_coordinator,
                    logger=self.logger
                )
                # Register callbacks
                self.controller_coordinator.on_motion_complete(self._on_motion_complete)
                self.controller_coordinator.on_error(self._on_controller_error)
                self.logger.info("ControllerCoordinator initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize ControllerCoordinator: {e}")
        
        # NEW: Task Executor (depends on controllers)
        self.task_executor: Optional[TaskExecutor] = None
        if self.config.enable_task_executor:
            try:
                self.task_executor = TaskExecutor(
                    config=self.config.task_executor,
                    logger=self.logger
                )
                # Register callbacks
                self.task_executor.on_task_complete(self._on_task_complete)
                self.task_executor.on_task_failed(self._on_task_failed)
                self.logger.info("TaskExecutor initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize TaskExecutor: {e}")
        
        # Register IPC callbacks
        self._register_ipc_callbacks()
        
        # Register manager callbacks
        self._register_manager_callbacks()
        
        self.logger.info("ROC subsystems initialized")
    
    def _init_dimc_integration(self):
        """
        Initialize DIMC integration.
        
        Per DIMC-Requirement-ROC.md, ROC must notify DIMC of:
        - Robot status changes (P0 Critical)
        - Control mode changes (P1 High)
        - Emergency stop events (P0 Critical Safety)
        - Joint states for arm robots (P2 Medium)
        """
        self.dimc: Optional[DIMC_API] = None
        
        if not self.config.enable_dimc_integration:
            self.logger.info("DIMC integration disabled by config")
            return
        
        if not DIMC_AVAILABLE:
            self.logger.warning(
                "DIMC integration unavailable - dimc_api not found. "
                "DIMC will not receive status/mode/estop updates from ROC."
            )
            return
        
        try:
            self.dimc = get_dimc_instance()
            self.logger.info("DIMC integration initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize DIMC integration: {e}")
            self.dimc = None
    
    def _init_agent_subsystems(self):
        """
        Initialize Bridge and Heartbeat agent subsystems.
        
        Per ROC_BRIDGE_HB_ANALYSIS.md:
        - HeartbeatAgent: Writes ROC heartbeat, monitors dependencies
        - BridgeHealthAgent: Monitors UE5 bridge health, auto-reconnects
        """
        # Heartbeat Agent
        self.heartbeat_agent: Optional[HeartbeatAgent] = None
        
        if self.config.enable_heartbeat_agent:
            try:
                self.heartbeat_agent = HeartbeatAgent(
                    config=self.config.heartbeat,
                    logger=self.logger
                )
                
                # Register callback for dependency failures
                self.heartbeat_agent.on_dependency_failure(
                    self._on_dependency_failure
                )
                
                self.logger.info("HeartbeatAgent initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize HeartbeatAgent: {e}")
                self.heartbeat_agent = None
        else:
            self.logger.info("HeartbeatAgent disabled by config")
        
        # Bridge Health Agent
        self.bridge_health_agent: Optional[BridgeHealthAgent] = None
        
        if self.config.enable_bridge_health_agent:
            try:
                self.bridge_health_agent = BridgeHealthAgent(
                    ipc_handler=self.ipc,
                    config=self.config.bridge_health,
                    logger=self.logger
                )
                
                # Register callback for bridge status changes
                self.bridge_health_agent.on_status_change(
                    self._on_bridge_status_change
                )
                
                self.logger.info("BridgeHealthAgent initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize BridgeHealthAgent: {e}")
                self.bridge_health_agent = None
        else:
            self.logger.info("BridgeHealthAgent disabled by config")
    
    def _init_monitoring_subsystems(self):
        """
        Initialize monitoring and resilience subsystems.
        
        Per ROC_CRITICAL_ANALYSIS.md:
        - EventRecorder: Centralized event/alert system
        - DegradationManager: Graceful degradation on failures
        - WatchdogManager: Execution timeout monitoring
        - StateTracker: State transition auditing
        - DiagnosticManager: Self-test and health checks
        - RateLimiter: Command rate limiting
        """
        # Event Recorder (always first - used by other components)
        self.event_recorder: Optional[ROCEventRecorder] = None
        
        if self.config.enable_event_recorder:
            try:
                self.event_recorder = ROCEventRecorder(
                    config=self.config.events,
                    logger=self.logger
                )
                # Register alert callback
                self.event_recorder.on_alert(self._on_event_alert)
                self.logger.info("EventRecorder initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize EventRecorder: {e}")
        
        # Degradation Manager
        self.degradation_manager: Optional[DegradationManager] = None
        
        if self.config.enable_degradation_manager:
            try:
                self.degradation_manager = DegradationManager(
                    config=self.config.degradation,
                    mode_manager=self.mode_manager,
                    logger=self.logger
                )
                # Register callbacks
                self.degradation_manager.on_capability_change(self._on_capability_change)
                self.degradation_manager.on_level_change(self._on_degradation_level_change)
                self.logger.info("DegradationManager initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize DegradationManager: {e}")
        
        # Watchdog Manager
        self.watchdog_manager: Optional[WatchdogManager] = None
        
        if self.config.enable_watchdog:
            try:
                self.watchdog_manager = WatchdogManager(
                    config=self.config.watchdog,
                    logger=self.logger
                )
                # Register timeout callback
                self.watchdog_manager.on_timeout(self._on_watchdog_timeout)
                self.logger.info("WatchdogManager initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize WatchdogManager: {e}")
        
        # State Tracker
        self.state_tracker: Optional[ROCStateTracker] = None
        
        if self.config.enable_state_tracker:
            try:
                self.state_tracker = ROCStateTracker(
                    config=self.config.state_tracker,
                    logger=self.logger
                )
                # Register state change callback
                self.state_tracker.on_state_change(self._on_state_transition)
                self.logger.info("StateTracker initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize StateTracker: {e}")
        
        # Diagnostic Manager
        self.diagnostic_manager: Optional[DiagnosticManager] = None
        
        if self.config.enable_diagnostics:
            try:
                self.diagnostic_manager = DiagnosticManager(
                    config=self.config.diagnostics,
                    logger=self.logger
                )
                # Register standard tests
                self.diagnostic_manager.register_standard_tests(
                    ipc_handler=self.ipc,
                    robot_manager=self.robot_manager,
                    mode_manager=self.mode_manager,
                    limit_checker=self.limit_checker,
                    heartbeat_agent=self.heartbeat_agent,
                    bridge_health_agent=self.bridge_health_agent
                )
                self.logger.info("DiagnosticManager initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize DiagnosticManager: {e}")
        
        # Rate Limiter
        self.rate_limiter: Optional[RateLimiter] = None
        
        if self.config.enable_rate_limiter:
            try:
                self.rate_limiter = RateLimiter(
                    config=self.config.rate_limiter,
                    logger=self.logger
                )
                # Register backpressure callback
                self.rate_limiter.on_backpressure(self._on_backpressure)
                self.logger.info("RateLimiter initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize RateLimiter: {e}")
        
        self.logger.info("Monitoring subsystems initialized")
    
    def _on_event_alert(self, event):
        """Handle alert from EventRecorder."""
        self.logger.warning(f"Alert: [{event.category.value}] {event.message}")
        # Could forward to UE5 or Webthread here
    
    def _on_capability_change(self, capability: Capability, enabled: bool):
        """Handle capability change from DegradationManager."""
        action = "enabled" if enabled else "disabled"
        self.logger.info(f"Capability {capability.value} {action}")
        
        if self.event_recorder:
            self.event_recorder.record_system_event(
                f"capability_{action}",
                f"Capability {capability.value} {action}",
                severity=EventSeverity.WARNING if not enabled else EventSeverity.INFO,
                capability=capability.value
            )
    
    def _on_degradation_level_change(self, old_level: DegradationLevel, new_level: DegradationLevel):
        """Handle degradation level change."""
        self.logger.warning(f"Degradation: {old_level.name} -> {new_level.name}")
        
        if self.event_recorder:
            self.event_recorder.record_health_event(
                "degradation_level_changed",
                f"System degradation level changed from {old_level.name} to {new_level.name}",
                severity=EventSeverity.WARNING if new_level != DegradationLevel.NOMINAL else EventSeverity.INFO,
                old_level=old_level.name,
                new_level=new_level.name
            )
    
    def _on_watchdog_timeout(self, name: str, item):
        """Handle watchdog timeout."""
        self.logger.error(f"Watchdog timeout: {name}")
        
        if self.event_recorder:
            self.event_recorder.record_health_event(
                "watchdog_timeout",
                f"Watchdog timeout for {name}",
                severity=EventSeverity.ERROR,
                item_name=name,
                timeout_count=item.timeout_count
            )
    
    def _on_state_transition(self, robot_id: str, transition):
        """Handle state transition notification."""
        self.logger.debug(
            f"State transition: {robot_id} "
            f"{transition.from_state} -> {transition.to_state}"
        )
    
    def _on_backpressure(self, robot_id: str, fullness: float):
        """Handle backpressure signal from RateLimiter."""
        if fullness > 0:
            self.logger.warning(f"Backpressure for {robot_id}: queue {fullness*100:.0f}% full")
        else:
            self.logger.info(f"Backpressure cleared for {robot_id}")

    def _on_dependency_failure(self, component: str, failed: bool):
        """
        Handle dependency failure notification from HeartbeatAgent.
        
        Args:
            component: Name of the dependency that failed/recovered
            failed: True if failed, False if recovered
        """
        if failed:
            self.logger.warning(f"Dependency {component} has failed")
            
            # Record event
            if self.event_recorder:
                self.event_recorder.record_health_event(
                    "dependency_failure",
                    f"Dependency {component} has failed",
                    severity=EventSeverity.ERROR,
                    component=component
                )
            
            # Notify degradation manager
            if self.degradation_manager:
                self.degradation_manager.on_dependency_failure(component)
            
            # Specific handling based on component
            if component == 'dimc':
                self.logger.error(
                    "DIMC failure detected - spatial data unavailable"
                )
            elif component == 'ue5_plugin':
                self.logger.error(
                    "UE5 plugin failure detected - consider reconnecting"
                )
        else:
            self.logger.info(f"Dependency {component} has recovered")
            
            # Record recovery event
            if self.event_recorder:
                self.event_recorder.record_health_event(
                    "dependency_recovered",
                    f"Dependency {component} has recovered",
                    severity=EventSeverity.INFO,
                    component=component
                )
            
            # Notify degradation manager
            if self.degradation_manager:
                self.degradation_manager.on_dependency_recovered(component)
    
    def _on_bridge_status_change(self, new_status: BridgeStatus):
        """
        Handle bridge status change notification from BridgeHealthAgent.
        
        Args:
            new_status: New bridge status
        """
        self.logger.info(f"Bridge status changed to: {new_status.name}")
        
        if new_status == BridgeStatus.FAILED:
            self.logger.error("Bridge connection lost")
            # Could trigger alerts or graceful degradation here
        
        elif new_status == BridgeStatus.DEGRADED:
            self.logger.warning("Bridge connection degraded")
        
        elif new_status == BridgeStatus.HEALTHY:
            self.logger.info("Bridge connection healthy")
    
    def _register_ipc_callbacks(self):
        """Register callbacks for IPC message handling."""
        self.ipc.register_callback("joint_command_request", self._handle_joint_command)
        self.ipc.register_callback("emergency_stop", self._handle_emergency_stop)
        self.ipc.register_callback("mode_change", self._handle_mode_change)
        self.ipc.register_callback("robot_registered", self._handle_robot_registered)
    
    def _register_manager_callbacks(self):
        """Register callbacks for robot manager events."""
        self.robot_manager.on_register(self._on_robot_registered)
        self.robot_manager.on_unregister(self._on_robot_unregistered)
        
        self.mode_manager.on_mode_change(self._on_mode_changed)
    
    async def start(self) -> bool:
        """
        Start the ROC coordinator.
        
        Returns:
            True if started successfully.
        """
        self.logger.info("Starting ROC Coordinator")
        
        # Record startup event
        if self.event_recorder:
            self.event_recorder.record_system_event(
                "startup_initiated",
                "ROC Coordinator starting",
                severity=EventSeverity.INFO
            )
        
        # Run startup diagnostics
        if self.diagnostic_manager:
            self.logger.info("Running startup diagnostics...")
            diagnostics_passed = await self.diagnostic_manager.run_startup_diagnostics()
            if not diagnostics_passed:
                self.logger.error("Startup diagnostics failed")
                if self.event_recorder:
                    self.event_recorder.record_system_event(
                        "startup_failed",
                        "ROC startup diagnostics failed",
                        severity=EventSeverity.ERROR
                    )
                # Continue anyway but log warning
                self.logger.warning("Continuing despite diagnostic failures")
        
        # Connect to UE5
        if not await self.ipc.connect():
            self.logger.error("Failed to connect to UE5")
            if self.event_recorder:
                self.event_recorder.record_connection_event(
                    "ipc_connect_failed",
                    "Failed to connect to UE5",
                    severity=EventSeverity.ERROR
                )
            return False
        
        self._running = True
        self._start_time = time.time()
        
        # Start state update loop
        self._state_update_task = asyncio.create_task(self._state_update_loop())
        
        # Start HeartbeatAgent
        if self.heartbeat_agent:
            await self.heartbeat_agent.start()
            # Update initial metrics
            self.heartbeat_agent.update_metrics(
                active_robots=len(self.robot_manager.list_robots()),
                commands_processed=self._commands_processed,
                current_mode=self.mode_manager.get_default_mode().value,
                ipc_connected=self.ipc.is_connected
            )
        
        # Start BridgeHealthAgent
        if self.bridge_health_agent:
            await self.bridge_health_agent.start()
        
        # Start WatchdogManager
        if self.watchdog_manager:
            await self.watchdog_manager.start()
        
        # Start periodic diagnostics
        if self.diagnostic_manager:
            await self.diagnostic_manager.start_periodic()
        
        # NEW: Start SafetyCoordinator
        if self.safety_coordinator:
            await self.safety_coordinator.start()
        
        # NEW: Start ControllerCoordinator
        if self.controller_coordinator:
            await self.controller_coordinator.start()
        
        # NEW: Start TaskExecutor
        if self.task_executor:
            await self.task_executor.start()
        
        # Start DIMC joint state update loop (P2 requirement)
        if self.dimc and self.config.joint_state_dimc_rate > 0:
            self._joint_state_dimc_task = asyncio.create_task(
                self._joint_state_dimc_loop()
            )
            self.logger.info(
                f"DIMC joint state loop started at {self.config.joint_state_dimc_rate}Hz"
            )
        
        # Record startup complete
        if self.event_recorder:
            self.event_recorder.record_system_event(
                "startup_complete",
                "ROC Coordinator started successfully",
                severity=EventSeverity.INFO
            )
        
        self.logger.info("ROC Coordinator started")
        return True
    
    async def stop(self):
        """Stop the ROC coordinator."""
        self.logger.info("Stopping ROC Coordinator")
        
        # Record shutdown event
        if self.event_recorder:
            self.event_recorder.record_system_event(
                "shutdown_initiated",
                "ROC Coordinator shutting down",
                severity=EventSeverity.INFO
            )
        
        self._running = False
        
        # Stop periodic diagnostics
        if self.diagnostic_manager:
            await self.diagnostic_manager.stop_periodic()
        
        # Stop WatchdogManager
        if self.watchdog_manager:
            await self.watchdog_manager.stop()
        
        # NEW: Stop TaskExecutor
        if self.task_executor:
            await self.task_executor.stop()
        
        # NEW: Stop ControllerCoordinator
        if self.controller_coordinator:
            await self.controller_coordinator.stop()
        
        # NEW: Stop SafetyCoordinator
        if self.safety_coordinator:
            await self.safety_coordinator.stop()
        
        # Stop agents first (they should clean up gracefully)
        if self.heartbeat_agent:
            await self.heartbeat_agent.stop()
        
        if self.bridge_health_agent:
            await self.bridge_health_agent.stop()
        
        # Stop state update task
        if self._state_update_task:
            self._state_update_task.cancel()
            try:
                await self._state_update_task
            except asyncio.CancelledError:
                pass
        
        # Stop DIMC joint state task
        if self._joint_state_dimc_task:
            self._joint_state_dimc_task.cancel()
            try:
                await self._joint_state_dimc_task
            except asyncio.CancelledError:
                pass
        
        # Disconnect from UE5
        await self.ipc.disconnect()
        
        self.logger.info("ROC Coordinator stopped")
    
    async def _state_update_loop(self):
        """Periodic state update to UE5."""
        interval = 1.0 / self.config.state_update_rate
        
        while self._running:
            try:
                await self._send_state_updates()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"State update error: {e}")
                await asyncio.sleep(interval)
    
    async def _send_state_updates(self):
        """Send state updates for all robots to UE5."""
        for robot_id, robot in self.robot_manager.get_all_robots().items():
            await self.ipc.send_state_update(
                robot_id=robot_id,
                mode=robot.mode.value,
                status=robot.status.name.lower(),
                safety_status=robot.safety.to_dict()
            )
        
        # Update heartbeat agent metrics
        if self.heartbeat_agent:
            self.heartbeat_agent.update_metrics(
                active_robots=len(self.robot_manager.list_robots()),
                commands_processed=self._commands_processed,
                ipc_connected=self.ipc.is_connected
            )
    
    async def _joint_state_dimc_loop(self):
        """
        Periodic joint state updates to DIMC (P2 requirement).
        
        Sends joint states for arm robots at configured rate (default 20Hz).
        DIMC uses this for end-effector collision detection.
        """
        interval = 1.0 / self.config.joint_state_dimc_rate
        
        while self._running:
            try:
                # Send joint states for all arm robots
                for robot_id in self.robot_manager.list_robots():
                    robot = self.robot_manager.get_robot(robot_id)
                    if robot and robot.joints:  # Only arm robots have joints
                        self.send_joint_states_to_dimc(robot_id)
                
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"DIMC joint state update error: {e}")
                await asyncio.sleep(interval)
    
    # ==========================================================================
    # IPC Message Handlers
    # ==========================================================================
    
    async def _handle_joint_command(self, message: IPCMessage):
        """Handle joint command request from UE5."""
        robot_id = message.data.get("robot_id")
        commands_data = message.data.get("commands", [])
        source = message.data.get("source", "rpm")
        
        self.logger.debug(f"Joint command for {robot_id}: {len(commands_data)} commands")
        
        # Get robot
        robot = self.robot_manager.get_robot(robot_id)
        if not robot:
            self.logger.warning(f"Unknown robot: {robot_id}")
            for cmd_data in commands_data:
                await self.ipc.send_command_rejected(
                    robot_id=robot_id,
                    command_id=cmd_data.get("command_id", ""),
                    joint_name=cmd_data.get("joint_name", ""),
                    reason="unknown_robot"
                )
            return
        
        # Validate each command
        approved_commands = []
        
        for cmd_data in commands_data:
            command = JointCommand(
                joint_name=cmd_data.get("joint_name", ""),
                target_position=cmd_data.get("target_position", 0.0),
                velocity_limit=cmd_data.get("velocity_limit", 0.0),
                command_id=cmd_data.get("command_id", "")
            )
            
            # Get joint limits
            joint = robot.get_joint(command.joint_name)
            joint_limits = None
            if joint and joint.limits:
                from .ue5_bridge.command_validator import JointLimits as ValidatorLimits
                joint_limits = ValidatorLimits(
                    lower=joint.limits.lower,
                    upper=joint.limits.upper,
                    velocity=joint.limits.velocity,
                    effort=joint.limits.effort
                )
            
            # Validate command
            result = self.validator.validate_command(
                robot_id, command, joint_limits
            )
            
            if result.approved:
                approved_commands.append(result.to_dict())
            else:
                await self.ipc.send_command_rejected(
                    robot_id=robot_id,
                    command_id=command.command_id,
                    joint_name=command.joint_name,
                    reason=result.reason.value if result.reason else "unknown"
                )
        
        # Send approved commands
        if approved_commands:
            await self.ipc.send_command_approved(robot_id, approved_commands)
        
        self._commands_processed += len(commands_data)
    
    async def _handle_emergency_stop(self, message: IPCMessage):
        """Handle emergency stop from UE5."""
        robot_id = message.data.get("robot_id", "all")
        reason = message.data.get("reason", "user_requested")
        
        self.logger.warning(f"Emergency stop received: {robot_id} - {reason}")
        
        if robot_id == "all":
            # Stop all robots
            self.robot_manager.broadcast_estop(reason)
            for rid in self.robot_manager.list_robots():
                self.validator.set_estop(rid, True)
                self.mode_manager.set_estop(rid, True)
                # DIMC Integration (P0 Critical Safety)
                self._notify_dimc_estop(rid, True)
        else:
            # Stop specific robot
            robot = self.robot_manager.get_robot(robot_id)
            if robot:
                robot.set_estop(True)
                self.validator.set_estop(robot_id, True)
                self.mode_manager.set_estop(robot_id, True)
                # DIMC Integration (P0 Critical Safety)
                self._notify_dimc_estop(robot_id, True)
        
        # Send safety alert
        await self.ipc.send_safety_alert(
            robot_id=robot_id,
            alert_type="emergency_stop_triggered",
            severity="critical",
            message_text=f"Emergency stop: {reason}"
        )
    
    async def _handle_mode_change(self, message: IPCMessage):
        """Handle mode change request from UE5."""
        robot_id = message.data.get("robot_id")
        new_mode_str = message.data.get("new_mode", "rpm")
        
        try:
            new_mode = ControlMode(new_mode_str)
        except ValueError:
            self.logger.warning(f"Invalid mode: {new_mode_str}")
            return
        
        result = self.mode_manager.request_transition(robot_id, new_mode)
        
        if result.success:
            self.logger.info(f"Mode changed for {robot_id}: {new_mode.value}")
            # Update robot state
            robot = self.robot_manager.get_robot(robot_id)
            if robot:
                robot.set_mode(new_mode)
            # DIMC Integration (P1 High) - notify mode change
            self._notify_dimc_mode_change(robot_id, new_mode)
        else:
            self.logger.warning(
                f"Mode change failed for {robot_id}: {result.message}"
            )
    
    async def _handle_robot_registered(self, message: IPCMessage):
        """Handle robot registration notification from UE5."""
        robot_id = message.data.get("robot_id")
        robot_name = message.data.get("robot_name", robot_id)
        joint_count = message.data.get("joint_count", 0)
        
        self.logger.info(
            f"UE5 registered robot: {robot_id} ({robot_name}) "
            f"with {joint_count} joints"
        )
        
        # Create placeholder if not already registered via FTI
        if robot_id not in self.robot_manager.list_robots():
            self.robot_manager.register_robot(robot_id)
    
    # ==========================================================================
    # Manager Callbacks
    # ==========================================================================
    
    def _on_robot_registered(self, robot_id: str, robot: RobotState):
        """Callback when robot is registered."""
        # Register with mode manager
        self.mode_manager.register_robot(robot_id)
        
        # DIMC Integration (P0 Critical) - notify robot is active
        self._notify_dimc_status(robot_id, "ACTIVE")
        
        # DIMC Integration (P1 High) - notify initial mode (RPM default)
        self._notify_dimc_mode_change(robot_id, ControlMode.RPM)
        
        # NEW: Register with SafetyCoordinator
        if self.safety_coordinator:
            self.safety_coordinator.register_robot(robot_id)
        
        # NEW: Register with ControllerCoordinator
        if self.controller_coordinator:
            # Determine what controllers this robot needs
            has_arm = bool(robot.joints)
            has_gripper = False  # Detect from joints or spec
            has_mobile = False   # Detect from spec
            
            # Count arm vs gripper joints (heuristic)
            arm_joints = 0
            gripper_joints = 0
            if robot.joints:
                for joint in robot.joints.values():
                    if "gripper" in joint.name.lower() or "finger" in joint.name.lower():
                        gripper_joints += 1
                    else:
                        arm_joints += 1
                
                has_gripper = gripper_joints > 0
            
            self.controller_coordinator.register_robot(
                robot_id=robot_id,
                has_arm=has_arm,
                has_gripper=has_gripper,
                has_mobile_base=has_mobile,
                arm_joint_count=arm_joints,
                gripper_joint_count=gripper_joints
            )
        
        # Register limits if robot has spec
        if robot.joints:
            spec = {"joints": [
                {
                    "name": j.name,
                    "type": j.joint_type.value,
                    "limits": {
                        "lower": j.limits.lower if j.limits else -3.14159,
                        "upper": j.limits.upper if j.limits else 3.14159,
                        "velocity": j.limits.velocity if j.limits else 2.0,
                        "effort": j.limits.effort if j.limits else 100.0
                    },
                    "ue5_constraint_name": j.ue5_constraint_name
                }
                for j in robot.joints.values()
            ]}
            self.limit_checker.register_robot_limits(robot_id, spec)
    
    def _on_robot_unregistered(self, robot_id: str, robot: RobotState):
        """Callback when robot is unregistered."""
        self.mode_manager.unregister_robot(robot_id)
        self.limit_checker.unregister_robot(robot_id)
        
        # NEW: Unregister from new coordinators
        if self.safety_coordinator:
            self.safety_coordinator.unregister_robot(robot_id)
        
        if self.controller_coordinator:
            self.controller_coordinator.unregister_robot(robot_id)
    
    def _on_mode_changed(
        self, 
        robot_id: str, 
        old_mode: ControlMode, 
        new_mode: ControlMode
    ):
        """Callback when robot mode changes."""
        self.logger.info(
            f"Mode changed for {robot_id}: {old_mode.value} -> {new_mode.value}"
        )
        # DIMC Integration (P1 High) - notify mode change
        self._notify_dimc_mode_change(robot_id, new_mode)
    
    def _get_robot_state_for_mode(self, robot_id: str) -> Dict[str, Any]:
        """Get robot state for mode manager decisions."""
        robot = self.robot_manager.get_robot(robot_id)
        if not robot:
            return {}
        
        return {
            "is_moving": robot.status.name == "MOVING",
            "obstacle_distance": robot.safety.obstacle_distance,
            "estop_active": robot.safety.estop_active
        }
    
    # ==========================================================================
    # DIMC Integration (per DIMC-Requirement-ROC.md)
    # ==========================================================================
    
    def _notify_dimc_status(self, robot_id: str, status: str):
        """
        Notify DIMC of robot status change (P0 Critical).
        
        Status values: 'ACTIVE', 'PAUSED', 'STOPPED', 'ESTOPPED', 'UNKNOWN'
        """
        if self.dimc:
            try:
                self.dimc.set_robot_status(robot_id, status)
                self.logger.debug(f"DIMC notified: {robot_id} status={status}")
            except Exception as e:
                self.logger.error(f"Failed to notify DIMC of status: {e}")
    
    def _notify_dimc_mode_change(self, robot_id: str, mode: ControlMode):
        """
        Notify DIMC of control mode change (P1 High).
        
        Mode values: 'ADM', 'MANUAL', 'REMOTE'
        DIMC uses this to enable/disable Evade subsystem.
        """
        if self.dimc:
            try:
                # Map ROC modes to DIMC modes
                dimc_mode = "ADM" if mode == ControlMode.ADM else "MANUAL"
                self.dimc.set_control_mode(robot_id, dimc_mode)
                self.logger.debug(f"DIMC notified: {robot_id} mode={dimc_mode}")
            except Exception as e:
                self.logger.error(f"Failed to notify DIMC of mode change: {e}")
    
    def _notify_dimc_estop(self, robot_id: str, triggered: bool):
        """
        Notify DIMC of emergency stop event (P0 Critical Safety).
        
        This is safety-critical - DIMC must immediately zero velocity readings.
        """
        if self.dimc:
            try:
                self.dimc.on_emergency_stop(robot_id, triggered)
                self.logger.debug(f"DIMC notified: {robot_id} estop={triggered}")
            except Exception as e:
                self.logger.error(f"Failed to notify DIMC of E-Stop: {e}")
    
    def send_joint_states_to_dimc(self, robot_id: str):
        """
        Send current joint states to DIMC (P2 Medium).
        
        For arm robots, DIMC uses this for end-effector collision detection.
        Should be called at 10-30 Hz depending on control mode.
        """
        if not self.dimc:
            return
        
        robot = self.robot_manager.get_robot(robot_id)
        if not robot or not robot.joints:
            return
        
        try:
            joint_states = {
                joint_name: {
                    "position": joint.position,
                    "velocity": joint.velocity,
                    "at_limit": joint.at_limit
                }
                for joint_name, joint in robot.joints.items()
            }
            self.dimc.update_joint_states(robot_id, joint_states)
        except Exception as e:
            self.logger.error(f"Failed to send joint states to DIMC: {e}")

    # ==========================================================================
    # External Integration
    # ==========================================================================
    
    def register_robot_from_fti(self, fti_spec: Dict[str, Any]) -> bool:
        """
        Register a robot from FTI specification.
        
        Args:
            fti_spec: FTI robot specification.
            
        Returns:
            True if registered successfully.
        """
        robot_id = fti_spec.get("robot_id")
        if not robot_id:
            self.logger.error("FTI spec missing robot_id")
            return False
        
        result, message = self.robot_manager.register_robot(robot_id, fti_spec)
        
        if result.name == "SUCCESS":
            # Register limits
            self.limit_checker.register_robot_limits(robot_id, fti_spec)
            return True
        
        self.logger.warning(f"Robot registration failed: {message}")
        return False
    
    def clear_emergency_stop(self, robot_id: str) -> bool:
        """
        Clear emergency stop for a robot.
        
        Args:
            robot_id: Robot identifier
            
        Returns:
            True if E-Stop was cleared successfully
        """
        robot = self.robot_manager.get_robot(robot_id)
        if not robot:
            self.logger.warning(f"Cannot clear E-Stop: unknown robot {robot_id}")
            return False
        
        # Clear in all subsystems
        robot.clear_estop()
        self.validator.set_estop(robot_id, False)
        self.mode_manager.set_estop(robot_id, False)
        
        # DIMC Integration (P0 Critical Safety) - notify E-Stop released
        self._notify_dimc_estop(robot_id, False)
        
        # Notify status is back to ACTIVE
        self._notify_dimc_status(robot_id, "ACTIVE")
        
        self.logger.info(f"Emergency stop cleared for {robot_id}")
        return True
    
    def update_from_dimc_joints(
        self, 
        robot_id: str, 
        joint_states: Dict[str, Any]
    ):
        """Update robot joints from DIMC message."""
        self.robot_manager.update_joint_states(robot_id, joint_states)
    
    def update_from_dimc_obstacles(
        self, 
        robot_id: str, 
        obstacle_data: Dict[str, Any]
    ):
        """Update obstacle data from DIMC message."""
        self.robot_manager.update_obstacles(robot_id, obstacle_data)
        
        # Update validator obstacle distance
        closest = obstacle_data.get("closest_distance_cm", float('inf'))
        self.validator.update_obstacle_distance(robot_id, closest)
        
        # NEW: Update safety coordinator
        if self.safety_coordinator:
            self.safety_coordinator.update_obstacle_data(robot_id, obstacle_data)
    
    def update_from_dimc_boundaries(
        self, 
        robot_id: str, 
        boundary_data: Dict[str, Any]
    ):
        """Update boundary status from DIMC message."""
        self.robot_manager.update_boundaries(robot_id, boundary_data)
        
        # Update validator
        status = "ok" if boundary_data.get("within_bounds", True) else "violation"
        self.validator.update_boundary_status(robot_id, status)
        
        # NEW: Update safety coordinator
        if self.safety_coordinator:
            self.safety_coordinator.update_boundary_data(robot_id, boundary_data)
    
    # ==========================================================================
    # NEW Callback Handlers for New Coordinators
    # ==========================================================================
    
    def _on_safety_estop(self, robot_id: str, estop_type: EStopType):
        """Handle E-Stop triggered by safety system."""
        self.logger.warning(f"Safety system triggered E-Stop for {robot_id}: {estop_type.name}")
        
        # Record event
        if self.event_recorder:
            self.event_recorder.record_safety_event(
                "safety_estop_triggered",
                f"Safety E-Stop triggered: {estop_type.name}",
                severity=EventSeverity.CRITICAL,
                robot_id=robot_id,
                estop_type=estop_type.name
            )
        
        # Emergency stop robot
        robot = self.robot_manager.get_robot(robot_id)
        if robot:
            robot.set_estop(True)
            self.validator.set_estop(robot_id, True)
            self.mode_manager.set_estop(robot_id, True)
            
            # Stop controllers
            if self.controller_coordinator:
                self.controller_coordinator.emergency_stop(robot_id)
        
        # Notify DIMC
        self._notify_dimc_estop(robot_id, True)
    
    def _on_safety_state_change(self, robot_id: str, state: SafetyState):
        """Handle safety state change."""
        self.logger.debug(f"Safety state for {robot_id}: {state.name}")
        
        # Update velocity multiplier for controllers
        if self.safety_coordinator and self.controller_coordinator:
            multiplier = self.safety_coordinator.get_velocity_multiplier(robot_id)
            self.controller_coordinator.set_velocity_multiplier(robot_id, multiplier)
    
    def _on_motion_complete(self, robot_id: str, controller_type: ControllerType, success: bool):
        """Handle motion completion from controller."""
        self.logger.debug(
            f"Motion complete for {robot_id} {controller_type.name}: {'success' if success else 'failed'}"
        )
        
        # Notify task executor if relevant
        if self.task_executor:
            # Task executor will handle this internally via its own controller tracking
            pass
    
    def _on_controller_error(self, robot_id: str, controller_type: ControllerType, error: str):
        """Handle controller error."""
        self.logger.error(f"Controller error for {robot_id} {controller_type.name}: {error}")
        
        if self.event_recorder:
            self.event_recorder.record_robot_event(
                "controller_error",
                f"Controller error: {error}",
                severity=EventSeverity.ERROR,
                robot_id=robot_id,
                controller_type=controller_type.name,
                error=error
            )
    
    def _on_task_complete(self, robot_id: str, task_id: str, success: bool):
        """Handle task completion from task executor."""
        self.logger.info(
            f"Task {task_id} for {robot_id}: {'completed' if success else 'failed'}"
        )
        
        if self.event_recorder:
            severity = EventSeverity.INFO if success else EventSeverity.WARNING
            self.event_recorder.record_robot_event(
                "task_complete" if success else "task_failed",
                f"Task {task_id} {'completed' if success else 'failed'}",
                severity=severity,
                robot_id=robot_id,
                task_id=task_id
            )
    
    def _on_task_failed(self, robot_id: str, task_id: str, reason: str):
        """Handle task failure from task executor."""
        self.logger.warning(f"Task {task_id} failed for {robot_id}: {reason}")
        
        if self.event_recorder:
            self.event_recorder.record_robot_event(
                "task_execution_failed",
                f"Task execution failed: {reason}",
                severity=EventSeverity.WARNING,
                robot_id=robot_id,
                task_id=task_id,
                reason=reason
            )
    
    # ==========================================================================
    # Status and Statistics
    # ==========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Get ROC coordinator status."""
        uptime = time.time() - self._start_time if self._start_time else 0
        
        status = {
            "running": self._running,
            "uptime_seconds": uptime,
            "ipc_connected": self.ipc.is_connected,
            "ipc_stats": self.ipc.get_statistics(),
            "robots": self.robot_manager.get_summary(),
            "modes": self.mode_manager.get_summary(),
            "validation_stats": self.validator.get_statistics(),
            "limit_stats": self.limit_checker.get_statistics(),
            "commands_processed": self._commands_processed
        }
        
        # Add heartbeat agent status
        if self.heartbeat_agent:
            status["heartbeat_agent"] = self.heartbeat_agent.get_health_report()
        else:
            status["heartbeat_agent"] = {"enabled": False}
        
        # Add bridge health agent status
        if self.bridge_health_agent:
            status["bridge_health_agent"] = self.bridge_health_agent.get_health_report()
        else:
            status["bridge_health_agent"] = {"enabled": False}
        
        # ======================================================================
        # NEW Monitoring Subsystem Status
        # ======================================================================
        
        # Event recorder statistics
        if self.event_recorder:
            status["event_recorder"] = self.event_recorder.get_statistics()
        else:
            status["event_recorder"] = {"enabled": False}
        
        # Degradation manager status
        if self.degradation_manager:
            status["degradation"] = self.degradation_manager.get_status()
        else:
            status["degradation"] = {"enabled": False}
        
        # Watchdog manager status
        if self.watchdog_manager:
            status["watchdog"] = self.watchdog_manager.get_status()
        else:
            status["watchdog"] = {"enabled": False}
        
        # State tracker status
        if self.state_tracker:
            status["state_tracker"] = self.state_tracker.get_status()
        else:
            status["state_tracker"] = {"enabled": False}
        
        # Diagnostic manager status
        if self.diagnostic_manager:
            status["diagnostics"] = self.diagnostic_manager.get_status()
        else:
            status["diagnostics"] = {"enabled": False}
        
        # Rate limiter status
        if self.rate_limiter:
            status["rate_limiter"] = self.rate_limiter.get_status()
        else:
            status["rate_limiter"] = {"enabled": False}
        
        # NEW: Task Executor status
        if self.task_executor:
            status["task_executor"] = self.task_executor.get_status()
        else:
            status["task_executor"] = {"enabled": False}
        
        # NEW: Safety Coordinator status
        if self.safety_coordinator:
            status["safety_coordinator"] = self.safety_coordinator.get_status()
        else:
            status["safety_coordinator"] = {"enabled": False}
        
        # NEW: Controller Coordinator status
        if self.controller_coordinator:
            status["controller_coordinator"] = self.controller_coordinator.get_status()
        else:
            status["controller_coordinator"] = {"enabled": False}
        
        return status
    
    def get_full_health_dashboard(self) -> Dict[str, Any]:
        """
        Get comprehensive health dashboard for Webthread/UI.
        
        This method aggregates health information from all agents and subsystems
        into a single unified view suitable for monitoring dashboards.
        
        Returns:
            Comprehensive health dashboard with all component statuses
        """
        uptime = time.time() - self._start_time if self._start_time else 0
        
        # Determine overall system health
        overall_health = "healthy"
        health_issues = []
        
        # Check IPC connection
        if not self.ipc.is_connected:
            overall_health = "critical"
            health_issues.append("IPC disconnected from UE5")
        
        # Check heartbeat agent
        if self.heartbeat_agent:
            if self.heartbeat_agent.is_degraded:
                overall_health = "degraded" if overall_health == "healthy" else overall_health
                health_issues.extend([
                    f"Dependency {c} failed" 
                    for c in self.heartbeat_agent.degraded_components
                ])
        
        # Check bridge health
        if self.bridge_health_agent:
            bridge_status = self.bridge_health_agent.status
            if bridge_status == BridgeStatus.FAILED:
                overall_health = "critical"
                health_issues.append("Bridge connection failed")
            elif bridge_status == BridgeStatus.DEGRADED:
                overall_health = "degraded" if overall_health == "healthy" else overall_health
                health_issues.append("Bridge connection degraded")
        
        # Check degradation manager
        if self.degradation_manager:
            deg_status = self.degradation_manager.get_status()
            if deg_status.get("level", "NOMINAL") != "NOMINAL":
                overall_health = "degraded" if overall_health == "healthy" else overall_health
                health_issues.append(f"System degraded: {deg_status.get('level')}")
        
        # Build dashboard
        dashboard = {
            "timestamp": time.time(),
            "component": "ROC",
            "overall_health": overall_health,
            "health_issues": health_issues,
            "uptime_seconds": round(uptime, 2),
            
            # Core status
            "core": {
                "running": self._running,
                "ipc_connected": self.ipc.is_connected,
                "robots_active": len(self.robot_manager.list_robots()),
                "commands_processed": self._commands_processed,
                "dimc_connected": self.dimc is not None
            },
            
            # Agent health
            "agents": {
                "heartbeat": (
                    self.heartbeat_agent.get_health_report() 
                    if self.heartbeat_agent else {"enabled": False}
                ),
                "bridge": (
                    self.bridge_health_agent.get_health_report()
                    if self.bridge_health_agent else {"enabled": False}
                )
            },
            
            # Subsystem health
            "subsystems": {
                "event_recorder": (
                    self.event_recorder.get_statistics()
                    if self.event_recorder else {"enabled": False}
                ),
                "degradation": (
                    self.degradation_manager.get_status()
                    if self.degradation_manager else {"enabled": False}
                ),
                "watchdog": (
                    self.watchdog_manager.get_status()
                    if self.watchdog_manager else {"enabled": False}
                ),
                "state_tracker": (
                    self.state_tracker.get_status()
                    if self.state_tracker else {"enabled": False}
                ),
                "diagnostics": (
                    self.diagnostic_manager.get_status()
                    if self.diagnostic_manager else {"enabled": False}
                ),
                "rate_limiter": (
                    self.rate_limiter.get_status()
                    if self.rate_limiter else {"enabled": False}
                )
            },
            
            # Robot summary
            "robots": self.robot_manager.get_summary(),
            
            # Mode summary
            "modes": self.mode_manager.get_summary(),
            
            # Recent events (if event recorder available)
            "recent_events": (
                [e.to_dict() for e in self.event_recorder.get_events(limit=10)]
                if self.event_recorder else []
            )
        }
        
        return dashboard
