"""
STL Converter - Convert STL files to USD format
STL (Stereolithography) is a common 3D printing and CAD format

This converter uses:
- trimesh: For loading and processing STL mesh data
- pxr (OpenUSD): For generating USD output files
"""

import os
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

# Mesh processing
import trimesh

# USD generation
from pxr import Gf, Sdf, Usd, UsdGeom, Vt

from .base_converter import BaseConverter, ConversionResult


class STLConverter(BaseConverter):
    """
    Converter for STL (Stereolithography) files.

    STL is a simple mesh format commonly used in 3D printing and CAD.
    Supports both ASCII and binary STL formats.

    Converts STL meshes to USD format with:
    - Full vertex/face geometry
    - Computed normals
    - Default material (STL has no material info)
    - Proper coordinate system transform (Z-up to UE5 Z-up)
    """

    def __init__(self, config: Optional[Dict] = None):
        """Initialize the STL converter."""
        super().__init__(config)
        self.supported_extensions = [".stl"]

        # Configuration options
        self.scale_factor = self.config.get("scale_factor", 1.0)  # Default: no scaling
        self.up_axis = self.config.get("up_axis", "Z")  # Z-up is standard

    def convert(self, input_path: str, output_path: str, robot_name: str) -> ConversionResult:
        """
        Convert an STL file to USD format.

        Args:
            input_path: Path to the STL file
            output_path: Path for the output USD file
            robot_name: Name of the robot/part

        Returns:
            ConversionResult with conversion details
        """
        # Validate input
        if not self.validate_input(input_path):
            return ConversionResult(
                success=False, error_message=f"Invalid input file: {input_path}"
            )

        warnings = []

        try:
            # Load STL mesh using trimesh
            self._log_info(f"Loading STL file: {input_path}")
            mesh = trimesh.load(input_path, force="mesh")

            if mesh is None or not hasattr(mesh, "vertices"):
                return ConversionResult(
                    success=False, error_message="Failed to load mesh from STL file"
                )

            # Get mesh statistics
            vertex_count = len(mesh.vertices)
            face_count = len(mesh.faces)
            self._log_info(f"Loaded mesh: {vertex_count} vertices, {face_count} faces")

            # Validate mesh
            if vertex_count == 0 or face_count == 0:
                return ConversionResult(success=False, error_message="STL file contains empty mesh")

            # Apply scale if configured
            if self.scale_factor != 1.0:
                mesh.apply_scale(self.scale_factor)
                self._log_info(f"Applied scale factor: {self.scale_factor}")

            # Ensure output directory exists
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)

            # Create USD stage
            self._log_info(f"Creating USD file: {output_path}")
            stage = Usd.Stage.CreateNew(output_path)

            if stage is None:
                return ConversionResult(
                    success=False,
                    error_message=f"Failed to create USD stage at {output_path}",
                )

            # Set up axis (UE5 uses Z-up)
            UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
            UsdGeom.SetStageMetersPerUnit(stage, 1.0)  # Meters

            # Create root xform
            root_path = f"/{robot_name}"
            root_xform = UsdGeom.Xform.Define(stage, root_path)
            stage.SetDefaultPrim(root_xform.GetPrim())

            # Create mesh prim
            mesh_path = f"{root_path}/mesh"
            usd_mesh = UsdGeom.Mesh.Define(stage, mesh_path)

            # Set mesh geometry
            # Vertices (as Vt.Vec3fArray) - convert to native Python float
            vertices = mesh.vertices.tolist()
            points = Vt.Vec3fArray(
                [Gf.Vec3f(float(v[0]), float(v[1]), float(v[2])) for v in vertices]
            )
            usd_mesh.GetPointsAttr().Set(points)

            # Faces (USD uses face vertex counts + indices)
            faces = mesh.faces.astype(np.int32)
            face_vertex_counts = Vt.IntArray([3] * len(faces))  # All triangles
            face_vertex_indices = Vt.IntArray(faces.flatten().tolist())
            usd_mesh.GetFaceVertexCountsAttr().Set(face_vertex_counts)
            usd_mesh.GetFaceVertexIndicesAttr().Set(face_vertex_indices)

            # Normals (per-vertex)
            if hasattr(mesh, "vertex_normals") and mesh.vertex_normals is not None:
                normals = mesh.vertex_normals.tolist()
                usd_normals = Vt.Vec3fArray(
                    [Gf.Vec3f(float(n[0]), float(n[1]), float(n[2])) for n in normals]
                )
                usd_mesh.GetNormalsAttr().Set(usd_normals)
                usd_mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)

            # Set mesh subdivision scheme to none (keep as triangles)
            usd_mesh.GetSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)

            # Add extent (bounding box)
            extent = self._compute_extent(mesh)
            usd_mesh.GetExtentAttr().Set(extent)

            # Save the stage
            stage.GetRootLayer().Save()
            self._log_info(f"USD file saved: {output_path}")

            # Validate output
            if not self.validate_output(output_path):
                return ConversionResult(success=False, error_message="Output validation failed")

            # STL doesn't contain material information
            warnings.append(
                "STL format does not contain material information - using default material"
            )

            # Add mesh statistics to warnings for info
            warnings.append(f"Mesh contains {vertex_count} vertices and {face_count} faces")

            return ConversionResult(
                success=True,
                output_path=output_path,
                format="usd",
                parts=[robot_name],
                materials=["default"],
                warnings=warnings,
            )

        except ImportError as e:
            self._log_error(f"Missing dependency: {e}")
            return ConversionResult(
                success=False,
                error_message=f"Missing required library: {str(e)}. Install with: pip install trimesh usd-core",
            )
        except Exception as e:
            self._log_error(f"Conversion error: {e}")
            import traceback

            traceback.print_exc()
            return ConversionResult(success=False, error_message=f"Conversion failed: {str(e)}")

    def _compute_extent(self, mesh: trimesh.Trimesh) -> Vt.Vec3fArray:
        """
        Compute the bounding box extent for USD.

        Args:
            mesh: The trimesh mesh

        Returns:
            Vt.Vec3fArray with min and max bounds
        """
        bounds = mesh.bounds.tolist()  # [[min_x, min_y, min_z], [max_x, max_y, max_z]]
        return Vt.Vec3fArray(
            [
                Gf.Vec3f(float(bounds[0][0]), float(bounds[0][1]), float(bounds[0][2])),
                Gf.Vec3f(float(bounds[1][0]), float(bounds[1][1]), float(bounds[1][2])),
            ]
        )

    def _is_ascii_stl(self, file_path: str) -> bool:
        """
        Detect if STL file is ASCII or binary format.

        Args:
            file_path: Path to the STL file

        Returns:
            True if ASCII, False if binary
        """
        with open(file_path, "rb") as f:
            # Read first 80 bytes
            header = f.read(80)
            # ASCII STL starts with 'solid '
            if header.startswith(b"solid "):
                # Verify it's truly ASCII by checking if it's valid UTF-8
                try:
                    header.decode("utf-8")
                    return True
                except UnicodeDecodeError:
                    return False
        return False
