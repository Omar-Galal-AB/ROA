"""
Unit tests for HierarchyBuilder
"""

import sys
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python"))

from Importers.hierarchy_builder import HierarchyBuilder, HierarchyNode


class TestHierarchyBuilder:
    """Test suite for HierarchyBuilder class."""

    @pytest.fixture
    def builder(self):
        """Create a HierarchyBuilder instance for testing."""
        return HierarchyBuilder()

    def test_initialization(self, builder):
        """Test HierarchyBuilder initializes correctly."""
        assert builder is not None
        assert len(builder.nodes) == 0
        assert len(builder.root_nodes) == 0

    def test_add_link(self, builder):
        """Test adding a link to the hierarchy."""
        node = builder.add_link("base_link", {"geometry": "box"})

        assert node.name == "base_link"
        assert node.node_type == "link"
        assert "base_link" in builder.nodes
        assert builder.nodes["base_link"].properties["geometry"] == "box"

    def test_add_joint(self, builder):
        """Test adding a joint to the hierarchy."""
        # Add links first
        builder.add_link("base_link")
        builder.add_link("arm_link")

        # Add joint
        node = builder.add_joint(
            name="base_to_arm",
            parent_link="base_link",
            child_link="arm_link",
            joint_type="revolute",
            transform={"xyz": "0 0 1", "rpy": "0 0 0"},
        )

        assert node.name == "base_to_arm"
        assert node.node_type == "joint"
        assert node.parent == "base_link"
        assert "base_to_arm" in builder.nodes

        # Check parent-child relationships
        assert "arm_link" in builder.nodes["base_link"].children
        assert builder.nodes["arm_link"].parent == "base_link"

    def test_build_hierarchy_simple(self, builder):
        """Test building a simple hierarchy."""
        builder.add_link("base")
        builder.add_link("arm")
        builder.add_joint("j1", "base", "arm", "revolute")

        hierarchy = builder.build_hierarchy()

        assert "root_nodes" in hierarchy
        assert "base" in hierarchy["root_nodes"]
        assert len(hierarchy["root_nodes"]) == 1
        assert hierarchy["depth"] == 1

    def test_build_hierarchy_complex(self, builder):
        """Test building a complex multi-level hierarchy."""
        # Create a tree: base -> arm1 -> arm2 -> gripper
        builder.add_link("base")
        builder.add_link("arm1")
        builder.add_link("arm2")
        builder.add_link("gripper")

        builder.add_joint("j1", "base", "arm1", "revolute")
        builder.add_joint("j2", "arm1", "arm2", "revolute")
        builder.add_joint("j3", "arm2", "gripper", "prismatic")

        hierarchy = builder.build_hierarchy()

        assert len(hierarchy["root_nodes"]) == 1
        assert "base" in hierarchy["root_nodes"]
        assert hierarchy["depth"] == 3

    def test_get_assembly_order(self, builder):
        """Test getting assembly order for parts."""
        builder.add_link("base")
        builder.add_link("arm")
        builder.add_link("gripper")

        builder.add_joint("j1", "base", "arm", "revolute")
        builder.add_joint("j2", "arm", "gripper", "prismatic")

        builder.build_hierarchy()
        assembly_order = builder.get_assembly_order()

        # Base should come first, gripper last
        assert assembly_order[0] == "base"
        assert assembly_order[-1] == "gripper"
        assert len(assembly_order) == 3

    def test_validate_hierarchy_valid(self, builder):
        """Test validation of a valid hierarchy."""
        builder.add_link("base")
        builder.add_link("arm")
        builder.add_joint("j1", "base", "arm", "revolute")

        builder.build_hierarchy()  # Need to build before validating
        is_valid, errors = builder.validate_hierarchy()

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_hierarchy_missing_parent(self, builder):
        """Test validation catches missing parent references."""
        builder.add_link("arm")
        # Create a link with a parent that doesn't exist
        builder.nodes["arm"].parent = "nonexistent_base"

        is_valid, errors = builder.validate_hierarchy()

        assert is_valid is False
        assert len(errors) > 0
        assert any("missing parent" in str(e).lower() for e in errors)

    def test_export_to_dict(self, builder):
        """Test exporting hierarchy to dictionary."""
        builder.add_link("base")
        builder.add_link("arm")
        builder.add_joint("j1", "base", "arm", "revolute")

        builder.build_hierarchy()
        export = builder.export_to_dict()

        assert "nodes" in export
        assert "root_nodes" in export
        assert "assembly_order" in export
        assert "depth" in export
        assert len(export["nodes"]) == 3  # 2 links + 1 joint

    def test_multiple_roots(self, builder):
        """Test hierarchy with multiple independent root nodes."""
        # Create two independent trees
        builder.add_link("robot1_base")
        builder.add_link("robot1_arm")
        builder.add_joint("j1", "robot1_base", "robot1_arm", "revolute")

        builder.add_link("robot2_base")
        builder.add_link("robot2_arm")
        builder.add_joint("j2", "robot2_base", "robot2_arm", "revolute")

        hierarchy = builder.build_hierarchy()

        assert len(hierarchy["root_nodes"]) == 2
        assert "robot1_base" in hierarchy["root_nodes"]
        assert "robot2_base" in hierarchy["root_nodes"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
