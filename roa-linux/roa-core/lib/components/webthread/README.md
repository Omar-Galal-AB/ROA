# Webthread - Integration Bridge Component

**Component**: Webthread  
**Purpose**: Central integration hub connecting ROS2 (+Gazebo if needed) with Unreal Engine 5  
**Language**: Python (primary) + C++ (performance-critical components)  
**Status**: In Development

## Overview

Webthread serves as the central nervous system of the ROA platform, managing all data flow between ROS2, Unreal Engine 5, and optionally Gazebo. It coordinates the startup, monitoring, and inter-operation of all ROA components.

## Architecture Phases

### Phase 1: Initialization (WebthreadInitializer)
One-time startup orchestration that configures the entire ROA environment including:
- UE5 physics system setup (Chaos Physics to Gazebo-equivalent parameters)
- Input system initialization (keyboard/mouse handlers)
- UI overlay loading and configuration
- Component startup coordination (FTI, DIMC, ROC, COMC)
- Configuration management and validation
- Error handling and recovery

### Phase 2: Runtime Operations
Continuous monitoring and coordination:
- Health monitoring (500ms periodic checks)
- Inter-component communication coordination
- Error detection and recovery
- Logging and diagnostics

## Directory Structure

```
webthread/
├── README.md                          # This file
├── src/
│   ├── python/                        # Primary bridge implementation
│   │   ├── webthread_core.py          # Main Webthread runtime
│   │   ├── webthread_initializer.py   # Initialization orchestrator
│   │   ├── ROS2Bridge/                # ROS2 integration
│   │   │   ├── __init__.py
│   │   │   ├── ros2_node.py           # Main ROS2 node
│   │   │   ├── topic_manager.py       # Topic management
│   │   │   ├── service_handler.py     # Service calls
│   │   │   └── action_handler.py      # Action server/client
│   │   ├── UE5Bridge/                 # UE5 integration
│   │   │   ├── __init__.py
│   │   │   ├── ue5_connector.py       # UE5 connection handler
│   │   │   ├── physics_configurator.py # Physics setup
│   │   │   ├── input_initializer.py   # Input system setup
│   │   │   ├── ui_initializer.py      # UI overlay setup
│   │   │   ├── component_starter.py   # Component coordination
│   │   │   └── data_synchronizer.py   # Data sync
│   │   ├── GazeboBridge/              # Optional Gazebo integration
│   │   │   ├── __init__.py
│   │   │   ├── gazebo_sync.py
│   │   │   └── physics_bridge.py
│   │   ├── Logging/                   # Logging system
│   │   │   ├── __init__.py
│   │   │   ├── logger.py              # Main logger
│   │   │   ├── event_recorder.py      # Event recording
│   │   │   └── log_viewer.py          # Log viewing utilities
│   │   ├── ErrorHandling/             # Error detection and handling
│   │   │   ├── __init__.py
│   │   │   ├── error_detector.py
│   │   │   └── error_reporter.py
│   │   └── StatusMonitor/             # Status monitoring interface
│   │       ├── __init__.py
│   │       ├── monitor_ui.py
│   │       └── connection_manager.py
│   └── cpp/                           # Performance-critical components
│       ├── WebthreadInitializer.h     # C++ initializer header
│       ├── WebthreadInitializer.cpp   # C++ initializer implementation
│       ├── PhysicsConfigurator.h
│       ├── PhysicsConfigurator.cpp
│       ├── InputInitializer.h
│       ├── InputInitializer.cpp
│       ├── UIInitializer.h
│       ├── UIInitializer.cpp
│       ├── ComponentStarter.h
│       ├── ComponentStarter.cpp
│       ├── ConfigManager.h
│       ├── ConfigManager.cpp
│       └── fast_serializer.cpp
├── tests/                             # Test files
│   ├── test_initializer.py
│   ├── test_ros2_bridge.py
│   ├── test_ue5_bridge.py
│   └── test_integration.py
├── ui/                                # UI files
│   ├── web/                           # Web-based dashboard (optional)
│   └── ue5/                           # UE5 editor widgets
└── Config/                            # Configuration files
    ├── roa_physics_config.ini         # Physics parameters
    ├── roa_keybindings.json           # Input mappings
    ├── roa_ui_settings.json           # UI preferences
    ├── roa_component_config.yaml      # Component startup parameters
    └── roa_safety_rules.json          # Safety settings
```

## WebthreadInitializer Module

The WebthreadInitializer is a specialized one-time startup orchestrator that runs once at system startup and then exits. It handles:

### 1. UE5 Environment Configuration
- Physics system setup (Chaos Physics engine)
- Physics material presets (Metal, Plastic, Rubber, Concrete)
- Joint configuration defaults
- Validation tests (drop, friction, joint movement)

### 2. Input System Initialization
- Keyboard/mouse handler setup (120 Hz polling)
- Input context configuration (RPM/ADM modes)
- Keybinding conflict detection
- Input validation (latency targets: <10ms keyboard, <15ms mouse)

### 3. UI System Initialization
- UI overlay loading (shortcuts panel, mode indicator, status panel)
- UI configuration (refresh rate, transparency, fonts, colors)
- UI positioning and performance targets

### 4. Component Startup Coordination
- Phase 1: Pre-checks (version, platform, hardware, network)
- Phase 2: Environment setup (physics, input, UI, configs)
- Phase 3: Component initialization (FTI → DIMC → ROC → COMC → Runtime)
- Phase 4: Validation (communication, latency, safety tests)

### 5. Configuration Management
- Load and validate configuration files
- Schema validation and range checking
- Fallback to defaults on corruption
- Persistence across sessions

### 6. Error Handling and Recovery
- Critical error detection (abort startup)
- Warning handling (degraded mode)
- Retry logic with exponential backoff
- User notification and diagnostic mode

### 7. Diagnostic and Logging
- Detailed initialization logs
- Performance metrics tracking
- Version and compatibility management

## Startup Sequence

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

**Total Startup Time Target**: 35-60 seconds (typical: 45 seconds)

## Configuration Files

### roa_physics_config.ini
Physics engine parameters including solver settings, world configuration, and material properties.

### roa_keybindings.json
Input mappings for RPM mode, ADM mode, and shared bindings with support for multiple profiles.

### roa_ui_settings.json
UI preferences including overlay settings, refresh rates, fade rates, and visual customization.

### roa_component_config.yaml
Component-specific startup parameters and coordination settings.

### roa_safety_rules.json
Safety parameters including collision thresholds, traffic priority, and multi-robot coordination rules.

## Integration Points

### ROS2 Integration
- Bidirectional data flow (ROS2 ↔ UE5)
- Support for nodes, topics, services, and actions
- Multi-instance simulation support

### UE5 Integration
- Physics engine configuration
- Input system control
- UI overlay management
- Component coordination

### Gazebo Integration (Optional)
- Conditional use if UE5 physics insufficient
- Real-time synchronization
- Physics fallback support

## Performance Targets

- **Startup Time**: < 60 seconds
- **Control Loop Latency**: < 20ms
- **Input Response**: < 10ms (keyboard), < 15ms (mouse)
- **UI Refresh Rate**: 60 Hz
- **Health Check Interval**: 500ms

## Success Criteria

Initialization is successful when:
1. All 5 components started and responding ✅
2. Physics configured to Gazebo-equivalent accuracy ✅
3. Input system responsive within latency targets ✅
4. UI overlays rendered at 60 Hz ✅
5. Inter-component communication validated ✅
6. No critical errors in log ✅
7. Total startup time < 60 seconds ✅

## Development Status

- [x] Directory structure created
- [ ] WebthreadInitializer C++ implementation
- [ ] Python bridge implementation
- [ ] ROS2Bridge modules
- [ ] UE5Bridge modules
- [ ] Logging system
- [ ] Error handling system
- [ ] Status monitor
- [ ] Configuration templates
- [ ] Test suite
- [ ] Documentation

## Dependencies

### Required
- Unreal Engine 5.6 or later
- ROS2 Humble LTS
- Python 3.10+
- Ubuntu 22.04 (primary) / Windows 10/11 (secondary)

### Python Packages
- rclpy (ROS2 Python client library)
- pyyaml (configuration parsing)
- Additional packages TBD

### C++ Libraries
- Unreal Engine SDK
- Standard Template Library (STL)

## License

TBD

## Authors

ROA Development Team

## Last Updated

2025-11-16
