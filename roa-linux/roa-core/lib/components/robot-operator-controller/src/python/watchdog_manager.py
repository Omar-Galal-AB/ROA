"""
Watchdog Manager - Execution monitoring and automatic recovery for ROC.

Provides:
- Command execution timeout monitoring
- Control loop hung detection
- Automatic subsystem restart
- Deadlock detection

Based on ROC_CRITICAL_ANALYSIS.md Gap #2.
"""

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set


class WatchdogState(Enum):
    """Watchdog item state."""

    INACTIVE = auto()
    ACTIVE = auto()
    WARNING = auto()
    TIMEOUT = auto()
    RECOVERED = auto()


class WatchdogAction(Enum):
    """Action to take on timeout."""

    LOG_WARNING = auto()
    CALLBACK = auto()
    RESTART_SUBSYSTEM = auto()
    TRIGGER_ESTOP = auto()


@dataclass
class WatchdogConfig:
    """Configuration for a watchdog item."""

    name: str
    timeout_ms: float
    action: WatchdogAction = WatchdogAction.CALLBACK
    warning_threshold_pct: float = 0.75  # Warn at 75% of timeout
    max_timeouts: int = 3  # Timeouts before escalation
    auto_restart: bool = False


@dataclass
class WatchdogItem:
    """Tracked watchdog item."""

    config: WatchdogConfig
    state: WatchdogState = WatchdogState.INACTIVE
    last_kick: float = 0.0
    timeout_count: int = 0
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WatchdogManagerConfig:
    """Configuration for WatchdogManager."""

    # Monitoring settings
    check_interval_ms: float = 100.0  # 10Hz check rate

    # Control loop monitoring
    control_loop_timeout_ms: float = 50.0  # 20Hz control loop = 50ms max
    control_loop_warning_ms: float = 35.0

    # Command execution
    command_timeout_ms: float = 5000.0  # 5s default command timeout

    # Subsystem monitoring
    subsystem_timeout_ms: float = 10000.0  # 10s subsystem heartbeat

    # Recovery
    max_restart_attempts: int = 3
    restart_delay_ms: float = 1000.0


TimeoutCallback = Callable[[str, WatchdogItem], None]  # name, item
RestartCallback = Callable[[str], bool]  # subsystem_name -> success


class WatchdogManager:
    """
    Monitors execution timeouts and provides automatic recovery.

    Responsibilities:
    - Track command execution timeouts
    - Monitor control loop timing
    - Detect hung subsystems
    - Trigger recovery actions
    - Report watchdog health

    Usage:
        manager = WatchdogManager()
        manager.on_timeout(handle_timeout)
        await manager.start()

        # Start watching a command
        manager.start_watch("cmd_123", timeout_ms=5000)
        # ... execute command ...
        manager.kick("cmd_123")  # Still alive
        # ... finish ...
        manager.stop_watch("cmd_123")

        # Control loop monitoring
        with manager.control_loop_context():
            process_control()
    """

    def __init__(
        self,
        config: Optional[WatchdogManagerConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize WatchdogManager.

        Args:
            config: Manager configuration
            logger: Logger instance
        """
        self.config = config or WatchdogManagerConfig()
        self.logger = logger or logging.getLogger(__name__)

        # Watched items
        self._items: Dict[str, WatchdogItem] = {}
        self._lock = threading.Lock()

        # Running state
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

        # Callbacks
        self._timeout_callbacks: List[TimeoutCallback] = []
        self._restart_callbacks: Dict[str, RestartCallback] = {}

        # Control loop tracking
        self._control_loop_start: Optional[float] = None
        self._control_loop_stats = {
            "iterations": 0,
            "overruns": 0,
            "max_latency_ms": 0.0,
            "avg_latency_ms": 0.0,
            "total_latency_ms": 0.0,
        }

        # Statistics
        self._stats = {
            "timeouts_detected": 0,
            "warnings_issued": 0,
            "restarts_triggered": 0,
            "restarts_succeeded": 0,
            "estops_triggered": 0,
        }

        self.logger.info("WatchdogManager initialized")

    # =========================================================================
    # LIFECYCLE
    # =========================================================================

    async def start(self):
        """Start watchdog monitoring."""
        if self._running:
            return

        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self.logger.info("WatchdogManager started")

    async def stop(self):
        """Stop watchdog monitoring."""
        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        self.logger.info("WatchdogManager stopped")

    async def _monitor_loop(self):
        """Main monitoring loop."""
        interval = self.config.check_interval_ms / 1000.0

        while self._running:
            try:
                await self._check_all_watchdogs()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Monitor loop error: {e}")
                await asyncio.sleep(interval)

    async def _check_all_watchdogs(self):
        """Check all watchdog items for timeout."""
        current_time = time.time()

        with self._lock:
            items_to_check = list(self._items.items())

        for name, item in items_to_check:
            if item.state == WatchdogState.INACTIVE:
                continue

            elapsed_ms = (current_time - item.last_kick) * 1000
            timeout_ms = item.config.timeout_ms
            warning_ms = timeout_ms * item.config.warning_threshold_pct

            if elapsed_ms >= timeout_ms:
                await self._handle_timeout(name, item)
            elif elapsed_ms >= warning_ms and item.state != WatchdogState.WARNING:
                self._handle_warning(name, item, elapsed_ms)

    # =========================================================================
    # WATCHDOG OPERATIONS
    # =========================================================================

    def start_watch(
        self,
        name: str,
        timeout_ms: Optional[float] = None,
        action: WatchdogAction = WatchdogAction.CALLBACK,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Start watching an item for timeout.

        Args:
            name: Unique identifier for this watchdog
            timeout_ms: Timeout in milliseconds (default: command_timeout_ms)
            action: Action to take on timeout
            metadata: Additional metadata to store
        """
        config = WatchdogConfig(
            name=name,
            timeout_ms=timeout_ms or self.config.command_timeout_ms,
            action=action,
        )

        item = WatchdogItem(
            config=config,
            state=WatchdogState.ACTIVE,
            last_kick=time.time(),
            metadata=metadata or {},
        )

        with self._lock:
            self._items[name] = item

        self.logger.debug(f"Started watchdog: {name} (timeout: {config.timeout_ms}ms)")

    def kick(self, name: str) -> bool:
        """
        Kick (refresh) a watchdog to prevent timeout.

        Args:
            name: Watchdog identifier

        Returns:
            True if watchdog was found and kicked
        """
        with self._lock:
            if name not in self._items:
                return False

            item = self._items[name]
            item.last_kick = time.time()
            item.state = WatchdogState.ACTIVE
            return True

    def stop_watch(self, name: str) -> bool:
        """
        Stop watching an item.

        Args:
            name: Watchdog identifier

        Returns:
            True if watchdog was found and stopped
        """
        with self._lock:
            if name in self._items:
                del self._items[name]
                self.logger.debug(f"Stopped watchdog: {name}")
                return True
            return False

    def is_watching(self, name: str) -> bool:
        """Check if an item is being watched."""
        with self._lock:
            return name in self._items

    def get_elapsed_ms(self, name: str) -> Optional[float]:
        """Get elapsed time since last kick in milliseconds."""
        with self._lock:
            if name not in self._items:
                return None
            item = self._items[name]
            return (time.time() - item.last_kick) * 1000

    # =========================================================================
    # TIMEOUT HANDLING
    # =========================================================================

    def _handle_warning(self, name: str, item: WatchdogItem, elapsed_ms: float):
        """Handle warning threshold reached."""
        item.state = WatchdogState.WARNING
        self._stats["warnings_issued"] += 1

        self.logger.warning(
            f"Watchdog warning: {name} at {elapsed_ms:.1f}ms "
            f"(timeout: {item.config.timeout_ms}ms)"
        )

    async def _handle_timeout(self, name: str, item: WatchdogItem):
        """Handle watchdog timeout."""
        item.state = WatchdogState.TIMEOUT
        item.timeout_count += 1
        self._stats["timeouts_detected"] += 1

        self.logger.error(
            f"Watchdog timeout: {name} " f"(count: {item.timeout_count}/{item.config.max_timeouts})"
        )

        # Execute action based on configuration
        action = item.config.action

        if action == WatchdogAction.LOG_WARNING:
            # Already logged
            pass

        elif action == WatchdogAction.CALLBACK:
            for callback in self._timeout_callbacks:
                try:
                    callback(name, item)
                except Exception as e:
                    self.logger.error(f"Timeout callback error: {e}")

        elif action == WatchdogAction.RESTART_SUBSYSTEM:
            await self._restart_subsystem(name, item)

        elif action == WatchdogAction.TRIGGER_ESTOP:
            await self._trigger_estop(name, item)

        # Check for escalation
        if item.timeout_count >= item.config.max_timeouts:
            self.logger.critical(f"Watchdog {name} exceeded max timeouts - escalating")
            await self._trigger_estop(name, item)

    async def _restart_subsystem(self, name: str, item: WatchdogItem):
        """Attempt to restart a subsystem."""
        self._stats["restarts_triggered"] += 1

        # Check for restart callback
        if name in self._restart_callbacks:
            callback = self._restart_callbacks[name]
            try:
                success = callback(name)
                if success:
                    self._stats["restarts_succeeded"] += 1
                    item.state = WatchdogState.RECOVERED
                    item.last_kick = time.time()
                    self.logger.info(f"Successfully restarted: {name}")
                else:
                    self.logger.error(f"Failed to restart: {name}")
            except Exception as e:
                self.logger.error(f"Restart callback error for {name}: {e}")
        else:
            self.logger.warning(f"No restart callback registered for: {name}")

    async def _trigger_estop(self, name: str, item: WatchdogItem):
        """Trigger emergency stop due to watchdog failure."""
        self._stats["estops_triggered"] += 1

        self.logger.critical(f"Watchdog {name} triggering E-STOP!")

        # This would integrate with safety system
        for callback in self._timeout_callbacks:
            try:
                item.metadata["escalated_to_estop"] = True
                callback(name, item)
            except Exception as e:
                self.logger.error(f"E-Stop callback error: {e}")

    # =========================================================================
    # CONTROL LOOP MONITORING
    # =========================================================================

    def control_loop_start(self):
        """Mark start of control loop iteration."""
        self._control_loop_start = time.perf_counter()

    def control_loop_end(self) -> float:
        """
        Mark end of control loop iteration.

        Returns:
            Latency in milliseconds
        """
        if self._control_loop_start is None:
            return 0.0

        elapsed_s = time.perf_counter() - self._control_loop_start
        latency_ms = elapsed_s * 1000

        # Update stats
        self._control_loop_stats["iterations"] += 1
        self._control_loop_stats["total_latency_ms"] += latency_ms
        self._control_loop_stats["avg_latency_ms"] = (
            self._control_loop_stats["total_latency_ms"] / self._control_loop_stats["iterations"]
        )

        if latency_ms > self._control_loop_stats["max_latency_ms"]:
            self._control_loop_stats["max_latency_ms"] = latency_ms

        # Check for overrun
        if latency_ms > self.config.control_loop_timeout_ms:
            self._control_loop_stats["overruns"] += 1
            self.logger.warning(
                f"Control loop overrun: {latency_ms:.2f}ms "
                f"(limit: {self.config.control_loop_timeout_ms}ms)"
            )
        elif latency_ms > self.config.control_loop_warning_ms:
            self.logger.debug(f"Control loop slow: {latency_ms:.2f}ms")

        self._control_loop_start = None
        return latency_ms

    class ControlLoopContext:
        """Context manager for control loop timing."""

        def __init__(self, manager: "WatchdogManager"):
            self.manager = manager

        def __enter__(self):
            self.manager.control_loop_start()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.manager.control_loop_end()
            return False

    def control_loop_context(self) -> "ControlLoopContext":
        """Get context manager for control loop timing."""
        return self.ControlLoopContext(self)

    # =========================================================================
    # SUBSYSTEM MONITORING
    # =========================================================================

    def register_subsystem(
        self,
        name: str,
        timeout_ms: Optional[float] = None,
        restart_callback: Optional[RestartCallback] = None,
    ):
        """
        Register a subsystem for monitoring.

        Args:
            name: Subsystem name
            timeout_ms: Heartbeat timeout
            restart_callback: Callback to restart subsystem
        """
        config = WatchdogConfig(
            name=name,
            timeout_ms=timeout_ms or self.config.subsystem_timeout_ms,
            action=(
                WatchdogAction.RESTART_SUBSYSTEM if restart_callback else WatchdogAction.CALLBACK
            ),
            auto_restart=restart_callback is not None,
        )

        item = WatchdogItem(config=config, state=WatchdogState.ACTIVE, last_kick=time.time())

        with self._lock:
            self._items[name] = item

        if restart_callback:
            self._restart_callbacks[name] = restart_callback

        self.logger.info(f"Registered subsystem: {name}")

    def subsystem_heartbeat(self, name: str) -> bool:
        """
        Report subsystem heartbeat.

        Args:
            name: Subsystem name

        Returns:
            True if subsystem is registered
        """
        return self.kick(name)

    # =========================================================================
    # CALLBACKS
    # =========================================================================

    def on_timeout(self, callback: TimeoutCallback):
        """Register timeout callback."""
        self._timeout_callbacks.append(callback)

    # =========================================================================
    # STATUS
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get watchdog manager status."""
        with self._lock:
            items_status = {
                name: {
                    "state": item.state.name,
                    "timeout_ms": item.config.timeout_ms,
                    "elapsed_ms": (time.time() - item.last_kick) * 1000,
                    "timeout_count": item.timeout_count,
                }
                for name, item in self._items.items()
            }

        return {
            "running": self._running,
            "watched_items": len(self._items),
            "items": items_status,
            "control_loop": self._control_loop_stats.copy(),
            "stats": self._stats.copy(),
        }

    def get_health_report(self) -> Dict[str, Any]:
        """Get health report for Webthread."""
        with self._lock:
            timeout_items = [
                name for name, item in self._items.items() if item.state == WatchdogState.TIMEOUT
            ]
            warning_items = [
                name for name, item in self._items.items() if item.state == WatchdogState.WARNING
            ]

        return {
            "healthy": len(timeout_items) == 0,
            "timeout_items": timeout_items,
            "warning_items": warning_items,
            "control_loop_overruns": self._control_loop_stats["overruns"],
            "total_timeouts": self._stats["timeouts_detected"],
        }
