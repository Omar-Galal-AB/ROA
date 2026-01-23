"""
Emergency Stop System

Provides immediate velocity override for safety-critical situations.
Based on REMROC pattern of direct cmd_vel control bypassing Nav2.

Key Features:
- Immediate velocity zeroing
- Zone-based emergency triggers
- Gradual deceleration for non-critical stops
- Cancel of all active navigation goals
- Collision avoidance velocity injection
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from geometry_msgs.msg import Twist, Point
from std_msgs.msg import Bool

from typing import Dict, Optional, List, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time
import math
import threading


class StopReason(Enum):
    """Reasons for emergency stop"""
    NONE = "none"
    MANUAL = "manual"  # User-triggered
    PROXIMITY = "proximity"  # Too close to another robot
    COLLISION = "collision"  # Imminent collision detected
    PATH_CONFLICT = "path_conflict"  # Entering critical section
    SYSTEM_ERROR = "system_error"  # System malfunction
    ZONE_VIOLATION = "zone_violation"  # Entered restricted zone
    TIMEOUT = "timeout"  # Communication timeout


class StopLevel(Enum):
    """Severity levels for stops"""
    SOFT = "soft"  # Gradual deceleration
    HARD = "hard"  # Immediate zero velocity
    EMERGENCY = "emergency"  # Emergency stop with goal cancellation


@dataclass
class StopState:
    """State of emergency stop for a robot"""
    is_stopped: bool = False
    reason: StopReason = StopReason.NONE
    level: StopLevel = StopLevel.SOFT
    triggered_at: float = 0.0
    triggered_by: Optional[str] = None  # Other robot or system
    auto_resume: bool = False
    resume_after: float = 0.0  # Seconds until auto-resume


@dataclass
class EvasionVector:
    """Velocity vector for collision avoidance"""
    linear_x: float = 0.0
    linear_y: float = 0.0
    angular_z: float = 0.0
    magnitude: float = 0.0
    direction_degrees: float = 0.0


class EmergencyStopSystem:
    """
    Emergency stop and collision avoidance system.
    
    Provides direct velocity control for safety, bypassing Nav2.
    Can inject evasion velocities to avoid collisions.
    """
    
    # Configuration
    HARD_STOP_DECEL = 2.0  # m/s^2 for hard stops
    SOFT_STOP_DECEL = 0.5  # m/s^2 for soft stops
    EVASION_SPEED = 0.2  # m/s default evasion speed
    MIN_STOP_DISTANCE = 0.3  # meters - critical stop distance
    
    def __init__(self, robot_interface=None, logger=None):
        """
        Args:
            robot_interface: RobotInterface instance for cmd_vel access
            logger: ROS2 logger
        """
        self.robot_interface = robot_interface
        self.logger = logger
        
        # Per-robot stop states
        self.stop_states: Dict[str, StopState] = {}
        
        # Callbacks
        self.stop_callbacks: List[Callable] = []  # (robot_id, reason, level)
        self.resume_callbacks: List[Callable] = []  # (robot_id)
        
        # Lock
        self._lock = threading.RLock()
        
        # Background thread for auto-resume
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
    
    def register_robot(self, robot_id: str) -> None:
        """Register a robot for stop management"""
        with self._lock:
            if robot_id not in self.stop_states:
                self.stop_states[robot_id] = StopState()
    
    def unregister_robot(self, robot_id: str) -> None:
        """Unregister a robot"""
        with self._lock:
            if robot_id in self.stop_states:
                del self.stop_states[robot_id]
    
    def emergency_stop(self, robot_id: str, 
                       reason: StopReason = StopReason.MANUAL,
                       level: StopLevel = StopLevel.HARD,
                       triggered_by: Optional[str] = None,
                       auto_resume_after: Optional[float] = None) -> bool:
        """
        Trigger emergency stop for a robot.
        
        Args:
            robot_id: Robot to stop
            reason: Why the stop was triggered
            level: Severity level
            triggered_by: Source of stop (other robot, system)
            auto_resume_after: Seconds until automatic resume (None = manual resume)
            
        Returns:
            True if stop was triggered successfully
        """
        with self._lock:
            if robot_id not in self.stop_states:
                self.register_robot(robot_id)
            
            state = self.stop_states[robot_id]
            state.is_stopped = True
            state.reason = reason
            state.level = level
            state.triggered_at = time.time()
            state.triggered_by = triggered_by
            state.auto_resume = auto_resume_after is not None
            state.resume_after = auto_resume_after or 0.0
            
            # Send zero velocity
            success = self._send_stop_velocity(robot_id, level)
            
            # Cancel navigation goals for EMERGENCY level
            if level == StopLevel.EMERGENCY and self.robot_interface:
                if robot_id in self.robot_interface.action_clients:
                    self.robot_interface.action_clients[robot_id].cancel_all()
            
            # Notify callbacks
            for callback in self.stop_callbacks:
                try:
                    callback(robot_id, reason, level)
                except Exception as e:
                    if self.logger:
                        self.logger.error(f"Stop callback error: {e}")
            
            if self.logger:
                self.logger.warn(f"Emergency stop: {robot_id} - {reason.value} ({level.value})")
            
            return success
    
    def resume(self, robot_id: str) -> bool:
        """
        Resume robot from emergency stop.
        
        Args:
            robot_id: Robot to resume
            
        Returns:
            True if resumed successfully
        """
        with self._lock:
            if robot_id not in self.stop_states:
                return False
            
            state = self.stop_states[robot_id]
            
            if not state.is_stopped:
                return True  # Already running
            
            state.is_stopped = False
            state.reason = StopReason.NONE
            state.auto_resume = False
            
            # Notify callbacks
            for callback in self.resume_callbacks:
                try:
                    callback(robot_id)
                except Exception as e:
                    if self.logger:
                        self.logger.error(f"Resume callback error: {e}")
            
            if self.logger:
                self.logger.info(f"Resumed: {robot_id}")
            
            return True
    
    def emergency_stop_all(self, reason: StopReason = StopReason.SYSTEM_ERROR,
                           level: StopLevel = StopLevel.EMERGENCY) -> None:
        """Stop all registered robots"""
        with self._lock:
            for robot_id in list(self.stop_states.keys()):
                self.emergency_stop(robot_id, reason, level)
            
            if self.logger:
                self.logger.warn("EMERGENCY STOP ALL ROBOTS")
    
    def resume_all(self) -> None:
        """Resume all stopped robots"""
        with self._lock:
            for robot_id in list(self.stop_states.keys()):
                self.resume(robot_id)
    
    def _send_stop_velocity(self, robot_id: str, level: StopLevel) -> bool:
        """Send zero velocity command"""
        if not self.robot_interface:
            return False
        
        return self.robot_interface.send_velocity(robot_id, 0.0, 0.0, 0.0)
    
    def _monitor_loop(self) -> None:
        """Background thread for auto-resume monitoring"""
        while self._running:
            time.sleep(0.1)
            
            current_time = time.time()
            
            with self._lock:
                for robot_id, state in list(self.stop_states.items()):
                    if not state.is_stopped:
                        continue
                    
                    if not state.auto_resume:
                        continue
                    
                    elapsed = current_time - state.triggered_at
                    if elapsed >= state.resume_after:
                        # Time to resume
                        self.resume(robot_id)
    
    def is_stopped(self, robot_id: str) -> bool:
        """Check if robot is currently stopped"""
        with self._lock:
            if robot_id not in self.stop_states:
                return False
            return self.stop_states[robot_id].is_stopped
    
    def get_stop_state(self, robot_id: str) -> Optional[StopState]:
        """Get stop state for a robot"""
        with self._lock:
            return self.stop_states.get(robot_id)
    
    def get_all_stopped(self) -> List[str]:
        """Get list of all stopped robots"""
        with self._lock:
            return [rid for rid, state in self.stop_states.items() if state.is_stopped]
    
    # === Collision Avoidance ===
    
    def calculate_evasion(self, robot_id: str, 
                          robot_position: Tuple[float, float],
                          obstacles: List[Tuple[float, float, float]],
                          ) -> Optional[EvasionVector]:
        """
        Calculate evasion velocity to avoid obstacles.
        
        Args:
            robot_id: Robot to calculate for
            robot_position: Current (x, y) position
            obstacles: List of (x, y, radius) obstacles/other robots
            
        Returns:
            EvasionVector if evasion needed, None otherwise
        """
        if not obstacles:
            return None
        
        # Resultant repulsion vector
        repulsion_x = 0.0
        repulsion_y = 0.0
        
        for ox, oy, radius in obstacles:
            dx = robot_position[0] - ox
            dy = robot_position[1] - oy
            distance = math.sqrt(dx*dx + dy*dy)
            
            # Distance to obstacle edge
            clearance = distance - radius
            
            if clearance <= 0:
                # Inside obstacle - max repulsion
                if distance > 0.01:
                    scale = self.EVASION_SPEED * 2.0
                    repulsion_x += (dx / distance) * scale
                    repulsion_y += (dy / distance) * scale
            elif clearance < self.MIN_STOP_DISTANCE * 2:
                # Close - repulsion inversely proportional to distance
                scale = self.EVASION_SPEED * (1.0 - clearance / (self.MIN_STOP_DISTANCE * 2))
                if distance > 0.01:
                    repulsion_x += (dx / distance) * scale
                    repulsion_y += (dy / distance) * scale
        
        if abs(repulsion_x) < 0.01 and abs(repulsion_y) < 0.01:
            return None
        
        magnitude = math.sqrt(repulsion_x**2 + repulsion_y**2)
        direction = math.degrees(math.atan2(repulsion_y, repulsion_x))
        
        return EvasionVector(
            linear_x=repulsion_x,
            linear_y=repulsion_y,
            angular_z=0.0,
            magnitude=magnitude,
            direction_degrees=direction
        )
    
    def send_evasion(self, robot_id: str, evasion: EvasionVector) -> bool:
        """
        Send evasion velocity to robot.
        
        Args:
            robot_id: Target robot
            evasion: Calculated evasion vector
            
        Returns:
            True if sent successfully
        """
        if not self.robot_interface:
            return False
        
        return self.robot_interface.send_velocity(
            robot_id,
            evasion.linear_x,
            evasion.linear_y,
            evasion.angular_z
        )
    
    def proximity_check_and_stop(self, robot_id: str,
                                  robot_position: Tuple[float, float],
                                  other_positions: Dict[str, Tuple[float, float]],
                                  critical_distance: float = 0.3,
                                  warning_distance: float = 0.5) -> Optional[str]:
        """
        Check proximity to other robots and trigger stop if needed.
        
        Args:
            robot_id: Robot to check
            robot_position: Current position
            other_positions: Dict of other robot positions
            critical_distance: Distance for hard stop
            warning_distance: Distance for soft stop
            
        Returns:
            ID of closest robot if stop triggered, None otherwise
        """
        closest_robot = None
        closest_distance = float('inf')
        
        for other_id, (ox, oy) in other_positions.items():
            if other_id == robot_id:
                continue
            
            dx = robot_position[0] - ox
            dy = robot_position[1] - oy
            distance = math.sqrt(dx*dx + dy*dy)
            
            if distance < closest_distance:
                closest_distance = distance
                closest_robot = other_id
        
        if closest_distance <= critical_distance:
            self.emergency_stop(
                robot_id,
                StopReason.PROXIMITY,
                StopLevel.HARD,
                triggered_by=closest_robot
            )
            return closest_robot
        elif closest_distance <= warning_distance:
            # Could implement soft stop or warning here
            pass
        
        return None
    
    def register_stop_callback(self, callback: Callable) -> None:
        """Register callback for stop events: callback(robot_id, reason, level)"""
        self.stop_callbacks.append(callback)
    
    def register_resume_callback(self, callback: Callable) -> None:
        """Register callback for resume events: callback(robot_id)"""
        self.resume_callbacks.append(callback)
    
    def shutdown(self) -> None:
        """Shutdown the emergency stop system"""
        self._running = False
        if self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)


class ZoneBasedStop:
    """
    Zone-based emergency stop triggers.
    Stops robots entering restricted zones.
    """
    
    @dataclass
    class Zone:
        """Restricted zone definition"""
        zone_id: str
        center_x: float
        center_y: float
        radius: float  # Circular zone
        is_active: bool = True
        stop_level: StopLevel = StopLevel.HARD
        allowed_robots: List[str] = field(default_factory=list)  # Empty = none allowed
    
    def __init__(self, emergency_stop_system: EmergencyStopSystem):
        self.emergency_system = emergency_stop_system
        self.zones: Dict[str, 'ZoneBasedStop.Zone'] = {}
        self._lock = threading.Lock()
    
    def add_zone(self, zone_id: str, x: float, y: float, radius: float,
                 stop_level: StopLevel = StopLevel.HARD,
                 allowed_robots: Optional[List[str]] = None) -> None:
        """Add a restricted zone"""
        with self._lock:
            self.zones[zone_id] = self.Zone(
                zone_id=zone_id,
                center_x=x,
                center_y=y,
                radius=radius,
                stop_level=stop_level,
                allowed_robots=allowed_robots or []
            )
    
    def remove_zone(self, zone_id: str) -> None:
        """Remove a zone"""
        with self._lock:
            if zone_id in self.zones:
                del self.zones[zone_id]
    
    def set_zone_active(self, zone_id: str, active: bool) -> None:
        """Enable/disable a zone"""
        with self._lock:
            if zone_id in self.zones:
                self.zones[zone_id].is_active = active
    
    def check_zone_violation(self, robot_id: str, 
                              position: Tuple[float, float]) -> Optional[str]:
        """
        Check if robot violates any zone.
        
        Returns:
            Zone ID if violation, None otherwise
        """
        with self._lock:
            for zone_id, zone in self.zones.items():
                if not zone.is_active:
                    continue
                
                if robot_id in zone.allowed_robots:
                    continue
                
                dx = position[0] - zone.center_x
                dy = position[1] - zone.center_y
                distance = math.sqrt(dx*dx + dy*dy)
                
                if distance < zone.radius:
                    # Trigger stop
                    self.emergency_system.emergency_stop(
                        robot_id,
                        StopReason.ZONE_VIOLATION,
                        zone.stop_level,
                        triggered_by=zone_id
                    )
                    return zone_id
        
        return None
    
    def get_active_zones(self) -> List['ZoneBasedStop.Zone']:
        """Get all active zones"""
        with self._lock:
            return [z for z in self.zones.values() if z.is_active]
