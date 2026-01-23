#!/usr/bin/env python3
"""
Example: Webthread/Evade Subsystem Usage

Shows how Webthread would use DIMC API for autonomous
obstacle avoidance in ADM mode.
"""

import sys
import time
from pathlib import Path

# Add DIMC to path
dimc_path = Path(__file__).parent.parent / "src" / "python"
sys.path.insert(0, str(dimc_path))

from dimc_api import DIMC_API, CollisionRisk


def simulate_robot_movement(robot_id: str, dimc: DIMC_API):
    """Simulate robot movement with Evade checks"""

    print(f"\n🤖 Moving {robot_id}...")

    # 1. Get environment scan
    scan = dimc.evade.get_environment_scan(robot_id)
    print(f"\n📡 Environment Scan:")
    print(f"   Position: {scan.position}")
    print(f"   Velocity: {scan.velocity}")
    print(f"   Obstacles detected: {len(scan.obstacles)}")
    print(f"   LIDAR active: {scan.lidar_available}")
    print(f"   Collision risk: {scan.collision_risk_level.value}")
    print(f"   Safe to move: {scan.safe_to_move}")

    # 2. Get Evade recommendation
    recommendation = dimc.evade.get_recommendation(robot_id)
    print(f"\n💡 Evade Recommendation:")
    print(f"   Action: {recommendation.action}")
    print(f"   Slowdown factor: {recommendation.slowdown_factor:.2f}")
    print(f"   Reason: {recommendation.reason}")
    print(f"   Risk level: {recommendation.risk_level.value}")

    if recommendation.nearest_obstacle_distance_m:
        print(f"   Nearest obstacle: {recommendation.nearest_obstacle_distance_m:.2f} m")

    # 3. Act on recommendation
    print(f"\n⚙️  Taking action...")
    if recommendation.action == "emergency_stop":
        print("   🛑 EMERGENCY STOP!")
        # robot.emergency_stop()
        return False

    elif recommendation.action == "slow_stop":
        print("   🟡 Decelerating to stop...")
        # robot.decelerate_to_stop(time=2.0)
        return False

    elif recommendation.action == "reduce_speed":
        print(f"   🟡 Reducing speed to {recommendation.slowdown_factor * 100:.0f}%")
        # robot.set_speed_multiplier(recommendation.slowdown_factor)

    elif recommendation.action == "caution":
        print("   🟢 Proceeding with caution")

    else:  # continue
        print("   🟢 Path clear - continuing")

    # 4. Check specific path before committing to movement
    target_direction = (1.0, 0.0, 0.0)  # Forward
    target_distance = 2.0  # 2 meters

    print(f"\n🔍 Checking path (forward, {target_distance} m)...")
    is_clear = dimc.evade.is_path_clear(robot_id, target_direction, target_distance)

    if is_clear:
        print("   ✅ Path is clear")
        # robot.move_forward(target_distance)
        return True
    else:
        print("   ❌ Path blocked - replanning required")
        # Call path planner for alternate route
        return False


def main():
    # Initialize DIMC
    print("=" * 60)
    print("Webthread/Evade - DIMC Integration Example")
    print("=" * 60)

    dimc = DIMC_API()
    dimc.initialize()
    dimc.start()

    # Wait for robots to be registered by FTI...
    all_robots = dimc.get_all_robots()

    if not all_robots:
        print("\n❌ No robots registered.")
        print("   In real system, FTI would register robots after URDF import.")
        return

    robot_id = all_robots[0]
    print(f"\n🎯 Target robot: {robot_id}")

    # PHASE 1: Calibration (during Webthread startup)
    print("\n" + "=" * 60)
    print("PHASE 1: Evade Calibration (Webthread Startup)")
    print("=" * 60)

    calibration = dimc.evade.calibrate(robot_id)
    print(f"\n✅ Calibration complete:")
    print(f"   Status: {calibration.calibration_status}")
    print(f"   Detection range: {calibration.detection_range_m} m")
    print(f"   Update rate: {calibration.update_rate_hz} Hz")
    print(f"   Safety zones: {len(calibration.safety_zones)}")
    print(f"   Sensors active: {calibration.sensors_active}")

    # PHASE 2: Runtime Evade checks
    print("\n" + "=" * 60)
    print("PHASE 2: Runtime Obstacle Avoidance")
    print("=" * 60)

    # Simulate movement decision
    can_move = simulate_robot_movement(robot_id, dimc)

    # PHASE 3: Continuous monitoring (would run in loop)
    print("\n" + "=" * 60)
    print("PHASE 3: Continuous Monitoring Loop")
    print("=" * 60)
    print("\n(In real system, this would run continuously at ~30Hz)")

    # Simulate a few monitoring cycles
    for i in range(3):
        print(f"\n--- Monitoring cycle {i+1} ---")
        risk = dimc.evade.get_collision_risk(robot_id)
        print(f"Current risk: {risk.value}")

        if risk == CollisionRisk.CRITICAL:
            print("🛑 CRITICAL RISK - Emergency stop!")
            break
        elif risk == CollisionRisk.HIGH:
            print("🟡 HIGH RISK - Reducing speed")
        elif risk == CollisionRisk.MEDIUM:
            print("🟡 MEDIUM RISK - Proceed with caution")
        else:
            print("🟢 Safe to proceed")

        time.sleep(0.1)  # Simulate 10Hz in example

    # Get detailed obstacle info
    print("\n" + "=" * 60)
    print("PHASE 4: Detailed Obstacle Analysis")
    print("=" * 60)

    obstacles = dimc.evade.get_obstacles(robot_id)
    print(f"\nDetected obstacles: {len(obstacles)}")

    for i, obs in enumerate(obstacles[:5], 1):  # Show first 5
        print(f"\n   Obstacle {i}:")
        print(f"     Type: {obs.obstacle_type.value}")
        print(f"     Distance: {obs.distance:.2f} m")
        print(f"     Collision risk: {obs.collision_risk:.2f}")
        print(
            f"     Position: ({obs.position[0]:.2f}, {obs.position[1]:.2f}, {obs.position[2]:.2f})"
        )

        if obs.obstacle_type.value == "robot":
            print(f"     Associated robot: {obs.associated_robot_id}")

    # Cleanup
    print("\n" + "=" * 60)
    dimc.stop()
    dimc.shutdown()
    print("Evade example complete")


if __name__ == "__main__":
    main()
