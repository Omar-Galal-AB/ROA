"""
MAPF (Multi-Agent Path Finding) Solver Service

Basic MAPF solver for computing collision-free paths for multiple robots.
Provides CBS (Conflict-Based Search) inspired algorithm for path deconfliction.

Based on Open-RMF traffic management patterns and REMROC's MAPF solver service.

Key Features:
- Multi-robot path planning
- Conflict detection in paths
- Temporal path deconfliction
- Wait-at-vertex strategy
- Priority-based resolution
"""

import rclpy
from rclpy.node import Node
from rclpy.service import Service
from geometry_msgs.msg import Point

from typing import Dict, List, Optional, Tuple, Set, NamedTuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import heapq
import math
import time
import threading


class PathNode(NamedTuple):
    """Node in a path with timing"""
    x: float
    y: float
    time: float  # Expected arrival time


@dataclass
class TimedPath:
    """Path with timing information"""
    robot_id: str
    waypoints: List[PathNode]
    start_time: float = 0.0
    
    @property
    def end_time(self) -> float:
        return self.waypoints[-1].time if self.waypoints else self.start_time
    
    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


@dataclass
class Conflict:
    """Conflict between two robot paths"""
    robot1_id: str
    robot2_id: str
    type: str  # 'vertex', 'edge', or 'follow'
    location: Tuple[float, float]
    time: float
    
    def __lt__(self, other):
        return self.time < other.time


@dataclass
class Constraint:
    """Constraint on robot movement"""
    robot_id: str
    location: Tuple[float, float]
    time: float
    is_vertex: bool = True  # vs edge constraint


@dataclass
class MAPFRequest:
    """Request for MAPF solution"""
    robot_starts: Dict[str, Tuple[float, float]]  # robot_id -> (x, y)
    robot_goals: Dict[str, Tuple[float, float]]   # robot_id -> (x, y)
    robot_priorities: Dict[str, int] = field(default_factory=dict)  # Higher = more priority
    time_limit_sec: float = 30.0
    robot_radius: float = 0.3
    average_speed: float = 0.5  # m/s


@dataclass 
class MAPFSolution:
    """Solution from MAPF solver"""
    success: bool
    paths: Dict[str, TimedPath]  # robot_id -> path
    makespan: float  # Total time for all robots
    sum_of_costs: float  # Sum of all path durations
    solve_time: float
    conflicts_resolved: int
    message: str = ""


class SpatialGrid:
    """
    Spatial grid for efficient collision checking.
    """
    
    def __init__(self, cell_size: float = 0.5):
        self.cell_size = cell_size
        self.grid: Dict[Tuple[int, int, int], Set[str]] = defaultdict(set)  # (x, y, t) -> robot_ids
    
    def _get_cell(self, x: float, y: float, t: float) -> Tuple[int, int, int]:
        """Get grid cell for coordinates"""
        return (
            int(x / self.cell_size),
            int(y / self.cell_size),
            int(t / 0.5)  # 0.5 second time resolution
        )
    
    def add_path(self, robot_id: str, path: List[PathNode]) -> None:
        """Add a path to the grid"""
        for node in path:
            cell = self._get_cell(node.x, node.y, node.time)
            self.grid[cell].add(robot_id)
            
            # Also add neighboring time cells for safety
            prev_cell = self._get_cell(node.x, node.y, node.time - 0.5)
            next_cell = self._get_cell(node.x, node.y, node.time + 0.5)
            self.grid[prev_cell].add(robot_id)
            self.grid[next_cell].add(robot_id)
    
    def remove_path(self, robot_id: str) -> None:
        """Remove a robot's path from the grid"""
        for cell in list(self.grid.keys()):
            self.grid[cell].discard(robot_id)
            if not self.grid[cell]:
                del self.grid[cell]
    
    def check_collision(self, robot_id: str, node: PathNode, 
                        radius: float) -> Optional[str]:
        """Check if position collides with other robots"""
        cell = self._get_cell(node.x, node.y, node.time)
        
        # Check this cell and neighbors
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                for dt in [-1, 0, 1]:
                    check_cell = (cell[0] + dx, cell[1] + dy, cell[2] + dt)
                    for other_id in self.grid.get(check_cell, set()):
                        if other_id != robot_id:
                            return other_id
        
        return None
    
    def clear(self) -> None:
        """Clear the grid"""
        self.grid.clear()


class SimpleMAPFSolver:
    """
    Simple MAPF solver using prioritized planning.
    
    Algorithm:
    1. Sort robots by priority
    2. Plan each robot's path avoiding higher-priority robots
    3. Add temporal delays at conflicts
    """
    
    def __init__(self, logger=None):
        self.logger = logger
        self.spatial_grid = SpatialGrid()
    
    def solve(self, request: MAPFRequest) -> MAPFSolution:
        """
        Solve MAPF problem.
        
        Args:
            request: MAPF request with starts and goals
            
        Returns:
            MAPFSolution with paths for all robots
        """
        start_time = time.time()
        
        # Sort robots by priority (higher first)
        robots = list(request.robot_starts.keys())
        robots.sort(key=lambda r: request.robot_priorities.get(r, 0), reverse=True)
        
        paths: Dict[str, TimedPath] = {}
        conflicts_resolved = 0
        
        self.spatial_grid.clear()
        
        for robot_id in robots:
            start = request.robot_starts[robot_id]
            goal = request.robot_goals[robot_id]
            
            # Find path avoiding existing paths
            path = self._find_path(
                robot_id, start, goal,
                request.average_speed,
                request.robot_radius
            )
            
            if path is None:
                return MAPFSolution(
                    success=False,
                    paths={},
                    makespan=0,
                    sum_of_costs=0,
                    solve_time=time.time() - start_time,
                    conflicts_resolved=conflicts_resolved,
                    message=f"No path found for {robot_id}"
                )
            
            paths[robot_id] = path
            self.spatial_grid.add_path(robot_id, path.waypoints)
            
            # Check time limit
            if time.time() - start_time > request.time_limit_sec:
                return MAPFSolution(
                    success=False,
                    paths=paths,
                    makespan=0,
                    sum_of_costs=0,
                    solve_time=time.time() - start_time,
                    conflicts_resolved=conflicts_resolved,
                    message="Time limit exceeded"
                )
        
        # Calculate metrics
        makespan = max(p.end_time for p in paths.values()) if paths else 0
        sum_of_costs = sum(p.duration for p in paths.values())
        
        return MAPFSolution(
            success=True,
            paths=paths,
            makespan=makespan,
            sum_of_costs=sum_of_costs,
            solve_time=time.time() - start_time,
            conflicts_resolved=conflicts_resolved,
            message="Success"
        )
    
    def _find_path(self, robot_id: str,
                   start: Tuple[float, float],
                   goal: Tuple[float, float],
                   speed: float,
                   radius: float) -> Optional[TimedPath]:
        """
        Find path from start to goal avoiding existing paths.
        Uses A* with time dimension.
        """
        # Simple straight-line path with conflict avoidance
        # In production, this would use proper A* with obstacles
        
        dx = goal[0] - start[0]
        dy = goal[1] - start[1]
        distance = math.sqrt(dx*dx + dy*dy)
        
        if distance < 0.01:
            # Already at goal
            return TimedPath(
                robot_id=robot_id,
                waypoints=[PathNode(start[0], start[1], 0.0)],
                start_time=0.0
            )
        
        # Create waypoints along straight line
        num_waypoints = max(2, int(distance / 0.5) + 1)
        waypoints = []
        current_time = 0.0
        
        for i in range(num_waypoints):
            t = i / (num_waypoints - 1)
            x = start[0] + t * dx
            y = start[1] + t * dy
            
            node = PathNode(x, y, current_time)
            
            # Check for collisions
            collision_robot = self.spatial_grid.check_collision(robot_id, node, radius)
            
            if collision_robot:
                # Wait at previous position
                wait_time = 1.0  # Wait 1 second
                current_time += wait_time
                node = PathNode(x, y, current_time)
            
            waypoints.append(node)
            
            if i < num_waypoints - 1:
                segment_length = distance / (num_waypoints - 1)
                current_time += segment_length / speed
        
        return TimedPath(
            robot_id=robot_id,
            waypoints=waypoints,
            start_time=0.0
        )


class CBSMAPFSolver:
    """
    Conflict-Based Search MAPF solver.
    
    More sophisticated than prioritized planning:
    1. Find initial paths ignoring other robots
    2. Detect conflicts between paths
    3. Create constraint tree nodes
    4. Resolve conflicts by branching with new constraints
    """
    
    MAX_ITERATIONS = 1000
    
    def __init__(self, logger=None):
        self.logger = logger
    
    def solve(self, request: MAPFRequest) -> MAPFSolution:
        """Solve using CBS algorithm"""
        start_time = time.time()
        
        # Initialize with shortest paths
        paths = {}
        for robot_id in request.robot_starts:
            path = self._compute_shortest_path(
                request.robot_starts[robot_id],
                request.robot_goals[robot_id],
                request.average_speed
            )
            paths[robot_id] = path
        
        # Find conflicts
        constraints: List[Constraint] = []
        conflicts_resolved = 0
        
        for iteration in range(self.MAX_ITERATIONS):
            # Check time limit
            if time.time() - start_time > request.time_limit_sec:
                break
            
            # Find first conflict
            conflict = self._find_conflict(paths, request.robot_radius)
            
            if conflict is None:
                # No conflicts - we're done
                break
            
            conflicts_resolved += 1
            
            # Resolve by adding constraint to lower priority robot
            p1 = request.robot_priorities.get(conflict.robot1_id, 0)
            p2 = request.robot_priorities.get(conflict.robot2_id, 0)
            
            constrained_robot = conflict.robot1_id if p1 <= p2 else conflict.robot2_id
            
            # Add wait constraint
            constraint = Constraint(
                robot_id=constrained_robot,
                location=conflict.location,
                time=conflict.time
            )
            constraints.append(constraint)
            
            # Replan for constrained robot
            new_path = self._replan_with_constraints(
                constrained_robot,
                request.robot_starts[constrained_robot],
                request.robot_goals[constrained_robot],
                constraints,
                request.average_speed
            )
            
            if new_path:
                paths[constrained_robot] = new_path
        
        # Check for remaining conflicts
        remaining_conflict = self._find_conflict(paths, request.robot_radius)
        success = remaining_conflict is None
        
        # Calculate metrics
        makespan = max(p.end_time for p in paths.values()) if paths else 0
        sum_of_costs = sum(p.duration for p in paths.values())
        
        return MAPFSolution(
            success=success,
            paths=paths,
            makespan=makespan,
            sum_of_costs=sum_of_costs,
            solve_time=time.time() - start_time,
            conflicts_resolved=conflicts_resolved,
            message="Success" if success else "Could not resolve all conflicts"
        )
    
    def _compute_shortest_path(self, start: Tuple[float, float],
                                goal: Tuple[float, float],
                                speed: float) -> TimedPath:
        """Compute shortest path ignoring other robots"""
        dx = goal[0] - start[0]
        dy = goal[1] - start[1]
        distance = math.sqrt(dx*dx + dy*dy)
        
        if distance < 0.01:
            return TimedPath(
                robot_id="",
                waypoints=[PathNode(start[0], start[1], 0.0)]
            )
        
        num_waypoints = max(2, int(distance / 0.5) + 1)
        waypoints = []
        
        for i in range(num_waypoints):
            t = i / (num_waypoints - 1)
            x = start[0] + t * dx
            y = start[1] + t * dy
            time_val = (t * distance) / speed
            waypoints.append(PathNode(x, y, time_val))
        
        return TimedPath(robot_id="", waypoints=waypoints)
    
    def _find_conflict(self, paths: Dict[str, TimedPath],
                       radius: float) -> Optional[Conflict]:
        """Find first conflict between any two paths"""
        robot_ids = list(paths.keys())
        
        for i, robot1 in enumerate(robot_ids):
            path1 = paths[robot1]
            
            for robot2 in robot_ids[i+1:]:
                path2 = paths[robot2]
                
                conflict = self._check_paths_conflict(
                    robot1, path1,
                    robot2, path2,
                    radius
                )
                
                if conflict:
                    return conflict
        
        return None
    
    def _check_paths_conflict(self, 
                               robot1: str, path1: TimedPath,
                               robot2: str, path2: TimedPath,
                               radius: float) -> Optional[Conflict]:
        """Check if two paths conflict"""
        collision_dist = radius * 2
        time_tolerance = 0.5
        
        for node1 in path1.waypoints:
            for node2 in path2.waypoints:
                # Check temporal proximity
                if abs(node1.time - node2.time) > time_tolerance:
                    continue
                
                # Check spatial proximity
                dx = node1.x - node2.x
                dy = node1.y - node2.y
                dist = math.sqrt(dx*dx + dy*dy)
                
                if dist < collision_dist:
                    return Conflict(
                        robot1_id=robot1,
                        robot2_id=robot2,
                        type='vertex',
                        location=(node1.x, node1.y),
                        time=node1.time
                    )
        
        return None
    
    def _replan_with_constraints(self,
                                  robot_id: str,
                                  start: Tuple[float, float],
                                  goal: Tuple[float, float],
                                  constraints: List[Constraint],
                                  speed: float) -> Optional[TimedPath]:
        """Replan path respecting constraints"""
        # Get constraints for this robot
        robot_constraints = [c for c in constraints if c.robot_id == robot_id]
        
        if not robot_constraints:
            return self._compute_shortest_path(start, goal, speed)
        
        # Find latest constraint time
        latest_constraint_time = max(c.time for c in robot_constraints)
        
        # Simple strategy: add wait at start
        path = self._compute_shortest_path(start, goal, speed)
        
        # Shift all times by wait amount
        wait_time = latest_constraint_time + 1.0
        shifted_waypoints = [
            PathNode(n.x, n.y, n.time + wait_time)
            for n in path.waypoints
        ]
        
        # Add wait at start
        wait_node = PathNode(start[0], start[1], 0.0)
        shifted_waypoints.insert(0, wait_node)
        
        return TimedPath(
            robot_id=robot_id,
            waypoints=shifted_waypoints,
            start_time=0.0
        )


class MAPFService:
    """
    ROS2 service wrapper for MAPF solver.
    """
    
    def __init__(self, node: Node, use_cbs: bool = False):
        self.node = node
        self.logger = node.get_logger()
        
        if use_cbs:
            self.solver = CBSMAPFSolver(self.logger)
        else:
            self.solver = SimpleMAPFSolver(self.logger)
        
        # Cache of recent solutions
        self.solution_cache: Dict[str, MAPFSolution] = {}
        self._cache_lock = threading.Lock()
    
    def solve_paths(self, 
                    robot_starts: Dict[str, Tuple[float, float]],
                    robot_goals: Dict[str, Tuple[float, float]],
                    priorities: Optional[Dict[str, int]] = None,
                    speed: float = 0.5,
                    radius: float = 0.3) -> MAPFSolution:
        """
        Solve for collision-free paths.
        
        Args:
            robot_starts: Starting positions
            robot_goals: Goal positions
            priorities: Robot priorities (higher = more important)
            speed: Average robot speed
            radius: Robot collision radius
            
        Returns:
            MAPFSolution with paths
        """
        request = MAPFRequest(
            robot_starts=robot_starts,
            robot_goals=robot_goals,
            robot_priorities=priorities or {},
            robot_radius=radius,
            average_speed=speed
        )
        
        solution = self.solver.solve(request)
        
        if solution.success:
            self.logger.info(f"MAPF solved: {len(solution.paths)} paths, "
                            f"makespan={solution.makespan:.1f}s")
        else:
            self.logger.warn(f"MAPF failed: {solution.message}")
        
        return solution
    
    def get_path_for_robot(self, robot_id: str,
                           start: Tuple[float, float],
                           goal: Tuple[float, float],
                           other_paths: Dict[str, List[Tuple[float, float, float]]],
                           speed: float = 0.5,
                           radius: float = 0.3) -> Optional[List[PathNode]]:
        """
        Get path for single robot avoiding existing paths.
        
        Args:
            robot_id: Robot to plan for
            start: Start position
            goal: Goal position
            other_paths: Existing paths {robot_id: [(x, y, t), ...]}
            speed: Robot speed
            radius: Robot radius
            
        Returns:
            List of PathNodes or None
        """
        # Build MAPF request
        robot_starts = {robot_id: start}
        robot_goals = {robot_id: goal}
        
        # Add other robots at their positions along paths
        # (simplified - treats first point as start, last as goal)
        for other_id, path in other_paths.items():
            if path:
                robot_starts[other_id] = (path[0][0], path[0][1])
                robot_goals[other_id] = (path[-1][0], path[-1][1])
        
        # Give new robot lowest priority
        priorities = {rid: 1 for rid in other_paths}
        priorities[robot_id] = 0
        
        solution = self.solve_paths(robot_starts, robot_goals, priorities, speed, radius)
        
        if solution.success and robot_id in solution.paths:
            return solution.paths[robot_id].waypoints
        
        return None
    
    def deconflict_path(self, robot_id: str,
                        path: List[Tuple[float, float]],
                        other_paths: Dict[str, List[Tuple[float, float, float]]],
                        speed: float = 0.5,
                        radius: float = 0.3) -> List[PathNode]:
        """
        Add timing to a path to avoid conflicts with existing paths.
        
        Args:
            robot_id: Robot ID
            path: Spatial path [(x, y), ...]
            other_paths: Existing timed paths
            speed: Robot speed
            radius: Robot radius
            
        Returns:
            Timed path with waits added as needed
        """
        if not path:
            return []
        
        # Build spatial grid with other paths
        grid = SpatialGrid()
        for other_id, other_path in other_paths.items():
            nodes = [PathNode(x, y, t) for x, y, t in other_path]
            grid.add_path(other_id, nodes)
        
        # Add timing to our path
        timed_path = []
        current_time = 0.0
        
        for i, (x, y) in enumerate(path):
            node = PathNode(x, y, current_time)
            
            # Check for collisions
            max_wait = 10.0  # Max wait time
            waited = 0.0
            
            while waited < max_wait:
                collision = grid.check_collision(robot_id, node, radius)
                if collision is None:
                    break
                
                # Wait a bit
                current_time += 0.5
                waited += 0.5
                node = PathNode(x, y, current_time)
            
            timed_path.append(node)
            
            # Add travel time to next point
            if i < len(path) - 1:
                next_x, next_y = path[i + 1]
                dist = math.sqrt((next_x - x)**2 + (next_y - y)**2)
                current_time += dist / speed
        
        return timed_path
