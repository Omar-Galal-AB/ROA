#!/usr/bin/env python3
"""
Example: ROC (Robot Orchestration Controller) Usage

Shows how ROC would use DIMC API to query robot states
for monitoring and state reporting.
"""

import sys
from pathlib import Path

# Add DIMC to path
dimc_path = Path(__file__).parent.parent / "src" / "python"
sys.path.insert(0, str(dimc_path))

from dimc_api import DIMC_API


def main():
    # Initialize DIMC
    dimc = DIMC_API()
    dimc.initialize()
    dimc.start()

    print("=" * 60)
    print("ROC - DIMC Integration Example")
    print("=" * 60)

    # Wait for robots to be registered by FTI...
    # (In real system, FTI would call dimc.register_robot() after importing URDF)

    # Query all robots
    print("\n1. Get all registered robots:")
    all_robots = dimc.get_all_robots()
    print(f"   Registered robots: {all_robots}")

    if not all_robots:
        print("\n   No robots registered yet.")
        print("   In real system, FTI would register robots after URDF import.")
        return

    # Query first robot
    robot_id = all_robots[0]
    print(f"\n2. Query robot state: {robot_id}")

    # Get position
    position = dimc.tracking.get_position(robot_id)
    if position:
        print(f"   Position: ({position[0]:.3f}, {position[1]:.3f}, {position[2]:.3f}) m")

    # Get orientation
    orientation = dimc.tracking.get_orientation(robot_id)
    if orientation:
        print(
            f"   Orientation: ({orientation[0]:.3f}, {orientation[1]:.3f}, "
            f"{orientation[2]:.3f}, {orientation[3]:.3f})"
        )

    # Get velocity
    velocity = dimc.tracking.get_velocity(robot_id)
    if velocity:
        print(f"   Velocity: ({velocity[0]:.3f}, {velocity[1]:.3f}, {velocity[2]:.3f}) m/s")

    # Get dimensions
    dimensions = dimc.tracking.get_dimensions(robot_id)
    if dimensions:
        print(f"   Dimensions:")
        print(f"     - Width:  {dimensions.width:.3f} m")
        print(f"     - Height: {dimensions.height:.3f} m")
        print(f"     - Length: {dimensions.length:.3f} m")

    # Get complete info
    print(f"\n3. Get complete robot info:")
    robot_info = dimc.tracking.get_robot_info(robot_id)
    if robot_info:
        print(f"   Robot ID: {robot_info.robot_id}")
        print(f"   Robot Type: {robot_info.robot_type.value}")
        print(f"   URDF Dimensions: {robot_info.has_urdf_dimensions}")
        print(f"   URDF Sensors: {robot_info.has_urdf_sensors}")
        print(f"   URDF Safety Zones: {robot_info.has_urdf_safety_zones}")

    # Multi-robot queries
    if len(all_robots) > 1:
        print(f"\n4. Multi-robot distance check:")
        robot_a = all_robots[0]
        robot_b = all_robots[1]

        distance = dimc.coordination.get_distance(robot_a, robot_b)
        if distance:
            print(f"   Distance between {robot_a} and {robot_b}: {distance:.3f} m")

            if distance < 1.0:
                print(f"   ⚠️  WARNING: Robots in close proximity!")
            elif distance < 2.0:
                print(f"   ⚠️  CAUTION: Robots approaching")

    # Cleanup
    print("\n" + "=" * 60)
    dimc.stop()
    dimc.shutdown()
    print("ROC example complete")


if __name__ == "__main__":
    main()
