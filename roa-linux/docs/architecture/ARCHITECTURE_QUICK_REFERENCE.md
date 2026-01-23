# ROA Architecture Quick Reference

**For complete details, see:** [ROA_ARCHITECTURE_DECISIONS.md](ROA_ARCHITECTURE_DECISIONS.md)

---

## Installation & Deployment

| Question | Answer |
|----------|--------|
| **How to install?** | Two modes: Standalone app OR UE5 plugin |
| **Platforms?** | Windows (exe), Linux (deb/rpm) |
| **Shortcuts?** | Auto-created on installation |
| **Updates?** | Automatic with rollback support |
| **Raspberry Pi?** | Full support as controller device |

**Installer locations:** `installers/windows/`, `installers/linux/`

---

## Application Structure

```
┌─────────────────────────────────────────┐
│ ROA - Single Unified Application        │
├─────────────────────────────────────────┤
│ [FTI] [DIMC] [COMC] [ROC] [Webthread]  │  ← Main Window (5 tabs)
└─────────────────────────────────────────┘

┌─────────────────────────┐  ┌─────────────────────────┐
│ ROC                     │  │ Webthread               │
│ (Separate Window)       │  │ (Separate Window)       │
│ - Robot controls        │  │ - System monitor        │
│ - Multi-robot support   │  │ - Alerts & logs         │
│ - Controller config     │  │ - Analytics             │
└─────────────────────────┘  └─────────────────────────┘
```

**Key:** ONE app, not separate apps per component

---

## File Storage

### Locations

| Mode | Location | Purpose |
|------|----------|---------|
| **Standalone** | `~/.roa/` (Linux/Mac)<br>`C:\Users\<User>\AppData\Roaming\ROA\` (Windows) | System-wide storage |
| **UE5 Plugin** | `UE5_Project/Saved/ROA/` | Project-specific storage |

### Automatic Tiering

```
Snapshot (0-24h) → Backup (24h-30d) → Archive (30d-1y) → Deleted
```

Runs daily at 2:00 AM automatically.

---

## Controllers

### Supported Hardware
- ✅ PS5 DualSense (full features)
- ✅ Xbox controllers
- ✅ Keyboard + Mouse
- ✅ Generic USB controllers

### PS5 Special Features
- Analog triggers (pressure-sensitive)
- Gyroscope for precision
- Adaptive triggers with haptic
- Touchpad for extra inputs

### Installation
```bash
pip install -r requirements_controllers.txt
```

---

## Device Architecture

### Three Modes

1. **Single Device** (Default)
   - Everything on one computer
   - Simplest setup, lowest latency
   - Use: Lab testing, development

2. **Controller + Monitor** (Hybrid) ⭐ Recommended
   - Controller Device (Raspberry Pi): ROC + light Webthread widget
   - Monitor Device (Workstation): Full Webthread + analytics
   - Use: Field operations

3. **Fully Distributed**
   - ROC on dedicated controller
   - Webthread on monitoring station
   - Use: Remote operations, multiple operators

---

## Communication

### Protocol Priority (Automatic Failover)

1. **WiFi** (Primary) - Fast, 100m-300m range
2. **Long-Range WiFi** - Up to 1km with antenna
3. **4G/5G Cellular** - Remote operations
4. **Bluetooth** - Emergency backup (10m)

System automatically selects best available protocol.

---

## Component Responsibilities

| Component | Primary Role | Data Flow |
|-----------|-------------|-----------|
| **FTI** | File conversion & UE5 assembly | URDF/STEP → UE5 Blueprint |
| **DIMC** | Sensor processing & spatial data | Sensors → Processed data → ROC |
| **COMC** | Communication & message routing | Commands ↔ Robots ↔ Components |
| **ROC** | Robot control & operator interface | User input → Commands → Robots |
| **Webthread** | System monitoring & coordination | Status ← All components |

---

## Error System

### How Errors Are Identified

1. Robot publishes error code
2. DIMC receives error
3. DIMC looks up error in robot's config YAML
4. DIMC executes predefined actions
5. Alert sent to all components

**Example robot config:**
```yaml
error_definitions:
  - code: 101
    name: "MOTOR_OVERHEAT"
    severity: "CRITICAL"
    actions: ["STOP_MOTOR", "ALERT_OPERATOR"]
```

---

## FTI UE5 Assembly

### What's Automated?

✅ Import all meshes from URDF  
✅ Create Blueprint with hierarchy  
✅ Configure joints with motion limits  
✅ Set up physics constraints  
✅ Add ROS2 control interface  
✅ Enable collision detection  
✅ Compile Blueprint  

**Result:** Robot ready to test in UE5 immediately, minimal manual work needed.

### Standalone Mode

FTI works WITHOUT UE5:
- Button shows "Convert Designs Outside UE5"
- User selects output directory
- Generates importable UE5 assets
- Can import later when UE5 available

---

## Webthread Behavior

### First Launch vs. Subsequent

| First Launch | Subsequent Launches |
|-------------|-------------------|
| Full initialization | Load cached config |
| Scan for configs | Skip if unchanged |
| Initialize all components | Verify health only |
| ~10 seconds | ~2 seconds |

### Memory Architecture

**Per-Project Memory:**
- Project settings
- Robot configurations
- Session history

**Collective Memory (Cross-Project):**
- User preferences
- Robot usage history
- Learned patterns
- Global error trends

---

## Autonomous Missions

### Mission File Format (YAML)

```yaml
mission:
  id: "mission_001"
  name: "Warehouse Patrol"
  
  schedule:
    type: "time"      # or "event" or "condition"
    time: "14:00:00"
    
  waypoints:
    - position: [10.5, 5.2, 0.0]
      action: "SCAN_AREA"
```

### Auto-Loading Options

1. **Time-based:** Run at specific time daily
2. **Event-based:** Trigger on event (e.g., robot idle)
3. **Condition-based:** When condition met (e.g., battery > 50%)
4. **Manual:** Operator starts

**Location:** `~/.roa/missions/robot_id/`

---

## Strategy View - Map Modes

### Three Modes

1. **Simulation (UE5)**
   - Top-down RTS-style camera
   - Real-time from UE5 world

2. **Real Robot**
   - Pre-loaded map
   - GPS + SLAM positioning
   - Live camera overlays

3. **Hybrid**
   - Satellite/Google Maps base
   - Robot position overlays
   - Geofencing boundaries

User selects mode in Settings, can switch dynamically.

---

## DIMC Sensor Integration

### Automatic Discovery

1. DIMC reads robot config YAML
2. Finds `sensors:` section
3. Auto-subscribes to each sensor topic
4. Processes based on sensor type (camera/lidar/imu/gps)
5. Fuses data into spatial representation
6. Publishes to ROC

**No manual configuration required!**

---

## Alert Display

### Where Alerts Appear

| Priority | Display Location |
|----------|-----------------|
| **CRITICAL** | Popup + Webthread + Status Bar |
| **WARNING** | Webthread + Status Bar |
| **INFO** | Webthread only |
| **SUCCESS** | Status Bar only |

### Webthread Tabs

1. **Dashboard** - Component overview
2. **Alerts** - Alert management
3. **Logs** - Detailed logs with filtering
4. **Analytics** - Performance metrics
5. **Settings** - Configuration
6. **Reports** - Generate exports

---

## Component Health Checks

### Beyond Heartbeats

Each component has **functional tests**:

- **FTI:** Attempt small file conversion every 60s
- **DIMC:** Verify sensor data actually updating
- **COMC:** Send test message, verify receipt
- **ROC:** Send test command, verify response

**Detection:**
```
Heartbeat: ✓  Functional: ✗
Status: DEGRADED
Alert: "ROC sending heartbeats but not processing commands"
```

---

## Implementation Status

### Phase 0: Complete ✅

- Gap analyses
- Architecture design
- Mock ROS2 system
- Mock UE5 system
- Qt Designer converter
- ROC test suite (155 tests)
- CI/CD pipeline

### Next: Phase 1

**Foundation & Packaging**
- Create installers
- Build unified application
- Package system

**Timeline:** 26 weeks for complete system  
**See:** [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md)

---

## Quick Commands

```bash
# Install ROA (Linux)
sudo dpkg -i ROA_Setup_v1.0.0.deb

# Install controller support
pip install -r requirements_controllers.txt

# Launch ROA
roa

# Run diagnostics
roa --diagnostics

# Check for updates
roa --check-updates

# Rollback update
roa --rollback

# Raspberry Pi controller mode
roa-setup --mode=controller --connect-to=192.168.1.100
```

---

## Documentation Index

| Document | Purpose |
|----------|---------|
| **ROA_ARCHITECTURE_DECISIONS.md** | Complete architectural blueprint (52KB) |
| **IMPLEMENTATION_ROADMAP.md** | 10-phase implementation plan (11KB) |
| **INSTALLATION_GUIDE.md** | Installation instructions (8KB) |
| **HOW_TO_PROCEED.md** | Next steps guide |
| **ARCHITECTURE_QUICK_REFERENCE.md** | This document |

---

**For detailed explanations, code examples, and implementation specifics:**
👉 **See [ROA_ARCHITECTURE_DECISIONS.md](ROA_ARCHITECTURE_DECISIONS.md)**

**Last Updated:** 2025-12-13
