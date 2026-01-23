"""
SMURF Schema Support Module

Implements SMURF (Supplementary Material for URDF Robots) schema support.
SMURF extends URDF with additional metadata stored in YAML/JSON files:
- Submechanisms (kinematic groups)
- Loop constraints (closed kinematic chains)
- Sensors and actuators
- Motor parameters
- Materials and physics properties

This module provides:
1. SMURF file parsing and generation
2. URDF + SMURF merging
3. Conversion to/from FTI internal format

Reference: https://github.com/dfki-ric/phobos
SMURF Spec: https://github.com/dfki-ric/phobos/wiki/SMURF
"""

import copy
import json
import logging
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Try to import YAML (optional dependency)
try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    yaml = None
    YAML_AVAILABLE = False

from .submechanism import (
    JointCoupling,
    LoopConstraint,
    Submechanism,
    SubmechanismManager,
    SubmechanismType,
)

logger = logging.getLogger(__name__)


@dataclass
class SMURFMotor:
    """SMURF motor definition."""

    name: str
    joint: str  # Associated joint
    motor_type: str = "dc"  # dc, bldc, stepper, servo
    max_torque: float = 100.0  # Nm
    max_velocity: float = 10.0  # rad/s
    gear_ratio: float = 1.0
    inertia: float = 0.001  # kg*m^2
    friction: float = 0.01  # Nm
    damping: float = 0.001  # Nm*s/rad


@dataclass
class SMURFSensor:
    """SMURF sensor definition."""

    name: str
    link: str  # Attached link
    sensor_type: str = "camera"  # camera, imu, lidar, force_torque, joint_state
    rate: float = 30.0  # Hz

    # Camera-specific
    width: int = 640
    height: int = 480
    fov: float = 60.0  # degrees

    # IMU-specific
    noise_stddev: float = 0.0

    # Position/orientation relative to link
    position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    orientation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 1.0])

    # Custom properties
    properties: Dict = field(default_factory=dict)


@dataclass
class SMURFMaterial:
    """SMURF extended material with physics properties."""

    name: str

    # Visual properties
    diffuse_color: List[float] = field(default_factory=lambda: [0.5, 0.5, 0.5, 1.0])
    specular_color: List[float] = field(default_factory=lambda: [0.5, 0.5, 0.5, 1.0])
    emissive_color: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 1.0])
    shininess: float = 50.0

    # Texture paths
    diffuse_texture: str = ""
    normal_texture: str = ""

    # Physics properties
    friction: float = 0.8
    restitution: float = 0.0
    density: float = 1000.0  # kg/m^3


@dataclass
class SMURFData:
    """
    Complete SMURF data structure.

    Contains all supplementary information for a URDF robot.
    """

    name: str = "robot"
    version: str = "2.0"

    # Submechanisms and loops
    submechanisms: List[Submechanism] = field(default_factory=list)
    loop_constraints: List[LoopConstraint] = field(default_factory=list)

    # Motors and sensors
    motors: List[SMURFMotor] = field(default_factory=list)
    sensors: List[SMURFSensor] = field(default_factory=list)

    # Materials with physics
    materials: List[SMURFMaterial] = field(default_factory=list)

    # Joint groups (for control)
    joint_groups: Dict[str, List[str]] = field(default_factory=dict)

    # Poses (named configurations)
    poses: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # Custom annotations
    annotations: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "version": self.version,
            "submechanisms": [sm.to_dict() for sm in self.submechanisms],
            "loop_constraints": [
                asdict(lc) if hasattr(lc, "__dataclass_fields__") else lc.to_dict()
                for lc in self.loop_constraints
            ],
            "motors": [asdict(m) for m in self.motors],
            "sensors": [asdict(s) for s in self.sensors],
            "materials": [asdict(m) for m in self.materials],
            "joint_groups": self.joint_groups,
            "poses": self.poses,
            "annotations": self.annotations,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SMURFData":
        """Create from dictionary."""
        submechanisms = [Submechanism.from_dict(sm) for sm in data.get("submechanisms", [])]
        loop_constraints = [LoopConstraint.from_dict(lc) for lc in data.get("loop_constraints", [])]
        motors = [SMURFMotor(**m) for m in data.get("motors", [])]
        sensors = [SMURFSensor(**s) for s in data.get("sensors", [])]
        materials = [SMURFMaterial(**m) for m in data.get("materials", [])]

        return cls(
            name=data.get("name", "robot"),
            version=data.get("version", "2.0"),
            submechanisms=submechanisms,
            loop_constraints=loop_constraints,
            motors=motors,
            sensors=sensors,
            materials=materials,
            joint_groups=data.get("joint_groups", {}),
            poses=data.get("poses", {}),
            annotations=data.get("annotations", {}),
        )


class SMURFParser:
    """
    Parse SMURF files (YAML or JSON).

    SMURF uses a multi-file structure:
    - smurf.yml/json: Main manifest
    - submechanisms.yml: Kinematic groups
    - motors.yml: Motor parameters
    - sensors.yml: Sensor definitions
    - materials.yml: Material properties
    """

    @classmethod
    def parse_smurf_directory(cls, smurf_dir: str) -> SMURFData:
        """
        Parse a SMURF directory containing multiple YAML/JSON files.

        Args:
            smurf_dir: Path to SMURF directory

        Returns:
            Merged SMURFData
        """
        smurf_path = Path(smurf_dir)

        if not smurf_path.is_dir():
            raise ValueError(f"Not a directory: {smurf_dir}")

        data = SMURFData()

        # Try to find main manifest
        for manifest_name in [
            "smurf.yml",
            "smurf.yaml",
            "smurf.json",
            "manifest.yml",
            "manifest.json",
        ]:
            manifest_path = smurf_path / manifest_name
            if manifest_path.exists():
                manifest = cls._load_file(str(manifest_path))
                data.name = manifest.get("modelname", manifest.get("name", "robot"))
                data.version = manifest.get("version", "2.0")
                break

        # Parse component files
        file_handlers = {
            "submechanisms": cls._parse_submechanisms,
            "motors": cls._parse_motors,
            "sensors": cls._parse_sensors,
            "materials": cls._parse_materials,
            "poses": cls._parse_poses,
            "joint_groups": cls._parse_joint_groups,
        }

        for component, handler in file_handlers.items():
            for ext in [".yml", ".yaml", ".json"]:
                file_path = smurf_path / f"{component}{ext}"
                if file_path.exists():
                    content = cls._load_file(str(file_path))
                    handler(content, data)
                    break

        return data

    @classmethod
    def parse_smurf_file(cls, file_path: str) -> SMURFData:
        """
        Parse a single SMURF file (merged format).

        Args:
            file_path: Path to SMURF YAML/JSON file

        Returns:
            SMURFData
        """
        content = cls._load_file(file_path)
        return SMURFData.from_dict(content)

    @classmethod
    def _load_file(cls, path: str) -> Dict:
        """Load YAML or JSON file."""
        path_obj = Path(path)
        content = path_obj.read_text()

        if path_obj.suffix in [".yml", ".yaml"]:
            if not YAML_AVAILABLE:
                raise ImportError("PyYAML required for YAML files: pip install pyyaml")
            return yaml.safe_load(content)
        else:
            return json.loads(content)

    @classmethod
    def _parse_submechanisms(cls, content: Any, data: SMURFData):
        """Parse submechanisms section."""
        if isinstance(content, dict):
            items = content.get("submechanisms", content.get("chains", []))
        elif isinstance(content, list):
            items = content
        else:
            return

        for item in items:
            # Handle SMURF format
            sm = Submechanism(
                name=item.get("name", item.get("contextual_name", "")),
                type=SubmechanismType.from_string(item.get("type", "serial")),
                joints=item.get("joints", []),
                independent_joints=item.get("jointnames_independent", item.get("independent", [])),
                spanning_tree_joints=item.get(
                    "jointnames_spanningtree", item.get("spanning_tree", [])
                ),
                active_joints=item.get("jointnames_active", item.get("active", [])),
            )
            data.submechanisms.append(sm)

        # Also check for loop_constraints in same file
        if isinstance(content, dict) and "loop_constraints" in content:
            for lc_data in content["loop_constraints"]:
                lc = LoopConstraint(
                    name=lc_data.get("name", ""),
                    link_a=lc_data.get("link", ""),
                    link_b=lc_data.get("joint", ""),
                    constraint_axes=lc_data.get("constraint_axes", [1, 1, 1, 1, 1, 1]),
                )
                data.loop_constraints.append(lc)

    @classmethod
    def _parse_motors(cls, content: Any, data: SMURFData):
        """Parse motors section."""
        if isinstance(content, dict):
            items = content.get("motors", [])
        elif isinstance(content, list):
            items = content
        else:
            return

        for item in items:
            motor = SMURFMotor(
                name=item.get("name", ""),
                joint=item.get("joint", ""),
                motor_type=item.get("type", "dc"),
                max_torque=item.get("maxEffort", item.get("max_torque", 100.0)),
                max_velocity=item.get("maxSpeed", item.get("max_velocity", 10.0)),
                gear_ratio=item.get("gearRatio", item.get("gear_ratio", 1.0)),
            )
            data.motors.append(motor)

    @classmethod
    def _parse_sensors(cls, content: Any, data: SMURFData):
        """Parse sensors section."""
        if isinstance(content, dict):
            items = content.get("sensors", [])
        elif isinstance(content, list):
            items = content
        else:
            return

        for item in items:
            sensor = SMURFSensor(
                name=item.get("name", ""),
                link=item.get("link", ""),
                sensor_type=item.get("type", "camera"),
                rate=item.get("rate", item.get("update_rate", 30.0)),
            )
            if "position" in item:
                sensor.position = item["position"]
            if "orientation" in item:
                sensor.orientation = item["orientation"]
            data.sensors.append(sensor)

    @classmethod
    def _parse_materials(cls, content: Any, data: SMURFData):
        """Parse materials section."""
        if isinstance(content, dict):
            items = content.get("materials", [])
        elif isinstance(content, list):
            items = content
        else:
            return

        for item in items:
            material = SMURFMaterial(
                name=item.get("name", ""),
                diffuse_color=item.get("diffuseColor", item.get("diffuse", [0.5, 0.5, 0.5, 1.0])),
                friction=item.get("friction", 0.8),
                restitution=item.get("restitution", 0.0),
            )
            if "diffuseTexture" in item:
                material.diffuse_texture = item["diffuseTexture"]
            data.materials.append(material)

    @classmethod
    def _parse_poses(cls, content: Any, data: SMURFData):
        """Parse poses section."""
        if isinstance(content, dict):
            items = content.get("poses", content)
        else:
            return

        for name, pose_data in items.items():
            if name != "poses" and isinstance(pose_data, dict):
                data.poses[name] = pose_data

    @classmethod
    def _parse_joint_groups(cls, content: Any, data: SMURFData):
        """Parse joint groups section."""
        if isinstance(content, dict):
            items = content.get("groups", content.get("joint_groups", content))
        else:
            return

        for name, joints in items.items():
            if isinstance(joints, list):
                data.joint_groups[name] = joints


class SMURFWriter:
    """
    Write SMURF files.

    Supports both single-file and multi-file output.
    """

    @classmethod
    def write_single_file(cls, data: SMURFData, output_path: str, format: str = "json"):
        """
        Write all SMURF data to a single file.

        Args:
            data: SMURFData to write
            output_path: Output file path
            format: 'json' or 'yaml'
        """
        content = data.to_dict()

        path_obj = Path(output_path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)

        if format == "yaml":
            if not YAML_AVAILABLE:
                raise ImportError("PyYAML required: pip install pyyaml")
            with open(output_path, "w") as f:
                yaml.dump(content, f, default_flow_style=False, sort_keys=False)
        else:
            with open(output_path, "w") as f:
                json.dump(content, f, indent=2)

    @classmethod
    def write_multi_file(cls, data: SMURFData, output_dir: str, format: str = "yaml"):
        """
        Write SMURF data as multiple files (Phobos-style).

        Creates:
        - smurf.yml: Main manifest
        - submechanisms.yml: Kinematic groups
        - motors.yml: Motor parameters
        - sensors.yml: Sensor definitions
        - materials.yml: Material properties

        Args:
            data: SMURFData to write
            output_dir: Output directory
            format: 'json' or 'yaml'
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        ext = ".yml" if format == "yaml" else ".json"

        def write_file(name: str, content: Any):
            file_path = output_path / f"{name}{ext}"
            if format == "yaml":
                if not YAML_AVAILABLE:
                    raise ImportError("PyYAML required: pip install pyyaml")
                with open(file_path, "w") as f:
                    yaml.dump(content, f, default_flow_style=False, sort_keys=False)
            else:
                with open(file_path, "w") as f:
                    json.dump(content, f, indent=2)

        # Main manifest
        manifest = {
            "modelname": data.name,
            "version": data.version,
            "files": [],
        }

        # Submechanisms
        if data.submechanisms or data.loop_constraints:
            sm_content = {
                "submechanisms": [
                    {
                        "name": sm.name,
                        "type": sm.type.value,
                        "jointnames_independent": sm.independent_joints,
                        "jointnames_spanningtree": sm.spanning_tree_joints,
                        "jointnames_active": sm.active_joints,
                    }
                    for sm in data.submechanisms
                ],
                "loop_constraints": [
                    {
                        "name": lc.name,
                        "link": lc.link_a,
                        "joint": lc.link_b,
                        "constraint_axes": lc.constraint_axes,
                    }
                    for lc in data.loop_constraints
                ],
            }
            write_file("submechanisms", sm_content)
            manifest["files"].append(f"submechanisms{ext}")

        # Motors
        if data.motors:
            motors_content = {"motors": [asdict(m) for m in data.motors]}
            write_file("motors", motors_content)
            manifest["files"].append(f"motors{ext}")

        # Sensors
        if data.sensors:
            sensors_content = {"sensors": [asdict(s) for s in data.sensors]}
            write_file("sensors", sensors_content)
            manifest["files"].append(f"sensors{ext}")

        # Materials
        if data.materials:
            materials_content = {"materials": [asdict(m) for m in data.materials]}
            write_file("materials", materials_content)
            manifest["files"].append(f"materials{ext}")

        # Poses
        if data.poses:
            write_file("poses", {"poses": data.poses})
            manifest["files"].append(f"poses{ext}")

        # Joint groups
        if data.joint_groups:
            write_file("joint_groups", {"groups": data.joint_groups})
            manifest["files"].append(f"joint_groups{ext}")

        # Write manifest
        write_file("smurf", manifest)


class SMURFConverter:
    """
    Convert between SMURF format and FTI internal format.

    Enables:
    - Import SMURF metadata alongside URDF
    - Export FTI robot data to SMURF format
    """

    @classmethod
    def merge_urdf_with_smurf(cls, urdf_data: Dict, smurf_data: SMURFData) -> Dict:
        """
        Merge URDF hierarchy data with SMURF metadata.

        Args:
            urdf_data: Parsed URDF hierarchy
            smurf_data: Parsed SMURF data

        Returns:
            Enhanced hierarchy data with SMURF information
        """
        merged = copy.deepcopy(urdf_data)

        # Add submechanisms
        merged["submechanisms"] = [sm.to_dict() for sm in smurf_data.submechanisms]

        # Add loop constraints
        merged["loop_constraints"] = [lc.to_dict() for lc in smurf_data.loop_constraints]

        # Enhance joints with motor data
        motor_map = {m.joint: m for m in smurf_data.motors}
        for joint in merged.get("joints", []):
            joint_name = joint.get("name", "")
            if joint_name in motor_map:
                motor = motor_map[joint_name]
                joint["motor"] = {
                    "name": motor.name,
                    "type": motor.motor_type,
                    "max_torque": motor.max_torque,
                    "max_velocity": motor.max_velocity,
                    "gear_ratio": motor.gear_ratio,
                }

        # Add sensors to links
        sensor_map = {}
        for sensor in smurf_data.sensors:
            if sensor.link not in sensor_map:
                sensor_map[sensor.link] = []
            sensor_map[sensor.link].append(asdict(sensor))

        for link_name, node_data in merged.get("nodes", {}).items():
            if link_name in sensor_map:
                node_data["sensors"] = sensor_map[link_name]

        # Add joint groups
        merged["joint_groups"] = smurf_data.joint_groups

        # Add poses
        merged["poses"] = smurf_data.poses

        # Add annotations
        merged["annotations"] = smurf_data.annotations

        return merged

    @classmethod
    def extract_smurf_from_hierarchy(cls, hierarchy_data: Dict) -> SMURFData:
        """
        Extract SMURF data from FTI hierarchy.

        Args:
            hierarchy_data: FTI internal hierarchy

        Returns:
            SMURFData
        """
        data = SMURFData(name=hierarchy_data.get("name", "robot"))

        # Extract submechanisms
        for sm_dict in hierarchy_data.get("submechanisms", []):
            data.submechanisms.append(Submechanism.from_dict(sm_dict))

        # Extract loop constraints
        for lc_dict in hierarchy_data.get("loop_constraints", []):
            data.loop_constraints.append(LoopConstraint.from_dict(lc_dict))

        # Extract motors from joints
        for joint in hierarchy_data.get("joints", []):
            if "motor" in joint:
                motor_data = joint["motor"]
                motor = SMURFMotor(
                    name=motor_data.get("name", joint.get("name", "")),
                    joint=joint.get("name", ""),
                    motor_type=motor_data.get("type", "dc"),
                    max_torque=motor_data.get("max_torque", 100.0),
                    max_velocity=motor_data.get("max_velocity", 10.0),
                    gear_ratio=motor_data.get("gear_ratio", 1.0),
                )
                data.motors.append(motor)

        # Extract sensors from links
        for link_name, node_data in hierarchy_data.get("nodes", {}).items():
            for sensor_data in node_data.get("sensors", []):
                sensor = SMURFSensor(**sensor_data)
                data.sensors.append(sensor)

        # Copy joint groups and poses
        data.joint_groups = hierarchy_data.get("joint_groups", {})
        data.poses = hierarchy_data.get("poses", {})
        data.annotations = hierarchy_data.get("annotations", {})

        return data


# Convenience functions
def load_smurf(path: str) -> SMURFData:
    """
    Load SMURF data from file or directory.

    Args:
        path: Path to SMURF file or directory

    Returns:
        SMURFData
    """
    if Path(path).is_dir():
        return SMURFParser.parse_smurf_directory(path)
    else:
        return SMURFParser.parse_smurf_file(path)


def save_smurf(data: SMURFData, path: str, multi_file: bool = False, format: str = "yaml"):
    """
    Save SMURF data to file or directory.

    Args:
        data: SMURFData to save
        path: Output path
        multi_file: If True, creates Phobos-style multi-file structure
        format: 'json' or 'yaml'
    """
    if multi_file:
        SMURFWriter.write_multi_file(data, path, format)
    else:
        SMURFWriter.write_single_file(data, path, format)


def merge_urdf_smurf(urdf_path: str, smurf_path: str) -> Dict:
    """
    Convenience function to load and merge URDF with SMURF.

    Args:
        urdf_path: Path to URDF file
        smurf_path: Path to SMURF file or directory

    Returns:
        Merged hierarchy data
    """
    from .urdf_converter import URDFConverter

    # Parse URDF
    urdf_converter = URDFConverter()
    urdf_data = urdf_converter.parse_urdf(urdf_path)

    # Parse SMURF
    smurf_data = load_smurf(smurf_path)

    # Merge
    return SMURFConverter.merge_urdf_with_smurf(urdf_data, smurf_data)
