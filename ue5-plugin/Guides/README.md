# ROA UE5 Plugin

**Robot Operator Assistant - Unreal Engine 5 Integration Plugin**

Version: 0.1.0-alpha  
License: Proprietary  
Engine: Unreal Engine 5.6+

---

## Overview

The ROA UE5 Plugin provides seamless integration between Unreal Engine 5 and the Robot Operator Assistant (ROA) system. It enables real-time robot simulation, visualization, and control through a JSON-based communication protocol with the Python Webthread component.

### Key Features

? **Universal Robot Support** - All 15 UR models (UR3, UR5, UR10, UR15, UR20, UR30, etc.)  
? **Real-Time Communication** - TCP/WebSocket bridge to Python/ROS2  
? **Physics Simulation** - Full Chaos physics integration  
? **Collision Detection** - Real-time safety monitoring  
? **Dynamic Spawning** - Runtime robot instantiation  
? **Joint Control** - Position and velocity control  
? **Widget System** - Adaptive UI generation  
? **Thread-Safe** - Robust multi-threaded architecture  

---

## Architecture

```
???????????????????????????????????????????????
?         Python Webthread (Port 9876)        ?
?   ???????????  ???????????  ??????????    ?
?   ?  ROS2   ?  ?   FTI   ?  ?  ROC   ?    ?
?   ???????????  ???????????  ??????????    ?
???????????????????????????????????????????????
      ? TCP/JSON
   ?
???????????????????????????????????????????????
?         ROA UE5 Plugin (C++)    ?
?   ????????????????  ????????????????       ?
?   ?Network Server???? World Manager?       ?
?   ????????????????  ????????????????       ?
?       ?    ?
?   ????????????????  ????????????????       ?
?   ?Message System?  ? Robot Actors ?       ?
?   ????????????????  ????????????????       ?
???????????????????????????????????????????????
          ?
???????????????????????????????????????????????
?          Unreal Engine 5.6       ?
?   ????????????  ????????????  ???????????  ?
?   ? Physics  ?  ? Rendering?  ? Widgets ?  ?
?   ????????????  ????????????  ???????????  ?
???????????????????????????????????????????????
```

---

## Installation

### Prerequisites
- Unreal Engine 5.6 or later
- Visual Studio 2022
- Windows 10/11 or Linux
- Python 3.10+ (for Webthread component)
- ROS2 Humble (optional, for real robot control)

### Installation Steps

1. **Copy Plugin to Project**
 ```powershell
   Copy-Item -Path "D:\ROA\ROA_v0.1.0-alpha_Windows\Plugins\ROA_PlugIn" `
      -Destination "YourProject\Plugins\ROA_PlugIn" -Recurse
   ```

2. **Generate Project Files**
   ```powershell
   # Right-click on YourProject.uproject ? "Generate Visual Studio project files"
   # Or use command line:
   "C:\Program Files\Epic Games\UE_5.6\Engine\Build\BatchFiles\GenerateProjectFiles.bat" `
     "YourProject.uproject"
   ```

3. **Build Plugin**
   - Open YourProject.sln in Visual Studio
   - Build the project (Development Editor configuration)
   - Or build from command line:
   ```powershell
   "C:\Program Files\Epic Games\UE_5.6\Engine\Build\BatchFiles\Build.bat" `
     YourProjectEditor Win64 Development "YourProject.uproject"
   ```

4. **Enable Plugin in Editor**
   - Launch Unreal Editor
   - Edit ? Plugins
   - Search for "ROA"
   - Enable "ROA - Robot Operator Assistant"
   - Restart Editor

5. **Verify Installation**
   - Check Output Log for: `ROA Plugin: Startup complete - Ready for connections`
   - Plugin should be listening on port 9876

---

## Usage

### Starting the System

1. **Launch UE5 Project**
   ```powershell
   Start-Process "YourProject.uproject"
   ```

2. **Start Python Webthread**
   ```bash
   cd D:\ROA\ROA_v0.1.0-alpha_Windows\ROA
   python -m components.webthread.src.python.webthread_core
 ```

3. **Connect**
   - Webthread will automatically connect to UE5 on port 9876
   - Check Output Log for connection confirmation

### Spawning a Robot

**From Python:**
```python
from webthread import UE5Connector

connector = UE5Connector("localhost", 9876)
connector.connect()

# Spawn UR5e robot
connector.spawn_robot(
    robot_id="ur5e_001",
 robot_type="ur5e",
    spawn_location={"x": 0.0, "y": 0.0, "z": 0.0},
    initial_joint_states=[0.0, -1.57, 1.57, 0.0, 1.57, 0.0]
)
```

**From Blueprint:**
- Use ROA Blueprint nodes (coming soon)

### Controlling Joints

**From Python:**
```python
# Set joint positions
connector.set_joint_positions(
 robot_id="ur5e_001",
    joint_positions=[0.0, -1.0, 1.5, 0.0, 1.0, 0.0],
    duration=2.0
)

# Set joint velocities
connector.set_joint_velocities(
  robot_id="ur5e_001",
    joint_velocities=[0.1, 0.0, 0.0, 0.0, 0.0, 0.0]
)
```

### Getting Robot State

```python
state = connector.get_robot_state("ur5e_001")
print(f"Position: {state['position']}")
print(f"Joint Positions: {state['joint_states']['positions']}")
print(f"End Effector: {state['end_effector_pose']}")
```

### Collision Detection

```python
# Collisions are automatically detected
# Subscribe to collision events:
def on_collision(event):
    print(f"Collision detected on {event['robot_id']}")
    print(f"Force: {event['collision_force']} N")

connector.on_collision = on_collision
```

---

## Communication Protocol

See [COMMUNICATION_PROTOCOL.md](./COMMUNICATION_PROTOCOL.md) for complete specification.

### Message Format
```json
{
    "message_id": "uuid-v4",
    "timestamp": 1234567890.123,
    "message_type": "REQUEST|RESPONSE|EVENT|ERROR",
    "command": "command_name",
    "payload": {}
}
```

### Supported Commands

| Category | Commands |
|----------|----------|
| Connection | connect, disconnect, heartbeat |
| Robot Mgmt | spawn_robot, despawn_robot, list_robots, get_robot_state |
| Control | move_robot, set_joint_positions, set_joint_velocities, emergency_stop |
| Physics | set_physics_parameters, enable_collision, get_collision_status |
| Scene | add_obstacle, remove_obstacle, clear_scene |
| Camera | set_camera_view, capture_screenshot |
| Widget | create_widget, update_widget_data |
| File Import | import_robot_file |
| System | get_system_status |

---

## Supported Robot Models

All Universal Robots models from URDF examples:

| Model | Payload | Reach | Joints | Config Path |
|-------|---------|-------|--------|-------------|
| UR3   | 3 kg    | 500mm | 6 | `D:\ROA\universal_robot-Examples\ur_description\urdf\ur3.xacro` |
| UR3e  | 3 kg    | 500mm | 6 | `D:\ROA\universal_robot-Examples\ur_description\urdf\ur3e.xacro` |
| UR5   | 5 kg    | 850mm | 6 | `D:\ROA\universal_robot-Examples\ur_description\urdf\ur5.xacro` |
| UR5e  | 5 kg  | 850mm | 6 | `D:\ROA\universal_robot-Examples\ur_description\urdf\ur5e.xacro` |
| UR7e  | 7 kg    | 1100mm | 6 | `D:\ROA\universal_robot-Examples\ur_description\urdf\ur7e.xacro` |
| UR8long| 8 kg   | 1300mm | 6 | `D:\ROA\universal_robot-Examples\ur_description\urdf\ur8long.xacro` |
| UR10  | 10 kg   | 1300mm | 6 | `D:\ROA\universal_robot-Examples\ur_description\urdf\ur10.xacro` |
| UR10e | 10 kg   | 1300mm | 6 | `D:\ROA\universal_robot-Examples\ur_description\urdf\ur10e.xacro` |
| UR12e | 12 kg   | 1300mm | 6 | `D:\ROA\universal_robot-Examples\ur_description\urdf\ur12e.xacro` |
| UR15  | 15 kg   | 1500mm | 6 | `D:\ROA\universal_robot-Examples\ur_description\urdf\ur15.xacro` |
| UR16e | 16 kg   | 900mm | 6 | `D:\ROA\universal_robot-Examples\ur_description\urdf\ur16e.xacro` |
| UR18  | 18 kg   | 1800mm | 6 | `D:\ROA\universal_robot-Examples\ur_description\urdf\ur18.xacro` |
| UR20  | 20 kg   | 1750mm | 6 | `D:\ROA\universal_robot-Examples\ur_description\urdf\ur20.xacro` |
| UR30  | 30 kg   | 1300mm | 6 | `D:\ROA\universal_robot-Examples\ur_description\urdf\ur30.xacro` |

---

## Plugin Components

### Core Classes

| Class | Description |
|-------|-------------|
| `FROAModule` | Main plugin module (startup/shutdown) |
| `FROANetworkServer` | TCP server for Python communication |
| `FROAWorldManager` | Robot and scene management |
| `AROARobotActor` | UE5 actor representing a robot |
| `FROAMessage` | Message serialization/deserialization |

### File Structure

```
Plugins/ROA_PlugIn/
??? Source/ROA/
?   ??? ROA.Build.cs
?   ??? Public/
?   ?   ??? ROAModule.h
?   ?   ??? ROAMessageTypes.h
?   ?   ??? ROANetworkServer.h
?   ?   ??? ROAWorldManager.h
?   ?   ??? ROARobotActor.h
?   ??? Private/
?    ??? ROAModule.cpp
?       ??? ROAMessageTypes.cpp
?       ??? ROANetworkServer.cpp (in progress)
?       ??? ROAWorldManager.cpp (in progress)
?       ??? ROARobotActor.cpp (in progress)
??? Content/
??? Resources/
??? ROA.uplugin
??? README.md
??? COMMUNICATION_PROTOCOL.md
??? BUILD_PROGRESS.md
```

---

## Development Status

**Current Version:** 0.1.0-alpha

### Completed ?
- Plugin module structure
- Communication protocol specification
- Message serialization system
- Network server interface
- World manager interface
- Robot actor interface
- All 15 UR robot models supported

### In Progress ?
- Network server implementation
- World manager implementation
- Robot actor implementation
- URDF parser
- Mesh importer

### Planned ??
- Widget system
- Camera management
- Advanced physics
- Recording/playback
- Multi-robot coordination

---

## Troubleshooting

### Plugin Not Loading
- Check UE5 version (5.6+ required)
- Verify plugin is in `Plugins/` folder
- Regenerate project files
- Check Output Log for errors

### Connection Failed
- Verify port 9876 is not in use
- Check firewall settings
- Ensure Python Webthread is running
- Check Output Log: `ROA Plugin: Network Server started on port 9876`

### Robot Not Spawning
- Verify URDF path is correct
- Check robot type is valid (ur3, ur5, etc.)
- Ensure meshes are accessible
- Check Output Log for spawn errors

### Compilation Errors
- Clean and rebuild project
- Verify all dependencies are installed
- Check Visual Studio 2022 is installed
- Ensure Windows SDK is up to date

---

## Performance

### Recommended Settings
- **Max Robots:** 50 (hardware dependent)
- **Update Rate:** 30 Hz for robot states
- **Physics Rate:** 60 Hz (UE5 default)
- **Heartbeat:** Every 5 seconds
- **Command Timeout:** 30 seconds

### Optimization Tips
- Use LOD meshes for distant robots
- Reduce physics complexity when possible
- Batch state updates
- Use async communication

---

## Contributing

This is a proprietary plugin for the ROA project. For contributions:
1. Follow UE5 coding standards
2. Add unit tests for new features
3. Update documentation
4. Submit pull request to main repository

---

## License

Copyright © 2025 ROA Development Team. All Rights Reserved.

This plugin is part of the Robot Operator Assistant project and is proprietary software.

---

## Support

- **GitHub:** https://github.com/Omar-Galal-AB/ROA
- **Documentation:** See `docs/` folder
- **Issues:** GitHub Issues

---

## Changelog

### v0.1.0-alpha (Current)
- Initial alpha release
- Core plugin structure
- Communication protocol
- Basic robot support
- Network layer foundation

---

**For detailed technical documentation, see:**
- [COMMUNICATION_PROTOCOL.md](./COMMUNICATION_PROTOCOL.md) - Protocol specification
- [BUILD_PROGRESS.md](./BUILD_PROGRESS.md) - Development status

**End of README**
