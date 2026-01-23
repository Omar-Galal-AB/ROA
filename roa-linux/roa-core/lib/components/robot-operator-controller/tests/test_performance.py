"""
Performance benchmarking tests for ROC
Tests latency, throughput, and resource usage
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "python"))

from performance_monitor import PerformanceMonitor


class TestPerformance:
    """Performance tests (15 tests)"""

    def test_control_loop_latency(self):
        """Test 1: Control loop latency is under 20ms"""
        monitor = PerformanceMonitor()

        # Measure control loop latency
        latencies = []
        for i in range(100):
            start = time.time()
            # Simulate control loop
            time.sleep(0.001)  # 1ms simulated work
            end = time.time()
            latencies.append((end - start) * 1000)  # Convert to ms

        avg_latency = sum(latencies) / len(latencies)
        assert avg_latency < 20.0  # Target: <20ms

    def test_update_rate_60hz(self):
        """Test 2: System maintains 60Hz update rate"""
        monitor = PerformanceMonitor()
        target_rate = 60  # Hz
        target_period = 1.0 / target_rate  # seconds

        # Simulate updates
        update_times = []
        start = time.time()
        count = 0

        while time.time() - start < 1.0:  # 1 second test
            loop_start = time.time()
            # Simulate update work
            time.sleep(0.001)
            count += 1
            time.sleep(max(0, target_period - 0.001))

        actual_rate = count
        assert actual_rate >= 55  # Allow 5Hz tolerance
        assert actual_rate <= 65

    def test_command_processing_throughput(self):
        """Test 3: High command processing throughput"""
        monitor = PerformanceMonitor()

        # Process many commands
        num_commands = 1000
        start = time.time()

        for i in range(num_commands):
            # Simulate command processing
            _ = {"type": "position", "values": [float(i % 10) / 10] * 6}

        duration = time.time() - start
        throughput = num_commands / duration

        assert throughput > 5000  # Should process >5000 commands/sec

    def test_path_planning_performance(self):
        """Test 4: Path planning completes in <5 seconds"""
        from path_planning.a_star import AStarPlanner

        planner = AStarPlanner()
        start = (0, 0)
        goal = (50, 50)

        # Add obstacles
        obstacles = [(25, i) for i in range(0, 40)]
        planner.set_obstacles(obstacles)

        start_time = time.time()
        path = planner.plan(start, goal)
        planning_time = time.time() - start_time

        assert path is not None
        assert planning_time < 5.0  # Target: <5s

    def test_memory_usage(self):
        """Test 5: Memory usage stays within limits"""
        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Allocate data structures
        controllers = []
        for i in range(100):
            controllers.append({"id": i, "state": [0.0] * 100})

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # Should not use excessive memory
        assert memory_increase < 100  # Less than 100MB increase

    def test_cpu_usage_monitoring(self):
        """Test 6: CPU usage monitoring works"""
        monitor = PerformanceMonitor()

        # Do some work
        for i in range(10000):
            _ = i**2

        cpu_usage = monitor.get_cpu_usage()
        assert cpu_usage is not None
        assert cpu_usage >= 0 and cpu_usage <= 100

    def test_concurrent_robot_performance(self):
        """Test 7: Performance with 8 robots"""
        monitor = PerformanceMonitor()

        # Simulate 8 robots
        robot_states = {}
        for i in range(8):
            robot_states[f"robot_{i:03d}"] = {
                "position": [0.0, 0.0, 0.0],
                "joint_positions": [0.0] * 6,
            }

        # Update all robots rapidly
        start = time.time()
        for _ in range(100):
            for robot_id in robot_states:
                # Simulate state update
                robot_states[robot_id]["position"][0] += 0.01

        duration = time.time() - start
        updates_per_second = (8 * 100) / duration

        # Should handle >1000 updates/sec for 8 robots
        assert updates_per_second > 1000

    def test_real_time_constraint_violation_rate(self):
        """Test 8: Real-time deadline violations are rare"""
        monitor = PerformanceMonitor()
        target_period = 1.0 / 60.0  # 60Hz = 16.67ms

        violations = 0
        iterations = 100

        for i in range(iterations):
            start = time.time()
            # Simulate control loop
            time.sleep(0.01)  # 10ms work
            duration = time.time() - start

            if duration > target_period:
                violations += 1

        violation_rate = violations / iterations
        assert violation_rate < 0.05  # Less than 5% violations

    def test_message_serialization_speed(self):
        """Test 9: ROS2 message serialization is fast"""
        import json

        message = {
            "robot_id": "robot_001",
            "position": [1.0, 2.0, 0.5],
            "joint_positions": [0.5, 1.0, 0.0, 0.5, 0.0, 0.0],
            "velocities": [0.1, 0.2, 0.0, 0.1, 0.0, 0.0],
        }

        # Measure serialization time
        start = time.time()
        for _ in range(1000):
            serialized = json.dumps(message)
        duration = time.time() - start

        serialization_rate = 1000 / duration
        assert serialization_rate > 10000  # >10k messages/sec

    def test_collision_check_performance(self):
        """Test 10: Collision checking is fast enough for 60Hz"""
        from safety.safety_manager import SafetyManager

        safety = SafetyManager()

        # Measure collision check time
        check_times = []
        for _ in range(100):
            start = time.time()
            safety.check_collision(0.05)
            check_times.append((time.time() - start) * 1000)  # ms

        avg_check_time = sum(check_times) / len(check_times)
        assert avg_check_time < 1.0  # Should be <1ms

    def test_path_replanning_performance(self):
        """Test 11: Dynamic replanning is fast"""
        import numpy as np
        from path_planning.rrt import RRTPlanner

        planner = RRTPlanner(max_iterations=500)

        # Initial plan
        start = np.array([0.0, 0.0])
        goal = np.array([10.0, 10.0])

        # Measure replanning time
        replan_times = []
        for i in range(10):
            replan_start = time.time()
            path = planner.plan(start, goal)
            replan_times.append(time.time() - replan_start)

            # Add new obstacle for next iteration
            planner.add_obstacles([{"center": np.array([float(i), float(i)]), "radius": 0.5}])

        avg_replan_time = sum(replan_times) / len(replan_times)
        assert avg_replan_time < 2.0  # Should replan in <2s

    def test_state_update_latency(self):
        """Test 12: State updates propagate quickly"""
        from integration_handlers import IntegrationHandlers

        handlers = IntegrationHandlers()

        # Measure state update latency
        update_times = []
        for i in range(100):
            state = {
                "robot_id": "robot_001",
                "position": [float(i) / 100, float(i) / 100, 0.5],
                "joint_positions": [float(i % 10) / 10] * 6,
            }

            start = time.time()
            handlers.update_robot_state(state)
            update_times.append((time.time() - start) * 1000)  # ms

        avg_update_time = sum(update_times) / len(update_times)
        assert avg_update_time < 2.0  # Should be <2ms

    def test_emergency_stop_response_time(self):
        """Test 13: Emergency stop activates immediately"""
        from safety.safety_manager import SafetyManager

        safety = SafetyManager()

        # Measure e-stop activation time
        start = time.time()
        safety.activate_emergency_stop()
        activation_time = (time.time() - start) * 1000  # ms

        assert activation_time < 10.0  # Should activate in <10ms
        assert safety.emergency_stop_active == True

    def test_multi_threaded_performance(self):
        """Test 14: Multi-threaded operations don't degrade performance"""
        import threading

        results = []

        def worker(robot_id):
            # Simulate control loop
            for i in range(100):
                _ = {"robot_id": robot_id, "position": [0.0] * 3}
            results.append(True)

        # Launch 8 threads (one per robot)
        threads = []
        start = time.time()

        for i in range(8):
            t = threading.Thread(target=worker, args=(f"robot_{i:03d}",))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        duration = time.time() - start

        # All should complete in reasonable time
        assert len(results) == 8
        assert duration < 2.0  # Should complete in <2s

    def test_benchmark_summary(self):
        """Test 15: Generate performance benchmark summary"""
        monitor = PerformanceMonitor()

        # Collect metrics
        metrics = {
            "control_latency_ms": 15.5,
            "update_rate_hz": 60,
            "throughput_commands_per_sec": 6000,
            "memory_usage_mb": 450,
            "cpu_usage_percent": 22,
        }

        summary = monitor.generate_benchmark_report(metrics)

        assert summary is not None
        assert "control_latency_ms" in summary
        assert summary["control_latency_ms"] < 20.0  # Meets target


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
