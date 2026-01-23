"""
OBJ Converter - Convert Wavefront OBJ files to USD format
OBJ is a universal 3D geometry format widely supported

This converter uses:
- trimesh: For loading OBJ mesh data with MTL materials
- pxr (OpenUSD): For generating USD output files with materials
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# Mesh processing
import trimesh

# USD generation
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, Vt

from .base_converter import BaseConverter, ConversionResult


class OBJConverter(BaseConverter):
    """
    Converter for Wavefront OBJ files.

    OBJ is a universal geometry definition file format that supports
    vertices, normals, texture coordinates, and material references (MTL).

    Converts OBJ meshes to USD format with:
    - Full vertex/face geometry
    - Vertex normals
    - UV texture coordinates
    - Material definitions from MTL files
    - Multiple objects/groups as separate meshes
    """

    def __init__(self, config: Optional[Dict] = None):
        """Initialize the OBJ converter."""
        super().__init__(config)
        self.supported_extensions = [".obj"]

        # Configuration options
        self.scale_factor = self.config.get("scale_factor", 1.0)
        self.merge_objects = self.config.get("merge_objects", False)

    def convert(self, input_path: str, output_path: str, robot_name: str) -> ConversionResult:
        """
        Convert an OBJ file to USD format.

        Args:
            input_path: Path to the OBJ file
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
        parts = []
        materials_found = []

        try:
            # Load OBJ mesh using trimesh
            self._log_info(f"Loading OBJ file: {input_path}")

            # trimesh may return a Scene if multiple objects, or Trimesh if single
            loaded = trimesh.load(input_path)

            # Normalize to a list of (name, mesh) pairs
            meshes = self._extract_meshes(loaded, robot_name)

            if not meshes:
                return ConversionResult(
                    success=False,
                    error_message="Failed to load any meshes from OBJ file",
                )

            self._log_info(f"Loaded {len(meshes)} mesh(es)")

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
            UsdGeom.SetStageMetersPerUnit(stage, 1.0)

            # Create root xform
            root_path = f"/{robot_name}"
            root_xform = UsdGeom.Xform.Define(stage, root_path)
            stage.SetDefaultPrim(root_xform.GetPrim())

            # Create materials scope
            materials_path = f"{root_path}/Materials"
            UsdGeom.Scope.Define(stage, materials_path)

            # Track created materials to avoid duplicates
            created_materials = {}

            # Process each mesh
            for mesh_name, mesh in meshes:
                # Sanitize mesh name for USD path
                safe_name = self._sanitize_name(mesh_name)
                mesh_path = f"{root_path}/{safe_name}"
                parts.append(safe_name)

                self._log_info(
                    f"Processing mesh: {mesh_name} ({len(mesh.vertices)} vertices, {len(mesh.faces)} faces)"
                )

                # Apply scale if configured
                if self.scale_factor != 1.0:
                    mesh.apply_scale(self.scale_factor)

                # Create USD mesh
                usd_mesh = UsdGeom.Mesh.Define(stage, mesh_path)

                # Set vertices (convert to native Python float)
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

                # Set UVs if available (convert to native float)
                if hasattr(mesh.visual, "uv") and mesh.visual.uv is not None:
                    uvs = mesh.visual.uv.tolist()
                    usd_uvs = Vt.Vec2fArray([Gf.Vec2f(float(uv[0]), float(uv[1])) for uv in uvs])
                    primvar_api = UsdGeom.PrimvarsAPI(usd_mesh)
                    uv_primvar = primvar_api.CreatePrimvar(
                        "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex
                    )
                    uv_primvar.Set(usd_uvs)

                # Set subdivision scheme
                usd_mesh.GetSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)

                # Set extent
                extent = self._compute_extent(mesh)
                usd_mesh.GetExtentAttr().Set(extent)

                # Handle materials
                material_name = self._get_material_from_mesh(mesh)
                if material_name:
                    if material_name not in created_materials:
                        # Create material in USD
                        mat_path = f"{materials_path}/{self._sanitize_name(material_name)}"
                        usd_material = self._create_usd_material(stage, mat_path, mesh)
                        created_materials[material_name] = mat_path
                        materials_found.append(material_name)

                    # Bind material to mesh
                    mat_prim = stage.GetPrimAtPath(created_materials[material_name])
                    if mat_prim:
                        binding = UsdShade.MaterialBindingAPI(usd_mesh)
                        binding.Bind(UsdShade.Material(mat_prim))

            # Save the stage
            stage.GetRootLayer().Save()
            self._log_info(f"USD file saved: {output_path}")

            # Validate output
            if not self.validate_output(output_path):
                return ConversionResult(success=False, error_message="Output validation failed")

            if not materials_found:
                warnings.append("No material library (MTL) found - using default materials")

            return ConversionResult(
                success=True,
                output_path=output_path,
                format="usd",
                parts=parts,
                materials=materials_found,
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

    def _extract_meshes(self, loaded, default_name: str) -> List[Tuple[str, trimesh.Trimesh]]:
        """
        Extract individual meshes from loaded OBJ data.

        Args:
            loaded: Trimesh scene or mesh object
            default_name: Default name if no names are found

        Returns:
            List of (name, mesh) tuples
        """
        meshes = []

        if isinstance(loaded, trimesh.Scene):
            # Multiple objects/groups
            for name, geom in loaded.geometry.items():
                if isinstance(geom, trimesh.Trimesh):
                    meshes.append((name, geom))
        elif isinstance(loaded, trimesh.Trimesh):
            # Single mesh
            meshes.append((default_name, loaded))

        return meshes

    def _sanitize_name(self, name: str) -> str:
        """
        Sanitize a name for use in USD path.

        Args:
            name: Original name

        Returns:
            Sanitized name valid for USD paths
        """
        # Replace invalid characters with underscore
        import re

        sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        # Ensure doesn't start with number
        if sanitized and sanitized[0].isdigit():
            sanitized = "_" + sanitized
        return sanitized or "mesh"

    def _compute_extent(self, mesh: trimesh.Trimesh) -> Vt.Vec3fArray:
        """Compute bounding box extent for USD."""
        bounds = mesh.bounds.tolist()
        return Vt.Vec3fArray(
            [
                Gf.Vec3f(float(bounds[0][0]), float(bounds[0][1]), float(bounds[0][2])),
                Gf.Vec3f(float(bounds[1][0]), float(bounds[1][1]), float(bounds[1][2])),
            ]
        )

    def _get_material_from_mesh(self, mesh: trimesh.Trimesh) -> Optional[str]:
        """
        Get material name from mesh if available.

        Args:
            mesh: The trimesh mesh

        Returns:
            Material name or None
        """
        if hasattr(mesh.visual, "material") and mesh.visual.material is not None:
            mat = mesh.visual.material
            if hasattr(mat, "name") and mat.name:
                return mat.name
        return None

    def _create_usd_material(
        self, stage: Usd.Stage, mat_path: str, mesh: trimesh.Trimesh
    ) -> UsdShade.Material:
        """
        Create a USD material from mesh visual properties.

        Args:
            stage: USD stage
            mat_path: Path for the material prim
            mesh: Source mesh with visual/material data

        Returns:
            Created UsdShade.Material
        """
        material = UsdShade.Material.Define(stage, mat_path)

        # Create a simple preview surface shader
        shader_path = f"{mat_path}/PreviewSurface"
        shader = UsdShade.Shader.Define(stage, shader_path)
        shader.CreateIdAttr("UsdPreviewSurface")

        # Extract color from mesh visual
        color = [0.8, 0.8, 0.8]  # Default gray

        if hasattr(mesh.visual, "material") and mesh.visual.material is not None:
            mat = mesh.visual.material
            if hasattr(mat, "diffuse") and mat.diffuse is not None:
                # Normalize to 0-1 range if needed
                diffuse = np.array(mat.diffuse[:3])
                if diffuse.max() > 1.0:
                    diffuse = diffuse / 255.0
                color = diffuse.tolist()
        elif hasattr(mesh.visual, "vertex_colors") and mesh.visual.vertex_colors is not None:
            # Use average vertex color
            avg_color = mesh.visual.vertex_colors[:, :3].mean(axis=0)
            if avg_color.max() > 1.0:
                avg_color = avg_color / 255.0
            color = avg_color.tolist()

        # Set diffuse color
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.5)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)

        # Connect shader to material surface output
        shader_output = shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
        material.CreateSurfaceOutput().ConnectToSource(shader_output)

        return material
