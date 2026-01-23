# Webthread Initializer Module

**Module Name:** WebthreadInitializer  
**Parent Component:** Webthread  
**Type:** One-time startup orchestrator  
**Lifecycle:** Runs once at system startup, then exits  

---

## Overview

The WebthreadInitializer is a dedicated module within Webthread responsible for orchestrating ROA's complete startup sequence. It handles all one-time initialization tasks including UE5 environment configuration, physics setup, input system initialization, UI loading, and component startup coordination.

**Key Principle:** This is a **startup-only** module, NOT a continuous runtime dependency. After initialization completes, it exits and hands control to runtime Webthread.

---

## Full Capabilities

### 1. UE5 Environment Configuration

**Physics System Setup:**
- Configure Chaos Physics engine to Gazebo-equivalent parameters
- Set solver iterations (position: 8, velocity: 8)
- Configure physics substeps (6-8 for robotics accuracy)
- Enable CCD (Continuous Collision Detection)
- Set world gravity to -980 cm/s² (UE5 units)
- Apply unit scaling (1 UE unit = 1 cm)

**Physics Material Presets:**
- Metal: Friction 0.4/0.35, Restitution 0.3, Density 7850 kg/m³
- Plastic: Friction 0.5/0.4, Restitution 0.5, Density 1200 kg/m³
- Rubber: Friction 0.9/0.8, Restitution 0.7, Density 1100 kg/m³
- Concrete: Friction 0.6/0.5, Restitution 0.2, Density 2400 kg/m³

**Joint Configuration Defaults:**
- Damping: 0.1
- Stiffness: 1000 N/m
- Angular limits: -180° to +180° (configurable per joint)
- Motor drives enabled with torque limits from URDF

**Validation Tests:**
- Drop test (verify gravity and collision response)
- Friction test (sliding block on incline)
- Joint movement test (verify limits and damping)

### 2. Input System Initialization

**Keyboard/Mouse Handler Setup:**
- Register context-sensitive input mappings
- Configure 120 Hz input polling rate
- Set keyboard latency target: <10ms
- Set mouse latency target: <15ms
- Initialize keybinding conflict detection system
- Load custom keybinding profiles (up to 5 saved profiles)

**Default Input Contexts:**
- RPM Mode input bindings (WASD, Arrows, Q/E, Y/U, C/V, R, T, Space, Tab)
- ADM Mode input bindings (WASD camera, Arrows nav, M/P/L/F/G/R/H, Ctrl+A)
- Shared bindings (V for view switching, F1/F2/F3/F12 for UI)
- Mouse sensitivity defaults (1.0x, configurable 0.5x-3.0x)

**Input Validation:**
- Test keyboard response time (<10ms requirement)
- Test mouse response time (<15ms requirement)
- Verify no input binding conflicts
- Validate gamepad/alternative input device support (if connected)

### 3. UI System Initialization

**UI Overlay Loading:**
- Semi-transparent shortcuts panel (60% opacity default)
- Mode indicator (RPM/ADM with color coding)
- Context-sensitive help overlay (F12)
- Emergency stop indicator
- Robot status panel
- Command menu overlay (right-click in ADM)

**UI Configuration:**
- Set refresh rate: 60 Hz
- Context help fade rate: 30 Hz
- Auto-hide delay: 5s (default, configurable 3s/5s/10s/Never)
- Font size: Medium (configurable Small/Medium/Large)
- Color scheme: Dark (configurable Light/Dark/High-contrast)
- UI transparency: 60% (configurable 20%-90%)

**UI Positioning:**
- Shortcuts panel: Bottom-right corner (default, draggable)
- Mode indicator: Top-left corner
- Status panel: Bottom-left corner
- Command menu: Cursor position (ADM mode)

**UI Performance Targets:**
- Toggle response time: <30ms (F1/F2/F3 keys)
- Menu open time: <50ms (right-click)
- Fade transition: 200ms smooth

### 4. Component Startup Coordination

**Startup Sequence:**

**Phase 1: Pre-checks (5-10 seconds)**
- Verify UE5 version compatibility (5.6 or later required)
- Check ROS2 installation (Humble LTS required)
- Validate platform (Ubuntu 22.04 primary, Windows 10/11 secondary)
- Verify hardware requirements (Alienware R5 specs)
- Check network connectivity for COMC
- Validate SQLite database access

**Phase 2: Environment Setup (10-15 seconds)**
- Execute physics configuration
- Initialize input system
- Load UI overlays
- Create/validate workspace directories
- Load configuration files (physics presets, keybindings, UI settings)

**Phase 3: Component Initialization (15-25 seconds)**
1. **FTI** - Files Type Importer
   - Start file monitoring service
   - Validate 3D format converters (URDF, XACRO, STL, SDF, USD)
   - Initialize conversion pipeline
   - Confirm ready status

2. **DIMC** - Dimensions Collector  
   - Initialize sensor simulation layer
   - Start environment scanning service
   - Calibrate obstacle detection (Evade subsystem)
   - Confirm ready status

3. **ROC** - Robot Operator Controller
   - Initialize ROS2 Control framework
   - Load control mode state machines (RPM/ADM)
   - Start safety system (Fragile/Standard/Robust modes)
   - Initialize Evade path planning (A*/RRT)
   - Confirm ready status

4. **COMC** - Communication Center
   - Initialize DDS middleware
   - Establish robot-to-robot communication channels
   - Start traffic priority system
   - Initialize multi-robot coordination
   - Confirm ready status

5. **Webthread Runtime**
   - Start health monitoring (500ms periodic checks)
   - Initialize error handling and recovery system
   - Begin component coordination
   - Activate logging and diagnostics

**Phase 4: Validation (5-10 seconds)**
- Test inter-component communication
- Verify all 5 components responding
- Run latency tests (control loop <20ms target)
- Validate safety system activation
- Confirm UI responsiveness

**Total Startup Time:** 35-60 seconds (typical: 45 seconds)

### 5. Configuration Management

**Configuration Files Loaded:**
- `roa_physics_config.ini` - Physics parameters
- `roa_keybindings.json` - Input mappings (5 profiles)
- `roa_ui_settings.json` - UI preferences
- `roa_component_config.yaml` - Component startup parameters
- `roa_safety_rules.json` - Traffic priority and safety settings

**Configuration Validation:**
- Schema validation for all config files
- Range checking (e.g., opacity 20%-90%)
- Conflict detection (e.g., duplicate keybindings)
- Fallback to defaults if config corrupted

**Configuration Persistence:**
- Save settings to `Config/DefaultEngine.ini` (UE5)
- Save user preferences to `~/.roa/` directory (Linux)
- Save user preferences to `%APPDATA%/ROA/` (Windows)

### 6. Error Handling and Recovery

**Initialization Failure Modes:**

**CRITICAL (Abort startup):**
- UE5 version incompatible
- ROS2 not found or wrong version
- Physics engine initialization failure
- No write access to config directories
- SQLite database locked or corrupted

**WARNING (Continue with degraded mode):**
- Custom keybindings file corrupted → Use defaults
- UI settings invalid → Use defaults
- One component fails to start → Log error, continue (graceful degradation)
- Network unavailable → COMC operates in local-only mode

**Recovery Actions:**
- **Retry Logic:** 3 attempts with exponential backoff (1s, 2s, 4s)
- **Fallback Configs:** Always maintain valid default configurations
- **User Notification:** Display detailed error messages in UE5 viewport
- **Diagnostic Mode:** Option to start in safe mode (minimal features)

**Error Reporting:**
- Write to `roa_init.log` with timestamp and stack trace
- Display in-engine notification with error code
- Offer "Report Issue" button (generates diagnostic bundle)

### 7. Diagnostic and Logging

**Initialization Log:**
- Startup timestamp
- UE5/ROS2 version detected
- Hardware specs detected (CPU, RAM, GPU)
- Each phase duration (Pre-checks: 8s, Setup: 12s, etc.)
- Component startup order and status
- Configuration files loaded
- Any warnings or errors encountered
- Final status (SUCCESS / PARTIAL / FAILED)

**Log Location:**
- Console output (real-time)
- `roa_init.log` file in project root
- UE5 Output Log integration

**Performance Metrics:**
- Total initialization time
- Per-component startup time
- Physics validation test results
- Input latency test results (keyboard/mouse)
- UI refresh rate validation

### 8. Version and Compatibility Management

**Version Checks:**
- UE5 minimum version: 5.6
- ROS2 version: Humble LTS (required)
- Python version: 3.10+ (for tools)
- USD library version compatibility
- DDS implementation check (FastDDS vs CycloneDDS)

**Compatibility Matrix:**
- Ubuntu 22.04 + UE5 5.6+ + ROS2 Humble = SUPPORTED
- Windows 10/11 + UE5 5.6+ + ROS2 Humble = SUPPORTED (secondary)
- Other configurations = WARNING (may work but untested)

**Automatic Updates Check:**
- Check for ROA component updates (optional)
- Notify if newer physics presets available
- Suggest UE5 plugin updates if available

---

## Startup Flow Diagram

```
START
  ↓
[Pre-checks] → Version, Platform, Hardware, Network
  ↓ (PASS)
[Environment Setup] → Physics, Input, UI, Configs
  ↓ (COMPLETE)
[Component Init] → FTI → DIMC → ROC → COMC → Webthread Runtime
  ↓ (ALL READY)
[Validation] → Comms Test, Latency Test, Safety Test
  ↓ (PASS)
[Handoff to Runtime Webthread]
  ↓
WebthreadInitializer EXITS
  ↓
SYSTEM READY
```

**Failure Path:**
```
Any Phase FAILS
  ↓
[Error Handler]
  ↓
CRITICAL? → YES → [Abort + Error Report] → STOP
  ↓ NO
[Apply Fallback/Degraded Mode]
  ↓
[Continue Next Phase]
```

---

## Integration with Runtime Webthread

**Handoff Process:**

1. **Initialization Complete Signal:**
   - WebthreadInitializer sets `initialization_complete` flag
   - Transfers control to runtime Webthread
   - Exits cleanly (frees memory)

2. **Runtime Webthread Receives:**
   - List of active components with health status
   - Configuration snapshot (physics, input, UI settings)
   - Any warnings from initialization (for monitoring)

3. **Runtime Phase Begins:**
   - Webthread monitors component health (500ms intervals)
   - Coordinates inter-component communication
   - Handles runtime errors (different from init errors)
   - Performs graceful degradation if components fail

**Key Distinction:**
- **WebthreadInitializer:** One-time setup orchestrator (exits after startup)
- **Runtime Webthread:** Continuous monitoring and coordination (runs entire session)

---

## Configuration File Examples

### roa_physics_config.ini
```ini
[Solver]
PositionIterations = 8
VelocityIterations = 8
Substeps = 6
EnableCCD = true

[World]
Gravity = -980.0
UnitScale = 1.0

[Materials]
Metal_Friction_Static = 0.4
Metal_Friction_Dynamic = 0.35
Metal_Restitution = 0.3
Metal_Density = 7850.0
```

### roa_keybindings.json
```json
{
  "profile_name": "Default",
  "rpm_mode": {
    "move_forward": "W",
    "move_left": "A",
    "move_back": "S",
    "move_right": "D",
    "gripper_close": "C",
    "gripper_open": "V",
    "emergency_stop": "Space"
  },
  "adm_mode": {
    "camera_pan": "Mouse_Middle_Drag",
    "move_command": "M",
    "pick_command": "P"
  },
  "shared": {
    "view_toggle": "V",
    "help_overlay": "F12"
  }
}
```

---

## Development Notes

**Implementation Language:** C++ (UE5 module) + Python (ROS2 integration)

**Module Structure:**
- `WebthreadInitializer.cpp/h` - Main orchestrator
- `PhysicsConfigurator.cpp/h` - Physics setup
- `InputInitializer.cpp/h` - Input system
- `UIInitializer.cpp/h` - UI overlay setup
- `ComponentStarter.cpp/h` - Component startup coordination
- `ConfigManager.cpp/h` - Configuration loading/validation

**Testing Strategy:**
- Unit tests for each subsystem (physics, input, UI)
- Integration test for full startup sequence
- Failure injection tests (missing config, wrong versions, etc.)
- Performance tests (startup time <60s requirement)

**Future Enhancements:**
- Parallel component initialization (reduce startup time to ~30s)
- Progressive UI loading (show partial UI while loading)
- Cloud-based configuration sync
- Automated performance benchmarking on startup

---

## Success Criteria

**Initialization Successful When:**
1. All 5 components started and responding ✅
2. Physics configured to Gazebo-equivalent accuracy ✅
3. Input system responsive (<10ms keyboard, <15ms mouse) ✅
4. UI overlays rendered at 60 Hz ✅
5. Inter-component communication validated ✅
6. No critical errors in log ✅
7. Total startup time <60 seconds ✅

**User Experience:**
- Clear progress indicator (Loading... 65%)
- Informative status messages ("Configuring physics...", "Starting ROC...")
- Error messages are actionable ("ROS2 not found. Install via apt install ros-humble-desktop")
- Smooth transition to runtime (no jarring UI changes)

---

**Last Updated:** 2025-11-16  
**Version:** 1.0  
**Status:** Design Complete - Ready for Implementation
