"""
RRT Path Planning Algorithm

Rapidly-exploring Random Tree for sampling-based path planning.
Better for high-dimensional spaces and complex environments than grid-based A*.

Author: ROA Development Team
Date: 2025-11-16
"""

from typing import Dict, List, Optional, Tuple
import math
import random


class RRTNode:
    """Node in the RRT tree"""
    
    def __init__(self, position: Tuple[float, float, float], parent=None):
        self.position = position
        self.parent = parent
        self.cost = 0.0  # Distance from start


class RRTPlanner:
    """
    RRT (Rapidly-exploring Random Tree) path planner
    
    Features:
    - Sampling-based planning
    - Better for complex/high-dimensional spaces
    - Probabilistically complete
    - Fast exploration
    
    Variants:
    - Basic RRT: Explores toward random points
    - RRT* (optional): Rewires tree for optimal paths
    """
    
    def __init__(
        self,
        max_iterations: int = 5000,
        step_size: float = 0.5,
        goal_sample_rate: float = 0.1,
        obstacle_padding: float = 0.05,
        use_rrt_star: bool = False,
        rewire_radius: float = 1.0
    ):
        """
        Initialize RRT planner
        
        Args:
            max_iterations: Maximum number of sampling iterations
            step_size: Maximum distance to extend tree per iteration
            goal_sample_rate: Probability of sampling goal (0-1)
            obstacle_padding: Safety padding around obstacles
            use_rrt_star: Use RRT* for optimal paths (slower)
            rewire_radius: Radius for rewiring in RRT*
        """
        self.max_iterations = max_iterations
        self.step_size = step_size
        self.goal_sample_rate = goal_sample_rate
        self.obstacle_padding = obstacle_padding
        self.use_rrt_star = use_rrt_star
        self.rewire_radius = rewire_radius
        
        # Tree storage
        self.nodes: List[RRTNode] = []
    
    def plan(
        self,
        start: Dict[str, float],
        goal: Dict[str, float],
        obstacles: List[Dict],
        bounds: Optional[Dict[str, Tuple[float, float]]] = None
    ) -> Optional[List[Dict[str, float]]]:
        """
        Plan path from start to goal using RRT
        
        Args:
            start: Start position {x, y, z}
            goal: Goal position {x, y, z}
            obstacles: List of obstacles with position and radius
            bounds: Optional search bounds {x: (min, max), y: (min, max), z: (min, max)}
            
        Returns:
            List of waypoints or None if no path found
        """
        # Initialize tree with start node
        start_pos = self._dict_to_tuple(start)
        goal_pos = self._dict_to_tuple(goal)
        
        self.nodes = [RRTNode(start_pos)]
        
        # Determine bounds for sampling
        if bounds is None:
            bounds = self._compute_bounds(start, goal)
        
        # RRT main loop
        for i in range(self.max_iterations):
            # Sample random point (or goal with probability)
            if random.random() < self.goal_sample_rate:
                sample = goal_pos
            else:
                sample = self._random_sample(bounds)
            
            # Find nearest node in tree
            nearest_node = self._nearest_node(sample)
            
            # Extend tree toward sample
            new_pos = self._steer(nearest_node.position, sample)
            
            # Check collision
            if self._is_collision_free(nearest_node.position, new_pos, obstacles):
                # Create new node
                new_node = RRTNode(new_pos, nearest_node)
                new_node.cost = nearest_node.cost + self._distance(nearest_node.position, new_pos)
                
                # RRT* optimization: rewire tree
                if self.use_rrt_star:
                    self._rewire(new_node, obstacles)
                
                self.nodes.append(new_node)
                
                # Check if reached goal
                if self._distance(new_pos, goal_pos) < self.step_size:
                    # Create goal node
                    if self._is_collision_free(new_pos, goal_pos, obstacles):
                        goal_node = RRTNode(goal_pos, new_node)
                        goal_node.cost = new_node.cost + self._distance(new_pos, goal_pos)
                        self.nodes.append(goal_node)
                        
                        # Extract path
                        return self._extract_path(goal_node)
        
        # No path found
        return None
    
    def _dict_to_tuple(self, pos: Dict[str, float]) -> Tuple[float, float, float]:
        """Convert position dict to tuple"""
        return (pos['x'], pos['y'], pos.get('z', 0.0))
    
    def _tuple_to_dict(self, pos: Tuple[float, float, float]) -> Dict[str, float]:
        """Convert position tuple to dict"""
        return {'x': pos[0], 'y': pos[1], 'z': pos[2]}
    
    def _compute_bounds(
        self,
        start: Dict[str, float],
        goal: Dict[str, float]
    ) -> Dict[str, Tuple[float, float]]:
        """Compute sampling bounds from start and goal"""
        margin = 5.0  # Extra space around start-goal bounding box
        
        return {
            'x': (
                min(start['x'], goal['x']) - margin,
                max(start['x'], goal['x']) + margin
            ),
            'y': (
                min(start['y'], goal['y']) - margin,
                max(start['y'], goal['y']) + margin
            ),
            'z': (
                min(start.get('z', 0.0), goal.get('z', 0.0)) - margin,
                max(start.get('z', 0.0), goal.get('z', 0.0)) + margin
            )
        }
    
    def _random_sample(
        self,
        bounds: Dict[str, Tuple[float, float]]
    ) -> Tuple[float, float, float]:
        """Sample random point within bounds"""
        x = random.uniform(bounds['x'][0], bounds['x'][1])
        y = random.uniform(bounds['y'][0], bounds['y'][1])
        z = random.uniform(bounds['z'][0], bounds['z'][1])
        return (x, y, z)
    
    def _nearest_node(self, sample: Tuple[float, float, float]) -> RRTNode:
        """Find nearest node in tree to sample point"""
        min_dist = float('inf')
        nearest = self.nodes[0]
        
        for node in self.nodes:
            dist = self._distance(node.position, sample)
            if dist < min_dist:
                min_dist = dist
                nearest = node
        
        return nearest
    
    def _steer(
        self,
        from_pos: Tuple[float, float, float],
        to_pos: Tuple[float, float, float]
    ) -> Tuple[float, float, float]:
        """
        Steer from from_pos toward to_pos by step_size
        
        Returns new position at most step_size away
        """
        dist = self._distance(from_pos, to_pos)
        
        if dist <= self.step_size:
            return to_pos
        
        # Interpolate
        ratio = self.step_size / dist
        new_x = from_pos[0] + ratio * (to_pos[0] - from_pos[0])
        new_y = from_pos[1] + ratio * (to_pos[1] - from_pos[1])
        new_z = from_pos[2] + ratio * (to_pos[2] - from_pos[2])
        
        return (new_x, new_y, new_z)
    
    def _distance(
        self,
        pos1: Tuple[float, float, float],
        pos2: Tuple[float, float, float]
    ) -> float:
        """Euclidean distance between two points"""
        return math.sqrt(
            (pos2[0] - pos1[0])**2 +
            (pos2[1] - pos1[1])**2 +
            (pos2[2] - pos1[2])**2
        )
    
    def _is_collision_free(
        self,
        from_pos: Tuple[float, float, float],
        to_pos: Tuple[float, float, float],
        obstacles: List[Dict]
    ) -> bool:
        """Check if line segment is collision-free"""
        # Sample points along the line
        steps = int(math.ceil(self._distance(from_pos, to_pos) / (self.step_size / 5.0)))
        
        for i in range(steps + 1):
            t = i / max(steps, 1)
            point = (
                from_pos[0] + t * (to_pos[0] - from_pos[0]),
                from_pos[1] + t * (to_pos[1] - from_pos[1]),
                from_pos[2] + t * (to_pos[2] - from_pos[2])
            )
            
            # Check collision with each obstacle
            for obstacle in obstacles:
                obs_pos = obstacle.get('position', {})
                obs_radius = obstacle.get('radius', 0.1)
                
                obs_tuple = (
                    obs_pos.get('x', 0),
                    obs_pos.get('y', 0),
                    obs_pos.get('z', 0)
                )
                
                if self._distance(point, obs_tuple) < (obs_radius + self.obstacle_padding):
                    return False
        
        return True
    
    def _rewire(self, new_node: RRTNode, obstacles: List[Dict]):
        """RRT* rewiring to optimize tree (optional)"""
        # Find nodes within rewire radius
        nearby_nodes = []
        for node in self.nodes:
            if self._distance(node.position, new_node.position) < self.rewire_radius:
                nearby_nodes.append(node)
        
        # Try to rewire nearby nodes through new_node
        for node in nearby_nodes:
            # Check if path through new_node is better
            potential_cost = new_node.cost + self._distance(new_node.position, node.position)
            
            if potential_cost < node.cost:
                # Check collision
                if self._is_collision_free(new_node.position, node.position, obstacles):
                    node.parent = new_node
                    node.cost = potential_cost
    
    def _extract_path(self, goal_node: RRTNode) -> List[Dict[str, float]]:
        """Extract path from tree by backtracking from goal"""
        path = []
        current = goal_node
        
        while current is not None:
            path.append(self._tuple_to_dict(current.position))
            current = current.parent
        
        # Reverse to get start-to-goal
        path.reverse()
        
        return path
