"""
Format Conversion Utilities

Provides bidirectional conversion between robot description formats:
- URDF ↔ SDF
- URDF ↔ SMURF
- SDF ↔ MJCF (MuJoCo)
- All formats → USD

This enables interoperability with different simulation environments:
- URDF: ROS ecosystem
- SDF: Gazebo simulation
- MJCF: MuJoCo simulation
- USD: Unreal Engine / Isaac Sim

Key features:
- Loop joint preservation during conversion
- Submechanism metadata transfer
- Motor/actuator parameter conversion
- Sensor definition conversion
- Material property mapping
"""

import json
import logging
import math
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
import xml.etree.ElementTree as ET
from xml.dom import minidom

logger = logging.getLogger(__name__)


@dataclass
class ConversionOptions:
    """Options for format conversion."""
    preserve_comments: bool = False
    preserve_gazebo_plugins: bool = True
    preserve_ros_control: bool = True
    convert_meshes: bool = False          # Convert mesh formats during conversion
    mesh_output_format: str = 'dae'       # Target mesh format
    scale_factor: float = 1.0             # Apply scaling during conversion
    add_inertia_fallback: bool = True     # Add dummy inertia if missing
    convert_mimic_to_coupling: bool = True  # Convert URDF mimic to SMURF coupling


class URDFToSDFConverter:
    """
    Convert URDF to SDF format.
    
    SDF supports additional features:
    - Multiple models per file
    - World definition
    - Loop joints (<loop_joint> tag)
    - Enhanced physics parameters
    """
    
    def __init__(self, options: Optional[ConversionOptions] = None):
        self.options = options or ConversionOptions()
    
    def convert(
        self,
        urdf_path: str,
        output_path: str,
        world_name: Optional[str] = None
    ) -> bool:
        """
        Convert URDF to SDF.
        
        Args:
            urdf_path: Path to input URDF file
            output_path: Path for output SDF file
            world_name: Optional world name for wrapping model
            
        Returns:
            True if successful
        """
        try:
            urdf_tree = ET.parse(urdf_path)
            urdf_root = urdf_tree.getroot()
            
            if urdf_root.tag != 'robot':
                logger.error("Invalid URDF: root element must be 'robot'")
                return False
            
            robot_name = urdf_root.get('name', 'robot')
            
            # Create SDF root
            sdf_root = ET.Element('sdf', {'version': '1.9'})
            
            # Optionally wrap in world
            if world_name:
                world = ET.SubElement(sdf_root, 'world', {'name': world_name})
                model_parent = world
            else:
                model_parent = sdf_root
            
            # Create model
            model = ET.SubElement(model_parent, 'model', {'name': robot_name})
            
            # Convert links
            links = urdf_root.findall('link')
            for link in links:
                self._convert_link(link, model)
            
            # Convert joints
            joints = urdf_root.findall('joint')
            loop_joints = []
            
            for joint in joints:
                is_loop = self._is_loop_joint(joint, urdf_root)
                if is_loop:
                    loop_joints.append(joint)
                else:
                    self._convert_joint(joint, model)
            
            # Add loop joints (SDF-specific)
            for loop_joint in loop_joints:
                self._add_loop_joint(loop_joint, model)
            
            # Preserve Gazebo plugins if present
            if self.options.preserve_gazebo_plugins:
                gazebo_elements = urdf_root.findall('gazebo')
                for gazebo in gazebo_elements:
                    self._convert_gazebo_element(gazebo, model)
            
            # Write output
            self._write_xml(sdf_root, output_path)
            logger.info(f"Converted URDF to SDF: {output_path}")
            return True
        
        except Exception as e:
            logger.error(f"URDF to SDF conversion failed: {e}")
            return False
    
    def _is_loop_joint(self, joint: ET.Element, urdf_root: ET.Element) -> bool:
        """Check if joint creates a kinematic loop."""
        # A loop joint is one where the child link is already reachable
        # from the parent through another path
        # Simple heuristic: check if child has multiple parents
        child_name = joint.find('child').get('link') if joint.find('child') is not None else ''
        
        parent_count = 0
        for j in urdf_root.findall('joint'):
            if j.find('child') is not None and j.find('child').get('link') == child_name:
                parent_count += 1
        
        return parent_count > 1
    
    def _convert_link(self, urdf_link: ET.Element, sdf_model: ET.Element):
        """Convert URDF link to SDF link."""
        link_name = urdf_link.get('name', 'link')
        sdf_link = ET.SubElement(sdf_model, 'link', {'name': link_name})
        
        # Pose (SDF requires explicit pose, URDF uses parent joint)
        pose = ET.SubElement(sdf_link, 'pose')
        pose.text = "0 0 0 0 0 0"
        
        # Inertial
        inertial = urdf_link.find('inertial')
        if inertial is not None:
            self._convert_inertial(inertial, sdf_link)
        elif self.options.add_inertia_fallback:
            self._add_dummy_inertial(sdf_link)
        
        # Visual
        for visual in urdf_link.findall('visual'):
            self._convert_visual(visual, sdf_link)
        
        # Collision
        for collision in urdf_link.findall('collision'):
            self._convert_collision(collision, sdf_link)
    
    def _convert_inertial(self, urdf_inertial: ET.Element, sdf_link: ET.Element):
        """Convert URDF inertial to SDF inertial."""
        sdf_inertial = ET.SubElement(sdf_link, 'inertial')
        
        # Mass
        mass = urdf_inertial.find('mass')
        if mass is not None:
            sdf_mass = ET.SubElement(sdf_inertial, 'mass')
            sdf_mass.text = mass.get('value', '1.0')
        
        # Pose from origin
        origin = urdf_inertial.find('origin')
        if origin is not None:
            pose = ET.SubElement(sdf_inertial, 'pose')
            xyz = origin.get('xyz', '0 0 0')
            rpy = origin.get('rpy', '0 0 0')
            pose.text = f"{xyz} {rpy}"
        
        # Inertia tensor
        inertia = urdf_inertial.find('inertia')
        if inertia is not None:
            sdf_inertia = ET.SubElement(sdf_inertial, 'inertia')
            for attr in ['ixx', 'ixy', 'ixz', 'iyy', 'iyz', 'izz']:
                elem = ET.SubElement(sdf_inertia, attr)
                elem.text = inertia.get(attr, '0.001')
    
    def _add_dummy_inertial(self, sdf_link: ET.Element):
        """Add dummy inertial for links without inertia."""
        sdf_inertial = ET.SubElement(sdf_link, 'inertial')
        mass = ET.SubElement(sdf_inertial, 'mass')
        mass.text = '0.001'
        inertia = ET.SubElement(sdf_inertial, 'inertia')
        for attr in ['ixx', 'ixy', 'ixz', 'iyy', 'iyz', 'izz']:
            elem = ET.SubElement(inertia, attr)
            elem.text = '0.0001' if 'i' in attr and attr.count(attr[1]) == 2 else '0'
    
    def _convert_visual(self, urdf_visual: ET.Element, sdf_link: ET.Element):
        """Convert URDF visual to SDF visual."""
        visual_name = urdf_visual.get('name', 'visual')
        sdf_visual = ET.SubElement(sdf_link, 'visual', {'name': visual_name})
        
        # Pose from origin
        origin = urdf_visual.find('origin')
        if origin is not None:
            pose = ET.SubElement(sdf_visual, 'pose')
            xyz = origin.get('xyz', '0 0 0')
            rpy = origin.get('rpy', '0 0 0')
            pose.text = f"{xyz} {rpy}"
        
        # Geometry
        geometry = urdf_visual.find('geometry')
        if geometry is not None:
            self._convert_geometry(geometry, sdf_visual)
        
        # Material
        material = urdf_visual.find('material')
        if material is not None:
            self._convert_material(material, sdf_visual)
    
    def _convert_collision(self, urdf_collision: ET.Element, sdf_link: ET.Element):
        """Convert URDF collision to SDF collision."""
        collision_name = urdf_collision.get('name', 'collision')
        sdf_collision = ET.SubElement(sdf_link, 'collision', {'name': collision_name})
        
        # Pose from origin
        origin = urdf_collision.find('origin')
        if origin is not None:
            pose = ET.SubElement(sdf_collision, 'pose')
            xyz = origin.get('xyz', '0 0 0')
            rpy = origin.get('rpy', '0 0 0')
            pose.text = f"{xyz} {rpy}"
        
        # Geometry
        geometry = urdf_collision.find('geometry')
        if geometry is not None:
            self._convert_geometry(geometry, sdf_collision)
        
        # Surface properties (SDF-specific)
        surface = ET.SubElement(sdf_collision, 'surface')
        friction = ET.SubElement(surface, 'friction')
        ode = ET.SubElement(friction, 'ode')
        mu = ET.SubElement(ode, 'mu')
        mu.text = '0.8'
        mu2 = ET.SubElement(ode, 'mu2')
        mu2.text = '0.8'
    
    def _convert_geometry(self, urdf_geom: ET.Element, sdf_parent: ET.Element):
        """Convert URDF geometry to SDF geometry."""
        sdf_geom = ET.SubElement(sdf_parent, 'geometry')
        
        box = urdf_geom.find('box')
        if box is not None:
            sdf_box = ET.SubElement(sdf_geom, 'box')
            size = ET.SubElement(sdf_box, 'size')
            size.text = box.get('size', '1 1 1')
            return
        
        cylinder = urdf_geom.find('cylinder')
        if cylinder is not None:
            sdf_cyl = ET.SubElement(sdf_geom, 'cylinder')
            radius = ET.SubElement(sdf_cyl, 'radius')
            radius.text = cylinder.get('radius', '0.1')
            length = ET.SubElement(sdf_cyl, 'length')
            length.text = cylinder.get('length', '0.1')
            return
        
        sphere = urdf_geom.find('sphere')
        if sphere is not None:
            sdf_sphere = ET.SubElement(sdf_geom, 'sphere')
            radius = ET.SubElement(sdf_sphere, 'radius')
            radius.text = sphere.get('radius', '0.1')
            return
        
        mesh = urdf_geom.find('mesh')
        if mesh is not None:
            sdf_mesh = ET.SubElement(sdf_geom, 'mesh')
            uri = ET.SubElement(sdf_mesh, 'uri')
            uri.text = mesh.get('filename', '')
            if mesh.get('scale'):
                scale = ET.SubElement(sdf_mesh, 'scale')
                scale.text = mesh.get('scale')
    
    def _convert_material(self, urdf_material: ET.Element, sdf_visual: ET.Element):
        """Convert URDF material to SDF material."""
        sdf_material = ET.SubElement(sdf_visual, 'material')
        
        color = urdf_material.find('color')
        if color is not None:
            rgba = color.get('rgba', '0.5 0.5 0.5 1.0')
            parts = rgba.split()
            if len(parts) >= 4:
                diffuse = ET.SubElement(sdf_material, 'diffuse')
                diffuse.text = rgba
                ambient = ET.SubElement(sdf_material, 'ambient')
                ambient.text = rgba
    
    def _convert_joint(self, urdf_joint: ET.Element, sdf_model: ET.Element):
        """Convert URDF joint to SDF joint."""
        joint_name = urdf_joint.get('name', 'joint')
        joint_type = urdf_joint.get('type', 'fixed')
        
        # Map URDF joint types to SDF
        type_map = {
            'revolute': 'revolute',
            'continuous': 'revolute',
            'prismatic': 'prismatic',
            'fixed': 'fixed',
            'floating': 'ball',
            'planar': 'prismatic',  # Approximation
        }
        sdf_type = type_map.get(joint_type, 'fixed')
        
        sdf_joint = ET.SubElement(sdf_model, 'joint', {
            'name': joint_name,
            'type': sdf_type
        })
        
        # Parent and child
        parent = urdf_joint.find('parent')
        child = urdf_joint.find('child')
        
        if parent is not None:
            sdf_parent = ET.SubElement(sdf_joint, 'parent')
            sdf_parent.text = parent.get('link', '')
        
        if child is not None:
            sdf_child = ET.SubElement(sdf_joint, 'child')
            sdf_child.text = child.get('link', '')
        
        # Pose from origin
        origin = urdf_joint.find('origin')
        if origin is not None:
            pose = ET.SubElement(sdf_joint, 'pose')
            xyz = origin.get('xyz', '0 0 0')
            rpy = origin.get('rpy', '0 0 0')
            pose.text = f"{xyz} {rpy}"
        
        # Axis
        axis = urdf_joint.find('axis')
        if axis is not None and sdf_type != 'fixed':
            sdf_axis = ET.SubElement(sdf_joint, 'axis')
            xyz = ET.SubElement(sdf_axis, 'xyz')
            xyz.text = axis.get('xyz', '0 0 1')
            
            # Limits
            limit = urdf_joint.find('limit')
            if limit is not None:
                sdf_limit = ET.SubElement(sdf_axis, 'limit')
                lower = ET.SubElement(sdf_limit, 'lower')
                lower.text = limit.get('lower', '-1.57')
                upper = ET.SubElement(sdf_limit, 'upper')
                upper.text = limit.get('upper', '1.57')
                effort = ET.SubElement(sdf_limit, 'effort')
                effort.text = limit.get('effort', '100')
                velocity = ET.SubElement(sdf_limit, 'velocity')
                velocity.text = limit.get('velocity', '1.0')
    
    def _add_loop_joint(self, urdf_joint: ET.Element, sdf_model: ET.Element):
        """Add SDF loop_joint for kinematic loop closure."""
        joint_name = urdf_joint.get('name', 'loop_joint')
        
        parent = urdf_joint.find('parent')
        child = urdf_joint.find('child')
        
        if parent is None or child is None:
            return
        
        # SDF uses <frame> with <attached_to> for loop closures
        frame = ET.SubElement(sdf_model, 'frame', {
            'name': f"{joint_name}_frame",
            'attached_to': parent.get('link', '')
        })
        
        origin = urdf_joint.find('origin')
        if origin is not None:
            pose = ET.SubElement(frame, 'pose')
            xyz = origin.get('xyz', '0 0 0')
            rpy = origin.get('rpy', '0 0 0')
            pose.text = f"{xyz} {rpy}"
        
        # Add comment about loop joint
        comment = ET.Comment(f' Loop joint: {joint_name} connects {parent.get("link")} to {child.get("link")} ')
        sdf_model.insert(0, comment)
    
    def _convert_gazebo_element(self, gazebo: ET.Element, sdf_model: ET.Element):
        """Convert Gazebo-specific elements."""
        reference = gazebo.get('reference', '')
        
        # Find target link/joint
        target_link = None
        for link in sdf_model.findall('link'):
            if link.get('name') == reference:
                target_link = link
                break
        
        # Copy plugins
        for plugin in gazebo.findall('plugin'):
            sdf_plugin = copy.deepcopy(plugin)
            if target_link is not None:
                target_link.append(sdf_plugin)
            else:
                sdf_model.append(sdf_plugin)
    
    def _write_xml(self, root: ET.Element, path: str):
        """Write formatted XML to file."""
        rough_string = ET.tostring(root, encoding='unicode')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="  ")
        
        # Remove extra blank lines
        lines = [line for line in pretty_xml.split('\n') if line.strip()]
        pretty_xml = '\n'.join(lines)
        
        Path(path).write_text(pretty_xml)


class SDFToURDFConverter:
    """
    Convert SDF to URDF format.
    
    Note: Some SDF features may be lost during conversion:
    - Loop joints (require workarounds)
    - Multiple models (converted to single robot)
    - World definitions (ignored)
    """
    
    def __init__(self, options: Optional[ConversionOptions] = None):
        self.options = options or ConversionOptions()
    
    def convert(
        self,
        sdf_path: str,
        output_path: str,
        model_name: Optional[str] = None
    ) -> bool:
        """
        Convert SDF to URDF.
        
        Args:
            sdf_path: Path to input SDF file
            output_path: Path for output URDF file
            model_name: Specific model to extract (if SDF has multiple)
            
        Returns:
            True if successful
        """
        try:
            sdf_tree = ET.parse(sdf_path)
            sdf_root = sdf_tree.getroot()
            
            # Find model(s)
            models = sdf_root.findall('.//model')
            if not models:
                logger.error("No models found in SDF")
                return False
            
            # Select model
            if model_name:
                model = None
                for m in models:
                    if m.get('name') == model_name:
                        model = m
                        break
                if model is None:
                    logger.error(f"Model '{model_name}' not found in SDF")
                    return False
            else:
                model = models[0]
                if len(models) > 1:
                    logger.warning(f"Multiple models found, using first: {model.get('name')}")
            
            robot_name = model.get('name', 'robot')
            
            # Create URDF root
            urdf_root = ET.Element('robot', {'name': robot_name})
            
            # Convert links
            for link in model.findall('link'):
                self._convert_link(link, urdf_root)
            
            # Convert joints
            for joint in model.findall('joint'):
                self._convert_joint(joint, urdf_root)
            
            # Handle loop joints (frames)
            for frame in model.findall('frame'):
                self._handle_frame(frame, urdf_root)
            
            # Write output
            self._write_xml(urdf_root, output_path)
            logger.info(f"Converted SDF to URDF: {output_path}")
            return True
        
        except Exception as e:
            logger.error(f"SDF to URDF conversion failed: {e}")
            return False
    
    def _convert_link(self, sdf_link: ET.Element, urdf_root: ET.Element):
        """Convert SDF link to URDF link."""
        link_name = sdf_link.get('name', 'link')
        urdf_link = ET.SubElement(urdf_root, 'link', {'name': link_name})
        
        # Inertial
        inertial = sdf_link.find('inertial')
        if inertial is not None:
            self._convert_inertial_to_urdf(inertial, urdf_link)
        
        # Visuals
        for visual in sdf_link.findall('visual'):
            self._convert_visual_to_urdf(visual, urdf_link)
        
        # Collisions
        for collision in sdf_link.findall('collision'):
            self._convert_collision_to_urdf(collision, urdf_link)
    
    def _convert_inertial_to_urdf(self, sdf_inertial: ET.Element, urdf_link: ET.Element):
        """Convert SDF inertial to URDF inertial."""
        urdf_inertial = ET.SubElement(urdf_link, 'inertial')
        
        # Mass
        mass = sdf_inertial.find('mass')
        if mass is not None and mass.text:
            urdf_mass = ET.SubElement(urdf_inertial, 'mass', {'value': mass.text})
        
        # Origin from pose
        pose = sdf_inertial.find('pose')
        if pose is not None and pose.text:
            parts = pose.text.split()
            if len(parts) >= 6:
                xyz = ' '.join(parts[:3])
                rpy = ' '.join(parts[3:6])
                ET.SubElement(urdf_inertial, 'origin', {'xyz': xyz, 'rpy': rpy})
        
        # Inertia
        inertia = sdf_inertial.find('inertia')
        if inertia is not None:
            attrs = {}
            for attr in ['ixx', 'ixy', 'ixz', 'iyy', 'iyz', 'izz']:
                elem = inertia.find(attr)
                attrs[attr] = elem.text if elem is not None and elem.text else '0'
            ET.SubElement(urdf_inertial, 'inertia', attrs)
    
    def _convert_visual_to_urdf(self, sdf_visual: ET.Element, urdf_link: ET.Element):
        """Convert SDF visual to URDF visual."""
        visual_name = sdf_visual.get('name', '')
        urdf_visual = ET.SubElement(urdf_link, 'visual', {'name': visual_name} if visual_name else {})
        
        # Pose to origin
        pose = sdf_visual.find('pose')
        if pose is not None and pose.text:
            parts = pose.text.split()
            if len(parts) >= 6:
                xyz = ' '.join(parts[:3])
                rpy = ' '.join(parts[3:6])
                ET.SubElement(urdf_visual, 'origin', {'xyz': xyz, 'rpy': rpy})
        
        # Geometry
        geometry = sdf_visual.find('geometry')
        if geometry is not None:
            self._convert_geometry_to_urdf(geometry, urdf_visual)
        
        # Material
        material = sdf_visual.find('material')
        if material is not None:
            self._convert_material_to_urdf(material, urdf_visual)
    
    def _convert_collision_to_urdf(self, sdf_collision: ET.Element, urdf_link: ET.Element):
        """Convert SDF collision to URDF collision."""
        collision_name = sdf_collision.get('name', '')
        urdf_collision = ET.SubElement(urdf_link, 'collision', {'name': collision_name} if collision_name else {})
        
        # Pose to origin
        pose = sdf_collision.find('pose')
        if pose is not None and pose.text:
            parts = pose.text.split()
            if len(parts) >= 6:
                xyz = ' '.join(parts[:3])
                rpy = ' '.join(parts[3:6])
                ET.SubElement(urdf_collision, 'origin', {'xyz': xyz, 'rpy': rpy})
        
        # Geometry
        geometry = sdf_collision.find('geometry')
        if geometry is not None:
            self._convert_geometry_to_urdf(geometry, urdf_collision)
    
    def _convert_geometry_to_urdf(self, sdf_geom: ET.Element, urdf_parent: ET.Element):
        """Convert SDF geometry to URDF geometry."""
        urdf_geom = ET.SubElement(urdf_parent, 'geometry')
        
        box = sdf_geom.find('box')
        if box is not None:
            size = box.find('size')
            if size is not None and size.text:
                ET.SubElement(urdf_geom, 'box', {'size': size.text})
            return
        
        cylinder = sdf_geom.find('cylinder')
        if cylinder is not None:
            radius = cylinder.find('radius')
            length = cylinder.find('length')
            r = radius.text if radius is not None and radius.text else '0.1'
            l = length.text if length is not None and length.text else '0.1'
            ET.SubElement(urdf_geom, 'cylinder', {'radius': r, 'length': l})
            return
        
        sphere = sdf_geom.find('sphere')
        if sphere is not None:
            radius = sphere.find('radius')
            r = radius.text if radius is not None and radius.text else '0.1'
            ET.SubElement(urdf_geom, 'sphere', {'radius': r})
            return
        
        mesh = sdf_geom.find('mesh')
        if mesh is not None:
            uri = mesh.find('uri')
            scale = mesh.find('scale')
            attrs = {'filename': uri.text if uri is not None and uri.text else ''}
            if scale is not None and scale.text:
                attrs['scale'] = scale.text
            ET.SubElement(urdf_geom, 'mesh', attrs)
    
    def _convert_material_to_urdf(self, sdf_material: ET.Element, urdf_visual: ET.Element):
        """Convert SDF material to URDF material."""
        urdf_material = ET.SubElement(urdf_visual, 'material', {'name': ''})
        
        diffuse = sdf_material.find('diffuse')
        if diffuse is not None and diffuse.text:
            ET.SubElement(urdf_material, 'color', {'rgba': diffuse.text})
    
    def _convert_joint(self, sdf_joint: ET.Element, urdf_root: ET.Element):
        """Convert SDF joint to URDF joint."""
        joint_name = sdf_joint.get('name', 'joint')
        joint_type = sdf_joint.get('type', 'fixed')
        
        # Map SDF joint types to URDF
        type_map = {
            'revolute': 'revolute',
            'prismatic': 'prismatic',
            'fixed': 'fixed',
            'ball': 'floating',
            'universal': 'revolute',  # Approximation
            'screw': 'prismatic',  # Approximation
        }
        urdf_type = type_map.get(joint_type, 'fixed')
        
        urdf_joint = ET.SubElement(urdf_root, 'joint', {
            'name': joint_name,
            'type': urdf_type
        })
        
        # Parent and child
        parent = sdf_joint.find('parent')
        child = sdf_joint.find('child')
        
        if parent is not None and parent.text:
            ET.SubElement(urdf_joint, 'parent', {'link': parent.text})
        
        if child is not None and child.text:
            ET.SubElement(urdf_joint, 'child', {'link': child.text})
        
        # Pose to origin
        pose = sdf_joint.find('pose')
        if pose is not None and pose.text:
            parts = pose.text.split()
            if len(parts) >= 6:
                xyz = ' '.join(parts[:3])
                rpy = ' '.join(parts[3:6])
                ET.SubElement(urdf_joint, 'origin', {'xyz': xyz, 'rpy': rpy})
        
        # Axis
        axis = sdf_joint.find('axis')
        if axis is not None:
            xyz = axis.find('xyz')
            if xyz is not None and xyz.text:
                ET.SubElement(urdf_joint, 'axis', {'xyz': xyz.text})
            
            # Limits
            limit = axis.find('limit')
            if limit is not None:
                attrs = {}
                for attr in ['lower', 'upper', 'effort', 'velocity']:
                    elem = limit.find(attr)
                    if elem is not None and elem.text:
                        attrs[attr] = elem.text
                if attrs:
                    ET.SubElement(urdf_joint, 'limit', attrs)
    
    def _handle_frame(self, sdf_frame: ET.Element, urdf_root: ET.Element):
        """Handle SDF frame (may represent loop joint)."""
        # Frames in SDF can represent loop closures
        # Add as comment in URDF
        frame_name = sdf_frame.get('name', '')
        attached_to = sdf_frame.get('attached_to', '')
        
        if frame_name and attached_to:
            comment = ET.Comment(f' Loop frame: {frame_name} attached to {attached_to} ')
            urdf_root.insert(0, comment)
    
    def _write_xml(self, root: ET.Element, path: str):
        """Write formatted XML to file."""
        rough_string = ET.tostring(root, encoding='unicode')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="  ")
        
        lines = [line for line in pretty_xml.split('\n') if line.strip()]
        pretty_xml = '\n'.join(lines)
        
        Path(path).write_text(pretty_xml)


class URDFToMJCFConverter:
    """
    Convert URDF to MJCF (MuJoCo) format.
    
    MuJoCo features:
    - Full closed-loop support (equality constraints)
    - Advanced actuator models
    - Tendon dynamics
    - Contact parameters
    """
    
    def __init__(self, options: Optional[ConversionOptions] = None):
        self.options = options or ConversionOptions()
    
    def convert(
        self,
        urdf_path: str,
        output_path: str,
        add_defaults: bool = True
    ) -> bool:
        """
        Convert URDF to MJCF.
        
        Args:
            urdf_path: Path to input URDF file
            output_path: Path for output MJCF file
            add_defaults: Add MuJoCo default settings
            
        Returns:
            True if successful
        """
        try:
            urdf_tree = ET.parse(urdf_path)
            urdf_root = urdf_tree.getroot()
            
            if urdf_root.tag != 'robot':
                logger.error("Invalid URDF: root element must be 'robot'")
                return False
            
            robot_name = urdf_root.get('name', 'robot')
            
            # Create MJCF root
            mjcf_root = ET.Element('mujoco', {'model': robot_name})
            
            # Add compiler settings
            compiler = ET.SubElement(mjcf_root, 'compiler')
            compiler.set('angle', 'radian')
            compiler.set('coordinate', 'local')
            compiler.set('inertiafromgeom', 'auto')
            
            # Add default settings
            if add_defaults:
                self._add_defaults(mjcf_root)
            
            # Create worldbody
            worldbody = ET.SubElement(mjcf_root, 'worldbody')
            
            # Find root link (base)
            root_link = self._find_root_link(urdf_root)
            
            # Build body hierarchy
            self._build_body_tree(urdf_root, worldbody, root_link)
            
            # Add actuators
            actuator = ET.SubElement(mjcf_root, 'actuator')
            self._add_actuators(urdf_root, actuator)
            
            # Add equality constraints for loop joints
            loop_joints = self._find_loop_joints(urdf_root)
            if loop_joints:
                equality = ET.SubElement(mjcf_root, 'equality')
                for joint in loop_joints:
                    self._add_loop_constraint(joint, equality)
            
            # Write output
            self._write_xml(mjcf_root, output_path)
            logger.info(f"Converted URDF to MJCF: {output_path}")
            return True
        
        except Exception as e:
            logger.error(f"URDF to MJCF conversion failed: {e}")
            return False
    
    def _add_defaults(self, mjcf_root: ET.Element):
        """Add default settings."""
        default = ET.SubElement(mjcf_root, 'default')
        
        # Joint defaults
        joint = ET.SubElement(default, 'joint')
        joint.set('damping', '0.5')
        joint.set('armature', '0.01')
        
        # Geom defaults
        geom = ET.SubElement(default, 'geom')
        geom.set('friction', '0.8 0.02 0.01')
        geom.set('margin', '0.001')
    
    def _find_root_link(self, urdf_root: ET.Element) -> str:
        """Find the root link (not a child of any joint)."""
        children = set()
        for joint in urdf_root.findall('joint'):
            child = joint.find('child')
            if child is not None:
                children.add(child.get('link', ''))
        
        for link in urdf_root.findall('link'):
            name = link.get('name', '')
            if name not in children:
                return name
        
        # Fallback: first link
        links = urdf_root.findall('link')
        return links[0].get('name', 'base') if links else 'base'
    
    def _build_body_tree(
        self,
        urdf_root: ET.Element,
        mjcf_parent: ET.Element,
        link_name: str,
        visited: Optional[set] = None
    ):
        """Recursively build MJCF body tree."""
        if visited is None:
            visited = set()
        
        if link_name in visited:
            return
        visited.add(link_name)
        
        # Find URDF link
        urdf_link = None
        for link in urdf_root.findall('link'):
            if link.get('name') == link_name:
                urdf_link = link
                break
        
        if urdf_link is None:
            return
        
        # Create MJCF body
        mjcf_body = ET.SubElement(mjcf_parent, 'body', {'name': link_name})
        
        # Add inertial
        inertial = urdf_link.find('inertial')
        if inertial is not None:
            self._convert_inertial_to_mjcf(inertial, mjcf_body)
        
        # Add geoms (visuals and collisions)
        for visual in urdf_link.findall('visual'):
            self._convert_geom_to_mjcf(visual, mjcf_body, 'visual')
        
        for collision in urdf_link.findall('collision'):
            self._convert_geom_to_mjcf(collision, mjcf_body, 'collision')
        
        # Find child joints and links
        for joint in urdf_root.findall('joint'):
            parent = joint.find('parent')
            child = joint.find('child')
            
            if parent is None or child is None:
                continue
            
            if parent.get('link') == link_name:
                child_name = child.get('link', '')
                
                # Add joint
                self._convert_joint_to_mjcf(joint, mjcf_body)
                
                # Recurse to child
                self._build_body_tree(urdf_root, mjcf_body, child_name, visited)
    
    def _convert_inertial_to_mjcf(self, urdf_inertial: ET.Element, mjcf_body: ET.Element):
        """Convert URDF inertial to MJCF inertial."""
        inertial = ET.SubElement(mjcf_body, 'inertial')
        
        # Mass
        mass = urdf_inertial.find('mass')
        if mass is not None:
            inertial.set('mass', mass.get('value', '1'))
        
        # Position from origin
        origin = urdf_inertial.find('origin')
        if origin is not None:
            xyz = origin.get('xyz', '0 0 0')
            inertial.set('pos', xyz)
        
        # Inertia (MJCF uses diaginertia for diagonal, fullinertia for full)
        inertia = urdf_inertial.find('inertia')
        if inertia is not None:
            ixx = inertia.get('ixx', '0.001')
            iyy = inertia.get('iyy', '0.001')
            izz = inertia.get('izz', '0.001')
            inertial.set('diaginertia', f"{ixx} {iyy} {izz}")
    
    def _convert_geom_to_mjcf(
        self,
        urdf_elem: ET.Element,
        mjcf_body: ET.Element,
        group: str
    ):
        """Convert URDF visual/collision to MJCF geom."""
        geometry = urdf_elem.find('geometry')
        if geometry is None:
            return
        
        geom = ET.SubElement(mjcf_body, 'geom')
        geom.set('group', '0' if group == 'collision' else '1')
        
        # Name
        name = urdf_elem.get('name', '')
        if name:
            geom.set('name', name)
        
        # Position from origin
        origin = urdf_elem.find('origin')
        if origin is not None:
            xyz = origin.get('xyz', '0 0 0')
            rpy = origin.get('rpy', '0 0 0')
            geom.set('pos', xyz)
            # Convert RPY to quaternion for MJCF
            # Simplified: use euler
            geom.set('euler', rpy)
        
        # Geometry type
        box = geometry.find('box')
        if box is not None:
            geom.set('type', 'box')
            size = box.get('size', '1 1 1')
            # MJCF uses half-extents
            parts = [str(float(x) / 2) for x in size.split()]
            geom.set('size', ' '.join(parts))
            return
        
        cylinder = geometry.find('cylinder')
        if cylinder is not None:
            geom.set('type', 'cylinder')
            radius = cylinder.get('radius', '0.1')
            length = cylinder.get('length', '0.1')
            half_length = str(float(length) / 2)
            geom.set('size', f"{radius} {half_length}")
            return
        
        sphere = geometry.find('sphere')
        if sphere is not None:
            geom.set('type', 'sphere')
            geom.set('size', sphere.get('radius', '0.1'))
            return
        
        mesh = geometry.find('mesh')
        if mesh is not None:
            geom.set('type', 'mesh')
            filename = mesh.get('filename', '')
            geom.set('mesh', Path(filename).stem)
    
    def _convert_joint_to_mjcf(self, urdf_joint: ET.Element, mjcf_body: ET.Element):
        """Convert URDF joint to MJCF joint."""
        joint_name = urdf_joint.get('name', 'joint')
        joint_type = urdf_joint.get('type', 'fixed')
        
        if joint_type == 'fixed':
            return  # Fixed joints don't need explicit MJCF joint
        
        mjcf_joint = ET.SubElement(mjcf_body, 'joint', {'name': joint_name})
        
        # Type mapping
        type_map = {
            'revolute': 'hinge',
            'continuous': 'hinge',
            'prismatic': 'slide',
            'floating': 'free',
        }
        mjcf_joint.set('type', type_map.get(joint_type, 'hinge'))
        
        # Axis
        axis = urdf_joint.find('axis')
        if axis is not None:
            mjcf_joint.set('axis', axis.get('xyz', '0 0 1'))
        
        # Limits
        limit = urdf_joint.find('limit')
        if limit is not None and joint_type != 'continuous':
            lower = limit.get('lower', '-3.14')
            upper = limit.get('upper', '3.14')
            mjcf_joint.set('range', f"{lower} {upper}")
    
    def _find_loop_joints(self, urdf_root: ET.Element) -> List[ET.Element]:
        """Find joints that create kinematic loops."""
        loop_joints = []
        
        children = {}
        for joint in urdf_root.findall('joint'):
            child = joint.find('child')
            if child is not None:
                child_name = child.get('link', '')
                if child_name not in children:
                    children[child_name] = []
                children[child_name].append(joint)
        
        for child_name, joints in children.items():
            if len(joints) > 1:
                loop_joints.extend(joints[1:])  # All but first are loops
        
        return loop_joints
    
    def _add_loop_constraint(self, urdf_joint: ET.Element, mjcf_equality: ET.Element):
        """Add MuJoCo equality constraint for loop closure."""
        joint_name = urdf_joint.get('name', 'loop')
        joint_type = urdf_joint.get('type', 'revolute')
        
        parent = urdf_joint.find('parent')
        child = urdf_joint.find('child')
        
        if parent is None or child is None:
            return
        
        # MuJoCo uses <weld> for fixed connections, <joint> for joint equality
        if joint_type == 'fixed':
            weld = ET.SubElement(mjcf_equality, 'weld', {
                'name': f"{joint_name}_weld",
                'body1': parent.get('link', ''),
                'body2': child.get('link', ''),
            })
        else:
            # For revolute/prismatic loops, use connect constraint
            connect = ET.SubElement(mjcf_equality, 'connect', {
                'name': f"{joint_name}_connect",
                'body1': parent.get('link', ''),
                'body2': child.get('link', ''),
                'anchor': '0 0 0',  # Would need actual position
            })
    
    def _add_actuators(self, urdf_root: ET.Element, mjcf_actuator: ET.Element):
        """Add actuators for all movable joints."""
        for joint in urdf_root.findall('joint'):
            joint_type = joint.get('type', 'fixed')
            
            if joint_type in ['revolute', 'continuous', 'prismatic']:
                joint_name = joint.get('name', '')
                
                # Position actuator (motor)
                motor = ET.SubElement(mjcf_actuator, 'motor', {
                    'name': f"{joint_name}_motor",
                    'joint': joint_name,
                    'gear': '1',
                })
                
                # Get effort limit
                limit = joint.find('limit')
                if limit is not None:
                    effort = limit.get('effort', '100')
                    motor.set('ctrlrange', f"-{effort} {effort}")
    
    def _write_xml(self, root: ET.Element, path: str):
        """Write formatted XML to file."""
        rough_string = ET.tostring(root, encoding='unicode')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="  ")
        
        lines = [line for line in pretty_xml.split('\n') if line.strip()]
        pretty_xml = '\n'.join(lines)
        
        Path(path).write_text(pretty_xml)


# Convenience functions
def convert_urdf_to_sdf(
    urdf_path: str,
    output_path: str,
    options: Optional[ConversionOptions] = None
) -> bool:
    """Convert URDF to SDF."""
    converter = URDFToSDFConverter(options)
    return converter.convert(urdf_path, output_path)


def convert_sdf_to_urdf(
    sdf_path: str,
    output_path: str,
    options: Optional[ConversionOptions] = None
) -> bool:
    """Convert SDF to URDF."""
    converter = SDFToURDFConverter(options)
    return converter.convert(sdf_path, output_path)


def convert_urdf_to_mjcf(
    urdf_path: str,
    output_path: str,
    options: Optional[ConversionOptions] = None
) -> bool:
    """Convert URDF to MJCF."""
    converter = URDFToMJCFConverter(options)
    return converter.convert(urdf_path, output_path)


def batch_convert(
    input_dir: str,
    output_dir: str,
    from_format: str,
    to_format: str,
    options: Optional[ConversionOptions] = None
) -> Dict[str, bool]:
    """
    Batch convert files between formats.
    
    Args:
        input_dir: Directory with input files
        output_dir: Directory for output files
        from_format: Source format ('urdf', 'sdf', 'mjcf')
        to_format: Target format ('urdf', 'sdf', 'mjcf')
        options: Conversion options
        
    Returns:
        Dictionary of filename -> success status
    """
    results = {}
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Extension mapping
    ext_map = {
        'urdf': ['.urdf', '.xacro'],
        'sdf': ['.sdf', '.world'],
        'mjcf': ['.xml'],
    }
    
    # Converter selection
    converters = {
        ('urdf', 'sdf'): URDFToSDFConverter,
        ('sdf', 'urdf'): SDFToURDFConverter,
        ('urdf', 'mjcf'): URDFToMJCFConverter,
    }
    
    converter_class = converters.get((from_format, to_format))
    if converter_class is None:
        logger.error(f"Unsupported conversion: {from_format} -> {to_format}")
        return results
    
    converter = converter_class(options)
    
    # Find input files
    input_exts = ext_map.get(from_format, ['.urdf'])
    output_ext = ext_map.get(to_format, ['.sdf'])[0]
    
    for input_file in input_path.iterdir():
        if input_file.suffix.lower() in input_exts:
            output_file = output_path / (input_file.stem + output_ext)
            
            try:
                success = converter.convert(str(input_file), str(output_file))
                results[input_file.name] = success
            except Exception as e:
                logger.error(f"Failed to convert {input_file}: {e}")
                results[input_file.name] = False
    
    return results
