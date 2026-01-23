# Final Design Clarifications - Phase 0 Ready

This document addresses all final clarification questions before beginning Phase 0 POC development.

## Table of Contents
1. [ROS2 Control Implementation Approach](#ros2-control-implementation-approach)
2. [Enhanced Error Handling Strategy](#enhanced-error-handling-strategy)
3. [Enhanced State Machine Design](#enhanced-state-machine-design)
4. [API Architecture Decision](#api-architecture-decision)
5. [Phased Testing Strategy](#phased-testing-strategy)

---

## 1. ROS2 Control Implementation Approach

### Question
*"We going to use ROS2 control and build a code extra for it so we can use ROS2 Control as our base construction?"*

### Answer: YES - Extend ROS2 Control ✅

**Implementation Strategy:**

```
ROS2 Control Framework (Base)
    ↓
ROC Custom Controller (Our Code)
    ↓
Adaptive UI Layer (Our Code)
```

**What We Build:**
1. **Custom Controller Plugin** extending `controller_interface::ControllerInterface`
2. **Adaptive UI** that queries ROS2 Control for available joints/capabilities
3. **ROC-Specific Features:**
   - Multi-robot tab management
   - Slider-based interface (left=min, right=max)
   - Yellow warning system for collisions
   - Position/velocity/torque displays
   - Task queue management

**What ROS2 Control Provides:**
- Joint state management
- Hardware abstraction layer
- Command/state interfaces
- Real-time safe execution
- Tested control loop infrastructure

**Code Structure:**
```
components/roc/
├── roc_controller/          # ROS2 Control plugin (C++)
│   ├── adaptive_controller.cpp
│   ├── joint_manager.cpp
│   └── safety_monitor.cpp
├── roc_ui/                  # Qt/Python UI (extends base)
│   ├── multi_robot_tabs.py
│   ├── adaptive_sliders.py
│   └── status_display.py
└── roc_bridge/              # ROC ↔ ROS2 Control interface
    └── hardware_interface.cpp
```

**Summary:** ROS2 Control is the foundation. We build ROC's unique features (adaptive UI, multi-robot, safety) on top of it.

---

## 2. Enhanced Error Handling Strategy

### Questions & Design Updates

#### 2.1 Tier 3 Reset Behavior

**Question:** *"Webthread will initialize a full reset for the system in case the whole system is malfunctioning and in case just one part will do the reset for just one part?"*

**Answer:** YES - Selective Reset with User Confirmation ✅

**Enhanced Tier 3 Logic:**

```
Component Failure Detected
    ↓
Is it critical to simulation?
    ├── YES (e.g., DIMC, ROC, COMC) → Pause simulation + Alert user
    └── NO  (e.g., FTI finished importing) → Continue running
    ↓
User Options:
1. Reset failed component only
2. Reset entire system
3. Continue without fix (if non-critical)
4. Save state and shutdown
```

**Specific Scenarios:**

| Component | Failure Impact | Webthread Action |
|-----------|---------------|------------------|
| **FTI** (after import done) | None - already completed | Alert only, no action needed |
| **FTI** (during import) | New robots can't be added | Continue with existing robots, alert user |
| **DIMC** | No position updates | **PAUSE simulation**, alert user (critical) |
| **ROC** | No control possible | **PAUSE simulation**, alert user (critical) |
| **COMC** | No robot coordination | Alert user, continue with single-robot mode |
| **Webthread** | Total system loss | Automatic restart (no choice) |

**User Interaction Flow:**
```
[Component Failed: DIMC]
[Simulation PAUSED]

Options:
1. [Reset DIMC Only] - Recommended
2. [Reset All Components]
3. [Finish Current Simulation] - Save and exit UE5
4. [Force Continue] - Unsafe, for debugging only

User Choice: _
```

#### 2.2 Component Independence

**Question:** *"We don't need all to be depended like this on each other like if the FTI stopped working after finishing its job, Webthread can then initiate to reset that part alone from the rest without stopping the whole process"*

**Answer:** AGREED - Improved Dependency Model ✅

**New Dependency Matrix:**

| Component | Critical at Runtime? | Can Restart Independently? | Simulation Must Pause? |
|-----------|---------------------|---------------------------|----------------------|
| FTI | NO (after import) | YES | NO |
| DIMC | YES (always) | YES | YES |
| ROC | YES (if controlling) | YES | YES |
| COMC | PARTIAL (multi-robot only) | YES | NO (degrade to single-robot) |
| Webthread | YES (always) | Auto-restart | YES |

**Graceful Degradation Strategy:**

```python
# Webthread Health Monitor
class ComponentHealthMonitor:
    def handle_failure(self, component, error):
        # Assess criticality
        is_critical = self.is_critical_now(component)
        
        if not is_critical:
            # Non-critical failure
            self.log_error(component, error)
            self.notify_user(severity="WARNING")
            return  # Continue running
        
        # Critical failure
        self.pause_simulation()
        
        # Present options to user
        options = self.get_restart_options(component)
        user_choice = self.prompt_user(options)
        
        if user_choice == "RESET_COMPONENT":
            self.restart_component(component)
        elif user_choice == "RESET_ALL":
            self.restart_all_components()
        elif user_choice == "SAVE_AND_EXIT":
            self.save_state()
            self.shutdown_gracefully()
    
    def is_critical_now(self, component):
        """Check if component is critical in current context"""
        if component == "FTI":
            return self.is_importing_robot()  # Only critical during import
        elif component == "COMC":
            return self.get_active_robot_count() > 1  # Only critical for multi-robot
        elif component in ["DIMC", "ROC"]:
            return True  # Always critical during simulation
        return False
```

**Updated Error Handling Tiers:**

**Tier 1: Local Recovery (Component-Level)**
- Component tries to fix itself
- Retry logic, fallback mechanisms
- Log to local error buffer
- Example: DIMC detects stale data → request fresh data from UE5

**Tier 2: Health Monitoring (Webthread - Passive)**
- Webthread receives heartbeats from all components
- Detects failures via timeout or error reports
- Logs to SQLite database
- Sends alerts to UI

**Tier 3: Coordinated Recovery (Webthread - Active)**
- Assess failure criticality in current context
- Pause simulation if critical
- Present user with options:
  1. Reset failed component only ✅ **NEW**
  2. Reset all components
  3. Finish current work safely
  4. Force continue (debugging mode)
- Execute user choice with status feedback

**CONS Update:**
- ❌ REMOVED: "All components depend on Webthread" (too rigid)
- ✅ NEW: "Components depend on Webthread for coordination, but can run independently if non-critical"
- ✅ NEW: "System supports graceful degradation based on failure context"

---

## 3. Enhanced State Machine Design

### 3.1 Reset State Addition

**Question:** *"We can add a reset state in the cycle, as error→reset→check→error→shutdown, it will go for shutdown in case it faced the same error in one streak"*

**Answer:** EXCELLENT IDEA - Enhanced State Machine ✅

**Updated State Machine with Reset & Error Counting:**

```
DISCONNECTED ──connect──> CONNECTING
                              ├──success──> IDLE
                              └──fail────> ERROR
                                              ↓
IDLE ──command──> MOVING                ERROR ──diagnose──> RESET
 ↑                   │                    ↑                    │
 │                   ├──success──> IDLE   │                   │
 │                   └──collision─> ERROR │                   │
 │                                         │                   │
 └──────────────────────────────────────reset_success────────┘
                                          │
                                    reset_failed (count++)
                                          │
                                    (if count >= 3)
                                          ↓
                                      SHUTDOWN
```

**State Machine with Error Streak Detection:**

```python
class RobotStateMachine:
    def __init__(self):
        self.state = "DISCONNECTED"
        self.error_streak = 0
        self.max_error_streak = 3  # Shutdown after 3 consecutive errors
        self.last_error = None
    
    def transition_to_error(self, error):
        # Check if same error as last time
        if error == self.last_error:
            self.error_streak += 1
        else:
            self.error_streak = 1  # New error type, reset count
        
        self.last_error = error
        self.state = "ERROR"
        
        # Decide next action
        if self.error_streak >= self.max_error_streak:
            self.state = "SHUTDOWN"
            self.log_critical(f"Repeated error {self.error_streak} times: {error}")
        else:
            self.attempt_reset()
    
    def attempt_reset(self):
        self.state = "RESET"
        success = self.execute_reset()
        
        if success:
            self.state = "IDLE"
            self.error_streak = 0  # Reset successful, clear streak
            self.last_error = None
        else:
            self.state = "ERROR"  # Reset failed, count increments
            # Will check error_streak again
```

**Complete State Definitions:**

| State | Description | Can Transition To |
|-------|-------------|-------------------|
| DISCONNECTED | Robot not connected | CONNECTING |
| CONNECTING | Establishing connection | IDLE, ERROR |
| IDLE | Ready to receive commands | MOVING, DISCONNECTED |
| MOVING | Executing task | IDLE, ERROR |
| ERROR | Problem detected | RESET, SHUTDOWN |
| RESET | Attempting recovery | IDLE, ERROR |
| SHUTDOWN | Permanent failure | (terminal state) |

### 3.2 Enhanced Error Types

**Question:** *"We can have two different errors, one called failure in case the robot reached the target but failed to do the task, AND another one called Error and it means it stopped before reaching the target by a problem in the system of ROA, AND last one called obstacle means something stopped it while it was working"*

**Answer:** PERFECT - Detailed Error Classification ✅

**Three Main Error Categories:**

#### Category 1: TASK_FAILURE
- **Definition:** Robot reached target position but couldn't complete task
- **Sub-types:**
  - `GRIPPER_FAILURE_WITH_OBJECT` - Has object, couldn't release/place
  - `GRIPPER_FAILURE_EMPTY` - Couldn't grasp object
  - `TOOL_MALFUNCTION` - Tool at target doesn't work
- **Response:** Mark task as failed, log reason, request human intervention
- **State Transition:** MOVING → ERROR (TASK_FAILURE) → RESET → IDLE

#### Category 2: SYSTEM_ERROR
- **Definition:** Internal ROA system problem prevented reaching target
- **Sub-types:**
  - `DIMC_DATA_LOSS` - Lost position tracking
  - `ROC_COMMAND_TIMEOUT` - Control commands not getting through
  - `COMC_CONNECTION_LOST` - Communication with other robots failed
  - `WEBTHREAD_CRASH` - Bridge to ROS2/UE5 failed
- **Response:** Log to database, attempt component reset, notify user
- **State Transition:** MOVING → ERROR (SYSTEM_ERROR) → RESET → Check if same error → SHUTDOWN (if 3x)

#### Category 3: OBSTACLE
- **Definition:** Physical obstruction detected by sensors during movement
- **Sub-types:**
  - `OBSTACLE_WITH_LOAD` - Carrying object, obstacle detected
  - `OBSTACLE_EMPTY` - Not carrying object, obstacle detected
  - `COLLISION_DETECTED` - Already made contact
  - `WORKSPACE_BOUNDARY` - Reached safety limit
- **Response:** 
  - Stop immediately
  - Yellow warning visual
  - Log position and obstacle info
  - Wait for user decision or path re-plan
- **State Transition:** MOVING → ERROR (OBSTACLE) → IDLE (after clearance)

**Error Classification Implementation:**

```python
class ErrorType(Enum):
    # TASK_FAILURE category
    GRIPPER_FAILURE_WITH_OBJECT = "task_failure_gripper_loaded"
    GRIPPER_FAILURE_EMPTY = "task_failure_gripper_empty"
    TOOL_MALFUNCTION = "task_failure_tool"
    
    # SYSTEM_ERROR category
    DIMC_DATA_LOSS = "system_error_dimc"
    ROC_COMMAND_TIMEOUT = "system_error_roc"
    COMC_CONNECTION_LOST = "system_error_comc"
    WEBTHREAD_CRASH = "system_error_webthread"
    
    # OBSTACLE category
    OBSTACLE_WITH_LOAD = "obstacle_loaded"
    OBSTACLE_EMPTY = "obstacle_empty"
    COLLISION_DETECTED = "obstacle_collision"
    WORKSPACE_BOUNDARY = "obstacle_boundary"

class ErrorHandler:
    def handle_error(self, error_type, robot_id):
        category = self.categorize(error_type)
        
        if category == "TASK_FAILURE":
            self.mark_task_failed(robot_id, error_type)
            self.notify_user(f"Robot {robot_id} reached target but task failed: {error_type}")
            return "REQUEST_HUMAN_INTERVENTION"
        
        elif category == "SYSTEM_ERROR":
            self.log_system_error(error_type, robot_id)
            return "ATTEMPT_COMPONENT_RESET"
        
        elif category == "OBSTACLE":
            has_load = "WITH_LOAD" in error_type.name
            self.show_yellow_warning(robot_id, has_load)
            self.log_obstacle(robot_id, error_type, has_load)
            
            if has_load:
                return "WAIT_FOR_USER_DECISION"  # Critical - don't auto-retry with load
            else:
                return "ATTEMPT_PATH_REPLAN"  # Can try alternate path
```

**Error Response Matrix:**

| Error Category | Has Object? | Auto-Recovery? | User Notification |
|----------------|-------------|----------------|-------------------|
| TASK_FAILURE | YES | NO | Required - task marked failed |
| TASK_FAILURE | NO | NO | Required - investigate cause |
| SYSTEM_ERROR | N/A | YES (3 attempts) | Warning + status |
| OBSTACLE | YES | NO | Required - safety priority |
| OBSTACLE | NO | YES (re-plan path) | Warning only |

**Updated State Machine with Error Categories:**

```
MOVING ──────┬──success──> IDLE
             │
             ├──TASK_FAILURE──> ERROR ──> mark_failed ──> IDLE (await new task)
             │
             ├──SYSTEM_ERROR──> ERROR ──> RESET ──> IDLE or SHUTDOWN (if 3x)
             │
             └──OBSTACLE─────> ERROR ──┬──empty──> IDLE (re-plan path)
                                       └──loaded─> IDLE (await user decision)
```

---

## 4. API Architecture Decision

### Question
*"Can't this be part of COMC as it works in the communication between (the user and the robots) and (the robots and the other robots), what I mean is should the main hub of API be COMC or in Webthread?"*

### Answer: Split Responsibility - Both Play a Role ✅

**Conceptual Clarification:**

**API Specifications ≠ Communication Protocol**

- **API Specs** = Interface definitions (what topics exist, what messages mean, parameters, etc.)
- **COMC** = Runtime communication between robots (executing the communication)
- **Webthread** = System integration and coordination hub

**Architecture Decision:**

```
┌─────────────────────────────────────────────────────────────┐
│                    API SPECIFICATIONS                        │
│                  (Defined in api_specs/)                     │
│  - ROS2 message types                                        │
│  - Topic names & frequencies                                 │
│  - Service definitions                                       │
│  - Action definitions                                        │
└─────────────────────────────────────────────────────────────┘
                            ↓
              Used by ALL components
                            ↓
        ┌───────────────────┴───────────────────┐
        │                                       │
        ↓                                       ↓
┌───────────────┐                      ┌───────────────┐
│   WEBTHREAD   │                      │     COMC      │
├───────────────┤                      ├───────────────┤
│ Implements:   │                      │ Implements:   │
│               │                      │               │
│ • User→Robot  │                      │ • Robot↔Robot │
│ • ROS2↔UE5    │                      │ • Work areas  │
│ • System APIs │                      │ • Coordination│
│ • Health      │                      │ • Collision   │
│ • Logging     │                      │   avoidance   │
└───────────────┘                      └───────────────┘
```

**Responsibility Split:**

#### Webthread Handles:
1. **User ↔ Robot Communication** (via ROC)
   - User sends commands → Webthread → ROC → Robot
   - Robot status → ROC → Webthread → User UI
   
2. **System Integration APIs**
   - ROS2 ↔ UE5 bridge
   - Component health monitoring
   - Central logging
   - Configuration management

3. **Examples:**
   - `/robot/{id}/command` - User command to specific robot
   - `/robot/{id}/status` - Robot status for UI display
   - `/system/health` - System-wide health check
   - `/ue5/sync` - UE5 synchronization

#### COMC Handles:
1. **Robot ↔ Robot Communication**
   - Robot broadcasts work area
   - Robots coordinate task sequencing
   - Collision avoidance negotiation
   
2. **Multi-Robot Coordination APIs**
   - Work area sharing
   - Task coordination
   - Proximity alerts

3. **Examples:**
   - `/robots/work_areas` - All robots publish work zones
   - `/robots/proximity_alert` - Collision warning between robots
   - `/robots/task_coordination` - "I'm going to X, anyone near X?"

**Why This Split Makes Sense:**

| Aspect | Webthread | COMC |
|--------|-----------|------|
| **Primary Users** | Humans (via UI), ROS2/UE5 | Robots themselves |
| **Message Pattern** | Hub-and-spoke (centralized) | Peer-to-peer or broadcast |
| **Latency Requirement** | <50ms (acceptable) | <20ms (safety-critical) |
| **Failure Impact** | System coordination lost | Multi-robot safety lost |
| **Example** | "User tells Robot 1 to move to X" | "Robot 1 tells Robot 2: stay away from X" |

**Shared API Definitions (api_specs/ folder):**

```
api_specs/
├── messages/
│   ├── RobotCommand.msg        # Used by Webthread (user→robot)
│   ├── RobotStatus.msg         # Used by Webthread (robot→user)
│   ├── WorkArea.msg            # Used by COMC (robot↔robot)
│   └── ProximityAlert.msg      # Used by COMC (robot↔robot)
├── services/
│   ├── ResetComponent.srv      # Used by Webthread (system control)
│   └── CoordinateTask.srv      # Used by COMC (robot coordination)
└── actions/
    ├── ExecuteTask.action      # Used by ROC (task execution)
    └── PathPlanning.action     # Used by COMC (collision-free path)
```

**Complete Communication Flow Example:**

```
User in ROC UI: "Move Robot 1 to position X"
    ↓
Webthread API: POST /robot/1/command {target: X}
    ↓
Webthread → ROS2 topic: /robot_1/command
    ↓
ROC receives command, starts movement
    ↓
Robot 1 → COMC: "I'm moving to X" via /robots/work_areas
    ↓
COMC checks: "Is any other robot near X?"
    ├── NO → Allow movement
    └── YES → Send /robots/proximity_alert to Robot 1 & Robot 2
    ↓
Robot 1 status → Webthread via /robot_1/status
    ↓
Webthread → ROC UI: Update displayed position
```

**Summary:**
- **API Specifications:** Defined centrally, used by all components
- **Webthread:** Implements user↔system and system↔ROS2/UE5 APIs
- **COMC:** Implements robot↔robot coordination APIs
- Both are API endpoints, different purposes

---

## 5. Phased Testing Strategy

### Question
*"We will go with the four types of tests but in order, so when we test each component alone and it functional, we then will go to the next phase of testing which is the components together, and last..."*

### Answer: Sequential Testing Phases - AGREED ✅

**Testing Phases in Order:**

```
Phase 1: Unit Testing (Each component alone)
    ↓ (All components pass)
Phase 2: Integration Testing (Components together, pairs)
    ↓ (All pairs work)
Phase 3: System Testing (End-to-end workflows)
    ↓ (All workflows pass)
Phase 4: Performance Testing (Real-world scenarios)
    ↓
Ready for Production/Demo
```

### Detailed Phase Breakdown

#### Phase 1: Unit Testing (Week 1-2 of development)

**Test each component in isolation with mocked dependencies.**

| Component | Unit Tests | Pass Criteria |
|-----------|-----------|---------------|
| **FTI** | Import URDF, STL, SDF files | Files imported, hierarchy preserved |
| **DIMC** | Track UE5 object positions | Position updates at 60Hz, <1cm error |
| **ROC** | Send control commands | Commands formatted correctly, sliders respond |
| **COMC** | Broadcast/receive work areas | Messages sent/received within 20ms |
| **Webthread** | Bridge ROS2↔UE5 | Messages cross bridge successfully |

**Tools:**
- Python: `pytest` with mocks
- C++: `gtest` with mock objects
- ROS2: `ros2 launch` test files

**Example Unit Test (FTI):**
```python
# test_fti_urdf_import.py
def test_import_ur5_urdf():
    fti = FileTypeImporter()
    robot_data = fti.import_file("ur5.urdf")
    
    assert robot_data.name == "ur5"
    assert len(robot_data.joints) == 6
    assert robot_data.has_hierarchy == True
    assert robot_data.base_link == "base_link"
```

**Exit Criteria for Phase 1:**
- ✅ 80%+ code coverage for each component
- ✅ All individual component tests passing
- ✅ No critical bugs in isolated operation

---

#### Phase 2: Integration Testing (Week 3-4 of development)

**Test component pairs working together.**

| Component Pair | Integration Test | Pass Criteria |
|----------------|-----------------|---------------|
| **FTI ↔ DIMC** | Import robot, track in UE5 | DIMC receives valid object from FTI |
| **DIMC ↔ ROC** | Track position, send commands | ROC gets positions, robot moves correctly |
| **ROC ↔ COMC** | Multi-robot coordination | Robots share commands, avoid collision |
| **COMC ↔ Webthread** | Robot status to UI | User sees all robot states |
| **Webthread ↔ UE5** | Full bridge communication | Bidirectional data flow works |

**Example Integration Test (DIMC ↔ ROC):**
```python
# test_dimc_roc_integration.py
def test_position_tracking_to_control():
    # Setup
    dimc = DimensionsCollector()
    roc = RobotOperatorController()
    
    # Start tracking
    dimc.start_tracking("robot_1")
    
    # ROC sends move command
    roc.send_command("robot_1", target=[1.0, 2.0, 3.0])
    
    # Wait for movement
    time.sleep(0.5)
    
    # DIMC should see new position
    position = dimc.get_position("robot_1")
    assert position.is_near([1.0, 2.0, 3.0], tolerance=0.1)
```

**Exit Criteria for Phase 2:**
- ✅ All component pairs can exchange data
- ✅ No data loss between components
- ✅ Latency requirements met (<20ms for critical paths)
- ✅ No integration bugs

---

#### Phase 3: System Testing (Week 5 of development)

**Test complete end-to-end workflows.**

| Workflow | Test Scenario | Pass Criteria |
|----------|--------------|---------------|
| **Robot Import & Control** | Import UR5, control via sliders | User can move robot smoothly |
| **Multi-Robot Coordination** | 2 robots, avoid collision | No collisions, work areas respected |
| **Task Queue Execution** | Queue 3 tasks for robot | All tasks execute in order |
| **Error Recovery** | Trigger obstacle, recover | Yellow warning, reset works |
| **System Monitoring** | Monitor 4 robots | All statuses update in real-time |

**Example System Test:**
```python
# test_complete_workflow.py
def test_import_and_control_ur5():
    """End-to-end: Import UR5 URDF and control it"""
    
    # Phase 1: Import
    fti = FileTypeImporter()
    robot_id = fti.import_robot("ur5.urdf")
    assert robot_id is not None
    
    # Phase 2: Verify in UE5
    dimc = DimensionsCollector()
    position = dimc.get_position(robot_id)
    assert position is not None
    
    # Phase 3: Control
    roc = RobotOperatorController()
    roc.connect_robot(robot_id)
    
    # Phase 4: Move robot
    initial_pos = dimc.get_position(robot_id)
    roc.send_command(robot_id, target=[1.0, 0.0, 0.5])
    time.sleep(1.0)
    final_pos = dimc.get_position(robot_id)
    
    assert final_pos != initial_pos  # Robot moved
    
    # Phase 5: Check logs
    logs = Webthread.get_logs(robot_id)
    assert "command_sent" in logs
    assert "movement_completed" in logs
```

**Exit Criteria for Phase 3:**
- ✅ All critical workflows work end-to-end
- ✅ User can perform typical operations without errors
- ✅ System handles typical failure scenarios gracefully
- ✅ No showstopper bugs

---

#### Phase 4: Performance Testing (Week 6 of development)

**Test under real-world load and stress conditions.**

| Test Type | Scenario | Pass Criteria |
|-----------|----------|---------------|
| **Latency** | Control loop timing | <20ms consistently |
| **Throughput** | 4 robots, simultaneous movement | 30+ FPS, no lag |
| **Stress** | 1000 commands in 1 minute | All executed, no drops |
| **Endurance** | Run for 1 hour | No memory leaks, stable |
| **Recovery** | Trigger 10 errors | All recovered within 5 seconds |

**Example Performance Test:**
```python
# test_performance_latency.py
def test_control_loop_latency():
    """Verify <20ms latency requirement"""
    
    roc = RobotOperatorController()
    robot_id = "test_robot_1"
    
    latencies = []
    for i in range(100):
        start_time = time.perf_counter()
        roc.send_command(robot_id, target=[i/100.0, 0, 0])
        
        # Wait for acknowledgment from Webthread
        ack = roc.wait_for_ack(robot_id)
        end_time = time.perf_counter()
        
        latency_ms = (end_time - start_time) * 1000
        latencies.append(latency_ms)
    
    avg_latency = statistics.mean(latencies)
    max_latency = max(latencies)
    p95_latency = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
    
    print(f"Latency - Avg: {avg_latency:.2f}ms, Max: {max_latency:.2f}ms, P95: {p95_latency:.2f}ms")
    
    assert avg_latency < 20.0, f"Average latency {avg_latency}ms exceeds 20ms target"
    assert p95_latency < 30.0, f"95th percentile {p95_latency}ms too high"
```

**Performance Metrics to Track:**

```
Control Loop Latency:
    Target: <20ms average
    Acceptable: <30ms P95
    Critical: <50ms P99

Frame Rate (4 robots):
    Target: 30 FPS
    Acceptable: 25 FPS
    Critical: 20 FPS

DIMC Update Rate:
    Target: 60 Hz
    Acceptable: 50 Hz
    Critical: 30 Hz

Memory Usage:
    Target: <4GB
    Acceptable: <6GB
    Critical: <8GB (32GB total available)

Error Recovery Time:
    Target: <2 seconds
    Acceptable: <5 seconds
    Critical: <10 seconds
```

**Exit Criteria for Phase 4:**
- ✅ All performance targets met under typical load
- ✅ System stable under stress conditions
- ✅ No performance degradation over time (memory leaks)
- ✅ Performance acceptable on target hardware (Alienware R5)

---

### Testing Phase Schedule

**Integrated into Development:**

```
Week 1-2: Phase 1 (Unit Tests)
    - Write tests for each component as you code
    - Run tests continuously during development
    - Fix failures immediately

Week 3-4: Phase 2 (Integration Tests)
    - Start as soon as 2+ components ready
    - Test component pairs
    - Fix integration issues before moving forward

Week 5: Phase 3 (System Tests)
    - After Phase 0 POC complete
    - Test full workflows
    - User acceptance testing

Week 6: Phase 4 (Performance Tests)
    - Optimize based on performance data
    - Final tuning before release
    - Benchmark against requirements

Week 7: Final Validation
    - Re-run all test phases
    - Document results
    - Demo preparation
```

**Continuous Testing Practices:**

1. **Automated Test Runs:**
   ```bash
   # Run all tests before each commit
   ./run_all_tests.sh
   ```

2. **CI/CD Integration:**
   - GitHub Actions run tests on every push
   - Block merges if tests fail
   - Performance regression detection

3. **Test Coverage Monitoring:**
   - Track coverage percentage
   - Flag untested code paths
   - Target: 80%+ coverage

4. **Nightly Test Runs:**
   - Full test suite overnight
   - Includes long-running tests
   - Performance benchmarking

**Summary:**
Testing proceeds sequentially through 4 phases (Unit → Integration → System → Performance), with each phase building on the success of the previous phase. Tests are written during development, not after.

---

## Summary of Final Decisions

### ✅ Confirmed Approaches

1. **ROS2 Control:** Use as base, extend with ROC-specific features
2. **Error Handling:** Hybrid 3-tier with selective reset and user confirmation
3. **State Machine:** Enhanced with RESET state and error streak detection (shutdown after 3)
4. **Error Types:** Three categories (TASK_FAILURE, SYSTEM_ERROR, OBSTACLE) with subtypes
5. **API Architecture:** Split - Webthread (user↔system), COMC (robot↔robot), shared specs
6. **Testing:** Sequential phases (Unit → Integration → System → Performance)

### ✅ Enhanced Features

1. **Component Independence:** Non-critical components can fail without stopping simulation
2. **Graceful Degradation:** System continues with reduced functionality when possible
3. **User-Controlled Recovery:** User decides reset scope (component vs. entire system)
4. **Context-Aware Criticality:** Failure impact assessed based on current operations
5. **Error Classification:** Detailed error types with different recovery strategies

### 🚀 Ready for Phase 0 POC

All clarifications complete. Begin 1-week proof-of-concept development focusing on:
- Days 1-2: Minimal UE5-ROS2 bridge
- Days 3-4: Control loop latency validation (<20ms)
- Days 5-6: Simple robot import test
- Day 7: Document findings, finalize architecture

**Design phase complete. Development phase ready to begin!**
