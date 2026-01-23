"""
Rate Limiter - Command rate limiting and backpressure for ROC.

Provides:
- Per-robot command rate limiting
- Queue depth enforcement
- Backpressure signals
- Command prioritization

Based on ROC_CRITICAL_ANALYSIS.md Gap #7.
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple


class CommandPriority(IntEnum):
    """Command priority levels (higher = more important)."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4
    SAFETY = 5  # Never rate limited


class RateLimitResult(Enum):
    """Result of rate limit check."""

    ALLOWED = "allowed"
    RATE_LIMITED = "rate_limited"
    QUEUE_FULL = "queue_full"
    BACKPRESSURE = "backpressure"


@dataclass
class CommandRecord:
    """Record of a command for rate tracking."""

    command_id: str
    robot_id: str
    command_type: str
    priority: CommandPriority
    timestamp: float
    size_bytes: int = 0


@dataclass
class RateLimiterConfig:
    """Configuration for RateLimiter."""

    # Rate limits
    max_commands_per_second: float = 100.0
    max_commands_per_robot_per_second: float = 50.0
    burst_size: int = 10  # Allow burst above rate

    # Queue limits
    max_queue_depth: int = 100
    max_queue_depth_per_robot: int = 20

    # Backpressure
    enable_backpressure: bool = True
    backpressure_threshold_pct: float = 0.8  # Signal at 80% queue

    # Priority handling
    priority_boost_when_full: bool = True  # Boost priority when queue filling
    drop_low_priority_when_full: bool = True

    # Sliding window
    window_size_s: float = 1.0


BackpressureCallback = Callable[[str, float], None]  # robot_id, queue_fullness


class RateLimiter:
    """
    Manages command rate limiting and backpressure for ROC.

    Responsibilities:
    - Enforce per-robot and global rate limits
    - Manage queue depth
    - Signal backpressure to UE5
    - Priority-based command handling

    Usage:
        limiter = RateLimiter()

        # Check if command allowed
        result = limiter.check_rate_limit("robot_0", "joint_command")

        if result == RateLimitResult.ALLOWED:
            limiter.record_command("robot_0", "joint_command", command_id)
            process_command()
        else:
            handle_rate_limited(result)
    """

    def __init__(
        self,
        config: Optional[RateLimiterConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize RateLimiter.

        Args:
            config: Limiter configuration
            logger: Logger instance
        """
        self.config = config or RateLimiterConfig()
        self.logger = logger or logging.getLogger(__name__)

        # Command tracking (sliding window)
        self._global_commands: Deque[CommandRecord] = deque()
        self._robot_commands: Dict[str, Deque[CommandRecord]] = {}

        # Queue tracking
        self._queue_depth = 0
        self._robot_queue_depth: Dict[str, int] = {}

        # Backpressure state
        self._backpressure_active: Dict[str, bool] = {}
        self._backpressure_callbacks: List[BackpressureCallback] = []

        # Statistics
        self._stats = {
            "commands_allowed": 0,
            "commands_rate_limited": 0,
            "commands_queue_rejected": 0,
            "backpressure_signals": 0,
            "low_priority_dropped": 0,
        }

        self.logger.info("RateLimiter initialized")

    # =========================================================================
    # RATE LIMITING
    # =========================================================================

    def check_rate_limit(
        self,
        robot_id: str,
        command_type: str,
        priority: CommandPriority = CommandPriority.NORMAL,
    ) -> RateLimitResult:
        """
        Check if a command is allowed under rate limits.

        Args:
            robot_id: Robot identifier
            command_type: Type of command
            priority: Command priority

        Returns:
            RateLimitResult indicating if allowed
        """
        # Safety commands always allowed
        if priority == CommandPriority.SAFETY:
            return RateLimitResult.ALLOWED

        current_time = time.time()

        # Clean old records
        self._clean_old_records(current_time)

        # Check queue depth first
        queue_result = self._check_queue_limits(robot_id, priority)
        if queue_result != RateLimitResult.ALLOWED:
            return queue_result

        # Check global rate
        if len(self._global_commands) >= self.config.max_commands_per_second:
            self._stats["commands_rate_limited"] += 1
            return RateLimitResult.RATE_LIMITED

        # Check per-robot rate
        robot_commands = self._robot_commands.get(robot_id, deque())
        if len(robot_commands) >= self.config.max_commands_per_robot_per_second:
            self._stats["commands_rate_limited"] += 1
            return RateLimitResult.RATE_LIMITED

        return RateLimitResult.ALLOWED

    def _check_queue_limits(self, robot_id: str, priority: CommandPriority) -> RateLimitResult:
        """Check queue depth limits."""
        # Global queue
        if self._queue_depth >= self.config.max_queue_depth:
            # Allow high priority to proceed
            if priority >= CommandPriority.HIGH:
                return RateLimitResult.ALLOWED

            # Drop low priority
            if self.config.drop_low_priority_when_full and priority == CommandPriority.LOW:
                self._stats["low_priority_dropped"] += 1

            self._stats["commands_queue_rejected"] += 1
            return RateLimitResult.QUEUE_FULL

        # Per-robot queue
        robot_depth = self._robot_queue_depth.get(robot_id, 0)
        if robot_depth >= self.config.max_queue_depth_per_robot:
            if priority >= CommandPriority.HIGH:
                return RateLimitResult.ALLOWED

            self._stats["commands_queue_rejected"] += 1
            return RateLimitResult.QUEUE_FULL

        # Check backpressure threshold
        if self.config.enable_backpressure:
            fullness = self._queue_depth / self.config.max_queue_depth
            if fullness >= self.config.backpressure_threshold_pct:
                self._signal_backpressure(robot_id, fullness)
                return RateLimitResult.BACKPRESSURE

        return RateLimitResult.ALLOWED

    def record_command(
        self,
        robot_id: str,
        command_type: str,
        command_id: str,
        priority: CommandPriority = CommandPriority.NORMAL,
        size_bytes: int = 0,
    ):
        """
        Record a command for rate tracking.

        Call this after the command is accepted for processing.

        Args:
            robot_id: Robot identifier
            command_type: Type of command
            command_id: Unique command ID
            priority: Command priority
            size_bytes: Size of command payload
        """
        record = CommandRecord(
            command_id=command_id,
            robot_id=robot_id,
            command_type=command_type,
            priority=priority,
            timestamp=time.time(),
            size_bytes=size_bytes,
        )

        # Add to global tracking
        self._global_commands.append(record)

        # Add to per-robot tracking
        if robot_id not in self._robot_commands:
            self._robot_commands[robot_id] = deque()
        self._robot_commands[robot_id].append(record)

        # Update queue depth
        self._queue_depth += 1
        self._robot_queue_depth[robot_id] = self._robot_queue_depth.get(robot_id, 0) + 1

        self._stats["commands_allowed"] += 1

    def command_completed(self, robot_id: str, command_id: str):
        """
        Record that a command completed.

        Reduces queue depth.

        Args:
            robot_id: Robot identifier
            command_id: Completed command ID
        """
        # Reduce queue depth
        self._queue_depth = max(0, self._queue_depth - 1)
        self._robot_queue_depth[robot_id] = max(0, self._robot_queue_depth.get(robot_id, 1) - 1)

        # Clear backpressure if queue draining
        if self.config.enable_backpressure:
            fullness = self._queue_depth / self.config.max_queue_depth
            if fullness < self.config.backpressure_threshold_pct * 0.5:
                self._clear_backpressure(robot_id)

    def _clean_old_records(self, current_time: float):
        """Remove records outside sliding window."""
        cutoff = current_time - self.config.window_size_s

        # Clean global
        while self._global_commands and self._global_commands[0].timestamp < cutoff:
            self._global_commands.popleft()

        # Clean per-robot
        for robot_id, commands in list(self._robot_commands.items()):
            while commands and commands[0].timestamp < cutoff:
                commands.popleft()

            # Remove empty entries
            if not commands:
                del self._robot_commands[robot_id]

    # =========================================================================
    # BACKPRESSURE
    # =========================================================================

    def _signal_backpressure(self, robot_id: str, fullness: float):
        """Signal backpressure to UE5."""
        if self._backpressure_active.get(robot_id, False):
            return  # Already signaled

        self._backpressure_active[robot_id] = True
        self._stats["backpressure_signals"] += 1

        self.logger.warning(
            f"Backpressure active for {robot_id} " f"(queue {fullness*100:.0f}% full)"
        )

        for callback in self._backpressure_callbacks:
            try:
                callback(robot_id, fullness)
            except Exception as e:
                self.logger.error(f"Backpressure callback error: {e}")

    def _clear_backpressure(self, robot_id: str):
        """Clear backpressure signal."""
        if not self._backpressure_active.get(robot_id, False):
            return

        self._backpressure_active[robot_id] = False

        self.logger.info(f"Backpressure cleared for {robot_id}")

        # Signal queue is draining
        for callback in self._backpressure_callbacks:
            try:
                callback(robot_id, 0.0)  # 0 indicates cleared
            except Exception as e:
                self.logger.error(f"Backpressure clear callback error: {e}")

    def on_backpressure(self, callback: BackpressureCallback):
        """Register backpressure callback."""
        self._backpressure_callbacks.append(callback)

    def is_backpressure_active(self, robot_id: Optional[str] = None) -> bool:
        """
        Check if backpressure is active.

        Args:
            robot_id: Specific robot or None for any

        Returns:
            True if backpressure active
        """
        if robot_id:
            return self._backpressure_active.get(robot_id, False)
        return any(self._backpressure_active.values())

    # =========================================================================
    # PRIORITY MANAGEMENT
    # =========================================================================

    def get_effective_priority(self, base_priority: CommandPriority) -> CommandPriority:
        """
        Get effective priority considering queue state.

        May boost priority when queue is filling.

        Args:
            base_priority: Base command priority

        Returns:
            Effective priority
        """
        if not self.config.priority_boost_when_full:
            return base_priority

        fullness = self._queue_depth / self.config.max_queue_depth

        # Boost priority when queue filling
        if fullness > 0.9 and base_priority < CommandPriority.CRITICAL:
            return CommandPriority(min(base_priority + 1, CommandPriority.CRITICAL))

        return base_priority

    # =========================================================================
    # RATE ADJUSTMENT
    # =========================================================================

    def set_rate_limit(self, robot_id: Optional[str], commands_per_second: float):
        """
        Dynamically adjust rate limit.

        Args:
            robot_id: Robot to adjust or None for global
            commands_per_second: New rate limit
        """
        if robot_id:
            # Per-robot adjustment would need per-robot config
            self.logger.info(f"Rate limit for {robot_id} set to {commands_per_second}/s")
        else:
            self.config.max_commands_per_second = commands_per_second
            self.logger.info(f"Global rate limit set to {commands_per_second}/s")

    def set_queue_limit(self, max_depth: int):
        """
        Dynamically adjust queue limit.

        Args:
            max_depth: New maximum queue depth
        """
        self.config.max_queue_depth = max_depth
        self.logger.info(f"Queue limit set to {max_depth}")

    # =========================================================================
    # STATUS
    # =========================================================================

    def get_current_rate(self, robot_id: Optional[str] = None) -> float:
        """
        Get current command rate.

        Args:
            robot_id: Specific robot or None for global

        Returns:
            Commands per second in current window
        """
        self._clean_old_records(time.time())

        if robot_id:
            commands = self._robot_commands.get(robot_id, deque())
            return len(commands) / self.config.window_size_s

        return len(self._global_commands) / self.config.window_size_s

    def get_queue_depth(self, robot_id: Optional[str] = None) -> int:
        """
        Get current queue depth.

        Args:
            robot_id: Specific robot or None for global

        Returns:
            Current queue depth
        """
        if robot_id:
            return self._robot_queue_depth.get(robot_id, 0)
        return self._queue_depth

    def get_queue_fullness(self, robot_id: Optional[str] = None) -> float:
        """
        Get queue fullness as percentage.

        Args:
            robot_id: Specific robot or None for global

        Returns:
            Queue fullness 0.0-1.0
        """
        if robot_id:
            depth = self._robot_queue_depth.get(robot_id, 0)
            return depth / self.config.max_queue_depth_per_robot
        return self._queue_depth / self.config.max_queue_depth

    def get_status(self) -> Dict[str, Any]:
        """Get rate limiter status."""
        self._clean_old_records(time.time())

        return {
            "global_rate": round(self.get_current_rate(), 2),
            "global_queue_depth": self._queue_depth,
            "global_queue_fullness_pct": round(self.get_queue_fullness() * 100, 1),
            "per_robot": {
                robot_id: {
                    "rate": round(self.get_current_rate(robot_id), 2),
                    "queue_depth": depth,
                    "backpressure": self._backpressure_active.get(robot_id, False),
                }
                for robot_id, depth in self._robot_queue_depth.items()
            },
            "backpressure_active": self.is_backpressure_active(),
            "stats": self._stats.copy(),
        }

    def get_health_report(self) -> Dict[str, Any]:
        """Get health report for Webthread."""
        fullness = self.get_queue_fullness()

        return {
            "healthy": fullness < self.config.backpressure_threshold_pct,
            "queue_fullness_pct": round(fullness * 100, 1),
            "backpressure_active": self.is_backpressure_active(),
            "commands_rate_limited": self._stats["commands_rate_limited"],
            "current_rate": round(self.get_current_rate(), 1),
        }
