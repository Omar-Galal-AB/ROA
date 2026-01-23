# ROC Integration Guide

This document describes how ROC (Robot Operator Controller) integrates with the other four ROA components.

## Overview

ROC acts as the universal robot controller and integrates with:
1. **FTI** (Files Type Importer) - Receives robot specifications
2. **DIMC** (Dimensions Collector) - Receives spatial data and obstacles  
3. **COMC** (Communication Center) - Multi-robot coordination
4. **Webthread** - System orchestration and monitoring

---

## Integration Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      WEBTHREAD                                │
│              (Central Integration Hub)                        │
└────────┬──────────────┬─────────────┬──────────────┬─────────┘
         │              │             │              │
    ┌────▼────┐    ┌───▼────┐   ┌───▼────┐    ┌────▼────┐
    │   FTI   │    │  DIMC  │   │  COMC  │    │   ROC   │
    │ (Import)│    │(Spatial)│   │(Coord) │    │(Control)│
    └────┬────┘    └───┬─────┘   └───┬────┘    └────┬────┘
         │             │              │              │
         └─────────────┴──────────────┴──────────────┘
                           ↓
                      Robots & UE5
```

---

## 1. FTI Integration

### Purpose
FTI provides robot specifications to ROC after importing a robot model.

### ROS2 Topics

#### ROC Subscribes:
- **`/fti/robot_specs`** (String/JSON)
  - Robot joint definitions, capabilities, structure
  - Published when robot is imported
  - Example:
    ```json
    {
      "robot_id": "robot_001",
      "robot_name": "ConstructionArm",
      "joints": [
        {"name": "joint1", "type": "revolute", "limits": [-3.14, 3.14]},
        {"name": "joint2", "type": "revolute", "limits": [-1.57, 1.57]}
      ],
      "capabilities": {
        "has_gripper": true,
        "has_mobile_base": false
      }
    }
    ```

- **`/fti/import_result`** (String/JSON)
  - Import success/failure notifications
  - Example:
    ```json
    {
      "success": true,
      "robot_name": "ConstructionArm",
      "content_path": "/Game/Robots/ConstructionArm"
    }
    ```

### Integration Handler
`FTIIntegrationHandler` in `integration_handlers.py`:
- Subscribes to FTI topics
- Parses robot specifications
- Calls `_on_robot_specs_received()` callback
- Stores robot info in ROC node

### Data Flow
```
FTI Import → robot_specs published → ROC receives → 
Store in self.robots → Configure adaptive UI → Ready for control
```

---

## 2. DIMC Integration

### Purpose
DIMC provides real-time spatial data, boundaries, and obstacle detection.

### ROS2 Topics

#### ROC Subscribes:
- **`/dimc/spatial_data`** (String/JSON) - 60Hz
  - Robot positions, orientations, boundaries
  - Example:
    ```json
    {
      "robot_id": "robot_001",
      "position": {"x": 1.5, "y": 2.3, "z": 0.0},
      "orientation": {"roll": 0.0, "pitch": 0.0, "yaw": 1.57},
      "boundaries": {
        "min": {"x": 0.0, "y": 0.0, "z": 0.0},
        "max": {"x": 10.0, "y": 10.0, "z": 3.0}
      }
    }
    ```

- **`/dimc/obstacles`** (String/JSON)
  - Obstacle detection data
  - Example:
    ```json
    {
      "robot_id": "robot_001",
      "distance": 0.45,
      "position": {"x": 2.0, "y": 2.5, "z": 0.5}
    }
    ```

#### ROC Publishes:
- **`/roc/target_positions`** (String/JSON)
  - Target positions for collision prediction
  - Example:
    ```json
    {
      "robot_id": "robot_001",
      "target_position": {"x": 3.0, "y": 4.0, "z": 0.0}
    }
    ```

### Integration Handler
`DIMCIntegrationHandler` in `integration_handlers.py`:
- Subscribes to DIMC spatial and obstacle data
- Calls `_on_spatial_data_received()` for position updates
- Calls `_on_obstacle_detected()` for collision warnings
- Publishes target positions for path prediction

### Data Flow
```
DIMC Tracking → spatial_data @ 60Hz → ROC updates position →
Safety checks → UI updates

DIMC Obstacle Detection → obstacles → ROC safety manager →
Auto-stop if needed → Visual warnings
```

---

## 3. COMC Integration

### Purpose
COMC handles multi-robot coordination and evasion path planning.

### ROS2 Topics

#### ROC Publishes:
- **`/roc/evasion_request`** (String/JSON)
  - Request alternative path to avoid obstacles/robots
  - Example:
    ```json
    {
      "robot_id": "robot_001",
      "current_x": 1.0, "current_y": 2.0, "current_z": 0.0,
      "target_x": 5.0, "target_y": 6.0, "target_z": 0.0,
      "robot_type": "ground",
      "priority": 2
    }
    ```

- **`/roc/robot_intentions`** (String/JSON)
  - Broadcast robot movement intentions
  - Example:
    ```json
    {
      "robot_id": "robot_001",
      "intention": "moving_to",
      "target_area": {"x": 5.0, "y": 6.0, "radius": 1.0}
    }
    ```

#### ROC Subscribes:
- **`/comc/evasion_response`** (String/JSON)
  - Alternative path from COMC
  - Example:
    ```json
    {
      "robot_id": "robot_001",
      "approved": true,
      "path": [
        {"x": 1.5, "y": 2.5, "z": 0.0},
        {"x": 2.0, "y": 3.5, "z": 0.0},
        {"x": 4.5, "y": 5.5, "z": 0.0}
      ]
    }
    ```

- **`/comc/work_areas`** (String/JSON)
  - Work area broadcasts from other robots
  - Used for collision avoidance

### Integration Handler
`COMCIntegrationHandler` in `integration_handlers.py`:
- Publishes evasion requests when obstacles detected
- Receives approved/denied evasion paths
- Calls `_on_evasion_response_received()` with path
- Publishes robot intentions for coordination

### Data Flow
```
ROC detects obstacle → Request evasion → COMC calculates path →
Response received → Update robot trajectory

Other robots broadcast work areas → ROC avoids areas →
Publishes own intentions → Coordination achieved
```

---

## 4. Webthread Integration

### Purpose
Webthread orchestrates all components and manages system-wide coordination.

### ROS2 Topics

#### ROC Publishes:
- **`/roc/status`** (String/JSON) - 1Hz
  - Component health and status
  - Example:
    ```json
    {
      "component": "ROC",
      "state": "rpm_active",
      "mode": "RPM",
      "robot_count": 2,
      "safety_level": "Standard",
      "active_robot": "robot_001"
    }
    ```

- **`/roc/command_history`** (String/JSON)
  - Command logging for Webthread
  - Example:
    ```json
    {
      "robot_id": "robot_001",
      "command": "move",
      "timestamp": 1700000000.123
    }
    ```

- **`/roc/errors`** (String/JSON)
  - Error reports
  - Example:
    ```json
    {
      "component": "ROC",
      "error_type": "collision",
      "details": "Obstacle detected at 0.15m",
      "robot_id": "robot_001"
    }
    ```

#### ROC Subscribes:
- **`/webthread/config_update`** (String/JSON)
  - Configuration updates from Webthread
  - Example:
    ```json
    {
      "safety_level": "Fragile",
      "update_rate": 60
    }
    ```

- **`/webthread/commands/roc`** (String/JSON)
  - System commands (restart, emergency_stop, status)
  - Example:
    ```json
    {
      "command": "emergency_stop"
    }
    ```

### Integration Handler
`WebthreadIntegrationHandler` in `integration_handlers.py`:
- Publishes status updates every 1 second
- Publishes command history for logging
- Publishes error reports
- Receives configuration updates
- Processes system commands

### Data Flow
```
ROC starts → Register with Webthread → Status updates @ 1Hz →
Webthread monitors health

Webthread config change → Update received → ROC reconfigures →
Confirm change

ROC error → Error published → Webthread logs → User notified
```

---

## Integration Sequence

### Startup Sequence

1. **Webthread starts** and initializes ROS2 bridge
2. **ROC starts** (`roc_ros2_node.py`)
   - Initializes integration handlers
   - Subscribes to all component topics
   - Transitions to CONNECTING state
3. **FTI imports robot** and publishes specs
4. **ROC receives specs** and configures controllers
5. **DIMC starts tracking** and publishes spatial data
6. **ROC receives position** and updates UI
7. **COMC starts** and begins coordination
8. **ROC transitions to IDLE** - ready for control

### Control Sequence (RPM Mode)

1. **User input** (keyboard/mouse)
2. **ROC processes input** → generates command
3. **Safety check** using DIMC obstacle data
4. **Publish target position** to DIMC
5. **If obstacle detected** → request evasion from COMC
6. **Receive evasion path** → update trajectory
7. **Execute command** → publish to ROS2 Control
8. **Log command** to Webthread
9. **Monitor execution** via DIMC feedback

### Multi-Robot Coordination

1. **Robot A** plans movement
2. **Publish intention** to COMC
3. **COMC broadcasts** to all robots
4. **Robot B** receives broadcast
5. **ROC checks** if paths conflict
6. **If conflict** → request alternative path
7. **COMC coordinates** timing/paths
8. **Both robots execute** safely

---

## Message Formats

All messages use JSON format via `std_msgs/String` for flexibility during development. Future versions may use custom ROS2 message types for better performance.

### Standard Fields
- `robot_id`: String identifier for the robot
- `timestamp`: Unix timestamp (seconds since epoch)
- `component`: Component name ("ROC", "FTI", "DIMC", "COMC")

---

## Error Handling

### Connection Failures
- If component connection lost → ROC publishes error to Webthread
- Webthread attempts reconnection
- ROC enters ERROR state if critical component unavailable

### Integration Errors
- JSON parsing errors logged
- Invalid data ignored with warning
- Callbacks protected with try/except

### Recovery
- Automatic retry for transient failures
- Manual intervention required for persistent errors
- Graceful degradation (e.g., continue with remaining robots)

---

## Testing Integration

### Unit Tests
Test each integration handler independently:
```python
# Test FTI integration
fti_handler = FTIIntegrationHandler(node, callback)
# Send test robot_specs message
# Verify callback called with correct data

# Test DIMC integration
dimc_handler = DIMCIntegrationHandler(node, spatial_cb, obstacle_cb)
# Send test spatial_data message
# Verify position updated correctly
```

### Integration Tests
Test end-to-end flows:
1. FTI import → ROC receives specs → Controllers configured
2. DIMC tracking → ROC updates position → UI displays correctly
3. Obstacle detected → COMC evasion → Path updated
4. Status updates → Webthread receives → Logged correctly

### System Tests
Full ROA system running:
- Import robot via FTI
- Control robot via ROC RPM mode
- Verify DIMC tracking works
- Test multi-robot coordination via COMC
- Check Webthread logging

---

## Performance Considerations

### Update Rates
- **DIMC spatial data**: 60Hz (high frequency)
- **COMC work areas**: 20Hz (medium frequency)
- **ROC status**: 1Hz (low frequency)
- **FTI specs**: On-demand (event-based)

### QoS Policies
- **Control commands**: RELIABLE (must not be lost)
- **Sensor data**: BEST_EFFORT (can tolerate loss)
- **Status updates**: RELIABLE with depth=10

### Latency Targets
- FTI specs → ROC: < 100ms
- DIMC data → ROC: < 20ms (control loop)
- COMC evasion → ROC: < 200ms
- ROC status → Webthread: < 50ms

---

## Configuration

Integration handlers are automatically initialized when ROC starts. No additional configuration required beyond standard `roc_config.yaml`.

---

## Troubleshooting

### "FTI integration not receiving specs"
- Check FTI is running: `ros2 node list | grep fti`
- Check topic: `ros2 topic echo /fti/robot_specs`
- Verify JSON format is correct

### "DIMC spatial data not updating"
- Check DIMC is publishing: `ros2 topic hz /dimc/spatial_data`
- Should be ~60Hz
- Check robot_id matches

### "COMC evasion not working"
- Check COMC node running
- Verify `/roc/evasion_request` is published
- Check `/comc/evasion_response` is subscribed

### "Webthread not receiving status"
- Check status publishing: `ros2 topic echo /roc/status`
- Should update every 1 second
- Verify Webthread subscriber active

---

## Summary

ROC integrates with all four other ROA components through well-defined ROS2 topic interfaces:

| Component | Purpose | Key Topics | Update Rate |
|-----------|---------|------------|-------------|
| **FTI** | Robot specs | `/fti/robot_specs` | On-import |
| **DIMC** | Spatial data | `/dimc/spatial_data`, `/dimc/obstacles` | 60Hz |
| **COMC** | Coordination | `/roc/evasion_request`, `/comc/evasion_response` | On-demand |
| **Webthread** | Orchestration | `/roc/status`, `/webthread/config_update` | 1Hz |

All integration is handled transparently by integration handlers, allowing ROC to focus on robot control logic.

---

**Last Updated**: 2025-11-16  
**Version**: 1.0
