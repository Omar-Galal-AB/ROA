"""
Converters Package - Format-specific conversion modules

Provides converters for various 3D model formats:
- URDF: ROS robot description format
- SDF: Gazebo simulation description format
- STL: Stereolithography mesh format
- OBJ: Wavefront 3D geometry format
- DAE: COLLADA digital asset exchange format
- STEP: CAD standard exchange format (with pythonocc-core)
- IGES: Legacy CAD format (with pythonocc-core)
- FBX: Autodesk Filmbox format
- glTF: GL Transmission Format (Khronos standard)

Special converters:
- CADConverter: Full STEP/IGES support with kinematics definition
- ParallelMechanismExporter: Closed-loop robots (multi-file export)
- FormatConverter: URDF ↔ SDF ↔ MJCF conversion utilities

Advanced features:
- Submechanism: Kinematic group management (SMURF-compatible)
- SMURFSupport: SMURF format parsing and generation
"""

from .base_converter import BaseConverter, ConversionResult
from .dae_converter import DAEConverter
from .fbx_converter import FBXConverter
from .gltf_converter import GLTFConverter
from .iges_converter import IGESConverter
from .obj_converter import OBJConverter
from .sdf_converter import SDFConverter
from .step_converter import STEPConverter
from .stl_converter import STLConverter
from .urdf_converter import URDFConverter

# Optional converters (may have additional dependencies)
try:
    from .cad_converter import CADConverter, JointDefinition, KinematicsWizard

    _cad_available = True
except ImportError:
    CADConverter = None
    JointDefinition = None
    KinematicsWizard = None
    _cad_available = False

try:
    from .parallel_mechanism_exporter import (
        BreakPointSelector,
        GeometricConstraintDetector,
        LoopDetector,
        ParallelMechanismExporter,
        WorldTransformComputer,
    )

    _parallel_available = True
except ImportError:
    ParallelMechanismExporter = None
    LoopDetector = None
    GeometricConstraintDetector = None
    WorldTransformComputer = None
    BreakPointSelector = None
    _parallel_available = False

# Submechanism support (SMURF-compatible kinematic groups)
try:
    from .submechanism import (
        JointCoupling,
        JointCouplingType,
        LoopConstraint,
        Submechanism,
        SubmechanismDetector,
        SubmechanismManager,
        SubmechanismType,
        create_submechanism_from_joints,
        detect_and_create_submechanisms,
    )

    _submechanism_available = True
except ImportError:
    Submechanism = None
    SubmechanismType = None
    SubmechanismDetector = None
    SubmechanismManager = None
    LoopConstraint = None
    JointCoupling = None
    JointCouplingType = None
    detect_and_create_submechanisms = None
    create_submechanism_from_joints = None
    _submechanism_available = False

# SMURF format support
try:
    from .smurf_support import (
        SMURFConverter,
        SMURFData,
        SMURFMaterial,
        SMURFMotor,
        SMURFParser,
        SMURFSensor,
        SMURFWriter,
        load_smurf,
        merge_urdf_smurf,
        save_smurf,
    )

    _smurf_available = True
except ImportError:
    SMURFData = None
    SMURFParser = None
    SMURFWriter = None
    SMURFConverter = None
    SMURFMotor = None
    SMURFSensor = None
    SMURFMaterial = None
    load_smurf = None
    save_smurf = None
    merge_urdf_smurf = None
    _smurf_available = False

# Format conversion utilities
try:
    from .format_converter import (
        ConversionOptions,
        SDFToURDFConverter,
        URDFToMJCFConverter,
        URDFToSDFConverter,
        batch_convert,
        convert_sdf_to_urdf,
        convert_urdf_to_mjcf,
        convert_urdf_to_sdf,
    )

    _format_converter_available = True
except ImportError:
    URDFToSDFConverter = None
    SDFToURDFConverter = None
    URDFToMJCFConverter = None
    ConversionOptions = None
    convert_urdf_to_sdf = None
    convert_sdf_to_urdf = None
    convert_urdf_to_mjcf = None
    batch_convert = None
    _format_converter_available = False

__all__ = [
    "BaseConverter",
    "ConversionResult",
    "URDFConverter",
    "SDFConverter",
    "STLConverter",
    "OBJConverter",
    "DAEConverter",
    "STEPConverter",
    "IGESConverter",
    "FBXConverter",
    "GLTFConverter",
    # CAD with kinematics
    "CADConverter",
    "JointDefinition",
    "KinematicsWizard",
    # Parallel mechanism
    "ParallelMechanismExporter",
    "LoopDetector",
    "GeometricConstraintDetector",
    "WorldTransformComputer",
    "BreakPointSelector",
    # Submechanism
    "Submechanism",
    "SubmechanismType",
    "SubmechanismDetector",
    "SubmechanismManager",
    "LoopConstraint",
    "JointCoupling",
    "JointCouplingType",
    "detect_and_create_submechanisms",
    "create_submechanism_from_joints",
    # SMURF
    "SMURFData",
    "SMURFParser",
    "SMURFWriter",
    "SMURFConverter",
    "SMURFMotor",
    "SMURFSensor",
    "SMURFMaterial",
    "load_smurf",
    "save_smurf",
    "merge_urdf_smurf",
    # Format conversion
    "URDFToSDFConverter",
    "SDFToURDFConverter",
    "URDFToMJCFConverter",
    "ConversionOptions",
    "convert_urdf_to_sdf",
    "convert_sdf_to_urdf",
    "convert_urdf_to_mjcf",
    "batch_convert",
    # Registry
    "CONVERTER_REGISTRY",
    "get_converter_class",
    "get_supported_formats",
]

# Converter registry for dynamic lookup
CONVERTER_REGISTRY = {
    # Robot description formats
    "urdf": URDFConverter,
    "xacro": URDFConverter,  # XACRO is handled by URDF converter
    "sdf": SDFConverter,
    "world": SDFConverter,  # Gazebo world files
    # Mesh formats
    "stl": STLConverter,
    "obj": OBJConverter,
    # Exchange formats
    "dae": DAEConverter,
    "collada": DAEConverter,
    "gltf": GLTFConverter,
    "glb": GLTFConverter,
    # CAD formats
    "step": STEPConverter,
    "stp": STEPConverter,
    "iges": IGESConverter,
    "igs": IGESConverter,
    # Animation/game formats
    "fbx": FBXConverter,
}


def get_converter_class(format_name: str):
    """
    Get the converter class for a given format name.

    Args:
        format_name: Format name (e.g., 'urdf', 'stl', 'obj', 'dae', 'step', 'fbx')

    Returns:
        Converter class or None if not supported
    """
    return CONVERTER_REGISTRY.get(format_name.lower())


def get_supported_formats() -> dict:
    """
    Get all supported formats grouped by category.

    Returns:
        Dictionary with format categories and their extensions
    """
    return {
        "robot_description": ["urdf", "xacro", "sdf", "world"],
        "mesh": ["stl", "obj"],
        "exchange": ["dae", "collada", "gltf", "glb"],
        "cad": ["step", "stp", "iges", "igs"],
        "animation": ["fbx"],
    }
