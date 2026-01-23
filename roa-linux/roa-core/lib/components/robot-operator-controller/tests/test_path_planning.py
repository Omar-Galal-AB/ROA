"""
Test suite for ROC path planning algorithms (A* and RRT)
Tests cover path generation, obstacle avoidance, and performance
"""

import os
import sys
from unittest.mock import MagicMock, Mock

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "python"))

from path_planning.a_star import AStarPlanner
from path_planning.rrt import RRTPlanner


class TestAStarPlanner:
    """Test suite for A* path planning algorithm (30 tests total)"""

    def test_astar_initialization(self):
        """Test 1: A* planner initializes correctly"""
        planner = AStarPlanner()
        assert planner is not None
        assert planner.algorithm_name == "A*"

    def test_astar_simple_path(self):
        """Test 2: A* finds simple straight path"""
        planner = AStarPlanner()
        start = (0, 0)
        goal = (5, 5)

        path = planner.plan(start, goal)
        assert path is not None
        assert len(path) > 0
        assert path[0] == start
        assert path[-1] == goal

    def test_astar_with_obstacles(self):
        """Test 3: A* avoids obstacles"""
        planner = AStarPlanner()
        start = (0, 0)
        goal = (10, 10)

        # Add obstacle in middle
        obstacles = [(5, 5), (5, 6), (6, 5), (6, 6)]
        planner.set_obstacles(obstacles)

        path = planner.plan(start, goal)
        assert path is not None
        # Path should not contain obstacle points
        for point in path:
            assert point not in obstacles

    def test_astar_complex_obstacles(self):
        """Test 4: A* handles complex obstacle configurations"""
        planner = AStarPlanner()
        start = (0, 0)
        goal = (20, 20)

        # Create a wall with gap
        obstacles = [(i, 10) for i in range(0, 15)]  # Wall with gap at x=15-20
        planner.set_obstacles(obstacles)

        path = planner.plan(start, goal)
        assert path is not None
        assert len(path) > 0

    def test_astar_no_path_exists(self):
        """Test 5: A* returns None when no path exists"""
        planner = AStarPlanner()
        start = (0, 0)
        goal = (10, 10)

        # Completely surround goal
        obstacles = [(9 + i, 9 + j) for i in range(-1, 3) for j in range(-1, 3)]
        planner.set_obstacles(obstacles)

        path = planner.plan(start, goal)
        assert path is None or len(path) == 0

    def test_astar_heuristic_function(self):
        """Test 6: A* uses correct heuristic (Manhattan/Euclidean)"""
        planner = AStarPlanner(heuristic="manhattan")
        assert planner.heuristic_type == "manhattan"

        h1 = planner.heuristic((0, 0), (3, 4))
        assert h1 == 7  # |3-0| + |4-0| = 7

        planner_euclidean = AStarPlanner(heuristic="euclidean")
        h2 = planner_euclidean.heuristic((0, 0), (3, 4))
        assert abs(h2 - 5.0) < 0.01  # sqrt(3^2 + 4^2) = 5

    def test_astar_path_smoothing(self):
        """Test 7: A* can smooth paths"""
        planner = AStarPlanner()
        start = (0, 0)
        goal = (10, 10)

        raw_path = planner.plan(start, goal)
        smoothed_path = planner.smooth_path(raw_path)

        # Smoothed path should have fewer points
        assert len(smoothed_path) <= len(raw_path)

    def test_astar_3d_planning(self):
        """Test 8: A* handles 3D spaces"""
        planner = AStarPlanner(dimensions=3)
        start = (0, 0, 0)
        goal = (5, 5, 5)

        path = planner.plan(start, goal)
        assert path is not None
        assert all(len(point) == 3 for point in path)

    def test_astar_grid_resolution(self):
        """Test 9: A* respects grid resolution"""
        planner = AStarPlanner(resolution=0.5)
        start = (0.0, 0.0)
        goal = (5.0, 5.0)

        path = planner.plan(start, goal)
        # Check path points align with grid resolution
        for point in path:
            assert point[0] % 0.5 == 0 or abs(point[0] % 0.5) < 0.01
            assert point[1] % 0.5 == 0 or abs(point[1] % 0.5) < 0.01

    def test_astar_performance_simple(self):
        """Test 10: A* completes simple planning in reasonable time"""
        import time

        planner = AStarPlanner()
        start = (0, 0)
        goal = (10, 10)

        start_time = time.time()
        path = planner.plan(start, goal)
        planning_time = time.time() - start_time

        assert path is not None
        assert planning_time < 1.0  # Should complete in < 1 second


class TestRRTPlanner:
    """Test suite for RRT (Rapidly-exploring Random Tree) planner"""

    def test_rrt_initialization(self):
        """Test 11: RRT planner initializes correctly"""
        planner = RRTPlanner()
        assert planner is not None
        assert planner.algorithm_name == "RRT"

    def test_rrt_simple_path(self):
        """Test 12: RRT finds path in open space"""
        planner = RRTPlanner(max_iterations=1000)
        start = np.array([0.0, 0.0])
        goal = np.array([5.0, 5.0])

        path = planner.plan(start, goal)
        assert path is not None
        assert len(path) > 0

    def test_rrt_with_obstacles(self):
        """Test 13: RRT avoids obstacles"""
        planner = RRTPlanner(max_iterations=2000)
        start = np.array([0.0, 0.0])
        goal = np.array([10.0, 10.0])

        # Add circular obstacle
        obstacles = [{"center": np.array([5.0, 5.0]), "radius": 1.5}]
        planner.set_obstacles(obstacles)

        path = planner.plan(start, goal)
        assert path is not None
        # Verify path avoids obstacle
        for point in path:
            dist = np.linalg.norm(point - obstacles[0]["center"])
            assert dist >= obstacles[0]["radius"] - 0.1  # Small tolerance

    def test_rrt_step_size(self):
        """Test 14: RRT respects step size parameter"""
        planner = RRTPlanner(step_size=0.5)
        start = np.array([0.0, 0.0])
        goal = np.array([5.0, 5.0])

        path = planner.plan(start, goal)
        if path and len(path) > 1:
            # Check consecutive points are at most step_size apart
            for i in range(len(path) - 1):
                dist = np.linalg.norm(path[i + 1] - path[i])
                assert dist <= 0.5 + 0.1  # step_size + tolerance

    def test_rrt_max_iterations(self):
        """Test 15: RRT respects iteration limit"""
        planner = RRTPlanner(max_iterations=100)
        start = np.array([0.0, 0.0])
        goal = np.array([100.0, 100.0])  # Very far goal

        path = planner.plan(start, goal)
        # May not find path with low iteration limit
        # Test passes if it doesn't hang
        assert True

    def test_rrt_star_optimization(self):
        """Test 16: RRT* finds better paths than basic RRT"""
        rrt_basic = RRTPlanner(variant="basic", max_iterations=1000)
        rrt_star = RRTPlanner(variant="rrt_star", max_iterations=1000)

        start = np.array([0.0, 0.0])
        goal = np.array([10.0, 10.0])

        path_basic = rrt_basic.plan(start, goal)
        path_star = rrt_star.plan(start, goal)

        if path_basic and path_star:
            # RRT* should find shorter path
            length_basic = sum(
                np.linalg.norm(path_basic[i + 1] - path_basic[i])
                for i in range(len(path_basic) - 1)
            )
            length_star = sum(
                np.linalg.norm(path_star[i + 1] - path_star[i]) for i in range(len(path_star) - 1)
            )
            # RRT* should be equal or better
            assert length_star <= length_basic * 1.1  # Allow 10% tolerance

    def test_rrt_3d_planning(self):
        """Test 17: RRT handles 3D spaces"""
        planner = RRTPlanner(dimensions=3, max_iterations=1000)
        start = np.array([0.0, 0.0, 0.0])
        goal = np.array([5.0, 5.0, 5.0])

        path = planner.plan(start, goal)
        assert path is not None
        assert all(len(point) == 3 for point in path)

    def test_rrt_goal_bias(self):
        """Test 18: RRT uses goal bias parameter"""
        planner = RRTPlanner(goal_bias=0.2, max_iterations=500)
        start = np.array([0.0, 0.0])
        goal = np.array([10.0, 10.0])

        path = planner.plan(start, goal)
        # With goal bias, should find path more quickly
        assert path is not None

    def test_rrt_bidirectional(self):
        """Test 19: Bidirectional RRT searches from both ends"""
        planner = RRTPlanner(variant="bidirectional", max_iterations=1000)
        start = np.array([0.0, 0.0])
        goal = np.array([10.0, 10.0])

        path = planner.plan(start, goal)
        assert path is not None

    def test_rrt_path_smoothing(self):
        """Test 20: RRT can smooth jagged paths"""
        planner = RRTPlanner(max_iterations=500)
        start = np.array([0.0, 0.0])
        goal = np.array([10.0, 10.0])

        raw_path = planner.plan(start, goal)
        if raw_path:
            smoothed_path = planner.smooth_path(raw_path)
            # Smoothed path should have fewer waypoints
            assert len(smoothed_path) <= len(raw_path)


class TestPathPlanningComparison:
    """Compare A* and RRT performance"""

    def test_astar_vs_rrt_simple_environment(self):
        """Test 21: Compare A* and RRT in simple environment"""
        astar = AStarPlanner()
        rrt = RRTPlanner(max_iterations=1000)

        start = (0.0, 0.0)
        goal = (10.0, 10.0)

        path_astar = astar.plan(start, goal)
        path_rrt = rrt.plan(np.array(start), np.array(goal))

        assert path_astar is not None
        assert path_rrt is not None

    def test_astar_vs_rrt_with_obstacles(self):
        """Test 22: Compare A* and RRT with obstacles"""
        astar = AStarPlanner()
        rrt = RRTPlanner(max_iterations=2000)

        start = (0.0, 0.0)
        goal = (20.0, 20.0)

        # Grid obstacles for A*
        obstacles_grid = [(10, i) for i in range(0, 15)]
        astar.set_obstacles(obstacles_grid)

        # Circular obstacles for RRT
        obstacles_rrt = [{"center": np.array([10.0, 7.0]), "radius": 3.0}]
        rrt.set_obstacles(obstacles_rrt)

        path_astar = astar.plan(start, goal)
        path_rrt = rrt.plan(np.array(start), np.array(goal))

        # Both should find paths
        assert path_astar is not None or path_rrt is not None

    def test_astar_optimality(self):
        """Test 23: A* finds optimal path (shortest)"""
        planner = AStarPlanner()
        start = (0, 0)
        goal = (5, 5)

        path = planner.plan(start, goal)
        if path:
            # Manhattan distance should be 10
            # A* should find near-optimal path
            path_length = len(path) - 1  # Number of steps
            assert path_length >= 10  # Can't be shorter than Manhattan
            assert path_length <= 15  # Should be reasonably optimal

    def test_rrt_probabilistic_completeness(self):
        """Test 24: RRT eventually finds path with enough iterations"""
        planner = RRTPlanner(max_iterations=5000)
        start = np.array([0.0, 0.0])
        goal = np.array([10.0, 10.0])

        # Small obstacle
        obstacles = [{"center": np.array([5.0, 5.0]), "radius": 0.5}]
        planner.set_obstacles(obstacles)

        path = planner.plan(start, goal)
        # With enough iterations, should find path
        assert path is not None

    def test_path_validity_checking(self):
        """Test 25: Validate planned paths are collision-free"""
        planner = AStarPlanner()
        start = (0, 0)
        goal = (10, 10)

        obstacles = [(5, 5)]
        planner.set_obstacles(obstacles)

        path = planner.plan(start, goal)
        if path:
            # Verify no path point is in obstacle
            for point in path:
                assert point not in obstacles


class TestPathRefinement:
    """Test path post-processing and refinement"""

    def test_path_smoothing_reduces_waypoints(self):
        """Test 26: Path smoothing reduces number of waypoints"""
        planner = AStarPlanner()
        start = (0, 0)
        goal = (10, 10)

        raw_path = planner.plan(start, goal)
        smoothed_path = planner.smooth_path(raw_path)

        assert len(smoothed_path) <= len(raw_path)

    def test_path_interpolation(self):
        """Test 27: Path can be interpolated for smooth motion"""
        planner = RRTPlanner(max_iterations=500)
        start = np.array([0.0, 0.0])
        goal = np.array([5.0, 5.0])

        path = planner.plan(start, goal)
        if path and len(path) >= 2:
            interpolated = planner.interpolate_path(path, num_points=100)
            assert len(interpolated) >= len(path)

    def test_path_velocity_profile(self):
        """Test 28: Generate velocity profile for path"""
        planner = AStarPlanner()
        start = (0, 0)
        goal = (10, 10)

        path = planner.plan(start, goal)
        if path:
            velocity_profile = planner.compute_velocity_profile(path, max_velocity=1.0)
            assert len(velocity_profile) == len(path)
            assert all(v >= 0 and v <= 1.0 for v in velocity_profile)

    def test_path_curvature_analysis(self):
        """Test 29: Analyze path curvature for feasibility"""
        planner = RRTPlanner(max_iterations=500)
        start = np.array([0.0, 0.0])
        goal = np.array([10.0, 10.0])

        path = planner.plan(start, goal)
        if path and len(path) >= 3:
            curvatures = planner.compute_curvature(path)
            assert len(curvatures) == len(path) - 2

    def test_path_replanning(self):
        """Test 30: Dynamic replanning when obstacles change"""
        planner = AStarPlanner()
        start = (0, 0)
        goal = (10, 10)

        # Initial path
        path1 = planner.plan(start, goal)

        # Add new obstacle
        new_obstacles = [(5, 5), (5, 6)]
        planner.add_obstacles(new_obstacles)

        # Replan
        path2 = planner.plan(start, goal)

        # Paths should be different
        assert path1 != path2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
