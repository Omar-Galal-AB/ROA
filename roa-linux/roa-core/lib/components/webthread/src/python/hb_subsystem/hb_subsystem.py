"""
hb_subsystem.py
ROA - Robot Operations & Automation
HB Subsystem Main Entry Point

This is the main class that coordinates all HB subsystem components:
- HB Receiver (multi-port)
- Health Aggregator
- HB Watchdog
- State Persistence

Startup Order:
1. State Persistence (load previous state if available)
2. HB Receiver (bind ports first, ready to receive)
3. Health Aggregator (start processing)
4. HB Watchdog (start monitoring)

Usage:
    hb = HBSubsystem()
    hb.start()
    
    # Get health status
    status = hb.get_component_health("FTI")
    
    # Get system summary
    summary = hb.get_system_summary()
    
    # Shutdown
    hb.stop()
"""

import threading
import time
import logging
from typing import Dict, Optional, Callable, List, Any

from .hb_types import (
    ComponentState, HealthLevel, AlertLevel,
    ComponentHealthStatus, CircuitBreakerState,
    FailureType, FailureEvent, ComponentID, HBTiming
)
from .hb_receiver import HBReceiver
from .health_aggregator import HealthAggregator, RecoveryAction
from .hb_watchdog import HBWatchdog, WatchdogStatus
from .state_persistence import StatePersistence, StateRecovery


class HBSubsystem:
    """
    Heartbeat Subsystem - Main entry point.
    
    Coordinates all HB components and provides unified API
    for the Webthread Core.
    """
    
    def __init__(
        self,
        bind_address: str = '127.0.0.1',
        fast_storage_path: Optional[str] = None,
        persistent_storage_path: Optional[str] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize HB Subsystem.
        
        Args:
            bind_address: Address for receivers to bind to
            fast_storage_path: Path for fast state storage
            persistent_storage_path: Path for persistent state storage
            logger: Optional logger
        """
        self.bind_address = bind_address
        self.logger = logger or logging.getLogger("HBSubsystem")
        
        # Components
        self.receiver: Optional[HBReceiver] = None
        self.aggregator: Optional[HealthAggregator] = None
        self.watchdog: Optional[HBWatchdog] = None
        self.persistence: Optional[StatePersistence] = None
        self.state_recovery = StateRecovery(logger=self.logger)
        
        # State
        self._running = False
        self._start_time = 0.0
        
        # Callbacks for WT Core
        self._health_callbacks: List[Callable[[str, ComponentHealthStatus], None]] = []
        self._critical_callbacks: List[Callable[[str, FailureEvent], None]] = []
        self._hb_failure_callbacks: List[Callable[[str, WatchdogStatus], None]] = []
        
        # Recovery executors (registered by WT Core)
        self._recovery_executors: Dict[RecoveryAction, Callable[[str], bool]] = {}
        
        # Initialize components
        self._init_components(fast_storage_path, persistent_storage_path)
        
        self.logger.info("HB Subsystem initialized")
    
    def _init_components(
        self,
        fast_storage_path: Optional[str],
        persistent_storage_path: Optional[str]
    ):
        """Initialize all subsystem components"""
        # 1. State Persistence
        self.persistence = StatePersistence(
            fast_storage_path=fast_storage_path,
            persistent_storage_path=persistent_storage_path,
            snapshot_interval_s=HBTiming.STATE_SNAPSHOT_INTERVAL_S,
            logger=logging.getLogger("HBSubsystem.Persistence")
        )
        self.persistence.set_state_provider(self._get_current_state)
        
        # 2. HB Receiver
        self.receiver = HBReceiver(
            bind_address=self.bind_address,
            logger=logging.getLogger("HBSubsystem.Receiver")
        )
        
        # 3. Health Aggregator
        self.aggregator = HealthAggregator(
            logger=logging.getLogger("HBSubsystem.Aggregator")
        )
        
        # 4. HB Watchdog
        self.watchdog = HBWatchdog(
            check_interval_ms=100,
            default_timeout_ms=500,
            logger=logging.getLogger("HBSubsystem.Watchdog")
        )
        
        # Wire up callbacks
        self._wire_callbacks()
    
    def _wire_callbacks(self):
        """Wire up internal callbacks between components"""
        # Receiver -> Aggregator handled by queues
        
        # Aggregator health changes -> our callbacks
        self.aggregator.on_health_change(self._on_health_change)
        self.aggregator.on_critical_failure(self._on_critical_failure)
        
        # Watchdog failures -> our callbacks
        self.watchdog.on_failure(self._on_watchdog_failure)
        self.watchdog.on_recovery(self._on_watchdog_recovery)
    
    # =========================================================================
    # LIFECYCLE
    # =========================================================================
    
    def start(self) -> bool:
        """
        Start the HB Subsystem.
        
        Startup order is critical:
        1. Load previous state
        2. Start receiver (binds ports)
        3. Start aggregator (connects to receiver queues)
        4. Start watchdog
        5. Start persistence
        
        Returns:
            True if started successfully
        """
        if self._running:
            self.logger.warning("HB Subsystem already running")
            return True
        
        self.logger.info("Starting HB Subsystem...")
        self._start_time = time.time()
        
        try:
            # 1. Load previous state
            self._load_previous_state()
            
            # 2. Start receiver FIRST (so it's ready for agents)
            if not self.receiver.start():
                self.logger.error("Failed to start HB Receiver")
                return False
            
            # 3. Start aggregator (connect to receiver queues)
            self.aggregator.start(
                heartbeat_queue=self.receiver.heartbeat_queue,
                failure_queue=self.receiver.failure_queue
            )
            
            # Register recovery executors
            for action, executor in self._recovery_executors.items():
                self.aggregator.register_recovery_executor(action, executor)
            
            # 4. Start watchdog
            self.watchdog.start()
            
            # Watch receiver and aggregator threads
            # We need access to internal threads - add simple checks
            self.watchdog.watch_queue(
                "heartbeat_queue",
                self.receiver.heartbeat_queue,
                max_depth=500
            )
            self.watchdog.watch_queue(
                "failure_queue",
                self.receiver.failure_queue,
                max_depth=50
            )
            
            # 5. Start persistence
            self.persistence.start()
            
            self._running = True
            self.logger.info("HB Subsystem started successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start HB Subsystem: {e}")
            self.stop()
            return False
    
    def stop(self):
        """Stop the HB Subsystem"""
        if not self._running:
            return
        
        self.logger.info("Stopping HB Subsystem...")
        
        # Stop in reverse order
        try:
            # 1. Stop persistence (takes final snapshot)
            if self.persistence:
                self.persistence.stop()
            
            # 2. Stop watchdog
            if self.watchdog:
                self.watchdog.stop()
            
            # 3. Stop aggregator
            if self.aggregator:
                self.aggregator.stop()
            
            # 4. Stop receiver
            if self.receiver:
                self.receiver.stop()
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
        
        self._running = False
        self.logger.info("HB Subsystem stopped")
    
    def is_running(self) -> bool:
        """Check if subsystem is running"""
        return self._running
    
    def get_uptime(self) -> float:
        """Get subsystem uptime in seconds"""
        if self._start_time:
            return time.time() - self._start_time
        return 0.0
    
    # =========================================================================
    # CALLBACKS FOR WT CORE
    # =========================================================================
    
    def on_health_change(self, callback: Callable[[str, ComponentHealthStatus], None]):
        """Register callback for component health changes"""
        self._health_callbacks.append(callback)
    
    def on_critical_failure(self, callback: Callable[[str, FailureEvent], None]):
        """Register callback for critical failures"""
        self._critical_callbacks.append(callback)
    
    def on_hb_subsystem_failure(self, callback: Callable[[str, WatchdogStatus], None]):
        """Register callback for HB subsystem internal failures"""
        self._hb_failure_callbacks.append(callback)
    
    def register_recovery_executor(self, action: RecoveryAction, executor: Callable[[str], bool]):
        """
        Register executor for recovery actions.
        
        Args:
            action: Recovery action type
            executor: Function that performs recovery, returns success
        """
        self._recovery_executors[action] = executor
        
        # If aggregator already running, register directly
        if self.aggregator:
            self.aggregator.register_recovery_executor(action, executor)
    
    # =========================================================================
    # INTERNAL CALLBACKS
    # =========================================================================
    
    def _on_health_change(self, component_name: str, status: ComponentHealthStatus):
        """Handle health change from aggregator"""
        for callback in self._health_callbacks:
            try:
                callback(component_name, status)
            except Exception as e:
                self.logger.error(f"Error in health callback: {e}")
    
    def _on_critical_failure(self, component_name: str, failure: FailureEvent):
        """Handle critical failure from aggregator"""
        for callback in self._critical_callbacks:
            try:
                callback(component_name, failure)
            except Exception as e:
                self.logger.error(f"Error in critical failure callback: {e}")
    
    def _on_watchdog_failure(self, name: str, status: WatchdogStatus):
        """Handle watchdog detecting internal failure"""
        self.logger.error(f"HB Subsystem internal failure: {name} is {status.value}")
        
        for callback in self._hb_failure_callbacks:
            try:
                callback(name, status)
            except Exception as e:
                self.logger.error(f"Error in HB failure callback: {e}")
    
    def _on_watchdog_recovery(self, name: str):
        """Handle watchdog detecting recovery"""
        self.logger.info(f"HB Subsystem component recovered: {name}")
    
    # =========================================================================
    # STATE MANAGEMENT
    # =========================================================================
    
    def _load_previous_state(self):
        """Load and apply previous state if available"""
        loaded = self.persistence.load_last_state()
        
        if loaded:
            # Recover component states
            recovered = self.state_recovery.recover_component_states(loaded)
            
            if recovered:
                self.logger.info(f"Recovered state for {len(recovered)} components")
                # State will be applied when aggregator starts
            
            # Recover circuit breaker states
            cb_states = self.state_recovery.recover_circuit_breakers(loaded)
            
            if cb_states:
                self.logger.info(f"Recovered circuit breaker states for {len(cb_states)} components")
    
    def _get_current_state(self) -> Dict[str, Any]:
        """Get current state for persistence"""
        state = {
            'components': {},
            'circuit_breakers': {},
            'pending_recoveries': {},
            'failure_counts': {},
            'metrics': {},
        }
        
        if self.aggregator:
            # Get component states
            for name, status in self.aggregator.get_all_health_statuses().items():
                state['components'][name] = status.to_dict()
            
            # Get circuit breaker states
            for name, cb_status in self.aggregator.get_all_circuit_breaker_statuses().items():
                state['circuit_breakers'][name] = {
                    'state': cb_status.state.value,
                    'failure_count': cb_status.failure_count,
                    'success_count': cb_status.success_count,
                    'last_failure_time': cb_status.last_failure_time,
                    'last_success_time': cb_status.last_success_time,
                }
            
            # Get recovery manager state
            for name in ComponentID.BY_NAME.keys():
                count = self.aggregator.recovery_manager.get_attempt_count(name)
                if count > 0:
                    state['pending_recoveries'][name] = count
        
        if self.receiver:
            state['metrics']['receiver'] = self.receiver.get_summary()
        
        if self.watchdog:
            state['metrics']['watchdog'] = self.watchdog.get_metrics()
        
        state['metrics']['uptime_seconds'] = self.get_uptime()
        
        return state
    
    # =========================================================================
    # PUBLIC API
    # =========================================================================
    
    def get_component_health(self, component_name: str) -> Optional[ComponentHealthStatus]:
        """Get health status for a specific component"""
        if self.aggregator:
            return self.aggregator.get_health_status(component_name)
        return None
    
    def get_all_component_health(self) -> Dict[str, ComponentHealthStatus]:
        """Get health status for all components"""
        if self.aggregator:
            return self.aggregator.get_all_health_statuses()
        return {}
    
    def get_alert_level(self, component_name: str) -> AlertLevel:
        """Get current alert level for a component"""
        if self.receiver:
            return self.receiver.get_alert_level(component_name)
        return AlertLevel.GREEN
    
    def get_all_alert_levels(self) -> Dict[str, AlertLevel]:
        """Get alert levels for all components"""
        if self.receiver:
            return self.receiver.get_all_alert_levels()
        return {}
    
    def get_circuit_breaker_state(self, component_name: str) -> Optional[CircuitBreakerState]:
        """Get circuit breaker state for a component"""
        if self.aggregator:
            status = self.aggregator.get_circuit_breaker_status(component_name)
            if status:
                return status.state
        return None
    
    def get_system_summary(self) -> Dict[str, Any]:
        """Get overall system health summary"""
        summary = {
            'running': self._running,
            'uptime_seconds': self.get_uptime(),
            'overall_health': 'unknown',
            'components': {},
        }
        
        if self.aggregator:
            agg_summary = self.aggregator.get_system_health_summary()
            summary.update(agg_summary)
        
        if self.receiver:
            summary['receiver'] = self.receiver.get_summary()
        
        if self.watchdog:
            summary['watchdog'] = self.watchdog.get_metrics()
        
        if self.persistence:
            summary['persistence'] = self.persistence.get_metrics()
        
        return summary
    
    def get_receiver_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get detailed receiver statistics"""
        if self.receiver:
            return self.receiver.get_all_stats()
        return {}
    
    def get_trend_analysis(self, component_name: str) -> Dict[str, Any]:
        """Get trend analysis for a component"""
        if self.aggregator:
            return self.aggregator.trend_analyzer.get_analysis(component_name)
        return {}
    
    def get_recovery_history(self, component_name: Optional[str] = None) -> List[Any]:
        """Get recovery history"""
        if self.aggregator:
            return self.aggregator.recovery_manager.get_history(component_name)
        return []
    
    def trigger_manual_snapshot(self) -> bool:
        """Trigger a manual state snapshot"""
        if self.persistence:
            return self.persistence.manual_snapshot()
        return False
    
    def get_state_history(self, max_entries: int = 10) -> List[Dict[str, Any]]:
        """Get historical state snapshots"""
        if self.persistence:
            return self.persistence.get_history(max_entries)
        return []


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_hb_subsystem(
    bind_address: str = '127.0.0.1',
    fast_storage_path: Optional[str] = None,
    persistent_storage_path: Optional[str] = None
) -> HBSubsystem:
    """
    Create and configure an HB Subsystem instance.
    
    Args:
        bind_address: Address for receivers to bind to
        fast_storage_path: Path for fast state storage
        persistent_storage_path: Path for persistent state storage
        
    Returns:
        Configured HBSubsystem instance
    """
    return HBSubsystem(
        bind_address=bind_address,
        fast_storage_path=fast_storage_path,
        persistent_storage_path=persistent_storage_path
    )
