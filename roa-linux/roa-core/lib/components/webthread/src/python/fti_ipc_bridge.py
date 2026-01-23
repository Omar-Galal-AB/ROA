#!/usr/bin/env python3
"""
FTI IPC Bridge - Connects Webthread GUI to FTI IPC Service

This bridge provides:
1. Request submission to IPC service
2. Progress monitoring with callbacks
3. Response handling
4. Service health checking

Architecture:
    Webthread GUI ──► FTI IPC Bridge ──► IPC Folder ──► FTI IPC Service
                          │                                    │
                          └──────── Progress Updates ──────────┘
"""

import json
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class ConversionState(Enum):
    """State of a conversion request"""

    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ConversionProgress:
    """Progress information for a conversion"""

    request_id: str
    percent: float = 0.0
    stage: str = "pending"
    message: str = ""
    state: ConversionState = ConversionState.PENDING
    started_at: float = 0.0
    updated_at: float = 0.0

    def elapsed_seconds(self) -> float:
        if self.started_at == 0:
            return 0
        return time.time() - self.started_at


@dataclass
class ConversionResult:
    """Result of a completed conversion"""

    request_id: str
    success: bool
    output_file: Optional[str] = None
    error: Optional[str] = None
    robot_name: Optional[str] = None
    link_count: int = 0
    joint_count: int = 0
    mesh_count: int = 0
    conversion_time: float = 0.0
    metadata: Dict = field(default_factory=dict)


class FTIIPCBridge:
    """
    Bridge between Webthread GUI and FTI IPC Service.

    Provides a clean interface for:
    - Submitting conversion requests
    - Monitoring progress
    - Handling completion/errors
    - Checking service health
    """

    PROTOCOL_VERSION = "1.0.0"

    def __init__(self, ipc_folder: Optional[str] = None):
        """
        Initialize the FTI IPC Bridge.

        Args:
            ipc_folder: Path to IPC folder. Auto-detects if not provided.
        """
        self.ipc_folder = ipc_folder or self._detect_ipc_folder()

        # Active conversions being monitored
        self._active_conversions: Dict[str, ConversionProgress] = {}

        # Callbacks
        self._progress_callbacks: List[Callable[[ConversionProgress], None]] = []
        self._completion_callbacks: List[Callable[[ConversionResult], None]] = []
        self._error_callbacks: List[Callable[[str, str], None]] = []

        # Monitoring thread
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitoring = False

        # Ensure IPC folders exist
        self._ensure_folders()

    def _detect_ipc_folder(self) -> str:
        """Auto-detect IPC folder location"""
        # Check Windows-accessible path first (for WSL)
        if os.path.exists("/mnt/d/ROA/.ipc"):
            return "/mnt/d/ROA/.ipc"
        if os.path.exists("/mnt/c/ROA/.ipc"):
            return "/mnt/c/ROA/.ipc"

        # Fall back to home directory
        return os.path.expanduser("~/.roa/ipc")

    def _ensure_folders(self):
        """Ensure all required IPC folders exist"""
        folders = ["requests", "responses", "progress", "ack"]
        for folder in folders:
            os.makedirs(os.path.join(self.ipc_folder, folder), exist_ok=True)

    # ═══════════════════════════════════════════════════════════════════
    # Service Health
    # ═══════════════════════════════════════════════════════════════════

    def is_service_running(self) -> bool:
        """Check if the IPC service is running"""
        status = self.get_service_status()
        if not status:
            return False

        # Service is running if heartbeat is recent (within 10 seconds)
        last_hb = status.get("timestamp", 0)
        return (time.time() - last_hb) < 10

    def get_service_status(self) -> Optional[Dict]:
        """Get current service status"""
        status_file = os.path.join(self.ipc_folder, "service.status")

        if not os.path.exists(status_file):
            return None

        try:
            with open(status_file, "r") as f:
                return json.load(f)
        except Exception:
            return None

    def get_service_uptime(self) -> float:
        """Get service uptime in seconds"""
        status = self.get_service_status()
        if not status:
            return 0.0

        started = status.get("started_at", 0)
        if started == 0:
            return 0.0

        return time.time() - started

    # ═══════════════════════════════════════════════════════════════════
    # Request Submission
    # ═══════════════════════════════════════════════════════════════════

    def submit_conversion(
        self,
        source_file: str,
        output_format: str = "usd",
        mesh_handling: str = "embed",
        auto_assemble: bool = True,
        generate_blueprint: bool = True,
        xacro_args: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Submit a conversion request to the IPC service.

        Args:
            source_file: Path to URDF/XACRO/SDF file
            output_format: Output format (usd, usda, usdz)
            mesh_handling: Mesh handling mode (embed, reference, convert)
            auto_assemble: Auto-assemble hierarchy in UE5
            generate_blueprint: Generate UE5 Blueprint
            xacro_args: XACRO arguments (key=value pairs)
            metadata: Additional metadata

        Returns:
            Request ID for tracking
        """
        if not os.path.exists(source_file):
            raise FileNotFoundError(f"Source file not found: {source_file}")

        # Generate request ID
        request_id = str(uuid.uuid4())

        # Build request
        request = {
            "protocol_version": self.PROTOCOL_VERSION,
            "request_id": request_id,
            "timestamp": time.time(),
            "request_type": "convert",
            "source_file": os.path.abspath(source_file),
            "options": {
                "output_format": output_format.lower(),
                "mesh_handling": mesh_handling.lower(),
                "auto_assemble": auto_assemble,
                "generate_blueprint": generate_blueprint,
            },
            "metadata": metadata or {},
        }

        # Add XACRO args if provided
        if xacro_args:
            request["options"]["xacro_args"] = xacro_args

        # Atomic write to requests folder
        request_file = os.path.join(self.ipc_folder, "requests", f"{request_id}.request.json")
        tmp_file = request_file + ".tmp"

        with open(tmp_file, "w") as f:
            json.dump(request, f, indent=2)
        os.rename(tmp_file, request_file)

        # Track this conversion
        self._active_conversions[request_id] = ConversionProgress(
            request_id=request_id,
            state=ConversionState.PENDING,
            started_at=time.time(),
            updated_at=time.time(),
        )

        return request_id

    def cancel_conversion(self, request_id: str) -> bool:
        """
        Cancel a pending or in-progress conversion.

        Args:
            request_id: ID of request to cancel

        Returns:
            True if cancel request was sent
        """
        cancel_request = {
            "protocol_version": self.PROTOCOL_VERSION,
            "request_id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "request_type": "cancel",
            "target_request_id": request_id,
        }

        cancel_file = os.path.join(self.ipc_folder, "requests", f"cancel_{request_id}.request.json")

        with open(cancel_file, "w") as f:
            json.dump(cancel_request, f, indent=2)

        # Update local tracking
        if request_id in self._active_conversions:
            self._active_conversions[request_id].state = ConversionState.CANCELLED

        return True

    # ═══════════════════════════════════════════════════════════════════
    # Progress Monitoring
    # ═══════════════════════════════════════════════════════════════════

    def get_progress(self, request_id: str) -> Optional[ConversionProgress]:
        """Get current progress of a conversion"""
        progress_file = os.path.join(self.ipc_folder, "progress", f"{request_id}.progress.json")

        if not os.path.exists(progress_file):
            return self._active_conversions.get(request_id)

        try:
            with open(progress_file, "r") as f:
                data = json.load(f)

            progress = ConversionProgress(
                request_id=request_id,
                percent=data.get("percent", 0),
                stage=data.get("stage", "unknown"),
                message=data.get("message", ""),
                state=ConversionState.PROCESSING,
                started_at=data.get("started_at", 0),
                updated_at=data.get("updated_at", time.time()),
            )

            # Update local tracking
            self._active_conversions[request_id] = progress

            return progress

        except Exception:
            return self._active_conversions.get(request_id)

    def get_result(self, request_id: str) -> Optional[ConversionResult]:
        """Get result of a completed conversion"""
        response_file = os.path.join(self.ipc_folder, "responses", f"{request_id}.response.json")

        if not os.path.exists(response_file):
            return None

        try:
            with open(response_file, "r") as f:
                data = json.load(f)

            return ConversionResult(
                request_id=request_id,
                success=data.get("success", False),
                output_file=data.get("output_file"),
                error=data.get("error"),
                robot_name=data.get("robot_name"),
                link_count=data.get("link_count", 0),
                joint_count=data.get("joint_count", 0),
                mesh_count=data.get("mesh_count", 0),
                conversion_time=data.get("conversion_time", 0),
                metadata=data.get("metadata", {}),
            )

        except Exception:
            return None

    def wait_for_completion(
        self,
        request_id: str,
        timeout: float = 300,
        poll_interval: float = 0.5,
        progress_callback: Optional[Callable[[ConversionProgress], None]] = None,
    ) -> Optional[ConversionResult]:
        """
        Wait for a conversion to complete.

        Args:
            request_id: ID of request to wait for
            timeout: Maximum seconds to wait
            poll_interval: Seconds between progress checks
            progress_callback: Called with progress updates

        Returns:
            ConversionResult if completed, None if timeout
        """
        start_time = time.time()

        while (time.time() - start_time) < timeout:
            # Check for result
            result = self.get_result(request_id)
            if result:
                return result

            # Get progress
            progress = self.get_progress(request_id)
            if progress and progress_callback:
                progress_callback(progress)

            # Check for failure
            if progress and progress.state == ConversionState.FAILED:
                return ConversionResult(
                    request_id=request_id,
                    success=False,
                    error="Conversion failed",
                )

            time.sleep(poll_interval)

        return None  # Timeout

    # ═══════════════════════════════════════════════════════════════════
    # Callback Registration
    # ═══════════════════════════════════════════════════════════════════

    def on_progress(self, callback: Callable[[ConversionProgress], None]):
        """Register callback for progress updates"""
        self._progress_callbacks.append(callback)

    def on_completion(self, callback: Callable[[ConversionResult], None]):
        """Register callback for conversion completion"""
        self._completion_callbacks.append(callback)

    def on_error(self, callback: Callable[[str, str], None]):
        """Register callback for errors (request_id, error_message)"""
        self._error_callbacks.append(callback)

    # ═══════════════════════════════════════════════════════════════════
    # Background Monitoring
    # ═══════════════════════════════════════════════════════════════════

    def start_monitoring(self):
        """Start background monitoring thread"""
        if self._monitoring:
            return

        self._monitoring = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop_monitoring(self):
        """Stop background monitoring thread"""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
            self._monitor_thread = None

    def _monitor_loop(self):
        """Background loop to monitor active conversions"""
        while self._monitoring:
            for request_id in list(self._active_conversions.keys()):
                try:
                    # Check for result
                    result = self.get_result(request_id)
                    if result:
                        # Notify completion callbacks
                        for callback in self._completion_callbacks:
                            try:
                                callback(result)
                            except Exception:
                                pass

                        # Remove from active
                        del self._active_conversions[request_id]
                        continue

                    # Get progress
                    progress = self.get_progress(request_id)
                    if progress:
                        # Notify progress callbacks
                        for callback in self._progress_callbacks:
                            try:
                                callback(progress)
                            except Exception:
                                pass

                except Exception as e:
                    # Notify error callbacks
                    for callback in self._error_callbacks:
                        try:
                            callback(request_id, str(e))
                        except Exception:
                            pass

            time.sleep(0.5)

    # ═══════════════════════════════════════════════════════════════════
    # Utility Methods
    # ═══════════════════════════════════════════════════════════════════

    def get_pending_requests(self) -> List[str]:
        """Get list of pending request IDs"""
        requests_folder = os.path.join(self.ipc_folder, "requests")
        pending = []

        if os.path.exists(requests_folder):
            for f in os.listdir(requests_folder):
                if f.endswith(".request.json") and not f.startswith("cancel_"):
                    request_id = f.replace(".request.json", "")
                    # Check if not completed
                    if not self.get_result(request_id):
                        pending.append(request_id)

        return pending

    def get_completed_requests(self, limit: int = 10) -> List[ConversionResult]:
        """Get list of recently completed conversions"""
        responses_folder = os.path.join(self.ipc_folder, "responses")
        results = []

        if os.path.exists(responses_folder):
            files = sorted(
                os.listdir(responses_folder),
                key=lambda f: os.path.getmtime(os.path.join(responses_folder, f)),
                reverse=True,
            )

            for f in files[:limit]:
                if f.endswith(".response.json"):
                    request_id = f.replace(".response.json", "")
                    result = self.get_result(request_id)
                    if result:
                        results.append(result)

        return results

    def cleanup_old_files(self, max_age_hours: int = 24):
        """Clean up old IPC files"""
        now = time.time()
        max_age_seconds = max_age_hours * 3600

        for folder in ["requests", "responses", "progress", "ack"]:
            folder_path = os.path.join(self.ipc_folder, folder)
            if not os.path.exists(folder_path):
                continue

            for f in os.listdir(folder_path):
                file_path = os.path.join(folder_path, f)
                try:
                    if os.path.getmtime(file_path) < (now - max_age_seconds):
                        os.remove(file_path)
                except Exception:
                    pass


# ═══════════════════════════════════════════════════════════════════════════
# Convenience Functions
# ═══════════════════════════════════════════════════════════════════════════


def quick_convert(
    source_file: str, wait: bool = True, timeout: float = 300, **options
) -> Optional[ConversionResult]:
    """
    Quick conversion helper function.

    Args:
        source_file: Path to robot file
        wait: Wait for completion
        timeout: Max wait time in seconds
        **options: Additional conversion options

    Returns:
        ConversionResult if wait=True, else None (returns immediately)
    """
    bridge = FTIIPCBridge()

    if not bridge.is_service_running():
        raise RuntimeError("FTI IPC Service is not running")

    request_id = bridge.submit_conversion(source_file, **options)

    if not wait:
        return None

    return bridge.wait_for_completion(request_id, timeout=timeout)


if __name__ == "__main__":
    # Simple test
    bridge = FTIIPCBridge()

    print(f"IPC Folder: {bridge.ipc_folder}")
    print(f"Service Running: {bridge.is_service_running()}")

    status = bridge.get_service_status()
    if status:
        print(f"Service Status: {json.dumps(status, indent=2)}")

    pending = bridge.get_pending_requests()
    print(f"Pending Requests: {len(pending)}")

    completed = bridge.get_completed_requests()
    print(f"Completed Requests: {len(completed)}")
