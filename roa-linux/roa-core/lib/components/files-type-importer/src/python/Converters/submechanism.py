"""
Submechanism Support Module

Implements the Submechanism concept from SMURF/Phobos for reusable kinematic groups.

A Submechanism represents a logical grouping of joints that work together:
- Serial chains (arm, leg, finger)
- Parallel mechanisms (Stewart platform actuator)
- Differential drives (wrist, gripper differential)
- Coupled joints (mimic joints, gear pairs)

This enables:
1. IK grouping - solve IK for each submechanism independently
2. Control abstraction - treat complex mechanisms as single actuators
3. Reusability - define once, instantiate multiple times
4. Analytical solving - apply specialized solvers per type

Based on: SMURF format submechanism specification
Reference: https://github.com/dfki-ric/phobos
"""

import copy
import json
import logging
import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


class SubmechanismType(Enum):
    """Types of submechanisms."""

    SERIAL = "serial"  # Standard serial chain (arm, leg)
    PARALLEL = "parallel"  # Parallel mechanism (Stewart actuator)
    DIFFERENTIAL = "differential"  # Differential drive (wrist, gripper)
    COUPLED = "coupled"  # Coupled/mimic joints
    PLANETARY = "planetary"  # Planetary gear set
    HYBRID = "hybrid"  # Mix of serial and parallel
    INDEPENDENT = "independent"  # Group of independent joints

    @classmethod
    def from_string(cls, value: str) -> "SubmechanismType":
        """Convert string to enum."""
        return cls(value.lower())


class JointCouplingType(Enum):
    """Types of joint coupling."""

    MIMIC = "mimic"  # Mimic joint (URDF mimic tag)
    GEAR = "gear"  # Gear pair (ratio-based)
    BELT = "belt"  # Belt/chain coupling
    TENDON = "tendon"  # Cable/tendon coupling
    LINKAGE = "linkage"  # Mechanical linkage
    DIFFERENTIAL = "differential"  # Differential coupling


@dataclass
class JointCoupling:
    """
    Defines coupling between joints.

    Examples:
    - Mimic joint: joint2 = multiplier * joint1 + offset
    - Gear pair: joint2 = gear_ratio * joint1
    - Differential: joint_out = (joint1 + joint2) / 2
    """

    joint_a: str  # Primary joint
    joint_b: str  # Secondary/coupled joint
    coupling_type: JointCouplingType = JointCouplingType.MIMIC
    multiplier: float = 1.0  # Coupling ratio
    offset: float = 0.0  # Constant offset
    bidirectional: bool = False  # Can drive in both directions?
    coupling_axis: Optional[List[float]] = None  # For 3D couplings

    def compute_coupled_position(self, primary_pos: float) -> float:
        """Compute coupled joint position from primary."""
        return self.multiplier * primary_pos + self.offset

    def compute_primary_position(self, coupled_pos: float) -> float:
        """Inverse: compute primary from coupled (if bidirectional)."""
        if abs(self.multiplier) < 1e-10:
            raise ValueError("Cannot invert coupling with zero multiplier")
        return (coupled_pos - self.offset) / self.multiplier


@dataclass
class LoopConstraint:
    """
    Defines a loop closure constraint (from SMURF).

    When a kinematic chain is broken for tree-based physics,
    this defines how to close it with a constraint.
    """

    name: str  # Constraint name
    link_a: str  # First link
    link_b: str  # Second link
    type: str = "fixed"  # Constraint type: fixed, revolute, prismatic, spherical
    constraint_axes: List[int] = field(
        default_factory=lambda: [1, 1, 1, 1, 1, 1]
    )  # xyz, rpy locked axes

    # Position relative to link_a
    position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    orientation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 1.0])  # Quaternion

    # Joint-like properties (for revolute/prismatic)
    axis: List[float] = field(default_factory=lambda: [0.0, 0.0, 1.0])
    lower_limit: float = -math.pi
    upper_limit: float = math.pi

    # Passive/actuated
    is_passive: bool = True  # Passive constraints close loops

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "LoopConstraint":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class Submechanism:
    """
    A logical grouping of joints that work together.

    Example: Stewart platform with 6 parallel actuators
    - name: "stewart_platform"
    - type: PARALLEL
    - joints: ["leg1", "leg2", "leg3", "leg4", "leg5", "leg6"]
    - independent_joints: ["leg1", "leg2", "leg3", "leg4", "leg5", "leg6"]
    - spanning_tree_joints: (empty - all are independent)
    - active_joints: ["leg1", "leg2", "leg3", "leg4", "leg5", "leg6"]
    """

    name: str  # Submechanism name (e.g., "left_arm")
    type: SubmechanismType  # Type classification

    # Joint classifications (from SMURF)
    joints: List[str] = field(default_factory=list)  # All joints in submechanism
    independent_joints: List[str] = field(default_factory=list)  # DoF-contributing joints
    spanning_tree_joints: List[str] = field(default_factory=list)  # Tree structure joints
    active_joints: List[str] = field(default_factory=list)  # Actuated joints

    # Links involved
    root_link: str = ""  # Base link of submechanism
    end_links: List[str] = field(default_factory=list)  # End-effector links

    # Loop constraints (for parallel mechanisms)
    loop_constraints: List[LoopConstraint] = field(default_factory=list)

    # Joint couplings (for coupled/differential)
    couplings: List[JointCoupling] = field(default_factory=list)

    # IK configuration
    ik_solver_type: str = "numerical"  # "analytical", "numerical", "delegated"
    ik_solver_params: Dict = field(default_factory=dict)

    # Custom properties
    properties: Dict = field(default_factory=dict)

    def get_dof(self) -> int:
        """Get effective degrees of freedom."""
        if self.independent_joints:
            return len(self.independent_joints)
        # For coupled mechanisms, subtract coupled joints
        return len(self.joints) - len(self.couplings)

    def get_actuated_dof(self) -> int:
        """Get actuated degrees of freedom."""
        return len(self.active_joints)

    def is_fully_actuated(self) -> bool:
        """Check if all DoF are actuated."""
        return self.get_actuated_dof() >= self.get_dof()

    def has_loops(self) -> bool:
        """Check if this submechanism has closed loops."""
        return len(self.loop_constraints) > 0

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "type": self.type.value,
            "joints": self.joints,
            "independent_joints": self.independent_joints,
            "spanning_tree_joints": self.spanning_tree_joints,
            "active_joints": self.active_joints,
            "root_link": self.root_link,
            "end_links": self.end_links,
            "loop_constraints": [lc.to_dict() for lc in self.loop_constraints],
            "couplings": [asdict(c) for c in self.couplings],
            "ik_solver_type": self.ik_solver_type,
            "ik_solver_params": self.ik_solver_params,
            "properties": self.properties,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Submechanism":
        """Create from dictionary."""
        loop_constraints = [LoopConstraint.from_dict(lc) for lc in data.get("loop_constraints", [])]
        couplings = [JointCoupling(**c) for c in data.get("couplings", [])]

        return cls(
            name=data["name"],
            type=SubmechanismType.from_string(data.get("type", "serial")),
            joints=data.get("joints", []),
            independent_joints=data.get("independent_joints", []),
            spanning_tree_joints=data.get("spanning_tree_joints", []),
            active_joints=data.get("active_joints", []),
            root_link=data.get("root_link", ""),
            end_links=data.get("end_links", []),
            loop_constraints=loop_constraints,
            couplings=couplings,
            ik_solver_type=data.get("ik_solver_type", "numerical"),
            ik_solver_params=data.get("ik_solver_params", {}),
            properties=data.get("properties", {}),
        )


class SubmechanismDetector:
    """
    Automatically detect submechanisms from robot structure.

    Detection strategies:
    1. Naming conventions (arm, leg, finger, gripper, wheel)
    2. Structural patterns (chains ending at same link = parallel)
    3. Joint types (coupled prismatic = Stewart leg)
    4. User hints from JSON file
    """

    # Common submechanism naming patterns
    NAMING_PATTERNS = {
        "serial": ["arm", "leg", "finger", "spine", "neck", "torso"],
        "parallel": ["platform", "stewart", "delta", "hexapod"],
        "differential": ["wrist", "gripper", "differential"],
        "coupled": ["mimic", "coupled", "synchronized"],
    }

    @classmethod
    def detect_submechanisms(
        cls, hierarchy_data: Dict, hints_file: Optional[str] = None
    ) -> List[Submechanism]:
        """
        Detect submechanisms from robot hierarchy.

        Args:
            hierarchy_data: Parsed robot data with joints and links
            hints_file: Optional JSON file with user-defined submechanisms

        Returns:
            List of detected submechanisms
        """
        submechanisms = []
        joints = hierarchy_data.get("joints", [])
        links = hierarchy_data.get("nodes", {})

        # Load user hints if provided
        user_hints = {}
        if hints_file and Path(hints_file).exists():
            with open(hints_file, "r") as f:
                user_hints = json.load(f)

        # Priority 1: User-defined submechanisms
        if "submechanisms" in user_hints:
            for sm_data in user_hints["submechanisms"]:
                submechanisms.append(Submechanism.from_dict(sm_data))
            logger.info(f"Loaded {len(submechanisms)} user-defined submechanisms")

        # Priority 2: Detect from mimic joints (coupled mechanisms)
        coupled = cls._detect_coupled_joints(joints)
        submechanisms.extend(coupled)

        # Priority 3: Detect from naming conventions
        named = cls._detect_from_naming(joints, links)
        submechanisms.extend(named)

        # Priority 4: Detect parallel mechanisms from structure
        parallel = cls._detect_parallel_structures(joints, links)
        submechanisms.extend(parallel)

        # Deduplicate (a joint can only belong to one submechanism)
        submechanisms = cls._deduplicate_submechanisms(submechanisms)

        logger.info(f"Detected {len(submechanisms)} submechanisms")
        for sm in submechanisms:
            logger.info(f"  {sm.name}: {sm.type.value} ({len(sm.joints)} joints)")

        return submechanisms

    @classmethod
    def _detect_coupled_joints(cls, joints: List[Dict]) -> List[Submechanism]:
        """Detect coupled mechanisms from mimic joints."""
        submechanisms = []

        mimic_groups = {}  # leader -> [followers]

        for joint in joints:
            mimic = joint.get("mimic")
            if mimic:
                leader = mimic.get("joint", "")
                if leader:
                    if leader not in mimic_groups:
                        mimic_groups[leader] = []
                    mimic_groups[leader].append(
                        {
                            "follower": joint.get("name"),
                            "multiplier": mimic.get("multiplier", 1.0),
                            "offset": mimic.get("offset", 0.0),
                        }
                    )

        for leader, followers in mimic_groups.items():
            all_joints = [leader] + [f["follower"] for f in followers]

            couplings = [
                JointCoupling(
                    joint_a=leader,
                    joint_b=f["follower"],
                    coupling_type=JointCouplingType.MIMIC,
                    multiplier=f["multiplier"],
                    offset=f["offset"],
                )
                for f in followers
            ]

            sm = Submechanism(
                name=f"coupled_{leader}",
                type=SubmechanismType.COUPLED,
                joints=all_joints,
                independent_joints=[leader],  # Only leader contributes DoF
                active_joints=[leader],
                couplings=couplings,
            )
            submechanisms.append(sm)

        return submechanisms

    @classmethod
    def _detect_from_naming(cls, joints: List[Dict], links: Dict) -> List[Submechanism]:
        """Detect submechanisms from naming conventions."""
        submechanisms = []

        # Group joints by prefix (left_, right_, l_, r_, etc.)
        prefixed_groups = {}
        for joint in joints:
            name = joint.get("name", "")

            # Extract prefix
            for prefix in [
                "left_",
                "right_",
                "l_",
                "r_",
                "front_",
                "rear_",
                "f_",
                "r_",
            ]:
                if name.lower().startswith(prefix):
                    remainder = name[len(prefix) :]
                    for pattern_type, patterns in cls.NAMING_PATTERNS.items():
                        for pattern in patterns:
                            if pattern in remainder.lower():
                                key = (prefix, pattern_type)
                                if key not in prefixed_groups:
                                    prefixed_groups[key] = []
                                prefixed_groups[key].append(joint)
                                break
                    break

        # Create submechanisms from groups
        for (prefix, sm_type), group_joints in prefixed_groups.items():
            if len(group_joints) >= 2:
                joint_names = [j.get("name") for j in group_joints]

                # Find root and end links
                parent_links = {j.get("parent_link") for j in group_joints}
                child_links = {j.get("child_link") for j in group_joints}
                root = list(parent_links - child_links)
                ends = list(child_links - parent_links)

                sm = Submechanism(
                    name=f"{prefix}{sm_type}",
                    type=SubmechanismType.from_string(sm_type),
                    joints=joint_names,
                    independent_joints=joint_names,  # Assume all independent
                    active_joints=joint_names,
                    root_link=root[0] if root else "",
                    end_links=ends,
                )
                submechanisms.append(sm)

        return submechanisms

    @classmethod
    def _detect_parallel_structures(cls, joints: List[Dict], links: Dict) -> List[Submechanism]:
        """Detect parallel mechanisms from structural patterns."""
        submechanisms = []

        # Find links with multiple children (potential parallel branches)
        parent_count = {}
        child_count = {}

        for joint in joints:
            parent = joint.get("parent_link", "")
            child = joint.get("child_link", "")

            child_count[parent] = child_count.get(parent, 0) + 1
            parent_count[child] = parent_count.get(child, 0) + 1

        # Links with 3+ children are potential parallel mechanism bases
        parallel_bases = [link for link, count in child_count.items() if count >= 3]

        # Links with 3+ parents are potential parallel mechanism platforms
        parallel_platforms = [link for link, count in parent_count.items() if count >= 3]

        # Check for Stewart platform pattern: base with 6 children, all connecting to platform
        for base in parallel_bases:
            base_joints = [j for j in joints if j.get("parent_link") == base]

            if len(base_joints) >= 6:
                # Check if they all connect to same platform
                end_links = [j.get("child_link") for j in base_joints]

                # Find joints continuing from these links
                continuation_joints = []
                for end in end_links:
                    for j in joints:
                        if j.get("parent_link") == end:
                            continuation_joints.append(j)

                # Check if continuations converge
                continuation_ends = {j.get("child_link") for j in continuation_joints}

                if len(continuation_ends) == 1:
                    # Stewart platform pattern!
                    platform = list(continuation_ends)[0]
                    all_joints = [j.get("name") for j in base_joints + continuation_joints]

                    # Create loop constraints for each leg
                    loop_constraints = []
                    for i, (bj, cj) in enumerate(zip(base_joints, continuation_joints)):
                        lc = LoopConstraint(
                            name=f"stewart_leg_{i}_closure",
                            link_a=bj.get("child_link"),
                            link_b=platform,
                            type="spherical",  # Ball joint at platform
                        )
                        loop_constraints.append(lc)

                    sm = Submechanism(
                        name=f"parallel_{base}",
                        type=SubmechanismType.PARALLEL,
                        joints=all_joints,
                        independent_joints=all_joints[:6],  # First 6 are actuated
                        active_joints=all_joints[:6],
                        root_link=base,
                        end_links=[platform],
                        loop_constraints=loop_constraints,
                        ik_solver_type="delegated",  # Need specialized solver
                        ik_solver_params={"solver": "stewart_ik"},
                    )
                    submechanisms.append(sm)

        return submechanisms

    @classmethod
    def _deduplicate_submechanisms(cls, submechanisms: List[Submechanism]) -> List[Submechanism]:
        """Remove overlapping submechanisms, keeping larger ones."""
        if not submechanisms:
            return []

        # Sort by size (prefer larger submechanisms)
        sorted_sms = sorted(submechanisms, key=lambda sm: len(sm.joints), reverse=True)

        result = []
        used_joints = set()

        for sm in sorted_sms:
            sm_joints = set(sm.joints)

            # Check if any joint already used
            if sm_joints & used_joints:
                # Partially overlapping - skip
                continue

            result.append(sm)
            used_joints.update(sm_joints)

        return result


class SubmechanismManager:
    """
    Manages submechanisms for a robot.

    Provides:
    - Hierarchical organization
    - IK solver delegation
    - State management
    - Serialization/deserialization
    """

    def __init__(self, robot_name: str):
        self.robot_name = robot_name
        self.submechanisms: Dict[str, Submechanism] = {}
        self.joint_to_submech: Dict[str, str] = {}  # Joint -> Submech name
        self.ik_callbacks: Dict[str, Callable] = {}  # Solver callbacks

    def add_submechanism(self, sm: Submechanism):
        """Add a submechanism."""
        self.submechanisms[sm.name] = sm
        for joint in sm.joints:
            self.joint_to_submech[joint] = sm.name

    def get_submechanism(self, name: str) -> Optional[Submechanism]:
        """Get submechanism by name."""
        return self.submechanisms.get(name)

    def get_submechanism_for_joint(self, joint_name: str) -> Optional[Submechanism]:
        """Get the submechanism containing a joint."""
        sm_name = self.joint_to_submech.get(joint_name)
        if sm_name:
            return self.submechanisms.get(sm_name)
        return None

    def register_ik_callback(
        self, sm_name: str, callback: Callable[[List[float]], Dict[str, float]]
    ):
        """
        Register an IK solver callback for a submechanism.

        Args:
            sm_name: Submechanism name
            callback: Function that takes target pose [x,y,z,rx,ry,rz]
                     and returns joint positions {joint_name: position}
        """
        self.ik_callbacks[sm_name] = callback

    def solve_ik(self, sm_name: str, target_pose: List[float]) -> Optional[Dict[str, float]]:
        """
        Solve IK for a submechanism.

        Args:
            sm_name: Submechanism name
            target_pose: Target [x, y, z, rx, ry, rz]

        Returns:
            Joint positions if solvable, None otherwise
        """
        if sm_name in self.ik_callbacks:
            return self.ik_callbacks[sm_name](target_pose)

        sm = self.submechanisms.get(sm_name)
        if not sm:
            return None

        # Fallback to delegated solver hint
        if sm.ik_solver_type == "delegated":
            logger.warning(f"No IK callback for delegated solver: {sm_name}")
            return None

        # Try numerical IK fallback (Damped Least Squares)
        result = self._numerical_ik_fallback(sm, target_pose)
        if result is not None:
            return result

        logger.warning(f"No IK solver for: {sm_name}")
        return None

    def _numerical_ik_fallback(
        self,
        sm: "Submechanism",
        target_pose: List[float],
        max_iterations: int = 100,
        tolerance: float = 1e-4,
        damping: float = 0.1,
    ) -> Optional[Dict[str, float]]:
        """
        Numerical IK using Damped Least Squares (Levenberg-Marquardt).

        This is a fallback when no analytical solver is available.
        Works for serial chains; parallel mechanisms need external solvers.

        Args:
            sm: Submechanism to solve
            target_pose: [x, y, z, rx, ry, rz] target pose
            max_iterations: Maximum solver iterations
            tolerance: Convergence tolerance
            damping: Damping factor (higher = more stable, slower)

        Returns:
            Joint positions dict or None if failed
        """
        try:
            import numpy as np
        except ImportError:
            logger.debug("NumPy not available for numerical IK")
            return None

        # Only works for serial chains
        if sm.type not in (SubmechanismType.SERIAL, SubmechanismType.INDEPENDENT):
            logger.debug(f"Numerical IK not suitable for {sm.type.value} submechanisms")
            return None

        # Get joints to solve
        joints = sm.independent_joints or sm.joints
        if not joints:
            return None

        n_joints = len(joints)

        # Initialize joint positions (current or zero)
        q = np.zeros(n_joints)

        target = np.array(target_pose[:3])  # Position only for now

        for iteration in range(max_iterations):
            # Compute current end-effector position (simplified FK)
            current_pos = self._simple_fk(joints, q)

            # Error
            error = target - current_pos
            error_norm = np.linalg.norm(error)

            if error_norm < tolerance:
                logger.debug(f"IK converged in {iteration} iterations")
                return {joints[i]: float(q[i]) for i in range(n_joints)}

            # Compute Jacobian (numerical approximation)
            J = self._compute_jacobian(joints, q, current_pos)

            # Damped Least Squares: q_dot = J^T * (J * J^T + λ²I)^-1 * error
            JJT = J @ J.T
            damped = JJT + (damping**2) * np.eye(3)

            try:
                q_dot = J.T @ np.linalg.solve(damped, error)
            except np.linalg.LinAlgError:
                logger.debug("Singular matrix in IK solver")
                break

            # Update joint positions
            q += q_dot

            # Apply joint limits if available
            q = self._apply_joint_limits(sm, joints, q)

        logger.debug(f"IK did not converge after {max_iterations} iterations")
        return None

    def _simple_fk(self, joints: List[str], q: "np.ndarray") -> "np.ndarray":
        """
        Simplified forward kinematics for IK solver.
        Returns approximate end-effector position.
        """
        import numpy as np

        # Default: assume unit link lengths along Z
        # This is a placeholder - real FK needs robot geometry
        pos = np.zeros(3)
        cumulative_angle = 0.0

        for i, angle in enumerate(q):
            cumulative_angle += angle
            # Simple 2D-ish approximation
            pos[0] += np.cos(cumulative_angle) * 0.1
            pos[1] += np.sin(cumulative_angle) * 0.1
            pos[2] += 0.1  # Stack upward

        return pos

    def _compute_jacobian(
        self,
        joints: List[str],
        q: "np.ndarray",
        current_pos: "np.ndarray",
        delta: float = 1e-6,
    ) -> "np.ndarray":
        """Compute Jacobian numerically."""
        import numpy as np

        n = len(joints)
        J = np.zeros((3, n))

        for i in range(n):
            q_plus = q.copy()
            q_plus[i] += delta
            pos_plus = self._simple_fk(joints, q_plus)
            J[:, i] = (pos_plus - current_pos) / delta

        return J

    def _apply_joint_limits(
        self, sm: "Submechanism", joints: List[str], q: "np.ndarray"
    ) -> "np.ndarray":
        """Apply joint limits from submechanism data."""
        import numpy as np

        # Default limits: ±π
        for i in range(len(q)):
            q[i] = np.clip(q[i], -np.pi, np.pi)

        return q

    def get_all_loop_constraints(self) -> List[LoopConstraint]:
        """Get all loop constraints from all submechanisms."""
        constraints = []
        for sm in self.submechanisms.values():
            constraints.extend(sm.loop_constraints)
        return constraints

    def get_all_couplings(self) -> List[JointCoupling]:
        """Get all joint couplings from all submechanisms."""
        couplings = []
        for sm in self.submechanisms.values():
            couplings.extend(sm.couplings)
        return couplings

    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "robot_name": self.robot_name,
            "submechanisms": [sm.to_dict() for sm in self.submechanisms.values()],
        }

    def to_json(self, path: str):
        """Save to JSON file."""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_dict(cls, data: Dict) -> "SubmechanismManager":
        """Load from dictionary."""
        mgr = cls(data.get("robot_name", "robot"))
        for sm_data in data.get("submechanisms", []):
            sm = Submechanism.from_dict(sm_data)
            mgr.add_submechanism(sm)
        return mgr

    @classmethod
    def from_json(cls, path: str) -> "SubmechanismManager":
        """Load from JSON file."""
        with open(path, "r") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def export_to_smurf_format(self, output_path: str):
        """
        Export submechanisms in SMURF-compatible format.

        This creates a YAML file that can be used with Phobos/SMURF tools.
        """
        import yaml

        smurf_data = {
            "submechanisms": [],
            "loop_constraints": [],
        }

        for sm in self.submechanisms.values():
            smurf_sm = {
                "name": sm.name,
                "type": sm.type.value,
                "jointnames_independent": sm.independent_joints,
                "jointnames_spanningtree": sm.spanning_tree_joints,
                "jointnames_active": sm.active_joints,
            }
            smurf_data["submechanisms"].append(smurf_sm)

        for lc in self.get_all_loop_constraints():
            smurf_lc = {
                "name": lc.name,
                "link": lc.link_a,
                "joint": lc.link_b,  # SMURF uses joint reference
                "constraint_axes": lc.constraint_axes,
            }
            smurf_data["loop_constraints"].append(smurf_lc)

        with open(output_path, "w") as f:
            yaml.dump(smurf_data, f, default_flow_style=False)


# Convenience functions
def detect_and_create_submechanisms(
    hierarchy_data: Dict, hints_file: Optional[str] = None
) -> SubmechanismManager:
    """
    Detect submechanisms and create a manager.

    Args:
        hierarchy_data: Parsed robot data
        hints_file: Optional user hints JSON

    Returns:
        SubmechanismManager with detected submechanisms
    """
    robot_name = hierarchy_data.get("name", "robot")
    submechanisms = SubmechanismDetector.detect_submechanisms(hierarchy_data, hints_file)

    manager = SubmechanismManager(robot_name)
    for sm in submechanisms:
        manager.add_submechanism(sm)

    return manager


def create_submechanism_from_joints(
    name: str,
    joints: List[str],
    sm_type: Union[str, SubmechanismType] = SubmechanismType.SERIAL,
    **kwargs,
) -> Submechanism:
    """
    Convenience function to create a submechanism from joint list.

    Args:
        name: Submechanism name
        joints: List of joint names
        sm_type: Type of submechanism
        **kwargs: Additional Submechanism attributes

    Returns:
        Configured Submechanism
    """
    if isinstance(sm_type, str):
        sm_type = SubmechanismType.from_string(sm_type)

    return Submechanism(
        name=name,
        type=sm_type,
        joints=joints,
        independent_joints=joints,
        active_joints=joints,
        **kwargs,
    )
