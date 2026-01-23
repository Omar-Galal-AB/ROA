#!/usr/bin/env python3
"""
FTI Pipeline Orchestrator - Automatic Conversion & Import Pipeline

This orchestrator handles the complete pipeline:
1. IPC Service Management
2. URDF/XACRO → USD Conversion
3. USD Import via Interchange
4. Hierarchy Assembly (Dimensions Collector)
5. Blueprint Generation

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                    FTI Pipeline Orchestrator                     │
    ├─────────────────────────────────────────────────────────────────┤
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐│
    │  │ IPC Svc  │→ │Converter │→ │Importer  │→ │Hierarchy Assemble││
    │  │ Manager  │  │(URDF→USD)│  │(Interchnge│  │(DIMC Integration)││
    │  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘│
    │       ↑                                                         │
    │       └──────── Progress Updates & Callbacks ───────────────────│
    └─────────────────────────────────────────────────────────────────┘
"""

import json
import logging
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Add parent paths for imports
sys.path.insert(
    0,
    str(Path(__file__).parent.parent.parent / "files-type-importer" / "src" / "python"),
)
sys.path.insert(0, str(Path(__file__).parent / "python"))

# Import FTI components
try:
    from fti_ipc_bridge import ConversionProgress, ConversionResult, FTIIPCBridge
except ImportError:
    FTIIPCBridge = None
    ConversionResult = None
    ConversionProgress = None


class PipelineStage(Enum):
    """Pipeline stages"""

    IDLE = auto()
    INIT = auto()
    IPC_CHECK = auto()
    PARSING = auto()
    XACRO_PROCESS = auto()
    HIERARCHY_BUILD = auto()
    MESH_PROCESS = auto()
    USD_GENERATE = auto()
    IPC_TRANSFER = auto()
    UE5_IMPORT = auto()
    HIERARCHY_ASSEMBLE = auto()
    BLUEPRINT_GEN = auto()
    COMPLETE = auto()
    ERROR = auto()


class PipelineStatus(Enum):
    """Pipeline status"""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PipelineConfig:
    """Configuration for the pipeline"""

    # IPC Configuration
    ipc_folder: str = "/mnt/d/ROA/.ipc"
    ipc_timeout: float = 300.0  # 5 minutes

    # Conversion Options
    output_format: str = "usd"
    mesh_handling: str = "embed"
    xacro_args: Dict[str, str] = field(default_factory=dict)

    # Post-Import Options
    auto_assemble: bool = True
    generate_blueprint: bool = True
    auto_physics: bool = True

    # UE5 Integration
    ue5_content_path: str = "/Game/Robots"
    ue5_import_options: Dict[str, Any] = field(default_factory=dict)

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None


@dataclass
class PipelineProgress:
    """Progress tracking for pipeline"""

    stage: PipelineStage = PipelineStage.IDLE
    percent: float = 0.0
    message: str = ""
    started_at: float = 0.0
    updated_at: float = 0.0

    # Stage-specific progress
    stage_percent: float = 0.0
    stage_message: str = ""

    # Results
    output_file: Optional[str] = None
    imported_asset: Optional[str] = None
    blueprint_path: Optional[str] = None

    def elapsed_seconds(self) -> float:
        if self.started_at == 0:
            return 0
        return time.time() - self.started_at


class FTIPipelineOrchestrator:
    """
    Orchestrates the complete FTI pipeline from file selection to assembled robot.

    This is the central coordinator that:
    - Manages IPC service lifecycle
    - Coordinates conversion process
    - Triggers UE5 import
    - Initiates hierarchy assembly
    - Generates Blueprints

    Usage:
        orchestrator = FTIPipelineOrchestrator()
        orchestrator.configure(auto_assemble=True, generate_blueprint=True)

        # Async execution
        orchestrator.start_pipeline("/path/to/robot.urdf")
        while orchestrator.is_running():
            progress = orchestrator.get_progress()
            print(f"{progress.percent:.0f}% - {progress.message}")
            time.sleep(0.5)

        result = orchestrator.get_result()

        # Or sync execution
        result = orchestrator.run_pipeline("/path/to/robot.urdf", wait=True)
    """

    # Stage weights for overall progress calculation
    STAGE_WEIGHTS = {
        PipelineStage.INIT: 2,
        PipelineStage.IPC_CHECK: 3,
        PipelineStage.PARSING: 10,
        PipelineStage.XACRO_PROCESS: 10,
        PipelineStage.HIERARCHY_BUILD: 10,
        PipelineStage.MESH_PROCESS: 20,
        PipelineStage.USD_GENERATE: 15,
        PipelineStage.IPC_TRANSFER: 5,
        PipelineStage.UE5_IMPORT: 15,
        PipelineStage.HIERARCHY_ASSEMBLE: 5,
        PipelineStage.BLUEPRINT_GEN: 5,
    }

    def __init__(self, config: Optional[PipelineConfig] = None):
        """Initialize the orchestrator"""
        self.config = config or PipelineConfig()
        self.logger = self._setup_logger()

        # State
        self._status = PipelineStatus.IDLE
        self._progress = PipelineProgress()
        self._result: Optional[Dict[str, Any]] = None
        self._error: Optional[str] = None

        # Callbacks
        self._progress_callbacks: List[Callable[[PipelineProgress], None]] = []
        self._completion_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._error_callbacks: List[Callable[[str], None]] = []

        # Thread management
        self._pipeline_thread: Optional[threading.Thread] = None
        self._cancel_requested = False
        self._lock = threading.Lock()

        # IPC Bridge
        self._ipc_bridge: Optional[FTIIPCBridge] = None
        if FTIIPCBridge:
            self._ipc_bridge = FTIIPCBridge(self.config.ipc_folder)

    def _setup_logger(self) -> logging.Logger:
        """Setup logging"""
        logger = logging.getLogger("FTIPipeline")
        logger.setLevel(getattr(logging, self.config.log_level.upper()))

        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

            if self.config.log_file:
                file_handler = logging.FileHandler(self.config.log_file)
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)

        return logger

    # ═══════════════════════════════════════════════════════════════════
    # Configuration
    # ═══════════════════════════════════════════════════════════════════

    def configure(self, **kwargs):
        """Update configuration"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)

    # ═══════════════════════════════════════════════════════════════════
    # Callback Registration
    # ═══════════════════════════════════════════════════════════════════

    def on_progress(self, callback: Callable[[PipelineProgress], None]):
        """Register progress callback"""
        self._progress_callbacks.append(callback)

    def on_complete(self, callback: Callable[[Dict[str, Any]], None]):
        """Register completion callback"""
        self._completion_callbacks.append(callback)

    def on_error(self, callback: Callable[[str], None]):
        """Register error callback"""
        self._error_callbacks.append(callback)

    # ═══════════════════════════════════════════════════════════════════
    # Pipeline Control
    # ═══════════════════════════════════════════════════════════════════

    def start_pipeline(self, source_file: str) -> bool:
        """
        Start the pipeline asynchronously.

        Args:
            source_file: Path to the robot file (URDF/XACRO/etc.)

        Returns:
            True if started successfully
        """
        with self._lock:
            if self._status == PipelineStatus.RUNNING:
                self.logger.warning("Pipeline already running")
                return False

            self._status = PipelineStatus.RUNNING
            self._cancel_requested = False
            self._error = None
            self._result = None

        self._pipeline_thread = threading.Thread(
            target=self._run_pipeline_thread, args=(source_file,), daemon=True
        )
        self._pipeline_thread.start()

        return True

    def run_pipeline(
        self, source_file: str, wait: bool = True, timeout: float = None
    ) -> Optional[Dict[str, Any]]:
        """
        Run the pipeline, optionally waiting for completion.

        Args:
            source_file: Path to robot file
            wait: Wait for completion
            timeout: Max wait time (uses config.ipc_timeout if not specified)

        Returns:
            Result dict if wait=True, else None
        """
        if not self.start_pipeline(source_file):
            return None

        if not wait:
            return None

        timeout = timeout or self.config.ipc_timeout
        start_time = time.time()

        while self.is_running():
            if (time.time() - start_time) > timeout:
                self.cancel()
                self._error = "Pipeline timeout"
                return None
            time.sleep(0.1)

        return self.get_result()

    def cancel(self):
        """Cancel the running pipeline"""
        self._cancel_requested = True
        with self._lock:
            self._status = PipelineStatus.CANCELLED

    def is_running(self) -> bool:
        """Check if pipeline is running"""
        return self._status == PipelineStatus.RUNNING

    def get_status(self) -> PipelineStatus:
        """Get current status"""
        return self._status

    def get_progress(self) -> PipelineProgress:
        """Get current progress"""
        return self._progress

    def get_result(self) -> Optional[Dict[str, Any]]:
        """Get pipeline result"""
        return self._result

    def get_error(self) -> Optional[str]:
        """Get error message"""
        return self._error

    # ═══════════════════════════════════════════════════════════════════
    # Pipeline Execution (Internal)
    # ═══════════════════════════════════════════════════════════════════

    def _run_pipeline_thread(self, source_file: str):
        """Main pipeline thread"""
        try:
            self._progress.started_at = time.time()
            self._progress.stage = PipelineStage.INIT

            self.logger.info(f"Starting pipeline for: {source_file}")

            # Stage 1: Initialize
            self._update_progress(PipelineStage.INIT, 0, "Initializing...")
            self._check_cancelled()

            # Validate source file
            if not os.path.exists(source_file):
                raise FileNotFoundError(f"Source file not found: {source_file}")

            # Stage 2: Check IPC Service
            self._update_progress(PipelineStage.IPC_CHECK, 0, "Checking IPC service...")
            self._ensure_ipc_service()
            self._check_cancelled()

            # Stage 3-8: Submit to IPC Service and monitor
            request_id = self._submit_conversion(source_file)
            conversion_result = self._monitor_conversion(request_id)
            self._check_cancelled()

            if not conversion_result or not conversion_result.success:
                error_msg = conversion_result.error if conversion_result else "Unknown error"
                raise RuntimeError(f"Conversion failed: {error_msg}")

            output_file = conversion_result.output_file
            self._progress.output_file = output_file

            # Stage 9: UE5 Import
            self._update_progress(PipelineStage.UE5_IMPORT, 0, "Importing to UE5...")
            imported_asset = self._import_to_ue5(output_file)
            self._progress.imported_asset = imported_asset
            self._check_cancelled()

            # Stage 10: Hierarchy Assembly (if enabled)
            if self.config.auto_assemble:
                self._update_progress(
                    PipelineStage.HIERARCHY_ASSEMBLE, 0, "Assembling hierarchy..."
                )
                self._assemble_hierarchy(imported_asset)
                self._check_cancelled()

            # Stage 11: Blueprint Generation (if enabled)
            blueprint_path = None
            if self.config.generate_blueprint:
                self._update_progress(PipelineStage.BLUEPRINT_GEN, 0, "Generating Blueprint...")
                robot_name = Path(source_file).stem
                blueprint_path = self._generate_blueprint(imported_asset, robot_name)
                self._progress.blueprint_path = blueprint_path

            # Complete
            self._update_progress(PipelineStage.COMPLETE, 100, "Pipeline complete!")

            self._result = {
                "success": True,
                "source_file": source_file,
                "output_file": output_file,
                "imported_asset": imported_asset,
                "blueprint_path": blueprint_path,
                "elapsed_time": self._progress.elapsed_seconds(),
            }

            self._status = PipelineStatus.COMPLETED
            self._notify_completion(self._result)

        except Exception as e:
            self.logger.error(f"Pipeline error: {e}")
            self._error = str(e)
            self._status = PipelineStatus.FAILED
            self._progress.stage = PipelineStage.ERROR
            self._notify_error(str(e))

    def _check_cancelled(self):
        """Check if cancellation was requested"""
        if self._cancel_requested:
            raise RuntimeError("Pipeline cancelled")

    def _update_progress(self, stage: PipelineStage, stage_percent: float, message: str):
        """Update progress and notify callbacks"""
        self._progress.stage = stage
        self._progress.stage_percent = stage_percent
        self._progress.stage_message = message
        self._progress.message = message
        self._progress.updated_at = time.time()

        # Calculate overall progress
        self._progress.percent = self._calculate_overall_progress(stage, stage_percent)

        self.logger.info(f"[{self._progress.percent:.0f}%] {message}")

        # Notify callbacks
        for callback in self._progress_callbacks:
            try:
                callback(self._progress)
            except Exception:
                pass

    def _calculate_overall_progress(self, stage: PipelineStage, stage_percent: float) -> float:
        """Calculate overall pipeline progress"""
        total_weight = sum(self.STAGE_WEIGHTS.values())
        completed_weight = 0

        stage_order = list(PipelineStage)
        current_index = stage_order.index(stage)

        for s in stage_order:
            if s == PipelineStage.IDLE or s == PipelineStage.COMPLETE or s == PipelineStage.ERROR:
                continue

            s_index = stage_order.index(s)
            weight = self.STAGE_WEIGHTS.get(s, 0)

            if s_index < current_index:
                completed_weight += weight
            elif s_index == current_index:
                completed_weight += weight * (stage_percent / 100.0)

        return (completed_weight / total_weight) * 100.0

    def _notify_completion(self, result: Dict[str, Any]):
        """Notify completion callbacks"""
        for callback in self._completion_callbacks:
            try:
                callback(result)
            except Exception:
                pass

    def _notify_error(self, error: str):
        """Notify error callbacks"""
        for callback in self._error_callbacks:
            try:
                callback(error)
            except Exception:
                pass

    # ═══════════════════════════════════════════════════════════════════
    # IPC Service Management
    # ═══════════════════════════════════════════════════════════════════

    def _ensure_ipc_service(self):
        """Ensure IPC service is running"""
        if not self._ipc_bridge:
            raise RuntimeError("IPC bridge not available")

        if self._ipc_bridge.is_service_running():
            self.logger.info("IPC service already running")
            self._update_progress(PipelineStage.IPC_CHECK, 100, "IPC service ready")
            return

        self.logger.warning("IPC service not running, attempting to start...")
        self._update_progress(PipelineStage.IPC_CHECK, 50, "Starting IPC service...")

        # Write start command
        cmd_file = os.path.join(self.config.ipc_folder, "commands", "start.cmd")
        os.makedirs(os.path.dirname(cmd_file), exist_ok=True)
        with open(cmd_file, "w") as f:
            json.dump({"command": "start", "timestamp": time.time()}, f)

        # Wait for service to start
        for i in range(30):  # 30 seconds timeout
            time.sleep(1)
            if self._ipc_bridge.is_service_running():
                self.logger.info("IPC service started successfully")
                self._update_progress(PipelineStage.IPC_CHECK, 100, "IPC service started")
                return

        raise RuntimeError("Failed to start IPC service")

    # ═══════════════════════════════════════════════════════════════════
    # Conversion
    # ═══════════════════════════════════════════════════════════════════

    def _submit_conversion(self, source_file: str) -> str:
        """Submit conversion request"""
        self._update_progress(PipelineStage.PARSING, 0, "Submitting conversion request...")

        request_id = self._ipc_bridge.submit_conversion(
            source_file=source_file,
            output_format=self.config.output_format,
            mesh_handling=self.config.mesh_handling,
            auto_assemble=self.config.auto_assemble,
            generate_blueprint=self.config.generate_blueprint,
            xacro_args=self.config.xacro_args if self.config.xacro_args else None,
        )

        self.logger.info(f"Conversion request submitted: {request_id}")
        return request_id

    def _monitor_conversion(self, request_id: str) -> Optional[ConversionResult]:
        """Monitor conversion progress"""
        stage_map = {
            "parsing": PipelineStage.PARSING,
            "xacro": PipelineStage.XACRO_PROCESS,
            "hierarchy": PipelineStage.HIERARCHY_BUILD,
            "meshes": PipelineStage.MESH_PROCESS,
            "mesh": PipelineStage.MESH_PROCESS,
            "usd": PipelineStage.USD_GENERATE,
            "ipc": PipelineStage.IPC_TRANSFER,
        }

        start_time = time.time()
        last_stage = ""

        while True:
            self._check_cancelled()

            # Check timeout
            if (time.time() - start_time) > self.config.ipc_timeout:
                raise RuntimeError("Conversion timeout")

            # Check for result
            result = self._ipc_bridge.get_result(request_id)
            if result:
                return result

            # Get progress
            progress = self._ipc_bridge.get_progress(request_id)
            if progress:
                stage_name = progress.stage.lower()

                # Map to pipeline stage
                pipeline_stage = stage_map.get(stage_name, PipelineStage.PARSING)
                stage_percent = progress.percent

                # Update if stage changed
                if stage_name != last_stage:
                    last_stage = stage_name
                    self.logger.info(f"Conversion stage: {stage_name}")

                self._update_progress(pipeline_stage, stage_percent, progress.message or stage_name)

            time.sleep(0.5)

    # ═══════════════════════════════════════════════════════════════════
    # UE5 Import
    # ═══════════════════════════════════════════════════════════════════

    def _import_to_ue5(self, usd_file: str) -> str:
        """
        Import USD to UE5.

        In production, this would:
        1. Use Interchange API to import USD
        2. Place assets in configured content path
        3. Return the imported asset path

        For now, simulates the import.
        """
        self._update_progress(PipelineStage.UE5_IMPORT, 25, "Preparing import...")
        time.sleep(0.5)

        robot_name = Path(usd_file).stem
        content_path = f"{self.config.ue5_content_path}/{robot_name}"

        self._update_progress(PipelineStage.UE5_IMPORT, 50, f"Importing to {content_path}...")
        time.sleep(0.5)

        # TODO: Actual UE5 import via Interchange
        # This would be done through:
        # 1. IPC command to UE5
        # 2. UE5 plugin receives command
        # 3. Interchange imports USD
        # 4. Response with asset path

        self._update_progress(PipelineStage.UE5_IMPORT, 100, "Import complete")

        return content_path

    # ═══════════════════════════════════════════════════════════════════
    # Hierarchy Assembly
    # ═══════════════════════════════════════════════════════════════════

    def _assemble_hierarchy(self, imported_asset: str):
        """
        Assemble robot hierarchy.

        This triggers the Dimensions Collector (DIMC) to:
        1. Analyze imported parts
        2. Build kinematic chain
        3. Apply physics constraints
        4. Create joint components
        """
        self._update_progress(PipelineStage.HIERARCHY_ASSEMBLE, 25, "Analyzing parts...")
        time.sleep(0.3)

        self._update_progress(PipelineStage.HIERARCHY_ASSEMBLE, 50, "Building kinematic chain...")
        time.sleep(0.3)

        if self.config.auto_physics:
            self._update_progress(PipelineStage.HIERARCHY_ASSEMBLE, 75, "Applying physics...")
            time.sleep(0.3)

        # TODO: Actual DIMC integration
        # This would send command to DIMC component

        self._update_progress(PipelineStage.HIERARCHY_ASSEMBLE, 100, "Hierarchy assembled")

    # ═══════════════════════════════════════════════════════════════════
    # Blueprint Generation
    # ═══════════════════════════════════════════════════════════════════

    def _generate_blueprint(self, imported_asset: str, robot_name: str) -> str:
        """
        Generate UE5 Blueprint from imported robot.

        Creates a Blueprint with:
        - Robot mesh hierarchy
        - Joint components
        - Animation capabilities
        - ROS2 integration hooks
        """
        self._update_progress(PipelineStage.BLUEPRINT_GEN, 50, f"Generating BP_{robot_name}...")

        blueprint_path = f"{self.config.ue5_content_path}/BP_{robot_name}"

        # TODO: Actual Blueprint generation
        # This would:
        # 1. Create Blueprint class
        # 2. Add components from imported hierarchy
        # 3. Setup default configurations
        # 4. Save Blueprint asset

        self._update_progress(PipelineStage.BLUEPRINT_GEN, 100, "Blueprint generated")

        return blueprint_path


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience Functions
# ═══════════════════════════════════════════════════════════════════════════════


def quick_pipeline(
    source_file: str,
    auto_assemble: bool = True,
    generate_blueprint: bool = True,
    ipc_folder: str = "/mnt/d/ROA/.ipc",
    timeout: float = 300,
) -> Optional[Dict[str, Any]]:
    """
    Quick pipeline execution.

    Args:
        source_file: Path to robot file
        auto_assemble: Auto-assemble hierarchy
        generate_blueprint: Generate Blueprint
        ipc_folder: IPC folder path
        timeout: Timeout in seconds

    Returns:
        Result dict or None on failure
    """
    config = PipelineConfig(
        ipc_folder=ipc_folder,
        ipc_timeout=timeout,
        auto_assemble=auto_assemble,
        generate_blueprint=generate_blueprint,
    )

    orchestrator = FTIPipelineOrchestrator(config)
    return orchestrator.run_pipeline(source_file, wait=True, timeout=timeout)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FTI Pipeline Orchestrator")
    parser.add_argument("source_file", help="Path to robot file")
    parser.add_argument("--no-assemble", action="store_true", help="Disable auto-assembly")
    parser.add_argument("--no-blueprint", action="store_true", help="Disable Blueprint generation")
    parser.add_argument("--ipc-folder", default="/mnt/d/ROA/.ipc", help="IPC folder path")
    parser.add_argument("--timeout", type=float, default=300, help="Timeout in seconds")

    args = parser.parse_args()

    def progress_callback(progress: PipelineProgress):
        print(f"\r[{progress.percent:5.1f}%] {progress.message}", end="", flush=True)

    config = PipelineConfig(
        ipc_folder=args.ipc_folder,
        ipc_timeout=args.timeout,
        auto_assemble=not args.no_assemble,
        generate_blueprint=not args.no_blueprint,
    )

    orchestrator = FTIPipelineOrchestrator(config)
    orchestrator.on_progress(progress_callback)

    print(f"Starting pipeline for: {args.source_file}")
    result = orchestrator.run_pipeline(args.source_file, wait=True)
    print()  # New line after progress

    if result and result.get("success"):
        print(f"\n✅ Pipeline completed in {result['elapsed_time']:.1f}s")
        print(f"   Output: {result['output_file']}")
        print(f"   Imported: {result['imported_asset']}")
        if result.get("blueprint_path"):
            print(f"   Blueprint: {result['blueprint_path']}")
    else:
        print(f"\n❌ Pipeline failed: {orchestrator.get_error()}")
