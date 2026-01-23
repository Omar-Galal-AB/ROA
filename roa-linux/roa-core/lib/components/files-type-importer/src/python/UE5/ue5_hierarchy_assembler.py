"""
UE5 Hierarchy Assembler - Automatic robot hierarchy reconstruction for UE5

This module provides tools for:
1. Detecting ROA-generated USD files after Interchange import
2. Parsing the customData metadata from USD files
3. Reconstructing the robot hierarchy in UE5 scene
4. Running automatically via PostImport hook or manually

v3.0 Features:
- Submechanism detection and grouping (6-dof-arm, parallel-mechanism, etc.)
- Enhanced joint data with full UE5 constraint parameters
- IK configuration per submechanism

The Problem:
    UE5's Interchange system flattens USD hierarchies during import.
    This means robot parts end up as separate actors without parent-child relationships.

The Solution:
    1. URDF converter embeds hierarchy metadata in USD customData
    2. After import, this module reads the metadata
    3. Recreates the hierarchy by re-parenting actors
    4. Applies the correct joint transforms
    5. NEW v3.0: Configures physics constraints with drive parameters

Gap Fixes Implemented:
- Gap 8.1: Works with any Interchange pipeline (auto-detects ROA files)
- Gap 8.2: Can be triggered automatically via PostImport hook
- Gap 8.3: v3.0 submechanism and enhanced joint support

Usage in UE5 Python:
    import ue5_hierarchy_assembler as roa

    # Option 1: Assemble from imported USD
    roa.assemble_from_usd_path("D:/ROA/Outputs/ur3_robot_assembled.usd")

    # Option 2: Assemble from asset path
    roa.assemble_from_asset("/Game/Robots/ur3_robot")

    # Option 3: Find and assemble all ROA robots in level
    roa.assemble_all_in_level()

    # NEW v3.0: Get submechanism info
    info = roa.get_robot_info_from_json("/path/to/hierarchy.json")
    print(info.submechanisms)  # List of kinematic groups
    print(info.robot_type)     # '6-dof-arm', 'parallel-mechanism', etc.

Integration with UE5 (for plugin developers):
    # In PostImportAsset callback
    if is_roa_generated_usd(asset_path):
        assemble_hierarchy(asset_path)
"""

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Try to import Unreal modules (only available in UE5)
try:
    import unreal

    HAS_UNREAL = True
except ImportError:
    HAS_UNREAL = False
    print("WARNING: Unreal module not available. Running in standalone mode.")


# =============================================================================
# v3.0 DATACLASSES - Submechanisms, Enhanced Joints, IK Config
# =============================================================================


@dataclass
class SubmechanismInfo:
    """Information about a kinematic submechanism (v3.0)."""

    name: str
    robot_type: str = "unknown"  # '6-dof-arm', 'parallel-mechanism', 'scara', etc.
    joints: List[str] = field(default_factory=list)
    links: List[str] = field(default_factory=list)
    root_link: str = ""
    tip_link: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubmechanismInfo":
        """Create from hierarchy JSON submechanism entry."""
        return cls(
            name=data.get("name", "unknown"),
            robot_type=data.get("robot_type", data.get("type", "unknown")),
            joints=data.get("joints", []),
            links=data.get("links", []),
            root_link=data.get("root_link", ""),
            tip_link=data.get("tip_link", ""),
        )


@dataclass
class EnhancedJointInfo:
    """Enhanced joint data with UE5 constraint parameters (v3.0)."""

    name: str
    joint_type: str  # 'revolute', 'prismatic', 'continuous', 'fixed'
    parent_link: str
    child_link: str
    axis: List[float] = field(default_factory=lambda: [0, 0, 1])

    # UE5 constraint parameters
    constraint_type: str = "Hinge"  # 'Hinge', 'Prismatic', 'Ball', 'Fixed'
    motion_type: str = "Angular"  # 'Angular', 'Linear'

    # Limits
    angular_limits: Dict[str, float] = field(default_factory=dict)  # lower, upper (deg)
    linear_limits: Dict[str, float] = field(default_factory=dict)  # min, max (cm)

    # Drive/Motor settings
    drive_enabled: bool = False
    stiffness: float = 0.0
    damping: float = 10.0
    max_force: float = 100.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EnhancedJointInfo":
        """Create from hierarchy JSON enhanced_joints entry."""
        ue5_params = data.get("ue5_constraint", {})
        drive = ue5_params.get("drive", {})

        return cls(
            name=data.get("name", ""),
            joint_type=data.get("type", "fixed"),
            parent_link=data.get("parent_link", ""),
            child_link=data.get("child_link", ""),
            axis=data.get("axis", [0, 0, 1]),
            constraint_type=ue5_params.get("type", "Fixed"),
            motion_type=ue5_params.get("motion_type", "Angular"),
            angular_limits=ue5_params.get("angular_limits", {}),
            linear_limits=ue5_params.get("linear_limits", {}),
            drive_enabled=drive.get("enabled", False),
            stiffness=drive.get("stiffness", 0.0),
            damping=drive.get("damping", 10.0),
            max_force=drive.get("max_force", 100.0),
        )


@dataclass
class IKConfigInfo:
    """IK solver configuration for a submechanism (v3.0)."""

    submechanism_name: str
    solver_type: str = "local"  # 'moveit', 'local', 'none'
    available: bool = False
    config: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "IKConfigInfo":
        """Create from hierarchy JSON ik_config entry."""
        return cls(
            submechanism_name=name,
            solver_type=data.get("solver", "none"),
            available=data.get("available", False),
            config=data.get("config", {}),
        )


@dataclass
class RobotInfoV3:
    """Complete robot information including v3.0 features."""

    robot_name: str
    version: str = "2.0"  # Will be "3.0" for new format
    root_link: str = ""
    link_count: int = 0
    joint_count: int = 0

    # v3.0 features
    robot_type: str = "unknown"
    submechanisms: List[SubmechanismInfo] = field(default_factory=list)
    enhanced_joints: List[EnhancedJointInfo] = field(default_factory=list)
    ik_configs: Dict[str, IKConfigInfo] = field(default_factory=dict)

    @property
    def has_v3_features(self) -> bool:
        """Check if this robot has v3.0 enhanced data."""
        return (
            self.version.startswith("3") or bool(self.submechanisms) or bool(self.enhanced_joints)
        )

    @property
    def ik_available(self) -> bool:
        """Check if IK is available for any submechanism."""
        return any(ik.available for ik in self.ik_configs.values())


def get_robot_info_from_json(json_path: str) -> Optional[RobotInfoV3]:
    """
    Load complete robot info from hierarchy JSON file (v2.0 or v3.0).

    Args:
        json_path: Path to the hierarchy JSON file

    Returns:
        RobotInfoV3 with all available data, or None if failed
    """
    try:
        with open(json_path, "r") as f:
            data = json.load(f)

        return parse_robot_info(data)
    except Exception as e:
        print(f"ERROR: Failed to load robot info from {json_path}: {e}")
        return None


def parse_robot_info(data: Dict[str, Any]) -> RobotInfoV3:
    """
    Parse robot info from hierarchy data dict.

    Handles both v2.0 and v3.0 hierarchy formats.

    Args:
        data: Hierarchy data dictionary

    Returns:
        RobotInfoV3 with all available data
    """
    version = data.get("version", "2.0")
    hierarchy = data.get("hierarchy", {})

    # Basic info
    info = RobotInfoV3(
        robot_name=data.get("robot_name", "unknown"),
        version=version,
        root_link=data.get("root_link", hierarchy.get("root_link", "base_link")),
        link_count=data.get(
            "link_count",
            len([n for n, d in hierarchy.get("nodes", {}).items() if d.get("type") == "link"]),
        ),
        joint_count=data.get("joint_count", len(hierarchy.get("joints", []))),
    )

    # v3.0: Parse submechanisms
    submech_data = data.get("submechanisms", {})
    if isinstance(submech_data, dict):
        info.robot_type = submech_data.get("robot_type", "unknown")
        for group in submech_data.get("groups", []):
            info.submechanisms.append(SubmechanismInfo.from_dict(group))
    elif isinstance(submech_data, list):
        for sm in submech_data:
            info.submechanisms.append(SubmechanismInfo.from_dict(sm))

    # v3.0: Parse enhanced joints
    enhanced_joints = data.get("enhanced_joints", [])
    for ej in enhanced_joints:
        info.enhanced_joints.append(EnhancedJointInfo.from_dict(ej))

    # v3.0: Parse IK configs
    ik_config_data = data.get("ik_config", {})
    for name, cfg in ik_config_data.items():
        info.ik_configs[name] = IKConfigInfo.from_dict(name, cfg)

    return info


# =============================================================================
# LEGACY DATACLASSES (v2.0 compatibility)
# =============================================================================


@dataclass
class LinkTransform:
    """Transform for a robot link."""

    translation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_rpy: Tuple[float, float, float] = (
        0.0,
        0.0,
        0.0,
    )  # Roll, Pitch, Yaw in radians

    def to_unreal_transform(self) -> "unreal.Transform":
        """Convert to Unreal Transform."""
        if not HAS_UNREAL:
            raise RuntimeError("Unreal module not available")

        # Convert translation (URDF uses meters, UE5 uses centimeters)
        location = unreal.Vector(
            self.translation[0] * 100.0,  # X
            self.translation[1] * 100.0,  # Y
            self.translation[2] * 100.0,  # Z
        )

        # Convert RPY to Unreal Rotator (degrees)
        roll_deg = math.degrees(self.rotation_rpy[0])
        pitch_deg = math.degrees(self.rotation_rpy[1])
        yaw_deg = math.degrees(self.rotation_rpy[2])

        rotation = unreal.Rotator(pitch_deg, yaw_deg, roll_deg)

        return unreal.Transform(location, rotation, unreal.Vector(1, 1, 1))


@dataclass
class LinkInfo:
    """Information about a robot link."""

    name: str
    parent_link: Optional[str] = None
    parent_joint: Optional[str] = None
    transform: LinkTransform = field(default_factory=LinkTransform)
    children: List[str] = field(default_factory=list)


@dataclass
class RobotHierarchy:
    """Complete robot hierarchy parsed from metadata."""

    robot_name: str
    root_link: str
    links: Dict[str, LinkInfo] = field(default_factory=dict)
    link_count: int = 0
    joint_count: int = 0

    @classmethod
    def from_metadata(cls, metadata: Dict[str, Any]) -> "RobotHierarchy":
        """
        Create RobotHierarchy from USD customData metadata.

        Args:
            metadata: Dictionary from USD customData

        Returns:
            Parsed RobotHierarchy
        """
        robot_name = metadata.get("robot_name", "unknown")
        root_link = metadata.get("root_link", "base_link")
        link_count = metadata.get("link_count", 0)
        joint_count = metadata.get("joint_count", 0)

        # Parse hierarchy string
        hierarchy_str = metadata.get("hierarchy", "")
        links = cls._parse_hierarchy_string(hierarchy_str)

        return cls(
            robot_name=robot_name,
            root_link=root_link,
            links=links,
            link_count=link_count,
            joint_count=joint_count,
        )

    @staticmethod
    def _parse_hierarchy_string(hierarchy_str: str) -> Dict[str, LinkInfo]:
        """
        Parse the hierarchy string from metadata.

        Format: "parent_link>joint_name>child_link(xyz,rpy);..."
        """
        links = {}

        if not hierarchy_str:
            return links

        for entry in hierarchy_str.split(";"):
            entry = entry.strip()
            if not entry:
                continue

            try:
                # Parse format: parent>joint>child(x,y,z,r,p,y)
                match = re.match(
                    r"(.+?)>(.+?)>(.+?)\(([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+)\)",
                    entry,
                )

                if match:
                    parent_link = match.group(1)
                    joint_name = match.group(2)
                    child_link = match.group(3)
                    x, y, z = (
                        float(match.group(4)),
                        float(match.group(5)),
                        float(match.group(6)),
                    )
                    r, p, yaw = (
                        float(match.group(7)),
                        float(match.group(8)),
                        float(match.group(9)),
                    )

                    # Create link info
                    link_info = LinkInfo(
                        name=child_link,
                        parent_link=parent_link,
                        parent_joint=joint_name,
                        transform=LinkTransform(translation=(x, y, z), rotation_rpy=(r, p, yaw)),
                    )

                    links[child_link] = link_info

                    # Track children
                    if parent_link not in links:
                        links[parent_link] = LinkInfo(name=parent_link)
                    links[parent_link].children.append(child_link)

            except Exception as e:
                print(f"Error parsing hierarchy entry '{entry}': {e}")

        return links

    def get_assembly_order(self) -> List[str]:
        """
        Get links in assembly order (parent before children).

        Returns:
            List of link names in assembly order
        """
        order = []
        visited = set()

        def visit(link_name: str):
            if link_name in visited:
                return
            visited.add(link_name)
            order.append(link_name)

            if link_name in self.links:
                for child in self.links[link_name].children:
                    visit(child)

        visit(self.root_link)
        return order


def read_usd_metadata(usd_path: str) -> Optional[Dict[str, Any]]:
    """
    Read customData metadata from a USD file.

    Args:
        usd_path: Path to USD file

    Returns:
        Metadata dictionary or None if not an ROA file
    """
    try:
        from pxr import Usd

        stage = Usd.Stage.Open(usd_path)
        if not stage:
            print(f"Could not open USD stage: {usd_path}")
            return None

        # Get root prim
        root_prim = stage.GetDefaultPrim()
        if not root_prim:
            # Try to find root prim by name
            for prim in stage.Traverse():
                if prim.GetParent().IsPseudoRoot():
                    root_prim = prim
                    break

        if not root_prim:
            print("No root prim found")
            return None

        # Check for ROA metadata
        custom_data = root_prim.GetCustomData()

        if not custom_data:
            return None

        if custom_data.get("export_source") != "ROA-FTI":
            return None

        return dict(custom_data)

    except ImportError:
        print("OpenUSD (pxr) not available. Cannot read USD metadata.")
        return None
    except Exception as e:
        print(f"Error reading USD metadata: {e}")
        return None


def is_roa_generated_usd(usd_path: str) -> bool:
    """
    Check if a USD file was generated by ROA.

    Args:
        usd_path: Path to USD file

    Returns:
        True if ROA-generated
    """
    metadata = read_usd_metadata(usd_path)
    return metadata is not None and metadata.get("export_source") == "ROA-FTI"


def find_actor_by_name(actor_name: str, world=None) -> Optional["unreal.Actor"]:
    """
    Find an actor in the current level by name.

    Args:
        actor_name: Name of the actor to find
        world: Optional world context (uses current if None)

    Returns:
        Actor if found, None otherwise
    """
    if not HAS_UNREAL:
        raise RuntimeError("Unreal module not available")

    if world is None:
        world = unreal.EditorLevelLibrary.get_editor_world()

    all_actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)

    for actor in all_actors:
        if actor.get_actor_label() == actor_name or actor.get_name() == actor_name:
            return actor

    return None


def find_all_roa_actors() -> List["unreal.Actor"]:
    """
    Find all actors in the current level that came from ROA imports.

    Returns:
        List of ROA-related actors
    """
    if not HAS_UNREAL:
        raise RuntimeError("Unreal module not available")

    world = unreal.EditorLevelLibrary.get_editor_world()
    all_actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)

    roa_actors = []

    for actor in all_actors:
        # Check if actor has ROA tag
        if actor.actor_has_tag("ROA_Import"):
            roa_actors.append(actor)
            continue

        # Check if actor name suggests ROA origin
        name = actor.get_actor_label()
        if any(
            pattern in name.lower()
            for pattern in ["_link", "_joint", "robot", "ur3", "ur5", "ur10"]
        ):
            roa_actors.append(actor)

    return roa_actors


def assemble_hierarchy(hierarchy: RobotHierarchy, name_prefix: str = "") -> bool:
    """
    Assemble robot hierarchy in UE5 by re-parenting actors.

    Args:
        hierarchy: Parsed robot hierarchy
        name_prefix: Optional prefix for actor names

    Returns:
        True if successful
    """
    if not HAS_UNREAL:
        raise RuntimeError("Unreal module not available")

    print(f"Assembling robot hierarchy: {hierarchy.robot_name}")
    print(f"  Root link: {hierarchy.root_link}")
    print(f"  Links: {hierarchy.link_count}, Joints: {hierarchy.joint_count}")

    # Get assembly order
    assembly_order = hierarchy.get_assembly_order()
    print(f"  Assembly order: {assembly_order}")

    # Find actors for each link
    actor_map: Dict[str, unreal.Actor] = {}

    for link_name in assembly_order:
        # Try different name patterns
        patterns = [
            f"{name_prefix}{link_name}",
            link_name,
            link_name.replace("_", ""),
            f"{hierarchy.robot_name}_{link_name}",
        ]

        actor = None
        for pattern in patterns:
            actor = find_actor_by_name(pattern)
            if actor:
                break

        if actor:
            actor_map[link_name] = actor
            print(f"  Found actor for {link_name}: {actor.get_name()}")
        else:
            print(f"  WARNING: Could not find actor for link: {link_name}")

    # Assemble hierarchy
    with unreal.ScopedEditorTransaction("ROA Hierarchy Assembly"):
        for link_name in assembly_order:
            if link_name == hierarchy.root_link:
                continue  # Root has no parent

            if link_name not in hierarchy.links:
                continue

            link_info = hierarchy.links[link_name]

            if link_info.parent_link and link_info.parent_link in actor_map:
                child_actor = actor_map.get(link_name)
                parent_actor = actor_map.get(link_info.parent_link)

                if child_actor and parent_actor:
                    # Set parent
                    child_actor.attach_to_actor(
                        parent_actor,
                        "",
                        unreal.AttachmentRule.KEEP_RELATIVE,
                        unreal.AttachmentRule.KEEP_RELATIVE,
                        unreal.AttachmentRule.KEEP_WORLD,
                        False,
                    )

                    # Apply transform
                    transform = link_info.transform.to_unreal_transform()
                    child_actor.set_actor_relative_transform(transform)

                    # Tag as ROA-assembled
                    child_actor.tags.append("ROA_Assembled")

                    print(f"  Attached {link_name} to {link_info.parent_link}")

    print(f"Hierarchy assembly complete for {hierarchy.robot_name}")
    return True


def assemble_from_usd_path(usd_path: str, name_prefix: str = "") -> bool:
    """
    Assemble robot hierarchy from USD file metadata.

    Args:
        usd_path: Path to USD file with ROA metadata
        name_prefix: Optional prefix for actor names

    Returns:
        True if successful
    """
    print(f"Reading metadata from: {usd_path}")

    metadata = read_usd_metadata(usd_path)

    if not metadata:
        print(f"ERROR: Could not read ROA metadata from {usd_path}")
        return False

    hierarchy = RobotHierarchy.from_metadata(metadata)
    return assemble_hierarchy(hierarchy, name_prefix)


def assemble_from_metadata_string(metadata_json: str, name_prefix: str = "") -> bool:
    """
    Assemble from JSON metadata string.

    Useful when metadata is passed as argument.

    Args:
        metadata_json: JSON string with metadata
        name_prefix: Optional prefix for actor names

    Returns:
        True if successful
    """
    try:
        metadata = json.loads(metadata_json)
        hierarchy = RobotHierarchy.from_metadata(metadata)
        return assemble_hierarchy(hierarchy, name_prefix)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON metadata: {e}")
        return False


def create_postimport_script(output_path: str = None) -> str:
    """
    Generate a UE5 Python script for PostImport hook.

    This script can be set up in UE5 to run automatically after USD import.

    Args:
        output_path: Where to save the script (optional)

    Returns:
        Generated script content
    """
    script = '''"""
ROA PostImport Hook for UE5
Automatically assembles robot hierarchies after USD import.

Setup:
1. Copy this script to your project's Python folder
2. In Project Settings > Interchange, add this as a PostImport script
   OR call from your custom import workflow
"""

import unreal
import ue5_hierarchy_assembler as roa

# Get the imported asset path from the import context
# This is passed by Interchange

def on_post_import(imported_assets):
    """Called after Interchange import completes."""
    for asset_path in imported_assets:
        # Check if this is an ROA-generated USD
        source_file = get_source_file_for_asset(asset_path)
        
        if source_file and roa.is_roa_generated_usd(source_file):
            print(f"ROA: Detected ROA-generated USD import: {source_file}")
            
            # Get the imported actor name (usually matches the USD default prim)
            actor_prefix = get_actor_prefix_from_asset(asset_path)
            
            # Assemble the hierarchy
            success = roa.assemble_from_usd_path(source_file, actor_prefix)
            
            if success:
                unreal.log("ROA: Hierarchy assembled successfully")
            else:
                unreal.log_warning("ROA: Hierarchy assembly had issues")


def get_source_file_for_asset(asset_path):
    """Get the source file path for an imported asset."""
    asset_import_data = unreal.AssetImportDataFunctionsLibrary.get_asset_import_data(asset_path)
    if asset_import_data:
        return asset_import_data.get_first_filename()
    return None


def get_actor_prefix_from_asset(asset_path):
    """Get the actor name prefix from asset path."""
    # Extract name from path like /Game/Robots/ur3_robot
    name = asset_path.split('/')[-1]
    return name + "_"

'''

    if output_path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w") as f:
            f.write(script)
        print(f"Generated PostImport script: {output_path}")

    return script


# Standalone testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python ue5_hierarchy_assembler.py <usd_file>")
        print()
        print("This script reads ROA metadata from a USD file and shows")
        print("the hierarchy that would be assembled in UE5.")
        sys.exit(1)

    usd_path = sys.argv[1]

    print(f"Reading USD metadata from: {usd_path}")
    print("-" * 60)

    metadata = read_usd_metadata(usd_path)

    if not metadata:
        print("ERROR: Could not read ROA metadata")
        print("This may not be an ROA-generated USD file.")
        sys.exit(1)

    print("Metadata found:")
    for key, value in metadata.items():
        if key == "hierarchy":
            print(f"  {key}: <{len(value)} chars>")
        else:
            print(f"  {key}: {value}")

    print()
    print("Parsed hierarchy:")
    print("-" * 60)

    hierarchy = RobotHierarchy.from_metadata(metadata)

    print(f"Robot: {hierarchy.robot_name}")
    print(f"Root: {hierarchy.root_link}")
    print(f"Links: {hierarchy.link_count}")
    print(f"Joints: {hierarchy.joint_count}")
    print()
    print("Assembly order:")

    for i, link_name in enumerate(hierarchy.get_assembly_order()):
        link_info = hierarchy.links.get(link_name)
        if link_info and link_info.parent_link:
            print(f"  {i+1}. {link_name} (parent: {link_info.parent_link})")
        else:
            print(f"  {i+1}. {link_name} (root)")

    print()
    print("To assemble in UE5, import the USD file then run:")
    print(f"  import ue5_hierarchy_assembler as roa")
    print(f'  roa.assemble_from_usd_path(r"{usd_path}")')
