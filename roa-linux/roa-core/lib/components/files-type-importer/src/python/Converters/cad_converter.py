"""
CAD Format Converter (STEP, IGES)

Converts CAD files to USD with optional kinematic assembly definition.

Features:
1. Auto-detect format (STEP vs IGES)
2. Skip converter if not CAD (lightweight detection)
3. Tessellation with quality presets
4. User-defined assembly/kinematics via Python sequence

Dependencies:
    conda install -c conda-forge pythonocc-core
    or
    pip install pythonocc-core  # May need build from source
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class CADFormat(Enum):
    """Supported CAD formats."""

    STEP = "step"
    IGES = "iges"
    UNKNOWN = "unknown"


class TessellationQuality(Enum):
    """Tessellation quality presets."""

    FAST = "fast"  # Quick preview, lower quality
    BALANCED = "balanced"  # Good balance (default)
    HIGH = "high"  # High quality, slower
    ULTRA = "ultra"  # Maximum quality, very slow


@dataclass
class CADPart:
    """Represents a part from CAD file."""

    name: str
    shape: object  # OCC shape
    transform: List[float] = None  # 4x4 matrix
    material: Optional[str] = None
    is_assembly: bool = False
    children: List["CADPart"] = field(default_factory=list)


@dataclass
class JointDefinition:
    """User-defined joint between CAD parts."""

    name: str
    joint_type: str  # 'revolute', 'prismatic', 'fixed', 'continuous'
    parent_part: str
    child_part: str
    origin: Tuple[float, float, float] = (0, 0, 0)
    axis: Tuple[float, float, float] = (0, 0, 1)
    limits: Optional[Tuple[float, float]] = None  # (lower, upper)


@dataclass
class ConversionResult:
    """Result of CAD conversion."""

    success: bool
    output_path: Optional[str] = None
    parts: List[str] = field(default_factory=list)
    hierarchy: Optional[Dict] = None
    warnings: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    conversion_time: float = 0.0


class CADConverter:
    """
    Converts STEP/IGES CAD files to USD.

    Features:
    - Auto-detects CAD format from file content
    - Lightweight check to skip non-CAD files quickly
    - Tessellation with configurable quality
    - Python sequence for defining assembly/kinematics

    Usage:
        converter = CADConverter()

        # Simple conversion
        result = converter.convert('robot.step', 'robot.usd')

        # With kinematics definition
        def define_kinematics(parts):
            return [
                JointDefinition(
                    name='joint1',
                    joint_type='revolute',
                    parent_part='base',
                    child_part='link1',
                    axis=(0, 0, 1),
                    limits=(-3.14, 3.14)
                ),
                # ... more joints
            ]

        result = converter.convert('robot.step', 'robot.usd',
                                  kinematics_callback=define_kinematics)
    """

    # File signatures for quick format detection
    STEP_SIGNATURES = [b"ISO-10303-21", b"STEP", b"END-ISO-10303"]
    IGES_SIGNATURES = [b"                                        S", b"IGES"]

    # Tessellation parameters for each quality preset
    TESSELLATION_PARAMS = {
        TessellationQuality.FAST: {
            "linear_deflection": 0.5,
            "angular_deflection": 0.5,
            "relative": True,
        },
        TessellationQuality.BALANCED: {
            "linear_deflection": 0.1,
            "angular_deflection": 0.3,
            "relative": True,
        },
        TessellationQuality.HIGH: {
            "linear_deflection": 0.01,
            "angular_deflection": 0.1,
            "relative": True,
        },
        TessellationQuality.ULTRA: {
            "linear_deflection": 0.001,
            "angular_deflection": 0.05,
            "relative": False,
        },
    }

    def __init__(
        self,
        quality: TessellationQuality = TessellationQuality.BALANCED,
        show_progress: bool = True,
    ):
        """
        Initialize CAD converter.

        Args:
            quality: Tessellation quality preset
            show_progress: Whether to show progress notifications
        """
        self.quality = quality
        self.show_progress = show_progress
        self._occ_available = self._check_occ_availability()

    def _check_occ_availability(self) -> bool:
        """Check if pythonocc-core is installed."""
        try:
            from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
            from OCC.Core.IGESControl import IGESControl_Reader
            from OCC.Core.STEPControl import STEPControl_Reader

            return True
        except ImportError:
            logger.warning(
                "pythonocc-core not installed. CAD conversion unavailable. "
                "Install with: conda install -c conda-forge pythonocc-core"
            )
            return False

    @staticmethod
    def is_cad_file(file_path: str) -> Tuple[bool, CADFormat]:
        """
        Quick check if file is a CAD format.

        This is a lightweight check that reads only the first few KB
        to detect format without full parsing.

        Args:
            file_path: Path to file

        Returns:
            (is_cad, format) tuple
        """
        try:
            # Check extension first (fast)
            ext = Path(file_path).suffix.lower()
            if ext in [".step", ".stp"]:
                return True, CADFormat.STEP
            elif ext in [".iges", ".igs"]:
                return True, CADFormat.IGES

            # Check file signature (slightly slower but more reliable)
            with open(file_path, "rb") as f:
                header = f.read(1024)

            for sig in CADConverter.STEP_SIGNATURES:
                if sig in header:
                    return True, CADFormat.STEP

            for sig in CADConverter.IGES_SIGNATURES:
                if sig in header:
                    return True, CADFormat.IGES

            return False, CADFormat.UNKNOWN

        except Exception:
            return False, CADFormat.UNKNOWN

    def convert(
        self,
        input_path: str,
        output_path: str,
        robot_name: Optional[str] = None,
        kinematics_callback: Optional[Callable[[List[CADPart]], List[JointDefinition]]] = None,
    ) -> ConversionResult:
        """
        Convert CAD file to USD.

        Args:
            input_path: Path to STEP/IGES file
            output_path: Path for output USD file
            robot_name: Name for the robot (auto-generated if not provided)
            kinematics_callback: Optional function to define joints between parts

        Returns:
            ConversionResult with conversion details
        """
        start_time = time.time()
        warnings = []

        # Quick format check
        is_cad, cad_format = self.is_cad_file(input_path)
        if not is_cad:
            return ConversionResult(
                success=False,
                error_message=f"Not a recognized CAD format: {input_path}",
                conversion_time=time.time() - start_time,
            )

        if not self._occ_available:
            return ConversionResult(
                success=False,
                error_message="pythonocc-core not installed. Run: conda install -c conda-forge pythonocc-core",
                conversion_time=time.time() - start_time,
            )

        robot_name = robot_name or Path(input_path).stem

        if self.show_progress:
            self._notify_user(
                f"🔧 CAD Import: Processing {Path(input_path).name}\n"
                f"This may take a moment for complex models..."
            )

        try:
            # Step 1: Load CAD file
            logger.info(f"Loading CAD file: {input_path}")
            parts = self._load_cad_file(input_path, cad_format)

            if not parts:
                return ConversionResult(
                    success=False,
                    error_message="No geometry found in CAD file",
                    conversion_time=time.time() - start_time,
                )

            logger.info(f"Found {len(parts)} parts in CAD file")

            # Step 2: Get kinematics definition (if callback provided)
            joints = []
            if kinematics_callback:
                try:
                    joints = kinematics_callback(parts)
                    logger.info(f"User defined {len(joints)} joints")
                except Exception as e:
                    warnings.append(f"Kinematics callback failed: {e}. Using static assembly.")

            # Step 3: Tessellate all parts
            logger.info(f"Tessellating with {self.quality.value} quality...")
            meshes = self._tessellate_parts(parts)

            # Step 4: Export to USD
            logger.info(f"Exporting to USD: {output_path}")
            hierarchy = self._export_to_usd(
                meshes=meshes,
                parts=parts,
                joints=joints,
                output_path=output_path,
                robot_name=robot_name,
            )

            conversion_time = time.time() - start_time

            if self.show_progress:
                self._notify_user(
                    f"✅ CAD Import Complete!\n"
                    f"  Parts: {len(parts)}\n"
                    f"  Joints: {len(joints)}\n"
                    f"  Time: {conversion_time:.1f}s"
                )

            return ConversionResult(
                success=True,
                output_path=output_path,
                parts=[p.name for p in parts],
                hierarchy=hierarchy,
                warnings=warnings,
                conversion_time=conversion_time,
            )

        except Exception as e:
            logger.error(f"CAD conversion failed: {e}")
            return ConversionResult(
                success=False,
                error_message=str(e),
                warnings=warnings,
                conversion_time=time.time() - start_time,
            )

    def _load_cad_file(self, file_path: str, cad_format: CADFormat) -> List[CADPart]:
        """Load parts from CAD file."""
        from OCC.Core.IFSelect import IFSelect_RetDone
        from OCC.Core.IGESControl import IGESControl_Reader
        from OCC.Core.STEPControl import STEPControl_Reader
        from OCC.Core.TopAbs import TopAbs_SHELL, TopAbs_SOLID
        from OCC.Core.TopExp import TopExp_Explorer
        from OCC.Core.TopoDS import topods

        parts = []

        if cad_format == CADFormat.STEP:
            reader = STEPControl_Reader()
            status = reader.ReadFile(file_path)
        else:  # IGES
            reader = IGESControl_Reader()
            status = reader.ReadFile(file_path)

        if status != IFSelect_RetDone:
            raise ValueError(f"Failed to read CAD file: {file_path}")

        reader.TransferRoots()
        shape = reader.OneShape()

        # Extract individual solids
        explorer = TopExp_Explorer(shape, TopAbs_SOLID)
        part_idx = 0

        while explorer.More():
            solid = topods.Solid(explorer.Current())
            part_name = f"Part_{part_idx:03d}"

            # Try to get name from STEP entity
            if cad_format == CADFormat.STEP:
                try:
                    from OCC.Core.STEPCAFControl import STEPCAFControl_Reader

                    # Could extract product names here
                except ImportError:
                    pass

            parts.append(CADPart(name=part_name, shape=solid, is_assembly=False))

            part_idx += 1
            explorer.Next()

        # If no solids, try shells
        if not parts:
            explorer = TopExp_Explorer(shape, TopAbs_SHELL)
            while explorer.More():
                shell = topods.Shell(explorer.Current())
                parts.append(CADPart(name=f"Shell_{part_idx:03d}", shape=shell, is_assembly=False))
                part_idx += 1
                explorer.Next()

        return parts

    def _tessellate_parts(self, parts: List[CADPart]) -> List[Dict]:
        """Tessellate CAD parts to triangle meshes."""
        from OCC.Core.BRep import BRep_Tool
        from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
        from OCC.Core.TopAbs import TopAbs_FACE
        from OCC.Core.TopExp import TopExp_Explorer
        from OCC.Core.TopLoc import TopLoc_Location
        from OCC.Core.TopoDS import topods

        params = self.TESSELLATION_PARAMS[self.quality]
        meshes = []

        for part in parts:
            # Tessellate
            mesh = BRepMesh_IncrementalMesh(
                part.shape,
                params["linear_deflection"],
                params["relative"],
                params["angular_deflection"],
            )
            mesh.Perform()

            if not mesh.IsDone():
                logger.warning(f"Tessellation failed for {part.name}")
                continue

            # Extract triangles
            vertices = []
            indices = []
            vertex_offset = 0

            explorer = TopExp_Explorer(part.shape, TopAbs_FACE)
            while explorer.More():
                face = topods.Face(explorer.Current())
                location = TopLoc_Location()
                triangulation = BRep_Tool.Triangulation(face, location)

                if triangulation:
                    # Get transformation
                    trsf = location.Transformation()

                    # Get nodes
                    num_nodes = triangulation.NbNodes()
                    for i in range(1, num_nodes + 1):
                        pnt = triangulation.Node(i)
                        pnt.Transform(trsf)
                        vertices.extend([pnt.X(), pnt.Y(), pnt.Z()])

                    # Get triangles
                    num_tris = triangulation.NbTriangles()
                    for i in range(1, num_tris + 1):
                        tri = triangulation.Triangle(i)
                        n1, n2, n3 = tri.Get()
                        indices.extend(
                            [
                                vertex_offset + n1 - 1,
                                vertex_offset + n2 - 1,
                                vertex_offset + n3 - 1,
                            ]
                        )

                    vertex_offset += num_nodes

                explorer.Next()

            if vertices:
                meshes.append(
                    {
                        "name": part.name,
                        "vertices": vertices,
                        "indices": indices,
                        "vertex_count": len(vertices) // 3,
                        "face_count": len(indices) // 3,
                    }
                )

        return meshes

    def _export_to_usd(
        self,
        meshes: List[Dict],
        parts: List[CADPart],
        joints: List[JointDefinition],
        output_path: str,
        robot_name: str,
    ) -> Dict:
        """Export tessellated meshes to USD with physics."""
        from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, Vt

        # Create stage
        stage = Usd.Stage.CreateNew(output_path)
        stage.SetMetadata("upAxis", "Z")
        stage.SetMetadata("metersPerUnit", 1.0)

        # Create root xform
        root_path = f"/{robot_name}"
        root_prim = UsdGeom.Xform.Define(stage, root_path)
        stage.SetDefaultPrim(root_prim.GetPrim())

        # Apply articulation root if we have joints
        if joints:
            UsdPhysics.ArticulationRootAPI.Apply(root_prim.GetPrim())

        # Build hierarchy
        hierarchy = {
            "robot_name": robot_name,
            "parts": [],
            "joints": [],
            "source": "CAD",
        }

        # Create links folder
        links_path = f"{root_path}/Links"
        UsdGeom.Scope.Define(stage, links_path)

        # Export each mesh as a link
        part_prims = {}
        for mesh_data in meshes:
            part_name = mesh_data["name"]
            link_path = f"{links_path}/{part_name}"

            # Create link xform
            link_xform = UsdGeom.Xform.Define(stage, link_path)

            # Create mesh
            mesh_path = f"{link_path}/Geometry"
            usd_mesh = UsdGeom.Mesh.Define(stage, mesh_path)

            # Set mesh data
            vertices = mesh_data["vertices"]
            points = [
                (vertices[i], vertices[i + 1], vertices[i + 2]) for i in range(0, len(vertices), 3)
            ]
            usd_mesh.GetPointsAttr().Set(Vt.Vec3fArray(points))

            indices = mesh_data["indices"]
            usd_mesh.GetFaceVertexIndicesAttr().Set(Vt.IntArray(indices))
            usd_mesh.GetFaceVertexCountsAttr().Set(Vt.IntArray([3] * (len(indices) // 3)))

            # Add physics
            UsdPhysics.RigidBodyAPI.Apply(link_xform.GetPrim())
            UsdPhysics.CollisionAPI.Apply(usd_mesh.GetPrim())
            UsdPhysics.MeshCollisionAPI.Apply(usd_mesh.GetPrim())

            part_prims[part_name] = link_xform

            hierarchy["parts"].append(
                {
                    "name": part_name,
                    "vertices": mesh_data["vertex_count"],
                    "faces": mesh_data["face_count"],
                }
            )

        # Create joints
        if joints:
            joints_path = f"{root_path}/Joints"
            UsdGeom.Scope.Define(stage, joints_path)

            for joint_def in joints:
                joint_path = f"{joints_path}/{joint_def.name}"

                parent_path = f"{links_path}/{joint_def.parent_part}"
                child_path = f"{links_path}/{joint_def.child_part}"

                if joint_def.joint_type == "revolute":
                    joint = UsdPhysics.RevoluteJoint.Define(stage, joint_path)
                    joint.GetAxisAttr().Set(
                        "X" if joint_def.axis[0] > 0.5 else "Y" if joint_def.axis[1] > 0.5 else "Z"
                    )
                    if joint_def.limits:
                        joint.GetLowerLimitAttr().Set(joint_def.limits[0] * 57.2958)  # to degrees
                        joint.GetUpperLimitAttr().Set(joint_def.limits[1] * 57.2958)
                elif joint_def.joint_type == "prismatic":
                    joint = UsdPhysics.PrismaticJoint.Define(stage, joint_path)
                    joint.GetAxisAttr().Set(
                        "X" if joint_def.axis[0] > 0.5 else "Y" if joint_def.axis[1] > 0.5 else "Z"
                    )
                    if joint_def.limits:
                        joint.GetLowerLimitAttr().Set(joint_def.limits[0])
                        joint.GetUpperLimitAttr().Set(joint_def.limits[1])
                else:  # fixed
                    joint = UsdPhysics.FixedJoint.Define(stage, joint_path)

                # Set body relationships
                joint.GetBody0Rel().SetTargets([Sdf.Path(parent_path)])
                joint.GetBody1Rel().SetTargets([Sdf.Path(child_path)])

                # Set local pose
                joint.GetLocalPos0Attr().Set(Gf.Vec3f(*joint_def.origin))
                joint.GetLocalPos1Attr().Set(Gf.Vec3f(0, 0, 0))

                hierarchy["joints"].append(
                    {
                        "name": joint_def.name,
                        "type": joint_def.joint_type,
                        "parent": joint_def.parent_part,
                        "child": joint_def.child_part,
                        "axis": list(joint_def.axis),
                        "limits": list(joint_def.limits) if joint_def.limits else None,
                    }
                )

        stage.Save()
        return hierarchy

    def _notify_user(self, message: str):
        """Show notification to user (for long operations)."""
        # This would integrate with FTI's notification system
        logger.info(message.replace("\n", " | "))

    def validate_output(self, output_path: str) -> bool:
        """Validate the generated USD file."""
        try:
            from pxr import Usd

            stage = Usd.Stage.Open(output_path)
            return stage is not None and stage.GetDefaultPrim()
        except Exception:
            return False


# =============================================
# CAD Kinematics Definition Helpers
# =============================================


def create_simple_arm_kinematics(parts: List[CADPart]) -> List[JointDefinition]:
    """
    Example kinematic definition for a simple robotic arm.

    Users can use this as a template for their own definitions.
    """
    # Sort parts by name/index
    part_names = sorted([p.name for p in parts])

    if len(part_names) < 2:
        return []

    joints = []

    # Create chain: base -> link1 -> link2 -> ...
    for i in range(len(part_names) - 1):
        joints.append(
            JointDefinition(
                name=f"joint_{i+1}",
                joint_type="revolute",
                parent_part=part_names[i],
                child_part=part_names[i + 1],
                axis=(0, 0, 1),  # Default Z-axis rotation
                limits=(-3.14159, 3.14159),  # Full rotation
            )
        )

    return joints


def create_kinematics_from_json(
    json_path: str,
) -> Callable[[List[CADPart]], List[JointDefinition]]:
    """
    Create kinematics callback from JSON definition file.

    JSON format:
    {
        "joints": [
            {
                "name": "joint1",
                "type": "revolute",
                "parent": "Part_000",
                "child": "Part_001",
                "origin": [0, 0, 0.1],
                "axis": [0, 0, 1],
                "limits": [-3.14, 3.14]
            }
        ]
    }
    """

    def callback(parts: List[CADPart]) -> List[JointDefinition]:
        with open(json_path, "r") as f:
            data = json.load(f)

        joints = []
        for j in data.get("joints", []):
            joints.append(
                JointDefinition(
                    name=j["name"],
                    joint_type=j.get("type", "revolute"),
                    parent_part=j["parent"],
                    child_part=j["child"],
                    origin=tuple(j.get("origin", [0, 0, 0])),
                    axis=tuple(j.get("axis", [0, 0, 1])),
                    limits=tuple(j["limits"]) if j.get("limits") else None,
                )
            )

        return joints

    return callback


# Interactive kinematics wizard (for future GUI integration)
class KinematicsWizard:
    """
    Interactive wizard for defining robot kinematics from CAD parts.

    This will integrate with the ROA GUI to let users:
    1. See list of detected parts
    2. Drag & drop to create parent-child relationships
    3. Configure joint types and limits
    4. Preview the kinematic chain
    """

    def __init__(self, parts: List[CADPart]):
        self.parts = parts
        self.joints: List[JointDefinition] = []
        self._callbacks = []

    def add_joint(
        self,
        name: str,
        joint_type: str,
        parent_part: str,
        child_part: str,
        origin: Tuple[float, float, float] = (0, 0, 0),
        axis: Tuple[float, float, float] = (0, 0, 1),
        limits: Optional[Tuple[float, float]] = None,
    ):
        """Add a joint definition."""
        self.joints.append(
            JointDefinition(
                name=name,
                joint_type=joint_type,
                parent_part=parent_part,
                child_part=child_part,
                origin=origin,
                axis=axis,
                limits=limits,
            )
        )
        self._notify_changed()

    def remove_joint(self, name: str):
        """Remove a joint by name."""
        self.joints = [j for j in self.joints if j.name != name]
        self._notify_changed()

    def get_kinematics(self) -> List[JointDefinition]:
        """Get the final joint definitions."""
        return self.joints

    def export_to_json(self, output_path: str):
        """Export kinematics definition to JSON."""
        data = {
            "joints": [
                {
                    "name": j.name,
                    "type": j.joint_type,
                    "parent": j.parent_part,
                    "child": j.child_part,
                    "origin": list(j.origin),
                    "axis": list(j.axis),
                    "limits": list(j.limits) if j.limits else None,
                }
                for j in self.joints
            ]
        }

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

    def on_changed(self, callback: Callable):
        """Register callback for changes."""
        self._callbacks.append(callback)

    def _notify_changed(self):
        for cb in self._callbacks:
            cb(self.joints)
