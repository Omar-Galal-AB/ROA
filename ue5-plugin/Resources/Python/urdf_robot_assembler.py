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

import unreal
import json
import math
import os
import tempfile
import time
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path


# =============================================================================
# COORDINATE CONVERSION: ROS to UE5
# =============================================================================
# ROS:  X-forward, Y-left, Z-up   (Right-handed, meters)
# UE5:  X-forward, Y-right, Z-up  (Left-handed, centimeters)

def ros_position_to_ue5(xyz: List[float], scale: float = 100.0) -> List[float]:
    """Convert ROS position (meters) to UE5 position (cm)."""
    return [
        xyz[0] * scale,      # X stays same
        -xyz[1] * scale,     # Y flips (left to right hand)
        xyz[2] * scale       # Z stays same
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
    cr, sr = math.cos(roll/2), math.sin(roll/2)
    cp, sp = math.cos(pitch/2), math.sin(pitch/2)
    cy, sy = math.cos(yaw/2), math.sin(yaw/2)
    
    return [
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy
    ]


def quaternion_multiply(q1: List[float], q2: List[float]) -> List[float]:
    """Multiply two quaternions: q1 * q2."""
    x1, y1, z1, w1 = q1
    x2, y2, z2, w2 = q2
    return [
        w1*x2 + x1*w2 + y1*z2 - z1*y2,
        w1*y2 - x1*z2 + y1*w2 + z1*x2,
        w1*z2 + x1*y2 - y1*x2 + z1*w2,
        w1*w2 - x1*x2 - y1*y2 - z1*z2
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
        vz + qw * tz + qx * ty - qy * tx
    ]


def ros_quaternion_to_ue5(q: List[float]) -> List[float]:
    """Convert ROS quaternion to UE5 (flip Y axis for handedness)."""
    x, y, z, w = q
    return [x, -y, -z, w]


def quaternion_to_rotator(q: List[float]) -> 'unreal.Rotator':
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
# PHYSICS BODY SETUP (ROC Requirements)
# =============================================================================
# These functions enable physics simulation on robot parts so they can be
# controlled via physics constraints and motors.

# Default physics parameters based on industrial robot specs
DEFAULT_DRIVE_STIFFNESS = 100000.0   # Position control stiffness (N/m or Nm/rad)
DEFAULT_DRIVE_DAMPING = 10000.0      # Velocity damping
DEFAULT_MAX_FORCE = 1000.0           # Max force/torque (will be overridden by URDF effort)
DEFAULT_LINK_MASS = 1.0              # Default mass if not in URDF (kg)


def setup_physics_body(
    actor: 'unreal.Actor',
    simulate_physics: bool = True,
    mass_kg: float = None,
    is_base_link: bool = False,
    verbose: bool = False
) -> bool:
    """
    Configure physics body for a robot link actor.
    
    For physics simulation to work:
    - Non-base links need simulate_physics = True
    - Base link should be kinematic (doesn't move) OR fixed to world
    
    Args:
        actor: The StaticMeshActor for the link
        simulate_physics: Whether this body should simulate physics
        mass_kg: Mass in kg (None = use mesh default)
        is_base_link: If True, this is the root link (should be kinematic)
        verbose: Print debug info
        
    Returns:
        True if setup succeeded
    """
    try:
        # Get the static mesh component
        mesh_comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        if not mesh_comp:
            if hasattr(actor, 'static_mesh_component'):
                mesh_comp = actor.static_mesh_component
        
        if not mesh_comp:
            if verbose:
                print(f"        [WARN] No mesh component found on {actor.get_actor_label()}")
            return False
        
        if is_base_link:
            # Base link should be kinematic - it doesn't move
            # Set Mobility to Stationary or use kinematic body
            mesh_comp.set_simulate_physics(False)
            mesh_comp.set_editor_property('mobility', unreal.ComponentMobility.STATIONARY)
            if verbose:
                print(f"        [PHYSICS] {actor.get_actor_label()}: Base link (stationary)")
        else:
            # Moving link - enable physics
            mesh_comp.set_editor_property('mobility', unreal.ComponentMobility.MOVABLE)
            mesh_comp.set_simulate_physics(simulate_physics)
            
            # Set mass if provided
            if mass_kg is not None and mass_kg > 0:
                mesh_comp.set_mass_override_in_kg(
                    bone_name=unreal.Name("None"),
                    mass_in_kg=mass_kg,
                    override_mass=True
                )
                if verbose:
                    print(f"        [PHYSICS] {actor.get_actor_label()}: mass={mass_kg:.2f}kg, simulate={simulate_physics}")
            else:
                if verbose:
                    print(f"        [PHYSICS] {actor.get_actor_label()}: simulate={simulate_physics}")
        
        return True
        
    except Exception as e:
        if verbose:
            print(f"        [ERROR] Physics setup failed for {actor.get_actor_label()}: {e}")
        return False


def configure_constraint_drive(
    constraint_comp: 'unreal.PhysicsConstraintComponent',
    joint_type: str,
    axis: str,
    limits: Dict = None,
    dynamics: Dict = None,
    verbose: bool = False
) -> bool:
    """
    Configure motor/drive on a physics constraint for ROC control.
    
    This enables ROC to control the joint by setting target position/velocity.
    
    For revolute joints:
    - Uses Angular Drive Mode (Twist and Swing)
    - Sets stiffness/damping for position control
    
    For prismatic joints:
    - Uses Linear Drive
    - Sets stiffness/damping for position control
    
    Args:
        constraint_comp: The UE5 PhysicsConstraintComponent
        joint_type: 'revolute', 'prismatic', 'continuous', or 'fixed'
        axis: Dominant axis 'x', 'y', or 'z'
        limits: Joint limits dict with 'effort', 'velocity', etc.
        dynamics: Joint dynamics dict with 'damping', 'friction' from URDF
        verbose: Print debug info
        
    Returns:
        True if drive configured successfully
    """
    try:
        if joint_type == 'fixed':
            # Fixed joints don't have motors
            return True
        
        # Get max force from URDF effort limit, or use default
        max_force = DEFAULT_MAX_FORCE
        if limits and 'effort' in limits and limits['effort'] > 0:
            max_force = limits['effort']
        
        # Get stiffness and damping - use URDF dynamics if available
        stiffness = DEFAULT_DRIVE_STIFFNESS
        damping = DEFAULT_DRIVE_DAMPING
        
        # NEW: Use URDF dynamics if provided
        if dynamics:
            # URDF damping maps to UE5 damping (resistance to velocity)
            if dynamics.get('damping') and dynamics['damping'] > 0:
                # Scale URDF damping to UE5 range (URDF is typically 0-100, UE5 needs 1000-100000)
                damping = dynamics['damping'] * 100.0
                if damping < 100:
                    damping = DEFAULT_DRIVE_DAMPING  # Use default if too low
            
            # URDF friction adds to damping for stability
            if dynamics.get('friction') and dynamics['friction'] > 0:
                damping += dynamics['friction'] * 50.0
        
        if joint_type in ['revolute', 'continuous']:
            # Angular drive for rotation
            constraint_comp.set_angular_drive_mode(unreal.AngularDriveMode.TWIST_AND_SWING)
            constraint_comp.set_angular_drive_params(stiffness, damping, max_force)
            
            # Enable orientation target for position control
            try:
                constraint_comp.set_editor_property('angular_orientation_target', unreal.Rotator(0, 0, 0))
            except:
                pass
            
            if verbose:
                urdf_source = " (from URDF)" if dynamics else ""
                print(f"          [DRIVE] Angular: stiffness={stiffness:.0f}, damping={damping:.0f}, max_force={max_force:.0f}{urdf_source}")
            
        elif joint_type == 'prismatic':
            # Linear drive for translation
            constraint_comp.set_linear_drive_params(stiffness, damping, max_force)
            
            # Enable position target
            try:
                constraint_comp.set_editor_property('linear_position_target', unreal.Vector(0, 0, 0))
            except:
                pass
            
            if verbose:
                urdf_source = " (from URDF)" if dynamics else ""
                print(f"          [DRIVE] Linear: stiffness={stiffness:.0f}, damping={damping:.0f}, max_force={max_force:.0f}{urdf_source}")
        
        return True
        
    except Exception as e:
        if verbose:
            print(f"          [ERROR] Drive configuration failed: {e}")
        return False


def export_robot_specs_for_roc(
    robot_name: str,
    hierarchy_data: Dict,
    constraint_map: Dict[str, str],
    actors_by_link: Dict[str, List['unreal.Actor']],
    output_path: str = None,
    verbose: bool = False
) -> str:
    """
    Export robot specifications JSON for ROC (Robot Operator Controller).
    
    This creates a JSON file with all the information ROC needs to control the robot:
    - Joint names and types
    - UE5 constraint names (for finding components)
    - Joint limits
    - Kinematic chain
    - Link-to-actor mapping
    - Capabilities (gripper detection, reach, payload)
    - Dynamics (damping, friction)
    
    Args:
        robot_name: Name of the robot
        hierarchy_data: Parsed hierarchy JSON
        constraint_map: Dict mapping joint_name -> constraint_actor_label
        actors_by_link: Dict mapping link_name -> [actors]
        output_path: Where to save JSON (default: same folder as hierarchy)
        verbose: Print debug info
        
    Returns:
        Path to created JSON file
    """
    try:
        hierarchy = hierarchy_data.get('hierarchy', {})
        joints_list = hierarchy.get('joints', [])
        links_data = hierarchy.get('links', {})
        if not links_data:
            links_data = hierarchy.get('nodes', {})
        
        # Build joints info for ROC
        joints_info = []
        controllable_joints = []
        kinematic_chain = []
        gripper_joint_name = None
        has_mobile_base = False
        max_reach = 0.0
        
        for joint in joints_list:
            joint_name = joint.get('name', '')
            joint_type = joint.get('type', 'fixed')
            limits = joint.get('limits', {})
            
            # Extract dynamics if available
            dynamics = joint.get('dynamics', {})
            
            joint_spec = {
                'name': joint_name,
                'joint_type': joint_type,
                'parent_link': joint.get('parent_link', ''),
                'child_link': joint.get('child_link', ''),
                'axis': joint.get('axis', [0, 0, 1]),
                'origin': joint.get('origin', {}),
                'limits': limits,
                'dynamics': {
                    'damping': dynamics.get('damping', 0.0),
                    'friction': dynamics.get('friction', 0.0)
                },
                'ue5_constraint_name': constraint_map.get(joint_name, ''),
                'ue5_constraint_path': f"/Game/Robots/{robot_name}/{constraint_map.get(joint_name, '')}"
            }
            joints_info.append(joint_spec)
            
            # Track controllable joints (not fixed)
            if joint_type not in ['fixed']:
                controllable_joints.append(joint_name)
            
            # Build kinematic chain from child links
            child_link = joint.get('child_link', '')
            if child_link and child_link not in kinematic_chain:
                kinematic_chain.append(child_link)
            
            # Detect gripper (common naming patterns)
            joint_lower = joint_name.lower()
            if any(g in joint_lower for g in ['gripper', 'finger', 'hand', 'tool', 'ee', 'end_effector']):
                gripper_joint_name = joint_name
            
            # Detect mobile base
            if any(m in joint_lower for m in ['wheel', 'caster', 'base_joint', 'drive']):
                has_mobile_base = True
            
            # Estimate reach from joint origins (cumulative Z distance)
            origin = joint.get('origin', {})
            if origin:
                xyz = origin.get('xyz', [0, 0, 0])
                if isinstance(xyz, list) and len(xyz) >= 3:
                    # Add Z component to reach (rough estimate)
                    max_reach += abs(xyz[2])
        
        # Build links info with mass and inertia
        links_info = []
        total_mass = 0.0
        root_nodes = hierarchy.get('root_nodes', [])
        
        # Insert root link at beginning of kinematic chain
        if root_nodes:
            for root in root_nodes:
                if root not in kinematic_chain:
                    kinematic_chain.insert(0, root)
        
        for link_name, actors in actors_by_link.items():
            actor_names = [a.get_actor_label() for a in actors if a]
            actor_paths = [f"/Game/Robots/{robot_name}/Parts/{name}" for name in actor_names]
            
            # Get link properties from hierarchy
            link_info = links_data.get(link_name, {})
            link_props = link_info.get('properties', {})
            
            mass = link_props.get('mass', DEFAULT_LINK_MASS)
            total_mass += mass
            
            # Get inertia if available
            inertia = link_props.get('inertia', {})
            
            links_info.append({
                'name': link_name,
                'ue5_actor_name': actor_names[0] if actor_names else '',
                'ue5_actor_names': actor_names,
                'ue5_actor_path': actor_paths[0] if actor_paths else '',
                'is_root': link_name in root_nodes,
                'mass': mass,
                'inertia': {
                    'ixx': inertia.get('ixx', 0.0),
                    'ixy': inertia.get('ixy', 0.0),
                    'ixz': inertia.get('ixz', 0.0),
                    'iyy': inertia.get('iyy', 0.0),
                    'iyz': inertia.get('iyz', 0.0),
                    'izz': inertia.get('izz', 0.0)
                }
            })
        
        # Detect robot type from structure
        robot_type = 'generic'
        dof = len(controllable_joints)
        if has_mobile_base:
            robot_type = 'mobile_robot'
        elif dof >= 6 and dof <= 8:
            robot_type = 'industrial_arm'
        elif dof >= 4 and dof <= 5:
            robot_type = 'collaborative'
        elif dof == 1:
            robot_type = 'single_actuator'
        
        # Estimate max payload (rough heuristic based on mass and DOF)
        # Industrial arms: ~10% of total mass as payload
        max_payload = total_mass * 0.1
        
        # Construct full robot spec (ALL ROC requirements)
        robot_spec = {
            'robot_id': f"{robot_name}_001",
            'robot_name': robot_name,
            'source_file': hierarchy_data.get('source_file', ''),
            'import_timestamp': time.time(),
            'export_timestamp': hierarchy_data.get('export_timestamp', ''),
            'version': '1.0',
            
            'joints': joints_info,
            'links': links_info,
            
            # Capabilities section (P1 requirement)
            'capabilities': {
                'has_gripper': gripper_joint_name is not None,
                'gripper_joint_name': gripper_joint_name,
                'has_mobile_base': has_mobile_base,
                'mobile_base_type': 'differential' if has_mobile_base else None,
                'max_payload_kg': round(max_payload, 2),
                'max_reach_m': round(max_reach / 100.0, 3),  # Convert cm to m
                'robot_type': robot_type
            },
            
            'control_hierarchy': {
                'root_link': root_nodes[0] if root_nodes else '',
                'kinematic_chain': kinematic_chain,
                'dof': dof,
                'controllable_joints': controllable_joints
            },
            
            'ue5_assets': {
                'blueprint_path': f"/Game/Robots/{robot_name}/BP_{robot_name}",
                'content_folder': f"/Game/Robots/{robot_name}",
                'root_actor_name': f"BP_{robot_name}_C_0",
                'constraint_prefix': f"{robot_name}_Constraint_"
            }
        }
        
        # Determine output path
        if output_path is None:
            # Try to find a good location for ROC specs
            # Priority: 1. FTI storage, 2. Temp directory
            fti_storage = "D:/ROA/.fti_storage"
            if os.path.isdir(fti_storage):
                output_path = os.path.join(fti_storage, f"{robot_name}_roc_specs.json")
            else:
                # Fallback to temp
                output_path = os.path.join(tempfile.gettempdir(), f"{robot_name}_roc_specs.json")
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Write JSON
        with open(output_path, 'w') as f:
            json.dump(robot_spec, f, indent=2)
        
        if verbose:
            print(f"  [ROC] Exported robot specs: {output_path}")
            print(f"        Joints: {len(joints_info)}, Controllable: {len(controllable_joints)}")
        
        return output_path
        
    except Exception as e:
        if verbose:
            print(f"  [ERROR] Failed to export ROC specs: {e}")
        return ""


# =============================================================================
# DIMC EXPORT (Dimensions Collector Requirements)
# =============================================================================
# DIMC needs: RobotID, RobotName, RobotActor, Dimensions, Sensors, SafetyZones,
# CollisionMesh reference, RobotType detection, and DataFlags

# Robot type enumeration matching DIMC's ERobotType
ROBOT_TYPES = {
    'industrial_arm': 'IndustrialArm',
    'mobile_robot': 'MobileRobot', 
    'humanoid': 'Humanoid',
    'drone': 'Drone',
    'single_actuator': 'SingleActuator',
    'collaborative': 'Collaborative',
    'generic': 'Generic'
}

# Default sensor profiles by robot type (matching DIMC requirements)
DEFAULT_SENSOR_PROFILES = {
    'IndustrialArm': {
        'lidar': {'ray_count': 64, 'range_min': 0.1, 'range_max': 10.0, 'fov_horizontal': 360.0},
        'depth_camera': None,
        'safety_zones': {'warning': 0.5, 'critical': 0.2, 'stop': 0.05}
    },
    'MobileRobot': {
        'lidar': {'ray_count': 180, 'range_min': 0.1, 'range_max': 15.0, 'fov_horizontal': 270.0},
        'depth_camera': {'width': 640, 'height': 480, 'fov': 60.0, 'depth_min': 0.1, 'depth_max': 10.0},
        'safety_zones': {'warning': 1.0, 'critical': 0.3, 'stop': 0.1}
    },
    'Collaborative': {
        'lidar': {'ray_count': 128, 'range_min': 0.1, 'range_max': 5.0, 'fov_horizontal': 360.0},
        'depth_camera': None,
        'safety_zones': {'warning': 0.3, 'critical': 0.1, 'stop': 0.02}
    },
    'Humanoid': {
        'lidar': {'ray_count': 128, 'range_min': 0.1, 'range_max': 5.0, 'fov_horizontal': 360.0},
        'depth_camera': {'width': 640, 'height': 480, 'fov': 90.0, 'depth_min': 0.1, 'depth_max': 5.0},
        'safety_zones': {'warning': 0.8, 'critical': 0.3, 'stop': 0.1}
    },
    'Generic': {
        'lidar': {'ray_count': 32, 'range_min': 0.1, 'range_max': 10.0, 'fov_horizontal': 360.0},
        'depth_camera': None,
        'safety_zones': {'warning': 0.5, 'critical': 0.2, 'stop': 0.05}
    }
}


def calculate_robot_dimensions(
    actors_by_link: Dict[str, List['unreal.Actor']],
    verbose: bool = False
) -> Dict[str, float]:
    """
    Calculate robot dimensions from UE5 mesh bounds.
    
    Returns dimensions in METERS (DIMC expects meters, UE5 uses cm internally).
    
    Args:
        actors_by_link: Dict mapping link_name -> [actors]
        verbose: Print debug info
        
    Returns:
        Dict with width, height, length, bounding_radius (all in meters)
    """
    min_bounds = [float('inf'), float('inf'), float('inf')]
    max_bounds = [float('-inf'), float('-inf'), float('-inf')]
    
    for link_name, actors in actors_by_link.items():
        for actor in actors:
            try:
                # Get actor bounds
                origin, extent = actor.get_actor_bounds(only_colliding_components=False)
                
                # Calculate min/max from center and extent
                actor_min = [
                    origin.x - extent.x,
                    origin.y - extent.y,
                    origin.z - extent.z
                ]
                actor_max = [
                    origin.x + extent.x,
                    origin.y + extent.y,
                    origin.z + extent.z
                ]
                
                for i in range(3):
                    min_bounds[i] = min(min_bounds[i], actor_min[i])
                    max_bounds[i] = max(max_bounds[i], actor_max[i])
                    
            except Exception as e:
                if verbose:
                    print(f"        [WARN] Could not get bounds for {actor.get_actor_label()}: {e}")
    
    # Calculate dimensions (convert cm to meters)
    if min_bounds[0] == float('inf'):
        # No valid bounds found
        return {'width': 0.0, 'height': 0.0, 'length': 0.0, 'bounding_radius': 0.0, 'from_urdf': False}
    
    length = (max_bounds[0] - min_bounds[0]) / 100.0  # X axis -> meters
    width = (max_bounds[1] - min_bounds[1]) / 100.0   # Y axis -> meters
    height = (max_bounds[2] - min_bounds[2]) / 100.0  # Z axis -> meters
    
    # Bounding radius for sphere checks
    bounding_radius = math.sqrt(length**2 + width**2 + height**2) / 2.0
    
    if verbose:
        print(f"        [DIMS] L={length:.3f}m W={width:.3f}m H={height:.3f}m R={bounding_radius:.3f}m")
    
    return {
        'width': round(width, 4),
        'height': round(height, 4),
        'length': round(length, 4),
        'bounding_radius': round(bounding_radius, 4),
        'from_urdf': False  # Calculated from mesh, not URDF
    }


def parse_urdf_sensors(hierarchy_data: Dict, verbose: bool = False) -> List[Dict]:
    """
    Parse sensor definitions from URDF/hierarchy data.
    
    Looks for sensor information that FTI may have extracted from URDF <sensor> tags.
    Now supports the new v3.1 FTI format with full sensor parameters.
    
    Args:
        hierarchy_data: Parsed hierarchy JSON
        verbose: Print debug info
        
    Returns:
        List of sensor definitions for DIMC
    """
    sensors = []
    hierarchy = hierarchy_data.get('hierarchy', {})
    
    # Check if FTI extracted sensors (v3.1 format)
    urdf_sensors = hierarchy.get('sensors', [])
    
    for sensor in urdf_sensors:
        sensor_name = sensor.get('name', 'sensor')
        sensor_type = sensor.get('type', 'LIDAR')  # v3.1 already maps to DIMC types
        
        # Build sensor definition - v3.1 format is already DIMC-compatible
        sensor_def = {
            'sensor_name': sensor_name,
            'sensor_type': sensor_type,
            'mount_link_name': sensor.get('parent_link', 'base_link'),
            'mount_offset': sensor.get('origin', {'xyz': [0, 0, 0], 'rpy': [0, 0, 0]}),
            'from_urdf': sensor.get('from_urdf', True)
        }
        
        # Copy type-specific parameters from FTI
        if sensor_type == 'LIDAR':
            sensor_def['ray_count'] = sensor.get('ray_count', 360)
            sensor_def['range_min'] = sensor.get('range_min', 0.1)
            sensor_def['range_max'] = sensor.get('range_max', 10.0)
            sensor_def['fov_horizontal'] = sensor.get('fov_horizontal', 360.0)
            sensor_def['fov_vertical'] = sensor.get('fov_vertical', 30.0)
            sensor_def['vertical_layers'] = sensor.get('vertical_layers', 1)
            
        elif sensor_type == 'DepthCamera':
            sensor_def['image_width'] = sensor.get('image_width', 640)
            sensor_def['image_height'] = sensor.get('image_height', 480)
            sensor_def['camera_fov'] = sensor.get('camera_fov', 60.0)
            sensor_def['depth_min'] = sensor.get('depth_min', 0.1)
            sensor_def['depth_max'] = sensor.get('depth_max', 10.0)
            
        elif sensor_type == 'Ultrasonic':
            sensor_def['ultrasonic_range'] = sensor.get('ultrasonic_range', 2.0)
            sensor_def['beam_angle'] = sensor.get('beam_angle', 15.0)
            
        elif sensor_type == 'IMU':
            sensor_def['update_rate'] = sensor.get('update_rate', 100.0)
        
        sensors.append(sensor_def)
        
        if verbose:
            print(f"        [SENSOR] {sensor_name}: {sensor_type} on {sensor_def['mount_link_name']}")
    
    return sensors


def parse_safety_zones(hierarchy_data: Dict, dimensions: Dict, verbose: bool = False) -> Dict:
    """
    Parse safety zone configuration from URDF or calculate from dimensions.
    
    Now supports FTI v3.1 format with global_safety_zone and per-joint safety_controllers.
    
    Args:
        hierarchy_data: Parsed hierarchy JSON
        dimensions: Robot dimensions dict
        verbose: Print debug info
        
    Returns:
        Safety zone config for DIMC (all values in meters)
    """
    hierarchy = hierarchy_data.get('hierarchy', {})
    
    # Check for FTI v3.1 global_safety_zone (aggregated from all joints)
    global_safety = hierarchy.get('global_safety_zone', {})
    if global_safety and global_safety.get('from_urdf'):
        # Convert safety controller values to zone distances
        # k_position is typically 10-100, we scale to useful distances
        k_pos = global_safety.get('k_position', 0)
        return {
            'warning_zone': 0.5 if k_pos == 0 else max(0.5, 1.0 / k_pos * 10),
            'critical_zone': 0.2 if k_pos == 0 else max(0.2, 1.0 / k_pos * 5),
            'stop_zone': 0.05 if k_pos == 0 else max(0.05, 1.0 / k_pos),
            'from_urdf': True
        }
    
    # Check for individual safety_controllers (legacy format)
    safety_controllers = hierarchy.get('safety_controllers', {})
    if safety_controllers:
        # Use first available safety controller
        for joint_name, sc in safety_controllers.items():
            k_pos = sc.get('k_position', 0)
            if k_pos > 0:
                return {
                    'warning_zone': max(0.5, 1.0 / k_pos * 10),
                    'critical_zone': max(0.2, 1.0 / k_pos * 5),
                    'stop_zone': max(0.05, 1.0 / k_pos),
                    'from_urdf': True
                }
    
    # Calculate from dimensions (fallback)
    max_dim = max(dimensions.get('width', 0), dimensions.get('height', 0), dimensions.get('length', 0))
    
    if max_dim > 0:
        warning = max_dim * 1.5   # 1.5x max dimension
        critical = max_dim * 0.5  # 0.5x max dimension
        stop = max_dim * 0.1      # 0.1x max dimension
    else:
        # Absolute fallback
        warning = 0.5
        critical = 0.2
        stop = 0.05
    
    if verbose:
        print(f"        [SAFETY] Warning={warning:.2f}m Critical={critical:.2f}m Stop={stop:.2f}m (calculated)")
    
    return {
        'warning_zone': round(warning, 3),
        'critical_zone': round(critical, 3),
        'stop_zone': round(stop, 3),
        'from_urdf': False
    }


def detect_robot_type(hierarchy_data: Dict, controllable_joints: List[str], verbose: bool = False) -> str:
    """
    Detect robot type from URDF structure for DIMC profile selection.
    
    Uses joint names, link names, and DOF count to classify the robot.
    
    Args:
        hierarchy_data: Parsed hierarchy JSON
        controllable_joints: List of non-fixed joint names
        verbose: Print debug info
        
    Returns:
        Robot type string matching DIMC's ERobotType enum
    """
    hierarchy = hierarchy_data.get('hierarchy', {})
    joints_list = hierarchy.get('joints', [])
    links = hierarchy.get('links', {})
    if not links:
        links = hierarchy.get('nodes', {})
    
    dof = len(controllable_joints)
    joint_names_lower = [j.lower() for j in controllable_joints]
    link_names_lower = [l.lower() for l in links.keys()]
    
    # Check for mobile base indicators
    has_wheels = any('wheel' in j or 'caster' in j or 'drive' in j for j in joint_names_lower)
    has_tracks = any('track' in j for j in joint_names_lower)
    
    # Check for humanoid indicators
    has_legs = any('leg' in l or 'ankle' in l or 'knee' in l or 'hip' in l for l in link_names_lower)
    has_arms = any('arm' in l or 'elbow' in l or 'shoulder' in l for l in link_names_lower)
    
    # Check for drone indicators
    has_rotors = any('rotor' in j or 'propeller' in j or 'motor' in j for j in joint_names_lower)
    
    # Check for collaborative robot patterns (UR, Franka, etc.)
    robot_name = hierarchy_data.get('robot_name', '').lower()
    is_cobot = any(c in robot_name for c in ['ur3', 'ur5', 'ur10', 'ur16', 'ur20', 'ur30', 'franka', 'panda', 'iiwa', 'sawyer', 'baxter'])
    
    # Classify
    robot_type = 'Generic'
    
    if has_rotors and dof >= 4:
        robot_type = 'Drone'
    elif has_legs and has_arms:
        robot_type = 'Humanoid'
    elif has_wheels or has_tracks:
        robot_type = 'MobileRobot'
    elif is_cobot or (dof >= 6 and dof <= 7):
        robot_type = 'Collaborative'
    elif dof >= 4 and dof <= 8:
        robot_type = 'IndustrialArm'
    elif dof == 1:
        robot_type = 'SingleActuator'
    
    if verbose:
        print(f"        [TYPE] Detected: {robot_type} (DOF={dof})")
    
    return robot_type


def apply_default_sensors(robot_type: str, dimensions: Dict, verbose: bool = False) -> List[Dict]:
    """
    Apply default sensor profile based on robot type.
    
    Used when URDF doesn't define sensors.
    
    Args:
        robot_type: Detected robot type
        dimensions: Robot dimensions for positioning
        verbose: Print debug info
        
    Returns:
        List of default sensor definitions
    """
    profile = DEFAULT_SENSOR_PROFILES.get(robot_type, DEFAULT_SENSOR_PROFILES['Generic'])
    sensors = []
    
    # Default LIDAR
    lidar_config = profile.get('lidar')
    if lidar_config:
        # Mount LIDAR at top center of robot
        mount_height = dimensions.get('height', 0.5)
        
        sensors.append({
            'sensor_name': 'default_lidar',
            'sensor_type': 'LIDAR',
            'mount_link_name': 'base_link',
            'mount_offset': {
                'position': [0, 0, mount_height],
                'rotation': [0, 0, 0]
            },
            'ray_count': lidar_config['ray_count'],
            'range_min': lidar_config['range_min'],
            'range_max': lidar_config['range_max'],
            'fov_horizontal': lidar_config['fov_horizontal'],
            'fov_vertical': 30.0,
            'vertical_layers': 1,
            'from_urdf': False
        })
        
        if verbose:
            print(f"        [SENSOR] Applied default LIDAR profile for {robot_type}")
    
    # Default depth camera
    depth_config = profile.get('depth_camera')
    if depth_config:
        sensors.append({
            'sensor_name': 'default_depth_camera',
            'sensor_type': 'DepthCamera',
            'mount_link_name': 'base_link',
            'mount_offset': {
                'position': [dimensions.get('length', 0.2) / 2, 0, dimensions.get('height', 0.3)],
                'rotation': [0, 0, 0]
            },
            'image_width': depth_config['width'],
            'image_height': depth_config['height'],
            'camera_fov': depth_config['fov'],
            'depth_min': depth_config['depth_min'],
            'depth_max': depth_config['depth_max'],
            'from_urdf': False
        })
        
        if verbose:
            print(f"        [SENSOR] Applied default depth camera for {robot_type}")
    
    return sensors


def export_robot_config_for_dimc(
    robot_name: str,
    hierarchy_data: Dict,
    actors_by_link: Dict[str, List['unreal.Actor']],
    root_actor: 'unreal.Actor' = None,
    output_path: str = None,
    verbose: bool = False
) -> str:
    """
    Export robot configuration for DIMC (Dimensions Collector).
    
    Creates a JSON file with ALL information DIMC needs:
    - RobotID and RobotName (REQUIRED)
    - RobotActor reference info (REQUIRED)
    - Dimensions (calculated from mesh if not in URDF)
    - Sensors (from URDF or default profile)
    - SafetyZones (from URDF or calculated)
    - RobotType (auto-detected)
    - DataFlags (what was found vs calculated)
    
    Args:
        robot_name: Name of the robot
        hierarchy_data: Parsed hierarchy JSON
        actors_by_link: Dict mapping link_name -> [actors]
        root_actor: The main robot actor (base_link actor)
        output_path: Where to save JSON
        verbose: Print debug info
        
    Returns:
        Path to created JSON file
    """
    try:
        if verbose:
            print("\n  [DIMC] Exporting robot configuration...")
        
        hierarchy = hierarchy_data.get('hierarchy', {})
        root_nodes = hierarchy.get('root_nodes', [])
        
        # Get or find root actor
        if root_actor is None and root_nodes:
            root_link_actors = actors_by_link.get(root_nodes[0], [])
            if root_link_actors:
                root_actor = root_link_actors[0]
        
        root_actor_name = root_actor.get_actor_label() if root_actor else ''
        root_actor_path = f"/Game/Robots/{robot_name}/Parts/{root_actor_name}" if root_actor_name else ''
        
        # Calculate dimensions from mesh bounds
        dimensions = calculate_robot_dimensions(actors_by_link, verbose)
        
        # Get controllable joints for robot type detection
        joints_list = hierarchy.get('joints', [])
        controllable_joints = [j.get('name') for j in joints_list if j.get('type', 'fixed') != 'fixed']
        
        # Detect robot type
        robot_type = detect_robot_type(hierarchy_data, controllable_joints, verbose)
        
        # Parse sensors from URDF
        sensors = parse_urdf_sensors(hierarchy_data, verbose)
        has_urdf_sensors = len(sensors) > 0
        
        # Apply default sensors if none found in URDF
        if not sensors:
            sensors = apply_default_sensors(robot_type, dimensions, verbose)
        
        # Parse or calculate safety zones
        safety_zones = parse_safety_zones(hierarchy_data, dimensions, verbose)
        
        # Get collision mesh info (first actor's mesh)
        collision_mesh_path = ''
        if root_actor:
            try:
                mesh_comp = root_actor.get_component_by_class(unreal.StaticMeshComponent)
                if mesh_comp and mesh_comp.static_mesh:
                    collision_mesh_path = mesh_comp.static_mesh.get_path_name()
            except:
                pass
        
        # Build data flags (what was found vs calculated)
        data_flags = {
            'has_dimensions': dimensions.get('from_urdf', False),
            'has_sensors': has_urdf_sensors,
            'has_safety_zones': safety_zones.get('from_urdf', False),
            'has_collision_mesh': bool(collision_mesh_path),
            'has_joint_limits': any(j.get('limits') for j in joints_list)
        }
        
        # Get link-to-actor mapping for DIMC
        links_info = []
        for link_name, actors in actors_by_link.items():
            if actors:
                actor = actors[0]
                links_info.append({
                    'link_name': link_name,
                    'actor_name': actor.get_actor_label(),
                    'is_root': link_name in root_nodes
                })
        
        # Construct full DIMC config (ALL requirements)
        dimc_config = {
            # ===== REQUIRED FIELDS =====
            'robot_id': f"{robot_name}_001",
            'robot_name': robot_name,
            'robot_actor': {
                'actor_name': root_actor_name,
                'actor_path': root_actor_path,
                'actor_class': 'StaticMeshActor'
            },
            
            # ===== DIMENSIONS =====
            'dimensions': {
                'width': dimensions['width'],      # Y axis (meters)
                'height': dimensions['height'],    # Z axis (meters)
                'length': dimensions['length'],    # X axis (meters)
                'bounding_radius': dimensions['bounding_radius'],
                'from_urdf': dimensions.get('from_urdf', False)
            },
            
            # ===== SENSORS =====
            'sensors': sensors,
            
            # ===== SAFETY ZONES (all in meters) =====
            'safety_zones': {
                'warning_zone': safety_zones['warning_zone'],
                'critical_zone': safety_zones['critical_zone'],
                'stop_zone': safety_zones['stop_zone'],
                'from_urdf': safety_zones.get('from_urdf', False)
            },
            
            # ===== COLLISION MESH =====
            'collision_mesh': {
                'mesh_path': collision_mesh_path,
                'use_complex_collision': False
            },
            
            # ===== ROBOT TYPE =====
            'robot_type': robot_type,
            
            # ===== DATA FLAGS =====
            'data_flags': data_flags,
            
            # ===== ADDITIONAL INFO =====
            'source_file': hierarchy_data.get('source_file', ''),
            'export_timestamp': time.time(),
            'links': links_info,
            'dof': len(controllable_joints),
            
            # ===== UE5 SPECIFIC =====
            'ue5_info': {
                'units': 'meters',  # DIMC expects meters
                'coordinate_system': 'left_handed',
                'content_folder': f"/Game/Robots/{robot_name}"
            }
        }
        
        # Determine output path
        if output_path is None:
            fti_storage = "D:/ROA/.fti_storage"
            if os.path.isdir(fti_storage):
                output_path = os.path.join(fti_storage, f"{robot_name}_dimc_config.json")
            else:
                output_path = os.path.join(tempfile.gettempdir(), f"{robot_name}_dimc_config.json")
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Write JSON
        with open(output_path, 'w') as f:
            json.dump(dimc_config, f, indent=2)
        
        if verbose:
            print(f"  [DIMC] Exported config: {output_path}")
            print(f"         Type: {robot_type}, Sensors: {len(sensors)}, DOF: {len(controllable_joints)}")
            print(f"         Dims: {dimensions['length']:.2f}L x {dimensions['width']:.2f}W x {dimensions['height']:.2f}H (m)")
            flags_true = [k for k, v in data_flags.items() if v]
            print(f"         From URDF: {', '.join(flags_true) if flags_true else 'dimensions calculated'}")
        
        return output_path
        
    except Exception as e:
        if verbose:
            print(f"  [ERROR] Failed to export DIMC config: {e}")
            import traceback
            traceback.print_exc()
        return ""


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
                if filename.lower().startswith(robot_name) and filename.endswith('_hierarchy.json'):
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
        with open(hierarchy_path, 'r') as f:
            data = json.load(f)
        
        # Validate it's from ROA-FTI
        if data.get('export_source') != 'ROA-FTI':
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
    hierarchy = hierarchy_data.get('hierarchy', {})
    nodes = hierarchy.get('nodes', {})
    
    if link_name not in nodes:
        return None
    
    node = nodes[link_name]
    properties = node.get('properties', {})
    
    # Check for visual_origin in properties
    visual_origin = properties.get('visual_origin')
    if visual_origin:
        return visual_origin
    
    return None


def apply_visual_origin(link_pos: List[float], link_quat: List[float], 
                        visual_origin: Dict, scale: float = 100.0) -> Tuple[List[float], List[float]]:
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
    xyz = visual_origin.get('xyz', [0, 0, 0])
    rpy = visual_origin.get('rpy', [0, 0, 0])
    
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
    
    hierarchy = hierarchy_data.get('hierarchy', {})
    nodes = hierarchy.get('nodes', {})
    root_nodes = hierarchy.get('root_nodes', [])
    
    # Default scale: URDF meters to UE5 centimeters
    scale = 100.0
    
    transforms = {}  # link_name -> {'position': [x,y,z], 'quaternion': [x,y,z,w]}
    
    # Build a map of joint transforms: child_link -> joint_transform
    # In URDF, a joint connects parent_link to child_link with a transform
    joint_transforms = {}
    for node_name, node in nodes.items():
        if node.get('type') == 'joint':
            transform = node.get('transform')
            # The child_link is stored directly in the joint's properties
            child_link = node.get('properties', {}).get('child_link')
            if child_link and transform:
                joint_transforms[child_link] = transform
    
    def process_link(link_name: str, parent_pos: List[float], parent_quat: List[float]):
        """Recursively process links to compute world transforms."""
        if link_name not in nodes:
            return
        
        node = nodes[link_name]
        if node.get('type') != 'link':
            return
        
        # Get the joint transform that positions this link relative to parent
        transform = joint_transforms.get(link_name, {})
        
        if isinstance(transform, dict):
            xyz = transform.get('xyz', [0, 0, 0])
            rpy = transform.get('rpy', [0, 0, 0])
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
        transforms[link_name] = {
            'position': world_pos,
            'quaternion': world_quat
        }
        
        # Process children (other links)
        for child in node.get('children', []):
            if child in nodes and nodes[child].get('type') == 'link':
                process_link(child, world_pos, world_quat)
    
    # Process from each root
    identity_quat = [0.0, 0.0, 0.0, 1.0]
    for root in root_nodes:
        # Root link starts at origin
        transforms[root] = {
            'position': list(origin),
            'quaternion': identity_quat
        }
        # Process children of root
        if root in nodes:
            for child in nodes[root].get('children', []):
                if child in nodes and nodes[child].get('type') == 'link':
                    process_link(child, origin, identity_quat)
    
    return transforms


def compute_joint_world_positions_from_actors(
    joints_list: List[Dict],
    actors_by_link: Dict[str, List['unreal.Actor']],
    verbose: bool = False
) -> Dict[str, 'unreal.Vector']:
    """
    Compute world positions for joints using actual actor mesh bounds.
    
    This is more accurate than using URDF kinematic chain because:
    - USD import bakes visual origins into mesh positions
    - Actor mesh bounds reflect actual geometry placement in UE5
    
    Strategy: Place constraint at the geometric interface between parent and child meshes.
    We find the closest axis-aligned face between parent and child bounding boxes.
    
    Args:
        joints_list: List of joint dictionaries from hierarchy
        actors_by_link: Map of link names to their UE5 actors
        verbose: Print debug info
        
    Returns:
        Dictionary mapping joint names to world positions (unreal.Vector)
    """
    joint_positions = {}
    
    for joint in joints_list:
        joint_name = joint.get('name', '')
        parent_link = joint.get('parent_link', '')
        child_link = joint.get('child_link', '')
        joint_type = joint.get('type', 'fixed')
        axis = joint.get('axis', [1, 0, 0])
        
        parent_actors = actors_by_link.get(parent_link, [])
        child_actors = actors_by_link.get(child_link, [])
        
        if not parent_actors or not child_actors:
            continue
        
        # Get visual actors (prefer visual over collision)
        parent_actor = get_visual_actor(parent_actors)
        child_actor = get_visual_actor(child_actors)
        
        if not parent_actor or not child_actor:
            continue
        
        # Get mesh bounds for both actors
        parent_bounds = get_actor_mesh_bounds(parent_actor)
        child_bounds = get_actor_mesh_bounds(child_actor)
        
        if parent_bounds and child_bounds:
            parent_center = parent_bounds['center']
            parent_extent = parent_bounds['extent']
            child_center = child_bounds['center']
            child_extent = child_bounds['extent']
            
            # Find the interface point between parent and child
            # Strategy: Find the closest faces on each bounding box
            # The joint should be at the midpoint between these faces
            
            # Compute direction from parent to child
            dx = child_center.x - parent_center.x
            dy = child_center.y - parent_center.y
            dz = child_center.z - parent_center.z
            
            # Determine which axis has the largest separation (likely the connection axis)
            abs_dx, abs_dy, abs_dz = abs(dx), abs(dy), abs(dz)
            
            if abs_dx >= abs_dy and abs_dx >= abs_dz:
                # Connected along X axis
                if dx > 0:
                    # Child is to the +X of parent
                    parent_face_x = parent_center.x + parent_extent.x
                    child_face_x = child_center.x - child_extent.x
                else:
                    # Child is to the -X of parent
                    parent_face_x = parent_center.x - parent_extent.x
                    child_face_x = child_center.x + child_extent.x
                joint_x = (parent_face_x + child_face_x) / 2
                joint_y = (parent_center.y + child_center.y) / 2
                joint_z = (parent_center.z + child_center.z) / 2
            elif abs_dy >= abs_dx and abs_dy >= abs_dz:
                # Connected along Y axis
                if dy > 0:
                    parent_face_y = parent_center.y + parent_extent.y
                    child_face_y = child_center.y - child_extent.y
                else:
                    parent_face_y = parent_center.y - parent_extent.y
                    child_face_y = child_center.y + child_extent.y
                joint_x = (parent_center.x + child_center.x) / 2
                joint_y = (parent_face_y + child_face_y) / 2
                joint_z = (parent_center.z + child_center.z) / 2
            else:
                # Connected along Z axis
                if dz > 0:
                    parent_face_z = parent_center.z + parent_extent.z
                    child_face_z = child_center.z - child_extent.z
                else:
                    parent_face_z = parent_center.z - parent_extent.z
                    child_face_z = child_center.z + child_extent.z
                joint_x = (parent_center.x + child_center.x) / 2
                joint_y = (parent_center.y + child_center.y) / 2
                joint_z = (parent_face_z + child_face_z) / 2
            
            joint_pos = unreal.Vector(joint_x, joint_y, joint_z)
            
            if verbose:
                print(f"        {joint_name}: parent=({parent_center.x:.1f}, {parent_center.y:.1f}, {parent_center.z:.1f}) "
                      f"child=({child_center.x:.1f}, {child_center.y:.1f}, {child_center.z:.1f}) "
                      f"-> joint=({joint_pos.x:.1f}, {joint_pos.y:.1f}, {joint_pos.z:.1f})")
        else:
            # Fallback: use midpoint between actor locations
            parent_loc = parent_actor.get_actor_location()
            child_loc = child_actor.get_actor_location()
            joint_pos = unreal.Vector(
                (parent_loc.x + child_loc.x) / 2,
                (parent_loc.y + child_loc.y) / 2,
                (parent_loc.z + child_loc.z) / 2
            )
            if verbose:
                print(f"        {joint_name}: Using actor midpoint (bounds unavailable)")
        
        joint_positions[joint_name] = joint_pos
    
    return joint_positions


def get_actor_mesh_bounds(actor: 'unreal.Actor') -> Optional[Dict]:
    """
    Get the world-space mesh bounds (center and extent) for an actor.
    
    For USD-imported meshes, the actor origin might be at a common import point,
    but the mesh geometry is at a different location (visual origins baked in).
    We need the TRUE world-space bounds of the mesh, not actor origin + local bounds.
    
    Args:
        actor: UE5 Actor with a static mesh component
        
    Returns:
        Dict with 'center' and 'extent' as unreal.Vector, or None
    """
    try:
        # Try to get static mesh component
        mesh_comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        if not mesh_comp:
            # Fallback for static mesh actors
            if hasattr(actor, 'static_mesh_component'):
                mesh_comp = actor.static_mesh_component
        
        if mesh_comp:
            # Method 1: Use Bounds property which gives world-space box
            # This is the most accurate for USD imports with baked visual origins
            try:
                # Get world bounds (origin and extent)
                bounds_origin, bounds_extent = mesh_comp.bounds.origin, mesh_comp.bounds.box_extent
                center = unreal.Vector(bounds_origin.x, bounds_origin.y, bounds_origin.z)
                extent = unreal.Vector(bounds_extent.x, bounds_extent.y, bounds_extent.z)
                return {'center': center, 'extent': extent}
            except:
                pass
            
            # Method 2: Get component world bounds
            try:
                min_bound, max_bound = mesh_comp.get_local_bounds()
                comp_loc = mesh_comp.get_component_location()
                center = unreal.Vector(
                    comp_loc.x + (min_bound.x + max_bound.x) / 2,
                    comp_loc.y + (min_bound.y + max_bound.y) / 2,
                    comp_loc.z + (min_bound.z + max_bound.z) / 2
                )
                extent = unreal.Vector(
                    abs(max_bound.x - min_bound.x) / 2,
                    abs(max_bound.y - min_bound.y) / 2,
                    abs(max_bound.z - min_bound.z) / 2
                )
                return {'center': center, 'extent': extent}
            except:
                pass
            
            # Method 3: Fallback to actor bounds
            try:
                origin, extent = actor.get_actor_bounds(False)
                return {'center': origin, 'extent': extent}
            except:
                pass
    except Exception as e:
        pass
    return None


def compute_joint_world_positions(hierarchy_data: Dict, import_offset: 'unreal.Vector' = None) -> Dict[str, 'unreal.Vector']:
    """
    Compute world positions for all joints using hierarchy data.
    
    This is essential for correct constraint placement when USD import
    places all actors at a common pivot point.
    
    For each joint, the world position is:
    - parent_link_world_position + joint_origin_offset (converted to UE5 coords)
    
    Args:
        hierarchy_data: The loaded hierarchy dictionary
        import_offset: The offset where USD actors were imported (from actor location)
        
    Returns:
        Dictionary mapping joint names to world positions (unreal.Vector)
    """
    if import_offset is None:
        import_offset = unreal.Vector(0, 0, 0)
    
    # Compute link world transforms from hierarchy
    # Note: we use [0,0,0] as origin since import_offset is added separately
    link_transforms = compute_link_transforms(hierarchy_data, [0.0, 0.0, 0.0])
    
    hierarchy = hierarchy_data.get('hierarchy', {})
    joints_list = hierarchy.get('joints', [])
    
    joint_positions = {}
    scale = 100.0  # meters to cm
    
    for joint in joints_list:
        joint_name = joint.get('name', '')
        parent_link = joint.get('parent_link', '')
        origin = joint.get('origin', {})
        origin_xyz = origin.get('xyz', [0, 0, 0])
        
        # Get parent link world position from computed transforms
        parent_transform = link_transforms.get(parent_link)
        if parent_transform:
            parent_pos = parent_transform['position']
            parent_quat = parent_transform['quaternion']
        else:
            # Parent not found - use origin
            parent_pos = [0, 0, 0]
            parent_quat = [0, 0, 0, 1]
        
        # Convert joint origin offset to UE5 coordinates
        joint_offset_ue5 = ros_position_to_ue5(origin_xyz, scale)
        
        # Apply parent rotation to joint offset
        rotated_offset = quaternion_rotate_vector(parent_quat, joint_offset_ue5)
        
        # Joint world position = import_offset + parent_pos + rotated_offset
        joint_world_pos = unreal.Vector(
            import_offset.x + parent_pos[0] + rotated_offset[0],
            import_offset.y + parent_pos[1] + rotated_offset[1],
            import_offset.z + parent_pos[2] + rotated_offset[2]
        )
        
        joint_positions[joint_name] = joint_world_pos
    
    return joint_positions


def compute_joint_world_axes(hierarchy_data: Dict) -> Dict[str, List[float]]:
    """
    Compute world-frame rotation axes for all joints using hierarchy data.
    
    URDF joint axes are in the JOINT'S LOCAL FRAME, which is rotated by:
    1. The parent link's accumulated world rotation
    2. The joint's own origin RPY rotation
    
    For correct UE5 constraint configuration, we need the axis in WORLD FRAME.
    This function transforms each joint's local axis to world coordinates.
    
    Args:
        hierarchy_data: The loaded hierarchy dictionary
        
    Returns:
        Dictionary mapping joint names to world-frame axis [X, Y, Z] in UE5 coords.
        The axis is normalized and has Y flipped for ROS→UE5 conversion.
    """
    # Compute link world transforms from hierarchy
    link_transforms = compute_link_transforms(hierarchy_data, [0.0, 0.0, 0.0])
    
    hierarchy = hierarchy_data.get('hierarchy', {})
    joints_list = hierarchy.get('joints', [])
    
    world_axes = {}
    
    for joint in joints_list:
        joint_name = joint.get('name', '')
        parent_link = joint.get('parent_link', '')
        origin = joint.get('origin', {})
        origin_rpy = origin.get('rpy', [0, 0, 0])
        local_axis = joint.get('axis', [0, 0, 1])  # URDF local axis
        
        # Get parent link world rotation (as quaternion)
        parent_transform = link_transforms.get(parent_link)
        if parent_transform:
            parent_quat = parent_transform['quaternion']
        else:
            parent_quat = [0, 0, 0, 1]  # Identity
        
        # Apply joint origin rotation to get joint frame orientation
        joint_origin_quat = rpy_to_quaternion(origin_rpy)
        joint_world_quat = quaternion_multiply(parent_quat, joint_origin_quat)
        
        # Transform local axis to world frame using joint's world orientation
        world_axis_ros = quaternion_rotate_vector(joint_world_quat, local_axis)
        
        # Convert from ROS to UE5 coordinates (flip Y)
        # ROS: X-forward, Y-left, Z-up
        # UE5: X-forward, Y-right, Z-up
        world_axis_ue5 = [
            world_axis_ros[0],   # X stays
            -world_axis_ros[1],  # Y flips
            world_axis_ros[2]    # Z stays
        ]
        
        # Normalize (should already be unit length, but be safe)
        length = (world_axis_ue5[0]**2 + world_axis_ue5[1]**2 + world_axis_ue5[2]**2) ** 0.5
        if length > 0.001:
            world_axis_ue5 = [c / length for c in world_axis_ue5]
        
        world_axes[joint_name] = world_axis_ue5
    
    return world_axes


# =============================================================================
# ACTOR FINDING AND MATCHING
# =============================================================================

def find_robot_actors(
    robot_name: str = "",
    link_names: List[str] = None,
    reference_position: 'unreal.Vector' = None,
    position_tolerance: float = 1000.0
) -> Dict[str, List[Any]]:
    """
    Find all mesh actors in the level that belong to a specific robot.
    
    USD import creates actors with labels like:
    - "base_link_inertia_visual" (from mesh name)
    - "shoulder_link_visual" (from mesh name)
    
    **CRITICAL**: Multiple robots (e.g., UR10 and UR18) may have IDENTICAL link names!
    This function uses TWO strategies to disambiguate:
    
    1. **Robot Name Prefix** (preferred): If actors have robot name in their label/path
       (e.g., "ur10_shoulder_link_visual"), they are matched to that robot.
    
    2. **Position Clustering**: When multiple robots have same link names, we use
       reference_position (from hierarchy JSON's expected import location) to filter
       actors that are spatially close to each other (part of the same robot).
    
    Args:
        robot_name: Robot name to filter by (e.g., "ur10", "ur18")
        link_names: List of link names from hierarchy to match against mesh names
        reference_position: Expected world position of this robot (used for clustering)
                           If None, will try to detect from first matched actor
        position_tolerance: Max distance in cm from reference to consider actors part of same robot
        
    Returns:
        Dictionary mapping link names to lists of actor objects (visual + collision)
    """
    editor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = editor_subsystem.get_all_level_actors()
    
    robot_actors = {}  # link_name -> [actor1, actor2, ...]
    robot_name_lower = robot_name.lower() if robot_name else ""
    
    # Build patterns to match - we need to find "base_link" in "base_link_inertia_visual"
    link_patterns = []
    if link_names:
        for link in link_names:
            link_lower = link.lower()
            link_patterns.append((link_lower, link))
        # Sort by length descending so longer/more specific patterns match first
        link_patterns.sort(key=lambda x: len(x[0]), reverse=True)
    
    # PHASE 1: Collect all candidate actors with their match info
    candidates = []  # [(actor, matched_link, has_robot_prefix), ...]
    
    for actor in all_actors:
        if not isinstance(actor, unreal.StaticMeshActor):
            continue
        
        # Get the actor label - this is typically the mesh name after USD import
        actor_label = actor.get_actor_label().lower()
        
        # Also check mesh asset name and asset path (may contain robot name)
        mesh_name = ""
        asset_path = ""
        mesh_component = actor.static_mesh_component
        if mesh_component and mesh_component.static_mesh:
            mesh_name = mesh_component.static_mesh.get_name().lower()
            try:
                asset_path = mesh_component.static_mesh.get_path_name().lower()
            except:
                pass
        
        # Combined name for matching
        search_text = f"{actor_label} {mesh_name} {asset_path}"
        
        # Check if actor has robot name prefix (e.g., "ur10_" or "/ur10/")
        has_robot_prefix = False
        if robot_name_lower:
            # Look for robot name as prefix, path segment, or standalone
            prefixes_to_check = [
                f"{robot_name_lower}_",      # ur10_shoulder_link
                f"/{robot_name_lower}/",     # /ur10/shoulder_link
                f"{robot_name_lower}/",      # ur10/shoulder_link
                f"_{robot_name_lower}_",     # prefix_ur10_shoulder
            ]
            for prefix in prefixes_to_check:
                if prefix in search_text:
                    has_robot_prefix = True
                    break
        
        matched_link = None
        
        if link_patterns:
            # Find the best matching link (longest/most specific pattern wins)
            for pattern, original_name in link_patterns:
                # Check if the link name is in the actor label or mesh name
                if pattern in search_text:
                    # Verify this is a visual or collision mesh
                    if any(suffix in search_text for suffix in ['visual', 'collision', 'mesh', '_link']):
                        matched_link = original_name
                        break
                    else:
                        matched_link = original_name
                        break
        elif robot_name_lower:
            # Fallback: filter by robot name in actor label
            if robot_name_lower in actor_label or robot_name_lower in mesh_name:
                matched_link = actor_label.replace('_visual', '').replace('_collision', '')
        else:
            # No filter - try to determine if this is a robot part
            if any(x in search_text for x in ['_link', '_visual', '_collision', '_inertia']):
                matched_link = actor_label.replace('_visual', '').replace('_collision', '')
        
        if matched_link:
            candidates.append((actor, matched_link, has_robot_prefix))
    
    # PHASE 2: Filter candidates - prefer those with robot prefix, or use position clustering
    
    # First, check if we have any candidates with the robot prefix
    prefixed_candidates = [(a, link, prefix) for a, link, prefix in candidates if prefix]
    unprefixed_candidates = [(a, link, prefix) for a, link, prefix in candidates if not prefix]
    
    if prefixed_candidates:
        # Use only prefixed candidates (we can clearly identify this robot's actors)
        final_candidates = prefixed_candidates
    elif reference_position is not None and unprefixed_candidates:
        # No prefix found, use position clustering to disambiguate
        # Only accept actors within tolerance of reference position
        final_candidates = []
        for actor, link, prefix in unprefixed_candidates:
            actor_pos = actor.get_actor_location()
            distance = math.sqrt(
                (actor_pos.x - reference_position.x) ** 2 +
                (actor_pos.y - reference_position.y) ** 2 +
                (actor_pos.z - reference_position.z) ** 2
            )
            if distance <= position_tolerance:
                final_candidates.append((actor, link, prefix))
    else:
        # No prefix and no reference position - use all candidates (old behavior)
        # WARNING: This may mix actors from multiple robots!
        final_candidates = candidates
    
    # PHASE 3: Group final candidates by link name
    for actor, matched_link, _ in final_candidates:
        if matched_link not in robot_actors:
            robot_actors[matched_link] = []
        robot_actors[matched_link].append(actor)
    
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
    for suffix in ['_mesh', '_visual', '_collision', '_link', '_0', '_1']:
        clean_actor = clean_actor.replace(suffix, '')
    
    for link in link_names:
        clean_link = link.lower().replace('_link', '')
        if clean_link in clean_actor or clean_actor in clean_link:
            return link
    
    return None


def get_visual_actor(actors: List['unreal.Actor']) -> 'unreal.Actor':
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
        if 'visual' in label:
            return actor
    
    # If no visual found, try to avoid collision
    for actor in actors:
        label = actor.get_actor_label().lower()
        if 'collision' not in label:
            return actor
    
    # Fallback to first actor
    return actors[0]


def detect_robot_reference_position(
    robot_name: str,
    link_names: List[str],
    prefer_selected: bool = True
) -> Optional['unreal.Vector']:
    """
    Detect the reference position for a robot to enable position-based filtering.
    
    This is useful when multiple robots have identical link names and we need
    to determine which actors belong to which robot.
    
    Strategies (in order of preference):
    1. If user has selected an actor, use that actor's position
    2. Look for actors with robot name in path (prefixed naming)
    3. Look for "base_link" actor that's not already assigned
    
    Args:
        robot_name: Robot name (e.g., "ur18")
        link_names: List of link names from hierarchy
        prefer_selected: If True, use currently selected actor as reference
        
    Returns:
        Reference position vector or None if detection failed
    """
    editor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    
    # Strategy 1: Use currently selected actor if user has selected one
    if prefer_selected:
        try:
            selected = editor_subsystem.get_selected_level_actors()
            if selected:
                for actor in selected:
                    if isinstance(actor, unreal.StaticMeshActor):
                        actor_label = actor.get_actor_label().lower()
                        # Check if it looks like a robot part
                        if any(x in actor_label for x in ['_link', '_visual', '_collision']):
                            pos = actor.get_actor_location()
                            return pos
        except:
            pass
    
    # Strategy 2: Look for actors with robot name prefix
    all_actors = editor_subsystem.get_all_level_actors()
    robot_name_lower = robot_name.lower()
    
    for actor in all_actors:
        if not isinstance(actor, unreal.StaticMeshActor):
            continue
        
        actor_label = actor.get_actor_label().lower()
        
        # Check for robot name prefix
        if f"{robot_name_lower}_" in actor_label or f"/{robot_name_lower}/" in actor_label:
            pos = actor.get_actor_location()
            return pos
    
    # Strategy 3: Look for any "base_link" actor
    # This is risky if there are multiple robots, so we just take the first one
    # The user should select an actor to disambiguate
    for actor in all_actors:
        if not isinstance(actor, unreal.StaticMeshActor):
            continue
        
        actor_label = actor.get_actor_label().lower()
        if 'base_link' in actor_label and 'visual' in actor_label:
            pos = actor.get_actor_location()
            return pos
    
    return None


# =============================================================================
# MATERIAL APPLICATION
# =============================================================================

def create_dynamic_material(color: List[float], mat_name: str = "ROA_Material", outer: Any = None) -> 'unreal.MaterialInstanceDynamic':
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
            '/Engine/BasicShapes/BasicShapeMaterial',
            '/Engine/EngineMaterials/DefaultMaterial',
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
                for param_name in ['BaseColor', 'Base Color', 'Color', 'Tint']:
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


def apply_color_override(actor: 'unreal.StaticMeshActor', color: List[float], verbose: bool = False) -> bool:
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
                        for param in ['BaseColor', 'Base Color', 'Color', 'Tint', 'DiffuseColor', 'Diffuse']:
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
                        '/Engine/BasicShapes/BasicShapeMaterial',
                        '/Engine/EngineMaterials/DefaultMaterial',
                    ]
                    world = unreal.EditorLevelLibrary.get_editor_world()
                    for base_path in base_paths:
                        base_mat = unreal.EditorAssetLibrary.load_asset(base_path)
                        if base_mat:
                            dynamic_mat = unreal.KismetMaterialLibrary.create_dynamic_material_instance(
                                world, base_mat
                            )
                            if dynamic_mat:
                                linear_color = unreal.LinearColor(r, g, b, a)
                                for param in ['BaseColor', 'Base Color', 'Color']:
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


def apply_material_to_actor(actor: 'unreal.StaticMeshActor', color: List[float], mat_name: str = "", verbose: bool = False):
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
    hierarchy = hierarchy_data.get('hierarchy', {})
    materials = hierarchy.get('materials', {})
    link_materials = hierarchy.get('link_materials', {})
    
    # Get material names for this link
    mat_names = link_materials.get(link_name, [])
    
    if not mat_names:
        return None
    
    # Use first material
    mat_name = mat_names[0]
    mat_data = materials.get(mat_name, {})
    
    return mat_data.get('color')


# =============================================================================
# MAIN ASSEMBLY FUNCTIONS
# =============================================================================

def assemble_robot(
    robot_name_or_path: str,
    origin: List[float] = None,
    verbose: bool = True,
    materials_only: bool = True,
    create_constraints: bool = True
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
    
    robot_name = hierarchy_data.get('robot_name', 'robot')
    if verbose:
        print(f"      Robot: {robot_name}")
        hierarchy = hierarchy_data.get('hierarchy', {})
        print(f"      Links: {len([n for n, d in hierarchy.get('nodes', {}).items() if d.get('type') == 'link'])}")
    
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
        hierarchy = hierarchy_data.get('hierarchy', {})
        link_names = [n for n, d in hierarchy.get('nodes', {}).items() if d.get('type') == 'link']
        if verbose:
            print("\n[3/4] Skipping transform computation (materials_only mode)")
            print(f"      USD import already positioned actors correctly")
    
    # Step 4: Find actors
    if verbose:
        step_name = "Finding actors..." if materials_only else "Assembling robot..."
        print(f"\n[4/5] {step_name}")
    
    # Note: link_names was already set above (either from transforms or from hierarchy)
    # Do NOT overwrite it here - that was causing the empty list bug!
    
    # IMPORTANT: Multiple robots may have identical link names (e.g., UR10 and UR18 both have "shoulder_link")
    # We need to detect a reference position to disambiguate which actors belong to THIS robot.
    # If user has selected an actor from the target robot, use that as reference.
    reference_position = detect_robot_reference_position(robot_name, link_names, prefer_selected=True)
    
    if reference_position and verbose:
        print(f"      Reference position for '{robot_name}': ({reference_position.x:.1f}, {reference_position.y:.1f}, {reference_position.z:.1f})")
        print(f"      (TIP: Select an actor from your target robot before running to ensure correct matching)")
    
    actors_by_link = find_robot_actors(robot_name, link_names, reference_position=reference_position)
    if not actors_by_link:
        print(f"[ERROR] No actors found matching: {robot_name}")
        print(f"        Link names searched: {link_names[:5]}...")
        print("        Make sure you've imported the USD file first!")
        if reference_position:
            print(f"        Reference position used: ({reference_position.x:.1f}, {reference_position.y:.1f}, {reference_position.z:.1f})")
            print("        TIP: If wrong robot was matched, select an actor from the correct robot and try again.")
        return False
    
    # Count total actors found
    total_actors = sum(len(actor_list) for actor_list in actors_by_link.values())
    
    if verbose:
        print(f"      Found {total_actors} actors for {len(actors_by_link)} links")
    
    # Check if materials are available
    hierarchy = hierarchy_data.get('hierarchy', {})
    has_materials = bool(hierarchy.get('materials'))
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
                link_pos = tf['position']
                link_quat = tf['quaternion']
                
                # Check for visual origin in hierarchy (mesh offset from link frame)
                visual_origin = get_visual_origin(hierarchy_data, link_name) if not skip_visual_origins else None
                
                if visual_origin:
                    # Apply visual origin transform to get final mesh position
                    final_pos, final_quat = apply_visual_origin(link_pos, link_quat, visual_origin)
                    visual_origins_applied += 1
                    origin_applied = True
                    if verbose:
                        vo_xyz = visual_origin.get('xyz', [0,0,0])
                        vo_rpy = visual_origin.get('rpy', [0,0,0])
                        print(f"        VO: xyz=[{vo_xyz[0]:.3f}, {vo_xyz[1]:.3f}, {vo_xyz[2]:.3f}] rpy=[{vo_rpy[0]:.2f}, {vo_rpy[1]:.2f}, {vo_rpy[2]:.2f}]")
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
                    print(f"      [MAT] {link_name}: rgba({color[0]:.2f}, {color[1]:.2f}, {color[2]:.2f}, {color[3] if len(color) > 3 else 1.0:.2f})")
    
    # Step 6: Create physics constraints
    constraints_created = 0
    if create_constraints:
        if verbose:
            print("\n[6/6] Creating physics constraints...")
        
        # Get joints from hierarchy
        joints_list = hierarchy.get('joints', [])
        
        if joints_list:
            # Use actor mesh bounds to compute accurate joint positions
            # This accounts for visual origins already baked into USD meshes
            if verbose:
                print("      Computing joint positions from actor mesh bounds...")
            
            joint_world_positions = compute_joint_world_positions_from_actors(
                joints_list, actors_by_link, verbose=verbose
            )
            
            for joint in joints_list:
                parent_link = joint.get('parent_link')
                child_link = joint.get('child_link')
                joint_name = joint.get('name', f"{parent_link}-{child_link}")
                
                # Find actors for parent and child
                parent_actors = actors_by_link.get(parent_link, [])
                child_actors = actors_by_link.get(child_link, [])
                
                if parent_actors and child_actors:
                    # IMPORTANT: Prefer visual actors over collision actors
                    parent_actor = get_visual_actor(parent_actors)
                    child_actor = get_visual_actor(child_actors)
                    
                    # Get precomputed world position for this joint
                    joint_world_pos = joint_world_positions.get(joint_name)
                    
                    # Create the constraint with correct world position
                    constraint = create_physics_constraint(
                        parent_actor, child_actor, joint,
                        joint_world_pos=joint_world_pos,
                        robot_name=robot_name,
                        verbose=verbose
                    )
                    if constraint:
                        constraints_created += 1
                else:
                    if verbose:
                        print(f"      [SKIP] {joint_name}: Missing actors (parent={parent_link}, child={child_link})")
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
            if filename.endswith('_hierarchy.json'):
                robot_name = filename.replace('_hierarchy.json', '')
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
            if filename.endswith('_hierarchy.json'):
                robot_name = filename.replace('_hierarchy.json', '')
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
    length = math.sqrt(sum(a*a for a in axis))
    if length > 0:
        axis = [a/length for a in axis]
    else:
        axis = [1, 0, 0]  # Default to X
    
    # Determine dominant axis
    abs_axis = [abs(a) for a in axis]
    max_idx = abs_axis.index(max(abs_axis))
    dominant = ['x', 'y', 'z'][max_idx]
    
    settings = {
        'x_motion': 'Locked',
        'y_motion': 'Locked',
        'z_motion': 'Locked',
        'swing1_motion': 'Locked',  # Y-axis rotation
        'swing2_motion': 'Locked',  # Z-axis rotation
        'twist_motion': 'Locked',   # X-axis rotation
        'dominant_axis': dominant
    }
    
    if joint_type == 'fixed':
        # All locked (default)
        pass
    elif joint_type == 'revolute':
        # Limited rotation around axis
        if dominant == 'x':
            settings['twist_motion'] = 'Limited'
        elif dominant == 'y':
            settings['swing1_motion'] = 'Limited'
        else:  # z
            settings['swing2_motion'] = 'Limited'
    elif joint_type == 'continuous':
        # Free rotation around axis
        if dominant == 'x':
            settings['twist_motion'] = 'Free'
        elif dominant == 'y':
            settings['swing1_motion'] = 'Free'
        else:  # z
            settings['swing2_motion'] = 'Free'
    elif joint_type == 'prismatic':
        # Limited linear motion along axis
        if dominant == 'x':
            settings['x_motion'] = 'Limited'
        elif dominant == 'y':
            settings['y_motion'] = 'Limited'
        else:  # z
            settings['z_motion'] = 'Limited'
    elif joint_type == 'floating':
        # All free
        settings['x_motion'] = 'Free'
        settings['y_motion'] = 'Free'
        settings['z_motion'] = 'Free'
        settings['swing1_motion'] = 'Free'
        settings['swing2_motion'] = 'Free'
        settings['twist_motion'] = 'Free'
    elif joint_type == 'planar':
        # XY linear free, Z locked, twist free
        settings['x_motion'] = 'Free'
        settings['y_motion'] = 'Free'
        settings['twist_motion'] = 'Free'
    
    return settings


def get_mesh_extension_axis(actor: 'unreal.Actor') -> List[float]:
    """
    Analyze an actor's mesh bounding box to determine the primary extension axis.
    
    The extension axis is the direction along which the mesh extends the most.
    For robot arm segments, this is typically along the length of the arm piece.
    
    Args:
        actor: The actor to analyze
        
    Returns:
        Normalized direction vector [x, y, z] of the primary extension axis
    """
    # Get the actor's bounding box
    origin, box_extent = actor.get_actor_bounds(only_colliding_components=False)
    
    # box_extent contains half-extents in each axis
    extent_x = box_extent.x
    extent_y = box_extent.y
    extent_z = box_extent.z
    
    # The longest axis is the extension direction
    max_extent = max(extent_x, extent_y, extent_z)
    
    if max_extent < 0.01:
        return [1, 0, 0]  # Default fallback
    
    # Determine which axis is longest
    if extent_x >= extent_y and extent_x >= extent_z:
        return [1, 0, 0]  # Extends in X
    elif extent_y >= extent_x and extent_y >= extent_z:
        return [0, 1, 0]  # Extends in Y
    else:
        return [0, 0, 1]  # Extends in Z


def compute_constraint_rotation_from_geometry(
    parent_actor: 'unreal.Actor',
    child_actor: 'unreal.Actor',
    joint_pos: 'unreal.Vector',
    urdf_axis: List[float] = None,
    verbose: bool = False
) -> 'unreal.Rotator':
    """
    Compute constraint rotation based on the EXPANSION DIRECTION from the joint.
    
    Strategy: The constraint axis follows the direction the child EXPANDS from
    the joint position. This is simply the vector: Joint → Child Center.
    
    This is the "first expansion" - how the part grows from its attachment point.
    
    Args:
        parent_actor: The parent link actor
        child_actor: The child link actor  
        joint_pos: The joint position in world space
        urdf_axis: URDF axis hint [x, y, z] - typically [0,0,1] for Z rotation
        verbose: Print debug info
        
    Returns:
        Rotator to orient the constraint correctly
    """
    # Get child mesh bounds
    child_bounds = get_actor_mesh_bounds(child_actor)
    
    if not child_bounds:
        if verbose:
            print(f"        [WARN] Bounds unavailable, using default Z rotation")
        return unreal.Rotator(-90.0, 0.0, 0.0)
    
    child_center = child_bounds['center']
    
    # ========== EXPANSION DIRECTION: Joint → Child Center ==========
    # This is the "first expansion" - how the part grows from the joint
    exp_dx = child_center.x - joint_pos.x
    exp_dy = child_center.y - joint_pos.y
    exp_dz = child_center.z - joint_pos.z
    
    abs_dx, abs_dy, abs_dz = abs(exp_dx), abs(exp_dy), abs(exp_dz)
    
    # Find which axis has the largest component - that's the expansion direction
    if abs_dx >= abs_dy and abs_dx >= abs_dz:
        expansion_axis = 0  # Expands along X
        expansion_label = 'X'
    elif abs_dy >= abs_dx and abs_dy >= abs_dz:
        expansion_axis = 1  # Expands along Y
        expansion_label = 'Y'
    else:
        expansion_axis = 2  # Expands along Z
        expansion_label = 'Z'
    
    if verbose:
        print(f"        ┌─── EXPANSION ANALYSIS ───")
        print(f"        │ JOINT POS: ({joint_pos.x:.1f}, {joint_pos.y:.1f}, {joint_pos.z:.1f})")
        print(f"        │ CHILD CENTER: ({child_center.x:.1f}, {child_center.y:.1f}, {child_center.z:.1f})")
        print(f"        │")
        print(f"        │ EXPANSION VECTOR: ({exp_dx:.1f}, {exp_dy:.1f}, {exp_dz:.1f})")
        print(f"        │ EXPANSION AXIS: {expansion_label} (direction part grows from joint)")
        print(f"        └───────────────────────────")
    
    # The constraint axis = the expansion axis
    rotation_axis = expansion_axis
    
    # Convert rotation axis to constraint rotator
    # Constraint's twist axis (X-axis of constraint) must align with rotation_axis
    if rotation_axis == 0:  # Expansion along X
        pitch, yaw, roll = 0.0, 180.0, 0.0
    elif rotation_axis == 1:  # Expansion along Y
        pitch, yaw, roll = 0.0, -90.0, 0.0
    else:  # rotation_axis == 2, Expansion along Z
        pitch, yaw, roll = 90.0, 0.0, 0.0
    
    if verbose:
        print(f"        Constraint rotation: (P:{pitch:.1f}, Y:{yaw:.1f}, R:{roll:.1f})")
    
    return unreal.Rotator(pitch, yaw, roll)


def create_physics_constraint(
    parent_actor: 'unreal.Actor',
    child_actor: 'unreal.Actor',
    joint_data: Dict,
    joint_world_pos: 'unreal.Vector' = None,
    robot_name: str = "",
    verbose: bool = True
) -> Optional['unreal.PhysicsConstraintActor']:
    """
    Create a UE5 Physics Constraint between two actors based on URDF joint data.
    
    Creates a PhysicsConstraintActor at the joint position and configures it
    to connect the parent and child actors.
    
    Args:
        parent_actor: Parent link actor (StaticMeshActor)
        child_actor: Child link actor (StaticMeshActor)
        joint_data: Joint info from hierarchy JSON
            - name: Joint name
            - type: revolute, prismatic, continuous, fixed, etc.
            - axis: [x, y, z]
            - limits: {lower, upper, effort, velocity} or None
            - origin: {xyz, rpy}
        joint_world_pos: Pre-computed world position for the constraint (optional)
                        If provided, overrides the fallback actor-location-based calculation
        verbose: Print progress
        
    Returns:
        Created PhysicsConstraintActor or None if failed
    """
    try:
        joint_name = joint_data.get('name', 'joint')
        joint_type = joint_data.get('type', 'fixed')
        axis = joint_data.get('axis', [1, 0, 0])
        limits = joint_data.get('limits')
        origin = joint_data.get('origin', {})
        
        # Get constraint motion settings from URDF joint type
        motion_settings = urdf_axis_to_ue5_constraint(axis, joint_type)
        
        # Determine constraint world position
        # If joint_world_pos is provided (pre-computed from hierarchy), use it
        # Otherwise fall back to actor-location-based calculation (less accurate for USD imports)
        if joint_world_pos is not None:
            # Use pre-computed world position from hierarchy transforms
            constraint_pos = joint_world_pos
            if verbose:
                print(f"        Parent: {parent_actor.get_actor_label()}")
                print(f"        Child:  {child_actor.get_actor_label()}")
                print(f"        Constraint at (computed): ({constraint_pos.x:.1f}, {constraint_pos.y:.1f}, {constraint_pos.z:.1f})")
        else:
            # Fallback: Calculate from actor locations (may be inaccurate for USD imports)
            parent_loc = parent_actor.get_actor_location()
            child_loc = child_actor.get_actor_location()
            origin_xyz = origin.get('xyz', [0, 0, 0])
            
            # Convert ROS position to UE5: X same, Y flips, Z same, scale m->cm
            joint_offset_ue5 = unreal.Vector(
                origin_xyz[0] * 100.0,     # X stays same
                -origin_xyz[1] * 100.0,    # Y flips (ROS Y-left to UE5 Y-right)
                origin_xyz[2] * 100.0      # Z stays same
            )
            
            # Joint position = parent location + joint offset
            constraint_pos = unreal.Vector(
                parent_loc.x + joint_offset_ue5.x,
                parent_loc.y + joint_offset_ue5.y,
                parent_loc.z + joint_offset_ue5.z
            )
            
            if verbose:
                print(f"        Parent: {parent_actor.get_actor_label()} at ({parent_loc.x:.1f}, {parent_loc.y:.1f}, {parent_loc.z:.1f})")
                print(f"        Child:  {child_actor.get_actor_label()} at ({child_loc.x:.1f}, {child_loc.y:.1f}, {child_loc.z:.1f})")
                print(f"        Constraint at (fallback): ({constraint_pos.x:.1f}, {constraint_pos.y:.1f}, {constraint_pos.z:.1f})")
        
        # Compute constraint rotation based on mesh geometry analysis
        # This analyzes the actual mesh bounding boxes to determine how parts extend
        # and orients the constraint's rotation axis perpendicular to the part's extension
        constraint_rotation = compute_constraint_rotation_from_geometry(
            parent_actor,
            child_actor,
            constraint_pos,
            urdf_axis=axis,
            verbose=verbose
        )
        
        if verbose:
            print(f"        Joint axis (URDF): {axis}")
            print(f"        Final constraint rotation: (P:{constraint_rotation.pitch:.1f}, Y:{constraint_rotation.yaw:.1f}, R:{constraint_rotation.roll:.1f})")
        
        # Create Physics Constraint Actor at joint position with correct rotation
        constraint_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.PhysicsConstraintActor,
            constraint_pos,
            constraint_rotation
        )
        
        if not constraint_actor:
            if verbose:
                print(f"      [FAIL] Could not spawn PhysicsConstraintActor for {joint_name}")
            return None
        
        # Name the actor with robot prefix
        if robot_name:
            constraint_actor.set_actor_label(f"{robot_name}_Constraint_{joint_name}")
        else:
            constraint_actor.set_actor_label(f"Constraint_{joint_name}")
        
        # Get the constraint component
        constraint_comp = constraint_actor.constraint_comp
        if not constraint_comp:
            # Fallback to getting by class
            constraint_comp = constraint_actor.get_component_by_class(unreal.PhysicsConstraintComponent)
        
        if not constraint_comp:
            if verbose:
                print(f"      [FAIL] No PhysicsConstraintComponent found for {joint_name}")
            unreal.EditorLevelLibrary.destroy_actor(constraint_actor)
            return None
        
        # CRITICAL: Connect the two physics bodies
        # Set constraint actors directly via editor properties
        # This is the primary method for connecting StaticMeshActors
        try:
            constraint_comp.set_editor_property('constraint_actor1', parent_actor)
            constraint_comp.set_editor_property('constraint_actor2', child_actor)
        except Exception as e:
            if verbose:
                print(f"        [WARN] Could not set constraint actors: {e}")
        
        # Disable collision between constrained bodies
        constraint_comp.set_disable_collision(True)
        
        # Configure linear motion based on joint type
        constraint_comp.set_linear_x_limit(
            getattr(unreal.LinearConstraintMotion, motion_settings['x_motion'].upper(), 
                    unreal.LinearConstraintMotion.LCM_LOCKED),
            0.0
        )
        constraint_comp.set_linear_y_limit(
            getattr(unreal.LinearConstraintMotion, motion_settings['y_motion'].upper(),
                    unreal.LinearConstraintMotion.LCM_LOCKED),
            0.0
        )
        constraint_comp.set_linear_z_limit(
            getattr(unreal.LinearConstraintMotion, motion_settings['z_motion'].upper(),
                    unreal.LinearConstraintMotion.LCM_LOCKED),
            0.0
        )
        
        # Set angular motion
        swing1_mode = getattr(unreal.AngularConstraintMotion, 
                              'ACM_' + motion_settings['swing1_motion'].upper(),
                              unreal.AngularConstraintMotion.ACM_LOCKED)
        swing2_mode = getattr(unreal.AngularConstraintMotion,
                              'ACM_' + motion_settings['swing2_motion'].upper(),
                              unreal.AngularConstraintMotion.ACM_LOCKED)
        twist_mode = getattr(unreal.AngularConstraintMotion,
                             'ACM_' + motion_settings['twist_motion'].upper(),
                             unreal.AngularConstraintMotion.ACM_LOCKED)
        
        constraint_comp.set_angular_swing1_limit(swing1_mode, 45.0)
        constraint_comp.set_angular_swing2_limit(swing2_mode, 45.0)
        constraint_comp.set_angular_twist_limit(twist_mode, 45.0)
        
        # Apply limits if present (convert radians to degrees)
        if limits and joint_type in ['revolute', 'prismatic']:
            lower = limits.get('lower', 0.0)
            upper = limits.get('upper', 0.0)
            
            if joint_type == 'revolute':
                # Angular limits in degrees
                lower_deg = math.degrees(lower)
                upper_deg = math.degrees(upper)
                limit_angle = max(abs(lower_deg), abs(upper_deg))
                
                if motion_settings['dominant_axis'] == 'x':
                    constraint_comp.set_angular_twist_limit(
                        unreal.AngularConstraintMotion.ACM_LIMITED, limit_angle)
                elif motion_settings['dominant_axis'] == 'y':
                    constraint_comp.set_angular_swing1_limit(
                        unreal.AngularConstraintMotion.ACM_LIMITED, limit_angle)
                else:
                    constraint_comp.set_angular_swing2_limit(
                        unreal.AngularConstraintMotion.ACM_LIMITED, limit_angle)
            else:
                # Linear limits in cm (convert from meters)
                lower_cm = lower * 100.0
                upper_cm = upper * 100.0
                limit_dist = max(abs(lower_cm), abs(upper_cm))
                
                if motion_settings['dominant_axis'] == 'x':
                    constraint_comp.set_linear_x_limit(
                        unreal.LinearConstraintMotion.LCM_LIMITED, limit_dist)
                elif motion_settings['dominant_axis'] == 'y':
                    constraint_comp.set_linear_y_limit(
                        unreal.LinearConstraintMotion.LCM_LIMITED, limit_dist)
                else:
                    constraint_comp.set_linear_z_limit(
                        unreal.LinearConstraintMotion.LCM_LIMITED, limit_dist)
        
        # =====================================================================
        # MOTOR/DRIVE CONFIGURATION (Required for ROC control)
        # =====================================================================
        # Configure the constraint's drive so ROC can control it via targets
        # NEW: Pass dynamics (damping/friction) from URDF if available
        dynamics = joint_data.get('dynamics', None)
        configure_constraint_drive(
            constraint_comp,
            joint_type=joint_type,
            axis=motion_settings['dominant_axis'],
            limits=limits,
            dynamics=dynamics,
            verbose=verbose
        )
        
        if verbose:
            print(f"      [CONSTRAINT] {joint_name}: {joint_type} on {motion_settings['dominant_axis']}-axis")
        
        return constraint_actor
        
    except Exception as e:
        if verbose:
            print(f"      [ERROR] Failed to create constraint: {e}")
        return None


def create_robot_constraints(
    robot_name_or_path: str,
    actors_by_link: Dict[str, List['unreal.Actor']] = None,
    verbose: bool = True
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
    
    robot_name = hierarchy_data.get('robot_name', 'robot')
    hierarchy = hierarchy_data.get('hierarchy', {})
    joints_list = hierarchy.get('joints', [])
    
    if not joints_list:
        print(f"[WARNING] No joints found in hierarchy. Is this version 2.2+?")
        print(f"          Re-convert the URDF to generate joints data.")
        return 0
    
    if verbose:
        print(f"\n[INFO] Robot: {robot_name}")
        print(f"       Joints: {len(joints_list)}")
    
    # Find actors if not provided
    if actors_by_link is None:
        link_names = list(hierarchy.get('nodes', {}).keys())
        actors_by_link = find_robot_actors(robot_name, link_names)
    
    if not actors_by_link:
        print(f"[ERROR] No actors found for robot: {robot_name}")
        return 0
    
    # Create constraints
    constraints_created = 0
    if verbose:
        print(f"\n[INFO] Creating physics constraints...")
    
    for joint in joints_list:
        parent_link = joint.get('parent_link')
        child_link = joint.get('child_link')
        joint_type = joint.get('type', 'fixed')
        
        # Skip if we can't find both actors
        parent_actors = actors_by_link.get(parent_link, [])
        child_actors = actors_by_link.get(child_link, [])
        
        if not parent_actors or not child_actors:
            if verbose:
                print(f"      [SKIP] {joint.get('name')}: Missing actors (parent={len(parent_actors)}, child={len(child_actors)})")
            continue
        
        # Use first actor of each (usually there's only one per link for visual)
        parent_actor = parent_actors[0]
        child_actor = child_actors[0]
        
        # Create constraint
        constraint = create_physics_constraint(parent_actor, child_actor, joint, robot_name=robot_name, verbose=verbose)
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
    verbose: bool = True
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
        'success': False,
        'actors_positioned': 0,
        'colors_applied': 0,
        'constraints_created': 0,
        'robot_name': ''
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
    
    robot_name = hierarchy_data.get('robot_name', 'robot')
    result['robot_name'] = robot_name
    hierarchy = hierarchy_data.get('hierarchy', {})
    
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
            location = unreal.Vector(tf['position'][0], tf['position'][1], tf['position'][2])
            rotation = quaternion_to_rotator(tf['quaternion'])
            
            for actor in actor_list:
                actor.set_actor_location(location, False, False)
                actor.set_actor_rotation(rotation, False)
                positioned += 1
            
            if verbose:
                print(f"      [POS] {link_name} ({len(actor_list)} actors)")
    
    result['actors_positioned'] = positioned
    
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
                    print(f"      [COL] {link_name}: RGBA({color[0]:.2f}, {color[1]:.2f}, {color[2]:.2f}, {color[3] if len(color) > 3 else 1.0:.2f})")
            else:
                if verbose:
                    print(f"      [---] {link_name}: No color defined")
        
        result['colors_applied'] = colors_applied
    else:
        print("\n[4/4] Skipping colors (disabled)")
    
    # Step 4.5: Enable physics simulation on all link actors
    # This is required for ROC to control the robot
    print("\n[4.5/5] Enabling physics on robot parts...")
    
    hierarchy = hierarchy_data.get('hierarchy', {})
    # Base link can be under 'base_link' or as first item in 'root_nodes'
    base_link_name = hierarchy.get('base_link', None)
    if not base_link_name:
        root_nodes = hierarchy.get('root_nodes', [])
        if root_nodes:
            base_link_name = root_nodes[0]
    
    links_data = hierarchy.get('links', {})
    # Also check 'nodes' for backwards compatibility
    if not links_data:
        links_data = hierarchy.get('nodes', {})
    
    physics_enabled = 0
    
    for link_name, actor_list in actors_by_link.items():
        # Get mass from hierarchy if available
        link_info = links_data.get(link_name, {})
        link_properties = link_info.get('properties', {})
        mass = link_properties.get('mass', DEFAULT_LINK_MASS)
        
        # Check if this is the base link (should be stationary)
        is_base = (link_name == base_link_name)
        
        for actor in actor_list:
            setup_physics_body(actor, mass_kg=mass, is_base_link=is_base, verbose=verbose)
            physics_enabled += 1
    
    result['physics_enabled'] = physics_enabled
    if verbose:
        print(f"      [PHYSICS] Enabled on {physics_enabled} actors (base: {base_link_name})")
    
    # Step 5: Create physics constraints
    if apply_constraints:
        print("\n[5/5] Creating physics constraints...")
        
        joints_list = hierarchy.get('joints', [])
        constraint_map = {}  # Maps joint_name -> constraint_actor for ROC export
        
        if joints_list:
            constraints = 0
            for joint in joints_list:
                parent_link = joint.get('parent_link')
                child_link = joint.get('child_link')
                joint_name = joint.get('name', f'joint_{constraints}')
                
                parent_actors = actors_by_link.get(parent_link, [])
                child_actors = actors_by_link.get(child_link, [])
                
                if parent_actors and child_actors:
                    constraint = create_physics_constraint(
                        parent_actors[0], 
                        child_actors[0], 
                        joint,
                        robot_name=robot_name,
                        verbose=verbose
                    )
                    if constraint:
                        constraints += 1
                        # Store the constraint actor label (name) for ROC export
                        constraint_map[joint_name] = constraint.get_actor_label()
                elif verbose:
                    print(f"      [SKIP] {joint.get('name')}: Missing actors")
            
            result['constraints_created'] = constraints
            
            # Export robot specs for ROC
            if constraints > 0:
                export_robot_specs_for_roc(
                    robot_name=robot_name,
                    hierarchy_data=hierarchy_data,
                    constraint_map=constraint_map,
                    actors_by_link=actors_by_link,
                    verbose=verbose
                )
                
                # Export robot config for DIMC
                export_robot_config_for_dimc(
                    robot_name=robot_name,
                    hierarchy_data=hierarchy_data,
                    actors_by_link=actors_by_link,
                    root_actor=None,  # Will be auto-detected from base_link
                    verbose=verbose
                )
        else:
            print("      [WARN] No joints data found (need hierarchy v2.2+)")
    else:
        print("\n[5/5] Skipping constraints (disabled)")
    
    # Summary
    result['success'] = positioned > 0
    
    print("")
    print("╔════════════════════════════════════════════════════════════╗")
    print(f"║  PYCO COMPLETE: {robot_name}")
    print("╠════════════════════════════════════════════════════════════╣")
    print(f"║  Parts Positioned:    {result['actors_positioned']:4d}")
    print(f"║  Colors Applied:      {result['colors_applied']:4d}")
    print(f"║  Physics Enabled:     {result.get('physics_enabled', 0):4d}")
    print(f"║  Constraints Created: {result['constraints_created']:4d}")
    print("╚════════════════════════════════════════════════════════════╝")
    
    return result


# Convenience alias
pyco = PYCO  # lowercase version for easier typing


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
print("  list_robots()                    - List available robot hierarchy files")
print("  reset_robot('robot_name')        - Reset robot parts to origin")
print("")
print("Workflow:")
print("  1. Import USD file into UE5")
print("  2. assemble_robot('ur20')           # Position all parts correctly")
print("  3. create_robot_constraints('ur20') # Add physics joints")
print("")

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
    
    robot_name = hierarchy_data.get('robot_name', 'robot')
    hierarchy = hierarchy_data.get('hierarchy', {})
    
    # Generate unique robot ID if not provided
    if not robot_id:
        import time
        robot_id = f"{robot_name}_{int(time.time()) % 10000:04d}"
    
    # Extract joint information
    joints_list = hierarchy.get('joints', [])
    roc_joints = []
    
    for joint in joints_list:
        joint_type = joint.get('type', 'fixed')
        
        # Skip fixed joints (not controllable)
        if joint_type == 'fixed':
            continue
        
        # Get joint limits
        limits = joint.get('limits', {})
        lower = limits.get('lower', -3.14159)  # Default to ±π
        upper = limits.get('upper', 3.14159)
        velocity_limit = limits.get('velocity', 1.0)
        effort_limit = limits.get('effort', 100.0)
        
        roc_joint = {
            "name": joint.get('name', ''),
            "type": joint_type,
            "limits": [lower, upper],
            "velocity_limit": velocity_limit,
            "effort_limit": effort_limit,
            "parent_link": joint.get('parent_link', ''),
            "child_link": joint.get('child_link', ''),
            "axis": joint.get('axis', [0, 0, 1])
        }
        roc_joints.append(roc_joint)
    
    # Detect capabilities
    dof = len(roc_joints)
    has_gripper = any('gripper' in j['name'].lower() or 'finger' in j['name'].lower() for j in roc_joints)
    has_mobile_base = any('wheel' in j['name'].lower() or 'caster' in j['name'].lower() for j in roc_joints)
    is_articulated_arm = dof >= 4 and not has_mobile_base
    
    # Check for submechanism data (v3.0+)
    submech = hierarchy_data.get('submechanisms', {})
    robot_type = submech.get('robot_type', 'unknown')
    if robot_type == 'unknown':
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
            "dof": dof
        },
        "content_path": f"/Game/Robots/{robot_name}",
        "hierarchy_path": hierarchy_path,
        "ready_for_control": True,
        "version": hierarchy_data.get('version', '2.0')
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
        robot_name = specs['robot_name']
        output_dir = tempfile.gettempdir()
        output_path = os.path.join(output_dir, f"{robot_name}_roc_specs.json")
    
    # Save to file
    try:
        with open(output_path, 'w') as f:
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
            from rclpy.node import Node
            import rclpy
            from std_msgs.msg import String
            
            if not rclpy.ok():
                rclpy.init()
            
            # Create temporary node for publishing
            node = Node('fti_roc_bridge')
            publisher = node.create_publisher(String, '/fti/robot_specs', 10)
            
            # Publish specs
            msg = String()
            msg.data = json.dumps(generate_roc_specs(robot_name_or_path))
            publisher.publish(msg)
            
            print("[ROC] Published robot specs to /fti/robot_specs topic")
            
            # Cleanup
            node.destroy_node()
        except ImportError:
            print("[ROC] ROS2 not available for publishing - specs saved to file only")
        except Exception as e:
            print(f"[ROC] Error publishing specs: {e}")
    
    print(f"\n[ROC] Robot prepared for ROC integration")
    print(f"[ROC] Specs file: {specs_path}")
    return True

