"""
hb_watchdog.py
ROA - Robot Operations & Automation
HB Subsystem Watchdog - Self-monitoring for the heartbeat subsystem

The HB subsystem needs its own watchdog to detect if it becomes
unresponsive. This watchdog runs in a separate thread and monitors
the health of the receiver, aggregator, and other HB components.

If the HB subsystem fails, the watchdog reports to WT Core so it
can take action (restart HB subsystem, enter degraded mode, etc.)

Key Features:
- Monitors HB receiver thread liveness
- Monitors HB aggregator thread liveness
- Monitors queue depths
- Reports to WT Core on HB subsystem failures
- Self-pet mechanism to prove watchdog is alive
"""

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class WatchdogStatus(Enum):
    """Watchdog status states"""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    DEAD = "dead"


@dataclass
class WatchedThread:
    """Information about a watched thread"""

    name: str
    thread: Optional[threading.Thread]
    last_pet_time: float
    pet_timeout_ms: float
    status: WatchdogStatus
    check_callback: Optional[Callable[[], bool]] = None


class HBWatchdog:
    """
    Watchdog for the HB Subsystem.

    Monitors the health of HB subsystem components and reports
    to WT Core if any component becomes unresponsive.

    Usage:
        watchdog = HBWatchdog()
        watchdog.watch_thread("receiver", receiver_thread, pet_callback)
        watchdog.watch_thread("aggregator", aggregator_thread)
        watchdog.on_failure(failure_handler)
        watchdog.start()

        # In watched threads, periodically call:
        watchdog.pet("receiver")
    """

    def __init__(
        self,
        check_interval_ms: float = 100,
        default_timeout_ms: float = 500,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize HBWatchdog.

        Args:
            check_interval_ms: How often to check watched threads
            default_timeout_ms: Default pet timeout
            logger: Optional logger
        """
        self.check_interval_ms = check_interval_ms
        self.default_timeout_ms = default_timeout_ms
        self.logger = logger or logging.getLogger("HBWatchdog")

        self._lock = threading.RLock()
        self._running = False
        self._stop_event = threading.Event()
        self._watchdog_thread: Optional[threading.Thread] = None

        # Watched threads
        self._watched: Dict[str, WatchedThread] = {}

        # Queue monitoring
        self._watched_queues: Dict[str, tuple] = {}  # name -> (queue, max_depth)

        # Callbacks
        self._failure_callbacks: List[Callable[[str, WatchdogStatus], None]] = []
        self._recovery_callbacks: List[Callable[[str], None]] = []

        # Watchdog's own heartbeat (to prove it's alive)
        self._own_last_beat = time.time()
        self._own_beat_interval_ms = 100

        # Statistics
        self._pet_counts: Dict[str, int] = {}
        self._failure_counts: Dict[str, int] = {}

    def watch_thread(
        self,
        name: str,
        thread: threading.Thread,
        timeout_ms: Optional[float] = None,
        check_callback: Optional[Callable[[], bool]] = None,
    ):
        """
        Register a thread to watch.

        Args:
            name: Name of the thread/component
            thread: Thread object to monitor
            timeout_ms: Custom timeout for this thread
            check_callback: Optional callback that returns True if thread is healthy
        """
        with self._lock:
            self._watched[name] = WatchedThread(
                name=name,
                thread=thread,
                last_pet_time=time.time(),
                pet_timeout_ms=timeout_ms or self.default_timeout_ms,
                status=WatchdogStatus.HEALTHY,
                check_callback=check_callback,
            )
            self._pet_counts[name] = 0
            self._failure_counts[name] = 0

            self.logger.info(f"Watching thread: {name}")

    def unwatch_thread(self, name: str):
        """Stop watching a thread"""
        with self._lock:
            if name in self._watched:
                del self._watched[name]
                self.logger.info(f"Stopped watching thread: {name}")

    def watch_queue(self, name: str, queue_obj, max_depth: int = 1000):
        """
        Register a queue to monitor.

        Args:
            name: Name of the queue
            queue_obj: Queue object (must have qsize() method)
            max_depth: Maximum allowed depth before warning
        """
        with self._lock:
            self._watched_queues[name] = (queue_obj, max_depth)
            self.logger.info(f"Watching queue: {name} (max: {max_depth})")

    def pet(self, name: str):
        """
        Pet the watchdog for a specific thread.

        Threads must call this periodically to prove they're alive.

        Args:
            name: Name of the thread/component
        """
        with self._lock:
            watched = self._watched.get(name)
            if watched:
                watched.last_pet_time = time.time()
                self._pet_counts[name] = self._pet_counts.get(name, 0) + 1

    def on_failure(self, callback: Callable[[str, WatchdogStatus], None]):
        """Register callback for thread failures"""
        self._failure_callbacks.append(callback)

    def on_recovery(self, callback: Callable[[str], None]):
        """Register callback for thread recovery"""
        self._recovery_callbacks.append(callback)

    def start(self):
        """Start the watchdog"""
        if self._running:
            return

        self.logger.info("Starting HB Watchdog...")

        self._running = True
        self._stop_event.clear()
        self._own_last_beat = time.time()

        self._watchdog_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._watchdog_thread.name = "HBWatchdog"
        self._watchdog_thread.start()

        self.logger.info("HB Watchdog started")

    def stop(self):
        """Stop the watchdog"""
        if not self._running:
            return

        self.logger.info("Stopping HB Watchdog...")

        self._running = False
        self._stop_event.set()

        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=1.0)

        self.logger.info("HB Watchdog stopped")

    def is_running(self) -> bool:
        """Check if watchdog is running"""
        return self._running

    def get_own_heartbeat_age_ms(self) -> float:
        """Get age of watchdog's own last heartbeat"""
        return (time.time() - self._own_last_beat) * 1000

    def _watch_loop(self):
        """Main watchdog loop"""
        self.logger.debug("Watchdog loop started")
        interval_s = self.check_interval_ms / 1000.0

        while self._running and not self._stop_event.is_set():
            try:
                # Update own heartbeat
                self._own_last_beat = time.time()

                # Check all watched threads
                self._check_threads()

                # Check all watched queues
                self._check_queues()

            except Exception as e:
                self.logger.error(f"Error in watchdog loop: {e}")

            self._stop_event.wait(interval_s)

        self.logger.debug("Watchdog loop ended")

    def _check_threads(self):
        """Check all watched threads"""
        now = time.time()

        with self._lock:
            for name, watched in self._watched.items():
                old_status = watched.status
                new_status = self._evaluate_thread_status(watched, now)

                if new_status != old_status:
                    watched.status = new_status
                    self._on_status_change(name, old_status, new_status)

    def _evaluate_thread_status(self, watched: WatchedThread, now: float) -> WatchdogStatus:
        """Evaluate the status of a watched thread"""
        # Check if thread is alive
        if watched.thread and not watched.thread.is_alive():
            return WatchdogStatus.DEAD

        # Check custom callback if provided
        if watched.check_callback:
            try:
                if not watched.check_callback():
                    return WatchdogStatus.CRITICAL
            except:
                return WatchdogStatus.WARNING

        # Check pet timeout
        elapsed_ms = (now - watched.last_pet_time) * 1000

        if elapsed_ms > watched.pet_timeout_ms * 2:
            return WatchdogStatus.CRITICAL
        elif elapsed_ms > watched.pet_timeout_ms:
            return WatchdogStatus.WARNING
        else:
            return WatchdogStatus.HEALTHY

    def _check_queues(self):
        """Check all watched queues"""
        with self._lock:
            for name, (queue_obj, max_depth) in self._watched_queues.items():
                try:
                    depth = queue_obj.qsize()
                    if depth > max_depth:
                        self.logger.warning(f"Queue {name} depth {depth} exceeds max {max_depth}")
                        # Could trigger a callback here
                except:
                    pass

    def _on_status_change(self, name: str, old_status: WatchdogStatus, new_status: WatchdogStatus):
        """Handle status change for a watched thread"""
        self.logger.warning(
            f"Thread {name} status changed: {old_status.value} -> {new_status.value}"
        )

        if new_status in [WatchdogStatus.CRITICAL, WatchdogStatus.DEAD]:
            self._failure_counts[name] = self._failure_counts.get(name, 0) + 1

            # Notify failure callbacks
            for callback in self._failure_callbacks:
                try:
                    callback(name, new_status)
                except Exception as e:
                    self.logger.error(f"Error in failure callback: {e}")

        elif new_status == WatchdogStatus.HEALTHY and old_status in [
            WatchdogStatus.CRITICAL,
            WatchdogStatus.DEAD,
        ]:
            # Recovery
            for callback in self._recovery_callbacks:
                try:
                    callback(name)
                except Exception as e:
                    self.logger.error(f"Error in recovery callback: {e}")

    def get_status(self, name: str) -> Optional[WatchdogStatus]:
        """Get status of a watched thread"""
        with self._lock:
            watched = self._watched.get(name)
            if watched:
                return watched.status
            return None

    def get_all_statuses(self) -> Dict[str, WatchdogStatus]:
        """Get statuses of all watched threads"""
        with self._lock:
            return {name: watched.status for name, watched in self._watched.items()}

    def get_metrics(self) -> Dict[str, Any]:
        """Get watchdog metrics"""
        with self._lock:
            return {
                "running": self._running,
                "own_heartbeat_age_ms": self.get_own_heartbeat_age_ms(),
                "watched_threads": len(self._watched),
                "watched_queues": len(self._watched_queues),
                "thread_statuses": {
                    name: {
                        "status": watched.status.value,
                        "pet_count": self._pet_counts.get(name, 0),
                        "failure_count": self._failure_counts.get(name, 0),
                        "last_pet_age_ms": (time.time() - watched.last_pet_time) * 1000,
                    }
                    for name, watched in self._watched.items()
                },
            }


class ComponentWatchdog:
    """
    Watchdog for individual components (not HB subsystem).

    This is a simpler watchdog that components can use internally
    to monitor their own health.

    Usage:
        watchdog = ComponentWatchdog("FTI", timeout_ms=100)
        watchdog.on_timeout(handle_timeout)
        watchdog.start()

        # In component main loop:
        watchdog.pet()
    """

    def __init__(
        self,
        component_name: str,
        timeout_ms: float = 100,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize ComponentWatchdog.

        Args:
            component_name: Name of the component
            timeout_ms: Time without pet before timeout
            logger: Optional logger
        """
        self.component_name = component_name
        self.timeout_ms = timeout_ms
        self.logger = logger or logging.getLogger(f"Watchdog.{component_name}")

        self._lock = threading.Lock()
        self._running = False
        self._stop_event = threading.Event()
        self._last_pet = time.time()
        self._thread: Optional[threading.Thread] = None

        self._timeout_callback: Optional[Callable[[], None]] = None
        self._timeout_count = 0

    def on_timeout(self, callback: Callable[[], None]):
        """Register callback for timeout events"""
        self._timeout_callback = callback

    def pet(self):
        """Pet the watchdog to reset timer"""
        with self._lock:
            self._last_pet = time.time()

    def start(self):
        """Start the watchdog"""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()
        self._last_pet = time.time()

        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.name = f"Watchdog-{self.component_name}"
        self._thread.start()

    def stop(self):
        """Stop the watchdog"""
        self._running = False
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)

    def _watch_loop(self):
        """Watchdog loop"""
        check_interval = self.timeout_ms / 1000.0 / 2  # Check twice per timeout period

        while self._running and not self._stop_event.is_set():
            try:
                with self._lock:
                    elapsed_ms = (time.time() - self._last_pet) * 1000

                if elapsed_ms > self.timeout_ms:
                    self._timeout_count += 1
                    self.logger.warning(
                        f"Watchdog timeout for {self.component_name} "
                        f"(no pet for {elapsed_ms:.0f}ms)"
                    )

                    if self._timeout_callback:
                        try:
                            self._timeout_callback()
                        except Exception as e:
                            self.logger.error(f"Error in timeout callback: {e}")

                    # Reset after callback to avoid repeated calls
                    with self._lock:
                        self._last_pet = time.time()

            except Exception as e:
                self.logger.error(f"Error in watchdog loop: {e}")

            self._stop_event.wait(check_interval)

    def get_timeout_count(self) -> int:
        """Get number of timeout events"""
        return self._timeout_count

    def get_last_pet_age_ms(self) -> float:
        """Get age of last pet in milliseconds"""
        with self._lock:
            return (time.time() - self._last_pet) * 1000
