"""
DAE (COLLADA) Converter - Convert COLLADA files to USD format
DAE (Digital Asset Exchange) is an XML-based format widely used in:
- Gazebo simulation
- Game engines (Unity, Unreal)
- 3D modeling tools

This converter uses:
- trimesh: For loading DAE mesh data with materials
- pxr (OpenUSD): For generating USD output files with materials
"""

import os
from pathlib import Path
from typing import Optional, Dict, List
import numpy as np
import xml.etree.ElementTree as ET

# Mesh processing
import trimesh

# USD generation
from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf, Vt

from .base_converter import BaseConverter, ConversionResult


class DAEConverter(BaseConverter):
    """
    Converter for COLLADA/DAE files.
    
    COLLADA (COLLAborative Design Activity) is an XML-based schema
    for exchanging digital assets among graphics software.
    
    Features:
    - Full mesh geometry extraction
    - Material and texture support
    - Scene hierarchy preservation
    - Multiple geometry support
    - Animation data awareness (geometry only for now)
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize the DAE converter."""
        super().__init__(config)
        self.supported_extensions = ['.dae']
        
        # Configuration options
        self.scale_factor = self.config.get('scale_factor', 1.0)
        self.merge_meshes = self.config.get('merge_meshes', False)
        self.import_materials = self.config.get('import_materials', True)
    
    def convert(
        self,
        input_path: str,
        output_path: str,
        robot_name: str
    ) -> ConversionResult:
        """
        Convert a DAE file to USD format.
        
        Args:
            input_path: Path to the DAE file
            output_path: Path for the output USD file
            robot_name: Name of the robot/model
            
        Returns:
            ConversionResult with conversion details
        """
        # Validate input
        if not self.validate_input(input_path):
            return ConversionResult(
                success=False,
                error_message=f"Invalid input file: {input_path}"
            )
        
        warnings = []
        parts = []
        materials_found = []
        
        try:
            # Load DAE using trimesh
            self._log_info(f"Loading DAE file: {input_path}")
            
            # trimesh may return a Scene for DAE files
            loaded = trimesh.load(input_path, force=None)
            
            # Extract meshes and materials
            meshes = self._extract_meshes(loaded, robot_name)
            
            if not meshes:
                return ConversionResult(
                    success=False,
                    error_message="No meshes found in DAE file"
                )
            
            self._log_info(f"Loaded {len(meshes)} mesh(es)")
            
            # Extract materials from DAE XML
            dae_materials = self._extract_dae_materials(input_path)
            
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
            
            # Set up axis (DAE typically uses Y-up, convert to Z-up for UE5)
            UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
            UsdGeom.SetStageMetersPerUnit(stage, 1.0)
            
            # Create root xform
            root_path = f"/{self._sanitize_name(robot_name)}"
            root_xform = UsdGeom.Xform.Define(stage, root_path)
            stage.SetDefaultPrim(root_xform.GetPrim())
            
            # Create materials scope
            materials_path = f"{root_path}/Materials"
            UsdGeom.Scope.Define(stage, materials_path)
            
            # Create USD materials
            usd_materials = {}
            for mat_name, mat_data in dae_materials.items():
                mat_usd_path = f"{materials_path}/{self._sanitize_name(mat_name)}"
                self._create_usd_material(stage, mat_usd_path, mat_data)
                usd_materials[mat_name] = mat_usd_path
                materials_found.append(mat_name)
            
            # Process each mesh
            for mesh_name, mesh, mesh_material in meshes:
                safe_name = self._sanitize_name(mesh_name)
                mesh_path = f"{root_path}/{safe_name}"
                parts.append(safe_name)
                
                vertex_count = len(mesh.vertices)
                face_count = len(mesh.faces)
                self._log_info(f"Processing mesh: {mesh_name} ({vertex_count} vertices, {face_count} faces)")
                
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
                
                # Set UVs if available
                if hasattr(mesh.visual, 'uv') and mesh.visual.uv is not None:
                    uvs = mesh.visual.uv.tolist()
                    st_primvar = usd_mesh.CreatePrimvar(
                        "st", 
                        Sdf.ValueTypeNames.TexCoord2fArray,
                        UsdGeom.Tokens.vertex
                    )
                    st_primvar.Set(Vt.Vec2fArray([
                        Gf.Vec2f(float(uv[0]), float(uv[1])) 
                        for uv in uvs
                    ]))
                
                # Set subdivision scheme
                usd_mesh.GetSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
                
                # Bind material
                if mesh_material and mesh_material in usd_materials:
                    mat_prim = stage.GetPrimAtPath(usd_materials[mesh_material])
                    if mat_prim:
                        UsdShade.MaterialBindingAPI(usd_mesh.GetPrim()).Bind(
                            UsdShade.Material(mat_prim)
                        )
                elif self.import_materials and hasattr(mesh.visual, 'material'):
                    # Create inline material from mesh visual
                    vis_mat = mesh.visual.material
                    if vis_mat is not None and hasattr(vis_mat, 'main_color'):
                        inline_mat_name = f"{safe_name}_material"
                        inline_mat_path = f"{materials_path}/{inline_mat_name}"
                        color = vis_mat.main_color / 255.0 if vis_mat.main_color.max() > 1 else vis_mat.main_color
                        self._create_usd_material(stage, inline_mat_path, {'color': color.tolist()})
                        mat_prim = stage.GetPrimAtPath(inline_mat_path)
                        if mat_prim:
                            UsdShade.MaterialBindingAPI(usd_mesh.GetPrim()).Bind(
                                UsdShade.Material(mat_prim)
                            )
                        materials_found.append(inline_mat_name)
            
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
            
        except Exception as e:
            self._log_error(f"Conversion error: {e}")
            import traceback
            traceback.print_exc()
            return ConversionResult(
                success=False,
                error_message=f"DAE conversion failed: {str(e)}"
            )
    
    def _extract_meshes(self, loaded, robot_name: str) -> List[tuple]:
        """
        Extract meshes from loaded trimesh object.
        
        Returns:
            List of (name, mesh, material_name) tuples
        """
        meshes = []
        
        if isinstance(loaded, trimesh.Scene):
            # Scene with multiple geometries
            for name, geom in loaded.geometry.items():
                if isinstance(geom, trimesh.Trimesh):
                    # Try to get material name
                    mat_name = None
                    if hasattr(geom.visual, 'material') and geom.visual.material:
                        mat_name = getattr(geom.visual.material, 'name', None)
                    meshes.append((name, geom, mat_name))
        elif isinstance(loaded, trimesh.Trimesh):
            # Single mesh
            mat_name = None
            if hasattr(loaded.visual, 'material') and loaded.visual.material:
                mat_name = getattr(loaded.visual.material, 'name', None)
            meshes.append((robot_name, loaded, mat_name))
        
        return meshes
    
    def _extract_dae_materials(self, dae_path: str) -> Dict[str, Dict]:
        """
        Extract materials from DAE XML.
        
        Args:
            dae_path: Path to DAE file
            
        Returns:
            Dictionary of material_name -> material_data
        """
        materials = {}
        
        try:
            tree = ET.parse(dae_path)
            root = tree.getroot()
            
            # COLLADA namespace
            ns = {'c': 'http://www.collada.org/2005/11/COLLADASchema'}
            
            # Try to find materials
            for material_elem in root.findall('.//c:material', ns):
                mat_id = material_elem.get('id', material_elem.get('name', 'unknown'))
                materials[mat_id] = {'color': [0.8, 0.8, 0.8, 1.0]}
                
                # Try to find effect reference
                instance_effect = material_elem.find('c:instance_effect', ns)
                if instance_effect is not None:
                    effect_url = instance_effect.get('url', '').lstrip('#')
                    
                    # Find the effect
                    for effect in root.findall(f'.//c:effect[@id="{effect_url}"]', ns):
                        # Look for diffuse color
                        diffuse = effect.find('.//c:diffuse/c:color', ns)
                        if diffuse is not None and diffuse.text:
                            try:
                                color_values = [float(x) for x in diffuse.text.split()]
                                if len(color_values) >= 3:
                                    materials[mat_id]['color'] = color_values[:4] if len(color_values) >= 4 else color_values[:3] + [1.0]
                            except ValueError:
                                pass
        except Exception as e:
            self._log_warning(f"Could not parse DAE materials: {e}")
        
        return materials
    
    def _create_usd_material(self, stage, mat_path: str, mat_data: Dict):
        """Create a USD material from material data."""
        material = UsdShade.Material.Define(stage, mat_path)
        shader_path = f"{mat_path}/PreviewSurface"
        shader = UsdShade.Shader.Define(stage, shader_path)
        shader.CreateIdAttr("UsdPreviewSurface")
        
        # Diffuse color
        color = mat_data.get('color', [0.8, 0.8, 0.8, 1.0])
        if color and len(color) >= 3:
            shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
                Gf.Vec3f(float(color[0]), float(color[1]), float(color[2]))
            )
            if len(color) > 3:
                shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(float(color[3]))
        
        # Default PBR values
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.5)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
        
        # Connect shader output
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
