# ROC Standalone Desktop Application

A standalone Qt6 desktop application for controlling robots through the ROA Robot Operator Controller.

## Features

- **Dual Control Modes**: RPM (manual) and ADM (autonomous) control
- **Universal Robot Support**: Works with any robot type imported through FTI
- **Joint Control**: 6-DOF arm control with real-time sliders
- **Gripper Control**: Precise gripper positioning
- **Safety Monitoring**: Three-level safety system with visual alerts
- **Path Planning**: A* and RRT algorithms for autonomous navigation
- **Multi-Robot Support**: Control multiple robots (up to 8+)
- **Performance Monitoring**: Real-time latency and resource tracking

## Requirements

- Python 3.10+
- PyQt6
- NumPy
- SciPy (for path planning)
- pyyaml

## Installation

```bash
# Install dependencies
pip install -r ../requirements.txt
```

## Usage

### Linux/Mac:
```bash
./run_roc.sh
```

### Windows:
```bash
python roc_desktop.py
```

### Manual:
```bash
cd components/robot-operator-controller/standalone
python3 roc_desktop.py
```

## User Interface

### Left Panel: Robot Selection & Safety
- **Robot Selector**: Choose active robot from imported list
- **Safety Monitor**: View safety level and system alerts
- **Status Indicators**: Collision detection, path clear, limits

### Center Panel: Joint Control
- **Control Mode**: Switch between RPM and ADM
- **Joint Sliders**: 6 configurable joint controls (-180° to +180°)
- **Gripper Control**: 0-100% opening
- **Quick Actions**: Home position, Emergency stop

### Right Panel: Advanced Features
- **Path Planning**: Calculate trajectories with A* or RRT
- **Console**: View system logs and events
- **Performance**: Monitor control loop, latency, resources

## Control Modes

### RPM Mode (Role Playing Mode)
- Direct manual control with sliders
- Keyboard/mouse input support
- Real-time joint position feedback
- Immediate response (<20ms latency target)

### ADM Mode (Auto Driven Mode)
- Strategic autonomous control
- Path planning integration
- Multi-robot coordination
- High-level task commands

## Safety System

Three configurable safety levels:

1. **Fragile**: Maximum protection, slow speeds, large margins
2. **Standard**: Balanced protection and performance (default)
3. **Robust**: Minimal protection, maximum performance

Visual indicators show:
- Collision detection status
- Path clearance
- Joint limits
- Emergency stop readiness

## Path Planning

### A* Algorithm
- Grid-based pathfinding
- Optimal paths guaranteed
- Good for structured environments

### RRT Algorithm
- Sampling-based approach
- Better for complex obstacles
- Faster computation for high-DOF

**Usage:**
1. Select algorithm
2. Set target position (X, Y, Z)
3. Click "Calculate Path"
4. Review path information
5. Execute (in future versions)

## Keyboard Shortcuts

*(To be implemented)*
- `Space`: Emergency stop
- `H`: Home position
- `R/A`: Switch RPM/ADM mode
- `1-6`: Select joint for keyboard control
- `+/-`: Adjust selected joint

## Architecture

```
┌──────────────────────────────────┐
│  ROC Desktop App (Qt)            │
│  ┌────────────────────────────┐  │
│  │ ControlThread              │  │
│  │ (20Hz control loop)        │  │
│  └────────────────────────────┘  │
│          ↓                        │
│  ┌────────────────────────────┐  │
│  │ ROC ROS2 Node              │  │
│  │ (Robot control logic)      │  │
│  └────────────────────────────┘  │
└──────────────────────────────────┘
         ↓
    ROS2 Topics
         ↓
    Robot Hardware
```

## Integration with ROA System

The standalone app integrates with:
- **FTI**: Import robot specifications
- **DIMC**: Receive spatial data for collision avoidance
- **COMC**: Coordinate with other robots
- **Webthread**: System monitoring and configuration

## Dual-Mode Design

ROC is designed for dual operation:

1. **Standalone Mode**: This Qt desktop application
   - Full control capabilities
   - Independent of UE5
   - Ideal for development and testing

2. **Integrated Mode**: UE5 widgets (future implementation)
   - In-engine control
   - Visual feedback in 3D
   - Better for simulation

## Troubleshooting

**App won't start:**
- Install PyQt6: `pip install PyQt6`
- Check Python 3.10+: `python3 --version`

**No robots available:**
- Import robots using FTI first
- Check ROS2 connection
- Verify robot specifications published on `/fti/robot_specs`

**Joint controls not working:**
- Verify RPM mode is selected
- Check safety system isn't blocking motion
- Review console for errors

**Path planning fails:**
- Ensure target position is reachable
- Check for obstacles in path
- Try different algorithm

## Development

Built with PyQt6, the app uses:
- **MVC pattern**: Separate UI and logic
- **Threading**: Background control loop
- **Signals/Slots**: Event handling
- **Modular widgets**: Reusable components

Extends existing ROC Python modules:
- `roc_ros2_node.py`
- `controllers/`
- `control_modes/`
- `path_planning/`

## Future Enhancements

- [ ] 3D visualization of robot
- [ ] Teach pendant mode
- [ ] Task recording/playback
- [ ] Multi-robot formation control
- [ ] VR/AR integration
- [ ] Mobile companion app

## License

Part of the ROA project.
