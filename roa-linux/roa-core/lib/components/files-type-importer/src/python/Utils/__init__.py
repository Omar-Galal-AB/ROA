"""
Utils Package - Utility modules for FTI

Provides utility functions and classes for:
- Progress reporting and tracking
- Mesh optimization and repair
- LOD generation
- Mesh analysis
- Temp file management
- Retry handling
- Input validation
- Texture handling
- Assembly validation
- UE5 quality configuration
"""

from .progress_reporter import (
    ProgressReporter,
    BatchProgressReporter,
    ProgressInfo,
    ProgressStage,
    create_progress_reporter,
)

# Mesh optimization stack (optional: requires numpy<1.25/scipy). Fall back gracefully.
try:
    from .mesh_optimization import (
        MeshOptimizer,
        MeshAnalyzer,
        LODGenerator,
        LODLevel,
        OptimizationResult,
        optimize_mesh,
        generate_lods,
        analyze_mesh,
    )
    MESH_OPT_AVAILABLE = True
except Exception as _mesh_exc:
    MESH_OPT_AVAILABLE = False
    # Provide lightweight stubs to avoid import-time crashes where not needed
    class MeshOptimizer:  # type: ignore
        pass
    class MeshAnalyzer:  # type: ignore
        pass
    class LODGenerator:  # type: ignore
        pass
    class LODLevel:  # type: ignore
        pass
    class OptimizationResult:  # type: ignore
        pass
    def optimize_mesh(*args, **kwargs):  # type: ignore
        raise RuntimeError(f"Mesh optimization unavailable: {_mesh_exc}")
    def generate_lods(*args, **kwargs):  # type: ignore
        raise RuntimeError(f"LOD generation unavailable: {_mesh_exc}")
    def analyze_mesh(*args, **kwargs):  # type: ignore
        raise RuntimeError(f"Mesh analysis unavailable: {_mesh_exc}")

from .temp_manager import (
    TempFileManager,
    TempFileRecord,
    temp_transaction,
    cleanup_old_temp_files,
)

from .retry_handler import (
    retry,
    RetryError,
    RetryConfig,
    RetryContext,
    retry_file_operation,
    retry_with_fallback,
    FILE_OPERATION_RETRY,
    NETWORK_RETRY,
)

from .input_validator import (
    PreflightValidator,
    ValidationResult,
    ValidationIssue,
    ValidationSeverity,
    validate_file,
)

from .texture_handler import (
    TextureHandler,
    TextureInfo,
    TextureResult,
    TextureType,
    process_model_textures,
)

from .assembly_validator import (
    AssemblyValidator,
    AssemblyValidationResult,
    AssemblyIssue,
    AssemblyStats,
    ValidationLevel,
    validate_assembly,
)

from .ue5_quality_config import (
    UE5QualityConfig,
    QualityPreset,
    get_default_config,
    get_config_for_preset,
    PRESET_ROBOT_VISUALIZATION,
    PRESET_ROBOT_SIMULATION,
    PRESET_ROBOT_REAL_TIME,
)

from .async_batch_processor import (
    AsyncBatchProcessor,
    BatchItem,
    BatchResult,
    BatchStatus,
    BatchProgressCallback,
    ConsoleBatchProgress,
    create_batch_items,
    batch_import_async,
    batch_import_sync,
)

# GPU compute (optional: requires PyTorch or CuPy)
try:
    from .gpu_compute import (
        GPUManager,
        GPUInfo,
        GPUBackend,
        GPUWorkspaceComputer,
        gpu_task,
        gpu_batch,
    )
    GPU_COMPUTE_AVAILABLE = True
except ImportError as _gpu_exc:
    GPU_COMPUTE_AVAILABLE = False
    # Stubs for graceful fallback
    class GPUManager:  # type: ignore
        def is_available(self): return False
    class GPUInfo:  # type: ignore
        pass
    class GPUBackend:  # type: ignore
        pass
    class GPUWorkspaceComputer:  # type: ignore
        pass
    def gpu_task(f): return f  # type: ignore
    def gpu_batch(*args, **kwargs): return lambda f: f  # type: ignore

# CAD hierarchy inference (optional: requires pythonocc-core for full features)
try:
    from .cad_hierarchy_inference import (
        CADHierarchyInference,
        InferredJoint,
        InferredJointType,
        PartConnection,
        GeometricFeature,
        RobotTemplate,
        AssemblyHintsGenerator,
        ROBOT_TEMPLATES,
        infer_robot_from_cad,
    )
    CAD_INFERENCE_AVAILABLE = True
except ImportError as _cad_exc:
    CAD_INFERENCE_AVAILABLE = False
    # Stubs for graceful fallback
    class CADHierarchyInference:  # type: ignore
        pass
    class InferredJoint:  # type: ignore
        pass
    class InferredJointType:  # type: ignore
        pass
    class PartConnection:  # type: ignore
        pass
    class GeometricFeature:  # type: ignore
        pass
    class RobotTemplate:  # type: ignore
        pass
    class AssemblyHintsGenerator:  # type: ignore
        pass
    ROBOT_TEMPLATES = []  # type: ignore
    def infer_robot_from_cad(*args, **kwargs):  # type: ignore
        raise RuntimeError(f"CAD inference unavailable: {_cad_exc}")

# MoveIt integration (optional: requires roa_bridge or fastdds)
try:
    from .moveit_bridge import (
        MoveItBridge,
        LocalIKSolver,
        IKManager,
        Pose,
        JointState,
        Trajectory,
        TrajectoryPoint,
        IKRequest,
        IKResponse,
        MotionPlanRequest,
        MotionPlanResponse,
        IKSolverType,
        PlannerType,
        create_ik_manager,
    )
    MOVEIT_AVAILABLE = True
except ImportError as _moveit_exc:
    MOVEIT_AVAILABLE = False
    # Stubs for graceful fallback
    class MoveItBridge:  # type: ignore
        pass
    class LocalIKSolver:  # type: ignore
        pass
    class IKManager:  # type: ignore
        pass
    class Pose:  # type: ignore
        pass
    class JointState:  # type: ignore
        pass
    class Trajectory:  # type: ignore
        pass
    class TrajectoryPoint:  # type: ignore
        pass
    class IKRequest:  # type: ignore
        pass
    class IKResponse:  # type: ignore
        pass
    class MotionPlanRequest:  # type: ignore
        pass
    class MotionPlanResponse:  # type: ignore
        pass
    class IKSolverType:  # type: ignore
        pass
    class PlannerType:  # type: ignore
        pass
    def create_ik_manager(*args, **kwargs):  # type: ignore
        raise RuntimeError(f"MoveIt bridge unavailable: {_moveit_exc}")

__all__ = [
    # Progress reporting
    "ProgressReporter",
    "BatchProgressReporter",
    "ProgressInfo",
    "ProgressStage",
    "create_progress_reporter",
    
    # Mesh optimization
    "MeshOptimizer",
    "MeshAnalyzer",
    "LODGenerator",
    "LODLevel",
    "OptimizationResult",
    "optimize_mesh",
    "generate_lods",
    "analyze_mesh",
    "MESH_OPT_AVAILABLE",
    
    # Temp file management
    "TempFileManager",
    "TempFileRecord",
    "temp_transaction",
    "cleanup_old_temp_files",
    
    # Retry handling
    "retry",
    "RetryError",
    "RetryConfig",
    "RetryContext",
    "retry_file_operation",
    "retry_with_fallback",
    "FILE_OPERATION_RETRY",
    "NETWORK_RETRY",
    
    # Input validation
    "PreflightValidator",
    "ValidationResult",
    "ValidationIssue",
    "ValidationSeverity",
    "validate_file",
    
    # Texture handling
    "TextureHandler",
    "TextureInfo",
    "TextureResult",
    "TextureType",
    "process_model_textures",
    
    # Assembly validation
    "AssemblyValidator",
    "AssemblyValidationResult",
    "AssemblyIssue",
    "AssemblyStats",
    "ValidationLevel",
    "validate_assembly",
    
    # UE5 quality config
    "UE5QualityConfig",
    "QualityPreset",
    "get_default_config",
    "get_config_for_preset",
    "PRESET_ROBOT_VISUALIZATION",
    "PRESET_ROBOT_SIMULATION",
    "PRESET_ROBOT_REAL_TIME",
    
    # Async batch processing
    "AsyncBatchProcessor",
    "BatchItem",
    "BatchResult",
    "BatchStatus",
    "BatchProgressCallback",
    "ConsoleBatchProgress",
    "create_batch_items",
    "batch_import_async",
    "batch_import_sync",
    
    # GPU compute
    "GPUManager",
    "GPUInfo",
    "GPUBackend",
    "GPUWorkspaceComputer",
    "gpu_task",
    "gpu_batch",
    "GPU_COMPUTE_AVAILABLE",
    
    # CAD hierarchy inference
    "CADHierarchyInference",
    "InferredJoint",
    "InferredJointType",
    "PartConnection",
    "GeometricFeature",
    "RobotTemplate",
    "AssemblyHintsGenerator",
    "ROBOT_TEMPLATES",
    "infer_robot_from_cad",
    "CAD_INFERENCE_AVAILABLE",
    
    # MoveIt integration
    "MoveItBridge",
    "LocalIKSolver",
    "IKManager",
    "Pose",
    "JointState",
    "Trajectory",
    "TrajectoryPoint",
    "IKRequest",
    "IKResponse",
    "MotionPlanRequest",
    "MotionPlanResponse",
    "IKSolverType",
    "PlannerType",
    "create_ik_manager",
    "MOVEIT_AVAILABLE",
]
