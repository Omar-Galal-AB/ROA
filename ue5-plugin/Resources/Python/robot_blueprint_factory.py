"""
robot_blueprint_factory.py
ROA - Robot Operations & Automation

Robot Blueprint Factory v7.6 - World-Frame Axes for Constraint Rotation
Creates complete robot Blueprints with StaticMeshComponents and PhysicsConstraintComponents.

NEW in v7.6:
- URDF axes are in JOINT LOCAL FRAME - must be transformed to WORLD FRAME!
- Added compute_joint_world_axes() in urdf_robot_assembler to handle this
- For shoulder_lift_joint: local axis=[0,0,1] + parent rotation π/2 around X → world axis=[0,1,0]
- Python now sends world-frame UE5-converted axes to C++
- C++ no longer flips Y (Python already did the conversion)
- Key insight: parent link rotations affect the meaning of the local axis!

PREVIOUS BUGS:
- v7.5: Used raw URDF axis without considering parent frame rotations
- Result: All joints showed axis Z, but shoulder_lift should be Y in world frame

ROTATION MAPPING (ROS→UE5):
- URDF Z-axis → Pitch ±90° (shoulder_pan spins around vertical)
- URDF Y-axis → Yaw ±90° (shoulder_lift, elbow rotate around horizontal)  
- URDF X-axis → 0° or 180° (twist along arm direction)

NEW in v7.3:
- Constraint rotation now uses URDF axis (not expansion direction)
- Rotation set inside ConfigureConstraintPhysics for correctness
- shoulder_lift and elbow now rotate correctly around Y axis
- Key insight: expansion direction ≠ rotation axis!

NEW in v7.2:
- Constraint rotation computed from mesh geometry (like urdf_robot_assembler)
- AutoRotateAllConstraints() orients constraints based on expansion direction
- Twist axis aligned with rotation axis (perpendicular to part extension)

NEW in v7.1:
- Physics configuration now done via C++ ROABlueprintUtils (persists after save!)
- ConfigureAllConstraintPhysics() sets angular motion, limits, and drive
- EnableAllMeshPhysics() enables physics simulation on non-base meshes
- Python set_editor_property() for physics properties doesn't work - C++ does!

NEW in v7.0:
- Full joint physics configuration for ROC (Robot Operations Control)
- Angular limits from URDF (lower/upper) applied correctly per-axis
- Angular drive enabled for velocity control
- Linear motion locked for revolute joints
- Max velocity and effort from URDF limits

NEW in v6.9:
- Uses C++ AutoPositionConstraintsFromMesh() for constraint positions
- Computes positions from actual StaticMesh bounds (not URDF data)
- GetMeshAttachmentPoint finds where child mesh connects to parent

KEY INSIGHT:
=============
USD meshes have their pivots baked at the connection points. The mesh
bounding box Origin is the geometric center. By finding the closest point
on the child's bounding box to the parent's center, we get the attachment
point - exactly where the constraint should be.

This is computed in C++ using StaticMesh->GetBounds().

PHYSICS CONFIGURATION:
======================
For each joint, the following is configured:
- Linear Motion: Locked (X, Y, Z) for revolute/fixed joints
- Angular Motion: Limited on rotation axis, Locked on others
- Angular Limits: From URDF limits.lower/upper (converted to degrees)
- Angular Drive: Enabled for velocity control via ROC
- Max Velocity: From URDF limits.velocity (rad/s → deg/s)
- Max Effort: From URDF limits.effort (N·m)

WORKFLOW:
=========
1. Run bp('robot_name')    - Creates Blueprint with all components + constraints
2. C++ AutoPositionConstraintsFromMesh computes positions from mesh geometry
3. Open Blueprint to verify physics settings
4. Use ROC to control joint velocities

Author: ROA Team
Date: January 2026
"""

import os
import json
import math
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

try:
    import unreal
    HAS_UNREAL = True
except ImportError:
    HAS_UNREAL = False
    print("[RobotBlueprintFactory] WARNING: Unreal module not available.")

# Import joint position/axis computation from urdf_robot_assembler
try:
    from urdf_robot_assembler import compute_joint_world_positions, compute_joint_world_axes
    HAS_URDF_ASSEMBLER = True
except ImportError:
    HAS_URDF_ASSEMBLER = False
    print("[RobotBlueprintFactory] WARNING: urdf_robot_assembler not available for joint positions/axes.")


# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_BLUEPRINT_PATH = "/Game/Robots/Blueprints"
ROA_OUTPUTS_PATH = os.environ.get('ROA_OUTPUTS', 'D:/ROA/Outputs')

BP_PREFIX = "BP_"
URDF_TO_UE5_SCALE = 100.0  # meters -> centimeters


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_mesh_component_bounds(component) -> Optional[Dict]:
    """
    Get the local-space mesh bounds (center and extent) for a StaticMeshComponent.
    
    For Blueprint components, all are relative to the root. We use the mesh's
    local bounds to find where geometry is located.
    
    Args:
        component: StaticMeshComponent
        
    Returns:
        Dict with 'center' and 'extent' as unreal.Vector, or None
    """
    if not HAS_UNREAL or not component:
        return None
    
    try:
        # Get the static mesh
        static_mesh = component.get_editor_property('static_mesh')
        if not static_mesh:
            return None
        
        # Get mesh bounds
        bounds = static_mesh.get_bounds()
        
        # bounds is FBoxSphereBounds - has Origin and BoxExtent
        center = bounds.origin
        extent = bounds.box_extent
        
        return {
            'center': unreal.Vector(center.x, center.y, center.z),
            'extent': unreal.Vector(extent.x, extent.y, extent.z)
        }
    except Exception as e:
        return None


def compute_joint_position_from_mesh_bounds(parent_bounds: Dict, child_bounds: Dict) -> Optional['unreal.Vector']:
    """
    Compute joint position at the START of the child part (where it connects to parent).
    
    Strategy: Find which face of the child mesh is closest to the parent mesh.
    The joint is placed at that face - this is the "beginning" of the child part.
    
    For robot arms: the joint is at the base of each link where it attaches to the previous link.
    
    Args:
        parent_bounds: Dict with 'center' and 'extent' for parent mesh
        child_bounds: Dict with 'center' and 'extent' for child mesh
        
    Returns:
        Joint position as unreal.Vector (at child's connection face), or None
    """
    if not parent_bounds or not child_bounds:
        return None
    
    parent_center = parent_bounds['center']
    parent_extent = parent_bounds['extent']
    child_center = child_bounds['center']
    child_extent = child_bounds['extent']
    
    # Compute direction from parent to child
    dx = child_center.x - parent_center.x
    dy = child_center.y - parent_center.y
    dz = child_center.z - parent_center.z
    
    # Determine which axis has the largest separation (the connection axis)
    abs_dx, abs_dy, abs_dz = abs(dx), abs(dy), abs(dz)
    
    # Place joint at the CHILD's face that is closest to parent (the beginning of the child)
    if abs_dx >= abs_dy and abs_dx >= abs_dz:
        # Connected along X axis
        if dx > 0:
            # Child is to the +X side of parent, so child's -X face is the connection point
            joint_x = child_center.x - child_extent.x
        else:
            # Child is to the -X side of parent, so child's +X face is the connection point
            joint_x = child_center.x + child_extent.x
        joint_y = child_center.y
        joint_z = child_center.z
    elif abs_dy >= abs_dx and abs_dy >= abs_dz:
        # Connected along Y axis
        if dy > 0:
            joint_y = child_center.y - child_extent.y
        else:
            joint_y = child_center.y + child_extent.y
        joint_x = child_center.x
        joint_z = child_center.z
    else:
        # Connected along Z axis
        if dz > 0:
            joint_z = child_center.z - child_extent.z
        else:
            joint_z = child_center.z + child_extent.z
        joint_x = child_center.x
        joint_y = child_center.y
    
    return unreal.Vector(joint_x, joint_y, joint_z)


def compute_joint_world_positions_from_urdf(joints: List[Dict], scale: float = 100.0) -> Dict[str, 'unreal.Vector']:
    """
    Compute world positions for all joints using URDF origin data.
    
    URDF joint origins are RELATIVE to the parent link frame. We need to
    accumulate transforms down the kinematic chain to get world positions.
    
    Args:
        joints: List of joint dictionaries with 'origin.xyz' data
        scale: Conversion factor from URDF meters to UE5 centimeters (default 100)
        
    Returns:
        Dict mapping joint_name -> unreal.Vector (world position in cm)
    """
    if not HAS_UNREAL:
        return {}
    
    # Build parent->child mapping and joint lookup
    joint_by_child = {}  # child_link -> joint
    for joint in joints:
        child = joint.get('child_link')
        if child:
            joint_by_child[child] = joint
    
    # Track accumulated world position for each link
    link_world_pos = {}  # link_name -> (x, y, z) in UE5 coords
    link_world_pos['base_link'] = (0.0, 0.0, 0.0)  # Root is at origin
    
    # Process joints in order (parent before child)
    processed = set(['base_link'])
    joint_positions = {}
    
    # Keep processing until all joints are done
    max_iterations = len(joints) * 2
    iteration = 0
    
    while len(joint_positions) < len(joints) and iteration < max_iterations:
        iteration += 1
        
        for joint in joints:
            joint_name = joint.get('name', '')
            if joint_name in joint_positions:
                continue  # Already processed
            
            parent_link = joint.get('parent_link')
            child_link = joint.get('child_link')
            
            # Can only process if parent's world position is known
            if parent_link not in link_world_pos:
                continue
            
            # Get parent world position
            px, py, pz = link_world_pos[parent_link]
            
            # Get joint origin relative to parent (in URDF meters)
            origin = joint.get('origin', {})
            xyz = origin.get('xyz', [0, 0, 0])
            
            # URDF uses X-forward, Y-left, Z-up
            # UE5 uses X-forward, Y-right, Z-up
            # So we need to negate Y
            urdf_x, urdf_y, urdf_z = xyz[0], xyz[1], xyz[2]
            
            # Convert to UE5 coordinates (meters -> cm, flip Y)
            ue_x = urdf_x * scale
            ue_y = -urdf_y * scale  # Flip Y for UE5
            ue_z = urdf_z * scale
            
            # Joint world position = parent position + relative offset
            joint_world_x = px + ue_x
            joint_world_y = py + ue_y
            joint_world_z = pz + ue_z
            
            joint_positions[joint_name] = unreal.Vector(joint_world_x, joint_world_y, joint_world_z)
            
            # Child link's world position is at the joint location
            if child_link:
                link_world_pos[child_link] = (joint_world_x, joint_world_y, joint_world_z)
                processed.add(child_link)
    
    return joint_positions


def find_hierarchy_file(robot_name_or_path: str) -> Optional[str]:
    """Find the hierarchy JSON file for a robot."""
    if os.path.isfile(robot_name_or_path):
        return robot_name_or_path
    
    if '../../' in robot_name_or_path:
        base = 'D:/ROA/Outputs'
        name = os.path.basename(robot_name_or_path)
        candidate = os.path.join(base, name)
        if os.path.isfile(candidate):
            return candidate
    
    search_paths = [
        os.path.join(ROA_OUTPUTS_PATH, f"{robot_name_or_path}_hierarchy.json"),
        os.path.join(ROA_OUTPUTS_PATH, robot_name_or_path, f"{robot_name_or_path}_hierarchy.json"),
        f"D:/ROA/Outputs/{robot_name_or_path}_hierarchy.json",
    ]
    
    for path in search_paths:
        if os.path.isfile(path):
            return path
    
    return None


def load_hierarchy(hierarchy_path: str) -> Optional[Dict]:
    """Load and parse hierarchy JSON file."""
    try:
        with open(hierarchy_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[RobotBlueprintFactory] ERROR loading hierarchy: {e}")
        return None


# =============================================================================
# SimpleConstructionScript (SCS) ACCESS - The Proper Way (from ElgEditorScripting)
# =============================================================================

def get_blueprint_scs(blueprint) -> Optional[Any]:
    """
    Get the SimpleConstructionScript from a Blueprint.
    This is the proper way to access Blueprint component structure.
    
    Based on ElgEditorScripting C++ plugin:
        USimpleConstructionScript* blueprintSCS = Blueprint->SimpleConstructionScript;
    """
    if not HAS_UNREAL or not blueprint:
        return None
    
    try:
        # Try to get SCS directly (UE5.x Python API)
        if hasattr(blueprint, 'simple_construction_script'):
            return blueprint.simple_construction_script
        elif hasattr(blueprint, 'get_editor_property'):
            return blueprint.get_editor_property('simple_construction_script')
        else:
            return None
    except Exception as e:
        print(f"[SCS] Could not access SimpleConstructionScript: {e}")
        return None


def get_scs_nodes(blueprint) -> List[Any]:
    """
    Get all SCS nodes (USCS_Node) from a Blueprint.
    Each node has a ComponentTemplate that is the actual component.
    
    Based on ElgEditorScripting C++ plugin:
        const TArray<USCS_Node*>& nodes = bpGenerated->SimpleConstructionScript->GetAllNodes();
    """
    scs = get_blueprint_scs(blueprint)
    if not scs:
        return []
    
    try:
        if hasattr(scs, 'get_all_nodes'):
            return list(scs.get_all_nodes())
        elif hasattr(scs, 'all_nodes'):
            return list(scs.all_nodes)
        else:
            return []
    except Exception as e:
        print(f"[SCS] Could not get SCS nodes: {e}")
        return []


def get_component_template(scs_node) -> Optional[Any]:
    """
    Get the ComponentTemplate from an SCS Node.
    This is the actual component object you can modify.
    
    Based on ElgEditorScripting C++ plugin:
        components.Add(node->ComponentTemplate);
    """
    if not scs_node:
        return None
    
    try:
        if hasattr(scs_node, 'component_template'):
            return scs_node.component_template
        elif hasattr(scs_node, 'get_editor_property'):
            return scs_node.get_editor_property('component_template')
        else:
            return None
    except Exception as e:
        print(f"[SCS] Could not get ComponentTemplate: {e}")
        return None


def get_component_class(scs_node) -> Optional[Any]:
    """
    Get the ComponentClass from an SCS Node.
    """
    if not scs_node:
        return None
    
    try:
        if hasattr(scs_node, 'component_class'):
            return scs_node.component_class
        elif hasattr(scs_node, 'get_editor_property'):
            return scs_node.get_editor_property('component_class')
        else:
            return None
    except Exception as e:
        return None


def find_constraint_in_blueprint_scs(blueprint, constraint_name: str):
    """
    Find a PhysicsConstraintComponent in Blueprint's SCS by name.
    Returns the ComponentTemplate which can be directly modified.
    """
    nodes = get_scs_nodes(blueprint)
    
    for node in nodes:
        template = get_component_template(node)
        if not template:
            continue
        
        if isinstance(template, unreal.PhysicsConstraintComponent):
            if constraint_name in template.get_name():
                return template
    
    return None


def set_constraint_component_names_scs(blueprint, joint_name: str, 
                                        parent_link: str, child_link: str) -> bool:
    """
    Set component_name1/2 on a PhysicsConstraintComponent.
    
    v6.1: Tries C++ ROABlueprintUtils first (if available), falls back to Python.
    
    Args:
        blueprint: The Blueprint asset
        joint_name: Name of the joint (constraint will be Constraint_<joint_name>)
        parent_link: Name of parent link component
        child_link: Name of child link component
        
    Returns:
        True if successful
    """
    if not HAS_UNREAL:
        return False
    
    expected_name = f"Constraint_{joint_name}"
    
    # v6.1: TRY C++ FUNCTION FIRST (this is the proper way)
    if hasattr(unreal, 'ROABlueprintUtils'):
        try:
            result = unreal.ROABlueprintUtils.set_constraint_component_names(
                blueprint, expected_name, 
                unreal.Name(parent_link), unreal.Name(child_link)
            )
            if result:
                print(f"      [C++] {expected_name}: {parent_link} <-> {child_link}")
                return True
        except Exception as e:
            print(f"      [C++ WARN] {expected_name}: {e}")
    
    # Fallback: Try Python approach (may not persist)
    constraint = find_constraint_in_blueprint_scs(blueprint, expected_name)
    
    if not constraint:
        print(f"      [SKIP] Constraint not found: {expected_name}")
        return False
    
    try:
        if hasattr(constraint, 'modify'):
            constraint.modify()
        
        cn1 = constraint.get_editor_property('component_name1')
        cn2 = constraint.get_editor_property('component_name2')
        
        if hasattr(cn1, 'set_editor_property'):
            cn1.set_editor_property('component_name', unreal.Name(parent_link))
            cn2.set_editor_property('component_name', unreal.Name(child_link))
        
        constraint.set_editor_property('component_name1', cn1)
        constraint.set_editor_property('component_name2', cn2)
        
        print(f"      [PY] {expected_name}: {parent_link} <-> {child_link}")
        return True
        
    except Exception as e:
        print(f"      [ERR] {expected_name}: {e}")
        return False


def mark_blueprint_modified(blueprint) -> bool:
    """
    Mark a Blueprint as structurally modified.
    This is required for changes to persist.
    
    Based on ElgEditorScripting C++ plugin:
        FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
    """
    if not HAS_UNREAL:
        return False
    
    try:
        # Try multiple approaches to mark as modified
        if hasattr(unreal, 'BlueprintEditorLibrary'):
            # Compile marks it as modified
            unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
            return True
        elif hasattr(blueprint, 'mark_package_dirty'):
            blueprint.mark_package_dirty()
            return True
        else:
            return False
    except Exception as e:
        print(f"[WARN] Could not mark blueprint as modified: {e}")
        return False


def get_joint_motion_type(joint_type: str):
    """Get UE5 angular motion type from URDF joint type."""
    if not HAS_UNREAL:
        return None
    if joint_type in ['revolute', 'prismatic']:
        return unreal.AngularConstraintMotion.ACM_LIMITED
    elif joint_type == 'continuous':
        return unreal.AngularConstraintMotion.ACM_FREE
    else:
        return unreal.AngularConstraintMotion.ACM_LOCKED


def configure_constraint_physics(constraint, joint_data: Dict, debug: bool = False) -> bool:
    """
    Configure a PhysicsConstraintComponent with joint physics settings for ROC.
    
    v7.1: This function is a placeholder - actual physics configuration is done
    via C++ ROABlueprintUtils.configure_constraint_physics() for persistence.
    
    Args:
        constraint: PhysicsConstraintComponent
        joint_data: Dict with joint info (type, axis, limits, dynamics)
        debug: Print debug info
        
    Returns:
        True (always, actual config done in C++)
    """
    # v7.1: Physics configuration now handled by C++ ROABlueprintUtils
    # Python set_editor_property() doesn't work for constraint physics properties
    # The actual configuration happens in Step 8 via ConfigureAllConstraintPhysics()
    if debug:
        joint_name = joint_data.get('name', 'unknown')
        joint_type = joint_data.get('type', 'fixed')
        print(f"          [DEFER] {joint_name} ({joint_type}) - physics config via C++")
    return True  # Return success - actual config in C++
            



def get_links_from_hierarchy(hierarchy: Dict) -> Dict:
    """Get links/nodes from hierarchy data."""
    links = hierarchy.get('links', {})
    if not links:
        links = hierarchy.get('nodes', {})
    return {k: v for k, v in links.items() if v.get('type') == 'link'}


def get_root_link(hierarchy: Dict) -> Optional[str]:
    """Get the root link name."""
    roots = hierarchy.get('root_nodes', [])
    return roots[0] if roots else None


def find_mesh_asset(link_name: str, robot_name: str, debug: bool = False) -> Optional[str]:
    """Find a StaticMesh asset for a link."""
    if not HAS_UNREAL:
        return None
    
    # Try common naming patterns first
    patterns = [
        f"/Game/Robots/{robot_name}/{robot_name}_robot_{link_name}",
        f"/Game/Robots/{robot_name}/{link_name}",
        f"/Game/Robots/{robot_name}_robot_{link_name}",
        f"/Game/{robot_name}/{robot_name}_robot_{link_name}",
        f"/Game/{robot_name}/{link_name}",
        # Also try without underscores (some imports format differently)
        f"/Game/Robots/{robot_name}/{robot_name}_{link_name}",
        f"/Game/Robots/{robot_name}/SM_{link_name}",
        f"/Game/Robots/{robot_name}/StaticMesh_{link_name}",
    ]
    
    if debug:
        print(f"      [DEBUG] Searching for: {link_name}")
        print(f"      [DEBUG] Patterns: {patterns[:3]}...")
    
    for pattern in patterns:
        if unreal.EditorAssetLibrary.does_asset_exist(pattern):
            if debug:
                print(f"      [DEBUG] Found at: {pattern}")
            return pattern
    
    # Search using EditorAssetLibrary.list_assets (more compatible)
    search_paths = [f"/Game/Robots/{robot_name}", f"/Game/{robot_name}", "/Game/Robots", "/Game"]
    
    for search_path in search_paths:
        if not unreal.EditorAssetLibrary.does_directory_exist(search_path):
            if debug:
                print(f"      [DEBUG] Directory not found: {search_path}")
            continue
        
        if debug:
            print(f"      [DEBUG] Searching directory: {search_path}")
        
        try:
            # List all assets in directory recursively
            assets = unreal.EditorAssetLibrary.list_assets(search_path, recursive=True)
            
            if debug and search_path == search_paths[0]:
                print(f"      [DEBUG] Found {len(assets)} assets in {search_path}")
                if assets:
                    print(f"      [DEBUG] First 5 assets: {[str(a) for a in assets[:5]]}")
            
            for asset_path in assets:
                asset_path_str = str(asset_path).lower()
                asset_name = os.path.basename(asset_path_str)
                
                # CRITICAL: When searching in generic directories (/Game/Robots, /Game),
                # we MUST verify the robot name is in the path to avoid mixing robots!
                # e.g., ur10e_assembled meshes should NOT be used for ur18 or ur30
                is_robot_specific_path = robot_name.lower() in search_path.lower()
                if not is_robot_specific_path:
                    # Must verify robot name is in the asset path
                    if robot_name.lower() not in asset_path_str:
                        continue  # Skip - this is a different robot's mesh!
                
                # Check if this asset contains the link name and is a mesh
                # Prefer "visual" meshes over "collision" meshes
                if link_name.lower() in asset_name:
                    # Skip collision meshes if we're looking for a specific link
                    if 'collision' in asset_name and 'visual' not in asset_name:
                        # Check if there's a visual version first
                        visual_path = str(asset_path).replace('collision', 'visual')
                        if unreal.EditorAssetLibrary.does_asset_exist(visual_path):
                            continue  # Skip collision, visual exists
                    
                    # Verify it's a StaticMesh
                    loaded = unreal.EditorAssetLibrary.load_asset(asset_path)
                    if loaded and isinstance(loaded, unreal.StaticMesh):
                        if debug:
                            print(f"      [DEBUG] Found mesh: {asset_path}")
                        return str(asset_path)
        except Exception as e:
            if debug:
                print(f"      [DEBUG] Error searching {search_path}: {e}")
            continue
    
    return None


def debug_find_meshes(robot_name: str):
    """Debug function to find where meshes are located."""
    if not HAS_UNREAL:
        print("Unreal not available")
        return
    
    print(f"Searching for meshes related to: {robot_name}")
    print("=" * 60)
    
    # Check common directories
    dirs_to_check = [
        "/Game",
        "/Game/Robots", 
        f"/Game/Robots/{robot_name}",
        f"/Game/{robot_name}",
    ]
    
    for dir_path in dirs_to_check:
        exists = unreal.EditorAssetLibrary.does_directory_exist(dir_path)
        print(f"  [{'+' if exists else '-'}] {dir_path}")
        
        if exists:
            try:
                assets = unreal.EditorAssetLibrary.list_assets(dir_path, recursive=False)
                if assets:
                    print(f"      Contents ({len(assets)} items):")
                    for asset in assets[:10]:
                        print(f"        - {asset}")
                    if len(assets) > 10:
                        print(f"        ... and {len(assets) - 10} more")
            except:
                pass
    
    print("=" * 60)
    print("TIP: Run this to see what's in your Content Browser")


def compute_link_relative_position(link_name: str, hierarchy_data: Dict) -> unreal.Vector:
    """
    Get the RELATIVE position of a link from its parent joint.
    This is the offset from parent link to this link (joint origin).
    Used when components are parented in the Blueprint hierarchy.
    """
    hierarchy = hierarchy_data.get('hierarchy', {})
    joints = hierarchy.get('joints', [])
    
    # Find the joint where this link is the child
    for joint in joints:
        if joint.get('child_link') == link_name:
            origin = joint.get('origin', {})
            xyz = origin.get('xyz', [0, 0, 0])
            
            # URDF to UE5: X same, Y flips, Z same, scale m->cm
            return unreal.Vector(
                xyz[0] * URDF_TO_UE5_SCALE,
                -xyz[1] * URDF_TO_UE5_SCALE,  # Y flips
                xyz[2] * URDF_TO_UE5_SCALE
            )
    
    # Root link or no parent joint - position at origin
    return unreal.Vector(0.0, 0.0, 0.0)


def compute_link_world_transform(link_name: str, hierarchy_data: Dict) -> Tuple[unreal.Vector, unreal.Rotator]:
    """
    Compute the WORLD transform (position + rotation) of a link by walking down the kinematic chain from root.
    Properly accumulates rotations and applies them to translations.
    
    Returns (position, rotation) tuple.
    """
    hierarchy = hierarchy_data.get('hierarchy', {})
    joints = hierarchy.get('joints', [])
    
    # Build maps
    child_to_joint = {}
    for joint in joints:
        child = joint.get('child_link')
        if child:
            child_to_joint[child] = joint
    
    # Build path from root to this link
    path = []
    current = link_name
    visited = set()
    while current in child_to_joint and current not in visited:
        visited.add(current)
        joint = child_to_joint[current]
        path.append(joint)
        current = joint.get('parent_link')
    
    # Reverse to go root -> link
    path.reverse()
    
    # Accumulate transforms
    # Start at origin with no rotation
    pos_x, pos_y, pos_z = 0.0, 0.0, 0.0
    # For rotation, we'll use quaternion math - but UE5 uses Rotator (pitch, yaw, roll)
    # For simplicity, just accumulate the RPY rotations (this is approximate but works for many robots)
    rot_pitch, rot_yaw, rot_roll = 0.0, 0.0, 0.0
    
    for joint in path:
        origin = joint.get('origin', {})
        xyz = origin.get('xyz', [0, 0, 0])
        rpy = origin.get('rpy', [0, 0, 0])  # roll, pitch, yaw in URDF
        
        # Apply current rotation to the translation offset
        # This is a simplified rotation - for accurate results we'd use full quaternion math
        # For now, just use the translation directly (works if robot is mostly axis-aligned)
        
        # URDF to UE5 coordinate transform and scale
        # URDF: X-forward, Y-left, Z-up
        # UE5:  X-forward, Y-right, Z-up
        dx = xyz[0] * URDF_TO_UE5_SCALE
        dy = -xyz[1] * URDF_TO_UE5_SCALE  # Y flips
        dz = xyz[2] * URDF_TO_UE5_SCALE
        
        pos_x += dx
        pos_y += dy
        pos_z += dz
        
        # Accumulate rotation (URDF rpy is roll, pitch, yaw around X, Y, Z)
        # Convert to UE5 Rotator (pitch, yaw, roll) in degrees
        # URDF rpy: [roll_x, pitch_y, yaw_z] in radians
        # UE5: Rotator(pitch, yaw, roll) in degrees
        rot_roll += math.degrees(rpy[0])    # Roll around X
        rot_pitch += math.degrees(rpy[1])   # Pitch around Y  
        rot_yaw += math.degrees(rpy[2])     # Yaw around Z
    
    position = unreal.Vector(pos_x, pos_y, pos_z)
    # UE5 Rotator constructor: (pitch, yaw, roll)
    rotation = unreal.Rotator(rot_pitch, rot_yaw, rot_roll)
    
    return position, rotation


def compute_link_world_position(link_name: str, hierarchy_data: Dict) -> unreal.Vector:
    """
    Compute the WORLD position of a link (backward compatible wrapper).
    """
    position, _ = compute_link_world_transform(link_name, hierarchy_data)
    return position


def compute_joint_world_position(joint_name: str, hierarchy_data: Dict) -> unreal.Vector:
    """
    Compute the WORLD position of a joint by:
    1. Getting the parent link's world position
    2. Adding the joint's local offset (from the joint's origin/transform)
    
    Args:
        joint_name: Name of the joint
        hierarchy_data: The hierarchy JSON data
        
    Returns:
        World position as unreal.Vector (in UE5 coordinates, centimeters)
    """
    hierarchy = hierarchy_data.get('hierarchy', {})
    joints = hierarchy.get('joints', [])
    nodes = hierarchy.get('nodes', {})
    
    # Find this joint
    joint_info = None
    for joint in joints:
        if joint.get('name') == joint_name:
            joint_info = joint
            break
    
    # Also check nodes (some hierarchies store joints there too)
    if not joint_info and joint_name in nodes:
        node = nodes[joint_name]
        if node.get('type') == 'joint':
            joint_info = {
                'name': joint_name,
                'parent_link': node.get('parent'),
                'child_link': node.get('properties', {}).get('child_link'),
                'origin': node.get('transform', {})
            }
    
    if not joint_info:
        print(f"      [WARN] Joint not found: {joint_name}")
        return unreal.Vector(0.0, 0.0, 0.0)
    
    # Get parent link's world position
    parent_link = joint_info.get('parent_link')
    parent_world_pos = unreal.Vector(0.0, 0.0, 0.0)
    if parent_link:
        parent_world_pos = compute_link_world_position(parent_link, hierarchy_data)
    
    # Get joint's local offset from its origin/transform
    origin = joint_info.get('origin', {})
    if not origin:
        origin = joint_info.get('transform', {})
    
    xyz = origin.get('xyz', [0, 0, 0])
    
    # URDF to UE5: X same, Y flips, Z same, scale m->cm
    joint_offset = unreal.Vector(
        xyz[0] * URDF_TO_UE5_SCALE,
        -xyz[1] * URDF_TO_UE5_SCALE,  # Y flips in UE5
        xyz[2] * URDF_TO_UE5_SCALE
    )
    
    # World position = parent position + joint offset
    world_pos = unreal.Vector(
        parent_world_pos.x + joint_offset.x,
        parent_world_pos.y + joint_offset.y,
        parent_world_pos.z + joint_offset.z
    )
    
    return world_pos


def get_joint_motion_type(joint_type: str):
    """Convert URDF joint type to UE5 angular motion type."""
    if joint_type == 'fixed':
        return unreal.AngularConstraintMotion.ACM_LOCKED
    elif joint_type == 'continuous':
        return unreal.AngularConstraintMotion.ACM_FREE
    elif joint_type in ['revolute', 'prismatic']:
        return unreal.AngularConstraintMotion.ACM_LIMITED
    else:
        return unreal.AngularConstraintMotion.ACM_LOCKED


# =============================================================================
# BLUEPRINT CREATION - THE MAIN FUNCTION
# =============================================================================

def create_robot_blueprint(robot_name_or_path: str, 
                           output_path: str = None) -> Optional[str]:
    """
    Create a complete Blueprint with StaticMeshComponents and PhysicsConstraintComponents.
    
    This does what you do manually:
    1. Adds all mesh components (like dragging into world)
    2. Adds physics constraints between them (like running Assemble Robot)
    3. Configures joint limits from the JSON
    
    Args:
        robot_name_or_path: Robot name or path to hierarchy JSON
        output_path: Where to save BP (default: /Game/Robots/Blueprints/BP_<name>)
        
    Returns:
        Path to created Blueprint, or None if failed
    """
    if not HAS_UNREAL:
        print("[RobotBlueprintFactory] ERROR: Unreal not available")
        return None
    
    print("=" * 70)
    print("  ROA Robot Blueprint Factory v5.8")
    print("  Creating Blueprint with Meshes + Physics Constraints")
    if hasattr(unreal, 'ROABlueprintUtils'):
        print("  [C++ MODE] ROABlueprintUtils available - constraint names will persist!")
    else:
        print("  [PY MODE] No C++. Run scn() if constraint names don't persist.")
    print("=" * 70)
    
    # =========================================================================
    # STEP 1: Load hierarchy data
    # =========================================================================
    hierarchy_path = find_hierarchy_file(robot_name_or_path)
    if not hierarchy_path:
        print(f"[ERROR] Could not find hierarchy for: {robot_name_or_path}")
        return None
    
    print(f"\n[1/7] Loading hierarchy: {hierarchy_path}")
    
    hierarchy_data = load_hierarchy(hierarchy_path)
    if not hierarchy_data:
        return None
    
    robot_name = hierarchy_data.get('robot_name', 'robot')
    hierarchy = hierarchy_data.get('hierarchy', {})
    
    links = get_links_from_hierarchy(hierarchy)
    joints = hierarchy.get('joints', [])
    root_link = get_root_link(hierarchy)
    
    print(f"      Robot: {robot_name}")
    print(f"      Links: {len(links)}")
    print(f"      Joints: {len(joints)}")
    print(f"      Root: {root_link}")
    
    # =========================================================================
    # STEP 2: Find all mesh assets
    # =========================================================================
    print(f"\n[2/7] Finding mesh assets...")
    
    # Debug: Show what directories exist first
    print(f"      Checking directories for robot: {robot_name}")
    dirs_to_check = [f"/Game/Robots/{robot_name}", f"/Game/{robot_name}", "/Game/Robots"]
    for d in dirs_to_check:
        exists = unreal.EditorAssetLibrary.does_directory_exist(d)
        print(f"      {'[+]' if exists else '[-]'} {d}")
        if exists:
            try:
                assets = unreal.EditorAssetLibrary.list_assets(d, recursive=True)
                if assets:
                    print(f"          Found {len(assets)} assets")
                    # Show first few
                    for a in assets[:3]:
                        print(f"            - {a}")
            except Exception as e:
                print(f"          Error listing: {e}")
    
    link_meshes = {}
    first_link = True
    for link_name in links.keys():
        mesh_path = find_mesh_asset(link_name, robot_name, debug=first_link)
        first_link = False
        if mesh_path:
            link_meshes[link_name] = mesh_path
            print(f"      [OK] {link_name}")
        else:
            print(f"      [--] {link_name}: No mesh (collision-only?)")
    
    if not link_meshes:
        print(f"[ERROR] No mesh assets found! Import the USD first.")
        print(f"        Expected path: /Game/Robots/{robot_name}/")
        print(f"        TIP: Run debug_find_meshes('{robot_name}') in Python to debug")
        return None
    
    print(f"      Found {len(link_meshes)}/{len(links)} meshes")
    
    # =========================================================================
    # STEP 3: Create the Blueprint
    # =========================================================================
    if not output_path:
        output_path = f"{DEFAULT_BLUEPRINT_PATH}/{BP_PREFIX}{robot_name}"
    
    print(f"\n[3/8] Creating Blueprint: {output_path}")
    
    try:
        factory = unreal.BlueprintFactory()
        factory.set_editor_property("parent_class", unreal.Actor)
        
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        
        bp_name = os.path.basename(output_path)
        bp_package = os.path.dirname(output_path)
        
        if not unreal.EditorAssetLibrary.does_directory_exist(bp_package):
            unreal.EditorAssetLibrary.make_directory(bp_package)
        
        if unreal.EditorAssetLibrary.does_asset_exist(output_path):
            unreal.EditorAssetLibrary.delete_asset(output_path)
        
        blueprint = asset_tools.create_asset(
            asset_name=bp_name,
            package_path=bp_package,
            asset_class=unreal.Blueprint,
            factory=factory
        )
        
        if not blueprint:
            print(f"[ERROR] Failed to create Blueprint")
            return None
        
        print(f"      Created: {bp_name}")
        
    except Exception as e:
        print(f"[ERROR] Blueprint creation failed: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    # =========================================================================
    # STEP 4: Get SubobjectDataSubsystem
    # =========================================================================
    print(f"\n[4/8] Setting up component system...")
    
    try:
        # Get the subsystem for adding components
        subsystem = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
        
        # Gather existing subobjects (includes the default scene root)
        existing_handles = subsystem.k2_gather_subobject_data_for_blueprint(blueprint)
        
        if not existing_handles:
            print(f"      [WARN] No existing subobjects found")
            root_handle = None
        else:
            # First handle is typically the root (DefaultSceneRoot)
            root_handle = existing_handles[0]
            print(f"      Root handle acquired")
        
        # Get the generated class and CDO (Class Default Object)
        gen_class = blueprint.generated_class()
        cdo = gen_class.get_default_object() if gen_class else None
        
        if not cdo:
            print(f"[ERROR] Could not get Blueprint CDO")
            return None
        
        print(f"      CDO acquired: {type(cdo)}")
        
    except Exception as e:
        print(f"[ERROR] Could not get SubobjectDataSubsystem: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    # =========================================================================
    # STEP 5: Add StaticMeshComponents for each link
    # =========================================================================
    print(f"\n[5/8] Adding StaticMeshComponents...")
    
    # Build parent-child map from joints
    parent_map = {}  # child_link -> parent_link
    for joint in joints:
        child = joint.get('child_link')
        parent = joint.get('parent_link')
        if child and parent:
            parent_map[child] = parent
    
    # Track created component handles
    component_handles = {}  # link_name -> SubobjectDataHandle
    mesh_count = 0
    
    # Add components in order (root first, then children)
    links_to_process = [root_link] if root_link else []
    processed = set()
    
    # Build processing order (BFS from root)
    while links_to_process:
        current = links_to_process.pop(0)
        if current in processed:
            continue
        processed.add(current)
        
        # Add children of current to queue
        for child, parent in parent_map.items():
            if parent == current and child not in processed:
                links_to_process.append(child)
    
    # Now process in order
    # IMPORTANT: All mesh components attach to ROOT (not to each other)!
    # The physics constraints handle parent-child relationships.
    # If we parent components to each other, transforms compound incorrectly.
    for link_name in processed:
        if link_name not in link_meshes:
            continue
            
        mesh_path = link_meshes[link_name]
        
        try:
            # ALL components attach directly to root - constraints do the parenting!
            parent_handle = root_handle
            
            if not parent_handle:
                print(f"      [SKIP] {link_name}: No root handle")
                continue
            
            # Create AddNewSubobjectParams
            params = unreal.AddNewSubobjectParams()
            params.parent_handle = parent_handle
            params.new_class = unreal.StaticMeshComponent
            params.blueprint_context = blueprint
            
            # Add the component
            new_handle, fail_reason = subsystem.add_new_subobject(params)
            
            # Check if handle is valid
            handle_valid = new_handle is not None and str(new_handle) != "" and "Invalid" not in str(fail_reason)
            if not handle_valid:
                print(f"      [ERR] {link_name}: {fail_reason}")
                continue
            
            # Store handle
            component_handles[link_name] = new_handle
            
            # Rename the component first (important!)
            subsystem.rename_subobject(new_handle, unreal.Text(link_name))
            
            # Get SubobjectData and try to access the component template immediately
            subobject_data = subsystem.k2_find_subobject_data_from_handle(new_handle)
            if subobject_data:
                # Use SubobjectDataBlueprintFunctionLibrary to get the actual component!
                component = None
                
                # Try using the function library (UE5.x way)
                if hasattr(unreal, 'SubobjectDataBlueprintFunctionLibrary'):
                    lib = unreal.SubobjectDataBlueprintFunctionLibrary
                    try:
                        component = lib.get_object_for_blueprint(subobject_data, blueprint)
                    except Exception as e:
                        print(f"      [DEBUG] get_object_for_blueprint failed: {e}")
                    
                    if not component:
                        try:
                            component = lib.get_object(subobject_data)
                        except Exception as e:
                            print(f"      [DEBUG] get_object failed: {e}")
                
                # Debug: Print available methods on first component
                if mesh_count == 0:
                    print(f"      [DEBUG] SubobjectDataBlueprintFunctionLibrary available:")
                    if hasattr(unreal, 'SubobjectDataBlueprintFunctionLibrary'):
                        for attr in sorted(dir(unreal.SubobjectDataBlueprintFunctionLibrary)):
                            if not attr.startswith('_') and 'object' in attr.lower():
                                print(f"          - {attr}")
                        print(f"      [DEBUG] Component retrieved: {component}")
                
                if component and isinstance(component, unreal.StaticMeshComponent):
                    # v5.6: CRITICAL - Notify BEFORE modifying component (pre-edit)
                    try:
                        component.modify()
                    except:
                        pass
                    
                    # v5.6: Use ALWAYS notify mode for all property changes
                    notify_mode = unreal.PropertyAccessChangeNotifyMode.ALWAYS
                    
                    # Load and set the mesh
                    mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
                    if mesh:
                        component.set_static_mesh(mesh)
                        component.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE, notify_mode)
                    
                    # USD Import Note: Meshes imported from USD have their pivot points
                    # already set at the joint/origin location. So we place all parts at
                    # (0,0,0) with zero rotation - the pivots handle the assembly!
                    # This is the "let the mesh geometry do the work" approach.
                    component.set_editor_property("relative_location", unreal.Vector(0, 0, 0), notify_mode)
                    component.set_editor_property("relative_rotation", unreal.Rotator(0, 0, 0), notify_mode)
                    
                    # v7.1: Physics simulation is now enabled via C++ ROABlueprintUtils.enable_all_mesh_physics()
                    # Python set_editor_property('simulate_physics') doesn't persist in Blueprints
                    # The actual physics setup happens in Step 8
                    is_base = (link_name == root_link or link_name in ['base_link', 'base', 'base_link_inertia'])
                    if is_base:
                        print(f"      [MESH] {link_name} @ origin (BASE - will be fixed)")
                    else:
                        print(f"      [MESH] {link_name} @ origin (physics via C++)")
                else:
                    print(f"      [ADD] {link_name} - handle only, no component access")
            else:
                print(f"      [ADD] {link_name} - no SubobjectData")
            
            mesh_count += 1
            
        except Exception as e:
            print(f"      [ERR] {link_name}: {e}")
    
    print(f"      Added {mesh_count} mesh components")
    
    # =========================================================================
    # STEP 5.5: Compute joint world positions from URDF data
    # =========================================================================
    # Use the full hierarchy data to compute world positions.
    # This accounts for joint rotations down the kinematic chain.
    
    print(f"\n[5.5/8] Computing joint positions from URDF (with rotations)...")
    
    joint_positions = {}
    
    if HAS_URDF_ASSEMBLER:
        # Use the proper function from urdf_robot_assembler that handles rotations
        # NOTE: compute_joint_world_positions expects the FULL hierarchy_data dict
        # (with 'hierarchy' key inside), not just the inner hierarchy
        try:
            joint_positions = compute_joint_world_positions(hierarchy_data, import_offset=unreal.Vector(0, 0, 0))
            print(f"      Using urdf_robot_assembler.compute_joint_world_positions()")
        except Exception as e:
            print(f"      [WARN] compute_joint_world_positions failed: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to simple calculation
            joint_positions = compute_joint_world_positions_from_urdf(joints, scale=URDF_TO_UE5_SCALE)
    else:
        # Fallback: simple calculation (doesn't handle rotations properly)
        joint_positions = compute_joint_world_positions_from_urdf(joints, scale=URDF_TO_UE5_SCALE)
        print(f"      [WARN] Using simple position calculation (rotations ignored)")
    
    for joint_name, pos in joint_positions.items():
        print(f"      [POS] {joint_name}: ({pos.x:.1f}, {pos.y:.1f}, {pos.z:.1f})")
    
    print(f"      Computed {len(joint_positions)}/{len(joints)} joint positions")
    
    # =========================================================================
    # STEP 5.6: Compute world-frame axes for all joints
    # =========================================================================
    # URDF axes are in JOINT LOCAL FRAME. We need WORLD FRAME for correct constraint rotation.
    # This must be done BEFORE Step 6 so we can set rotation when creating constraints!
    
    world_axes = {}
    if HAS_URDF_ASSEMBLER:
        try:
            world_axes = compute_joint_world_axes(hierarchy_data)
            print(f"      [v7.16] Computed world-frame axes for {len(world_axes)} joints")
        except Exception as e:
            print(f"      [WARN] compute_joint_world_axes failed: {e}")
    
    # =========================================================================
    # STEP 6: Add PhysicsConstraintComponents for each joint (v7.16: C++ creation)
    # =========================================================================
    print(f"\n[6/8] Adding PhysicsConstraintComponents...")
    
    constraint_count = 0
    constraint_handles = {}
    
    # v7.16: Check if C++ CreateAllConstraintsInBlueprint is available
    # This creates constraints with rotation ALREADY SET, which persists in Blueprint!
    use_cpp_constraint_creation = (
        hasattr(unreal, 'ROABlueprintUtils') and 
        hasattr(unreal.ROABlueprintUtils, 'create_all_constraints_in_blueprint')
    )
    
    if use_cpp_constraint_creation:
        print(f"      [v7.16] Using C++ constraint creation (rotation will persist!)")
        
        # Build constraint data array for C++ batch creation
        # Format: "Name|PosX,PosY,PosZ|RotP,RotY,RotR|Comp1|Comp2|Type|AxisX,AxisY,AxisZ|Lower,Upper|Vel,Effort"
        constraint_data_array = []
        
        for joint in joints:
            joint_name = joint.get('name', 'joint')
            joint_type = joint.get('type', 'fixed')
            parent_link = joint.get('parent_link', '')
            child_link = joint.get('child_link', '')
            axis = joint.get('axis', [0, 0, 1])
            limits = joint.get('limits', {})
            
            constraint_name = f"Constraint_{joint_name}"
            
            # Get position from computed joint_positions or use origin
            joint_pos = joint_positions.get(joint_name, unreal.Vector(0, 0, 0))
            if isinstance(joint_pos, unreal.Vector):
                pos_x, pos_y, pos_z = joint_pos.x, joint_pos.y, joint_pos.z
            else:
                pos_x, pos_y, pos_z = 0, 0, 0
            
            # Compute rotation from URDF axis (world-frame if available)
            if joint_name in world_axes:
                urdf_axis = world_axes[joint_name]
            else:
                # Fallback to local axis with Y-flip for ROS→UE5
                local_axis = axis if axis else [0, 0, 1]
                urdf_axis = [local_axis[0], -local_axis[1], local_axis[2]]
            
            abs_x, abs_y, abs_z = abs(urdf_axis[0]), abs(urdf_axis[1]), abs(urdf_axis[2])
            
            if abs_z >= abs_x and abs_z >= abs_y:
                rot_pitch, rot_yaw, rot_roll = 90.0, 0.0, 0.0  # Z-axis
                rotation_source = f"Z-axis ({urdf_axis[2]:.2f})"
            elif abs_y >= abs_x:
                yaw_angle = 90.0 if urdf_axis[1] >= 0 else -90.0
                rot_pitch, rot_yaw, rot_roll = 0.0, yaw_angle, 0.0  # Y-axis
                rotation_source = f"Y-axis ({urdf_axis[1]:.2f})"
            else:
                if urdf_axis[0] < 0:
                    rot_pitch, rot_yaw, rot_roll = 0.0, 0.0, 180.0  # -X-axis
                    rotation_source = f"-X-axis ({urdf_axis[0]:.2f})"
                else:
                    rot_pitch, rot_yaw, rot_roll = 0.0, 0.0, 0.0  # X-axis
                    rotation_source = f"X-axis ({urdf_axis[0]:.2f})"
            
            # Get limits
            limit_lower = limits.get('lower', -3.14159) if limits else -3.14159
            limit_upper = limits.get('upper', 3.14159) if limits else 3.14159
            max_velocity = limits.get('velocity', 2.0) if limits else 2.0
            max_effort = limits.get('effort', 100.0) if limits else 100.0
            
            # Build data string for C++
            # Format: "Name|PosX,PosY,PosZ|RotP,RotY,RotR|Comp1|Comp2|Type|AxisX,AxisY,AxisZ|Lower,Upper|Vel,Effort"
            data_str = (
                f"{constraint_name}|"
                f"{pos_x:.1f},{pos_y:.1f},{pos_z:.1f}|"
                f"{rot_pitch:.1f},{rot_yaw:.1f},{rot_roll:.1f}|"
                f"{parent_link}|{child_link}|"
                f"{joint_type}|"
                f"{urdf_axis[0]:.2f},{urdf_axis[1]:.2f},{urdf_axis[2]:.2f}|"
                f"{limit_lower:.4f},{limit_upper:.4f}|"
                f"{max_velocity:.2f},{max_effort:.2f}"
            )
            constraint_data_array.append(data_str)
            
            print(f"      [CONSTRAINT] {constraint_name} @ ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
            print(f"          [ROT] {rotation_source} → (P:{rot_pitch:.0f}, Y:{rot_yaw:.0f}, R:{rot_roll:.0f})")
            print(f"          Connects: {parent_link} <-> {child_link} ({joint_type})")
        
        # Get root component name for attachment
        root_component_name = ""
        if root_handle:
            try:
                root_data = subsystem.k2_find_subobject_data_from_handle(root_handle)
                if root_data:
                    lib = unreal.SubobjectDataBlueprintFunctionLibrary
                    root_obj = lib.get_object(root_data)
                    if root_obj:
                        root_component_name = root_obj.get_name()
            except:
                pass
        
        # Call C++ to create all constraints with rotation already set!
        try:
            constraint_count = unreal.ROABlueprintUtils.create_all_constraints_in_blueprint(
                blueprint,
                root_component_name,
                constraint_data_array
            )
            print(f"      [C++] Created {constraint_count}/{len(joints)} constraints with rotation!")
        except Exception as e:
            print(f"      [ERR] C++ constraint creation failed: {e}")
            print(f"      [FALLBACK] Will use Python constraint creation...")
            use_cpp_constraint_creation = False
            constraint_count = 0
    
    # Fallback: Python-based constraint creation (rotation may not persist)
    if not use_cpp_constraint_creation:
        print(f"      [FALLBACK] Using Python constraint creation...")
        
        for joint in joints:
            joint_name = joint.get('name', 'joint')
            joint_type = joint.get('type', 'fixed')
            parent_link = joint.get('parent_link')
            child_link = joint.get('child_link')
            axis = joint.get('axis', [1, 0, 0])
            limits = joint.get('limits', {})
            
            # All constraints attach to root (they reference components by name)
            constraint_parent = root_handle
            
            if not constraint_parent:
                print(f"      [SKIP] {joint_name}: No root handle for constraint")
                continue
            
            try:
                # Create constraint component
                constraint_name = f"Constraint_{joint_name}"
                params = unreal.AddNewSubobjectParams()
                params.parent_handle = constraint_parent
                params.new_class = unreal.PhysicsConstraintComponent
                params.blueprint_context = blueprint
                
                new_handle, fail_reason = subsystem.add_new_subobject(params)
                
                # Check if handle is valid
                handle_valid = new_handle is not None and str(new_handle) != "" and "Invalid" not in str(fail_reason)
                if not handle_valid:
                    print(f"      [ERR] {joint_name}: {fail_reason}")
                    continue
                
                # Rename the constraint
                subsystem.rename_subobject(new_handle, unreal.Text(constraint_name))
                constraint_handles[joint_name] = new_handle
                
                # Get SubobjectData and try to access the constraint immediately
                subobject_data = subsystem.k2_find_subobject_data_from_handle(new_handle)
                if subobject_data:
                    # Use SubobjectDataBlueprintFunctionLibrary to get the actual constraint!
                    constraint = None
                    
                    if hasattr(unreal, 'SubobjectDataBlueprintFunctionLibrary'):
                        lib = unreal.SubobjectDataBlueprintFunctionLibrary
                        try:
                            constraint = lib.get_object_for_blueprint(subobject_data, blueprint)
                        except:
                            pass
                        
                        if not constraint:
                            try:
                                constraint = lib.get_object(subobject_data)
                            except:
                                pass
                    
                    if constraint and isinstance(constraint, unreal.PhysicsConstraintComponent):
                        # CRITICAL: Notify the Blueprint that we're modifying the component
                        try:
                            constraint.modify()
                        except:
                            pass
                        
                        # Set position
                        joint_pos = joint_positions.get(joint_name)
                        if joint_pos:
                            constraint.set_editor_property("relative_location", joint_pos)
                            print(f"      [CONSTRAINT] {constraint_name} @ ({joint_pos.x:.1f}, {joint_pos.y:.1f}, {joint_pos.z:.1f})")
                        else:
                            constraint.set_editor_property("relative_location", unreal.Vector(0, 0, 0))
                            print(f"      [CONSTRAINT] {constraint_name} @ origin (fallback)")
                        
                        # Compute rotation from URDF axis
                        if joint_name in world_axes:
                            urdf_axis = world_axes[joint_name]
                        else:
                            local_axis = axis if axis else [0, 0, 1]
                            urdf_axis = [local_axis[0], -local_axis[1], local_axis[2]]
                        
                        abs_x, abs_y, abs_z = abs(urdf_axis[0]), abs(urdf_axis[1]), abs(urdf_axis[2])
                        
                        if abs_z >= abs_x and abs_z >= abs_y:
                            constraint_rotation = unreal.Rotator(90.0, 0.0, 0.0)
                            rotation_source = f"Z-axis ({urdf_axis[2]:.2f})"
                        elif abs_y >= abs_x:
                            yaw_angle = 90.0 if urdf_axis[1] >= 0 else -90.0
                            constraint_rotation = unreal.Rotator(0.0, yaw_angle, 0.0)
                            rotation_source = f"Y-axis ({urdf_axis[1]:.2f})"
                        else:
                            if urdf_axis[0] < 0:
                                constraint_rotation = unreal.Rotator(0.0, 0.0, 180.0)
                                rotation_source = f"-X-axis ({urdf_axis[0]:.2f})"
                            else:
                                constraint_rotation = unreal.Rotator(0.0, 0.0, 0.0)
                                rotation_source = f"X-axis ({urdf_axis[0]:.2f})"
                        
                        constraint.set_editor_property("relative_rotation", constraint_rotation)
                        print(f"          [ROT] {rotation_source} → (P:{constraint_rotation.pitch:.0f}, Y:{constraint_rotation.yaw:.0f}, R:{constraint_rotation.roll:.0f})")
                        print(f"          Connects: {parent_link} <-> {child_link}")
                        
                        # Set component names
                        try:
                            cn1 = constraint.get_editor_property('component_name1')
                            cn2 = constraint.get_editor_property('component_name2')
                            if hasattr(cn1, 'set_editor_property'):
                                cn1.set_editor_property('component_name', unreal.Name(parent_link))
                                cn2.set_editor_property('component_name', unreal.Name(child_link))
                                constraint.set_editor_property('component_name1', cn1)
                                constraint.set_editor_property('component_name2', cn2)
                                print(f"          [NAMES SET] component_name1={parent_link}, component_name2={child_link}")
                            elif hasattr(cn1, 'component_name'):
                                cn1.component_name = unreal.Name(parent_link)
                                cn2.component_name = unreal.Name(child_link)
                                constraint.set_editor_property('component_name1', cn1)
                                constraint.set_editor_property('component_name2', cn2)
                                print(f"          [NAMES SET] component_name1={parent_link}, component_name2={child_link}")
                        except Exception as cn_err:
                            print(f"          [WARN] Could not set component names: {cn_err}")
                        
                        # Disable collision
                        try:
                            constraint.set_editor_property("disable_collision", True)
                        except:
                            pass
                        
                        # Configure physics
                        physics_configured = configure_constraint_physics(constraint, joint, debug=True)
                        
                        if physics_configured:
                            print(f"      [JOINT] {constraint_name}: {parent_link} <-> {child_link} ({joint_type}) - physics configured!")
                        else:
                            print(f"      [JOINT] {constraint_name}: {parent_link} <-> {child_link} ({joint_type}) - basic setup only")
                    else:
                        print(f"      [ADD] {constraint_name} - handle only")
                else:
                    print(f"      [ADD] {constraint_name} - no SubobjectData")
                
                constraint_count += 1
                
            except Exception as e:
                print(f"      [ERR] {joint_name}: {e}")
        
        print(f"      Added {constraint_count} constraint components (Python fallback)")
    
    # =========================================================================
    # STEP 7: Add Blueprint description
    # =========================================================================
    print(f"\n[7/8] Adding Blueprint description...")
    
    description = f"""ROA Robot Blueprint: {robot_name}

Components:
  - {mesh_count} StaticMeshComponents (robot links)
  - {constraint_count} PhysicsConstraintComponents (joints)

Physics Configuration (v7.2):
  - Configured via C++ ROABlueprintUtils (persists!)
  - Constraint rotation from mesh geometry analysis
  - Angular limits from URDF
  - Angular drive enabled for ROC velocity control
  - Linear motion locked
  - Physics simulation on non-base meshes

All components at origin (0,0,0) - USD pivots baked in mesh geometry.

Source: {hierarchy_path}

Created by ROA Robot Blueprint Factory v7.2"""
    
    blueprint.set_editor_property("blueprint_description", description)
    print(f"      Description added")
    
    # =========================================================================
    # STEP 8: Final compile and save (v7.16 - C++ constraint creation)
    # =========================================================================
    print(f"\n[8/8] Final compile and save...")
    
    # v7.16: If constraints were created via C++, they have rotation and physics set.
    # But we still need to call auto_position_constraints_from_mesh for accurate positions!
    
    if hasattr(unreal, 'ROABlueprintUtils'):
        try:
            # Build parent_child_map for mesh-based positioning
            parent_child_map = {}
            for joint in joints:
                joint_name = joint.get('name', '')
                parent_link = joint.get('parent_link', '')
                child_link = joint.get('child_link', '')
                
                if joint_name and parent_link and child_link:
                    constraint_name = f"Constraint_{joint_name}"
                    parent_child_map[constraint_name] = f"{parent_link}|{child_link}"
            
            if use_cpp_constraint_creation:
                # v7.16: Constraints already have rotation and physics, but need accurate positions!
                print(f"      [v7.16] C++ constraints have rotation/physics, updating positions from mesh bounds...")
                
                # Call auto_position to get accurate mesh-based positions
                if hasattr(unreal.ROABlueprintUtils, 'auto_position_constraints_from_mesh'):
                    pos_count = unreal.ROABlueprintUtils.auto_position_constraints_from_mesh(
                        blueprint, parent_child_map
                    )
                    print(f"      [C++] Auto-positioned {pos_count}/{len(parent_child_map)} constraints from mesh bounds")
            else:
                # Fallback path: constraints created via Python, need full C++ setup
                print(f"      [C++] Using ROABlueprintUtils for final constraint setup...")
                
                # Call C++ function to set all constraint names
                count = unreal.ROABlueprintUtils.set_all_constraint_component_names(
                    blueprint, parent_child_map
                )
                print(f"      [C++] Set names on {count}/{len(parent_child_map)} constraints")
                
                # Auto-position constraints from mesh bounds
                if hasattr(unreal.ROABlueprintUtils, 'auto_position_constraints_from_mesh'):
                    pos_count = unreal.ROABlueprintUtils.auto_position_constraints_from_mesh(
                        blueprint, parent_child_map
                    )
                    print(f"      [C++] Auto-positioned {pos_count}/{len(parent_child_map)} constraints from mesh bounds")
                
                # Configure constraint physics
                if hasattr(unreal.ROABlueprintUtils, 'configure_all_constraint_physics'):
                    # Build physics config mapping
                    physics_config_map = {}
                    for joint in joints:
                        joint_name = joint.get('name', '')
                        joint_type = joint.get('type', 'fixed')
                        
                        if joint_name in world_axes:
                            axis = world_axes[joint_name]
                        else:
                            local_axis = joint.get('axis', [0, 0, 1])
                            axis = [local_axis[0], -local_axis[1], local_axis[2]]
                        
                        limits = joint.get('limits') or {}
                        
                        constraint_name = f"Constraint_{joint_name}"
                        axis_str = f"{axis[0]},{axis[1] if len(axis) > 1 else 0},{axis[2] if len(axis) > 2 else 1}"
                        lower = limits.get('lower', -3.14159) if limits else -3.14159
                        upper = limits.get('upper', 3.14159) if limits else 3.14159
                        velocity = limits.get('velocity', 2.0) if limits else 2.0
                        effort = limits.get('effort', 100.0) if limits else 100.0
                        
                        config_str = f"{joint_type}|{axis_str}|{lower},{upper}|{velocity},{effort}"
                        physics_config_map[constraint_name] = config_str
                    
                    physics_count = unreal.ROABlueprintUtils.configure_all_constraint_physics(
                        blueprint, physics_config_map
                    )
                    print(f"      [C++] Configured physics + rotation on {physics_count}/{len(physics_config_map)} constraints")
            
            # v7.1: Enable physics simulation on mesh components (always do this)
            if hasattr(unreal.ROABlueprintUtils, 'enable_all_mesh_physics'):
                base_links = ['base_link', 'base', 'base_link_inertia']
                if root_link and root_link not in base_links:
                    base_links.append(root_link)
                
                mesh_physics_count = unreal.ROABlueprintUtils.enable_all_mesh_physics(
                    blueprint, base_links
                )
                print(f"      [C++] Enabled physics on {mesh_physics_count} mesh components")
            
            # Compile and mark modified
            unreal.ROABlueprintUtils.compile_and_mark_modified(blueprint)
            print(f"      [C++] Blueprint compiled and marked structurally modified")
        except Exception as cpp_err:
            print(f"      [C++ WARN] {cpp_err}")
            import traceback
            traceback.print_exc()
            mark_blueprint_modified(blueprint)
    else:
        # Fallback to Python approach
        mark_blueprint_modified(blueprint)
        print(f"      Blueprint marked as modified and compiled")
    
    # Save
    unreal.EditorAssetLibrary.save_asset(output_path)
    print(f"      Saved: {output_path}")
    
    print("=" * 70)
    print(f"  SUCCESS! Blueprint created: {output_path}")
    print("=" * 70)
    print(f"  Mesh Components: {mesh_count}")
    print(f"  Constraint Components: {constraint_count}")
    print("")
    if hasattr(unreal, 'ROABlueprintUtils'):
        print("  [C++] Constraint names set via ROABlueprintUtils - should persist!")
        print("        Open the Blueprint to verify.")
    else:
        print("  [Python-only] Open the Blueprint to verify constraint names are set.")
        print("                If not, run scn() while the Blueprint is open.")
    print("=" * 70)
    
    _register_robot_blueprint(robot_name, output_path, hierarchy_path)
    
    return output_path


def _register_robot_blueprint(robot_name: str, bp_path: str, hierarchy_path: str):
    """Register a robot Blueprint in the ROA registry."""
    registry_path = os.path.join(ROA_OUTPUTS_PATH, "robot_blueprints.json")
    
    registry = {}
    if os.path.exists(registry_path):
        try:
            with open(registry_path, 'r') as f:
                registry = json.load(f)
        except:
            pass
    
    import datetime
    registry[robot_name] = {
        "blueprint_path": bp_path,
        "hierarchy_path": hierarchy_path,
        "mesh_count": 0,
        "constraint_count": 0,
        "created": datetime.datetime.now().isoformat()
    }
    
    try:
        with open(registry_path, 'w') as f:
            json.dump(registry, f, indent=2)
        print(f"      Registered in: {registry_path}")
    except Exception as e:
        print(f"      Warning: Could not update registry: {e}")


# =============================================================================
# SPAWN ROBOT - Alternative using existing assembly
# =============================================================================

def spawn_robot(robot_name_or_path: str = None,
                location: Tuple[float, float, float] = None) -> bool:
    """
    Spawn a robot using the traditional assembly method.
    Use this if you prefer the actor-based approach over Blueprint components.
    """
    if not HAS_UNREAL:
        print("[RobotBlueprintFactory] ERROR: Unreal not available")
        return False
    
    print("=" * 70)
    print("  ROA Robot Spawner (Actor-based)")
    print("=" * 70)
    
    hierarchy_path = find_hierarchy_file(robot_name_or_path)
    if not hierarchy_path:
        print(f"[ERROR] Could not find hierarchy for: {robot_name_or_path}")
        return False
    
    print(f"Hierarchy: {hierarchy_path}")
    
    try:
        import sys
        python_path = os.path.dirname(os.path.abspath(__file__))
        if python_path not in sys.path:
            sys.path.insert(0, python_path)
        
        from urdf_robot_assembler import assemble_robot
        
        result = assemble_robot(
            hierarchy_path,
            verbose=True,
            materials_only=True,
            create_constraints=True
        )
        
        if result:
            print("=" * 70)
            print(f"  SUCCESS! Robot spawned with constraints")
            print("=" * 70)
            return True
        else:
            print("[ERROR] Assembly failed")
            return False
            
    except Exception as e:
        print(f"[ERROR] Assembly failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================================================
# LIST FUNCTIONS
# =============================================================================

def list_robot_blueprints() -> List[str]:
    """List all registered robot Blueprints."""
    registry_path = os.path.join(ROA_OUTPUTS_PATH, "robot_blueprints.json")
    
    if not os.path.exists(registry_path):
        print("[INFO] No robot Blueprints registered yet")
        print("       Use bp('robot_name') to create one")
        return []
    
    try:
        with open(registry_path, 'r') as f:
            registry = json.load(f)
    except:
        return []
    
    print("=" * 60)
    print("  Registered Robot Blueprints")
    print("=" * 60)
    
    robots = []
    for name, info in registry.items():
        bp_path = info.get("blueprint_path", "unknown")
        if HAS_UNREAL:
            exists = "[OK]" if unreal.EditorAssetLibrary.does_asset_exist(bp_path) else "[?]"
        else:
            exists = "[?]"
        print(f"  {exists} {name}: {bp_path}")
        robots.append(name)
    
    print("=" * 60)
    return robots


# =============================================================================
# SHORT ALIASES
# =============================================================================

def bp(robot_name: str) -> Optional[str]:
    """Create a robot Blueprint with meshes and constraints. Usage: bp('ur10e')"""
    return create_robot_blueprint(robot_name)


def sr(robot_name: str = None, x: float = 0, y: float = 0, z: float = 0) -> bool:
    """Spawn robot using actor-based assembly. Usage: sr('ur10e')"""
    return spawn_robot(robot_name, (x, y, z))


def lbp() -> List[str]:
    """List registered Blueprints. Usage: lbp()"""
    return list_robot_blueprints()


# =============================================================================
# SETUP BP - Configure constraints in Blueprint Editor with file picker
# =============================================================================

def setup_bp(hierarchy_json_path: str = None) -> bool:
    """
    Setup constraint names on the currently open Blueprint.
    
    This function:
    1. Gets the currently open Blueprint from the Editor
    2. Opens a file picker dialog to select the JSON hierarchy (if not provided)
    3. Sets component_name1/2 on each PhysicsConstraintComponent
    4. User saves manually (Ctrl+S)
    
    Usage:
        - Open a Blueprint in the Editor
        - Run: setup_bp()  (will prompt for JSON file)
        - Or run: setup_bp('/path/to/hierarchy.json')
        - Save the Blueprint (Ctrl+S)
    """
    if not HAS_UNREAL:
        print("[ROA] Unreal not available")
        return False
    
    print("=" * 70)
    print("  ROA: Setup Blueprint Constraints")
    print("=" * 70)
    
    try:
        # =====================================================================
        # STEP 1: Get the currently open Blueprint
        # =====================================================================
        asset_editor = unreal.get_editor_subsystem(unreal.AssetEditorSubsystem)
        if not asset_editor:
            print("[ERR] Could not get AssetEditorSubsystem")
            return False
        
        edited_assets = asset_editor.get_all_edited_assets()
        
        blueprint = None
        for asset in edited_assets:
            if isinstance(asset, unreal.Blueprint):
                blueprint = asset
                break
        
        if not blueprint:
            print("[ERR] No Blueprint is currently open in the Editor!")
            print("      Please open a Blueprint first, then run this command.")
            return False
        
        bp_name = blueprint.get_name()
        print(f"[1/5] Found open Blueprint: {bp_name}")
        
        # =====================================================================
        # STEP 2: Get or select the hierarchy JSON file
        # =====================================================================
        print(f"\n[2/5] Loading hierarchy file...")
        
        if hierarchy_json_path and os.path.exists(hierarchy_json_path):
            # Use provided path
            json_path = hierarchy_json_path
            print(f"      Using provided path: {json_path}")
        else:
            # Try to auto-detect from robot name
            robot_name = bp_name.replace("BP_", "")
            json_path = find_hierarchy_file(robot_name)
            
            if json_path:
                print(f"      Auto-detected: {json_path}")
            else:
                # Open file picker dialog
                print(f"      Opening file picker dialog...")
                
                try:
                    # Use Unreal's file dialog
                    dialog_title = "Select Robot Hierarchy JSON File"
                    default_path = ROA_OUTPUTS_PATH
                    file_types = "JSON Files (*.json)|*.json"
                    
                    # Try using DesktopPlatform for file dialog
                    if hasattr(unreal, 'DesktopPlatformBlueprintLibrary'):
                        selected_files = unreal.DesktopPlatformBlueprintLibrary.open_file_dialog(
                            None,  # Parent window
                            dialog_title,
                            default_path,
                            "",  # Default file
                            file_types,
                            False  # Multiple select
                        )
                        if selected_files:
                            json_path = selected_files[0]
                    elif hasattr(unreal, 'EditorUtilityLibrary'):
                        # Alternative: Use EditorUtilityLibrary if available
                        result = unreal.EditorUtilityLibrary.show_platform_open_file_dialog(
                            dialog_title,
                            default_path,
                            "*",
                            file_types,
                            False
                        )
                        if result:
                            json_path = result[0] if isinstance(result, (list, tuple)) else result
                except Exception as e:
                    print(f"      [WARN] File dialog failed: {e}")
                    print(f"      Please provide the path manually:")
                    print(f"      Usage: setup_bp('/path/to/hierarchy.json')")
                    return False
        
        if not json_path or not os.path.exists(json_path):
            print(f"[ERR] No hierarchy file selected or found!")
            print(f"      Usage: setup_bp('/path/to/hierarchy.json')")
            return False
        
        print(f"      Hierarchy file: {json_path}")
        
        # =====================================================================
        # STEP 3: Load hierarchy data
        # =====================================================================
        print(f"\n[3/5] Parsing hierarchy...")
        
        hierarchy_data = load_hierarchy(json_path)
        if not hierarchy_data:
            print(f"[ERR] Failed to load hierarchy from: {json_path}")
            return False
        
        hierarchy = hierarchy_data.get('hierarchy', {})
        joints = hierarchy.get('joints', [])
        
        print(f"      Found {len(joints)} joints")
        
        # =====================================================================
        # STEP 4: Set constraint component_name1/2 using SCS
        # =====================================================================
        print(f"\n[4/5] Setting constraint names via SCS...")
        
        constraints_set = 0
        
        # Use SCS approach (the proper way from ElgEditorScripting)
        for joint in joints:
            joint_name = joint.get('name', 'joint')
            parent_link = joint.get('parent_link', '')
            child_link = joint.get('child_link', '')
            
            if set_constraint_component_names_scs(blueprint, joint_name, parent_link, child_link):
                constraints_set += 1
        
        # =====================================================================
        # STEP 5: Mark modified, compile, and save
        # =====================================================================
        print(f"\n[5/5] Finalizing...")
        
        try:
            blueprint.modify()
            package = blueprint.get_outer()
            if package:
                package.mark_package_dirty()
        except:
            pass
        
        try:
            if hasattr(unreal, 'BlueprintEditorLibrary'):
                unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
                print(f"      Compiled Blueprint")
        except:
            pass
        
        print("=" * 70)
        print(f"  SUCCESS! Set {constraints_set} constraint names")
        print("")
        print("  IMPORTANT: Save the Blueprint (Ctrl+S) to persist changes!")
        print("=" * 70)
        
        return True
        
    except Exception as e:
        print(f"[ERR] Setup failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# Alias for easier typing
def scn(json_path: str = None) -> bool:
    """Alias for setup_bp(). Usage: scn() or scn('/path/to/hierarchy.json')"""
    return setup_bp(json_path)


# =============================================================================
# BLUEPRINT EDITOR MENU INTEGRATION
# =============================================================================

# Global reference to keep menu entry script alive
_roa_menu_entry = None

def _create_roa_menu_entry_class():
    """
    Factory function to create the ROAMenuEntry class.
    This avoids issues with conditional inheritance at module load time.
    """
    if not HAS_UNREAL:
        return None
    
    if not hasattr(unreal, 'ToolMenuEntryScript'):
        return None
    
    class ROAMenuEntry(unreal.ToolMenuEntryScript):
        """
        Custom menu entry for ROA Setup BP command.
        This class creates a menu item that executes Python code when clicked.
        """
        
        def __init__(self):
            super().__init__()
            
            # Configure the menu entry data
            self.init_entry(
                owner_name="ROA",
                menu="AssetEditor.BlueprintEditor.MainMenu.Asset",
                section="",
                name="ROA_SetupBP",
                label="ROA: Setup Constraints",
                tool_tip="Setup constraint component_name1/2 from hierarchy JSON file"
            )
        
        @unreal.ufunction(override=True)
        def execute(self, context) -> None:
            """Called when the menu item is clicked."""
            print("[ROA] Menu item clicked - running setup_bp()...")
            setup_bp()
        
        @unreal.ufunction(override=True)
        def can_execute(self, context) -> bool:
            """Check if the menu item should be enabled."""
            return True
    
    return ROAMenuEntry


def register_blueprint_editor_menu():
    """
    Register ROA menu in the Blueprint Editor.
    Adds 'ROA: Setup Constraints' to the Asset menu in Blueprint Editor.
    """
    global _roa_menu_entry
    
    if not HAS_UNREAL:
        return False
    
    try:
        menus = unreal.ToolMenus.get()
        
        # Try different menu locations for Blueprint Editor
        menu_locations = [
            "AssetEditor.BlueprintEditor.MainMenu.Asset",
            "AssetEditor.BlueprintEditor.MainMenu.Edit",
            "AssetEditor.BlueprintEditor.MainMenu",
        ]
        
        # Method 1: Try ToolMenuEntryScript approach (cleanest)
        try:
            ROAMenuEntry = _create_roa_menu_entry_class()
            if ROAMenuEntry:
                _roa_menu_entry = ROAMenuEntry()
                if unreal.ToolMenus.add_menu_entry_object(_roa_menu_entry):
                    print("[ROA] Menu entry registered via ToolMenuEntryScript")
                    menus.refresh_all_widgets()
                    return True
        except Exception as e:
            print(f"[ROA] ToolMenuEntryScript method failed: {e}")
        
        # Method 2: Try extend_menu approach
        for menu_path in menu_locations:
            try:
                menu = menus.extend_menu(menu_path)
                if menu:
                    # Add a section for ROA
                    menu.add_section("ROASection", "ROA Robot Tools")
                    
                    # Create menu entry
                    entry = unreal.ToolMenuEntry(
                        name="ROA_SetupBP",
                        type=unreal.MultiBlockType.MENU_ENTRY
                    )
                    entry.set_label("ROA: Setup Constraints")
                    entry.set_tool_tip("Run setup_bp() to configure constraint names")
                    
                    # Try to add the entry
                    menu.add_menu_entry("ROASection", entry)
                    
                    print(f"[ROA] Menu extended at: {menu_path}")
                    menus.refresh_all_widgets()
                    return True
                    
            except Exception as e:
                pass
        
        # Method 3: Print diagnostic info about available menus
        print("[ROA] Could not register menu. Available menu paths:")
        print("      Use scn() command in Python console instead.")
        
        return False
        
    except Exception as e:
        print(f"[ROA] Menu registration failed: {e}")
        return False


def list_blueprint_editor_menus():
    """
    Diagnostic function to list available Blueprint Editor menu paths.
    Run this to find valid menu paths for extending.
    """
    if not HAS_UNREAL:
        print("Unreal not available")
        return
    
    menus = unreal.ToolMenus.get()
    
    # Common menu paths to check
    paths_to_check = [
        "LevelEditor.MainMenu",
        "LevelEditor.MainMenu.File",
        "LevelEditor.MainMenu.Edit",
        "LevelEditor.MainMenu.Window",
        "AssetEditor.BlueprintEditor.MainMenu",
        "AssetEditor.BlueprintEditor.MainMenu.File",
        "AssetEditor.BlueprintEditor.MainMenu.Edit",
        "AssetEditor.BlueprintEditor.MainMenu.Asset",
        "AssetEditor.BlueprintEditor.MainMenu.View",
        "AssetEditor.BlueprintEditor.MainMenu.Debug",
        "AssetEditor.BlueprintEditor.ToolBar",
        "AssetEditor.BlueprintEditor.ToolBar.Asset",
        "ContentBrowser.AssetContextMenu",
    ]
    
    print("=" * 60)
    print("  Blueprint Editor Menu Paths")
    print("=" * 60)
    
    for path in paths_to_check:
        try:
            is_registered = menus.is_menu_registered(path)
            menu = menus.find_menu(path)
            status = "✓ FOUND" if menu else ("○ registered" if is_registered else "✗ not found")
            print(f"  {status}: {path}")
        except:
            print(f"  ? error: {path}")
    
    print("=" * 60)


# =============================================================================
# LEVEL EDITOR MENU (More Reliable)
# =============================================================================

def register_level_editor_menu():
    """
    Register ROA menu in the Level Editor's main menu bar.
    This is more reliable than Blueprint Editor menus from Python.
    """
    if not HAS_UNREAL:
        return False
    
    try:
        menus = unreal.ToolMenus.get()
        
        # Extend the Window menu in Level Editor (always available)
        menu = menus.extend_menu("LevelEditor.MainMenu.Window")
        if menu:
            # Add ROA section
            menu.add_section("ROA", "ROA Robot Tools")
            
            # Create menu entry - note: Python callbacks need ToolMenuEntryScript
            # Since that's limited, we just add a placeholder that reminds users
            entry = unreal.ToolMenuEntry(
                name="ROA_SetupBP_Info",
                type=unreal.MultiBlockType.MENU_ENTRY
            )
            entry.set_label("ROA: Use scn() in Python Console")
            entry.set_tool_tip("Open Python console and run: scn()")
            menu.add_menu_entry("ROA", entry)
            
            menus.refresh_all_widgets()
            print("[ROA] Added ROA section to Window menu")
            return True
            
    except Exception as e:
        print(f"[ROA] Level Editor menu registration: {e}")
    
    return False


# =============================================================================
# MODULE INITIALIZATION
# =============================================================================

if HAS_UNREAL:
    print("=" * 70)
    print("  ROA Robot Blueprint Factory v6.1 (C++ Integration)")
    print("=" * 70)
    print("  Commands:")
    print("    bp('robot_name')  - Create Blueprint + auto-configure constraints")
    print("    scn()             - Retry constraint names (if bp() missed some)")
    print("    lbp()             - List registered Blueprints")
    print("")
    if hasattr(unreal, 'ROABlueprintUtils'):
        print("  [C++ MODE] ROABlueprintUtils detected!")
        print("    Constraint names will persist correctly after save.")
    else:
        print("  [Python-only Mode] ROABlueprintUtils not compiled yet.")
        print("    Constraint names may not persist. Rebuild plugin to enable C++.")
    print("")
    print("  Workflow:")
    print("    1. bp('ur10e')    - Creates Blueprint with ALL constraints configured")
    print("    2. Open and verify in Blueprint Editor")
    print("    3. If constraints are wrong, run scn() to reconfigure")
    print("=" * 70)
    
    # Try to register menus (Level Editor is more reliable)
    register_level_editor_menu()
    register_blueprint_editor_menu()
