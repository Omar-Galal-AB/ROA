#!/usr/bin/env python3
"""
Test script to verify USD Physics output from urdf_converter.py v3.0
"""

import os
import sys

# Add the src/python directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src", "python"))

from Converters.urdf_converter import URDFConverter
from pxr import Usd, UsdGeom, UsdPhysics


def test_physics_output():
    """Test the URDF converter with physics enabled"""

    # Input/output paths
    urdf_path = os.path.join(
        os.path.dirname(__file__), "examples", "sample_robots", "simple_arm.urdf"
    )
    output_path = "/tmp/simple_arm_physics_test.usda"

    print(f"=" * 60)
    print(f"Testing USD Physics Output")
    print(f"=" * 60)
    print(f"Input URDF: {urdf_path}")
    print(f"Output USD: {output_path}")
    print()

    # Create converter with physics enabled
    config = {"include_physics": True, "scale": 100.0, "file_type": "usd"}  # cm

    converter = URDFConverter(config=config)

    # Convert
    print("Converting URDF to USD with physics...")
    result = converter.convert(urdf_path, output_path, "usda")

    # ConversionResult object - check success attribute
    if not result.success:
        print(f"❌ Conversion failed!")
        print(f"Errors: {result.errors}")
        return False

    print(f"✅ Conversion successful!")
    print()

    # Analyze the output
    print("=" * 60)
    print("Analyzing USD Physics Content")
    print("=" * 60)

    stage = Usd.Stage.Open(output_path)
    if not stage:
        print("❌ Failed to open output USD file")
        return False

    # Check for PhysicsScene
    print("\n📦 PhysicsScene:")
    physics_scene = stage.GetPrimAtPath("/PhysicsScene")
    if physics_scene:
        scene = UsdPhysics.Scene(physics_scene)
        grav_dir = scene.GetGravityDirectionAttr().Get()
        grav_mag = scene.GetGravityMagnitudeAttr().Get()
        print(f"   ✅ Found at /PhysicsScene")
        print(f"   Gravity direction: {grav_dir}")
        print(f"   Gravity magnitude: {grav_mag}")
    else:
        print("   ❌ Not found")

    # Check for ArticulationRootAPI
    print("\n🤖 ArticulationRootAPI:")
    robot_prim = stage.GetPrimAtPath("/simple_arm")
    if robot_prim:
        if robot_prim.HasAPI(UsdPhysics.ArticulationRootAPI):
            print(f"   ✅ Applied to /simple_arm")
        else:
            print(f"   ❌ Not found on /simple_arm")
    else:
        print(f"   ❌ Robot prim not found")

    # Check for Physics Joints
    print("\n🔗 Physics Joints:")
    joints_prim = stage.GetPrimAtPath("/simple_arm/Joints")
    if joints_prim:
        print(f"   ✅ Joints scope found at /simple_arm/Joints")
        for child in joints_prim.GetChildren():
            joint_path = str(child.GetPath())
            print(f"\n   Joint: {child.GetName()}")

            # Check joint type
            if child.IsA(UsdPhysics.RevoluteJoint):
                joint = UsdPhysics.RevoluteJoint(child)
                axis = joint.GetAxisAttr().Get()
                lower = joint.GetLowerLimitAttr().Get()
                upper = joint.GetUpperLimitAttr().Get()
                print(f"      Type: RevoluteJoint")
                print(f"      Axis: {axis}")
                print(f"      Limits: [{lower}°, {upper}°]")
            elif child.IsA(UsdPhysics.PrismaticJoint):
                joint = UsdPhysics.PrismaticJoint(child)
                axis = joint.GetAxisAttr().Get()
                lower = joint.GetLowerLimitAttr().Get()
                upper = joint.GetUpperLimitAttr().Get()
                print(f"      Type: PrismaticJoint")
                print(f"      Axis: {axis}")
                print(f"      Limits: [{lower}m, {upper}m]")
            elif child.IsA(UsdPhysics.FixedJoint):
                print(f"      Type: FixedJoint")

            # Check DriveAPI
            drive_apis = child.GetAppliedSchemas()
            drive_names = [s for s in drive_apis if "DriveAPI" in s]
            if drive_names:
                print(f"      DriveAPI: {drive_names}")
                # Try to read drive parameters
                for drive_name in drive_names:
                    # Extract instance name (e.g., "PhysicsDriveAPI:rotZ" -> "rotZ")
                    if ":" in drive_name:
                        instance = drive_name.split(":")[1]
                        drive_api = UsdPhysics.DriveAPI.Get(child, instance)
                        stiffness = drive_api.GetStiffnessAttr().Get()
                        damping = drive_api.GetDampingAttr().Get()
                        max_force = drive_api.GetMaxForceAttr().Get()
                        print(
                            f"         {instance}: stiffness={stiffness}, damping={damping}, maxForce={max_force}"
                        )

            # Check body relationships
            joint_base = UsdPhysics.Joint(child)
            body0 = joint_base.GetBody0Rel().GetTargets()
            body1 = joint_base.GetBody1Rel().GetTargets()
            print(f"      Body0 (parent): {body0}")
            print(f"      Body1 (child): {body1}")
    else:
        print(f"   ❌ Joints scope not found")

    # Check for RigidBodyAPI on links
    print("\n📐 RigidBodyAPI on Links:")
    for prim in Usd.PrimRange(stage.GetPseudoRoot()):
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            print(f"   ✅ {prim.GetPath()}")
            if prim.HasAPI(UsdPhysics.MassAPI):
                mass_api = UsdPhysics.MassAPI(prim)
                mass = mass_api.GetMassAttr().Get()
                print(f"      Mass: {mass}")

    # Check for FilteredPairsAPI
    print("\n🛡️ FilteredPairsAPI (self-collision filtering):")
    if robot_prim and robot_prim.HasAPI(UsdPhysics.FilteredPairsAPI):
        filtered_api = UsdPhysics.FilteredPairsAPI(robot_prim)
        pairs = filtered_api.GetFilteredPairsRel().GetTargets()
        print(f"   ✅ Applied to /simple_arm")
        print(f"   Filtered pairs: {pairs}")
    else:
        print(f"   ❌ Not found")

    # Print the USD file content for inspection
    print("\n" + "=" * 60)
    print("USD File Content (first 100 lines):")
    print("=" * 60)
    with open(output_path, "r") as f:
        lines = f.readlines()
        for i, line in enumerate(lines[:100]):
            print(f"{i+1:3d}: {line.rstrip()}")
        if len(lines) > 100:
            print(f"... ({len(lines) - 100} more lines)")

    print("\n" + "=" * 60)
    print("✅ Test complete!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = test_physics_output()
    sys.exit(0 if success else 1)
