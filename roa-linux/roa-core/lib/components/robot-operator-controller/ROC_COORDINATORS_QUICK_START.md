# ROC New Coordinators - Developer Quick Start

This guide explains how to use the newly integrated ROC coordinators.

---

## Overview

Three new coordinators have been added to ROC:

1. **SafetyCoordinator** - Unified safety monitoring and E-Stop recovery
2. **ControllerCoordinator** - Motion controller orchestration
3. **TaskExecutor** - Autonomous task execution for ADM mode

All are integrated into `ROCCoordinator` and configured via `ROCConfig`.

---

## Safety Coordinator

### Purpose
Monitors robot safety in real-time, triggers E-Stops on violations, manages recovery.

### Usage from ROC Coordinator

```python
# Access via coordinator
coordinator = ROCCoordinator(config)

# Get safety status for a robot
status = coordinator.safety_coordinator.get_robot_safety_status("robot_0")
print(f"Safety state: {status.state.name}")
print(f"Closest obstacle: {status.closest_obstacle_cm}cm")
print(f"E-Stop active: {status.estop_active}")

# Trigger manual E-Stop
coordinator.safety_coordinator.trigger_user_estop("robot_0", reason="operator_requested")

# Trigger global E-Stop (all robots)
coordinator.safety_coordinator.trigger_global_estop(reason="emergency")

# Start recovery after E-Stop cleared
await coordinator.safety_coordinator.start_recovery("robot_0")

# Operator acknowledges E-Stop
coordinator.safety_coordinator.acknowledge_estop("robot_0")

# Get velocity multiplier (for obstacle avoidance)
velocity_mult = coordinator.safety_coordinator.get_velocity_multiplier("robot_0")
# Returns 0.0-1.0 based on obstacles/safety state

# Check if safe to operate
if coordinator.safety_coordinator.is_safe_to_operate("robot_0"):
    # Proceed with motion
    pass

# Set safety level
from .safety.safety_manager import SafetyLevel
coordinator.safety_coordinator.set_safety_level(SafetyLevel.FRAGILE)
```

### Configuration

```python
from .safety_coordinator import SafetyCoordinatorConfig

config = SafetyCoordinatorConfig(
    # Obstacle thresholds (cm)
    obstacle_warning_distance=100.0,
    obstacle_slow_distance=50.0,
    obstacle_stop_distance=10.0,
    
    # Auto E-Stop triggers
    auto_estop_on_collision=True,
    auto_estop_on_limit_exceed=True,
    auto_estop_on_boundary_violation=True,
    
    # Monitoring rate
    safety_check_rate_hz=60.0
)
```

### Key Features

- **Real-time monitoring**: 60Hz safety checks
- **Obstacle-based velocity reduction**: Slows robot near obstacles
- **Auto E-Stop triggers**: Collision, limits, boundaries
- **E-Stop recovery protocol**: 7-phase staged recovery
- **Per-robot safety state**: Independent safety for each robot

---

## Controller Coordinator

### Purpose
Manages all motion controllers (arm, gripper, mobile) for all robots.

### Usage from ROC Coordinator

```python
# Access via coordinator
coordinator = ROCCoordinator(config)

# Execute arm motion
await coordinator.controller_coordinator.execute_arm_command(
    robot_id="robot_0",
    joint_positions={
        "shoulder_pan_joint": 1.57,
        "shoulder_lift_joint": -1.0,
        "elbow_joint": 1.5,
        "wrist_1_joint": 0.0,
        "wrist_2_joint": 0.0,
        "wrist_3_joint": 0.0
    },
    velocity_scale=0.5,  # 50% max velocity
    priority=10  # Higher = executed first
)

# Execute gripper command
await coordinator.controller_coordinator.execute_gripper_command(
    robot_id="robot_0",
    position=0.8,  # 0.0=closed, 1.0=open
    force=50.0,    # Gripping force (optional)
    priority=5
)

# Execute mobile base command
await coordinator.controller_coordinator.execute_mobile_command(
    robot_id="robot_0",
    linear_velocity=(0.5, 0.0, 0.0),  # (x, y, z) m/s
    angular_velocity=0.2,  # rad/s
    duration_s=5.0,  # Run for 5 seconds (None=continuous)
    priority=5
)

# Emergency stop a robot
coordinator.controller_coordinator.emergency_stop("robot_0")

# Emergency stop all robots
coordinator.controller_coordinator.emergency_stop_all()

# Set velocity multiplier from safety
coordinator.controller_coordinator.set_velocity_multiplier("robot_0", 0.5)

# Direct controller access
arm_controller = coordinator.controller_coordinator.get_arm_controller("robot_0")
current_joints = coordinator.controller_coordinator.get_joint_positions("robot_0")

# Get controller status
status = coordinator.controller_coordinator.get_controller_status("robot_0")
print(f"Arm state: {status['arm']['state']}")
print(f"Current joints: {status['arm']['joints']}")
```

### Configuration

```python
from .controller_coordinator import ControllerCoordinatorConfig

config = ControllerCoordinatorConfig(
    # Command queue
    max_queue_depth=100,
    command_timeout_s=5.0,
    
    # Interpolation
    interpolation_rate_hz=60.0,
    max_position_delta=0.1,  # rad/step
    
    # Safety
    apply_velocity_limits=True,
    check_limits_before_execute=True
)
```

### Key Features

- **Per-robot controllers**: Arm, gripper, mobile base
- **Command queuing**: Priority-based execution
- **60Hz interpolation**: Smooth motion
- **Safety integration**: Velocity multipliers from SafetyCoordinator
- **Emergency stop**: Immediate halt with queue clearing

---

## Task Executor

### Purpose
Executes autonomous tasks for ADM mode using path planning and controllers.

### Usage from ROC Coordinator

```python
# Access via coordinator
coordinator = ROCCoordinator(config)

# Create a task
from .task_executor import Task, TaskType

task = Task(
    task_id="move_to_station",
    task_type=TaskType.NAVIGATE,
    robot_id="robot_0",
    target_position={"x": 5.0, "y": 3.0, "z": 0.0},
    target_orientation={"roll": 0, "pitch": 0, "yaw": 1.57},
    priority=10
)

# Execute task (async)
success = await coordinator.task_executor.execute_task(task)

if success:
    print("Task completed successfully!")
else:
    print("Task failed")

# Cancel task
coordinator.task_executor.cancel_task("robot_0")

# Pause/resume task
coordinator.task_executor.pause_task("robot_0")
coordinator.task_executor.resume_task("robot_0")

# Get task status
status = coordinator.task_executor.get_task_status("robot_0")
print(f"State: {status.state.name}")
print(f"Progress: {status.waypoint_progress.progress_percent:.1f}%")
```

### Configuration

```python
from .task_executor import TaskExecutorConfig, PlannerType

config = TaskExecutorConfig(
    # Planner
    default_planner=PlannerType.A_STAR,
    
    # Waypoint navigation
    waypoint_tolerance=0.05,  # meters
    orientation_tolerance=0.1,  # radians
    
    # Replanning
    replan_on_obstacle=True,
    replan_rate_hz=2.0,
    max_replan_attempts=5,
    
    # Timeouts
    planning_timeout_s=5.0,
    waypoint_timeout_s=30.0,
    task_timeout_s=300.0
)
```

### Key Features

- **Path planning**: A* and RRT algorithms
- **Waypoint navigation**: Tolerance-based waypoint tracking
- **Replanning**: Automatic on obstacle detection
- **Velocity ramping**: Slow approach to waypoints
- **Timeout handling**: Per-phase timeouts

---

## Integration Example

Complete example showing all three coordinators working together:

```python
import asyncio
from .roc_coordinator import ROCCoordinator, ROCConfig
from .task_executor import Task, TaskType

async def main():
    # Initialize ROC with all coordinators enabled
    config = ROCConfig(
        enable_safety_coordinator=True,
        enable_controller_coordinator=True,
        enable_task_executor=True
    )
    
    coordinator = ROCCoordinator(config)
    await coordinator.start()
    
    # Register a robot (normally done via FTI)
    robot_spec = {
        "robot_id": "robot_0",
        "joints": [...]  # Joint specifications
    }
    coordinator.register_robot_from_fti(robot_spec)
    
    # Check safety before executing task
    if not coordinator.safety_coordinator.is_safe_to_operate("robot_0"):
        print("Robot not safe to operate!")
        return
    
    # Create autonomous navigation task
    task = Task(
        task_id="warehouse_pickup",
        task_type=TaskType.NAVIGATE,
        robot_id="robot_0",
        target_position={"x": 10.0, "y": 5.0, "z": 0.0},
        priority=10
    )
    
    # Execute task (TaskExecutor uses ControllerCoordinator)
    print("Executing task...")
    success = await coordinator.task_executor.execute_task(task)
    
    if success:
        print("Task completed!")
        
        # Now execute gripper command
        await coordinator.controller_coordinator.execute_gripper_command(
            robot_id="robot_0",
            position=0.0,  # Close gripper
            force=50.0
        )
        print("Gripper closed")
    else:
        print("Task failed - check safety status")
        status = coordinator.safety_coordinator.get_robot_safety_status("robot_0")
        print(f"Safety violations: {status.active_violations}")
    
    # Shutdown
    await coordinator.stop()

# Run
asyncio.run(main())
```

---

## DIMC Integration

All coordinators integrate with DIMC for spatial awareness:

```python
# DIMC obstacle updates → SafetyCoordinator
coordinator.update_from_dimc_obstacles("robot_0", {
    "closest_distance_cm": 45.0,
    "obstacles": [...]
})
# → SafetyCoordinator checks thresholds
# → Triggers E-Stop if < 10cm
# → Reduces velocity if < 100cm

# DIMC boundary updates → SafetyCoordinator
coordinator.update_from_dimc_boundaries("robot_0", {
    "within_bounds": False,
    "margin_cm": 2.0
})
# → SafetyCoordinator triggers E-Stop on boundary violation
```

---

## Callbacks

Register callbacks to respond to coordinator events:

```python
# Safety callbacks
def on_estop(robot_id, estop_type):
    print(f"E-Stop triggered for {robot_id}: {estop_type.name}")
    # Send alert to UI
    
coordinator.safety_coordinator.on_estop_triggered(on_estop)

# Controller callbacks
def on_motion_complete(robot_id, controller_type, success):
    print(f"Motion complete: {robot_id} {controller_type.name}")
    
coordinator.controller_coordinator.on_motion_complete(on_motion_complete)

# Task executor callbacks
def on_task_complete(robot_id, task_id, success):
    print(f"Task {task_id} complete: {success}")
    
coordinator.task_executor.on_task_complete(on_task_complete)
```

---

## Status Monitoring

All coordinators report status via `get_status()`:

```python
# Full ROC status (includes all coordinators)
status = coordinator.get_status()

print("Safety Coordinator:")
print(f"  Robots monitored: {len(status['safety_coordinator']['robots'])}")

print("Controller Coordinator:")
print(f"  Commands executed: {status['controller_coordinator']['statistics']['commands_executed']}")

print("Task Executor:")
print(f"  Active tasks: {status['task_executor']['active_tasks']}")

# Health dashboard for UI
dashboard = coordinator.get_full_health_dashboard()
print(f"Overall health: {dashboard['overall_health']}")
```

---

## Common Patterns

### Pattern 1: Safe Motion Execution

```python
async def execute_safe_motion(coordinator, robot_id, target_joints):
    # 1. Check safety
    if not coordinator.safety_coordinator.is_safe_to_operate(robot_id):
        return False
    
    # 2. Get velocity multiplier
    vel_mult = coordinator.safety_coordinator.get_velocity_multiplier(robot_id)
    
    # 3. Execute with safety limits
    return await coordinator.controller_coordinator.execute_arm_command(
        robot_id=robot_id,
        joint_positions=target_joints,
        velocity_scale=vel_mult
    )
```

### Pattern 2: E-Stop and Recovery

```python
async def estop_and_recover(coordinator, robot_id):
    # 1. Trigger E-Stop
    coordinator.safety_coordinator.trigger_user_estop(robot_id)
    
    # 2. Wait for operator acknowledgment
    # (UI would call acknowledge_estop when ready)
    
    # 3. Start recovery
    success = await coordinator.safety_coordinator.start_recovery(robot_id)
    
    return success
```

### Pattern 3: Autonomous Task with Error Handling

```python
async def execute_task_with_retry(coordinator, task, max_retries=3):
    for attempt in range(max_retries):
        try:
            success = await coordinator.task_executor.execute_task(task)
            if success:
                return True
            
            print(f"Task failed, retry {attempt + 1}/{max_retries}")
            await asyncio.sleep(2.0)
        
        except Exception as e:
            print(f"Task error: {e}")
    
    return False
```

---

## Troubleshooting

### Safety Coordinator Issues

**Robot stuck in E-Stop:**
- Check `get_robot_safety_status()` for active violations
- Ensure operator has called `acknowledge_estop()`
- Check recovery phase via `recovery_manager.get_status()`

**Unexpected velocity reduction:**
- Check `closest_obstacle_cm` - may be obstacle nearby
- Verify obstacle thresholds in config
- Check safety level (Fragile reduces velocity)

### Controller Coordinator Issues

**Commands not executing:**
- Check if command queue is full (`get_status()`)
- Verify velocity multiplier is not 0.0 (E-Stop active)
- Check controller state (may be in error state)

**Jerky motion:**
- Increase `interpolation_rate_hz` (default 60Hz)
- Reduce `max_position_delta` for smoother steps
- Check velocity scaling

### Task Executor Issues

**Task planning fails:**
- Check planning timeout (increase if needed)
- Verify start/goal positions are valid
- Check for obstacles blocking path

**Task execution stalls:**
- Check waypoint tolerance (may be too tight)
- Verify controllers are responding
- Check for safety coordinator blocking motion

---

## Performance Tips

1. **Tune loop rates** based on your robot:
   - High-precision: 100Hz interpolation
   - Standard: 60Hz (default)
   - Low-bandwidth: 30Hz

2. **Command priorities**:
   - E-Stop recovery: Priority 100
   - Collision avoidance: Priority 50
   - Normal tasks: Priority 10
   - Background: Priority 1

3. **Safety thresholds**:
   - Conservative: 100/50/20cm (warning/slow/stop)
   - Standard: 100/50/10cm (default)
   - Aggressive: 50/25/5cm (fast operation)

---

## Next Steps

- See `ROC_GAPS_IMPLEMENTATION_COMPLETE.md` for architecture details
- See unit test files (when created) for usage examples
- See main ROC documentation for overall system architecture
