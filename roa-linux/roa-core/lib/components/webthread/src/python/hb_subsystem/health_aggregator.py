"""
health_aggregator.py
ROA - Robot Operations & Automation
Health Aggregator - Circuit breakers, trend analysis, recovery orchestration

This module aggregates health information from all components, implements
circuit breaker patterns, analyzes health trends, and orchestrates recovery
when failures are detected.

Key Features:
- Circuit breaker per component (from failsafe-go)
- Health trend analysis
- Recovery orchestration with max attempts
- Failure scenario handling
- Recovery verification (3 consecutive healthy HBs)
"""

import threading
import time
import logging
import queue
from typing import Dict, Optional, Callable, List, Any, Tuple
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

from .hb_types import (
    HeartbeatPacket, ComponentState, HealthLevel, AlertLevel,
    ComponentHealthStatus, CircuitBreakerState, CircuitBreakerStatus,
    FailureType, FailureEvent, ComponentID, HBTiming,
    bitmap_to_activities
)


# =============================================================================
# CIRCUIT BREAKER
# =============================================================================

class CircuitBreaker:
    """
    Circuit Breaker pattern from failsafe-go.
    
    States:
    - CLOSED: Normal operation, requests flow through
    - OPEN: Too many failures, requests are blocked
    - HALF_OPEN: Testing if service recovered
    
    Used to isolate failing components and allow graceful recovery.
    """
    
    def __init__(
        self,
        component_name: str,
        failure_threshold: int = 3,
        success_threshold: int = 3,
        timeout_seconds: float = 30.0,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize CircuitBreaker.
        
        Args:
            component_name: Component this breaker protects
            failure_threshold: Failures before opening circuit
            success_threshold: Successes in half-open before closing
            timeout_seconds: Time before transitioning open -> half-open
            logger: Optional logger
        """
        self.component_name = component_name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout_seconds = timeout_seconds
        
        self.logger = logger or logging.getLogger(f"CircuitBreaker.{component_name}")
        
        self._lock = threading.Lock()
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._last_success_time = 0.0
        self._opened_at = 0.0
        self._half_open_at = 0.0
        
        # Callbacks
        self._on_state_change: Optional[Callable[[CircuitBreakerState, CircuitBreakerState], None]] = None
    
    def record_success(self):
        """Record a successful heartbeat/operation"""
        with self._lock:
            self._success_count += 1
            self._last_success_time = time.time()
            
            if self._state == CircuitBreakerState.HALF_OPEN:
                if self._success_count >= self.success_threshold:
                    self._transition(CircuitBreakerState.CLOSED)
            
            elif self._state == CircuitBreakerState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0
    
    def record_failure(self):
        """Record a failed heartbeat/operation"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitBreakerState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._transition(CircuitBreakerState.OPEN)
            
            elif self._state == CircuitBreakerState.HALF_OPEN:
                # Any failure in half-open goes back to open
                self._transition(CircuitBreakerState.OPEN)
    
    def is_available(self) -> bool:
        """
        Check if the circuit allows requests.
        
        Also handles timeout-based transition from OPEN to HALF_OPEN.
        
        Returns:
            True if requests should be allowed
        """
        with self._lock:
            if self._state == CircuitBreakerState.CLOSED:
                return True
            
            elif self._state == CircuitBreakerState.OPEN:
                # Check if timeout has passed
                if time.time() - self._opened_at >= self.timeout_seconds:
                    self._transition(CircuitBreakerState.HALF_OPEN)
                    return True  # Allow test request
                return False
            
            else:  # HALF_OPEN
                return True
    
    def get_state(self) -> CircuitBreakerState:
        """Get current state"""
        with self._lock:
            return self._state
    
    def get_status(self) -> CircuitBreakerStatus:
        """Get detailed status"""
        with self._lock:
            return CircuitBreakerStatus(
                component_name=self.component_name,
                state=self._state,
                failure_count=self._failure_count,
                success_count=self._success_count,
                last_failure_time=self._last_failure_time,
                last_success_time=self._last_success_time,
                open_until=self._opened_at + self.timeout_seconds if self._state == CircuitBreakerState.OPEN else 0,
                half_open_successes=self._success_count if self._state == CircuitBreakerState.HALF_OPEN else 0
            )
    
    def reset(self):
        """Reset circuit breaker to closed state"""
        with self._lock:
            old_state = self._state
            self._state = CircuitBreakerState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            if old_state != CircuitBreakerState.CLOSED:
                self.logger.info(f"Circuit breaker reset from {old_state.value}")
    
    def on_state_change(self, callback: Callable[[CircuitBreakerState, CircuitBreakerState], None]):
        """Register callback for state changes"""
        self._on_state_change = callback
    
    def _transition(self, new_state: CircuitBreakerState):
        """Transition to new state"""
        old_state = self._state
        self._state = new_state
        
        if new_state == CircuitBreakerState.OPEN:
            self._opened_at = time.time()
            self._success_count = 0
            self.logger.warning(f"Circuit OPENED for {self.component_name}")
        
        elif new_state == CircuitBreakerState.HALF_OPEN:
            self._half_open_at = time.time()
            self._success_count = 0
            self.logger.info(f"Circuit HALF-OPEN for {self.component_name}")
        
        elif new_state == CircuitBreakerState.CLOSED:
            self._failure_count = 0
            self.logger.info(f"Circuit CLOSED for {self.component_name}")
        
        if self._on_state_change:
            try:
                self._on_state_change(old_state, new_state)
            except:
                pass


# =============================================================================
# RECOVERY MANAGER
# =============================================================================

class RecoveryAction(Enum):
    """Recovery actions that can be taken"""
    NONE = "none"
    RESTART_COMPONENT = "restart"
    REINITIALIZE = "reinitialize"
    GRACEFUL_SHUTDOWN = "graceful_shutdown"
    FORCE_SHUTDOWN = "force_shutdown"
    NOTIFY_OPERATOR = "notify_operator"
    ENTER_DEGRADED_MODE = "degraded_mode"


@dataclass
class RecoveryAttempt:
    """Record of a recovery attempt"""
    component_name: str
    action: RecoveryAction
    timestamp: float
    trigger_failure: FailureType
    success: Optional[bool] = None
    completed_at: Optional[float] = None
    notes: str = ""


class RecoveryManager:
    """
    Manages recovery attempts for failed components.
    
    Implements max recovery attempts and cooldown periods.
    Tracks recovery history for analysis.
    """
    
    def __init__(
        self,
        max_attempts: int = HBTiming.MAX_RECOVERY_ATTEMPTS,
        cooldown_ms: int = HBTiming.RECOVERY_COOLDOWN_MS,
        verification_count: int = HBTiming.RECOVERY_VERIFICATION_COUNT,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize RecoveryManager.
        
        Args:
            max_attempts: Max recovery attempts before escalation
            cooldown_ms: Cooldown between attempts
            verification_count: Healthy HBs needed to verify recovery
            logger: Optional logger
        """
        self.max_attempts = max_attempts
        self.cooldown_ms = cooldown_ms
        self.verification_count = verification_count
        
        self.logger = logger or logging.getLogger("RecoveryManager")
        
        self._lock = threading.Lock()
        
        # Track attempts per component
        self._attempt_counts: Dict[str, int] = {}
        self._last_attempt_times: Dict[str, float] = {}
        
        # Pending verifications (component -> healthy HB count)
        self._pending_verifications: Dict[str, int] = {}
        
        # Recovery history
        self._history: deque = deque(maxlen=100)
        
        # Callbacks
        self._recovery_executors: Dict[RecoveryAction, Callable[[str], bool]] = {}
        self._on_recovery_exhausted: Optional[Callable[[str], None]] = None
    
    def register_executor(self, action: RecoveryAction, executor: Callable[[str], bool]):
        """
        Register executor for a recovery action.
        
        Args:
            action: Recovery action type
            executor: Function that performs the recovery, returns success bool
        """
        self._recovery_executors[action] = executor
    
    def on_recovery_exhausted(self, callback: Callable[[str], None]):
        """Register callback for when max recovery attempts exceeded"""
        self._on_recovery_exhausted = callback
    
    def attempt_recovery(
        self,
        component_name: str,
        failure: FailureEvent,
        action: RecoveryAction = RecoveryAction.RESTART_COMPONENT
    ) -> bool:
        """
        Attempt recovery for a component.
        
        Args:
            component_name: Component to recover
            failure: Failure that triggered recovery
            action: Recovery action to take
            
        Returns:
            True if recovery was attempted (not necessarily successful)
        """
        with self._lock:
            # Check cooldown
            last_attempt = self._last_attempt_times.get(component_name, 0)
            if (time.time() - last_attempt) * 1000 < self.cooldown_ms:
                self.logger.debug(f"Recovery cooldown active for {component_name}")
                return False
            
            # Check max attempts
            attempts = self._attempt_counts.get(component_name, 0)
            if attempts >= self.max_attempts:
                self.logger.error(
                    f"Max recovery attempts ({self.max_attempts}) exceeded for {component_name}"
                )
                if self._on_recovery_exhausted:
                    try:
                        self._on_recovery_exhausted(component_name)
                    except:
                        pass
                return False
            
            # Record attempt
            self._attempt_counts[component_name] = attempts + 1
            self._last_attempt_times[component_name] = time.time()
            
            attempt = RecoveryAttempt(
                component_name=component_name,
                action=action,
                timestamp=time.time(),
                trigger_failure=failure.failure_type
            )
            
            # Execute recovery
            executor = self._recovery_executors.get(action)
            if executor:
                try:
                    success = executor(component_name)
                    attempt.success = success
                    attempt.completed_at = time.time()
                    
                    if success:
                        self._pending_verifications[component_name] = 0
                        self.logger.info(f"Recovery action {action.value} executed for {component_name}")
                    else:
                        self.logger.warning(f"Recovery action {action.value} failed for {component_name}")
                        
                except Exception as e:
                    attempt.success = False
                    attempt.notes = str(e)
                    self.logger.error(f"Recovery error for {component_name}: {e}")
            else:
                self.logger.warning(f"No executor registered for action {action.value}")
                attempt.notes = "No executor registered"
            
            self._history.append(attempt)
            return True
    
    def record_healthy_heartbeat(self, component_name: str) -> bool:
        """
        Record a healthy heartbeat for verification.
        
        Args:
            component_name: Component that sent healthy HB
            
        Returns:
            True if recovery is now verified
        """
        with self._lock:
            if component_name not in self._pending_verifications:
                return False
            
            self._pending_verifications[component_name] += 1
            count = self._pending_verifications[component_name]
            
            if count >= self.verification_count:
                # Recovery verified
                self.logger.info(
                    f"Recovery verified for {component_name} "
                    f"({self.verification_count} consecutive healthy HBs)"
                )
                del self._pending_verifications[component_name]
                self._attempt_counts[component_name] = 0  # Reset counter
                return True
            
            return False
    
    def is_pending_verification(self, component_name: str) -> bool:
        """Check if component is pending recovery verification"""
        with self._lock:
            return component_name in self._pending_verifications
    
    def get_attempt_count(self, component_name: str) -> int:
        """Get current attempt count for component"""
        with self._lock:
            return self._attempt_counts.get(component_name, 0)
    
    def reset_attempts(self, component_name: str):
        """Reset attempt counter for component"""
        with self._lock:
            self._attempt_counts[component_name] = 0
            if component_name in self._pending_verifications:
                del self._pending_verifications[component_name]
    
    def get_history(self, component_name: Optional[str] = None) -> List[RecoveryAttempt]:
        """Get recovery history, optionally filtered by component"""
        with self._lock:
            if component_name:
                return [a for a in self._history if a.component_name == component_name]
            return list(self._history)


# =============================================================================
# TREND ANALYZER
# =============================================================================

class TrendAnalyzer:
    """
    Analyzes health trends over time.
    
    Detects patterns like:
    - Gradual degradation
    - Repeated failures
    - Response time increases
    """
    
    def __init__(
        self,
        window_size: int = 100,
        degradation_threshold: float = 0.2,  # 20% increase
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize TrendAnalyzer.
        
        Args:
            window_size: Number of samples to analyze
            degradation_threshold: Threshold for detecting degradation
            logger: Optional logger
        """
        self.window_size = window_size
        self.degradation_threshold = degradation_threshold
        self.logger = logger or logging.getLogger("TrendAnalyzer")
        
        self._lock = threading.Lock()
        
        # Per-component data
        self._response_times: Dict[str, deque] = {}
        self._health_levels: Dict[str, deque] = {}
        self._error_counts: Dict[str, deque] = {}
        self._timestamps: Dict[str, deque] = {}
    
    def record(
        self,
        component_name: str,
        response_time_ms: float,
        health_level: HealthLevel,
        error_count: int
    ):
        """Record a data point for analysis"""
        with self._lock:
            if component_name not in self._response_times:
                self._response_times[component_name] = deque(maxlen=self.window_size)
                self._health_levels[component_name] = deque(maxlen=self.window_size)
                self._error_counts[component_name] = deque(maxlen=self.window_size)
                self._timestamps[component_name] = deque(maxlen=self.window_size)
            
            self._response_times[component_name].append(response_time_ms)
            self._health_levels[component_name].append(health_level.value)
            self._error_counts[component_name].append(error_count)
            self._timestamps[component_name].append(time.time())
    
    def is_degrading(self, component_name: str) -> bool:
        """Check if component shows degradation trend"""
        with self._lock:
            if component_name not in self._response_times:
                return False
            
            times = list(self._response_times[component_name])
            if len(times) < 10:
                return False
            
            # Compare recent average to older average
            mid = len(times) // 2
            old_avg = sum(times[:mid]) / mid
            new_avg = sum(times[mid:]) / (len(times) - mid)
            
            if old_avg > 0:
                increase = (new_avg - old_avg) / old_avg
                return increase > self.degradation_threshold
            
            return False
    
    def get_average_response_time(self, component_name: str) -> float:
        """Get average response time for component"""
        with self._lock:
            times = self._response_times.get(component_name)
            if times and len(times) > 0:
                return sum(times) / len(times)
            return 0.0
    
    def get_health_trend(self, component_name: str) -> str:
        """Get health trend description"""
        with self._lock:
            levels = self._health_levels.get(component_name)
            if not levels or len(levels) < 5:
                return "insufficient_data"
            
            levels_list = list(levels)
            mid = len(levels_list) // 2
            old_avg = sum(levels_list[:mid]) / mid
            new_avg = sum(levels_list[mid:]) / (len(levels_list) - mid)
            
            if new_avg < old_avg - 0.5:
                return "improving"
            elif new_avg > old_avg + 0.5:
                return "degrading"
            else:
                return "stable"
    
    def get_analysis(self, component_name: str) -> Dict[str, Any]:
        """Get full trend analysis for component"""
        with self._lock:
            return {
                'component_name': component_name,
                'avg_response_time_ms': self.get_average_response_time(component_name),
                'health_trend': self.get_health_trend(component_name),
                'is_degrading': self.is_degrading(component_name),
                'sample_count': len(self._response_times.get(component_name, [])),
            }


# =============================================================================
# FAILURE SCENARIO HANDLER
# =============================================================================

class FailureScenarioHandler:
    """
    Handles predefined failure scenarios with appropriate responses.
    
    Each scenario has a detection rule and recommended recovery action.
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("FailureScenarioHandler")
        
        # Failure type -> (severity threshold, recovery action)
        self.scenarios: Dict[FailureType, Tuple[HealthLevel, RecoveryAction]] = {
            FailureType.HEARTBEAT_TIMEOUT: (HealthLevel.CRITICAL, RecoveryAction.RESTART_COMPONENT),
            FailureType.SEQUENCE_GAP: (HealthLevel.DEGRADED, RecoveryAction.NONE),  # Monitor only
            FailureType.HEALTH_DEGRADED: (HealthLevel.DEGRADED, RecoveryAction.REINITIALIZE),
            FailureType.HIGH_LATENCY: (HealthLevel.ACCEPTABLE, RecoveryAction.NONE),  # Monitor only
            FailureType.HIGH_MEMORY: (HealthLevel.DEGRADED, RecoveryAction.RESTART_COMPONENT),
            FailureType.HIGH_CPU: (HealthLevel.ACCEPTABLE, RecoveryAction.NONE),  # Monitor only
            FailureType.QUEUE_OVERFLOW: (HealthLevel.DEGRADED, RecoveryAction.REINITIALIZE),
            FailureType.STATE_ERROR: (HealthLevel.CRITICAL, RecoveryAction.RESTART_COMPONENT),
            FailureType.ACTIVITY_MISSING: (HealthLevel.CRITICAL, RecoveryAction.RESTART_COMPONENT),
            FailureType.RATE_ANOMALY: (HealthLevel.ACCEPTABLE, RecoveryAction.NONE),  # Monitor only
            FailureType.CHECKSUM_ERROR: (HealthLevel.ACCEPTABLE, RecoveryAction.NONE),  # Monitor only
            FailureType.STARTUP_FAILURE: (HealthLevel.FAILED, RecoveryAction.RESTART_COMPONENT),
            FailureType.RECOVERY_EXHAUSTED: (HealthLevel.FAILED, RecoveryAction.NOTIFY_OPERATOR),
        }
    
    def get_recommended_action(self, failure: FailureEvent) -> Tuple[bool, RecoveryAction]:
        """
        Get recommended action for a failure.
        
        Args:
            failure: The failure event
            
        Returns:
            Tuple of (should_act, action)
        """
        scenario = self.scenarios.get(failure.failure_type)
        if not scenario:
            return (False, RecoveryAction.NONE)
        
        severity_threshold, action = scenario
        
        # Only act if severity meets threshold
        if failure.severity.value >= severity_threshold.value:
            return (True, action)
        
        return (False, RecoveryAction.NONE)


# =============================================================================
# HEALTH AGGREGATOR - MAIN CLASS
# =============================================================================

class HealthAggregator:
    """
    Main Health Aggregator.
    
    Combines all health information, runs circuit breakers, analyzes trends,
    and orchestrates recovery.
    
    Usage:
        aggregator = HealthAggregator()
        aggregator.register_recovery_executor(RecoveryAction.RESTART_COMPONENT, restart_fn)
        aggregator.start()
        
        # Process heartbeats (from receiver queue)
        aggregator.process_heartbeat(component_name, packet)
        
        # Process failures (from receiver queue)
        aggregator.process_failure(failure_event)
    """
    
    def __init__(
        self,
        logger: Optional[logging.Logger] = None
    ):
        """Initialize HealthAggregator"""
        self.logger = logger or logging.getLogger("HealthAggregator")
        
        # Component health statuses
        self._health_statuses: Dict[str, ComponentHealthStatus] = {}
        self._lock = threading.RLock()
        
        # Circuit breakers per component
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # Recovery manager
        self.recovery_manager = RecoveryManager(logger=self.logger)
        
        # Trend analyzer
        self.trend_analyzer = TrendAnalyzer(logger=self.logger)
        
        # Failure scenario handler
        self.scenario_handler = FailureScenarioHandler(logger=self.logger)
        
        # Processing thread
        self._running = False
        self._stop_event = threading.Event()
        
        # Queues (will be linked to receiver queues)
        self.heartbeat_queue: Optional[queue.Queue] = None
        self.failure_queue: Optional[queue.Queue] = None
        
        # Callbacks
        self._health_callbacks: List[Callable[[str, ComponentHealthStatus], None]] = []
        self._critical_callbacks: List[Callable[[str, FailureEvent], None]] = []
        
        # Initialize circuit breakers for known components
        for component_name in ComponentID.BY_NAME.keys():
            self._circuit_breakers[component_name] = CircuitBreaker(
                component_name,
                logger=logging.getLogger(f"CircuitBreaker.{component_name}")
            )
    
    def start(
        self,
        heartbeat_queue: queue.Queue,
        failure_queue: queue.Queue
    ):
        """
        Start the aggregator.
        
        Args:
            heartbeat_queue: Queue to receive heartbeats from
            failure_queue: Queue to receive failures from
        """
        self.heartbeat_queue = heartbeat_queue
        self.failure_queue = failure_queue
        
        self._running = True
        self._stop_event.clear()
        
        # Start processing thread
        self._process_thread = threading.Thread(target=self._process_loop, daemon=True)
        self._process_thread.name = "HealthAggregator"
        self._process_thread.start()
        
        self.logger.info("HealthAggregator started")
    
    def stop(self):
        """Stop the aggregator"""
        self._running = False
        self._stop_event.set()
        
        if hasattr(self, '_process_thread') and self._process_thread.is_alive():
            self._process_thread.join(timeout=1.0)
        
        self.logger.info("HealthAggregator stopped")
    
    # =========================================================================
    # CALLBACKS
    # =========================================================================
    
    def on_health_change(self, callback: Callable[[str, ComponentHealthStatus], None]):
        """Register callback for health status changes"""
        self._health_callbacks.append(callback)
    
    def on_critical_failure(self, callback: Callable[[str, FailureEvent], None]):
        """Register callback for critical failures"""
        self._critical_callbacks.append(callback)
    
    def register_recovery_executor(self, action: RecoveryAction, executor: Callable[[str], bool]):
        """Register executor for recovery action"""
        self.recovery_manager.register_executor(action, executor)
    
    # =========================================================================
    # PROCESSING
    # =========================================================================
    
    def _process_loop(self):
        """Main processing loop"""
        self.logger.debug("Processing loop started")
        
        while self._running and not self._stop_event.is_set():
            try:
                # Process heartbeats
                self._drain_heartbeat_queue()
                
                # Process failures
                self._drain_failure_queue()
                
            except Exception as e:
                self.logger.error(f"Error in processing loop: {e}")
            
            self._stop_event.wait(0.010)  # 10ms tick
        
        self.logger.debug("Processing loop ended")
    
    def _drain_heartbeat_queue(self):
        """Process all pending heartbeats"""
        if not self.heartbeat_queue:
            return
        
        while not self.heartbeat_queue.empty():
            try:
                component_name, packet = self.heartbeat_queue.get_nowait()
                self._process_heartbeat(component_name, packet)
            except queue.Empty:
                break
            except Exception as e:
                self.logger.error(f"Error processing heartbeat: {e}")
    
    def _drain_failure_queue(self):
        """Process all pending failures"""
        if not self.failure_queue:
            return
        
        while not self.failure_queue.empty():
            try:
                failure = self.failure_queue.get_nowait()
                self._process_failure(failure)
            except queue.Empty:
                break
            except Exception as e:
                self.logger.error(f"Error processing failure: {e}")
    
    def _process_heartbeat(self, component_name: str, packet: HeartbeatPacket):
        """Process a received heartbeat"""
        with self._lock:
            # Update circuit breaker
            cb = self._circuit_breakers.get(component_name)
            if cb:
                cb.record_success()
            
            # Get/create health status
            status = self._health_statuses.get(component_name)
            if status is None:
                status = ComponentHealthStatus(
                    component_id=packet.component_id,
                    component_name=component_name,
                    state=packet.state,
                    health=packet.health,
                    alert_level=AlertLevel.GREEN,
                    last_heartbeat_time=time.time(),
                    last_sequence=packet.sequence,
                    consecutive_misses=0,
                    response_time_avg_ms=packet.response_time_us / 1000.0,
                    error_count=packet.error_count,
                    recovery_attempts=0,
                    memory_percent=packet.memory_percent,
                    cpu_percent=packet.cpu_percent,
                    queue_depth=packet.queue_depth,
                    last_activities=bitmap_to_activities(packet.activity_bitmap),
                    warnings=[]
                )
                self._health_statuses[component_name] = status
            else:
                # Update existing status
                status.state = packet.state
                status.health = packet.health
                status.alert_level = AlertLevel.GREEN
                status.last_heartbeat_time = time.time()
                status.last_sequence = packet.sequence
                status.consecutive_misses = 0
                status.error_count = packet.error_count
                status.memory_percent = packet.memory_percent
                status.cpu_percent = packet.cpu_percent
                status.queue_depth = packet.queue_depth
                status.last_activities = bitmap_to_activities(packet.activity_bitmap)
                status.updated_at = time.time()
                
                # Rolling average for response time
                old_avg = status.response_time_avg_ms
                new_time = packet.response_time_us / 1000.0
                status.response_time_avg_ms = old_avg * 0.9 + new_time * 0.1
            
            # Record for trend analysis
            self.trend_analyzer.record(
                component_name,
                packet.response_time_us / 1000.0,
                packet.health,
                packet.error_count
            )
            
            # Check recovery verification
            if self.recovery_manager.record_healthy_heartbeat(component_name):
                status.recovery_attempts = 0
            
            # Check for warnings
            self._check_warnings(status, packet)
        
        # Notify callbacks
        self._notify_health_change(component_name, status)
    
    def _process_failure(self, failure: FailureEvent):
        """Process a failure event"""
        component_name = failure.component_name
        
        with self._lock:
            # Update circuit breaker
            cb = self._circuit_breakers.get(component_name)
            if cb:
                cb.record_failure()
            
            # Update health status
            status = self._health_statuses.get(component_name)
            if status:
                status.consecutive_misses += 1
                status.health = max(status.health, failure.severity, key=lambda h: h.value)
                
                if failure.failure_type == FailureType.HEARTBEAT_TIMEOUT:
                    # Determine alert level
                    if failure.severity == HealthLevel.FAILED:
                        status.alert_level = AlertLevel.BLACK
                    elif failure.severity == HealthLevel.CRITICAL:
                        status.alert_level = AlertLevel.RED
                    elif failure.severity == HealthLevel.DEGRADED:
                        status.alert_level = AlertLevel.ORANGE
                    else:
                        status.alert_level = AlertLevel.YELLOW
                
                status.warnings.append(failure.details)
                if len(status.warnings) > 10:
                    status.warnings = status.warnings[-10:]
                
                status.updated_at = time.time()
        
        # Determine if action needed
        should_act, action = self.scenario_handler.get_recommended_action(failure)
        
        if should_act and action != RecoveryAction.NONE:
            self.recovery_manager.attempt_recovery(component_name, failure, action)
            
            with self._lock:
                status = self._health_statuses.get(component_name)
                if status:
                    status.recovery_attempts = self.recovery_manager.get_attempt_count(component_name)
        
        # Notify if critical
        if failure.severity.value >= HealthLevel.CRITICAL.value:
            for callback in self._critical_callbacks:
                try:
                    callback(component_name, failure)
                except:
                    pass
    
    def _check_warnings(self, status: ComponentHealthStatus, packet: HeartbeatPacket):
        """Check for warning conditions"""
        warnings = []
        
        # High memory
        if packet.memory_percent > 80:
            warnings.append(f"High memory usage: {packet.memory_percent}%")
        
        # High CPU
        if packet.cpu_percent > 90:
            warnings.append(f"High CPU usage: {packet.cpu_percent}%")
        
        # High queue depth
        if packet.queue_depth > 100:
            warnings.append(f"High queue depth: {packet.queue_depth}")
        
        # Degrading trend
        if self.trend_analyzer.is_degrading(status.component_name):
            warnings.append("Performance degradation trend detected")
        
        status.warnings = warnings
    
    def _notify_health_change(self, component_name: str, status: ComponentHealthStatus):
        """Notify callbacks of health change"""
        for callback in self._health_callbacks:
            try:
                callback(component_name, status)
            except:
                pass
    
    # =========================================================================
    # PUBLIC API
    # =========================================================================
    
    def get_health_status(self, component_name: str) -> Optional[ComponentHealthStatus]:
        """Get health status for a component"""
        with self._lock:
            return self._health_statuses.get(component_name)
    
    def get_all_health_statuses(self) -> Dict[str, ComponentHealthStatus]:
        """Get health statuses for all components"""
        with self._lock:
            return self._health_statuses.copy()
    
    def get_circuit_breaker_status(self, component_name: str) -> Optional[CircuitBreakerStatus]:
        """Get circuit breaker status for a component"""
        cb = self._circuit_breakers.get(component_name)
        if cb:
            return cb.get_status()
        return None
    
    def get_all_circuit_breaker_statuses(self) -> Dict[str, CircuitBreakerStatus]:
        """Get circuit breaker statuses for all components"""
        return {
            name: cb.get_status()
            for name, cb in self._circuit_breakers.items()
        }
    
    def get_system_health_summary(self) -> Dict[str, Any]:
        """Get overall system health summary"""
        with self._lock:
            total = len(self._health_statuses)
            if total == 0:
                return {
                    'overall_health': 'unknown',
                    'total_components': 0,
                    'healthy_count': 0,
                    'degraded_count': 0,
                    'failed_count': 0,
                }
            
            healthy = sum(1 for s in self._health_statuses.values() 
                         if s.health.value <= HealthLevel.HEALTHY.value)
            degraded = sum(1 for s in self._health_statuses.values()
                          if s.health in [HealthLevel.ACCEPTABLE, HealthLevel.DEGRADED])
            failed = sum(1 for s in self._health_statuses.values()
                        if s.health.value >= HealthLevel.CRITICAL.value)
            
            if failed > 0:
                overall = 'critical'
            elif degraded > 0:
                overall = 'degraded'
            elif healthy == total:
                overall = 'healthy'
            else:
                overall = 'unknown'
            
            return {
                'overall_health': overall,
                'total_components': total,
                'healthy_count': healthy,
                'degraded_count': degraded,
                'failed_count': failed,
                'component_statuses': {
                    name: {
                        'health': status.health.name,
                        'state': status.state.name,
                        'alert': status.alert_level.name,
                    }
                    for name, status in self._health_statuses.items()
                }
            }
