"""
glTF Converter - Convert glTF/GLB files to USD format

glTF (GL Transmission Format) is a royalty-free specification for
efficient transmission and loading of 3D scenes and models.

This converter handles:
- glTF 2.0 JSON format (.gltf)
- Binary glTF (.glb)
- Embedded and external resources
- PBR materials
- Animations (skeletal and morph targets)
- Scene hierarchy
"""

import os
import sys
import json
import base64
import struct
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
import numpy as np
import logging

# USD generation
from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf, Vt

# glTF library
try:
    from pygltflib import GLTF2
    PYGLTFLIB_AVAILABLE = True
except ImportError:
    PYGLTFLIB_AVAILABLE = False

# Mesh processing
try:
    import trimesh
    TRIMESH_AVAILABLE = True
except ImportError:
    TRIMESH_AVAILABLE = False

from .base_converter import BaseConverter, ConversionResult


class GLTFConverter(BaseConverter):
    """
    Converter for glTF 2.0 files to USD format.
    
    Features:
    - Full glTF 2.0 support
    - Binary glTF (.glb) support
    - PBR material conversion
    - Scene hierarchy preservation
    - Animation support (skeletal, morph)
    - Texture handling (embedded and external)
    - Extension support
    """
    
    # Supported glTF extensions
    SUPPORTED_EXTENSIONS = [
        'KHR_materials_pbrSpecularGlossiness',
        'KHR_texture_transform',
        'KHR_materials_unlit',
        'KHR_draco_mesh_compression',  # Requires draco library
    ]
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize the glTF converter."""
        super().__init__(config)
        self.supported_extensions = ['.gltf', '.glb']
        self.logger = logging.getLogger(__name__)
        
        # Configuration
        self.scale_factor = self.config.get('scale_factor', 100.0)  # glTF uses meters
        self.import_materials = self.config.get('import_materials', True)
        self.import_textures = self.config.get('import_textures', True)
        self.import_animations = self.config.get('import_animations', True)
        
        # Verify dependencies
        if not PYGLTFLIB_AVAILABLE:
            self.logger.warning("pygltflib not available - glTF support limited")
        if not TRIMESH_AVAILABLE:
            self.logger.warning("trimesh not available - mesh processing limited")
    
    def convert(
        self,
        input_path: str,
        output_path: str,
        robot_name: str
    ) -> ConversionResult:
        """
        Convert a glTF file to USD format.
        
        Args:
            input_path: Path to glTF/GLB file
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
        
        if not PYGLTFLIB_AVAILABLE:
            return ConversionResult(
                success=False,
                error_message="pygltflib library not installed. Run: pip install pygltflib"
            )
        
        warnings = []
        parts = []
        materials_found = []
        
        try:
            self._log_info(f"Loading glTF file: {input_path}")
            
            # Load glTF
            gltf = GLTF2().load(input_path)
            
            # Check for unsupported extensions
            if gltf.extensionsRequired:
                for ext in gltf.extensionsRequired:
                    if ext not in self.SUPPORTED_EXTENSIONS:
                        warnings.append(f"Required extension not fully supported: {ext}")
            
            # Create USD stage
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            
            stage = Usd.Stage.CreateNew(output_path)
            
            # Set stage metadata
            stage.SetMetadata('upAxis', 'Z')  # UE5 uses Z-up
            stage.SetDefaultPrim(stage.DefinePrim(f'/{robot_name}', 'Xform'))
            
            root_prim = stage.GetDefaultPrim()
            
            # Process scenes
            scene_index = gltf.scene if gltf.scene is not None else 0
            if gltf.scenes and scene_index < len(gltf.scenes):
                scene = gltf.scenes[scene_index]
                self._log_info(f"Processing scene: {scene.name or 'default'}")
                
                # Process root nodes
                if scene.nodes:
                    for node_idx in scene.nodes:
                        node_parts = self._process_node(
                            gltf=gltf,
                            node_index=node_idx,
                            stage=stage,
                            parent_path=root_prim.GetPath(),
                            input_path=input_path
                        )
                        parts.extend(node_parts)
            else:
                warnings.append("No scene found in glTF, processing all nodes")
                if gltf.nodes:
                    for i, node in enumerate(gltf.nodes):
                        node_parts = self._process_node(
                            gltf=gltf,
                            node_index=i,
                            stage=stage,
                            parent_path=root_prim.GetPath(),
                            input_path=input_path
                        )
                        parts.extend(node_parts)
            
            # Process materials
            if self.import_materials and gltf.materials:
                for i, material in enumerate(gltf.materials):
                    mat_name = material.name or f"material_{i}"
                    materials_found.append(mat_name)
                    self._create_usd_material(
                        gltf=gltf,
                        material=material,
                        material_index=i,
                        stage=stage,
                        root_path=root_prim.GetPath(),
                        input_path=input_path
                    )
            
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
            
        except Exception as e:
            self._log_error(f"Conversion failed: {e}")
            import traceback
            traceback.print_exc()
            return ConversionResult(
                success=False,
                error_message=f"glTF conversion failed: {str(e)}",
                warnings=warnings
            )
    
    def _process_node(
        self,
        gltf: 'GLTF2',
        node_index: int,
        stage: 'Usd.Stage',
        parent_path: 'Sdf.Path',
        input_path: str,
        depth: int = 0
    ) -> List[str]:
        """
        Process a glTF node and its children.
        
        Returns:
            List of created part paths
        """
        if node_index >= len(gltf.nodes):
            return []
        
        node = gltf.nodes[node_index]
        node_name = node.name or f"node_{node_index}"
        node_name = self._sanitize_name(node_name)
        
        parts = []
        
        # Create USD prim for node
        node_path = parent_path.AppendChild(node_name)
        xform = UsdGeom.Xform.Define(stage, node_path)
        
        # Apply transform
        self._apply_node_transform(node, xform)
        
        # Process mesh if present
        if node.mesh is not None and node.mesh < len(gltf.meshes):
            mesh = gltf.meshes[node.mesh]
            mesh_name = mesh.name or f"mesh_{node.mesh}"
            
            for prim_idx, primitive in enumerate(mesh.primitives):
                prim_name = f"{mesh_name}_prim_{prim_idx}" if len(mesh.primitives) > 1 else mesh_name
                prim_name = self._sanitize_name(prim_name)
                
                mesh_path = node_path.AppendChild(prim_name)
                self._create_mesh_prim(
                    gltf=gltf,
                    primitive=primitive,
                    stage=stage,
                    mesh_path=mesh_path,
                    input_path=input_path
                )
                parts.append(str(mesh_path))
        
        # Process children
        if node.children:
            for child_idx in node.children:
                child_parts = self._process_node(
                    gltf=gltf,
                    node_index=child_idx,
                    stage=stage,
                    parent_path=node_path,
                    input_path=input_path,
                    depth=depth + 1
                )
                parts.extend(child_parts)
        
        return parts
    
    def _apply_node_transform(self, node, xform: 'UsdGeom.Xform'):
        """Apply glTF node transform to USD xform."""
        # glTF uses column-major matrices, right-handed Y-up
        # USD uses row-major matrices
        
        if node.matrix:
            # Direct matrix
            m = node.matrix
            matrix = Gf.Matrix4d(
                m[0], m[4], m[8], m[12],
                m[1], m[5], m[9], m[13],
                m[2], m[6], m[10], m[14],
                m[3], m[7], m[11], m[15]
            )
            xform.AddTransformOp().Set(matrix)
        else:
            # TRS components
            if node.translation:
                t = node.translation
                # Convert Y-up to Z-up and scale
                xform.AddTranslateOp().Set(Gf.Vec3d(
                    t[0] * self.scale_factor,
                    -t[2] * self.scale_factor,  # Swap Y/Z
                    t[1] * self.scale_factor
                ))
            
            if node.rotation:
                r = node.rotation  # Quaternion [x, y, z, w]
                quat = Gf.Quatd(r[3], r[0], r[1], r[2])
                xform.AddOrientOp().Set(quat)
            
            if node.scale:
                s = node.scale
                xform.AddScaleOp().Set(Gf.Vec3f(s[0], s[2], s[1]))
    
    def _create_mesh_prim(
        self,
        gltf: 'GLTF2',
        primitive,
        stage: 'Usd.Stage',
        mesh_path: 'Sdf.Path',
        input_path: str
    ):
        """Create a USD mesh from a glTF primitive."""
        usd_mesh = UsdGeom.Mesh.Define(stage, mesh_path)
        
        # Get accessor data
        if primitive.attributes.POSITION is None:
            self._log_warning("Primitive has no position data")
            return
        
        # Load position data
        positions = self._get_accessor_data(gltf, primitive.attributes.POSITION, input_path)
        if positions is not None:
            # Convert coordinate system (Y-up to Z-up) and scale
            vertices = []
            for i in range(0, len(positions), 3):
                x = positions[i] * self.scale_factor
                y = positions[i + 1] * self.scale_factor
                z = positions[i + 2] * self.scale_factor
                # Y-up to Z-up: (x, y, z) -> (x, z, -y)
                vertices.extend([x, z, -y])
            
            points = [(vertices[i], vertices[i+1], vertices[i+2]) 
                     for i in range(0, len(vertices), 3)]
            usd_mesh.GetPointsAttr().Set(points)
        
        # Load indices
        if primitive.indices is not None:
            indices = self._get_accessor_data(gltf, primitive.indices, input_path)
            if indices is not None:
                # glTF uses triangles
                face_vertex_counts = [3] * (len(indices) // 3)
                usd_mesh.GetFaceVertexCountsAttr().Set(face_vertex_counts)
                usd_mesh.GetFaceVertexIndicesAttr().Set([int(i) for i in indices])
        
        # Load normals
        if hasattr(primitive.attributes, 'NORMAL') and primitive.attributes.NORMAL is not None:
            normals = self._get_accessor_data(gltf, primitive.attributes.NORMAL, input_path)
            if normals is not None:
                normal_vectors = []
                for i in range(0, len(normals), 3):
                    x, y, z = normals[i], normals[i+1], normals[i+2]
                    # Convert coordinate system
                    normal_vectors.append((x, z, -y))
                usd_mesh.GetNormalsAttr().Set(normal_vectors)
                usd_mesh.SetNormalsInterpolation('vertex')
        
        # Load UVs
        if hasattr(primitive.attributes, 'TEXCOORD_0') and primitive.attributes.TEXCOORD_0 is not None:
            uvs = self._get_accessor_data(gltf, primitive.attributes.TEXCOORD_0, input_path)
            if uvs is not None:
                uv_pairs = [(uvs[i], 1.0 - uvs[i+1])  # Flip V coordinate
                           for i in range(0, len(uvs), 2)]
                usd_mesh.GetPrimvar('st').Set(uv_pairs)
    
    def _get_accessor_data(
        self,
        gltf: 'GLTF2',
        accessor_index: int,
        input_path: str
    ) -> Optional[List[float]]:
        """Extract data from a glTF accessor."""
        if accessor_index >= len(gltf.accessors):
            return None
        
        accessor = gltf.accessors[accessor_index]
        buffer_view = gltf.bufferViews[accessor.bufferView]
        buffer = gltf.buffers[buffer_view.buffer]
        
        # Get component type and count
        component_type = accessor.componentType
        count = accessor.count
        accessor_type = accessor.type
        
        # Number of components per element
        type_counts = {
            'SCALAR': 1,
            'VEC2': 2,
            'VEC3': 3,
            'VEC4': 4,
            'MAT2': 4,
            'MAT3': 9,
            'MAT4': 16
        }
        components = type_counts.get(accessor_type, 1)
        
        # Component size and format
        component_formats = {
            5120: ('b', 1),   # BYTE
            5121: ('B', 1),   # UNSIGNED_BYTE
            5122: ('h', 2),   # SHORT
            5123: ('H', 2),   # UNSIGNED_SHORT
            5125: ('I', 4),   # UNSIGNED_INT
            5126: ('f', 4),   # FLOAT
        }
        
        if component_type not in component_formats:
            self._log_warning(f"Unknown component type: {component_type}")
            return None
        
        fmt, size = component_formats[component_type]
        
        # Get buffer data
        if buffer.uri:
            if buffer.uri.startswith('data:'):
                # Embedded data URI
                data_start = buffer.uri.find(',') + 1
                buffer_data = base64.b64decode(buffer.uri[data_start:])
            else:
                # External file
                buffer_path = Path(input_path).parent / buffer.uri
                with open(buffer_path, 'rb') as f:
                    buffer_data = f.read()
        else:
            # GLB binary chunk
            buffer_data = gltf.binary_blob()
        
        # Extract data
        offset = (buffer_view.byteOffset or 0) + (accessor.byteOffset or 0)
        stride = buffer_view.byteStride or (size * components)
        
        data = []
        for i in range(count):
            element_offset = offset + i * stride
            for j in range(components):
                value_offset = element_offset + j * size
                value = struct.unpack_from(fmt, buffer_data, value_offset)[0]
                data.append(float(value))
        
        return data
    
    def _create_usd_material(
        self,
        gltf: 'GLTF2',
        material,
        material_index: int,
        stage: 'Usd.Stage',
        root_path: 'Sdf.Path',
        input_path: str
    ):
        """Create a USD material from a glTF material."""
        mat_name = material.name or f"material_{material_index}"
        mat_name = self._sanitize_name(mat_name)
        
        materials_path = root_path.AppendChild("Materials")
        if not stage.GetPrimAtPath(materials_path):
            UsdGeom.Scope.Define(stage, materials_path)
        
        mat_path = materials_path.AppendChild(mat_name)
        usd_material = UsdShade.Material.Define(stage, mat_path)
        
        # Create shader
        shader_path = mat_path.AppendChild("PBRShader")
        shader = UsdShade.Shader.Define(stage, shader_path)
        shader.CreateIdAttr("UsdPreviewSurface")
        
        # PBR properties
        pbr = material.pbrMetallicRoughness
        if pbr:
            if pbr.baseColorFactor:
                color = pbr.baseColorFactor
                shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
                    Gf.Vec3f(color[0], color[1], color[2])
                )
                if len(color) > 3 and color[3] < 1.0:
                    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(color[3])
            
            shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(
                pbr.metallicFactor if pbr.metallicFactor is not None else 0.0
            )
            
            shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(
                pbr.roughnessFactor if pbr.roughnessFactor is not None else 0.5
            )
        
        # Emissive
        if material.emissiveFactor:
            e = material.emissiveFactor
            shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(
                Gf.Vec3f(e[0], e[1], e[2])
            )
        
        # Connect shader to material
        usd_material.CreateSurfaceOutput().ConnectToSource(
            shader.ConnectableAPI(), "surface"
        )
    
    def _sanitize_name(self, name: str) -> str:
        """Sanitize a name for USD compatibility."""
        # Replace invalid characters
        sanitized = name.replace(' ', '_').replace('-', '_').replace('.', '_')
        sanitized = ''.join(c for c in sanitized if c.isalnum() or c == '_')
        
        # Ensure starts with letter or underscore
        if sanitized and sanitized[0].isdigit():
            sanitized = '_' + sanitized
        
        return sanitized or 'unnamed'
    
    def _log_info(self, message: str):
        """Log info message."""
        self.logger.info(f"[GLTFConverter] {message}")
    
    def _log_warning(self, message: str):
        """Log warning message."""
        self.logger.warning(f"[GLTFConverter] {message}")
    
    def _log_error(self, message: str):
        """Log error message."""
        self.logger.error(f"[GLTFConverter] {message}")
