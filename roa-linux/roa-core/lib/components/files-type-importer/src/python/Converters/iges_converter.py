"""
IGES Converter - Convert IGES (Initial Graphics Exchange Specification) files to USD format
IGES is a legacy CAD format (ANSI Y14.26M) still widely used for:
- Legacy CAD data exchange
- Surface and curve data
- Simple geometry transfer

This converter uses:
- trimesh: For loading IGES files (via cascadio/OCP backend)
- pxr (OpenUSD): For generating USD output files

Note: IGES loading requires OpenCASCADE-based backends (cascadio/OCP).
"""

import os
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

# Mesh processing
import trimesh

# USD generation
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, Vt

from .base_converter import BaseConverter, ConversionResult


class IGESConverter(BaseConverter):
    """
    Converter for IGES (Initial Graphics Exchange Specification) files.

    IGES is a vendor-neutral format developed in 1979, still used for:
    - Legacy CAD system interoperability
    - Aerospace and automotive industries
    - Government and military applications
    - Simple geometry and surface data

    Features:
    - B-Rep to mesh conversion
    - Surface geometry handling
    - Wire-frame entity conversion where possible
    - Color extraction
    """

    def __init__(self, config: Optional[Dict] = None):
        """Initialize the IGES converter."""
        super().__init__(config)
        self.supported_extensions = [".iges", ".igs"]

        # Configuration
        self.scale_factor = self.config.get("scale_factor", 1.0)
        self.units = self.config.get("units", "mm")  # IGES default is often mm or inches

        # Check for IGES support
        self._iges_supported = False
        self._iges_backend = None
        self._check_iges_support()

    def _check_iges_support(self):
        """Check if IGES loading is supported."""
        # IGES uses same backends as STEP
        try:
            import cascadio

            self._iges_supported = True
            self._iges_backend = "cascadio"
            self._log_info("IGES support: cascadio backend available")
            return
        except ImportError:
            pass

        try:
            import OCP

            self._iges_supported = True
            self._iges_backend = "OCP"
            self._log_info("IGES support: OCP backend available")
            return
        except ImportError:
            pass

        # Try with trimesh anyway
        self._log_warning(
            "No dedicated IGES backend found. Install 'cascadio' or 'OCP' for full support."
        )
        self._iges_supported = True
        self._iges_backend = "trimesh"

    def convert(self, input_path: str, output_path: str, robot_name: str) -> ConversionResult:
        """
        Convert an IGES file to USD format.

        Args:
            input_path: Path to the IGES file
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

        if not self._iges_supported:
            return ConversionResult(
                success=False,
                error_message="IGES support not available. Install 'cascadio' or 'OCP' package.",
            )

        warnings = []
        parts = []
        materials_found = []

        try:
            self._log_info(f"Loading IGES file: {input_path}")
            self._log_info(f"Using backend: {self._iges_backend}")

            # Load IGES with trimesh
            loaded = trimesh.load(input_path, force=None)

            # Extract meshes
            meshes = self._extract_meshes(loaded, robot_name)

            if not meshes:
                return ConversionResult(
                    success=False, error_message="No geometry found in IGES file"
                )

            self._log_info(f"Extracted {len(meshes)} entity(ies)")

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

            # Set up stage (IGES typically uses Z-up)
            UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)

            # Set meters per unit based on IGES units
            meters_per_unit = self._get_meters_per_unit()
            UsdGeom.SetStageMetersPerUnit(stage, meters_per_unit)

            # Create root xform
            root_path = f"/{self._sanitize_name(robot_name)}"
            root_xform = UsdGeom.Xform.Define(stage, root_path)
            stage.SetDefaultPrim(root_xform.GetPrim())

            # Create materials scope
            materials_path = f"{root_path}/Materials"
            UsdGeom.Scope.Define(stage, materials_path)

            # Create default IGES material
            default_mat_path = f"{materials_path}/IGES_Material"
            self._create_default_material(stage, default_mat_path)
            materials_found.append("IGES_Material")

            # Process each mesh/entity
            for mesh_name, mesh, color in meshes:
                safe_name = self._sanitize_name(mesh_name)
                mesh_path = f"{root_path}/{safe_name}"
                parts.append(safe_name)

                vertex_count = len(mesh.vertices)
                face_count = len(mesh.faces)
                self._log_info(
                    f"Processing entity: {mesh_name} ({vertex_count} vertices, {face_count} faces)"
                )

                # Apply scale
                if self.scale_factor != 1.0:
                    mesh.apply_scale(self.scale_factor)

                # Create USD mesh
                usd_mesh = UsdGeom.Mesh.Define(stage, mesh_path)

                # Set vertices
                vertices = mesh.vertices.tolist()
                points = Vt.Vec3fArray(
                    [Gf.Vec3f(float(v[0]), float(v[1]), float(v[2])) for v in vertices]
                )
                usd_mesh.GetPointsAttr().Set(points)

                # Set faces
                faces = mesh.faces.astype(np.int32)
                face_vertex_counts = Vt.IntArray([3] * len(faces))
                face_vertex_indices = Vt.IntArray(faces.flatten().tolist())
                usd_mesh.GetFaceVertexCountsAttr().Set(face_vertex_counts)
                usd_mesh.GetFaceVertexIndicesAttr().Set(face_vertex_indices)

                # Set normals
                if hasattr(mesh, "vertex_normals") and mesh.vertex_normals is not None:
                    normals = mesh.vertex_normals.tolist()
                    usd_normals = Vt.Vec3fArray(
                        [Gf.Vec3f(float(n[0]), float(n[1]), float(n[2])) for n in normals]
                    )
                    usd_mesh.GetNormalsAttr().Set(usd_normals)
                    usd_mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)

                # Set subdivision scheme
                usd_mesh.GetSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)

                # Create and bind material
                if color is not None:
                    mat_name = f"{safe_name}_material"
                    mat_path = f"{materials_path}/{mat_name}"
                    self._create_colored_material(stage, mat_path, color)
                    mat_prim = stage.GetPrimAtPath(mat_path)
                    if mat_prim:
                        UsdShade.MaterialBindingAPI(usd_mesh.GetPrim()).Bind(
                            UsdShade.Material(mat_prim)
                        )
                    materials_found.append(mat_name)
                else:
                    # Use default material
                    mat_prim = stage.GetPrimAtPath(default_mat_path)
                    if mat_prim:
                        UsdShade.MaterialBindingAPI(usd_mesh.GetPrim()).Bind(
                            UsdShade.Material(mat_prim)
                        )

            # Save stage
            stage.GetRootLayer().Save()
            self._log_info(f"USD file saved: {output_path}")

            # Validate output
            if not self.validate_output(output_path):
                return ConversionResult(success=False, error_message="Output validation failed")

            return ConversionResult(
                success=True,
                output_path=output_path,
                format="usd",
                parts=parts,
                materials=materials_found,
                warnings=warnings,
            )

        except ImportError as e:
            return ConversionResult(
                success=False,
                error_message=f"Missing IGES support library: {str(e)}. Install 'cascadio' or 'OCP'.",
            )
        except Exception as e:
            self._log_error(f"Conversion error: {e}")
            import traceback

            traceback.print_exc()
            return ConversionResult(
                success=False, error_message=f"IGES conversion failed: {str(e)}"
            )

    def _get_meters_per_unit(self) -> float:
        """Get meters per unit based on configured units."""
        unit_map = {
            "mm": 0.001,
            "cm": 0.01,
            "m": 1.0,
            "in": 0.0254,
            "ft": 0.3048,
            "inch": 0.0254,
            "feet": 0.3048,
            "millimeter": 0.001,
            "centimeter": 0.01,
            "meter": 1.0,
        }
        return unit_map.get(self.units.lower(), 0.001)  # Default to mm

    def _extract_meshes(self, loaded, robot_name: str) -> List[tuple]:
        """Extract meshes from loaded trimesh object."""
        meshes = []

        if isinstance(loaded, trimesh.Scene):
            for i, (name, geom) in enumerate(loaded.geometry.items()):
                if isinstance(geom, trimesh.Trimesh):
                    color = self._extract_color(geom)
                    meshes.append((name or f"entity_{i}", geom, color))
        elif isinstance(loaded, trimesh.Trimesh):
            color = self._extract_color(loaded)
            meshes.append((robot_name, loaded, color))

        return meshes

    def _extract_color(self, mesh: trimesh.Trimesh) -> Optional[List[float]]:
        """Extract color from mesh visual."""
        try:
            if hasattr(mesh, "visual") and mesh.visual is not None:
                if hasattr(mesh.visual, "main_color") and mesh.visual.main_color is not None:
                    color = mesh.visual.main_color
                    if hasattr(color, "__iter__"):
                        color = [float(c) / 255.0 if c > 1 else float(c) for c in color[:4]]
                        return color
        except:
            pass
        return None

    def _create_default_material(self, stage, mat_path: str):
        """Create a default IGES material (engineering gray)."""
        material = UsdShade.Material.Define(stage, mat_path)
        shader_path = f"{mat_path}/PreviewSurface"
        shader = UsdShade.Shader.Define(stage, shader_path)
        shader.CreateIdAttr("UsdPreviewSurface")

        # Engineering-like appearance
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(0.65, 0.65, 0.7)
        )
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.35)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.15)

        shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
        material.CreateSurfaceOutput().ConnectToSource(
            shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
        )

        return material

    def _create_colored_material(self, stage, mat_path: str, color: List[float]):
        """Create a USD material with specified color."""
        material = UsdShade.Material.Define(stage, mat_path)
        shader_path = f"{mat_path}/PreviewSurface"
        shader = UsdShade.Shader.Define(stage, shader_path)
        shader.CreateIdAttr("UsdPreviewSurface")

        if len(color) >= 3:
            shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
                Gf.Vec3f(float(color[0]), float(color[1]), float(color[2]))
            )
        if len(color) > 3:
            shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(float(color[3]))

        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.4)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.1)

        shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
        material.CreateSurfaceOutput().ConnectToSource(
            shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
        )

        return material

    def _sanitize_name(self, name: str) -> str:
        """Sanitize a name for use in USD paths."""
        import re

        sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        if sanitized and sanitized[0].isdigit():
            sanitized = "_" + sanitized
        return sanitized or "unnamed"
