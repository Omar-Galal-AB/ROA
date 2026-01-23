#!/usr/bin/env python3
"""
Test script for FTI Converters
Tests that converters actually produce USD output files
"""

import os
import sys
import tempfile
from pathlib import Path

# Add the source directory to path
sys.path.insert(0, str(Path(__file__).parent / "src" / "python"))


def test_stl_converter():
    """Test STL to USD conversion with a simple STL file."""
    print("\n" + "=" * 60)
    print("TEST: STL Converter")
    print("=" * 60)

    from Converters.stl_converter import STLConverter

    # Create a simple ASCII STL file
    stl_content = """solid test
  facet normal 0 0 1
    outer loop
      vertex 0 0 0
      vertex 1 0 0
      vertex 0.5 1 0
    endloop
  endfacet
  facet normal 0 0 -1
    outer loop
      vertex 0 0 0.1
      vertex 0.5 1 0.1
      vertex 1 0 0.1
    endloop
  endfacet
endsolid test"""

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / "test.stl"
        output_path = Path(tmpdir) / "test.usda"

        # Write test STL
        input_path.write_text(stl_content)
        print(f"  Created test STL: {input_path}")

        # Convert
        converter = STLConverter()
        result = converter.convert(str(input_path), str(output_path), "test_mesh")

        # Check result
        if result.success:
            if output_path.exists():
                file_size = output_path.stat().st_size
                print(f"  ✅ SUCCESS: Created {output_path.name} ({file_size} bytes)")

                # Print first 20 lines of USD file
                content = output_path.read_text()
                lines = content.split("\n")[:20]
                print("  USD content (first 20 lines):")
                for line in lines:
                    print(f"    {line}")
                return True
            else:
                print(f"  ❌ FAILED: Output file not created")
                return False
        else:
            print(f"  ❌ FAILED: {result.error_message}")
            return False


def test_obj_converter():
    """Test OBJ to USD conversion with a simple OBJ file."""
    print("\n" + "=" * 60)
    print("TEST: OBJ Converter")
    print("=" * 60)

    from Converters.obj_converter import OBJConverter

    # Create a simple OBJ file (a triangle)
    obj_content = """# Simple triangle
v 0 0 0
v 1 0 0
v 0.5 1 0
vn 0 0 1
f 1//1 2//1 3//1
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / "test.obj"
        output_path = Path(tmpdir) / "test.usda"

        # Write test OBJ
        input_path.write_text(obj_content)
        print(f"  Created test OBJ: {input_path}")

        # Convert
        converter = OBJConverter()
        result = converter.convert(str(input_path), str(output_path), "test_obj")

        # Check result
        if result.success:
            if output_path.exists():
                file_size = output_path.stat().st_size
                print(f"  ✅ SUCCESS: Created {output_path.name} ({file_size} bytes)")
                print(f"  Parts: {result.parts}")
                print(f"  Materials: {result.materials}")
                return True
            else:
                print(f"  ❌ FAILED: Output file not created")
                return False
        else:
            print(f"  ❌ FAILED: {result.error_message}")
            return False


def test_urdf_converter():
    """Test URDF to USD conversion with a simple URDF file."""
    print("\n" + "=" * 60)
    print("TEST: URDF Converter")
    print("=" * 60)

    from Converters.urdf_converter import URDFConverter

    # Create a simple URDF file
    urdf_content = """<?xml version="1.0"?>
<robot name="test_robot">
  <material name="blue">
    <color rgba="0 0 0.8 1"/>
  </material>
  
  <link name="base_link">
    <visual>
      <geometry>
        <box size="0.5 0.5 0.1"/>
      </geometry>
      <material name="blue"/>
    </visual>
    <collision>
      <geometry>
        <box size="0.5 0.5 0.1"/>
      </geometry>
    </collision>
    <inertial>
      <mass value="1.0"/>
      <inertia ixx="0.01" ixy="0" ixz="0" iyy="0.01" iyz="0" izz="0.01"/>
    </inertial>
  </link>
  
  <link name="link1">
    <visual>
      <origin xyz="0 0 0.25" rpy="0 0 0"/>
      <geometry>
        <cylinder radius="0.05" length="0.5"/>
      </geometry>
    </visual>
    <inertial>
      <mass value="0.5"/>
      <inertia ixx="0.005" ixy="0" ixz="0" iyy="0.005" iyz="0" izz="0.002"/>
    </inertial>
  </link>
  
  <joint name="joint1" type="revolute">
    <parent link="base_link"/>
    <child link="link1"/>
    <origin xyz="0 0 0.05" rpy="0 0 0"/>
    <axis xyz="0 0 1"/>
    <limit lower="-1.57" upper="1.57" effort="10" velocity="1"/>
  </joint>
  
  <link name="link2">
    <visual>
      <origin xyz="0 0 0.15" rpy="0 0 0"/>
      <geometry>
        <sphere radius="0.08"/>
      </geometry>
    </visual>
  </link>
  
  <joint name="joint2" type="fixed">
    <parent link="link1"/>
    <child link="link2"/>
    <origin xyz="0 0 0.5" rpy="0 0 0"/>
  </joint>
</robot>
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / "test_robot.urdf"
        output_path = Path(tmpdir) / "test_robot.usda"

        # Write test URDF
        input_path.write_text(urdf_content)
        print(f"  Created test URDF: {input_path}")

        # Convert
        converter = URDFConverter()
        result = converter.convert(str(input_path), str(output_path), "test_robot")

        # Check result
        if result.success:
            if output_path.exists():
                file_size = output_path.stat().st_size
                print(f"  ✅ SUCCESS: Created {output_path.name} ({file_size} bytes)")
                print(f"  Parts (links): {result.parts}")
                print(f"  Materials: {result.materials}")
                if result.warnings:
                    print(f"  Warnings: {result.warnings}")

                # Print first 30 lines of USD file
                content = output_path.read_text()
                lines = content.split("\n")[:30]
                print("  USD content (first 30 lines):")
                for line in lines:
                    print(f"    {line}")
                return True
            else:
                print(f"  ❌ FAILED: Output file not created")
                return False
        else:
            print(f"  ❌ FAILED: {result.error_message}")
            return False


def main():
    print("=" * 60)
    print("FTI CONVERTER TEST SUITE")
    print("=" * 60)
    print("Testing that converters produce actual USD output files")

    results = {}

    # Run tests
    try:
        results["STL"] = test_stl_converter()
    except Exception as e:
        print(f"  ❌ EXCEPTION: {e}")
        import traceback

        traceback.print_exc()
        results["STL"] = False

    try:
        results["OBJ"] = test_obj_converter()
    except Exception as e:
        print(f"  ❌ EXCEPTION: {e}")
        import traceback

        traceback.print_exc()
        results["OBJ"] = False

    try:
        results["URDF"] = test_urdf_converter()
    except Exception as e:
        print(f"  ❌ EXCEPTION: {e}")
        import traceback

        traceback.print_exc()
        results["URDF"] = False

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {name} Converter: {status}")

    print(f"\n  Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n  🎉 ALL TESTS PASSED - Converters produce real USD output!")
        return 0
    else:
        print("\n  ⚠️  Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
