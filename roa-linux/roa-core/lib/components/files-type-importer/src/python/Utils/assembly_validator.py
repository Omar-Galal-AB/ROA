"""
Assembly Validator for FTI

Validates converted robot assemblies to ensure they are complete
and ready for use in Unreal Engine 5.

Focused validation for UE5 output requirements:
- Mesh integrity
- Joint hierarchy
- Material assignments
- Physics properties
- USD structure validation
"""

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# USD validation
from pxr import Sdf, Usd, UsdGeom, UsdPhysics, UsdShade


class ValidationLevel(Enum):
    """Validation strictness levels."""

    MINIMAL = "minimal"  # Basic structure only
    STANDARD = "standard"  # Default validation
    STRICT = "strict"  # Full validation for production
    UE5_READY = "ue5_ready"  # UE5-specific validation


@dataclass
class AssemblyIssue:
    """A validation issue found in the assembly."""

    severity: str  # error, warning, info
    category: str  # structure, geometry, material, physics, hierarchy
    code: str
    message: str
    prim_path: Optional[str] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "category": self.category,
            "code": self.code,
            "message": self.message,
            "prim_path": self.prim_path,
            "suggestion": self.suggestion,
        }


@dataclass
class AssemblyStats:
    """Statistics about the assembly."""

    total_prims: int = 0
    mesh_count: int = 0
    xform_count: int = 0
    material_count: int = 0
    joint_count: int = 0
    total_vertices: int = 0
    total_faces: int = 0
    hierarchy_depth: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_prims": self.total_prims,
            "meshes": self.mesh_count,
            "xforms": self.xform_count,
            "materials": self.material_count,
            "joints": self.joint_count,
            "vertices": self.total_vertices,
            "faces": self.total_faces,
            "hierarchy_depth": self.hierarchy_depth,
        }


@dataclass
class AssemblyValidationResult:
    """Result of assembly validation."""

    valid: bool
    level: ValidationLevel
    ue5_compatible: bool
    file_path: str
    stats: AssemblyStats = field(default_factory=AssemblyStats)
    issues: List[AssemblyIssue] = field(default_factory=list)

    @property
    def errors(self) -> List[AssemblyIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[AssemblyIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def add_issue(self, issue: AssemblyIssue):
        self.issues.append(issue)
        if issue.severity == "error":
            self.valid = False
            self.ue5_compatible = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "ue5_compatible": self.ue5_compatible,
            "level": self.level.value,
            "file_path": self.file_path,
            "stats": self.stats.to_dict(),
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "issues": [i.to_dict() for i in self.issues],
        }


class AssemblyValidator:
    """
    Validates converted robot assemblies for UE5 compatibility.

    Checks:
    - USD file structure
    - Mesh geometry integrity
    - Material assignments
    - Joint hierarchy
    - Physics properties
    - UE5-specific requirements
    """

    # UE5 limits and recommendations
    UE5_MAX_VERTICES_PER_MESH = 500000
    UE5_MAX_BONES = 256
    UE5_RECOMMENDED_LOD_LEVELS = 4

    def __init__(
        self,
        level: ValidationLevel = ValidationLevel.STANDARD,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize validator.

        Args:
            level: Validation strictness level
            logger: Logger instance
        """
        self.level = level
        self.logger = logger or logging.getLogger(__name__)

    def validate(
        self, usd_path: str, level: Optional[ValidationLevel] = None
    ) -> AssemblyValidationResult:
        """
        Validate a USD assembly file.

        Args:
            usd_path: Path to USD file
            level: Override validation level

        Returns:
            AssemblyValidationResult with findings
        """
        validation_level = level or self.level

        result = AssemblyValidationResult(
            valid=True, level=validation_level, ue5_compatible=True, file_path=usd_path
        )

        # Check file exists
        if not os.path.exists(usd_path):
            result.add_issue(
                AssemblyIssue(
                    severity="error",
                    category="structure",
                    code="FILE_NOT_FOUND",
                    message=f"USD file not found: {usd_path}",
                )
            )
            return result

        try:
            stage = Usd.Stage.Open(usd_path)
            if not stage:
                result.add_issue(
                    AssemblyIssue(
                        severity="error",
                        category="structure",
                        code="CANNOT_OPEN_STAGE",
                        message="Failed to open USD stage",
                    )
                )
                return result

            # Gather statistics
            result.stats = self._gather_stats(stage)

            # Run validation checks
            self._validate_stage_structure(stage, result)
            self._validate_hierarchy(stage, result)
            self._validate_meshes(stage, result)

            if validation_level in [
                ValidationLevel.STANDARD,
                ValidationLevel.STRICT,
                ValidationLevel.UE5_READY,
            ]:
                self._validate_materials(stage, result)

            if validation_level in [ValidationLevel.STRICT, ValidationLevel.UE5_READY]:
                self._validate_physics(stage, result)

            if validation_level == ValidationLevel.UE5_READY:
                self._validate_ue5_specific(stage, result)

        except Exception as e:
            result.add_issue(
                AssemblyIssue(
                    severity="error",
                    category="structure",
                    code="VALIDATION_ERROR",
                    message=f"Validation error: {str(e)}",
                )
            )

        return result

    def _gather_stats(self, stage: "Usd.Stage") -> AssemblyStats:
        """Gather statistics about the assembly."""
        stats = AssemblyStats()
        max_depth = 0

        for prim in stage.Traverse():
            stats.total_prims += 1

            # Track depth
            depth = len(str(prim.GetPath()).split("/")) - 1
            max_depth = max(max_depth, depth)

            if prim.IsA(UsdGeom.Mesh):
                stats.mesh_count += 1

                mesh = UsdGeom.Mesh(prim)
                points = mesh.GetPointsAttr().Get()
                faces = mesh.GetFaceVertexCountsAttr().Get()

                if points:
                    stats.total_vertices += len(points)
                if faces:
                    stats.total_faces += len(faces)

            elif prim.IsA(UsdGeom.Xform):
                stats.xform_count += 1

            if prim.HasAPI(UsdPhysics.RevoluteJointAPI) or prim.HasAPI(
                UsdPhysics.PrismaticJointAPI
            ):
                stats.joint_count += 1

        # Count materials
        for prim in stage.Traverse():
            if prim.IsA(UsdShade.Material):
                stats.material_count += 1

        stats.hierarchy_depth = max_depth

        return stats

    def _validate_stage_structure(self, stage: "Usd.Stage", result: AssemblyValidationResult):
        """Validate basic USD stage structure."""
        # Check for default prim
        default_prim = stage.GetDefaultPrim()
        if not default_prim:
            result.add_issue(
                AssemblyIssue(
                    severity="warning",
                    category="structure",
                    code="NO_DEFAULT_PRIM",
                    message="Stage has no default prim set",
                    suggestion="Set a default prim for easier referencing",
                )
            )

        # Check up axis
        up_axis = stage.GetMetadata("upAxis")
        if up_axis != "Z":
            result.add_issue(
                AssemblyIssue(
                    severity="warning",
                    category="structure",
                    code="WRONG_UP_AXIS",
                    message=f"Up axis is '{up_axis}', UE5 expects 'Z'",
                    suggestion="Ensure stage uses Z-up coordinate system",
                )
            )

        # Check for empty stage
        if result.stats.total_prims == 0:
            result.add_issue(
                AssemblyIssue(
                    severity="error",
                    category="structure",
                    code="EMPTY_STAGE",
                    message="USD stage contains no prims",
                )
            )

    def _validate_hierarchy(self, stage: "Usd.Stage", result: AssemblyValidationResult):
        """Validate hierarchy structure."""
        # Check hierarchy depth
        if result.stats.hierarchy_depth > 50:
            result.add_issue(
                AssemblyIssue(
                    severity="warning",
                    category="hierarchy",
                    code="DEEP_HIERARCHY",
                    message=f"Hierarchy depth ({result.stats.hierarchy_depth}) is very deep",
                    suggestion="Consider flattening the hierarchy for better performance",
                )
            )

        # Look for orphaned prims
        root_prims = [p for p in stage.GetPseudoRoot().GetChildren()]

        if len(root_prims) > 10:
            result.add_issue(
                AssemblyIssue(
                    severity="info",
                    category="hierarchy",
                    code="MANY_ROOT_PRIMS",
                    message=f"Stage has {len(root_prims)} root prims",
                    suggestion="Consider organizing under a single root",
                )
            )

    def _validate_meshes(self, stage: "Usd.Stage", result: AssemblyValidationResult):
        """Validate mesh geometry."""
        for prim in stage.Traverse():
            if not prim.IsA(UsdGeom.Mesh):
                continue

            mesh = UsdGeom.Mesh(prim)
            prim_path = str(prim.GetPath())

            # Check points
            points = mesh.GetPointsAttr().Get()
            if not points or len(points) == 0:
                result.add_issue(
                    AssemblyIssue(
                        severity="error",
                        category="geometry",
                        code="EMPTY_MESH",
                        message="Mesh has no vertices",
                        prim_path=prim_path,
                    )
                )
                continue

            # Check vertex count
            if len(points) > self.UE5_MAX_VERTICES_PER_MESH:
                result.add_issue(
                    AssemblyIssue(
                        severity="warning",
                        category="geometry",
                        code="HIGH_VERTEX_COUNT",
                        message=f"Mesh has {len(points):,} vertices (UE5 limit: {self.UE5_MAX_VERTICES_PER_MESH:,})",
                        prim_path=prim_path,
                        suggestion="Consider simplifying or splitting the mesh",
                    )
                )

            # Check faces
            face_counts = mesh.GetFaceVertexCountsAttr().Get()
            face_indices = mesh.GetFaceVertexIndicesAttr().Get()

            if not face_counts or not face_indices:
                result.add_issue(
                    AssemblyIssue(
                        severity="error",
                        category="geometry",
                        code="NO_FACES",
                        message="Mesh has no face data",
                        prim_path=prim_path,
                    )
                )
                continue

            # Check for non-triangulated faces
            non_tri = [c for c in face_counts if c != 3]
            if non_tri:
                result.add_issue(
                    AssemblyIssue(
                        severity="info",
                        category="geometry",
                        code="NON_TRIANGULATED",
                        message=f"Mesh has {len(non_tri)} non-triangle faces",
                        prim_path=prim_path,
                        suggestion="UE5 will triangulate automatically",
                    )
                )

            # Check normals
            normals = mesh.GetNormalsAttr().Get()
            if not normals:
                result.add_issue(
                    AssemblyIssue(
                        severity="warning",
                        category="geometry",
                        code="NO_NORMALS",
                        message="Mesh has no normals",
                        prim_path=prim_path,
                        suggestion="Normals will be auto-generated but may not be optimal",
                    )
                )

    def _validate_materials(self, stage: "Usd.Stage", result: AssemblyValidationResult):
        """Validate material assignments."""
        meshes_without_materials = []

        for prim in stage.Traverse():
            if prim.IsA(UsdGeom.Mesh):
                # Check for material binding
                binding_api = UsdShade.MaterialBindingAPI(prim)
                bound_material = binding_api.ComputeBoundMaterial()

                if not bound_material[0]:  # Material prim
                    meshes_without_materials.append(str(prim.GetPath()))

        if meshes_without_materials:
            if len(meshes_without_materials) <= 5:
                msg = f"Meshes without materials: {', '.join(meshes_without_materials)}"
            else:
                msg = f"{len(meshes_without_materials)} meshes have no material assignment"

            result.add_issue(
                AssemblyIssue(
                    severity="info",
                    category="material",
                    code="NO_MATERIAL",
                    message=msg,
                    suggestion="UE5 will assign a default material",
                )
            )

        # Validate material structure
        for prim in stage.Traverse():
            if prim.IsA(UsdShade.Material):
                material = UsdShade.Material(prim)
                surface = material.GetSurfaceOutput()

                if not surface or not surface.GetConnectedSource():
                    result.add_issue(
                        AssemblyIssue(
                            severity="warning",
                            category="material",
                            code="INCOMPLETE_MATERIAL",
                            message="Material has no connected surface shader",
                            prim_path=str(prim.GetPath()),
                        )
                    )

    def _validate_physics(self, stage: "Usd.Stage", result: AssemblyValidationResult):
        """Validate physics properties."""
        has_physics = False

        for prim in stage.Traverse():
            if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                has_physics = True

            if prim.HasAPI(UsdPhysics.MassAPI):
                mass_api = UsdPhysics.MassAPI(prim)
                mass = mass_api.GetMassAttr().Get()

                if mass is not None and mass <= 0:
                    result.add_issue(
                        AssemblyIssue(
                            severity="warning",
                            category="physics",
                            code="INVALID_MASS",
                            message=f"Mass is {mass}, should be positive",
                            prim_path=str(prim.GetPath()),
                        )
                    )

        if not has_physics and result.stats.joint_count > 0:
            result.add_issue(
                AssemblyIssue(
                    severity="info",
                    category="physics",
                    code="NO_PHYSICS_SETUP",
                    message="Joints defined but no physics bodies found",
                    suggestion="Add UsdPhysics.RigidBodyAPI for physics simulation",
                )
            )

    def _validate_ue5_specific(self, stage: "Usd.Stage", result: AssemblyValidationResult):
        """Validate UE5-specific requirements."""
        # Check for LODs
        has_lods = False
        for prim in stage.Traverse():
            if "LOD" in prim.GetName():
                has_lods = True
                break

        if not has_lods and result.stats.total_vertices > 100000:
            result.add_issue(
                AssemblyIssue(
                    severity="info",
                    category="ue5",
                    code="NO_LODS",
                    message="High-poly model without LODs",
                    suggestion=f"Consider adding {self.UE5_RECOMMENDED_LOD_LEVELS} LOD levels for performance",
                )
            )

        # Check for collision meshes
        has_collision = False
        for prim in stage.Traverse():
            name = prim.GetName().lower()
            if "collision" in name or "ucx" in name:
                has_collision = True
                break
            if prim.HasAPI(UsdPhysics.CollisionAPI):
                has_collision = True
                break

        if not has_collision:
            result.add_issue(
                AssemblyIssue(
                    severity="info",
                    category="ue5",
                    code="NO_COLLISION",
                    message="No collision geometry found",
                    suggestion="Add collision meshes for physics interaction",
                )
            )

        # Check scale (UE5 uses centimeters)
        for prim in stage.Traverse():
            if prim.IsA(UsdGeom.Mesh):
                mesh = UsdGeom.Mesh(prim)
                points = mesh.GetPointsAttr().Get()

                if points and len(points) > 0:
                    # Check if scale seems correct
                    import math

                    max_extent = max(
                        max(abs(p[0]) for p in points),
                        max(abs(p[1]) for p in points),
                        max(abs(p[2]) for p in points),
                    )

                    if max_extent < 1.0:
                        result.add_issue(
                            AssemblyIssue(
                                severity="warning",
                                category="ue5",
                                code="SMALL_SCALE",
                                message=f"Model appears very small (max extent: {max_extent:.4f})",
                                prim_path=str(prim.GetPath()),
                                suggestion="UE5 uses centimeters - scale may need adjustment (100x for meters)",
                            )
                        )
                    break


def validate_assembly(
    usd_path: str, level: ValidationLevel = ValidationLevel.UE5_READY
) -> AssemblyValidationResult:
    """
    Convenience function to validate a USD assembly.

    Args:
        usd_path: Path to USD file
        level: Validation level

    Returns:
        AssemblyValidationResult
    """
    validator = AssemblyValidator(level=level)
    return validator.validate(usd_path)
