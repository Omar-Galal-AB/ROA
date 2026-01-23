# ROC Design Phase Summary

## Overview

This document summarizes all design artifacts created for the Robot Operator Controller (ROC) component during the design phase. **No implementation has been performed yet** - these files provide the complete blueprint for building the ROC hybrid architecture.

---

## Architecture Decision

**Chosen Approach: Hybrid Architecture**

| Component | Platform | Responsibilities |
|-----------|----------|------------------|
| **UE5 ROC Plugin** | Windows | Joint motor control, widget UI, real-time execution |
| **Linux ROC Module** | WSL Linux | Safety validation, FTI/DIMC integration, ROS2 bridge |

### Why Hybrid?

1. **UE5 handles realtime**: Direct physics constraint control without network latency
2. **Linux handles safety**: All commands validated before execution
3. **No ROS2 delay for joints**: Direct IPC avoids ROS2 transport overhead
4. **Existing infrastructure**: Uses established dual-port TCP bridge (9876/9877)

---

## Created Files Summary

### 1. Requirement Documents (`/home/myws/roa/docs/`)

| File | Purpose | Key Content |
|------|---------|-------------|
| [ROC_REQUIREMENTS_FROM_FTI.md](../../docs/ROC_REQUIREMENTS_FROM_FTI.md) | What FTI must export for ROC | `ue5_constraint_name`, joint limits, kinematic chain |
| [ROC_REQUIREMENTS_FROM_DIMC.md](../../docs/ROC_REQUIREMENTS_FROM_DIMC.md) | What DIMC must provide at runtime | Joint states @60Hz, obstacles @20Hz, boundaries @10Hz |

### 2. Design Documents (`docs/`)

| File | Purpose | Key Content |
|------|---------|-------------|
| [UE5_ROC_PLUGIN_DESIGN.md](UE5_ROC_PLUGIN_DESIGN.md) | UE5 C++ plugin architecture | `ROCSubsystem`, `RobotController`, widget blueprints |
| [LINUX_ROC_MODULE_DESIGN.md](LINUX_ROC_MODULE_DESIGN.md) | Python module architecture | `ipc_handler`, `robot_state`, `command_validator` |

### 3. Configuration Files (`Config/`)

| File | Purpose | Key Settings |
|------|---------|--------------|
| [ipc_protocol.yaml](../Config/ipc_protocol.yaml) | IPC message definitions | All UE5↔Linux message types with examples |
| [validation_config.yaml](../Config/validation_config.yaml) | Safety validation rules | Position/velocity limits, collision thresholds |
| [widget_config.yaml](../Config/widget_config.yaml) | UI widget settings | Slider appearance, keyboard bindings, colors |
| [registry_config.yaml](../Config/registry_config.yaml) | Robot registry settings | Max robots, update rates, FTI/DIMC integration |

### 4. Test Scaffolding (`tests/`)

| File | Purpose | Test Count |
|------|---------|------------|
| [test_ipc_handler.py](../tests/test_ipc_handler.py) | IPC connection & messaging tests | ~25 tests |
| [test_command_validator.py](../tests/test_command_validator.py) | Validation pipeline tests | ~30 tests |
| [test_robot_state.py](../tests/test_robot_state.py) | Robot state management tests | ~30 tests |
| [test_mode_manager.py](../tests/test_mode_manager.py) | Mode switching tests | ~20 tests |
| [conftest.py](../tests/conftest.py) | Shared fixtures & utilities | Fixtures, helpers |

---

## Module Structure (After Implementation)

### UE5 Plugin (C++)

```
Plugins/ROA_PlugIn/Source/ROA/
├── Public/
│   ├── ROC/
│   │   ├── ROCSubsystem.h          # Game instance subsystem
│   │   ├── ROCTypes.h              # Shared enums, structs
│   │   ├── RobotController.h       # Per-robot controller
│   │   └── JointController.h       # Per-joint motor control
├── Private/
│   ├── ROC/
│   │   ├── ROCSubsystem.cpp
│   │   ├── RobotController.cpp
│   │   └── JointController.cpp
└── Widgets/
    └── WBP_RobotControlPanel       # Widget Blueprint
```

### Linux Module (Python)

```
robot-operator-controller/
├── src/python/
│   ├── ue5_bridge/
│   │   ├── __init__.py
│   │   ├── ipc_handler.py          # TCP communication
│   │   └── command_validator.py    # Validation pipeline
│   ├── robot_registry/
│   │   ├── __init__.py
│   │   ├── robot_state.py          # Per-robot state
│   │   └── robot_manager.py        # Multi-robot coordination
│   ├── safety/
│   │   ├── __init__.py
│   │   └── limit_checker.py        # Joint limit validation
│   └── control_modes/
│       ├── __init__.py
│       └── mode_manager.py         # RPM/ADM switching
```

---

## IPC Message Flow

```
┌──────────────────────────────────────────────────────────────┐
│                    UE5 → Linux (Port 9876)                   │
├──────────────────────────────────────────────────────────────┤
│  joint_command_request  │ Request to move joint(s)          │
│  emergency_stop         │ Immediate halt all motion          │
│  mode_change           │ Switch RPM ↔ ADM                    │
│  robot_registered      │ New robot spawned in UE5            │
│  heartbeat             │ Keep-alive signal                   │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                    Linux → UE5 (Port 9877)                   │
├──────────────────────────────────────────────────────────────┤
│  command_approved      │ Command passed safety checks        │
│  command_rejected      │ Command failed validation           │
│  safety_alert          │ Warning or notification             │
│  state_update          │ Periodic status update              │
│  heartbeat_ack         │ Acknowledge heartbeat               │
└──────────────────────────────────────────────────────────────┘
```

---

## Integration Points

### FTI Integration (Robot Import)

```python
# When FTI imports a robot, it publishes to:
topic = "/fti/robot_specs"
# ROC subscribes and creates RobotState from spec
```

**Required fields from FTI:**
- `robot_id`, `robot_name`
- `joints[].name`, `joints[].type`, `joints[].limits`
- `joints[].ue5_constraint_name` (NEW - FTI must add this)

### DIMC Integration (Runtime Data)

```python
# ROC subscribes to DIMC topics:
joint_states_topic = "/dimc/{robot_id}/joint_states"  # 60 Hz
obstacles_topic = "/dimc/{robot_id}/obstacles"        # 20 Hz
boundaries_topic = "/dimc/{robot_id}/boundaries"      # 10 Hz
```

**Required fields from DIMC:**
- Joint positions, velocities, efforts per joint (NEW - DIMC currently only tracks robot-level)
- Obstacle positions and distances
- Boundary status

---

## Safety Validation Pipeline

```
Command from UE5
      │
      ▼
┌─────────────────┐
│ E-Stop Active?  │──Yes──► REJECT (emergency_stop_active)
└────────┬────────┘
         │No
         ▼
┌─────────────────┐
│ Position Limits │──Fail──► REJECT or CLAMP
└────────┬────────┘
         │Pass
         ▼
┌─────────────────┐
│ Velocity Limits │──Fail──► REDUCE velocity
└────────┬────────┘
         │Pass
         ▼
┌─────────────────┐
│ Collision Check │──Risk──► STOP or SLOW
└────────┬────────┘
         │Clear
         ▼
┌─────────────────┐
│ Boundary Check  │──Violation──► CLAMP to boundary
└────────┬────────┘
         │OK
         ▼
    APPROVED ✓
```

---

## Control Modes

| Mode | Full Name | Description |
|------|-----------|-------------|
| **RPM** | Remote Position Mode | Manual control via sliders/keyboard |
| **ADM** | Autonomous Decision Mode | Automated control (planned paths) |

### Mode Transition Rules

- **RPM → ADM**: Requires robot stopped, no obstacles < 50cm
- **ADM → RPM**: Always allowed when robot stopped
- **E-Stop → RPM**: Must clear E-Stop first, then back to RPM

---

## Next Steps (Implementation Phase)

When you're ready to implement, follow this order:

### Phase 1: Linux Core (Python)
1. Create `ue5_bridge/ipc_handler.py`
2. Create `robot_registry/robot_state.py`
3. Create `safety/limit_checker.py`
4. Create `ue5_bridge/command_validator.py`
5. Create `control_modes/mode_manager.py`
6. Create `robot_registry/robot_manager.py`
7. Integrate with existing `roc_ros2_node.py`

### Phase 2: UE5 Plugin (C++)
1. Create `ROCTypes.h` (enums, structs)
2. Create `ROCSubsystem` (game subsystem)
3. Create `JointController` (motor control)
4. Create `RobotController` (robot coordination)
5. Create Widget Blueprint
6. Integrate with existing FTI plugin

### Phase 3: Integration Testing
1. Run test scaffolding
2. Test IPC round-trip
3. Test safety pipeline
4. Test mode switching
5. End-to-end robot control test

---

## File Locations Quick Reference

```
/home/myws/roa/
├── docs/
│   ├── ROC_REQUIREMENTS_FROM_FTI.md    # FTI team requirements
│   └── ROC_REQUIREMENTS_FROM_DIMC.md   # DIMC team requirements
│
└── roa_linux/roa-core/lib/components/robot-operator-controller/
    ├── docs/
    │   ├── UE5_ROC_PLUGIN_DESIGN.md    # UE5 C++ design
    │   ├── LINUX_ROC_MODULE_DESIGN.md  # Python module design
    │   └── ROC_DESIGN_SUMMARY.md       # This file
    ├── Config/
    │   ├── ipc_protocol.yaml           # Message definitions
    │   ├── validation_config.yaml      # Safety thresholds
    │   ├── widget_config.yaml          # UI configuration
    │   └── registry_config.yaml        # Robot registry config
    └── tests/
        ├── conftest.py                 # Shared fixtures
        ├── test_ipc_handler.py         # IPC tests
        ├── test_command_validator.py   # Validation tests
        ├── test_robot_state.py         # State management tests
        └── test_mode_manager.py        # Mode switching tests
```

---

## Design Constraints Reminder

⚠️ **IMPORTANT**: During this design phase, NO modifications were made to existing ROA files. All new files were created in the `robot-operator-controller/` folder only, as required due to concurrent workspace usage.

---

*Design phase completed. Awaiting implementation approval.*
