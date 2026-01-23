"""
Fleet Discovery Protocol

Implements active robot discovery, fleet membership management, and departure detection.
This addresses the P2 Gap: Fleet Discovery Protocol.

Features:
- Periodic discovery broadcasts
- Robot health monitoring
- Automatic departure detection
- Fleet membership events
"""

import json
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy


class RobotStatus(Enum):
    """Robot fleet membership status"""

    UNKNOWN = "unknown"
    DISCOVERING = "discovering"  # Seen but not confirmed
    ACTIVE = "active"  # Confirmed fleet member
    IDLE = "idle"  # Active but not executing tasks
    BUSY = "busy"  # Executing a task
    WARNING = "warning"  # Health issues detected
    LEAVING = "leaving"  # Graceful departure
    LOST = "lost"  # No response - presumed departed


class CapabilityType(Enum):
    """Robot capability types"""

    NAVIGATION = "navigation"
    MANIPULATION = "manipulation"
    SENSING = "sensing"
    TRANSPORT = "transport"
    CHARGING = "charging"


@dataclass
class RobotInfo:
    """Information about a discovered robot"""

    robot_id: str
    robot_type: str = "unknown"
    status: RobotStatus = RobotStatus.UNKNOWN
    capabilities: Set[CapabilityType] = field(default_factory=set)
    position: Optional[tuple] = None  # (x, y, z)
    battery_level: float = 100.0
    current_task: Optional[str] = None
    last_seen: float = 0.0
    first_seen: float = 0.0
    heartbeat_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_healthy(self, timeout: float = 30.0) -> bool:
        """Check if robot is considered healthy"""
        return (
            self.status in [RobotStatus.ACTIVE, RobotStatus.IDLE, RobotStatus.BUSY]
            and time.time() - self.last_seen < timeout
        )

    def time_since_seen(self) -> float:
        """Get time since last heartbeat"""
        return time.time() - self.last_seen


@dataclass
class DiscoveryMessage:
    """Discovery protocol message"""

    message_type: str  # "announce", "heartbeat", "query", "response", "leaving"
    robot_id: str
    robot_type: str = "unknown"
    capabilities: List[str] = field(default_factory=list)
    position: Optional[tuple] = None
    battery_level: float = 100.0
    current_task: Optional[str] = None
    status: str = "active"
    timestamp: float = 0.0
    sequence: int = 0

    def to_json(self) -> str:
        """Serialize to JSON"""
        return json.dumps(
            {
                "type": self.message_type,
                "robot_id": self.robot_id,
                "robot_type": self.robot_type,
                "capabilities": self.capabilities,
                "position": self.position,
                "battery": self.battery_level,
                "task": self.current_task,
                "status": self.status,
                "timestamp": self.timestamp,
                "seq": self.sequence,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> "DiscoveryMessage":
        """Deserialize from JSON"""
        d = json.loads(data)
        return cls(
            message_type=d.get("type", "unknown"),
            robot_id=d.get("robot_id", ""),
            robot_type=d.get("robot_type", "unknown"),
            capabilities=d.get("capabilities", []),
            position=tuple(d["position"]) if d.get("position") else None,
            battery_level=d.get("battery", 100.0),
            current_task=d.get("task"),
            status=d.get("status", "unknown"),
            timestamp=d.get("timestamp", 0.0),
            sequence=d.get("seq", 0),
        )


class FleetDiscovery:
    """
    Fleet discovery and membership management.

    Provides:
    - Automatic robot discovery via periodic announcements
    - Health monitoring with configurable timeouts
    - Departure detection (graceful and lost)
    - Fleet membership callbacks
    """

    # Timing constants
    ANNOUNCE_INTERVAL = 5.0  # seconds between announcements
    HEARTBEAT_INTERVAL = 2.0  # seconds between heartbeats
    DISCOVERY_TIMEOUT = 10.0  # seconds to confirm discovery
    HEALTH_TIMEOUT = 15.0  # seconds before warning
    LOST_TIMEOUT = 30.0  # seconds before marked lost
    CLEANUP_INTERVAL = 60.0  # seconds between cleanup cycles

    # Confirmation threshold
    MIN_HEARTBEATS_FOR_ACTIVE = 3  # heartbeats needed to confirm membership

    def __init__(self, node: Node, robot_id: str, robot_type: str = "generic"):
        """
        Initialize fleet discovery.

        Args:
            node: ROS2 node
            robot_id: This robot's unique identifier
            robot_type: Type of this robot
        """
        self.node = node
        self.robot_id = robot_id
        self.robot_type = robot_type

        # Fleet registry
        self._fleet: Dict[str, RobotInfo] = {}

        # Own state
        self._capabilities: Set[CapabilityType] = set()
        self._position: Optional[tuple] = None
        self._battery_level: float = 100.0
        self._current_task: Optional[str] = None
        self._status = RobotStatus.ACTIVE

        # Message sequence
        self._sequence = 0

        # Callbacks
        self._join_callbacks: List[Callable[[str, RobotInfo], None]] = []
        self._leave_callbacks: List[Callable[[str, RobotStatus], None]] = []
        self._update_callbacks: List[Callable[[str, RobotInfo], None]] = []

        # Threading
        self._lock = threading.RLock()
        self._running = True

        # Discovery QoS - best effort for discovery, reliable for important
        self._discovery_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        # Start background threads
        self._announcer = threading.Thread(target=self._announce_loop, daemon=True)
        self._announcer.start()

        self._monitor = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor.start()

        self.node.get_logger().info(f"FleetDiscovery initialized for {robot_id} ({robot_type})")

    def shutdown(self):
        """Shutdown discovery service"""
        # Announce departure
        self._broadcast_leaving()
        self._running = False

    # =========================================================================
    # Self Configuration
    # =========================================================================

    def set_capabilities(self, capabilities: List[CapabilityType]):
        """Set this robot's capabilities"""
        self._capabilities = set(capabilities)

    def update_position(self, x: float, y: float, z: float = 0.0):
        """Update this robot's position"""
        self._position = (x, y, z)

    def update_battery(self, level: float):
        """Update battery level"""
        self._battery_level = max(0.0, min(100.0, level))

    def update_task(self, task_id: Optional[str]):
        """Update current task"""
        self._current_task = task_id
        self._status = RobotStatus.BUSY if task_id else RobotStatus.IDLE

    def set_status(self, status: RobotStatus):
        """Set robot status"""
        self._status = status

    # =========================================================================
    # Fleet Queries
    # =========================================================================

    def get_fleet(self) -> Dict[str, RobotInfo]:
        """Get all known robots"""
        with self._lock:
            return dict(self._fleet)

    def get_active_robots(self) -> List[str]:
        """Get IDs of all active robots"""
        with self._lock:
            return [
                rid
                for rid, info in self._fleet.items()
                if info.status in [RobotStatus.ACTIVE, RobotStatus.IDLE, RobotStatus.BUSY]
            ]

    def get_healthy_robots(self) -> List[str]:
        """Get IDs of all healthy robots"""
        with self._lock:
            return [rid for rid, info in self._fleet.items() if info.is_healthy()]

    def get_robot_info(self, robot_id: str) -> Optional[RobotInfo]:
        """Get info for a specific robot"""
        with self._lock:
            return self._fleet.get(robot_id)

    def get_robots_with_capability(self, capability: CapabilityType) -> List[str]:
        """Get robots with a specific capability"""
        with self._lock:
            return [
                rid
                for rid, info in self._fleet.items()
                if capability in info.capabilities and info.is_healthy()
            ]

    def get_idle_robots(self) -> List[str]:
        """Get robots that are idle"""
        with self._lock:
            return [
                rid
                for rid, info in self._fleet.items()
                if info.status == RobotStatus.IDLE and info.is_healthy()
            ]

    def get_fleet_size(self) -> int:
        """Get number of active fleet members"""
        with self._lock:
            return len(
                [
                    r
                    for r in self._fleet.values()
                    if r.status in [RobotStatus.ACTIVE, RobotStatus.IDLE, RobotStatus.BUSY]
                ]
            )

    # =========================================================================
    # Message Handling
    # =========================================================================

    def handle_discovery_message(self, message_data: str):
        """
        Handle incoming discovery message.

        Args:
            message_data: JSON-encoded discovery message
        """
        try:
            msg = DiscoveryMessage.from_json(message_data)

            if msg.robot_id == self.robot_id:
                return  # Ignore own messages

            if msg.message_type == "announce":
                self._handle_announce(msg)
            elif msg.message_type == "heartbeat":
                self._handle_heartbeat(msg)
            elif msg.message_type == "query":
                self._handle_query(msg)
            elif msg.message_type == "response":
                self._handle_response(msg)
            elif msg.message_type == "leaving":
                self._handle_leaving(msg)
            else:
                self.node.get_logger().debug(f"Unknown message type: {msg.message_type}")

        except Exception as e:
            self.node.get_logger().error(f"Error handling discovery message: {e}")

    def _handle_announce(self, msg: DiscoveryMessage):
        """Handle robot announcement"""
        with self._lock:
            now = time.time()

            if msg.robot_id not in self._fleet:
                # New robot discovered
                info = RobotInfo(
                    robot_id=msg.robot_id,
                    robot_type=msg.robot_type,
                    status=RobotStatus.DISCOVERING,
                    capabilities=set(
                        CapabilityType(c)
                        for c in msg.capabilities
                        if c in [e.value for e in CapabilityType]
                    ),
                    position=msg.position,
                    battery_level=msg.battery_level,
                    current_task=msg.current_task,
                    last_seen=now,
                    first_seen=now,
                    heartbeat_count=1,
                )
                self._fleet[msg.robot_id] = info

                self.node.get_logger().info(f"Discovered robot: {msg.robot_id} ({msg.robot_type})")
            else:
                # Update existing
                info = self._fleet[msg.robot_id]
                info.last_seen = now
                info.heartbeat_count += 1
                info.position = msg.position or info.position
                info.battery_level = msg.battery_level
                info.current_task = msg.current_task

                # Promote to active if enough heartbeats
                if (
                    info.status == RobotStatus.DISCOVERING
                    and info.heartbeat_count >= self.MIN_HEARTBEATS_FOR_ACTIVE
                ):
                    info.status = RobotStatus.ACTIVE
                    self._notify_join(msg.robot_id, info)

    def _handle_heartbeat(self, msg: DiscoveryMessage):
        """Handle heartbeat message"""
        with self._lock:
            now = time.time()

            if msg.robot_id in self._fleet:
                info = self._fleet[msg.robot_id]
                old_status = info.status

                info.last_seen = now
                info.heartbeat_count += 1
                info.battery_level = msg.battery_level
                info.position = msg.position or info.position
                info.current_task = msg.current_task

                # Update status based on message
                if msg.status == "busy":
                    info.status = RobotStatus.BUSY
                elif msg.status == "idle":
                    info.status = RobotStatus.IDLE
                elif msg.status in ["active", "unknown"]:
                    if info.status in [RobotStatus.WARNING, RobotStatus.LOST]:
                        info.status = RobotStatus.ACTIVE

                # Promote discovering robots
                if (
                    info.status == RobotStatus.DISCOVERING
                    and info.heartbeat_count >= self.MIN_HEARTBEATS_FOR_ACTIVE
                ):
                    info.status = RobotStatus.ACTIVE
                    self._notify_join(msg.robot_id, info)

                # Recover from warning/lost
                if old_status in [RobotStatus.WARNING, RobotStatus.LOST]:
                    info.status = RobotStatus.ACTIVE
                    self.node.get_logger().info(f"Robot {msg.robot_id} recovered")

                self._notify_update(msg.robot_id, info)
            else:
                # Unknown robot sending heartbeat - treat as announce
                self._handle_announce(msg)

    def _handle_query(self, msg: DiscoveryMessage):
        """Handle discovery query - respond with our info"""
        response = self._create_message("response")
        self._send_message(response)

    def _handle_response(self, msg: DiscoveryMessage):
        """Handle query response"""
        # Same as announce
        self._handle_announce(msg)

    def _handle_leaving(self, msg: DiscoveryMessage):
        """Handle graceful departure"""
        with self._lock:
            if msg.robot_id in self._fleet:
                info = self._fleet[msg.robot_id]
                info.status = RobotStatus.LEAVING

                self.node.get_logger().info(f"Robot {msg.robot_id} departing gracefully")
                self._notify_leave(msg.robot_id, RobotStatus.LEAVING)

                # Remove after short delay
                del self._fleet[msg.robot_id]

    # =========================================================================
    # Broadcasting
    # =========================================================================

    def _announce_loop(self):
        """Background thread for periodic announcements"""
        while self._running:
            try:
                # Alternate between announce and heartbeat
                time.sleep(self.HEARTBEAT_INTERVAL)

                if self._running:
                    msg = self._create_message("heartbeat")
                    self._send_message(msg)

            except Exception as e:
                self.node.get_logger().error(f"Announce loop error: {e}")

    def _create_message(self, msg_type: str) -> DiscoveryMessage:
        """Create a discovery message"""
        self._sequence += 1
        return DiscoveryMessage(
            message_type=msg_type,
            robot_id=self.robot_id,
            robot_type=self.robot_type,
            capabilities=[c.value for c in self._capabilities],
            position=self._position,
            battery_level=self._battery_level,
            current_task=self._current_task,
            status=self._status.value,
            timestamp=time.time(),
            sequence=self._sequence,
        )

    def _send_message(self, msg: DiscoveryMessage):
        """
        Send discovery message.

        In a real implementation, this would publish to a ROS2 topic.
        Subclasses should override this method.
        """
        # This is a hook - actual implementation would publish to ROS2
        pass

    def _broadcast_leaving(self):
        """Broadcast departure message"""
        msg = self._create_message("leaving")
        self._send_message(msg)

    def broadcast_query(self):
        """Broadcast a discovery query to find all robots"""
        msg = self._create_message("query")
        self._send_message(msg)
        self.node.get_logger().info("Broadcast discovery query")

    # =========================================================================
    # Health Monitoring
    # =========================================================================

    def _monitor_loop(self):
        """Background thread for health monitoring"""
        while self._running:
            try:
                time.sleep(self.HEARTBEAT_INTERVAL)
                self._check_fleet_health()

            except Exception as e:
                self.node.get_logger().error(f"Monitor loop error: {e}")

    def _check_fleet_health(self):
        """Check health of all fleet members"""
        with self._lock:
            now = time.time()
            to_remove = []

            for robot_id, info in self._fleet.items():
                time_since = now - info.last_seen

                if info.status == RobotStatus.LEAVING:
                    continue

                if time_since > self.LOST_TIMEOUT:
                    if info.status != RobotStatus.LOST:
                        info.status = RobotStatus.LOST
                        self.node.get_logger().warn(
                            f"Robot {robot_id} marked LOST (no response for {time_since:.1f}s)"
                        )
                        self._notify_leave(robot_id, RobotStatus.LOST)

                    # Clean up very old entries
                    if time_since > self.CLEANUP_INTERVAL:
                        to_remove.append(robot_id)

                elif time_since > self.HEALTH_TIMEOUT:
                    if info.status not in [RobotStatus.WARNING, RobotStatus.LOST]:
                        info.status = RobotStatus.WARNING
                        self.node.get_logger().warn(
                            f"Robot {robot_id} health warning (no response for {time_since:.1f}s)"
                        )
                        self._notify_update(robot_id, info)

            # Remove stale entries
            for robot_id in to_remove:
                del self._fleet[robot_id]
                self.node.get_logger().info(f"Removed stale robot entry: {robot_id}")

    # =========================================================================
    # Callbacks
    # =========================================================================

    def on_robot_join(self, callback: Callable[[str, RobotInfo], None]):
        """Register callback for robot joining fleet"""
        self._join_callbacks.append(callback)

    def on_robot_leave(self, callback: Callable[[str, RobotStatus], None]):
        """Register callback for robot leaving fleet"""
        self._leave_callbacks.append(callback)

    def on_robot_update(self, callback: Callable[[str, RobotInfo], None]):
        """Register callback for robot status updates"""
        self._update_callbacks.append(callback)

    def _notify_join(self, robot_id: str, info: RobotInfo):
        """Notify join callbacks"""
        self.node.get_logger().info(f"Robot {robot_id} joined fleet")
        for callback in self._join_callbacks:
            try:
                callback(robot_id, info)
            except Exception as e:
                self.node.get_logger().error(f"Join callback error: {e}")

    def _notify_leave(self, robot_id: str, status: RobotStatus):
        """Notify leave callbacks"""
        for callback in self._leave_callbacks:
            try:
                callback(robot_id, status)
            except Exception as e:
                self.node.get_logger().error(f"Leave callback error: {e}")

    def _notify_update(self, robot_id: str, info: RobotInfo):
        """Notify update callbacks"""
        for callback in self._update_callbacks:
            try:
                callback(robot_id, info)
            except Exception as e:
                self.node.get_logger().error(f"Update callback error: {e}")

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_fleet_stats(self) -> Dict[str, Any]:
        """Get fleet statistics"""
        with self._lock:
            status_counts = {}
            for info in self._fleet.values():
                status = info.status.value
                status_counts[status] = status_counts.get(status, 0) + 1

            return {
                "total_robots": len(self._fleet),
                "healthy_count": len(self.get_healthy_robots()),
                "active_count": len(self.get_active_robots()),
                "idle_count": len(self.get_idle_robots()),
                "status_breakdown": status_counts,
                "my_id": self.robot_id,
                "my_status": self._status.value,
            }
