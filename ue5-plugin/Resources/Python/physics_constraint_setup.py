"""
physics_constraint_setup.py
ROA - Robot Operations & Automation

Physics Constraint Setup Module
Creates UE5 PhysicsConstraintComponents from USD Physics joint data.

This module bridges USD Physics schema to UE5 Physics Constraints:
- UsdPhysicsRevoluteJoint → Angular constraint (twist free, swing locked)
- UsdPhysicsPrismaticJoint → Linear constraint (one axis free)
- UsdPhysicsFixedJoint → Fully locked constraint

USD Physics APIs read:
- Joint type (Revolute/Prismatic/Fixed)
- body0, body1 relationships
- axis (X/Y/Z)
- lowerLimit, upperLimit
- DriveAPI: stiffness, damping, maxForce, targetPosition, targetVelocity

Author: ROA Team
Date: January 2026
"""

import math
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

# Try to import Unreal modules
try:
    import unreal
    HAS_UNREAL = True
except ImportError:
    HAS_UNREAL = False
    print("WARNING: Unreal module not available. Running in standalone mode.")

# Try to import OpenUSD
try:
    from pxr import Usd, UsdPhysics, UsdGeom, Gf
    HAS_USD = True
except ImportError:
    HAS_USD = False
    print("WARNING: OpenUSD (pxr) not available.")


class JointType(Enum):
    """Joint types supported by ROA"""
    REVOLUTE = "revolute"
    PRISMATIC = "prismatic"
    FIXED = "fixed"
    CONTINUOUS = "continuous"  # Revolute without limits


@dataclass
class JointDriveParams:
    """Drive parameters for joint motors"""
    stiffness: float = 1000.0      # Position drive strength
    damping: float = 100.0         # Velocity drive strength
    max_force: float = 1000.0      # Maximum force/torque
    target_position: float = 0.0   # Target position (rad or m)
    target_velocity: float = 0.0   # Target velocity (rad/s or m/s)
    drive_type: str = "force"      # "force" or "acceleration"


@dataclass
class JointLimits:
    """Joint limit parameters"""
    lower: float = 0.0             # Lower limit (deg or cm)
    upper: float = 0.0             # Upper limit (deg or cm)
    has_limits: bool = True        # Whether limits are active


@dataclass
class PhysicsJointData:
    """Complete physics joint data parsed from USD"""
    name: str
    joint_type: JointType
    
    # Body references (USD paths)
    body0_path: str = ""           # Parent link path
    body1_path: str = ""           # Child link path
    
    # Axis of motion
    axis: str = "X"                # X, Y, or Z
    
    # Local poses
    local_pos0: Tuple[float, float, float] = (0, 0, 0)
    local_rot0: Tuple[float, float, float, float] = (1, 0, 0, 0)  # Quaternion wxyz
    local_pos1: Tuple[float, float, float] = (0, 0, 0)
    local_rot1: Tuple[float, float, float, float] = (1, 0, 0, 0)
    
    # Limits (in UE5 units: degrees for angular, cm for linear)
    limits: JointLimits = field(default_factory=JointLimits)
    
    # Drive parameters
    drive: JointDriveParams = field(default_factory=JointDriveParams)


@dataclass
class PhysicsSceneData:
    """Physics scene settings from USD"""
    gravity_direction: Tuple[float, float, float] = (0, 0, -1)
    gravity_magnitude: float = 981.0  # cm/s² (UE5 units)


@dataclass
class FilteredPairsData:
    """Self-collision filtering data from USD"""
    # List of (body0_path, body1_path) pairs that should not collide
    pairs: List[Tuple[str, str]] = field(default_factory=list)


def parse_usd_physics_scene(usd_path: str) -> Optional[PhysicsSceneData]:
    """
    Parse PhysicsScene from USD file to get gravity settings.
    
    Args:
        usd_path: Path to USD file
        
    Returns:
        PhysicsSceneData or None if no scene found
    """
    if not HAS_USD:
        return None
    
    try:
        stage = Usd.Stage.Open(usd_path)
        if not stage:
            return None
        
        # Look for PhysicsScene prim
        for prim in stage.Traverse():
            if prim.IsA(UsdPhysics.Scene):
                scene = UsdPhysics.Scene(prim)
                
                data = PhysicsSceneData()
                
                # Get gravity direction
                gravity_dir = scene.GetGravityDirectionAttr().Get()
                if gravity_dir:
                    data.gravity_direction = (gravity_dir[0], gravity_dir[1], gravity_dir[2])
                
                # Get gravity magnitude (convert m/s² to cm/s² for UE5)
                gravity_mag = scene.GetGravityMagnitudeAttr().Get()
                if gravity_mag:
                    data.gravity_magnitude = gravity_mag * 100.0  # m to cm
                
                print(f"Parsed PhysicsScene: gravity={data.gravity_direction} @ {data.gravity_magnitude} cm/s²")
                return data
                
    except Exception as e:
        print(f"Error parsing PhysicsScene: {e}")
    
    return None


def parse_usd_filtered_pairs(usd_path: str) -> FilteredPairsData:
    """
    Parse FilteredPairsAPI from USD file to get self-collision filtering.
    
    Args:
        usd_path: Path to USD file
        
    Returns:
        FilteredPairsData with collision pairs to disable
    """
    if not HAS_USD:
        return FilteredPairsData()
    
    data = FilteredPairsData()
    
    try:
        stage = Usd.Stage.Open(usd_path)
        if not stage:
            return data
        
        # Look for prims with FilteredPairsAPI
        for prim in stage.Traverse():
            if prim.HasAPI(UsdPhysics.FilteredPairsAPI):
                filtered_api = UsdPhysics.FilteredPairsAPI(prim)
                targets = filtered_api.GetFilteredPairsRel().GetTargets()
                
                # Targets are in pairs: [body0, body1, body0, body1, ...]
                for i in range(0, len(targets) - 1, 2):
                    pair = (str(targets[i]), str(targets[i + 1]))
                    data.pairs.append(pair)
                
                if data.pairs:
                    print(f"Parsed {len(data.pairs)} filtered collision pairs")
                    
    except Exception as e:
        print(f"Error parsing FilteredPairsAPI: {e}")
    
    return data


def parse_usd_physics_joints(usd_path: str) -> List[PhysicsJointData]:
    """
    Parse all physics joints from a USD file.
    
    Args:
        usd_path: Path to USD file with physics joints
        
    Returns:
        List of PhysicsJointData objects
    """
    if not HAS_USD:
        print("ERROR: OpenUSD not available")
        return []
    
    joints = []
    
    try:
        stage = Usd.Stage.Open(usd_path)
        if not stage:
            print(f"ERROR: Could not open USD stage: {usd_path}")
            return joints
        
        print(f"Parsing physics joints from: {usd_path}")
        
        # Traverse all prims looking for physics joints
        for prim in stage.Traverse():
            joint_data = None
            
            if prim.IsA(UsdPhysics.RevoluteJoint):
                joint_data = _parse_revolute_joint(prim)
            elif prim.IsA(UsdPhysics.PrismaticJoint):
                joint_data = _parse_prismatic_joint(prim)
            elif prim.IsA(UsdPhysics.FixedJoint):
                joint_data = _parse_fixed_joint(prim)
            
            if joint_data:
                joints.append(joint_data)
                print(f"  Found {joint_data.joint_type.value} joint: {joint_data.name}")
        
        print(f"Parsed {len(joints)} physics joints")
        
    except Exception as e:
        print(f"ERROR parsing USD physics: {e}")
        import traceback
        traceback.print_exc()
    
    return joints


def _parse_revolute_joint(prim) -> PhysicsJointData:
    """Parse a PhysicsRevoluteJoint prim."""
    joint = UsdPhysics.RevoluteJoint(prim)
    
    data = PhysicsJointData(
        name=prim.GetName(),
        joint_type=JointType.REVOLUTE
    )
    
    # Get body references
    body0_targets = joint.GetBody0Rel().GetTargets()
    body1_targets = joint.GetBody1Rel().GetTargets()
    
    if body0_targets:
        data.body0_path = str(body0_targets[0])
    if body1_targets:
        data.body1_path = str(body1_targets[0])
    
    # Get axis
    axis_attr = joint.GetAxisAttr()
    if axis_attr:
        data.axis = axis_attr.Get() or "X"
    
    # Get local poses
    local_pos0 = joint.GetLocalPos0Attr().Get()
    local_pos1 = joint.GetLocalPos1Attr().Get()
    local_rot0 = joint.GetLocalRot0Attr().Get()
    local_rot1 = joint.GetLocalRot1Attr().Get()
    
    if local_pos0:
        # Convert from meters to centimeters
        data.local_pos0 = (local_pos0[0] * 100, local_pos0[1] * 100, local_pos0[2] * 100)
    if local_pos1:
        data.local_pos1 = (local_pos1[0] * 100, local_pos1[1] * 100, local_pos1[2] * 100)
    if local_rot0:
        data.local_rot0 = (local_rot0.GetReal(), local_rot0.GetImaginary()[0], 
                           local_rot0.GetImaginary()[1], local_rot0.GetImaginary()[2])
    if local_rot1:
        data.local_rot1 = (local_rot1.GetReal(), local_rot1.GetImaginary()[0],
                           local_rot1.GetImaginary()[1], local_rot1.GetImaginary()[2])
    
    # Get limits (already in degrees from USD)
    lower = joint.GetLowerLimitAttr().Get()
    upper = joint.GetUpperLimitAttr().Get()
    
    # Check if this is a continuous joint (no effective limits)
    if lower is not None and upper is not None:
        if abs(upper - lower) >= 360:
            data.limits = JointLimits(lower=0, upper=0, has_limits=False)
        else:
            data.limits = JointLimits(lower=lower, upper=upper, has_limits=True)
    else:
        data.limits = JointLimits(has_limits=False)
    
    # Get drive parameters
    data.drive = _parse_drive_api(prim, data.axis, is_angular=True)
    
    return data


def _parse_prismatic_joint(prim) -> PhysicsJointData:
    """Parse a PhysicsPrismaticJoint prim."""
    joint = UsdPhysics.PrismaticJoint(prim)
    
    data = PhysicsJointData(
        name=prim.GetName(),
        joint_type=JointType.PRISMATIC
    )
    
    # Get body references
    body0_targets = joint.GetBody0Rel().GetTargets()
    body1_targets = joint.GetBody1Rel().GetTargets()
    
    if body0_targets:
        data.body0_path = str(body0_targets[0])
    if body1_targets:
        data.body1_path = str(body1_targets[0])
    
    # Get axis
    axis_attr = joint.GetAxisAttr()
    if axis_attr:
        data.axis = axis_attr.Get() or "X"
    
    # Get local poses
    local_pos0 = joint.GetLocalPos0Attr().Get()
    local_pos1 = joint.GetLocalPos1Attr().Get()
    
    if local_pos0:
        # Convert from meters to centimeters
        data.local_pos0 = (local_pos0[0] * 100, local_pos0[1] * 100, local_pos0[2] * 100)
    if local_pos1:
        data.local_pos1 = (local_pos1[0] * 100, local_pos1[1] * 100, local_pos1[2] * 100)
    
    # Get limits (convert meters to centimeters)
    lower = joint.GetLowerLimitAttr().Get()
    upper = joint.GetUpperLimitAttr().Get()
    
    if lower is not None and upper is not None:
        data.limits = JointLimits(lower=lower * 100, upper=upper * 100, has_limits=True)
    else:
        data.limits = JointLimits(has_limits=False)
    
    # Get drive parameters
    data.drive = _parse_drive_api(prim, data.axis, is_angular=False)
    
    return data


def _parse_fixed_joint(prim) -> PhysicsJointData:
    """Parse a PhysicsFixedJoint prim."""
    joint = UsdPhysics.FixedJoint(prim)
    
    data = PhysicsJointData(
        name=prim.GetName(),
        joint_type=JointType.FIXED
    )
    
    # Get body references
    body0_targets = joint.GetBody0Rel().GetTargets()
    body1_targets = joint.GetBody1Rel().GetTargets()
    
    if body0_targets:
        data.body0_path = str(body0_targets[0])
    if body1_targets:
        data.body1_path = str(body1_targets[0])
    
    # Fixed joints have no axis, limits, or drive
    data.limits = JointLimits(has_limits=False)
    
    return data


def _parse_drive_api(prim, axis: str, is_angular: bool) -> JointDriveParams:
    """
    Parse DriveAPI parameters from a joint prim.
    
    USD DriveAPI uses instance names like "rotX", "rotY", "rotZ" for angular
    and "transX", "transY", "transZ" for linear.
    """
    drive = JointDriveParams()
    
    # Determine drive instance name
    if is_angular:
        instance_name = f"rot{axis}"
    else:
        instance_name = f"trans{axis}"
    
    # Check if DriveAPI is applied
    if not prim.HasAPI(UsdPhysics.DriveAPI, instance_name):
        return drive
    
    drive_api = UsdPhysics.DriveAPI.Get(prim, instance_name)
    if not drive_api:
        return drive
    
    # Read drive parameters
    stiffness = drive_api.GetStiffnessAttr().Get()
    damping = drive_api.GetDampingAttr().Get()
    max_force = drive_api.GetMaxForceAttr().Get()
    target_pos = drive_api.GetTargetPositionAttr().Get()
    target_vel = drive_api.GetTargetVelocityAttr().Get()
    drive_type = drive_api.GetTypeAttr().Get()
    
    if stiffness is not None:
        drive.stiffness = stiffness
    if damping is not None:
        drive.damping = damping
    if max_force is not None:
        drive.max_force = max_force
    if target_pos is not None:
        drive.target_position = target_pos
    if target_vel is not None:
        drive.target_velocity = target_vel
    if drive_type:
        drive.drive_type = str(drive_type)
    
    return drive


# ═══════════════════════════════════════════════════════════════════════════
# UE5 Physics Constraint Creation
# ═══════════════════════════════════════════════════════════════════════════

def _calculate_constraint_rotation(joint: PhysicsJointData) -> 'unreal.Rotator':
    """
    Calculate the proper rotation for a constraint based on joint's actual orientation.
    
    This dynamically calculates the constraint rotation from the joint's local quaternion
    rotation, ensuring the Y-axis (and all axes) align with the actual joint frame,
    not a predefined orientation.
    
    UE5 PhysicsConstraint default orientation:
    - Twist axis = X (the axis that allows rotation for revolute joints)
    - Swing1 = Y, Swing2 = Z
    
    Strategy:
    1. Convert joint's local quaternion (local_rot0) to euler angles
    2. This gives us the joint's actual orientation in space
    3. Apply axis-specific rotation to align UE5's X-axis with the joint's rotation axis
    4. This ensures the constraint frame follows the joint's orientation dynamically
    
    Coordinate system notes:
    - USD/URDF typically use right-handed Z-up
    - UE5 uses left-handed Z-up  
    - Y-flip is applied during position conversion
    """
    if not HAS_UNREAL:
        return None
    
    import math
    
    # Get the joint's local rotation quaternion (w, x, y, z)
    w, x, y, z = joint.local_rot0
    
    # Convert quaternion to euler angles (Tait-Bryan angles, ZYX convention for UE5)
    # This gives us the joint frame's actual orientation
    
    # Roll (rotation around X-axis)
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.degrees(math.atan2(sinr_cosp, cosr_cosp))
    
    # Pitch (rotation around Y-axis)
    sinp = 2.0 * (w * y - z * x)
    sinp = max(-1.0, min(1.0, sinp))  # Clamp to avoid math domain error
    pitch = math.degrees(math.asin(sinp))
    
    # Yaw (rotation around Z-axis)
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.degrees(math.atan2(siny_cosp, cosy_cosp))
    
    # Now apply the axis-specific rotation offset
    # This rotates the constraint so its twist axis (X) aligns with the joint's rotation axis
    # The rotation happens in the joint's LOCAL frame, not world frame
    axis = joint.axis.upper() if joint.axis else "X"
    
    # Create rotation offset based on joint axis
    # These offsets rotate UE5's default X-axis to align with the specified axis
    if axis == "X":
        # Joint rotates around local X - UE5 constraint X-axis is already correct
        axis_roll_offset = 0.0
        axis_pitch_offset = 0.0
        axis_yaw_offset = 0.0
        
    elif axis == "Y":
        # Joint rotates around local Y
        # Rotate constraint 90° around local Z to align X->Y
        axis_roll_offset = 0.0
        axis_pitch_offset = 0.0  
        axis_yaw_offset = 90.0
        
    elif axis == "Z":
        # Joint rotates around local Z
        # Rotate constraint -90° around local Y to align X->Z
        axis_roll_offset = 0.0
        axis_pitch_offset = -90.0
        axis_yaw_offset = 0.0
    else:
        axis_roll_offset = 0.0
        axis_pitch_offset = 0.0
        axis_yaw_offset = 0.0
    
    # Combine the joint's orientation with the axis offset
    # This composition ensures the constraint follows the joint's actual rotation
    final_roll = roll + axis_roll_offset
    final_pitch = pitch + axis_pitch_offset
    final_yaw = yaw + axis_yaw_offset
    
    print(f"  [Rotation] Joint '{joint.name}' axis={axis}")
    print(f"    Joint orientation: R={roll:.1f}°, P={pitch:.1f}°, Y={yaw:.1f}°")
    print(f"    Axis offset: R={axis_roll_offset:.1f}°, P={axis_pitch_offset:.1f}°, Y={axis_yaw_offset:.1f}°")
    print(f"    Final constraint: R={final_roll:.1f}°, P={final_pitch:.1f}°, Y={final_yaw:.1f}°")
    
    return unreal.Rotator(roll=final_roll, pitch=final_pitch, yaw=final_yaw)


def create_physics_constraints(joints: List[PhysicsJointData], 
                                actor_map: Dict[str, 'unreal.Actor'],
                                robot_name: str = "") -> List['unreal.PhysicsConstraintComponent']:
    """
    Create UE5 PhysicsConstraintComponents for all joints.
    
    Args:
        joints: List of parsed joint data
        actor_map: Map from USD path/link name to UE5 Actor
        robot_name: Name prefix for constraint actors (e.g., "ur30_robot")
        
    Returns:
        List of created constraint components
    """
    if not HAS_UNREAL:
        print("ERROR: Unreal module not available")
        return []
    
    print("=" * 80)
    print(f"[Physics] create_physics_constraints() called")
    print(f"  Joints: {len(joints)}")
    print(f"  robot_name parameter: '{robot_name}' (type: {type(robot_name).__name__})")
    print(f"  robot_name is empty: {not robot_name}")
    print("=" * 80)
    
    constraints = []
    
    for joint in joints:
        constraint = create_single_constraint(joint, actor_map, robot_name)
        if constraint:
            constraints.append(constraint)
    
    print(f"Created {len(constraints)} physics constraints")
    return constraints


def create_single_constraint(joint: PhysicsJointData, 
                             actor_map: Dict[str, 'unreal.Actor'],
                             robot_name: str = "") -> Optional['unreal.PhysicsConstraintComponent']:
    """
    Create a single PhysicsConstraintComponent for a joint.
    
    Args:
        joint: Joint data from USD
        actor_map: Map from USD path/link name to UE5 Actor
        robot_name: Name prefix for constraint actors (e.g., "ur30_robot")
        
    Returns:
        Created constraint component or None
    """
    if not HAS_UNREAL:
        return None
    
    # Find the parent and child actors
    parent_actor = _find_actor_for_body(joint.body0_path, actor_map)
    child_actor = _find_actor_for_body(joint.body1_path, actor_map)
    
    if not parent_actor or not child_actor:
        print(f"WARNING: Could not find actors for joint {joint.name}")
        print(f"  body0: {joint.body0_path} -> {parent_actor}")
        print(f"  body1: {joint.body1_path} -> {child_actor}")
        return None
    
    print(f"Creating constraint: {joint.name}")
    print(f"  Type: {joint.joint_type.value}, Axis: {joint.axis}")
    print(f"  Parent: {parent_actor.get_name()}, Child: {child_actor.get_name()}")
    
    # Create the constraint component using proper UE5 API
    # Method 1: Add component to child actor using EditorActorSubsystem
    try:
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        
        # Create a PhysicsConstraintActor instead for more reliable constraint setup
        # This is the recommended approach for editor-time constraint creation
        world = unreal.EditorLevelLibrary.get_editor_world()
        
        # Calculate constraint position in world space
        constraint_world_pos = child_actor.get_actor_location()
        constraint_world_pos.x += joint.local_pos0[0]
        constraint_world_pos.y += joint.local_pos0[1]
        constraint_world_pos.z += joint.local_pos0[2]
        
        # Calculate proper rotation based on joint axis and local rotation
        constraint_rotation = _calculate_constraint_rotation(joint)
        if constraint_rotation is None:
            constraint_rotation = unreal.Rotator(0, 0, 0)
        
        print(f"  Constraint rotation: Roll={constraint_rotation.roll:.1f}, Pitch={constraint_rotation.pitch:.1f}, Yaw={constraint_rotation.yaw:.1f}")
        
        # Spawn PhysicsConstraintActor with proper orientation
        constraint_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.PhysicsConstraintActor,
            constraint_world_pos,
            constraint_rotation
        )
        
        if not constraint_actor:
            print(f"  ERROR: Failed to spawn PhysicsConstraintActor for {joint.name}")
            return None
        
        # Rename the constraint actor with robot name prefix for uniqueness
        print("=" * 80)
        print(f"[NAMING DEBUG]")
        print(f"  robot_name parameter: '{robot_name}' (len={len(robot_name) if robot_name else 0})")
        print(f"  joint.name: '{joint.name}'")
        print(f"  robot_name bool check: {bool(robot_name)}")
        
        if robot_name:
            constraint_label = f"{robot_name}_Constraint_{joint.name}"
            print(f"  Using robot prefix - label: '{constraint_label}'")
        else:
            constraint_label = f"Constraint_{joint.name}"
            print(f"  NO robot prefix - label: '{constraint_label}'")
        print("=" * 80)
        
        constraint_actor.set_actor_label(constraint_label)
        
        # Get the constraint component from the actor
        constraint = constraint_actor.get_editor_property("constraint_comp")
        
        if not constraint:
            print(f"  ERROR: PhysicsConstraintActor has no constraint component")
            return None
        
        # Set the constrained actors
        constraint.set_editor_property("constraint_actor1", parent_actor)
        constraint.set_editor_property("constraint_actor2", child_actor)
        
        # Get component names for the constraint
        parent_comp = _get_root_primitive_component(parent_actor)
        child_comp = _get_root_primitive_component(child_actor)
        
        if parent_comp:
            constraint.set_editor_property("component_name1", unreal.Name(parent_comp.get_name()))
        if child_comp:
            constraint.set_editor_property("component_name2", unreal.Name(child_comp.get_name()))
        
        # Disable collision between constrained bodies
        constraint.set_editor_property("disable_collision", True)
        
        # Configure constraint profile based on joint type
        # Access constraint settings directly on the component
        if joint.joint_type == JointType.FIXED:
            _configure_fixed_constraint_direct(constraint, joint)
        elif joint.joint_type == JointType.REVOLUTE:
            _configure_revolute_constraint_direct(constraint, joint)
        elif joint.joint_type == JointType.PRISMATIC:
            _configure_prismatic_constraint_direct(constraint, joint)
        elif joint.joint_type == JointType.CONTINUOUS:
            _configure_continuous_constraint_direct(constraint, joint)
        
        print(f"  ✓ Created constraint: {joint.name}")
        return constraint
        
    except Exception as e:
        print(f"  ERROR creating constraint {joint.name}: {e}")
        import traceback
        traceback.print_exc()
        return None


def _find_actor_for_body(body_path: str, actor_map: Dict[str, 'unreal.Actor']) -> Optional['unreal.Actor']:
    """
    Find UE5 actor for a USD body path.
    Uses multiple matching strategies for robustness.
    """
    if not body_path:
        return None
    
    # Strategy 1: Direct lookup
    if body_path in actor_map:
        return actor_map[body_path]
    
    # Strategy 2: Try just the prim name (last component of path)
    prim_name = body_path.split('/')[-1]
    if prim_name in actor_map:
        return actor_map[prim_name]
    
    # Strategy 3: Case-insensitive exact match
    prim_name_lower = prim_name.lower()
    for key, actor in actor_map.items():
        key_name = key.split('/')[-1].lower()
        if key_name == prim_name_lower:
            return actor
    
    # Strategy 4: Substring match (for prefixes/suffixes added by UE5)
    # e.g., "base_link" might become "SM_base_link" or "base_link_0"
    for key, actor in actor_map.items():
        key_name = key.split('/')[-1].lower()
        # Check if one contains the other
        if prim_name_lower in key_name or key_name in prim_name_lower:
            return actor
    
    # Strategy 5: Word boundary match (handle underscores differently)
    prim_words = set(prim_name_lower.replace('_', ' ').split())
    for key, actor in actor_map.items():
        key_name = key.split('/')[-1].lower()
        key_words = set(key_name.replace('_', ' ').split())
        # If significant overlap in words, consider it a match
        if len(prim_words & key_words) >= min(len(prim_words), len(key_words)) * 0.7:
            return actor
    
    return None


def _get_root_primitive_component(actor: 'unreal.Actor') -> Optional['unreal.PrimitiveComponent']:
    """Get the root primitive component of an actor."""
    root = actor.get_editor_property("root_component")
    if isinstance(root, unreal.PrimitiveComponent):
        return root
    
    # Try to find any static mesh component
    components = actor.get_components_by_class(unreal.StaticMeshComponent)
    if components:
        return components[0]
    
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Direct Component Configuration (for PhysicsConstraintComponent)
# These work directly on the component rather than a profile object
# ═══════════════════════════════════════════════════════════════════════════

def _configure_fixed_constraint_direct(constraint, joint: PhysicsJointData):
    """Configure a fully locked constraint directly on component."""
    # Use set_angular_swing1_limit, set_angular_swing2_limit, etc.
    constraint.set_angular_swing1_limit(unreal.AngularConstraintMotion.ACM_LOCKED, 0)
    constraint.set_angular_swing2_limit(unreal.AngularConstraintMotion.ACM_LOCKED, 0)
    constraint.set_angular_twist_limit(unreal.AngularConstraintMotion.ACM_LOCKED, 0)
    constraint.set_linear_x_limit(unreal.LinearConstraintMotion.LCM_LOCKED, 0)
    constraint.set_linear_y_limit(unreal.LinearConstraintMotion.LCM_LOCKED, 0)
    constraint.set_linear_z_limit(unreal.LinearConstraintMotion.LCM_LOCKED, 0)


def _configure_revolute_constraint_direct(constraint, joint: PhysicsJointData):
    """Configure a revolute (hinge) constraint directly on component."""
    # Lock all linear motion
    constraint.set_linear_x_limit(unreal.LinearConstraintMotion.LCM_LOCKED, 0)
    constraint.set_linear_y_limit(unreal.LinearConstraintMotion.LCM_LOCKED, 0)
    constraint.set_linear_z_limit(unreal.LinearConstraintMotion.LCM_LOCKED, 0)
    
    # Configure angular motion based on axis
    # In UE5: Twist = X axis rotation, Swing1 = Y axis, Swing2 = Z axis
    limit_angle = abs(joint.limits.upper - joint.limits.lower) / 2 if joint.limits.has_limits else 0
    
    if joint.axis == "X":
        if joint.limits.has_limits:
            constraint.set_angular_twist_limit(unreal.AngularConstraintMotion.ACM_LIMITED, limit_angle)
        else:
            constraint.set_angular_twist_limit(unreal.AngularConstraintMotion.ACM_FREE, 0)
        constraint.set_angular_swing1_limit(unreal.AngularConstraintMotion.ACM_LOCKED, 0)
        constraint.set_angular_swing2_limit(unreal.AngularConstraintMotion.ACM_LOCKED, 0)
        
    elif joint.axis == "Y":
        constraint.set_angular_twist_limit(unreal.AngularConstraintMotion.ACM_LOCKED, 0)
        if joint.limits.has_limits:
            constraint.set_angular_swing1_limit(unreal.AngularConstraintMotion.ACM_LIMITED, limit_angle)
        else:
            constraint.set_angular_swing1_limit(unreal.AngularConstraintMotion.ACM_FREE, 0)
        constraint.set_angular_swing2_limit(unreal.AngularConstraintMotion.ACM_LOCKED, 0)
        
    elif joint.axis == "Z":
        constraint.set_angular_twist_limit(unreal.AngularConstraintMotion.ACM_LOCKED, 0)
        constraint.set_angular_swing1_limit(unreal.AngularConstraintMotion.ACM_LOCKED, 0)
        if joint.limits.has_limits:
            constraint.set_angular_swing2_limit(unreal.AngularConstraintMotion.ACM_LIMITED, limit_angle)
        else:
            constraint.set_angular_swing2_limit(unreal.AngularConstraintMotion.ACM_FREE, 0)
    
    # Configure drive if available
    if joint.drive.stiffness > 0 or joint.drive.damping > 0:
        _configure_angular_drive_direct(constraint, joint)


def _configure_prismatic_constraint_direct(constraint, joint: PhysicsJointData):
    """Configure a prismatic (sliding) constraint directly on component."""
    # Lock all angular motion
    constraint.set_angular_swing1_limit(unreal.AngularConstraintMotion.ACM_LOCKED, 0)
    constraint.set_angular_swing2_limit(unreal.AngularConstraintMotion.ACM_LOCKED, 0)
    constraint.set_angular_twist_limit(unreal.AngularConstraintMotion.ACM_LOCKED, 0)
    
    # Configure linear motion based on axis
    limit_size = abs(joint.limits.upper - joint.limits.lower) / 2 if joint.limits.has_limits else 0
    
    if joint.axis == "X":
        if joint.limits.has_limits:
            constraint.set_linear_x_limit(unreal.LinearConstraintMotion.LCM_LIMITED, limit_size)
        else:
            constraint.set_linear_x_limit(unreal.LinearConstraintMotion.LCM_FREE, 0)
        constraint.set_linear_y_limit(unreal.LinearConstraintMotion.LCM_LOCKED, 0)
        constraint.set_linear_z_limit(unreal.LinearConstraintMotion.LCM_LOCKED, 0)
        
    elif joint.axis == "Y":
        constraint.set_linear_x_limit(unreal.LinearConstraintMotion.LCM_LOCKED, 0)
        if joint.limits.has_limits:
            constraint.set_linear_y_limit(unreal.LinearConstraintMotion.LCM_LIMITED, limit_size)
        else:
            constraint.set_linear_y_limit(unreal.LinearConstraintMotion.LCM_FREE, 0)
        constraint.set_linear_z_limit(unreal.LinearConstraintMotion.LCM_LOCKED, 0)
        
    elif joint.axis == "Z":
        constraint.set_linear_x_limit(unreal.LinearConstraintMotion.LCM_LOCKED, 0)
        constraint.set_linear_y_limit(unreal.LinearConstraintMotion.LCM_LOCKED, 0)
        if joint.limits.has_limits:
            constraint.set_linear_z_limit(unreal.LinearConstraintMotion.LCM_LIMITED, limit_size)
        else:
            constraint.set_linear_z_limit(unreal.LinearConstraintMotion.LCM_FREE, 0)
    
    # Configure drive if available
    if joint.drive.stiffness > 0 or joint.drive.damping > 0:
        _configure_linear_drive_direct(constraint, joint)


def _configure_continuous_constraint_direct(constraint, joint: PhysicsJointData):
    """Configure a continuous (unlimited rotation) constraint directly."""
    joint.limits.has_limits = False
    _configure_revolute_constraint_direct(constraint, joint)


def _configure_angular_drive_direct(constraint, joint: PhysicsJointData):
    """Configure angular drive parameters on component."""
    # Set angular drive mode
    constraint.set_angular_drive_mode(unreal.AngularDriveMode.TWIST_AND_SWING)
    
    # Set drive parameters using component methods
    # UE5 uses OrientationTarget for angular positioning
    constraint.set_angular_orientation_drive(True, True)  # Enable twist and swing drive
    constraint.set_angular_velocity_drive(True, True)
    
    # Set drive strength and damping
    # Note: These may need to be set via constraint_instance in some UE5 versions
    try:
        constraint.set_angular_drive_params(joint.drive.stiffness, joint.drive.damping, joint.drive.max_force)
    except Exception as e:
        print(f"    Warning: Could not set angular drive params via method: {e}")


def _configure_linear_drive_direct(constraint, joint: PhysicsJointData):
    """Configure linear drive parameters on component."""
    # Enable linear drive
    constraint.set_linear_position_drive(True, True, True)  # X, Y, Z
    constraint.set_linear_velocity_drive(True, True, True)
    
    # Set drive parameters
    try:
        constraint.set_linear_drive_params(joint.drive.stiffness, joint.drive.damping, joint.drive.max_force)
    except Exception as e:
        print(f"    Warning: Could not set linear drive params via method: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# High-Level API
# ═══════════════════════════════════════════════════════════════════════════

def setup_physics_from_usd(usd_path: str, actor_map: Optional[Dict[str, 'unreal.Actor']] = None) -> bool:
    """
    Set up physics constraints from a USD file.
    
    This is the main entry point for physics setup. It:
    1. Parses PhysicsScene for gravity settings
    2. Parses physics joints (Revolute, Prismatic, Fixed)
    3. Parses FilteredPairsAPI for self-collision filtering
    4. Creates UE5 PhysicsConstraintActors
    5. Applies all settings
    
    Args:
        usd_path: Path to USD file with physics joints
        actor_map: Optional map of link names to actors (auto-discovers if None)
        
    Returns:
        True if successful
    """
    print("═══════════════════════════════════════════════════════")
    print(f"ROA Physics Setup: {usd_path}")
    print("═══════════════════════════════════════════════════════")
    
    # Step 1: Parse PhysicsScene for gravity (Issue 6 fix)
    scene_data = parse_usd_physics_scene(usd_path)
    if scene_data and HAS_UNREAL:
        _apply_physics_scene_settings(scene_data)
    
    # Step 2: Parse USD physics joints
    joints = parse_usd_physics_joints(usd_path)
    
    if not joints:
        print("No physics joints found in USD file")
        return False
    
    # Step 3: Parse FilteredPairsAPI for self-collision (Issue 8 fix)
    filtered_pairs = parse_usd_filtered_pairs(usd_path)
    
    # Step 4: Build actor map if not provided
    if actor_map is None:
        actor_map = _discover_robot_actors(joints)
    
    if not actor_map:
        print("ERROR: Could not discover robot actors")
        return False
    
    # Step 5: Create physics constraints
    constraints = create_physics_constraints(joints, actor_map)
    
    # Step 6: Apply self-collision filtering from FilteredPairsAPI
    if filtered_pairs.pairs and HAS_UNREAL:
        _apply_collision_filtering(filtered_pairs, actor_map)
    
    print("═══════════════════════════════════════════════════════")
    print(f"Physics setup complete: {len(constraints)} constraints created")
    print("═══════════════════════════════════════════════════════")
    
    return len(constraints) > 0


def _apply_physics_scene_settings(scene_data: PhysicsSceneData):
    """
    Apply PhysicsScene settings to UE5 world.
    Note: UE5 gravity is set per-project, not per-level, so this logs a warning.
    """
    if not HAS_UNREAL:
        return
    
    # UE5's default gravity is -980 cm/s² in Z direction
    # We can't easily change project settings at runtime, but we log the info
    expected_gravity = scene_data.gravity_magnitude
    gravity_dir = scene_data.gravity_direction
    
    print(f"USD PhysicsScene gravity: {gravity_dir} @ {expected_gravity:.1f} cm/s²")
    print(f"  Note: UE5 project gravity should be set to match (~980 cm/s² default)")
    
    # Could potentially use world settings override if available
    try:
        world = unreal.EditorLevelLibrary.get_editor_world()
        world_settings = world.get_world_settings()
        # Log current UE5 gravity for comparison
        print(f"  UE5 world global gravity: {world_settings.get_editor_property('global_gravity_z')}")
    except Exception as e:
        print(f"  Could not read UE5 gravity settings: {e}")


def _apply_collision_filtering(filtered_pairs: 'FilteredPairsData', 
                                actor_map: Dict[str, 'unreal.Actor']):
    """
    Apply self-collision filtering from USD FilteredPairsAPI.
    
    In UE5, this is done by setting collision channels or using
    'Ignore' on specific actor pairs via collision responses.
    """
    if not HAS_UNREAL:
        return
    
    print(f"Applying collision filtering for {len(filtered_pairs.pairs)} pairs...")
    
    applied_count = 0
    for body0_path, body1_path in filtered_pairs.pairs:
        # Find actors for both bodies
        actor0 = _find_actor_for_body(body0_path, actor_map)
        actor1 = _find_actor_for_body(body1_path, actor_map)
        
        if not actor0 or not actor1:
            continue
        
        # Try to set collision ignore between the two actors' components
        try:
            comp0 = _get_root_primitive_component(actor0)
            comp1 = _get_root_primitive_component(actor1)
            
            if comp0 and comp1:
                # Use MoveIgnoreActors - actors will ignore each other in collision
                comp0.ignore_actor_when_moving(actor1, True)
                comp1.ignore_actor_when_moving(actor0, True)
                applied_count += 1
        except Exception as e:
            # Some components may not support this
            pass
    
    if applied_count > 0:
        print(f"  Applied collision ignore to {applied_count} actor pairs")


def _discover_robot_actors(joints: List[PhysicsJointData]) -> Dict[str, 'unreal.Actor']:
    """
    Discover robot actors in the level based on joint body paths.
    Uses multiple matching strategies for robustness.
    """
    if not HAS_UNREAL:
        return {}
    
    actor_map = {}
    
    # Collect all unique link names from joints
    link_names = set()
    for joint in joints:
        if joint.body0_path:
            link_names.add(joint.body0_path.split('/')[-1])
        if joint.body1_path:
            link_names.add(joint.body1_path.split('/')[-1])
    
    print(f"Looking for {len(link_names)} robot links...")
    
    # Find actors in level
    world = unreal.EditorLevelLibrary.get_editor_world()
    all_actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)
    
    # Build actor name index for faster lookup
    actor_index = {}
    for actor in all_actors:
        actor_label = actor.get_actor_label()
        actor_index[actor_label] = actor
        actor_index[actor_label.lower()] = actor
    
    for link_name in link_names:
        link_lower = link_name.lower()
        matched = False
        
        # Strategy 1: Exact match
        if link_name in actor_index:
            actor_map[link_name] = actor_index[link_name]
            print(f"  Found (exact): {link_name}")
            continue
        
        # Strategy 2: Case-insensitive exact
        if link_lower in actor_index:
            actor_map[link_name] = actor_index[link_lower]
            print(f"  Found (case-insensitive): {link_name}")
            continue
        
        # Strategy 3: Substring match
        for actor_label, actor in actor_index.items():
            if isinstance(actor_label, str):  # Skip lowercase duplicates
                label_lower = actor_label.lower()
                if link_lower in label_lower or label_lower in link_lower:
                    actor_map[link_name] = actor
                    print(f"  Found (substring): {link_name} -> {actor_label}")
                    matched = True
                    break
        
        if matched:
            continue
        
        # Strategy 4: UE5 naming conventions (SM_, SK_, etc.)
        prefixes = ['SM_', 'SK_', 'S_', 'M_', '']
        suffixes = ['', '_0', '_1', '_2', '_Mesh', '_mesh']
        for prefix in prefixes:
            for suffix in suffixes:
                test_name = f"{prefix}{link_name}{suffix}"
                if test_name in actor_index:
                    actor_map[link_name] = actor_index[test_name]
                    print(f"  Found (UE5 naming): {link_name} -> {test_name}")
                    matched = True
                    break
            if matched:
                break
        
        if not matched:
            print(f"  WARNING: Could not find actor for link: {link_name}")
    
    return actor_map


# ═══════════════════════════════════════════════════════════════════════════
# Testing / Standalone Mode
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Test parsing with a sample USD file
    import sys
    
    if len(sys.argv) > 1:
        usd_path = sys.argv[1]
        joints = parse_usd_physics_joints(usd_path)
        
        print("\nParsed Joints:")
        for joint in joints:
            print(f"\n{joint.name}:")
            print(f"  Type: {joint.joint_type.value}")
            print(f"  Axis: {joint.axis}")
            print(f"  Body0: {joint.body0_path}")
            print(f"  Body1: {joint.body1_path}")
            print(f"  Limits: {joint.limits}")
            print(f"  Drive: stiffness={joint.drive.stiffness}, damping={joint.drive.damping}")
    else:
        print("Usage: python physics_constraint_setup.py <usd_file>")
