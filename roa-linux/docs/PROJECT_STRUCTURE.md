# ROA Project Structure

## Proposed Directory Organization

This document outlines the recommended folder structure for the ROA system components.

```
ROA/
├── README.md                          # Project overview and quick start
├── ARCHITECTURE.md                    # Detailed system architecture (this document's companion)
├── LICENSE                            # Project license
├── .gitignore                         # Git ignore rules
│
├── docs/                              # Documentation
│   ├── user-guide/                    # End-user documentation
│   │   ├── getting-started.md
│   │   ├── robot-import.md
│   │   ├── robot-control.md
│   │   └── multi-robot-coordination.md
│   ├── developer-guide/               # Developer documentation
│   │   ├── setup.md
│   │   ├── contributing.md
│   │   ├── api-reference.md
│   │   └── extending-system.md
│   ├── architecture/                  # Architecture diagrams and design docs
│   │   ├── component-diagrams/
│   │   ├── sequence-diagrams/
│   │   └── data-flow-diagrams/
│   └── tutorials/                     # Step-by-step tutorials
│       ├── first-robot-import.md
│       ├── multi-robot-scenario.md
│       └── custom-robot-type.md
│
├── components/                        # Main system components
│   │
│   ├── files-type-importer/          # Component 1: Files Type Importer for UE5
│   │   ├── README.md                  # Component-specific documentation
│   │   ├── src/                       # Source code
│   │   │   ├── cpp/                   # C++ UE5 plugin code
│   │   │   │   ├── FileTypeImporter.h
│   │   │   │   ├── FileTypeImporter.cpp
│   │   │   │   ├── Converters/        # Format converters
│   │   │   │   │   ├── URDFConverter.cpp
│   │   │   │   │   ├── STEPConverter.cpp
│   │   │   │   │   ├── IGESConverter.cpp
│   │   │   │   │   └── ...
│   │   │   │   └── Importers/         # Format-specific importers
│   │   │   └── python/                # Python utilities (if needed)
│   │   ├── tests/                     # Unit and integration tests
│   │   ├── examples/                  # Example robot files
│   │   └── Config/                    # Configuration files
│   │
│   ├── universal-robot-controller/   # Component 2: Universal Robot Controller
│   │   ├── README.md
│   │   ├── src/
│   │   │   ├── cpp/                   # C++ UE5 UI and core logic
│   │   │   │   ├── RobotController.h
│   │   │   │   ├── RobotController.cpp
│   │   │   │   ├── UI/                # Controller UI widgets
│   │   │   │   │   ├── ControllerWidget.cpp
│   │   │   │   │   ├── SliderControls.cpp
│   │   │   │   │   └── RobotSelector.cpp
│   │   │   │   ├── Controllers/       # Individual controller types
│   │   │   │   │   ├── ArmController.cpp
│   │   │   │   │   ├── BaseController.cpp
│   │   │   │   │   ├── GripperController.cpp
│   │   │   │   │   └── ...
│   │   │   │   └── Safety/            # Safety systems
│   │   │   │       ├── CollisionDetector.cpp
│   │   │   │       └── SafetyMonitor.cpp
│   │   │   └── python/                # ROS2 interface
│   │   │       ├── ros2_interface.py
│   │   │       └── command_translator.py
│   │   ├── tests/
│   │   ├── UI/                        # UE5 UI assets (UMG widgets)
│   │   └── Config/
│   │
│   ├── dimensions-collector/          # Component 3: Dimensions Collector for UE5
│   │   ├── README.md
│   │   ├── src/
│   │   │   ├── cpp/                   # C++ UE5 plugin
│   │   │   │   ├── DimensionsCollector.h
│   │   │   │   ├── DimensionsCollector.cpp
│   │   │   │   ├── Tracking/          # Position/orientation tracking
│   │   │   │   │   ├── PositionTracker.cpp
│   │   │   │   │   ├── OrientationTracker.cpp
│   │   │   │   │   └── MovementDeltaCalculator.cpp
│   │   │   │   ├── Measurement/       # Size and distance measurement
│   │   │   │   │   ├── SizeMeasurer.cpp
│   │   │   │   │   └── DistanceCalculator.cpp
│   │   │   │   └── Export/            # Data export utilities
│   │   │   └── python/                # Data processing utilities
│   │   ├── tests/
│   │   └── Config/
│   │
│   ├── communication-system/          # Component 4: Communication System Between Robots
│   │   ├── README.md
│   │   ├── src/
│   │   │   ├── python/                # Primary implementation
│   │   │   │   ├── communication_manager.py
│   │   │   │   ├── Protocol/          # Custom protocol implementation
│   │   │   │   │   ├── message_types.py
│   │   │   │   │   ├── protocol_handler.py
│   │   │   │   │   └── serializer.py
│   │   │   │   ├── Coordination/      # Multi-robot coordination
│   │   │   │   │   ├── work_area_manager.py
│   │   │   │   │   ├── collision_avoidance.py
│   │   │   │   │   └── task_coordinator.py
│   │   │   │   └── Networking/        # Network layer
│   │   │   │       ├── tcp_server.py
│   │   │   │       ├── tcp_client.py
│   │   │   │       └── message_queue.py
│   │   │   └── cpp/                   # Performance-critical parts (if needed)
│   │   ├── tests/
│   │   ├── protocols/                 # Protocol specifications
│   │   └── Config/
│   │
│   └── webthread/                     # Component 5: Webthread Integration Bridge
│       ├── README.md
│       ├── src/
│       │   ├── python/                # Primary bridge implementation
│       │   │   ├── webthread_core.py
│       │   │   ├── ROS2Bridge/        # ROS2 integration
│       │   │   │   ├── ros2_node.py
│       │   │   │   ├── topic_manager.py
│       │   │   │   ├── service_handler.py
│       │   │   │   └── action_handler.py
│       │   │   ├── UE5Bridge/         # UE5 integration
│       │   │   │   ├── ue5_connector.py
│       │   │   │   └── data_synchronizer.py
│       │   │   ├── GazeboBridge/      # Optional Gazebo integration
│       │   │   │   ├── gazebo_sync.py
│       │   │   │   └── physics_bridge.py
│       │   │   ├── Logging/           # Logging system
│       │   │   │   ├── logger.py
│       │   │   │   ├── event_recorder.py
│       │   │   │   └── log_viewer.py
│       │   │   ├── ErrorHandling/     # Error detection and handling
│       │   │   │   ├── error_detector.py
│       │   │   │   └── error_reporter.py
│       │   │   └── StatusMonitor/     # Status monitoring interface
│       │   │       ├── monitor_ui.py
│       │   │       └── connection_manager.py
│       │   └── cpp/                   # Performance-critical bridge components
│       │       └── fast_serializer.cpp
│       ├── tests/
│       ├── ui/                        # Status monitor UI files
│       │   ├── web/                   # Web-based dashboard (optional)
│       │   └── ue5/                   # UE5 editor widgets
│       └── Config/
│
├── shared/                            # Shared libraries and utilities
│   ├── common/                        # Common utilities
│   │   ├── math_utils.py
│   │   ├── coordinate_transforms.py
│   │   └── constants.py
│   ├── messages/                      # Shared message definitions
│   │   ├── ros2_messages/             # ROS2 message types
│   │   └── custom_messages/           # Custom message types
│   ├── interfaces/                    # Component interfaces
│   │   ├── IController.h
│   │   ├── ICollector.h
│   │   └── ICommunicator.h
│   └── config/                        # Shared configuration
│       ├── system_config.yaml
│       └── robot_types.yaml
│
├── ue5-project/                       # Unreal Engine 5 Project
│   ├── ROA.uproject                   # UE5 project file
│   ├── Source/                        # UE5 C++ source
│   ├── Content/                       # UE5 content
│   │   ├── Robots/                    # Imported robot assets
│   │   ├── UI/                        # Controller UI widgets
│   │   └── Maps/                      # Simulation environments
│   ├── Plugins/                       # UE5 plugins
│   │   ├── FileTypeImporter/          # Files Type Importer plugin
│   │   ├── DimensionsCollector/       # Dimensions Collector plugin
│   │   └── WebthreadConnector/        # Webthread connection plugin
│   └── Config/
│
├── ros2-workspace/                    # ROS2 Workspace
│   ├── src/                           # ROS2 packages
│   │   ├── roa_msgs/                  # Custom ROS2 messages
│   │   ├── roa_control/               # Robot control nodes
│   │   ├── roa_communication/         # Communication system nodes
│   │   └── roa_webthread/             # Webthread ROS2 interface
│   └── install/                       # Built packages
│
├── gazebo-models/                     # Gazebo models (optional)
│   └── robots/                        # Robot models for Gazebo
│
├── scripts/                           # Utility scripts
│   ├── setup/                         # Setup and installation scripts
│   │   ├── setup_ue5.sh
│   │   ├── setup_ros2.sh
│   │   └── install_dependencies.sh
│   ├── build/                         # Build scripts
│   │   ├── build_all.sh
│   │   ├── build_components.sh
│   │   └── build_ue5_plugins.sh
│   ├── testing/                       # Testing scripts
│   │   ├── run_tests.sh
│   │   └── integration_test.sh
│   └── deployment/                    # Deployment scripts
│       ├── deploy_local.sh
│       └── deploy_distributed.sh
│
├── tests/                             # Integration and system tests
│   ├── integration/                   # Integration tests
│   │   ├── test_import_to_control.py
│   │   ├── test_multi_robot.py
│   │   └── test_ros2_ue5_bridge.py
│   ├── system/                        # System-level tests
│   │   ├── test_full_workflow.py
│   │   └── test_performance.py
│   └── fixtures/                      # Test fixtures and data
│       └── sample_robots/
│
├── examples/                          # Example projects and demos
│   ├── single-robot-demo/
│   ├── multi-robot-construction/
│   └── custom-robot-integration/
│
├── config/                            # System-wide configuration
│   ├── default_config.yaml
│   ├── robots/                        # Robot-specific configurations
│   │   ├── robot_templates/
│   │   └── known_robots/
│   └── environments/                  # Environment configurations
│       ├── development.yaml
│       ├── testing.yaml
│       └── production.yaml
│
└── tools/                             # Development and debugging tools
    ├── log-viewer/                    # Log viewing tool
    ├── robot-simulator/               # Standalone robot simulator
    └── performance-profiler/          # Performance profiling tools
```

## Component Interdependencies

### Build Order
1. **shared/** - Common libraries (no dependencies)
2. **components/dimensions-collector/** - Depends on shared
3. **components/files-type-importer/** - Depends on shared
4. **components/communication-system/** - Depends on shared
5. **components/universal-robot-controller/** - Depends on shared, dimensions-collector
6. **components/webthread/** - Depends on all other components
7. **ue5-project/** - Integrates all UE5 plugins
8. **ros2-workspace/** - ROS2 packages

### Runtime Dependencies
- **Files Type Importer** → UE5 only
- **Dimensions Collector** → UE5 only
- **Universal Robot Controller** → UE5 + Webthread + Dimensions Collector
- **Communication System** → Webthread + Dimensions Collector
- **Webthread** → All components + ROS2 + UE5 + (optional) Gazebo

## File Naming Conventions

### C++ Files
- Headers: `PascalCase.h` (e.g., `RobotController.h`)
- Source: `PascalCase.cpp` (e.g., `RobotController.cpp`)
- Interfaces: `IInterfaceName.h` (e.g., `IController.h`)

### Python Files
- Modules: `snake_case.py` (e.g., `robot_controller.py`)
- Classes: `PascalCase` within files (e.g., `class RobotController`)
- Functions: `snake_case` (e.g., `def get_position()`)

### Configuration Files
- YAML: `kebab-case.yaml` (e.g., `system-config.yaml`)
- JSON: `kebab-case.json` (e.g., `robot-types.json`)

### Documentation
- Markdown: `kebab-case.md` (e.g., `getting-started.md`)
- README files: `README.md` (uppercase)

## Configuration Management

### Hierarchical Configuration
1. **System Default**: `config/default_config.yaml`
2. **Environment**: `config/environments/{env}.yaml`
3. **Component**: `components/{component}/Config/config.yaml`
4. **User/Runtime**: Runtime overrides

### Configuration Topics
- Network settings (ports, addresses)
- Performance tuning (timeouts, buffer sizes)
- Safety parameters (collision thresholds, speed limits)
- Logging levels and outputs
- Robot type definitions

## Build System

### UE5 Components
- Use Unreal Build Tool (UBT)
- Plugins have individual `.uplugin` files
- Build from UE5 Editor or command line

### ROS2 Components
- Use `colcon build` for ROS2 workspace
- Standard ROS2 package structure
- Custom message generation

### Python Components
- Use `setuptools` or `poetry` for package management
- Virtual environments for dependency isolation
- Requirements files for each component

### C++ Standalone Components
- CMake build system
- Integration with UE5 build when needed

## Testing Strategy

### Unit Tests
- Each component has `tests/` directory
- Python: `pytest` framework
- C++: UE5's testing framework or Google Test

### Integration Tests
- Cross-component testing in `tests/integration/`
- Simulate component interactions
- Mock external dependencies (ROS2, UE5) when needed

### System Tests
- Full end-to-end workflows
- Performance benchmarks
- Multi-robot scenarios

### Test Data
- Sample robot models in `tests/fixtures/sample_robots/`
- Test configurations
- Expected output data

## Deployment Models

### Development Environment
- All components on single machine
- Local ROS2 and UE5
- Direct file system access

### Distributed Deployment
- **Webthread** on server
- **UE5** on high-performance workstation
- **ROS2** on robot controllers or separate compute nodes
- Network communication between all

### Cloud/Hybrid
- **Webthread** and logging in cloud
- **UE5** local for rendering
- **ROS2** on edge devices or cloud

## Version Control Strategy

### Git Workflow
- `main` branch: stable releases
- `develop` branch: integration branch
- Feature branches: `feature/component-name`
- Release branches: `release/v1.0.0`

### Component Versioning
- Semantic versioning (MAJOR.MINOR.PATCH)
- Components can version independently
- System version tracks overall compatibility

### Submodules (Optional)
- Consider using Git submodules for components if they need independent repos
- Shared libraries as submodule

## Documentation Structure

### User Documentation
- Getting started guides
- Step-by-step tutorials
- UI screenshots and walkthroughs
- Troubleshooting guides

### Developer Documentation
- API references (auto-generated from code)
- Architecture diagrams
- Contribution guidelines
- Code style guides

### System Documentation
- Deployment guides
- Configuration references
- Performance tuning guides
- Security guidelines

## Next Steps

1. **Create skeleton structure**: Set up folders with README files
2. **Define interfaces**: Create interface definitions in `shared/interfaces/`
3. **Setup build system**: Configure CMake, UBT, and ROS2 build files
4. **Create templates**: Component templates for consistency
5. **Initialize CI/CD**: Setup automated testing and deployment
6. **Documentation framework**: Setup documentation generation tools
