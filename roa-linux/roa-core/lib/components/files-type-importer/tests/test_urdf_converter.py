"""
Unit tests for URDFConverter
"""

import os

# Add parent directory to path for imports
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python"))

from Converters.urdf_converter import URDFConverter


class TestURDFConverter:
    """Test suite for URDFConverter class."""

    @pytest.fixture
    def converter(self):
        """Create a URDFConverter instance for testing."""
        return URDFConverter()

    def test_initialization(self, converter):
        """Test URDFConverter initializes correctly."""
        assert converter is not None
        assert ".urdf" in converter.supported_extensions
        assert ".xacro" in converter.supported_extensions

    def test_get_supported_extensions(self, converter):
        """Test getting supported extensions."""
        extensions = converter.get_supported_extensions()
        assert ".urdf" in extensions
        assert ".xacro" in extensions

    def test_validate_input_valid_file(self, converter):
        """Test input validation with valid file."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name

        try:
            result = converter.validate_input(temp_path)
            assert result is True
        finally:
            os.unlink(temp_path)

    def test_validate_input_nonexistent_file(self, converter):
        """Test input validation with nonexistent file."""
        result = converter.validate_input("/nonexistent/file.urdf")
        assert result is False

    def test_convert_invalid_file(self, converter):
        """Test conversion with invalid file."""
        result = converter.convert(
            input_path="/nonexistent/file.urdf",
            output_path="/tmp/output.usd",
            robot_name="TestRobot",
        )
        assert result.success is False
        assert "Invalid input file" in result.error_message

    def test_convert_simple_urdf(self, converter):
        """Test conversion of a simple URDF file."""
        urdf_content = """<?xml version="1.0"?>
<robot name="test_robot">
  <link name="base_link">
    <visual>
      <geometry>
        <box size="1 1 1"/>
      </geometry>
    </visual>
  </link>
  <link name="arm_link">
    <visual>
      <geometry>
        <cylinder radius="0.1" length="0.5"/>
      </geometry>
    </visual>
  </link>
  <joint name="base_to_arm" type="revolute">
    <parent link="base_link"/>
    <child link="arm_link"/>
    <origin xyz="0 0 1" rpy="0 0 0"/>
  </joint>
</robot>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".urdf", delete=False) as f:
            temp_input = f.name
            f.write(urdf_content)

        with tempfile.NamedTemporaryFile(suffix=".usd", delete=False) as f:
            temp_output = f.name

        try:
            result = converter.convert(
                input_path=temp_input, output_path=temp_output, robot_name="TestRobot"
            )

            assert result.success is True
            assert len(result.parts) == 2
            assert "base_link" in result.parts
            assert "arm_link" in result.parts
        finally:
            os.unlink(temp_input)
            if os.path.exists(temp_output):
                os.unlink(temp_output)

    def test_convert_urdf_with_materials(self, converter):
        """Test conversion of URDF with materials."""
        urdf_content = """<?xml version="1.0"?>
<robot name="test_robot">
  <material name="blue">
    <color rgba="0 0 1 1"/>
  </material>
  <material name="red">
    <color rgba="1 0 0 1"/>
  </material>
  <link name="base_link">
    <visual>
      <geometry>
        <box size="1 1 1"/>
      </geometry>
      <material name="blue"/>
    </visual>
  </link>
</robot>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".urdf", delete=False) as f:
            temp_input = f.name
            f.write(urdf_content)

        with tempfile.NamedTemporaryFile(suffix=".usd", delete=False) as f:
            temp_output = f.name

        try:
            result = converter.convert(
                input_path=temp_input, output_path=temp_output, robot_name="TestRobot"
            )

            assert result.success is True
            assert len(result.materials) == 2
            assert "blue" in result.materials
            assert "red" in result.materials
        finally:
            os.unlink(temp_input)
            if os.path.exists(temp_output):
                os.unlink(temp_output)

    def test_convert_invalid_xml(self, converter):
        """Test conversion with invalid XML."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".urdf", delete=False) as f:
            temp_input = f.name
            f.write("This is not valid XML")

        with tempfile.NamedTemporaryFile(suffix=".usd", delete=False) as f:
            temp_output = f.name

        try:
            result = converter.convert(
                input_path=temp_input, output_path=temp_output, robot_name="TestRobot"
            )

            assert result.success is False
            assert "Failed to parse URDF XML" in result.error_message
        finally:
            os.unlink(temp_input)
            if os.path.exists(temp_output):
                os.unlink(temp_output)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
