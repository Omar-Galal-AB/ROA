"""
state_persistence.py
ROA - Robot Operations & Automation
HB Subsystem State Persistence - Snapshot and crash recovery

Implements periodic state snapshots and crash recovery for the HB subsystem.
This allows the system to recover state after unexpected restarts and
provides historical data for debugging.

Key Features:
- Periodic snapshots (every 5 seconds by default)
- Fast storage (tmpfs/ramdisk) for current state
- Persistent storage for history
- Crash recovery - load last known state on startup
- State versioning for compatibility
"""

import gzip
import json
import logging
import os
import shutil
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# State format version
STATE_VERSION = 1


@dataclass
class ComponentStateSnapshot:
    """Snapshot of a single component's state"""

    component_name: str
    component_id: int
    state: str  # ComponentState name
    health: str  # HealthLevel name
    alert_level: str  # AlertLevel name
    last_heartbeat_time: float
    last_sequence: int
    consecutive_misses: int
    response_time_avg_ms: float
    error_count: int
    recovery_attempts: int
    memory_percent: int
    cpu_percent: int
    queue_depth: int


@dataclass
class CircuitBreakerSnapshot:
    """Snapshot of circuit breaker state"""

    component_name: str
    state: str  # CircuitBreakerState name
    failure_count: int
    success_count: int
    last_failure_time: float
    last_success_time: float


@dataclass
class SystemStateSnapshot:
    """Complete system state snapshot"""

    version: int
    timestamp: float
    timestamp_iso: str
    uptime_seconds: float
    components: Dict[str, Dict[str, Any]]
    circuit_breakers: Dict[str, Dict[str, Any]]
    pending_recoveries: Dict[str, int]
    failure_counts: Dict[str, int]
    metrics: Dict[str, Any]


class StatePersistence:
    """
    Manages state persistence for the HB subsystem.

    Usage:
        persistence = StatePersistence(
            fast_storage_path="/dev/shm/roa_hb",  # tmpfs
            persistent_storage_path="/var/lib/roa/hb"
        )
        persistence.start()

        # Periodic snapshots happen automatically

        # On startup, recover previous state:
        last_state = persistence.load_last_state()

        # Manual snapshot:
        persistence.snapshot(current_state)
    """

    def __init__(
        self,
        fast_storage_path: Optional[str] = None,
        persistent_storage_path: Optional[str] = None,
        snapshot_interval_s: float = 5.0,
        max_history_files: int = 100,
        compress_history: bool = True,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize StatePersistence.

        Args:
            fast_storage_path: Path for fast storage (tmpfs/ramdisk preferred)
            persistent_storage_path: Path for persistent storage
            snapshot_interval_s: Interval between automatic snapshots
            max_history_files: Maximum number of history files to keep
            compress_history: Whether to compress historical snapshots
            logger: Optional logger
        """
        # Default paths
        if fast_storage_path is None:
            # Try tmpfs locations
            for path in ["/dev/shm/roa_hb", "/run/roa_hb", "/tmp/roa_hb"]:
                if os.path.isdir(os.path.dirname(path)) or path.startswith("/tmp"):
                    fast_storage_path = path
                    break

        if persistent_storage_path is None:
            # Default to home directory for persistence
            persistent_storage_path = os.path.expanduser("~/.roa/hb_state")

        self.fast_storage_path = Path(fast_storage_path)
        self.persistent_storage_path = Path(persistent_storage_path)
        self.snapshot_interval_s = snapshot_interval_s
        self.max_history_files = max_history_files
        self.compress_history = compress_history

        self.logger = logger or logging.getLogger("StatePersistence")

        self._lock = threading.Lock()
        self._running = False
        self._stop_event = threading.Event()
        self._snapshot_thread: Optional[threading.Thread] = None

        # State provider callback
        self._state_provider: Optional[callable] = None

        # Statistics
        self._snapshot_count = 0
        self._last_snapshot_time = 0.0
        self._last_snapshot_size = 0
        self._start_time = time.time()

        # Ensure directories exist
        self._ensure_directories()

    def _ensure_directories(self):
        """Ensure storage directories exist"""
        try:
            self.fast_storage_path.mkdir(parents=True, exist_ok=True)
            self.persistent_storage_path.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Fast storage: {self.fast_storage_path}")
            self.logger.info(f"Persistent storage: {self.persistent_storage_path}")
        except Exception as e:
            self.logger.error(f"Failed to create storage directories: {e}")

    def set_state_provider(self, provider: callable):
        """
        Set callback that provides current state.

        The callback should return a dictionary with the current state.

        Args:
            provider: Function that returns current state dict
        """
        self._state_provider = provider

    def start(self):
        """Start automatic snapshots"""
        if self._running:
            return

        self.logger.info("Starting state persistence...")

        self._running = True
        self._stop_event.clear()
        self._start_time = time.time()

        self._snapshot_thread = threading.Thread(target=self._snapshot_loop, daemon=True)
        self._snapshot_thread.name = "StatePersistence"
        self._snapshot_thread.start()

        self.logger.info("State persistence started")

    def stop(self):
        """Stop automatic snapshots"""
        if not self._running:
            return

        self.logger.info("Stopping state persistence...")

        self._running = False
        self._stop_event.set()

        if self._snapshot_thread and self._snapshot_thread.is_alive():
            self._snapshot_thread.join(timeout=2.0)

        # Final snapshot before stopping
        try:
            self._do_snapshot()
        except:
            pass

        self.logger.info("State persistence stopped")

    def _snapshot_loop(self):
        """Automatic snapshot loop"""
        self.logger.debug("Snapshot loop started")

        while self._running and not self._stop_event.is_set():
            try:
                self._do_snapshot()
            except Exception as e:
                self.logger.error(f"Snapshot error: {e}")

            self._stop_event.wait(self.snapshot_interval_s)

        self.logger.debug("Snapshot loop ended")

    def _do_snapshot(self):
        """Perform a snapshot"""
        if not self._state_provider:
            return

        try:
            # Get current state
            state_data = self._state_provider()

            # Build snapshot
            snapshot = SystemStateSnapshot(
                version=STATE_VERSION,
                timestamp=time.time(),
                timestamp_iso=datetime.now().isoformat(),
                uptime_seconds=time.time() - self._start_time,
                components=state_data.get("components", {}),
                circuit_breakers=state_data.get("circuit_breakers", {}),
                pending_recoveries=state_data.get("pending_recoveries", {}),
                failure_counts=state_data.get("failure_counts", {}),
                metrics=state_data.get("metrics", {}),
            )

            # Save to fast storage
            self._save_to_fast_storage(snapshot)

            # Periodically save to persistent storage
            if self._snapshot_count % 12 == 0:  # Every minute (12 * 5s)
                self._save_to_persistent_storage(snapshot)

            self._snapshot_count += 1
            self._last_snapshot_time = time.time()

        except Exception as e:
            self.logger.error(f"Error during snapshot: {e}")
            raise

    def _save_to_fast_storage(self, snapshot: SystemStateSnapshot):
        """Save snapshot to fast storage"""
        filepath = self.fast_storage_path / "current_state.json"
        temp_path = self.fast_storage_path / "current_state.json.tmp"

        with self._lock:
            try:
                # Write to temp file first
                data = self._snapshot_to_dict(snapshot)
                json_str = json.dumps(data, indent=2)

                with open(temp_path, "w") as f:
                    f.write(json_str)

                # Atomic rename
                temp_path.rename(filepath)

                self._last_snapshot_size = len(json_str)

            except Exception as e:
                self.logger.error(f"Failed to save to fast storage: {e}")
                if temp_path.exists():
                    temp_path.unlink()

    def _save_to_persistent_storage(self, snapshot: SystemStateSnapshot):
        """Save snapshot to persistent storage"""
        timestamp = datetime.fromtimestamp(snapshot.timestamp)
        filename = f"state_{timestamp.strftime('%Y%m%d_%H%M%S')}"

        if self.compress_history:
            filename += ".json.gz"
            filepath = self.persistent_storage_path / filename

            try:
                data = self._snapshot_to_dict(snapshot)
                json_bytes = json.dumps(data).encode("utf-8")

                with gzip.open(filepath, "wb") as f:
                    f.write(json_bytes)

            except Exception as e:
                self.logger.error(f"Failed to save compressed snapshot: {e}")
        else:
            filename += ".json"
            filepath = self.persistent_storage_path / filename

            try:
                data = self._snapshot_to_dict(snapshot)
                with open(filepath, "w") as f:
                    json.dump(data, f, indent=2)

            except Exception as e:
                self.logger.error(f"Failed to save snapshot: {e}")

        # Cleanup old files
        self._cleanup_old_files()

    def _cleanup_old_files(self):
        """Remove old history files"""
        try:
            files = sorted(self.persistent_storage_path.glob("state_*"))

            if len(files) > self.max_history_files:
                for old_file in files[: -self.max_history_files]:
                    old_file.unlink()
                    self.logger.debug(f"Removed old state file: {old_file.name}")

        except Exception as e:
            self.logger.error(f"Error cleaning up old files: {e}")

    def _snapshot_to_dict(self, snapshot: SystemStateSnapshot) -> Dict[str, Any]:
        """Convert snapshot to dictionary"""
        return {
            "version": snapshot.version,
            "timestamp": snapshot.timestamp,
            "timestamp_iso": snapshot.timestamp_iso,
            "uptime_seconds": snapshot.uptime_seconds,
            "components": snapshot.components,
            "circuit_breakers": snapshot.circuit_breakers,
            "pending_recoveries": snapshot.pending_recoveries,
            "failure_counts": snapshot.failure_counts,
            "metrics": snapshot.metrics,
        }

    def load_last_state(self) -> Optional[Dict[str, Any]]:
        """
        Load the most recent state snapshot.

        Tries fast storage first, then persistent storage.

        Returns:
            State dictionary or None if no state found
        """
        # Try fast storage first
        fast_path = self.fast_storage_path / "current_state.json"
        if fast_path.exists():
            try:
                with open(fast_path, "r") as f:
                    data = json.load(f)

                if self._validate_state(data):
                    self.logger.info(
                        f"Loaded state from fast storage (age: {time.time() - data['timestamp']:.1f}s)"
                    )
                    return data
            except Exception as e:
                self.logger.warning(f"Failed to load from fast storage: {e}")

        # Try persistent storage
        try:
            files = sorted(self.persistent_storage_path.glob("state_*"), reverse=True)

            for filepath in files[:5]:  # Try last 5 files
                try:
                    if filepath.suffix == ".gz":
                        with gzip.open(filepath, "rb") as f:
                            data = json.loads(f.read().decode("utf-8"))
                    else:
                        with open(filepath, "r") as f:
                            data = json.load(f)

                    if self._validate_state(data):
                        self.logger.info(f"Loaded state from persistent storage: {filepath.name}")
                        return data

                except Exception as e:
                    self.logger.warning(f"Failed to load {filepath.name}: {e}")
                    continue

        except Exception as e:
            self.logger.warning(f"Failed to search persistent storage: {e}")

        self.logger.info("No previous state found")
        return None

    def _validate_state(self, data: Dict[str, Any]) -> bool:
        """Validate state data structure"""
        required_keys = ["version", "timestamp", "components"]

        for key in required_keys:
            if key not in data:
                return False

        # Check version compatibility
        if data["version"] > STATE_VERSION:
            self.logger.warning(
                f"State version {data['version']} is newer than supported {STATE_VERSION}"
            )
            return False

        return True

    def get_history(self, max_entries: int = 10) -> List[Dict[str, Any]]:
        """
        Get historical state snapshots.

        Args:
            max_entries: Maximum number of entries to return

        Returns:
            List of state dictionaries (newest first)
        """
        history = []

        try:
            files = sorted(self.persistent_storage_path.glob("state_*"), reverse=True)

            for filepath in files[:max_entries]:
                try:
                    if filepath.suffix == ".gz":
                        with gzip.open(filepath, "rb") as f:
                            data = json.loads(f.read().decode("utf-8"))
                    else:
                        with open(filepath, "r") as f:
                            data = json.load(f)

                    history.append(data)

                except Exception as e:
                    self.logger.debug(f"Failed to load history file {filepath.name}: {e}")

        except Exception as e:
            self.logger.error(f"Error loading history: {e}")

        return history

    def manual_snapshot(self) -> bool:
        """
        Trigger a manual snapshot.

        Returns:
            True if snapshot was successful
        """
        try:
            self._do_snapshot()
            return True
        except:
            return False

    def clear_fast_storage(self):
        """Clear fast storage"""
        try:
            for file in self.fast_storage_path.glob("*"):
                file.unlink()
            self.logger.info("Fast storage cleared")
        except Exception as e:
            self.logger.error(f"Failed to clear fast storage: {e}")

    def get_metrics(self) -> Dict[str, Any]:
        """Get persistence metrics"""
        return {
            "running": self._running,
            "snapshot_count": self._snapshot_count,
            "last_snapshot_time": self._last_snapshot_time,
            "last_snapshot_age_s": (
                time.time() - self._last_snapshot_time if self._last_snapshot_time else 0
            ),
            "last_snapshot_size_bytes": self._last_snapshot_size,
            "fast_storage_path": str(self.fast_storage_path),
            "persistent_storage_path": str(self.persistent_storage_path),
            "snapshot_interval_s": self.snapshot_interval_s,
        }


class StateRecovery:
    """
    Handles state recovery after crashes.

    Takes loaded state and applies it to the HB subsystem components.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("StateRecovery")

    def recover_component_states(
        self, loaded_state: Dict[str, Any], max_age_seconds: float = 300  # 5 minutes
    ) -> Dict[str, Dict[str, Any]]:
        """
        Extract recoverable component states.

        Args:
            loaded_state: State dictionary from persistence
            max_age_seconds: Maximum age of state to consider valid

        Returns:
            Dictionary of component states to restore
        """
        if not loaded_state:
            return {}

        # Check age
        state_age = time.time() - loaded_state.get("timestamp", 0)
        if state_age > max_age_seconds:
            self.logger.warning(f"State too old ({state_age:.0f}s), not recovering")
            return {}

        components = loaded_state.get("components", {})
        recoverable = {}

        for name, state in components.items():
            # Only recover if not in failed state
            if state.get("health") != "FAILED":
                recoverable[name] = {
                    "last_sequence": state.get("last_sequence", 0),
                    "recovery_attempts": state.get("recovery_attempts", 0),
                    "response_time_avg_ms": state.get("response_time_avg_ms", 0),
                }

        self.logger.info(f"Recovered state for {len(recoverable)} components")
        return recoverable

    def recover_circuit_breakers(self, loaded_state: Dict[str, Any]) -> Dict[str, str]:
        """
        Extract circuit breaker states.

        Args:
            loaded_state: State dictionary from persistence

        Returns:
            Dictionary of component name -> circuit breaker state name
        """
        if not loaded_state:
            return {}

        breakers = loaded_state.get("circuit_breakers", {})
        return {name: state.get("state", "CLOSED") for name, state in breakers.items()}

    def recover_failure_counts(self, loaded_state: Dict[str, Any]) -> Dict[str, int]:
        """
        Extract failure counts for components.

        Args:
            loaded_state: State dictionary from persistence

        Returns:
            Dictionary of component name -> failure count
        """
        if not loaded_state:
            return {}

        return loaded_state.get("failure_counts", {})
