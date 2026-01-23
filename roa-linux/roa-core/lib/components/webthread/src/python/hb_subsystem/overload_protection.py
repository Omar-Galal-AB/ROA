"""
overload_protection.py
ROA - Robot Operations & Automation
Heartbeat Subsystem - Overload Protection

Implements 3-layer protection based on failsafe-go patterns:
1. Bulkhead - Limits concurrent processing (semaphore-based)
2. RateLimiter - Prevents flood attacks (token bucket)
3. AdaptiveLimiter - Auto-adjusts based on execution trends

These protect the HB receiver from being overwhelmed by:
- Malicious flood attacks
- Runaway components sending too many HBs
- Burst traffic during system events
"""

import threading
import time
import logging
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from enum import Enum
from collections import deque


# =============================================================================
# EXCEPTIONS
# =============================================================================

class OverloadError(Exception):
    """Base exception for overload protection"""
    pass


class BulkheadFullError(OverloadError):
    """Raised when bulkhead has no available permits"""
    pass


class RateLimitExceededError(OverloadError):
    """Raised when rate limit is exceeded"""
    pass


class AdaptiveLimitExceededError(OverloadError):
    """Raised when adaptive limit is exceeded"""
    pass


# =============================================================================
# BULKHEAD - Concurrency Limiting
# =============================================================================

class Bulkhead:
    """
    Bulkhead pattern from failsafe-go.
    
    Limits the number of concurrent operations to prevent resource exhaustion.
    Uses a semaphore to control access.
    
    Usage:
        bulkhead = Bulkhead(max_concurrent=10)
        
        if bulkhead.try_acquire():
            try:
                # Process heartbeat
                pass
            finally:
                bulkhead.release()
    """
    
    def __init__(self, max_concurrent: int, name: str = "default"):
        """
        Initialize Bulkhead.
        
        Args:
            max_concurrent: Maximum concurrent operations allowed
            name: Name for logging/metrics
        """
        self.name = name
        self.max_concurrent = max_concurrent
        self._semaphore = threading.Semaphore(max_concurrent)
        self._active_count = 0
        self._lock = threading.Lock()
        self._rejected_count = 0
        self._acquired_count = 0
        self.logger = logging.getLogger(f"Bulkhead.{name}")
    
    def try_acquire(self, timeout: float = 0) -> bool:
        """
        Try to acquire a permit without blocking (or with short timeout).
        
        Args:
            timeout: Maximum time to wait (0 = no wait)
            
        Returns:
            True if permit acquired
        """
        if timeout <= 0:
            # Non-blocking acquire
            acquired = self._semaphore.acquire(blocking=False)
        else:
            # Blocking with timeout
            acquired = self._semaphore.acquire(blocking=True, timeout=timeout)
        
        with self._lock:
            if acquired:
                self._active_count += 1
                self._acquired_count += 1
            else:
                self._rejected_count += 1
        
        return acquired
    
    def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        Acquire a permit, blocking if necessary.
        
        Args:
            timeout: Maximum time to wait (None = wait forever)
            
        Returns:
            True if permit acquired
        """
        if timeout is None:
            self._semaphore.acquire()
            with self._lock:
                self._active_count += 1
                self._acquired_count += 1
            return True
        else:
            return self.try_acquire(timeout)
    
    def release(self):
        """Release a permit"""
        with self._lock:
            if self._active_count > 0:
                self._active_count -= 1
        self._semaphore.release()
    
    def is_full(self) -> bool:
        """Check if bulkhead is at capacity"""
        with self._lock:
            return self._active_count >= self.max_concurrent
    
    def get_active_count(self) -> int:
        """Get current number of active operations"""
        with self._lock:
            return self._active_count
    
    def get_available(self) -> int:
        """Get number of available permits"""
        with self._lock:
            return self.max_concurrent - self._active_count
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get bulkhead metrics"""
        with self._lock:
            return {
                'name': self.name,
                'max_concurrent': self.max_concurrent,
                'active_count': self._active_count,
                'available': self.max_concurrent - self._active_count,
                'acquired_count': self._acquired_count,
                'rejected_count': self._rejected_count,
            }


# =============================================================================
# RATE LIMITER - Token Bucket
# =============================================================================

class RateLimiterMode(Enum):
    """Rate limiter modes"""
    SMOOTH = "smooth"   # Evenly distributed permits
    BURSTY = "bursty"   # Allows bursts up to limit


class RateLimiter:
    """
    Rate Limiter using token bucket algorithm.
    
    Limits the rate of operations per time period.
    Prevents flood attacks and runaway components.
    
    Usage:
        limiter = RateLimiter(max_per_second=100)
        
        if limiter.try_acquire():
            # Process heartbeat
            pass
        else:
            # Rate limited
            pass
    """
    
    def __init__(
        self,
        max_per_second: float,
        burst_size: Optional[int] = None,
        mode: RateLimiterMode = RateLimiterMode.SMOOTH,
        name: str = "default"
    ):
        """
        Initialize RateLimiter.
        
        Args:
            max_per_second: Maximum operations per second
            burst_size: Maximum burst size (defaults to 10% of rate or 10)
            mode: SMOOTH or BURSTY mode
            name: Name for logging/metrics
        """
        self.name = name
        self.max_per_second = max_per_second
        self.mode = mode
        self.burst_size = burst_size or max(int(max_per_second * 0.1), 10)
        
        self._lock = threading.Lock()
        self._tokens = float(self.burst_size)  # Start with full bucket
        self._last_update = time.time()
        self._interval = 1.0 / max_per_second  # Time between permits
        
        # Metrics
        self._acquired_count = 0
        self._rejected_count = 0
        
        self.logger = logging.getLogger(f"RateLimiter.{name}")
    
    def try_acquire(self, permits: int = 1) -> bool:
        """
        Try to acquire permits without blocking.
        
        Args:
            permits: Number of permits to acquire
            
        Returns:
            True if permits acquired
        """
        with self._lock:
            self._refill_tokens()
            
            if self._tokens >= permits:
                self._tokens -= permits
                self._acquired_count += permits
                return True
            else:
                self._rejected_count += permits
                return False
    
    def acquire(self, permits: int = 1, timeout: Optional[float] = None) -> bool:
        """
        Acquire permits, blocking if necessary.
        
        Args:
            permits: Number of permits to acquire
            timeout: Maximum time to wait
            
        Returns:
            True if permits acquired within timeout
        """
        deadline = time.time() + timeout if timeout else None
        
        while True:
            if self.try_acquire(permits):
                return True
            
            if deadline and time.time() >= deadline:
                return False
            
            # Wait for tokens to refill
            wait_time = self._interval * permits
            if deadline:
                wait_time = min(wait_time, deadline - time.time())
            
            if wait_time <= 0:
                return False
            
            time.sleep(wait_time)
    
    def _refill_tokens(self):
        """Refill tokens based on elapsed time"""
        now = time.time()
        elapsed = now - self._last_update
        self._last_update = now
        
        # Add tokens based on elapsed time
        new_tokens = elapsed * self.max_per_second
        self._tokens = min(self._tokens + new_tokens, float(self.burst_size))
    
    def get_available_permits(self) -> float:
        """Get current available permits"""
        with self._lock:
            self._refill_tokens()
            return self._tokens
    
    def reset(self):
        """Reset limiter to initial state"""
        with self._lock:
            self._tokens = float(self.burst_size)
            self._last_update = time.time()
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get rate limiter metrics"""
        with self._lock:
            return {
                'name': self.name,
                'max_per_second': self.max_per_second,
                'burst_size': self.burst_size,
                'available_tokens': self._tokens,
                'acquired_count': self._acquired_count,
                'rejected_count': self._rejected_count,
                'mode': self.mode.value,
            }


# =============================================================================
# MIN RATE DETECTOR - Detect too-slow heartbeats
# =============================================================================

class MinRateDetector:
    """
    Detects when heartbeat rate falls below minimum.
    
    Complements RateLimiter by detecting when HBs are coming
    too slowly (indicating component issues).
    """
    
    def __init__(
        self,
        min_per_second: float,
        window_seconds: float = 1.0,
        name: str = "default"
    ):
        """
        Initialize MinRateDetector.
        
        Args:
            min_per_second: Minimum expected rate
            window_seconds: Time window for rate calculation
            name: Name for logging
        """
        self.name = name
        self.min_per_second = min_per_second
        self.window_seconds = window_seconds
        
        self._lock = threading.Lock()
        self._timestamps: deque = deque()
        self._violation_count = 0
        
        self.logger = logging.getLogger(f"MinRateDetector.{name}")
    
    def record(self) -> bool:
        """
        Record a heartbeat and check if rate is below minimum.
        
        Returns:
            True if rate is acceptable, False if below minimum
        """
        now = time.time()
        
        with self._lock:
            # Add current timestamp
            self._timestamps.append(now)
            
            # Remove old timestamps
            cutoff = now - self.window_seconds
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()
            
            # Calculate rate
            count = len(self._timestamps)
            rate = count / self.window_seconds
            
            if rate < self.min_per_second:
                self._violation_count += 1
                return False
            
            return True
    
    def get_current_rate(self) -> float:
        """Get current rate in the window"""
        now = time.time()
        
        with self._lock:
            cutoff = now - self.window_seconds
            count = sum(1 for t in self._timestamps if t >= cutoff)
            return count / self.window_seconds
    
    def is_below_minimum(self) -> bool:
        """Check if current rate is below minimum"""
        return self.get_current_rate() < self.min_per_second
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get detector metrics"""
        with self._lock:
            return {
                'name': self.name,
                'min_per_second': self.min_per_second,
                'current_rate': self.get_current_rate(),
                'window_seconds': self.window_seconds,
                'violation_count': self._violation_count,
            }


# =============================================================================
# ADAPTIVE LIMITER - Auto-adjusting limits
# =============================================================================

class AdaptiveLimiter:
    """
    Adaptive Limiter that auto-adjusts based on execution trends.
    
    From failsafe-go: Increases limit when execution times decrease,
    decreases limit when times increase. This allows the system to
    self-optimize based on actual load.
    """
    
    def __init__(
        self,
        initial_limit: int = 100,
        min_limit: int = 10,
        max_limit: int = 1000,
        increase_factor: float = 1.1,
        decrease_factor: float = 0.9,
        sample_window: int = 100,
        name: str = "default"
    ):
        """
        Initialize AdaptiveLimiter.
        
        Args:
            initial_limit: Starting limit
            min_limit: Minimum allowed limit
            max_limit: Maximum allowed limit
            increase_factor: Factor to increase limit by (when times decrease)
            decrease_factor: Factor to decrease limit by (when times increase)
            sample_window: Number of samples for trend detection
            name: Name for logging
        """
        self.name = name
        self.min_limit = min_limit
        self.max_limit = max_limit
        self.increase_factor = increase_factor
        self.decrease_factor = decrease_factor
        self.sample_window = sample_window
        
        self._lock = threading.Lock()
        self._current_limit = initial_limit
        self._active_count = 0
        self._execution_times: deque = deque(maxlen=sample_window)
        self._last_avg_time: Optional[float] = None
        
        # Metrics
        self._adjustments_up = 0
        self._adjustments_down = 0
        self._rejected_count = 0
        self._acquired_count = 0
        
        self.logger = logging.getLogger(f"AdaptiveLimiter.{name}")
    
    def try_acquire(self) -> bool:
        """
        Try to acquire a permit.
        
        Returns:
            True if permit acquired
        """
        with self._lock:
            if self._active_count < self._current_limit:
                self._active_count += 1
                self._acquired_count += 1
                return True
            else:
                self._rejected_count += 1
                return False
    
    def release(self, execution_time_ms: float):
        """
        Release a permit and record execution time.
        
        Args:
            execution_time_ms: How long the operation took
        """
        with self._lock:
            if self._active_count > 0:
                self._active_count -= 1
            
            self._execution_times.append(execution_time_ms)
            self._maybe_adjust_limit()
    
    def _maybe_adjust_limit(self):
        """Check if limit should be adjusted based on trends"""
        if len(self._execution_times) < self.sample_window:
            return
        
        # Calculate current average
        current_avg = sum(self._execution_times) / len(self._execution_times)
        
        if self._last_avg_time is not None:
            if current_avg < self._last_avg_time * 0.95:  # Times decreased by >5%
                # Increase limit
                new_limit = int(self._current_limit * self.increase_factor)
                self._current_limit = min(new_limit, self.max_limit)
                self._adjustments_up += 1
                self.logger.debug(f"Limit increased to {self._current_limit}")
                
            elif current_avg > self._last_avg_time * 1.05:  # Times increased by >5%
                # Decrease limit
                new_limit = int(self._current_limit * self.decrease_factor)
                self._current_limit = max(new_limit, self.min_limit)
                self._adjustments_down += 1
                self.logger.debug(f"Limit decreased to {self._current_limit}")
        
        self._last_avg_time = current_avg
    
    def get_current_limit(self) -> int:
        """Get current limit"""
        with self._lock:
            return self._current_limit
    
    def get_active_count(self) -> int:
        """Get current active count"""
        with self._lock:
            return self._active_count
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get adaptive limiter metrics"""
        with self._lock:
            avg_time = (
                sum(self._execution_times) / len(self._execution_times)
                if self._execution_times else 0
            )
            return {
                'name': self.name,
                'current_limit': self._current_limit,
                'min_limit': self.min_limit,
                'max_limit': self.max_limit,
                'active_count': self._active_count,
                'avg_execution_time_ms': avg_time,
                'adjustments_up': self._adjustments_up,
                'adjustments_down': self._adjustments_down,
                'acquired_count': self._acquired_count,
                'rejected_count': self._rejected_count,
            }


# =============================================================================
# COMPOSITE OVERLOAD PROTECTOR
# =============================================================================

class OverloadProtector:
    """
    Composite 3-layer overload protection.
    
    Combines Bulkhead + RateLimiter + AdaptiveLimiter for comprehensive
    protection against various overload scenarios.
    
    Usage:
        protector = OverloadProtector(
            max_concurrent=10,
            max_per_second=100,
            component_name="FTI"
        )
        
        if protector.try_acquire():
            try:
                start = time.time()
                # Process heartbeat
                pass
            finally:
                elapsed_ms = (time.time() - start) * 1000
                protector.release(elapsed_ms)
    """
    
    def __init__(
        self,
        max_concurrent: int = 10,
        max_per_second: float = 100.0,
        min_per_second: float = 10.0,
        adaptive_enabled: bool = True,
        component_name: str = "default"
    ):
        """
        Initialize OverloadProtector.
        
        Args:
            max_concurrent: Max concurrent operations (Bulkhead)
            max_per_second: Max rate (RateLimiter)
            min_per_second: Min rate for detection
            adaptive_enabled: Enable adaptive limiting
            component_name: Component this protects
        """
        self.component_name = component_name
        self.adaptive_enabled = adaptive_enabled
        
        # Layer 1: Bulkhead
        self.bulkhead = Bulkhead(max_concurrent, f"{component_name}_bulkhead")
        
        # Layer 2: Rate Limiter
        self.rate_limiter = RateLimiter(
            max_per_second, 
            name=f"{component_name}_rate"
        )
        
        # Layer 2b: Min Rate Detector
        self.min_rate_detector = MinRateDetector(
            min_per_second,
            name=f"{component_name}_min_rate"
        )
        
        # Layer 3: Adaptive Limiter
        if adaptive_enabled:
            self.adaptive_limiter = AdaptiveLimiter(
                initial_limit=max_concurrent * 2,
                name=f"{component_name}_adaptive"
            )
        else:
            self.adaptive_limiter = None
        
        self.logger = logging.getLogger(f"OverloadProtector.{component_name}")
        self._rejection_callbacks: list = []
    
    def try_acquire(self) -> bool:
        """
        Try to acquire through all protection layers.
        
        Returns:
            True if all layers allow the operation
        """
        # Layer 1: Check bulkhead
        if not self.bulkhead.try_acquire():
            self._on_rejection("bulkhead_full")
            return False
        
        # Layer 2: Check rate limit
        if not self.rate_limiter.try_acquire():
            self.bulkhead.release()
            self._on_rejection("rate_exceeded")
            return False
        
        # Record for min rate detection
        self.min_rate_detector.record()
        
        # Layer 3: Check adaptive limit
        if self.adaptive_limiter and not self.adaptive_limiter.try_acquire():
            self.bulkhead.release()
            self._on_rejection("adaptive_limit")
            return False
        
        return True
    
    def release(self, execution_time_ms: float = 0.0):
        """
        Release all permits.
        
        Args:
            execution_time_ms: Execution time for adaptive adjustment
        """
        self.bulkhead.release()
        
        if self.adaptive_limiter:
            self.adaptive_limiter.release(execution_time_ms)
    
    def is_rate_below_minimum(self) -> bool:
        """Check if incoming rate is below minimum (component may be failing)"""
        return self.min_rate_detector.is_below_minimum()
    
    def on_rejection(self, callback: Callable[[str], None]):
        """Register callback for when operations are rejected"""
        self._rejection_callbacks.append(callback)
    
    def _on_rejection(self, reason: str):
        """Handle rejection"""
        self.logger.debug(f"Rejected: {reason}")
        for callback in self._rejection_callbacks:
            try:
                callback(reason)
            except:
                pass
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get combined metrics from all layers"""
        metrics = {
            'component': self.component_name,
            'bulkhead': self.bulkhead.get_metrics(),
            'rate_limiter': self.rate_limiter.get_metrics(),
            'min_rate_detector': self.min_rate_detector.get_metrics(),
        }
        
        if self.adaptive_limiter:
            metrics['adaptive_limiter'] = self.adaptive_limiter.get_metrics()
        
        return metrics


# =============================================================================
# PER-COMPONENT PROTECTOR FACTORY
# =============================================================================

class OverloadProtectorFactory:
    """
    Factory for creating per-component overload protectors.
    
    Each component gets its own protector with appropriate limits.
    """
    
    # Default limits per component type
    DEFAULT_LIMITS = {
        'FTI': {'max_concurrent': 15, 'max_per_second': 50, 'min_per_second': 15},
        'ROC': {'max_concurrent': 10, 'max_per_second': 50, 'min_per_second': 15},
        'DIMC': {'max_concurrent': 10, 'max_per_second': 50, 'min_per_second': 15},
        'COMC': {'max_concurrent': 10, 'max_per_second': 50, 'min_per_second': 10},
        'ROS2Bridge': {'max_concurrent': 15, 'max_per_second': 50, 'min_per_second': 15},
        'UE5Bridge': {'max_concurrent': 15, 'max_per_second': 50, 'min_per_second': 15},
    }
    
    @classmethod
    def create(cls, component_name: str, **overrides) -> OverloadProtector:
        """
        Create an overload protector for a component.
        
        Args:
            component_name: Name of the component
            **overrides: Override default limits
            
        Returns:
            Configured OverloadProtector
        """
        limits = cls.DEFAULT_LIMITS.get(component_name, {
            'max_concurrent': 10,
            'max_per_second': 50,
            'min_per_second': 15,
        })
        
        # Apply overrides
        limits.update(overrides)
        
        return OverloadProtector(
            max_concurrent=limits['max_concurrent'],
            max_per_second=limits['max_per_second'],
            min_per_second=limits['min_per_second'],
            component_name=component_name
        )
