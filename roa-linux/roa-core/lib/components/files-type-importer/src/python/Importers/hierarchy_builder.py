"""
Hierarchy Builder - Preserves and organizes assembly hierarchies
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class HierarchyNode:
    """Represents a node in the robot assembly hierarchy."""
    name: str
    node_type: str  # 'link' or 'joint'
    parent: Optional[str] = None
    children: List[str] = None
    transform: Optional[Dict] = None  # xyz, rpy for joints
    properties: Optional[Dict] = None  # Additional node properties
    
    def __post_init__(self):
        """Initialize mutable default values."""
        if self.children is None:
            self.children = []
        if self.properties is None:
            self.properties = {}


class HierarchyBuilder:
    """
    Builds and maintains robot assembly hierarchies.
    
    Preserves parent-child relationships between robot parts (links)
    and their connections (joints) for proper assembly structure.
    """
    
    def __init__(self):
        """Initialize the hierarchy builder."""
        self.nodes: Dict[str, HierarchyNode] = {}
        self.root_nodes: List[str] = []
    
    def add_link(
        self,
        name: str,
        properties: Optional[Dict] = None
    ) -> HierarchyNode:
        """
        Add a link (robot part) to the hierarchy.
        
        Args:
            name: Name of the link
            properties: Optional properties (geometry, materials, etc.)
            
        Returns:
            Created HierarchyNode
        """
        node = HierarchyNode(
            name=name,
            node_type='link',
            properties=properties or {}
        )
        self.nodes[name] = node
        return node
    
    def add_joint(
        self,
        name: str,
        parent_link: str,
        child_link: str,
        joint_type: str,
        transform: Optional[Dict] = None,
        properties: Optional[Dict] = None
    ) -> HierarchyNode:
        """
        Add a joint connection to the hierarchy.
        
        Args:
            name: Name of the joint
            parent_link: Name of parent link
            child_link: Name of child link
            joint_type: Type of joint (revolute, prismatic, fixed, etc.)
            transform: Transform from parent to child (xyz, rpy)
            properties: Optional joint properties (limits, axis, etc.)
            
        Returns:
            Created HierarchyNode
        """
        # Create joint node - store child_link in properties for easy access
        joint_props = properties or {}
        joint_props['joint_type'] = joint_type
        joint_props['child_link'] = child_link  # Store for joints list
        
        node = HierarchyNode(
            name=name,
            node_type='joint',
            parent=parent_link,
            transform=transform,
            properties=joint_props
        )
        self.nodes[name] = node
        
        # Update parent-child relationships
        if parent_link in self.nodes:
            self.nodes[parent_link].children.append(child_link)
        
        if child_link in self.nodes:
            self.nodes[child_link].parent = parent_link
        
        return node
    
    def build_hierarchy(self) -> Dict:
        """
        Build the complete hierarchy structure.
        
        Returns:
            Hierarchy dictionary with root nodes, tree structure, and joints list
        """
        # Find root nodes (links with no parent)
        self.root_nodes = [
            name for name, node in self.nodes.items()
            if node.node_type == 'link' and node.parent is None
        ]
        
        # Build tree structure
        tree = {
            'root_nodes': self.root_nodes,
            'nodes': {},
            'depth': self._calculate_depth()
        }
        
        for name, node in self.nodes.items():
            tree['nodes'][name] = {
                'type': node.node_type,
                'parent': node.parent,
                'children': node.children,
                'transform': node.transform,
                'properties': node.properties
            }
        
        # Build dedicated joints list for physics constraints (UE5)
        # Format optimized for easy constraint creation
        # v3.1 - Added dynamics, mimic for ROC motor control
        joints_list = []
        for name, node in self.nodes.items():
            if node.node_type == 'joint':
                props = node.properties or {}
                joint_entry = {
                    'name': name,
                    'type': props.get('joint_type', 'fixed'),
                    'parent_link': node.parent,
                    'child_link': props.get('child_link'),  # Stored during add_joint
                    'axis': props.get('axis', [1, 0, 0]),
                    'limits': props.get('limits'),  # {lower, upper, effort, velocity} or None
                    'origin': node.transform,  # {xyz, rpy}
                    # NEW v3.1: Additional properties for ROC/DIMC
                    'dynamics': props.get('dynamics'),  # {damping, friction} or None
                    'mimic': props.get('mimic'),  # {joint, multiplier, offset} or None
                }
                joints_list.append(joint_entry)
        
        tree['joints'] = joints_list
        
        return tree
    
    def _calculate_depth(self) -> int:
        """
        Calculate maximum depth of the hierarchy tree.
        
        Returns:
            Maximum depth
        """
        max_depth = 0
        
        for root in self.root_nodes:
            depth = self._get_node_depth(root, 0)
            max_depth = max(max_depth, depth)
        
        return max_depth
    
    def _get_node_depth(self, node_name: str, current_depth: int) -> int:
        """
        Recursively calculate depth of a node.
        
        Args:
            node_name: Name of the node
            current_depth: Current depth in recursion
            
        Returns:
            Maximum depth from this node
        """
        if node_name not in self.nodes:
            return current_depth
        
        node = self.nodes[node_name]
        if not node.children:
            return current_depth
        
        max_child_depth = current_depth
        for child in node.children:
            child_depth = self._get_node_depth(child, current_depth + 1)
            max_child_depth = max(max_child_depth, child_depth)
        
        return max_child_depth
    
    def get_assembly_order(self) -> List[str]:
        """
        Get the order in which parts should be assembled.
        
        Returns:
            List of part names in assembly order (breadth-first)
        """
        assembly_order = []
        visited = set()
        queue = list(self.root_nodes)
        
        while queue:
            node_name = queue.pop(0)
            if node_name in visited:
                continue
            
            visited.add(node_name)
            if node_name in self.nodes:
                node = self.nodes[node_name]
                if node.node_type == 'link':
                    assembly_order.append(node_name)
                
                # Add children to queue
                queue.extend(node.children)
        
        return assembly_order
    
    def validate_hierarchy(self) -> Tuple[bool, List[str]]:
        """
        Validate the hierarchy for common issues.
        
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        # Check for cycles
        if self._has_cycles():
            errors.append("Hierarchy contains cycles")
        
        # Check for orphaned nodes
        orphaned = self._find_orphaned_nodes()
        if orphaned:
            errors.append(f"Found orphaned nodes: {', '.join(orphaned)}")
        
        # Check for missing references
        missing = self._find_missing_references()
        if missing:
            errors.append(f"Found missing parent references: {', '.join(missing)}")
        
        return (len(errors) == 0, errors)
    
    def _has_cycles(self) -> bool:
        """Check if hierarchy contains cycles."""
        visited = set()
        rec_stack = set()
        
        for node_name in self.nodes:
            if node_name not in visited:
                if self._has_cycle_util(node_name, visited, rec_stack):
                    return True
        
        return False
    
    def _has_cycle_util(
        self,
        node_name: str,
        visited: set,
        rec_stack: set
    ) -> bool:
        """Utility function to detect cycles using DFS."""
        visited.add(node_name)
        rec_stack.add(node_name)
        
        if node_name in self.nodes:
            for child in self.nodes[node_name].children:
                if child not in visited:
                    if self._has_cycle_util(child, visited, rec_stack):
                        return True
                elif child in rec_stack:
                    return True
        
        rec_stack.remove(node_name)
        return False
    
    def _find_orphaned_nodes(self) -> List[str]:
        """Find link nodes that are not connected to any root."""
        reachable = set()
        
        # DFS from each root to find all reachable nodes
        for root in self.root_nodes:
            self._mark_reachable(root, reachable)
        
        # Find link nodes not reachable from any root (ignore joints)
        orphaned = [
            name for name, node in self.nodes.items()
            if name not in reachable 
            and name not in self.root_nodes
            and node.node_type == 'link'  # Only check links, not joints
        ]
        
        return orphaned
    
    def _mark_reachable(self, node_name: str, reachable: set):
        """Mark all nodes reachable from given node."""
        if node_name in reachable or node_name not in self.nodes:
            return
        
        reachable.add(node_name)
        for child in self.nodes[node_name].children:
            self._mark_reachable(child, reachable)
    
    def _find_missing_references(self) -> List[str]:
        """Find parent references that don't exist in nodes."""
        missing = []
        
        for name, node in self.nodes.items():
            if node.parent and node.parent not in self.nodes:
                missing.append(f"{name} -> {node.parent}")
        
        return missing
    
    def export_to_dict(self) -> Dict:
        """
        Export hierarchy to dictionary format for serialization.
        
        Returns:
            Dictionary representation of hierarchy
        """
        return {
            'nodes': {
                name: {
                    'type': node.node_type,
                    'parent': node.parent,
                    'children': node.children,
                    'transform': node.transform,
                    'properties': node.properties
                }
                for name, node in self.nodes.items()
            },
            'root_nodes': self.root_nodes,
            'assembly_order': self.get_assembly_order(),
            'depth': self._calculate_depth()
        }
