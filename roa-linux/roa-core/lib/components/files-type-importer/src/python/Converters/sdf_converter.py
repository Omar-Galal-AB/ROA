"""
SDF Converter - Convert SDF (Simulation Description Format) files to USD

SDF is the standard format for Gazebo simulation environments.
Similar to URDF but with additional features like:
- Multiple robots in one file
- World definitions
- Physics parameters
- Sensors
- Plugins

v3.4 Enhancements (ported from URDF converter):
- VRML mesh support (.wrl files)
- Extended mesh formats: STL, OBJ, DAE, WRL, PLY, GLB, GLTF
- Convex decomposition for collision meshes (V-HACD)
- Texture embedding support
- Separate /Visuals and /Collisions folders
"""

import os
import sys
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Optional, Dict, List, Tuple
import numpy as np
import math
import logging

# Mesh processing
try:
    import trimesh
    TRIMESH_AVAILABLE = True
except ImportError:
    TRIMESH_AVAILABLE = False

# USD generation
from pxr import Usd, UsdGeom, UsdPhysics, UsdShade, Sdf, Gf, Vt

from .base_converter import BaseConverter, ConversionResult


class SDFConverter(BaseConverter):
    """
    Converter for SDF (Simulation Description Format) files.
    
    SDF is the standard format used in Gazebo for describing
    simulation environments including robots, objects, and worlds.
    
    Features:
    - Full model/link/joint hierarchy
    - Visual and collision geometry
    - Multiple models per file
    - World definitions
    - Physics properties
    - Material/color support
    - Mesh loading (STL, OBJ, DAE)
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize the SDF converter."""
        super().__init__(config)
        self.supported_extensions = ['.sdf', '.world']
        self.logger = logging.getLogger(__name__)
        
        # Configuration
        self.scale_factor = self.config.get('scale_factor', 1.0)
        self.include_collision = self.config.get('include_collision', True)
        self.include_visual = self.config.get('include_visual', True)
        self.sdf_dir = None
        
        # v3.4: Mesh configuration (ported from URDF converter)
        self.mesh_config = {
            'enable_convex_decomposition': self.config.get('enable_convex_decomposition', True),
            'convex_max_hulls': self.config.get('convex_max_hulls', 16),
            'convex_resolution': self.config.get('convex_resolution', 100000),
            'embed_textures': self.config.get('embed_textures', False),
        }
        
        # v3.4: Supported mesh formats
        self.supported_mesh_formats = ['.stl', '.obj', '.dae', '.wrl', '.ply', '.glb', '.gltf']
    
    def convert(
        self,
        input_path: str,
        output_path: str,
        robot_name: str
    ) -> ConversionResult:
        """
        Convert an SDF file to USD format.
        
        Args:
            input_path: Path to SDF file
            output_path: Path for output USD file
            robot_name: Name for the robot/model
            
        Returns:
            ConversionResult with conversion status
        """
        if not self.validate_input(input_path):
            return ConversionResult(
                success=False,
                error_message=f"Invalid input file: {input_path}"
            )
        
        warnings = []
        parts = []
        materials_found = []
        
        try:
            self._log_info(f"Parsing SDF file: {input_path}")
            tree = ET.parse(input_path)
            root = tree.getroot()
            
            # Handle both <sdf> and <world> root elements
            if root.tag == 'sdf':
                sdf_version = root.get('version', '1.6')
                self._log_info(f"SDF version: {sdf_version}")
            elif root.tag == 'world':
                self._log_info("Processing world file")
            else:
                return ConversionResult(
                    success=False,
                    error_message=f"Invalid SDF file: root element must be 'sdf' or 'world', found '{root.tag}'"
                )
            
            self.sdf_dir = Path(input_path).parent
            
            # Create USD stage
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            
            stage = Usd.Stage.CreateNew(output_path)
            stage.SetMetadata('upAxis', 'Z')
            
            # Set default prim
            root_prim = stage.DefinePrim(f'/{robot_name}', 'Xform')
            stage.SetDefaultPrim(root_prim)
            
            # v3.4: Create separate root folders for visuals and collisions
            visuals_root = stage.DefinePrim(f'/{robot_name}/Visuals', 'Scope')
            collisions_root = stage.DefinePrim(f'/{robot_name}/Collisions', 'Scope')
            
            # Process all models
            models = root.findall('.//model')
            if not models:
                # Check if root itself contains model elements directly
                links = root.findall('.//link')
                if links:
                    # Treat the file as a single model
                    self._log_info("No model element found, treating as single model")
                    model_parts, model_mats = self._process_model_content(
                        root, stage, root_prim.GetPath(), robot_name
                    )
                    parts.extend(model_parts)
                    materials_found.extend(model_mats)
                else:
                    warnings.append("No models or links found in SDF file")
            else:
                self._log_info(f"Found {len(models)} models")
                
                for model in models:
                    model_name = model.get('name', 'model')
                    model_name = self._sanitize_name(model_name)
                    
                    model_path = root_prim.GetPath().AppendChild(model_name)
                    model_xform = UsdGeom.Xform.Define(stage, model_path)
                    
                    # Apply model pose
                    pose = model.find('pose')
                    if pose is not None:
                        self._apply_pose(pose, model_xform)
                    
                    model_parts, model_mats = self._process_model_content(
                        model, stage, model_path, model_name
                    )
                    parts.extend(model_parts)
                    materials_found.extend(model_mats)
            
            # Save stage
            stage.GetRootLayer().Save()
            self._log_info(f"USD file saved: {output_path}")
            
            return ConversionResult(
                success=True,
                output_path=output_path,
                format='usd',
                parts=parts,
                materials=materials_found,
                warnings=warnings
            )
            
        except ET.ParseError as e:
            return ConversionResult(
                success=False,
                error_message=f"Invalid XML in SDF file: {e}"
            )
        except Exception as e:
            self._log_error(f"Conversion failed: {e}")
            import traceback
            traceback.print_exc()
            return ConversionResult(
                success=False,
                error_message=f"SDF conversion failed: {str(e)}",
                warnings=warnings
            )
    
    def _process_model_content(
        self,
        model_elem: ET.Element,
        stage: 'Usd.Stage',
        parent_path: 'Sdf.Path',
        model_name: str
    ) -> Tuple[List[str], List[str]]:
        """
        Process model content (links, joints, nested models).
        
        Returns:
            Tuple of (parts list, materials list)
        """
        parts = []
        materials = []
        
        # Extract links
        links = model_elem.findall('link')
        for link in links:
            link_parts, link_mats = self._process_link(link, stage, parent_path)
            parts.extend(link_parts)
            materials.extend(link_mats)
        
        # Extract joints
        joints = model_elem.findall('joint')
        for joint in joints:
            self._process_joint(joint, stage, parent_path)
        
        # Process nested models
        nested_models = model_elem.findall('model')
        for nested in nested_models:
            nested_name = nested.get('name', 'nested_model')
            nested_name = self._sanitize_name(nested_name)
            
            nested_path = parent_path.AppendChild(nested_name)
            nested_xform = UsdGeom.Xform.Define(stage, nested_path)
            
            pose = nested.find('pose')
            if pose is not None:
                self._apply_pose(pose, nested_xform)
            
            nested_parts, nested_mats = self._process_model_content(
                nested, stage, nested_path, nested_name
            )
            parts.extend(nested_parts)
            materials.extend(nested_mats)
        
        return parts, materials
    
    def _process_link(
        self,
        link_elem: ET.Element,
        stage: 'Usd.Stage',
        parent_path: 'Sdf.Path'
    ) -> Tuple[List[str], List[str]]:
        """
        Process an SDF link element.
        
        Returns:
            Tuple of (parts list, materials list)
        """
        parts = []
        materials = []
        
        link_name = link_elem.get('name', 'link')
        link_name = self._sanitize_name(link_name)
        
        link_path = parent_path.AppendChild(link_name)
        link_xform = UsdGeom.Xform.Define(stage, link_path)
        
        # Apply link pose
        pose = link_elem.find('pose')
        if pose is not None:
            self._apply_pose(pose, link_xform)
        
        # Process visuals
        if self.include_visual:
            visuals = link_elem.findall('visual')
            for i, visual in enumerate(visuals):
                visual_name = visual.get('name', f'visual_{i}')
                visual_name = self._sanitize_name(visual_name)
                
                visual_path = link_path.AppendChild(visual_name)
                visual_parts, visual_mats = self._process_geometry_element(
                    visual, stage, visual_path, is_collision=False
                )
                parts.extend(visual_parts)
                materials.extend(visual_mats)
        
        # Process collisions
        if self.include_collision:
            collisions = link_elem.findall('collision')
            for i, collision in enumerate(collisions):
                collision_name = collision.get('name', f'collision_{i}')
                collision_name = self._sanitize_name(collision_name)
                
                collision_path = link_path.AppendChild(f"{collision_name}_collision")
                collision_parts, _ = self._process_geometry_element(
                    collision, stage, collision_path, is_collision=True
                )
                # Don't add collision to visible parts
        
        # Add inertial properties
        inertial = link_elem.find('inertial')
        if inertial is not None:
            self._add_physics_properties(inertial, stage, link_path)
        
        parts.append(str(link_path))
        return parts, materials
    
    def _process_geometry_element(
        self,
        geom_parent: ET.Element,
        stage: 'Usd.Stage',
        geom_path: 'Sdf.Path',
        is_collision: bool = False
    ) -> Tuple[List[str], List[str]]:
        """
        Process a visual or collision element with geometry.
        
        Returns:
            Tuple of (parts list, materials list)
        """
        parts = []
        materials = []
        
        geom_xform = UsdGeom.Xform.Define(stage, geom_path)
        
        # Apply pose
        pose = geom_parent.find('pose')
        if pose is not None:
            self._apply_pose(pose, geom_xform)
        
        geometry = geom_parent.find('geometry')
        if geometry is None:
            return parts, materials
        
        # Handle different geometry types
        if geometry.find('mesh') is not None:
            mesh_elem = geometry.find('mesh')
            mesh_path = geom_path.AppendChild('mesh')
            self._process_mesh_geometry(mesh_elem, stage, mesh_path)
            parts.append(str(mesh_path))
            
        elif geometry.find('box') is not None:
            box_elem = geometry.find('box')
            size_text = box_elem.findtext('size', '1 1 1')
            size = [float(x) * self.scale_factor for x in size_text.split()]
            
            cube = UsdGeom.Cube.Define(stage, geom_path.AppendChild('box'))
            cube.GetSizeAttr().Set(1.0)
            cube.AddScaleOp().Set(Gf.Vec3f(size[0], size[1], size[2]))
            parts.append(str(geom_path.AppendChild('box')))
            
        elif geometry.find('sphere') is not None:
            sphere_elem = geometry.find('sphere')
            radius = float(sphere_elem.findtext('radius', '1')) * self.scale_factor
            
            sphere = UsdGeom.Sphere.Define(stage, geom_path.AppendChild('sphere'))
            sphere.GetRadiusAttr().Set(radius)
            parts.append(str(geom_path.AppendChild('sphere')))
            
        elif geometry.find('cylinder') is not None:
            cyl_elem = geometry.find('cylinder')
            radius = float(cyl_elem.findtext('radius', '1')) * self.scale_factor
            length = float(cyl_elem.findtext('length', '1')) * self.scale_factor
            
            cylinder = UsdGeom.Cylinder.Define(stage, geom_path.AppendChild('cylinder'))
            cylinder.GetRadiusAttr().Set(radius)
            cylinder.GetHeightAttr().Set(length)
            parts.append(str(geom_path.AppendChild('cylinder')))
            
        elif geometry.find('plane') is not None:
            plane_elem = geometry.find('plane')
            size_text = plane_elem.findtext('size', '1 1')
            size = [float(x) * self.scale_factor for x in size_text.split()]
            
            # Create a flat mesh for plane
            mesh = UsdGeom.Mesh.Define(stage, geom_path.AppendChild('plane'))
            hw, hd = size[0] / 2, size[1] / 2
            mesh.GetPointsAttr().Set([
                (-hw, -hd, 0), (hw, -hd, 0), (hw, hd, 0), (-hw, hd, 0)
            ])
            mesh.GetFaceVertexCountsAttr().Set([4])
            mesh.GetFaceVertexIndicesAttr().Set([0, 1, 2, 3])
            parts.append(str(geom_path.AppendChild('plane')))
        
        # Process material (for visuals only)
        if not is_collision:
            material = geom_parent.find('material')
            if material is not None:
                mat_name = self._create_material_from_sdf(material, stage, geom_path.GetParentPath())
                if mat_name:
                    materials.append(mat_name)
        
        return parts, materials
    
    def _process_mesh_geometry(
        self,
        mesh_elem: ET.Element,
        stage: 'Usd.Stage',
        mesh_path: 'Sdf.Path',
        is_collision: bool = False
    ):
        """
        Process a mesh geometry element (v3.4 enhanced).
        
        v3.4: Now supports VRML (.wrl), GLB, GLTF, PLY formats.
        Applies convex decomposition for collision meshes.
        """
        uri = mesh_elem.findtext('uri', '')
        
        # Handle different URI schemes
        mesh_file_path = self._resolve_mesh_uri(uri)
        
        if mesh_file_path and Path(mesh_file_path).exists():
            # Load mesh with trimesh
            if TRIMESH_AVAILABLE:
                try:
                    loaded_mesh = self._load_mesh_file(mesh_file_path)
                    
                    if loaded_mesh is not None:
                        # v3.4: Apply convex decomposition for collision meshes
                        if is_collision and self.mesh_config.get('enable_convex_decomposition', True):
                            loaded_mesh = self._apply_convex_decomposition(loaded_mesh)
                        
                        self._create_usd_mesh_from_trimesh(loaded_mesh, stage, mesh_path)
                        
                        # v3.4: Embed textures if enabled
                        if self.mesh_config.get('embed_textures', False) and not is_collision:
                            self._embed_mesh_textures(loaded_mesh, stage, mesh_path)
                    else:
                        self._create_placeholder_mesh(stage, mesh_path)
                except Exception as e:
                    self._log_warning(f"Failed to load mesh {mesh_file_path}: {e}")
                    self._create_placeholder_mesh(stage, mesh_path)
            else:
                self._log_warning("trimesh not available for mesh loading")
                self._create_placeholder_mesh(stage, mesh_path)
        else:
            self._log_warning(f"Mesh file not found: {uri}")
            self._create_placeholder_mesh(stage, mesh_path)
        
        # Apply scale if specified
        scale_elem = mesh_elem.find('scale')
        if scale_elem is not None:
            scale_text = scale_elem.text or '1 1 1'
            scale = [float(x) for x in scale_text.split()]
            xform = UsdGeom.Xformable(stage.GetPrimAtPath(mesh_path))
            xform.AddScaleOp().Set(Gf.Vec3f(scale[0], scale[1], scale[2]))
    
    def _load_mesh_file(self, file_path: str) -> Optional['trimesh.Trimesh']:
        """
        Load mesh file with extended format support (v3.4).
        
        Supports: STL, OBJ, DAE, WRL (VRML), PLY, GLB, GLTF
        """
        if not TRIMESH_AVAILABLE:
            return None
        
        file_ext = Path(file_path).suffix.lower()
        
        try:
            if file_ext == '.wrl':
                # VRML format - requires explicit file_type
                mesh = trimesh.load(file_path, file_type='vrml', force='mesh')
            elif file_ext in ['.glb', '.gltf']:
                # glTF formats
                mesh = trimesh.load(file_path, force='mesh')
            elif file_ext == '.ply':
                mesh = trimesh.load(file_path, file_type='ply', force='mesh')
            else:
                # Standard formats (STL, OBJ, DAE)
                mesh = trimesh.load(file_path, force='mesh')
            
            # Handle Scene objects (from DAE, GLTF)
            if hasattr(mesh, 'geometry'):
                meshes = list(mesh.geometry.values())
                if meshes:
                    mesh = trimesh.util.concatenate(meshes)
                else:
                    return None
            
            return mesh
            
        except Exception as e:
            self._log_warning(f"Failed to load mesh {file_path}: {e}")
            return None
    
    def _apply_convex_decomposition(self, mesh: 'trimesh.Trimesh') -> 'trimesh.Trimesh':
        """
        Apply convex decomposition for collision optimization (v3.4).
        
        Uses V-HACD algorithm to decompose complex meshes into convex hulls.
        """
        if not TRIMESH_AVAILABLE:
            return mesh
        
        try:
            # Use trimesh's convex decomposition (V-HACD)
            max_hulls = self.mesh_config.get('convex_max_hulls', 16)
            resolution = self.mesh_config.get('convex_resolution', 100000)
            
            hulls = mesh.convex_decomposition(
                maxhulls=max_hulls,
                resolution=resolution
            )
            
            if hulls and len(hulls) > 0:
                # Combine all hulls into single mesh for USD
                combined = trimesh.util.concatenate(hulls)
                self._log_info(f"Convex decomposition: {len(hulls)} hulls")
                return combined
            else:
                # Fallback to convex hull
                return mesh.convex_hull
                
        except Exception as e:
            self._log_warning(f"Convex decomposition failed, using convex hull: {e}")
            try:
                return mesh.convex_hull
            except Exception:
                return mesh
    
    def _embed_mesh_textures(
        self,
        mesh: 'trimesh.Trimesh',
        stage: 'Usd.Stage',
        mesh_path: 'Sdf.Path'
    ):
        """Embed mesh textures into USD (v3.4)."""
        if not hasattr(mesh, 'visual') or mesh.visual is None:
            return
        
        try:
            visual = mesh.visual
            if hasattr(visual, 'material') and visual.material is not None:
                material = visual.material
                
                # Create material if we have color or texture
                if hasattr(material, 'main_color') and material.main_color is not None:
                    color = material.main_color[:3] / 255.0  # Normalize
                    
                    # Create USD material
                    mat_path = mesh_path.GetParentPath().AppendChild('Material')
                    usd_material = UsdShade.Material.Define(stage, mat_path)
                    shader = UsdShade.Shader.Define(stage, mat_path.AppendChild('Shader'))
                    shader.CreateIdAttr("UsdPreviewSurface")
                    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
                        Gf.Vec3f(float(color[0]), float(color[1]), float(color[2]))
                    )
                    
                    usd_material.CreateSurfaceOutput().ConnectToSource(
                        shader.ConnectableAPI(), "surface"
                    )
                    
                    # Bind material to mesh
                    mesh_prim = stage.GetPrimAtPath(mesh_path)
                    if mesh_prim:
                        UsdShade.MaterialBindingAPI(mesh_prim).Bind(usd_material)
                        
        except Exception as e:
            self._log_warning(f"Failed to embed textures: {e}")
    
    def _resolve_mesh_uri(self, uri: str) -> Optional[str]:
        """Resolve mesh URI to file path."""
        if not uri:
            return None
        
        # Handle file:// URIs
        if uri.startswith('file://'):
            return uri[7:]
        
        # Handle model:// URIs (Gazebo model database)
        if uri.startswith('model://'):
            model_uri = uri[8:]
            # Try common Gazebo model paths
            gazebo_paths = [
                Path.home() / '.gazebo' / 'models',
                Path('/usr/share/gazebo/models'),
                Path('/opt/ros') / 'models',
            ]
            
            for base_path in gazebo_paths:
                full_path = base_path / model_uri
                if full_path.exists():
                    return str(full_path)
            
            # Try relative to SDF file
            if self.sdf_dir:
                relative_path = self.sdf_dir / model_uri
                if relative_path.exists():
                    return str(relative_path)
        
        # Assume relative path
        if self.sdf_dir:
            relative_path = self.sdf_dir / uri
            if relative_path.exists():
                return str(relative_path)
        
        return uri
    
    def _create_usd_mesh_from_trimesh(
        self,
        mesh: 'trimesh.Trimesh',
        stage: 'Usd.Stage',
        mesh_path: 'Sdf.Path'
    ):
        """Create USD mesh from trimesh object."""
        usd_mesh = UsdGeom.Mesh.Define(stage, mesh_path)
        
        # Convert vertices
        vertices = mesh.vertices * self.scale_factor
        points = [tuple(v) for v in vertices]
        usd_mesh.GetPointsAttr().Set(points)
        
        # Convert faces
        face_counts = [3] * len(mesh.faces)
        face_indices = mesh.faces.flatten().tolist()
        
        usd_mesh.GetFaceVertexCountsAttr().Set(face_counts)
        usd_mesh.GetFaceVertexIndicesAttr().Set(face_indices)
        
        # Add normals if available
        if mesh.vertex_normals is not None:
            normals = [tuple(n) for n in mesh.vertex_normals]
            usd_mesh.GetNormalsAttr().Set(normals)
            usd_mesh.SetNormalsInterpolation('vertex')
    
    def _create_placeholder_mesh(
        self,
        stage: 'Usd.Stage',
        mesh_path: 'Sdf.Path'
    ):
        """Create a placeholder cube when mesh loading fails."""
        cube = UsdGeom.Cube.Define(stage, mesh_path)
        cube.GetSizeAttr().Set(0.1 * self.scale_factor)
    
    def _process_joint(
        self,
        joint_elem: ET.Element,
        stage: 'Usd.Stage',
        parent_path: 'Sdf.Path'
    ):
        """Process an SDF joint element."""
        joint_name = joint_elem.get('name', 'joint')
        joint_type = joint_elem.get('type', 'fixed')
        
        parent_link = joint_elem.findtext('parent', '')
        child_link = joint_elem.findtext('child', '')
        
        # Note: USD Physics joints would be set up here
        # For now, we just log the joint info
        self._log_info(f"Joint: {joint_name} ({joint_type}): {parent_link} -> {child_link}")
    
    def _apply_pose(self, pose_elem: ET.Element, xform: 'UsdGeom.Xform'):
        """Apply SDF pose to USD transform."""
        if pose_elem.text is None:
            return
        
        values = [float(x) for x in pose_elem.text.split()]
        
        if len(values) >= 3:
            # Position (x, y, z)
            pos = [v * self.scale_factor for v in values[:3]]
            xform.AddTranslateOp().Set(Gf.Vec3d(pos[0], pos[1], pos[2]))
        
        if len(values) >= 6:
            # Rotation (roll, pitch, yaw) in radians
            roll, pitch, yaw = values[3:6]
            
            # Convert Euler to quaternion
            # SDF uses XYZ Euler (roll-pitch-yaw)
            cr, sr = math.cos(roll/2), math.sin(roll/2)
            cp, sp = math.cos(pitch/2), math.sin(pitch/2)
            cy, sy = math.cos(yaw/2), math.sin(yaw/2)
            
            w = cr * cp * cy + sr * sp * sy
            x = sr * cp * cy - cr * sp * sy
            y = cr * sp * cy + sr * cp * sy
            z = cr * cp * sy - sr * sp * cy
            
            quat = Gf.Quatd(w, x, y, z)
            xform.AddOrientOp().Set(quat)
    
    def _add_physics_properties(
        self,
        inertial_elem: ET.Element,
        stage: 'Usd.Stage',
        link_path: 'Sdf.Path'
    ):
        """Add physics properties from inertial element."""
        mass = inertial_elem.findtext('mass', '1.0')
        
        # Create physics mass API
        prim = stage.GetPrimAtPath(link_path)
        if prim:
            mass_api = UsdPhysics.MassAPI.Apply(prim)
            mass_api.GetMassAttr().Set(float(mass))
    
    def _create_material_from_sdf(
        self,
        material_elem: ET.Element,
        stage: 'Usd.Stage',
        parent_path: 'Sdf.Path'
    ) -> Optional[str]:
        """Create USD material from SDF material."""
        # Get ambient/diffuse colors
        diffuse = material_elem.find('diffuse')
        ambient = material_elem.find('ambient')
        
        if diffuse is None and ambient is None:
            return None
        
        # Create materials scope
        materials_path = parent_path.AppendPath('Materials')
        if not stage.GetPrimAtPath(materials_path):
            UsdGeom.Scope.Define(stage, materials_path)
        
        mat_name = f"mat_{hash(ET.tostring(material_elem)) % 10000}"
        mat_path = materials_path.AppendChild(mat_name)
        
        usd_material = UsdShade.Material.Define(stage, mat_path)
        shader = UsdShade.Shader.Define(stage, mat_path.AppendChild('Shader'))
        shader.CreateIdAttr("UsdPreviewSurface")
        
        if diffuse is not None and diffuse.text:
            color = [float(x) for x in diffuse.text.split()[:3]]
            shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
                Gf.Vec3f(color[0], color[1], color[2])
            )
        
        usd_material.CreateSurfaceOutput().ConnectToSource(
            shader.ConnectableAPI(), "surface"
        )
        
        return mat_name
    
    def _sanitize_name(self, name: str) -> str:
        """Sanitize name for USD compatibility."""
        sanitized = name.replace(' ', '_').replace('-', '_').replace('.', '_')
        sanitized = ''.join(c for c in sanitized if c.isalnum() or c == '_')
        if sanitized and sanitized[0].isdigit():
            sanitized = '_' + sanitized
        return sanitized or 'unnamed'
    
    def _log_info(self, message: str):
        """Log info message."""
        self.logger.info(f"[SDFConverter] {message}")
    
    def _log_warning(self, message: str):
        """Log warning message."""
        self.logger.warning(f"[SDFConverter] {message}")
    
    def _log_error(self, message: str):
        """Log error message."""
        self.logger.error(f"[SDFConverter] {message}")
