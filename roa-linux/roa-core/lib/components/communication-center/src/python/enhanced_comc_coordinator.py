"""
Enhanced COMC (Communication Center) Coordinator

Integrates all the new coordination layers:
- Robot Interface Layer (action clients, cmd_vel)
- Path Conflict Detection
- Emergency Stop System
- Blocking Task Manager
- Enhanced State Tracker
- MAPF Solver Service

This is the main coordinator that orchestrates multi-robot communication
and coordination based on patterns from REMROC, Open-RMF, and Task Manager.

NOTE: This is standalone code - NOT integrated into ROA yet.
"""

import rclpy
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup, MutuallyExclusiveCallbackGroup
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy

from geometry_msgs.msg import Twist, Point, PoseStamped
from nav_msgs.msg import Odometry, Path
from std_msgs.msg import String, Bool
from sensor_msgs.msg import LaserScan

from typing import Dict, List, Optional, Tuple, Callable, Any
from dataclasses import dataclass
from enum import Enum
import time
import threading
import json

# Import our new modules
from robot_interface import RobotInterface, RobotState, RobotData
from path_conflict_detector import PathConflictDetector, CriticalSection, ConflictType
from emergency_stop import EmergencyStopSystem, StopReason, StopLevel, ZoneBasedStop
from blocking_task_manager import BlockingTaskManager, Task, TaskType, TaskPriority, Mission
from enhanced_state_tracker import (
    EnhancedStateTracker, OperationalState, CoordinationState, 
    HealthStatus, RobotFullState
)
from mapf_solver import MAPFService, MAPFSolution, TimedPath, PathNode


class CoordinationMode(Enum):
    """COMC coordination modes"""
    PASSIVE = "passive"  # Only monitor, don't intervene
    ADVISORY = "advisory"  # Suggest actions but don't enforce
    ACTIVE = "active"  # Actively coordinate robots
    EMERGENCY = "emergency"  # Emergency mode - stop all


@dataclass
class CoordinationConfig:
    """Configuration for the coordinator"""
    # Distances
    critical_distance: float = 0.3  # meters - hard stop
    caution_distance: float = 0.5  # meters - slow down
    warning_distance: float = 1.0  # meters - awareness
    
    # Timing
    coordination_rate: float = 10.0  # Hz
    state_publish_rate: float = 5.0  # Hz
    heartbeat_rate: float = 1.0  # Hz
    stale_timeout: float = 5.0  # seconds
    
    # Behavior
    enable_emergency_stop: bool = True
    enable_path_coordination: bool = True
    enable_mapf: bool = True
    default_robot_speed: float = 0.5  # m/s
    default_robot_radius: float = 0.3  # meters


class EnhancedCOMCCoordinator(Node):
    """
    Enhanced Communication Center Coordinator.
    
    Main coordinator node that integrates all coordination subsystems:
    - Monitors robot states and positions
    - Detects and resolves path conflicts
    - Manages emergency stops
    - Coordinates task execution
    - Provides MAPF path planning
    
    Based on REMROC coordinator pattern with enhancements from Open-RMF.
    """
    
    def __init__(self, config: Optional[CoordinationConfig] = None):
        super().__init__('enhanced_comc_coordinator')
        
        self.config = config or CoordinationConfig()
        self.mode = CoordinationMode.ACTIVE
        
        # === Initialize Subsystems ===
        
        # Robot Interface Layer (REMROC pattern)
        self.robot_interface = RobotInterface(self)
        
        # Path Conflict Detector
        self.conflict_detector = PathConflictDetector(self.get_logger())
        
        # Emergency Stop System
        self.emergency_stop = EmergencyStopSystem(
            self.robot_interface, 
            self.get_logger()
        )
        
        # Zone-based stops
        self.zone_manager = ZoneBasedStop(self.emergency_stop)
        
        # Blocking Task Manager
        self.task_manager = BlockingTaskManager(
            self.robot_interface,
            self.get_logger()
        )
        
        # Enhanced State Tracker
        self.state_tracker = EnhancedStateTracker(self.get_logger())
        
        # MAPF Solver
        self.mapf_service = MAPFService(self, use_cbs=False)  # Start with simple solver
        
        # === Callback Groups ===
        self.timer_callback_group = MutuallyExclusiveCallbackGroup()
        self.service_callback_group = ReentrantCallbackGroup()
        self.subscriber_callback_group = ReentrantCallbackGroup()
        
        # === QoS Profiles ===
        self.reliable_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )
        
        self.best_effort_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )
        
        # === Publishers ===
        
        # Fleet status
        self.fleet_status_pub = self.create_publisher(
            String, '/comc/fleet_status', 10
        )
        
        # Coordination commands
        self.coordination_cmd_pub = self.create_publisher(
            String, '/comc/coordination_commands', 10
        )
        
        # Emergency stop broadcast
        self.emergency_stop_pub = self.create_publisher(
            Bool, '/comc/emergency_stop', self.reliable_qos
        )
        
        # === Subscribers ===
        
        # Robot discovery/registration
        self.robot_discovery_sub = self.create_subscription(
            String, '/comc/robot_discovery',
            self._robot_discovery_callback,
            10,
            callback_group=self.subscriber_callback_group
        )
        
        # External emergency stop trigger
        self.external_estop_sub = self.create_subscription(
            Bool, '/comc/external_emergency_stop',
            self._external_estop_callback,
            self.reliable_qos,
            callback_group=self.subscriber_callback_group
        )
        
        # Path announcements from robots
        self.path_announce_sub = self.create_subscription(
            Path, '/comc/path_announcements',
            self._path_announcement_callback,
            10,
            callback_group=self.subscriber_callback_group
        )
        
        # === Timers ===
        
        # Main coordination loop
        self.coordination_timer = self.create_timer(
            1.0 / self.config.coordination_rate,
            self._coordination_tick,
            callback_group=self.timer_callback_group
        )
        
        # State publishing
        self.state_pub_timer = self.create_timer(
            1.0 / self.config.state_publish_rate,
            self._publish_fleet_status,
            callback_group=self.timer_callback_group
        )
        
        # === Register Callbacks ===
        
        # Emergency stop callbacks
        self.emergency_stop.register_stop_callback(self._on_robot_stopped)
        self.emergency_stop.register_resume_callback(self._on_robot_resumed)
        
        # State tracker callbacks
        self.state_tracker.register_state_change_callback(self._on_state_change)
        self.state_tracker.register_health_callback(self._on_health_change)
        
        # Task manager callbacks
        self.task_manager.register_task_callback(self._on_task_state_change)
        
        # === Internal State ===
        self._lock = threading.RLock()
        self._pending_conflicts: List[CriticalSection] = []
        self._robots_waiting: Dict[str, str] = {}  # robot_id -> waiting_for
        
        self.get_logger().info("Enhanced COMC Coordinator initialized")
    
    # === Robot Management ===
    
    def register_robot(self, robot_id: str, robot_type: str = "",
                       capabilities: Optional[List[str]] = None) -> None:
        """Register a robot with all subsystems"""
        self.get_logger().info(f"Registering robot: {robot_id}")
        
        # Register with all subsystems
        self.robot_interface.register_robot(robot_id)
        self.emergency_stop.register_robot(robot_id)
        self.task_manager.register_robot(robot_id)
        self.state_tracker.register_robot(robot_id, robot_type, capabilities)
        
        # Set initial state
        self.state_tracker.update_operational_state(robot_id, OperationalState.IDLE)
    
    def unregister_robot(self, robot_id: str) -> None:
        """Unregister a robot from all subsystems"""
        self.get_logger().info(f"Unregistering robot: {robot_id}")
        
        self.robot_interface.unregister_robot(robot_id)
        self.emergency_stop.unregister_robot(robot_id)
        self.task_manager.unregister_robot(robot_id)
        self.state_tracker.unregister_robot(robot_id)
        self.conflict_detector.clear_path(robot_id)
    
    def get_registered_robots(self) -> List[str]:
        """Get list of registered robot IDs"""
        return self.state_tracker.get_robot_ids()
    
    # === Main Coordination Loop ===
    
    def _coordination_tick(self) -> None:
        """Main coordination loop - runs at coordination_rate Hz"""
        if self.mode == CoordinationMode.PASSIVE:
            return
        
        try:
            self._update_robot_states()
            self._check_proximity()
            self._process_path_conflicts()
            self._process_waiting_robots()
        except Exception as e:
            self.get_logger().error(f"Coordination tick error: {e}")
    
    def _update_robot_states(self) -> None:
        """Update state tracker from robot interface"""
        for robot_id in self.robot_interface.get_robot_ids():
            data = self.robot_interface.get_robot_data(robot_id)
            if data is None:
                continue
            
            # Update position
            if data.position:
                import math
                yaw = 0.0
                if data.orientation:
                    # Extract yaw from quaternion
                    q = data.orientation
                    yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                                     1.0 - 2.0 * (q.y * q.y + q.z * q.z))
                
                self.state_tracker.update_position(
                    robot_id, data.position.x, data.position.y, yaw
                )
            
            # Update velocity
            if data.linear_velocity:
                self.state_tracker.update_velocity(
                    robot_id,
                    data.linear_velocity.x,
                    data.linear_velocity.y,
                    data.angular_velocity.z if data.angular_velocity else 0.0
                )
            
            # Update sensor state
            if data.laser_min_range < float('inf'):
                self.state_tracker.update_sensor_state(
                    robot_id,
                    laser_ok=True,
                    min_obstacle_distance=data.laser_min_range
                )
            
            # Heartbeat
            self.state_tracker.heartbeat(robot_id)
    
    def _check_proximity(self) -> None:
        """Check proximity between all robots"""
        if not self.config.enable_emergency_stop:
            return
        
        positions = self.state_tracker.get_all_positions()
        
        for robot_id, (x, y) in positions.items():
            # Check zone violations
            self.zone_manager.check_zone_violation(robot_id, (x, y))
            
            # Check proximity to other robots
            other_positions = {k: v for k, v in positions.items() if k != robot_id}
            
            triggered_by = self.emergency_stop.proximity_check_and_stop(
                robot_id, (x, y), other_positions,
                self.config.critical_distance,
                self.config.caution_distance
            )
            
            if triggered_by:
                self.get_logger().warn(
                    f"Proximity stop: {robot_id} too close to {triggered_by}"
                )
    
    def _process_path_conflicts(self) -> None:
        """Process and resolve path conflicts"""
        if not self.config.enable_path_coordination:
            return
        
        conflicts = self.conflict_detector.get_unresolved_conflicts()
        
        for conflict in conflicts:
            self._resolve_conflict(conflict)
    
    def _resolve_conflict(self, conflict: CriticalSection) -> None:
        """Resolve a path conflict between two robots"""
        robot1 = conflict.robot1_id
        robot2 = conflict.robot2_id
        
        # Determine which robot should wait
        waiting_robot = robot2 if conflict.priority_robot == robot1 else robot1
        priority_robot = conflict.priority_robot or robot1
        
        self.get_logger().info(
            f"Resolving conflict: {waiting_robot} yields to {priority_robot}"
        )
        
        # Update coordination state
        self.state_tracker.update_coordination_state(
            waiting_robot,
            CoordinationState.WAITING_AT_CRITICAL_SECTION,
            priority_robot
        )
        
        self._robots_waiting[waiting_robot] = priority_robot
        
        # If in active mode, actually stop the waiting robot
        if self.mode == CoordinationMode.ACTIVE:
            self.emergency_stop.emergency_stop(
                waiting_robot,
                StopReason.PATH_CONFLICT,
                StopLevel.SOFT,
                triggered_by=priority_robot,
                auto_resume_after=None  # Resume manually when clear
            )
    
    def _process_waiting_robots(self) -> None:
        """Check if waiting robots can resume"""
        positions = self.state_tracker.get_all_positions()
        
        for waiting_robot, waiting_for in list(self._robots_waiting.items()):
            if waiting_robot not in positions or waiting_for not in positions:
                continue
            
            waiting_pos = positions[waiting_robot]
            other_pos = positions[waiting_for]
            
            # Check if conflict is cleared
            should_wait, _ = self.conflict_detector.should_robot_wait(
                waiting_robot, waiting_pos
            )
            
            if not should_wait:
                # Clear to resume
                self.get_logger().info(f"Resuming {waiting_robot} - conflict cleared")
                
                self.emergency_stop.resume(waiting_robot)
                self.state_tracker.update_coordination_state(
                    waiting_robot, CoordinationState.NONE
                )
                del self._robots_waiting[waiting_robot]
    
    # === Task Coordination ===
    
    def navigate_robot(self, robot_id: str, x: float, y: float,
                       yaw: float = 0.0, blocking: bool = False,
                       priority: TaskPriority = TaskPriority.NORMAL) -> Tuple[bool, str]:
        """
        Navigate robot to a pose.
        
        Args:
            robot_id: Target robot
            x, y: Goal position
            yaw: Goal orientation
            blocking: Wait for completion
            priority: Task priority
            
        Returns:
            (success, message)
        """
        # Update state
        self.state_tracker.update_operational_state(robot_id, OperationalState.NAVIGATING)
        
        # Check for conflicts with current paths
        current_pos = self.state_tracker.get_state(robot_id)
        if current_pos:
            start = (current_pos.position.x, current_pos.position.y)
            goal = (x, y)
            
            # Use MAPF if enabled
            if self.config.enable_mapf:
                other_paths = {}
                for rid in self.state_tracker.get_robot_ids():
                    if rid != robot_id:
                        state = self.state_tracker.get_state(rid)
                        if state and state.current_path:
                            other_paths[rid] = [
                                (px, py, 0.0) for px, py in state.current_path
                            ]
                
                if other_paths:
                    timed_path = self.mapf_service.get_path_for_robot(
                        robot_id, start, goal, other_paths,
                        self.config.default_robot_speed,
                        self.config.default_robot_radius
                    )
                    
                    if timed_path:
                        # Register path with conflict detector
                        path_points = [(n.x, n.y) for n in timed_path]
                        self.conflict_detector.set_path(robot_id, path_points)
        
        # Submit task
        return self.task_manager.submit_navigate(
            robot_id, x, y, yaw, priority, blocking
        )
    
    def follow_path(self, robot_id: str, 
                    waypoints: List[Tuple[float, float]],
                    blocking: bool = False,
                    priority: TaskPriority = TaskPriority.NORMAL) -> Tuple[bool, str]:
        """
        Make robot follow a path.
        
        Args:
            robot_id: Target robot
            waypoints: Path waypoints
            blocking: Wait for completion
            priority: Task priority
            
        Returns:
            (success, message)
        """
        # Register path with conflict detector
        self.conflict_detector.set_path(robot_id, waypoints)
        
        # Check for conflicts
        conflicts = self.conflict_detector.get_conflicts_for_robot(robot_id)
        if conflicts:
            self.get_logger().warn(
                f"Path for {robot_id} has {len(conflicts)} conflicts"
            )
        
        # Update state
        self.state_tracker.update_operational_state(robot_id, OperationalState.NAVIGATING)
        self.state_tracker.update_path(robot_id, waypoints)
        
        # Submit task
        return self.task_manager.submit_follow_path(
            robot_id, waypoints, priority, blocking
        )
    
    def cancel_robot_tasks(self, robot_id: str) -> None:
        """Cancel all tasks for a robot"""
        self.task_manager.cancel_all_for_robot(robot_id)
        self.conflict_detector.clear_path(robot_id)
        self.state_tracker.update_operational_state(robot_id, OperationalState.IDLE)
        self.state_tracker.clear_task(robot_id)
    
    # === Emergency Control ===
    
    def emergency_stop_robot(self, robot_id: str,
                              reason: StopReason = StopReason.MANUAL) -> bool:
        """Emergency stop a specific robot"""
        return self.emergency_stop.emergency_stop(robot_id, reason, StopLevel.EMERGENCY)
    
    def emergency_stop_all(self, reason: StopReason = StopReason.SYSTEM_ERROR) -> None:
        """Emergency stop all robots"""
        self.mode = CoordinationMode.EMERGENCY
        self.emergency_stop.emergency_stop_all(reason, StopLevel.EMERGENCY)
        
        # Broadcast
        msg = Bool()
        msg.data = True
        self.emergency_stop_pub.publish(msg)
    
    def resume_robot(self, robot_id: str) -> bool:
        """Resume a stopped robot"""
        success = self.emergency_stop.resume(robot_id)
        if success:
            self.state_tracker.update_operational_state(robot_id, OperationalState.IDLE)
        return success
    
    def resume_all(self) -> None:
        """Resume all stopped robots"""
        self.mode = CoordinationMode.ACTIVE
        self.emergency_stop.resume_all()
        
        for robot_id in self.state_tracker.get_robot_ids():
            self.state_tracker.update_operational_state(robot_id, OperationalState.IDLE)
        
        # Broadcast
        msg = Bool()
        msg.data = False
        self.emergency_stop_pub.publish(msg)
    
    # === Zone Management ===
    
    def add_restricted_zone(self, zone_id: str, x: float, y: float,
                            radius: float, allowed_robots: Optional[List[str]] = None) -> None:
        """Add a restricted zone"""
        self.zone_manager.add_zone(
            zone_id, x, y, radius,
            StopLevel.HARD, allowed_robots
        )
        self.get_logger().info(f"Added restricted zone: {zone_id} at ({x}, {y}) r={radius}")
    
    def remove_restricted_zone(self, zone_id: str) -> None:
        """Remove a restricted zone"""
        self.zone_manager.remove_zone(zone_id)
    
    # === MAPF Planning ===
    
    def plan_fleet_paths(self, 
                         goals: Dict[str, Tuple[float, float]],
                         priorities: Optional[Dict[str, int]] = None) -> MAPFSolution:
        """
        Plan collision-free paths for multiple robots.
        
        Args:
            goals: Goal positions for each robot
            priorities: Robot priorities (higher = more important)
            
        Returns:
            MAPFSolution with paths
        """
        # Get current positions
        starts = {}
        for robot_id in goals:
            state = self.state_tracker.get_state(robot_id)
            if state:
                starts[robot_id] = (state.position.x, state.position.y)
            else:
                self.get_logger().warn(f"No position for {robot_id}")
        
        return self.mapf_service.solve_paths(
            starts, goals, priorities,
            self.config.default_robot_speed,
            self.config.default_robot_radius
        )
    
    # === Callbacks ===
    
    def _robot_discovery_callback(self, msg: String) -> None:
        """Handle robot discovery announcements"""
        try:
            data = json.loads(msg.data)
            robot_id = data.get('robot_id')
            robot_type = data.get('type', '')
            action = data.get('action', 'register')
            
            if action == 'register' and robot_id:
                self.register_robot(robot_id, robot_type)
            elif action == 'unregister' and robot_id:
                self.unregister_robot(robot_id)
        except Exception as e:
            self.get_logger().error(f"Robot discovery error: {e}")
    
    def _external_estop_callback(self, msg: Bool) -> None:
        """Handle external emergency stop"""
        if msg.data:
            self.get_logger().warn("External emergency stop triggered")
            self.emergency_stop_all(StopReason.MANUAL)
        else:
            self.get_logger().info("External emergency stop cleared")
            self.resume_all()
    
    def _path_announcement_callback(self, msg: Path) -> None:
        """Handle path announcements from robots"""
        if not msg.poses:
            return
        
        # Extract robot ID from frame_id (format: "robot_id/map")
        frame = msg.header.frame_id
        robot_id = frame.split('/')[0] if '/' in frame else frame
        
        # Convert to waypoints
        waypoints = [(pose.pose.position.x, pose.pose.position.y) 
                     for pose in msg.poses]
        
        # Register with conflict detector
        conflicts = self.conflict_detector.set_path(robot_id, waypoints)
        
        if conflicts:
            self.get_logger().info(
                f"Path from {robot_id} has {len(conflicts)} conflicts"
            )
    
    def _on_robot_stopped(self, robot_id: str, reason: StopReason, level: StopLevel) -> None:
        """Callback when robot is stopped"""
        self.state_tracker.update_operational_state(
            robot_id, OperationalState.EMERGENCY_STOP
        )
    
    def _on_robot_resumed(self, robot_id: str) -> None:
        """Callback when robot is resumed"""
        self.state_tracker.update_operational_state(
            robot_id, OperationalState.IDLE
        )
    
    def _on_state_change(self, event) -> None:
        """Callback for state changes"""
        # Log significant changes
        if event.field_name == 'operational_state':
            self.get_logger().debug(
                f"Robot {event.robot_id}: {event.old_value} -> {event.new_value}"
            )
    
    def _on_health_change(self, robot_id: str, health: HealthStatus) -> None:
        """Callback for health changes"""
        if health in [HealthStatus.UNHEALTHY, HealthStatus.CRITICAL]:
            self.get_logger().warn(f"Robot {robot_id} health: {health.value}")
    
    def _on_task_state_change(self, task: Task, state) -> None:
        """Callback for task state changes"""
        if state.value == 'completed':
            self.state_tracker.update_operational_state(
                task.robot_id, OperationalState.IDLE
            )
            self.state_tracker.clear_task(task.robot_id)
            self.conflict_detector.clear_path(task.robot_id)
    
    # === Status Publishing ===
    
    def _publish_fleet_status(self) -> None:
        """Publish fleet status"""
        summary = self.state_tracker.get_fleet_summary()
        
        # Add conflict info
        summary['active_conflicts'] = len(self.conflict_detector.get_unresolved_conflicts())
        summary['robots_waiting'] = len(self._robots_waiting)
        summary['mode'] = self.mode.value
        
        msg = String()
        msg.data = json.dumps(summary)
        self.fleet_status_pub.publish(msg)
    
    # === Mode Control ===
    
    def set_mode(self, mode: CoordinationMode) -> None:
        """Set coordination mode"""
        old_mode = self.mode
        self.mode = mode
        self.get_logger().info(f"Mode changed: {old_mode.value} -> {mode.value}")
    
    # === Lifecycle ===
    
    def shutdown(self) -> None:
        """Shutdown the coordinator"""
        self.get_logger().info("Shutting down COMC Coordinator")
        
        # Stop all robots safely
        if self.config.enable_emergency_stop:
            self.emergency_stop.emergency_stop_all(StopReason.SYSTEM_ERROR, StopLevel.SOFT)
        
        # Shutdown subsystems
        self.emergency_stop.shutdown()
        self.state_tracker.shutdown()
        self.task_manager.shutdown()


def main(args=None):
    """Main entry point"""
    rclpy.init(args=args)
    
    config = CoordinationConfig()
    coordinator = EnhancedCOMCCoordinator(config)
    
    try:
        rclpy.spin(coordinator)
    except KeyboardInterrupt:
        pass
    finally:
        coordinator.shutdown()
        coordinator.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
