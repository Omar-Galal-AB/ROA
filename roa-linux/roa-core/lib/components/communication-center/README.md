# COMC - Communication Center

**Component 4 of 5 in the ROA System**

## Overview

The Communication Center (COMC) enables multi-robot coordination and inter-robot communication in the ROA system. It provides DDS-based peer-to-peer communication for work area broadcasting, collision avoidance, and collaborative task execution.

## Purpose

COMC handles **robot-to-robot communication** (not user-to-robot, which is handled by Webthread). It enables:

1. **Work Area Broadcasting**: Robots share their operational zones to prevent interference
2. **Collision Avoidance**: Real-time proximity alerts between robots
3. **Task Coordination**: Coordinate multi-robot operations without central bottleneck
4. **Heterogeneous Support**: Different robot types can communicate using standard protocol

## Status

✅ **Full Implementation Complete** - Ready for Integration and Testing

**Priority**: High (Component 4 in startup sequence after FTI, DIMC, ROC)

**Implementation Status**:
- ✅ Core Python modules (6 modules: comc_node, work_area_manager, proximity_monitor, qos_profiles, task_coordinator, evade_coordinator)
- ✅ Integration handlers (4 handlers: DIMC, Webthread, ROC, FTI)
- ✅ ROS2 message definitions (WorkArea, ProximityAlert, TaskCoordination)
- ✅ ROS2 service definitions (CoordinateTask, ReserveArea, QueryProximity)
- ✅ Unit tests (19 test cases, work area + proximity)
- ✅ Configuration files (YAML config, JSON integration spec)
- ✅ Launch file (ROS2 launch with parameters)
- ✅ Example demo (multi-robot coordination)
- ✅ ROS2 package build files (package.xml, setup.py, CMakeLists.txt)
- ✅ Integration guide (complete documentation)
- ⏳ Integration testing with other components (next step)

## Technology Stack

### Core Technologies
- **Middleware**: DDS (Data Distribution Service) via ROS2 Humble
- **Implementation**: eProsima Fast DDS (included with ROS2)
- **Language**: Python (primary) with optional C++ for performance-critical paths
- **Communication Pattern**: Peer-to-peer + broadcast (decentralized)

### Why DDS?
- Industry standard for real-time robotics
- Built into ROS2 (no additional installation)
- Configurable QoS policies for reliability vs performance trade-offs
- Automatic node discovery
- Proven in safety-critical systems

## Architecture

### Component Role in ROA System

```
┌─────────────────────────────────────────────────────────┐
│                     WEBTHREAD                            │
│  (Central coordinator - handles user↔system APIs)       │
└───────────────────┬─────────────────────────────────────┘
                    ↓ (Startup & health monitoring)
    ┌───────────────┴───────────────┬─────────────┬───────────────┐
    ↓                               ↓             ↓               ↓
┌────────┐                     ┌────────┐    ┌────────┐     ┌────────┐
│  FTI   │                     │  DIMC  │    │  ROC   │     │  COMC  │ ← YOU ARE HERE
└────────┘                     └────────┘    └────────┘     └────┬───┘
                                                                  │
                        Robot ↔ Robot Communication ──────────────┘
                        (Work areas, proximity, coordination)
```

### API Responsibility Split

| API Type | Handler | Examples |
|----------|---------|----------|
| **User → Robot** | Webthread | User commands, robot status queries |
| **System Integration** | Webthread | ROS2↔UE5 bridge, component health |
| **Robot ↔ Robot** | COMC | Work areas, proximity alerts, task coordination |

Source: `docs/DESIGN_CLARIFICATIONS_FINAL.md` Section 4

## Core Features

### 1. Work Area Management

**Purpose**: Prevent robots from interfering with each other's operations

**Functionality**:
- Each robot broadcasts its current work area (3D bounding box)
- Updates at 20Hz or when work area changes
- Other robots subscribe to work area broadcasts
- Automatic conflict detection

**Message Type**: `WorkArea.msg`
```
Header header
string robot_id
geometry_msgs/Point center
geometry_msgs/Vector3 dimensions  # width, height, depth
float64 priority  # Task priority for conflict resolution
```

### 2. Proximity Alerts

**Purpose**: Real-time collision avoidance between robots

**Functionality**:
- Continuous distance monitoring between all active robots
- Alert threshold: Configurable (default 50cm)
- Escalating warnings: Yellow (50cm), Orange (30cm), Red (10cm)
- Automatic slow-down or stop based on proximity

**Message Type**: `ProximityAlert.msg`
```
Header header
string source_robot_id
string target_robot_id
float64 current_distance
float64 approach_velocity
string severity  # "warning", "caution", "critical"
```

**Latency Requirement**: <20ms (safety-critical)

### 3. Task Coordination

**Purpose**: Enable multi-robot collaborative tasks

**Functionality**:
- Task priority broadcasting
- Resource reservation (objects, areas, tools)
- Deadlock prevention
- Task handoff between robots

**Service Type**: `CoordinateTask.srv`
```
# Request
string requesting_robot_id
string task_type
string[] required_resources
uint8 priority

---
# Response
bool approved
string[] conflicting_robots
string alternative_suggestion
```

### 4. Evade Subsystem Integration

**Purpose**: Support autonomous obstacle avoidance in ADM mode

**Functionality** (from `docs/ENHANCED_FEATURES.md`):
- COMC broadcasts evasion intent to all robots
- Reserves alternative path space
- Coordinates timing to avoid conflicts
- Priority-based right-of-way (higher task priority evades less)
- Deadlock detection and resolution

**Integration Points**:
- DIMC: Provides obstacle detection data
- ROC: Receives evasion commands for execution
- COMC: Coordinates multi-robot evasion maneuvers

**Implementation**: `evade_coordinator.py`
- Path conflict detection
- Alternative path calculation
- Evasion intent broadcasting
- Deadlock handling

### 5. Task Coordination

**Purpose**: Enable multi-robot collaborative tasks

**Functionality**:
- Task priority broadcasting
- Resource reservation (objects, areas, tools)
- Deadlock prevention
- Task handoff between robots

**Service Type**: `CoordinateTask.srv`
```
# Request
string requesting_robot_id
string task_type
string[] required_resources
uint8 priority

---
# Response
bool approved
string[] conflicting_robots
string alternative_suggestion
```

**Implementation**: `task_coordinator.py`
- Priority-based task approval
- Resource locking mechanism
- Deadlock detection and resolution
- Task status tracking

### 6. Component Integration

**Purpose**: Connect COMC with other ROA components

**Integration Handlers**:
- `DIMCIntegrationHandler`: Position data and obstacle detection
- `WebthreadIntegrationHandler`: Health monitoring and commands
- `ROCIntegrationHandler`: Evasion coordination
- `FTIIntegrationHandler`: New robot notifications

**Implementation**: `integration_handlers.py`

## Performance Requirements

| Metric | Target | Critical? | Source |
|--------|--------|-----------|--------|
| **Safety Message Latency** | <20ms | ✅ Yes | DETAILED_ANSWERS.md Q9 |
| **Coordination Message Latency** | <50ms | No | DETAILED_ANSWERS.md Q9 |
| **Status Update Latency** | <100ms | No | DESIGN_CLARIFICATIONS_FINAL.md |
| **Work Area Update Rate** | 20Hz | No | AI_CONTEXT.md |
| **Maximum Robots Supported** | 8+ (optimized for 4) | No | DETAILED_ANSWERS.md Q7 |

## ROS2 Integration

### Topics Published

```python
# Work area broadcasting (all robots)
/robots/work_areas
    Type: custom_msgs/WorkAreaArray
    QoS: Reliable, TransientLocal
    Rate: 20Hz or on change

# Proximity alerts (safety-critical)
/robots/proximity_alert
    Type: custom_msgs/ProximityAlert
    QoS: BestEffort, Volatile, Deadline=20ms
    Rate: 60Hz (matched to DIMC update rate)

# Task coordination status
/robots/task_coordination
    Type: custom_msgs/TaskCoordination
    QoS: Reliable, TransientLocal
    Rate: 10Hz
```

### Services Provided

```python
# Coordinate task between robots
/comc/coordinate_task
    Type: custom_srvs/CoordinateTask
    Description: Request coordination for multi-robot task

# Reserve work area
/comc/reserve_area
    Type: custom_srvs/ReserveArea
    Description: Reserve spatial area for robot operation

# Query robot proximity
/comc/query_proximity
    Type: custom_srvs/QueryProximity
    Description: Get distances to nearby robots
```

### QoS Policy Configuration

**Safety-Critical Messages** (Proximity Alerts):
```python
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, Duration

safety_qos = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,  # Fast > guaranteed
    durability=DurabilityPolicy.VOLATILE,
    deadline=Duration(milliseconds=20),
    history=HistoryPolicy.KEEP_LAST,
    depth=1  # Only latest alert matters
)
```

**Coordination Messages** (Work Areas):
```python
coordination_qos = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,  # Must not lose
    durability=DurabilityPolicy.TRANSIENT_LOCAL,  # Late joiners get data
    history=HistoryPolicy.KEEP_LAST,
    depth=10  # Keep recent work area updates
)
```

Source: `docs/DETAILED_ANSWERS.md` Section on DDS

## Directory Structure

```
components/communication-center/
├── README.md                           # This file
├── IMPLEMENTATION_SUMMARY.md           # Implementation details
├── INTEGRATION_GUIDE.md                # Integration with other components
├── src/
│   ├── python/                         # Primary implementation
│   │   ├── __init__.py
│   │   ├── comc_node.py                # Main ROS2 node
│   │   ├── work_area_manager.py        # Work area broadcasting/subscription
│   │   ├── proximity_monitor.py        # Proximity alert system
│   │   ├── task_coordinator.py         # Multi-robot task coordination
│   │   ├── evade_coordinator.py        # Evade subsystem integration
│   │   └── qos_profiles.py             # QoS policy definitions
│   └── cpp/                            # Optional C++ for performance
│       └── (future: low-level optimizations)
├── tests/
│   ├── test_work_area_manager.py
│   ├── test_proximity_monitor.py
│   ├── test_task_coordinator.py
│   └── test_integration.py
├── launch/
│   └── comc.launch.py                  # ROS2 launch file
├── msg/                                # Custom message definitions
│   ├── WorkArea.msg
│   ├── WorkAreaArray.msg
│   ├── ProximityAlert.msg
│   └── TaskCoordination.msg
├── srv/                                # Custom service definitions
│   ├── CoordinateTask.srv
│   ├── ReserveArea.srv
│   └── QueryProximity.srv
├── Config/
│   ├── comc_config.yaml                # Configuration parameters
│   └── integration_config.json         # Webthread integration spec
└── examples/
    └── multi_robot_coordination_demo.py
```

## Integration Points

### With Other Components

**FTI (Files Type Importer)**:
- No direct integration
- COMC receives robot metadata via Webthread

**DIMC (Dimensions Collector)**:
- Input: Robot positions, velocities, work areas
- Usage: Calculate proximity, detect potential collisions
- Topic: Subscribe to `/robot/{id}/pose` and `/robot/{id}/dimensions`

**ROC (Robot Operator Controller)**:
- Output: Evasion commands, coordination requests
- Usage: Execute multi-robot coordinated movements
- Integration: Via Webthread orchestration

**Webthread**:
- Health monitoring: COMC reports status via heartbeat
- Component coordination: Webthread starts COMC after ROC
- Error recovery: Webthread can restart COMC if failed
- Criticality: Partial (only for multi-robot operations)

### Startup Sequence

From `docs/WEBTHREAD_INITIALIZER.md`:

```
Phase 3: Component Startup
1. FTI   ✅ Starts first
2. DIMC  ✅ Starts after FTI
3. ROC   ✅ Starts after DIMC
4. COMC  ← Starts after ROC (you are here)
5. Webthread Runtime
```

### Graceful Degradation

From `docs/ENHANCED_FEATURES.md`:

**If COMC Fails**:
- System continues in **single-robot mode**
- Multi-robot tasks automatically paused
- Increased safety margins applied
- User notified with yellow warning
- Robots operate independently without coordination

**Criticality**: PARTIAL
- Critical for multi-robot operations
- Not critical for single robot
- Non-critical if only one robot active

## Development Phases

### Phase 1: Core Functionality (Weeks 1-2)
- [ ] Basic ROS2 node structure
- [ ] Work area broadcasting/subscription
- [ ] Simple proximity monitoring
- [ ] Integration with Webthread health monitoring
- [ ] Unit tests for core functionality

### Phase 2: Safety & Coordination (Weeks 3-4)
- [ ] Advanced proximity alerts with escalation
- [ ] Task coordination service
- [ ] QoS policy implementation
- [ ] Integration tests with DIMC
- [ ] Multi-robot coordination tests

### Phase 3: Evade Integration (Week 5)
- [ ] Evade subsystem coordinator
- [ ] Path reservation system
- [ ] Deadlock detection and prevention
- [ ] Integration with ROC for evasion execution
- [ ] System tests with obstacle scenarios

### Phase 4: Optimization (Week 6)
- [ ] Performance tuning (<20ms safety latency)
- [ ] C++ modules for critical paths (if needed)
- [ ] Comprehensive testing with 4+ robots
- [ ] Documentation completion

## Testing Strategy

### Unit Tests
- Work area calculation and broadcasting
- Proximity distance calculations
- Task priority handling
- QoS policy application
- Message serialization/deserialization

### Integration Tests
- COMC ↔ DIMC: Proximity based on real positions
- COMC ↔ ROC: Coordination commands execution
- COMC ↔ Webthread: Health monitoring and recovery
- Multi-robot communication (2, 4, 8 robots)

### System Tests
- End-to-end multi-robot coordination scenario
- Obstacle avoidance with Evade subsystem
- Graceful degradation (COMC failure)
- Performance under load (8 robots, high message rate)

### Performance Tests
- Latency measurement (safety messages <20ms)
- Throughput testing (max messages/second)
- Scalability testing (2, 4, 6, 8 robots)
- Recovery time measurement

## Configuration

### Default Parameters

```yaml
# comc_config.yaml
comc:
  node_name: "communication_center"
  
  proximity:
    alert_threshold_warning: 0.5   # meters
    alert_threshold_caution: 0.3   # meters
    alert_threshold_critical: 0.1  # meters
    update_rate: 60                # Hz (matches DIMC)
  
  work_area:
    broadcast_rate: 20             # Hz
    default_margin: 0.1            # meters (safety buffer)
  
  task_coordination:
    max_wait_time: 10.0            # seconds (deadlock timeout)
    priority_levels: 5             # 0=lowest, 4=highest
  
  performance:
    max_robots: 8
    message_queue_size: 100
```

## Key References

This specification is derived from comprehensive analysis of all 18 documentation files:

1. **AI_CONTEXT.md**: Component overview, status, and integration points
2. **ARCHITECTURE.md**: System architecture and COMC purpose
3. **DESIGN_DECISIONS.md**: Technology stack (DDS, ROS2, Python)
4. **DETAILED_ANSWERS.md**: DDS implementation details and QoS policies
5. **ENHANCED_FEATURES.md**: Evade subsystem integration requirements
6. **DESIGN_CLARIFICATIONS_FINAL.md**: API architecture split (Webthread vs COMC)
7. **PROJECT_STRUCTURE.md**: Directory organization
8. **PRE_DEVELOPMENT_ANALYSIS.md**: Performance requirements and risk mitigation

## Next Steps

1. **Create Implementation Summary**: Document detailed implementation plan
2. **Define ROS2 Messages**: Create `.msg` and `.srv` files
3. **Implement Core Node**: Basic COMC ROS2 node with health monitoring
4. **Work Area Manager**: Broadcasting and subscription logic
5. **Proximity Monitor**: Real-time collision avoidance
6. **Integration Guide**: Document integration with other components
7. **Testing Infrastructure**: Unit, integration, and system tests

## Status Tracking

- [x] Requirements analysis from 18 documentation files
- [x] README created with comprehensive overview
- [x] COMC_ANALYSIS.md created
- [x] IMPLEMENTATION_SUMMARY.md created
- [x] INTEGRATION_GUIDE.md created
- [x] Directory structure created
- [x] ROS2 message definitions (3 messages)
- [x] ROS2 service definitions (3 services)
- [x] QoS profile configurations
- [x] Work area manager implementation
- [x] Proximity monitor implementation
- [x] Task coordinator implementation (NEW)
- [x] Evade coordinator implementation (NEW)
- [x] Integration handlers for all components (NEW)
  - [x] DIMC integration
  - [x] Webthread integration
  - [x] ROC integration
  - [x] FTI integration
- [x] Core COMC node implementation
- [x] Unit tests (19 test cases)
- [x] Configuration files
- [x] Launch file
- [x] Example demo
- [x] ROS2 package build files (package.xml, setup.py, CMakeLists.txt)
- [ ] Integration testing with other components
- [ ] Performance benchmarking (<20ms latency validation)
- [ ] Multi-robot system testing (4+ robots)

---

**Document Version**: 1.0  
**Last Updated**: 2025-11-16  
**Status**: Requirements Complete, Ready for Implementation  
**Author**: Derived from 18 ROA documentation files analysis
