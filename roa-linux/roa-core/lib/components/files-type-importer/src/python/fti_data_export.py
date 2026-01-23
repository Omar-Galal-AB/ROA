"""
Data Export Interface for FTI
Exports model metadata for integration with DIMC, ROC, and COMC

v3.2 - Added COMC support:
- export_for_comc() function for multi-robot coordination data
- Robot type detection (IndustrialArm, MobileRobot, etc.)
- Bounding radius calculation from link geometry
- Footprint extraction for path planning
- Capability detection (is_mobile, has_gripper, reach)
- Safety zone calculation

v3.4 - Enhanced detection and estimation:
- Humanoid robot type detection (torso + symmetric limbs)
- Quadruped robot type detection (4-leg structures)
- Physics-based payload estimation (joint torque analysis)
- Accurate footprint from actual geometry:
  * Wheel spread for mobile robots
  * Inertia-based dimensions for bases
  * Stance width for humanoids
  * Leg spread for quadrupeds
  * Rotor spread for drones
- Inter-robot collision margin precomputation:
  * Static/dynamic margins
  * Footprint and workspace margins
  * Robot-type specific adjustments
  * Pairing recommendations
"""

import json
import math
from dataclasses import asdict
from typing import Dict, List, Optional, Tuple


class FTIDataExporter:
    """
    Exports FTI data in formats compatible with other ROA components.

    Provides model metadata for DIMC (dimensions, hierarchy) and
    ROC (joint definitions for control).
    """

    def __init__(self):
        """Initialize the data exporter."""
        pass

    def export_for_dimc(self, import_result, hierarchy_data: Optional[Dict] = None) -> Dict:
        """
        Export model metadata for Dimensions Collector (DIMC).

        DIMC needs:
        - Part names and hierarchy
        - Assembly structure
        - Initial dimensions (will be refined by DIMC)

        Args:
            import_result: ImportResult from FTI
            hierarchy_data: Optional hierarchy information from converter

        Returns:
            Dictionary with DIMC-compatible metadata
        """
        metadata = {
            "robot_name": import_result.robot_name,
            "import_success": import_result.success,
            "parts": {
                "count": import_result.parts_count,
                "names": [],
                "paths": import_result.parts_paths or [],
            },
            "assembly": {"path": import_result.assembly_path, "hierarchy": None},
            "content_location": import_result.content_path,
        }

        # Add hierarchy if available
        if hierarchy_data:
            metadata["assembly"]["hierarchy"] = {
                "root_nodes": hierarchy_data.get("root_nodes", []),
                "assembly_order": hierarchy_data.get("assembly_order", []),
                "depth": hierarchy_data.get("depth", 0),
                "nodes": hierarchy_data.get("nodes", {}),
            }

            # Extract part names from hierarchy
            if "nodes" in hierarchy_data:
                metadata["parts"]["names"] = [
                    name
                    for name, node in hierarchy_data["nodes"].items()
                    if node.get("type") == "link"
                ]

        return metadata

    def export_for_roc(self, import_result, hierarchy_data: Optional[Dict] = None) -> Dict:
        """
        Export joint definitions for Robot Operator Controller (ROC).

        ROC needs:
        - Joint names and types
        - Joint limits and properties
        - Parent-child relationships for control hierarchy

        Args:
            import_result: ImportResult from FTI
            hierarchy_data: Optional hierarchy information from converter

        Returns:
            Dictionary with ROC-compatible joint definitions
        """
        joint_info = {
            "robot_name": import_result.robot_name,
            "joints": [],
            "links": [],
            "control_hierarchy": None,
        }

        if hierarchy_data and "nodes" in hierarchy_data:
            # Extract joint information
            for name, node in hierarchy_data["nodes"].items():
                if node.get("type") == "joint":
                    joint_def = {
                        "name": name,
                        "parent_link": node.get("parent"),
                        "child_link": None,  # Determined from children
                        "joint_type": node.get("properties", {}).get("joint_type"),
                        "transform": node.get("transform"),
                        "properties": node.get("properties", {}),
                    }

                    # Find child link from parent's children
                    parent_node = hierarchy_data["nodes"].get(node.get("parent"))
                    if parent_node and parent_node.get("children"):
                        # Child is typically the non-joint child
                        for child in parent_node["children"]:
                            child_node = hierarchy_data["nodes"].get(child)
                            if child_node and child_node.get("type") == "link":
                                joint_def["child_link"] = child
                                break

                    joint_info["joints"].append(joint_def)

                elif node.get("type") == "link":
                    link_def = {
                        "name": name,
                        "parent": node.get("parent"),
                        "children": node.get("children", []),
                    }
                    joint_info["links"].append(link_def)

            # Add control hierarchy
            joint_info["control_hierarchy"] = {
                "root_nodes": hierarchy_data.get("root_nodes", []),
                "assembly_order": hierarchy_data.get("assembly_order", []),
            }

        return joint_info

    def export_status_for_webthread(self, status: str, component_info: Dict) -> Dict:
        """
        Export status information for Webthread monitoring.

        Args:
            status: Current FTI status
            component_info: Additional component information

        Returns:
            Dictionary with status information
        """
        return {
            "component": "FTI",
            "status": status,
            "timestamp": component_info.get("timestamp"),
            "supported_formats": component_info.get("supported_formats", []),
            "active_imports": component_info.get("active_imports", 0),
            "total_imports": component_info.get("total_imports", 0),
            "last_error": component_info.get("last_error"),
        }

    def create_import_command(
        self,
        file_path: str,
        robot_name: Optional[str] = None,
        import_mode: str = "both",
    ) -> str:
        """
        Create a JSON import command for ROS2 topic.

        Args:
            file_path: Path to the 3D model file
            robot_name: Optional robot name
            import_mode: Import mode (parts, assembly, both)

        Returns:
            JSON string with import command
        """
        command = {
            "command": "import_robot",
            "file_path": file_path,
            "robot_name": robot_name,
            "import_mode": import_mode,
        }
        return json.dumps(command)

    # ==================== COMC EXPORT (v3.2) ====================

    def export_for_comc(self, import_result, hierarchy_data: Optional[Dict] = None) -> Dict:
        """
        Export robot specifications for COMC (Communication Center) coordination.

        COMC needs this data for:
        - Collision detection (bounding_radius)
        - Path planning (footprint)
        - Coordination mode selection (robot_type, is_mobile)
        - Task assignment (capabilities)
        - Safety zone triggers (safety_zones)

        Args:
            import_result: ImportResult from FTI
            hierarchy_data: Hierarchy data from URDF converter with links, joints, sensors

        Returns:
            Dictionary with COMC-compatible robot specifications
        """
        robot_id = getattr(import_result, "robot_id", None) or import_result.robot_name

        # Detect robot type from structure
        robot_type = self._detect_robot_type(hierarchy_data)

        # Calculate geometry for collision detection and path planning
        bounding_radius = self._calculate_bounding_radius(hierarchy_data)
        footprint = self._extract_footprint(hierarchy_data, robot_type)
        collision_shapes = self._extract_collision_shapes(hierarchy_data)

        # Detect capabilities
        capabilities = self._detect_capabilities(hierarchy_data, robot_type)

        # Calculate safety zones
        safety_zones = self._calculate_safety_zones(hierarchy_data, bounding_radius)

        # Build kinematic chain summary
        kinematic_chain = self._build_kinematic_chain_summary(hierarchy_data)

        # v3.4: Calculate collision margins for inter-robot coordination
        collision_margins = self._calculate_collision_margins(
            bounding_radius, footprint, robot_type
        )

        # v3.4: Estimate payload capacity from joint torques
        payload_capacity = self._estimate_payload_capacity(hierarchy_data, robot_type)

        return {
            "robot_id": robot_id,
            "robot_name": import_result.robot_name,
            "robot_type": robot_type,
            "geometry": {
                "bounding_radius": bounding_radius,
                "collision_shapes": collision_shapes,
                "footprint": footprint,
                "collision_margins": collision_margins,  # v3.4
            },
            "kinematic_chain": kinematic_chain,
            "capabilities": {
                **capabilities,
                "payload_capacity_kg": payload_capacity,  # v3.4
            },
            "safety_zones": safety_zones,
            # Metadata
            "export_version": "3.4",
            "source": "FTI",
        }

    def _detect_robot_type(self, hierarchy_data: Optional[Dict]) -> str:
        """
        Detect robot type based on structure and joint configuration (v3.4 enhanced).

        Detection heuristics:
        - Mobile robots: Have wheel joints or differential drive
        - Industrial arms: Have 5+ revolute joints in a chain with gripper
        - Humanoids: Have torso/chest + symmetric arm/leg structure (v3.4)
        - Drones: Have rotor/propeller joints (4+)
        - Quadrupeds: Have 4 leg chains with hip/knee/ankle

        Returns:
            Robot type string: 'IndustrialArm', 'MobileRobot', 'Humanoid', 'Drone', 'Quadruped', 'Unknown'
        """
        if not hierarchy_data:
            return "Unknown"

        joints = hierarchy_data.get("joints", [])
        nodes = hierarchy_data.get("nodes", {})

        # Count joint types
        revolute_count = 0
        continuous_count = 0
        wheel_count = 0

        # Look for indicators
        has_wheels = False
        has_gripper = False
        has_base_link = False

        # v3.4: Humanoid detection indicators
        has_torso = False
        has_left_arm = False
        has_right_arm = False
        has_left_leg = False
        has_right_leg = False
        has_head = False

        # v3.4: Quadruped indicators
        leg_count = 0

        for joint in joints:
            joint_type = joint.get("type", "fixed").lower()
            joint_name = joint.get("name", "").lower()
            child_link = (joint.get("child_link") or "").lower()
            parent_link = (joint.get("parent_link") or "").lower()

            if joint_type == "revolute":
                revolute_count += 1
            elif joint_type == "continuous":
                continuous_count += 1

            # Detect wheels
            if "wheel" in joint_name or "wheel" in child_link:
                wheel_count += 1
                has_wheels = True

            # Detect gripper
            if any(g in joint_name for g in ["gripper", "finger", "hand", "grasp"]):
                has_gripper = True
            if any(g in child_link for g in ["gripper", "finger", "hand", "grasp"]):
                has_gripper = True

            # v3.4: Humanoid body part detection
            combined = joint_name + child_link + parent_link
            if any(t in combined for t in ["torso", "chest", "trunk", "body"]):
                has_torso = True
            if any(h in combined for h in ["head", "neck"]):
                has_head = True
            if "left" in combined and any(
                a in combined for a in ["arm", "shoulder", "elbow", "wrist"]
            ):
                has_left_arm = True
            if "right" in combined and any(
                a in combined for a in ["arm", "shoulder", "elbow", "wrist"]
            ):
                has_right_arm = True
            if "left" in combined and any(
                l in combined for l in ["leg", "hip", "knee", "ankle", "thigh", "shin"]
            ):
                has_left_leg = True
            if "right" in combined and any(
                l in combined for l in ["leg", "hip", "knee", "ankle", "thigh", "shin"]
            ):
                has_right_leg = True

            # v3.4: Count legs for quadruped
            if any(l in joint_name for l in ["leg", "hip", "thigh"]) and any(
                s in joint_name
                for s in [
                    "fl",
                    "fr",
                    "bl",
                    "br",
                    "lf",
                    "rf",
                    "lb",
                    "rb",
                    "front_left",
                    "front_right",
                    "back_left",
                    "back_right",
                    "rear",
                ]
            ):
                leg_count += 1

        # Check for base_link (common in mobile robots)
        for node_name in nodes.keys():
            if "base" in node_name.lower():
                has_base_link = True
                break

        # v3.4: Humanoid detection (check first - most specific)
        if has_torso and (has_left_arm or has_right_arm) and (has_left_leg or has_right_leg):
            return "Humanoid"

        # Symmetric arm structure also suggests humanoid
        if has_left_arm and has_right_arm and revolute_count >= 10:
            return "Humanoid"

        # v3.4: Quadruped detection
        if leg_count >= 8:  # 4 legs * 2+ joints each
            return "Quadruped"

        # Detection logic
        if wheel_count >= 2 or (has_wheels and continuous_count >= 2):
            return "MobileRobot"

        if revolute_count >= 5 and has_gripper:
            return "IndustrialArm"

        if revolute_count >= 6:
            # Check if it's a serial chain (arm-like)
            if self._is_serial_chain(joints):
                return "IndustrialArm"

        # Check for drone (rotor joints)
        rotor_count = sum(
            1
            for j in joints
            if "rotor" in j.get("name", "").lower() or "prop" in j.get("name", "").lower()
        )
        if rotor_count >= 4:
            return "Drone"

        # Default based on structure
        if has_wheels or has_base_link:
            return "MobileRobot"
        elif revolute_count > 0:
            return "IndustrialArm"

        return "Unknown"

    def _is_serial_chain(self, joints: List[Dict]) -> bool:
        """Check if joints form a serial kinematic chain (typical of robot arms)."""
        if len(joints) < 3:
            return False

        # Build parent-child map
        child_to_parent = {}
        for joint in joints:
            child = joint.get("child_link")
            parent = joint.get("parent_link")
            if child and parent:
                child_to_parent[child] = parent

        # Check for a long chain
        max_chain_length = 0
        for start_link in child_to_parent.keys():
            length = 1
            current = start_link
            visited = set()
            while current in child_to_parent and current not in visited:
                visited.add(current)
                current = child_to_parent[current]
                length += 1
            max_chain_length = max(max_chain_length, length)

        return max_chain_length >= 5

    def _calculate_bounding_radius(self, hierarchy_data: Optional[Dict]) -> float:
        """
        Calculate bounding radius from link geometry.

        Uses maximum extent from all link collision/visual geometries.
        This is used by COMC for collision detection.

        Returns:
            Bounding radius in meters (minimum 0.1m)
        """
        if not hierarchy_data:
            return 0.5  # Default safe radius

        nodes = hierarchy_data.get("nodes", {})
        joints = hierarchy_data.get("joints", [])

        max_radius = 0.0

        # Method 1: Sum of joint origins (kinematic reach)
        total_reach = 0.0
        for joint in joints:
            origin = joint.get("origin", {})
            xyz = origin.get("xyz", [0, 0, 0])
            distance = math.sqrt(xyz[0] ** 2 + xyz[1] ** 2 + xyz[2] ** 2)
            total_reach += distance

        max_radius = max(max_radius, total_reach)

        # Method 2: Check link properties for collision geometry bounds
        for node_name, node_data in nodes.items():
            if node_data.get("type") != "link":
                continue

            props = node_data.get("properties", {})

            # Check for mass - heavier links are usually larger
            mass = props.get("mass", 0)
            if mass > 0:
                # Rough estimate: mass ~ volume, radius ~ cbrt(volume)
                estimated_radius = (mass / 1000) ** (1 / 3) * 0.1  # rough scaling
                max_radius = max(max_radius, estimated_radius)

        # Ensure minimum safe radius
        return max(0.1, max_radius)

    def _extract_footprint(self, hierarchy_data: Optional[Dict], robot_type: str) -> Dict:
        """
        Extract footprint for path planning (v3.4 enhanced).

        v3.4: Now analyzes actual base_link geometry and inertia to calculate
        accurate footprint dimensions instead of using defaults.

        Mobile robots: Rectangular or circular based on actual base dimensions
        Arms: Fixed workspace polygon based on reach
        Humanoids: Polygon based on stance width
        Quadrupeds: Rectangle based on leg spread

        Returns:
            Footprint dictionary with type and dimensions
        """
        if not hierarchy_data:
            return {"type": "circle", "radius": 0.3}

        nodes = hierarchy_data.get("nodes", {})
        joints = hierarchy_data.get("joints", [])

        # Find base_link and extract its properties
        base_link_name = None
        base_link_props = {}
        for node_name, node_data in nodes.items():
            if node_data.get("type") == "link":
                name_lower = node_name.lower()
                # Look for common base link names
                if any(b in name_lower for b in ["base_link", "base_footprint", "chassis", "body"]):
                    base_link_name = node_name
                    base_link_props = node_data.get("properties", {})
                    break

        # Fallback: use root node
        if not base_link_name:
            root_nodes = hierarchy_data.get("root_nodes", [])
            if root_nodes:
                base_link_name = root_nodes[0]
                base_link_props = nodes.get(base_link_name, {}).get("properties", {})

        # v3.4: Calculate footprint from base inertia and mass
        footprint_dims = self._calculate_footprint_from_inertia(base_link_props)

        if robot_type == "MobileRobot":
            # v3.4: Calculate from wheel positions or base geometry
            wheel_spread = self._calculate_wheel_spread(joints, nodes)

            if wheel_spread["width"] > 0 and wheel_spread["length"] > 0:
                # Use wheel-based rectangular footprint
                return {
                    "type": "rectangle",
                    "width": round(wheel_spread["width"] * 1.1, 3),  # 10% margin
                    "length": round(wheel_spread["length"] * 1.1, 3),
                    "center_offset_x": wheel_spread.get("center_x", 0),
                    "center_offset_y": wheel_spread.get("center_y", 0),
                    "from_geometry": True,
                }
            elif footprint_dims["width"] > 0:
                # Use inertia-based footprint
                return {
                    "type": "rectangle",
                    "width": round(footprint_dims["width"], 3),
                    "length": round(footprint_dims["length"], 3),
                    "from_inertia": True,
                }
            else:
                # Default circular
                return {
                    "type": "circle",
                    "radius": 0.3,
                }

        elif robot_type == "IndustrialArm":
            # Fixed base with reach radius
            bounding = self._calculate_bounding_radius(hierarchy_data)
            base_radius = footprint_dims.get("radius", 0.2)
            return {
                "type": "fixed",
                "workspace_radius": round(bounding, 3),
                "base_radius": round(base_radius, 3),
                "from_geometry": True,
            }

        elif robot_type == "Humanoid":
            # v3.4: Humanoid footprint from stance width
            stance_width = self._calculate_humanoid_stance(joints, nodes)
            return {
                "type": "polygon",
                "shape": "capsule",  # Elongated shape for walking
                "width": round(stance_width.get("width", 0.5), 3),
                "length": round(stance_width.get("length", 0.3), 3),
                "from_geometry": True,
            }

        elif robot_type == "Quadruped":
            # v3.4: Quadruped footprint from leg spread
            leg_spread = self._calculate_quadruped_spread(joints, nodes)
            return {
                "type": "rectangle",
                "width": round(leg_spread.get("width", 0.4), 3),
                "length": round(leg_spread.get("length", 0.6), 3),
                "from_geometry": True,
            }

        elif robot_type == "Drone":
            # v3.4: Drone footprint from rotor spread
            rotor_spread = self._calculate_rotor_spread(joints)
            return {
                "type": "circle",
                "radius": round(rotor_spread * 0.6, 3),  # Propeller disk
                "from_geometry": True,
            }

        else:
            return {
                "type": "circle",
                "radius": 0.3,
            }

    def _calculate_footprint_from_inertia(self, link_props: Dict) -> Dict:
        """
        Calculate footprint dimensions from link inertia tensor (v3.4).

        Uses principal moments of inertia to estimate link dimensions.
        For a rectangular box: Ixx ~ m(y² + z²)/12, Iyy ~ m(x² + z²)/12
        """
        result = {"width": 0, "length": 0, "radius": 0}

        mass = link_props.get("mass", 0)
        inertia = link_props.get("inertia", {})

        if mass <= 0 or not inertia:
            return result

        ixx = inertia.get("ixx", 0)
        iyy = inertia.get("iyy", 0)
        izz = inertia.get("izz", 0)

        if ixx <= 0 or iyy <= 0 or izz <= 0:
            return result

        # Solve for dimensions assuming rectangular box
        # Ixx = m(y² + z²)/12, Iyy = m(x² + z²)/12, Izz = m(x² + y²)/12
        # Assuming z (height) is small for base links
        try:
            # Estimate x and y from Izz (horizontal plane inertia)
            # Izz = m(x² + y²)/12
            xy_sum = 12 * izz / mass

            # Use Ixx and Iyy to differentiate x and y
            # Ixx - Iyy = m(y² - x²)/12
            xy_diff = 12 * (ixx - iyy) / mass

            # Solve: x² + y² = xy_sum, y² - x² = xy_diff
            y_sq = (xy_sum + xy_diff) / 2
            x_sq = (xy_sum - xy_diff) / 2

            if x_sq > 0 and y_sq > 0:
                result["width"] = math.sqrt(y_sq)
                result["length"] = math.sqrt(x_sq)
                result["radius"] = math.sqrt(xy_sum) / 2
        except Exception:
            pass

        return result

    def _calculate_wheel_spread(self, joints: List[Dict], nodes: Dict) -> Dict:
        """
        Calculate footprint from wheel joint positions (v3.4).
        """
        result = {"width": 0, "length": 0, "center_x": 0, "center_y": 0}

        wheel_positions = []
        for joint in joints:
            joint_name = joint.get("name", "").lower()
            child_link = (joint.get("child_link") or "").lower()

            if "wheel" in joint_name or "wheel" in child_link:
                origin = joint.get("origin", {})
                xyz = origin.get("xyz", [0, 0, 0])
                wheel_positions.append(xyz)

        if len(wheel_positions) >= 2:
            # Calculate bounding box
            xs = [p[0] for p in wheel_positions]
            ys = [p[1] for p in wheel_positions]

            result["length"] = max(xs) - min(xs) if xs else 0
            result["width"] = max(ys) - min(ys) if ys else 0
            result["center_x"] = (max(xs) + min(xs)) / 2 if xs else 0
            result["center_y"] = (max(ys) + min(ys)) / 2 if ys else 0

        return result

    def _calculate_humanoid_stance(self, joints: List[Dict], nodes: Dict) -> Dict:
        """Calculate humanoid stance width from hip/ankle positions (v3.4)."""
        result = {"width": 0.5, "length": 0.3}

        foot_positions = []
        for joint in joints:
            joint_name = joint.get("name", "").lower()
            if any(f in joint_name for f in ["ankle", "foot"]):
                origin = joint.get("origin", {})
                xyz = origin.get("xyz", [0, 0, 0])
                foot_positions.append(xyz)

        if len(foot_positions) >= 2:
            ys = [p[1] for p in foot_positions]
            result["width"] = abs(max(ys) - min(ys))
            xs = [p[0] for p in foot_positions]
            result["length"] = abs(max(xs) - min(xs)) if xs else 0.3

        return result

    def _calculate_quadruped_spread(self, joints: List[Dict], nodes: Dict) -> Dict:
        """Calculate quadruped footprint from leg positions (v3.4)."""
        result = {"width": 0.4, "length": 0.6}

        hip_positions = []
        for joint in joints:
            joint_name = joint.get("name", "").lower()
            if "hip" in joint_name or "thigh" in joint_name:
                origin = joint.get("origin", {})
                xyz = origin.get("xyz", [0, 0, 0])
                hip_positions.append(xyz)

        if len(hip_positions) >= 4:
            xs = [p[0] for p in hip_positions]
            ys = [p[1] for p in hip_positions]
            result["length"] = abs(max(xs) - min(xs))
            result["width"] = abs(max(ys) - min(ys))

        return result

    def _calculate_rotor_spread(self, joints: List[Dict]) -> float:
        """Calculate drone footprint from rotor positions (v3.4)."""
        rotor_positions = []
        for joint in joints:
            joint_name = joint.get("name", "").lower()
            if "rotor" in joint_name or "prop" in joint_name or "motor" in joint_name:
                origin = joint.get("origin", {})
                xyz = origin.get("xyz", [0, 0, 0])
                rotor_positions.append(xyz)

        if len(rotor_positions) >= 2:
            # Find max distance from center
            max_dist = 0
            for pos in rotor_positions:
                dist = math.sqrt(pos[0] ** 2 + pos[1] ** 2)
                max_dist = max(max_dist, dist)
            return max_dist

        return 0.3  # Default

    def _extract_collision_shapes(self, hierarchy_data: Optional[Dict]) -> List[Dict]:
        """
        Extract collision shapes for all links.

        Returns a simplified list of collision primitives.
        """
        if not hierarchy_data:
            return []

        nodes = hierarchy_data.get("nodes", {})
        shapes = []

        for node_name, node_data in nodes.items():
            if node_data.get("type") != "link":
                continue

            props = node_data.get("properties", {})

            # Use mass to estimate size if no explicit geometry
            mass = props.get("mass", 0)
            if mass > 0:
                # Rough sphere approximation
                estimated_radius = 0.05 + (mass / 10) * 0.1  # scale by mass
                shapes.append(
                    {
                        "link_name": node_name,
                        "shape_type": "sphere",
                        "dimensions": {"radius": min(0.3, estimated_radius)},
                    }
                )
            else:
                # Default small sphere for links without mass
                shapes.append(
                    {
                        "link_name": node_name,
                        "shape_type": "sphere",
                        "dimensions": {"radius": 0.05},
                    }
                )

        return shapes

    def _detect_capabilities(self, hierarchy_data: Optional[Dict], robot_type: str) -> Dict:
        """
        Detect robot capabilities from structure.

        Returns:
            Dictionary with capability flags
        """
        if not hierarchy_data:
            return {
                "is_mobile": False,
                "max_speed_mps": 0.0,
                "has_gripper": False,
                "max_payload_kg": 0.0,
                "reach_m": 0.0,
                "workspace_type": "unknown",
            }

        joints = hierarchy_data.get("joints", [])
        nodes = hierarchy_data.get("nodes", {})

        # Is mobile?
        is_mobile = robot_type == "MobileRobot"

        # Max speed from wheel joints
        max_speed = 0.0
        if is_mobile:
            for joint in joints:
                limits = joint.get("limits", {})
                if limits:
                    velocity = limits.get("velocity", 0)
                    # Wheel velocity to linear speed: v = omega * r
                    # Assume typical wheel radius of 0.1m
                    wheel_radius = 0.1
                    linear_speed = velocity * wheel_radius
                    max_speed = max(max_speed, linear_speed)
            if max_speed == 0:
                max_speed = 1.0  # Default mobile robot speed

        # Has gripper?
        has_gripper = False
        for node_name in nodes.keys():
            if any(g in node_name.lower() for g in ["gripper", "finger", "hand", "grasp", "tool"]):
                has_gripper = True
                break
        for joint in joints:
            if any(
                g in joint.get("name", "").lower() for g in ["gripper", "finger", "hand", "grasp"]
            ):
                has_gripper = True
                break

        # Calculate reach
        reach = self._calculate_reach(joints)

        # v3.4: Improved payload estimation using physics-based calculation
        max_payload = self._estimate_payload_capacity(joints, nodes, reach)

        # Workspace type
        if is_mobile:
            workspace_type = "mobile"
        elif robot_type == "IndustrialArm":
            workspace_type = "fixed"
        elif robot_type == "Humanoid":
            workspace_type = "bipedal"
        elif robot_type == "Quadruped":
            workspace_type = "quadruped"
        else:
            workspace_type = "unknown"

        return {
            "is_mobile": is_mobile,
            "max_speed_mps": round(max_speed, 2),
            "has_gripper": has_gripper,
            "max_payload_kg": round(max_payload, 2),
            "reach_m": round(reach, 3),
            "workspace_type": workspace_type,
            "dof": len(
                [j for j in joints if j.get("type") in ("revolute", "prismatic", "continuous")]
            ),
        }

    def _estimate_payload_capacity(self, joints: List[Dict], nodes: Dict, reach: float) -> float:
        """
        Estimate payload capacity using physics-based calculation (v3.4).

        Uses multiple methods:
        1. Joint torque at full extension: tau = m * g * L (most accurate)
        2. Base joint as limiting factor (realistic for arms)
        3. Link mass distribution analysis

        Args:
            joints: List of joint definitions with limits
            nodes: Node properties with mass/inertia
            reach: Total kinematic reach

        Returns:
            Estimated payload capacity in kg
        """
        if reach <= 0:
            return 0.0

        g = 9.81  # gravity
        payloads = []

        # Method 1: Use minimum joint effort as limiting factor
        # (the weakest joint limits the payload)
        joint_payloads = []
        for joint in joints:
            joint_type = joint.get("type", "fixed").lower()
            if joint_type not in ("revolute", "prismatic"):
                continue

            limits = joint.get("limits", {})
            effort = limits.get("effort", 0) if limits else 0

            if effort > 0:
                origin = joint.get("origin", {})
                xyz = origin.get("xyz", [0, 0, 0])
                # Distance from this joint to end effector (rough estimate)
                joint_dist = math.sqrt(xyz[0] ** 2 + xyz[1] ** 2 + xyz[2] ** 2)

                # For revolute: tau = F * r = m * g * r
                # m = tau / (g * r)
                if joint_dist > 0.01:  # Avoid division by tiny numbers
                    estimated_payload = effort / (g * joint_dist)
                    joint_payloads.append(estimated_payload)

        if joint_payloads:
            # The minimum determines the actual capacity
            payloads.append(min(joint_payloads))

        # Method 2: Use total effort / (g * reach)
        total_effort = sum(
            (j.get("limits") or {}).get("effort", 0)
            for j in joints
            if j.get("type") in ("revolute", "prismatic")
        )
        if total_effort > 0 and reach > 0:
            # Divide by number of joints to avoid overestimation
            num_joints = len([j for j in joints if j.get("type") in ("revolute", "prismatic")])
            avg_effort = total_effort / max(num_joints, 1)
            payloads.append(avg_effort / (g * reach))

        # Method 3: Estimate from link masses (end effector should be ~10-20% of payload)
        link_masses = []
        for node_name, node_data in nodes.items():
            if node_data.get("type") == "link":
                props = node_data.get("properties", {})
                mass = props.get("mass", 0)
                if mass > 0:
                    link_masses.append(mass)

        if link_masses:
            # Lightest links are usually near end effector
            # Payload is typically 2-5x the end effector mass
            min_link_mass = min(link_masses)
            payloads.append(min_link_mass * 3)  # Conservative estimate

        # Return the most conservative estimate
        if payloads:
            return max(0.1, min(payloads))  # At least 100g, use minimum estimate

        return 0.0

    def _calculate_reach(self, joints: List[Dict]) -> float:
        """
        Calculate maximum reach from joint origins.

        Sums the distances of all joint origins in the kinematic chain.
        """
        total_reach = 0.0
        for joint in joints:
            origin = joint.get("origin", {})
            xyz = origin.get("xyz", [0, 0, 0])
            distance = math.sqrt(xyz[0] ** 2 + xyz[1] ** 2 + xyz[2] ** 2)
            total_reach += distance
        return total_reach

    def _calculate_collision_margins(
        self, bounding_radius: float, footprint: Dict, robot_type: str
    ) -> Dict:
        """
        Calculate inter-robot collision margins (v3.4).

        Precomputes minimum safe distances for robot-robot interactions.
        COMC uses these for path planning and coordination.

        Returns:
            Dictionary with margin values for different coordination scenarios
        """
        # Base margin is the bounding radius + safety buffer
        base_margin = bounding_radius * 1.1  # 10% safety buffer

        # Get footprint dimensions
        if footprint.get("type") == "rectangle":
            max_footprint_dim = max(footprint.get("width", 0), footprint.get("length", 0))
        elif footprint.get("type") == "circle":
            max_footprint_dim = footprint.get("radius", 0.3) * 2
        else:
            max_footprint_dim = bounding_radius

        # Calculate different margin types
        margins = {
            # Static margin: minimum distance when both robots are stationary
            "static_margin": round(base_margin, 3),
            # Dynamic margin: safe distance when robots are moving
            # Larger to account for stopping distance and uncertainty
            "dynamic_margin": round(base_margin * 1.5, 3),
            # Footprint margin: 2D ground-plane margin for mobile robots
            "footprint_margin": round(max_footprint_dim * 0.6, 3),
            # Workspace margin: for arm robots, minimum distance between workspaces
            "workspace_margin": (
                round(bounding_radius * 0.5, 3) if robot_type == "IndustrialArm" else 0.0
            ),
            # Passing margin: minimum clearance for robots to pass each other
            "passing_margin": round(max(base_margin, max_footprint_dim) * 1.2, 3),
        }

        # Robot-type specific adjustments
        if robot_type == "Drone":
            # Drones need more vertical clearance
            margins["vertical_margin"] = round(bounding_radius * 2.0, 3)
            margins["dynamic_margin"] = round(base_margin * 2.5, 3)  # Higher speed

        elif robot_type == "Humanoid":
            # Humanoids have unpredictable limb movements
            margins["dynamic_margin"] = round(base_margin * 2.0, 3)
            margins["arm_reach_margin"] = round(bounding_radius * 0.8, 3)

        elif robot_type == "Quadruped":
            # Quadrupeds have wider stance during movement
            margins["gait_margin"] = round(max_footprint_dim * 1.3, 3)

        # Precomputed margins for common robot pairings
        margins["pairing_recommendations"] = {
            "same_type": round(margins["dynamic_margin"] * 2, 3),
            "with_mobile_robot": round(margins["dynamic_margin"] + 0.5, 3),
            "with_arm": round(margins["workspace_margin"] + bounding_radius, 3),
            "with_human": round(margins["dynamic_margin"] * 2.5, 3),  # Extra safety for humans
        }

        return margins

    def _calculate_safety_zones(
        self, hierarchy_data: Optional[Dict], bounding_radius: float
    ) -> Dict:
        """
        Calculate safety zones for COMC proximity monitoring.

        Uses safety_controller data from URDF if available,
        otherwise calculates from bounding radius.

        Returns:
            Dictionary with warning, caution, and critical distances
        """
        # Default zones based on bounding radius
        default_zones = {
            "warning_distance": bounding_radius * 3.0,  # 3x bounding radius
            "caution_distance": bounding_radius * 2.0,  # 2x bounding radius
            "critical_distance": bounding_radius * 1.5,  # 1.5x bounding radius
        }

        if not hierarchy_data:
            return default_zones

        # Check for URDF safety_controller data
        safety_controllers = hierarchy_data.get("safety_controllers", {})
        global_safety = hierarchy_data.get("global_safety_zone", {})

        if global_safety and global_safety.get("from_urdf"):
            # Use URDF safety data to influence zones
            k_position = global_safety.get("k_position", 0)
            if k_position > 0:
                # Higher k_position means tighter control, reduce zones
                zone_scale = max(0.5, 1.0 - k_position / 100)
                return {
                    "warning_distance": bounding_radius * 3.0 * zone_scale,
                    "caution_distance": bounding_radius * 2.0 * zone_scale,
                    "critical_distance": bounding_radius * 1.5 * zone_scale,
                    "from_urdf_safety": True,
                }

        return default_zones

    def _build_kinematic_chain_summary(self, hierarchy_data: Optional[Dict]) -> Dict:
        """
        Build kinematic chain summary for COMC.

        Provides simplified chain info for coordination.
        """
        if not hierarchy_data:
            return {
                "base_link": "base_link",
                "end_effector_link": None,
                "dof": 0,
                "links": [],
                "joints": [],
            }

        root_nodes = hierarchy_data.get("root_nodes", [])
        joints = hierarchy_data.get("joints", [])
        nodes = hierarchy_data.get("nodes", {})

        # Find base and end effector
        base_link = root_nodes[0] if root_nodes else "base_link"

        # End effector is typically the last link in the chain
        end_effector = None
        for node_name, node_data in nodes.items():
            if node_data.get("type") == "link":
                children = node_data.get("children", [])
                if not children:  # Leaf link
                    # Prefer links with gripper/hand/tool in name
                    if any(
                        g in node_name.lower()
                        for g in ["gripper", "hand", "tool", "end", "effector"]
                    ):
                        end_effector = node_name
                        break
                    elif end_effector is None:
                        end_effector = node_name

        # Count DOF
        dof = sum(1 for j in joints if j.get("type") in ("revolute", "prismatic", "continuous"))

        # Extract link names
        links = [
            {"name": n, "ue5_actor_name": f"BP_{n}"}
            for n, d in nodes.items()
            if d.get("type") == "link"
        ]

        # Extract joint summary
        joint_summary = []
        for j in joints:
            joint_summary.append(
                {
                    "name": j.get("name"),
                    "joint_type": j.get("type"),
                    "limits": j.get("limits"),
                }
            )

        return {
            "base_link": base_link,
            "end_effector_link": end_effector,
            "dof": dof,
            "links": links,
            "joints": joint_summary,
        }

    # ==================== END COMC EXPORT ====================
