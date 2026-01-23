"""
COMC Enhanced API

Clean API layer for the enhanced COMC coordinator.
Provides simple functions for common operations.

Usage:
    from comc_api import COMCApi
    
    api = COMCApi()
    api.register_robot('robot1')
    api.navigate('robot1', 5.0, 3.0)
    api.emergency_stop('robot1')

DIMC Integration (per DIMC-Requirement-COMC.md):
    api.set_robot_priority('robot1', 2)  # High priority
    api.set_monitoring_zone('assembly', bounds, enhanced=True)
    api.add_robot_to_fleet('robot1', 'fleet_1')
"""

from typing import Dict, List, Optional, Tuple, Callable, Any
from dataclasses import dataclass
from enum import Enum

# Import our modules
from robot_interface import RobotInterface, RobotState
from path_conflict_detector import PathConflictDetector, CriticalSection
from emergency_stop import EmergencyStopSystem, StopReason, StopLevel
from blocking_task_manager import BlockingTaskManager, Task, TaskPriority, Mission
from enhanced_state_tracker import (
    EnhancedStateTracker, OperationalState, CoordinationState, 
    HealthStatus, RobotFullState
)
from mapf_solver import MAPFService, MAPFSolution
from dimc_notifier import DIMCNotifier, RobotPriorityLevel


class COMCStatus(Enum):
    """COMC system status"""
    NOT_INITIALIZED = "not_initialized"
    READY = "ready"
    COORDINATING = "coordinating"
    EMERGENCY = "emergency"
    SHUTDOWN = "shutdown"


@dataclass
class RobotSummary:
    """Summary of a robot's state"""
    robot_id: str
    operational_state: str
    coordination_state: str
    health: str
    position_x: float
    position_y: float
    is_stopped: bool
    current_task: Optional[str]
    battery_percent: float


class COMCApi:
    """
    High-level API for COMC operations.
    
    Provides simplified access to:
    - Robot registration
    - Navigation commands
    - Emergency stop
    - Path planning
    - Fleet status
    """
    
    def __init__(self, node=None, logger=None):
        """
        Initialize COMC API.
        
        Args:
            node: ROS2 node (optional, for ROS integration)
            logger: Logger instance
        """
        self.node = node
        self.logger = logger
        self.status = COMCStatus.NOT_INITIALIZED
        
        # Initialize subsystems
        self.robot_interface = RobotInterface(node) if node else None
        self.conflict_detector = PathConflictDetector(logger)
        self.emergency_stop = EmergencyStopSystem(self.robot_interface, logger)
        self.task_manager = BlockingTaskManager(self.robot_interface, logger)
        self.state_tracker = EnhancedStateTracker(logger)
        self.mapf_service = MAPFService(node) if node else None
        
        # DIMC Integration (per DIMC-Requirement-COMC.md)
        self.dimc_notifier = DIMCNotifier(node, logger)
        
        self.status = COMCStatus.READY
    
    # === Robot Management ===
    
    def register_robot(self, robot_id: str, robot_type: str = "", 
                        fleet_id: Optional[str] = None) -> bool:
        """
        Register a robot with COMC.
        
        Args:
            robot_id: Unique robot identifier
            robot_type: Type of robot (optional)
            fleet_id: Fleet to add robot to (optional)
            
        Returns:
            True if registered successfully
        """
        try:
            if self.robot_interface:
                self.robot_interface.register_robot(robot_id)
            self.emergency_stop.register_robot(robot_id)
            self.task_manager.register_robot(robot_id)
            self.state_tracker.register_robot(robot_id, robot_type)
            
            # Set initial DIMC priority to IDLE (per DIMC-Requirement-COMC.md)
            self.dimc_notifier.set_robot_priority(
                robot_id, RobotPriorityLevel.IDLE.value, reason="registration"
            )
            
            # Add to fleet if specified
            if fleet_id:
                self.dimc_notifier.on_robot_added_to_fleet(robot_id, fleet_id)
            
            if self.logger:
                self.logger.info(f"Registered robot: {robot_id}")
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to register {robot_id}: {e}")
            return False
    
    def unregister_robot(self, robot_id: str) -> bool:
        """Unregister a robot from COMC"""
        try:
            if self.robot_interface:
                self.robot_interface.unregister_robot(robot_id)
            self.emergency_stop.unregister_robot(robot_id)
            self.task_manager.unregister_robot(robot_id)
            self.state_tracker.unregister_robot(robot_id)
            self.conflict_detector.clear_path(robot_id)
            
            # Remove from any fleet (per DIMC-Requirement-COMC.md)
            if self.dimc_notifier.is_in_fleet(robot_id):
                self.dimc_notifier.on_robot_removed_from_fleet(robot_id)
            
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to unregister {robot_id}: {e}")
            return False
    
    def get_robots(self) -> List[str]:
        """Get list of registered robot IDs"""
        return self.state_tracker.get_robot_ids()
    
    def get_robot_status(self, robot_id: str) -> Optional[RobotSummary]:
        """Get summary of robot's current state"""
        state = self.state_tracker.get_state(robot_id)
        if not state:
            return None
        
        return RobotSummary(
            robot_id=robot_id,
            operational_state=state.operational_state.value,
            coordination_state=state.coordination_state.value,
            health=state.health_status.value,
            position_x=state.position.x,
            position_y=state.position.y,
            is_stopped=self.emergency_stop.is_stopped(robot_id),
            current_task=state.task.task_id,
            battery_percent=state.battery.percentage
        )
    
    # === Navigation ===
    
    def navigate(self, robot_id: str, x: float, y: float, 
                 yaw: float = 0.0, blocking: bool = False) -> Tuple[bool, str]:
        """
        Navigate robot to position.
        
        Args:
            robot_id: Target robot
            x, y: Goal position
            yaw: Goal orientation (radians)
            blocking: Wait for completion
            
        Returns:
            (success, message)
        """
        # Update state
        self.state_tracker.update_operational_state(robot_id, OperationalState.NAVIGATING)
        
        # Submit task
        return self.task_manager.submit_navigate(
            robot_id, x, y, yaw, TaskPriority.NORMAL, blocking
        )
    
    def navigate_priority(self, robot_id: str, x: float, y: float,
                          priority: str = "normal") -> Tuple[bool, str]:
        """
        Navigate with specified priority.
        
        Args:
            robot_id: Target robot
            x, y: Goal position
            priority: "low", "normal", "high", "urgent"
            
        Returns:
            (success, message)
        """
        priority_map = {
            "low": TaskPriority.LOW,
            "normal": TaskPriority.NORMAL,
            "high": TaskPriority.HIGH,
            "urgent": TaskPriority.URGENT
        }
        task_priority = priority_map.get(priority, TaskPriority.NORMAL)
        
        # Notify DIMC of priority for optimized sensing (per DIMC-Requirement-COMC.md)
        dimc_priority_map = {
            "low": RobotPriorityLevel.LOW.value,
            "normal": RobotPriorityLevel.NORMAL.value,
            "high": RobotPriorityLevel.HIGH.value,
            "urgent": RobotPriorityLevel.CRITICAL.value
        }
        self.dimc_notifier.set_robot_priority(
            robot_id, 
            dimc_priority_map.get(priority, RobotPriorityLevel.NORMAL.value),
            reason=f"navigation_{priority}"
        )
        
        self.state_tracker.update_operational_state(robot_id, OperationalState.NAVIGATING)
        return self.task_manager.submit_navigate(
            robot_id, x, y, 0.0, task_priority, blocking=False
        )
    
    def follow_path(self, robot_id: str, 
                    waypoints: List[Tuple[float, float]],
                    blocking: bool = False) -> Tuple[bool, str]:
        """
        Make robot follow a path.
        
        Args:
            robot_id: Target robot
            waypoints: List of (x, y) positions
            blocking: Wait for completion
            
        Returns:
            (success, message)
        """
        # Register path for conflict detection
        self.conflict_detector.set_path(robot_id, waypoints)
        
        self.state_tracker.update_operational_state(robot_id, OperationalState.NAVIGATING)
        self.state_tracker.update_path(robot_id, waypoints)
        
        return self.task_manager.submit_follow_path(
            robot_id, waypoints, TaskPriority.NORMAL, blocking
        )
    
    def cancel_navigation(self, robot_id: str) -> bool:
        """Cancel robot's current navigation"""
        self.task_manager.cancel_all_for_robot(robot_id)
        self.conflict_detector.clear_path(robot_id)
        self.state_tracker.update_operational_state(robot_id, OperationalState.IDLE)
        
        # Notify DIMC to reduce sensing priority (per DIMC-Requirement-COMC.md)
        self.dimc_notifier.set_robot_priority(
            robot_id, RobotPriorityLevel.IDLE.value, reason="navigation_cancelled"
        )
        return True
    
    # === Emergency Stop ===
    
    def stop(self, robot_id: str, reason: str = "manual") -> bool:
        """
        Stop a robot.
        
        Args:
            robot_id: Target robot
            reason: Reason for stop
            
        Returns:
            True if stopped
        """
        reason_map = {
            "manual": StopReason.MANUAL,
            "proximity": StopReason.PROXIMITY,
            "collision": StopReason.COLLISION,
            "error": StopReason.SYSTEM_ERROR
        }
        stop_reason = reason_map.get(reason, StopReason.MANUAL)
        
        return self.emergency_stop.emergency_stop(robot_id, stop_reason, StopLevel.HARD)
    
    def stop_all(self) -> None:
        """Stop all robots"""
        self.status = COMCStatus.EMERGENCY
        self.emergency_stop.emergency_stop_all(StopReason.MANUAL, StopLevel.EMERGENCY)
    
    def resume(self, robot_id: str) -> bool:
        """Resume a stopped robot"""
        success = self.emergency_stop.resume(robot_id)
        if success:
            self.state_tracker.update_operational_state(robot_id, OperationalState.IDLE)
        return success
    
    def resume_all(self) -> None:
        """Resume all robots"""
        self.emergency_stop.resume_all()
        for robot_id in self.state_tracker.get_robot_ids():
            self.state_tracker.update_operational_state(robot_id, OperationalState.IDLE)
        self.status = COMCStatus.READY
    
    def is_stopped(self, robot_id: str) -> bool:
        """Check if robot is stopped"""
        return self.emergency_stop.is_stopped(robot_id)
    
    # === Path Coordination ===
    
    def check_path_conflicts(self, robot_id: str, 
                              path: List[Tuple[float, float]]) -> List[str]:
        """
        Check if path conflicts with other robots.
        
        Args:
            robot_id: Robot to check
            path: Proposed path
            
        Returns:
            List of robot IDs with conflicts
        """
        conflicts = self.conflict_detector.set_path(robot_id, path)
        
        conflicting_robots = set()
        for cs in conflicts:
            if cs.robot1_id != robot_id:
                conflicting_robots.add(cs.robot1_id)
            if cs.robot2_id != robot_id:
                conflicting_robots.add(cs.robot2_id)
        
        return list(conflicting_robots)
    
    def get_conflicts(self) -> List[Tuple[str, str, str]]:
        """
        Get all active conflicts.
        
        Returns:
            List of (robot1, robot2, conflict_type)
        """
        conflicts = self.conflict_detector.get_all_conflicts()
        return [
            (cs.robot1_id, cs.robot2_id, cs.conflict_type.value)
            for cs in conflicts
        ]
    
    # === MAPF Planning ===
    
    def plan_paths(self, goals: Dict[str, Tuple[float, float]]) -> Optional[Dict[str, List[Tuple[float, float, float]]]]:
        """
        Plan collision-free paths for multiple robots.
        
        Args:
            goals: Dict of robot_id -> (x, y) goals
            
        Returns:
            Dict of robot_id -> [(x, y, time), ...] or None if failed
        """
        if not self.mapf_service:
            return None
        
        # Get current positions
        starts = {}
        for robot_id in goals:
            state = self.state_tracker.get_state(robot_id)
            if state:
                starts[robot_id] = (state.position.x, state.position.y)
        
        if len(starts) != len(goals):
            return None
        
        solution = self.mapf_service.solve_paths(starts, goals)
        
        if not solution.success:
            return None
        
        result = {}
        for robot_id, timed_path in solution.paths.items():
            result[robot_id] = [
                (n.x, n.y, n.time) for n in timed_path.waypoints
            ]
        
        return result
    
    # === Fleet Status ===
    
    def get_fleet_summary(self) -> Dict[str, Any]:
        """Get summary of fleet status"""
        summary = self.state_tracker.get_fleet_summary()
        summary['comc_status'] = self.status.value
        summary['active_conflicts'] = len(self.conflict_detector.get_unresolved_conflicts())
        return summary
    
    def get_all_positions(self) -> Dict[str, Tuple[float, float]]:
        """Get positions of all robots"""
        return self.state_tracker.get_all_positions()
    
    def get_idle_robots(self) -> List[str]:
        """Get robots that are idle"""
        return self.state_tracker.get_idle_robots()
    
    def get_navigating_robots(self) -> List[str]:
        """Get robots that are navigating"""
        return self.state_tracker.get_navigating_robots()
    
    def get_unhealthy_robots(self) -> List[str]:
        """Get robots with health issues"""
        result = []
        for robot_id in self.state_tracker.get_robot_ids():
            state = self.state_tracker.get_state(robot_id)
            if state and state.health_status in [HealthStatus.UNHEALTHY, HealthStatus.CRITICAL]:
                result.append(robot_id)
        return result
    
    # === State Updates (for integration) ===
    
    def update_position(self, robot_id: str, x: float, y: float, yaw: float = 0.0) -> None:
        """Update robot position (call from odometry subscriber)"""
        self.state_tracker.update_position(robot_id, x, y, yaw)
    
    def update_velocity(self, robot_id: str, linear_x: float, 
                        linear_y: float = 0.0, angular_z: float = 0.0) -> None:
        """Update robot velocity"""
        self.state_tracker.update_velocity(robot_id, linear_x, linear_y, angular_z)
    
    def update_battery(self, robot_id: str, percentage: float, 
                       is_charging: bool = False) -> None:
        """Update robot battery state"""
        self.state_tracker.update_battery(robot_id, percentage, is_charging)
    
    def heartbeat(self, robot_id: str) -> None:
        """Send heartbeat for robot"""
        self.state_tracker.heartbeat(robot_id)
    
    # === DIMC Integration (per DIMC-Requirement-COMC.md) ===
    
    def set_robot_priority(self, robot_id: str, priority: int, 
                           reason: str = "") -> bool:
        """
        Set robot priority for DIMC sensing optimization.
        
        Args:
            robot_id: Robot identifier
            priority: Priority level (1=critical, 10=minimal)
            reason: Optional reason for priority change
            
        Returns:
            True if notification sent successfully
        """
        return self.dimc_notifier.set_robot_priority(robot_id, priority, reason)
    
    def set_robot_priority_from_task(self, robot_id: str, task_type: str) -> bool:
        """
        Set robot priority based on task type.
        
        Args:
            robot_id: Robot identifier
            task_type: Type of task (emergency, navigation, idle, etc.)
            
        Returns:
            True if notification sent successfully
        """
        return self.dimc_notifier.set_robot_priority_from_task(robot_id, task_type)
    
    def set_monitoring_zone(self, zone_id: str, bounds: Dict[str, float],
                            enhanced: bool = False, reason: str = "") -> bool:
        """
        Configure a monitoring zone for DIMC.
        
        Enhanced zones get higher sensing frequency.
        
        Args:
            zone_id: Unique zone identifier
            bounds: Zone boundaries dict with min_x, max_x, min_y, max_y, min_z, max_z
            enhanced: If True, enable enhanced monitoring
            reason: Optional reason for zone configuration
            
        Returns:
            True if zone configured successfully
        """
        return self.dimc_notifier.set_monitoring_zone(zone_id, bounds, enhanced, reason)
    
    def add_robot_to_fleet(self, robot_id: str, fleet_id: str) -> bool:
        """
        Add robot to a coordinated fleet.
        
        Enables DIMC fleet-wide position publishing and inter-robot distance tracking.
        
        Args:
            robot_id: Robot to add
            fleet_id: Fleet identifier
            
        Returns:
            True if notification sent successfully
        """
        return self.dimc_notifier.on_robot_added_to_fleet(robot_id, fleet_id)
    
    def remove_robot_from_fleet(self, robot_id: str) -> bool:
        """
        Remove robot from its coordinated fleet.
        
        Args:
            robot_id: Robot to remove
            
        Returns:
            True if notification sent successfully
        """
        return self.dimc_notifier.on_robot_removed_from_fleet(robot_id)
    
    def form_fleet(self, fleet_id: str, robot_ids: List[str]) -> int:
        """
        Form a new fleet with multiple robots.
        
        Args:
            fleet_id: Fleet identifier
            robot_ids: List of robots to add to fleet
            
        Returns:
            Number of robots successfully added
        """
        return self.dimc_notifier.form_fleet(fleet_id, robot_ids)
    
    def disband_fleet(self, fleet_id: str) -> int:
        """
        Disband a fleet, removing all robots.
        
        Args:
            fleet_id: Fleet to disband
            
        Returns:
            Number of robots removed
        """
        return self.dimc_notifier.disband_fleet(fleet_id)
    
    def configure_workspace_zones(self, zones: List[Dict]) -> int:
        """
        Configure multiple monitoring zones at once.
        
        Args:
            zones: List of zone configurations
            
        Returns:
            Number of zones successfully configured
        """
        return self.dimc_notifier.configure_workspace(zones)
    
    # === Lifecycle ===
    
    def shutdown(self) -> None:
        """Shutdown COMC API"""
        self.status = COMCStatus.SHUTDOWN
        
        # Safe shutdown
        self.emergency_stop.emergency_stop_all(StopReason.SYSTEM_ERROR, StopLevel.SOFT)
        
        self.emergency_stop.shutdown()
        self.state_tracker.shutdown()
        self.task_manager.shutdown()
        self.dimc_notifier.shutdown()
