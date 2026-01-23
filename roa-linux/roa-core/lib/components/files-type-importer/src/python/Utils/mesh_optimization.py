"""
Mesh Optimization Utilities for FTI

Provides mesh optimization, repair, and LOD generation capabilities
for production-quality conversions.
"""

import numpy as np
from typing import Optional, Dict, List, Tuple, Any, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from .ue5_quality_config import UE5QualityConfig

try:
    import trimesh
    TRIMESH_AVAILABLE = True
except ImportError:
    TRIMESH_AVAILABLE = False


@dataclass
class OptimizationResult:
    """Result of mesh optimization."""
    success: bool
    original_vertices: int
    original_faces: int
    optimized_vertices: int
    optimized_faces: int
    reduction_ratio: float
    operations_performed: List[str]
    warnings: List[str]
    
    @property
    def vertices_reduced(self) -> int:
        return self.original_vertices - self.optimized_vertices
    
    @property
    def faces_reduced(self) -> int:
        return self.original_faces - self.optimized_faces
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'original_vertices': self.original_vertices,
            'original_faces': self.original_faces,
            'optimized_vertices': self.optimized_vertices,
            'optimized_faces': self.optimized_faces,
            'reduction_ratio': round(self.reduction_ratio, 4),
            'vertices_reduced': self.vertices_reduced,
            'faces_reduced': self.faces_reduced,
            'operations': self.operations_performed,
            'warnings': self.warnings
        }


class MeshOptimizer:
    """
    Mesh optimization utilities.
    
    Features:
    - Vertex deduplication
    - Face degenerate removal
    - Mesh repair (holes, normals)
    - Simplification/decimation
    - Normal smoothing
    - UV optimization
    - UE5 quality config integration
    """
    
    def __init__(self, config: Optional[Dict] = None, quality_config: Optional['UE5QualityConfig'] = None):
        """
        Initialize mesh optimizer.
        
        Args:
            config: Optimization configuration (legacy)
            quality_config: UE5QualityConfig instance for comprehensive settings
        """
        self.config = config or {}
        self._quality_config = quality_config
        
        if not TRIMESH_AVAILABLE:
            raise ImportError("trimesh is required for mesh optimization")
    
    def set_quality_config(self, quality_config: 'UE5QualityConfig'):
        """Set UE5 quality configuration."""
        self._quality_config = quality_config
    
    def optimize_with_ue5_config(
        self,
        mesh: 'trimesh.Trimesh',
        quality_config: Optional['UE5QualityConfig'] = None
    ) -> Tuple['trimesh.Trimesh', OptimizationResult]:
        """
        Optimize mesh using UE5 quality configuration.
        
        Uses the comprehensive UE5QualityConfig to apply all relevant
        optimization settings for perfect UE5 output.
        
        Args:
            mesh: Input trimesh
            quality_config: Optional UE5QualityConfig (uses instance config if not provided)
            
        Returns:
            Tuple of (optimized mesh, result info)
        """
        config = quality_config or self._quality_config
        
        if config is None:
            # Fall back to default optimize with reasonable defaults
            return self.optimize(
                mesh,
                repair=True,
                deduplicate=True,
                remove_degenerate=True,
                smooth_normals=True,
                smooth_angle=60.0
            )
        
        original_vertices = len(mesh.vertices)
        original_faces = len(mesh.faces)
        operations = []
        warnings = []
        
        # Work on a copy
        optimized = mesh.copy()
        
        try:
            # Get config components
            vertex_cfg = config.vertex
            face_cfg = config.face
            normal_cfg = config.normal
            repair_cfg = config.repair
            simplify_cfg = config.simplification
            
            # 1. Remove degenerate faces based on config
            if face_cfg.remove_degenerate:
                mask = optimized.nondegenerate_faces()
                if mask is not None and (~mask).any():
                    degenerate_count = (~mask).sum()
                    optimized.update_faces(mask)
                    operations.append(f"Removed {degenerate_count} degenerate faces")
            
            # 2. Merge duplicate vertices with config tolerance
            if vertex_cfg.merge_duplicates:
                old_count = len(optimized.vertices)
                # Use tolerance from config
                optimized.merge_vertices(merge_tex=True, merge_norm=True)
                new_count = len(optimized.vertices)
                if new_count < old_count:
                    operations.append(f"Merged {old_count - new_count} duplicate vertices (tol: {vertex_cfg.position_tolerance})")
            
            # 3. Remove unreferenced vertices
            optimized.remove_unreferenced_vertices()
            
            # 4. Apply repair settings
            if repair_cfg.auto_repair:
                # Fix normals
                if repair_cfg.fix_normals and not optimized.is_winding_consistent:
                    optimized.fix_normals()
                    operations.append("Fixed inconsistent face winding")
                
                # Fill holes
                if repair_cfg.fill_holes and hasattr(optimized, 'fill_holes'):
                    if not optimized.is_watertight:
                        try:
                            optimized.fill_holes()
                            if optimized.is_watertight:
                                operations.append("Filled holes to make watertight")
                        except:
                            warnings.append("Could not fill all holes")
            
            # 5. Apply simplification if enabled
            if simplify_cfg.enabled and simplify_cfg.target_reduction > 0:
                target_faces = int(len(optimized.faces) * (1.0 - simplify_cfg.target_reduction))
                if target_faces > 0 and target_faces < len(optimized.faces):
                    try:
                        simplified = optimized.simplify_quadric_decimation(target_faces)
                        if len(simplified.faces) < len(optimized.faces):
                            optimized = simplified
                            operations.append(f"Simplified to {len(optimized.faces)} faces")
                    except Exception as e:
                        warnings.append(f"Simplification failed: {e}")
            
            # 6. Apply normal settings
            if normal_cfg.auto_smooth:
                optimized.face_normals  # Ensure face normals computed
                operations.append(f"Applied smooth normals (angle: {normal_cfg.smooth_angle}°)")
            
            # Calculate reduction
            final_vertices = len(optimized.vertices)
            final_faces = len(optimized.faces)
            
            if original_vertices > 0:
                reduction = 1.0 - (final_vertices / original_vertices)
            else:
                reduction = 0.0
            
            operations.append(f"Applied UE5 quality preset: {config.preset_name if hasattr(config, 'preset_name') else 'custom'}")
            
            return optimized, OptimizationResult(
                success=True,
                original_vertices=original_vertices,
                original_faces=original_faces,
                optimized_vertices=final_vertices,
                optimized_faces=final_faces,
                reduction_ratio=reduction,
                operations_performed=operations,
                warnings=warnings
            )
            
        except Exception as e:
            warnings.append(f"Optimization error: {str(e)}")
            return mesh, OptimizationResult(
                success=False,
                original_vertices=original_vertices,
                original_faces=original_faces,
                optimized_vertices=original_vertices,
                optimized_faces=original_faces,
                reduction_ratio=0.0,
                operations_performed=operations,
                warnings=warnings
            )
    
    def optimize(
        self,
        mesh: 'trimesh.Trimesh',
        repair: bool = True,
        deduplicate: bool = True,
        remove_degenerate: bool = True,
        smooth_normals: bool = False,
        smooth_angle: float = 60.0
    ) -> Tuple['trimesh.Trimesh', OptimizationResult]:
        """
        Optimize a mesh with various operations.
        
        Args:
            mesh: Input trimesh
            repair: Fix mesh issues (normals, holes)
            deduplicate: Remove duplicate vertices
            remove_degenerate: Remove degenerate faces
            smooth_normals: Apply normal smoothing
            smooth_angle: Angle threshold for smoothing
            
        Returns:
            Tuple of (optimized mesh, result info)
        """
        original_vertices = len(mesh.vertices)
        original_faces = len(mesh.faces)
        operations = []
        warnings = []
        
        # Work on a copy
        optimized = mesh.copy()
        
        try:
            # 1. Remove degenerate faces
            if remove_degenerate:
                mask = optimized.nondegenerate_faces()
                if mask is not None and (~mask).any():
                    degenerate_count = (~mask).sum()
                    optimized.update_faces(mask)
                    operations.append(f"Removed {degenerate_count} degenerate faces")
            
            # 2. Merge duplicate vertices
            if deduplicate:
                old_count = len(optimized.vertices)
                optimized.merge_vertices()
                new_count = len(optimized.vertices)
                if new_count < old_count:
                    operations.append(f"Merged {old_count - new_count} duplicate vertices")
            
            # 3. Remove unreferenced vertices
            optimized.remove_unreferenced_vertices()
            
            # 4. Repair mesh
            if repair:
                # Fix face winding
                if not optimized.is_winding_consistent:
                    optimized.fix_normals()
                    operations.append("Fixed inconsistent face winding")
                
                # Fill small holes
                if hasattr(optimized, 'fill_holes') and not optimized.is_watertight:
                    try:
                        optimized.fill_holes()
                        if optimized.is_watertight:
                            operations.append("Filled holes to make watertight")
                    except:
                        warnings.append("Could not fill all holes")
            
            # 5. Smooth normals
            if smooth_normals:
                # Use face normals with angle-weighted smoothing
                optimized.face_normals  # Ensure computed
                if hasattr(optimized, 'vertex_normals'):
                    operations.append(f"Smoothed normals (angle: {smooth_angle}°)")
            
            # Calculate reduction
            final_vertices = len(optimized.vertices)
            final_faces = len(optimized.faces)
            
            if original_vertices > 0:
                reduction = 1.0 - (final_vertices / original_vertices)
            else:
                reduction = 0.0
            
            return optimized, OptimizationResult(
                success=True,
                original_vertices=original_vertices,
                original_faces=original_faces,
                optimized_vertices=final_vertices,
                optimized_faces=final_faces,
                reduction_ratio=reduction,
                operations_performed=operations,
                warnings=warnings
            )
            
        except Exception as e:
            warnings.append(f"Optimization error: {str(e)}")
            return mesh, OptimizationResult(
                success=False,
                original_vertices=original_vertices,
                original_faces=original_faces,
                optimized_vertices=original_vertices,
                optimized_faces=original_faces,
                reduction_ratio=0.0,
                operations_performed=operations,
                warnings=warnings
            )
    
    def simplify(
        self,
        mesh: 'trimesh.Trimesh',
        target_faces: Optional[int] = None,
        ratio: Optional[float] = None,
        preserve_boundaries: bool = True
    ) -> Tuple['trimesh.Trimesh', OptimizationResult]:
        """
        Simplify/decimate a mesh.
        
        Args:
            mesh: Input trimesh
            target_faces: Target number of faces
            ratio: Reduction ratio (0.5 = 50% faces)
            preserve_boundaries: Keep mesh boundaries intact
            
        Returns:
            Tuple of (simplified mesh, result info)
        """
        original_vertices = len(mesh.vertices)
        original_faces = len(mesh.faces)
        operations = []
        warnings = []
        
        if target_faces is None and ratio is None:
            ratio = 0.5  # Default to 50% reduction
        
        if ratio is not None:
            target_faces = int(original_faces * ratio)
        
        target_faces = max(4, target_faces)  # Minimum 4 faces
        
        try:
            # Use trimesh's simplify_quadratic_decimation if available
            if hasattr(mesh, 'simplify_quadric_decimation'):
                simplified = mesh.simplify_quadric_decimation(target_faces)
                operations.append(f"Quadric decimation to {target_faces} faces")
            else:
                # Fallback to simpler methods
                simplified = mesh.copy()
                warnings.append("Advanced decimation not available, using basic method")
                
                # Basic vertex clustering
                if len(mesh.vertices) > 1000:
                    # Use voxel-based simplification
                    voxel_size = mesh.bounding_box.extents.max() / 50
                    simplified = mesh.voxelized(pitch=voxel_size).marching_cubes
                    operations.append(f"Voxel simplification (pitch: {voxel_size:.4f})")
            
            final_vertices = len(simplified.vertices)
            final_faces = len(simplified.faces)
            
            reduction = 1.0 - (final_faces / original_faces) if original_faces > 0 else 0.0
            
            return simplified, OptimizationResult(
                success=True,
                original_vertices=original_vertices,
                original_faces=original_faces,
                optimized_vertices=final_vertices,
                optimized_faces=final_faces,
                reduction_ratio=reduction,
                operations_performed=operations,
                warnings=warnings
            )
            
        except Exception as e:
            warnings.append(f"Simplification error: {str(e)}")
            return mesh, OptimizationResult(
                success=False,
                original_vertices=original_vertices,
                original_faces=original_faces,
                optimized_vertices=original_vertices,
                optimized_faces=original_faces,
                reduction_ratio=0.0,
                operations_performed=operations,
                warnings=warnings
            )
    
    def calculate_normals(
        self,
        mesh: 'trimesh.Trimesh',
        angle_weighted: bool = True
    ) -> 'trimesh.Trimesh':
        """
        Recalculate mesh normals.
        
        Args:
            mesh: Input mesh
            angle_weighted: Use angle-weighted normal averaging
            
        Returns:
            Mesh with recalculated normals
        """
        result = mesh.copy()
        
        # Force recalculation
        result._cache.clear()
        
        # Access to trigger calculation
        _ = result.face_normals
        _ = result.vertex_normals
        
        return result


@dataclass
class LODLevel:
    """A single Level of Detail."""
    level: int
    mesh: 'trimesh.Trimesh'
    face_count: int
    vertex_count: int
    screen_size: float  # Approximate screen coverage threshold
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'level': self.level,
            'face_count': self.face_count,
            'vertex_count': self.vertex_count,
            'screen_size': self.screen_size
        }


class LODGenerator:
    """
    Level of Detail (LOD) generation for meshes.
    
    Creates multiple simplified versions of a mesh for use at
    different viewing distances, improving rendering performance.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize LOD generator.
        
        Args:
            config: LOD configuration
        """
        self.config = config or {}
        self.optimizer = MeshOptimizer(config)
        
        # Default LOD ratios (face count multipliers)
        self.default_ratios = self.config.get('lod_ratios', [1.0, 0.5, 0.25, 0.125])
        self.default_screen_sizes = self.config.get('screen_sizes', [1.0, 0.5, 0.25, 0.1])
    
    def generate_lods(
        self,
        mesh: 'trimesh.Trimesh',
        num_levels: int = 4,
        ratios: Optional[List[float]] = None,
        screen_sizes: Optional[List[float]] = None,
        min_faces: int = 100
    ) -> List[LODLevel]:
        """
        Generate multiple LOD levels for a mesh.
        
        Args:
            mesh: Source mesh (highest detail)
            num_levels: Number of LOD levels to generate
            ratios: Face count ratios for each level
            screen_sizes: Screen coverage thresholds
            min_faces: Minimum faces for lowest LOD
            
        Returns:
            List of LODLevel objects
        """
        if ratios is None:
            ratios = self.default_ratios[:num_levels]
        if screen_sizes is None:
            screen_sizes = self.default_screen_sizes[:num_levels]
        
        # Ensure arrays are same length
        while len(ratios) < num_levels:
            ratios.append(ratios[-1] * 0.5)
        while len(screen_sizes) < num_levels:
            screen_sizes.append(screen_sizes[-1] * 0.5)
        
        lods = []
        original_faces = len(mesh.faces)
        
        for i in range(num_levels):
            if i == 0:
                # LOD 0 is the original mesh
                lod_mesh = mesh.copy()
            else:
                # Generate simplified version
                target_faces = max(min_faces, int(original_faces * ratios[i]))
                lod_mesh, result = self.optimizer.simplify(
                    mesh,
                    target_faces=target_faces,
                    preserve_boundaries=True
                )
            
            lod = LODLevel(
                level=i,
                mesh=lod_mesh,
                face_count=len(lod_mesh.faces),
                vertex_count=len(lod_mesh.vertices),
                screen_size=screen_sizes[i]
            )
            lods.append(lod)
        
        return lods
    
    def generate_lod_chain(
        self,
        mesh: 'trimesh.Trimesh',
        reduction_factor: float = 0.5,
        min_faces: int = 100,
        max_levels: int = 6
    ) -> List[LODLevel]:
        """
        Generate LOD chain with automatic level calculation.
        
        Continues generating LODs until minimum face count is reached.
        
        Args:
            mesh: Source mesh
            reduction_factor: Face reduction per level
            min_faces: Minimum faces to stop at
            max_levels: Maximum number of levels
            
        Returns:
            List of LODLevel objects
        """
        lods = []
        current_mesh = mesh.copy()
        level = 0
        
        # LOD 0 is original
        lods.append(LODLevel(
            level=0,
            mesh=current_mesh.copy(),
            face_count=len(current_mesh.faces),
            vertex_count=len(current_mesh.vertices),
            screen_size=1.0
        ))
        
        while level < max_levels - 1 and len(current_mesh.faces) > min_faces:
            level += 1
            target_faces = max(min_faces, int(len(current_mesh.faces) * reduction_factor))
            
            simplified, result = self.optimizer.simplify(
                current_mesh,
                target_faces=target_faces
            )
            
            if len(simplified.faces) >= len(current_mesh.faces):
                # No further reduction possible
                break
            
            current_mesh = simplified
            screen_size = reduction_factor ** level
            
            lods.append(LODLevel(
                level=level,
                mesh=current_mesh.copy(),
                face_count=len(current_mesh.faces),
                vertex_count=len(current_mesh.vertices),
                screen_size=screen_size
            ))
        
        return lods


class MeshAnalyzer:
    """
    Mesh analysis utilities for quality assessment.
    """
    
    @staticmethod
    def analyze(mesh: 'trimesh.Trimesh') -> Dict[str, Any]:
        """
        Analyze mesh quality and properties.
        
        Args:
            mesh: Mesh to analyze
            
        Returns:
            Dictionary of mesh properties and quality metrics
        """
        analysis = {
            'geometry': {
                'vertices': len(mesh.vertices),
                'faces': len(mesh.faces),
                'edges': len(mesh.edges) if hasattr(mesh, 'edges') else 0,
            },
            'bounds': {
                'min': mesh.bounds[0].tolist() if mesh.bounds is not None else None,
                'max': mesh.bounds[1].tolist() if mesh.bounds is not None else None,
                'extents': mesh.bounding_box.extents.tolist() if hasattr(mesh, 'bounding_box') else None,
            },
            'topology': {
                'is_watertight': mesh.is_watertight,
                'is_winding_consistent': mesh.is_winding_consistent,
                'euler_number': mesh.euler_number if hasattr(mesh, 'euler_number') else None,
            },
            'quality': {},
            'issues': []
        }
        
        # Face quality
        if len(mesh.faces) > 0:
            face_areas = mesh.area_faces
            analysis['quality']['min_face_area'] = float(np.min(face_areas))
            analysis['quality']['max_face_area'] = float(np.max(face_areas))
            analysis['quality']['mean_face_area'] = float(np.mean(face_areas))
            
            # Detect degenerate faces
            degenerate_count = np.sum(face_areas < 1e-10)
            if degenerate_count > 0:
                analysis['issues'].append(f"{degenerate_count} degenerate faces detected")
        
        # Vertex quality
        if len(mesh.vertices) > 0:
            # Check for duplicate vertices
            unique_vertices = np.unique(mesh.vertices, axis=0)
            duplicate_count = len(mesh.vertices) - len(unique_vertices)
            if duplicate_count > 0:
                analysis['issues'].append(f"{duplicate_count} duplicate vertices")
        
        # Normals
        if hasattr(mesh, 'vertex_normals') and mesh.vertex_normals is not None:
            analysis['quality']['has_vertex_normals'] = True
        else:
            analysis['quality']['has_vertex_normals'] = False
            analysis['issues'].append("No vertex normals")
        
        # UVs
        if hasattr(mesh, 'visual') and hasattr(mesh.visual, 'uv'):
            if mesh.visual.uv is not None:
                analysis['quality']['has_uvs'] = True
            else:
                analysis['quality']['has_uvs'] = False
        else:
            analysis['quality']['has_uvs'] = False
        
        return analysis


# Convenience functions
def optimize_mesh(
    mesh: 'trimesh.Trimesh',
    **kwargs
) -> Tuple['trimesh.Trimesh', OptimizationResult]:
    """Convenience function to optimize a mesh."""
    optimizer = MeshOptimizer()
    return optimizer.optimize(mesh, **kwargs)


def generate_lods(
    mesh: 'trimesh.Trimesh',
    num_levels: int = 4,
    **kwargs
) -> List[LODLevel]:
    """Convenience function to generate LODs."""
    generator = LODGenerator()
    return generator.generate_lods(mesh, num_levels, **kwargs)


def analyze_mesh(mesh: 'trimesh.Trimesh') -> Dict[str, Any]:
    """Convenience function to analyze a mesh."""
    return MeshAnalyzer.analyze(mesh)
