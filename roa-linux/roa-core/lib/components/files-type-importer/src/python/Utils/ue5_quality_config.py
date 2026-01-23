"""
UE5 Quality Configuration for FTI Mesh Optimization

Comprehensive quality settings optimized for Unreal Engine 5.
Ensures all converted meshes meet UE5's requirements for:
- Real-time rendering performance
- Physics simulation
- Material compatibility
- LOD systems
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class QualityPreset(Enum):
    """Quality presets for different use cases."""

    MAXIMUM = "maximum"  # Highest quality, slower performance
    HIGH = "high"  # High quality, good performance
    BALANCED = "balanced"  # Default - balanced quality/performance
    PERFORMANCE = "performance"  # Optimized for real-time
    MOBILE = "mobile"  # Mobile/VR optimization
    CINEMATIC = "cinematic"  # Offline rendering quality


class NormalCalculation(Enum):
    """Normal calculation methods."""

    ANGLE_WEIGHTED = "angle_weighted"  # Weight by face angles (best quality)
    AREA_WEIGHTED = "area_weighted"  # Weight by face areas
    EQUAL_WEIGHTED = "equal_weighted"  # Simple average
    FACE_NORMALS = "face_normals"  # Flat shading


class UVUnwrapMethod(Enum):
    """UV unwrapping methods."""

    SMART_UV = "smart_uv"  # Automatic smart projection
    ANGLE_BASED = "angle_based"  # Minimize angle distortion
    CONFORMAL = "conformal"  # Minimize shape distortion
    PRESERVE_SEAMS = "preserve_seams"  # Keep existing seams


@dataclass
class VertexOptimizationConfig:
    """Vertex-level optimization settings."""

    # Merge vertices within this distance (world units)
    merge_threshold: float = 0.0001

    # Remove vertices not referenced by faces
    remove_unreferenced: bool = True

    # Optimize vertex order for GPU cache
    optimize_vertex_cache: bool = True

    # Target cache size for optimization (vertices)
    cache_size: int = 32


@dataclass
class FaceOptimizationConfig:
    """Face-level optimization settings."""

    # Remove faces with zero area
    remove_degenerate: bool = True

    # Threshold for degenerate face detection
    degenerate_threshold: float = 1e-10

    # Remove duplicate faces
    remove_duplicates: bool = True

    # Ensure consistent face winding (CCW for UE5)
    fix_winding: bool = True

    # Target winding direction (True = CCW, standard for UE5)
    counter_clockwise: bool = True


@dataclass
class NormalConfig:
    """Normal calculation and optimization settings."""

    # Recalculate normals
    recalculate: bool = True

    # Calculation method
    method: NormalCalculation = NormalCalculation.ANGLE_WEIGHTED

    # Smoothing angle in degrees (faces with angle < this are smoothed)
    smoothing_angle: float = 60.0

    # Preserve hard edges where angle exceeds threshold
    preserve_hard_edges: bool = True

    # Hard edge threshold in degrees
    hard_edge_angle: float = 80.0

    # Flip normals if needed (auto-detect)
    auto_flip: bool = True


@dataclass
class UVConfig:
    """UV mapping configuration for UE5."""

    # Generate UVs if missing
    generate_if_missing: bool = True

    # UV generation method
    unwrap_method: UVUnwrapMethod = UVUnwrapMethod.SMART_UV

    # Island margin for UV islands (prevents bleeding)
    island_margin: float = 0.02

    # Pack UVs efficiently
    pack_uvs: bool = True

    # Maximum UV stretch allowed (0-1)
    max_stretch: float = 0.15

    # Create lightmap UVs in channel 1 (UE5 standard)
    generate_lightmap_uvs: bool = True

    # Lightmap resolution hint
    lightmap_resolution: int = 64


@dataclass
class MeshRepairConfig:
    """Mesh repair configuration."""

    # Attempt to repair mesh
    enabled: bool = True

    # Fill small holes
    fill_holes: bool = True

    # Maximum hole size to fill (as % of mesh area)
    max_hole_size_ratio: float = 0.05

    # Remove non-manifold geometry
    fix_non_manifold: bool = True

    # Make mesh watertight if possible
    ensure_watertight: bool = False  # Can add geometry

    # Remove internal faces
    remove_internal: bool = True


@dataclass
class SimplificationConfig:
    """Mesh simplification/decimation settings."""

    # Enable simplification
    enabled: bool = False

    # Target reduction ratio (0.5 = 50% faces)
    target_ratio: float = 1.0

    # Minimum faces (never go below this)
    min_faces: int = 100

    # Preserve mesh boundaries
    preserve_boundaries: bool = True

    # Preserve UV seams
    preserve_uv_seams: bool = True

    # Preserve material boundaries
    preserve_material_boundaries: bool = True

    # Preserve hard edges
    preserve_hard_edges: bool = True

    # Quality threshold for decimation (0-1)
    quality_threshold: float = 0.5


@dataclass
class LODConfig:
    """Level of Detail configuration for UE5."""

    # Generate LODs
    generate_lods: bool = True

    # Number of LOD levels
    num_levels: int = 4

    # LOD reduction ratios [LOD0, LOD1, LOD2, LOD3, ...]
    reduction_ratios: List[float] = field(default_factory=lambda: [1.0, 0.5, 0.25, 0.125])

    # Screen size thresholds for each LOD (UE5 uses screen percentage)
    screen_sizes: List[float] = field(default_factory=lambda: [1.0, 0.5, 0.25, 0.1])

    # Minimum faces for lowest LOD
    min_faces: int = 100

    # Use same simplification settings for all LODs
    use_uniform_settings: bool = True


@dataclass
class CollisionConfig:
    """Collision mesh configuration for UE5."""

    # Generate collision mesh
    generate: bool = True

    # Type: convex_decomposition, convex_hull, simple_box, simple_sphere, trimesh
    collision_type: str = "convex_decomposition"

    # Maximum convex hulls for decomposition
    max_convex_hulls: int = 16

    # Maximum vertices per convex hull
    max_vertices_per_hull: int = 32

    # Concavity threshold for decomposition (0-1)
    concavity: float = 0.01

    # Resolution for voxelization
    resolution: int = 100000

    # Simplify collision mesh
    simplify: bool = True

    # Target collision faces (if simplifying)
    target_faces: int = 1000


@dataclass
class MaterialConfig:
    """Material handling for UE5."""

    # Preserve original material names
    preserve_names: bool = True

    # Create UE5-compatible material instances
    create_instances: bool = True

    # Convert to PBR workflow
    convert_to_pbr: bool = True

    # Default material properties if missing
    default_metallic: float = 0.0
    default_roughness: float = 0.5
    default_specular: float = 0.5

    # Handle transparent materials
    support_transparency: bool = True

    # Maximum texture size (resized if larger)
    max_texture_size: int = 4096

    # Texture format preference
    texture_format: str = "png"


@dataclass
class PhysicsConfig:
    """Physics properties for UE5."""

    # Calculate physics properties
    enabled: bool = True

    # Calculate center of mass
    calculate_center_of_mass: bool = True

    # Calculate moment of inertia
    calculate_inertia: bool = True

    # Default density (kg/m³) if not specified
    default_density: float = 1000.0

    # Generate physics asset
    generate_physics_asset: bool = True


@dataclass
class UE5QualityConfig:
    """
    Complete quality configuration for UE5 mesh optimization.

    This configuration ensures meshes are fully compatible with
    Unreal Engine 5's rendering and physics systems.
    """

    # Overall quality preset (can be overridden by individual settings)
    preset: QualityPreset = QualityPreset.BALANCED

    # Scale factor (1.0 = no change, URDF uses meters, UE5 uses cm)
    scale_factor: float = 100.0  # meters to centimeters

    # Coordinate system conversion
    convert_coordinates: bool = True
    up_axis: str = "Z"  # UE5 uses Z-up
    forward_axis: str = "X"  # UE5 uses X-forward

    # Component configs
    vertex: VertexOptimizationConfig = field(default_factory=VertexOptimizationConfig)
    face: FaceOptimizationConfig = field(default_factory=FaceOptimizationConfig)
    normal: NormalConfig = field(default_factory=NormalConfig)
    uv: UVConfig = field(default_factory=UVConfig)
    repair: MeshRepairConfig = field(default_factory=MeshRepairConfig)
    simplification: SimplificationConfig = field(default_factory=SimplificationConfig)
    lod: LODConfig = field(default_factory=LODConfig)
    collision: CollisionConfig = field(default_factory=CollisionConfig)
    material: MaterialConfig = field(default_factory=MaterialConfig)
    physics: PhysicsConfig = field(default_factory=PhysicsConfig)

    # Validation thresholds
    max_vertices_per_mesh: int = 500000
    max_faces_per_mesh: int = 500000
    warn_vertices_threshold: int = 100000
    warn_faces_threshold: int = 100000

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        import dataclasses

        return dataclasses.asdict(self)

    @classmethod
    def from_preset(cls, preset: QualityPreset) -> "UE5QualityConfig":
        """Create config from preset."""
        config = cls(preset=preset)

        if preset == QualityPreset.MAXIMUM:
            config.simplification.enabled = False
            config.lod.num_levels = 5
            config.normal.smoothing_angle = 45.0
            config.collision.max_convex_hulls = 32

        elif preset == QualityPreset.HIGH:
            config.simplification.enabled = False
            config.lod.num_levels = 4
            config.normal.smoothing_angle = 50.0

        elif preset == QualityPreset.BALANCED:
            # Default settings
            pass

        elif preset == QualityPreset.PERFORMANCE:
            config.simplification.enabled = True
            config.simplification.target_ratio = 0.7
            config.lod.num_levels = 4
            config.lod.reduction_ratios = [1.0, 0.4, 0.2, 0.1]
            config.uv.lightmap_resolution = 32

        elif preset == QualityPreset.MOBILE:
            config.simplification.enabled = True
            config.simplification.target_ratio = 0.5
            config.lod.num_levels = 3
            config.lod.reduction_ratios = [1.0, 0.3, 0.1]
            config.material.max_texture_size = 1024
            config.collision.max_convex_hulls = 8
            config.uv.generate_lightmap_uvs = False

        elif preset == QualityPreset.CINEMATIC:
            config.simplification.enabled = False
            config.lod.generate_lods = False
            config.normal.smoothing_angle = 30.0
            config.uv.island_margin = 0.01
            config.material.max_texture_size = 8192

        return config


# Preset configurations for common use cases
PRESET_ROBOT_VISUALIZATION = UE5QualityConfig(
    preset=QualityPreset.BALANCED,
    vertex=VertexOptimizationConfig(merge_threshold=0.0001),
    lod=LODConfig(generate_lods=True, num_levels=4),
    collision=CollisionConfig(generate=True, collision_type="convex_decomposition"),
)

PRESET_ROBOT_SIMULATION = UE5QualityConfig(
    preset=QualityPreset.HIGH,
    physics=PhysicsConfig(enabled=True, calculate_inertia=True),
    collision=CollisionConfig(generate=True, collision_type="trimesh"),
    lod=LODConfig(generate_lods=False),  # Full detail for simulation
)

PRESET_ROBOT_REAL_TIME = UE5QualityConfig(
    preset=QualityPreset.PERFORMANCE,
    simplification=SimplificationConfig(enabled=True, target_ratio=0.7),
    lod=LODConfig(generate_lods=True, num_levels=4),
    collision=CollisionConfig(generate=True, max_convex_hulls=8),
)


def get_default_config() -> UE5QualityConfig:
    """Get default UE5 quality configuration."""
    return UE5QualityConfig()


def get_config_for_preset(preset: str) -> UE5QualityConfig:
    """Get configuration for named preset."""
    preset_map = {
        "maximum": QualityPreset.MAXIMUM,
        "high": QualityPreset.HIGH,
        "balanced": QualityPreset.BALANCED,
        "performance": QualityPreset.PERFORMANCE,
        "mobile": QualityPreset.MOBILE,
        "cinematic": QualityPreset.CINEMATIC,
        "robot_visualization": None,  # Special preset
        "robot_simulation": None,
        "robot_real_time": None,
    }

    if preset.lower() == "robot_visualization":
        return PRESET_ROBOT_VISUALIZATION
    elif preset.lower() == "robot_simulation":
        return PRESET_ROBOT_SIMULATION
    elif preset.lower() == "robot_real_time":
        return PRESET_ROBOT_REAL_TIME

    quality_preset = preset_map.get(preset.lower(), QualityPreset.BALANCED)
    return UE5QualityConfig.from_preset(quality_preset)
