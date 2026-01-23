"""
COMC Resilience Module
======================
Circuit breakers, rate limiters, and recovery mechanisms for COMC.

This module addresses critical resilience gaps:
1. Circuit Breaker - Prevent cascading failures
2. Rate Limiter - Protect against overload
3. Retry Logic - Smart retry with backoff
4. Bulkhead - Isolate failures
5. Recovery Manager - Automated recovery procedures

Based on patterns from:
- Netflix Hystrix
- Microsoft Polly
- resilience4j
"""

import functools
import logging
import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

T = TypeVar("T")


# =============================================================================
# ENUMS
# =============================================================================


class CircuitState(Enum):
    """Circuit breaker states"""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, rejecting calls
    HALF_OPEN = "half_open"  # Testing if recovered


class RecoveryState(Enum):
    """Recovery procedure states"""

    IDLE = "idle"
    DETECTING = "detecting"
    RECOVERING = "recovering"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


# =============================================================================
# CIRCUIT BREAKER
# =============================================================================


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 3  # Successes before closing
    timeout_seconds: float = 30.0  # Time before half-open
    half_open_max_calls: int = 3  # Max calls in half-open state


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker"""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state_changes: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0


class CircuitBreaker:
    """
    Circuit Breaker implementation for COMC.

    Prevents cascading failures by monitoring error rates
    and temporarily blocking calls when failure threshold is exceeded.

    States:
    - CLOSED: Normal operation, all calls pass through
    - OPEN: Too many failures, calls are rejected immediately
    - HALF_OPEN: Testing recovery, limited calls allowed

    Usage:
        cb = CircuitBreaker("dimc_connection")

        try:
            result = cb.call(my_function, arg1, arg2)
        except CircuitBreakerOpenError:
            # Handle circuit open (use fallback)
            pass
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.logger = logger or logging.getLogger(f"CircuitBreaker.{name}")

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time = 0.0
        self._stats = CircuitBreakerStats()
        self._lock = threading.RLock()

        # Callbacks
        self._on_open: Optional[Callable[[], None]] = None
        self._on_close: Optional[Callable[[], None]] = None
        self._on_half_open: Optional[Callable[[], None]] = None

    @property
    def state(self) -> CircuitState:
        """Get current state (with timeout check)."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if timeout has passed
                if time.time() - self._last_failure_time > self.config.timeout_seconds:
                    self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Execute function through circuit breaker.

        Raises:
            CircuitBreakerOpenError: If circuit is open
            Original exception: If function fails
        """
        with self._lock:
            self._stats.total_calls += 1

            # Check state
            current_state = self.state

            if current_state == CircuitState.OPEN:
                self._stats.rejected_calls += 1
                raise CircuitBreakerOpenError(f"Circuit {self.name} is OPEN")

            if current_state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    self._stats.rejected_calls += 1
                    raise CircuitBreakerOpenError(
                        f"Circuit {self.name} is HALF_OPEN (max calls reached)"
                    )
                self._half_open_calls += 1

        # Execute function
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        """Handle successful call."""
        with self._lock:
            self._stats.successful_calls += 1
            self._stats.last_success_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
            else:
                # Reset failure count on success in CLOSED state
                self._failure_count = 0

    def _on_failure(self):
        """Handle failed call."""
        with self._lock:
            self._stats.failed_calls += 1
            self._stats.last_failure_time = time.time()
            self._last_failure_time = time.time()
            self._failure_count += 1

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open goes back to open
                self._transition_to(CircuitState.OPEN)
            elif self._failure_count >= self.config.failure_threshold:
                self._transition_to(CircuitState.OPEN)

    def _transition_to(self, new_state: CircuitState):
        """Transition to a new state."""
        if new_state == self._state:
            return

        old_state = self._state
        self._state = new_state
        self._stats.state_changes += 1

        self.logger.info(f"Circuit {self.name}: {old_state.value} -> {new_state.value}")

        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
            if self._on_close:
                self._on_close()

        elif new_state == CircuitState.OPEN:
            self._success_count = 0
            self._half_open_calls = 0
            if self._on_open:
                self._on_open()

        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0
            self._half_open_calls = 0
            if self._on_half_open:
                self._on_half_open()

    def reset(self):
        """Manually reset circuit to CLOSED."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)

    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "stats": {
                    "total_calls": self._stats.total_calls,
                    "successful_calls": self._stats.successful_calls,
                    "failed_calls": self._stats.failed_calls,
                    "rejected_calls": self._stats.rejected_calls,
                    "state_changes": self._stats.state_changes,
                },
            }

    # Callbacks
    def on_open(self, callback: Callable[[], None]):
        self._on_open = callback

    def on_close(self, callback: Callable[[], None]):
        self._on_close = callback

    def on_half_open(self, callback: Callable[[], None]):
        self._on_half_open = callback


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""

    pass


# =============================================================================
# RATE LIMITER
# =============================================================================


class RateLimiter:
    """
    Token bucket rate limiter for COMC.

    Controls the rate of operations to prevent overload.

    Usage:
        limiter = RateLimiter(rate=100, burst=10)  # 100/sec, burst of 10

        if limiter.acquire():
            # Perform operation
        else:
            # Rate limited, reject or queue
    """

    def __init__(
        self,
        rate: float,
        burst: int = 1,
        name: str = "default",
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize rate limiter.

        Args:
            rate: Operations per second
            burst: Maximum burst size
            name: Limiter name for logging
        """
        self.rate = rate
        self.burst = burst
        self.name = name
        self.logger = logger or logging.getLogger(f"RateLimiter.{name}")

        self._tokens = float(burst)
        self._last_update = time.time()
        self._lock = threading.Lock()

        # Stats
        self._acquired_count = 0
        self._rejected_count = 0

    def acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            True if acquired, False if rate limited
        """
        with self._lock:
            now = time.time()

            # Refill tokens based on elapsed time
            elapsed = now - self._last_update
            self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
            self._last_update = now

            if self._tokens >= tokens:
                self._tokens -= tokens
                self._acquired_count += 1
                return True
            else:
                self._rejected_count += 1
                return False

    def wait_and_acquire(self, tokens: int = 1, timeout: float = 5.0) -> bool:
        """
        Wait for tokens to become available.

        Args:
            tokens: Number of tokens to acquire
            timeout: Maximum wait time in seconds

        Returns:
            True if acquired, False if timeout
        """
        deadline = time.time() + timeout

        while time.time() < deadline:
            if self.acquire(tokens):
                return True

            # Calculate wait time
            with self._lock:
                tokens_needed = tokens - self._tokens
                wait_time = tokens_needed / self.rate

            time.sleep(min(wait_time, 0.1))

        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics."""
        with self._lock:
            return {
                "name": self.name,
                "rate": self.rate,
                "burst": self.burst,
                "current_tokens": self._tokens,
                "acquired": self._acquired_count,
                "rejected": self._rejected_count,
                "rejection_rate": self._rejected_count
                / max(1, self._acquired_count + self._rejected_count),
            }


# =============================================================================
# RETRY WITH BACKOFF
# =============================================================================


@dataclass
class RetryConfig:
    """Configuration for retry logic"""

    max_attempts: int = 3
    initial_delay_ms: int = 100
    max_delay_ms: int = 5000
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple = (Exception,)


class RetryHandler:
    """
    Retry handler with exponential backoff.

    Features:
    - Exponential backoff
    - Jitter to prevent thundering herd
    - Configurable retry conditions
    - Statistics tracking

    Usage:
        retry = RetryHandler(RetryConfig(max_attempts=3))

        result = retry.execute(my_function, arg1, arg2)
    """

    def __init__(
        self,
        config: Optional[RetryConfig] = None,
        name: str = "default",
        logger: Optional[logging.Logger] = None,
    ):
        self.config = config or RetryConfig()
        self.name = name
        self.logger = logger or logging.getLogger(f"RetryHandler.{name}")

        # Stats
        self._total_attempts = 0
        self._successful_attempts = 0
        self._failed_attempts = 0
        self._retries = 0

    def execute(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Execute function with retry logic.

        Raises:
            Last exception if all retries fail
        """
        last_exception = None

        for attempt in range(1, self.config.max_attempts + 1):
            self._total_attempts += 1

            try:
                result = func(*args, **kwargs)
                self._successful_attempts += 1

                if attempt > 1:
                    self.logger.info(f"Retry {self.name} succeeded on attempt {attempt}")

                return result

            except self.config.retryable_exceptions as e:
                last_exception = e
                self._failed_attempts += 1

                if attempt < self.config.max_attempts:
                    self._retries += 1
                    delay = self._calculate_delay(attempt)
                    self.logger.warning(
                        f"Retry {self.name} attempt {attempt} failed: {e}. "
                        f"Retrying in {delay:.0f}ms..."
                    )
                    time.sleep(delay / 1000.0)
                else:
                    self.logger.error(
                        f"Retry {self.name} exhausted all {self.config.max_attempts} attempts"
                    )

        raise last_exception

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff and jitter."""
        delay = self.config.initial_delay_ms * (self.config.exponential_base ** (attempt - 1))
        delay = min(delay, self.config.max_delay_ms)

        if self.config.jitter:
            # Add random jitter (0.5x to 1.5x)
            jitter_factor = 0.5 + random.random()
            delay *= jitter_factor

        return delay

    def get_stats(self) -> Dict[str, Any]:
        """Get retry statistics."""
        return {
            "name": self.name,
            "total_attempts": self._total_attempts,
            "successful": self._successful_attempts,
            "failed": self._failed_attempts,
            "retries": self._retries,
            "success_rate": self._successful_attempts / max(1, self._total_attempts),
        }


# =============================================================================
# BULKHEAD (ISOLATION)
# =============================================================================


class Bulkhead:
    """
    Bulkhead pattern for isolating failures.

    Limits concurrent executions to prevent one slow dependency
    from exhausting all resources.

    Usage:
        bulkhead = Bulkhead(max_concurrent=10, max_wait_ms=1000)

        with bulkhead:
            # Protected operation
    """

    def __init__(
        self,
        max_concurrent: int = 10,
        max_wait_ms: int = 1000,
        name: str = "default",
        logger: Optional[logging.Logger] = None,
    ):
        self.max_concurrent = max_concurrent
        self.max_wait_ms = max_wait_ms
        self.name = name
        self.logger = logger or logging.getLogger(f"Bulkhead.{name}")

        self._semaphore = threading.Semaphore(max_concurrent)
        self._current = 0
        self._lock = threading.Lock()

        # Stats
        self._acquired_count = 0
        self._rejected_count = 0
        self._max_concurrent_reached = 0

    def __enter__(self):
        if not self._semaphore.acquire(timeout=self.max_wait_ms / 1000.0):
            self._rejected_count += 1
            raise BulkheadFullError(f"Bulkhead {self.name} is full")

        with self._lock:
            self._current += 1
            self._acquired_count += 1
            if self._current > self._max_concurrent_reached:
                self._max_concurrent_reached = self._current

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        with self._lock:
            self._current -= 1
        self._semaphore.release()
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get bulkhead statistics."""
        with self._lock:
            return {
                "name": self.name,
                "max_concurrent": self.max_concurrent,
                "current_concurrent": self._current,
                "acquired": self._acquired_count,
                "rejected": self._rejected_count,
                "max_reached": self._max_concurrent_reached,
            }


class BulkheadFullError(Exception):
    """Raised when bulkhead is at capacity."""

    pass


# =============================================================================
# RECOVERY MANAGER
# =============================================================================


@dataclass
class RecoveryProcedure:
    """Definition of a recovery procedure"""

    name: str
    description: str
    condition: Callable[[], bool]  # Returns True if recovery needed
    action: Callable[[], bool]  # Returns True if recovery succeeded
    verification: Callable[[], bool]  # Returns True if recovery verified
    cooldown_seconds: float = 60.0
    max_attempts: int = 3


class RecoveryManager:
    """
    Manages automated recovery procedures.

    Features:
    - Automatic detection and recovery
    - Cooldown between attempts
    - Verification of recovery
    - Recovery history tracking

    Usage:
        recovery = RecoveryManager()

        recovery.register_procedure(RecoveryProcedure(
            name="reconnect_dimc",
            description="Reconnect to DIMC",
            condition=lambda: not dimc_connected(),
            action=lambda: reconnect_dimc(),
            verification=lambda: dimc_connected(),
        ))

        recovery.start()
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("RecoveryManager")
        self.procedures: Dict[str, RecoveryProcedure] = {}
        self._lock = threading.RLock()

        # State
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._check_interval = 5.0

        # Recovery tracking
        self._last_attempt: Dict[str, float] = {}
        self._attempt_count: Dict[str, int] = {}
        self._recovery_history: deque = deque(maxlen=100)

    def register_procedure(self, procedure: RecoveryProcedure):
        """Register a recovery procedure."""
        with self._lock:
            self.procedures[procedure.name] = procedure
            self._last_attempt[procedure.name] = 0.0
            self._attempt_count[procedure.name] = 0
            self.logger.info(f"Registered recovery procedure: {procedure.name}")

    def start(self):
        """Start automatic recovery monitoring."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._recovery_loop, daemon=True)
        self._thread.name = "RecoveryManager"
        self._thread.start()
        self.logger.info("Recovery Manager started")

    def stop(self):
        """Stop automatic recovery monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        self.logger.info("Recovery Manager stopped")

    def _recovery_loop(self):
        """Background recovery monitoring loop."""
        while self._running:
            try:
                self._check_and_recover()
            except Exception as e:
                self.logger.error(f"Recovery loop error: {e}")

            time.sleep(self._check_interval)

    def _check_and_recover(self):
        """Check conditions and execute recovery if needed."""
        with self._lock:
            now = time.time()

            for name, procedure in self.procedures.items():
                # Check cooldown
                if now - self._last_attempt.get(name, 0) < procedure.cooldown_seconds:
                    continue

                # Check max attempts
                if self._attempt_count.get(name, 0) >= procedure.max_attempts:
                    continue

                # Check condition
                try:
                    if procedure.condition():
                        self.logger.warning(f"Recovery needed: {procedure.description}")
                        self._execute_recovery(procedure)
                except Exception as e:
                    self.logger.error(f"Recovery condition check failed for {name}: {e}")

    def _execute_recovery(self, procedure: RecoveryProcedure):
        """Execute a recovery procedure."""
        name = procedure.name
        self._last_attempt[name] = time.time()
        self._attempt_count[name] = self._attempt_count.get(name, 0) + 1

        record = {
            "procedure": name,
            "timestamp": time.time(),
            "attempt": self._attempt_count[name],
            "success": False,
            "verified": False,
        }

        try:
            # Execute recovery action
            self.logger.info(f"Executing recovery: {name} (attempt {self._attempt_count[name]})")

            if procedure.action():
                self.logger.info(f"Recovery action completed: {name}")

                # Verify recovery
                time.sleep(1.0)  # Brief wait before verification

                if procedure.verification():
                    self.logger.info(f"Recovery verified: {name}")
                    record["success"] = True
                    record["verified"] = True
                    self._attempt_count[name] = 0  # Reset on success
                else:
                    self.logger.warning(f"Recovery verification failed: {name}")
                    record["success"] = True
                    record["verified"] = False
            else:
                self.logger.warning(f"Recovery action failed: {name}")

        except Exception as e:
            self.logger.error(f"Recovery error for {name}: {e}")
            record["error"] = str(e)

        self._recovery_history.append(record)

    def trigger_recovery(self, procedure_name: str) -> bool:
        """Manually trigger a recovery procedure."""
        with self._lock:
            if procedure_name not in self.procedures:
                return False

            procedure = self.procedures[procedure_name]
            self._execute_recovery(procedure)
            return True

    def get_status(self) -> Dict[str, Any]:
        """Get recovery manager status."""
        with self._lock:
            return {
                "running": self._running,
                "procedures": list(self.procedures.keys()),
                "attempt_counts": dict(self._attempt_count),
                "history": list(self._recovery_history),
            }


# =============================================================================
# UNIFIED RESILIENCE MANAGER
# =============================================================================


class COMCResilienceManager:
    """
    Unified resilience manager for COMC.

    Provides coordinated access to all resilience patterns.

    Enhanced with:
    - Per-operation circuit breakers (P3 Gap Fix)
    - Enhanced degradation modes (P3 Gap Fix)
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("COMCResilience")

        # Circuit breakers for each component
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}

        # Per-operation circuit breakers (P3 Gap Fix)
        self.operation_breakers = PerOperationCircuitBreakers(logger=self.logger)

        # Rate limiters
        self.rate_limiters: Dict[str, RateLimiter] = {}

        # Bulkheads
        self.bulkheads: Dict[str, Bulkhead] = {}

        # Retry handlers
        self.retry_handlers: Dict[str, RetryHandler] = {}

        # Recovery manager
        self.recovery_manager = RecoveryManager(logger)

        # Degradation manager (P3 Gap Fix)
        self.degradation_manager = DegradationManager(logger=self.logger)

        # Initialize default components
        self._init_defaults()

        self.logger.info("COMC Resilience Manager initialized")

    def _init_defaults(self):
        """Initialize default resilience components."""
        # Circuit breakers for component connections
        for component in ["DIMC", "ROC", "FTI", "Webthread", "UE5Bridge"]:
            self.circuit_breakers[component] = CircuitBreaker(
                name=component,
                config=CircuitBreakerConfig(failure_threshold=5, timeout_seconds=30.0),
                logger=self.logger,
            )

        # Rate limiters
        self.rate_limiters["messages"] = RateLimiter(
            rate=1000, burst=100, name="messages", logger=self.logger
        )
        self.rate_limiters["commands"] = RateLimiter(
            rate=100, burst=20, name="commands", logger=self.logger
        )

        # Bulkheads
        self.bulkheads["coordination"] = Bulkhead(
            max_concurrent=50, name="coordination", logger=self.logger
        )
        self.bulkheads["communication"] = Bulkhead(
            max_concurrent=100, name="communication", logger=self.logger
        )

        # Retry handlers
        self.retry_handlers["connection"] = RetryHandler(
            config=RetryConfig(max_attempts=3, initial_delay_ms=500),
            name="connection",
            logger=self.logger,
        )

        # Link degradation to circuit breakers
        self.degradation_manager.on_level_change(self._on_degradation_change)

    def _on_degradation_change(self, old_level: DegradationLevel, new_level: DegradationLevel):
        """Handle degradation level changes"""
        # Log the change
        self.logger.warning(f"System degradation: {old_level.value} -> {new_level.value}")

        # In emergency mode, reset safety circuits to ensure they work
        if new_level == DegradationLevel.EMERGENCY:
            self.operation_breakers.reset_category("safety")

    def get_circuit_breaker(self, name: str) -> CircuitBreaker:
        """Get or create a circuit breaker."""
        if name not in self.circuit_breakers:
            self.circuit_breakers[name] = CircuitBreaker(name=name, logger=self.logger)
        return self.circuit_breakers[name]

    def get_operation_breaker(self, operation: OperationType) -> CircuitBreaker:
        """Get circuit breaker for a specific operation type."""
        return self.operation_breakers.get(operation)

    def call_operation(
        self, operation: OperationType, func: Callable[..., T], *args, **kwargs
    ) -> T:
        """Execute function through operation-specific circuit breaker."""
        return self.operation_breakers.call(operation, func, *args, **kwargs)

    def get_rate_limiter(self, name: str, rate: float = 100, burst: int = 10) -> RateLimiter:
        """Get or create a rate limiter."""
        if name not in self.rate_limiters:
            self.rate_limiters[name] = RateLimiter(
                rate=rate, burst=burst, name=name, logger=self.logger
            )
        return self.rate_limiters[name]

    def is_feature_enabled(self, feature_name: str) -> bool:
        """Check if a feature is enabled (not degraded)."""
        return self.degradation_manager.is_feature_enabled(feature_name)

    def update_system_metrics(
        self,
        cpu: float = None,
        memory: float = None,
        error_rate: float = None,
        latency_ms: float = None,
    ):
        """Update system metrics for degradation monitoring."""
        open_circuits = len(self.operation_breakers.get_open_circuits())
        open_circuits += sum(
            1 for cb in self.circuit_breakers.values() if cb.state == CircuitState.OPEN
        )

        self.degradation_manager.update_metrics(
            cpu_percent=cpu,
            memory_percent=memory,
            error_rate=error_rate,
            open_circuits=open_circuits,
            latency_ms=latency_ms,
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get all resilience statistics."""
        return {
            "circuit_breakers": {
                name: cb.get_stats() for name, cb in self.circuit_breakers.items()
            },
            "operation_breakers": self.operation_breakers.get_stats(),
            "rate_limiters": {name: rl.get_stats() for name, rl in self.rate_limiters.items()},
            "bulkheads": {name: bh.get_stats() for name, bh in self.bulkheads.items()},
            "retry_handlers": {name: rh.get_stats() for name, rh in self.retry_handlers.items()},
            "recovery": self.recovery_manager.get_status(),
            "degradation": self.degradation_manager.get_status(),
        }

    def get_health_summary(self) -> Dict[str, Any]:
        """Get a summary of system health."""
        op_stats = self.operation_breakers.get_stats()
        deg_status = self.degradation_manager.get_status()

        component_health = {}
        for name, cb in self.circuit_breakers.items():
            component_health[name] = {
                "state": cb.state.value,
                "healthy": cb.state == CircuitState.CLOSED,
            }

        return {
            "degradation_level": deg_status["current_level"],
            "open_operation_circuits": op_stats["summary"]["open_circuits"],
            "healthy_operations": op_stats["summary"]["healthy_operations"],
            "component_health": component_health,
            "disabled_features": deg_status["disabled_features"],
        }

    def start(self):
        """Start resilience manager."""
        self.recovery_manager.start()

    def stop(self):
        """Stop resilience manager."""
        self.recovery_manager.stop()


# =============================================================================
# PER-OPERATION CIRCUIT BREAKERS (P3 Gap Fix)
# =============================================================================


class OperationType(Enum):
    """Types of operations for per-operation circuit breakers"""

    # Communication operations
    SEND_MESSAGE = "send_message"
    RECEIVE_MESSAGE = "receive_message"
    PUBLISH_TOPIC = "publish_topic"
    SUBSCRIBE_TOPIC = "subscribe_topic"

    # Coordination operations
    REQUEST_LOCK = "request_lock"
    RELEASE_LOCK = "release_lock"
    TASK_COORDINATION = "task_coordination"
    PATH_PLANNING = "path_planning"

    # Safety operations
    PROXIMITY_CHECK = "proximity_check"
    EMERGENCY_STOP = "emergency_stop"

    # Component connections
    CONNECT_COMPONENT = "connect_component"
    HEARTBEAT = "heartbeat"

    # Data operations
    QUERY_DATA = "query_data"
    UPDATE_DATA = "update_data"


@dataclass
class OperationCircuitConfig:
    """Configuration for per-operation circuit breakers"""

    # Per-operation overrides (operation_type -> config)
    operation_configs: Dict[str, CircuitBreakerConfig] = field(default_factory=dict)

    # Defaults for operation categories
    default_communication_config: CircuitBreakerConfig = field(
        default_factory=lambda: CircuitBreakerConfig(failure_threshold=5, timeout_seconds=30.0)
    )
    default_coordination_config: CircuitBreakerConfig = field(
        default_factory=lambda: CircuitBreakerConfig(failure_threshold=3, timeout_seconds=60.0)
    )
    default_safety_config: CircuitBreakerConfig = field(
        default_factory=lambda: CircuitBreakerConfig(
            failure_threshold=2,  # More sensitive for safety
            timeout_seconds=10.0,  # Quick recovery for safety
        )
    )


class PerOperationCircuitBreakers:
    """
    Manages circuit breakers for individual operation types.

    This addresses the P3 Gap: Circuit Breakers Not Per-Operation.

    Features:
    - Separate circuit breaker per operation type
    - Category-based default configurations
    - Aggregated statistics
    - Bulk operations (reset all, get all states)
    """

    # Operation categories
    COMMUNICATION_OPS = {
        OperationType.SEND_MESSAGE,
        OperationType.RECEIVE_MESSAGE,
        OperationType.PUBLISH_TOPIC,
        OperationType.SUBSCRIBE_TOPIC,
        OperationType.HEARTBEAT,
    }

    COORDINATION_OPS = {
        OperationType.REQUEST_LOCK,
        OperationType.RELEASE_LOCK,
        OperationType.TASK_COORDINATION,
        OperationType.PATH_PLANNING,
    }

    SAFETY_OPS = {OperationType.PROXIMITY_CHECK, OperationType.EMERGENCY_STOP}

    def __init__(
        self,
        config: Optional[OperationCircuitConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.config = config or OperationCircuitConfig()
        self.logger = logger or logging.getLogger("PerOperationCircuitBreakers")

        # Circuit breakers indexed by operation type
        self._breakers: Dict[OperationType, CircuitBreaker] = {}

        # Initialize all operation types
        for op_type in OperationType:
            self._create_breaker(op_type)

        self.logger.info(f"Initialized {len(self._breakers)} per-operation circuit breakers")

    def _get_config_for_operation(self, op_type: OperationType) -> CircuitBreakerConfig:
        """Get configuration for an operation type"""
        # Check for explicit override
        if op_type.value in self.config.operation_configs:
            return self.config.operation_configs[op_type.value]

        # Use category defaults
        if op_type in self.SAFETY_OPS:
            return self.config.default_safety_config
        elif op_type in self.COORDINATION_OPS:
            return self.config.default_coordination_config
        else:
            return self.config.default_communication_config

    def _create_breaker(self, op_type: OperationType):
        """Create circuit breaker for operation type"""
        config = self._get_config_for_operation(op_type)
        self._breakers[op_type] = CircuitBreaker(
            name=f"op_{op_type.value}", config=config, logger=self.logger
        )

    def get(self, operation: OperationType) -> CircuitBreaker:
        """Get circuit breaker for an operation type"""
        return self._breakers[operation]

    def call(self, operation: OperationType, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function through operation-specific circuit breaker"""
        return self._breakers[operation].call(func, *args, **kwargs)

    def get_state(self, operation: OperationType) -> CircuitState:
        """Get state of specific operation's circuit breaker"""
        return self._breakers[operation].state

    def get_all_states(self) -> Dict[str, str]:
        """Get states of all circuit breakers"""
        return {op.value: self._breakers[op].state.value for op in OperationType}

    def get_open_circuits(self) -> List[OperationType]:
        """Get list of operations with open circuits"""
        return [op for op, breaker in self._breakers.items() if breaker.state == CircuitState.OPEN]

    def reset(self, operation: OperationType):
        """Reset a specific circuit breaker"""
        self._breakers[operation].reset()

    def reset_all(self):
        """Reset all circuit breakers"""
        for breaker in self._breakers.values():
            breaker.reset()

    def reset_category(self, category: str):
        """Reset all circuit breakers in a category"""
        ops = set()
        if category == "communication":
            ops = self.COMMUNICATION_OPS
        elif category == "coordination":
            ops = self.COORDINATION_OPS
        elif category == "safety":
            ops = self.SAFETY_OPS

        for op in ops:
            self._breakers[op].reset()

    def get_stats(self) -> Dict[str, Any]:
        """Get aggregated statistics"""
        all_stats = {op.value: self._breakers[op].get_stats() for op in OperationType}

        # Aggregate
        total_calls = sum(s["stats"]["total_calls"] for s in all_stats.values())
        total_rejected = sum(s["stats"]["rejected_calls"] for s in all_stats.values())
        open_count = len(self.get_open_circuits())

        return {
            "operations": all_stats,
            "summary": {
                "total_calls": total_calls,
                "total_rejected": total_rejected,
                "open_circuits": open_count,
                "healthy_operations": len(OperationType) - open_count,
            },
        }


# =============================================================================
# ENHANCED DEGRADATION MODES (P3 Gap Fix)
# =============================================================================


class DegradationLevel(Enum):
    """System degradation levels"""

    NORMAL = "normal"  # Full functionality
    REDUCED = "reduced"  # Non-essential features disabled
    ESSENTIAL = "essential"  # Only critical operations
    EMERGENCY = "emergency"  # Safety-critical only
    OFFLINE = "offline"  # System shutdown/isolated


@dataclass
class DegradationThresholds:
    """Thresholds for automatic degradation"""

    # CPU thresholds (%)
    cpu_reduced: float = 80.0
    cpu_essential: float = 90.0
    cpu_emergency: float = 95.0

    # Memory thresholds (%)
    memory_reduced: float = 75.0
    memory_essential: float = 85.0
    memory_emergency: float = 95.0

    # Error rate thresholds (errors/min)
    error_rate_reduced: float = 10.0
    error_rate_essential: float = 25.0
    error_rate_emergency: float = 50.0

    # Open circuit thresholds
    open_circuits_reduced: int = 2
    open_circuits_essential: int = 4
    open_circuits_emergency: int = 6

    # Latency thresholds (ms)
    latency_reduced: float = 100.0
    latency_essential: float = 250.0
    latency_emergency: float = 500.0


@dataclass
class DegradedFeature:
    """Definition of a feature that can be degraded"""

    name: str
    description: str
    min_level: DegradationLevel  # Minimum level where feature is disabled
    disable_action: Optional[Callable[[], None]] = None
    enable_action: Optional[Callable[[], None]] = None
    is_safety_critical: bool = False


class DegradationManager:
    """
    Manages graceful system degradation.

    This addresses the P3 Gap: Limited Degradation Modes.

    Features:
    - Multiple degradation levels
    - Automatic level transitions based on metrics
    - Feature-level granular control
    - Safe recovery to higher functionality levels
    - Integration with monitoring
    """

    # Hysteresis to prevent oscillation (seconds)
    LEVEL_CHANGE_COOLDOWN = 30.0

    # Time required at lower metrics before upgrading
    UPGRADE_STABILITY_TIME = 60.0

    def __init__(
        self,
        thresholds: Optional[DegradationThresholds] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.thresholds = thresholds or DegradationThresholds()
        self.logger = logger or logging.getLogger("DegradationManager")

        self._current_level = DegradationLevel.NORMAL
        self._lock = threading.RLock()

        # Feature registry
        self._features: Dict[str, DegradedFeature] = {}
        self._disabled_features: Set[str] = set()

        # Timing
        self._last_level_change = 0.0
        self._stable_since: Dict[DegradationLevel, float] = {}

        # Metrics cache
        self._current_metrics: Dict[str, float] = {}

        # Callbacks
        self._level_callbacks: List[Callable[[DegradationLevel, DegradationLevel], None]] = []

        # Register default features
        self._register_default_features()

        self.logger.info("DegradationManager initialized")

    def _register_default_features(self):
        """Register default degradable features"""
        default_features = [
            DegradedFeature(
                name="detailed_logging",
                description="Detailed debug logging",
                min_level=DegradationLevel.REDUCED,
            ),
            DegradedFeature(
                name="metrics_collection",
                description="Fine-grained metrics collection",
                min_level=DegradationLevel.REDUCED,
            ),
            DegradedFeature(
                name="visualization_updates",
                description="UI/visualization updates",
                min_level=DegradationLevel.REDUCED,
            ),
            DegradedFeature(
                name="path_optimization",
                description="Advanced path optimization",
                min_level=DegradationLevel.ESSENTIAL,
            ),
            DegradedFeature(
                name="task_scheduling",
                description="Non-urgent task scheduling",
                min_level=DegradationLevel.ESSENTIAL,
            ),
            DegradedFeature(
                name="fleet_discovery",
                description="Fleet discovery broadcasts",
                min_level=DegradationLevel.ESSENTIAL,
            ),
            DegradedFeature(
                name="coordination",
                description="Multi-robot coordination",
                min_level=DegradationLevel.EMERGENCY,
                is_safety_critical=False,
            ),
            DegradedFeature(
                name="proximity_monitoring",
                description="Proximity safety monitoring",
                min_level=DegradationLevel.OFFLINE,  # Never disable
                is_safety_critical=True,
            ),
            DegradedFeature(
                name="emergency_stop",
                description="Emergency stop system",
                min_level=DegradationLevel.OFFLINE,  # Never disable
                is_safety_critical=True,
            ),
        ]

        for feature in default_features:
            self._features[feature.name] = feature

    @property
    def current_level(self) -> DegradationLevel:
        """Get current degradation level"""
        return self._current_level

    def register_feature(self, feature: DegradedFeature):
        """Register a degradable feature"""
        with self._lock:
            self._features[feature.name] = feature
            self.logger.debug(f"Registered feature: {feature.name}")

    def is_feature_enabled(self, feature_name: str) -> bool:
        """Check if a feature is currently enabled"""
        with self._lock:
            return feature_name not in self._disabled_features

    def update_metrics(
        self,
        cpu_percent: float = None,
        memory_percent: float = None,
        error_rate: float = None,
        open_circuits: int = None,
        latency_ms: float = None,
    ):
        """
        Update system metrics and check for level changes.

        Call this periodically with current system metrics.
        """
        with self._lock:
            # Update metrics cache
            if cpu_percent is not None:
                self._current_metrics["cpu"] = cpu_percent
            if memory_percent is not None:
                self._current_metrics["memory"] = memory_percent
            if error_rate is not None:
                self._current_metrics["error_rate"] = error_rate
            if open_circuits is not None:
                self._current_metrics["open_circuits"] = open_circuits
            if latency_ms is not None:
                self._current_metrics["latency"] = latency_ms

            # Determine appropriate level
            recommended_level = self._determine_level()

            # Apply level if different
            if recommended_level != self._current_level:
                self._transition_level(recommended_level)

    def _determine_level(self) -> DegradationLevel:
        """Determine appropriate degradation level based on metrics"""
        t = self.thresholds
        m = self._current_metrics

        # Check for emergency conditions
        if (
            m.get("cpu", 0) >= t.cpu_emergency
            or m.get("memory", 0) >= t.memory_emergency
            or m.get("error_rate", 0) >= t.error_rate_emergency
            or m.get("open_circuits", 0) >= t.open_circuits_emergency
            or m.get("latency", 0) >= t.latency_emergency
        ):
            return DegradationLevel.EMERGENCY

        # Check for essential conditions
        if (
            m.get("cpu", 0) >= t.cpu_essential
            or m.get("memory", 0) >= t.memory_essential
            or m.get("error_rate", 0) >= t.error_rate_essential
            or m.get("open_circuits", 0) >= t.open_circuits_essential
            or m.get("latency", 0) >= t.latency_essential
        ):
            return DegradationLevel.ESSENTIAL

        # Check for reduced conditions
        if (
            m.get("cpu", 0) >= t.cpu_reduced
            or m.get("memory", 0) >= t.memory_reduced
            or m.get("error_rate", 0) >= t.error_rate_reduced
            or m.get("open_circuits", 0) >= t.open_circuits_reduced
            or m.get("latency", 0) >= t.latency_reduced
        ):
            return DegradationLevel.REDUCED

        return DegradationLevel.NORMAL

    def _transition_level(self, new_level: DegradationLevel):
        """Transition to a new degradation level"""
        now = time.time()

        # Check cooldown
        if now - self._last_level_change < self.LEVEL_CHANGE_COOLDOWN:
            return

        # For upgrades (less degraded), require stability
        if new_level.value < self._current_level.value:
            stable_time = self._stable_since.get(new_level, now)
            if now - stable_time < self.UPGRADE_STABILITY_TIME:
                self._stable_since[new_level] = stable_time
                return

        old_level = self._current_level
        self._current_level = new_level
        self._last_level_change = now

        self.logger.warning(f"Degradation level change: {old_level.value} -> {new_level.value}")

        # Update features
        self._update_features()

        # Notify callbacks
        for callback in self._level_callbacks:
            try:
                callback(old_level, new_level)
            except Exception as e:
                self.logger.error(f"Degradation callback error: {e}")

    def _update_features(self):
        """Update feature states based on current level"""
        for name, feature in self._features.items():
            should_disable = self._current_level.value >= feature.min_level.value

            if should_disable and name not in self._disabled_features:
                # Disable feature
                self._disabled_features.add(name)
                self.logger.info(f"Feature disabled: {name} (level: {self._current_level.value})")

                if feature.disable_action:
                    try:
                        feature.disable_action()
                    except Exception as e:
                        self.logger.error(f"Feature disable action failed: {e}")

            elif not should_disable and name in self._disabled_features:
                # Enable feature
                self._disabled_features.remove(name)
                self.logger.info(f"Feature enabled: {name} (level: {self._current_level.value})")

                if feature.enable_action:
                    try:
                        feature.enable_action()
                    except Exception as e:
                        self.logger.error(f"Feature enable action failed: {e}")

    def force_level(self, level: DegradationLevel):
        """Force a specific degradation level (manual override)"""
        with self._lock:
            old_level = self._current_level
            self._current_level = level
            self._last_level_change = time.time()

            self.logger.warning(f"Forced degradation level: {level.value}")
            self._update_features()

            for callback in self._level_callbacks:
                try:
                    callback(old_level, level)
                except Exception:
                    pass

    def on_level_change(self, callback: Callable[[DegradationLevel, DegradationLevel], None]):
        """Register callback for level changes"""
        self._level_callbacks.append(callback)

    def get_status(self) -> Dict[str, Any]:
        """Get degradation status"""
        with self._lock:
            return {
                "current_level": self._current_level.value,
                "metrics": dict(self._current_metrics),
                "disabled_features": list(self._disabled_features),
                "enabled_features": [
                    f for f in self._features.keys() if f not in self._disabled_features
                ],
                "last_change": self._last_level_change,
                "feature_count": len(self._features),
            }


# =============================================================================
# DECORATOR HELPERS
# =============================================================================


def with_circuit_breaker(breaker: CircuitBreaker):
    """Decorator to wrap function with circuit breaker."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)

        return wrapper

    return decorator


def with_retry(handler: RetryHandler):
    """Decorator to wrap function with retry logic."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return handler.execute(func, *args, **kwargs)

        return wrapper

    return decorator


def with_rate_limit(limiter: RateLimiter, wait: bool = False, timeout: float = 5.0):
    """Decorator to wrap function with rate limiting."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if wait:
                if not limiter.wait_and_acquire(timeout=timeout):
                    raise RateLimitExceededError(f"Rate limit exceeded: {limiter.name}")
            else:
                if not limiter.acquire():
                    raise RateLimitExceededError(f"Rate limit exceeded: {limiter.name}")
            return func(*args, **kwargs)

        return wrapper

    return decorator


def with_operation_circuit(breakers: PerOperationCircuitBreakers, operation: OperationType):
    """Decorator to wrap function with operation-specific circuit breaker."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return breakers.call(operation, func, *args, **kwargs)

        return wrapper

    return decorator


def with_degradation_check(manager: DegradationManager, feature_name: str):
    """Decorator to check if feature is enabled before execution."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not manager.is_feature_enabled(feature_name):
                raise FeatureDisabledError(
                    f"Feature '{feature_name}' is disabled at degradation level "
                    f"{manager.current_level.value}"
                )
            return func(*args, **kwargs)

        return wrapper

    return decorator


class RateLimitExceededError(Exception):
    """Raised when rate limit is exceeded."""

    pass


class FeatureDisabledError(Exception):
    """Raised when a feature is disabled due to degradation."""

    pass
