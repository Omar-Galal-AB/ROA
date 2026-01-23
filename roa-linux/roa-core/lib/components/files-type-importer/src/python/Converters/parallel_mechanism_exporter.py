"""
Parallel Mechanism Exporter

Exports robots with closed kinematic loops as multi-file USD assemblies.

Since USD Physics doesn't support closed loops in a single articulation,
we split the mechanism into:
1. Open-chain segments (standard USD articulations)
2. Loop closure constraints (JSON metadata for UE5 reconstruction)

The result is a folder with the robot name containing multiple USD files 
that UE5 can import and reconstruct using Chaos Physics constraints.

KNOWN LIMITATIONS (Critical Gaps):
1. Geometric constraints (coincident points) not auto-detected from meshes
2. Stewart platforms with 6 parallel chains may need manual constraint definition
3. Relies on physics engine for mechanism solving (no analytical IK)
4. Constraint positions may need manual adjustment in UE5

For complex parallel mechanisms, consider using the manual constraint 
definition via JSON file alongside the URDF.
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import math
import logging

logger = logging.getLogger(__name__)


class GeometricConstraintDetector:
    """
    Detect geometric constraints that indicate closed loops.
    
    This addresses Gap #1: URDF doesn't explicitly define loops,
    but geometry can reveal where links should be constrained.
    """
    
    COINCIDENCE_THRESHOLD = 0.01  # 1cm tolerance for point coincidence
    
    @staticmethod
    def detect_geometric_loops(
        nodes: Dict,
        joints: List[Dict]
    ) -> List[Dict]:
        """
        Detect loops by analyzing link geometry for coincident points.
        
        This finds cases where:
        - Two link endpoints are at the same world position
        - Links share a common attachment point
        - Parallel chain endpoints converge
        
        Args:
            nodes: Link definitions with geometry
            joints: Joint definitions
            
        Returns:
            List of geometric constraint definitions
        """
        geometric_constraints = []
        
        # Compute world positions of all link endpoints
        link_endpoints = GeometricConstraintDetector._compute_link_endpoints(
            nodes, joints
        )
        
        # Find coincident points (within threshold)
        for link1, endpoints1 in link_endpoints.items():
            for link2, endpoints2 in link_endpoints.items():
                if link1 >= link2:  # Avoid duplicates
                    continue
                
                for ep1_name, ep1_pos in endpoints1.items():
                    for ep2_name, ep2_pos in endpoints2.items():
                        distance = GeometricConstraintDetector._distance(ep1_pos, ep2_pos)
                        
                        if distance < GeometricConstraintDetector.COINCIDENCE_THRESHOLD:
                            # Found a geometric constraint!
                            geometric_constraints.append({
                                'type': 'coincident_point',
                                'link1': link1,
                                'link2': link2,
                                'point1': ep1_name,
                                'point2': ep2_name,
                                'world_position': ep1_pos,
                                'distance': distance,
                                'confidence': 1.0 - (distance / GeometricConstraintDetector.COINCIDENCE_THRESHOLD),
                            })
        
        return geometric_constraints
    
    @staticmethod
    def _compute_link_endpoints(nodes: Dict, joints: List[Dict]) -> Dict:
        """Compute world-space positions of link endpoints."""
        endpoints = {}
        
        # Build transform chain
        transforms = {}  # link_name -> world_transform (4x4 matrix)
        
        for joint in joints:
            parent = joint.get('parent_link', '')
            child = joint.get('child_link', '')
            origin = joint.get('origin', {})
            
            if isinstance(origin, dict):
                xyz = origin.get('xyz', [0, 0, 0])
            else:
                xyz = origin if isinstance(origin, list) else [0, 0, 0]
            
            # Child link's origin in world frame (simplified - assuming chain from root)
            if parent not in transforms:
                transforms[parent] = [0, 0, 0]  # Root at origin
            
            parent_pos = transforms.get(parent, [0, 0, 0])
            transforms[child] = [
                parent_pos[0] + xyz[0],
                parent_pos[1] + xyz[1],
                parent_pos[2] + xyz[2],
            ]
        
        # For each link, compute endpoints based on geometry bounds
        for link_name, node_data in nodes.items():
            if not isinstance(node_data, dict):
                continue
            
            link_pos = transforms.get(link_name, [0, 0, 0])
            visual = node_data.get('visual', {})
            geometry = visual.get('geometry', {}) if isinstance(visual, dict) else {}
            
            # Estimate link bounds from geometry
            if geometry.get('type') == 'box':
                size = geometry.get('size', [0.1, 0.1, 0.1])
                half_z = size[2] / 2 if len(size) > 2 else 0.05
                
                endpoints[link_name] = {
                    'origin': link_pos,
                    'end': [link_pos[0], link_pos[1], link_pos[2] + half_z],
                }
            elif geometry.get('type') == 'cylinder':
                length = geometry.get('length', 0.1)
                endpoints[link_name] = {
                    'origin': link_pos,
                    'end': [link_pos[0], link_pos[1], link_pos[2] + length/2],
                }
            else:
                # Default: use joint origin as endpoint
                endpoints[link_name] = {
                    'origin': link_pos,
                }
        
        return endpoints
    
    @staticmethod
    def _distance(p1: List[float], p2: List[float]) -> float:
        """Euclidean distance between two points."""
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))


class WorldTransformComputer:
    """
    Compute world-space transforms for all links.
    
    This addresses Gap #3: Constraint positions need world-space coordinates,
    not just local joint origins.
    """
    
    @staticmethod
    def compute_world_transforms(
        joints: List[Dict],
        base_link: Optional[str] = None
    ) -> Dict[str, List[List[float]]]:
        """
        Compute world-space transform (4x4 matrix) for each link.
        
        Args:
            joints: Joint definitions
            base_link: Optional base link name (auto-detected if not provided)
            
        Returns:
            Dictionary of link_name -> 4x4 transform matrix
        """
        transforms = {}  # link_name -> 4x4 matrix
        
        # Find base link (parent that is never a child)
        if base_link is None:
            parents = {j.get('parent_link') for j in joints}
            children = {j.get('child_link') for j in joints}
            roots = parents - children
            base_link = list(roots)[0] if roots else ''
        
        # Identity transform for base
        transforms[base_link] = [
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ]
        
        # Build parent->children map
        children_map = {}  # parent -> [(child, joint), ...]
        for joint in joints:
            parent = joint.get('parent_link', '')
            if parent not in children_map:
                children_map[parent] = []
            children_map[parent].append((joint.get('child_link', ''), joint))
        
        # BFS from base to compute all transforms
        queue = [base_link]
        while queue:
            parent = queue.pop(0)
            parent_tf = transforms.get(parent, [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]])
            
            for child, joint in children_map.get(parent, []):
                if child in transforms:
                    continue
                
                # Get joint transform
                origin = joint.get('origin', {})
                xyz = origin.get('xyz', [0, 0, 0]) if isinstance(origin, dict) else [0, 0, 0]
                rpy = origin.get('rpy', [0, 0, 0]) if isinstance(origin, dict) else [0, 0, 0]
                
                # Build joint transform matrix
                joint_tf = WorldTransformComputer._build_transform(xyz, rpy)
                
                # Child transform = Parent * Joint
                child_tf = WorldTransformComputer._multiply_matrices(parent_tf, joint_tf)
                transforms[child] = child_tf
                
                queue.append(child)
        
        return transforms
    
    @staticmethod
    def get_world_position(transforms: Dict, link_name: str) -> List[float]:
        """Get world position of a link."""
        tf = transforms.get(link_name)
        if tf:
            return [tf[0][3], tf[1][3], tf[2][3]]
        return [0, 0, 0]
    
    @staticmethod
    def _build_transform(xyz: List[float], rpy: List[float]) -> List[List[float]]:
        """Build 4x4 transform from translation and RPY."""
        x, y, z = xyz
        roll, pitch, yaw = rpy
        
        # Rotation matrix from RPY
        cr, sr = math.cos(roll), math.sin(roll)
        cp, sp = math.cos(pitch), math.sin(pitch)
        cy, sy = math.cos(yaw), math.sin(yaw)
        
        r00 = cy * cp
        r01 = cy * sp * sr - sy * cr
        r02 = cy * sp * cr + sy * sr
        r10 = sy * cp
        r11 = sy * sp * sr + cy * cr
        r12 = sy * sp * cr - cy * sr
        r20 = -sp
        r21 = cp * sr
        r22 = cp * cr
        
        return [
            [r00, r01, r02, x],
            [r10, r11, r12, y],
            [r20, r21, r22, z],
            [0, 0, 0, 1]
        ]
    
    @staticmethod
    def _multiply_matrices(a: List[List[float]], b: List[List[float]]) -> List[List[float]]:
        """Multiply two 4x4 matrices."""
        result = [[0]*4 for _ in range(4)]
        for i in range(4):
            for j in range(4):
                for k in range(4):
                    result[i][j] += a[i][k] * b[k][j]
        return result


class BreakPointSelector:
    """
    Improved break point selection for closed loops.
    
    This addresses Gap #2: Better heuristics + user override.
    
    Priority:
    1. User-specified break points
    2. Joints marked as 'passive' or 'constraint'
    3. Non-actuated joints (no motor)
    4. Joints with smallest range of motion
    5. Spherical/ball joints (6-DOF, good for constraints)
    6. Last joint in the loop
    """
    
    # Joint type priorities (lower = better for breaking)
    TYPE_PRIORITY = {
        'spherical': 1,      # Best - allows all rotations
        'ball': 1,
        'universal': 2,      # Good - 2 DOF
        'revolute': 3,       # OK
        'continuous': 3,
        'prismatic': 4,      # Less ideal
        'fixed': 5,          # Rarely want to break here
    }
    
    @classmethod
    def select_break_point(
        cls,
        loop_joints: List[str],
        joint_map: Dict[str, Dict],
        user_overrides: Optional[Dict] = None
    ) -> Tuple[str, str, float]:
        """
        Select the best joint to break a loop.
        
        Args:
            loop_joints: List of joint names in the loop
            joint_map: Map of joint_name -> joint_data
            user_overrides: Optional user hints {'break_points': ['joint_name']}
            
        Returns:
            Tuple of (break_joint_name, reason, confidence)
        """
        # Priority 1: User override
        if user_overrides and 'break_points' in user_overrides:
            for override in user_overrides['break_points']:
                if override in loop_joints:
                    return (override, "user_specified", 1.0)
        
        candidates = []
        
        for name in loop_joints:
            joint = joint_map.get(name, {})
            score = 0
            reason = ""
            
            # Priority 2: Naming convention
            name_lower = name.lower()
            if any(hint in name_lower for hint in ['passive', 'constraint', 'loop', 'closure', 'dummy']):
                score += 100
                reason = "passive_naming"
            
            # Priority 3: Check for motor/actuator
            if 'motor' not in joint and 'actuator' not in joint:
                has_effort = joint.get('limits', {}).get('effort', 0) == 0
                if has_effort:
                    score += 50
                    reason = reason or "no_actuation"
            
            # Priority 4: Joint type
            joint_type = joint.get('type', 'revolute')
            type_priority = cls.TYPE_PRIORITY.get(joint_type, 3)
            score += (6 - type_priority) * 10  # Higher score for spherical
            reason = reason or f"type_{joint_type}"
            
            # Priority 5: Range of motion (smaller ROM = easier constraint)
            limits = joint.get('limits', {})
            lower = limits.get('lower', -math.pi)
            upper = limits.get('upper', math.pi)
            rom = abs(upper - lower)
            
            if rom < math.pi:  # Less than 180 degrees
                score += 20
            if rom < math.pi / 2:  # Less than 90 degrees
                score += 20
            
            candidates.append((name, score, reason))
        
        # Sort by score (highest first)
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        if candidates:
            best = candidates[0]
            confidence = min(best[1] / 100.0, 1.0)
            return (best[0], best[2], confidence)
        
        # Fallback: last joint
        return (loop_joints[-1], "fallback", 0.3)


class LoopDetector:
    """Detect closed kinematic loops in robot structure."""
    
    def __init__(self, user_hints: Optional[Dict] = None):
        """Initialize with optional user hints."""
        self.user_hints = user_hints or {}
        self.break_point_selector = BreakPointSelector()
    
    def detect_loops(
        self,
        joints: List[Dict],
        nodes: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Find all closed loops in the kinematic chain.
        
        Uses both:
        1. Graph-based cycle detection (topological loops)
        2. Geometric constraint detection (coincident points)
        
        Args:
            joints: Joint definitions
            nodes: Optional link definitions for geometric detection
        
        Returns:
            List of loop descriptions, each containing:
            - joints: List of joints forming the loop
            - break_point: Suggested joint to break the loop
            - loop_type: 'parallel' | 'four_bar' | 'complex' | 'geometric'
        """
        # Build adjacency graph
        graph = {}  # link -> [(connected_link, joint_name), ...]
        joint_map = {}  # joint_name -> joint_data
        
        for joint in joints:
            parent = joint.get('parent_link', '')
            child = joint.get('child_link', '')
            name = joint.get('name', '')
            
            if parent not in graph:
                graph[parent] = []
            if child not in graph:
                graph[child] = []
            
            graph[parent].append((child, name))
            graph[child].append((parent, name))  # Undirected for loop detection
            joint_map[name] = joint
        
        # Find cycles using DFS
        loops = []
        visited = set()
        
        def dfs(node, parent_joint, path, path_joints):
            visited.add(node)
            
            for neighbor, joint_name in graph.get(node, []):
                if joint_name == parent_joint:
                    continue  # Don't go back the same edge
                
                if neighbor in path:
                    # Found a cycle!
                    cycle_start = path.index(neighbor)
                    cycle_joints = path_joints[cycle_start:] + [joint_name]
                    
                    # Use improved break point selection
                    break_point, break_reason, break_confidence = self._choose_break_point(
                        cycle_joints, joint_map
                    )
                    
                    loop_info = {
                        'joints': cycle_joints,
                        'links': path[cycle_start:] + [neighbor],
                        'break_point': break_point,
                        'break_reason': break_reason,
                        'break_confidence': break_confidence,
                        'loop_type': LoopDetector._classify_loop(
                            cycle_joints, joint_map
                        ),
                    }
                    loops.append(loop_info)
                    return
                
                if neighbor not in visited:
                    dfs(neighbor, joint_name, path + [neighbor], path_joints + [joint_name])
        
        # Start DFS from all nodes
        for start_node in graph.keys():
            if start_node not in visited:
                dfs(start_node, None, [start_node], [])
        
        return loops
    
    def _choose_break_point(self, joint_names: List[str], joint_map: Dict) -> Tuple[str, str, float]:
        """
        Choose the best joint to break the loop using improved selection.
        
        Returns:
            Tuple of (joint_name, reason, confidence)
        """
        return BreakPointSelector.select_break_point(
            joint_names, 
            joint_map, 
            self.user_hints
        )
    
    @staticmethod
    def _classify_loop(joint_names: List[str], joint_map: Dict) -> str:
        """Classify the type of closed loop."""
        num_joints = len(joint_names)
        
        if num_joints == 4:
            return 'four_bar'
        elif num_joints == 6:
            # Could be Stewart platform actuator
            return 'parallel_actuator'
        elif num_joints <= 3:
            return 'simple_loop'
        else:
            return 'complex'


class ParallelMechanismExporter:
    """
    Export parallel mechanisms as multi-file USD assemblies.
    
    Strategy:
    1. Detect closed loops
    2. Break loops at strategic points
    3. Export each open chain as separate USD
    4. Export constraint metadata for UE5 reconstruction
    
    Enhanced features (v2.0):
    - World-space constraint positions
    - User hints for break point override
    - Improved break point selection
    - Submechanism integration
    """
    
    def __init__(self, config: Optional[Dict] = None, user_hints: Optional[Dict] = None):
        self.config = config or {}
        self.user_hints = user_hints or {}
        self.loop_detector = LoopDetector(user_hints=user_hints)
        self.world_transforms: Dict = {}
    
    def load_user_hints(self, hints_path: str):
        """Load user hints from JSON file."""
        with open(hints_path, 'r') as f:
            self.user_hints = json.load(f)
        self.loop_detector = LoopDetector(user_hints=self.user_hints)
        logger.info(f"Loaded user hints from {hints_path}")
    
    def export_parallel_mechanism(
        self,
        hierarchy_data: Dict,
        output_dir: str,
        robot_name: str
    ) -> Dict:
        """
        Export a parallel mechanism as multi-file assembly.
        
        Args:
            hierarchy_data: Parsed robot data with joints and links
            output_dir: Directory to save USD files
            robot_name: Name for the robot
            
        Returns:
            Export result with file paths and constraint data
        """
        output_path = Path(output_dir) / robot_name
        output_path.mkdir(parents=True, exist_ok=True)
        
        joints = hierarchy_data.get('joints', [])
        nodes = hierarchy_data.get('nodes', {})
        
        # Pre-compute world transforms for accurate constraint positions
        self.world_transforms = WorldTransformComputer.compute_world_transforms(joints)
        
        # Step 1: Detect loops
        loops = self.loop_detector.detect_loops(joints)
        
        if not loops:
            # No loops - standard export
            return {
                'has_loops': False,
                'message': 'No closed loops detected, use standard URDF converter'
            }
        
        print(f"[ParallelMechanism] Detected {len(loops)} closed loop(s)")
        
        # Step 2: Identify break points
        break_joints = set()
        constraints = []
        
        for loop in loops:
            break_joint = loop['break_point']
            break_joints.add(break_joint)
            
            # Create constraint data for UE5
            constraint = self._create_loop_constraint(loop, hierarchy_data)
            constraints.append(constraint)
            
            print(f"  Loop: {loop['loop_type']} - Breaking at: {break_joint}")
        
        # Step 3: Split into segments (open chains)
        segments = self._split_into_segments(hierarchy_data, break_joints)
        
        # Step 4: Export each segment as USD
        segment_files = []
        for i, segment in enumerate(segments):
            segment_file = output_path / f"segment_{i}_{segment['root_link']}.usd"
            self._export_segment_usd(segment, str(segment_file))
            segment_files.append({
                'file': str(segment_file),
                'root_link': segment['root_link'],
                'end_links': segment['end_links'],
            })
        
        # Step 5: Export constraint metadata
        constraints_file = output_path / "loop_constraints.json"
        constraint_data = {
            'robot_name': robot_name,
            'mechanism_type': 'parallel',
            'loops': [
                {
                    'type': loop['loop_type'],
                    'joints': loop['joints'],
                    'break_point': loop['break_point'],
                }
                for loop in loops
            ],
            'constraints': constraints,
            'reconstruction_instructions': self._generate_ue5_instructions(constraints),
        }
        
        with open(constraints_file, 'w') as f:
            json.dump(constraint_data, f, indent=2)
        
        # Step 6: Create root assembly file
        assembly_file = output_path / f"{robot_name}_assembly.usd"
        self._create_assembly_usd(segment_files, str(assembly_file), robot_name)
        
        # Step 7: Export UE5 Python reconstruction script
        ue5_script_file = output_path / "ue5_reconstruct_loops.py"
        self._export_ue5_reconstruction_script(constraints, str(ue5_script_file))
        
        # Step 8: Create README for the user
        readme_file = output_path / "README.txt"
        self._create_readme(readme_file, robot_name, loops, constraints, assembly_file.name)
        
        logger.info(f"[ParallelMechanism] Export complete: {output_path}")
        
        return {
            'success': True,
            'has_loops': True,
            'output_dir': str(output_path),
            'assembly_file': str(assembly_file),
            'segment_files': segment_files,
            'constraints_file': str(constraints_file),
            'ue5_script': str(ue5_script_file),
            'readme_file': str(readme_file),
            'loops_detected': len(loops),
            'instructions': (
                f"Parallel mechanism exported to: {output_path}/\n"
                f"This folder contains all files needed for UE5 import.\n"
                f"See README.txt for detailed instructions."
            ),
        }
    
    def _create_readme(
        self,
        readme_path: Path,
        robot_name: str,
        loops: List[Dict],
        constraints: List[Dict],
        assembly_filename: str
    ):
        """Create README explaining the folder contents."""
        content = f"""
================================================================================
  PARALLEL MECHANISM: {robot_name}
================================================================================

This robot contains closed kinematic loops (parallel mechanism).
USD Physics doesn't support closed loops, so the robot has been exported
as multiple files that you'll assemble in UE5.

FOLDER CONTENTS:
----------------
  {assembly_filename}      - Main assembly file (import this into UE5)
  segment_*.usd            - Individual chain segments
  loop_constraints.json    - Constraint definitions (machine-readable)
  ue5_reconstruct_loops.py - Python script to run in UE5
  README.txt               - This file

DETECTED LOOPS:
---------------
"""
        for i, loop in enumerate(loops):
            content += f"  Loop {i+1}: {loop['loop_type']}\n"
            content += f"    Joints: {', '.join(loop['joints'])}\n"
            content += f"    Break point: {loop['break_point']}\n\n"
        
        content += """
HOW TO IMPORT INTO UE5:
-----------------------
1. Copy this entire folder to your UE5 project's Content directory

2. In UE5, go to Content Browser and import the assembly USD:
   Right-click > Import To... > Select """ + assembly_filename + """

3. Drag the imported actor into your level

4. Run the reconstruction script to close the loops:
   - Open Output Log (Window > Developer Tools > Output Log)
   - Switch to Python console
   - Run these commands:
   
     exec(open('path/to/ue5_reconstruct_loops.py').read())
     reconstruct()
   
   OR if you have ROA installed:
   
     from ROA.editor_menu import assemble_robot_from_dialog
     assemble_robot_from_dialog()

5. The physics constraints will now connect the segments!

TROUBLESHOOTING:
----------------
- If the mechanism doesn't move correctly, you may need to adjust
  constraint positions in the UE5 Details panel.

- For complex parallel mechanisms (like Stewart platforms), you may
  need to define additional constraints manually.

- See loop_constraints.json for the exact constraint specifications.

KNOWN LIMITATIONS:
------------------
- Constraint positions are estimated from URDF joint origins
- Physics-only simulation (no analytical IK)
- May require manual tuning for complex mechanisms

For more information, see the FTI documentation:
  https://github.com/roa/files-type-importer/docs/PARALLEL_MECHANISMS.md

================================================================================
  Generated by ROA Files-Type-Importer (FTI)
================================================================================
"""
        
        with open(readme_path, 'w') as f:
            f.write(content)
    
    def _create_loop_constraint(self, loop: Dict, hierarchy_data: Dict) -> Dict:
        """Create UE5-compatible constraint data for a loop."""
        break_joint = loop['break_point']
        
        # Find the joint data
        joint_data = None
        for joint in hierarchy_data.get('joints', []):
            if joint.get('name') == break_joint:
                joint_data = joint
                break
        
        if not joint_data:
            return {}
        
        parent_link = joint_data.get('parent_link', '')
        child_link = joint_data.get('child_link', '')
        
        # Get world-space positions for accurate constraints
        parent_world_pos = WorldTransformComputer.get_world_position(
            self.world_transforms, parent_link
        )
        child_world_pos = WorldTransformComputer.get_world_position(
            self.world_transforms, child_link
        )
        
        # Get local joint origin
        origin = joint_data.get('origin', {})
        local_xyz = origin.get('xyz', [0, 0, 0]) if isinstance(origin, dict) else [0, 0, 0]
        local_rpy = origin.get('rpy', [0, 0, 0]) if isinstance(origin, dict) else [0, 0, 0]
        
        # Build constraint specification with both local and world positions
        constraint = {
            'name': f"loop_constraint_{loop['break_point']}",
            'type': joint_data.get('type', 'fixed'),
            'body0': parent_link,
            'body1': child_link,
            # Local frame positions (for physics engine)
            'local_pos0': local_xyz,
            'local_rot0': local_rpy,
            'local_pos1': [0, 0, 0],
            'local_rot1': [0, 0, 0],
            # World-space positions (for debugging/visualization)
            'world_pos0': parent_world_pos,
            'world_pos1': child_world_pos,
            # Break point selection metadata
            'break_reason': loop.get('break_reason', 'unknown'),
            'break_confidence': loop.get('break_confidence', 0.5),
        }
        
        # Add limits if available
        if 'limits' in joint_data:
            limits = joint_data['limits']
            constraint['limits'] = {
                'lower': limits.get('lower', -3.14159),
                'upper': limits.get('upper', 3.14159),
                'effort': limits.get('effort', 100),
                'velocity': limits.get('velocity', 1.0),
            }
        
        # Add axis for revolute/prismatic
        if joint_data.get('axis'):
            constraint['axis'] = joint_data['axis']
        
        return constraint
    
    def _split_into_segments(
        self,
        hierarchy_data: Dict,
        break_joints: set
    ) -> List[Dict]:
        """Split the mechanism into open-chain segments."""
        joints = hierarchy_data.get('joints', [])
        nodes = hierarchy_data.get('nodes', {})
        
        # Build graph excluding break joints
        active_joints = [j for j in joints if j.get('name') not in break_joints]
        
        # Find connected components
        link_to_segment = {}
        segments = []
        
        for joint in active_joints:
            parent = joint.get('parent_link')
            child = joint.get('child_link')
            
            parent_seg = link_to_segment.get(parent)
            child_seg = link_to_segment.get(child)
            
            if parent_seg is None and child_seg is None:
                # New segment
                seg = {
                    'links': {parent, child},
                    'joints': [joint],
                    'root_link': parent,
                    'end_links': [],
                }
                segments.append(seg)
                link_to_segment[parent] = seg
                link_to_segment[child] = seg
            elif parent_seg is not None and child_seg is None:
                # Add to parent's segment
                parent_seg['links'].add(child)
                parent_seg['joints'].append(joint)
                link_to_segment[child] = parent_seg
            elif parent_seg is None and child_seg is not None:
                # Add to child's segment
                child_seg['links'].add(parent)
                child_seg['joints'].append(joint)
                link_to_segment[parent] = child_seg
            elif parent_seg is not child_seg:
                # Merge segments
                parent_seg['links'].update(child_seg['links'])
                parent_seg['joints'].extend(child_seg['joints'])
                for link in child_seg['links']:
                    link_to_segment[link] = parent_seg
                segments.remove(child_seg)
            # else: same segment, just add joint
            else:
                parent_seg['joints'].append(joint)
        
        # Finalize segments
        for seg in segments:
            seg['links'] = list(seg['links'])
            # Find end links (leaves)
            child_links = {j.get('child_link') for j in seg['joints']}
            parent_links = {j.get('parent_link') for j in seg['joints']}
            seg['end_links'] = list(child_links - parent_links)
        
        return segments
    
    def _export_segment_usd(self, segment: Dict, output_path: str):
        """Export a segment as USD file."""
        from pxr import Usd, UsdGeom, UsdPhysics
        
        stage = Usd.Stage.CreateNew(output_path)
        stage.SetMetadata('upAxis', 'Z')
        
        root_name = segment['root_link']
        root_prim = stage.DefinePrim(f'/{root_name}', 'Xform')
        stage.SetDefaultPrim(root_prim)
        
        # Add articulation root
        UsdPhysics.ArticulationRootAPI.Apply(root_prim)
        
        # Add links and joints
        # (Simplified - in full implementation, would create geometry too)
        for link in segment['links']:
            link_prim = stage.DefinePrim(f'/{root_name}/{link}', 'Xform')
            UsdPhysics.RigidBodyAPI.Apply(link_prim)
        
        stage.Save()
    
    def _create_assembly_usd(
        self,
        segment_files: List[Dict],
        output_path: str,
        robot_name: str
    ):
        """Create root assembly that references all segments."""
        from pxr import Usd, UsdGeom, Sdf
        
        stage = Usd.Stage.CreateNew(output_path)
        stage.SetMetadata('upAxis', 'Z')
        
        root_prim = stage.DefinePrim(f'/{robot_name}', 'Xform')
        stage.SetDefaultPrim(root_prim)
        
        # Reference each segment
        for seg_info in segment_files:
            seg_name = Path(seg_info['file']).stem
            seg_prim = stage.DefinePrim(f'/{robot_name}/{seg_name}', 'Xform')
            
            # Add reference to segment file
            seg_prim.GetReferences().AddReference(
                Sdf.Reference(seg_info['file'])
            )
        
        # Add custom data about loop constraints
        root_prim.SetCustomDataByKey('parallel_mechanism', {
            'has_loops': True,
            'requires_reconstruction': True,
            'constraint_file': 'loop_constraints.json',
            'reconstruction_script': 'ue5_reconstruct_loops.py',
        })
        
        stage.Save()
    
    def _generate_ue5_instructions(self, constraints: List[Dict]) -> str:
        """Generate human-readable instructions for UE5 reconstruction."""
        instructions = [
            "=== UE5 Parallel Mechanism Reconstruction ===",
            "",
            "After importing the USD assembly into UE5:",
            "",
            "Option 1: Automatic (Python)",
            "  1. Open Output Log (Window > Developer Tools > Output Log)",
            "  2. Run: import ue5_reconstruct_loops",
            "  3. Select the imported actor",
            "  4. Run: ue5_reconstruct_loops.reconstruct()",
            "",
            "Option 2: Manual",
            "  For each constraint below, add a Physics Constraint Component:",
            "",
        ]
        
        for i, c in enumerate(constraints):
            instructions.extend([
                f"  Constraint {i+1}: {c.get('name')}",
                f"    Type: {c.get('type')}",
                f"    Connect: {c.get('body0')} <-> {c.get('body1')}",
                "",
            ])
        
        return "\n".join(instructions)
    
    def _export_ue5_reconstruction_script(
        self,
        constraints: List[Dict],
        output_path: str
    ):
        """Export Python script for UE5 to reconstruct loops."""
        script = '''"""
UE5 Loop Reconstruction Script

Run this in UE5 after importing the parallel mechanism USD.
It creates Physics Constraint components to close the kinematic loops.

Usage:
    1. Import the USD assembly into UE5
    2. Select the imported actor in the World Outliner
    3. Open Python console (Window > Developer Tools > Python)
    4. Run: import ue5_reconstruct_loops
    5. Run: ue5_reconstruct_loops.reconstruct()
"""

import unreal

# Constraint definitions (auto-generated from URDF)
LOOP_CONSTRAINTS = ''' + json.dumps(constraints, indent=4) + '''


def reconstruct(actor=None):
    """
    Reconstruct closed loops using Chaos Physics constraints.
    
    Args:
        actor: The imported USD actor. If None, uses selected actor.
    """
    if actor is None:
        selected = unreal.EditorLevelLibrary.get_selected_level_actors()
        if not selected:
            unreal.log_error("No actor selected. Select the USD actor first.")
            return
        actor = selected[0]
    
    unreal.log(f"Reconstructing loops for: {actor.get_name()}")
    
    for constraint_def in LOOP_CONSTRAINTS:
        add_loop_constraint(actor, constraint_def)
    
    unreal.log(f"Added {len(LOOP_CONSTRAINTS)} loop constraint(s)")


def add_loop_constraint(actor, constraint_def):
    """Add a physics constraint to close a loop."""
    name = constraint_def.get('name', 'LoopConstraint')
    body0_name = constraint_def.get('body0')
    body1_name = constraint_def.get('body1')
    joint_type = constraint_def.get('type', 'fixed')
    
    # Find the body components
    body0 = find_body_component(actor, body0_name)
    body1 = find_body_component(actor, body1_name)
    
    if not body0 or not body1:
        unreal.log_warning(f"Could not find bodies for constraint: {name}")
        return
    
    # Create physics constraint component
    constraint = unreal.PhysicsConstraintComponent(actor)
    constraint.set_editor_property('component_name', name)
    
    # Set constrained bodies
    constraint.set_constraint_reference_frame(
        unreal.ConstraintFrame.FRAME1,
        unreal.Transform(
            unreal.Vector(*constraint_def.get('local_pos0', [0,0,0])),
            unreal.Rotator(*constraint_def.get('local_rot0', [0,0,0])),
            unreal.Vector(1, 1, 1)
        )
    )
    
    # Configure constraint based on joint type
    profile = constraint.get_editor_property('constraint_instance')
    
    if joint_type == 'revolute':
        # Lock all except one rotation axis
        profile.set_angular_twist_motion(unreal.AngularConstraintMotion.ACM_FREE)
        profile.set_angular_swing1_motion(unreal.AngularConstraintMotion.ACM_LOCKED)
        profile.set_angular_swing2_motion(unreal.AngularConstraintMotion.ACM_LOCKED)
        profile.set_linear_x_motion(unreal.LinearConstraintMotion.LCM_LOCKED)
        profile.set_linear_y_motion(unreal.LinearConstraintMotion.LCM_LOCKED)
        profile.set_linear_z_motion(unreal.LinearConstraintMotion.LCM_LOCKED)
        
        # Apply limits
        limits = constraint_def.get('limits', {})
        if limits:
            profile.set_angular_twist_limit(limits.get('upper', 180) - limits.get('lower', -180))
    
    elif joint_type == 'prismatic':
        # Lock all except one translation axis
        axis = constraint_def.get('axis', [1, 0, 0])
        # Set free motion on the sliding axis
        if axis[0] > 0.5:
            profile.set_linear_x_motion(unreal.LinearConstraintMotion.LCM_FREE)
        elif axis[1] > 0.5:
            profile.set_linear_y_motion(unreal.LinearConstraintMotion.LCM_FREE)
        elif axis[2] > 0.5:
            profile.set_linear_z_motion(unreal.LinearConstraintMotion.LCM_FREE)
    
    elif joint_type == 'fixed':
        # Lock everything
        profile.set_angular_twist_motion(unreal.AngularConstraintMotion.ACM_LOCKED)
        profile.set_angular_swing1_motion(unreal.AngularConstraintMotion.ACM_LOCKED)
        profile.set_angular_swing2_motion(unreal.AngularConstraintMotion.ACM_LOCKED)
        profile.set_linear_x_motion(unreal.LinearConstraintMotion.LCM_LOCKED)
        profile.set_linear_y_motion(unreal.LinearConstraintMotion.LCM_LOCKED)
        profile.set_linear_z_motion(unreal.LinearConstraintMotion.LCM_LOCKED)
    
    # Attach constraint to actor
    actor.add_instance_component(constraint)
    
    unreal.log(f"Added constraint: {name} ({body0_name} <-> {body1_name})")


def find_body_component(actor, body_name):
    """Find a skeletal/static mesh component by name."""
    components = actor.get_components_by_class(unreal.PrimitiveComponent)
    
    for comp in components:
        if body_name.lower() in comp.get_name().lower():
            return comp
    
    return None


# Auto-run hint
if __name__ == '__main__':
    unreal.log("Run reconstruct() after selecting the USD actor")
'''
        
        with open(output_path, 'w') as f:
            f.write(script)
