# Mock UE5 System

Simulates UE5 world and actors without requiring UE5 installation.

## Usage

```python
from mock_ue5 import MockWorld, MockRobot

# Create world
world = MockWorld()

# Spawn robot
robot = world.spawn_robot("robot_001", num_joints=6, location=np.array([0, 0, 0]))

# Set joint positions
robot.set_joint_positions([0.5, 1.0, 0.0, 0.5, 0.0, 0.0])

# Check collisions
collision, distance = world.check_robot_collision("robot_001")

# Update simulation
world.tick(0.016)  # 60 FPS
```

## Features

- ✅ Robot simulation with kinematics
- ✅ Obstacle detection
- ✅ Collision checking
- ✅ Widget simulation
- ✅ Multi-robot support
