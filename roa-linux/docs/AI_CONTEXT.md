# ROA Project - AI Assistant Context Guide

**Version**: 1.0  
**Last Updated**: 2025-11-16  
**Purpose**: Quick start guide for AI assistants working on the ROA project

---

## Project Overview

**ROA** (Robot Operator Assistant) is a comprehensive robotics integration platform that bridges ROS2/Gazebo simulation with Unreal Engine 5 for real-time robot control, monitoring, and coordination in construction site scenarios.

### Quick Facts
- **Primary Language**: Python (ROS2 integration) + C++ (UE5 plugins)
- **Target Platform**: Ubuntu 22.04 (primary), Windows 10/11 (secondary)
- **Dependencies**: ROS2 Humble LTS, Unreal Engine 5.6+, Python 3.10+
- **Architecture**: Microservices with ROS2 communication layer

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     WEBTHREAD                            │
│  (Central coordinator connecting ROS2 ↔ UE5)            │
└───────────────────┬─────────────────────────────────────┘
                    ↓ (ROS2 Topics/Services)
    ┌───────────────┴───────────────┬─────────────┬───────────────┐
    ↓                               ↓             ↓               ↓
┌────────┐                     ┌────────┐    ┌────────┐     ┌────────┐
│  FTI   │                     │  DIMC  │    │  ROC   │     │  COMC  │
│3D Model│                     │Spatial │    │Control │     │ Multi  │
│Importer│                     │Tracking│    │ System │     │ Robot  │
└────────┘                     └────────┘    └────────┘     └────────┘
```

---

## Five Core Components

### 1. Files Type Importer (FTI) - ✅ IMPLEMENTED
**Status**: Production Ready  
**Location**: `components/files-type-importer/`

**Purpose**: Automated import of robot 3D models into UE5 without external tools

**Key Features**:
- Format auto-detection (URDF, STL, OBJ, FBX, DAE, STEP, IGES, USD)
- USD intermediate format conversion
- Hierarchy preservation with validation
- ROS2 integration for Webthread coordination
- Data export for DIMC (metadata) and ROC (joint definitions)

**Entry Points**:
- Python API: `src/python/file_type_importer.py`
- ROS2 Node: `src/python/fti_ros2_node.py`
- C++ Plugin: `src/cpp/FileTypeImporter.h/cpp`

**Tests**: 30 unit tests (100% passing)

**Documentation**:
- `README.md` - Component overview
- `INTEGRATION_GUIDE.md` - ROS2 integration specs
- `DESIGN_REVIEW.md` - Design compliance
- `IMPLEMENTATION_SUMMARY.md` - Technical details

### 2. Dimensions Collector (DIMC) - 🔄 PLANNED
**Status**: Not Yet Implemented  
**Location**: `components/dimensions-collector/` (to be created)

**Purpose**: Real-time spatial tracking and obstacle detection

**Will Provide**:
- Environment scanning
- Obstacle detection (Evade subsystem)
- Dynamic dimension tracking
- Collision avoidance data

**Integration Points**:
- Receives: Model metadata from FTI
- Provides: Spatial data to ROC, Webthread

### 3. Robot Operator Controller (ROC) - 🔄 PLANNED
**Status**: Not Yet Implemented  
**Location**: `components/robot-operator-controller/` (to be created)

**Purpose**: Universal robot control with dual control modes

**Control Modes**:
- **RPM** (Role Playing Mode): Direct manual control
- **ADM** (Auto Driven Mode): RTS-style strategic control

**Will Provide**:
- ROS2 Control framework integration
- Adaptive UI based on robot structure
- Safety system (Fragile/Standard/Robust)
- Path planning (A*, RRT)

**Integration Points**:
- Receives: Joint definitions from FTI, spatial data from DIMC
- Provides: Control commands to robots

### 4. Communication Center (COMC) - 🔄 PLANNED
**Status**: Not Yet Implemented  
**Location**: `components/communication-center/` (to be created)

**Purpose**: Multi-robot coordination and inter-robot communication

**Will Provide**:
- DDS middleware for robot-to-robot communication
- Traffic priority system
- Multi-robot task coordination
- Collision avoidance protocols

### 5. Webthread - ✅ PARTIALLY IMPLEMENTED
**Status**: Basic structure created, integration layer ready  
**Location**: `components/webthread/`

**Purpose**: Central integration hub connecting ROS2 ↔ UE5

**Current State**:
- Directory structure created
- WebthreadInitializer design documented
- Component starter framework present
- FTI integration interface ready

**Needs**:
- Complete ROS2 ↔ UE5 bridge implementation
- Health monitoring system
- Component coordination logic
- Error handling and recovery

---

## Project Structure

```
ROA/
├── components/              # Main components
│   ├── files-type-importer/ # ✅ FTI - Complete
│   ├── webthread/           # 🔄 Partial - Basic structure
│   └── [3 more planned]     # 🔄 DIMC, ROC, COMC
├── docs/                    # 17 design documents
│   ├── ARCHITECTURE.md      # Overall system design
│   ├── WEBTHREAD_INITIALIZER.md
│   ├── PROJECT_STRUCTURE.md
│   ├── DESIGN_DECISIONS.md
│   └── [13 more docs]
└── README.md                # Project root readme
```

---

## Key Design Documents (All 17)

### Critical to Read First:
1. **ARCHITECTURE.md** - Complete system architecture
2. **PROJECT_STRUCTURE.md** - Directory layout and organization
3. **DESIGN_DECISIONS.md** - Confirmed requirements per component
4. **WEBTHREAD_INITIALIZER.md** - Startup sequence and component coordination

### Implementation Guides:
5. **PRE_DEVELOPMENT_ANALYSIS.md** - Risk mitigation strategies
6. **DETAILED_ANSWERS.md** - Technical Q&A (USD format, DDS, etc.)
7. **INPUT_CONTROLS.md** - RPM/ADM control specifications

### Reference:
8. **SIMILAR_PROJECTS_RESEARCH.md** - Best practices from other projects
9. **ENHANCED_FEATURES.md** - Extended capabilities
10. **SIM_VS_REA_VERSIONS.md** - Simulation vs Real-world versions

### Development Setup:
11. **VSCODE_SETUP.md** - VS Code configuration
12. **GIT_SYNC_GUIDE.md** - Git workflow
13. **SHORTCUTS.txt** - Keyboard shortcuts reference

### Supporting:
14. **CLARIFICATIONS_EXPLAINED.md**
15. **DESIGN_CLARIFICATIONS_FINAL.md**
16. **FILESYSTEM_VS_DATABASE.md**
17. **REPOSITORY_STRUCTURE.md**

---

## Component Development Checklist

When implementing a new component, ensure:

- [ ] **Directory Structure** matches PROJECT_STRUCTURE.md
  - `src/python/` and/or `src/cpp/`
  - `tests/` with unit tests
  - `Config/` for configuration files
  - `README.md` with component overview

- [ ] **ROS2 Integration**
  - ROS2 node implementation
  - Topics for status, commands, results
  - Services for health checks
  - `integration_config.json` specification

- [ ] **Data Export Interfaces**
  - Export format for dependent components
  - Standardized data structures
  - Documentation of message formats

- [ ] **Testing**
  - Unit tests (target: 80%+ coverage)
  - Integration tests with ROS2
  - Validation of component readiness

- [ ] **Documentation**
  - Component README
  - Integration guide
  - API documentation
  - Design review document

- [ ] **Webthread Integration**
  - Startup coordination support
  - Health monitoring interface
  - Error recovery mechanism
  - Status reporting

---

## ROS2 Communication Standards

### Topic Naming Convention:
```
/roa/<component>/<topic_name>
Example: /roa/fti/status, /roa/fti/import_command
```

### Message Format (using std_msgs/String with JSON):
```json
{
  "component": "FTI",
  "status": "ready|importing|error",
  "data": { ... }
}
```

### Service Naming Convention:
```
/roa/<component>/<service_name>
Example: /roa/fti/check_status
```

### Standard Services Required:
- `check_status` - Health check (std_srvs/Trigger)
- Component-specific services as needed

---

## Development Workflow

### 1. Component Implementation Order (per WEBTHREAD_INITIALIZER.md):
```
Phase 3 Startup Sequence:
1. FTI (Files Type Importer)      ✅ Complete
2. DIMC (Dimensions Collector)    ⏳ Next
3. ROC (Robot Operator Controller)
4. COMC (Communication Center)
5. Webthread Runtime
```

### 2. Standard Development Flow:
1. Create component directory structure
2. Implement core logic (Python/C++)
3. Add ROS2 integration layer
4. Create data export interfaces
5. Write unit tests
6. Document integration points
7. Test with Webthread coordination

### 3. Testing Strategy:
- **Unit Tests**: Test individual modules in isolation
- **Integration Tests**: Test ROS2 communication
- **System Tests**: Test with Webthread coordination
- **Validation**: Verify against design documents

---

## Common Patterns

### Python Module Structure:
```python
"""
Module description
"""

import rclpy
from rclpy.node import Node
# ... imports

class ComponentNode(Node):
    def __init__(self):
        super().__init__('component_node')
        # Initialize
        
    def method(self):
        # Implementation
        
def main(args=None):
    rclpy.init(args=args)
    node = ComponentNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
```

### Configuration File Structure:
```json
{
  "component": {
    "name": "COMPONENT",
    "version": "0.1.0"
  },
  "ros2": {
    "node_name": "component_node",
    "topics": { ... },
    "services": { ... }
  },
  "webthread_integration": { ... }
}
```

---

## Quick Start for AI Assistants

### When Asked to Work on ROA:

1. **Read These First**:
   - This file (AI_CONTEXT.md)
   - ARCHITECTURE.md
   - Component-specific README (if working on a component)

2. **Understand Current State**:
   - FTI is complete ✅
   - Webthread has basic structure 🔄
   - DIMC, ROC, COMC are planned 🔄

3. **Follow These Principles**:
   - Match PROJECT_STRUCTURE.md layout
   - Implement ROS2 integration for all components
   - Create data export interfaces for component coordination
   - Write comprehensive tests (target 80%+ coverage)
   - Document everything (README, integration guide, API docs)

4. **Integration Requirements**:
   - ROS2 topics for communication
   - Health check service
   - Status reporting to Webthread
   - Startup coordination support
   - Error recovery mechanism

5. **Validation Checklist**:
   - [ ] Matches design documents
   - [ ] ROS2 integration complete
   - [ ] Tests passing (100% for new code)
   - [ ] Documentation complete
   - [ ] Integration interfaces defined

---

## Technology Stack

### Core Technologies:
- **ROS2 Humble LTS** - Robot middleware
- **Unreal Engine 5.6+** - 3D simulation and visualization
- **Python 3.10+** - Primary scripting language
- **C++17** - UE5 plugins and performance-critical code

### Python Libraries:
- **rclpy** - ROS2 Python client library
- **pyyaml** - Configuration parsing
- **numpy** - Numerical operations
- **pytest** - Testing framework

### Optional:
- **Gazebo** - Physics simulation (if UE5 physics insufficient)
- **USD (pxr)** - Universal Scene Description (format conversion)
- **trimesh** - Mesh processing

---

## Component Status Summary

| Component | Status | Tests | Documentation | ROS2 Integration |
|-----------|--------|-------|---------------|------------------|
| FTI | ✅ Complete | 30/30 | Complete | ✅ Ready |
| DIMC | 🔄 Planned | - | Design docs | Spec ready |
| ROC | 🔄 Planned | - | Design docs | Spec ready |
| COMC | 🔄 Planned | - | Design docs | Spec ready |
| Webthread | 🔄 Partial | - | Design docs | Framework ready |

---

## Known Issues & Limitations

### FTI:
- USD generation is stubbed (actual conversion not yet implemented)
- C++ ↔ Python bridge incomplete
- Additional format converters (FBX, DAE, STEP, IGES) planned but not implemented

### Webthread:
- Core coordination logic not yet implemented
- Health monitoring system needs implementation
- Error recovery mechanisms need implementation

### General:
- Integration tests between components not yet created
- System-level testing not yet possible (only FTI complete)
- Performance optimization deferred to later phase

---

## Next Steps (Recommended Priority)

1. **Complete Webthread Core** (enables system testing)
   - ROS2 ↔ UE5 bridge
   - Component coordination logic
   - Health monitoring system

2. **Implement DIMC** (next in startup sequence)
   - Spatial tracking system
   - Obstacle detection
   - Integration with FTI metadata

3. **Implement ROC** (robot control)
   - Control mode state machines (RPM/ADM)
   - Adaptive UI generation
   - Safety systems

4. **Implement COMC** (multi-robot)
   - DDS communication layer
   - Traffic priority system
   - Coordination protocols

5. **System Integration Testing**
   - Component interaction tests
   - End-to-end scenarios
   - Performance benchmarking

---

## Useful Commands

### Testing:
```bash
# Run all FTI tests
cd components/files-type-importer
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_urdf_converter.py -v
```

### ROS2:
```bash
# Source ROS2
source /opt/ros/humble/setup.bash

# Run FTI node
ros2 run fti fti_ros2_node

# Check FTI status
ros2 topic echo /fti/status

# Send import command
ros2 topic pub /fti/import_command std_msgs/String \
  'data: {"file_path": "/path/to/robot.urdf", "robot_name": "TestRobot", "import_mode": "both"}'
```

### Development:
```bash
# Install Python dependencies for FTI
cd components/files-type-importer
pip install -r requirements.txt

# Run linter
pylint src/python/

# Format code
black src/python/
```

---

## Contact & Resources

- **Repository**: https://github.com/Omar-Galal-AB/ROA
- **Branch**: `copilot/add-file-type-importer` (for FTI)
- **Main Branch**: `main`

---

**For AI Assistants**: This document provides the essential context for understanding the ROA project. When working on the project:
1. Read relevant sections of this document
2. Consult specific design documents as needed
3. Follow established patterns from FTI implementation
4. Maintain consistency with PROJECT_STRUCTURE.md
5. Ensure ROS2 integration for all components

**Document Version**: 1.0  
**Maintained By**: ROA Development Team  
**Last Review**: 2025-11-16
