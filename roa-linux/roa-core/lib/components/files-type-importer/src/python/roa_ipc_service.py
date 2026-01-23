#!/usr/bin/env python3
"""
ROA IPC Service - File-Based IPC Service for Linux

This service monitors the IPC folder for conversion requests from UE5
and processes them using the FileTypeImporter.

Key Features:
- Polling-based file watching (inotify doesn't work on /mnt/*)
- Adaptive polling (fast when active, slow when idle)
- Heartbeat for health monitoring
- Atomic file operations
- Request deduplication
- Timeout handling
- Graceful shutdown

Gap Fixes Implemented:
- Gap 2.1: Uses polling instead of inotify for /mnt/* paths
- Gap 2.2: Adaptive polling with intelligent backoff
- Gap 3.2: Graceful shutdown with pending request handling
- Gap 3.3: Proper heartbeat with service.status file
- Gap 4.2: Request-level timeout handling
- Gap 4.3: Request deduplication

Usage:
    # Start the service
    python roa_ipc_service.py

    # Start with custom IPC path
    python roa_ipc_service.py --ipc-path /mnt/d/MyROA/.ipc

    # Start in foreground with debug logging
    python roa_ipc_service.py --foreground --debug
"""

import argparse
import json
import logging
import os
import signal
import sys
import threading
import time
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Add paths for imports
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "IPC"))

# Import converter
from file_type_importer import FileTypeImporter

# Import FTI Storage subsystem
from fti_storage import (
    ConversionRecord,
    ConversionStatus,
    FTIStorage,
    get_storage,
    init_storage,
)

# Import IPC protocol
from IPC.ipc_protocol import (
    PROTOCOL_VERSION,
    ErrorCode,
    IPCPaths,
    IPCProgress,
    IPCRequest,
    IPCResponse,
    RequestDeduplicator,
    ServiceStatus,
    cleanup_request,
    read_request,
    write_ack,
    write_progress,
    write_response,
)
from Utils.path_handler import get_path_handler


# Configure logging
def setup_logging(debug: bool = False, log_file: Optional[str] = None):
    """Configure logging for the service."""
    level = logging.DEBUG if debug else logging.INFO

    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    # Use force=True to override any existing config (Python 3.8+)
    logging.basicConfig(
        level=level,
        format="%(asctime)s - ROA-IPC - %(levelname)s - %(message)s",
        handlers=handlers,
        force=True,
    )
    return logging.getLogger(__name__)


logger = logging.getLogger(__name__)


@dataclass
class ServiceConfig:
    """Service configuration."""

    ipc_path: str = r"D:\ROA\.ipc"

    # Polling settings
    poll_interval_active: float = 0.1  # 100ms when processing
    poll_interval_idle: float = 1.0  # 1s when idle
    poll_backoff_factor: float = 1.5  # Exponential backoff

    # Heartbeat settings
    heartbeat_interval: float = 5.0  # Update service.status every 5s

    # Client lifecycle settings
    client_heartbeat_timeout: float = 30.0  # Client considered dead after 30s no heartbeat
    client_check_interval: float = 10.0  # Check clients every 10s
    auto_shutdown_delay: float = 60.0  # Shutdown after 60s with no clients
    auto_shutdown_enabled: bool = True  # Enable auto-shutdown when no clients

    # Timeout settings
    default_timeout_ms: int = 60000  # 60 seconds
    max_timeout_ms: int = 300000  # 5 minutes max

    # Cleanup settings
    response_ttl_seconds: int = 3600  # Keep responses for 1 hour
    cleanup_interval: float = 300.0  # Run cleanup every 5 minutes

    # Concurrency
    max_concurrent_requests: int = 1  # Process one at a time (for now)


class AdaptivePoller:
    """
    Adaptive polling implementation.

    Implements: Gap 2.2 fix

    - Fast polling when requests are being processed
    - Slow polling when idle
    - Smooth transition using exponential backoff
    """

    def __init__(self, config: ServiceConfig):
        self.config = config
        self.current_interval = config.poll_interval_idle
        self._last_activity = time.time()

    def mark_activity(self):
        """Mark that activity occurred (speed up polling)."""
        self._last_activity = time.time()
        self.current_interval = self.config.poll_interval_active

    def wait(self):
        """Wait for the current interval, adjusting for idle time."""
        time.sleep(self.current_interval)

        # Gradually slow down if idle
        idle_time = time.time() - self._last_activity
        if idle_time > 5.0:  # Idle for more than 5 seconds
            self.current_interval = min(
                self.current_interval * self.config.poll_backoff_factor,
                self.config.poll_interval_idle,
            )


class ROAIPCService:
    """
    ROA IPC Service - Main service class.

    Monitors the IPC folder and processes conversion requests.
    """

    def __init__(self, config: Optional[ServiceConfig] = None):
        """Initialize the service."""
        self.config = config or ServiceConfig()
        self.paths = IPCPaths(self.config.ipc_path)
        self.poller = AdaptivePoller(self.config)
        self.deduplicator = RequestDeduplicator()

        # State
        self._running = False
        self._shutdown_event = threading.Event()
        self._start_time = None
        self._processed_count = 0
        self._failed_count = 0
        self._pending_requests: Set[str] = set()
        self._processed_files: Set[str] = set()

        # Client lifecycle management
        self._active_clients: Dict[str, float] = {}  # client_id -> last_heartbeat_time
        self._last_client_activity: float = 0.0  # Time of last client heartbeat
        self._no_clients_since: Optional[float] = None  # When we first noticed no clients

        # FTI Storage path for files that need to be copied
        self._fti_storage_path = self._init_fti_storage()

        # Initialize FTI Storage subsystem for logging and history
        self._storage = init_storage(self._fti_storage_path)
        logger.info(f"FTI Storage initialized: {self._fti_storage_path}")

        # FileTypeImporter instance
        self._fti: Optional[FileTypeImporter] = None

        # Path handler
        self.path_handler = get_path_handler()

        # Threads
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._cleanup_thread: Optional[threading.Thread] = None
        self._client_monitor_thread: Optional[threading.Thread] = None

        # Signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _init_fti_storage(self) -> Path:
        """
        Initialize FTI storage directory for files that need to be copied.

        This is used when files are in locations that can't be directly converted
        (e.g., network paths, inaccessible paths, non-WSL locations).

        Returns:
            Path to the FTI storage directory
        """
        # Primary storage location: D:\ROA\.fti_storage on Windows, /mnt/d/ROA/.fti_storage on Linux
        storage_paths = [
            Path("/mnt/d/ROA/.fti_storage"),
            Path("/mnt/c/ROA/.fti_storage"),
            Path.home() / ".roa" / "fti_storage",
        ]

        for storage_path in storage_paths:
            try:
                storage_path.mkdir(parents=True, exist_ok=True)
                # Create subdirectories
                (storage_path / "inputs").mkdir(exist_ok=True)
                (storage_path / "outputs").mkdir(exist_ok=True)
                (storage_path / "temp").mkdir(exist_ok=True)
                logger.info(f"FTI Storage initialized at: {storage_path}")
                return storage_path
            except Exception as e:
                logger.debug(f"Could not use storage path {storage_path}: {e}")

        # Fallback to temp directory
        import tempfile

        fallback = Path(tempfile.gettempdir()) / "roa_fti_storage"
        fallback.mkdir(parents=True, exist_ok=True)
        (fallback / "inputs").mkdir(exist_ok=True)
        (fallback / "outputs").mkdir(exist_ok=True)
        logger.warning(f"Using fallback FTI storage at: {fallback}")
        return fallback

    def _copy_to_fti_storage(self, source_path: str, include_package: bool = True) -> tuple:
        """
        Copy file(s) to FTI storage if needed.

        This is used when the source file is in an inaccessible location or
        when we need a local copy for processing.

        Args:
            source_path: Path to the source file
            include_package: If True, also copy package files (package.xml, config, meshes, etc.)

        Returns:
            Tuple of (new_path, package_path_or_None, was_copied)
        """
        import hashlib
        import shutil
        from pathlib import Path

        source = Path(source_path)

        # Check if source is already accessible
        if source.exists():
            # Check if we can read it
            try:
                with open(source, "rb") as f:
                    f.read(1)
                logger.debug(f"File already accessible: {source}")

                # Still return the package path if we find it
                package_path = self._find_package_root(source)
                return str(source), package_path, False
            except Exception as e:
                logger.debug(f"File not readable: {e}")

        # Need to copy the file
        # Create a unique subdirectory based on source path hash
        path_hash = hashlib.md5(str(source).encode()).hexdigest()[:12]
        target_dir = self._fti_storage_path / "inputs" / path_hash

        try:
            target_dir.mkdir(parents=True, exist_ok=True)

            if include_package:
                # Find and copy the entire package
                package_root = self._find_package_root(source)

                if package_root:
                    logger.info(f"Copying package from: {package_root}")

                    # Copy entire package directory structure
                    package_name = Path(package_root).name
                    target_package = target_dir / package_name

                    if target_package.exists():
                        shutil.rmtree(target_package)

                    shutil.copytree(package_root, target_package)

                    # Calculate new file path within copied package
                    rel_path = source.relative_to(package_root)
                    new_path = target_package / rel_path

                    logger.info(f"Package copied to: {target_package}")
                    return str(new_path), str(target_package), True

            # Just copy the single file
            target_file = target_dir / source.name
            shutil.copy2(source, target_file)
            logger.info(f"File copied to: {target_file}")
            return str(target_file), None, True

        except Exception as e:
            logger.error(f"Failed to copy file to FTI storage: {e}")
            return str(source), None, False

    def _find_package_root(self, file_path) -> str:
        """
        Find the ROS package root directory containing the given file.

        Searches upward for package.xml.

        Args:
            file_path: Path to a file within a package

        Returns:
            Path to package root, or None if not found
        """
        from pathlib import Path

        current = Path(file_path).parent

        for _ in range(10):  # Max 10 levels up
            package_xml = current / "package.xml"
            if package_xml.exists():
                return str(current)

            parent = current.parent
            if parent == current:
                break
            current = parent

        return None

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.stop()

    def _get_fti(self) -> FileTypeImporter:
        """Get or create FileTypeImporter instance."""
        if self._fti is None:
            self._fti = FileTypeImporter(
                enable_hb=False,  # No heartbeat needed
                enable_obs=False,  # No observability needed
            )
        return self._fti

    def start(self):
        """Start the IPC service."""
        logger.info("=" * 60)
        logger.info("ROA IPC Service Starting")
        logger.info(f"  Protocol Version: {PROTOCOL_VERSION}")
        logger.info(f"  IPC Path (Windows): {self.config.ipc_path}")
        logger.info(f"  IPC Path (Linux): {self.paths.base_path_linux}")
        logger.info("=" * 60)

        # Ensure directories exist
        self.paths.ensure_directories()

        # Clean up stale failed responses from previous sessions
        self._cleanup_stale_responses()

        # Acquire lock (single instance)
        if not self._acquire_lock():
            logger.error("Another instance is already running!")
            return False

        self._running = True
        self._start_time = time.time()
        self._last_client_activity = time.time()  # Assume a client just started us

        # Start heartbeat thread
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

        # Start cleanup thread
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

        # Start client monitor thread
        self._client_monitor_thread = threading.Thread(
            target=self._client_monitor_loop, daemon=True
        )
        self._client_monitor_thread.start()

        # Write initial status
        self._write_status()

        logger.info("Service started, entering main loop...")

        # Main processing loop
        try:
            self._main_loop()
        except Exception as e:
            logger.error(f"Fatal error in main loop: {e}")
            logger.error(traceback.format_exc())
        finally:
            self._cleanup_on_shutdown()

        return True

    def stop(self):
        """Stop the service gracefully."""
        logger.info("Stopping service...")
        self._running = False
        self._shutdown_event.set()

    def _acquire_lock(self) -> bool:
        """
        Acquire service lock file.

        Ensures only one instance runs at a time.
        """
        try:
            lock_path = self.paths.lock_file

            # Create lock file with PID
            if lock_path.exists():
                # Check if process is still running
                try:
                    with open(lock_path, "r") as f:
                        old_pid = int(f.read().strip())

                    # Check if old process exists
                    os.kill(old_pid, 0)
                    # If we get here, old process is still running
                    logger.error(f"Service already running with PID {old_pid}")
                    return False
                except (ValueError, ProcessLookupError, PermissionError):
                    # Old process is gone, we can take over
                    pass

            # Write our PID
            with open(lock_path, "w") as f:
                f.write(str(os.getpid()))

            return True
        except Exception as e:
            logger.error(f"Failed to acquire lock: {e}")
            return False

    def _release_lock(self):
        """Release the service lock file."""
        try:
            lock_path = self.paths.lock_file
            if lock_path.exists():
                lock_path.unlink()
        except:
            pass

    def _main_loop(self):
        """
        Main processing loop.

        Uses polling (not inotify) because inotify doesn't work on /mnt/*.
        Implements: Gap 2.1 fix
        """
        while self._running:
            try:
                # Check for new requests
                new_requests = self._scan_for_requests()

                if new_requests:
                    self.poller.mark_activity()

                    for request_file in new_requests:
                        if not self._running:
                            break
                        self._process_request_file(request_file)

                # Wait before next poll
                self.poller.wait()

            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                logger.error(traceback.format_exc())
                time.sleep(1.0)  # Avoid tight loop on persistent errors

    def _scan_for_requests(self) -> List[Path]:
        """
        Scan for new request files.

        Returns:
            List of new request files to process
        """
        try:
            requests_dir = self.paths.requests_dir

            if not requests_dir.exists():
                return []

            new_requests = []

            for f in requests_dir.iterdir():
                # Only process .json files (not .tmp)
                if f.suffix == ".json" and f.name.endswith(".request.json"):
                    if str(f) not in self._processed_files:
                        new_requests.append(f)

            return new_requests
        except Exception as e:
            logger.error(f"Error scanning requests: {e}")
            return []

    def _process_request_file(self, request_file: Path):
        """
        Process a single request file.

        Args:
            request_file: Path to the request JSON file
        """
        request_id = request_file.name.replace(".request.json", "")
        logger.info(f"Processing request: {request_id}")

        # Mark as processed immediately to avoid duplicate processing
        self._processed_files.add(str(request_file))
        self._pending_requests.add(request_id)

        start_time = time.time()

        try:
            # Read and parse request
            request = read_request(self.paths, request_id)

            if request is None:
                logger.error(f"Could not read request: {request_id}")
                self._send_error(request_id, ErrorCode.INVALID_JSON, "Could not parse request file")
                return

            # Validate request
            is_valid, error_msg = request.validate()
            if not is_valid:
                logger.error(f"Invalid request {request_id}: {error_msg}")
                self._send_error(request_id, ErrorCode.MISSING_FIELD, error_msg)
                return

            # Send acknowledgement
            write_ack(self.paths, request_id)

            # Check for duplicates
            is_new, existing_id = self.deduplicator.check(request)
            if not is_new:
                # Copy existing response to new request ID only if it was successful
                existing_response_file = self.paths.responses_dir / f"{existing_id}.response.json"
                if existing_response_file.exists():
                    try:
                        with open(existing_response_file, "r") as f:
                            existing_response = json.load(f)

                        # Only use cache for successful responses
                        if existing_response.get("success", False):
                            logger.info(
                                f"Duplicate request, returning cached response: {existing_id}"
                            )
                            # Update request_id to match new request
                            existing_response["request_id"] = request_id
                            existing_response["metadata"] = existing_response.get("metadata", {})
                            existing_response["metadata"]["cached_from"] = existing_id
                            # Write response with new request ID
                            new_response_file = (
                                self.paths.responses_dir / f"{request_id}.response.json"
                            )
                            with open(new_response_file, "w") as f:
                                json.dump(existing_response, f, indent=2)
                            logger.info(
                                f"Returned cached response for {request_id} (from {existing_id})"
                            )
                            self._processed_count += 1
                            return
                        else:
                            # Previous request failed, reprocess
                            logger.info(
                                f"Previous request {existing_id} failed, reprocessing {request_id}"
                            )
                            # Remove from deduplicator so it's processed fresh
                            self.deduplicator.remove(existing_id)
                    except Exception as e:
                        logger.warning(f"Could not check cached response: {e}, processing as new")
                        # Fall through to process as new request
                else:
                    logger.warning(
                        f"Cached response not found for {existing_id}, processing as new"
                    )

            # Check timeout
            timeout_ms = min(request.timeout_ms, self.config.max_timeout_ms)

            # Process based on request type
            if request.request_type == "convert":
                self._process_conversion(request, timeout_ms)
            elif request.request_type == "convert_xacro":
                # XACRO to URDF conversion (from UE5 plugin)
                self._process_xacro_to_urdf(request, timeout_ms)
            elif request.request_type == "prepare_for_ue5":
                self._process_prepare_for_ue5(request, timeout_ms)
            elif request.request_type == "convert_and_prepare":
                self._process_convert_and_prepare(request, timeout_ms)
            elif request.request_type == "validate":
                self._process_validation(request)
            elif request.request_type == "health_check":
                self._process_health_check(request)
            else:
                self._send_error(
                    request_id,
                    ErrorCode.INVALID_JSON,
                    f"Unknown request type: {request.request_type}",
                )

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Completed request {request_id} in {duration_ms}ms")
            self._processed_count += 1

        except Exception as e:
            logger.error(f"Error processing request {request_id}: {e}")
            logger.error(traceback.format_exc())
            self._send_error(request_id, ErrorCode.INTERNAL_ERROR, str(e))
            self._failed_count += 1
        finally:
            self._pending_requests.discard(request_id)
            # Clean up request file after processing
            cleanup_request(self.paths, request_id)

    def _process_conversion(self, request: IPCRequest, timeout_ms: int):
        """
        Process a conversion request.

        Args:
            request: The conversion request
            timeout_ms: Timeout in milliseconds
        """
        request_id = request.request_id
        conversion_start_time = time.time()

        # Update progress: Starting
        self._update_progress(request_id, 0.0, "Starting conversion...")

        # Get input path
        input_path = request.input.get("path", "")
        linux_input_path = self.path_handler.to_linux_path(input_path)

        # Detect input format for storage logging
        input_format = Path(input_path).suffix.lower() if input_path else ".unknown"

        # Generate unique record ID for storage tracking
        record_id = str(uuid.uuid4())

        # Check if file exists, if not try to copy from original location
        file_copied = False
        package_path = None

        if not os.path.exists(linux_input_path):
            # Try original path (might be Windows path that didn't convert)
            self._update_progress(
                request_id, 2.0, "File not directly accessible, checking locations..."
            )

            # Try to copy file to FTI storage
            if os.path.exists(input_path):
                linux_input_path, package_path, file_copied = self._copy_to_fti_storage(
                    input_path, include_package=True
                )
                if file_copied:
                    logger.info(f"File copied to FTI storage: {linux_input_path}")
                    self._update_progress(request_id, 5.0, "File copied to FTI storage")

            # Still not found?
            if not os.path.exists(linux_input_path):
                # Log failure to storage
                duration_ms = int((time.time() - conversion_start_time) * 1000)
                self._storage.log_conversion_failed(
                    record_id=record_id,
                    request_id=request_id,
                    input_path=input_path,
                    input_format=input_format,
                    error_code=str(ErrorCode.FILE_NOT_FOUND.value),
                    error_message=f"Input file not found and could not copy: {input_path}",
                    duration_ms=duration_ms,
                )
                self._send_error(
                    request_id,
                    ErrorCode.FILE_NOT_FOUND,
                    f"Input file not found and could not copy: {input_path}",
                )
                return
        else:
            # File exists - check if we need to copy package for XACRO processing
            ext = os.path.splitext(linux_input_path)[1].lower()
            if ext in [".xacro"]:
                # For XACRO files, we may need the full package for include resolution
                package_path = self._find_package_root(linux_input_path)
                if package_path:
                    logger.info(f"Found package root: {package_path}")

        # Get output settings
        output_dir = request.output.get("directory", "")
        linux_output_dir = self.path_handler.to_linux_path(output_dir)
        name_prefix = request.output.get("name_prefix", "robot")

        # Ensure output directory exists
        os.makedirs(linux_output_dir, exist_ok=True)

        # Update progress: Converting
        self._update_progress(request_id, 10.0, "Loading input file...")

        # Get options
        options = request.options or {}

        # Build FTI config
        fti_config = {
            "include_collision": options.get("include_collision", True),
            "include_visual": options.get("include_visual", True),
            "scale_factor": options.get("scale_factor", 1.0),
            "package_paths": options.get("package_paths", []),
        }

        # Add discovered package path to config
        if package_path:
            fti_config["package_paths"].append(package_path)

        # Get FTI instance
        fti = self._get_fti()

        # Define progress callback
        def progress_callback(percent: float, stage: str):
            # Scale to 10-90% range
            scaled = 10.0 + (percent * 0.8)
            self._update_progress(request_id, scaled, stage)

        # Run conversion with timeout
        import signal as sig

        def timeout_handler(signum, frame):
            raise TimeoutError(f"Conversion timed out after {timeout_ms}ms")

        old_handler = sig.signal(sig.SIGALRM, timeout_handler)
        sig.alarm(timeout_ms // 1000)

        try:
            # Update progress
            self._update_progress(request_id, 20.0, "Converting to USD...")

            # Detect format
            ext = Path(linux_input_path).suffix.lower()

            # Build output path - use user's selected directory!
            output_base = os.path.join(linux_output_dir, name_prefix)

            logger.info(f"Output will be written to: {linux_output_dir}")
            logger.info(f"Output base name: {output_base}")

            # Call FileTypeImporter's import_robot method
            # This returns ImportResult with success/paths/warnings
            # Extract xacro_args from options if provided
            xacro_args = options.get("xacro_args", None)

            result = fti.import_robot(
                file_path=linux_input_path,
                robot_name=name_prefix,
                import_mode="both",
                output_path=linux_output_dir,  # Use user's selected output directory
                xacro_args=xacro_args,  # Pass XACRO arguments if provided
            )

            self._update_progress(request_id, 90.0, "Finalizing...")

        except TimeoutError as e:
            sig.alarm(0)
            sig.signal(sig.SIGALRM, old_handler)
            # Log timeout to storage
            duration_ms = int((time.time() - conversion_start_time) * 1000)
            self._storage.log_conversion_failed(
                record_id=record_id,
                request_id=request_id,
                input_path=input_path,
                input_format=input_format,
                error_code=str(ErrorCode.TIMEOUT.value),
                error_message=str(e),
                duration_ms=duration_ms,
            )
            self._send_error(request_id, ErrorCode.TIMEOUT, str(e))
            return
        finally:
            sig.alarm(0)
            sig.signal(sig.SIGALRM, old_handler)

        # Check result
        if not result.success:
            # Log failure to storage
            duration_ms = int((time.time() - conversion_start_time) * 1000)
            self._storage.log_conversion_failed(
                record_id=record_id,
                request_id=request_id,
                input_path=input_path,
                input_format=input_format,
                error_code=str(ErrorCode.USD_GENERATION_FAILED.value),
                error_message=result.error_message or "Conversion failed",
                duration_ms=duration_ms,
            )
            self._send_error(
                request_id,
                ErrorCode.USD_GENERATION_FAILED,
                result.error_message or "Conversion failed",
            )
            return

        # Build output file info from ImportResult
        from IPC.ipc_protocol import OutputFile

        outputs = {}

        # ImportResult has assembly_path and parts_paths
        if hasattr(result, "assembly_path") and result.assembly_path:
            linux_path = result.assembly_path
            windows_path = self.path_handler.to_windows_path(linux_path)
            size = os.path.getsize(linux_path) if os.path.exists(linux_path) else 0
            outputs["primary"] = OutputFile(linux_path, windows_path, size)

        if hasattr(result, "parts_paths") and result.parts_paths:
            for i, part_path in enumerate(result.parts_paths):
                if os.path.exists(part_path):
                    windows_path = self.path_handler.to_windows_path(part_path)
                    size = os.path.getsize(part_path)
                    outputs[f"part_{i}"] = OutputFile(part_path, windows_path, size)

        # Build metadata from ImportResult
        metadata = {
            "robot_name": name_prefix,
            "input_format": ext,
            "warnings": result.warnings if hasattr(result, "warnings") else [],
            "version": "3.0",  # FTI v3.0 with submechanisms and enhanced joints
        }

        if hasattr(result, "parts_count"):
            metadata["parts_count"] = result.parts_count
        if hasattr(result, "content_path"):
            metadata["content_path"] = result.content_path

        # NEW: Include hierarchy JSON path for UE5 assembler
        if hasattr(result, "hierarchy_path") and result.hierarchy_path:
            metadata["hierarchy_path"] = result.hierarchy_path
            windows_hierarchy = self.path_handler.to_windows_path(result.hierarchy_path)
            metadata["hierarchy_path_windows"] = windows_hierarchy

        # NEW: Include submechanism info for GUI display
        if hasattr(result, "submechanisms") and result.submechanisms:
            sm_data = result.submechanisms
            metadata["submechanisms"] = {
                "available": sm_data.get("available", False),
                "robot_type": sm_data.get("robot_type", "unknown"),
                "count": len(sm_data.get("submechanisms", [])),
                "names": [sm.get("name") for sm in sm_data.get("submechanisms", [])],
            }

        # NEW: Include IK availability for GUI
        if hasattr(result, "ik_available"):
            metadata["ik_available"] = result.ik_available

        # Log successful conversion to storage
        duration_ms = int((time.time() - conversion_start_time) * 1000)
        primary_output = outputs.get("primary")
        output_path_for_log = primary_output.linux_path if primary_output else linux_output_dir

        self._storage.log_conversion_complete(
            record_id=record_id,
            request_id=request_id,
            input_path=input_path,
            input_format=input_format,
            output_path=output_path_for_log,
            output_format=".usd",
            duration_ms=duration_ms,
            metadata=metadata,
        )

        # Send success response
        self._update_progress(request_id, 100.0, "Complete!")

        response = IPCResponse.create_success(
            request_id=request_id,
            outputs=outputs,
            metadata=metadata,
            duration_ms=duration_ms,
        )

        write_response(self.paths, response)

    def _process_xacro_to_urdf(self, request: IPCRequest, timeout_ms: int):
        """
        Process XACRO to URDF conversion request.

        This is called from UE5 plugin for standalone XACRO processing.
        It resolves $(find package) and other ROS2 substitution args.

        Args:
            request: The request with source_file and output_file
            timeout_ms: Timeout in milliseconds
        """
        request_id = request.request_id

        # Update progress
        self._update_progress(request_id, 0.0, "Starting XACRO conversion...")

        # Get paths from request - may come in different fields
        source_file = (
            request.input.get("path", "")
            or request.input.get("source_file", "")
            or request.data.get("source_file", "")
        )
        output_file = (
            request.output.get("path", "")
            or request.output.get("output_file", "")
            or request.data.get("output_file", "")
        )

        if not source_file:
            self._send_error(request_id, ErrorCode.MISSING_FIELD, "source_file is required")
            return

        # Convert paths
        linux_source = self.path_handler.to_linux_path(source_file)
        linux_output = self.path_handler.to_linux_path(output_file) if output_file else None

        # Default output path
        if not linux_output:
            linux_output = os.path.splitext(linux_source)[0] + ".urdf"

        logger.info(f"XACRO conversion: {linux_source} -> {linux_output}")

        if not os.path.exists(linux_source):
            self._send_error(
                request_id,
                ErrorCode.FILE_NOT_FOUND,
                f"XACRO file not found: {source_file}",
            )
            return

        self._update_progress(request_id, 10.0, "Finding package root...")

        # Find package root for include resolution
        package_path = self._find_package_root(linux_source)

        self._update_progress(request_id, 20.0, "Processing XACRO...")

        try:
            import subprocess

            # Get XACRO args from options
            options = request.options or {}
            xacro_args = options.get("xacro_args", {})

            # Build xacro args string (key:=value pairs)
            xacro_args_str = ""
            if xacro_args:
                args_list = [f"{k}:={v}" for k, v in xacro_args.items()]
                xacro_args_str = " " + " ".join(args_list)
                logger.info(f"XACRO args: {xacro_args_str}")

            # Build xacro command with ROS2 environment
            # Source ROS2 first to get ament_index_python
            xacro_cmd = [
                "bash",
                "-c",
                f"source /opt/ros/humble/setup.bash && "
                f'xacro "{linux_source}"{xacro_args_str} > "{linux_output}"',
            ]

            logger.info(f"Running: {' '.join(xacro_cmd)}")

            result = subprocess.run(
                xacro_cmd,
                capture_output=True,
                text=True,
                timeout=timeout_ms // 1000 if timeout_ms else 60,
                cwd=package_path or os.path.dirname(linux_source),
            )

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "Unknown error"
                logger.error(f"XACRO failed: {error_msg}")
                self._send_error(
                    request_id,
                    ErrorCode.XACRO_EXPANSION_FAILED,
                    f"XACRO processing failed: {error_msg}",
                )
                return

            # Verify output exists
            if not os.path.exists(linux_output):
                self._send_error(
                    request_id,
                    ErrorCode.XACRO_EXPANSION_FAILED,
                    "XACRO produced no output file",
                )
                return

            self._update_progress(request_id, 90.0, "Conversion complete!")

            # Convert output path back to Windows format for response
            windows_output = self.path_handler.to_windows_path(linux_output)

            # Build success response - use dict directly for UE5 compatibility
            outputs = {
                "urdf": {
                    "linux_path": linux_output,
                    "windows_path": windows_output,
                    "size_bytes": os.path.getsize(linux_output),
                    "format": "urdf",
                }
            }

            self._update_progress(request_id, 100.0, "Complete!")

            response = IPCResponse.create_success(
                request_id=request_id,
                outputs=outputs,
                metadata={"source_format": "xacro"},
                duration_ms=int((time.time() - self._start_time) * 1000),
            )

            # Also write response as simple JSON for UE5 compatibility
            simple_response = {
                "success": True,
                "output_file": linux_output,
                "windows_path": windows_output,
                "request_id": request_id,
            }

            response_file = self.paths.responses_dir / f"{request_id}.response.json"
            with open(response_file, "w") as f:
                import json

                json.dump(simple_response, f)

            logger.info(f"XACRO conversion successful: {linux_output}")

        except subprocess.TimeoutExpired:
            self._send_error(
                request_id,
                ErrorCode.TIMEOUT,
                f"XACRO processing timed out after {timeout_ms}ms",
            )
        except Exception as e:
            logger.error(f"XACRO conversion error: {e}")
            self._send_error(request_id, ErrorCode.XACRO_EXPANSION_FAILED, str(e))

    def _process_prepare_for_ue5(self, request: IPCRequest, timeout_ms: int):
        """
        Process a 'prepare_for_ue5' request.

        This adds hierarchy assembly metadata to an existing USD file
        so it can be properly reconstructed in UE5 after import.

        Args:
            request: The prepare request
            timeout_ms: Timeout in milliseconds
        """
        request_id = request.request_id

        # Update progress: Starting
        self._update_progress(request_id, 0.0, "Preparing USD for UE5...")

        # Get input path
        input_path = request.input.get("path", "")
        linux_input_path = self.path_handler.to_linux_path(input_path)

        if not os.path.exists(linux_input_path):
            self._send_error(request_id, ErrorCode.FILE_NOT_FOUND, f"File not found: {input_path}")
            return

        try:
            # Update progress
            self._update_progress(request_id, 20.0, "Reading USD metadata...")

            # For now, we'll add assembly metadata using our UE5 hierarchy module
            from UE5.ue5_hierarchy_assembler import RobotHierarchy

            self._update_progress(request_id, 50.0, "Adding hierarchy metadata...")

            # TODO: Parse USD file and add customData for hierarchy
            # For now, we just verify the file and generate assembly script

            # Generate assembly Python script alongside the USD
            output_dir = os.path.dirname(linux_input_path)
            base_name = os.path.splitext(os.path.basename(linux_input_path))[0]
            script_path = os.path.join(output_dir, f"{base_name}_assembly.py")

            assembly_script = self._generate_assembly_script(base_name, linux_input_path)

            with open(script_path, "w") as f:
                f.write(assembly_script)

            self._update_progress(request_id, 90.0, "Finalizing...")

            # Convert paths back to Windows for response
            windows_output = self.path_handler.to_windows_path(linux_input_path)
            windows_script = self.path_handler.to_windows_path(script_path)

            # Create success response
            response = IPCResponse.create_success(
                request_id=request_id,
                outputs={
                    "usd_file": windows_output,
                    "assembly_script": windows_script,
                },
                metadata={
                    "prepared_for_ue5": True,
                    "robot_name": base_name,
                },
                duration_ms=int((time.time() - self._start_time) * 1000),
            )

            write_response(self.paths, response)
            logger.info(f"Prepared USD for UE5: {windows_output}")

        except Exception as e:
            logger.error(f"Error preparing for UE5: {e}")
            logger.error(traceback.format_exc())
            self._send_error(request_id, ErrorCode.INTERNAL_ERROR, str(e))

    def _process_convert_and_prepare(self, request: IPCRequest, timeout_ms: int):
        """
        Process a 'convert_and_prepare' request.

        Converts URDF/XACRO to USD and adds UE5 assembly metadata.

        Args:
            request: The convert and prepare request
            timeout_ms: Timeout in milliseconds
        """
        request_id = request.request_id

        # Update progress: Starting
        self._update_progress(request_id, 0.0, "Converting and preparing for UE5...")

        # First, do the normal conversion
        self._process_conversion(request, timeout_ms)

        # If conversion succeeded, also generate assembly script
        response_path = os.path.join(self.paths.responses_dir, f"{request_id}.response.json")

        if os.path.exists(response_path):
            try:
                with open(response_path, "r") as f:
                    response = json.load(f)

                if response.get("success"):
                    output_file = response.get("outputs", {}).get("primary")
                    if output_file:
                        linux_output = self.path_handler.to_linux_path(output_file)
                        output_dir = os.path.dirname(linux_output)
                        base_name = os.path.splitext(os.path.basename(linux_output))[0]
                        script_path = os.path.join(output_dir, f"{base_name}_assembly.py")

                        assembly_script = self._generate_assembly_script(base_name, linux_output)

                        with open(script_path, "w") as f:
                            f.write(assembly_script)

                        # Update response with assembly script
                        response["outputs"]["assembly_script"] = self.path_handler.to_windows_path(
                            script_path
                        )
                        response["metadata"]["prepared_for_ue5"] = True

                        with open(response_path, "w") as f:
                            json.dump(response, f, indent=2)

                        logger.info(f"Generated assembly script: {script_path}")
            except Exception as e:
                logger.warning(f"Could not add assembly script: {e}")

    def _generate_assembly_script(self, robot_name: str, usd_path: str) -> str:
        """
        Generate a Python script for UE5 to assemble the robot hierarchy.

        Args:
            robot_name: Name of the robot
            usd_path: Path to the USD file

        Returns:
            Python script as string
        """
        script = f'''"""
ROA Robot Assembly Script for UE5
Robot: {robot_name}
USD: {usd_path}

This script reconstructs the robot hierarchy after USD import in UE5.
Run this in UE5 Python console or via Execute Python Script.

Usage in UE5:
    1. Import the USD file using Interchange
    2. Run this script to reassemble the hierarchy
"""

import unreal

def assemble_robot():
    """Assemble {robot_name} from imported USD parts."""
    
    # Get editor subsystem
    editor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    
    # Find all actors that start with our robot name
    robot_name = "{robot_name}"
    all_actors = editor_subsystem.get_all_level_actors()
    
    robot_actors = [a for a in all_actors if robot_name.lower() in a.get_name().lower()]
    
    if not robot_actors:
        unreal.log_error(f"No actors found for robot: {{robot_name}}")
        return False
    
    unreal.log(f"Found {{len(robot_actors)}} actors for {{robot_name}}")
    
    # Find root actor (usually base_link)
    root_actor = None
    for actor in robot_actors:
        name = actor.get_name().lower()
        if 'base_link' in name or 'base' in name:
            root_actor = actor
            break
    
    if not root_actor:
        root_actor = robot_actors[0]
        unreal.log_warning(f"No base_link found, using {{root_actor.get_name()}} as root")
    
    unreal.log(f"Root actor: {{root_actor.get_name()}}")
    
    # TODO: Parse hierarchy from USD customData and re-parent actors
    # For now, just log success
    unreal.log(f"Robot {{robot_name}} assembly complete!")
    return True

if __name__ == "__main__":
    assemble_robot()
'''
        return script

    def _process_prepare_for_ue5(self, request: IPCRequest, timeout_ms: int):
        """
        Process a 'prepare_for_ue5' request.

        This adds hierarchy assembly metadata to an existing USD file
        so it can be properly reconstructed in UE5 after import.

        Args:
            request: The prepare request
            timeout_ms: Timeout in milliseconds
        """
        request_id = request.request_id

        # Update progress: Starting
        self._update_progress(request_id, 0.0, "Preparing USD for UE5...")

        # Get input path
        input_path = request.input.get("path", "")
        linux_input_path = self.path_handler.to_linux_path(input_path)

        if not os.path.exists(linux_input_path):
            self._send_error(request_id, ErrorCode.FILE_NOT_FOUND, f"File not found: {input_path}")
            return

        try:
            # Update progress
            self._update_progress(request_id, 20.0, "Reading USD metadata...")

            # For now, we'll add assembly metadata using our UE5 hierarchy module
            from UE5.ue5_hierarchy_assembler import RobotHierarchy

            self._update_progress(request_id, 50.0, "Adding hierarchy metadata...")

            # TODO: Parse USD file and add customData for hierarchy
            # For now, we just verify the file and generate assembly script

            # Generate assembly Python script alongside the USD
            output_dir = os.path.dirname(linux_input_path)
            base_name = os.path.splitext(os.path.basename(linux_input_path))[0]
            script_path = os.path.join(output_dir, f"{base_name}_assembly.py")

            assembly_script = self._generate_assembly_script(base_name, linux_input_path)

            with open(script_path, "w") as f:
                f.write(assembly_script)

            self._update_progress(request_id, 90.0, "Finalizing...")

            # Convert paths back to Windows for response
            windows_output = self.path_handler.to_windows_path(linux_input_path)
            windows_script = self.path_handler.to_windows_path(script_path)

            # Create success response
            response = IPCResponse.create_success(
                request_id=request_id,
                outputs={
                    "usd_file": windows_output,
                    "assembly_script": windows_script,
                },
                metadata={
                    "prepared_for_ue5": True,
                    "robot_name": base_name,
                },
                duration_ms=int((time.time() - self._start_time) * 1000),
            )

            write_response(self.paths, response)
            logger.info(f"Prepared USD for UE5: {windows_output}")

        except Exception as e:
            logger.error(f"Error preparing for UE5: {e}")
            logger.error(traceback.format_exc())
            self._send_error(request_id, ErrorCode.INTERNAL_ERROR, str(e))

    def _process_convert_and_prepare(self, request: IPCRequest, timeout_ms: int):
        """
        Process a 'convert_and_prepare' request.

        Converts URDF/XACRO to USD and adds UE5 assembly metadata.

        Args:
            request: The convert and prepare request
            timeout_ms: Timeout in milliseconds
        """
        request_id = request.request_id

        # Update progress: Starting
        self._update_progress(request_id, 0.0, "Converting and preparing for UE5...")

        # First, do the normal conversion
        self._process_conversion(request, timeout_ms)

        # If conversion succeeded, also generate assembly script
        response_path = os.path.join(self.paths.responses_dir, f"{request_id}.response.json")

        if os.path.exists(response_path):
            try:
                with open(response_path, "r") as f:
                    response = json.load(f)

                if response.get("success"):
                    output_file = response.get("outputs", {}).get("primary")
                    if output_file:
                        linux_output = self.path_handler.to_linux_path(output_file)
                        output_dir = os.path.dirname(linux_output)
                        base_name = os.path.splitext(os.path.basename(linux_output))[0]
                        script_path = os.path.join(output_dir, f"{base_name}_assembly.py")

                        assembly_script = self._generate_assembly_script(base_name, linux_output)

                        with open(script_path, "w") as f:
                            f.write(assembly_script)

                        # Update response with assembly script
                        response["outputs"]["assembly_script"] = self.path_handler.to_windows_path(
                            script_path
                        )
                        response["metadata"]["prepared_for_ue5"] = True

                        with open(response_path, "w") as f:
                            json.dump(response, f, indent=2)

                        logger.info(f"Generated assembly script: {script_path}")
            except Exception as e:
                logger.warning(f"Could not add assembly script: {e}")

    def _generate_assembly_script(self, robot_name: str, usd_path: str) -> str:
        """
        Generate a Python script for UE5 to assemble the robot hierarchy.

        Args:
            robot_name: Name of the robot
            usd_path: Path to the USD file

        Returns:
            Python script as string
        """
        script = f'''"""
ROA Robot Assembly Script for UE5
Robot: {robot_name}
USD: {usd_path}

This script reconstructs the robot hierarchy after USD import in UE5.
Run this in UE5 Python console or via Execute Python Script.

Usage in UE5:
    1. Import the USD file using Interchange
    2. Run this script to reassemble the hierarchy
"""

import unreal

def assemble_robot():
    """Assemble {robot_name} from imported USD parts."""
    
    # Get editor subsystem
    editor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    
    # Find all actors that start with our robot name
    robot_name = "{robot_name}"
    all_actors = editor_subsystem.get_all_level_actors()
    
    robot_actors = [a for a in all_actors if robot_name.lower() in a.get_name().lower()]
    
    if not robot_actors:
        unreal.log_error(f"No actors found for robot: {{robot_name}}")
        return False
    
    unreal.log(f"Found {{len(robot_actors)}} actors for {{robot_name}}")
    
    # Find root actor (usually base_link)
    root_actor = None
    for actor in robot_actors:
        name = actor.get_name().lower()
        if 'base_link' in name or 'base' in name:
            root_actor = actor
            break
    
    if not root_actor:
        root_actor = robot_actors[0]
        unreal.log_warning(f"No base_link found, using {{root_actor.get_name()}} as root")
    
    unreal.log(f"Root actor: {{root_actor.get_name()}}")
    
    # TODO: Parse hierarchy from USD customData and re-parent actors
    # For now, just log success
    unreal.log(f"Robot {{robot_name}} assembly complete!")
    return True

if __name__ == "__main__":
    assemble_robot()
'''
        return script

    def _process_validation(self, request: IPCRequest):
        """Process a validation request."""
        # TODO: Implement file validation
        request_id = request.request_id

        response = IPCResponse.create_success(
            request_id=request_id, outputs={}, metadata={"valid": True}, duration_ms=0
        )

        write_response(self.paths, response)

    def _process_health_check(self, request: IPCRequest):
        """Process a health check request."""
        request_id = request.request_id

        response = IPCResponse.create_success(
            request_id=request_id,
            outputs={},
            metadata={
                "status": "healthy",
                "uptime_seconds": (time.time() - self._start_time if self._start_time else 0),
                "processed_count": self._processed_count,
                "failed_count": self._failed_count,
                "version": PROTOCOL_VERSION,
            },
            duration_ms=0,
        )

        write_response(self.paths, response)

    def _send_error(
        self,
        request_id: str,
        error_code: ErrorCode,
        message: str,
        details: Optional[Dict] = None,
    ):
        """Send an error response."""
        response = IPCResponse.create_error(
            request_id=request_id,
            error_code=error_code,
            message=message,
            details=details,
        )

        write_response(self.paths, response)

    def _update_progress(self, request_id: str, percent: float, stage: str):
        """Update progress for a request."""
        progress = IPCProgress(request_id=request_id, percent=percent, stage=stage)
        write_progress(self.paths, progress)

    def _cleanup_stale_responses(self):
        """
        Clean up stale failed responses from previous sessions.
        This prevents 'stuck' behavior when retrying failed conversions.
        """
        try:
            responses_dir = self.paths.responses_dir
            if not responses_dir.exists():
                return

            stale_count = 0
            for response_file in responses_dir.glob("*.response.json"):
                try:
                    with open(response_file, "r") as f:
                        response = json.load(f)

                    # Remove failed responses older than 5 minutes
                    completed_at = response.get("completed_at", "")
                    if completed_at:
                        from datetime import datetime, timezone

                        completed_time = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
                        age_seconds = (datetime.now(timezone.utc) - completed_time).total_seconds()

                        # Remove failed responses or old successful responses
                        is_failed = not response.get("success", False)
                        is_old = age_seconds > 300  # 5 minutes

                        if is_failed or is_old:
                            response_file.unlink()
                            stale_count += 1
                except Exception as e:
                    logger.debug(f"Could not process {response_file}: {e}")

            if stale_count > 0:
                logger.info(f"Cleaned up {stale_count} stale response files")
        except Exception as e:
            logger.warning(f"Error cleaning stale responses: {e}")

    def _write_status(self):
        """Write service status file with client information."""
        try:
            status = ServiceStatus(
                status="running",
                pid=os.getpid(),
                pending_requests=list(self._pending_requests),
                processed_count=self._processed_count,
                failed_count=self._failed_count,
                uptime_seconds=(time.time() - self._start_time if self._start_time else 0),
            )

            # Add client lifecycle info to status
            status_dict = json.loads(status.to_json())
            status_dict["clients"] = list(self._active_clients.keys())
            status_dict["client_count"] = len(self._active_clients)
            status_dict["auto_shutdown_enabled"] = self.config.auto_shutdown_enabled
            status_dict["auto_shutdown_delay"] = self.config.auto_shutdown_delay

            if self._no_clients_since:
                remaining = self.config.auto_shutdown_delay - (time.time() - self._no_clients_since)
                status_dict["shutdown_in_seconds"] = max(0, remaining)

            with open(self.paths.service_status_file, "w") as f:
                f.write(json.dumps(status_dict, indent=2))
        except Exception as e:
            logger.error(f"Failed to write status: {e}")

    def _heartbeat_loop(self):
        """
        Heartbeat thread loop.

        Updates service.status every 5 seconds.
        Implements: Gap 3.3 fix
        """
        while self._running and not self._shutdown_event.wait(self.config.heartbeat_interval):
            self._write_status()

        logger.debug("Heartbeat thread exiting")

    def _client_monitor_loop(self):
        """
        Client monitor thread loop.

        Scans for client heartbeat files and manages auto-shutdown.

        Lifecycle:
        1. Clients write heartbeat files to heartbeats/ folder
        2. Service scans for fresh heartbeats
        3. If no fresh heartbeats for auto_shutdown_delay, service shuts down
        """
        logger.info("Client monitor started")
        logger.info(
            f"  Auto-shutdown: {'enabled' if self.config.auto_shutdown_enabled else 'disabled'}"
        )
        logger.info(f"  Client timeout: {self.config.client_heartbeat_timeout}s")
        logger.info(f"  Shutdown delay: {self.config.auto_shutdown_delay}s")

        while self._running and not self._shutdown_event.wait(self.config.client_check_interval):
            try:
                self._scan_client_heartbeats()
                self._check_auto_shutdown()
            except Exception as e:
                logger.error(f"Client monitor error: {e}")

        logger.debug("Client monitor thread exiting")

    def _scan_client_heartbeats(self):
        """
        Scan for client heartbeat files.

        Heartbeat file format: heartbeats/{client_id}.heartbeat.json
        Content: {"client_id": "...", "timestamp": 1234567890.123, "type": "ue5_plugin|roa_app"}
        """
        heartbeats_dir = self.paths._base / "heartbeats"

        if not heartbeats_dir.exists():
            # Create heartbeats directory
            heartbeats_dir.mkdir(parents=True, exist_ok=True)
            return

        now = time.time()
        active_clients = {}

        for hb_file in heartbeats_dir.iterdir():
            if not hb_file.name.endswith(".heartbeat.json"):
                continue

            try:
                with open(hb_file, "r") as f:
                    data = json.load(f)

                client_id = data.get("client_id", hb_file.stem)
                timestamp = data.get("timestamp", 0)
                client_type = data.get("type", "unknown")

                # ROBUSTNESS: Validate timestamp is a valid Unix epoch
                # If timestamp looks like app uptime (< year 2000), try to use file mtime instead
                # Valid Unix epoch for 2020+: > 1577836800 (Jan 1, 2020)
                if timestamp < 1577836800:
                    # Timestamp is invalid (probably app uptime instead of Unix epoch)
                    # Fall back to file modification time
                    try:
                        file_mtime = hb_file.stat().st_mtime
                        logger.warning(
                            f"Invalid timestamp {timestamp} for {client_id}, using file mtime {file_mtime}"
                        )
                        timestamp = file_mtime
                    except:
                        logger.warning(f"Could not get file mtime for {hb_file}")
                        continue

                age = now - timestamp

                if age < self.config.client_heartbeat_timeout:
                    # Client is alive
                    active_clients[client_id] = timestamp
                    self._last_client_activity = max(self._last_client_activity, timestamp)

                    if client_id not in self._active_clients:
                        logger.info(f"Client connected: {client_id} (type: {client_type})")
                else:
                    # Client heartbeat is stale
                    if client_id in self._active_clients:
                        logger.info(f"Client disconnected (timeout): {client_id} (age={age:.0f}s)")

                    # Clean up old heartbeat file
                    if age > self.config.client_heartbeat_timeout * 2:
                        try:
                            hb_file.unlink()
                            logger.debug(f"Removed stale heartbeat: {hb_file.name}")
                        except:
                            pass

            except Exception as e:
                logger.debug(f"Error reading heartbeat {hb_file}: {e}")

        # Update active clients
        self._active_clients = active_clients

        # Log client count periodically
        if len(active_clients) > 0:
            logger.debug(f"Active clients: {list(active_clients.keys())}")

    def _check_auto_shutdown(self):
        """
        Check if we should auto-shutdown due to no active clients.
        """
        if not self.config.auto_shutdown_enabled:
            return

        # Don't shutdown if there are pending requests
        if self._pending_requests:
            self._no_clients_since = None
            return

        now = time.time()

        if len(self._active_clients) == 0:
            # No active clients
            if self._no_clients_since is None:
                self._no_clients_since = now
                logger.info("No active clients detected, starting shutdown timer...")
            else:
                no_client_duration = now - self._no_clients_since
                remaining = self.config.auto_shutdown_delay - no_client_duration

                if remaining <= 0:
                    logger.info("=" * 60)
                    logger.info(
                        "AUTO-SHUTDOWN: No clients for %.0f seconds"
                        % self.config.auto_shutdown_delay
                    )
                    logger.info("Service will now shut down.")
                    logger.info("To keep service running, ensure a client sends heartbeats.")
                    logger.info("=" * 60)
                    self.stop()
                elif int(remaining) % 10 == 0 and int(remaining) > 0:
                    logger.info(f"Auto-shutdown in {int(remaining)} seconds (no active clients)")
        else:
            # We have active clients, reset timer
            if self._no_clients_since is not None:
                logger.info("Client activity detected, cancelling shutdown timer")
            self._no_clients_since = None

    def _cleanup_loop(self):
        """
        Cleanup thread loop.

        Removes old response files and orphaned files.
        """
        while self._running and not self._shutdown_event.wait(self.config.cleanup_interval):
            try:
                self._cleanup_old_files()
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

        logger.debug("Cleanup thread exiting")

    def _cleanup_old_files(self):
        """Clean up old response files."""
        now = time.time()
        ttl = self.config.response_ttl_seconds

        for folder in [self.paths.responses_dir, self.paths.progress_dir]:
            if not folder.exists():
                continue

            for f in folder.iterdir():
                try:
                    age = now - f.stat().st_mtime
                    if age > ttl:
                        f.unlink()
                        logger.debug(f"Cleaned up old file: {f}")
                except Exception as e:
                    logger.warning(f"Could not clean up {f}: {e}")

    def _cleanup_on_shutdown(self):
        """
        Cleanup on shutdown.

        Implements: Gap 3.2 fix - graceful shutdown
        """
        logger.info("Cleaning up on shutdown...")

        # Write final status
        try:
            status = ServiceStatus(
                status="stopped",
                pid=os.getpid(),
                pending_requests=list(self._pending_requests),
                processed_count=self._processed_count,
                failed_count=self._failed_count,
                uptime_seconds=(time.time() - self._start_time if self._start_time else 0),
            )

            with open(self.paths.service_status_file, "w") as f:
                f.write(status.to_json())
        except:
            pass

        # Log pending requests
        if self._pending_requests:
            logger.warning(f"Shutting down with {len(self._pending_requests)} pending requests:")
            for req_id in self._pending_requests:
                logger.warning(f"  - {req_id}")

        # Release lock
        self._release_lock()

        logger.info("Service stopped.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="ROA IPC Service - File-Based IPC for URDF to USD conversion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Start with default settings
    python roa_ipc_service.py
    
    # Start with custom IPC path
    python roa_ipc_service.py --ipc-path "D:\\MyROA\\.ipc"
    
    # Debug mode
    python roa_ipc_service.py --debug
    
    # Log to file
    python roa_ipc_service.py --log-file /var/log/roa-ipc.log
""",
    )

    parser.add_argument(
        "--ipc-path", default=r"D:\ROA\.ipc", help="Path to IPC folder (Windows format)"
    )

    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    parser.add_argument("--log-file", help="Log to file instead of stdout")

    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.1,
        help="Base polling interval in seconds (default: 0.1)",
    )

    parser.add_argument(
        "--no-auto-shutdown",
        action="store_true",
        help="Disable auto-shutdown when no clients are connected",
    )

    parser.add_argument(
        "--auto-shutdown-delay",
        type=float,
        default=60.0,
        help="Seconds to wait before auto-shutdown when no clients (default: 60)",
    )

    parser.add_argument(
        "--version", action="version", version=f"ROA IPC Service v{PROTOCOL_VERSION}"
    )

    args = parser.parse_args()

    # Setup logging
    global logger
    logger = setup_logging(debug=args.debug, log_file=args.log_file)

    # Create config
    config = ServiceConfig(
        ipc_path=args.ipc_path,
        poll_interval_active=args.poll_interval,
        auto_shutdown_enabled=not args.no_auto_shutdown,
        auto_shutdown_delay=args.auto_shutdown_delay,
    )

    # Create and start service
    service = ROAIPCService(config)

    try:
        service.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        service.stop()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
