#!/usr/bin/env python3
"""
Pipeline Validator - Deep inspection of the FTI physics pipeline

This script traces the complete data flow from URDF to UE5-ready USD,
checking each stage for correctness, type consistency, and edge cases.

Run from FTI Linux side:
    python3 pipeline_validator.py /path/to/test.urdf

Author: ROA Team
Date: January 2026
"""

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add the converters path
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))
sys.path.insert(0, str(script_dir / "Converters"))

# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATION RESULT TRACKING
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ValidationResult:
    stage: str
    passed: bool
    message: str
    details: Dict[str, Any] = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


class PipelineValidator:
    def __init__(self, urdf_path: str):
        self.urdf_path = urdf_path
        self.results: List[ValidationResult] = []
        self.stage_data: Dict[str, Any] = {}

    def log_result(self, stage: str, passed: bool, message: str, details: Dict = None):
        result = ValidationResult(stage, passed, message, details or {})
        self.results.append(result)
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} [{stage}] {message}")
        if details:
            for k, v in details.items():
                print(f"       {k}: {v}")
        return passed

    def print_summary(self):
        print("\n" + "═" * 70)
        print("PIPELINE VALIDATION SUMMARY")
        print("═" * 70)

        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)

        print(f"Total Checks: {len(self.results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")

        if failed > 0:
            print("\nFailed Checks:")
            for r in self.results:
                if not r.passed:
                    print(f"  ❌ [{r.stage}] {r.message}")

        print("═" * 70)
        return failed == 0

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 1: URDF PARSING
    # ═══════════════════════════════════════════════════════════════════════════

    def validate_stage1_urdf_parsing(self):
        """Validate URDF file parsing and data extraction"""
        print("\n" + "─" * 70)
        print("STAGE 1: URDF PARSING")
        print("─" * 70)

        import xml.etree.ElementTree as ET

        # Check 1.1: File exists and is readable
        if not os.path.exists(self.urdf_path):
            return self.log_result("1.1", False, f"URDF file not found: {self.urdf_path}")

        self.log_result("1.1", True, "URDF file exists")

        # Check 1.2: Valid XML
        try:
            tree = ET.parse(self.urdf_path)
            root = tree.getroot()
            self.log_result("1.2", True, "Valid XML format")
        except ET.ParseError as e:
            return self.log_result("1.2", False, f"XML parse error: {e}")

        # Check 1.3: Root is 'robot'
        if root.tag != "robot":
            return self.log_result("1.3", False, f"Root element is '{root.tag}', expected 'robot'")
        self.log_result("1.3", True, "Root element is 'robot'")

        # Check 1.4: Has robot name
        robot_name = root.get("name")
        if not robot_name:
            self.log_result("1.4", False, "Robot has no name attribute")
        else:
            self.log_result("1.4", True, f"Robot name: {robot_name}")

        # Check 1.5: Extract links
        links = root.findall(".//link")
        link_names = [l.get("name") for l in links]
        self.log_result(
            "1.5",
            len(links) > 0,
            f"Found {len(links)} links",
            {"links": link_names[:5] if len(link_names) > 5 else link_names},
        )

        # Check 1.6: Extract joints
        joints = root.findall(".//joint")
        joint_data = []
        for j in joints:
            jd = {
                "name": j.get("name"),
                "type": j.get("type"),
                "parent": (j.find("parent").get("link") if j.find("parent") is not None else None),
                "child": (j.find("child").get("link") if j.find("child") is not None else None),
            }

            # Extract axis
            axis_elem = j.find("axis")
            if axis_elem is not None:
                xyz = axis_elem.get("xyz", "1 0 0")
                jd["axis"] = [float(x) for x in xyz.split()]
            else:
                jd["axis"] = [1, 0, 0]

            # Extract limits
            limit_elem = j.find("limit")
            if limit_elem is not None:
                jd["limits"] = {
                    "lower": float(limit_elem.get("lower", 0)),
                    "upper": float(limit_elem.get("upper", 0)),
                    "effort": float(limit_elem.get("effort", 0)),
                    "velocity": float(limit_elem.get("velocity", 0)),
                }

            joint_data.append(jd)

        self.log_result(
            "1.6",
            len(joints) > 0,
            f"Found {len(joints)} joints",
            {"types": list(set(j["type"] for j in joint_data))},
        )

        # Store for next stages
        self.stage_data["urdf"] = {
            "robot_name": robot_name,
            "links": link_names,
            "joints": joint_data,
        }

        # Check 1.7: All joints have valid parent/child
        orphan_joints = [
            j for j in joint_data if j["parent"] not in link_names or j["child"] not in link_names
        ]
        self.log_result(
            "1.7",
            len(orphan_joints) == 0,
            f"Joint parent/child validation: {len(joint_data) - len(orphan_joints)}/{len(joint_data)} valid",
            {"orphans": [j["name"] for j in orphan_joints]} if orphan_joints else {},
        )

        # Check 1.8: Joint types are supported
        supported_types = {
            "revolute",
            "continuous",
            "prismatic",
            "fixed",
            "floating",
            "planar",
        }
        unsupported = [j for j in joint_data if j["type"] not in supported_types]
        self.log_result(
            "1.8",
            len(unsupported) == 0,
            f"All joint types supported: {len(joint_data) - len(unsupported)}/{len(joint_data)}",
            (
                {"unsupported": [f"{j['name']}:{j['type']}" for j in unsupported]}
                if unsupported
                else {}
            ),
        )

        return True

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 2: URDF TO USD CONVERSION
    # ═══════════════════════════════════════════════════════════════════════════

    def validate_stage2_conversion(self):
        """Validate the URDF to USD conversion process"""
        print("\n" + "─" * 70)
        print("STAGE 2: URDF → USD CONVERSION")
        print("─" * 70)

        from Converters.urdf_converter import URDFConverter

        # Check 2.1: Converter instantiation
        try:
            config = {
                "include_physics": True,
                "log_level": "INFO",
            }
            converter = URDFConverter(config)
            self.log_result("2.1", True, "URDFConverter instantiated")
        except Exception as e:
            return self.log_result("2.1", False, f"Converter init failed: {e}")

        # Check 2.2: Physics config initialized
        has_physics_config = hasattr(converter, "physics_config") and converter.physics_config
        self.log_result(
            "2.2",
            has_physics_config,
            "Physics config initialized",
            {"config": converter.physics_config} if has_physics_config else {},
        )

        # Check 2.3: Conversion execution
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_robot.usd")
            robot_name = self.stage_data.get("urdf", {}).get("robot_name", "test_robot")

            try:
                result = converter.convert(self.urdf_path, output_path, robot_name)
                self.log_result(
                    "2.3",
                    result.success,
                    f"Conversion {'succeeded' if result.success else 'failed'}",
                    {"error": result.error_message} if not result.success else {},
                )

                if not result.success:
                    return False

            except Exception as e:
                import traceback

                return self.log_result(
                    "2.3", False, f"Conversion exception: {e}\n{traceback.format_exc()}"
                )

            # Check 2.4: Output file exists
            assembled_path = result.assembled_file
            if not assembled_path or not os.path.exists(assembled_path):
                return self.log_result("2.4", False, f"Output USD not created: {assembled_path}")
            self.log_result("2.4", True, f"USD file created: {os.path.basename(assembled_path)}")

            # Store for next stage
            self.stage_data["usd_path"] = assembled_path

            # Check 2.5: Validate USD with OpenUSD (Stage 3)
            self.validate_stage3_usd_physics(assembled_path)

            # Stage 4: Validate UE5 parser can read it correctly
            self.validate_stage4_ue5_parser(assembled_path)

        return True

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 3: USD PHYSICS SCHEMA VALIDATION
    # ═══════════════════════════════════════════════════════════════════════════

    def validate_stage3_usd_physics(self, usd_path: str):
        """Validate USD Physics schema in generated file"""
        print("\n" + "─" * 70)
        print("STAGE 3: USD PHYSICS SCHEMA VALIDATION")
        print("─" * 70)

        try:
            from pxr import Usd, UsdGeom, UsdPhysics
        except ImportError:
            return self.log_result("3.0", False, "OpenUSD (pxr) not available")

        # Check 3.1: USD stage opens
        try:
            stage = Usd.Stage.Open(usd_path)
            self.log_result("3.1", stage is not None, "USD stage opened")
        except Exception as e:
            return self.log_result("3.1", False, f"Failed to open USD: {e}")

        # Check 3.2: PhysicsScene exists
        physics_scenes = []
        for prim in stage.Traverse():
            if prim.IsA(UsdPhysics.Scene):
                physics_scenes.append(prim)

        self.log_result(
            "3.2",
            len(physics_scenes) > 0,
            f"Found {len(physics_scenes)} PhysicsScene(s)",
            {"paths": [str(p.GetPath()) for p in physics_scenes]},
        )

        # Check 3.3: PhysicsScene has gravity
        if physics_scenes:
            scene = UsdPhysics.Scene(physics_scenes[0])
            gravity_dir = scene.GetGravityDirectionAttr().Get()
            gravity_mag = scene.GetGravityMagnitudeAttr().Get()
            self.log_result(
                "3.3",
                gravity_mag is not None and gravity_mag > 0,
                f"Gravity configured",
                {
                    "direction": list(gravity_dir) if gravity_dir else None,
                    "magnitude": gravity_mag,
                },
            )

        # Check 3.4: ArticulationRootAPI on robot
        articulation_roots = []
        for prim in stage.Traverse():
            if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
                articulation_roots.append(prim)

        self.log_result(
            "3.4",
            len(articulation_roots) > 0,
            f"Found {len(articulation_roots)} ArticulationRootAPI",
            {"paths": [str(p.GetPath()) for p in articulation_roots]},
        )

        # Check 3.5: Physics joints
        revolute_joints = []
        prismatic_joints = []
        fixed_joints = []

        for prim in stage.Traverse():
            if prim.IsA(UsdPhysics.RevoluteJoint):
                revolute_joints.append(prim)
            elif prim.IsA(UsdPhysics.PrismaticJoint):
                prismatic_joints.append(prim)
            elif prim.IsA(UsdPhysics.FixedJoint):
                fixed_joints.append(prim)

        total_joints = len(revolute_joints) + len(prismatic_joints) + len(fixed_joints)
        urdf_joints = self.stage_data.get("urdf", {}).get("joints", [])

        self.log_result(
            "3.5",
            total_joints > 0,
            f"Physics joints: {total_joints} (revolute={len(revolute_joints)}, prismatic={len(prismatic_joints)}, fixed={len(fixed_joints)})",
            {"expected_from_urdf": len(urdf_joints)},
        )

        # Check 3.6: Each physics joint has body references
        joints_with_bodies = 0
        joints_missing_bodies = []

        all_physics_joints = revolute_joints + prismatic_joints + fixed_joints
        for jprim in all_physics_joints:
            # Try to get body relationships
            has_body0 = False
            has_body1 = False

            if jprim.IsA(UsdPhysics.RevoluteJoint):
                joint = UsdPhysics.RevoluteJoint(jprim)
            elif jprim.IsA(UsdPhysics.PrismaticJoint):
                joint = UsdPhysics.PrismaticJoint(jprim)
            else:
                joint = UsdPhysics.FixedJoint(jprim)

            body0 = joint.GetBody0Rel().GetTargets()
            body1 = joint.GetBody1Rel().GetTargets()

            if body0 and body1:
                joints_with_bodies += 1
            else:
                joints_missing_bodies.append(jprim.GetName())

        self.log_result(
            "3.6",
            joints_with_bodies == len(all_physics_joints),
            f"Joints with body refs: {joints_with_bodies}/{len(all_physics_joints)}",
            {"missing": joints_missing_bodies} if joints_missing_bodies else {},
        )

        # Check 3.7: DriveAPI on joints
        joints_with_drive = 0
        for jprim in revolute_joints + prismatic_joints:  # Fixed joints don't have drives
            # Check for DriveAPI
            has_drive = False
            for axis in ["X", "Y", "Z"]:
                if jprim.HasAPI(UsdPhysics.DriveAPI, f"rot{axis}") or jprim.HasAPI(
                    UsdPhysics.DriveAPI, f"trans{axis}"
                ):
                    has_drive = True
                    break
            if has_drive:
                joints_with_drive += 1

        moveable_joints = len(revolute_joints) + len(prismatic_joints)
        self.log_result(
            "3.7",
            joints_with_drive == moveable_joints,
            f"DriveAPI on joints: {joints_with_drive}/{moveable_joints}",
        )

        # Check 3.8: Limits on revolute joints
        joints_with_limits = 0
        for jprim in revolute_joints:
            joint = UsdPhysics.RevoluteJoint(jprim)
            lower = joint.GetLowerLimitAttr().Get()
            upper = joint.GetUpperLimitAttr().Get()
            if lower is not None and upper is not None:
                joints_with_limits += 1

        self.log_result(
            "3.8",
            True,  # Just informational
            f"Revolute joints with limits: {joints_with_limits}/{len(revolute_joints)}",
        )

        # Check 3.9: Validate joint axis
        axis_issues = []
        for jprim in revolute_joints + prismatic_joints:
            if jprim.IsA(UsdPhysics.RevoluteJoint):
                joint = UsdPhysics.RevoluteJoint(jprim)
            else:
                joint = UsdPhysics.PrismaticJoint(jprim)

            axis = joint.GetAxisAttr().Get()
            if axis not in ["X", "Y", "Z"]:
                axis_issues.append(f"{jprim.GetName()}: axis={axis}")

        self.log_result(
            "3.9",
            len(axis_issues) == 0,
            f"Joint axes valid: {moveable_joints - len(axis_issues)}/{moveable_joints}",
            {"issues": axis_issues} if axis_issues else {},
        )

        # Store parsed data for UE5 side validation
        self.stage_data["usd_physics"] = {
            "physics_scenes": len(physics_scenes),
            "articulation_roots": len(articulation_roots),
            "revolute_joints": len(revolute_joints),
            "prismatic_joints": len(prismatic_joints),
            "fixed_joints": len(fixed_joints),
            "joints_with_drive": joints_with_drive,
        }

        return True

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 4: UE5 PHYSICS PARSER VALIDATION
    # ═══════════════════════════════════════════════════════════════════════════

    def validate_stage4_ue5_parser(self, usd_path: str = None):
        """Validate the UE5 physics parser can read the USD correctly"""
        print("\n" + "─" * 70)
        print("STAGE 4: UE5 PHYSICS PARSER VALIDATION")
        print("─" * 70)

        # We need to test the physics_constraint_setup.py parser
        # Add UE5 Python path
        ue5_python_path = "/home/D/ROA/UE5_Projects/ROA_V1/Content/Python/ROA"
        if os.path.exists(ue5_python_path):
            sys.path.insert(0, ue5_python_path)
        else:
            return self.log_result("4.0", False, f"UE5 Python path not found: {ue5_python_path}")

        # Check 4.1: Import physics module
        try:
            import physics_constraint_setup as physics

            self.log_result("4.1", True, "physics_constraint_setup imported")
        except ImportError as e:
            return self.log_result("4.1", False, f"Import failed: {e}")

        # Use stored USD path if available
        if usd_path is None:
            usd_path = self.stage_data.get("usd_path")

        if not usd_path or not os.path.exists(usd_path):
            return self.log_result("4.2", False, f"USD file not available for testing")

        # Check 4.2: Parse PhysicsScene
        try:
            scene_data = physics.parse_usd_physics_scene(usd_path)
            self.log_result(
                "4.2",
                scene_data is not None,
                f"PhysicsScene parsed",
                {"gravity_mag": scene_data.gravity_magnitude if scene_data else None},
            )
        except Exception as e:
            self.log_result("4.2", False, f"PhysicsScene parse error: {e}")

        # Check 4.3: Parse physics joints
        try:
            joints = physics.parse_usd_physics_joints(usd_path)
            self.log_result("4.3", len(joints) > 0, f"Parsed {len(joints)} physics joints")
        except Exception as e:
            return self.log_result("4.3", False, f"Joint parse error: {e}")

        # Check 4.4: Validate joint data completeness
        complete_joints = 0
        incomplete_joints = []
        for j in joints:
            issues = []
            if not j.body0_path:
                issues.append("missing body0")
            if not j.body1_path:
                issues.append("missing body1")
            if j.joint_type not in [
                physics.JointType.REVOLUTE,
                physics.JointType.PRISMATIC,
                physics.JointType.FIXED,
                physics.JointType.CONTINUOUS,
            ]:
                issues.append(f"unknown type: {j.joint_type}")

            if issues:
                incomplete_joints.append(f"{j.name}: {', '.join(issues)}")
            else:
                complete_joints += 1

        self.log_result(
            "4.4",
            complete_joints == len(joints),
            f"Complete joint data: {complete_joints}/{len(joints)}",
            {"incomplete": incomplete_joints} if incomplete_joints else {},
        )

        # Check 4.5: Unit conversions
        # Verify that linear limits are in cm (not m)
        # Verify that angular limits are in degrees (not radians)
        unit_issues = []
        for j in joints:
            if j.joint_type == physics.JointType.PRISMATIC and j.limits.has_limits:
                # Prismatic limits should be in cm (typically 0-100+ range)
                limit_range = abs(j.limits.upper - j.limits.lower)
                if limit_range < 0.1:  # Suspiciously small, probably still in meters
                    unit_issues.append(
                        f"{j.name}: prismatic limit range {limit_range} seems too small (meters?)"
                    )

            if j.joint_type == physics.JointType.REVOLUTE and j.limits.has_limits:
                # Revolute limits should be in degrees (typically -180 to 180)
                if abs(j.limits.upper) < 10 and abs(j.limits.lower) < 10:
                    # Could be radians if limits are like -3.14 to 3.14
                    unit_issues.append(
                        f"{j.name}: revolute limits [{j.limits.lower:.2f}, {j.limits.upper:.2f}] might be radians"
                    )

        self.log_result(
            "4.5",
            len(unit_issues) == 0,
            f"Unit conversion check: {len(joints) - len(unit_issues)}/{len(joints)} OK",
            {"issues": unit_issues} if unit_issues else {},
        )

        # Check 4.6: DriveParams presence
        joints_with_drive = [j for j in joints if j.drive.stiffness > 0 or j.drive.damping > 0]
        self.log_result(
            "4.6",
            True,
            f"Joints with drive params: {len(joints_with_drive)}/{len(joints)}",
        )

        # Check 4.7: Parse FilteredPairs
        try:
            filtered = physics.parse_usd_filtered_pairs(usd_path)
            self.log_result("4.7", True, f"FilteredPairs parsed: {len(filtered.pairs)} pairs")
        except Exception as e:
            self.log_result("4.7", False, f"FilteredPairs parse error: {e}")

        # Store for comparison
        self.stage_data["ue5_parsed"] = {
            "joint_count": len(joints),
            "joints_with_drive": len(joints_with_drive),
            "joint_names": [j.name for j in joints],
        }

        return True

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 5: CROSS-STAGE CONSISTENCY
    # ═══════════════════════════════════════════════════════════════════════════

    def validate_stage5_consistency(self):
        """Validate data consistency across all stages"""
        print("\n" + "─" * 70)
        print("STAGE 5: CROSS-STAGE CONSISTENCY")
        print("─" * 70)

        urdf_data = self.stage_data.get("urdf", {})
        usd_physics = self.stage_data.get("usd_physics", {})
        ue5_parsed = self.stage_data.get("ue5_parsed", {})

        # Check 5.1: Joint count matches through pipeline
        urdf_joint_count = len(urdf_data.get("joints", []))
        usd_joint_count = (
            usd_physics.get("revolute_joints", 0)
            + usd_physics.get("prismatic_joints", 0)
            + usd_physics.get("fixed_joints", 0)
        )
        ue5_joint_count = ue5_parsed.get("joint_count", 0)

        counts_match = urdf_joint_count == usd_joint_count == ue5_joint_count
        self.log_result(
            "5.1",
            counts_match,
            f"Joint count consistency: URDF={urdf_joint_count}, USD={usd_joint_count}, UE5={ue5_joint_count}",
        )

        # Check 5.2: Joint types mapped correctly
        urdf_joints = urdf_data.get("joints", [])
        revolute_in_urdf = len([j for j in urdf_joints if j["type"] in ("revolute", "continuous")])
        prismatic_in_urdf = len([j for j in urdf_joints if j["type"] == "prismatic"])
        fixed_in_urdf = len([j for j in urdf_joints if j["type"] == "fixed"])

        type_mapping_ok = (
            revolute_in_urdf == usd_physics.get("revolute_joints", 0)
            and prismatic_in_urdf == usd_physics.get("prismatic_joints", 0)
            and fixed_in_urdf == usd_physics.get("fixed_joints", 0)
        )

        self.log_result(
            "5.2",
            type_mapping_ok,
            f"Joint type mapping",
            {
                "URDF": f"rev={revolute_in_urdf}, pris={prismatic_in_urdf}, fix={fixed_in_urdf}",
                "USD": f"rev={usd_physics.get('revolute_joints', 0)}, pris={usd_physics.get('prismatic_joints', 0)}, fix={usd_physics.get('fixed_joints', 0)}",
            },
        )

        # Check 5.3: Joint names preserved
        urdf_joint_names = set(j["name"] for j in urdf_joints)
        ue5_joint_names = set(ue5_parsed.get("joint_names", []))

        # Names might be sanitized (underscores replacing special chars)
        # Just check count for now
        self.log_result(
            "5.3",
            len(urdf_joint_names) == len(ue5_joint_names),
            f"Joint name count: URDF={len(urdf_joint_names)}, UE5={len(ue5_joint_names)}",
        )

        return True

    # ═══════════════════════════════════════════════════════════════════════════
    # MAIN VALIDATION
    # ═══════════════════════════════════════════════════════════════════════════

    def run_full_validation(self):
        """Run the complete pipeline validation"""
        print("╔" + "═" * 68 + "╗")
        print("║" + "  FTI PIPELINE DEEP VALIDATION".center(68) + "║")
        print("╚" + "═" * 68 + "╝")
        print(f"\nInput: {self.urdf_path}")

        # Run all stages
        # Stage 1: URDF parsing validation
        self.validate_stage1_urdf_parsing()
        # Stage 2: URDF→USD conversion (also calls Stage 3 and 4 internally)
        self.validate_stage2_conversion()
        # Stage 5: Cross-stage consistency checks
        self.validate_stage5_consistency()

        return self.print_summary()


def main():
    if len(sys.argv) < 2:
        print("Usage: python pipeline_validator.py <urdf_file>")
        print("\nExample URDFs to test with:")
        print("  - /home/myws/roa/roa_linux/test_assets/simple_arm.urdf")
        print("  - /home/myws/roa/roa_linux/test_assets/ur3.urdf")
        sys.exit(1)

    urdf_path = sys.argv[1]
    validator = PipelineValidator(urdf_path)
    success = validator.run_full_validation()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
