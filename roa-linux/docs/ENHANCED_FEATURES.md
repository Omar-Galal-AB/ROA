# Enhanced Features - ROA System

This document details the advanced features added to the ROA (Robot Operating Architecture) system including dual control modes, intelligent obstacle avoidance, safety level system, and improved architecture resilience.

## Table of Contents
1. [Dual Control Modes](#dual-control-modes)
2. [Evade Subsystem](#evade-subsystem)
3. [Three-Level Safety System](#three-level-safety-system)
4. [Improved Architecture Resilience](#improved-architecture-resilience)

---

## Dual Control Modes

The ROA system supports two distinct control paradigms that can be used simultaneously across different robots or switched per robot as needed.

### RPM (Role Playing Mode)

**Description:** Manual, direct control mode where the operator controls each robot individually in real-time.

**Characteristics:**
- Direct slider-based interface for all robot joints/axes
- Real-time command execution (<20ms latency)
- Full operator authority with safety limit enforcement
- Visual feedback: Position, orientation, distance displayed above sliders
- Yellow warning indicators for safety violations
- Individual robot selection via tabbed interface

**Use Cases:**
- Precision tasks requiring human judgment
- Learning and familiarization with robot capabilities
- Troubleshooting and diagnostic operations
- Complex manipulation requiring real-time adjustment
- Critical tasks where automation is unsuitable

**Safety Features in RPM:**
- Slider ranges respect safety margins (10% by default)
- Safety level enforcement (Fragile/Standard/Robust applies)
- Collision detection with auto-stop
- Work area boundary enforcement
- User override capability with confirmation prompts

### ADM (Auto Driven Mode)

**Description:** Autonomous, self-driven mode inspired by RTS (Real-Time Strategy) games where robots execute high-level commands independently.

**Characteristics:**
- High-level task commands (e.g., "Move object A to position B")
- Automatic path planning and execution
- Autonomous obstacle avoidance via Evade subsystem
- Multi-step task completion without constant supervision
- Collision-free coordination with other robots via COMC
- Automatic re-planning when environment changes

**Use Cases:**
- Repetitive tasks (assembly line operations)
- Multi-robot coordinated operations
- Efficiency-focused construction work
- Tasks with well-defined start/end states
- Operations requiring minimal human intervention

**ADM Task Structure:**
```
Task Command:
  - Target: Object/Position
  - Action: Pick/Place/Move/Assemble
  - Priority: Low/Normal/High/Critical
  - Safety Level: Fragile/Standard/Robust
  - Timeout: Max execution time
  - Fallback: User intervention/retry/skip
```

### Mixed Mode Operation

**Key Feature:** Different robots can operate in different modes simultaneously.

**Examples:**
- Robot 1 (RPM): User controls arm for precision welding
- Robot 2 (ADM): Autonomous material transport
- Robot 3 (ADM): Autonomous quality inspection
- Robot 4 (RPM): User controls drone for visual inspection

**Mode Switching:**
- Per-robot configuration
- User can switch robot from ADM → RPM at any time (takes control)
- RPM → ADM requires task specification
- Mode indicator visible in ROC interface
- Transition time: <500ms

**Visual Indicators:**
- **RPM Mode:** Blue highlight on robot tab, manual control icon
- **ADM Mode:** Green highlight on robot tab, automation icon
- **Transitioning:** Yellow highlight during mode switch

---

## Evade Subsystem

**Purpose:** Intelligent obstacle avoidance for robots in ADM mode, enabling autonomous navigation around unexpected obstacles.

### Core Functionality

**Real-Time Obstacle Detection:**
- Continuous monitoring via DIMC at 60Hz
- Obstacle classification (static, dynamic, robot, boundary)
- Distance measurement and approach velocity calculation
- Collision risk assessment

**Automatic Path Recalculation:**
- Safe detour generation when obstacle detected
- Collision-free routing considering all active robots via COMC
- Maintains task objectives while avoiding obstacles
- Respects work area boundaries and safety zones

**Configuration Parameters:**
- **Max Detour Distance:** 2m default (configurable per robot type)
  - Aerial drones: Up to 5m (more maneuverable)
  - Ground robots: 1-2m (limited space)
  - Manipulators: 0.5-1m (workspace constraints)
- **Safety Margin:** 10-50cm buffer around obstacles
- **Re-plan Timeout:** 5s maximum for alternative path calculation
- **Fallback Threshold:** 3 consecutive evasion failures triggers user notification

### Evasion Behavior Flow

```
1. OBSTACLE_DETECTED
   ↓
   - Assess obstacle type and distance
   - Calculate collision risk
   - Determine if evasion is possible
   
2. TRY_IMMEDIATE_SAFE_DETOUR
   ↓
   - Generate alternate path within safety margin
   - Check path validity (no new collisions)
   - Coordinate with other robots via COMC
   - IF PATH_VALID → Execute detour
   - ELSE → Go to step 3

3. PATH_BLOCKED_CALCULATE_ALTERNATIVE
   ↓
   - Expand search radius up to max detour (2m)
   - Generate multiple path candidates
   - Evaluate each for safety and efficiency
   - Select best viable path
   - IF VALID_PATH_FOUND → Execute
   - ELSE → Go to step 4

4. NO_VALID_PATH_REQUEST_OPERATOR
   ↓
   - Stop robot safely
   - Yellow warning in ROC interface
   - Display obstacle information
   - Options presented to user:
     • Take manual control (switch to RPM)
     • Provide different route waypoints
     • Cancel task
     • Wait for obstacle to clear (if dynamic)

5. CRITICAL_BLOCK_FULL_STOP
   ↓
   - Immediate stop (emergency braking)
   - Notify all nearby robots via COMC
   - Create safety zone around stopped robot
   - Automatic switch to RPM mode
   - Require user acknowledgment to resume
```

### Load-Aware Evasion

**Without Load (Empty):**
- More aggressive evasion (tighter margins acceptable)
- Faster movements during detour
- Re-plan attempts: Up to 3 times
- Fallback: Automatic after 3 failures

**With Load (Carrying Object):**
- Conservative evasion (larger safety margins)
- Slower, controlled movements
- Safety level enforcement (Fragile → extra cautious)
- Re-plan attempts: 1 time only
- Fallback: Immediate user notification

**With Fragile Load:**
- Maximum safety margins (2x normal)
- Minimal acceleration during evasion
- No aggressive maneuvers
- Stop-and-assess approach (pause before each movement)
- User confirmation for any detour >0.5m

### Multi-Robot Coordination During Evasion

**COMC Integration:**
- Broadcast evasion intent to all robots
- Reserve alternative path space
- Coordinate timing to avoid conflicts
- Priority-based right-of-way (task priority determines who evades)

**Deadlock Prevention:**
- Timeout-based backoff (lower priority robot waits)
- Alternative path suggestions from COMC
- User intervention after 10s deadlock

---

## Three-Level Safety System

**Purpose:** Adaptive safety parameters based on task requirements and object characteristics, balancing speed/efficiency with safety.

### Safety Level Specifications

#### 1. Fragile Mode (Maximum Care)

**When to Use:**
- Glass, ceramics, electronics
- Delicate assemblies
- Precision instruments
- Art installations
- Any task marked "handle with care"

**Parameters:**
| Parameter | Value | Ratio to Standard |
|-----------|-------|-------------------|
| Speed | 60% of normal | 0.6x |
| Max Acceleration | 50% of normal | 0.5x |
| Gripper Force | Minimum safe (configurable) | 0.3-0.5x |
| Jerk (rate of acceleration change) | 30% of normal | 0.3x |
| Safety Margin (collision) | 20cm default | 2x |
| Evasion Aggressiveness | Very conservative | Minimal |

**Visual Indicators:**
- Orange/yellow color scheme in ROC
- "FRAGILE" label on robot tab
- Speed/force limiters visible and enforced

**RPM Behavior:**
- Slider ranges restricted to safe zones
- Force feedback when approaching limits
- Cannot override safety limits (unlike other modes)
- Warning if user attempts dangerous movements

**ADM Behavior:**
- Extended task completion times accepted
- Prefers longer, safer paths
- Stops fully before any direction change
- Re-plans on any unexpected vibration/acceleration

#### 2. Standard Mode (Normal Operations)

**When to Use:**
- Most industrial construction tasks
- General material handling
- Standard assembly operations
- Wood, plastic, metal (non-critical)
- Default mode for unspecified tasks

**Parameters:**
| Parameter | Value | Ratio to Standard |
|-----------|-------|-------------------|
| Speed | 100% of rated capacity | 1.0x |
| Max Acceleration | 100% of rated | 1.0x |
| Gripper Force | Standard from URDF specs | 1.0x |
| Jerk | Normal | 1.0x |
| Safety Margin (collision) | 10cm default | 1x |
| Evasion Aggressiveness | Balanced | Normal |

**Visual Indicators:**
- Blue color scheme in ROC
- "STANDARD" label (or no label - default)
- Full range sliders available

**RPM Behavior:**
- Full slider ranges with 10% safety margin
- User can override limits with confirmation
- Normal responsiveness

**ADM Behavior:**
- Balanced speed vs safety
- Standard path planning
- Normal evasion behavior

#### 3. Robust Mode (Heavy Duty)

**When to Use:**
- Steel beams, concrete blocks
- Heavy equipment moving
- High-force tasks (pressing, crushing)
- Time-critical operations
- Environments with loose constraints

**Parameters:**
| Parameter | Value | Ratio to Standard |
|-----------|-------|-------------------|
| Speed | 100-120% (if robot capable) | 1.0-1.2x |
| Max Acceleration | 100-150% | 1.0-1.5x |
| Gripper Force | Maximum rated | 1.5-2.0x |
| Jerk | Fast | 1.5x |
| Safety Margin (collision) | 5cm (minimum) | 0.5x |
| Evasion Aggressiveness | Efficiency-focused | Maximum |

**Visual Indicators:**
- Red/dark color scheme in ROC
- "ROBUST" or "HEAVY DUTY" label
- Extended slider ranges (up to +5% over URDF max)
- Warning icon (indicates aggressive mode)

**RPM Behavior:**
- Extended slider ranges
- Reduced safety enforcements
- User has more authority
- Warnings but allows aggressive movements

**ADM Behavior:**
- Prioritizes task completion speed
- Tighter safety margins
- More aggressive evasion maneuvers
- Shorter timeout for re-planning

### Safety Level Selection & Switching

**Selection Methods:**
1. **Manual:** User selects via dropdown in ROC
2. **Auto-Suggest:** System recommends based on object metadata (if available in URDF/task definition)
3. **Task-Based:** Specified in task command (ADM mode)

**Switching During Operation:**
- Requires robot to be in IDLE state (not moving)
- Transition time: <100ms
- User confirmation required
- Logs level change in Webthread

**Override Rules:**
- Fragile mode: Cannot be overridden (safety-critical)
- Standard mode: Can upgrade to Robust with confirmation
- Robust mode: Can downgrade anytime without confirmation

**Cross-Mode Application:**
- Safety levels apply in BOTH RPM and ADM modes
- RPM: Affects slider ranges and responsiveness
- ADM: Affects path planning and evasion behavior

---

## Improved Architecture Resilience

**Goal:** Reduce single-point-of-failure risk while maintaining Webthread as central coordinator.

### Problem with Original Design

**Original:** All components critically dependent on Webthread
- Any Webthread failure → entire system stops
- Component cannot operate without continuous Webthread connection
- Rigid architecture limits fault tolerance

### Enhanced Architecture

**New Model:** Webthread as coordinator, not executor

#### Component Independence

**FTI (Files Type Importer):**
- **Criticality:** Non-critical after import completes
- **Independence:** Can fail/restart without affecting running simulation
- **Recovery:** Restart only when new import needed

**DIMC (Dimensions Collector):**
- **Criticality:** Critical during robot operation (safety-critical)
- **Independence:** Can cache data locally for 1s if Webthread unreachable
- **Recovery:** Must reconnect within 2s or robots auto-stop (safety)

**ROC (Robot Operator Controller):**
- **Criticality:** Critical when controlling robots
- **Independence:** Can buffer commands locally for 500ms
- **Recovery:** Pauses robot if Webthread unreachable >2s, waits for reconnection

**COMC (Communication Center):**
- **Criticality:** Partial (only for multi-robot coordination)
- **Independence:** Degrades to single-robot mode if isolated
- **Recovery:** Robots continue individual operation, multi-robot tasks paused

**Webthread:**
- **Criticality:** High (but not instant-failure)
- **Independence:** Auto-restart mechanism (systemd or similar)
- **Recovery:** Components pause 2s, resume when Webthread back online

#### Health Check System

**Periodic Health Monitoring:**
- **Frequency:** Every 500ms (2 Hz)
- **Method:** Heartbeat messages via ROS2 topics
- **Timeout:** 3 missed heartbeats = component considered failed (1.5s total)

**Health Check Flow:**
```
Component → Webthread (every 500ms):
  {
    "component": "ROC",
    "status": "HEALTHY",
    "timestamp": <unix_time>,
    "active_robots": [1, 3],
    "cpu_usage": 23.5,
    "memory_mb": 145
  }

Webthread → Component (every 500ms):
  {
    "status": "ACK",
    "timestamp": <unix_time>,
    "system_state": "NORMAL"
  }
```

**Failure Detection:**
1. Component misses heartbeat → Webthread flags as "DEGRADED"
2. Component misses 3 heartbeats → Webthread flags as "FAILED"
3. Webthread analyzes impact (critical vs non-critical)
4. Webthread takes action based on criticality

#### Graceful Degradation Hierarchy

**Failure Scenarios:**

| Component Failed | Impact | System Response | User Notification |
|------------------|--------|-----------------|-------------------|
| FTI (during import) | Cannot complete import | Pause import, notify user | Yellow warning |
| FTI (after import) | None | Continue operation | Info message only |
| DIMC | Robots cannot operate safely | Stop all robots | Red alert |
| ROC (one robot) | That robot stops | Other robots continue | Yellow warning |
| ROC (all robots) | No manual control | ADM continues if active | Red alert |
| COMC | Multi-robot coordination lost | Degrade to single-robot | Yellow warning |
| Webthread | System pause | 2s grace period → auto-restart | Red alert → Info when recovered |

**Recovery Strategies:**

**Fast Recovery (<2s):**
- Component restarts automatically
- Resumes from last known good state
- No user intervention required
- Logged but not alerted

**Medium Recovery (2-10s):**
- Component requires manual restart
- User notified with yellow warning
- System continues in degraded mode
- User can choose to wait or take action

**Slow Recovery (>10s):**
- Component failure is critical
- User intervention required
- System pauses affected operations
- User presented with recovery options:
  - Manual component restart
  - Reset component to default
  - Continue in degraded mode
  - Full system restart

#### Webthread Auto-Restart

**Mechanism:**
- Supervised by systemd (Linux) or equivalent
- Auto-restart on crash with exponential backoff
- Max restart attempts: 5 in 60s window
- If exceeded → requires manual intervention

**State Preservation:**
- Last known system state saved to disk every 10s
- Robot positions cached
- Active tasks logged
- On restart: Attempt to resume from last state

**Component Notification:**
- Webthread broadcasts "RESTARTING" message before shutdown
- Components enter "WAIT_MODE" for up to 10s
- Webthread broadcasts "READY" on successful restart
- Components resume operation

#### User Control During Failures

**User Options When Component Fails:**

1. **Reset Component Only**
   - Restart just the failed component
   - Preserve all other system state
   - Fastest recovery (5-10s)

2. **Reset All Components**
   - Full system reset
   - All components restart in order
   - Clean slate (15-30s)

3. **Finish Safely Then Reset**
   - Complete current robot tasks
   - Bring robots to safe positions
   - Then reset failed component
   - Prevents mid-task interruption (30-60s)

4. **Force Continue**
   - Override safety checks
   - Continue with degraded functionality
   - Only for non-critical component failures
   - Requires administrator privilege

**Decision Support:**
- System recommends action based on context
- Shows impact of each option
- Highlights risks if continuing degraded

---

## Implementation Notes

### Phase 0 POC Scope

**What to Implement:**
- Basic RPM mode (manual control)
- ADM concept validation (simple task execution)
- Evade prototype (basic obstacle detection and simple detour)
- Standard safety level only
- Basic Webthread health monitoring

**What to Defer:**
- Full Evade system with multi-robot coordination
- Fragile and Robust safety levels
- Advanced auto-restart mechanisms
- Full graceful degradation

### State Machine Updates

**New States Added:**
- `RPM_ACTIVE` - Robot in manual control mode
- `ADM_ACTIVE` - Robot in autonomous mode
- `EVADING` - Robot executing obstacle avoidance maneuver
- `DEGRADED` - Component operating with reduced functionality
- `WAIT_RECONNECT` - Component waiting for Webthread recovery

**State Transitions:**
```
IDLE → RPM_ACTIVE (user takes control)
IDLE → ADM_ACTIVE (task assigned)
RPM_ACTIVE ↔ ADM_ACTIVE (mode switch)
ADM_ACTIVE → EVADING (obstacle detected)
EVADING → ADM_ACTIVE (evasion complete)
EVADING → ERROR (evasion failed)
ANY_STATE → DEGRADED (component failure detected)
DEGRADED → IDLE (recovery successful)
```

### Performance Targets

| Metric | Target | Critical? |
|--------|--------|-----------|
| Mode switch time | <500ms | No |
| Evade detection latency | <50ms | Yes (safety) |
| Evade path calculation | <200ms | No |
| Safety level transition | <100ms | No |
| Health check frequency | 2 Hz (500ms) | No |
| Component failure detection | <1.5s | Yes |
| Auto-restart time | <2s | Yes |

### Testing Requirements

**Unit Tests:**
- RPM slider control with safety limits
- ADM task parsing and execution
- Evade path generation algorithms
- Safety level parameter application
- Health check message handling

**Integration Tests:**
- RPM ↔ ADM mode switching
- Evade coordination via COMC
- Component failure and recovery
- Multi-robot with mixed modes

**System Tests:**
- End-to-end task in ADM with obstacles
- Graceful degradation scenarios
- Full recovery from Webthread restart
- Mixed-mode multi-robot operation

---

## Future Enhancements

**Potential Additions:**
1. **Learning-Based Evasion:** ML model learns optimal evasion strategies
2. **Predictive Obstacle Avoidance:** Anticipate moving obstacles
3. **Dynamic Safety Levels:** Auto-adjust based on task progress
4. **Multi-Robot Choreography:** Coordinated movement patterns in ADM
5. **Voice Control:** Natural language task commands in ADM
6. **AR/VR Integration:** Mixed reality control interface for RPM

---

**Document Version:** 1.0  
**Last Updated:** 2025-11-15  
**Status:** Design Complete, Ready for Phase 0 POC Implementation
