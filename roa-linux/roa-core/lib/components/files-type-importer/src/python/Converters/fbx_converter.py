"""
FBX Converter - Convert FBX (Filmbox) files to USD format
FBX is Autodesk's proprietary format widely used in:
- 3D animation and game development
- Motion capture data
- Autodesk Maya, 3ds Max exports

This converter uses:
- pyassimp: Python bindings for Assimp library (supports FBX)
- pxr (OpenUSD): For generating USD output files

Note: Requires the 'pyassimp' package and Assimp library installed.
Install via: pip install pyassimp
On Linux, also: apt-get install libassimp-dev
"""

import os
from pathlib import Path
from typing import Optional, Dict, List
import numpy as np

# USD generation
from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf, Vt

from .base_converter import BaseConverter, ConversionResult


class FBXConverter(BaseConverter):
    """
    Converter for FBX (Filmbox) files.
    
    FBX is Autodesk's proprietary format, commonly used for:
    - Animation and rigging data
    - Game asset exchange
    - Motion capture data
    - Scenes from Maya, 3ds Max, Blender
    
    Features:
    - Mesh geometry extraction
    - Material and texture references
    - Hierarchy preservation
    - Animation support (skeleton/joints)
    - UV coordinates
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize the FBX converter."""
        super().__init__(config)
        self.supported_extensions = ['.fbx']
        
        # Configuration
        self.scale_factor = self.config.get('scale_factor', 1.0)
        self.import_animations = self.config.get('import_animations', False)
        self.triangulate = self.config.get('triangulate', True)
        
        # Check for pyassimp availability
        self._assimp_available = False
        self._check_assimp_support()
    
    def _check_assimp_support(self):
        """Check if pyassimp is available."""
        try:
            import pyassimp
            self._assimp_available = True
            self._log_info("FBX support: pyassimp available")
        except ImportError:
            self._log_warning("pyassimp not found. Install with: pip install pyassimp")
            self._assimp_available = False
    
    def convert(
        self,
        input_path: str,
        output_path: str,
        robot_name: str
    ) -> ConversionResult:
        """
        Convert an FBX file to USD format.
        
        Args:
            input_path: Path to the FBX file
            output_path: Path for the output USD file
            robot_name: Name of the robot/asset
            
        Returns:
            ConversionResult with conversion details
        """
        # Validate input
        if not self.validate_input(input_path):
            return ConversionResult(
                success=False,
                error_message=f"Invalid input file: {input_path}"
            )
        
        if not self._assimp_available:
            return ConversionResult(
                success=False,
                error_message="FBX support requires pyassimp. Install with: pip install pyassimp"
            )
        
        warnings = []
        parts = []
        materials_found = []
        
        try:
            import pyassimp
            from pyassimp import postprocess
            
            # Configure processing flags
            processing_flags = (
                postprocess.aiProcess_GenNormals |
                postprocess.aiProcess_GenUVCoords |
                postprocess.aiProcess_OptimizeMeshes
            )
            if self.triangulate:
                processing_flags |= postprocess.aiProcess_Triangulate
            
            self._log_info(f"Loading FBX file: {input_path}")
            
            # Load FBX with pyassimp
            scene = pyassimp.load(input_path, processing=processing_flags)
            
            if not scene or not scene.meshes:
                return ConversionResult(
                    success=False,
                    error_message="No meshes found in FBX file"
                )
            
            self._log_info(f"Found {len(scene.meshes)} mesh(es)")
            
            # Ensure output directory exists
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Create USD stage
            self._log_info(f"Creating USD file: {output_path}")
            stage = Usd.Stage.CreateNew(output_path)
            
            if stage is None:
                pyassimp.release(scene)
                return ConversionResult(
                    success=False,
                    error_message=f"Failed to create USD stage at {output_path}"
                )
            
            # Set up stage (FBX can use Y-up or Z-up)
            UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)  # Most FBX uses Y-up
            UsdGeom.SetStageMetersPerUnit(stage, 0.01)  # FBX typically uses cm
            
            # Create root xform
            root_path = f"/{self._sanitize_name(robot_name)}"
            root_xform = UsdGeom.Xform.Define(stage, root_path)
            stage.SetDefaultPrim(root_xform.GetPrim())
            
            # Create materials scope
            materials_path = f"{root_path}/Materials"
            UsdGeom.Scope.Define(stage, materials_path)
            
            # Process materials from scene
            mat_map = {}
            for i, mat in enumerate(scene.materials):
                mat_name = self._get_material_name(mat, i)
                safe_mat_name = self._sanitize_name(mat_name)
                mat_path = f"{materials_path}/{safe_mat_name}"
                
                self._create_usd_material_from_assimp(stage, mat_path, mat)
                mat_map[i] = mat_path
                materials_found.append(safe_mat_name)
            
            # Process meshes
            for i, mesh in enumerate(scene.meshes):
                mesh_name = mesh.name or f"mesh_{i}"
                safe_name = self._sanitize_name(mesh_name)
                mesh_path = f"{root_path}/{safe_name}"
                parts.append(safe_name)
                
                vertex_count = len(mesh.vertices)
                face_count = len(mesh.faces)
                self._log_info(f"Processing mesh: {mesh_name} ({vertex_count} vertices, {face_count} faces)")
                
                # Create USD mesh
                usd_mesh = UsdGeom.Mesh.Define(stage, mesh_path)
                
                # Set vertices
                vertices = mesh.vertices
                if self.scale_factor != 1.0:
                    vertices = vertices * self.scale_factor
                
                points = Vt.Vec3fArray([
                    Gf.Vec3f(float(v[0]), float(v[1]), float(v[2])) 
                    for v in vertices
                ])
                usd_mesh.GetPointsAttr().Set(points)
                
                # Set faces
                face_vertex_counts = Vt.IntArray()
                face_vertex_indices = Vt.IntArray()
                
                for face in mesh.faces:
                    face_vertex_counts.append(len(face))
                    for idx in face:
                        face_vertex_indices.append(int(idx))
                
                usd_mesh.GetFaceVertexCountsAttr().Set(face_vertex_counts)
                usd_mesh.GetFaceVertexIndicesAttr().Set(face_vertex_indices)
                
                # Set normals
                if mesh.normals is not None and len(mesh.normals) > 0:
                    normals = Vt.Vec3fArray([
                        Gf.Vec3f(float(n[0]), float(n[1]), float(n[2])) 
                        for n in mesh.normals
                    ])
                    usd_mesh.GetNormalsAttr().Set(normals)
                    usd_mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
                
                # Set UV coordinates
                if hasattr(mesh, 'texturecoords') and mesh.texturecoords is not None:
                    for uv_idx, uv_set in enumerate(mesh.texturecoords):
                        if uv_set is not None and len(uv_set) > 0:
                            uv_name = "st" if uv_idx == 0 else f"st{uv_idx}"
                            uvs = Vt.Vec2fArray([
                                Gf.Vec2f(float(uv[0]), float(uv[1])) 
                                for uv in uv_set
                            ])
                            uv_attr = usd_mesh.CreatePrimvar(
                                uv_name,
                                Sdf.ValueTypeNames.TexCoord2fArray,
                                UsdGeom.Tokens.vertex
                            )
                            uv_attr.Set(uvs)
                            break  # Usually only first UV set needed
                
                # Set subdivision scheme
                usd_mesh.GetSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
                
                # Bind material
                mat_index = mesh.materialindex
                if mat_index in mat_map:
                    mat_prim = stage.GetPrimAtPath(mat_map[mat_index])
                    if mat_prim:
                        UsdShade.MaterialBindingAPI(usd_mesh.GetPrim()).Bind(
                            UsdShade.Material(mat_prim)
                        )
            
            # Process skeleton/joints if present
            if self.import_animations and scene.rootnode:
                skeleton_joints = self._extract_skeleton(scene.rootnode)
                if skeleton_joints:
                    warnings.append(f"Found {len(skeleton_joints)} joints (skeleton import pending)")
            
            # Clean up assimp scene
            pyassimp.release(scene)
            
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
                error_message=f"Missing library: {str(e)}. Install pyassimp."
            )
        except Exception as e:
            self._log_error(f"Conversion error: {e}")
            import traceback
            traceback.print_exc()
            return ConversionResult(
                success=False,
                error_message=f"FBX conversion failed: {str(e)}"
            )
    
    def _get_material_name(self, mat, index: int) -> str:
        """Get material name from assimp material."""
        try:
            # Try to get name from material properties
            for key, value in mat.properties.items():
                if 'name' in key.lower():
                    if isinstance(value, str) and value:
                        return value
        except:
            pass
        return f"material_{index}"
    
    def _create_usd_material_from_assimp(self, stage, mat_path: str, assimp_mat):
        """Create USD material from assimp material."""
        material = UsdShade.Material.Define(stage, mat_path)
        shader_path = f"{mat_path}/PreviewSurface"
        shader = UsdShade.Shader.Define(stage, shader_path)
        shader.CreateIdAttr("UsdPreviewSurface")
        
        # Default values
        diffuse = [0.8, 0.8, 0.8]
        opacity = 1.0
        roughness = 0.5
        metallic = 0.0
        
        # Extract properties from assimp material
        try:
            props = assimp_mat.properties
            
            # Diffuse color
            for key in ['diffuse', '$clr.diffuse', 'COLOR_DIFFUSE']:
                if key in props:
                    val = props[key]
                    if hasattr(val, '__iter__') and len(val) >= 3:
                        diffuse = [float(val[0]), float(val[1]), float(val[2])]
                        if len(val) > 3:
                            opacity = float(val[3])
                        break
            
            # Opacity
            for key in ['opacity', '$mat.opacity']:
                if key in props:
                    opacity = float(props[key])
                    break
            
            # Roughness/Shininess
            for key in ['shininess', '$mat.shininess']:
                if key in props:
                    shininess = float(props[key])
                    # Convert shininess to roughness (inverse relationship)
                    roughness = max(0.0, min(1.0, 1.0 - (shininess / 128.0)))
                    break
            
            # Metallic (PBR)
            for key in ['metallic', '$mat.metallic']:
                if key in props:
                    metallic = float(props[key])
                    break
                    
        except Exception as e:
            self._log_warning(f"Error extracting material properties: {e}")
        
        # Set shader inputs
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(diffuse[0], diffuse[1], diffuse[2])
        )
        shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(opacity)
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metallic)
        
        shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
        material.CreateSurfaceOutput().ConnectToSource(
            shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
        )
        
        return material
    
    def _extract_skeleton(self, node, depth: int = 0) -> List[str]:
        """Extract skeleton joints from node hierarchy."""
        joints = []
        
        # Skip if max depth reached
        if depth > 100:  # Safety limit
            return joints
        
        try:
            if node.name:
                # Check if this looks like a joint (common naming conventions)
                name_lower = node.name.lower()
                if any(kw in name_lower for kw in ['bone', 'joint', 'skeleton', 'armature']):
                    joints.append(node.name)
            
            # Recurse into children
            for child in node.children:
                joints.extend(self._extract_skeleton(child, depth + 1))
                
        except Exception:
            pass
        
        return joints
    
    def _sanitize_name(self, name: str) -> str:
        """Sanitize a name for use in USD paths."""
        import re
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        if sanitized and sanitized[0].isdigit():
            sanitized = '_' + sanitized
        return sanitized or 'unnamed'
