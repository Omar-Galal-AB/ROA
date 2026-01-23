# ROC - Robot Operator Controller

**Component 3 of 5** in the ROA (Robot Operations & Automation) System

[![Status](https://img.shields.io/badge/Status-Ready%20for%20Implementation-green.svg)]()
[![ROS2](https://img.shields.io/badge/ROS2-Humble-blue.svg)]()
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)]()
[![C++](https://img.shields.io/badge/C++-17-blue.svg)]()

---

## Overview

**ROC** (Robot Operator Controller) is a universal robot control system that supports all robot types through an adaptive, plugin-based architecture. It features dual control modes for both manual precision control and autonomous strategic operations.

### Key Features

🎮 **Dual Control Modes**
- **RPM** (Role Playing Mode): Direct manual control with keyboard/mouse
- **ADM** (Auto Driven Mode): RTS-style strategic autonomous control

🤖 **Universal Robot Support**
- Adaptive to any robot type without custom programming
- Industrial arms, mobile robots, hybrid systems, aerial platforms
- Dynamic feature detection and UI adjustment

⚡ **Real-Time Performance**
- <20ms control loop latency
- 60Hz state update rate
- Dedicated real-time control thread

🛡️ **Three-Level Safety System**
- Fragile, Standard, Robust safety levels
- Collision detection on all robot parts
- Auto-stop and visual warnings

🎯 **Multi-Robot Coordination**
- Control up to 8+ robots (optimized for 4)
- Individual or formation control
- Mixed-mode operation (some RPM, some ADM)

📊 **Intelligent Path Planning**
- A* and RRT algorithms
- Real-time re-planning on obstacles
- Integration with Evade subsystem

---

## Architecture

### Component Structure

```
robot-operator-controller/
├── src/
│   ├── python/                    # ROS2 interface and control logic
│   │   ├── roc_ros2_node.py      # Main ROS2 node
│   │   ├── controllers/           # Individual robot part controllers
│   │   │   ├── __init__.py
│   │   │   ├── base_controller.py
│   │   │   ├── arm_controller.py
│   │   │   ├── gripper_controller.py
│   │   │   └── mobile_controller.py
│   │   ├── control_modes/         # RPM and ADM implementations
│   │   │   ├── __init__.py
│   │   │   ├── rpm_mode.py
│   │   │   └── adm_mode.py
│   │   ├── safety/                # Safety management
│   │   │   ├── __init__.py
│   │   │   ├── safety_manager.py
│   │   │   └── collision_detector.py
│   │   ├── path_planning/         # Autonomous navigation
│   │   │   ├── __init__.py
│   │   │   ├── a_star.py
│   │   │   └── rrt_planner.py
│   │   └── command_queue.py       # Task queue management
│   └── cpp/                       # UE5 integration
│       ├── RobotController.h
│       ├── RobotController.cpp
│       ├── UI/                    # UE5 UI widgets
│       │   ├── ControllerWidget.h
│       │   ├── ControllerWidget.cpp
│       │   ├── SliderControls.h
│       │   ├── SliderControls.cpp
│       │   ├── RobotSelector.h
│       │   └── RobotSelector.cpp
│       └── Safety/
│           ├── CollisionDetector.h
│           └── CollisionDetector.cpp
├── tests/                         # Unit and integration tests
│   ├── test_controllers.py
│   ├── test_rpm_mode.py
│   ├── test_adm_mode.py
│   ├── test_safety.py
│   └── test_path_planning.py
├── Config/                        # Configuration files
│   ├── roc_config.yaml           # Main configuration
│   ├── safety_levels.yaml        # Safety level definitions
│   └── control_mappings.yaml     # Input control mappings
├── UI/                            # UE5 UI assets
│   └── Widgets/
│       └── WBP_ROC_Controller.uasset
├── docs/                          # Documentation
│   ├── ROC_ANALYSIS.md           # Comprehensive analysis
│   ├── INTEGRATION_GUIDE.md      # Integration specifications
│   └── API_REFERENCE.md          # API documentation
└── README.md                      # This file
```

### Control Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     User Input Layer                         │
│  Keyboard/Mouse (RPM) | Strategic Commands (ADM)            │
└───────────────────────┬─────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│                    ROC Control Interface                     │
│  ┌──────────────┐              ┌──────────────┐            │
│  │  RPM Mode    │              │  ADM Mode    │            │
│  │ - Direct Ctrl│              │ - Task Queue │            │
│  │ - Sliders    │              │ - Path Plan  │            │
│  └──────┬───────┘              └──────┬───────┘            │
│         └──────────────┬───────────────┘                    │
└────────────────────────┼────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│                  Safety Validation Layer                     │
│  - Boundary Checking                                         │
│  - Collision Detection                                       │
│  - Safety Level Enforcement                                  │
└───────────────────────┬─────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│                   ROS2 Control Framework                     │
│  Hardware Interface → Controller Manager → Controllers       │
└───────────────────────┬─────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│                      Robot Actuators                         │
│  Joints | Motors | Grippers | Mobile Base                   │
└─────────────────────────────────────────────────────────────┘
```

### State Machine

```
DISCONNECTED
    ↓
CONNECTING ──[timeout]──> ERROR
    ↓
IDLE
    ↓
    ├──[RPM selected]──> RPM_ACTIVE ──> MOVING ──┐
    │                                             │
    └──[ADM selected]──> ADM_ACTIVE ──> EXECUTING ┤
                                                  │
                                                  ↓
                                          ┌───> IDLE
                                          │
                                    [collision/error]
                                          ↓
                                        ERROR
                                          ↓
                                        RESET
                                          ↓
                                        CHECK
                                          ↓
                                    IDLE/SHUTDOWN
```

---

## Control Modes

### RPM (Role Playing Mode)

**Direct manual control for precision operations**

**Features**:
- Real-time keyboard/mouse input (<10ms response)
- Slider-based control interface
- WASD movement, arrow keys for gripper
- Right-click for 6-DOF gripper freedom
- Visual position/orientation feedback
- Safety warnings with yellow indicators

**Use Cases**:
- Precision manipulation tasks
- Learning robot capabilities
- Troubleshooting and diagnostics
- Tasks requiring human judgment

**Input Controls**:
```
Movement:      W A S D
Gripper Arm:   Arrow Keys (↑↓←→)
Close Grip:    C
Open Grip:     V
Extend/Retract: E / Q
Rotate:        Y / U
Return Home:   R
E-Stop:        Space
```

### ADM (Auto Driven Mode)

**Strategic autonomous control for efficiency**

**Features**:
- High-level task commands
- Autonomous path planning (A*, RRT)
- Multi-step task execution
- Automatic obstacle avoidance
- Multi-robot coordination
- Command queuing with priorities

**Use Cases**:
- Repetitive construction tasks
- Multi-robot coordinated operations
- Efficiency-focused work
- Minimal supervision required

**Command Menu**:
```
[M] Move to Location
[P] Pick Object
[L] Place Object
[F] Follow Path
[G] Form Group (multi-robot)
[R] Return to Base
[H] Halt Current Task
```

---

## Safety System

### Three Safety Levels

| Level | Speed | Safety Margin | Use Case |
|-------|-------|---------------|----------|
| **Fragile** | 60% | 10mm | Delicate objects, precision work |
| **Standard** | 100% | 5mm | Normal operations, default |
| **Robust** | 100%+ | 2mm | Heavy construction, speed priority |

### Safety Features

✅ **Collision Detection**
- Sensors on ALL robot parts
- Real-time collision checking at 60Hz
- Integration with DIMC obstacle detection

✅ **Auto-Stop**
- Immediate halt on collision
- Emergency stop via Space key
- Graceful stop with deceleration

✅ **Visual Warnings**
- Yellow sign when obstacle detected (inactive robot)
- Entire UI turns yellow when active and obstacle near
- Distance indicators to other robots

✅ **Boundary Enforcement**
- Workspace limits from DIMC
- Safety margin calculation
- User override with confirmation

---

## Integration Points

### Inputs from Other Components

#### FTI (Files Type Importer)
- **Data**: Robot joint definitions, structure, capabilities
- **Format**: JSON metadata
- **Frequency**: On robot import (one-time)
- **Usage**: Configure adaptive UI, enable/disable features

#### DIMC (Dimensions Collector)
- **Data**: Robot positions, orientations, boundaries, obstacles
- **Format**: ROS2 custom messages
- **Frequency**: 60Hz continuous updates
- **Usage**: Safety checking, position display, collision avoidance

#### COMC (Communication Center)
- **Data**: Other robots' status, work areas, coordination requests
- **Format**: ROS2 DDS messages
- **Frequency**: 20Hz for broadcasts, real-time for alerts
- **Usage**: Multi-robot coordination, collision avoidance

#### Webthread
- **Data**: Component status, configuration updates, error notifications
- **Format**: ROS2 services and topics
- **Frequency**: Health checks every 1s, on-demand updates
- **Usage**: System coordination, configuration, error handling

### Outputs to Other Components

#### Robots (via ROS2 Control)
- **Data**: Position/velocity/torque commands, gripper control, emergency stop
- **Format**: ROS2 Control messages
- **Frequency**: 60Hz control loop
- **Purpose**: Execute robot movements and tasks

#### Webthread
- **Data**: Component health, active mode, command history, errors
- **Format**: ROS2 topics and services
- **Frequency**: Status every 1s, events immediately
- **Purpose**: System monitoring, logging, error reporting

#### DIMC
- **Data**: Target positions, safety margin requests
- **Format**: ROS2 messages
- **Frequency**: On command execution
- **Purpose**: Collision prediction, safe operation

#### COMC
- **Data**: Robot intentions, work area requests
- **Format**: ROS2 DDS messages
- **Frequency**: On task start, 5Hz during execution
- **Purpose**: Multi-robot coordination, collision avoidance

---

## Configuration

### Main Configuration (`roc_config.yaml`)

```yaml
roc:
  node_name: "robot_operator_controller"
  update_rate: 60  # Hz
  
  control:
    latency_target: 20  # milliseconds
    max_robots: 8
    default_mode: "RPM"
  
  safety:
    default_level: "Standard"
    emergency_stop_decel: 2.0  # m/s²
    collision_check_rate: 60  # Hz
  
  path_planning:
    algorithm: "A*"  # A* or RRT
    max_planning_time: 5.0  # seconds
    replanning_rate: 2  # Hz
  
  ui:
    interface_type: "standalone"  # standalone or ue5_widget
    update_rate: 30  # FPS
    show_overlay: true
```

### Safety Levels (`safety_levels.yaml`)

```yaml
safety_levels:
  Fragile:
    speed_multiplier: 0.6
    safety_margin: 0.01  # meters (10mm)
    collision_sensitivity: "high"
    auto_stop_distance: 0.05  # meters
  
  Standard:
    speed_multiplier: 1.0
    safety_margin: 0.005  # meters (5mm)
    collision_sensitivity: "medium"
    auto_stop_distance: 0.03  # meters
  
  Robust:
    speed_multiplier: 1.2
    safety_margin: 0.002  # meters (2mm)
    collision_sensitivity: "low"
    auto_stop_distance: 0.02  # meters
```

### Control Mappings (`control_mappings.yaml`)

```yaml
rpm_mode:
  keyboard:
    movement:
      forward: 'W'
      left: 'A'
      backward: 'S'
      right: 'D'
    gripper_arm:
      up: 'Up'
      down: 'Down'
      left: 'Left'
      right: 'Right'
    gripper:
      close: 'C'
      open: 'V'
      extend: 'E'
      retract: 'Q'
      rotate_left: 'Y'
      rotate_right: 'U'
    quick_actions:
      return_home: 'R'
      emergency_stop: 'Space'
      switch_robot: 'Tab'
  
adm_mode:
  keyboard:
    camera:
      forward: 'W'
      left: 'A'
      backward: 'S'
      right: 'D'
    selection:
      up: 'Up'
      down: 'Down'
      left: 'Left'
      right: 'Right'
    commands:
      move: 'M'
      pick: 'P'
      place: 'L'
      follow: 'F'
      group: 'G'
      return: 'R'
      halt: 'H'
```

---

## API Reference

### ROS2 Node: `robot_operator_controller`

#### Published Topics

| Topic | Type | Rate | Description |
|-------|------|------|-------------|
| `/roc/status` | `roc_msgs/ROCStatus` | 1 Hz | Component health and mode |
| `/roc/robot_state` | `roc_msgs/RobotState` | 60 Hz | Current robot state |
| `/roc/command_feedback` | `roc_msgs/CommandFeedback` | On-event | Command execution status |

#### Subscribed Topics

| Topic | Type | Rate | Description |
|-------|------|------|-------------|
| `/fti/robot_specs` | `fti_msgs/RobotSpecs` | On-import | Robot specifications |
| `/dimc/spatial_data` | `dimc_msgs/SpatialData` | 60 Hz | Position and boundary data |
| `/comc/robot_status` | `comc_msgs/RobotStatus` | 20 Hz | Other robots' status |
| `/webthread/config_update` | `std_msgs/String` | On-demand | Configuration changes |

#### Services

| Service | Type | Description |
|---------|------|-------------|
| `/roc/set_mode` | `roc_srvs/SetMode` | Switch between RPM/ADM |
| `/roc/set_safety_level` | `roc_srvs/SetSafetyLevel` | Change safety level |
| `/roc/queue_command` | `roc_srvs/QueueCommand` | Add task to queue |
| `/roc/emergency_stop` | `std_srvs/Trigger` | Immediate emergency stop |
| `/roc/health_check` | `std_srvs/Trigger` | Component health status |

#### Actions

| Action | Type | Description |
|--------|------|-------------|
| `/roc/execute_path` | `roc_actions/ExecutePath` | Execute planned path |
| `/roc/execute_task` | `roc_actions/ExecuteTask` | Execute high-level task |

---

## Usage Examples

### Example 1: Start ROC Node

```bash
# Start the ROC ROS2 node
ros2 run robot_operator_controller roc_ros2_node

# With custom config
ros2 run robot_operator_controller roc_ros2_node --ros-args \
  --params-file /path/to/custom_config.yaml
```

### Example 2: Switch to ADM Mode (Python)

```python
import rclpy
from rclpy.node import Node
from roc_srvs.srv import SetMode

class ModeChanger(Node):
    def __init__(self):
        super().__init__('mode_changer')
        self.client = self.create_client(SetMode, '/roc/set_mode')
        
    def switch_to_adm(self):
        request = SetMode.Request()
        request.mode = 'ADM'
        request.robot_id = 'robot_1'
        
        future = self.client.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        
        if future.result().success:
            self.get_logger().info('Switched to ADM mode')
        else:
            self.get_logger().error(f'Failed: {future.result().message}')

# Usage
rclpy.init()
changer = ModeChanger()
changer.switch_to_adm()
rclpy.shutdown()
```

### Example 3: Queue a Task (Command Line)

```bash
# Queue a move task in ADM mode
ros2 service call /roc/queue_command roc_srvs/QueueCommand \
  "{robot_id: 'robot_1', 
    task_type: 'move', 
    target_position: {x: 1.0, y: 2.0, z: 0.0}, 
    priority: 'normal'}"
```

### Example 4: Emergency Stop

```bash
# Trigger emergency stop for all robots
ros2 service call /roc/emergency_stop std_srvs/Trigger
```

---

## Performance Targets

| Metric | Target | Critical |
|--------|--------|----------|
| Control loop latency | <20ms avg | Yes |
| Input response time | <10ms | Yes |
| Mode switch time | <500ms | No |
| Frame rate (4 robots) | 30+ FPS | No |
| Memory usage | <4GB | No |
| CPU usage | <80% | No |
| Path planning time | <5s | No |
| Safety check rate | 60 Hz | Yes |

---

## Testing

### Run Unit Tests

```bash
# Run all tests
cd components/robot-operator-controller
python3 -m pytest tests/

# Run specific test file
python3 -m pytest tests/test_rpm_mode.py

# Run with coverage
python3 -m pytest --cov=src/python tests/
```

### Run Integration Tests

```bash
# Launch test environment
ros2 launch robot_operator_controller test_integration.launch.py

# Run integration tests
python3 -m pytest tests/integration/
```

### Performance Testing

```bash
# Benchmark control loop latency
ros2 run robot_operator_controller benchmark_latency

# Stress test with multiple robots
ros2 run robot_operator_controller stress_test --robots 8
```

---

## Development Status

### Phase 1: Foundation ⏳
- [ ] Directory structure
- [ ] ROS2 node skeleton
- [ ] Base controller class
- [ ] State machine
- [ ] Configuration loading
- [ ] Health monitoring

### Phase 2: RPM Mode ⏳
- [ ] RPM mode implementation
- [ ] Slider controls
- [ ] Keyboard input handling
- [ ] Safety integration
- [ ] Collision detection

### Phase 3: ADM Mode ⏳
- [ ] ADM mode implementation
- [ ] Path planning (A*, RRT)
- [ ] Task queue system
- [ ] Command menu

### Phase 4: Multi-Robot ⏳
- [ ] Robot selection
- [ ] Multi-robot state management
- [ ] Formation control
- [ ] Mixed-mode operation

### Phase 5: Safety & Polish ⏳
- [ ] Safety level system
- [ ] Visual warnings
- [ ] UE5 UI widgets
- [ ] UI overlay

### Phase 6: Integration ⏳
- [ ] FTI integration
- [ ] DIMC integration
- [ ] COMC integration
- [ ] Webthread integration

---

## Documentation

- **[ROC_ANALYSIS.md](docs/ROC_ANALYSIS.md)** - Comprehensive analysis of 18 documentation files
- **[INTEGRATION_GUIDE.md](docs/INTEGRATION_GUIDE.md)** - Integration with other components (TBD)
- **[API_REFERENCE.md](docs/API_REFERENCE.md)** - Complete API documentation (TBD)
- **[USER_GUIDE.md](docs/USER_GUIDE.md)** - User manual for operators (TBD)

---

## Dependencies

### Required
- **ROS2 Humble LTS** - Core framework
- **Python 3.10+** - Python components
- **C++17 compiler** - C++ components
- **ros2_control** - Robot control framework
- **Unreal Engine 5.6+** - UI widgets (optional for standalone)

### Optional
- **OMPL** - Advanced path planning
- **MoveIt2** - Motion planning integration
- **rqt** - Visualization and debugging

---

## Contributing

See main [CONTRIBUTING.md](../../CONTRIBUTING.md) for contribution guidelines.

---

## License

To be determined - See main [LICENSE](../../LICENSE)

---

## References

- **ROS2 Control**: https://control.ros.org/
- **ROS2 Humble**: https://docs.ros.org/en/humble/
- **Unreal Engine 5**: https://docs.unrealengine.com/5.0/
- **OMPL**: https://ompl.kavrakilab.org/

---

**Component Status**: Ready for Implementation  
**Last Updated**: 2025-11-16  
**Maintainer**: ROA Development Team
