"""
ROA Universal Robot Assembler for UE5
======================================
Automatically assembles ANY robot converted by the ROA FTI system.

This module reads the hierarchy JSON file generated during URDF-to-USD conversion
and uses it to properly position and orient all robot parts in UE5.

Features:
- Works with ANY robot (not hardcoded configurations)
- Reads hierarchy from FTI-generated JSON file
- Proper ROS to UE5 coordinate conversion
- Transform chain accumulation (parent-child relationships)
- Visual origin transforms applied correctly
- Auto-detect robot parts in scene

Usage in UE5 Python Console:
    from ROA.urdf_robot_assembler import assemble_robot

    # Option 1: Auto-detect and assemble from hierarchy file
    assemble_robot("/path/to/robot_hierarchy.json")

    # Option 2: Assemble by robot name (searches common locations)
    assemble_robot("ur18")

    # Option 3: Assemble all robots in level
    assemble_all()

Integration:
    This is called automatically by the FTI after USD import.
"""

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import unreal

# =============================================================================
# COORDINATE CONVERSION: ROS to UE5
# =============================================================================
# ROS:  X-forward, Y-left, Z-up   (Right-handed, meters)
# UE5:  X-forward, Y-right, Z-up  (Left-handed, centimeters)


def ros_position_to_ue5(xyz: List[float], scale: float = 100.0) -> List[float]:
    """Convert ROS position (meters) to UE5 position (cm)."""
    return [
        xyz[0] * scale,  # X stays same
        -xyz[1] * scale,  # Y flips (left to right hand)
        xyz[2] * scale,  # Z stays same
    ]


def parse_xyz_string(xyz_str: str) -> List[float]:
    """Parse '0 0 0' format to [0.0, 0.0, 0.0]."""
    if not xyz_str:
        return [0.0, 0.0, 0.0]
    return [float(x) for x in xyz_str.split()]


def parse_rpy_string(rpy_str: str) -> List[float]:
    """Parse '0 0 0' RPY format to [0.0, 0.0, 0.0]."""
    if not rpy_str:
        return [0.0, 0.0, 0.0]
    return [float(r) for r in rpy_str.split()]


# =============================================================================
# QUATERNION MATH
# =============================================================================


def rpy_to_quaternion(rpy: List[float]) -> List[float]:
    """Convert Roll-Pitch-Yaw (radians) to quaternion [x, y, z, w]."""
    roll, pitch, yaw = rpy
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)

    return [
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    ]


def quaternion_multiply(q1: List[float], q2: List[float]) -> List[float]:
    """Multiply two quaternions: q1 * q2."""
    x1, y1, z1, w1 = q1
    x2, y2, z2, w2 = q2
    return [
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
    ]


def quaternion_rotate_vector(q: List[float], v: List[float]) -> List[float]:
    """Rotate vector v by quaternion q."""
    qx, qy, qz, qw = q
    vx, vy, vz = v

    tx = 2.0 * (qy * vz - qz * vy)
    ty = 2.0 * (qz * vx - qx * vz)
    tz = 2.0 * (qx * vy - qy * vx)

    return [
        vx + qw * tx + qy * tz - qz * ty,
        vy + qw * ty + qz * tx - qx * tz,
        vz + qw * tz + qx * ty - qy * tx,
    ]


def ros_quaternion_to_ue5(q: List[float]) -> List[float]:
    """Convert ROS quaternion to UE5 (flip Y axis for handedness)."""
    x, y, z, w = q
    return [x, -y, -z, w]


def quaternion_to_rotator(q: List[float]) -> "unreal.Rotator":
    """Convert quaternion [x,y,z,w] to Unreal Rotator."""
    x, y, z, w = q

    # Roll (X rotation)
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    # Pitch (Y rotation)
    sinp = 2.0 * (w * y - z * x)
    pitch = math.asin(max(-1.0, min(1.0, sinp)))

    # Yaw (Z rotation)
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return unreal.Rotator(math.degrees(pitch), math.degrees(yaw), math.degrees(roll))


# =============================================================================
# HIERARCHY LOADING
# =============================================================================


def find_hierarchy_file(robot_name_or_path: str) -> Optional[str]:
    """
    Find the hierarchy JSON file for a robot.

    Args:
        robot_name_or_path: Either a full path to JSON, or a robot name to search for

    Returns:
        Path to hierarchy file, or None if not found
    """
    # If it's already a path to a file
    if os.path.isfile(robot_name_or_path):
        return robot_name_or_path

    # Search common locations
    search_paths = [
        tempfile.gettempdir(),
        "D:/ROA/FTI-Outputs",
        "D:/ROA/output-tests",
        "C:/temp",
    ]

    robot_name = robot_name_or_path.lower()

    for search_dir in search_paths:
        if os.path.isdir(search_dir):
            for filename in os.listdir(search_dir):
                if filename.lower().startswith(robot_name) and filename.endswith("_hierarchy.json"):
                    return os.path.join(search_dir, filename)

    return None


def load_hierarchy(hierarchy_path: str) -> Optional[Dict]:
    """
    Load hierarchy data from JSON file.

    Args:
        hierarchy_path: Path to the hierarchy JSON file

    Returns:
        Hierarchy dictionary or None if failed
    """
    try:
        with open(hierarchy_path, "r") as f:
            data = json.load(f)

        # Validate it's from ROA-FTI
        if data.get("export_source") != "ROA-FTI":
            print(f"[WARN] File doesn't appear to be from ROA-FTI: {hierarchy_path}")

        return data
    except Exception as e:
        print(f"[ERROR] Failed to load hierarchy file: {e}")
        return None


# =============================================================================
# TRANSFORM COMPUTATION
# =============================================================================


def get_visual_origin(hierarchy_data: Dict, link_name: str) -> Optional[Dict]:
    """
    Get the visual origin transform for a link from hierarchy properties.

    Visual origin is the offset from link frame to mesh geometry,
    required for correct mesh positioning.

    Args:
        hierarchy_data: The loaded hierarchy dictionary
        link_name: Name of the link

    Returns:
        Visual origin dict with 'xyz' and 'rpy' or None if not found
    """
    hierarchy = hierarchy_data.get("hierarchy", {})
    nodes = hierarchy.get("nodes", {})

    if link_name not in nodes:
        return None

    node = nodes[link_name]
    properties = node.get("properties", {})

    # Check for visual_origin in properties
    visual_origin = properties.get("visual_origin")
    if visual_origin:
        return visual_origin

    return None


def apply_visual_origin(
    link_pos: List[float],
    link_quat: List[float],
    visual_origin: Dict,
    scale: float = 100.0,
) -> Tuple[List[float], List[float]]:
    """
    Apply visual origin offset to get final mesh transform.

    Final mesh position = link_position + link_rotation * visual_offset
    Final mesh rotation = link_rotation * visual_rotation

    Args:
        link_pos: Link frame world position [x, y, z] in UE5 cm
        link_quat: Link frame world quaternion [x, y, z, w]
        visual_origin: Visual origin dict with 'xyz' (meters) and 'rpy' (radians)
        scale: Meters to cm conversion (default 100)

    Returns:
        Tuple of (final_position, final_quaternion) in UE5 coordinates
    """
    # Get visual origin xyz and rpy
    xyz = visual_origin.get("xyz", [0, 0, 0])
    rpy = visual_origin.get("rpy", [0, 0, 0])

    # Handle string format
    if isinstance(xyz, str):
        xyz = parse_xyz_string(xyz)
    if isinstance(rpy, str):
        rpy = parse_rpy_string(rpy)

    # Convert to UE5 coordinates
    visual_offset_ue5 = ros_position_to_ue5(xyz, scale)
    visual_quat_ros = rpy_to_quaternion(rpy)
    visual_quat_ue5 = ros_quaternion_to_ue5(visual_quat_ros)

    # Apply visual offset: world_pos = link_pos + link_rotation * visual_offset
    rotated_offset = quaternion_rotate_vector(link_quat, visual_offset_ue5)
    final_pos = [link_pos[i] + rotated_offset[i] for i in range(3)]

    # Apply visual rotation: world_rot = link_rotation * visual_rotation
    final_quat = quaternion_multiply(link_quat, visual_quat_ue5)

    return final_pos, final_quat


def compute_link_transforms(hierarchy_data: Dict, origin: List[float] = None) -> Dict[str, Dict]:
    """
    Compute world transforms for all links using the hierarchy data.

    This is the key algorithm - accumulates transforms from root to leaves.

    Args:
        hierarchy_data: The loaded hierarchy dictionary
        origin: Assembly origin in UE5 world [x, y, z] in cm

    Returns:
        Dictionary mapping link names to their world transforms
    """
    if origin is None:
        origin = [0.0, 0.0, 0.0]

    hierarchy = hierarchy_data.get("hierarchy", {})
    nodes = hierarchy.get("nodes", {})
    root_nodes = hierarchy.get("root_nodes", [])

    # Default scale: URDF meters to UE5 centimeters
    scale = 100.0

    transforms = {}  # link_name -> {'position': [x,y,z], 'quaternion': [x,y,z,w]}

    # Build a map of joint transforms: child_link -> joint_transform
    # In URDF, a joint connects parent_link to child_link with a transform
    joint_transforms = {}
    for node_name, node in nodes.items():
        if node.get("type") == "joint":
            transform = node.get("transform")
            # The child_link is stored directly in the joint's properties
            child_link = node.get("properties", {}).get("child_link")
            if child_link and transform:
                joint_transforms[child_link] = transform

    def process_link(link_name: str, parent_pos: List[float], parent_quat: List[float]):
        """Recursively process links to compute world transforms."""
        if link_name not in nodes:
            return

        node = nodes[link_name]
        if node.get("type") != "link":
            return

        # Get the joint transform that positions this link relative to parent
        transform = joint_transforms.get(link_name, {})

        if isinstance(transform, dict):
            xyz = transform.get("xyz", [0, 0, 0])
            rpy = transform.get("rpy", [0, 0, 0])
        else:
            xyz = [0, 0, 0]
            rpy = [0, 0, 0]

        # Handle string or list format
        if isinstance(xyz, str):
            xyz = parse_xyz_string(xyz)
        if isinstance(rpy, str):
            rpy = parse_rpy_string(rpy)

        # Convert to UE5 coordinates
        joint_pos_ue5 = ros_position_to_ue5(xyz, scale)
        joint_quat_ros = rpy_to_quaternion(rpy)
        joint_quat_ue5 = ros_quaternion_to_ue5(joint_quat_ros)

        # World position = parent position + parent rotation * joint offset
        rotated_offset = quaternion_rotate_vector(parent_quat, joint_pos_ue5)
        world_pos = [parent_pos[i] + rotated_offset[i] for i in range(3)]

        # World rotation = parent rotation * joint rotation
        world_quat = quaternion_multiply(parent_quat, joint_quat_ue5)

        # Store transform
        transforms[link_name] = {"position": world_pos, "quaternion": world_quat}

        # Process children (other links)
        for child in node.get("children", []):
            if child in nodes and nodes[child].get("type") == "link":
                process_link(child, world_pos, world_quat)

    # Process from each root
    identity_quat = [0.0, 0.0, 0.0, 1.0]
    for root in root_nodes:
        # Root link starts at origin
        transforms[root] = {"position": list(origin), "quaternion": identity_quat}
        # Process children of root
        if root in nodes:
            for child in nodes[root].get("children", []):
                if child in nodes and nodes[child].get("type") == "link":
                    process_link(child, origin, identity_quat)

    return transforms


# =============================================================================
# ACTOR FINDING AND MATCHING
# =============================================================================


def find_robot_actors(
    robot_name: str = "",
    link_names: List[str] = None,
    reference_position: List[float] = None,
    position_tolerance: float = 500.0,
) -> Dict[str, List[Any]]:
    """
    Find all mesh actors in the level that belong to a specific robot.

    MULTI-ROBOT SUPPORT:
    USD files from ROA FTI use robot-prefixed mesh names for disambiguation:
    - "ur18_shoulder_link_visual" (robot-prefixed, preferred)
    - "ur10_base_link_visual" (different robot)

    Matching priority:
    1. Robot-prefixed names (e.g., "ur18_shoulder_link_visual")
    2. Position clustering (actors near reference_position)
    3. Legacy names without prefix (for backward compatibility)

    Args:
        robot_name: Robot name prefix for filtering (e.g., "ur18")
        link_names: List of link names from hierarchy to match
        reference_position: Optional [x, y, z] position to filter by proximity (cm)
        position_tolerance: Distance threshold for position clustering (cm)

    Returns:
        Dictionary mapping link names to lists of actor objects
    """
    editor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = editor_subsystem.get_all_level_actors()

    robot_actors = {}  # link_name -> [actor1, actor2, ...]
    robot_name_lower = robot_name.lower().replace("-", "_").replace(" ", "_") if robot_name else ""

    # Build patterns to match - prioritize robot-prefixed patterns
    link_patterns_prefixed = []  # (pattern, original_link_name) with robot prefix
    link_patterns_standard = []  # (pattern, original_link_name) without prefix

    if link_names:
        for link in link_names:
            link_lower = link.lower().replace("-", "_")
            # Robot-prefixed pattern (e.g., "ur18_shoulder_link")
            if robot_name_lower:
                prefixed = f"{robot_name_lower}_{link_lower}"
                link_patterns_prefixed.append((prefixed, link))
            # Standard pattern (e.g., "shoulder_link")
            link_patterns_standard.append((link_lower, link))
        # Sort by length descending so longer/more specific patterns match first
        link_patterns_prefixed.sort(key=lambda x: len(x[0]), reverse=True)
        link_patterns_standard.sort(key=lambda x: len(x[0]), reverse=True)

    # Phase 1: Find actors matching robot-prefixed names (highest priority)
    prefixed_matches = {}
    for actor in all_actors:
        if not isinstance(actor, unreal.StaticMeshActor):
            continue

        actor_label = actor.get_actor_label().lower().replace("-", "_")
        mesh_name = ""
        mesh_component = actor.static_mesh_component
        if mesh_component and mesh_component.static_mesh:
            mesh_name = mesh_component.static_mesh.get_name().lower().replace("-", "_")

        search_text = f"{actor_label} {mesh_name}"

        # Try robot-prefixed patterns first
        for pattern, original_name in link_patterns_prefixed:
            if pattern in search_text:
                if any(suffix in search_text for suffix in ["visual", "collision", "mesh"]):
                    if original_name not in prefixed_matches:
                        prefixed_matches[original_name] = []
                    prefixed_matches[original_name].append(actor)
                    break

    # If we found prefixed matches, use them (multi-robot scene)
    if prefixed_matches:
        print(
            f"[ASSEMBLER] Found {len(prefixed_matches)} links with robot-prefixed names (multi-robot mode)"
        )
        return prefixed_matches

    # Phase 2: Position clustering (if reference_position provided)
    if reference_position:
        print(f"[ASSEMBLER] Using position clustering around {reference_position}")
        position_matches = {}
        ref_vec = unreal.Vector(reference_position[0], reference_position[1], reference_position[2])

        for actor in all_actors:
            if not isinstance(actor, unreal.StaticMeshActor):
                continue

            actor_pos = actor.get_actor_location()
            distance = (unreal.Vector(actor_pos.x, actor_pos.y, actor_pos.z) - ref_vec).length()

            if distance > position_tolerance:
                continue

            actor_label = actor.get_actor_label().lower()
            mesh_name = ""
            mesh_component = actor.static_mesh_component
            if mesh_component and mesh_component.static_mesh:
                mesh_name = mesh_component.static_mesh.get_name().lower()

            search_text = f"{actor_label} {mesh_name}"

            for pattern, original_name in link_patterns_standard:
                if pattern in search_text:
                    if any(
                        suffix in search_text for suffix in ["visual", "collision", "mesh", "_link"]
                    ):
                        if original_name not in position_matches:
                            position_matches[original_name] = []
                        position_matches[original_name].append(actor)
                        break

        if position_matches:
            print(f"[ASSEMBLER] Found {len(position_matches)} links via position clustering")
            return position_matches

    # Phase 3: Standard matching (legacy single-robot mode)
    print(f"[ASSEMBLER] Using standard matching (single-robot mode)")
    for actor in all_actors:
        if not isinstance(actor, unreal.StaticMeshActor):
            continue

        actor_label = actor.get_actor_label().lower()
        mesh_name = ""
        mesh_component = actor.static_mesh_component
        if mesh_component and mesh_component.static_mesh:
            mesh_name = mesh_component.static_mesh.get_name().lower()

        search_text = f"{actor_label} {mesh_name}"
        matched_link = None

        if link_patterns_standard:
            for pattern, original_name in link_patterns_standard:
                if pattern in search_text:
                    if any(
                        suffix in search_text for suffix in ["visual", "collision", "mesh", "_link"]
                    ):
                        matched_link = original_name
                        break
        elif robot_name_lower:
            # Fallback: filter by robot name in actor label
            if robot_name_lower in actor_label or robot_name_lower in mesh_name:
                matched_link = actor_label.replace("_visual", "").replace("_collision", "")
        else:
            # No filter - try to determine if this is a robot part
            if any(x in search_text for x in ["_link", "_visual", "_collision", "_inertia"]):
                matched_link = actor_label.replace("_visual", "").replace("_collision", "")

        if matched_link:
            if matched_link not in robot_actors:
                robot_actors[matched_link] = []
            robot_actors[matched_link].append(actor)

    print(f"[ASSEMBLER] Found {len(robot_actors)} links via standard matching")
    return robot_actors


def match_actor_to_link(actor_name: str, link_names: List[str]) -> Optional[str]:
    """
    Match an actor name to a link name.

    Args:
        actor_name: Name of the actor in UE5
        link_names: List of link names from hierarchy

    Returns:
        Matched link name or None
    """
    actor_lower = actor_name.lower()

    # Try exact match first
    for link in link_names:
        link_lower = link.lower()
        if link_lower in actor_lower or actor_lower in link_lower:
            return link

    # Try with common prefixes/suffixes removed
    clean_actor = actor_lower
    for suffix in ["_mesh", "_visual", "_collision", "_link", "_0", "_1"]:
        clean_actor = clean_actor.replace(suffix, "")

    for link in link_names:
        clean_link = link.lower().replace("_link", "")
        if clean_link in clean_actor or clean_actor in clean_link:
            return link

    return None


def get_visual_actor(actors: List["unreal.Actor"]) -> "unreal.Actor":
    """
    From a list of actors for a link, prefer the visual actor over collision.

    Visual actors typically have correct world positions after USD import,
    while collision actors may all be at the same position.

    Args:
        actors: List of actors (visual and collision) for a link

    Returns:
        The visual actor if found, otherwise the first actor
    """
    if not actors:
        return None

    # First, try to find a visual actor
    for actor in actors:
        label = actor.get_actor_label().lower()
        if "visual" in label:
            return actor

    # If no visual found, try to avoid collision
    for actor in actors:
        label = actor.get_actor_label().lower()
        if "collision" not in label:
            return actor

    # Fallback to first actor
    return actors[0]


# =============================================================================
# MATERIAL APPLICATION
# =============================================================================


def create_dynamic_material(
    color: List[float], mat_name: str = "ROA_Material", outer: Any = None
) -> "unreal.MaterialInstanceDynamic":
    """
    Create a dynamic material instance with the specified color.

    Args:
        color: RGBA values [0-1, 0-1, 0-1, 0-1]
        mat_name: Name for the material
        outer: Outer object for the dynamic material (usually the mesh component)

    Returns:
        MaterialInstanceDynamic or None
    """
    try:
        # Try using KismetMaterialLibrary which is the correct UE5 approach
        # for creating dynamic material instances at runtime
        r, g, b = color[0], color[1], color[2]
        a = color[3] if len(color) > 3 else 1.0

        # Try multiple base material paths
        base_material_paths = [
            "/Engine/BasicShapes/BasicShapeMaterial",
            "/Engine/EngineMaterials/DefaultMaterial",
        ]

        base_material = None
        for path in base_material_paths:
            try:
                base_material = unreal.EditorAssetLibrary.load_asset(path)
                if base_material:
                    break
            except:
                pass

        if not base_material:
            return None

        # Method 1: Use KismetMaterialLibrary (preferred)
        try:
            world = unreal.EditorLevelLibrary.get_editor_world()
            dynamic_mat = unreal.KismetMaterialLibrary.create_dynamic_material_instance(
                world, base_material
            )
            if dynamic_mat:
                linear_color = unreal.LinearColor(r, g, b, a)
                for param_name in ["BaseColor", "Base Color", "Color", "Tint"]:
                    try:
                        dynamic_mat.set_vector_parameter_value(param_name, linear_color)
                    except:
                        pass
                return dynamic_mat
        except:
            pass

        return None

    except Exception as e:
        print(f"[WARN] Failed to create dynamic material {mat_name}: {e}")
        return None


def apply_color_override(
    actor: "unreal.StaticMeshActor", color: List[float], verbose: bool = False
) -> bool:
    """
    Apply color to an actor using vertex color or material override.

    This is a more robust approach that doesn't require dynamic materials.
    Uses the mesh component's color override feature.

    Args:
        actor: StaticMeshActor to colorize
        color: RGBA [0-1] values
        verbose: Print debug info

    Returns:
        True if successful
    """
    try:
        mesh_comp = actor.static_mesh_component
        if not mesh_comp:
            return False

        r, g, b = color[0], color[1], color[2]
        a = color[3] if len(color) > 3 else 1.0

        num_materials = mesh_comp.get_num_materials()
        success = False

        for i in range(num_materials):
            original_mat = mesh_comp.get_material(i)

            # Try multiple approaches in order of preference
            applied = False

            # Approach 1: Use create_dynamic_material_instance on the mesh component
            # This is the correct UE5 Python approach
            if not applied:
                try:
                    # Create dynamic material from the mesh component's current material
                    dynamic_mat = mesh_comp.create_dynamic_material_instance(i)
                    if dynamic_mat:
                        linear_color = unreal.LinearColor(r, g, b, a)
                        # Try common color parameter names
                        for param in [
                            "BaseColor",
                            "Base Color",
                            "Color",
                            "Tint",
                            "DiffuseColor",
                            "Diffuse",
                        ]:
                            try:
                                dynamic_mat.set_vector_parameter_value(param, linear_color)
                                applied = True
                            except:
                                pass
                except:
                    pass

            # Approach 2: Use KismetMaterialLibrary with a basic engine material
            if not applied:
                try:
                    base_paths = [
                        "/Engine/BasicShapes/BasicShapeMaterial",
                        "/Engine/EngineMaterials/DefaultMaterial",
                    ]
                    world = unreal.EditorLevelLibrary.get_editor_world()
                    for base_path in base_paths:
                        base_mat = unreal.EditorAssetLibrary.load_asset(base_path)
                        if base_mat:
                            dynamic_mat = (
                                unreal.KismetMaterialLibrary.create_dynamic_material_instance(
                                    world, base_mat
                                )
                            )
                            if dynamic_mat:
                                linear_color = unreal.LinearColor(r, g, b, a)
                                for param in ["BaseColor", "Base Color", "Color"]:
                                    try:
                                        dynamic_mat.set_vector_parameter_value(param, linear_color)
                                    except:
                                        pass
                                mesh_comp.set_material(i, dynamic_mat)
                                applied = True
                                break
                except:
                    pass

            if applied:
                success = True
                if verbose:
                    print(f"        Applied color ({r:.2f}, {g:.2f}, {b:.2f}) to slot {i}")

        return success

    except Exception as e:
        if verbose:
            print(f"[WARN] apply_color_override failed: {e}")
        return False


def apply_material_to_actor(
    actor: "unreal.StaticMeshActor",
    color: List[float],
    mat_name: str = "",
    verbose: bool = False,
):
    """
    Apply a colored material to a StaticMeshActor.

    Uses multiple fallback approaches:
    1. Create dynamic material from existing material
    2. Color override on mesh component

    Args:
        actor: The actor to apply material to
        color: RGBA values [0-1, 0-1, 0-1, 0-1]
        mat_name: Optional material name for debugging
        verbose: Print debug info
    """
    # Try the robust color override method first
    success = apply_color_override(actor, color, verbose)

    if not success:
        # Fallback: try creating a completely new dynamic material
        try:
            mesh_component = actor.static_mesh_component
            if mesh_component:
                dynamic_mat = create_dynamic_material(color, mat_name)
                if dynamic_mat:
                    num_materials = mesh_component.get_num_materials()
                    for i in range(num_materials):
                        mesh_component.set_material(i, dynamic_mat)
                    success = True
        except Exception as e:
            if verbose:
                print(f"[WARN] Fallback material application failed: {e}")


def get_link_color(link_name: str, hierarchy_data: Dict) -> Optional[List[float]]:
    """
    Get the color for a link from hierarchy data.

    Args:
        link_name: Name of the link
        hierarchy_data: The loaded hierarchy dictionary

    Returns:
        RGBA color list or None
    """
    hierarchy = hierarchy_data.get("hierarchy", {})
    materials = hierarchy.get("materials", {})
    link_materials = hierarchy.get("link_materials", {})

    # Get material names for this link
    mat_names = link_materials.get(link_name, [])

    if not mat_names:
        return None

    # Use first material
    mat_name = mat_names[0]
    mat_data = materials.get(mat_name, {})

    return mat_data.get("color")


# =============================================================================
# MAIN ASSEMBLY FUNCTIONS
# =============================================================================


def assemble_robot(
    robot_name_or_path: str,
    origin: List[float] = None,
    verbose: bool = True,
    materials_only: bool = True,
    create_constraints: bool = True,
) -> bool:
    """
    Assemble a robot in UE5 using the FTI-generated hierarchy data.

    This function:
    1. Finds robot actors in the level (imported from USD)
    2. Optionally applies materials/colors from URDF
    3. Optionally creates physics constraints for joints

    Args:
        robot_name_or_path: Robot name or path to hierarchy JSON file
        origin: Assembly origin [x, y, z] in cm. Default [0, 0, 50]
        verbose: Print detailed progress messages
        materials_only: If True (default), only apply materials without repositioning.
                       The USD import already places actors correctly.
                       Set to False to recompute and apply transforms.
        create_constraints: If True (default), create physics constraints for all joints.

    Returns:
        True if assembly succeeded, False otherwise
    """
    if origin is None:
        origin = [0.0, 0.0, 50.0]

    if verbose:
        print("=" * 60)
        print("  ROA Universal Robot Assembler")
        print("=" * 60)

    # Step 1: Find hierarchy file
    if verbose:
        print(f"\n[1/4] Looking for hierarchy data: {robot_name_or_path}")

    hierarchy_path = find_hierarchy_file(robot_name_or_path)
    if not hierarchy_path:
        print(f"[ERROR] Could not find hierarchy file for: {robot_name_or_path}")
        return False

    if verbose:
        print(f"      Found: {hierarchy_path}")

    # Step 2: Load hierarchy
    if verbose:
        print("\n[2/4] Loading hierarchy data...")

    hierarchy_data = load_hierarchy(hierarchy_path)
    if not hierarchy_data:
        return False

    robot_name = hierarchy_data.get("robot_name", "robot")
    if verbose:
        print(f"      Robot: {robot_name}")
        hierarchy = hierarchy_data.get("hierarchy", {})
        print(
            f"      Links: {len([n for n, d in hierarchy.get('nodes', {}).items() if d.get('type') == 'link'])}"
        )

    # Step 3: Compute transforms (only if not materials_only mode)
    transforms = {}
    link_names = []

    if not materials_only:
        if verbose:
            print("\n[3/4] Computing transforms...")
        transforms = compute_link_transforms(hierarchy_data, origin)
        if verbose:
            print(f"      Computed {len(transforms)} link transforms")
        link_names = list(transforms.keys())
    else:
        # In materials_only mode, get link names from hierarchy for actor search
        hierarchy = hierarchy_data.get("hierarchy", {})
        link_names = [n for n, d in hierarchy.get("nodes", {}).items() if d.get("type") == "link"]
        if verbose:
            print("\n[3/4] Skipping transform computation (materials_only mode)")
            print(f"      USD import already positioned actors correctly")

    # Step 4: Find actors
    if verbose:
        step_name = "Finding actors..." if materials_only else "Assembling robot..."
        print(f"\n[4/5] {step_name}")

    # Note: link_names was already set above (either from transforms or from hierarchy)
    # Do NOT overwrite it here - that was causing the empty list bug!

    actors_by_link = find_robot_actors(robot_name, link_names)
    if not actors_by_link:
        print(f"[ERROR] No actors found matching: {robot_name}")
        print(f"        Link names searched: {link_names[:5]}...")
        print("        Make sure you've imported the USD file first!")
        return False

    # Count total actors found
    total_actors = sum(len(actor_list) for actor_list in actors_by_link.values())

    if verbose:
        print(f"      Found {total_actors} actors for {len(actors_by_link)} links")

    # Check if materials are available
    hierarchy = hierarchy_data.get("hierarchy", {})
    has_materials = bool(hierarchy.get("materials"))
    materials_applied = 0

    # Track matched actors
    matched_count = 0
    unmatched_links = []
    visual_origins_applied = 0

    # Apply transforms only if NOT in materials_only mode
    if not materials_only:
        # IMPORTANT: Visual origins are already baked into the USD file during conversion
        # (confirmed by inspecting ur20_parts.usd - meshes have translate/rotate ops matching URDF visual origins)
        # Therefore, we must NOT apply them again in the assembler!
        skip_visual_origins = True  # USD already has visual origins baked in

        for link_name, actor_list in actors_by_link.items():
            if link_name in transforms:
                tf = transforms[link_name]
                link_pos = tf["position"]
                link_quat = tf["quaternion"]

                # Check for visual origin in hierarchy (mesh offset from link frame)
                visual_origin = (
                    get_visual_origin(hierarchy_data, link_name)
                    if not skip_visual_origins
                    else None
                )

                if visual_origin:
                    # Apply visual origin transform to get final mesh position
                    final_pos, final_quat = apply_visual_origin(link_pos, link_quat, visual_origin)
                    visual_origins_applied += 1
                    origin_applied = True
                    if verbose:
                        vo_xyz = visual_origin.get("xyz", [0, 0, 0])
                        vo_rpy = visual_origin.get("rpy", [0, 0, 0])
                        print(
                            f"        VO: xyz=[{vo_xyz[0]:.3f}, {vo_xyz[1]:.3f}, {vo_xyz[2]:.3f}] rpy=[{vo_rpy[0]:.2f}, {vo_rpy[1]:.2f}, {vo_rpy[2]:.2f}]"
                        )
                else:
                    # No visual origin, use link frame directly (old behavior)
                    final_pos = link_pos
                    final_quat = link_quat
                    origin_applied = False

                # Apply final transform to all actors (visual + collision) for this link
                location = unreal.Vector(final_pos[0], final_pos[1], final_pos[2])
                rotation = quaternion_to_rotator(final_quat)

                for actor in actor_list:
                    actor.set_actor_location(location, False, False)
                    actor.set_actor_rotation(rotation, False)
                    matched_count += 1

                if verbose:
                    origin_marker = " [+VO]" if origin_applied else ""
                    print(f"      [OK] {link_name} ({len(actor_list)} actors){origin_marker}")
            else:
                unmatched_links.append(link_name)
    else:
        # In materials_only mode, just count matched actors (no repositioning)
        for link_name, actor_list in actors_by_link.items():
            matched_count += len(actor_list)
            if verbose:
                print(f"      [OK] {link_name} ({len(actor_list)} actors) - position preserved")

    # Step 5: Apply materials
    if has_materials:
        if verbose:
            print("\n[5/6] Applying materials...")

        for link_name, actor_list in actors_by_link.items():
            color = get_link_color(link_name, hierarchy_data)
            if color:
                for actor in actor_list:
                    apply_material_to_actor(actor, color, link_name)
                materials_applied += 1
                if verbose:
                    print(
                        f"      [MAT] {link_name}: rgba({color[0]:.2f}, {color[1]:.2f}, {color[2]:.2f}, {color[3] if len(color) > 3 else 1.0:.2f})"
                    )

    # Step 6: Create physics constraints
    constraints_created = 0
    if create_constraints:
        if verbose:
            print("\n[6/6] Creating physics constraints...")

        # Check for enhanced joints (v3.0+) with full UE5 constraint parameters
        enhanced_joints = hierarchy_data.get("enhanced_joints", [])
        joints_list = hierarchy.get("joints", [])

        # Build enhanced joints lookup by name
        enhanced_lookup = {}
        if enhanced_joints:
            for ej in enhanced_joints:
                enhanced_lookup[ej.get("name", "")] = ej
            if verbose:
                print(f"      Using enhanced joint data (v3.0) with {len(enhanced_lookup)} joints")

        if joints_list:
            for joint in joints_list:
                parent_link = joint.get("parent_link")
                child_link = joint.get("child_link")
                joint_name = joint.get("name", "")

                # Find actors for parent and child
                parent_actors = actors_by_link.get(parent_link, [])
                child_actors = actors_by_link.get(child_link, [])

                if parent_actors and child_actors:
                    # IMPORTANT: Prefer visual actors over collision actors
                    # Visual actors have correct world positions, collision actors may not
                    parent_actor = get_visual_actor(parent_actors)
                    child_actor = get_visual_actor(child_actors)

                    # Get enhanced joint data if available
                    enhanced_data = enhanced_lookup.get(joint_name)

                    # Create the constraint with enhanced data
                    constraint = create_physics_constraint(
                        parent_actor,
                        child_actor,
                        joint,
                        enhanced_joint=enhanced_data,
                        verbose=verbose,
                    )
                    if constraint:
                        constraints_created += 1
                else:
                    if verbose:
                        print(f"      [SKIP] {joint.get('name', 'unknown')}: Missing actors")
        else:
            if verbose:
                print("      No joints array in hierarchy (version < 2.2?)")

    # Summary
    print("")
    print("=" * 60)
    if materials_only:
        print(f"  ASSEMBLY COMPLETE!")
        print(f"  Mode: Materials only (positions preserved from USD import)")
    else:
        print(f"  ASSEMBLY COMPLETE!")
        if visual_origins_applied > 0:
            print(f"  Visual Origins: {visual_origins_applied} applied")
    print(f"  Matched: {matched_count} actors across {len(actors_by_link)} links")
    if has_materials:
        print(f"  Materials: {materials_applied} applied")
    if create_constraints:
        print(f"  Constraints: {constraints_created} created")
    if unmatched_links and not materials_only:
        print(f"\n  Links without transforms (virtual/fixed joints):")
        for name in unmatched_links[:5]:  # Show first 5
            print(f"    - {name}")
        if len(unmatched_links) > 5:
            print(f"    ... and {len(unmatched_links) - 5} more")
    print("=" * 60)

    return matched_count > 0


def assemble_all(verbose: bool = True) -> int:
    """
    Find and assemble all ROA robots in the current level.

    Args:
        verbose: Print detailed progress messages

    Returns:
        Number of robots successfully assembled
    """
    if verbose:
        print("\n[INFO] Searching for ROA robots in scene...")

    # Search for hierarchy files in temp directory
    temp_dir = tempfile.gettempdir()
    assembled_count = 0

    if os.path.isdir(temp_dir):
        for filename in os.listdir(temp_dir):
            if filename.endswith("_hierarchy.json"):
                robot_name = filename.replace("_hierarchy.json", "")
                hierarchy_path = os.path.join(temp_dir, filename)

                if verbose:
                    print(f"\n[FOUND] {robot_name}")

                if assemble_robot(hierarchy_path, verbose=verbose):
                    assembled_count += 1

    if verbose:
        print(f"\n[DONE] Assembled {assembled_count} robot(s)")

    return assembled_count


def reset_robot(robot_name: str = "") -> int:
    """
    Reset all robot parts to origin.

    Args:
        robot_name: Robot name to reset (empty for all)

    Returns:
        Number of actors reset
    """
    actors = find_robot_actors(robot_name)

    for actor in actors.values():
        actor.set_actor_location(unreal.Vector(0, 0, 0), False, False)
        actor.set_actor_rotation(unreal.Rotator(0, 0, 0), False)

    print(f"[RESET] Moved {len(actors)} actors to origin")
    return len(actors)


def list_robots() -> List[str]:
    """
    List all hierarchy files available for assembly.

    Returns:
        List of robot names
    """
    robots = []
    temp_dir = tempfile.gettempdir()

    if os.path.isdir(temp_dir):
        for filename in os.listdir(temp_dir):
            if filename.endswith("_hierarchy.json"):
                robot_name = filename.replace("_hierarchy.json", "")
                robots.append(robot_name)

    if robots:
        print(f"\n[INFO] Available robots for assembly:")
        for r in robots:
            print(f"  - {r}")
    else:
        print("\n[INFO] No robot hierarchy files found.")
        print("       Convert a URDF file using FTI first!")

    return robots


# =============================================================================
# PHYSICS CONSTRAINTS
# =============================================================================


def compute_constraint_rotation_from_axis(
    axis: List[float], rpy: List[float] = None
) -> "unreal.Rotator":
    """
    Compute constraint rotation to align with URDF joint axis.

    UE5 Physics Constraints default free axis is X (Twist).
    URDF joints can have any arbitrary axis. This function computes
    the rotation needed to align the constraint's X-axis with the URDF axis.

    Additionally, applies the joint origin RPY rotation.

    Coordinate conversion:
    - ROS: X-forward, Y-left, Z-up (right-handed)
    - UE5: X-forward, Y-right, Z-up (left-handed)
    - Y is flipped between systems

    Args:
        axis: [x, y, z] rotation axis from URDF (in ROS coordinates)
        rpy: [roll, pitch, yaw] joint origin rotation in radians

    Returns:
        unreal.Rotator to apply to constraint actor
    """
    if rpy is None:
        rpy = [0, 0, 0]

    # Normalize axis
    length = math.sqrt(sum(a * a for a in axis))
    if length > 0:
        axis = [a / length for a in axis]
    else:
        axis = [1, 0, 0]  # Default X

    # Convert axis from ROS to UE5 (flip Y)
    ue5_axis = [axis[0], -axis[1], axis[2]]

    # Compute rotation to align X-axis (1,0,0) with target axis
    # Using the rotation that takes (1,0,0) to ue5_axis
    x_axis = [1.0, 0.0, 0.0]

    # Dot product
    dot = x_axis[0] * ue5_axis[0] + x_axis[1] * ue5_axis[1] + x_axis[2] * ue5_axis[2]

    if dot > 0.9999:
        # Axes are parallel - no rotation needed
        pitch, yaw, roll = 0, 0, 0
    elif dot < -0.9999:
        # Axes are opposite - rotate 180 around Z or Y
        pitch, yaw, roll = 0, 180, 0
    else:
        # Cross product gives rotation axis
        cross = [
            x_axis[1] * ue5_axis[2] - x_axis[2] * ue5_axis[1],
            x_axis[2] * ue5_axis[0] - x_axis[0] * ue5_axis[2],
            x_axis[0] * ue5_axis[1] - x_axis[1] * ue5_axis[0],
        ]

        # Angle from dot product
        angle_rad = math.acos(max(-1, min(1, dot)))
        angle_deg = math.degrees(angle_rad)

        # Normalize cross product to get rotation axis
        cross_len = math.sqrt(sum(c * c for c in cross))
        if cross_len > 0.0001:
            cross = [c / cross_len for c in cross]

        # Convert axis-angle to Euler angles
        # Simplified: determine dominant direction
        abs_cross = [abs(c) for c in cross]
        max_idx = abs_cross.index(max(abs_cross))

        if max_idx == 0:  # Rotate around X
            roll = angle_deg if cross[0] > 0 else -angle_deg
            pitch, yaw = 0, 0
        elif max_idx == 1:  # Rotate around Y
            pitch = angle_deg if cross[1] > 0 else -angle_deg
            roll, yaw = 0, 0
        else:  # Rotate around Z
            yaw = angle_deg if cross[2] > 0 else -angle_deg
            roll, pitch = 0, 0

    # Apply joint origin RPY (convert from radians to degrees, flip Y for handedness)
    if any(r != 0 for r in rpy):
        roll += math.degrees(rpy[0])
        pitch += math.degrees(-rpy[1])  # Flip for handedness
        yaw += math.degrees(rpy[2])

    return unreal.Rotator(pitch, yaw, roll)


def urdf_axis_to_ue5_constraint(axis: List[float], joint_type: str) -> Dict[str, str]:
    """
    Map URDF joint axis to UE5 constraint motion settings.

    URDF uses generic axis [x, y, z], UE5 uses specific motion axes:
    - XMotion/YMotion/ZMotion for linear
    - Swing1/Swing2/Twist for angular (Y/Z/X respectively)

    Args:
        axis: [x, y, z] axis from URDF (normalized)
        joint_type: URDF joint type (revolute, prismatic, continuous, fixed)

    Returns:
        Dict of UE5 constraint settings
    """
    # Normalize axis
    length = math.sqrt(sum(a * a for a in axis))
    if length > 0:
        axis = [a / length for a in axis]
    else:
        axis = [1, 0, 0]  # Default to X

    # Determine dominant axis
    abs_axis = [abs(a) for a in axis]
    max_idx = abs_axis.index(max(abs_axis))
    dominant = ["x", "y", "z"][max_idx]

    settings = {
        "x_motion": "Locked",
        "y_motion": "Locked",
        "z_motion": "Locked",
        "swing1_motion": "Locked",  # Y-axis rotation
        "swing2_motion": "Locked",  # Z-axis rotation
        "twist_motion": "Locked",  # X-axis rotation
        "dominant_axis": dominant,
    }

    if joint_type == "fixed":
        # All locked (default)
        pass
    elif joint_type == "revolute":
        # Limited rotation around axis
        if dominant == "x":
            settings["twist_motion"] = "Limited"
        elif dominant == "y":
            settings["swing1_motion"] = "Limited"
        else:  # z
            settings["swing2_motion"] = "Limited"
    elif joint_type == "continuous":
        # Free rotation around axis
        if dominant == "x":
            settings["twist_motion"] = "Free"
        elif dominant == "y":
            settings["swing1_motion"] = "Free"
        else:  # z
            settings["swing2_motion"] = "Free"
    elif joint_type == "prismatic":
        # Limited linear motion along axis
        if dominant == "x":
            settings["x_motion"] = "Limited"
        elif dominant == "y":
            settings["y_motion"] = "Limited"
        else:  # z
            settings["z_motion"] = "Limited"
    elif joint_type == "floating":
        # All free
        settings["x_motion"] = "Free"
        settings["y_motion"] = "Free"
        settings["z_motion"] = "Free"
        settings["swing1_motion"] = "Free"
        settings["swing2_motion"] = "Free"
        settings["twist_motion"] = "Free"
    elif joint_type == "planar":
        # XY linear free, Z locked, twist free
        settings["x_motion"] = "Free"
        settings["y_motion"] = "Free"
        settings["twist_motion"] = "Free"

    return settings


def create_physics_constraint(
    parent_actor: "unreal.Actor",
    child_actor: "unreal.Actor",
    joint_data: Dict,
    enhanced_joint: Optional[Dict] = None,
    verbose: bool = True,
) -> Optional["unreal.PhysicsConstraintActor"]:
    """
    Create a UE5 Physics Constraint between two actors based on URDF joint data.

    Creates a PhysicsConstraintActor at the joint position and configures it
    to connect the parent and child actors.

    NEW in v3.0: Uses enhanced_joint data for drive parameters and motor limits.

    Args:
        parent_actor: Parent link actor (StaticMeshActor)
        child_actor: Child link actor (StaticMeshActor)
        joint_data: Joint info from hierarchy JSON
            - name: Joint name
            - type: revolute, prismatic, continuous, fixed, etc.
            - axis: [x, y, z]
            - limits: {lower, upper, effort, velocity} or None
            - origin: {xyz, rpy}
        enhanced_joint: Enhanced joint data from v3.0 hierarchy (optional)
            - ue5_constraint: Full UE5 constraint parameters
            - suggested_profile: Constraint profile suggestion
        verbose: Print progress

    Returns:
        Created PhysicsConstraintActor or None if failed
    """
    try:
        joint_name = joint_data.get("name", "joint")
        joint_type = joint_data.get("type", "fixed")
        axis = joint_data.get("axis", [1, 0, 0])
        limits = joint_data.get("limits")
        origin = joint_data.get("origin", {})

        # Extract enhanced data if available
        ue5_params = None
        drive_params = None
        if enhanced_joint:
            ue5_params = enhanced_joint.get("ue5_constraint", {})
            drive_params = ue5_params.get("drive", {})
            if verbose:
                profile = enhanced_joint.get("suggested_profile", "standard")
                print(f"      [{joint_name}] Using enhanced data, profile: {profile}")

        # Get constraint motion settings from URDF joint type
        motion_settings = urdf_axis_to_ue5_constraint(axis, joint_type)

        # Get actor positions
        parent_loc = parent_actor.get_actor_location()
        child_loc = child_actor.get_actor_location()

        # Calculate joint position from parent + joint origin offset
        # The joint origin in URDF is the transform from parent link to child link
        # We need to convert from ROS (meters, left-handed) to UE5 (cm, right-handed)
        origin_xyz = origin.get("xyz", [0, 0, 0])

        # Convert ROS position to UE5: X same, Y flips, Z same, scale m->cm
        joint_offset_ue5 = unreal.Vector(
            origin_xyz[0] * 100.0,  # X stays same
            -origin_xyz[1] * 100.0,  # Y flips (ROS Y-left to UE5 Y-right)
            origin_xyz[2] * 100.0,  # Z stays same
        )

        # Joint position = parent location + joint offset
        # This is more accurate than using child location directly
        constraint_pos = unreal.Vector(
            parent_loc.x + joint_offset_ue5.x,
            parent_loc.y + joint_offset_ue5.y,
            parent_loc.z + joint_offset_ue5.z,
        )

        # Compute constraint rotation based on URDF joint axis
        # UE5 constraint default axis is X - we need to rotate to align with URDF axis
        constraint_rotation = compute_constraint_rotation_from_axis(
            axis, origin.get("rpy", [0, 0, 0])
        )

        if verbose:
            print(
                f"        Parent: {parent_actor.get_actor_label()} at ({parent_loc.x:.1f}, {parent_loc.y:.1f}, {parent_loc.z:.1f})"
            )
            print(
                f"        Child:  {child_actor.get_actor_label()} at ({child_loc.x:.1f}, {child_loc.y:.1f}, {child_loc.z:.1f})"
            )
            print(
                f"        Joint axis: {axis} -> Rotation: ({constraint_rotation.pitch:.1f}, {constraint_rotation.yaw:.1f}, {constraint_rotation.roll:.1f})"
            )
            print(
                f"        Joint offset (URDF): {origin_xyz} -> Constraint at ({constraint_pos.x:.1f}, {constraint_pos.y:.1f}, {constraint_pos.z:.1f})"
            )

        # Create Physics Constraint Actor at joint position with proper rotation
        constraint_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.PhysicsConstraintActor, constraint_pos, constraint_rotation
        )

        if not constraint_actor:
            if verbose:
                print(f"      [FAIL] Could not spawn PhysicsConstraintActor for {joint_name}")
            return None

        # Name the actor with robot prefix for multi-robot disambiguation
        # Extract robot prefix from parent actor name (e.g., ur16e_robot from ur16e_robot_base_link_visual)
        parent_label = parent_actor.get_actor_label()
        robot_prefix = ""
        # Find robot prefix by checking what comes before common link names
        for link_marker in [
            "_base_link",
            "_shoulder_link",
            "_forearm_link",
            "_wrist_",
            "_link_",
        ]:
            if link_marker in parent_label.lower():
                idx = parent_label.lower().find(link_marker)
                robot_prefix = parent_label[:idx]
                break

        if robot_prefix:
            constraint_name = f"{robot_prefix}_Constraint_{joint_name}"
        else:
            constraint_name = f"Constraint_{joint_name}"
        constraint_actor.set_actor_label(constraint_name)

        # Get the constraint component
        constraint_comp = constraint_actor.constraint_comp
        if not constraint_comp:
            # Fallback to getting by class
            constraint_comp = constraint_actor.get_component_by_class(
                unreal.PhysicsConstraintComponent
            )

        if not constraint_comp:
            if verbose:
                print(f"      [FAIL] No PhysicsConstraintComponent found for {joint_name}")
            unreal.EditorLevelLibrary.destroy_actor(constraint_actor)
            return None

        # CRITICAL: Connect the two physics bodies
        # Set constraint actors directly via editor properties
        # This is the primary method for connecting StaticMeshActors
        try:
            constraint_comp.set_editor_property("constraint_actor1", parent_actor)
            constraint_comp.set_editor_property("constraint_actor2", child_actor)
        except Exception as e:
            if verbose:
                print(f"        [WARN] Could not set constraint actors: {e}")

        # Disable collision between constrained bodies
        constraint_comp.set_disable_collision(True)

        # Configure linear motion based on joint type
        constraint_comp.set_linear_x_limit(
            getattr(
                unreal.LinearConstraintMotion,
                motion_settings["x_motion"].upper(),
                unreal.LinearConstraintMotion.LCM_LOCKED,
            ),
            0.0,
        )
        constraint_comp.set_linear_y_limit(
            getattr(
                unreal.LinearConstraintMotion,
                motion_settings["y_motion"].upper(),
                unreal.LinearConstraintMotion.LCM_LOCKED,
            ),
            0.0,
        )
        constraint_comp.set_linear_z_limit(
            getattr(
                unreal.LinearConstraintMotion,
                motion_settings["z_motion"].upper(),
                unreal.LinearConstraintMotion.LCM_LOCKED,
            ),
            0.0,
        )

        # Set angular motion
        swing1_mode = getattr(
            unreal.AngularConstraintMotion,
            "ACM_" + motion_settings["swing1_motion"].upper(),
            unreal.AngularConstraintMotion.ACM_LOCKED,
        )
        swing2_mode = getattr(
            unreal.AngularConstraintMotion,
            "ACM_" + motion_settings["swing2_motion"].upper(),
            unreal.AngularConstraintMotion.ACM_LOCKED,
        )
        twist_mode = getattr(
            unreal.AngularConstraintMotion,
            "ACM_" + motion_settings["twist_motion"].upper(),
            unreal.AngularConstraintMotion.ACM_LOCKED,
        )

        constraint_comp.set_angular_swing1_limit(swing1_mode, 45.0)
        constraint_comp.set_angular_swing2_limit(swing2_mode, 45.0)
        constraint_comp.set_angular_twist_limit(twist_mode, 45.0)

        # Apply limits if present (convert radians to degrees)
        if limits and joint_type in ["revolute", "prismatic"]:
            lower = limits.get("lower", 0.0)
            upper = limits.get("upper", 0.0)

            if joint_type == "revolute":
                # Angular limits in degrees
                lower_deg = math.degrees(lower)
                upper_deg = math.degrees(upper)
                limit_angle = max(abs(lower_deg), abs(upper_deg))

                if motion_settings["dominant_axis"] == "x":
                    constraint_comp.set_angular_twist_limit(
                        unreal.AngularConstraintMotion.ACM_LIMITED, limit_angle
                    )
                elif motion_settings["dominant_axis"] == "y":
                    constraint_comp.set_angular_swing1_limit(
                        unreal.AngularConstraintMotion.ACM_LIMITED, limit_angle
                    )
                else:
                    constraint_comp.set_angular_swing2_limit(
                        unreal.AngularConstraintMotion.ACM_LIMITED, limit_angle
                    )
            else:
                # Linear limits in cm (convert from meters)
                lower_cm = lower * 100.0
                upper_cm = upper * 100.0
                limit_dist = max(abs(lower_cm), abs(upper_cm))

                if motion_settings["dominant_axis"] == "x":
                    constraint_comp.set_linear_x_limit(
                        unreal.LinearConstraintMotion.LCM_LIMITED, limit_dist
                    )
                elif motion_settings["dominant_axis"] == "y":
                    constraint_comp.set_linear_y_limit(
                        unreal.LinearConstraintMotion.LCM_LIMITED, limit_dist
                    )
                else:
                    constraint_comp.set_linear_z_limit(
                        unreal.LinearConstraintMotion.LCM_LIMITED, limit_dist
                    )

        # NEW v3.0: Apply enhanced drive parameters if available
        if drive_params and drive_params.get("enabled"):
            try:
                # Configure angular drive for revolute/continuous joints
                if joint_type in ["revolute", "continuous"]:
                    # Get drive settings
                    stiffness = drive_params.get("stiffness", 0.0)
                    damping = drive_params.get("damping", 10.0)
                    max_force = drive_params.get("max_force", 100.0)

                    # Enable angular drive on the twist axis (most common for revolute)
                    try:
                        # Set angular drive mode
                        constraint_comp.set_editor_property(
                            "angular_drive_mode",
                            unreal.AngularDriveMode.TWIST_AND_SWING,
                        )

                        # Configure twist drive
                        constraint_comp.set_angular_velocity_drive_twist_and_swing(True, False)
                        constraint_comp.set_angular_drive_params(stiffness, damping, max_force)

                        if verbose:
                            print(
                                f"        [DRIVE] stiffness={stiffness}, damping={damping}, max_force={max_force}"
                            )
                    except Exception as drive_err:
                        if verbose:
                            print(f"        [DRIVE] Could not set drive params: {drive_err}")

                # Configure linear drive for prismatic joints
                elif joint_type == "prismatic":
                    stiffness = drive_params.get("stiffness", 0.0)
                    damping = drive_params.get("damping", 50.0)
                    max_force = drive_params.get("max_force", 100.0)

                    try:
                        constraint_comp.set_linear_velocity_drive(True, True, True)
                        constraint_comp.set_linear_drive_params(stiffness, damping, max_force)

                        if verbose:
                            print(
                                f"        [DRIVE] linear stiffness={stiffness}, damping={damping}"
                            )
                    except Exception as drive_err:
                        if verbose:
                            print(f"        [DRIVE] Could not set linear drive: {drive_err}")
            except Exception as e:
                if verbose:
                    print(f"        [DRIVE] Drive setup failed: {e}")

        if verbose:
            print(
                f"      [CONSTRAINT] {joint_name}: {joint_type} on {motion_settings['dominant_axis']}-axis"
            )

        return constraint_actor

    except Exception as e:
        if verbose:
            print(f"      [ERROR] Failed to create constraint: {e}")
        return None


def create_robot_constraints(
    robot_name_or_path: str,
    actors_by_link: Dict[str, List["unreal.Actor"]] = None,
    verbose: bool = True,
) -> int:
    """
    Create physics constraints for all joints in a robot.

    This reads the hierarchy JSON and creates UE5 Physics Constraint Components
    between parent-child link pairs according to URDF joint definitions.

    Args:
        robot_name_or_path: Robot name or path to hierarchy JSON
        actors_by_link: Optional pre-found actors dict. If None, will search.
        verbose: Print progress

    Returns:
        Number of constraints created
    """
    if verbose:
        print("\n" + "=" * 60)
        print("  ROA Physics Constraint Creator")
        print("=" * 60)

    # Find hierarchy file
    hierarchy_path = find_hierarchy_file(robot_name_or_path)
    if not hierarchy_path:
        print(f"[ERROR] Could not find hierarchy file for: {robot_name_or_path}")
        return 0

    # Load hierarchy
    hierarchy_data = load_hierarchy(hierarchy_path)
    if not hierarchy_data:
        return 0

    robot_name = hierarchy_data.get("robot_name", "robot")
    hierarchy = hierarchy_data.get("hierarchy", {})
    joints_list = hierarchy.get("joints", [])

    if not joints_list:
        print(f"[WARNING] No joints found in hierarchy. Is this version 2.2+?")
        print(f"          Re-convert the URDF to generate joints data.")
        return 0

    if verbose:
        print(f"\n[INFO] Robot: {robot_name}")
        print(f"       Joints: {len(joints_list)}")

    # Find actors if not provided
    if actors_by_link is None:
        link_names = list(hierarchy.get("nodes", {}).keys())
        actors_by_link = find_robot_actors(robot_name, link_names)

    if not actors_by_link:
        print(f"[ERROR] No actors found for robot: {robot_name}")
        return 0

    # Create constraints
    constraints_created = 0
    if verbose:
        print(f"\n[INFO] Creating physics constraints...")

    for joint in joints_list:
        parent_link = joint.get("parent_link")
        child_link = joint.get("child_link")
        joint_type = joint.get("type", "fixed")

        # Skip if we can't find both actors
        parent_actors = actors_by_link.get(parent_link, [])
        child_actors = actors_by_link.get(child_link, [])

        if not parent_actors or not child_actors:
            if verbose:
                print(
                    f"      [SKIP] {joint.get('name')}: Missing actors (parent={len(parent_actors)}, child={len(child_actors)})"
                )
            continue

        # Use first actor of each (usually there's only one per link for visual)
        parent_actor = parent_actors[0]
        child_actor = child_actors[0]

        # Create constraint
        constraint = create_physics_constraint(parent_actor, child_actor, joint, verbose)
        if constraint:
            constraints_created += 1

    if verbose:
        print(f"\n[RESULT] Created {constraints_created}/{len(joints_list)} constraints")
        print("=" * 60)

    return constraints_created


# =============================================================================
# PYCO - Full Robot Setup (Position + Colors + Constraints)
# =============================================================================


def PYCO(
    robot_name_or_path: str,
    origin: List[float] = None,
    apply_colors: bool = True,
    apply_constraints: bool = True,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    PYCO - Complete robot setup: Position, Colors, and Constraints.

    This is the all-in-one function that:
    1. Positions all robot parts correctly (assembly)
    2. Applies URDF material colors to each link
    3. Creates physics constraints between joints

    Args:
        robot_name_or_path: Robot name or path to hierarchy JSON
        origin: Assembly origin [x, y, z] in cm. Default [0, 0, 50]
        apply_colors: Whether to apply URDF colors (default True)
        apply_constraints: Whether to create physics constraints (default True)
        verbose: Print detailed progress

    Returns:
        Dict with results:
        {
            'success': bool,
            'actors_positioned': int,
            'colors_applied': int,
            'constraints_created': int,
            'robot_name': str
        }
    """
    if origin is None:
        origin = [0.0, 0.0, 50.0]

    result = {
        "success": False,
        "actors_positioned": 0,
        "colors_applied": 0,
        "constraints_created": 0,
        "robot_name": "",
    }

    print("")
    print("╔════════════════════════════════════════════════════════════╗")
    print("║           PYCO - ROA Complete Robot Setup                  ║")
    print("║     (Position + Y-Materials + CO-nstraints)                ║")
    print("╚════════════════════════════════════════════════════════════╝")

    # Step 1: Find hierarchy file
    print(f"\n[1/4] Loading robot data: {robot_name_or_path}")

    hierarchy_path = find_hierarchy_file(robot_name_or_path)
    if not hierarchy_path:
        print(f"[ERROR] Could not find hierarchy file for: {robot_name_or_path}")
        return result

    hierarchy_data = load_hierarchy(hierarchy_path)
    if not hierarchy_data:
        print("[ERROR] Failed to load hierarchy data")
        return result

    robot_name = hierarchy_data.get("robot_name", "robot")
    result["robot_name"] = robot_name
    hierarchy = hierarchy_data.get("hierarchy", {})

    print(f"      Robot: {robot_name}")
    print(f"      Version: {hierarchy_data.get('version', 'unknown')}")

    # Step 2: Compute transforms and find actors
    print("\n[2/4] Computing transforms & finding actors...")

    transforms = compute_link_transforms(hierarchy_data, origin)
    link_names = list(transforms.keys())
    actors_by_link = find_robot_actors(robot_name, link_names)

    if not actors_by_link:
        print(f"[ERROR] No actors found for robot: {robot_name}")
        print("        Make sure you've imported the USD file first!")
        return result

    total_actors = sum(len(a) for a in actors_by_link.values())
    print(f"      Found {total_actors} actors for {len(actors_by_link)} links")

    # Step 3: Position all actors
    print("\n[3/4] Positioning robot parts...")

    positioned = 0
    for link_name, actor_list in actors_by_link.items():
        if link_name in transforms:
            tf = transforms[link_name]
            location = unreal.Vector(tf["position"][0], tf["position"][1], tf["position"][2])
            rotation = quaternion_to_rotator(tf["quaternion"])

            for actor in actor_list:
                actor.set_actor_location(location, False, False)
                actor.set_actor_rotation(rotation, False)
                positioned += 1

            if verbose:
                print(f"      [POS] {link_name} ({len(actor_list)} actors)")

    result["actors_positioned"] = positioned

    # Step 4: Apply colors from URDF materials
    if apply_colors:
        print("\n[4/4] Applying materials & colors...")

        colors_applied = 0
        for link_name, actor_list in actors_by_link.items():
            color = get_link_color(link_name, hierarchy_data)
            if color:
                for actor in actor_list:
                    apply_material_to_actor(actor, color, link_name, verbose)
                colors_applied += 1
                if verbose:
                    print(
                        f"      [COL] {link_name}: RGBA({color[0]:.2f}, {color[1]:.2f}, {color[2]:.2f}, {color[3] if len(color) > 3 else 1.0:.2f})"
                    )
            else:
                if verbose:
                    print(f"      [---] {link_name}: No color defined")

        result["colors_applied"] = colors_applied
    else:
        print("\n[4/4] Skipping colors (disabled)")

    # Step 5: Create physics constraints
    if apply_constraints:
        print("\n[5/5] Creating physics constraints...")

        joints_list = hierarchy.get("joints", [])
        if joints_list:
            constraints = 0
            for joint in joints_list:
                parent_link = joint.get("parent_link")
                child_link = joint.get("child_link")

                parent_actors = actors_by_link.get(parent_link, [])
                child_actors = actors_by_link.get(child_link, [])

                if parent_actors and child_actors:
                    constraint = create_physics_constraint(
                        parent_actors[0], child_actors[0], joint, verbose
                    )
                    if constraint:
                        constraints += 1
                elif verbose:
                    print(f"      [SKIP] {joint.get('name')}: Missing actors")

            result["constraints_created"] = constraints
        else:
            print("      [WARN] No joints data found (need hierarchy v2.2+)")
    else:
        print("\n[5/5] Skipping constraints (disabled)")

    # Summary
    result["success"] = positioned > 0

    print("")
    print("╔════════════════════════════════════════════════════════════╗")
    print(f"║  PYCO COMPLETE: {robot_name}")
    print("╠════════════════════════════════════════════════════════════╣")
    print(f"║  Parts Positioned:    {result['actors_positioned']:4d}")
    print(f"║  Colors Applied:      {result['colors_applied']:4d}")
    print(f"║  Constraints Created: {result['constraints_created']:4d}")
    print("╚════════════════════════════════════════════════════════════╝")

    return result


# Convenience alias
pyco = PYCO  # lowercase version for easier typing


# =============================================================================
# ROC PREPARATION - Generate robot specs for Robot Operator Controller
# =============================================================================


def generate_roc_specs(robot_name_or_path: str, robot_id: str = None) -> Optional[Dict[str, Any]]:
    """
    Generate robot specifications for ROC (Robot Operator Controller).

    This prepares the robot data in the format ROC expects, enabling:
    - Automatic adaptive UI configuration (sliders for each joint)
    - Joint limits and safety bounds
    - Robot capabilities detection (gripper, mobile base, etc.)
    - One-step closer to ROC taking control of the robot

    Args:
        robot_name_or_path: Robot name or path to hierarchy JSON file
        robot_id: Optional unique ID for this robot instance (auto-generated if not provided)

    Returns:
        ROC-compatible robot specification dictionary, or None if failed

    Format (matches /fti/robot_specs topic):
        {
            "robot_id": "robot_001",
            "robot_name": "ur20",
            "robot_type": "6-dof-arm",
            "joints": [
                {"name": "joint1", "type": "revolute", "limits": [-3.14, 3.14], "velocity_limit": 1.0},
                ...
            ],
            "capabilities": {
                "has_gripper": false,
                "has_mobile_base": false,
                "is_articulated_arm": true,
                "dof": 6
            },
            "content_path": "/Game/Robots/ur20",
            "ready_for_control": true
        }
    """
    # Find hierarchy file
    hierarchy_path = find_hierarchy_file(robot_name_or_path)
    if not hierarchy_path:
        print(f"[ERROR] Could not find hierarchy file for: {robot_name_or_path}")
        return None

    # Load hierarchy
    hierarchy_data = load_hierarchy(hierarchy_path)
    if not hierarchy_data:
        return None

    robot_name = hierarchy_data.get("robot_name", "robot")
    hierarchy = hierarchy_data.get("hierarchy", {})

    # Generate unique robot ID if not provided
    if not robot_id:
        import time

        robot_id = f"{robot_name}_{int(time.time()) % 10000:04d}"

    # Extract joint information
    joints_list = hierarchy.get("joints", [])
    roc_joints = []

    for joint in joints_list:
        joint_type = joint.get("type", "fixed")

        # Skip fixed joints (not controllable)
        if joint_type == "fixed":
            continue

        # Get joint limits
        limits = joint.get("limits", {})
        lower = limits.get("lower", -3.14159)  # Default to ±π
        upper = limits.get("upper", 3.14159)
        velocity_limit = limits.get("velocity", 1.0)
        effort_limit = limits.get("effort", 100.0)

        roc_joint = {
            "name": joint.get("name", ""),
            "type": joint_type,
            "limits": [lower, upper],
            "velocity_limit": velocity_limit,
            "effort_limit": effort_limit,
            "parent_link": joint.get("parent_link", ""),
            "child_link": joint.get("child_link", ""),
            "axis": joint.get("axis", [0, 0, 1]),
        }
        roc_joints.append(roc_joint)

    # Detect capabilities
    dof = len(roc_joints)
    has_gripper = any(
        "gripper" in j["name"].lower() or "finger" in j["name"].lower() for j in roc_joints
    )
    has_mobile_base = any(
        "wheel" in j["name"].lower() or "caster" in j["name"].lower() for j in roc_joints
    )
    is_articulated_arm = dof >= 4 and not has_mobile_base

    # Check for submechanism data (v3.0+)
    submech = hierarchy_data.get("submechanisms", {})
    robot_type = submech.get("robot_type", "unknown")
    if robot_type == "unknown":
        # Auto-detect robot type
        if is_articulated_arm:
            robot_type = f"{dof}-dof-arm"
        elif has_mobile_base:
            robot_type = "mobile-robot"
        else:
            robot_type = "mechanism"

    # Build complete specs
    roc_specs = {
        "robot_id": robot_id,
        "robot_name": robot_name,
        "robot_type": robot_type,
        "joints": roc_joints,
        "capabilities": {
            "has_gripper": has_gripper,
            "has_mobile_base": has_mobile_base,
            "is_articulated_arm": is_articulated_arm,
            "dof": dof,
        },
        "content_path": f"/Game/Robots/{robot_name}",
        "hierarchy_path": hierarchy_path,
        "ready_for_control": True,
        "version": hierarchy_data.get("version", "2.0"),
    }

    print(f"\n[ROC] Robot specifications generated:")
    print(f"      Robot ID:   {robot_id}")
    print(f"      Robot Name: {robot_name}")
    print(f"      Robot Type: {robot_type}")
    print(f"      DOF:        {dof}")
    print(f"      Joints:     {len(roc_joints)}")
    print(f"      Gripper:    {has_gripper}")
    print(f"      Mobile:     {has_mobile_base}")

    return roc_specs


def save_roc_specs(robot_name_or_path: str, output_path: str = None) -> Optional[str]:
    """
    Generate and save ROC specs to a JSON file.

    This file can be:
    1. Used by ROC standalone desktop app
    2. Published to /fti/robot_specs topic when ROS2 is available
    3. Read by UE5 ROC widget for adaptive UI

    Args:
        robot_name_or_path: Robot name or path to hierarchy JSON
        output_path: Output file path (auto-generated if not provided)

    Returns:
        Path to saved specs file, or None if failed
    """
    specs = generate_roc_specs(robot_name_or_path)
    if not specs:
        return None

    # Generate output path
    if not output_path:
        robot_name = specs["robot_name"]
        output_dir = tempfile.gettempdir()
        output_path = os.path.join(output_dir, f"{robot_name}_roc_specs.json")

    # Save to file
    try:
        with open(output_path, "w") as f:
            json.dump(specs, f, indent=2)
        print(f"[ROC] Specs saved to: {output_path}")
        return output_path
    except Exception as e:
        print(f"[ERROR] Failed to save ROC specs: {e}")
        return None


def prepare_for_roc(robot_name_or_path: str, auto_publish: bool = False) -> bool:
    """
    Complete preparation for ROC control after robot assembly.

    This is the recommended function to call after assemble_robot() to enable
    ROC to automatically configure and control the robot.

    What this does:
    1. Generates robot specifications in ROC format
    2. Saves specs to a file for ROC desktop app or UE5 widget
    3. Optionally publishes to /fti/robot_specs topic (if ROS2 available)

    After calling this, ROC can:
    - Automatically configure joint sliders
    - Know joint limits for safety bounds
    - Enable gripper controls if detected
    - Take control of the robot faster

    Args:
        robot_name_or_path: Robot name or hierarchy JSON path
        auto_publish: If True and ROS2 available, publish to /fti/robot_specs

    Returns:
        True if preparation succeeded
    """
    print("\n" + "=" * 60)
    print("  ROC PREPARATION")
    print("=" * 60)

    # Generate and save specs
    specs_path = save_roc_specs(robot_name_or_path)
    if not specs_path:
        return False

    # Try to publish if ROS2 is available and auto_publish is True
    if auto_publish:
        try:
            # Try importing ROS2 publisher
            import rclpy
            from rclpy.node import Node
            from std_msgs.msg import String

            if not rclpy.ok():
                rclpy.init()

            # Create temporary node for publishing
            node = Node("fti_roc_bridge")
            publisher = node.create_publisher(String, "/fti/robot_specs", 10)

            # Publish specs
            msg = String()
            msg.data = json.dumps(generate_roc_specs(robot_name_or_path))
            publisher.publish(msg)

            print("[ROC] Published robot specs to /fti/robot_specs topic")

            # Cleanup
            node.destroy_node()

        except ImportError:
            print("[ROC] ROS2 not available - specs saved to file for manual use")
        except Exception as e:
            print(f"[ROC] ROS2 publish failed: {e} - specs saved to file")

    print("\n[ROC] ✓ Robot is ready for ROC control!")
    print(f"      Specs file: {specs_path}")
    print("=" * 60)

    return True


# =============================================================================
# MODULE INITIALIZATION
# =============================================================================

print("")
print("ROA Universal Robot Assembler loaded!")
print("")
print("Commands:")
print("  PYCO('robot_name')               - FULL SETUP: Position + Colors + Constraints")
print("  assemble_robot('robot_name')     - Position only (fast, no physics)")
print("  create_robot_constraints('name') - Constraints only (if already positioned)")
print("  prepare_for_roc('robot_name')    - Prepare robot for ROC control")
print("  list_robots()                    - List available robot hierarchy files")
print("  reset_robot('robot_name')        - Reset robot parts to origin")
print("")
print("Workflow:")
print("  1. Import USD file into UE5")
print("  2. assemble_robot('ur20')           # Position all parts correctly")
print("  3. create_robot_constraints('ur20') # Add physics joints")
print("  4. prepare_for_roc('ur20')          # Enable ROC control")
print("")
