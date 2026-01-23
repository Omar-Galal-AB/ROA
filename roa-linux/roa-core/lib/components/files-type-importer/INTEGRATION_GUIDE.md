# FTI Integration Guide

## Overview

This document describes how the Files Type Importer (FTI) integrates with Webthread and other ROA components (DIMC, ROC, COMC).

---

## Integration Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     WEBTHREAD (Coordinator)                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │          Component Startup Orchestration              │  │
│  │  Phase 3: FTI → DIMC → ROC → COMC → Runtime         │  │
│  └──────────────────────────────────────────────────────┘  │
│                           ↓                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              ROS2 Communication Layer                 │  │
│  │  Topics: status, commands, results                   │  │
│  │  Services: check_status, validate_file               │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                   FTI (Files Type Importer)                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            fti_ros2_node.py (ROS2 Node)              │  │
│  │  - Subscribes to: fti/import_command                 │  │
│  │  - Publishes to: fti/status, fti/import_result       │  │
│  │  - Services: fti/check_status                        │  │
│  └──────────────────────────────────────────────────────┘  │
│                           ↓                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │        file_type_importer.py (Core Logic)            │  │
│  │  - Format detection                                   │  │
│  │  - Conversion pipeline (URDF/STL/OBJ → USD)          │  │
│  │  - Hierarchy builder                                  │  │
│  │  - Validation & fallback                              │  │
│  └──────────────────────────────────────────────────────┘  │
│                           ↓                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │      fti_data_export.py (Data Export Layer)          │  │
│  │  - Export for DIMC (hierarchy, parts)                │  │
│  │  - Export for ROC (joint definitions)                │  │
│  │  - Export for Webthread (status)                     │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
           ↓                    ↓                    ↓
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│      DIMC       │  │       ROC       │  │       UE5       │
│ (Dimensions)    │  │   (Control)     │  │  (Rendering)    │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

---

## ROS2 Interface Specification

### Topics

#### 1. `fti/status` (Publisher)
- **Type**: `std_msgs/String` (JSON)
- **QoS**: Default
- **Purpose**: Publishes FTI status and capabilities
- **Message Format**:
```json
{
  "component": "FTI",
  "status": "ready|importing|error",
  "supported_formats": ["urdf", "stl", "obj", ...]
}
```

#### 2. `fti/import_command` (Subscriber)
- **Type**: `std_msgs/String` (JSON)
- **QoS**: Reliable
- **Purpose**: Receives import commands from Webthread
- **Message Format**:
```json
{
  "command": "import_robot",
  "file_path": "/path/to/robot.urdf",
  "robot_name": "ConstructionArm",
  "import_mode": "both"
}
```

#### 3. `fti/import_result` (Publisher)
- **Type**: `std_msgs/String` (JSON)
- **QoS**: Reliable
- **Purpose**: Publishes import results
- **Message Format**:
```json
{
  "success": true,
  "robot_name": "ConstructionArm",
  "content_path": "/Game/Robots/ConstructionArm",
  "parts_count": 5,
  "assembly_path": "/tmp/ConstructionArm.usd",
  "parts_paths": ["link1", "link2", ...],
  "error_message": null,
  "warnings": []
}
```

### Services

#### 1. `fti/check_status` (Server)
- **Type**: `std_srvs/Trigger`
- **Purpose**: Health check service for Webthread monitoring
- **Response**:
```
success: true/false
message: JSON with status details
```

---

## Integration with Webthread

### Startup Sequence (Phase 3)

**Step 1: Webthread Initialization**
```python
# In webthread_initializer.py
component_starter.start_component("FTI")
```

**Step 2: FTI Node Launch**
```bash
ros2 run fti fti_ros2_node
```

**Step 3: Status Verification**
```python
# Webthread checks FTI status
response = fti_status_client.call(Trigger.Request())
if response.success:
    status = json.loads(response.message)
    print(f"FTI ready: {status['status']}")
```

**Step 4: Integration Confirmation**
- FTI publishes to `fti/status`
- Webthread confirms receipt
- Component marked as READY

### Runtime Communication

**Import Request Flow**:
1. User/Webthread publishes to `fti/import_command`
2. FTI receives command and begins import
3. FTI publishes status update to `fti/status` (status: "importing")
4. FTI completes import
5. FTI publishes result to `fti/import_result`
6. FTI publishes status update (status: "ready")
7. Webthread forwards metadata to DIMC and ROC

---

## Data Export for Other Components

### For DIMC (Dimensions Collector)

**What DIMC Needs**:
- Robot part names and hierarchy
- Assembly structure (parent-child relationships)
- Initial bounding information

**Data Format**:
```json
{
  "robot_name": "ConstructionArm",
  "parts": {
    "count": 5,
    "names": ["base_link", "arm_link", ...],
    "paths": ["/Game/Robots/ConstructionArm/Parts/base_link", ...]
  },
  "assembly": {
    "hierarchy": {
      "root_nodes": ["base_link"],
      "assembly_order": ["base_link", "arm_link", ...],
      "nodes": {
        "base_link": {
          "type": "link",
          "children": ["arm_link"]
        }
      }
    }
  }
}
```

**Delivery**: Via `fti/import_result` or dedicated topic `fti/model_metadata`

### For ROC (Robot Operator Controller)

**What ROC Needs**:
- Joint definitions (name, type, limits)
- Control hierarchy (which joints control which parts)
- Parent-child relationships for coordinated control

**Data Format**:
```json
{
  "robot_name": "ConstructionArm",
  "joints": [
    {
      "name": "base_to_arm",
      "joint_type": "revolute",
      "parent_link": "base_link",
      "child_link": "arm_link",
      "transform": {"xyz": "0 0 1", "rpy": "0 0 0"}
    }
  ],
  "control_hierarchy": {
    "root_nodes": ["base_link"],
    "assembly_order": ["base_link", "arm_link", ...]
  }
}
```

**Delivery**: Via `fti/import_result` or dedicated topic `fti/joint_definitions`

### For UE5 Content Drawer

**What UE5 Needs**:
- Content paths for imported assets
- Folder organization structure
- Material assignments

**Data Format**: Paths included in `import_result`
```
content_path: "/Game/Robots/ConstructionArm"
parts_paths: [
  "/Game/Robots/ConstructionArm/Parts/base_link",
  "/Game/Robots/ConstructionArm/Parts/arm_link"
]
assembly_path: "/Game/Robots/ConstructionArm/Assembly/ConstructionArm_Complete"
```

---

## Configuration

### integration_config.json

Location: `components/files-type-importer/Config/integration_config.json`

Defines:
- ROS2 interface specifications
- Webthread integration parameters
- Data export formats
- Validation criteria

---

## Component Dependencies

### FTI Provides To:
- **DIMC**: Model metadata, hierarchy, part list
- **ROC**: Joint definitions, control hierarchy
- **UE5**: Imported asset paths
- **Webthread**: Status, health, import results

### FTI Receives From:
- **Webthread**: Import commands, configuration updates
- **User**: Direct import requests (dev mode)

### FTI Has No Dependencies On:
- DIMC, ROC, COMC (FTI is first to start)
- UE5 (import happens before UE5 needs the data)

---

## Validation & Testing

### Startup Validation
```python
# Check FTI is ready
ros2 service call /fti/check_status std_srvs/srv/Trigger

# Expected response:
# success: True
# message: '{"status": "ready", "supported_formats": [...]}'
```

### Integration Test
```python
# Send import command
ros2 topic pub /fti/import_command std_msgs/String \
  'data: {"file_path": "/path/to/robot.urdf", "robot_name": "TestRobot", "import_mode": "both"}'

# Monitor result
ros2 topic echo /fti/import_result

# Expected: Success message with paths and metadata
```

---

## Error Handling

### FTI Error States:
1. **NOT_STARTED**: Component not initialized
2. **INITIALIZING**: Starting up, loading converters
3. **READY**: Operational, waiting for commands
4. **IMPORTING**: Actively processing import
5. **ERROR**: Import failed or internal error

### Error Recovery:
- Webthread monitors `fti/status`
- On ERROR state, Webthread can:
  - Request restart (recovery strategy)
  - Continue with degraded mode (if non-critical)
  - Alert user

---

## Future Enhancements

### Planned for Future Versions:
1. **Custom ROS2 Message Types**: Replace `std_msgs/String` with custom messages
2. **Batch Import Service**: Import multiple robots in one call
3. **Progress Reporting**: Real-time import progress via topic
4. **Cache Management**: Reuse converted USD files
5. **Hot Reload**: Update models without full restart

---

## Quick Reference

### Start FTI Node
```bash
ros2 run fti fti_ros2_node
```

### Check FTI Status
```bash
ros2 topic echo /fti/status
```

### Send Import Command
```bash
ros2 topic pub /fti/import_command std_msgs/String \
  'data: {"file_path": "/path/to/model.urdf", "robot_name": "MyRobot", "import_mode": "both"}'
```

### Monitor Import Results
```bash
ros2 topic echo /fti/import_result
```

---

**Document Version**: 1.0  
**Last Updated**: 2025-11-16  
**Component**: Files Type Importer (FTI)  
**Integration Status**: Ready for Webthread Integration
