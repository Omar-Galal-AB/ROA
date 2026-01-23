#!/usr/bin/env python3
"""
Example: COMC (Coordinated Motion Controller) Usage

Shows how COMC would use DIMC API to coordinate multiple
robots and prevent collisions.
"""

import sys
from pathlib import Path

# Add DIMC to path
dimc_path = Path(__file__).parent.parent / "src" / "python"
sys.path.insert(0, str(dimc_path))

from dimc_api import DIMC_API


def check_multi_robot_safety(dimc: DIMC_API):
    """Check safety for all robot pairs"""

    print("\n" + "=" * 60)
    print("Multi-Robot Safety Analysis")
    print("=" * 60)

    all_robots = dimc.get_all_robots()

    if len(all_robots) < 2:
        print("\n⚠️  Need at least 2 robots for coordination")
        return

    print(f"\n🤖 Monitoring {len(all_robots)} robots: {all_robots}")

    # Get all inter-robot distances
    print("\n📏 Inter-Robot Distances:")
    distances = dimc.coordination.get_all_distances()

    critical_pairs = []
    warning_pairs = []

    for (robot_a, robot_b), distance in distances.items():
        status = "🟢"
        level = "SAFE"

        if distance < 0.5:  # Critical: < 50cm
            status = "🔴"
            level = "CRITICAL"
            critical_pairs.append((robot_a, robot_b, distance))
        elif distance < 1.0:  # Warning: < 1m
            status = "🟡"
            level = "WARNING"
            warning_pairs.append((robot_a, robot_b, distance))
        elif distance < 2.0:  # Caution: < 2m
            status = "🟡"
            level = "CAUTION"

        print(f"   {status} {robot_a} ↔ {robot_b}: {distance:.2f} m ({level})")

    # Handle critical situations
    if critical_pairs:
        print("\n🚨 CRITICAL PROXIMITY ALERTS:")
        for robot_a, robot_b, distance in critical_pairs:
            print(f"   {robot_a} and {robot_b} are DANGEROUSLY CLOSE ({distance:.2f} m)")
            print(f"   → Triggering emergency stop for both robots")
            # send_emergency_stop(robot_a)
            # send_emergency_stop(robot_b)

    # Handle warnings
    if warning_pairs:
        print("\n⚠️  PROXIMITY WARNINGS:")
        for robot_a, robot_b, distance in warning_pairs:
            print(f"   {robot_a} and {robot_b} are in proximity ({distance:.2f} m)")
            print(f"   → Requesting speed reduction")
            # request_speed_reduction(robot_a, factor=0.5)
            # request_speed_reduction(robot_b, factor=0.5)


def coordinate_robot_movement(robot_id: str, dimc: DIMC_API):
    """Coordinate single robot movement considering all others"""

    print(f"\n" + "=" * 60)
    print(f"Coordinating Movement: {robot_id}")
    print("=" * 60)

    # Get robots in proximity
    nearby_robots = dimc.coordination.get_robots_in_proximity(robot_id, max_distance_m=3.0)

    print(f"\n🔍 Nearby robots (within 3m): {len(nearby_robots)}")

    if not nearby_robots:
        print("   ✅ No nearby robots - safe to proceed at full speed")
        return True

    # Analyze each nearby robot
    for other_id, distance in nearby_robots:
        print(f"\n   🤖 {other_id}:")
        print(f"      Distance: {distance:.2f} m")

        # Get other robot's state
        other_info = dimc.tracking.get_robot_info(other_id)
        if other_info:
            print(f"      Type: {other_info.robot_type.value}")
            print(
                f"      Velocity: ({other_info.velocity[0]:.2f}, "
                f"{other_info.velocity[1]:.2f}, {other_info.velocity[2]:.2f}) m/s"
            )

        # Check if other robot sees us as obstacle
        other_obstacles = dimc.evade.get_obstacles(other_id)
        robot_obstacles = [o for o in other_obstacles if o.associated_robot_id == robot_id]

        if robot_obstacles:
            print(f"      ⚠️  {other_id} has detected us as obstacle!")
            print(f"      Their collision risk: {robot_obstacles[0].collision_risk:.2f}")

    # Decision making
    min_distance = min(dist for _, dist in nearby_robots)

    if min_distance < 0.5:
        print(f"\n   🛑 STOP: Robot within {min_distance:.2f} m")
        return False
    elif min_distance < 1.0:
        print(f"   🟡 SLOW: Robot within {min_distance:.2f} m (reduce to 30%)")
        # set_speed_multiplier(robot_id, 0.3)
        return True
    elif min_distance < 2.0:
        print(f"   🟡 CAUTION: Robot within {min_distance:.2f} m (reduce to 60%)")
        # set_speed_multiplier(robot_id, 0.6)
        return True
    else:
        print(f"   🟢 SAFE: Nearest robot at {min_distance:.2f} m")
        return True


def main():
    print("=" * 60)
    print("COMC - DIMC Integration Example")
    print("=" * 60)

    # Initialize DIMC
    dimc = DIMC_API()
    dimc.initialize()
    dimc.start()

    # Wait for robots...
    all_robots = dimc.get_all_robots()

    if not all_robots:
        print("\n❌ No robots registered.")
        print("   In real system, FTI would register robots after URDF import.")
        return

    print(f"\n🎯 Active robots: {all_robots}")

    # Scenario 1: Multi-robot safety check
    check_multi_robot_safety(dimc)

    # Scenario 2: Coordinate single robot
    if len(all_robots) >= 1:
        coordinate_robot_movement(all_robots[0], dimc)

    # Scenario 3: Formation coordination
    if len(all_robots) >= 3:
        print("\n" + "=" * 60)
        print("Formation Coordination")
        print("=" * 60)

        print("\n📐 Analyzing robot formation:")

        # Get all positions
        positions = {}
        for robot_id in all_robots[:3]:  # First 3 robots
            pos = dimc.tracking.get_position(robot_id)
            if pos:
                positions[robot_id] = pos
                print(f"   {robot_id}: ({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})")

        # Calculate formation center
        if len(positions) >= 3:
            center_x = sum(p[0] for p in positions.values()) / len(positions)
            center_y = sum(p[1] for p in positions.values()) / len(positions)
            center_z = sum(p[2] for p in positions.values()) / len(positions)

            print(f"\n   Formation center: ({center_x:.2f}, {center_y:.2f}, {center_z:.2f})")

            # Check formation spread
            max_dist_from_center = 0
            for robot_id, pos in positions.items():
                dist = (
                    (pos[0] - center_x) ** 2 + (pos[1] - center_y) ** 2 + (pos[2] - center_z) ** 2
                ) ** 0.5
                max_dist_from_center = max(max_dist_from_center, dist)

            print(f"   Formation spread: {max_dist_from_center:.2f} m")

            if max_dist_from_center > 5.0:
                print("   ⚠️  Formation too spread out!")
            else:
                print("   ✅ Formation compact")

    # Cleanup
    print("\n" + "=" * 60)
    dimc.stop()
    dimc.shutdown()
    print("COMC example complete")


if __name__ == "__main__":
    main()
