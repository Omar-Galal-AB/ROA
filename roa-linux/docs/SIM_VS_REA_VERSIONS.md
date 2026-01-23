# SIM vs REA Versions Architecture

This document defines the two versions of the ROA system: **SIM** (Simulation with UE5) and **REA** (Real-world testing without UE5).

---

## Two System Versions

### SIM Version (Primary Focus)
**SIM** = **Simulation Version with Unreal Engine 5**

- Full system including UE5 simulation environment
- All five components active
- Primary development focus
- Used for testing, development, and visualization

### REA Version (Future)
**REA** = **Real-world Testing Version without UE5**

- Real robot hardware testing
- UE5-specific components excluded
- Lightweight for deployment on robot controllers
- Used for actual construction site deployment

---

## Component Breakdown by Version

| Component | SIM Version | REA Version | Notes |
|-----------|------------|------------|-------|
| **Files Type Importer** | ✅ Required | ❌ Not needed | Only for importing models into UE5 |
| **Dimensions Collector** | ✅ Required (UE5) | ✅ Required (Hardware) | Different implementation |
| **Universal Robot Controller** | ✅ Required | ✅ Required | Core component for both |
| **Communication System** | ✅ Required | ✅ Required | Core component for both |
| **Webthread** | ✅ Required (Full) | ✅ Required (Lite) | Different features enabled |
| **UE5 Integration** | ✅ Required | ❌ Not needed | Simulation only |
| **ROS2** | ✅ Required | ✅ Required | Both versions |
| **Gazebo** | ⚠️ Optional | ❌ Not needed | Only if UE5 physics insufficient |

---

## Detailed Component Differences

### 1. Files Type Importer

**SIM Version:**
- ✅ Fully implemented
- Imports robot models into UE5
- Converts 3D formats (URDF, STL, STEP, etc.)
- Creates Content Drawer folders

**REA Version:**
- ❌ Not included
- Real robots already have physical form
- No 3D model import needed

---

### 2. Dimensions Collector

**SIM Version (UE5-based):**
- ✅ Implemented as UE5 plugin (C++)
- Collects data from UE5 scene
- Tracks simulated robot positions
- Uses UE5 coordinate system
- 60Hz update rate from simulation

**REA Version (Hardware-based):**
- ✅ Implemented as ROS2 node (Python/C++)
- Collects data from real robot sensors
- Tracks actual robot positions via encoders, IMU, cameras
- Uses real-world coordinate system
- Update rate depends on sensor hardware

**Key Difference:**
- SIM reads from UE5 scene
- REA reads from robot hardware sensors

---

### 3. Universal Robot Controller

**SIM Version:**
- ✅ Full implementation
- Dual-mode: Standalone app + UE5 widget
- Controls simulated robots in UE5
- Sends commands through Webthread to ROS2
- ROS2 updates simulation in UE5

**REA Version:**
- ✅ Full implementation
- Standalone app only (no UE5 widget)
- Controls real robot hardware
- Sends commands through Webthread to ROS2
- ROS2 sends commands to robot controllers
- Same UI, same controls, different backend

**Key Difference:**
- SIM: Commands → ROS2 → UE5 simulation
- REA: Commands → ROS2 → Real robot hardware

---

### 4. Communication System

**SIM Version:**
- ✅ Full implementation
- Robots communicate in simulation
- Virtual collision avoidance
- Work area coordination in UE5

**REA Version:**
- ✅ Full implementation
- Same code, different data source
- Real robots communicate
- Physical collision avoidance
- Work area coordination on construction site

**Key Difference:**
- Same implementation, just uses real robot positions instead of simulated

---

### 5. Webthread

**SIM Version (Full Features):**
- ✅ ROS2 ↔ UE5 bridge (main feature)
- ✅ Optional Gazebo integration
- ✅ Simulation control
- ✅ UE5 status monitoring
- ✅ Visual sensor simulation
- ✅ Logging system
- ✅ Status monitor interface

**REA Version (Lite Features):**
- ✅ ROS2 ↔ Robot Hardware interface
- ❌ No UE5 bridge (not needed)
- ❌ No Gazebo (not needed)
- ❌ No simulation control
- ✅ Robot hardware status monitoring
- ✅ Real sensor data collection
- ✅ Logging system (same as SIM)
- ✅ Status monitor interface (simplified)

**Key Difference:**
- SIM: Bridges ROS2 ↔ UE5
- REA: Interfaces ROS2 ↔ Robot Hardware

---

## Repository Structure for Both Versions

### Single Repository with Conditional Components

```
ROA/
├── main (single branch)
│   ├── components/
│   │   ├── files-type-importer/      # SIM ONLY
│   │   │   └── README.md (marked as SIM only)
│   │   ├── universal-robot-controller/  # BOTH (SIM + REA)
│   │   │   ├── src/
│   │   │   │   ├── common/           # Shared code
│   │   │   │   ├── sim/              # SIM-specific code
│   │   │   │   └── rea/              # REA-specific code
│   │   ├── dimensions-collector/     # BOTH (different implementations)
│   │   │   ├── src/
│   │   │   │   ├── ue5/              # SIM version (UE5 plugin)
│   │   │   │   └── hardware/         # REA version (sensor integration)
│   │   ├── communication-system/     # BOTH (same code)
│   │   └── webthread/                # BOTH (different features)
│   │       ├── src/
│   │       │   ├── common/           # Shared code
│   │       │   ├── ue5_bridge/       # SIM-specific
│   │       │   └── hardware_interface/  # REA-specific
│   ├── ue5-project/                  # SIM ONLY
│   └── docs/
│       ├── SIM_VERSION.md            # SIM-specific docs
│       └── REA_VERSION.md            # REA-specific docs
```

---

## Build Configuration

### SIM Version Build
```bash
# Build with UE5 support
cmake -DBUILD_VERSION=SIM ..
# or
colcon build --cmake-args -DBUILD_VERSION=SIM

# Enables:
# - Files Type Importer
# - UE5 Dimensions Collector
# - UE5 Webthread bridge
# - UE5 project plugins
```

### REA Version Build
```bash
# Build without UE5 support
cmake -DBUILD_VERSION=REA ..
# or
colcon build --cmake-args -DBUILD_VERSION=REA

# Enables:
# - Hardware Dimensions Collector
# - Hardware Webthread interface
# - Robot controller (standalone only)
# - Communication system

# Excludes:
# - Files Type Importer
# - UE5 plugins
# - UE5 project
```

---

## Development Workflow

### Current Focus: SIM Version

**Priority:** Develop SIM version first
- More complex (includes UE5)
- Easier to test (no real robot hardware needed)
- Visual feedback helpful for development
- Can develop REA version later by adapting SIM code

**Development Order:**
1. **Phase 1-5**: Build SIM version (see ARCHITECTURE.md)
2. **Phase 6**: Extract REA version from SIM codebase
3. **Phase 7**: Test REA on real robot hardware

---

## Code Sharing Strategy

### Shared Code (Common)
- Universal Robot Controller core logic
- Communication System protocol
- Webthread logging system
- ROS2 message definitions
- Configuration management

### SIM-Specific Code
- Files Type Importer (entire component)
- UE5 Dimensions Collector plugin
- UE5 Webthread bridge
- UE5 Controller widget
- UE5 project files

### REA-Specific Code
- Hardware Dimensions Collector (sensor integration)
- Hardware Webthread interface
- Robot hardware drivers
- Real sensor calibration

---

## Version Tagging Strategy

### Git Tags for Versions
```bash
# SIM version releases
git tag -a sim-v1.0.0 -m "SIM Version 1.0.0"

# REA version releases
git tag -a rea-v1.0.0 -m "REA Version 1.0.0"

# Combined release (both versions)
git tag -a v1.0.0 -m "ROA 1.0.0 (SIM + REA)"
```

---

## Deployment

### SIM Version Deployment
**Target:** Development workstation / Lab computer

**Requirements:**
- High-performance PC
- NVIDIA/AMD GPU for UE5
- UE5 installed
- ROS2 Humble
- Python + C++ toolchain

**Use Cases:**
- Algorithm development
- Testing multi-robot coordination
- Training operators
- Research and visualization

---

### REA Version Deployment
**Target:** Robot controller hardware / Edge devices

**Requirements:**
- Robot controller computer (e.g., Raspberry Pi, Industrial PC)
- ROS2 Humble
- Python + C++ toolchain
- No GPU required
- Minimal dependencies

**Use Cases:**
- Construction site deployment
- Real robot testing
- Production operations
- Field research

---

## Migration Path: SIM → REA

### How to Adapt SIM Code to REA

1. **Disable UE5 Components**
   - Comment out Files Type Importer
   - Use hardware Dimensions Collector instead of UE5 version

2. **Replace Webthread Bridge**
   - Remove UE5 bridge code
   - Enable hardware interface code

3. **Configure for Real Hardware**
   - Update ROS2 topics to real robot topics
   - Configure sensor parameters
   - Set hardware-specific limits

4. **Test Incrementally**
   - Test controller with real robot
   - Verify dimensions from sensors
   - Validate communication between robots

---

## Configuration Files

### Version Selection

**CMakeLists.txt:**
```cmake
option(BUILD_VERSION "Build version: SIM or REA" "SIM")

if(BUILD_VERSION STREQUAL "SIM")
    add_definitions(-DVERSION_SIM)
    # Include UE5 components
    add_subdirectory(components/files-type-importer)
    add_subdirectory(ue5-project)
elseif(BUILD_VERSION STREQUAL "REA")
    add_definitions(-DVERSION_REA)
    # Exclude UE5 components
endif()
```

**config.yaml:**
```yaml
version: SIM  # or REA

sim:
  ue5_enabled: true
  gazebo_enabled: false
  dimensions_source: ue5

rea:
  ue5_enabled: false
  gazebo_enabled: false
  dimensions_source: hardware
  robot_hardware:
    - robot1:
        ip: 192.168.1.100
        sensors: [imu, camera, lidar]
    - robot2:
        ip: 192.168.1.101
        sensors: [imu, camera]
```

---

## Testing Strategy

### SIM Version Testing
- Unit tests for each component
- Integration tests in UE5 simulation
- Multi-robot coordination tests
- Performance benchmarks
- Visual validation

### REA Version Testing
- Unit tests (shared with SIM)
- Hardware-in-the-loop tests
- Real robot movement tests
- Safety system validation
- Field testing

---

## Documentation Updates Needed

### Per-Version Documentation

**SIM_VERSION.md** (to be created):
- UE5 setup instructions
- Simulation environment configuration
- Robot model import guide
- Simulation-specific features

**REA_VERSION.md** (to be created):
- Hardware setup instructions
- Sensor calibration guide
- Robot hardware configuration
- Deployment checklist

---

## Summary

| Aspect | SIM Version | REA Version |
|--------|------------|------------|
| **Purpose** | Development & Testing | Production Deployment |
| **Environment** | UE5 Simulation | Real Hardware |
| **Components** | All 5 | 4 (no File Importer) |
| **UE5** | Required | Not needed |
| **Hardware** | Not required | Real robots needed |
| **Focus** | Primary (now) | Secondary (later) |
| **Complexity** | Higher | Lower |
| **Development** | Easier to test | Requires hardware |

**Current Strategy:**
1. ✅ Focus on SIM version development (primary)
2. ⏳ Build REA version later by adapting SIM code
3. 🔄 Maintain single codebase with version-specific sections
4. 📦 Deploy appropriate version per use case

---

**Last Updated**: Design Phase  
**Status**: SIM version primary focus, REA version planned for future
