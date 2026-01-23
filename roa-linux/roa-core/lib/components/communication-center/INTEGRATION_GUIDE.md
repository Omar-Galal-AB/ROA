# COMC Integration Guide

**Document**: Integration Guide for Communication Center  
**Version**: 0.1.0  
**Date**: 2025-11-16

---

## Overview

This guide explains how to integrate COMC (Communication Center) with the other ROA components: FTI, DIMC, Webthread, and ROC.

---

## Integration Architecture

```
┌──────────────────────────────────────────────────────┐
│                    WEBTHREAD                         │
│         (Central Coordination & Health Monitoring)   │
└────────┬─────────────┬─────────────┬────────────────┘
         │             │             │
         │             │             │
    ┌────▼─────┐  ┌───▼────┐   ┌───▼────┐   ┌────────┐
    │   FTI    │  │  DIMC  │   │  ROC   │   │  COMC  │
    │(Import)  │  │(Sensor)│   │(Control)│  │(Coord) │
    └────┬─────┘  └───┬────┘   └───┬────┘   └───┬────┘
         │            │            │            │
         └────────────┴────────────┴────────────┘
                      ↓
              Robot ↔ Robot Communication
```

---

## Component Integration Details

### 1. Integration with DIMC (Dimensions Collector)

**Purpose**: COMC receives robot position, velocity, and obstacle data from DIMC.

**Topics Subscribed**:
```python
# Robot position data (60Hz from DIMC)
/robot/{robot_id}/pose
  Type: std_msgs/String (JSON format)
  Format: {
    "robot_id": "robot_1",
    "x": 1.0,
    "y": 2.0,
    "z": 0.5,
    "vx": 0.1,  # velocity
    "vy": 0.0,
    "vz": 0.0
  }

# Obstacle detection (for Evade subsystem)
/dimc/obstacles
  Type: std_msgs/String (JSON format)
  Format: {
    "obstacle_id": "obs_1",
    "x": 3.0,
    "y": 4.0,
    "z": 0.0,
    "width": 0.5,
    "height": 1.0,
    "depth": 0.5,
    "type": "static"  # static, dynamic, robot, boundary
  }
```

**Handler**: `DIMCIntegrationHandler`

**Usage**:
```python
# In COMC node initialization:
self.dimc_handler = DIMCIntegrationHandler(
    self, self.proximity_monitor, self.evade_coordinator
)

# Subscribe to specific robot's position
self.dimc_handler.subscribe_to_robot_position("robot_1")
```

**What DIMC Must Provide**:
- Continuous position updates at 60Hz for all active robots
- Obstacle detection data for autonomous navigation (ADM mode)
- Velocity vectors for approach velocity calculations

---

### 2. Integration with Webthread (Central Hub)

**Purpose**: COMC reports health status and receives coordination commands from Webthread.

**Topics Published**:
```python
# Health status (2Hz to Webthread)
/comc/{robot_id}/status
  Type: std_msgs/String (JSON format)
  Format: {
    "component": "COMC",
    "robot_id": "robot_1",
    "status": "HEALTHY",  # HEALTHY, WARNING, ERROR
    "timestamp": 1234567890.0,
    "active_robots": 4,
    "conflicts": 0,
    "active_tasks": 2,
    "resource_locks": 3
  }
```

**Topics Subscribed**:
```python
# Commands from Webthread
/webthread/commands/{robot_id}
  Type: std_msgs/String (JSON format)
  Format: {
    "command": "restart",  # restart, status, shutdown
    "timestamp": 1234567890.0
  }
```

**Handler**: `WebthreadIntegrationHandler`

**Usage**:
```python
# In COMC node initialization:
self.webthread_handler = WebthreadIntegrationHandler(self)

# Publish health status (called by timer)
self.webthread_handler.publish_health_status(
    status='HEALTHY',
    active_robots=4,
    conflicts=0
)
```

**What Webthread Must Provide**:
- Subscribe to `/comc/{robot_id}/status` for health monitoring
- Send restart/status commands when needed
- Handle COMC failures according to graceful degradation strategy

**Startup Sequence** (from WEBTHREAD_INITIALIZER.md):
```
Phase 3: Component Startup
1. FTI   ✅ Starts first
2. DIMC  ✅ Starts after FTI
3. ROC   ✅ Starts after DIMC
4. COMC  ✅ Starts after ROC (Component 4)
5. Webthread Runtime
```

---

### 3. Integration with ROC (Robot Operator Controller)

**Purpose**: COMC coordinates evasion maneuvers for robots in ADM (Auto Driven Mode).

**Topics Subscribed**:
```python
# Evasion requests from ROC (when robot needs to avoid obstacle)
/roc/evasion_request
  Type: std_msgs/String (JSON format)
  Format: {
    "robot_id": "robot_1",
    "current_x": 1.0,
    "current_y": 2.0,
    "current_z": 0.5,
    "target_x": 5.0,
    "target_y": 6.0,
    "target_z": 0.5,
    "robot_type": "ground",  # ground, aerial, manipulator
    "priority": 2
  }
```

**Topics Published**:
```python
# Evasion responses to ROC (approved path or denial)
/comc/evasion_response
  Type: std_msgs/String (JSON format)
  Format: {
    "robot_id": "robot_1",
    "approved": true,
    "timestamp": 1234567890.0,
    "path": [
      {"x": 1.0, "y": 2.0, "z": 0.5},
      {"x": 3.0, "y": 4.0, "z": 0.5},
      {"x": 5.0, "y": 6.0, "z": 0.5}
    ]
  }
```

**Handler**: `ROCIntegrationHandler`

**Usage**:
```python
# In COMC node initialization:
self.roc_handler = ROCIntegrationHandler(self, self.evade_coordinator)

# Handler automatically responds to evasion requests
```

**What ROC Must Provide**:
- Send evasion requests when robot in ADM mode encounters obstacle
- Execute the approved alternative path received from COMC
- Handle evasion denials (no valid path found)

**Evade Workflow** (from ENHANCED_FEATURES.md):
```
1. DIMC detects obstacle → notifies ROC
2. ROC (ADM mode) → requests evasion from COMC
3. COMC calculates detour path
4. COMC checks path with other robots (no conflicts)
5. COMC broadcasts evasion intent to all robots
6. COMC responds to ROC with approved path
7. ROC executes the alternative path
```

---

### 4. Integration with FTI (Files Type Importer)

**Purpose**: COMC receives notifications when new robots are imported into the system.

**Topics Subscribed**:
```python
# Robot import notifications from FTI
/fti/robot_imported
  Type: std_msgs/String (JSON format)
  Format: {
    "robot_id": "robot_5",
    "robot_type": "quadruped",
    "timestamp": 1234567890.0
  }
```

**Handler**: `FTIIntegrationHandler`

**Usage**:
```python
# In COMC node initialization:
self.fti_handler = FTIIntegrationHandler(self)

# Handler automatically tracks new robots
```

**What FTI Must Provide**:
- Publish notification when robot import completes
- Include robot ID and type in notification

**Note**: COMC automatically handles new robots once they start publishing position data via DIMC.

---

## ROS2 Package Build Instructions

### Prerequisites
```bash
# ROS2 Humble installed
# Ubuntu 22.04
source /opt/ros/humble/setup.bash
```

### Build Steps

1. **Navigate to workspace**:
```bash
cd /path/to/ROA
```

2. **Build COMC package**:
```bash
colcon build --packages-select communication_center
```

3. **Source the package**:
```bash
source install/setup.bash
```

4. **Verify installation**:
```bash
ros2 pkg list | grep communication_center
```

### Launch COMC

**Single Robot**:
```bash
ros2 launch communication_center comc.launch.py robot_id:=robot_1
```

**Multiple Robots** (different terminals):
```bash
# Terminal 1
ros2 launch communication_center comc.launch.py robot_id:=robot_1

# Terminal 2
ros2 launch communication_center comc.launch.py robot_id:=robot_2

# Terminal 3
ros2 launch communication_center comc.launch.py robot_id:=robot_3
```

---

## Integration Testing

### Test Scenario 1: Proximity Alerts

**Setup**:
1. Launch COMC for 2 robots
2. Simulate DIMC position updates
3. Move robots closer together

**Expected**:
- Warning alert at 0.5m
- Caution alert at 0.3m
- Critical alert at 0.1m

**Test Command**:
```bash
# Publish position update
ros2 topic pub /robot/robot_1/pose std_msgs/String \
  "{data: '{\"robot_id\": \"robot_1\", \"x\": 0.0, \"y\": 0.0, \"z\": 0.0}'}"
```

### Test Scenario 2: Work Area Conflicts

**Setup**:
1. Launch COMC for 2 robots
2. Set overlapping work areas

**Expected**:
- Conflict detection logged
- Status report includes conflict count

### Test Scenario 3: Evasion Coordination

**Setup**:
1. Launch COMC, DIMC (simulated), ROC (simulated)
2. Send evasion request from ROC
3. Verify path calculation and approval

**Expected**:
- Detour path calculated
- Path broadcasted to other robots
- Response sent to ROC

---

## Performance Validation

### Latency Benchmarks

Run benchmarks to validate performance targets:

```bash
# Safety message latency (<20ms target)
ros2 topic hz /robots/proximity_alert

# Work area update rate (20Hz target)
ros2 topic hz /robots/work_areas

# Health status rate (2Hz target)
ros2 topic hz /comc/robot_1/status
```

### Expected Results

| Metric | Target | Measurement Command |
|--------|--------|---------------------|
| Proximity alerts | 60Hz | `ros2 topic hz /robots/proximity_alert` |
| Work areas | 20Hz | `ros2 topic hz /robots/work_areas` |
| Health status | 2Hz | `ros2 topic hz /comc/robot_1/status` |

---

## Troubleshooting

### Issue: COMC not receiving position data

**Check**:
1. Is DIMC running?
2. Is DIMC publishing to `/robot/{robot_id}/pose`?
3. Check topic: `ros2 topic echo /robot/robot_1/pose`

### Issue: No proximity alerts generated

**Check**:
1. Are robot positions being updated?
2. Are robots within alert threshold (0.5m)?
3. Check logs: `ros2 topic echo /comc/robot_1/status`

### Issue: Evasion requests not processed

**Check**:
1. Is ROC publishing to `/roc/evasion_request`?
2. Are obstacle data available from DIMC?
3. Check evade coordinator status in logs

---

## Configuration

### Modify Alert Thresholds

Edit `Config/comc_config.yaml`:
```yaml
proximity:
  alert_threshold_warning: 0.5   # Change this
  alert_threshold_caution: 0.3   # Change this
  alert_threshold_critical: 0.1  # Change this
```

### Modify Update Rates

Edit `Config/comc_config.yaml`:
```yaml
work_area:
  broadcast_rate: 20  # Change this

proximity:
  update_rate: 60  # Change this
```

---

## API Reference

See separate documentation:
- **README.md**: Component overview
- **COMC_ANALYSIS.md**: Requirements analysis
- **IMPLEMENTATION_SUMMARY.md**: Implementation details

---

## Next Steps

1. **Integration Testing**: Test with actual DIMC and Webthread
2. **Performance Benchmarking**: Validate <20ms latency
3. **Multi-Robot Scenarios**: Test with 4+ robots
4. **Real Hardware**: Test on actual robots (REA version)

---

**Status**: Integration handlers implemented and ready for testing  
**Last Updated**: 2025-11-16  
**Contact**: ROA Development Team
