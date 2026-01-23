# ROA v0.2 - Native ROS2 Integration

## Overview

This module replaces the v0.1 TCP bridge with native ROS2 DDS communication for low-latency (<5ms) robot control between UE5 and ROS2 ecosystem.

## Architecture

```
UE5 Plugin (Windows)              WSL (Ubuntu 22.04)
├─ rclcpp embedded                ├─ ROS2 Humble
├─ Fast-DDS (UDP multicast)       ├─ rclpy node
└─ ROARobotActor                  └─ ROABridgeNode
         │                                 │
         └────── DDS Topics ──────────────┘
           /robot/{id}/joint_states  →
           /robot/{id}/joint_commands ←
```

## Components

### `ros2_node.py`
Main bridge node providing:
- **ROABridgeNode**: Single-robot ROS2 bridge
  - Subscribes to UE5 joint states
  - Publishes joint commands to UE5
  - QoS profiles optimized for real-time control
  
- **ROABridgeManager**: Multi-robot support
  - Manages multiple bridge nodes
  - Multi-threaded executor
  - Per-robot topic namespacing

## Usage

### Standalone Mode (Single Robot)

```bash
# Launch ROS2 bridge for robot_0
roa --ros2-native --robot-id robot_0

# Or use ros2 component directly
roa --component ros2 --robot-id my_robot
```

### Multi-Robot Mode

```python
from components.ros2_native import ROABridgeManager

manager = ROABridgeManager()
manager.add_robot('robot_0', enable_logging=True)
manager.add_robot('robot_1', enable_logging=False)
manager.start()

# Your application logic here

manager.stop()
```

### Python API

```python
import rclpy
from components.ros2_native import ROABridgeNode

rclpy.init()
node = ROABridgeNode(robot_id='robot_0')

# Get current joint state
joint_state = node.get_current_joint_state()

# Send joint command
node.send_joint_command(
    joint_names=['joint1', 'joint2', 'joint3'],
    positions=[0.5, -0.3, 1.2],
    time_from_start=1.0
)

rclpy.spin(node)
```

## Topics

### From UE5 (Published by UE5 Plugin)
- `/robot/{robot_id}/joint_states` (sensor_msgs/JointState)
  - Joint positions, velocities, efforts
  - Published at 30 Hz

### To UE5 (Subscribed by UE5 Plugin)
- `/robot/{robot_id}/joint_commands` (trajectory_msgs/JointTrajectory)
  - Target joint positions
  - Time-based trajectory execution

## Dependencies

```bash
# ROS2 Humble (required)
sudo apt install ros-humble-rclpy

# Message packages
sudo apt install ros-humble-sensor-msgs
sudo apt install ros-humble-trajectory-msgs

# Optional: ROS2 tools
sudo apt install ros-humble-ros2cli
sudo apt install ros-humble-rqt
```

## Testing

### Verify Topics

```bash
# Source ROS2
source /opt/ros/humble/setup.bash

# List topics (should see robot topics)
ros2 topic list

# Echo joint states from UE5
ros2 topic echo /robot/robot_0/joint_states

# Publish test command to UE5
ros2 topic pub /robot/robot_0/joint_commands trajectory_msgs/msg/JointTrajectory \
  "joint_names: ['joint1', 'joint2']
   points:
   - positions: [0.5, -0.3]
     time_from_start: {sec: 1, nanosec: 0}"
```

### Monitor Performance

```bash
# Check topic Hz (should be ~30 Hz for joint_states)
ros2 topic hz /robot/robot_0/joint_states

# Check latency
ros2 topic delay /robot/robot_0/joint_states
```

## Migration from v0.1 TCP

### Before (v0.1)
```python
# TCP server on port 12345
from components.communication_center import TCPServer
server = TCPServer(port=12345)
server.start()
```

### After (v0.2)
```bash
# Native ROS2 bridge
roa --ros2-native --robot-id robot_0
```

### Compatibility
- v0.1 TCP mode still available as fallback
- UE5 plugin auto-detects mode (native vs TCP)
- Backward compatibility maintained

## Performance

| Metric | v0.1 TCP | v0.2 Native ROS2 |
|--------|----------|------------------|
| Latency | 50-100ms | <5ms |
| Protocol | TCP | UDP (DDS) |
| Bandwidth | Limited | High throughput |
| Multi-robot | Sequential | Parallel |
| Ecosystem | Custom | Native ROS2 |

## Troubleshooting

### "Could not launch ROS2 bridge"
- Install ROS2 Humble: `sudo apt install ros-humble-desktop`
- Source ROS2: `source /opt/ros/humble/setup.bash`

### "No topics visible"
- Check DDS discovery: `ros2 doctor --report`
- Verify multicast: `ip maddress show`
- Check firewall: `sudo ufw allow from 224.0.0.0/4`

### "High latency"
- Check QoS settings (RELIABLE vs BEST_EFFORT)
- Verify network not congested
- Monitor with `ros2 topic delay`

## Future Enhancements

- [ ] Sensor support (Camera, LiDAR, IMU)
- [ ] Service calls for configuration
- [ ] Action server for complex trajectories
- [ ] TF2 integration for transforms
- [ ] Gazebo-style plugin architecture

## License

Copyright ROA Development Team. All Rights Reserved.
