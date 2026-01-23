"""
DIMC Notifier - COMC → DIMC Integration

Handles outbound notifications from COMC to DIMC for:
- Robot priority changes
- Monitoring zone configurations
- Fleet membership updates

This enables DIMC to optimize its sensing based on COMC coordination state.

Reference: docs/DIMC-Requirement-COMC.md
"""

import json
import time
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum

try:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String
    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False


class RobotPriorityLevel(Enum):
    """
    Priority levels for DIMC sensing optimization.
    Lower number = higher priority = more sensing resources.
    """
    CRITICAL = 1      # Emergency tasks, highest sensing frequency
    HIGH = 2          # Payload transport, above-normal sensing
    NORMAL = 3        # Standard navigation
    LOW = 5           # Background tasks
    PATROL = 7        # Patrol/monitoring
    IDLE = 8          # Idle robots, minimal sensing
    MINIMAL = 10      # Minimal tracking


@dataclass
class MonitoringZone:
    """Zone configuration for DIMC"""
    zone_id: str
    bounds: Dict[str, float]  # min_x, max_x, min_y, max_y, min_z, max_z
    enhanced: bool = False
    reason: str = ""
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'zone_id': self.zone_id,
            'bounds': self.bounds,
            'enhanced': self.enhanced,
            'reason': self.reason,
            'timestamp': self.timestamp
        }
    
    def is_valid(self) -> bool:
        """Validate zone bounds"""
        required = ['min_x', 'max_x', 'min_y', 'max_y', 'min_z', 'max_z']
        if not all(k in self.bounds for k in required):
            return False
        if self.bounds['min_x'] >= self.bounds['max_x']:
            return False
        if self.bounds['min_y'] >= self.bounds['max_y']:
            return False
        if self.bounds['min_z'] >= self.bounds['max_z']:
            return False
        return True


@dataclass
class FleetMembership:
    """Fleet membership record"""
    robot_id: str
    fleet_id: str
    joined_at: float = field(default_factory=time.time)


class DIMCNotifier:
    """
    Notifies DIMC of coordination-relevant changes from COMC.
    
    Provides the following APIs (per DIMC-Requirement-COMC.md):
    - set_robot_priority(robot_id, priority) → Adjust DIMC sensing rate
    - set_monitoring_zone(zone_id, bounds, enhanced) → Configure enhanced zones
    - on_robot_added_to_fleet(robot_id, fleet_id) → Enable fleet tracking
    - on_robot_removed_from_fleet(robot_id) → Disable fleet tracking
    """
    
    def __init__(self, node=None, logger=None, use_direct_api: bool = False):
        """
        Initialize DIMC notifier.
        
        Args:
            node: ROS2 node (for topic-based communication)
            logger: Logger instance
            use_direct_api: If True, use direct DIMC API calls instead of ROS2
        """
        self.node = node
        self.logger = logger
        self.use_direct_api = use_direct_api
        
        # State tracking
        self.robot_priorities: Dict[str, int] = {}
        self.monitoring_zones: Dict[str, MonitoringZone] = {}
        self.fleet_memberships: Dict[str, FleetMembership] = {}  # robot_id -> membership
        
        # Direct API reference (when not using ROS2)
        self._dimc_api = None
        
        # ROS2 publishers
        self._priority_pub = None
        self._zone_pub = None
        self._fleet_pub = None
        
        if ROS2_AVAILABLE and node:
            self._init_ros2_publishers()
    
    def _init_ros2_publishers(self):
        """Initialize ROS2 publishers for DIMC communication"""
        self._priority_pub = self.node.create_publisher(
            String,
            '/comc/robot_priorities',
            10
        )
        
        self._zone_pub = self.node.create_publisher(
            String,
            '/comc/monitoring_zones',
            10
        )
        
        self._fleet_pub = self.node.create_publisher(
            String,
            '/comc/fleet_membership',
            10
        )
        
        if self.logger:
            self.logger.info("DIMC notifier ROS2 publishers initialized")
    
    def set_dimc_api(self, dimc_api):
        """
        Set direct DIMC API reference for non-ROS2 communication.
        
        Args:
            dimc_api: DIMC API instance (from dimc_api.py)
        """
        self._dimc_api = dimc_api
        self.use_direct_api = True
    
    # =========================================================================
    # Robot Priority API (DIMC-Requirement-COMC.md Section 1)
    # =========================================================================
    
    def set_robot_priority(self, robot_id: str, priority: int, 
                           reason: str = "") -> bool:
        """
        Set robot priority for DIMC sensing optimization.
        
        Higher priority robots get more sensing resources (higher frequency).
        
        Args:
            robot_id: Robot identifier
            priority: Priority level (1=critical, 10=minimal)
                      1-2: Critical/High - 60Hz sensing
                      3-4: Normal - 30Hz sensing
                      5-6: Low - 20Hz sensing
                      7+: Minimal - 10Hz sensing
            reason: Optional reason for priority change
            
        Returns:
            True if notification sent successfully
        """
        # Validate priority range
        priority = max(1, min(10, priority))
        
        # Store locally
        old_priority = self.robot_priorities.get(robot_id)
        self.robot_priorities[robot_id] = priority
        
        if self.logger and old_priority != priority:
            self.logger.info(f"Robot {robot_id} priority: {old_priority} → {priority} ({reason})")
        
        # Notify DIMC
        return self._notify_priority_change(robot_id, priority, reason)
    
    def set_robot_priority_from_task(self, robot_id: str, task_type: str) -> bool:
        """
        Set robot priority based on task type.
        
        Convenience method that maps task types to priority levels.
        
        Args:
            robot_id: Robot identifier
            task_type: Type of task being executed
            
        Returns:
            True if notification sent successfully
        """
        priority_map = {
            'emergency': RobotPriorityLevel.CRITICAL.value,
            'emergency_delivery': RobotPriorityLevel.CRITICAL.value,
            'carrying_payload': RobotPriorityLevel.HIGH.value,
            'payload_transport': RobotPriorityLevel.HIGH.value,
            'navigation': RobotPriorityLevel.NORMAL.value,
            'pick_place': RobotPriorityLevel.NORMAL.value,
            'patrol': RobotPriorityLevel.PATROL.value,
            'monitoring': RobotPriorityLevel.PATROL.value,
            'idle': RobotPriorityLevel.IDLE.value,
            'charging': RobotPriorityLevel.MINIMAL.value,
        }
        
        priority = priority_map.get(task_type.lower(), RobotPriorityLevel.NORMAL.value)
        return self.set_robot_priority(robot_id, priority, reason=task_type)
    
    def _notify_priority_change(self, robot_id: str, priority: int, 
                                 reason: str) -> bool:
        """Send priority change notification to DIMC"""
        if self.use_direct_api and self._dimc_api:
            try:
                self._dimc_api.set_robot_priority(robot_id, priority)
                return True
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Direct DIMC API call failed: {e}")
                return False
        
        if self._priority_pub:
            msg = String()
            msg.data = json.dumps({
                'robot_id': robot_id,
                'priority': priority,
                'reason': reason,
                'timestamp': time.time()
            })
            self._priority_pub.publish(msg)
            return True
        
        return False
    
    def get_robot_priority(self, robot_id: str) -> int:
        """Get current priority for a robot"""
        return self.robot_priorities.get(robot_id, RobotPriorityLevel.NORMAL.value)
    
    def publish_all_priorities(self) -> bool:
        """Publish all robot priorities in a single message"""
        if self._priority_pub:
            msg = String()
            msg.data = json.dumps({
                'priorities': self.robot_priorities,
                'timestamp': time.time()
            })
            self._priority_pub.publish(msg)
            return True
        return False
    
    # =========================================================================
    # Monitoring Zones API (DIMC-Requirement-COMC.md Section 2)
    # =========================================================================
    
    def set_monitoring_zone(self, zone_id: str, bounds: Dict[str, float],
                            enhanced: bool = False, reason: str = "") -> bool:
        """
        Configure a monitoring zone for DIMC.
        
        Enhanced zones get higher sensing frequency and obstacle detection priority.
        
        Args:
            zone_id: Unique zone identifier
            bounds: Zone boundaries:
                    {'min_x': 0, 'max_x': 10, 'min_y': 0, 'max_y': 10, 'min_z': 0, 'max_z': 3}
            enhanced: If True, enable enhanced monitoring (more frequent sensing)
            reason: Optional reason for zone configuration
            
        Returns:
            True if zone configured successfully
        """
        zone = MonitoringZone(
            zone_id=zone_id,
            bounds=bounds,
            enhanced=enhanced,
            reason=reason
        )
        
        if not zone.is_valid():
            if self.logger:
                self.logger.error(f"Invalid zone bounds for {zone_id}")
            return False
        
        self.monitoring_zones[zone_id] = zone
        
        if self.logger:
            mode = "enhanced" if enhanced else "normal"
            self.logger.info(f"Zone {zone_id} configured as {mode}: {reason}")
        
        return self._notify_zone_change(zone)
    
    def remove_monitoring_zone(self, zone_id: str) -> bool:
        """Remove a monitoring zone"""
        if zone_id in self.monitoring_zones:
            del self.monitoring_zones[zone_id]
            if self.logger:
                self.logger.info(f"Zone {zone_id} removed")
            return self._notify_zone_removed(zone_id)
        return False
    
    def _notify_zone_change(self, zone: MonitoringZone) -> bool:
        """Send zone configuration to DIMC"""
        if self.use_direct_api and self._dimc_api:
            try:
                self._dimc_api.set_monitoring_zone(
                    zone.zone_id,
                    zone.bounds,
                    zone.enhanced
                )
                return True
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Direct DIMC API call failed: {e}")
                return False
        
        if self._zone_pub:
            msg = String()
            msg.data = json.dumps(zone.to_dict())
            self._zone_pub.publish(msg)
            return True
        
        return False
    
    def _notify_zone_removed(self, zone_id: str) -> bool:
        """Notify DIMC that zone was removed"""
        if self._zone_pub:
            msg = String()
            msg.data = json.dumps({
                'zone_id': zone_id,
                'action': 'removed',
                'timestamp': time.time()
            })
            self._zone_pub.publish(msg)
            return True
        return False
    
    def publish_all_zones(self) -> bool:
        """Publish all zones in a single message"""
        if self._zone_pub:
            msg = String()
            msg.data = json.dumps({
                'zones': [z.to_dict() for z in self.monitoring_zones.values()],
                'timestamp': time.time()
            })
            self._zone_pub.publish(msg)
            return True
        return False
    
    # =========================================================================
    # Fleet Membership API (DIMC-Requirement-COMC.md Section 3)
    # =========================================================================
    
    def on_robot_added_to_fleet(self, robot_id: str, fleet_id: str) -> bool:
        """
        Notify DIMC that a robot joined a coordinated fleet.
        
        This enables DIMC to:
        - Include robot in fleet-wide position publishing
        - Calculate inter-robot distances for fleet members
        - Generate proximity alerts between fleet members
        
        Args:
            robot_id: Robot joining the fleet
            fleet_id: Fleet identifier
            
        Returns:
            True if notification sent successfully
        """
        membership = FleetMembership(robot_id=robot_id, fleet_id=fleet_id)
        self.fleet_memberships[robot_id] = membership
        
        if self.logger:
            self.logger.info(f"Robot {robot_id} added to fleet {fleet_id}")
        
        return self._notify_fleet_change(robot_id, fleet_id, 'added')
    
    def on_robot_removed_from_fleet(self, robot_id: str) -> bool:
        """
        Notify DIMC that a robot left its coordinated fleet.
        
        Args:
            robot_id: Robot leaving the fleet
            
        Returns:
            True if notification sent successfully
        """
        fleet_id = None
        if robot_id in self.fleet_memberships:
            fleet_id = self.fleet_memberships[robot_id].fleet_id
            del self.fleet_memberships[robot_id]
        
        if self.logger:
            self.logger.info(f"Robot {robot_id} removed from fleet {fleet_id or 'unknown'}")
        
        return self._notify_fleet_change(robot_id, fleet_id, 'removed')
    
    def _notify_fleet_change(self, robot_id: str, fleet_id: Optional[str],
                             action: str) -> bool:
        """Send fleet membership change to DIMC"""
        if self.use_direct_api and self._dimc_api:
            try:
                if action == 'added':
                    self._dimc_api.on_robot_added_to_fleet(robot_id, fleet_id)
                else:
                    self._dimc_api.on_robot_removed_from_fleet(robot_id)
                return True
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Direct DIMC API call failed: {e}")
                return False
        
        if self._fleet_pub:
            msg = String()
            msg.data = json.dumps({
                'robot_id': robot_id,
                'fleet_id': fleet_id,
                'action': action,
                'timestamp': time.time()
            })
            self._fleet_pub.publish(msg)
            return True
        
        return False
    
    def get_fleet_robots(self, fleet_id: str) -> List[str]:
        """Get all robots in a specific fleet"""
        return [
            robot_id for robot_id, membership in self.fleet_memberships.items()
            if membership.fleet_id == fleet_id
        ]
    
    def get_all_fleets(self) -> Dict[str, List[str]]:
        """Get all fleets with their member robots"""
        fleets: Dict[str, List[str]] = {}
        for robot_id, membership in self.fleet_memberships.items():
            if membership.fleet_id not in fleets:
                fleets[membership.fleet_id] = []
            fleets[membership.fleet_id].append(robot_id)
        return fleets
    
    def is_in_fleet(self, robot_id: str) -> bool:
        """Check if robot is in any coordinated fleet"""
        return robot_id in self.fleet_memberships
    
    # =========================================================================
    # Convenience Methods
    # =========================================================================
    
    def configure_workspace(self, zones: List[Dict]) -> int:
        """
        Configure multiple monitoring zones at once.
        
        Args:
            zones: List of zone configurations:
                   [{'zone_id': 'area1', 'bounds': {...}, 'enhanced': True}, ...]
        
        Returns:
            Number of zones successfully configured
        """
        count = 0
        for zone_config in zones:
            if self.set_monitoring_zone(
                zone_id=zone_config['zone_id'],
                bounds=zone_config['bounds'],
                enhanced=zone_config.get('enhanced', False),
                reason=zone_config.get('reason', '')
            ):
                count += 1
        return count
    
    def form_fleet(self, fleet_id: str, robot_ids: List[str]) -> int:
        """
        Form a new fleet with multiple robots.
        
        Args:
            fleet_id: Fleet identifier
            robot_ids: List of robots to add to fleet
            
        Returns:
            Number of robots successfully added
        """
        count = 0
        for robot_id in robot_ids:
            if self.on_robot_added_to_fleet(robot_id, fleet_id):
                count += 1
        return count
    
    def disband_fleet(self, fleet_id: str) -> int:
        """
        Disband a fleet, removing all robots.
        
        Args:
            fleet_id: Fleet to disband
            
        Returns:
            Number of robots removed
        """
        robots = self.get_fleet_robots(fleet_id)
        count = 0
        for robot_id in robots:
            if self.on_robot_removed_from_fleet(robot_id):
                count += 1
        return count
    
    def shutdown(self):
        """Cleanup resources"""
        # Clear all states
        self.robot_priorities.clear()
        self.monitoring_zones.clear()
        self.fleet_memberships.clear()
        
        if self.logger:
            self.logger.info("DIMC notifier shutdown complete")
