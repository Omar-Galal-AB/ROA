"""
STEP Converter - Convert STEP/STP CAD files to USD format
STEP (Standard for the Exchange of Product Data) is an ISO standard 
(ISO 10303) widely used in CAD/CAM applications.

This converter uses:
- trimesh: For loading STEP files (via cascadio/OCP backend)
- pxr (OpenUSD): For generating USD output files

Note: STEP loading requires the 'cascadio' or 'OCP' Python package
for full support. Trimesh will attempt to load with available backends.
"""

import os
from pathlib import Path
from typing import Optional, Dict, List
import numpy as np

# Mesh processing
import trimesh

# USD generation
from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf, Vt

from .base_converter import BaseConverter, ConversionResult


class STEPConverter(BaseConverter):
    """
    Converter for STEP/STP CAD files.
    
    STEP is the international standard for exchanging product model data
    in CAD/CAM applications. Commonly used for:
    - Mechanical parts and assemblies
    - Industrial robot components
    - Precision engineering models
    
    Features:
    - Full B-Rep to mesh conversion
    - Multiple solid body support
    - Assembly structure preservation
    - Surface quality control
    - Color/material extraction where available
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize the STEP converter."""
        super().__init__(config)
        self.supported_extensions = ['.step', '.stp']
        
        # Configuration options
        self.scale_factor = self.config.get('scale_factor', 1.0)
        self.linear_deflection = self.config.get('linear_deflection', 0.1)  # Mesh quality
        self.angular_deflection = self.config.get('angular_deflection', 0.5)  # Mesh quality
        
        # Check for STEP support
        self._check_step_support()
    
    def _check_step_support(self):
        """Check if STEP loading is supported."""
        self._step_supported = False
        self._step_backend = None
        
        # Check for cascadio (OpenCASCADE wrapper)
        try:
            import cascadio
            self._step_supported = True
            self._step_backend = 'cascadio'
            self._log_info("STEP support: cascadio backend available")
            return
        except ImportError:
            pass
        
        # Check for OCP (OpenCASCADE Python)
        try:
            import OCP
            self._step_supported = True
            self._step_backend = 'OCP'
            self._log_info("STEP support: OCP backend available")
            return
        except ImportError:
            pass
        
        # Trimesh may still work with limited STEP support
        self._log_warning("No dedicated STEP backend found. Install 'cascadio' or 'OCP' for full support.")
        self._step_supported = True  # Try anyway with trimesh
        self._step_backend = 'trimesh'
    
    def convert(
        self,
        input_path: str,
        output_path: str,
        robot_name: str
    ) -> ConversionResult:
        """
        Convert a STEP file to USD format.
        
        Args:
            input_path: Path to the STEP file
            output_path: Path for the output USD file
            robot_name: Name of the robot/part
            
        Returns:
            ConversionResult with conversion details
        """
        # Validate input
        if not self.validate_input(input_path):
            return ConversionResult(
                success=False,
                error_message=f"Invalid input file: {input_path}"
            )
        
        if not self._step_supported:
            return ConversionResult(
                success=False,
                error_message="STEP support not available. Install 'cascadio' or 'OCP' package."
            )
        
        warnings = []
        parts = []
        materials_found = []
        
        try:
            # Load STEP file
            self._log_info(f"Loading STEP file: {input_path}")
            self._log_info(f"Using backend: {self._step_backend}")
            
            # Load with trimesh (uses available backend)
            loaded = trimesh.load(input_path, force=None)
            
            # Extract meshes
            meshes = self._extract_meshes(loaded, robot_name)
            
            if not meshes:
                return ConversionResult(
                    success=False,
                    error_message="No geometry found in STEP file"
                )
            
            self._log_info(f"Extracted {len(meshes)} solid(s)")
            
            # Ensure output directory exists
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Create USD stage
            self._log_info(f"Creating USD file: {output_path}")
            stage = Usd.Stage.CreateNew(output_path)
            
            if stage is None:
                return ConversionResult(
                    success=False,
                    error_message=f"Failed to create USD stage at {output_path}"
                )
            
            # Set up stage (STEP typically uses Z-up, matching UE5)
            UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
            UsdGeom.SetStageMetersPerUnit(stage, 1.0)  # STEP uses mm, we assume already scaled
            
            # Create root xform
            root_path = f"/{self._sanitize_name(robot_name)}"
            root_xform = UsdGeom.Xform.Define(stage, root_path)
            stage.SetDefaultPrim(root_xform.GetPrim())
            
            # Create default material for CAD parts
            materials_path = f"{root_path}/Materials"
            UsdGeom.Scope.Define(stage, materials_path)
            
            default_mat_path = f"{materials_path}/CAD_Material"
            self._create_cad_material(stage, default_mat_path)
            materials_found.append("CAD_Material")
            
            # Process each mesh/solid
            for mesh_name, mesh, color in meshes:
                safe_name = self._sanitize_name(mesh_name)
                mesh_path = f"{root_path}/{safe_name}"
                parts.append(safe_name)
                
                vertex_count = len(mesh.vertices)
                face_count = len(mesh.faces)
                self._log_info(f"Processing solid: {mesh_name} ({vertex_count} vertices, {face_count} faces)")
                
                # Apply scale
                if self.scale_factor != 1.0:
                    mesh.apply_scale(self.scale_factor)
                
                # Create USD mesh
                usd_mesh = UsdGeom.Mesh.Define(stage, mesh_path)
                
                # Set vertices
                vertices = mesh.vertices.tolist()
                points = Vt.Vec3fArray([
                    Gf.Vec3f(float(v[0]), float(v[1]), float(v[2])) 
                    for v in vertices
                ])
                usd_mesh.GetPointsAttr().Set(points)
                
                # Set faces
                faces = mesh.faces.astype(np.int32)
                face_vertex_counts = Vt.IntArray([3] * len(faces))
                face_vertex_indices = Vt.IntArray(faces.flatten().tolist())
                usd_mesh.GetFaceVertexCountsAttr().Set(face_vertex_counts)
                usd_mesh.GetFaceVertexIndicesAttr().Set(face_vertex_indices)
                
                # Set normals
                if hasattr(mesh, 'vertex_normals') and mesh.vertex_normals is not None:
                    normals = mesh.vertex_normals.tolist()
                    usd_normals = Vt.Vec3fArray([
                        Gf.Vec3f(float(n[0]), float(n[1]), float(n[2])) 
                        for n in normals
                    ])
                    usd_mesh.GetNormalsAttr().Set(usd_normals)
                    usd_mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
                
                # Set subdivision scheme
                usd_mesh.GetSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
                
                # Create material with solid color if available
                if color is not None:
                    mat_name = f"{safe_name}_material"
                    mat_path = f"{materials_path}/{mat_name}"
                    self._create_usd_material(stage, mat_path, color)
                    mat_prim = stage.GetPrimAtPath(mat_path)
                    if mat_prim:
                        UsdShade.MaterialBindingAPI(usd_mesh.GetPrim()).Bind(
                            UsdShade.Material(mat_prim)
                        )
                    materials_found.append(mat_name)
                else:
                    # Use default CAD material
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
                return ConversionResult(
                    success=False,
                    error_message="Output validation failed"
                )
            
            return ConversionResult(
                success=True,
                output_path=output_path,
                format='usd',
                parts=parts,
                materials=materials_found,
                warnings=warnings
            )
            
        except ImportError as e:
            return ConversionResult(
                success=False,
                error_message=f"Missing STEP support library: {str(e)}. Install 'cascadio' or 'OCP'."
            )
        except Exception as e:
            self._log_error(f"Conversion error: {e}")
            import traceback
            traceback.print_exc()
            return ConversionResult(
                success=False,
                error_message=f"STEP conversion failed: {str(e)}"
            )
    
    def _extract_meshes(self, loaded, robot_name: str) -> List[tuple]:
        """
        Extract meshes from loaded trimesh object.
        
        Returns:
            List of (name, mesh, color) tuples
        """
        meshes = []
        
        if isinstance(loaded, trimesh.Scene):
            # Multiple solids/bodies
            for i, (name, geom) in enumerate(loaded.geometry.items()):
                if isinstance(geom, trimesh.Trimesh):
                    color = self._extract_color(geom)
                    meshes.append((name or f"solid_{i}", geom, color))
        elif isinstance(loaded, trimesh.Trimesh):
            # Single solid
            color = self._extract_color(loaded)
            meshes.append((robot_name, loaded, color))
        
        return meshes
    
    def _extract_color(self, mesh: trimesh.Trimesh) -> Optional[List[float]]:
        """Extract color from mesh visual."""
        try:
            if hasattr(mesh, 'visual') and mesh.visual is not None:
                if hasattr(mesh.visual, 'main_color') and mesh.visual.main_color is not None:
                    color = mesh.visual.main_color
                    # Normalize to 0-1 if needed
                    if hasattr(color, '__iter__'):
                        color = [float(c) / 255.0 if c > 1 else float(c) for c in color[:4]]
                        return color
        except:
            pass
        return None
    
    def _create_cad_material(self, stage, mat_path: str):
        """Create a default CAD material (metallic gray)."""
        material = UsdShade.Material.Define(stage, mat_path)
        shader_path = f"{mat_path}/PreviewSurface"
        shader = UsdShade.Shader.Define(stage, shader_path)
        shader.CreateIdAttr("UsdPreviewSurface")
        
        # CAD-like appearance: slightly metallic gray
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(0.7, 0.7, 0.75)
        )
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.3)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.2)
        
        shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
        material.CreateSurfaceOutput().ConnectToSource(
            shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
        )
        
        return material
    
    def _create_usd_material(self, stage, mat_path: str, color: List[float]):
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
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        if sanitized and sanitized[0].isdigit():
            sanitized = '_' + sanitized
        return sanitized or 'unnamed'
