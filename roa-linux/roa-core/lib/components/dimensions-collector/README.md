# Dimensions Collector (DIMC)

**Component**: DIMC - Dimensions Collector for UE5  
**Version**: 1.0.0  
**Status**: ✅ Implemented  
**Last Updated**: 2025-11-16

---

## Overview

The Dimensions Collector (DIMC) is a critical ROA component that extracts and tracks spatial and dimensional data from the Unreal Engine 5 scene in real-time. It provides essential information for robot control, safety, and coordination.

### Primary Responsibilities

1. **Real-Time Tracking** (60Hz update rate)
   - Object sizes and dimensions
   - Position tracking (local + global coordinates)
   - Orientation monitoring
   - Movement delta calculation
   - Inter-robot distance calculation

2. **Sensor Simulation & Obstacle Detection** (for Evade subsystem)
   - Sensor simulation layer (LIDAR, depth cameras)
   - Environment scanning service
   - Real-time obstacle detection at 60Hz
   - Obstacle classification (static, dynamic, robot, boundary)
   - Collision risk assessment
   - Path clearance checking for autonomous navigation (ADM mode)

3. **Data Provision**
   - Feeds boundary information to ROC (Robot Operator Controller)
   - Provides obstacle data to ROC for Evade subsystem (autonomous path planning)
   - Provides spatial data to Webthread for ROS2 synchronization
   - Supplies position data to COMC (Communication Center)

4. **Export Capability**
   - Robot last known locations
   - Task completion status
   - Historical position data

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Unreal Engine 5 Scene                   │
│              (Robot Actors & Environment)                │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│           C++ UE5 Plugin (DimensionsCollector)           │
│  60Hz physics tick - Actor tracking & data collection    │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              Python Core (dimc_core.py)                  │
│     ROS2 integration & high-level coordination           │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
    ┌───────┐   ┌───────┐   ┌────────┐
    │  ROC  │   │Webthrd│   │  COMC  │
    │Display│   │ Sync  │   │Coord.  │
    └───────┘   └───────┘   └────────┘
```

---

## Component Structure

```
dimensions-collector/
├── README.md                          # This file
├── .gitignore                         # Ignore cache/build files
├── requirements.txt                   # Python dependencies
├── Config/                            # Configuration files
│   ├── dimc_settings.json             # Main settings
│   ├── tracking_params.yaml           # Tracking parameters
│   └── export_config.json             # Export settings
├── src/
│   ├── python/                        # Python implementation
│   │   ├── __init__.py
│   │   ├── dimc_core.py               # Main coordinator
│   │   ├── ros2_publisher.py          # ROS2 topic publisher
│   │   ├── sensor_simulation.py       # Sensor simulation layer
│   │   ├── obstacle_detection.py      # Obstacle detection (Evade)
│   │   ├── Tracking/                  # Tracking subsystem
│   │   │   ├── __init__.py
│   │   │   ├── position_tracker.py    # Position tracking
│   │   │   ├── orientation_tracker.py # Orientation tracking
│   │   │   ├── delta_calculator.py    # Movement delta
│   │   │   └── distance_calculator.py # Inter-robot distance
│   │   ├── Measurement/               # Measurement subsystem
│   │   │   ├── __init__.py
│   │   │   ├── size_measurer.py       # Object dimensions
│   │   │   ├── bounds_calculator.py   # Bounding box/sphere
│   │   │   └── safety_zones.py        # Safety boundary calc
│   │   └── Export/                    # Export subsystem
│   │       ├── __init__.py
│   │       ├── rosbag_exporter.py     # ROS bag export
│   │       ├── json_exporter.py       # JSON export
│   │       └── csv_exporter.py        # CSV export
│   └── cpp/                           # C++ UE5 plugin
│       ├── DimensionsCollector.h      # Plugin header
│       └── DimensionsCollector.cpp    # Plugin implementation
├── tests/                             # Unit tests
│   ├── __init__.py
│   ├── test_position_tracker.py
│   ├── test_size_measurer.py
│   └── test_distance_calculator.py
└── examples/                          # Example configurations
    └── sample_tracking_config.yaml
```

---

## Key Features

### 1. Real-Time Tracking (60Hz)

**Position Tracking**:
- Local coordinates (position within robot assembly)
- Global coordinates (world space position)
- Continuous updates at 60 FPS
- Configurable coordinate frames

**Orientation Tracking**:
- Rotation from origin (quaternion + Euler angles)
- Relative orientation to other robots
- Support for different reference frames

**Movement Delta**:
- Track position changes over time
- Velocity calculation
- Acceleration monitoring
- Configurable time windows

**Inter-Robot Distance**:
- Real-time distance calculations between all robots
- Minimum clearance monitoring
- Collision prediction
- Safety margin enforcement

### 2. Measurement System

**Size Measurement**:
- Visual mesh dimensions
- Collision mesh dimensions
- Bounding box (AABB - Axis-Aligned Bounding Box)
- Bounding sphere
- Component-level measurements

**Boundary Calculations**:
- Physical collision boundaries
- Visual mesh boundaries
- Safety zones (configurable margins)
- Work area definitions

### 3. Data Export

**ROS Bag Export**:
- Complete robot state history
- TF (transform) data
- Joint states
- Sensor data
- Playback capability

**JSON Export**:
- Human-readable summaries
- Task completion reports
- Last known positions
- Configuration snapshots

**CSV Export**:
- Position history
- Distance matrices
- Performance metrics
- Analysis-ready format

---

## ROS2 Integration

### Published Topics

```python
# Robot pose (60 Hz)
/dimc/robot/{robot_id}/pose
# Type: geometry_msgs/PoseStamped
# World position and orientation

# Robot dimensions (on change)
/dimc/robot/{robot_id}/dimensions
# Type: custom_msgs/RobotDimensions
# Bounding box, sphere, component sizes

# Movement delta (60 Hz)
/dimc/robot/{robot_id}/velocity
# Type: geometry_msgs/TwistStamped
# Linear and angular velocity

# Inter-robot distances (20 Hz)
/dimc/distances
# Type: custom_msgs/DistanceMatrix
# Distances between all robot pairs

# Safety zones (on change)
/dimc/robot/{robot_id}/safety_zone
# Type: custom_msgs/SafetyZone
# Configurable safety boundaries
```

### Provided Services

```python
# Get robot information
/dimc/get_robot_info
# Request: robot_id (string)
# Response: RobotInfo (dimensions, limits, state)

# Get distance between robots
/dimc/get_distance
# Request: robot_id_1, robot_id_2 (strings)
# Response: distance (float64)

# Export data
/dimc/export_data
# Request: format (string), filename (string)
# Response: success (bool), filepath (string)
```

---

## Configuration

### dimc_settings.json

```json
{
  "update_rate_hz": 60,
  "coordinate_frame": "world",
  "measurement_type": "both",
  "safety_margin_meters": 0.1,
  "enable_export": true,
  "export_interval_seconds": 60,
  "max_robots": 10,
  "logging": {
    "enabled": true,
    "level": "INFO",
    "file": "dimc.log"
  }
}
```

### tracking_params.yaml

```yaml
tracking:
  position:
    update_rate: 60  # Hz
    precision: 0.001  # meters
    coordinate_system: "world"
  
  orientation:
    update_rate: 60  # Hz
    format: "quaternion"  # or "euler"
    
  velocity:
    update_rate: 60  # Hz
    window_size: 10  # samples for smoothing
    
  distance:
    update_rate: 20  # Hz (less frequent)
    max_distance: 100.0  # meters (ignore beyond)

measurement:
  use_visual_mesh: true
  use_collision_mesh: true
  bounding_box_type: "AABB"  # or "OBB"
  safety_margin: 0.1  # meters
```

### export_config.json

```json
{
  "rosbag": {
    "enabled": true,
    "retention_days": 7,
    "topics": [
      "/dimc/robot/+/pose",
      "/dimc/robot/+/velocity",
      "/dimc/distances"
    ]
  },
  "json": {
    "enabled": true,
    "retention_days": 30,
    "include_task_summary": true
  },
  "csv": {
    "enabled": false,
    "fields": ["timestamp", "robot_id", "x", "y", "z"]
  }
}
```

---

## Usage

### Python API

```python
from dimc_core import DimensionsCollector

# Initialize DIMC
dimc = DimensionsCollector()
dimc.initialize()

# Register a robot
dimc.register_robot("robot_1", actor_reference)

# Get current position
pose = dimc.get_position("robot_1")
print(f"Position: {pose.position}")
print(f"Orientation: {pose.orientation}")

# Get dimensions
dims = dimc.get_dimensions("robot_1")
print(f"Bounding box: {dims.width} x {dims.height} x {dims.length}")

# Get distance between robots
distance = dimc.get_distance("robot_1", "robot_2")
print(f"Distance: {distance} meters")

# Export data
dimc.export_to_rosbag("session_data.bag")
dimc.export_to_json("summary.json")
```

### UE5 Blueprint

```
DimensionsCollector (Blueprint Node)
├── RegisterRobot (robot_id, actor)
├── GetPosition (robot_id) -> Vector
├── GetDimensions (robot_id) -> BoundingBox
├── GetDistance (robot_id_1, robot_id_2) -> float
└── ExportData (format, filename)
```

---

## Performance

### Update Rates
- **Position/Orientation**: 60 Hz (16.6ms period)
- **Velocity/Delta**: 60 Hz (calculated from position)
- **Inter-Robot Distance**: 20 Hz (50ms period)
- **Dimensions**: On-demand or on change

### Latency Targets
- Position query: < 1ms
- Dimension query: < 5ms
- Distance calculation: < 10ms
- Export operation: < 1s (background)

### Resource Usage
- CPU: < 5% (on Ryzen 7)
- Memory: < 100 MB per robot
- Disk: Depends on export settings

---

## Integration with Other Components

### Webthread
- Receives robot registration events
- Publishes tracking data to ROS2
- Logs DIMC events
- Monitors DIMC health (500ms heartbeat)
- Calls `initialize()` during startup to enable sensor simulation and obstacle detection
- Calls `calibrate_evade_subsystem()` during initialization phase for each robot

### Robot Operator Controller (ROC)
- Receives position/orientation data for display
- Gets safety boundaries for control limits
- Uses distance data for collision warnings
- Updates UI with movement delta
- **Evade Subsystem Integration**:
  - Calls `get_obstacles()` to retrieve detected obstacles for path planning
  - Calls `is_path_clear()` to validate planned paths before execution (ADM mode)
  - Calls `get_environment_scan()` for comprehensive obstacle awareness
  - Uses obstacle data for autonomous navigation in ADM mode

### Communication Center (COMC)
- Receives position data for multi-robot coordination
- Gets safety zones for work area management
- Uses distance data for proximity alerts
- Coordinates multi-robot evasion maneuvers

### Files Type Importer (FTI)
- Receives robot metadata after import
- Gets initial dimensions for tracking setup
- Provides robot hierarchy information

---

## Safety Features

### Collision Detection
- Visual mesh collision checks
- Collision mesh collision checks
- Configurable safety margin (default: 10cm)
- Real-time alerts to ROC

### Boundary Monitoring
- Robot work area boundaries
- Safety zone violations
- Minimum clearance thresholds
- Emergency stop triggers

### Data Validation
- Position sanity checks (outlier detection)
- Dimension validation
- State consistency verification
- Error detection and recovery

---

## Testing

### Unit Tests
- Position tracking accuracy
- Dimension measurement correctness
- Distance calculation precision
- Export format validation

### Integration Tests
- ROS2 topic publishing
- UE5 plugin integration
- Multi-robot tracking
- Performance benchmarks

### Performance Tests
- 60 Hz update rate verification
- Latency measurements
- Memory usage monitoring
- Scalability testing (10+ robots)

---

## Dependencies

### Python
- rclpy (ROS2 Python client)
- numpy (mathematical operations)
- pyyaml (configuration parsing)
- rosbag2_py (ROS bag export)

### C++
- Unreal Engine 5.6+ SDK
- Chaos Physics Engine
- Standard Template Library

---

## Troubleshooting

### Issue: Low Update Rate
**Symptom**: Updates slower than 60 Hz  
**Solution**: Check UE5 physics tick rate, reduce tracked robots

### Issue: Incorrect Dimensions
**Symptom**: Wrong bounding box sizes  
**Solution**: Verify mesh type (visual vs collision), check scale

### Issue: Missing Distance Data
**Symptom**: Inter-robot distances not published  
**Solution**: Ensure multiple robots registered, check COMC connection

### Issue: Export Failure
**Symptom**: Cannot export to ROS bag  
**Solution**: Check disk space, verify rosbag2 installation, check permissions

---

## Future Enhancements

### Phase 2
- [ ] Predictive collision detection
- [ ] Path replay from history
- [ ] 3D visualization of safety zones
- [ ] Cloud storage integration

### Phase 3
- [ ] Machine learning for anomaly detection
- [ ] Automated calibration
- [ ] Multi-sensor fusion
- [ ] Real-time analytics dashboard

---

## References

- [ROA Architecture](../../docs/ARCHITECTURE.md)
- [ROS2 Humble Documentation](https://docs.ros.org/en/humble/)
- [Unreal Engine Physics](https://docs.unrealengine.com/5.6/en-US/physics-in-unreal-engine/)
- [TF2 (ROS Transform Library)](http://wiki.ros.org/tf2)

---

**Author**: GitHub Copilot  
**License**: TBD  
**Contact**: See main repository README
