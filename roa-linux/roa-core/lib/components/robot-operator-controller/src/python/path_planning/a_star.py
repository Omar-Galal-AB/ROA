"""
A* Path Planning Algorithm

Optimal grid-based path planning for robot navigation.
Finds shortest collision-free path from start to goal.

Author: ROA Development Team
Date: 2025-11-16
"""

from typing import Dict, List, Optional, Tuple, Set
import heapq
import math


class Node:
    """Node in the A* search tree"""
    
    def __init__(self, position: Tuple[float, float, float], parent=None):
        self.position = position
        self.parent = parent
        self.g = 0  # Cost from start to current node
        self.h = 0  # Heuristic cost from current node to goal
        self.f = 0  # Total cost (g + h)
    
    def __lt__(self, other):
        return self.f < other.f
    
    def __eq__(self, other):
        return self.position == other.position
    
    def __hash__(self):
        return hash(self.position)


class AStarPlanner:
    """
    A* path planning algorithm
    
    Features:
    - Optimal path finding
    - Collision avoidance
    - 3D navigation support
    - Configurable grid resolution
    """
    
    def __init__(
        self,
        grid_resolution: float = 0.1,
        obstacle_padding: float = 0.05,
        diagonal_movement: bool = True
    ):
        """
        Initialize A* planner
        
        Args:
            grid_resolution: Grid cell size in meters
            obstacle_padding: Safety padding around obstacles
            diagonal_movement: Allow diagonal movement
        """
        self.grid_resolution = grid_resolution
        self.obstacle_padding = obstacle_padding
        self.diagonal_movement = diagonal_movement
        
        # Movement directions (including diagonals if enabled)
        self.movements = [
            (1, 0, 0), (-1, 0, 0),  # X axis
            (0, 1, 0), (0, -1, 0),  # Y axis
            (0, 0, 1), (0, 0, -1),  # Z axis
        ]
        
        if diagonal_movement:
            self.movements.extend([
                (1, 1, 0), (1, -1, 0), (-1, 1, 0), (-1, -1, 0),  # XY diagonal
                (1, 0, 1), (1, 0, -1), (-1, 0, 1), (-1, 0, -1),  # XZ diagonal
                (0, 1, 1), (0, 1, -1), (0, -1, 1), (0, -1, -1),  # YZ diagonal
            ])
    
    def plan(
        self,
        start: Dict[str, float],
        goal: Dict[str, float],
        obstacles: List[Dict]
    ) -> Optional[List[Dict[str, float]]]:
        """
        Plan path from start to goal
        
        Args:
            start: Start position {x, y, z}
            goal: Goal position {x, y, z}
            obstacles: List of obstacles with position and radius
            
        Returns:
            List of waypoints or None if no path found
        """
        # Convert to grid coordinates
        start_grid = self._to_grid(start)
        goal_grid = self._to_grid(goal)
        
        # Initialize start node
        start_node = Node(start_grid)
        start_node.g = 0
        start_node.h = self._heuristic(start_grid, goal_grid)
        start_node.f = start_node.g + start_node.h
        
        # Open and closed sets
        open_set = []
        heapq.heappush(open_set, start_node)
        open_dict = {start_grid: start_node}
        closed_set: Set[Tuple] = set()
        
        # Maximum iterations to prevent infinite loops
        max_iterations = 10000
        iterations = 0
        
        while open_set and iterations < max_iterations:
            iterations += 1
            
            # Get node with lowest f score
            current = heapq.heappop(open_set)
            del open_dict[current.position]
            
            # Check if reached goal
            if current.position == goal_grid:
                return self._reconstruct_path(current)
            
            closed_set.add(current.position)
            
            # Explore neighbors
            for movement in self.movements:
                neighbor_pos = (
                    current.position[0] + movement[0],
                    current.position[1] + movement[1],
                    current.position[2] + movement[2]
                )
                
                # Skip if in closed set
                if neighbor_pos in closed_set:
                    continue
                
                # Check collision
                neighbor_world = self._to_world(neighbor_pos)
                if self._is_collision(neighbor_world, obstacles):
                    continue
                
                # Calculate costs
                movement_cost = math.sqrt(sum(m**2 for m in movement))
                tentative_g = current.g + movement_cost
                
                # Check if neighbor already in open set
                if neighbor_pos in open_dict:
                    neighbor = open_dict[neighbor_pos]
                    if tentative_g < neighbor.g:
                        neighbor.g = tentative_g
                        neighbor.f = neighbor.g + neighbor.h
                        neighbor.parent = current
                        heapq.heapify(open_set)
                else:
                    neighbor = Node(neighbor_pos, current)
                    neighbor.g = tentative_g
                    neighbor.h = self._heuristic(neighbor_pos, goal_grid)
                    neighbor.f = neighbor.g + neighbor.h
                    heapq.heappush(open_set, neighbor)
                    open_dict[neighbor_pos] = neighbor
        
        # No path found
        return None
    
    def _heuristic(
        self,
        pos1: Tuple[float, float, float],
        pos2: Tuple[float, float, float]
    ) -> float:
        """Euclidean distance heuristic"""
        return math.sqrt(
            (pos2[0] - pos1[0])**2 +
            (pos2[1] - pos1[1])**2 +
            (pos2[2] - pos1[2])**2
        )
    
    def _to_grid(self, pos: Dict[str, float]) -> Tuple[int, int, int]:
        """Convert world coordinates to grid coordinates"""
        return (
            int(round(pos['x'] / self.grid_resolution)),
            int(round(pos['y'] / self.grid_resolution)),
            int(round(pos.get('z', 0.0) / self.grid_resolution))
        )
    
    def _to_world(self, grid_pos: Tuple[int, int, int]) -> Dict[str, float]:
        """Convert grid coordinates to world coordinates"""
        return {
            'x': grid_pos[0] * self.grid_resolution,
            'y': grid_pos[1] * self.grid_resolution,
            'z': grid_pos[2] * self.grid_resolution
        }
    
    def _is_collision(
        self,
        position: Dict[str, float],
        obstacles: List[Dict]
    ) -> bool:
        """Check if position collides with any obstacle"""
        for obstacle in obstacles:
            obs_pos = obstacle.get('position', {})
            obs_radius = obstacle.get('radius', 0.1)
            
            # Calculate distance to obstacle
            dx = position['x'] - obs_pos.get('x', 0)
            dy = position['y'] - obs_pos.get('y', 0)
            dz = position['z'] - obs_pos.get('z', 0)
            distance = math.sqrt(dx**2 + dy**2 + dz**2)
            
            # Check collision with padding
            if distance < (obs_radius + self.obstacle_padding):
                return True
        
        return False
    
    def _reconstruct_path(self, goal_node: Node) -> List[Dict[str, float]]:
        """Reconstruct path from goal to start"""
        path = []
        current = goal_node
        
        while current is not None:
            path.append(self._to_world(current.position))
            current = current.parent
        
        # Reverse to get start-to-goal path
        path.reverse()
        
        # Smooth path (remove unnecessary waypoints)
        return self._smooth_path(path)
    
    def _smooth_path(
        self,
        path: List[Dict[str, float]]
    ) -> List[Dict[str, float]]:
        """Remove unnecessary waypoints from path"""
        if len(path) <= 2:
            return path
        
        smoothed = [path[0]]
        i = 0
        
        while i < len(path) - 1:
            # Try to skip as many points as possible
            j = len(path) - 1
            while j > i + 1:
                # Check if we can go directly from path[i] to path[j]
                if self._is_line_clear(path[i], path[j], []):
                    smoothed.append(path[j])
                    i = j
                    break
                j -= 1
            else:
                # Can't skip, add next point
                i += 1
                if i < len(path):
                    smoothed.append(path[i])
        
        return smoothed
    
    def _is_line_clear(
        self,
        start: Dict[str, float],
        end: Dict[str, float],
        obstacles: List[Dict]
    ) -> bool:
        """Check if line segment is collision-free"""
        # Sample points along the line
        steps = int(math.ceil(
            math.sqrt(
                (end['x'] - start['x'])**2 +
                (end['y'] - start['y'])**2 +
                (end['z'] - start['z'])**2
            ) / self.grid_resolution
        ))
        
        for i in range(steps + 1):
            t = i / max(steps, 1)
            point = {
                'x': start['x'] + t * (end['x'] - start['x']),
                'y': start['y'] + t * (end['y'] - start['y']),
                'z': start['z'] + t * (end['z'] - start['z'])
            }
            
            if self._is_collision(point, obstacles):
                return False
        
        return True
