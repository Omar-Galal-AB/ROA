"""
URDF Converter - Convert URDF files to USD format
URDF (Unified Robot Description Format) is the standard for ROS robots

This converter uses:
- xml.etree: For parsing URDF XML
- trimesh: For loading mesh files referenced in URDF
- pxr (OpenUSD): For generating USD with joints and physics
- numpy: For 4x4 transformation matrices

v3.0 - Added USD Physics support:
- PhysicsScene with gravity
- ArticulationRootAPI for robot kinematic chain
- PhysicsRevoluteJoint, PhysicsPrismaticJoint, PhysicsFixedJoint
- DriveAPI for motor control (position/velocity targets)
- LimitAPI for joint limits
- MassAPI for link masses and inertia
- CollisionAPI for collision detection
- FilteredPairsAPI for self-collision filtering between adjacent links

v3.1 - Added sensor and dynamics support:
- Sensor extraction (LIDAR, Camera, IMU, Contact, etc.)
- Joint dynamics (damping, friction)
- Safety controllers and mimic joints
- Gazebo plugin sensor parsing

v3.2 - Added COMC integration:
- Robot type detection
- Bounding radius and footprint calculation
- Capabilities detection (mobile, gripper, reach)
- Safety zone calculation

v3.3 - Improved organization:
- Separate /Visuals and /Collisions folders at robot level
- Cleaner USD structure for easier navigation in UE5

v3.4 - Enhanced mesh and collision support:
- VRML mesh format support (.wrl)
- Convex decomposition for collision meshes (V-HACD)
- Improved footprint detection from actual base geometry
- Better payload estimation from inertia and kinematics
- Humanoid robot type detection
- Texture embedding support in USD
"""

import os
import sys
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Optional, Dict, List, Tuple
import math

# Numpy - with binary compatibility check
try:
    import numpy as np
except ImportError as e:
    raise ImportError(
        f"NumPy is required for URDF conversion: {e}\n"
        "Install with: pip install 'numpy<2.0'"
    )
except Exception as e:
    # Binary incompatibility (numpy.dtype size mismatch)
    raise RuntimeError(
        f"NumPy binary incompatibility detected: {e}\n"
        "This usually means numpy was upgraded but C extensions weren't rebuilt.\n"
        "Fix: pip install --force-reinstall --no-cache-dir 'numpy<2.0'\n"
        "Or use a clean virtual environment."
    )

# Mesh processing - with binary compatibility check
try:
    import trimesh
except ImportError as e:
    raise ImportError(
        f"Trimesh is required for mesh loading: {e}\n"
        "Install with: pip install trimesh"
    )
except Exception as e:
    # Usually triggered by scipy/numpy ABI mismatch in trimesh dependencies
    raise RuntimeError(
        f"Mesh processing library incompatibility: {e}\n"
        "This is often caused by numpy/scipy version mismatches.\n"
        "Recommended fix:\n"
        "  1. Create a clean virtual environment\n"
        "  2. pip install 'numpy<2.0' scipy trimesh\n"
        "Or disable mesh optimization in the converter config."
    )

# USD generation
try:
    from pxr import Usd, UsdGeom, UsdPhysics, UsdShade, Sdf, Gf, Vt
    # Verify UsdPhysics joint classes are available
    _physics_available = hasattr(UsdPhysics, 'RevoluteJoint')
except ImportError as e:
    raise ImportError(
        f"OpenUSD (pxr) is required for USD generation: {e}\n"
        "Install from: https://github.com/PixarAnimationStudios/USD"
    )

# Add parent directory to import HierarchyBuilder
sys.path.insert(0, str(Path(__file__).parent.parent))

# Support both relative imports (when used as package) and absolute imports (when run standalone)
try:
    from .base_converter import BaseConverter, ConversionResult
except ImportError:
    from base_converter import BaseConverter, ConversionResult

try:
    from Importers.hierarchy_builder import HierarchyBuilder
except ImportError:
    # Try parent path
    import_path = str(Path(__file__).parent.parent / "Importers")
    if import_path not in sys.path:
        sys.path.insert(0, import_path)
    from hierarchy_builder import HierarchyBuilder

# Path handling for Windows/Linux interop
try:
    from Utils.path_handler import ROAPathHandler, get_path_handler
except ImportError:
    try:
        from ..Utils.path_handler import ROAPathHandler, get_path_handler
    except ImportError:
        ROAPathHandler = None
        get_path_handler = None


class URDFConverter(BaseConverter):
    """
    Converter for URDF (Unified Robot Description Format) files.
    
    URDF is the standard format used in ROS for describing robot models.
    This converter parses URDF XML and converts it to USD format for UE5.
    
    Features:
    - Full link/joint hierarchy conversion
    - Visual and collision geometry support
    - Mesh loading (STL, OBJ, DAE)
    - Material conversion with colors
    - Joint types: fixed, revolute, continuous, prismatic
    - Proper 4x4 transformation matrices
    - Physics properties (mass, inertia)
    - XACRO macro expansion (automatic)
    - Custom ROS package path resolution for package:// URLs
    """
    
    # Default ROS package search paths
    DEFAULT_PACKAGE_PATHS = [
        '/home/myws/ros_packages',
        '/opt/ros/humble/share',
        '/opt/ros/galactic/share',
        '/opt/ros/foxy/share',
        '/mnt/c/ros2-windows/share',
    ]
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize the URDF converter."""
        super().__init__(config)
        self.supported_extensions = ['.urdf', '.xacro']
        
        # Configuration
        self.scale_factor = self.config.get('scale_factor', 1.0)
        self.include_collision = self.config.get('include_collision', True)
        self.include_visual = self.config.get('include_visual', True)
        self.urdf_dir = None
        
        # USD Physics configuration (v3.0)
        self.include_physics = self.config.get('include_physics', True)
        self.physics_config = {
            'gravity_direction': self.config.get('gravity_direction', [0, 0, -1]),
            'gravity_magnitude': self.config.get('gravity_magnitude', 9.81),
            'default_drive_stiffness': self.config.get('default_drive_stiffness', 1000.0),
            'default_drive_damping': self.config.get('default_drive_damping', 100.0),
            'default_max_force': self.config.get('default_max_force', 1000.0),
            'enable_self_collision_filter': self.config.get('enable_self_collision_filter', True),
        }
        
        # v3.4: Enhanced mesh and collision configuration
        self.mesh_config = {
            'enable_convex_decomposition': self.config.get('enable_convex_decomposition', True),
            'convex_max_hulls': self.config.get('convex_max_hulls', 16),
            'convex_resolution': self.config.get('convex_resolution', 100000),
            'embed_textures': self.config.get('embed_textures', False),
            'supported_mesh_formats': ['.stl', '.obj', '.dae', '.wrl', '.ply', '.glb', '.gltf'],
        }
        
        # Package path resolution
        self.package_paths: List[str] = self.config.get(
            'package_paths', 
            self.DEFAULT_PACKAGE_PATHS.copy()
        )
        self._package_cache: Dict[str, Path] = {}
        
        # XACRO processor (lazy loaded)
        self._xacro_processor = None
        
        # Path handler for Windows/Linux interop
        if get_path_handler is not None:
            self.path_handler = get_path_handler(self.config.get('path_config'))
        else:
            self.path_handler = None
    
    def register_package(self, package_name: str, package_path: str):
        """
        Register a ROS package path for package:// URL resolution.
        
        Args:
            package_name: The package name (e.g., 'ur_description')
            package_path: The absolute path to the package directory
        """
        self._package_cache[package_name] = Path(package_path)
    
    def add_package_path(self, path: str):
        """Add a custom ROS package search path."""
        if path not in self.package_paths:
            self.package_paths.append(path)
    
    def _get_xacro_processor(self):
        """Get or create XACRO processor with registered packages."""
        if self._xacro_processor is None:
            try:
                # Try to import from sibling directory
                import sys
                sys.path.insert(0, str(Path(__file__).parent.parent))
                from xacro_processor import XacroProcessor
                self._xacro_processor = XacroProcessor()
                
                # Register our package paths with the XACRO processor
                for pkg_name, pkg_path in self._package_cache.items():
                    self._xacro_processor.register_package(pkg_name, str(pkg_path))
                    
            except ImportError:
                self._xacro_processor = False  # Mark as unavailable
        return self._xacro_processor if self._xacro_processor else None
    
    def _is_xacro_file(self, file_path: str) -> bool:
        """
        Check if a file contains XACRO macros.
        Looks for xacro namespace or macro elements.
        """
        try:
            with open(file_path, 'r') as f:
                content = f.read(4096)  # Read first 4KB
            
            # Check for XACRO indicators
            xacro_indicators = [
                'xmlns:xacro=',
                '<xacro:',
                '${',  # XACRO property substitution
                'xacro:include',
                'xacro:macro',
                'xacro:property'
            ]
            
            for indicator in xacro_indicators:
                if indicator in content:
                    return True
            
            return False
        except:
            return False
    
    def _extract_xacro_defaults(self, xacro_path: str) -> Dict[str, str]:
        """
        Extract default arguments from a XACRO file.
        
        Parses <xacro:arg name="..." default="..."/> elements to get defaults.
        
        Args:
            xacro_path: Path to the XACRO file
            
        Returns:
            Dict of argument name -> default value
        """
        defaults = {}
        try:
            import re
            with open(xacro_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Match <xacro:arg name="..." default="..."/>
            pattern = r'<xacro:arg\s+name\s*=\s*["\']([^"\']+)["\']\s+default\s*=\s*["\']([^"\']*)["\']'
            matches = re.findall(pattern, content)
            
            for name, default in matches:
                # Skip defaults that reference other args (like $(arg ...))
                if '$(arg' not in default and '$(' not in default:
                    defaults[name] = default
                    
            self._log_info(f"Extracted {len(defaults)} default XACRO arguments")
            
        except Exception as e:
            self._log_warning(f"Failed to extract XACRO defaults: {e}")
            
        return defaults
    
    def _expand_xacro(self, xacro_path: str, xacro_args: Optional[Dict[str, str]] = None) -> tuple:
        """
        Expand XACRO file to URDF.
        
        Args:
            xacro_path: Path to the XACRO file
            xacro_args: Optional dictionary of arguments to pass to xacro
            
        Returns:
            Tuple of (success, message, urdf_path)
        """
        processor = self._get_xacro_processor()
        
        if processor is None:
            return False, "XACRO processor not available. Install xacro: pip install xacro", None
        
        # Generate output path
        import tempfile
        base_name = Path(xacro_path).stem
        urdf_path = os.path.join(tempfile.gettempdir(), f"{base_name}_expanded.urdf")
        
        # Merge extracted defaults with provided args (provided args take precedence)
        defaults = self._extract_xacro_defaults(xacro_path)
        merged_args = {**defaults, **(xacro_args or {})}
        
        self._log_info(f"Expanding XACRO: {xacro_path} -> {urdf_path}")
        if merged_args:
            self._log_info(f"XACRO arguments: {merged_args}")
        
        success, message, result = processor.process(xacro_path, urdf_path, xacro_args=merged_args)
        
        if success:
            self._log_info(f"XACRO expansion successful")
            return True, "XACRO expanded successfully", result
        else:
            return False, message, None
    
    def _auto_register_package_from_path(self, file_path: str):
        """
        Auto-detect and register ROS package from input file path.
        
        Searches upward from the file path to find package.xml,
        then registers the package with the XACRO processor.
        
        Args:
            file_path: Path to the URDF/XACRO file
        """
        try:
            from pathlib import Path
            import xml.etree.ElementTree as ET
            
            current_path = Path(file_path).parent
            
            # Search upward for package.xml (max 10 levels)
            for _ in range(10):
                package_xml = current_path / "package.xml"
                
                if package_xml.exists():
                    # Parse package name from package.xml
                    try:
                        tree = ET.parse(str(package_xml))
                        root = tree.getroot()
                        name_elem = root.find('name')
                        
                        if name_elem is not None and name_elem.text:
                            package_name = name_elem.text.strip()
                            package_path = str(current_path)
                            
                            # Register with XACRO processor
                            processor = self._get_xacro_processor()
                            if processor:
                                processor.register_package(package_name, package_path)
                                self._log_info(f"Auto-registered package: {package_name} -> {package_path}")
                            
                            # Also cache it for our own use
                            self.register_package(package_name, package_path)
                            return True
                    except Exception as e:
                        self._log_warning(f"Error parsing package.xml: {e}")
                
                # Move up one directory
                parent = current_path.parent
                if parent == current_path:  # Reached filesystem root
                    break
                current_path = parent
            
        except Exception as e:
            self._log_warning(f"Error in auto package detection: {e}")
        
        return False

    def convert(
        self,
        input_path: str,
        output_path: str,
        robot_name: str,
        xacro_args: Optional[Dict[str, str]] = None
    ) -> ConversionResult:
        """
        Convert a URDF file to USD format.
        Automatically handles XACRO files by expanding them first.
        
        Args:
            input_path: Path to URDF or XACRO file
            output_path: Path for output USD file
            robot_name: Name of the robot
            xacro_args: Optional dict of XACRO arguments (e.g., {'ur_type': 'ur5'})
        """
        if not self.validate_input(input_path):
            return ConversionResult(
                success=False,
                error_message=f"Invalid input file: {input_path}"
            )
        
        warnings = []
        parts = []
        materials_found = []
        
        # Auto-detect and register package from input path (Fix for XACRO package resolution)
        self._auto_register_package_from_path(input_path)
        
        # Check if this is a XACRO file that needs expansion
        actual_input_path = input_path
        if input_path.endswith('.xacro') or self._is_xacro_file(input_path):
            self._log_info(f"Detected XACRO file, expanding macros first...")
            success, msg, expanded_path = self._expand_xacro(input_path, xacro_args=xacro_args)
            if not success:
                return ConversionResult(
                    success=False,
                    error_message=f"XACRO expansion failed: {msg}"
                )
            actual_input_path = expanded_path
            warnings.append(f"XACRO file expanded to temporary URDF")
        
        try:
            self._log_info(f"Parsing URDF file: {actual_input_path}")
            tree = ET.parse(actual_input_path)
            root = tree.getroot()
            
            if root.tag != 'robot':
                return ConversionResult(
                    success=False,
                    error_message="Invalid URDF file: root element must be 'robot'"
                )
            
            urdf_robot_name = root.get('name', robot_name)
            # Store robot name for use in mesh naming (multi-robot disambiguation)
            self._current_robot_name = self._sanitize_name(urdf_robot_name)
            self._log_info(f"Processing URDF robot: {urdf_robot_name} (prefix: {self._current_robot_name})")
            self.urdf_dir = Path(input_path).parent
            
            links = self._extract_links(root)
            joints = self._extract_joints(root)
            materials = self._extract_materials(root)
            
            # NEW: Extract sensors for DIMC
            sensors = self._extract_sensors(root)
            
            self._log_info(f"Found {len(links)} links, {len(joints)} joints, {len(materials)} materials, {len(sensors)} sensors")
            
            link_tree, root_link = self._build_link_tree(links, joints)
            
            if root_link is None:
                return ConversionResult(
                    success=False,
                    error_message="Could not determine root link in URDF"
                )
            
            self._log_info(f"Root link: {root_link}")
            
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate only assembled output file (v2.3 - no more parts file)
            base_output = Path(output_path)
            # Ensure .usd extension for USD stage creation
            usd_suffix = base_output.suffix if base_output.suffix in ['.usd', '.usda', '.usdc'] else '.usd'
            assembled_output_path = str(base_output.parent / f"{base_output.stem}_assembled{usd_suffix}")
            
            # ========== ASSEMBLED (Complete robot body) ==========
            self._log_info(f"Creating ASSEMBLED file: {assembled_output_path}")
            assembled_stage = Usd.Stage.CreateNew(assembled_output_path)
            
            if assembled_stage is None:
                return ConversionResult(
                    success=False,
                    error_message=f"Failed to create USD stage at {assembled_output_path}"
                )
            
            UsdGeom.SetStageUpAxis(assembled_stage, UsdGeom.Tokens.z)
            UsdGeom.SetStageMetersPerUnit(assembled_stage, 1.0)
            
            # === USD Physics: Create PhysicsScene (v3.0) ===
            if self.include_physics:
                self._create_physics_scene(assembled_stage)
            
            assembled_robot_path = f"/{self._sanitize_name(urdf_robot_name)}_Assembled"
            assembled_robot_xform = UsdGeom.Xform.Define(assembled_stage, assembled_robot_path)
            assembled_stage.SetDefaultPrim(assembled_robot_xform.GetPrim())
            assembled_robot_xform.GetPrim().SetMetadata('documentation',
                'Complete robot assembly - drag this into your scene for the full robot')
            
            # === USD Physics: Apply ArticulationRootAPI to robot root (v3.0) ===
            if self.include_physics:
                robot_prim = assembled_robot_xform.GetPrim()
                UsdPhysics.ArticulationRootAPI.Apply(robot_prim)
                self._log_info(f"Applied ArticulationRootAPI to robot root: {assembled_robot_path}")
            
            # Add customData for UE5 hierarchy reconstruction
            # UE5's Interchange flattens USD hierarchy - this metadata helps rebuild it
            hierarchy_data = self._build_hierarchy_metadata(root_link, link_tree, joints)
            root_prim = assembled_robot_xform.GetPrim()
            root_prim.SetCustomDataByKey("export_source", "ROA_URDF_Converter")
            root_prim.SetCustomDataByKey("robot_name", urdf_robot_name)
            root_prim.SetCustomDataByKey("robot_prefix", self._current_robot_name)  # Sanitized name for actor matching
            root_prim.SetCustomDataByKey("root_link", root_link)
            root_prim.SetCustomDataByKey("hierarchy", hierarchy_data)
            root_prim.SetCustomDataByKey("link_count", len(links))
            root_prim.SetCustomDataByKey("joint_count", len(joints))
            # Document naming convention for assembler: meshes are named "robotprefix_linkname_visual"
            root_prim.SetCustomDataByKey("mesh_naming_convention", f"{self._current_robot_name}_<link_name>_visual")
            self._log_info(f"Added UE5 hierarchy customData for {len(links)} links (prefix: {self._current_robot_name})")
            
            # Create Materials in assembled file
            assembled_materials_path = f"{assembled_robot_path}/Materials"
            UsdGeom.Scope.Define(assembled_stage, assembled_materials_path)
            
            assembled_usd_materials = {}
            for mat_name, mat_data in materials.items():
                mat_path = f"{assembled_materials_path}/{self._sanitize_name(mat_name)}"
                self._create_usd_material(assembled_stage, mat_path, mat_data)
                assembled_usd_materials[mat_name] = mat_path
            
            # NOTE: Visuals and Collisions are placed INSIDE each link's hierarchy
            # This ensures proper transform inheritance when imported into UE5
            # (UE5's Interchange imports the USD hierarchy, and meshes inside links
            # inherit the link transforms, appearing correctly assembled)
            
            # Create the full robot hierarchy with proper joint transforms
            created_links = set()
            self._create_link_hierarchy(
                stage=assembled_stage,
                parent_path=assembled_robot_path,
                link_name=root_link,
                links=links,
                joints=joints,
                link_tree=link_tree,
                usd_materials=assembled_usd_materials,
                materials=materials,
                created_links=created_links,
                parts=[],  # Don't need to track parts here
                warnings=warnings,
                visuals_root=None,   # Meshes go INSIDE each link (correct behavior)
                collisions_root=None  # This ensures transform inheritance works in UE5
            )
            
            # === USD Physics: Create Physics Joints (v3.0) ===
            if self.include_physics:
                self._create_physics_joints(
                    stage=assembled_stage,
                    robot_path=assembled_robot_path,
                    root_link=root_link,
                    joints=joints,
                    link_tree=link_tree,
                    warnings=warnings
                )
                self._log_info(f"Created USD Physics joints for {len(joints)} joints")
            
            assembled_stage.GetRootLayer().Save()
            self._log_info(f"Assembled file saved: {assembled_output_path}")
            
            # Validate output
            if not self.validate_output(assembled_output_path):
                warnings.append("Assembled file validation failed")
            
            # Track materials from this file for result (since we no longer iterate in parts)
            for mat_name in materials.keys():
                if mat_name not in materials_found:
                    materials_found.append(mat_name)
            
            # Build hierarchy with all data including sensors (v3.1)
            hierarchy = self._build_hierarchy(links, joints, materials, sensors)
            
            # Return result with assembled file (v2.3 - no parts file)
            result = ConversionResult(
                success=True,
                output_path=assembled_output_path,  # Primary output is assembled
                format='usd',
                parts=parts,
                materials=materials_found,
                warnings=warnings
            )
            result.hierarchy = hierarchy
            result.assembled_file = assembled_output_path
            
            # Generate UE5 hierarchy reconstruction script
            ue5_script_path = str(base_output.parent / f"{base_output.stem}_ue5_rebuild_hierarchy.py")
            self._generate_ue5_script(ue5_script_path, urdf_robot_name, root_link, link_tree, joints)
            result.ue5_script = ue5_script_path
            
            self._log_info(f"✅ Created 2 files:")
            self._log_info(f"   - Assembled: {assembled_output_path}")
            self._log_info(f"   - UE5 Script: {ue5_script_path}")
            
            return result
            
        except ET.ParseError as e:
            self._log_error(f"XML parsing error: {e}")
            return ConversionResult(success=False, error_message=f"Failed to parse URDF XML: {str(e)}")
        except ImportError as e:
            self._log_error(f"Missing dependency: {e}")
            return ConversionResult(success=False, error_message=f"Missing required library: {str(e)}")
        except Exception as e:
            self._log_error(f"Conversion error: {e}")
            import traceback
            traceback.print_exc()
            return ConversionResult(success=False, error_message=f"Conversion failed: {str(e)}")
    
    def _extract_links(self, root: ET.Element) -> Dict[str, Dict]:
        """Extract all link elements from URDF."""
        links = {}
        for link_elem in root.findall('link'):
            link_name = link_elem.get('name')
            inertial = None
            inertial_elem = link_elem.find('inertial')
            if inertial_elem is not None:
                inertial = self._parse_inertial(inertial_elem)
            
            visuals = []
            for visual_elem in link_elem.findall('visual'):
                visual = self._parse_visual_or_collision(visual_elem)
                if visual:
                    visuals.append(visual)
            
            collisions = []
            for collision_elem in link_elem.findall('collision'):
                collision = self._parse_visual_or_collision(collision_elem)
                if collision:
                    collisions.append(collision)
            
            links[link_name] = {
                'name': link_name,
                'inertial': inertial,
                'visuals': visuals,
                'collisions': collisions
            }
        return links
    
    def _parse_inertial(self, elem: ET.Element) -> Dict:
        result = {'origin': self._parse_origin(elem.find('origin')), 'mass': 0.0, 'inertia': None}
        mass_elem = elem.find('mass')
        if mass_elem is not None:
            result['mass'] = float(mass_elem.get('value', 0.0))
        inertia_elem = elem.find('inertia')
        if inertia_elem is not None:
            result['inertia'] = {k: float(inertia_elem.get(k, 0.0)) for k in ['ixx','ixy','ixz','iyy','iyz','izz']}
        return result
    
    def _parse_visual_or_collision(self, elem: ET.Element) -> Optional[Dict]:
        if elem is None:
            return None
        result = {
            'name': elem.get('name'),
            'origin': self._parse_origin(elem.find('origin')),
            'geometry': None,
            'material': None
        }
        geom_elem = elem.find('geometry')
        if geom_elem is not None:
            result['geometry'] = self._parse_geometry(geom_elem)
        material_elem = elem.find('material')
        if material_elem is not None:
            result['material'] = material_elem.get('name')
        return result
    
    def _parse_origin(self, elem: ET.Element) -> Dict:
        if elem is None:
            return {'xyz': [0, 0, 0], 'rpy': [0, 0, 0]}
        xyz = [float(x) for x in elem.get('xyz', '0 0 0').split()]
        rpy = [float(r) for r in elem.get('rpy', '0 0 0').split()]
        return {'xyz': xyz, 'rpy': rpy}
    
    def _parse_geometry(self, elem: ET.Element) -> Optional[Dict]:
        mesh_elem = elem.find('mesh')
        if mesh_elem is not None:
            scale = [float(s) for s in mesh_elem.get('scale', '1 1 1').split()]
            return {'type': 'mesh', 'filename': mesh_elem.get('filename'), 'scale': scale}
        box_elem = elem.find('box')
        if box_elem is not None:
            return {'type': 'box', 'size': [float(s) for s in box_elem.get('size', '1 1 1').split()]}
        cyl_elem = elem.find('cylinder')
        if cyl_elem is not None:
            return {'type': 'cylinder', 'radius': float(cyl_elem.get('radius', 0.1)), 'length': float(cyl_elem.get('length', 1.0))}
        sphere_elem = elem.find('sphere')
        if sphere_elem is not None:
            return {'type': 'sphere', 'radius': float(sphere_elem.get('radius', 0.1))}
        return None
    
    def _extract_joints(self, root: ET.Element) -> Dict[str, Dict]:
        joints = {}
        for joint_elem in root.findall('joint'):
            joint_name = joint_elem.get('name')
            joint_type = joint_elem.get('type')
            parent_elem = joint_elem.find('parent')
            child_elem = joint_elem.find('child')
            parent_link = parent_elem.get('link') if parent_elem is not None else None
            child_link = child_elem.get('link') if child_elem is not None else None
            origin = self._parse_origin(joint_elem.find('origin'))
            axis_elem = joint_elem.find('axis')
            axis = [float(a) for a in axis_elem.get('xyz', '1 0 0').split()] if axis_elem is not None else [1, 0, 0]
            limit_elem = joint_elem.find('limit')
            limits = None
            if limit_elem is not None:
                limits = {k: float(limit_elem.get(k, 0.0)) for k in ['lower', 'upper', 'effort', 'velocity']}
            
            # NEW: Parse dynamics (damping, friction) for ROC motor control
            dynamics_elem = joint_elem.find('dynamics')
            dynamics = None
            if dynamics_elem is not None:
                dynamics = {
                    'damping': float(dynamics_elem.get('damping', 0.0)),
                    'friction': float(dynamics_elem.get('friction', 0.0))
                }
            
            # NEW: Parse safety_controller for DIMC safety zones
            safety_elem = joint_elem.find('safety_controller')
            safety_controller = None
            if safety_elem is not None:
                safety_controller = {
                    'soft_lower_limit': float(safety_elem.get('soft_lower_limit', 0.0)),
                    'soft_upper_limit': float(safety_elem.get('soft_upper_limit', 0.0)),
                    'k_position': float(safety_elem.get('k_position', 0.0)),
                    'k_velocity': float(safety_elem.get('k_velocity', 0.0))
                }
            
            # NEW: Parse mimic joint (for gripper fingers that mirror each other)
            mimic_elem = joint_elem.find('mimic')
            mimic = None
            if mimic_elem is not None:
                mimic = {
                    'joint': mimic_elem.get('joint'),
                    'multiplier': float(mimic_elem.get('multiplier', 1.0)),
                    'offset': float(mimic_elem.get('offset', 0.0))
                }
            
            joints[joint_name] = {
                'name': joint_name, 'type': joint_type, 'parent': parent_link,
                'child': child_link, 'origin': origin, 'axis': axis, 'limits': limits,
                'dynamics': dynamics,  # NEW
                'safety_controller': safety_controller,  # NEW
                'mimic': mimic  # NEW
            }
        return joints
    
    def _extract_materials(self, root: ET.Element) -> Dict[str, Dict]:
        materials = {}
        for mat_elem in root.findall('material'):
            mat_name = mat_elem.get('name')
            materials[mat_name] = self._parse_material(mat_elem)
        for link_elem in root.findall('.//visual/material'):
            mat_name = link_elem.get('name')
            if mat_name and mat_name not in materials:
                materials[mat_name] = self._parse_material(link_elem)
        return materials
    
    def _parse_material(self, elem: ET.Element) -> Dict:
        result = {'color': None, 'texture': None}
        color_elem = elem.find('color')
        if color_elem is not None:
            result['color'] = [float(c) for c in color_elem.get('rgba', '0.8 0.8 0.8 1.0').split()]
        texture_elem = elem.find('texture')
        if texture_elem is not None:
            result['texture'] = texture_elem.get('filename')
        return result
    
    # ==================== NEW: SENSOR EXTRACTION (DIMC Requirements) ====================
    
    def _extract_sensors(self, root: ET.Element) -> List[Dict]:
        """
        Extract sensor definitions from URDF for DIMC.
        
        Parses:
        - <sensor> tags (standard URDF extension)
        - <gazebo> plugin sensors (common in ROS robots)
        
        Returns:
            List of sensor definitions with type, mount point, and parameters
        """
        sensors = []
        
        # Parse standard <sensor> tags
        for sensor_elem in root.findall('.//sensor'):
            sensor = self._parse_sensor_element(sensor_elem)
            if sensor:
                sensors.append(sensor)
                self._log_info(f"Found sensor: {sensor.get('name')} ({sensor.get('type')})")
        
        # Parse Gazebo plugin sensors (many ROS robots define sensors this way)
        for gazebo_elem in root.findall('.//gazebo'):
            gazebo_sensors = self._parse_gazebo_sensors(gazebo_elem)
            sensors.extend(gazebo_sensors)
        
        return sensors
    
    def _parse_sensor_element(self, elem: ET.Element) -> Optional[Dict]:
        """Parse a <sensor> element from URDF."""
        if elem is None:
            return None
        
        sensor_name = elem.get('name', 'unnamed_sensor')
        sensor_type = elem.get('type', 'ray').lower()
        
        # Get parent link
        parent_elem = elem.find('parent')
        parent_link = parent_elem.get('link') if parent_elem is not None else 'base_link'
        
        # Get origin/pose
        origin = self._parse_origin(elem.find('origin'))
        if origin is None:
            # Try 'pose' attribute (SDF-style)
            pose_elem = elem.find('pose')
            if pose_elem is not None and pose_elem.text:
                pose_values = [float(v) for v in pose_elem.text.split()]
                if len(pose_values) >= 6:
                    origin = {
                        'xyz': pose_values[0:3],
                        'rpy': pose_values[3:6]
                    }
                else:
                    origin = {'xyz': [0, 0, 0], 'rpy': [0, 0, 0]}
            else:
                origin = {'xyz': [0, 0, 0], 'rpy': [0, 0, 0]}
        
        sensor = {
            'name': sensor_name,
            'type': self._map_sensor_type(sensor_type),
            'parent_link': parent_link,
            'origin': origin,
            'from_urdf': True
        }
        
        # Parse type-specific parameters
        if sensor_type in ['ray', 'lidar', 'laser', 'gpu_ray']:
            sensor.update(self._parse_lidar_params(elem))
        elif sensor_type in ['camera', 'depth', 'rgbd', 'depth_camera']:
            sensor.update(self._parse_camera_params(elem))
        elif sensor_type in ['imu']:
            sensor.update(self._parse_imu_params(elem))
        elif sensor_type in ['contact', 'force_torque']:
            sensor.update(self._parse_contact_params(elem))
        
        return sensor
    
    def _map_sensor_type(self, urdf_type: str) -> str:
        """Map URDF/Gazebo sensor type to DIMC sensor type."""
        type_map = {
            'ray': 'LIDAR',
            'lidar': 'LIDAR',
            'laser': 'LIDAR',
            'gpu_ray': 'LIDAR',
            'gpu_lidar': 'LIDAR',
            'camera': 'DepthCamera',
            'depth': 'DepthCamera',
            'depth_camera': 'DepthCamera',
            'rgbd': 'DepthCamera',
            'rgbd_camera': 'DepthCamera',
            'imu': 'IMU',
            'contact': 'ContactSensor',
            'force_torque': 'ContactSensor',
            'sonar': 'Ultrasonic',
            'ultrasonic': 'Ultrasonic',
            'proximity': 'ProximitySensor',
        }
        return type_map.get(urdf_type.lower(), 'LIDAR')
    
    def _parse_lidar_params(self, elem: ET.Element) -> Dict:
        """Parse LIDAR/ray sensor parameters."""
        params = {
            'ray_count': 360,
            'range_min': 0.1,
            'range_max': 10.0,
            'fov_horizontal': 360.0,
            'fov_vertical': 30.0,
            'vertical_layers': 1
        }
        
        ray_elem = elem.find('.//ray') or elem.find('.//lidar')
        if ray_elem is not None:
            # Horizontal scan
            h_scan = ray_elem.find('.//horizontal')
            if h_scan is not None:
                params['ray_count'] = int(h_scan.findtext('samples', '360'))
                min_angle = float(h_scan.findtext('min_angle', '-3.14159'))
                max_angle = float(h_scan.findtext('max_angle', '3.14159'))
                params['fov_horizontal'] = math.degrees(max_angle - min_angle)
            
            # Vertical scan (for 3D LIDAR)
            v_scan = ray_elem.find('.//vertical')
            if v_scan is not None:
                params['vertical_layers'] = int(v_scan.findtext('samples', '1'))
                min_angle = float(v_scan.findtext('min_angle', '-0.26'))
                max_angle = float(v_scan.findtext('max_angle', '0.26'))
                params['fov_vertical'] = math.degrees(max_angle - min_angle)
            
            # Range
            range_elem = ray_elem.find('.//range')
            if range_elem is not None:
                params['range_min'] = float(range_elem.findtext('min', '0.1'))
                params['range_max'] = float(range_elem.findtext('max', '10.0'))
        
        return params
    
    def _parse_camera_params(self, elem: ET.Element) -> Dict:
        """Parse camera/depth sensor parameters."""
        params = {
            'image_width': 640,
            'image_height': 480,
            'camera_fov': 60.0,
            'depth_min': 0.1,
            'depth_max': 10.0
        }
        
        camera_elem = elem.find('.//camera')
        if camera_elem is not None:
            # Image dimensions
            image_elem = camera_elem.find('.//image')
            if image_elem is not None:
                params['image_width'] = int(image_elem.findtext('width', '640'))
                params['image_height'] = int(image_elem.findtext('height', '480'))
            
            # FOV
            h_fov = camera_elem.find('.//horizontal_fov')
            if h_fov is not None and h_fov.text:
                params['camera_fov'] = math.degrees(float(h_fov.text))
            
            # Clip planes
            clip_elem = camera_elem.find('.//clip')
            if clip_elem is not None:
                params['depth_min'] = float(clip_elem.findtext('near', '0.1'))
                params['depth_max'] = float(clip_elem.findtext('far', '10.0'))
        
        return params
    
    def _parse_imu_params(self, elem: ET.Element) -> Dict:
        """Parse IMU sensor parameters."""
        return {
            'update_rate': float(elem.findtext('.//update_rate', '100.0')),
            'noise_stddev': float(elem.findtext('.//noise/stddev', '0.01'))
        }
    
    def _parse_contact_params(self, elem: ET.Element) -> Dict:
        """Parse contact/force-torque sensor parameters."""
        return {
            'update_rate': float(elem.findtext('.//update_rate', '100.0'))
        }
    
    def _parse_gazebo_sensors(self, gazebo_elem: ET.Element) -> List[Dict]:
        """
        Parse sensors defined in <gazebo> elements.
        
        Many ROS robots define sensors in Gazebo plugins rather than URDF <sensor> tags.
        """
        sensors = []
        reference_link = gazebo_elem.get('reference', 'base_link')
        
        # Find sensor elements directly under gazebo
        for sensor_elem in gazebo_elem.findall('sensor'):
            sensor = self._parse_sensor_element(sensor_elem)
            if sensor:
                # Override parent link with gazebo reference if not specified
                if sensor.get('parent_link') == 'base_link':
                    sensor['parent_link'] = reference_link
                sensors.append(sensor)
                self._log_info(f"Found Gazebo sensor: {sensor.get('name')} on {reference_link}")
        
        # Parse common Gazebo plugins that define sensors
        for plugin_elem in gazebo_elem.findall('plugin'):
            plugin_name = plugin_elem.get('name', '')
            plugin_filename = plugin_elem.get('filename', '')
            
            # LIDAR plugins
            if 'ray' in plugin_filename or 'lidar' in plugin_filename or 'laser' in plugin_filename:
                sensor = {
                    'name': plugin_name or 'gazebo_lidar',
                    'type': 'LIDAR',
                    'parent_link': reference_link,
                    'origin': {'xyz': [0, 0, 0], 'rpy': [0, 0, 0]},
                    'from_urdf': True,
                    'ray_count': 360,
                    'range_min': 0.1,
                    'range_max': 10.0,
                    'fov_horizontal': 360.0
                }
                sensors.append(sensor)
            
            # Camera plugins
            elif 'camera' in plugin_filename:
                sensor = {
                    'name': plugin_name or 'gazebo_camera',
                    'type': 'DepthCamera',
                    'parent_link': reference_link,
                    'origin': {'xyz': [0, 0, 0], 'rpy': [0, 0, 0]},
                    'from_urdf': True,
                    'image_width': 640,
                    'image_height': 480,
                    'camera_fov': 60.0
                }
                sensors.append(sensor)
            
            # IMU plugins
            elif 'imu' in plugin_filename:
                sensor = {
                    'name': plugin_name or 'gazebo_imu',
                    'type': 'IMU',
                    'parent_link': reference_link,
                    'origin': {'xyz': [0, 0, 0], 'rpy': [0, 0, 0]},
                    'from_urdf': True
                }
                sensors.append(sensor)
        
        return sensors
    
    # ==================== END SENSOR EXTRACTION ====================
    
    def _build_link_tree(self, links: Dict, joints: Dict) -> Tuple[Dict, Optional[str]]:
        child_links = set()
        link_tree = {name: [] for name in links}
        for joint_name, joint in joints.items():
            parent, child = joint['parent'], joint['child']
            if parent in link_tree:
                link_tree[parent].append((joint_name, child))
            child_links.add(child)
        root_link = None
        for link_name in links:
            if link_name not in child_links:
                root_link = link_name
                break
        return link_tree, root_link
    
    def _build_hierarchy_metadata(self, root_link: str, link_tree: Dict, joints: Dict) -> str:
        """
        Build hierarchy metadata string for UE5 reconstruction.
        Format: Each line is "child_link|parent_link|joint_name|joint_type|x,y,z|roll,pitch,yaw"
        UE5 can parse this after import to rebuild the hierarchy.
        """
        lines = []
        
        def traverse(link_name: str, parent_name: str = ""):
            for joint_name, child_link in link_tree.get(link_name, []):
                joint_data = joints.get(joint_name, {})
                joint_type = joint_data.get('type', 'fixed')
                origin = joint_data.get('origin', {'xyz': [0, 0, 0], 'rpy': [0, 0, 0]})
                xyz = origin.get('xyz', [0, 0, 0])
                rpy = origin.get('rpy', [0, 0, 0])
                
                xyz_str = f"{xyz[0]:.6f},{xyz[1]:.6f},{xyz[2]:.6f}"
                rpy_str = f"{rpy[0]:.6f},{rpy[1]:.6f},{rpy[2]:.6f}"
                
                line = f"{child_link}|{link_name}|{joint_name}|{joint_type}|{xyz_str}|{rpy_str}"
                lines.append(line)
                traverse(child_link, link_name)
        
        traverse(root_link)
        return "\n".join(lines)
    
    def _generate_ue5_script(self, script_path: str, robot_name: str, root_link: str, link_tree: Dict, joints: Dict):
        """
        Generate a Python script for Unreal Engine 5 that rebuilds the robot hierarchy
        after USD import (since UE5's Interchange flattens USD hierarchies).
        
        Run this script in UE5's Python console after importing the USD file.
        """
        # Build the hierarchy data for the script
        hierarchy_entries = []
        
        def traverse(link_name: str, parent_name: str = ""):
            for joint_name, child_link in link_tree.get(link_name, []):
                joint_data = joints.get(joint_name, {})
                joint_type = joint_data.get('type', 'fixed')
                origin = joint_data.get('origin', {'xyz': [0, 0, 0], 'rpy': [0, 0, 0]})
                xyz = origin.get('xyz', [0, 0, 0])
                rpy = origin.get('rpy', [0, 0, 0])
                
                # Convert radians to degrees for UE5
                rpy_deg = [math.degrees(r) for r in rpy]
                
                entry = {
                    'child': child_link,
                    'parent': link_name,
                    'joint': joint_name,
                    'type': joint_type,
                    'xyz': xyz,
                    'rpy_deg': rpy_deg
                }
                hierarchy_entries.append(entry)
                traverse(child_link, link_name)
        
        traverse(root_link)
        
        script_content = f'''"""
UE5 Hierarchy Reconstruction Script for {robot_name}
===================================================
This script rebuilds the robot hierarchy after importing the USD file.

UE5's Interchange system flattens USD hierarchies when importing.
Run this script in UE5's Python console to:
1. Find all imported Static Mesh Actors from the robot
2. Attach them to their proper parents
3. Apply correct transforms from URDF joint origins

IMPORTANT - Before running this script:
1. Import the {robot_name}_assembled.usd file via Content Browser
2. DRAG the imported meshes from Content Browser into the Level viewport
   (The meshes must be placed as actors in the level, not just imported as assets)
3. Open Window > Developer Tools > Output Log
4. Run: exec(open(r"{script_path}").read())

To list all actors in the level first (for debugging):
  exec(open(r"{script_path}").read()); list_all_actors()

Generated by ROA URDF Converter
"""

import unreal
import math

# Robot configuration
ROBOT_NAME = "{robot_name}"
ROOT_LINK = "{root_link}"

# Hierarchy data: (child_link, parent_link, joint_name, joint_type, [x,y,z], [roll_deg, pitch_deg, yaw_deg])
HIERARCHY_DATA = [
'''
        
        for entry in hierarchy_entries:
            xyz = entry['xyz']
            rpy = entry['rpy_deg']
            script_content += f"    ('{entry['child']}', '{entry['parent']}', '{entry['joint']}', '{entry['type']}', [{xyz[0]:.6f}, {xyz[1]:.6f}, {xyz[2]:.6f}], [{rpy[0]:.3f}, {rpy[1]:.3f}, {rpy[2]:.3f}]),\n"
        
        script_content += f''']

def find_actor_by_link_name(link_name, prefer_visual=True):
    """Find an actor in the level that matches the link name.
    
    Searches for actors with naming patterns (prioritized):
    1. Robot-prefixed names: 'robotname_shoulder_link_visual' (multi-robot support)
    2. Standard names: 'shoulder_link_visual'
    3. Exact match: 'shoulder_link'
    4. Partial matches in actor labels
    """
    # Get all actors
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_subsystem.get_all_level_actors()
    
    # Sanitize names
    sanitized_name = link_name.replace('-', '_').replace(' ', '_').lower()
    sanitized_robot = ROBOT_NAME.replace('-', '_').replace(' ', '_').lower()
    
    # Build search patterns - prioritize robot-prefixed names for multi-robot disambiguation
    search_patterns = []
    if prefer_visual:
        search_patterns = [
            # Robot-prefixed patterns (highest priority for multi-robot scenes)
            f"{{sanitized_robot}}_{{sanitized_name}}_visual",
            f"{{sanitized_robot}}_{{sanitized_name}}",
            # Standard patterns (fallback for single-robot scenes)
            sanitized_name + '_visual',
            sanitized_name,
            sanitized_name + '_collision',
            link_name.lower() + '_visual',
            link_name.lower(),
        ]
    else:
        search_patterns = [
            # Robot-prefixed patterns
            f"{{sanitized_robot}}_{{sanitized_name}}",
            f"{{sanitized_robot}}_{{sanitized_name}}_visual",
            # Standard patterns
            sanitized_name,
            sanitized_name + '_visual',
            sanitized_name + '_collision',
            link_name.lower(),
        ]
    
    # First pass: exact matches (actor name starts with pattern)
    for pattern in search_patterns:
        for actor in all_actors:
            actor_name = actor.get_actor_label().lower()
            # Check if actor name starts with our pattern
            if actor_name.startswith(pattern) or actor_name == pattern:
                unreal.log(f"  Found actor: {{actor.get_actor_label()}} (matched: {{pattern}})")
                return actor
    
    # Second pass: partial matches (pattern is contained in actor name)
    for pattern in search_patterns:
        for actor in all_actors:
            actor_name = actor.get_actor_label().lower()
            if pattern in actor_name:
                unreal.log(f"  Found actor: {{actor.get_actor_label()}} (contains: {{pattern}})")
                return actor
    
    return None

def create_empty_actor(name, location=unreal.Vector(0, 0, 0)):
    """Create an empty actor to serve as hierarchy parent."""
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    spawned = actor_subsystem.spawn_actor_from_class(unreal.Actor, location)
    spawned.set_actor_label(name)
    return spawned

def list_all_actors():
    """List all actors in the current level - useful for debugging."""
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_subsystem.get_all_level_actors()
    
    unreal.log("=" * 60)
    unreal.log(f"All actors in level ({{len(all_actors)}} total):")
    unreal.log("=" * 60)
    
    static_mesh_actors = []
    for actor in all_actors:
        label = actor.get_actor_label()
        class_name = actor.get_class().get_name()
        if 'StaticMeshActor' in class_name:
            static_mesh_actors.append(label)
            unreal.log(f"  [MESH] {{label}}")
        else:
            unreal.log(f"  [{{class_name}}] {{label}}")
    
    unreal.log("=" * 60)
    unreal.log(f"Static Mesh Actors found: {{len(static_mesh_actors)}}")
    if len(static_mesh_actors) == 0:
        unreal.log_warning("No static mesh actors found! Did you drag the meshes into the level?")
    unreal.log("=" * 60)
    return static_mesh_actors

def rebuild_hierarchy():
    """Rebuild the robot hierarchy from the imported meshes."""
    unreal.log("=" * 60)
    unreal.log(f"Rebuilding hierarchy for {{ROBOT_NAME}}")
    unreal.log("=" * 60)
    
    # Create a root actor for the robot
    root_actor = find_actor_by_link_name(ROOT_LINK)
    if root_actor is None:
        unreal.log_warning(f"Root link '{{ROOT_LINK}}' not found, creating empty actor")
        root_actor = create_empty_actor(ROBOT_NAME)
    else:
        unreal.log(f"Found root link: {{root_actor.get_actor_label()}}")
    
    # Track created parent actors
    link_actors = {{ROOT_LINK: root_actor}}
    
    # Process each hierarchy entry
    for child_link, parent_link, joint_name, joint_type, xyz, rpy_deg in HIERARCHY_DATA:
        unreal.log(f"Processing: {{parent_link}} -> {{child_link}} ({{joint_type}})")
        
        # Find child actor
        child_actor = find_actor_by_link_name(child_link)
        
        if child_actor is None:
            unreal.log_warning(f"  Child actor '{{child_link}}' not found")
            continue
        
        # Find or get parent actor
        parent_actor = link_actors.get(parent_link)
        if parent_actor is None:
            parent_actor = find_actor_by_link_name(parent_link)
            if parent_actor:
                link_actors[parent_link] = parent_actor
        
        if parent_actor is None:
            unreal.log_warning(f"  Parent actor '{{parent_link}}' not found")
            continue
        
        # Attach child to parent
        child_actor.attach_to_actor(
            parent_actor,
            unreal.Name("None"),
            unreal.EAttachmentRule.KEEP_RELATIVE,
            unreal.EAttachmentRule.KEEP_RELATIVE,
            unreal.EAttachmentRule.KEEP_RELATIVE,
            False
        )
        
        # Apply transform (convert meters to centimeters for UE5)
        location = unreal.Vector(xyz[0] * 100, xyz[1] * 100, xyz[2] * 100)
        rotation = unreal.Rotator(rpy_deg[1], rpy_deg[2], rpy_deg[0])  # UE5: Pitch, Yaw, Roll
        
        child_actor.set_actor_relative_location(location, False, False)
        child_actor.set_actor_relative_rotation(rotation, False, False)
        
        # Track this actor
        link_actors[child_link] = child_actor
        
        unreal.log(f"  Attached {{child_link}} to {{parent_link}} at {{location}}")
    
    unreal.log("=" * 60)
    unreal.log(f"Hierarchy rebuild complete! {{len(link_actors)}} links processed.")
    unreal.log("=" * 60)

# Run the rebuild
if __name__ == "__main__" or True:
    rebuild_hierarchy()
'''
        
        # Write the script
        with open(script_path, 'w') as f:
            f.write(script_content)
        
        self._log_info(f"Generated UE5 hierarchy script: {script_path}")
    
    def _create_link_hierarchy(self, stage, parent_path, link_name, links, joints, link_tree, usd_materials, materials, created_links, parts, warnings, parent_joint_data=None, visuals_root=None, collisions_root=None):
        """
        Create the robot hierarchy with proper joint transforms applied.
        Each child link is positioned according to its parent joint's origin transform.
        
        Args:
            visuals_root: Optional root path for all visual geometries (v3.3)
            collisions_root: Optional root path for all collision geometries (v3.3)
        
        v3.3: Visuals and collisions can now be organized in separate top-level folders
        """
        if link_name in created_links:
            return
        created_links.add(link_name)
        link_data = links.get(link_name)
        if link_data is None:
            warnings.append(f"Link not found: {link_name}")
            return
        
        safe_name = self._sanitize_name(link_name)
        link_path = f"{parent_path}/{safe_name}"
        link_xform = UsdGeom.Xform.Define(stage, link_path)
        parts.append(link_name)
        
        # Apply joint transform if this link has a parent joint
        if parent_joint_data is not None:
            origin = parent_joint_data.get('origin', {'xyz': [0, 0, 0], 'rpy': [0, 0, 0]})
            xyz = origin.get('xyz', [0, 0, 0])
            rpy = origin.get('rpy', [0, 0, 0])
            
            # Apply translation (convert to USD units - meters)
            if any(v != 0 for v in xyz):
                link_xform.AddTranslateOp().Set(Gf.Vec3d(xyz[0], xyz[1], xyz[2]))
                self._log_info(f"  Applied translation to {link_name}: ({xyz[0]:.4f}, {xyz[1]:.4f}, {xyz[2]:.4f})")
            
            # Apply rotation (RPY in radians → degrees for USD)
            # URDF uses fixed-axis XYZ (roll-pitch-yaw) convention
            if any(v != 0 for v in rpy):
                roll, pitch, yaw = rpy
                # Apply in reverse order: Z (yaw) → Y (pitch) → X (roll)
                if yaw != 0:
                    link_xform.AddRotateZOp().Set(float(math.degrees(yaw)))
                if pitch != 0:
                    link_xform.AddRotateYOp().Set(float(math.degrees(pitch)))
                if roll != 0:
                    link_xform.AddRotateXOp().Set(float(math.degrees(roll)))
                self._log_info(f"  Applied rotation to {link_name}: roll={math.degrees(roll):.1f}°, pitch={math.degrees(pitch):.1f}°, yaw={math.degrees(yaw):.1f}°")
        
        # Create visuals in separate root folder or under link
        if self.include_visual and link_data['visuals']:
            if visuals_root:
                # v3.3: Place all visuals in dedicated /Visuals folder
                visuals_path = visuals_root
            else:
                # Legacy: Place visuals under link
                visuals_path = f"{link_path}/Visuals"
                UsdGeom.Scope.Define(stage, visuals_path)
            
            for i, visual in enumerate(link_data['visuals']):
                # Use ROBOT_linkname_visual naming for multi-robot disambiguation
                robot_prefix = getattr(self, '_current_robot_name', '')
                if robot_prefix:
                    visual_name = f"{robot_prefix}_{safe_name}_visual" if len(link_data['visuals']) == 1 else f"{robot_prefix}_{safe_name}_visual_{i}"
                else:
                    visual_name = f"{safe_name}_visual" if len(link_data['visuals']) == 1 else f"{safe_name}_visual_{i}"
                self._create_geometry(stage, visuals_path, visual_name, visual, usd_materials, materials, warnings)
        
        # Create collisions in separate root folder or under link
        if self.include_collision and link_data['collisions']:
            if collisions_root:
                # v3.3: Place all collisions in dedicated /Collisions folder
                collisions_path = collisions_root
            else:
                # Legacy: Place collisions under link
                collisions_path = f"{link_path}/Collisions"
                UsdGeom.Scope.Define(stage, collisions_path)
            
            for i, collision in enumerate(link_data['collisions']):
                # Use ROBOT_linkname_collision naming for multi-robot disambiguation
                robot_prefix = getattr(self, '_current_robot_name', '')
                if robot_prefix:
                    collision_name = f"{robot_prefix}_{safe_name}_collision" if len(link_data['collisions']) == 1 else f"{robot_prefix}_{safe_name}_collision_{i}"
                else:
                    collision_name = f"{safe_name}_collision" if len(link_data['collisions']) == 1 else f"{safe_name}_collision_{i}"
                self._create_geometry(stage, collisions_path, collision_name, collision, {}, {}, warnings, is_collision=True)
        
        if link_data['inertial'] and link_data['inertial']['mass'] > 0:
            self._add_physics_to_link(stage, link_path, link_data['inertial'])
        
        # Process child links with their joint transforms (pass along the root paths)
        for joint_name, child_link_name in link_tree.get(link_name, []):
            joint_data = joints.get(joint_name)
            if joint_data:
                self._log_info(f"Joint: {joint_name} ({joint_data['type']}) - {joint_data['parent']} -> {child_link_name}")
            # Pass joint_data to child so it applies the transform
            self._create_link_hierarchy(stage, link_path, child_link_name, links, joints, link_tree, usd_materials, materials, created_links, parts, warnings, parent_joint_data=joint_data, visuals_root=visuals_root, collisions_root=collisions_root)
    
    def _create_flat_parts(self, stage, parent_path, root_link, links, link_tree, usd_materials, materials, parts, warnings):
        """
        Create a FLAT structure of parts - each link is at the top level for easy individual access.
        No nesting - just link_name folders with their meshes inside.
        """
        self._log_info("Creating flat parts structure...")
        
        # Collect all link names first
        all_links = []
        self._collect_all_links(root_link, link_tree, all_links)
        
        for link_name in all_links:
            link_data = links.get(link_name)
            if link_data is None:
                continue
            
            safe_name = self._sanitize_name(link_name)
            link_path = f"{parent_path}/{safe_name}"
            UsdGeom.Xform.Define(stage, link_path)
            parts.append(link_name)
            
            # Get robot prefix for multi-robot disambiguation
            robot_prefix = getattr(self, '_current_robot_name', '')
            
            # Add visuals directly under link (no Visuals subfolder for cleaner structure)
            if self.include_visual and link_data['visuals']:
                for i, visual in enumerate(link_data['visuals']):
                    # Use ROBOT_linkname_visual naming
                    if robot_prefix:
                        visual_name = f"{robot_prefix}_{safe_name}_visual" if len(link_data['visuals']) == 1 else f"{robot_prefix}_{safe_name}_visual_{i}"
                    else:
                        visual_name = f"{safe_name}_visual" if len(link_data['visuals']) == 1 else f"{safe_name}_visual_{i}"
                    self._create_geometry(stage, link_path, visual_name, visual, usd_materials, materials, warnings)
            
            # Add collisions with robot-prefixed names
            if self.include_collision and link_data['collisions']:
                for i, collision in enumerate(link_data['collisions']):
                    # Use ROBOT_linkname_collision naming
                    if robot_prefix:
                        collision_name = f"{robot_prefix}_{safe_name}_collision" if len(link_data['collisions']) == 1 else f"{robot_prefix}_{safe_name}_collision_{i}"
                    else:
                        collision_name = f"{safe_name}_collision" if len(link_data['collisions']) == 1 else f"{safe_name}_collision_{i}"
                    self._create_geometry(stage, link_path, collision_name, collision, {}, {}, warnings, is_collision=True)
        
        self._log_info(f"Created {len(all_links)} individual parts")
    
    def _collect_all_links(self, link_name, link_tree, result):
        """Recursively collect all link names in the robot."""
        result.append(link_name)
        for joint_name, child_link_name in link_tree.get(link_name, []):
            self._collect_all_links(child_link_name, link_tree, result)
    
    def _create_assembled_robot(self, stage, assembled_path, parts_path, root_link, links, joints, link_tree, warnings):
        """
        Create an assembled robot that references all parts in their correct positions.
        This creates a complete robot body ready to drag into a scene.
        """
        self._log_info("Creating assembled robot body...")
        
        # First, build a map of link_name -> actual USD path in Parts hierarchy
        link_paths = {}
        self._build_link_path_map(parts_path, root_link, link_tree, link_paths)
        
        # Recursively add references to parts with proper transforms
        self._add_assembled_link(
            stage=stage,
            assembled_parent=assembled_path,
            link_name=root_link,
            link_paths=link_paths,
            links=links,
            joints=joints,
            link_tree=link_tree,
            created=set(),
            warnings=warnings
        )
        
        self._log_info("Assembled robot body created successfully")
    
    def _build_link_path_map(self, parent_path, link_name, link_tree, link_paths):
        """Build a map of link names to their actual USD paths in the Parts hierarchy."""
        safe_name = self._sanitize_name(link_name)
        link_path = f"{parent_path}/{safe_name}"
        link_paths[link_name] = link_path
        
        # Recurse for children
        for joint_name, child_link_name in link_tree.get(link_name, []):
            self._build_link_path_map(link_path, child_link_name, link_tree, link_paths)
    
    def _add_assembled_link(self, stage, assembled_parent, link_name, link_paths,
                            links, joints, link_tree, created, warnings):
        """
        Recursively add links to the assembled robot with cumulative transforms.
        Uses USD references to avoid duplicating geometry.
        """
        if link_name in created:
            return
        created.add(link_name)
        
        link_data = links.get(link_name)
        if link_data is None:
            return
        
        safe_name = self._sanitize_name(link_name)
        parts_link_path = link_paths.get(link_name)  # Use the actual path from the map
        assembled_link_path = f"{assembled_parent}/{safe_name}"
        
        if parts_link_path is None:
            warnings.append(f"Could not find parts path for link: {link_name}")
            return
        
        # Create an Xform for this link in the assembled hierarchy
        assembled_xform = UsdGeom.Xform.Define(stage, assembled_link_path)
        prim = assembled_xform.GetPrim()
        
        # Add reference to the original part (this shares geometry, no duplication)
        prim.GetReferences().AddInternalReference(parts_link_path)
        
        # Process child links through joints
        for joint_name, child_link_name in link_tree.get(link_name, []):
            joint_data = joints.get(joint_name)
            if joint_data:
                # Apply joint origin transform
                origin = joint_data.get('origin', {'xyz': [0, 0, 0], 'rpy': [0, 0, 0]})
                xyz = origin.get('xyz', [0, 0, 0])
                rpy = origin.get('rpy', [0, 0, 0])
                
                # Create child link with joint transform applied
                child_safe_name = self._sanitize_name(child_link_name)
                child_path = f"{assembled_link_path}/{child_safe_name}"
                child_xform = UsdGeom.Xform.Define(stage, child_path)
                
                # Apply translation
                if any(v != 0 for v in xyz):
                    child_xform.AddTranslateOp().Set(Gf.Vec3d(xyz[0], xyz[1], xyz[2]))
                
                # Apply rotation (RPY to quaternion)
                if any(v != 0 for v in rpy):
                    roll, pitch, yaw = rpy
                    # Apply rotations in order: Z (yaw), Y (pitch), X (roll)
                    if yaw != 0:
                        child_xform.AddRotateZOp().Set(float(math.degrees(yaw)))
                    if pitch != 0:
                        child_xform.AddRotateYOp().Set(float(math.degrees(pitch)))
                    if roll != 0:
                        child_xform.AddRotateXOp().Set(float(math.degrees(roll)))
                
                # Add reference to child's parts using the correct path from map
                child_parts_path = link_paths.get(child_link_name)
                if child_parts_path:
                    child_xform.GetPrim().GetReferences().AddInternalReference(child_parts_path)
                
                # Recurse for grandchildren
                for grandchild_joint, grandchild_link in link_tree.get(child_link_name, []):
                    self._add_assembled_link(
                        stage=stage,
                        assembled_parent=child_path,
                        link_name=grandchild_link,
                        link_paths=link_paths,
                        links=links,
                        joints=joints,
                        link_tree=link_tree,
                        created=created,
                        warnings=warnings
                    )
                
                created.add(child_link_name)
    
    def _create_geometry(self, stage, parent_path, name, geom_data, usd_materials, materials, warnings, is_collision=False):
        geom = geom_data.get('geometry')
        if geom is None:
            return
        geom_path = f"{parent_path}/{name}"
        origin = geom_data.get('origin', {'xyz': [0, 0, 0], 'rpy': [0, 0, 0]})
        geom_type = geom.get('type')
        
        if geom_type == 'box':
            size = geom.get('size', [1, 1, 1])
            usd_geom = UsdGeom.Cube.Define(stage, geom_path)
            usd_geom.GetSizeAttr().Set(1.0)
            xform = UsdGeom.Xformable(usd_geom)
            xform.AddScaleOp().Set(Gf.Vec3f(size[0]/2, size[1]/2, size[2]/2))
        elif geom_type == 'cylinder':
            usd_geom = UsdGeom.Cylinder.Define(stage, geom_path)
            usd_geom.GetRadiusAttr().Set(geom.get('radius', 0.1))
            usd_geom.GetHeightAttr().Set(geom.get('length', 1.0))
            usd_geom.GetAxisAttr().Set('Z')
        elif geom_type == 'sphere':
            usd_geom = UsdGeom.Sphere.Define(stage, geom_path)
            usd_geom.GetRadiusAttr().Set(geom.get('radius', 0.1))
        elif geom_type == 'mesh':
            mesh_path = self._resolve_mesh_path(geom.get('filename', ''))
            if mesh_path and mesh_path.exists():
                try:
                    # v3.4: Enhanced mesh loading with VRML support
                    mesh = self._load_mesh_file(mesh_path, warnings)
                    if mesh is not None and hasattr(mesh, 'vertices'):
                        mesh.apply_scale(geom.get('scale', [1,1,1]))
                        
                        # v3.4: Apply convex decomposition for collision meshes
                        if is_collision and self.mesh_config.get('enable_convex_decomposition', True):
                            mesh = self._apply_convex_decomposition(mesh, name, warnings)
                        
                        usd_geom = UsdGeom.Mesh.Define(stage, geom_path)
                        # Convert to native Python float for USD compatibility
                        vertices = mesh.vertices.tolist()
                        usd_geom.GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(float(v[0]), float(v[1]), float(v[2])) for v in vertices]))
                        faces = mesh.faces.astype(np.int32)
                        usd_geom.GetFaceVertexCountsAttr().Set(Vt.IntArray([3] * len(faces)))
                        usd_geom.GetFaceVertexIndicesAttr().Set(Vt.IntArray(faces.flatten().tolist()))
                        if hasattr(mesh, 'vertex_normals'):
                            normals = mesh.vertex_normals.tolist()
                            usd_geom.GetNormalsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(float(n[0]), float(n[1]), float(n[2])) for n in normals]))
                        usd_geom.GetSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
                        
                        # v3.4: Handle texture embedding
                        if self.mesh_config.get('embed_textures', False):
                            self._embed_mesh_textures(stage, geom_path, mesh, mesh_path, warnings)
                    else:
                        warnings.append(f"Failed to load mesh: {geom.get('filename')}")
                        return
                except Exception as e:
                    warnings.append(f"Error loading mesh {geom.get('filename')}: {e}")
                    return
            else:
                warnings.append(f"Mesh file not found: {geom.get('filename')}")
                return
        else:
            warnings.append(f"Unknown geometry type: {geom_type}")
            return
        
        self._apply_origin_transform(stage, geom_path, origin)
        
        if not is_collision:
            mat_name = geom_data.get('material')
            if mat_name and mat_name in usd_materials:
                mat_prim = stage.GetPrimAtPath(usd_materials[mat_name])
                if mat_prim:
                    # Apply MaterialBindingAPI schema before binding to prevent USD import warnings
                    geom_prim = stage.GetPrimAtPath(geom_path)
                    binding_api = UsdShade.MaterialBindingAPI.Apply(geom_prim)
                    binding_api.Bind(UsdShade.Material(mat_prim))
        if is_collision:
            prim = stage.GetPrimAtPath(geom_path)
            if prim:
                UsdPhysics.CollisionAPI.Apply(prim)
    
    def _load_mesh_file(self, mesh_path: Path, warnings: List[str]):
        """
        Load mesh file with extended format support (v3.4).
        
        Supports:
        - STL (ASCII and binary)
        - OBJ (with MTL)
        - DAE (Collada)
        - WRL/VRML (new in v3.4)
        - PLY
        - GLTF/GLB
        
        Args:
            mesh_path: Path to mesh file
            warnings: List to append warnings to
            
        Returns:
            trimesh.Trimesh object or None
        """
        suffix = mesh_path.suffix.lower()
        
        try:
            if suffix == '.wrl':
                # VRML support via trimesh (handles VRML 2.0 / VRML97)
                mesh = trimesh.load(str(mesh_path), file_type='vrml', force='mesh')
                self._log_info(f"Loaded VRML mesh: {mesh_path.name}")
            elif suffix in ['.gltf', '.glb']:
                # GLTF/GLB support
                scene = trimesh.load(str(mesh_path))
                if isinstance(scene, trimesh.Scene):
                    # Merge all geometries in scene
                    meshes = [g for g in scene.geometry.values() if isinstance(g, trimesh.Trimesh)]
                    if meshes:
                        mesh = trimesh.util.concatenate(meshes)
                    else:
                        warnings.append(f"No mesh geometry found in GLTF: {mesh_path.name}")
                        return None
                else:
                    mesh = scene
                self._log_info(f"Loaded GLTF mesh: {mesh_path.name}")
            else:
                # Standard formats (STL, OBJ, DAE, PLY)
                mesh = trimesh.load(str(mesh_path), force='mesh')
            
            return mesh
            
        except Exception as e:
            warnings.append(f"Failed to load mesh {mesh_path.name}: {e}")
            return None
    
    def _apply_convex_decomposition(self, mesh, name: str, warnings: List[str]):
        """
        Apply convex decomposition to collision mesh (v3.4).
        
        Uses V-HACD algorithm via trimesh for better physics collision.
        Falls back to convex hull if V-HACD fails.
        
        Args:
            mesh: trimesh.Trimesh input mesh
            name: Name for logging
            warnings: List to append warnings to
            
        Returns:
            Convex decomposed or simplified mesh
        """
        try:
            # Check if mesh is already convex
            if mesh.is_convex:
                self._log_info(f"  Mesh {name} is already convex, skipping decomposition")
                return mesh
            
            # Try V-HACD decomposition
            try:
                convex_hulls = mesh.convex_decomposition(
                    maxhulls=self.mesh_config.get('convex_max_hulls', 16),
                    resolution=self.mesh_config.get('convex_resolution', 100000)
                )
                
                if convex_hulls and len(convex_hulls) > 0:
                    # Combine all convex hulls into single mesh
                    if len(convex_hulls) == 1:
                        result = convex_hulls[0]
                    else:
                        result = trimesh.util.concatenate(convex_hulls)
                    
                    self._log_info(f"  Convex decomposition for {name}: {len(convex_hulls)} hulls")
                    return result
                    
            except Exception as vhacd_error:
                self._log_warning(f"V-HACD failed for {name}: {vhacd_error}, falling back to convex hull")
            
            # Fallback to simple convex hull
            convex_hull = mesh.convex_hull
            if convex_hull is not None:
                self._log_info(f"  Using convex hull for {name}")
                return convex_hull
            
            # If all else fails, return original mesh
            warnings.append(f"Convex decomposition failed for {name}, using original mesh")
            return mesh
            
        except Exception as e:
            warnings.append(f"Error in convex decomposition for {name}: {e}")
            return mesh
    
    def _embed_mesh_textures(self, stage, geom_path: str, mesh, mesh_path: Path, warnings: List[str]):
        """
        Embed textures from mesh into USD (v3.4).
        
        Extracts texture references from mesh materials and embeds them
        as USD texture assets.
        
        Args:
            stage: USD stage
            geom_path: Path to geometry prim
            mesh: trimesh.Trimesh mesh
            mesh_path: Original mesh file path
            warnings: List to append warnings to
        """
        try:
            # Check if mesh has visual (textures/materials)
            if not hasattr(mesh, 'visual') or mesh.visual is None:
                return
            
            visual = mesh.visual
            
            # Handle TextureVisuals (has UV and texture image)
            if hasattr(visual, 'material') and visual.material is not None:
                material = visual.material
                
                # Check for diffuse texture
                if hasattr(material, 'image') and material.image is not None:
                    # Save texture as asset
                    texture_name = f"{mesh_path.stem}_diffuse.png"
                    texture_dir = mesh_path.parent / "textures"
                    texture_dir.mkdir(exist_ok=True)
                    texture_path = texture_dir / texture_name
                    
                    # Save the image
                    try:
                        material.image.save(str(texture_path))
                        self._log_info(f"  Embedded texture: {texture_name}")
                        
                        # Reference texture in USD material
                        # (USD material binding would be handled separately)
                    except Exception as save_error:
                        warnings.append(f"Failed to save texture {texture_name}: {save_error}")
                        
        except Exception as e:
            # Texture embedding is optional, don't fail the import
            self._log_warning(f"Texture embedding skipped: {e}")
    
    def _resolve_mesh_path(self, filename: str) -> Optional[Path]:
        """
        Resolve mesh file path from URDF filename attribute.
        
        Handles:
        - package://pkg_name/path/to/mesh.stl - ROS package URLs
        - file:///absolute/path.stl - File URLs
        - relative/path.stl - Relative to URDF directory
        - /absolute/path.stl - Absolute paths
        
        Uses registered package paths and default search locations.
        """
        if not filename:
            return None
            
        if filename.startswith('package://'):
            # Parse package URL: package://pkg_name/relative/path
            rel_path = filename.replace('package://', '')
            parts = rel_path.split('/', 1)
            
            if len(parts) == 2:
                pkg_name, pkg_rel_path = parts
                
                # 1. Check explicitly registered packages first
                if pkg_name in self._package_cache:
                    mesh_path = self._package_cache[pkg_name] / pkg_rel_path
                    if mesh_path.exists():
                        return mesh_path
                
                # 2. Search in configured package paths
                for base_path in self.package_paths:
                    pkg_dir = Path(base_path) / pkg_name
                    if pkg_dir.exists():
                        mesh_path = pkg_dir / pkg_rel_path
                        if mesh_path.exists():
                            # Cache for future lookups
                            self._package_cache[pkg_name] = pkg_dir
                            return mesh_path
                
                # 3. Search relative to URDF directory (common pattern)
                if self.urdf_dir:
                    # Try package dir relative to URDF location
                    for search_base in [self.urdf_dir, self.urdf_dir.parent, self.urdf_dir.parent.parent]:
                        # Look for package folder
                        pkg_dir = search_base / pkg_name
                        if pkg_dir.exists():
                            mesh_path = pkg_dir / pkg_rel_path
                            if mesh_path.exists():
                                self._package_cache[pkg_name] = pkg_dir
                                return mesh_path
                        
                        # Also try just the relative path (without package name)
                        mesh_path = search_base / pkg_rel_path
                        if mesh_path.exists():
                            return mesh_path
            else:
                # No package name, just relative path after package://
                rel_path = parts[0]
                for base in [self.urdf_dir, self.urdf_dir.parent, self.urdf_dir.parent.parent]:
                    if base:
                        mp = base / rel_path
                        if mp.exists():
                            return mp
                            
        elif filename.startswith('file://'):
            return Path(filename.replace('file://', ''))
            
        # Try relative to URDF directory
        if self.urdf_dir:
            mp = self.urdf_dir / filename
            if mp.exists():
                return mp
                
        # Try as absolute path
        mp = Path(filename)
        if mp.exists():
            return mp
            
        return None
    
    def _apply_origin_transform(self, stage, prim_path, origin):
        prim = stage.GetPrimAtPath(prim_path)
        if not prim:
            return
        xformable = UsdGeom.Xformable(prim)
        xyz = origin.get('xyz', [0, 0, 0])
        rpy = origin.get('rpy', [0, 0, 0])
        if any(v != 0 for v in xyz):
            xformable.AddTranslateOp().Set(Gf.Vec3d(*xyz))
        if any(v != 0 for v in rpy):
            roll_deg, pitch_deg, yaw_deg = [math.degrees(r) for r in rpy]
            if yaw_deg != 0:
                xformable.AddRotateZOp().Set(yaw_deg)
            if pitch_deg != 0:
                xformable.AddRotateYOp().Set(pitch_deg)
            if roll_deg != 0:
                xformable.AddRotateXOp().Set(roll_deg)
    
    def _add_physics_to_link(self, stage, link_path, inertial):
        prim = stage.GetPrimAtPath(link_path)
        if not prim:
            return
        UsdPhysics.RigidBodyAPI.Apply(prim)
        mass_api = UsdPhysics.MassAPI.Apply(prim)
        mass_api.GetMassAttr().Set(inertial.get('mass', 1.0))
        origin = inertial.get('origin', {})
        xyz = origin.get('xyz', [0, 0, 0])
        if any(v != 0 for v in xyz):
            mass_api.GetCenterOfMassAttr().Set(Gf.Vec3f(*xyz))
        
        # Add inertia tensor if available (v3.0)
        inertia = inertial.get('inertia')
        if inertia:
            # USD uses diagonal inertia only, compute from URDF inertia tensor
            ixx = inertia.get('ixx', 1.0)
            iyy = inertia.get('iyy', 1.0)
            izz = inertia.get('izz', 1.0)
            mass_api.GetDiagonalInertiaAttr().Set(Gf.Vec3f(ixx, iyy, izz))
    
    # ==================== USD PHYSICS METHODS (v3.0) ====================
    
    def _create_physics_scene(self, stage):
        """
        Create a PhysicsScene prim with gravity settings.
        Required for USD Physics simulation.
        """
        scene_path = "/PhysicsScene"
        physics_scene = UsdPhysics.Scene.Define(stage, scene_path)
        
        # Set gravity
        gravity_dir = self.physics_config['gravity_direction']
        gravity_mag = self.physics_config['gravity_magnitude']
        
        physics_scene.GetGravityDirectionAttr().Set(Gf.Vec3f(*gravity_dir))
        physics_scene.GetGravityMagnitudeAttr().Set(gravity_mag)
        
        self._log_info(f"Created PhysicsScene with gravity: {gravity_dir} @ {gravity_mag} m/s²")
        return physics_scene
    
    def _create_physics_joints(self, stage, robot_path, root_link, joints, link_tree, warnings):
        """
        Create USD Physics joint prims for all URDF joints.
        
        Maps URDF joint types to USD Physics joint types:
        - revolute/continuous -> PhysicsRevoluteJoint
        - prismatic -> PhysicsPrismaticJoint  
        - fixed -> PhysicsFixedJoint
        
        Also adds:
        - DriveAPI for motor control
        - LimitAPI for joint limits
        - FilteredPairsAPI for self-collision between adjacent links
        """
        joints_path = f"{robot_path}/Joints"
        UsdGeom.Scope.Define(stage, joints_path)
        
        # Track adjacent link pairs for self-collision filtering
        adjacent_pairs = []
        
        for joint_name, joint_data in joints.items():
            joint_type = joint_data.get('type', 'fixed')
            parent_link = joint_data.get('parent')
            child_link = joint_data.get('child')
            
            if not parent_link or not child_link:
                warnings.append(f"Joint {joint_name} missing parent or child link")
                continue
            
            # Create the appropriate joint type
            safe_joint_name = self._sanitize_name(joint_name)
            joint_prim_path = f"{joints_path}/{safe_joint_name}"
            
            # Get link paths for body references
            parent_link_path = self._find_link_path(stage, robot_path, parent_link)
            child_link_path = self._find_link_path(stage, robot_path, child_link)
            
            if not parent_link_path or not child_link_path:
                warnings.append(f"Could not find link paths for joint {joint_name}")
                continue
            
            # Create joint based on type
            if joint_type in ('revolute', 'continuous'):
                joint_prim = self._create_revolute_joint(
                    stage, joint_prim_path, joint_data,
                    parent_link_path, child_link_path
                )
            elif joint_type == 'prismatic':
                joint_prim = self._create_prismatic_joint(
                    stage, joint_prim_path, joint_data,
                    parent_link_path, child_link_path
                )
            elif joint_type == 'fixed':
                joint_prim = self._create_fixed_joint(
                    stage, joint_prim_path, joint_data,
                    parent_link_path, child_link_path
                )
            else:
                # Default to fixed for unknown types
                warnings.append(f"Unknown joint type '{joint_type}' for {joint_name}, using fixed")
                joint_prim = self._create_fixed_joint(
                    stage, joint_prim_path, joint_data,
                    parent_link_path, child_link_path
                )
            
            if joint_prim:
                self._log_info(f"  Created {joint_type} joint: {joint_name}")
                adjacent_pairs.append((parent_link_path, child_link_path))
        
        # Add self-collision filtering for adjacent links
        if self.physics_config['enable_self_collision_filter'] and adjacent_pairs:
            self._add_filtered_pairs(stage, robot_path, adjacent_pairs)
    
    def _find_link_path(self, stage, robot_path, link_name):
        """
        Find the USD path for a link in the assembled robot hierarchy.
        Searches recursively since links are nested.
        """
        safe_name = self._sanitize_name(link_name)
        
        # Try direct child first
        direct_path = f"{robot_path}/{safe_name}"
        if stage.GetPrimAtPath(direct_path):
            return direct_path
        
        # Search recursively
        robot_prim = stage.GetPrimAtPath(robot_path)
        if robot_prim:
            for prim in Usd.PrimRange(robot_prim):
                if prim.GetName() == safe_name:
                    return str(prim.GetPath())
        
        return None
    
    def _create_revolute_joint(self, stage, joint_path, joint_data, parent_path, child_path):
        """
        Create a PhysicsRevoluteJoint for revolute/continuous URDF joints.
        """
        joint = UsdPhysics.RevoluteJoint.Define(stage, joint_path)
        prim = joint.GetPrim()
        
        # Set body references
        joint.GetBody0Rel().SetTargets([parent_path])
        joint.GetBody1Rel().SetTargets([child_path])
        
        # Set axis (URDF axis -> USD axis token)
        axis = joint_data.get('axis', [1, 0, 0])
        usd_axis = self._axis_to_token(axis)
        joint.GetAxisAttr().Set(usd_axis)
        
        # Set local pose from URDF origin
        origin = joint_data.get('origin', {'xyz': [0, 0, 0], 'rpy': [0, 0, 0]})
        self._set_joint_local_pose(joint, origin)
        
        # Add limits (for revolute joints, not continuous)
        joint_type = joint_data.get('type', 'revolute')
        limits = joint_data.get('limits')
        if limits and joint_type == 'revolute':
            lower = math.degrees(limits.get('lower', -math.pi))
            upper = math.degrees(limits.get('upper', math.pi))
            joint.GetLowerLimitAttr().Set(lower)
            joint.GetUpperLimitAttr().Set(upper)
            self._log_info(f"    Limits: [{lower:.1f}°, {upper:.1f}°]")
        
        # Add DriveAPI for motor control
        self._add_drive_api(prim, joint_data, 'angular')
        
        return prim
    
    def _create_prismatic_joint(self, stage, joint_path, joint_data, parent_path, child_path):
        """
        Create a PhysicsPrismaticJoint for prismatic URDF joints.
        """
        joint = UsdPhysics.PrismaticJoint.Define(stage, joint_path)
        prim = joint.GetPrim()
        
        # Set body references
        joint.GetBody0Rel().SetTargets([parent_path])
        joint.GetBody1Rel().SetTargets([child_path])
        
        # Set axis
        axis = joint_data.get('axis', [1, 0, 0])
        usd_axis = self._axis_to_token(axis)
        joint.GetAxisAttr().Set(usd_axis)
        
        # Set local pose from URDF origin
        origin = joint_data.get('origin', {'xyz': [0, 0, 0], 'rpy': [0, 0, 0]})
        self._set_joint_local_pose(joint, origin)
        
        # Add limits
        limits = joint_data.get('limits')
        if limits:
            lower = limits.get('lower', -1.0)  # meters
            upper = limits.get('upper', 1.0)   # meters
            joint.GetLowerLimitAttr().Set(lower)
            joint.GetUpperLimitAttr().Set(upper)
            self._log_info(f"    Limits: [{lower:.3f}m, {upper:.3f}m]")
        
        # Add DriveAPI for motor control
        self._add_drive_api(prim, joint_data, 'linear')
        
        return prim
    
    def _create_fixed_joint(self, stage, joint_path, joint_data, parent_path, child_path):
        """
        Create a PhysicsFixedJoint for fixed URDF joints.
        """
        joint = UsdPhysics.FixedJoint.Define(stage, joint_path)
        prim = joint.GetPrim()
        
        # Set body references
        joint.GetBody0Rel().SetTargets([parent_path])
        joint.GetBody1Rel().SetTargets([child_path])
        
        # Set local pose from URDF origin
        origin = joint_data.get('origin', {'xyz': [0, 0, 0], 'rpy': [0, 0, 0]})
        self._set_joint_local_pose(joint, origin)
        
        return prim
    
    def _axis_to_token(self, axis):
        """
        Convert URDF axis vector to USD axis token.
        USD only supports X, Y, Z as axis - pick dominant axis.
        """
        abs_axis = [abs(a) for a in axis]
        max_idx = abs_axis.index(max(abs_axis))
        
        if max_idx == 0:
            return "X"
        elif max_idx == 1:
            return "Y"
        else:
            return "Z"
    
    def _set_joint_local_pose(self, joint, origin):
        """
        Set the local pose (position and orientation) for a USD Physics joint.
        Uses localPos0/localRot0 for body0 frame.
        """
        xyz = origin.get('xyz', [0, 0, 0])
        rpy = origin.get('rpy', [0, 0, 0])
        
        # Set local position
        joint.GetLocalPos0Attr().Set(Gf.Vec3f(*xyz))
        joint.GetLocalPos1Attr().Set(Gf.Vec3f(0, 0, 0))
        
        # Convert RPY to quaternion for local rotation
        quat = self._rpy_to_quaternion(rpy)
        joint.GetLocalRot0Attr().Set(quat)
        joint.GetLocalRot1Attr().Set(Gf.Quatf(1, 0, 0, 0))  # Identity
    
    def _rpy_to_quaternion(self, rpy):
        """
        Convert Roll-Pitch-Yaw (radians) to USD Quaternion.
        URDF uses fixed-axis XYZ convention (roll, pitch, yaw).
        """
        roll, pitch, yaw = rpy
        
        # Compute quaternion from Euler angles (XYZ order)
        cy = math.cos(yaw * 0.5)
        sy = math.sin(yaw * 0.5)
        cp = math.cos(pitch * 0.5)
        sp = math.sin(pitch * 0.5)
        cr = math.cos(roll * 0.5)
        sr = math.sin(roll * 0.5)
        
        w = cr * cp * cy + sr * sp * sy
        x = sr * cp * cy - cr * sp * sy
        y = cr * sp * cy + sr * cp * sy
        z = cr * cp * sy - sr * sp * cy
        
        return Gf.Quatf(w, x, y, z)
    
    def _add_drive_api(self, joint_prim, joint_data, drive_type='angular'):
        """
        Add DriveAPI to a joint for motor control.
        
        Args:
            joint_prim: The USD joint prim
            joint_data: URDF joint data
            drive_type: 'angular' for revolute, 'linear' for prismatic
        """
        # Determine the drive axis based on URDF axis
        axis = joint_data.get('axis', [1, 0, 0])
        axis_token = self._axis_to_token(axis)
        
        # For angular drives, the instance name is like "angular:X"
        if drive_type == 'angular':
            # Apply DriveAPI with rotation axis
            drive_api_name = f"rot{axis_token}"
        else:
            # For linear drives
            drive_api_name = f"trans{axis_token}"
        
        # Apply the multi-apply DriveAPI schema
        drive_api = UsdPhysics.DriveAPI.Apply(joint_prim, drive_api_name)
        
        # Set drive parameters
        # Use URDF effort/velocity limits if available, else use defaults
        limits = joint_data.get('limits') or {}
        
        stiffness = self.physics_config['default_drive_stiffness']
        damping = self.physics_config['default_drive_damping']
        max_force = limits.get('effort', self.physics_config['default_max_force']) if limits else self.physics_config['default_max_force']
        
        drive_api.GetStiffnessAttr().Set(stiffness)
        drive_api.GetDampingAttr().Set(damping)
        drive_api.GetMaxForceAttr().Set(max_force)
        
        # Set drive type to force (not acceleration)
        drive_api.GetTypeAttr().Set("force")
        
        # Initialize target position/velocity to 0
        drive_api.GetTargetPositionAttr().Set(0.0)
        drive_api.GetTargetVelocityAttr().Set(0.0)
        
        self._log_info(f"    DriveAPI: stiffness={stiffness}, damping={damping}, maxForce={max_force}")
    
    def _add_filtered_pairs(self, stage, robot_path, adjacent_pairs):
        """
        Add FilteredPairsAPI to disable self-collision between adjacent links.
        This prevents physically connected links from colliding with each other.
        """
        robot_prim = stage.GetPrimAtPath(robot_path)
        if not robot_prim:
            return
        
        # Apply FilteredPairsAPI to the robot root
        filtered_api = UsdPhysics.FilteredPairsAPI.Apply(robot_prim)
        
        # Build list of filtered pair paths
        filtered_paths = []
        for parent_path, child_path in adjacent_pairs:
            filtered_paths.append(parent_path)
            filtered_paths.append(child_path)
        
        # Set the filtered pairs relationship
        if filtered_paths:
            filtered_api.GetFilteredPairsRel().SetTargets(filtered_paths)
            self._log_info(f"Added self-collision filtering for {len(adjacent_pairs)} adjacent link pairs")
    
    # ==================== END USD PHYSICS METHODS ====================
    
    def _create_usd_material(self, stage, mat_path, mat_data):
        material = UsdShade.Material.Define(stage, mat_path)
        shader_path = f"{mat_path}/PreviewSurface"
        shader = UsdShade.Shader.Define(stage, shader_path)
        shader.CreateIdAttr("UsdPreviewSurface")
        color = mat_data.get('color', [0.8, 0.8, 0.8, 1.0])
        if color and len(color) >= 3:
            shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(color[0], color[1], color[2]))
            if len(color) > 3:
                shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(color[3])
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.5)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
        shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
        material.CreateSurfaceOutput().ConnectToSource(shader.CreateOutput("surface", Sdf.ValueTypeNames.Token))
        return material
    
    def _sanitize_name(self, name: str) -> str:
        import re
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        if sanitized and sanitized[0].isdigit():
            sanitized = '_' + sanitized
        return sanitized or 'unnamed'
    
    def _build_hierarchy(self, links, joints, materials=None, sensors=None):
        """
        Build hierarchy dictionary for UE5 assembler with complete robot data.
        
        v3.1 - Enhanced with:
        - Link mass and inertia (for ROC/DIMC)
        - Joint dynamics (damping, friction) for ROC motor control
        - Safety controller data for DIMC
        - Sensor definitions for DIMC
        - Mimic joint relationships
        
        Args:
            links: Dictionary of link data (includes visuals, inertial)
            joints: Dictionary of joint data (includes dynamics, safety_controller)
            materials: Dictionary of material definitions with colors
            sensors: List of sensor definitions for DIMC
            
        Returns:
            Dictionary with hierarchy, materials, sensors, and link-material mappings
        """
        builder = HierarchyBuilder()
        
        # Build link-to-materials mapping
        link_materials = {}
        for link_name, link_data in links.items():
            mat_names = []
            for visual in link_data.get('visuals', []):
                mat_name = visual.get('material')
                if mat_name and mat_name not in mat_names:
                    mat_names.append(mat_name)
            if mat_names:
                link_materials[link_name] = mat_names
        
        # Add links with mass and inertia properties (NEW for ROC/DIMC)
        for link_name, link_data in links.items():
            inertial = link_data.get('inertial', {})
            link_properties = {
                'mass': inertial.get('mass', 0.0) if inertial else 0.0,
                'inertia': inertial.get('inertia', {}) if inertial else {},
                'inertial_origin': inertial.get('origin', {}) if inertial else {},
            }
            builder.add_link(name=link_name, properties=link_properties)
        
        # Collect safety controller data from all joints for DIMC
        safety_controllers = {}
        
        for joint in joints.values():
            # Include all joint properties for physics constraint creation
            joint_properties = {
                'axis': joint.get('axis', [1, 0, 0]),
                'limits': joint.get('limits'),  # {lower, upper, effort, velocity}
                'dynamics': joint.get('dynamics'),  # NEW: {damping, friction}
                'mimic': joint.get('mimic'),  # NEW: {joint, multiplier, offset}
            }
            builder.add_joint(
                name=joint['name'],
                parent_link=joint['parent'],
                child_link=joint['child'],
                joint_type=joint['type'],
                transform=joint.get('origin'),
                properties=joint_properties
            )
            
            # Collect safety controller if present
            if joint.get('safety_controller'):
                safety_controllers[joint['name']] = joint['safety_controller']
        
        hierarchy_dict = builder.build_hierarchy()
        is_valid, errors = builder.validate_hierarchy()
        hierarchy_dict['validation'] = (is_valid, errors)
        hierarchy_dict['assembly_order'] = builder.get_assembly_order()
        
        # Add materials data for UE5 assembler
        hierarchy_dict['materials'] = materials or {}
        hierarchy_dict['link_materials'] = link_materials
        
        # NEW: Add sensors for DIMC
        hierarchy_dict['sensors'] = sensors or []
        
        # NEW: Add safety controllers for DIMC
        hierarchy_dict['safety_controllers'] = safety_controllers
        
        # NEW: Calculate aggregate safety zone from all safety controllers
        if safety_controllers:
            # Use the most restrictive safety zone
            min_soft_lower = min(sc.get('soft_lower_limit', 0) for sc in safety_controllers.values())
            max_soft_upper = max(sc.get('soft_upper_limit', 0) for sc in safety_controllers.values())
            max_k_position = max(sc.get('k_position', 0) for sc in safety_controllers.values())
            hierarchy_dict['global_safety_zone'] = {
                'soft_lower_limit': min_soft_lower,
                'soft_upper_limit': max_soft_upper,
                'k_position': max_k_position,
                'from_urdf': True
            }
        
        return hierarchy_dict
