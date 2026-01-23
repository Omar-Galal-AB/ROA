# ROA Communication Protocol Specification

**Version:** 1.0.0  
**Last Updated:** 2025-01-XX  
**Transport:** TCP Socket / WebSocket  
**Port:** 9876  
**Format:** JSON

---

## Overview

The ROA UE5 Plugin communicates with the Python-based Webthread component via JSON messages over TCP/WebSocket. All messages follow a consistent structure with request/response patterns.

---

## Message Structure

### Base Message Format
```json
{
    "message_id": "unique-uuid-v4",
    "timestamp": 1234567890.123,
    "message_type": "REQUEST|RESPONSE|EVENT|ERROR",
    "command": "command_name",
    "payload": {}
}
```

### Field Descriptions
- **message_id**: Unique identifier (UUID v4) for message tracking
- **timestamp**: Unix timestamp with milliseconds
- **message_type**: Type of message (REQUEST, RESPONSE, EVENT, ERROR)
- **command**: Command name (snake_case)
- **payload**: Command-specific data

---

## Command Categories

### 1. Connection Management

#### `connect`
**Request:**
```json
{
    "message_type": "REQUEST",
    "command": "connect",
    "payload": {
     "client_name": "UE5_ROA_Plugin",
     "version": "1.0.0",
        "capabilities": ["robot_spawn", "physics_sim", "widgets"]
    }
}
```

**Response:**
```json
{
    "message_type": "RESPONSE",
    "command": "connect",
    "payload": {
        "status": "success",
        "server_version": "1.0.0",
        "session_id": "session-uuid"
    }
}
```

#### `disconnect`
**Request:**
```json
{
    "message_type": "REQUEST",
    "command": "disconnect",
    "payload": {
        "session_id": "session-uuid"
    }
}
```

#### `heartbeat`
**Request/Response:**
```json
{
    "message_type": "EVENT",
 "command": "heartbeat",
    "payload": {
   "timestamp": 1234567890.123
    }
}
```

---

### 2. Robot Management

#### `spawn_robot`
**Request:**
```json
{
    "message_type": "REQUEST",
    "command": "spawn_robot",
    "payload": {
      "robot_id": "robot_001",
        "robot_type": "ur5e",
        "urdf_path": "/path/to/robot.urdf",
        "spawn_location": {
        "x": 0.0,
         "y": 0.0,
  "z": 0.0
   },
        "spawn_rotation": {
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 0.0
        },
        "initial_joint_states": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    }
}
```

**Response:**
```json
{
    "message_type": "RESPONSE",
    "command": "spawn_robot",
    "payload": {
   "status": "success",
        "robot_id": "robot_001",
        "actor_handle": "ue5-actor-handle",
        "joint_count": 6,
        "joint_names": ["shoulder_pan", "shoulder_lift", "elbow", "wrist_1", "wrist_2", "wrist_3"]
    }
}
```

#### `despawn_robot`
**Request:**
```json
{
    "message_type": "REQUEST",
    "command": "despawn_robot",
    "payload": {
      "robot_id": "robot_001"
    }
}
```

#### `get_robot_state`
**Request:**
```json
{
    "message_type": "REQUEST",
    "command": "get_robot_state",
    "payload": {
        "robot_id": "robot_001"
}
}
```

**Response:**
```json
{
    "message_type": "RESPONSE",
    "command": "get_robot_state",
    "payload": {
        "robot_id": "robot_001",
 "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
     "joint_states": {
    "positions": [0.0, -1.57, 1.57, 0.0, 1.57, 0.0],
         "velocities": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "efforts": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        },
      "end_effector_pose": {
      "position": {"x": 0.5, "y": 0.0, "z": 0.3},
  "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
      }
    }
}
```

#### `list_robots`
**Request:**
```json
{
    "message_type": "REQUEST",
    "command": "list_robots",
    "payload": {}
}
```

**Response:**
```json
{
    "message_type": "RESPONSE",
    "command": "list_robots",
    "payload": {
  "robots": [
      {
      "robot_id": "robot_001",
         "robot_type": "ur5e",
         "status": "active"
         }
  ]
    }
}
```

---

### 3. Robot Control

#### `move_robot`
**Request:**
```json
{
    "message_type": "REQUEST",
    "command": "move_robot",
    "payload": {
   "robot_id": "robot_001",
        "target_position": {"x": 1.0, "y": 0.5, "z": 0.0},
        "target_rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 1.57}
    }
}
```

#### `set_joint_positions`
**Request:**
```json
{
    "message_type": "REQUEST",
    "command": "set_joint_positions",
    "payload": {
      "robot_id": "robot_001",
      "joint_positions": [0.0, -1.57, 1.57, 0.0, 1.57, 0.0],
  "duration": 2.0
    }
}
```

#### `set_joint_velocities`
**Request:**
```json
{
    "message_type": "REQUEST",
    "command": "set_joint_velocities",
    "payload": {
"robot_id": "robot_001",
     "joint_velocities": [0.1, 0.2, 0.0, 0.0, 0.0, 0.0]
    }
}
```

#### `emergency_stop`
**Request:**
```json
{
  "message_type": "REQUEST",
    "command": "emergency_stop",
    "payload": {
        "robot_id": "robot_001"
    }
}
```

---

### 4. Physics Configuration

#### `set_physics_parameters`
**Request:**
```json
{
    "message_type": "REQUEST",
    "command": "set_physics_parameters",
    "payload": {
        "robot_id": "robot_001",
     "gravity": {"x": 0.0, "y": 0.0, "z": -9.81},
        "mass_scale": 1.0,
"damping": 0.1,
   "friction": 0.5
  }
}
```

#### `enable_collision`
**Request:**
```json
{
    "message_type": "REQUEST",
    "command": "enable_collision",
    "payload": {
        "robot_id": "robot_001",
        "enabled": true
    }
}
```

---

### 5. Collision & Safety

#### `collision_detected` (EVENT from UE5)
**Event:**
```json
{
    "message_type": "EVENT",
    "command": "collision_detected",
"payload": {
        "robot_id": "robot_001",
        "collision_point": {"x": 0.5, "y": 0.0, "z": 0.3},
        "collision_normal": {"x": 0.0, "y": 0.0, "z": 1.0},
        "collision_force": 150.0,
        "other_object": "wall_001"
    }
}
```

#### `get_collision_status`
**Request:**
```json
{
    "message_type": "REQUEST",
    "command": "get_collision_status",
    "payload": {
     "robot_id": "robot_001"
    }
}
```

**Response:**
```json
{
    "message_type": "RESPONSE",
    "command": "get_collision_status",
    "payload": {
        "is_colliding": false,
        "collision_count": 0,
        "safety_status": "ok"
    }
}
```

---

### 6. Scene Management

#### `add_obstacle`
**Request:**
```json
{
    "message_type": "REQUEST",
    "command": "add_obstacle",
    "payload": {
        "obstacle_id": "obstacle_001",
        "shape": "box",
        "dimensions": {"x": 1.0, "y": 1.0, "z": 1.0},
        "position": {"x": 2.0, "y": 0.0, "z": 0.5},
        "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
    }
}
```

#### `remove_obstacle`
**Request:**
```json
{
    "message_type": "REQUEST",
    "command": "remove_obstacle",
    "payload": {
        "obstacle_id": "obstacle_001"
    }
}
```

#### `clear_scene`
**Request:**
```json
{
    "message_type": "REQUEST",
    "command": "clear_scene",
    "payload": {}
}
```

---

### 7. Camera & Visualization

#### `set_camera_view`
**Request:**
```json
{
    "message_type": "REQUEST",
    "command": "set_camera_view",
    "payload": {
  "camera_id": "main_camera",
        "position": {"x": 5.0, "y": 5.0, "z": 3.0},
        "look_at": {"x": 0.0, "y": 0.0, "z": 0.0}
    }
}
```

#### `capture_screenshot`
**Request:**
```json
{
    "message_type": "REQUEST",
 "command": "capture_screenshot",
    "payload": {
        "output_path": "/path/to/screenshot.png",
        "resolution": {"width": 1920, "height": 1080}
    }
}
```

---

### 8. Widget & UI

#### `create_widget`
**Request:**
```json
{
    "message_type": "REQUEST",
    "command": "create_widget",
    "payload": {
        "widget_id": "control_panel_001",
        "widget_type": "robot_control_panel",
        "robot_id": "robot_001",
      "position": {"x": 100, "y": 100}
    }
}
```

#### `update_widget_data`
**Request:**
```json
{
    "message_type": "REQUEST",
    "command": "update_widget_data",
    "payload": {
        "widget_id": "control_panel_001",
        "data": {
            "joint_positions": [0.0, -1.57, 1.57, 0.0, 1.57, 0.0],
            "status": "moving"
        }
    }
}
```

#### `widget_event` (EVENT from UE5)
**Event:**
```json
{
    "message_type": "EVENT",
    "command": "widget_event",
    "payload": {
        "widget_id": "control_panel_001",
     "event_type": "slider_changed",
        "data": {
  "slider_id": "joint_0",
   "value": 0.523
        }
    }
}
```

---

### 9. File Import (FTI Integration)

#### `import_robot_file`
**Request:**
```json
{
    "message_type": "REQUEST",
"command": "import_robot_file",
    "payload": {
        "file_path": "/path/to/robot.urdf",
        "file_type": "urdf",
        "robot_name": "my_robot",
        "import_meshes": true,
   "import_collisions": true
    }
}
```

**Response:**
```json
{
    "message_type": "RESPONSE",
    "command": "import_robot_file",
    "payload": {
        "status": "success",
        "robot_definition": {
    "name": "my_robot",
            "joint_count": 6,
    "link_count": 7,
            "mesh_paths": ["/path/to/meshes/base.stl"],
        "joint_limits": [
          {"name": "joint_0", "min": -3.14, "max": 3.14}
            ]
    }
    }
}
```

---

### 10. System Status

#### `get_system_status`
**Request:**
```json
{
    "message_type": "REQUEST",
    "command": "get_system_status",
    "payload": {}
}
```

**Response:**
```json
{
    "message_type": "RESPONSE",
    "command": "get_system_status",
    "payload": {
        "ue5_version": "5.6.0",
        "plugin_version": "1.0.0",
        "active_robots": 3,
      "fps": 60.0,
 "physics_enabled": true,
        "ros2_connected": true
    }
}
```

---

## Error Handling

### Error Response Format
```json
{
    "message_type": "ERROR",
    "command": "original_command",
  "payload": {
        "error_code": "ERR_ROBOT_NOT_FOUND",
        "error_message": "Robot with ID 'robot_001' not found",
        "details": {}
    }
}
```

### Error Codes
- `ERR_CONNECTION_FAILED` - Connection to UE5 failed
- `ERR_ROBOT_NOT_FOUND` - Robot ID not found
- `ERR_INVALID_COMMAND` - Unknown command
- `ERR_INVALID_PAYLOAD` - Malformed payload
- `ERR_SPAWN_FAILED` - Robot spawn failed
- `ERR_PHYSICS_ERROR` - Physics simulation error
- `ERR_FILE_NOT_FOUND` - File import failed
- `ERR_WIDGET_ERROR` - Widget creation/update failed
- `ERR_COLLISION` - Collision detected (safety stop)
- `ERR_JOINT_LIMIT` - Joint limit exceeded
- `ERR_TIMEOUT` - Command timeout

---

## Supported Robot Types

All Universal Robot models are supported:
- **ur3**, **ur3e** - Lightweight collaborative robot
- **ur5**, **ur5e** - Medium payload collaborative robot
- **ur7e** - Extended reach collaborative robot
- **ur8long** - Long reach robot
- **ur10**, **ur10e** - Heavy payload collaborative robot
- **ur12e** - High payload collaborative robot
- **ur15** - High payload robot
- **ur16e** - Heavy payload collaborative robot
- **ur18** - Heavy payload robot
- **ur20** - Extra heavy payload robot
- **ur30** - Extra heavy payload robot

---

## Connection Lifecycle

1. **Connect**: Client sends `connect` request
2. **Handshake**: Server responds with session_id
3. **Commands**: Client sends commands with session_id
4. **Events**: Server sends events (collisions, state changes)
5. **Heartbeat**: Periodic heartbeat every 5 seconds
6. **Disconnect**: Client sends `disconnect` or connection drops

---

## Performance Guidelines

- **Maximum Message Size**: 10 MB
- **Heartbeat Interval**: 5 seconds
- **Command Timeout**: 30 seconds
- **Recommended Update Rate**: 30 Hz for robot state updates
- **Maximum Concurrent Robots**: 50 (performance dependent)

---

## Future Extensions

Planned command additions:
- Path planning integration
- Multi-robot coordination
- Recording/playback
- Advanced collision queries
- Tool/gripper control
- Force/torque feedback

---

**End of Protocol Specification**
