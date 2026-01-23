# ROA Architecture & Design Decisions

**Document Version:** 1.0  
**Date:** 2025-12-13  
**Status:** Architectural Blueprint for Implementation

This document addresses critical architectural decisions for ROA (Robotic Operation Assistant) covering installation, packaging, UI design, file management, component integration, and hardware support.

---

## 1. Installation & Packaging

### 1.1 Dual-Mode Operation

**Decision:** ROA supports two operational modes:

1. **Standalone Application** - Independent operation without UE5
2. **UE5 Plugin** - Integrated within Unreal Engine 5 projects

### 1.2 Package Structure

```
ROA/
├── installers/
│   ├── windows/
│   │   ├── ROA_Setup_vX.X.X.exe          # Windows installer
│   │   └── ROA_UE5_Plugin_vX.X.X.zip     # UE5 plugin package
│   ├── linux/
│   │   ├── ROA_Setup_vX.X.X.deb          # Debian package
│   │   ├── ROA_Setup_vX.X.X.rpm          # RedHat package
│   │   └── ROA_UE5_Plugin_vX.X.X.tar.gz  # UE5 plugin package
│   └── INSTALLATION_GUIDE.md
├── packages/
│   ├── roa-core/                          # Core functionality
│   ├── roa-standalone/                    # Standalone app
│   └── roa-ue5-plugin/                    # UE5 plugin
```

### 1.3 Installation Instructions

**Standalone Installation:**
- **Windows:** Double-click `.exe`, follow wizard, creates desktop shortcut
- **Linux:** `sudo dpkg -i ROA_Setup.deb` or `sudo rpm -i ROA_Setup.rpm`
- **Shortcut:** Automatically created at installation

**UE5 Plugin Installation:**
1. Extract plugin to `UE5_Project/Plugins/ROA/`
2. Enable in UE5 Editor → Plugins → ROA
3. Restart UE5 Editor
4. ROA launches automatically when project opens

### 1.4 Auto-Update System

**Implementation:**
- Check for updates on startup (configurable frequency)
- Download updates in background
- Prompt user for installation
- Support rollback to previous version
- Update manifest hosted on GitHub Releases

**Update Channels:**
- **Stable:** Production releases
- **Beta:** Testing releases
- **Dev:** Nightly builds

---

## 2. Unified Application Design

### 2.1 Single Application Architecture

**Decision:** ROA is ONE unified application, not separate apps per component.

**Old Design (❌ Deprecated):**
- Separate ROC app
- Separate Webthread app
- Disconnected interfaces

**New Design (✅ Adopted):**
- Single "ROA" application
- Integrated component views
- Unified status bar
- Seamless component switching

### 2.2 Main Window Layout

```
┌─────────────────────────────────────────────────────────────┐
│ ROA - Robotic Operation Assistant                    [_][□][X]│
├─────────────────────────────────────────────────────────────┤
│ [FTI] [DIMC] [COMC] [ROC] [Webthread]          Status: ● OK │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│                                                               │
│              COMPONENT CONTENT AREA                          │
│              (Dynamic based on selected tab)                 │
│                                                               │
│                                                               │
├─────────────────────────────────────────────────────────────┤
│ UE5: Connected | Heartbeat: ✓ | Last Update: 0.1s ago       │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 Component Views

#### FTI View
```
┌─────────────────────────────────────────────────────────────┐
│ File Translator & Integrator                                 │
├─────────────────────────────────────────────────────────────┤
│ Heartbeat: ● Active (Interval: 1.0s)                         │
│                                                               │
│ Last Converted Files:                                         │
│ • robot_arm_v2.urdf → robot_arm_v2.uasset (2 mins ago)      │
│ • gripper_model.stl → gripper_model.uasset (5 mins ago)     │
│                                                               │
│ Shortcuts:                                                    │
│ 📁 Content/Robots/     📁 Content/Meshes/                    │
│ 📁 Content/Configs/    📁 Exports/                           │
│                                                               │
│ ┌────────────────────────────────────────┐                  │
│ │  UE5 Status: Connected                 │                  │
│ │  [Convert Designs Locally]             │                  │
│ └────────────────────────────────────────┘                  │
│                                                               │
│ ┌────────────────────────────────────────┐                  │
│ │  UE5 Status: Not Connected             │                  │
│ │  [Convert Designs Outside UE5]         │                  │
│ │  Output Directory: [/path/to/export]   │                  │
│ └────────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

**FTI Behavior:**
- **UE5 Connected:** Button shows "Convert Designs Locally"
  - Converts and places in UE5 Content folder
  - Webthread provides Content folder path
  - Auto-assembles robot in UE5
  - Configures joints and motion ranges
  
- **UE5 Disconnected:** Button shows "Convert Designs Outside UE5"
  - Converts to specified output directory
  - User selects export location
  - Generates importable UE5 assets

#### DIMC View
```
┌─────────────────────────────────────────────────────────────┐
│ Data Integration & Monitoring Component                      │
├─────────────────────────────────────────────────────────────┤
│ Heartbeat: ● Active (Interval: 0.5s)                         │
│                                                               │
│ Last Operation Status:                                        │
│ ✓ Spatial data processed (Robot: robot_001)                 │
│ ✓ Sensor data integrated (12 sensors active)                │
│ ⚠ Warning: GPS signal weak on robot_003                     │
│                                                               │
│ Active Sensors:                                               │
│ Robot robot_001: Camera(2), LiDAR(1), IMU(1), GPS(1)        │
│ Robot robot_002: Camera(1), Ultrasonic(4), IMU(1)           │
│                                                               │
│ Data Flow: [=========>] 89% | 4.2 MB/s                      │
└─────────────────────────────────────────────────────────────┘
```

#### COMC View
```
┌─────────────────────────────────────────────────────────────┐
│ Communication Component                                       │
├─────────────────────────────────────────────────────────────┤
│ Heartbeat: ● Active (Interval: 0.5s)                         │
│                                                               │
│ Last Operation Status:                                        │
│ ✓ Commands transmitted (Queue: 3 pending)                   │
│ ✓ ROS2 nodes healthy (5/5 active)                           │
│ ✓ Network latency: 12ms (Good)                              │
│                                                               │
│ Message Statistics:                                           │
│ Sent: 1,247 | Received: 1,189 | Dropped: 0                  │
│                                                               │
│ Connection Status:                                            │
│ ROS2 Master: ● Connected                                     │
│ UE5 Bridge: ● Connected                                      │
│ Network: WiFi (Signal: ████░ 80%)                            │
└─────────────────────────────────────────────────────────────┘
```

#### ROC View (Separate Window)
```
┌─────────────────────────────────────────────────────────────┐
│ Robot Operator Controller                             [_][□][X]│
├─────────────────────────────────────────────────────────────┤
│ [robot_001] [robot_002] [robot_003]                          │
│   Active      Standby      Idle                             │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│ Robot: robot_001 (Mobile Manipulator)                        │
│ Status: ● Active | Mode: RPM (Manual)                       │
│                                                               │
│ ┌──────────────────────┐  ┌──────────────────────┐         │
│ │  Joint Controls      │  │  Movement Controls   │         │
│ │  J1: [======>  ] 45° │  │  [↑] Forward         │         │
│ │  J2: [====>    ] 30° │  │  [←][↓][→]           │         │
│ │  J3: [=>       ] 10° │  │  Speed: [=====> ] 75%│         │
│ │  J4: [=====>   ] 40° │  │                       │         │
│ │  J5: [=======> ] 60° │  │  [Emergency Stop]    │         │
│ │  J6: [====>    ] 30° │  │                       │         │
│ └──────────────────────┘  └──────────────────────┘         │
│                                                               │
│ ┌──────────────────────────────────────────────┐            │
│ │ End Effector Position: (1.2m, 0.5m, 0.8m)   │            │
│ │ Gripper: Open [=====>     ] 50%              │            │
│ └──────────────────────────────────────────────┘            │
│                                                               │
│ Controller: [PS5 Controller Connected ✓]                    │
│ [Configure Controller Mapping]                               │
└─────────────────────────────────────────────────────────────┘
```

#### Webthread View (Separate Window)
```
┌─────────────────────────────────────────────────────────────┐
│ Webthread - System Monitor                           [_][□][X]│
├─────────────────────────────────────────────────────────────┤
│ Project: RoboticsLab_Project | UE5: Connected               │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│ Component Status:                                             │
│ FTI:  ● Active   | Last: 0.5s | Uptime: 2h 34m              │
│ DIMC: ● Active   | Last: 0.2s | Uptime: 2h 34m              │
│ COMC: ● Active   | Last: 0.3s | Uptime: 2h 34m              │
│ ROC:  ● Active   | Last: 0.1s | Uptime: 2h 34m              │
│                                                               │
│ System Health: ████████░░ 85%                                │
│                                                               │
│ UE5 Project Info:                                             │
│ Content Path: C:/Projects/RoboticsLab/Content/               │
│ Assets: 142 | Robots: 3 | Scenes: 5                         │
│                                                               │
│ Alerts: [1 Warning, 0 Errors]                                │
│ ⚠ GPS signal weak on robot_003                              │
│                                                               │
│ [View Full Logs] [Export Report] [Settings]                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Error Identification System

### 3.1 Error Classification

**Decision:** Error types are robot-specific and defined in robot configuration files.

**Robot Configuration File Format (YAML):**
```yaml
robot:
  id: "robot_001"
  name: "Mobile Manipulator Alpha"
  type: "mobile_manipulator"
  
error_definitions:
  # Hardware Errors (100-199)
  - code: 101
    name: "MOTOR_OVERHEAT"
    severity: "CRITICAL"
    description: "Motor temperature exceeded safe threshold"
    actions: ["STOP_MOTOR", "ALERT_OPERATOR", "LOG_INCIDENT"]
    
  - code: 102
    name: "BATTERY_LOW"
    severity: "WARNING"
    description: "Battery level below 20%"
    actions: ["ALERT_OPERATOR", "REDUCE_SPEED"]
    
  # Sensor Errors (200-299)
  - code: 201
    name: "LIDAR_FAILURE"
    severity: "CRITICAL"
    description: "LiDAR sensor not responding"
    actions: ["STOP_ROBOT", "ALERT_OPERATOR", "SWITCH_TO_BACKUP"]
    
  # Communication Errors (300-399)
  - code: 301
    name: "CONNECTION_LOST"
    severity: "CRITICAL"
    description: "Lost connection to control system"
    actions: ["ENTER_SAFE_MODE", "ALERT_OPERATOR"]
    
  # Navigation Errors (400-499)
  - code: 401
    name: "PATH_BLOCKED"
    severity: "WARNING"
    description: "Obstacle detected in planned path"
    actions: ["REPLAN_PATH", "ALERT_OPERATOR"]
```

### 3.2 Error Detection Flow

```
Robot → Publishes Error Code → DIMC → Looks up in Robot Config → 
→ Classifies Error → Executes Actions → Notifies Components
```

**DIMC responsibilities:**
- Monitor all robot error topics
- Match error codes to robot configurations
- Execute predefined actions
- Broadcast alerts to ROA components
- Log all errors with timestamps

---

## 4. File Storage Architecture

### 4.1 Storage Locations

**Decision:** Dual storage system based on context.

**Standalone Mode:**
```
~/.roa/                              (Linux/Mac)
C:\Users\<User>\AppData\Roaming\ROA\ (Windows)
├── snapshots/
│   ├── robot_001/
│   │   ├── snapshot_2025-12-13_14-30-00.json
│   │   └── snapshot_2025-12-13_15-45-00.json
│   └── robot_002/
├── backups/
│   └── [Snapshots older than 24 hours]
├── archives/
│   └── [Backups older than 30 days]
├── configs/
├── logs/
└── projects/
```

**UE5 Plugin Mode:**
```
UE5_Project/
├── Saved/
│   └── ROA/
│       ├── snapshots/
│       ├── backups/
│       ├── archives/
│       └── logs/
└── Content/
    └── ROA/
        ├── Robots/
        ├── Configs/
        └── Meshes/
```

**Rationale:**
- **Standalone:** System-wide storage, accessible across projects
- **UE5 Plugin:** Project-specific storage, tied to UE5 project lifecycle

### 4.2 Automatic File Tiering

**Decision:** Implement automatic tiering system.

**Tiering Rules:**
1. **Snapshot → Backup:** After 24 hours
2. **Backup → Archive:** After 30 days
3. **Archive Retention:** 1 year (configurable)

**Implementation:**
```python
class FileLifecycleManager:
    def __init__(self):
        self.snapshot_age_threshold = 24 * 3600  # 24 hours
        self.backup_age_threshold = 30 * 86400   # 30 days
        self.archive_retention = 365 * 86400     # 1 year
        
    def run_tiering_cycle(self):
        # Move snapshots to backups
        old_snapshots = self.get_files_older_than(
            'snapshots/', self.snapshot_age_threshold
        )
        for snapshot in old_snapshots:
            self.move_file(snapshot, 'snapshots/', 'backups/')
            
        # Move backups to archives
        old_backups = self.get_files_older_than(
            'backups/', self.backup_age_threshold
        )
        for backup in old_backups:
            self.move_file(backup, 'backups/', 'archives/')
            
        # Delete old archives
        old_archives = self.get_files_older_than(
            'archives/', self.archive_retention
        )
        for archive in old_archives:
            self.delete_file(archive)
```

**Scheduled Execution:**
- Runs daily at 2:00 AM
- User notification of moved/deleted files
- Option to disable auto-tiering

### 4.3 Comparative Analysis Storage

**Decision:** Create separate analysis directory.

```
~/.roa/analysis/
├── project_evolution/
│   ├── project_001_timeline.json
│   ├── project_002_timeline.json
│   └── comparative_reports/
│       ├── project_001_vs_002.pdf
│       └── monthly_comparison_2025-12.pdf
└── metrics/
    ├── robot_performance_history.db
    └── component_usage_stats.db
```

**Features:**
- Track project development over time
- Compare snapshots across time periods
- Generate evolution reports
- Identify trends and patterns

---

## 5. Webthread Behavior

### 5.1 Launch Sequence

**First Project Open:**
```
1. Initialize Webthread core
2. Detect UE5 project (if plugin mode)
3. Scan for robot configurations
4. Initialize all components (FTI, DIMC, COMC, ROC)
5. Establish ROS2 connections
6. Load project-specific settings
7. Display main window
```

**Subsequent Opens:**
```
1. Initialize Webthread core
2. Load cached project configuration
3. Skip component initialization if settings unchanged
4. Verify component health (heartbeat check)
5. Resume previous session state (optional)
6. Display main window
```

**Optimization:**
- Cache project settings after first scan
- Only re-scan if project structure changed
- Use delta loading for faster startup
- Skip redundant component initialization

### 5.2 Project Memory Architecture

**Decision:** Hybrid approach - per-project + collective memory.

**Per-Project Memory:**
```yaml
project_memory:
  project_id: "RoboticsLab_2025"
  ue5_project_path: "/path/to/project"
  robots: ["robot_001", "robot_002"]
  content_path: "/path/to/project/Content"
  last_opened: "2025-12-13T14:30:00Z"
  settings:
    auto_backup: true
    snapshot_interval: 300  # seconds
  session_history:
    - timestamp: "2025-12-13T14:30:00Z"
      duration: 7200  # seconds
      operations: 45
```

**Collective Memory (Cross-Project):**
```yaml
global_memory:
  user_preferences:
    theme: "dark"
    notification_level: "important_only"
    default_snapshot_interval: 300
  
  robot_library:
    - robot_id: "robot_001"
      last_seen_project: "RoboticsLab_2025"
      total_usage_hours: 142.5
      configurations_count: 7
      
  learned_patterns:
    - pattern: "battery_drain_correlation"
      confidence: 0.87
      description: "High speed correlates with 30% faster battery drain"
      
  error_history:
    total_errors: 234
    most_common: ["BATTERY_LOW", "PATH_BLOCKED", "GPS_WEAK"]
```

**Benefits:**
- Per-project: Isolated configurations, project-specific optimizations
- Collective: Cross-project learning, global preferences, robot tracking

### 5.3 Component Health Detection

**Problem:** Components send heartbeats but don't function correctly.

**Solution:** Functional health checks beyond heartbeats.

**Health Check System:**
```python
class ComponentHealthMonitor:
    def __init__(self):
        self.health_checks = {
            'FTI': [
                self.check_file_conversion_capability,
                self.check_ue5_connection,
                self.check_output_directory_writable
            ],
            'DIMC': [
                self.check_sensor_data_processing,
                self.check_spatial_data_publishing,
                self.check_ros2_topics_active
            ],
            'COMC': [
                self.check_message_transmission,
                self.check_ros2_master_connection,
                self.check_command_queue_processing
            ],
            'ROC': [
                self.check_control_command_execution,
                self.check_controller_input_reception,
                self.check_robot_state_updates
            ]
        }
        
    def perform_health_check(self, component: str) -> HealthStatus:
        """Execute functional tests, not just heartbeat check."""
        results = []
        for check in self.health_checks[component]:
            result = check()
            results.append(result)
            
        # Component is healthy only if ALL checks pass
        if all(results):
            return HealthStatus.HEALTHY
        elif any(results):
            return HealthStatus.DEGRADED  # Partial functionality
        else:
            return HealthStatus.FAILED
```

**Functional Tests:**
- **FTI:** Attempt small file conversion every 60s
- **DIMC:** Verify sensor data actually updating
- **COMC:** Send test message, verify receipt
- **ROC:** Send test command, verify robot response

**Detection:**
```
Heartbeat: ✓  Functional: ✗  →  Status: DEGRADED
Alert: "ROC is sending heartbeats but not processing commands"
```

---

## 6. UI & Alert System

### 6.1 Alert Display Strategy

**Decision:** Centralized alert system in Webthread with component-specific views.

**Alert Priority Levels:**
1. **CRITICAL:** Red, system halt required
2. **WARNING:** Orange, attention needed
3. **INFO:** Blue, informational
4. **SUCCESS:** Green, operation completed

**Alert Display Locations:**

**Main ROA Window:**
```
┌─────────────────────────────────────────────────────────────┐
│ Status Bar (Bottom)                                          │
│ [!] 1 Critical Alert | [⚠] 3 Warnings | [i] 5 Info         │
│ [Click to view details]                                      │
└─────────────────────────────────────────────────────────────┘
```

**Webthread Alert Panel:**
```
┌─────────────────────────────────────────────────────────────┐
│ Alerts & Notifications                                       │
├─────────────────────────────────────────────────────────────┤
│ [!] CRITICAL - robot_001 - MOTOR_OVERHEAT                   │
│     2 minutes ago | Source: DIMC                             │
│     [Acknowledge] [View Details] [Emergency Stop]            │
│                                                               │
│ [⚠] WARNING - robot_003 - GPS_WEAK_SIGNAL                   │
│     5 minutes ago | Source: DIMC                             │
│     [Acknowledge] [View Details]                             │
│                                                               │
│ [i] INFO - FTI - File converted successfully                │
│     10 minutes ago | robot_arm_v2.urdf → .uasset             │
│     [Dismiss]                                                 │
└─────────────────────────────────────────────────────────────┘
```

**Popup Notifications (Critical Only):**
```
┌──────────────────────────────────────┐
│ [!] CRITICAL ALERT                   │
├──────────────────────────────────────┤
│ Robot: robot_001                     │
│ Error: MOTOR_OVERHEAT                │
│ Time: 2025-12-13 14:35:22           │
│                                      │
│ Motor temperature: 95°C (Max: 80°C) │
│ Action taken: Motor stopped         │
│                                      │
│ [Emergency Stop] [View Details] [OK]│
└──────────────────────────────────────┘
```

### 6.2 Webthread Menu Options

**Decision:** Implement tabbed interface for different functionalities.

**Webthread Tabs:**
1. **Dashboard** - Overview of all components
2. **Alerts** - Alert management (as shown above)
3. **Logs** - Detailed system logs with filtering
4. **Analytics** - Performance metrics and graphs
5. **Settings** - Configuration options
6. **Reports** - Generate and export reports

### 6.3 Strategy View - Map Visualization

**Decision:** Multi-mode map system.

**Strategy View Modes:**

**1. Simulation Mode (UE5):**
- Top-down camera view (RTS-style)
- Click-drag to pan
- Scroll to zoom
- Click robots to select
- Real-time position updates from UE5

**2. Real Robot Mode (Live):**
- Pre-loaded map from project files
- Robot positions from GPS/SLAM data
- Sensor fusion for accurate positioning
- Live camera feeds in corner overlays
- Path planning visualization

**3. Hybrid Mode:**
- Satellite/Google Maps base layer
- Robot position overlays
- Mission waypoints
- Geofencing boundaries
- Terrain elevation data

**Map Data Sources:**
```python
class MapDataProvider:
    def __init__(self, mode: MapMode):
        self.mode = mode
        self.data_sources = {
            MapMode.SIMULATION: [UE5WorldData()],
            MapMode.REAL: [PreloadedMap(), RobotGPS(), RobotSLAM()],
            MapMode.HYBRID: [SatelliteMap(), RobotGPS(), GeofenceData()]
        }
```

**User Preference:**
- Configurable in Settings → Strategy View
- Can switch modes dynamically
- Save preference per project

---

## 7. Robot Control System

### 7.1 Controller Support

**Decision:** Full support for PS5, Xbox, and keyboard/mouse.

**Required Libraries (Add to ROC):**
```python
# requirements_roc.txt
pydualsense>=0.7.0      # PS5 DualSense controller
pygame>=2.5.0           # General game controller support
approxeng.input>=3.0.0  # Multi-controller support
evdev>=1.6.0            # Linux event device support
pynput>=1.7.6           # Keyboard/mouse input
```

**Controller Configuration System:**
```python
class ControllerMapper:
    """Maps controller inputs to robot actions."""
    
    def __init__(self):
        self.mappings = {}
        self.controller_type = None  # PS5, Xbox, Keyboard, etc.
        
    def configure_ps5(self):
        """
        Full PS5 DualSense support including:
        - Analog triggers (L2/R2 as pressure-sensitive)
        - Gyroscope for precision control
        - Adaptive triggers (haptic feedback)
        - Touchpad for additional inputs
        """
        self.mappings = {
            'left_stick_x': 'base_rotation',
            'left_stick_y': 'forward_backward',
            'right_stick_x': 'arm_yaw',
            'right_stick_y': 'arm_pitch',
            'L1': 'gripper_open',
            'R1': 'gripper_close',
            'L2_analog': 'speed_control',      # Pressure-sensitive
            'R2_analog': 'height_control',     # Pressure-sensitive
            'triangle': 'mode_switch',
            'circle': 'emergency_stop',
            'square': 'save_position',
            'cross': 'go_to_home',
            'dpad_up': 'increase_precision',
            'dpad_down': 'decrease_precision',
            'touchpad_swipe': 'camera_control',
            'gyro_tilt': 'fine_adjustment'
        }
        
    def load_custom_mapping(self, config_file: str):
        """Load user-defined controller mappings."""
        with open(config_file) as f:
            self.mappings = yaml.safe_load(f)
```

**Controller Configuration UI:**
```
┌─────────────────────────────────────────────────────────────┐
│ Controller Configuration                                     │
├─────────────────────────────────────────────────────────────┤
│ Detected: PS5 DualSense Controller ✓                        │
│                                                               │
│ Button Mapping:                                              │
│ ├─ Left Stick X   →  [Base Rotation        ▼]              │
│ ├─ Left Stick Y   →  [Forward/Backward     ▼]              │
│ ├─ Right Stick X  →  [Arm Yaw              ▼]              │
│ ├─ Right Stick Y  →  [Arm Pitch            ▼]              │
│ ├─ L1             →  [Gripper Open         ▼]              │
│ ├─ R1             →  [Gripper Close        ▼]              │
│ ├─ L2 (Analog)    →  [Speed Control        ▼] ✓ Pressure   │
│ ├─ R2 (Analog)    →  [Height Control       ▼] ✓ Pressure   │
│ └─ ...                                                       │
│                                                               │
│ Advanced Options:                                            │
│ ☑ Enable Gyroscope Control                                  │
│ ☑ Use Adaptive Triggers                                     │
│ ☑ Enable Haptic Feedback                                    │
│ Deadzone: [=====>     ] 15%                                 │
│ Sensitivity: [=======> ] 75%                                │
│                                                               │
│ [Test Controller] [Save] [Load Preset] [Reset to Default]  │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 Device Architecture Decision

**Question:** ROC + Webthread on same device, separate devices, or hybrid?

**Decision:** **Flexible Multi-Mode Architecture**

**Mode 1: Single Device (Default)**
- ROA runs entirely on one computer (workstation/laptop)
- Both ROC and Webthread in same application
- Simplest setup, lowest latency
- **Use Case:** Lab testing, simulation, development

**Mode 2: Controller Device + Monitor Device**
- **Controller Device** (Raspberry Pi + touchscreen):
  - Runs lightweight ROC interface
  - Webthread widget (status summary only)
  - Controller input handling
  - Sends commands to main system
  
- **Monitor Device** (Workstation):
  - Runs full Webthread with analytics
  - Processes sensor data
  - Handles simulation/UE5
  - Generates reports
  
- **Use Case:** Field operations, mobile control

**Mode 3: Fully Distributed**
- ROC on dedicated controller device
- Webthread on monitoring station
- Separate communication channel
- **Use Case:** Remote operations, multiple operators

**Implementation:**
```python
class ROADeploymentMode(Enum):
    SINGLE_DEVICE = "single"
    CONTROLLER_MONITOR = "hybrid"
    FULLY_DISTRIBUTED = "distributed"

class ROAArchitecture:
    def __init__(self, mode: ROADeploymentMode):
        self.mode = mode
        
    def configure(self):
        if self.mode == ROADeploymentMode.SINGLE_DEVICE:
            self.setup_unified()
        elif self.mode == ROADeploymentMode.CONTROLLER_MONITOR:
            self.setup_hybrid()
        else:
            self.setup_distributed()
```

**Recommended Configuration:**
- **Lab/Development:** Single Device
- **Field Operations:** Controller + Monitor (Hybrid)
- **Multiple Operators:** Fully Distributed

### 7.3 Signal Transmission

**Decision:** Adaptive multi-protocol system.

**Communication Protocols (Priority Order):**

1. **WiFi (Primary)**
   - Fastest, highest bandwidth
   - Range: ~100m indoors, ~300m outdoors
   - Protocol: ROS2 over WiFi (DDS/UDP)
   - Frequency: 5GHz (preferred) or 2.4GHz
   
2. **Long-Range WiFi (Secondary)**
   - External antenna/mesh network
   - Range: up to 1km
   - Lower bandwidth but stable
   
3. **4G/5G (Tertiary)**
   - For remote operations
   - Requires cellular module
   - Higher latency (~50-100ms)
   
4. **Bluetooth (Emergency Backup)**
   - Very short range (~10m)
   - Controller connection only
   - Emergency stop commands

**Automatic Failover:**
```python
class CommunicationManager:
    def __init__(self):
        self.protocols = [
            WiFiProtocol(priority=1),
            LongRangeWiFiProtocol(priority=2),
            CellularProtocol(priority=3),
            BluetoothProtocol(priority=4)
        ]
        self.active_protocol = None
        
    def select_best_protocol(self):
        """Automatically select best available protocol."""
        for protocol in self.protocols:
            if protocol.is_available() and protocol.meets_requirements():
                self.active_protocol = protocol
                return protocol
        return None
        
    def handle_connection_loss(self):
        """Failover to next available protocol."""
        self.active_protocol = self.select_best_protocol()
        if not self.active_protocol:
            self.trigger_emergency_stop()
```

**Hardware Requirements:**
- **WiFi:** Built-in on most devices
- **Long-Range:** External WiFi antenna/router
- **Cellular:** USB 4G/5G modem or built-in
- **Bluetooth:** Built-in on most devices

### 7.4 Raspberry Pi Controller

**Decision:** Support Raspberry Pi as dedicated controller device.

**Raspberry Pi Setup:**
- **Model:** Raspberry Pi 4 (4GB+ RAM recommended)
- **OS:** Raspberry Pi OS Lite (64-bit)
- **Display:** 7" touchscreen or HDMI display
- **Input:** PS5/Xbox controller via Bluetooth/USB

**Installation on Raspberry Pi:**
```bash
# Install ROA for Raspberry Pi
wget https://github.com/Omar-Galal-AB/ROA/releases/latest/roa-rpi-installer.sh
chmod +x roa-rpi-installer.sh
sudo ./roa-rpi-installer.sh

# Install in controller mode
roa-setup --mode=controller --connect-to=192.168.1.100
```

**ROC on Raspberry Pi Features:**
- Lightweight interface optimized for touchscreen
- Controller input prioritization
- Network connection to main Webthread
- Emergency stop always available
- Battery indicator (if using portable power)

**Load Distribution Decision:**

**Recommended:** Hybrid approach
- **Raspberry Pi runs:**
  - ROC control interface
  - Controller input processing
  - Emergency stop handling
  - Webthread status widget (lightweight)
  
- **Main computer runs:**
  - Full Webthread with analytics
  - DIMC (sensor data processing)
  - FTI (file conversion)
  - UE5 simulation
  - Heavy computations

**Rationale:**
- Raspberry Pi has limited processing power
- Sensor data processing is CPU-intensive
- Webthread analytics require more resources
- ROC control is lightweight and responsive
- Network latency is acceptable (<50ms)

---

## 8. Autonomous Mode

### 8.1 Pre-programmed Mission Loading

**Decision:** Implement mission file system with auto-loading capability.

**Mission File Format (YAML):**
```yaml
mission:
  id: "mission_001"
  name: "Warehouse Patrol Route Alpha"
  robot: "robot_001"
  created: "2025-12-13T10:00:00Z"
  version: "1.0"
  
  parameters:
    max_speed: 1.5  # m/s
    safety_level: "STANDARD"
    loop: true
    
  waypoints:
    - id: "wp_001"
      position: [10.5, 5.2, 0.0]
      action: "SCAN_AREA"
      duration: 5  # seconds
      
    - id: "wp_002"
      position: [15.0, 5.2, 0.0]
      action: "PICK_OBJECT"
      target: "box_001"
      
    - id: "wp_003"
      position: [15.0, 10.5, 0.0]
      action: "PLACE_OBJECT"
      target: "shelf_A1"
      
  conditions:
    abort_on_error: true
    return_home_on_completion: true
```

**Mission Storage:**
```
~/.roa/missions/
├── robot_001/
│   ├── patrol_route_alpha.yaml
│   ├── inspection_mission.yaml
│   └── delivery_task.yaml
├── robot_002/
│   └── pick_and_place.yaml
└── shared/
    └── emergency_return_home.yaml
```

### 8.2 Automatic Mission Loading

**Auto-Load System:**
```python
class MissionAutoLoader:
    def __init__(self):
        self.mission_directory = Path("~/.roa/missions/").expanduser()
        self.scheduled_missions = {}
        
    def scan_for_scheduled_missions(self):
        """Check for missions scheduled to run."""
        for robot_dir in self.mission_directory.iterdir():
            robot_id = robot_dir.name
            for mission_file in robot_dir.glob("*.yaml"):
                mission = self.load_mission(mission_file)
                
                if self.should_auto_load(mission):
                    self.schedule_mission(robot_id, mission)
                    
    def should_auto_load(self, mission: dict) -> bool:
        """Determine if mission should auto-load."""
        # Check for schedule in mission file
        if 'schedule' in mission:
            schedule = mission['schedule']
            if schedule['type'] == 'time':
                return self.is_scheduled_time(schedule['time'])
            elif schedule['type'] == 'event':
                return self.check_event_trigger(schedule['event'])
            elif schedule['type'] == 'condition':
                return self.evaluate_condition(schedule['condition'])
        return False
        
    def load_mission_to_robot(self, robot_id: str, mission: dict):
        """Load mission into ROC command queue."""
        commands = self.convert_mission_to_commands(mission)
        
        # Add to ROC command queue
        roc_queue = ROCCommandQueue(robot_id)
        for cmd in commands:
            roc_queue.add_command(cmd, priority=CommandPriority.MISSION)
```

**Mission Scheduling Options:**

1. **Time-based:**
```yaml
schedule:
  type: "time"
  time: "14:00:00"  # Run daily at 2 PM
  repeat: "daily"
```

2. **Event-based:**
```yaml
schedule:
  type: "event"
  event: "robot_idle_for_5_minutes"
```

3. **Condition-based:**
```yaml
schedule:
  type: "condition"
  condition: "battery_level > 50 AND robot_status == IDLE"
```

4. **Manual:**
```yaml
schedule:
  type: "manual"  # Operator starts mission
```

### 8.3 Mission Display in ROC

**ROC Commands Menu with Missions:**
```
┌─────────────────────────────────────────────────────────────┐
│ Commands & Missions - robot_001                              │
├─────────────────────────────────────────────────────────────┤
│ Active Mission: Warehouse Patrol Route Alpha                │
│ Status: ● Running | Progress: [======>   ] 65%              │
│ Current Waypoint: wp_002 (15.0, 5.2, 0.0)                   │
│ Next Action: PICK_OBJECT (box_001)                          │
│                                                               │
│ [Pause Mission] [Stop Mission] [View Details]               │
├─────────────────────────────────────────────────────────────┤
│ Available Missions:                                          │
│ □ Patrol Route Alpha        ⏰ Scheduled: 14:00            │
│ □ Inspection Mission        ⚙️  Manual Start               │
│ □ Delivery Task             ⏸️  Paused                     │
│                                                               │
│ [Load Mission] [Create New] [Import] [Refresh]              │
├─────────────────────────────────────────────────────────────┤
│ Manual Command Queue: (3 commands)                          │
│ 1. MOVE_TO (10.0, 5.0, 0.0)      [Priority: HIGH]          │
│ 2. ROTATE (90°)                   [Priority: NORMAL]        │
│ 3. GRIPPER_OPEN                   [Priority: NORMAL]        │
│                                                               │
│ [Add Command] [Clear Queue] [Export as Mission]             │
└─────────────────────────────────────────────────────────────┘
```

**Command Queue Priority:**
1. **EMERGENCY:** Emergency stop, safety overrides
2. **MISSION:** Autonomous mission commands
3. **OPERATOR:** Manual operator commands
4. **BACKGROUND:** Status updates, telemetry

---

## 9. Component Interaction Details

### 9.1 DIMC → ROC Information Flow

**Question:** Which component sends robot info to ROC?

**Answer:** **DIMC is the primary source**, but multiple components contribute:

**Information Flow:**
```
Sensors → DIMC (processes) → ROC (displays + uses for control)
Robot State → COMC (transmits) → ROC (updates)
UE5 World → Webthread (monitors) → ROC (context)
```

**DIMC Responsibilities:**
- Process raw sensor data (LiDAR, cameras, IMU, GPS)
- Compute spatial data (position, orientation, obstacles)
- Publish processed data to ROS2 topics
- Monitor sensor health

**ROC Receives from:**
1. **DIMC:** Spatial data, sensor readings, obstacle maps
2. **COMC:** Robot state, command acknowledgments
3. **Webthread:** System health, component status
4. **Direct from Robot:** Emergency signals, hardware status

**Data Flow Example:**
```python
# DIMC publishes spatial data
dimc_node.publish_spatial_data(
    robot_id="robot_001",
    position=[10.5, 5.2, 0.0],
    orientation=[0.0, 0.0, 45.0],
    obstacles=[
        Obstacle(position=[12.0, 6.0, 0.0], size=0.5),
        Obstacle(position=[14.0, 4.0, 0.0], size=0.8)
    ],
    sensors={
        'camera_1': SensorStatus.ACTIVE,
        'lidar_1': SensorStatus.ACTIVE,
        'gps_1': SensorStatus.WEAK_SIGNAL
    }
)

# ROC subscribes and updates display
roc_node.subscribe('/spatial_data', self.update_robot_display)
```

---

## 10. FTI Advanced Features

### 10.1 UE5 Robot Assembly

**Question:** How does FTI convert motion ranges, joints, and assemble robots in UE5?

**Answer:** Multi-step automated process using UE5 Python API.

**Conversion Pipeline:**
```
URDF/STEP File → FTI Parser → Joint Extraction → 
→ UE5 Asset Creation → Physics Setup → Control Configuration
```

**Implementation:**
```python
class FTI_UE5_Assembler:
    def __init__(self):
        self.ue5_api = UE5PythonAPI()
        
    def convert_robot_to_ue5(self, urdf_file: str, output_path: str):
        """
        Complete robot conversion and assembly in UE5.
        """
        # Step 1: Parse URDF
        robot_model = URDFParser.parse(urdf_file)
        
        # Step 2: Extract components
        links = robot_model.get_links()
        joints = robot_model.get_joints()
        meshes = robot_model.get_meshes()
        
        # Step 3: Import meshes to UE5
        ue5_assets = {}
        for mesh in meshes:
            asset = self.ue5_api.import_mesh(
                mesh_file=mesh.file_path,
                output_path=f"{output_path}/Meshes/{mesh.name}"
            )
            ue5_assets[mesh.name] = asset
            
        # Step 4: Create Blueprint
        robot_bp = self.ue5_api.create_blueprint(
            name=robot_model.name,
            parent_class="Actor",
            output_path=f"{output_path}/Robots/"
        )
        
        # Step 5: Assemble components in Blueprint
        root_component = self.create_root(robot_bp, robot_model.root_link)
        
        for joint in joints:
            self.add_joint_to_blueprint(
                blueprint=robot_bp,
                joint=joint,
                parent_mesh=ue5_assets[joint.parent_link],
                child_mesh=ue5_assets[joint.child_link]
            )
            
        # Step 6: Configure physics
        for joint in joints:
            self.setup_physics_constraint(
                blueprint=robot_bp,
                joint=joint,
                motion_range=joint.limits  # From URDF
            )
            
        # Step 7: Add control interface
        self.add_roc_control_interface(robot_bp, robot_model)
        
        # Step 8: Save and compile
        self.ue5_api.compile_blueprint(robot_bp)
        
        return robot_bp
        
    def add_joint_to_blueprint(self, blueprint, joint, parent_mesh, child_mesh):
        """Add joint with proper hierarchy and transforms."""
        
        # Create Physics Constraint component
        constraint = self.ue5_api.add_component(
            blueprint=blueprint,
            component_type="PhysicsConstraintComponent",
            name=f"Constraint_{joint.name}"
        )
        
        # Configure constraint based on joint type
        if joint.type == "revolute":
            constraint.set_angular_limits(
                swing1_motion="ACM_Locked",
                swing2_motion="ACM_Locked",
                twist_motion="ACM_Limited"
            )
            constraint.set_angular_twist_limit(
                angle_min=math.degrees(joint.lower_limit),
                angle_max=math.degrees(joint.upper_limit)
            )
            
        elif joint.type == "prismatic":
            constraint.set_linear_limits(
                x_motion="ACM_Limited",
                y_motion="ACM_Locked",
                z_motion="ACM_Locked"
            )
            constraint.set_linear_x_limit(
                limit_min=joint.lower_limit,
                limit_max=joint.upper_limit
            )
            
        # Set up constraint connections
        constraint.set_constrained_components(
            component1=parent_mesh,
            component2=child_mesh
        )
        
    def setup_physics_constraint(self, blueprint, joint, motion_range):
        """Configure realistic physics for joint."""
        
        # Add motor for active control
        motor = self.ue5_api.add_angular_motor(
            constraint_name=f"Constraint_{joint.name}",
            max_force=joint.effort_limit,
            max_velocity=joint.velocity_limit
        )
        
        # Enable collision between non-adjacent links only
        self.ue5_api.set_collision_response(
            blueprint=blueprint,
            link1=joint.parent_link,
            link2=joint.child_link,
            collision_enabled=False  # Adjacent links don't collide
        )
        
    def add_roc_control_interface(self, blueprint, robot_model):
        """Add ROS2 control interface to Blueprint."""
        
        # Add ROS2 component
        ros2_comp = self.ue5_api.add_component(
            blueprint=blueprint,
            component_type="ROS2Component",
            name="ROC_Interface"
        )
        
        # Subscribe to control commands
        ros2_comp.subscribe_to_topic(
            topic=f"/robot/{robot_model.name}/joint_commands",
            message_type="JointCommand"
        )
        
        # Publish joint states
        ros2_comp.publish_on_topic(
            topic=f"/robot/{robot_model.name}/joint_states",
            message_type="JointState",
            frequency=60  # Hz
        )
        
        # Add Blueprint event handlers
        self.ue5_api.add_event_graph(
            blueprint=blueprint,
            event="OnJointCommandReceived",
            logic=[
                "Parse incoming joint command",
                "Apply force/position to each joint motor",
                "Update joint state",
                "Publish new state to ROS2"
            ]
        )
```

**Result in UE5:**
- Fully assembled robot with correct hierarchy
- All joints configured with motion ranges from URDF
- Physics constraints matching real robot
- ROS2 control interface ready
- Can be immediately tested in UE5 simulation

**Minimal Manual Setup Required:**
- Adjust material colors/textures (optional)
- Fine-tune collision meshes if needed (FTI uses defaults)
- Configure advanced physics (friction, damping) if needed

**FTI Automated Setup:**
- ✓ Import all meshes
- ✓ Create component hierarchy
- ✓ Configure all joints with limits
- ✓ Set up physics constraints
- ✓ Add ROS2 control interface
- ✓ Enable collision detection
- ✓ Compile Blueprint
- ✓ Robot ready to use

### 10.2 Standalone FTI Operation

**Decision:** FTI works independently of UE5.

**Modes:**
1. **UE5 Connected:** Direct conversion to UE5 project
2. **UE5 Disconnected:** Export to specified directory

**UI Behavior (from section 2.3):**
- Button changes based on UE5 connection status
- User selects output directory when disconnected
- Generated files are UE5-importable (uasset format)
- Can be imported later when UE5 is available

---

## 11. DIMC Sensor Integration

### 11.1 Automatic Sensor Detection

**Question:** How does DIMC automatically use robot sensors?

**Answer:** Robot configuration file declares sensors, DIMC auto-discovers and integrates.

**Robot Configuration (Extended):**
```yaml
robot:
  id: "robot_001"
  name: "Mobile Manipulator Alpha"
  
  sensors:
    - id: "camera_front"
      type: "camera"
      topic: "/robot_001/camera/front/image"
      frame_rate: 30
      resolution: [1920, 1080]
      
    - id: "lidar_main"
      type: "lidar"
      topic: "/robot_001/lidar/scan"
      scan_rate: 10
      range: [0.1, 30.0]  # meters
      fov: 360  # degrees
      
    - id: "imu_main"
      type: "imu"
      topic: "/robot_001/imu/data"
      frequency: 100  # Hz
      
    - id: "gps_main"
      type: "gps"
      topic: "/robot_001/gps/fix"
      frequency: 1  # Hz
      
    - id: "ultrasonic_1"
      type: "ultrasonic"
      topic: "/robot_001/ultrasonic/1"
      frequency: 20
      range: [0.02, 4.0]
```

**DIMC Auto-Discovery:**
```python
class DIMCSensorManager:
    def __init__(self, robot_config: dict):
        self.robot_id = robot_config['robot']['id']
        self.sensors = robot_config['robot']['sensors']
        self.subscribers = {}
        
    def initialize_sensors(self):
        """Automatically subscribe to all sensor topics."""
        for sensor in self.sensors:
            subscriber = self.create_subscriber(
                topic=sensor['topic'],
                message_type=self.get_message_type(sensor['type']),
                callback=self.create_sensor_callback(sensor)
            )
            self.subscribers[sensor['id']] = subscriber
            
    def create_sensor_callback(self, sensor: dict):
        """Generate appropriate callback based on sensor type."""
        sensor_type = sensor['type']
        
        if sensor_type == 'camera':
            return lambda msg: self.process_camera_data(sensor['id'], msg)
        elif sensor_type == 'lidar':
            return lambda msg: self.process_lidar_data(sensor['id'], msg)
        elif sensor_type == 'imu':
            return lambda msg: self.process_imu_data(sensor['id'], msg)
        elif sensor_type == 'gps':
            return lambda msg: self.process_gps_data(sensor['id'], msg)
        elif sensor_type == 'ultrasonic':
            return lambda msg: self.process_ultrasonic_data(sensor['id'], msg)
            
    def process_sensor_data(self):
        """Fuse all sensor data into spatial representation."""
        spatial_data = SpatialData()
        
        # Position from GPS + IMU fusion
        spatial_data.position = self.fuse_position_data()
        
        # Orientation from IMU
        spatial_data.orientation = self.get_imu_orientation()
        
        # Obstacles from LiDAR + Ultrasonic + Camera
        spatial_data.obstacles = self.detect_obstacles()
        
        # Publish integrated data
        self.publish_spatial_data(spatial_data)
```

**Sensor Fusion Process:**
1. DIMC reads robot config on initialization
2. Auto-subscribes to all sensor topics
3. Processes each sensor type appropriately
4. Fuses data into coherent spatial representation
5. Publishes integrated data to ROC and other components

**No Manual Configuration Required:**
- Sensors defined once in robot config
- DIMC handles everything automatically
- New sensors? Just add to config file
- DIMC dynamically adapts

---

## 12. Implementation Priority

### 12.1 Immediate Actions (Phase 1)

1. **Installer Creation**
   - Windows: NSIS or Inno Setup
   - Linux: Debian/RPM packages
   - Include auto-update mechanism

2. **UE5 Plugin Package**
   - Plugin structure following UE5 conventions
   - Auto-enable on installation
   - Integration with UE5 Editor

3. **Unified Application UI**
   - Single main window
   - Five component tabs
   - Separate windows for ROC and Webthread

4. **Controller Support**
   - Add required libraries (pydualsense, pygame, etc.)
   - Implement controller configuration UI
   - PS5 full feature support (analog triggers, gyro)

### 12.2 Short-term Actions (Phase 2)

1. **File Storage System**
   - Implement tiering (snapshot → backup → archive)
   - Dual storage (standalone vs UE5 plugin)
   - Scheduled tiering jobs

2. **Mission System**
   - Mission file format and parser
   - Auto-loading based on schedules
   - Integration with ROC command queue

3. **Error System**
   - Robot-specific error definitions
   - DIMC error classification
   - Alert propagation to all components

4. **FTI UE5 Assembly**
   - URDF to UE5 Blueprint conversion
   - Automatic joint configuration
   - Physics constraint setup

### 12.3 Medium-term Actions (Phase 3)

1. **Raspberry Pi Support**
   - ARM-optimized builds
   - Touchscreen interface
   - Network architecture for distributed mode

2. **Advanced Sensor Integration**
   - Automatic sensor discovery in DIMC
   - Sensor fusion algorithms
   - Camera-based obstacle detection

3. **Strategy View**
   - Multiple map modes (simulation, real, hybrid)
   - Real-time robot position updates
   - Path planning visualization

4. **Component Health System**
   - Functional health checks beyond heartbeats
   - Automated remediation
   - Performance monitoring

---

## 13. Summary of Key Decisions

| Topic | Decision | Rationale |
|-------|----------|-----------|
| **Application Structure** | Single unified ROA app | Simplified UX, better integration |
| **Installation** | Dual packages (standalone + UE5 plugin) | Supports both use cases |
| **Auto-Update** | Integrated update system | Keep users on latest version |
| **File Storage** | Dual location (system + project) | Context-appropriate storage |
| **File Tiering** | Automatic with configurable retention | Manage storage automatically |
| **Webthread Startup** | Cache-optimized second launch | Faster startup after first run |
| **Memory** | Hybrid (per-project + collective) | Best of both approaches |
| **Health Checks** | Functional tests beyond heartbeats | Detect degraded state |
| **Alerts** | Centralized in Webthread + popups for critical | Balanced notification system |
| **Map Visualization** | Multi-mode (sim/real/hybrid) | Flexible for different scenarios |
| **Controller Support** | Full PS5/Xbox + keyboard/mouse | Maximum control options |
| **Device Architecture** | Flexible multi-mode | Adaptable to deployment scenario |
| **Communication** | WiFi primary with failover | Reliable with backups |
| **Raspberry Pi** | Supported as controller device | Enable mobile control |
| **Mission System** | File-based with auto-loading | Flexible automation |
| **DIMC** | Primary source of robot info | Centralized sensor processing |
| **FTI UE5 Assembly** | Fully automated from URDF | Minimal manual setup |
| **FTI Standalone** | Operational without UE5 | Greater flexibility |
| **Sensor Integration** | Automatic from config file | Zero-configuration operation |

---

## Next Steps

1. Review this architecture document
2. Approve key decisions
3. Begin Phase 1 implementation
4. Provide Qt Designer files when ready
5. Test on Raspberry Pi once controller mode is implemented

This document serves as the architectural blueprint for ROA development. All design decisions are documented with rationale and implementation guidance.
