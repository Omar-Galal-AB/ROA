"""
CAD Hierarchy Inference Module

Implements sophisticated CAD hierarchy and kinematics inference for
STEP/IGES files that lack assembly structure information.

Strategies:
1. Geometric proximity analysis - detect part connections
2. Cylindrical surface detection - infer revolute joints
3. Template matching - recognize known robot patterns
4. User hints from JSON/YAML file
5. Mating surface detection - find contact surfaces

Based on analysis of:
- Fusion360 assembly pattern detection
- onshape-to-robot joint inference
- STEP AP242 semantic product information

Reference implementations analyzed:
- https://github.com/reus/onshape-to-robot
- Fusion360 Joints API
"""

import json
import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set, Callable
import numpy as np

logger = logging.getLogger(__name__)

# Check for OpenCASCADE availability
try:
    from OCC.Core.gp import gp_Pnt, gp_Vec, gp_Ax1, gp_Dir, gp_Trsf
    from OCC.Core.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
    from OCC.Core.GeomAbs import (
        GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Sphere, 
        GeomAbs_Cone, GeomAbs_Torus
    )
    from OCC.Core.BRepGProp import brepgprop_VolumeProperties
    from OCC.Core.GProp import GProp_GProps
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_SOLID
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.TopoDS import topods_Face, topods_Edge, TopoDS_Shape
    PYTHONOCC_AVAILABLE = True
except ImportError:
    PYTHONOCC_AVAILABLE = False
    logger.warning("pythonocc-core not available, CAD inference will be limited")


class InferredJointType(Enum):
    """Types of joints that can be inferred from geometry."""
    FIXED = "fixed"
    REVOLUTE = "revolute"
    PRISMATIC = "prismatic"
    SPHERICAL = "spherical"
    PLANAR = "planar"
    CYLINDRICAL = "cylindrical"
    UNKNOWN = "unknown"


@dataclass
class InferredJoint:
    """A joint inferred from CAD geometry analysis."""
    name: str
    joint_type: InferredJointType
    parent_part: str
    child_part: str
    
    # Position and axis
    origin: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    axis: List[float] = field(default_factory=lambda: [0.0, 0.0, 1.0])
    
    # Limits (if determinable)
    lower_limit: Optional[float] = None
    upper_limit: Optional[float] = None
    
    # Confidence score (0-1)
    confidence: float = 0.5
    
    # Evidence supporting this inference
    evidence: List[str] = field(default_factory=list)
    
    # User override flag
    user_defined: bool = False
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'name': self.name,
            'type': self.joint_type.value,
            'parent_link': self.parent_part,
            'child_link': self.child_part,
            'origin': {'xyz': self.origin, 'rpy': [0, 0, 0]},
            'axis': self.axis,
            'limits': {
                'lower': self.lower_limit or -math.pi,
                'upper': self.upper_limit or math.pi,
            },
            'confidence': self.confidence,
            'evidence': self.evidence,
            'user_defined': self.user_defined,
        }


@dataclass
class PartConnection:
    """Detected connection between two parts."""
    part_a: str
    part_b: str
    connection_type: str  # 'contact', 'coaxial', 'concentric', 'parallel', 'mate'
    contact_point: List[float]
    contact_normal: Optional[List[float]] = None
    shared_axis: Optional[List[float]] = None
    contact_area: float = 0.0
    confidence: float = 0.5


@dataclass
class GeometricFeature:
    """A geometric feature detected on a part."""
    part_name: str
    feature_type: str  # 'cylinder', 'plane', 'sphere', 'hole', 'shaft', 'boss'
    
    # Feature geometry
    center: List[float]
    axis: Optional[List[float]] = None
    radius: Optional[float] = None
    normal: Optional[List[float]] = None
    
    # Bounding info
    length: float = 0.0
    area: float = 0.0
    
    # Role inference
    likely_role: str = ""  # 'bearing', 'shaft', 'mounting', 'actuator'


class RobotTemplate:
    """
    Template for recognizing known robot configurations.
    
    Enables pattern matching to quickly identify:
    - Serial manipulators (UR5, Panda, etc.)
    - Parallel robots (Stewart, Delta)
    - Mobile robots (differential, ackermann)
    - Humanoids
    """
    
    def __init__(
        self,
        name: str,
        pattern_type: str,
        num_parts_range: Tuple[int, int],
        expected_joints: List[Dict],
        detection_hints: List[str]
    ):
        self.name = name
        self.pattern_type = pattern_type
        self.num_parts_range = num_parts_range
        self.expected_joints = expected_joints
        self.detection_hints = detection_hints
    
    def matches(self, parts: List[str], features: List[GeometricFeature]) -> float:
        """
        Calculate match score for this template.
        
        Returns:
            Match confidence 0-1
        """
        score = 0.0
        
        # Check part count
        num_parts = len(parts)
        if self.num_parts_range[0] <= num_parts <= self.num_parts_range[1]:
            score += 0.2
        
        # Check for hint keywords in part names
        for hint in self.detection_hints:
            for part in parts:
                if hint.lower() in part.lower():
                    score += 0.1
        
        return min(score, 1.0)


# Standard robot templates
ROBOT_TEMPLATES = [
    RobotTemplate(
        name="6-DOF Serial Arm",
        pattern_type="serial_arm",
        num_parts_range=(7, 15),
        expected_joints=[
            {'type': 'revolute', 'name_hints': ['base', 'shoulder']},
            {'type': 'revolute', 'name_hints': ['shoulder', 'upper']},
            {'type': 'revolute', 'name_hints': ['elbow']},
            {'type': 'revolute', 'name_hints': ['wrist1', 'forearm']},
            {'type': 'revolute', 'name_hints': ['wrist2']},
            {'type': 'revolute', 'name_hints': ['wrist3', 'tool']},
        ],
        detection_hints=['base', 'shoulder', 'elbow', 'wrist', 'tool', 'flange', 'link']
    ),
    RobotTemplate(
        name="SCARA Robot",
        pattern_type="scara",
        num_parts_range=(4, 8),
        expected_joints=[
            {'type': 'revolute', 'name_hints': ['base', 'arm1']},
            {'type': 'revolute', 'name_hints': ['arm2', 'forearm']},
            {'type': 'prismatic', 'name_hints': ['z', 'vertical']},
            {'type': 'revolute', 'name_hints': ['tool', 'gripper']},
        ],
        detection_hints=['scara', 'base', 'arm', 'vertical', 'tool']
    ),
    RobotTemplate(
        name="Stewart Platform",
        pattern_type="stewart",
        num_parts_range=(8, 20),
        expected_joints=[
            {'type': 'spherical', 'name_hints': ['platform', 'top']},
            {'type': 'prismatic', 'name_hints': ['leg', 'actuator', 'strut']},
            {'type': 'spherical', 'name_hints': ['base', 'bottom']},
        ],
        detection_hints=['platform', 'base', 'leg', 'strut', 'actuator', 'stewart']
    ),
    RobotTemplate(
        name="Delta Robot",
        pattern_type="delta",
        num_parts_range=(6, 15),
        expected_joints=[
            {'type': 'revolute', 'name_hints': ['motor', 'arm']},
            {'type': 'spherical', 'name_hints': ['forearm', 'rod']},
            {'type': 'spherical', 'name_hints': ['platform', 'end']},
        ],
        detection_hints=['delta', 'arm', 'forearm', 'platform', 'motor']
    ),
]


class CADHierarchyInference:
    """
    Infer assembly hierarchy and joints from CAD geometry.
    
    Workflow:
    1. Extract geometric features from each part
    2. Detect connections between parts
    3. Match against known robot templates
    4. Infer joint types from connection geometry
    5. Apply user hints/overrides
    6. Build kinematic chain
    """
    
    # Thresholds
    PROXIMITY_THRESHOLD = 0.01  # 1cm for contact detection
    COAXIAL_THRESHOLD = 0.01   # 1cm for axis alignment
    ANGULAR_THRESHOLD = 0.05   # ~3 degrees for parallel detection
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.proximity_threshold = self.config.get('proximity_threshold', self.PROXIMITY_THRESHOLD)
        self.coaxial_threshold = self.config.get('coaxial_threshold', self.COAXIAL_THRESHOLD)
        self.user_hints: Dict = {}
        self.features_cache: Dict[str, List[GeometricFeature]] = {}
    
    def load_hints(self, hints_path: str):
        """
        Load user-defined assembly hints from JSON file.
        
        Hints file format:
        {
            "joints": [
                {
                    "name": "shoulder_joint",
                    "type": "revolute",
                    "parent": "base",
                    "child": "shoulder",
                    "axis": [0, 0, 1]
                }
            ],
            "fixed_parts": ["base_plate"],
            "end_effector": "gripper"
        }
        """
        with open(hints_path, 'r') as f:
            self.user_hints = json.load(f)
        logger.info(f"Loaded assembly hints from {hints_path}")
    
    def infer_hierarchy(
        self,
        parts: Dict[str, Any],  # part_name -> OCC shape or mesh
        base_part: Optional[str] = None
    ) -> Dict:
        """
        Infer complete assembly hierarchy from CAD parts.
        
        Args:
            parts: Dictionary of part names to geometry
            base_part: Optional root part name
            
        Returns:
            Hierarchy data with inferred joints
        """
        logger.info(f"Inferring hierarchy for {len(parts)} parts")
        
        part_names = list(parts.keys())
        
        # Step 1: Extract geometric features
        features_by_part = {}
        for name, shape in parts.items():
            features = self._extract_features(name, shape)
            features_by_part[name] = features
            self.features_cache[name] = features
        
        # Step 2: Detect connections
        connections = self._detect_connections(parts, features_by_part)
        logger.info(f"Detected {len(connections)} connections")
        
        # Step 3: Match against templates
        matched_template = self._match_template(part_names, features_by_part)
        if matched_template:
            logger.info(f"Matched template: {matched_template.name}")
        
        # Step 4: Infer joints from connections
        inferred_joints = self._infer_joints_from_connections(
            connections, features_by_part, matched_template
        )
        
        # Step 5: Apply user hints (override inferred)
        final_joints = self._apply_user_hints(inferred_joints)
        
        # Step 6: Determine base part
        if base_part is None:
            base_part = self._determine_base_part(parts, final_joints)
        
        # Step 7: Build kinematic tree
        hierarchy = self._build_kinematic_tree(part_names, final_joints, base_part)
        
        return hierarchy
    
    def _extract_features(
        self,
        part_name: str,
        shape: Any
    ) -> List[GeometricFeature]:
        """Extract geometric features from a CAD shape."""
        features = []
        
        if not PYTHONOCC_AVAILABLE:
            # Fallback: basic bounding box analysis
            return self._extract_features_fallback(part_name, shape)
        
        try:
            # Analyze faces for feature detection
            face_explorer = TopExp_Explorer(shape, TopAbs_FACE)
            
            while face_explorer.More():
                face = topods_Face(face_explorer.Current())
                surface = BRepAdaptor_Surface(face)
                surface_type = surface.GetType()
                
                if surface_type == GeomAbs_Cylinder:
                    # Cylindrical surface - potential joint axis
                    cylinder = surface.Cylinder()
                    axis = cylinder.Axis()
                    center = axis.Location()
                    direction = axis.Direction()
                    radius = cylinder.Radius()
                    
                    feature = GeometricFeature(
                        part_name=part_name,
                        feature_type='cylinder',
                        center=[center.X(), center.Y(), center.Z()],
                        axis=[direction.X(), direction.Y(), direction.Z()],
                        radius=radius,
                    )
                    
                    # Determine role based on radius
                    if radius < 0.01:  # Small hole
                        feature.likely_role = 'screw_hole'
                    elif radius < 0.05:
                        feature.likely_role = 'bearing_or_shaft'
                    else:
                        feature.likely_role = 'large_cylinder'
                    
                    features.append(feature)
                
                elif surface_type == GeomAbs_Plane:
                    # Planar surface - potential mounting face
                    plane = surface.Plane()
                    location = plane.Location()
                    normal = plane.Axis().Direction()
                    
                    # Calculate face area
                    props = GProp_GProps()
                    brepgprop_VolumeProperties(face, props)
                    area = abs(props.Mass())
                    
                    if area > 0.001:  # Significant surface
                        feature = GeometricFeature(
                            part_name=part_name,
                            feature_type='plane',
                            center=[location.X(), location.Y(), location.Z()],
                            normal=[normal.X(), normal.Y(), normal.Z()],
                            area=area,
                            likely_role='mounting_surface',
                        )
                        features.append(feature)
                
                elif surface_type == GeomAbs_Sphere:
                    # Spherical surface - potential ball joint
                    sphere = surface.Sphere()
                    center = sphere.Location()
                    radius = sphere.Radius()
                    
                    feature = GeometricFeature(
                        part_name=part_name,
                        feature_type='sphere',
                        center=[center.X(), center.Y(), center.Z()],
                        radius=radius,
                        likely_role='ball_joint',
                    )
                    features.append(feature)
                
                face_explorer.Next()
        
        except Exception as e:
            logger.warning(f"Feature extraction failed for {part_name}: {e}")
        
        return features
    
    def _extract_features_fallback(
        self,
        part_name: str,
        shape: Any
    ) -> List[GeometricFeature]:
        """Fallback feature extraction without OpenCASCADE."""
        # Use bounding box or mesh-based analysis
        features = []
        
        # Try to get bounding box
        try:
            if hasattr(shape, 'bounds') or hasattr(shape, 'bounding_box'):
                # Trimesh-like interface
                bounds = shape.bounds if hasattr(shape, 'bounds') else shape.bounding_box
                center = [(bounds[0][i] + bounds[1][i]) / 2 for i in range(3)]
                size = [bounds[1][i] - bounds[0][i] for i in range(3)]
                
                # Infer cylindrical features from elongated bounding boxes
                max_dim = max(size)
                min_dim = min(size)
                
                if max_dim / min_dim > 3:  # Elongated shape
                    max_idx = size.index(max_dim)
                    axis = [0, 0, 0]
                    axis[max_idx] = 1.0
                    
                    feature = GeometricFeature(
                        part_name=part_name,
                        feature_type='elongated',
                        center=center,
                        axis=axis,
                        length=max_dim,
                        likely_role='link',
                    )
                    features.append(feature)
        
        except Exception as e:
            logger.debug(f"Fallback feature extraction failed: {e}")
        
        return features
    
    def _detect_connections(
        self,
        parts: Dict[str, Any],
        features_by_part: Dict[str, List[GeometricFeature]]
    ) -> List[PartConnection]:
        """Detect connections between parts based on geometry."""
        connections = []
        part_names = list(parts.keys())
        
        for i, part_a in enumerate(part_names):
            for part_b in part_names[i+1:]:
                # Check for coaxial cylinders (revolute joint)
                coaxial = self._check_coaxial_cylinders(
                    features_by_part.get(part_a, []),
                    features_by_part.get(part_b, []),
                    part_a, part_b
                )
                if coaxial:
                    connections.append(coaxial)
                    continue
                
                # Check for coincident spheres (spherical joint)
                spherical = self._check_coincident_spheres(
                    features_by_part.get(part_a, []),
                    features_by_part.get(part_b, []),
                    part_a, part_b
                )
                if spherical:
                    connections.append(spherical)
                    continue
                
                # Check for parallel planes (prismatic or planar)
                planar = self._check_parallel_planes(
                    features_by_part.get(part_a, []),
                    features_by_part.get(part_b, []),
                    part_a, part_b
                )
                if planar:
                    connections.append(planar)
        
        return connections
    
    def _check_coaxial_cylinders(
        self,
        features_a: List[GeometricFeature],
        features_b: List[GeometricFeature],
        part_a: str,
        part_b: str
    ) -> Optional[PartConnection]:
        """Check for coaxial cylindrical features between parts."""
        cylinders_a = [f for f in features_a if f.feature_type == 'cylinder']
        cylinders_b = [f for f in features_b if f.feature_type == 'cylinder']
        
        for cyl_a in cylinders_a:
            for cyl_b in cylinders_b:
                # Check axis alignment
                axis_a = np.array(cyl_a.axis)
                axis_b = np.array(cyl_b.axis)
                
                dot = abs(np.dot(axis_a, axis_b))
                if dot < 1.0 - self.ANGULAR_THRESHOLD:
                    continue  # Not parallel
                
                # Check if axes are coaxial (same line)
                center_a = np.array(cyl_a.center)
                center_b = np.array(cyl_b.center)
                diff = center_b - center_a
                
                # Project diff onto axis and perpendicular
                along_axis = np.dot(diff, axis_a) * axis_a
                perpendicular = diff - along_axis
                
                if np.linalg.norm(perpendicular) < self.coaxial_threshold:
                    # Coaxial cylinders found!
                    contact_point = ((center_a + center_b) / 2).tolist()
                    
                    return PartConnection(
                        part_a=part_a,
                        part_b=part_b,
                        connection_type='coaxial',
                        contact_point=contact_point,
                        shared_axis=cyl_a.axis,
                        confidence=0.9 if dot > 0.99 else 0.7,
                    )
        
        return None
    
    def _check_coincident_spheres(
        self,
        features_a: List[GeometricFeature],
        features_b: List[GeometricFeature],
        part_a: str,
        part_b: str
    ) -> Optional[PartConnection]:
        """Check for coincident spherical features."""
        spheres_a = [f for f in features_a if f.feature_type == 'sphere']
        spheres_b = [f for f in features_b if f.feature_type == 'sphere']
        
        for sph_a in spheres_a:
            for sph_b in spheres_b:
                center_a = np.array(sph_a.center)
                center_b = np.array(sph_b.center)
                
                distance = np.linalg.norm(center_b - center_a)
                
                if distance < self.proximity_threshold:
                    return PartConnection(
                        part_a=part_a,
                        part_b=part_b,
                        connection_type='concentric',
                        contact_point=center_a.tolist(),
                        confidence=0.85,
                    )
        
        return None
    
    def _check_parallel_planes(
        self,
        features_a: List[GeometricFeature],
        features_b: List[GeometricFeature],
        part_a: str,
        part_b: str
    ) -> Optional[PartConnection]:
        """Check for parallel/contacting planar surfaces."""
        planes_a = [f for f in features_a if f.feature_type == 'plane']
        planes_b = [f for f in features_b if f.feature_type == 'plane']
        
        for plane_a in planes_a:
            for plane_b in planes_b:
                normal_a = np.array(plane_a.normal)
                normal_b = np.array(plane_b.normal)
                
                # Check if normals are parallel (same or opposite direction)
                dot = abs(np.dot(normal_a, normal_b))
                if dot < 1.0 - self.ANGULAR_THRESHOLD:
                    continue
                
                # Check if planes are close (potential contact)
                center_a = np.array(plane_a.center)
                center_b = np.array(plane_b.center)
                
                # Distance along normal
                diff = center_b - center_a
                distance = abs(np.dot(diff, normal_a))
                
                if distance < self.proximity_threshold:
                    return PartConnection(
                        part_a=part_a,
                        part_b=part_b,
                        connection_type='mate',
                        contact_point=((center_a + center_b) / 2).tolist(),
                        contact_normal=normal_a.tolist(),
                        confidence=0.6,
                    )
        
        return None
    
    def _match_template(
        self,
        part_names: List[str],
        features_by_part: Dict[str, List[GeometricFeature]]
    ) -> Optional[RobotTemplate]:
        """Match parts against known robot templates."""
        all_features = []
        for features in features_by_part.values():
            all_features.extend(features)
        
        best_match = None
        best_score = 0.0
        
        for template in ROBOT_TEMPLATES:
            score = template.matches(part_names, all_features)
            if score > best_score and score > 0.3:
                best_match = template
                best_score = score
        
        return best_match
    
    def _infer_joints_from_connections(
        self,
        connections: List[PartConnection],
        features_by_part: Dict[str, List[GeometricFeature]],
        template: Optional[RobotTemplate]
    ) -> List[InferredJoint]:
        """Infer joint types from detected connections."""
        joints = []
        
        for i, conn in enumerate(connections):
            joint_type = InferredJointType.FIXED
            axis = [0, 0, 1]
            evidence = []
            
            if conn.connection_type == 'coaxial':
                joint_type = InferredJointType.REVOLUTE
                axis = conn.shared_axis or [0, 0, 1]
                evidence.append("Coaxial cylindrical surfaces detected")
            
            elif conn.connection_type == 'concentric':
                joint_type = InferredJointType.SPHERICAL
                evidence.append("Concentric spherical surfaces detected")
            
            elif conn.connection_type == 'mate':
                # Could be fixed or prismatic
                # Check if template suggests prismatic
                if template and template.pattern_type in ['scara', 'stewart']:
                    joint_type = InferredJointType.PRISMATIC
                    axis = conn.contact_normal or [0, 0, 1]
                    evidence.append("Mating surfaces with prismatic template")
                else:
                    joint_type = InferredJointType.FIXED
                    evidence.append("Mating surfaces - assumed fixed")
            
            joint = InferredJoint(
                name=f"joint_{i}_{conn.part_a}_{conn.part_b}",
                joint_type=joint_type,
                parent_part=conn.part_a,
                child_part=conn.part_b,
                origin=conn.contact_point,
                axis=axis,
                confidence=conn.confidence,
                evidence=evidence,
            )
            joints.append(joint)
        
        return joints
    
    def _apply_user_hints(
        self,
        inferred_joints: List[InferredJoint]
    ) -> List[InferredJoint]:
        """Apply user-defined hints to override or add joints."""
        final_joints = []
        inferred_by_parts = {}
        
        # Index inferred joints by part pairs
        for joint in inferred_joints:
            key = (joint.parent_part, joint.child_part)
            inferred_by_parts[key] = joint
        
        # Apply user-defined joints
        for hint in self.user_hints.get('joints', []):
            parent = hint.get('parent', '')
            child = hint.get('child', '')
            key = (parent, child)
            
            user_joint = InferredJoint(
                name=hint.get('name', f'user_joint_{parent}_{child}'),
                joint_type=InferredJointType(hint.get('type', 'fixed')),
                parent_part=parent,
                child_part=child,
                origin=hint.get('origin', [0, 0, 0]),
                axis=hint.get('axis', [0, 0, 1]),
                lower_limit=hint.get('lower_limit'),
                upper_limit=hint.get('upper_limit'),
                confidence=1.0,
                evidence=["User-defined hint"],
                user_defined=True,
            )
            
            # Override inferred joint
            inferred_by_parts[key] = user_joint
        
        return list(inferred_by_parts.values())
    
    def _determine_base_part(
        self,
        parts: Dict[str, Any],
        joints: List[InferredJoint]
    ) -> str:
        """Determine which part should be the base (root)."""
        # Priority 1: User hint
        if 'base_part' in self.user_hints:
            return self.user_hints['base_part']
        
        if 'fixed_parts' in self.user_hints and self.user_hints['fixed_parts']:
            return self.user_hints['fixed_parts'][0]
        
        # Priority 2: Part with "base" in name
        for name in parts.keys():
            if 'base' in name.lower():
                return name
        
        # Priority 3: Part that is only a parent, never a child
        parent_count = {}
        child_count = {}
        for joint in joints:
            parent_count[joint.parent_part] = parent_count.get(joint.parent_part, 0) + 1
            child_count[joint.child_part] = child_count.get(joint.child_part, 0) + 1
        
        for name in parts.keys():
            if name in parent_count and name not in child_count:
                return name
        
        # Priority 4: First part
        return list(parts.keys())[0]
    
    def _build_kinematic_tree(
        self,
        part_names: List[str],
        joints: List[InferredJoint],
        base_part: str
    ) -> Dict:
        """Build kinematic tree from parts and joints."""
        hierarchy = {
            'name': 'inferred_robot',
            'base_link': base_part,
            'nodes': {},
            'joints': [],
        }
        
        # Create link nodes
        for name in part_names:
            hierarchy['nodes'][name] = {
                'name': name,
                'type': 'link',
            }
        
        # Add joints
        for joint in joints:
            hierarchy['joints'].append(joint.to_dict())
        
        return hierarchy


class AssemblyHintsGenerator:
    """
    Generate assembly hints template for user to fill in.
    
    Creates a JSON file with detected parts and
    placeholder joint definitions for user to complete.
    """
    
    @classmethod
    def generate_hints_template(
        cls,
        parts: Dict[str, Any],
        inferred_joints: List[InferredJoint],
        output_path: str
    ):
        """
        Generate a hints template file.
        
        Args:
            parts: Detected parts
            inferred_joints: Auto-detected joints
            output_path: Where to save the hints JSON
        """
        hints = {
            "_comment": "Assembly hints for CAD to robot conversion",
            "_instructions": [
                "Fill in or modify the joint definitions below",
                "Delete joints that don't exist",
                "Add missing joints",
                "Set 'base_part' to the fixed base link",
                "Set 'end_effector' to the tool link"
            ],
            "parts": list(parts.keys()),
            "base_part": "",
            "end_effector": "",
            "fixed_parts": [],
            "joints": [
                {
                    "name": j.name,
                    "type": j.joint_type.value,
                    "parent": j.parent_part,
                    "child": j.child_part,
                    "origin": j.origin,
                    "axis": j.axis,
                    "lower_limit": j.lower_limit or -3.14159,
                    "upper_limit": j.upper_limit or 3.14159,
                    "_confidence": j.confidence,
                    "_evidence": j.evidence,
                }
                for j in inferred_joints
            ],
        }
        
        with open(output_path, 'w') as f:
            json.dump(hints, f, indent=2)
        
        logger.info(f"Generated assembly hints template: {output_path}")


# Convenience function
def infer_robot_from_cad(
    parts: Dict[str, Any],
    hints_file: Optional[str] = None,
    base_part: Optional[str] = None
) -> Dict:
    """
    Convenience function to infer robot hierarchy from CAD parts.
    
    Args:
        parts: Dictionary of part names to geometry
        hints_file: Optional path to assembly hints JSON
        base_part: Optional base part name
        
    Returns:
        Inferred robot hierarchy
    """
    inference = CADHierarchyInference()
    
    if hints_file:
        inference.load_hints(hints_file)
    
    return inference.infer_hierarchy(parts, base_part)
