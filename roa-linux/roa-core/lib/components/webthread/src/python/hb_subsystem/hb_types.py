"""
hb_types.py
ROA - Robot Operations & Automation
Heartbeat Subsystem - Types, Constants, and Data Structures

This module defines all enums, constants, and data structures for the HB subsystem.
Based on extensive research from ROS2 Lifecycle, SimPRIVE, Failsafe-go, and FDIR patterns.
"""

import struct
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from typing import Any, Dict, List, Optional

# =============================================================================
# TIMING CONSTANTS
# =============================================================================


class HBTiming:
    """Heartbeat timing constants"""

    TARGET_INTERVAL_MS = 25  # Target heartbeat interval
    MAX_INTERVAL_MS = 50  # Maximum allowed interval
    TIMEOUT_THRESHOLD_MS = 200  # 4 missed HBs = timeout
    ACTIVITY_WINDOW_MS = 100  # Activity must occur within this window
    IDLE_ACKNOWLEDGE_INTERVAL_MS = 50  # How often idle can be acknowledged

    # Detection thresholds
    YELLOW_THRESHOLD_MS = 50  # 1 missed HB
    ORANGE_THRESHOLD_MS = 100  # 2 missed HBs
    RED_THRESHOLD_MS = 150  # 3 missed HBs
    RESET_THRESHOLD_MS = 200  # 4 missed HBs - trigger reset

    # Recovery timing
    RECOVERY_VERIFICATION_COUNT = 3  # Need 3 consecutive healthy HBs
    MAX_RECOVERY_ATTEMPTS = 3  # Max attempts before escalation
    RECOVERY_COOLDOWN_MS = 5000  # Cooldown between recovery attempts

    # Persistence
    STATE_SNAPSHOT_INTERVAL_S = 5  # Snapshot state every 5 seconds


# =============================================================================
# NETWORK CONSTANTS
# =============================================================================


class HBPorts:
    """Dedicated UDP ports for each component's heartbeat"""

    FTI = 9877  # Files Type Importer
    ROC = 9878  # Robot Operator Controller
    DIMC = 9879  # Dimensions Collector
    COMC = 9880  # Communication Center
    ROS2_BRIDGE = 9881  # ROS2 Bridge
    UE5_BRIDGE = 9882  # UE5 Bridge

    # Mapping for easy lookup
    BY_COMPONENT = {
        "FTI": 9877,
        "ROC": 9878,
        "DIMC": 9879,
        "COMC": 9880,
        "ROS2Bridge": 9881,
        "UE5Bridge": 9882,
    }

    # Reverse mapping
    BY_PORT = {v: k for k, v in BY_COMPONENT.items()}

    # Base port for dynamic allocation
    BASE_PORT = 9877

    # Receiver bind address
    BIND_ADDRESS = "127.0.0.1"


# =============================================================================
# ACTIVITY TYPES - What counts as "legitimate" activity
# =============================================================================


class ActivityCategory(IntEnum):
    """Activity categories for validation"""

    CATEGORY_A = 1  # Core Operations - any 1 = valid
    CATEGORY_B = 2  # I/O Operations - any 1 = valid
    CATEGORY_C = 3  # Health Checks - requires 2+ = valid
    CATEGORY_D = 4  # Component-Specific - any 1 = valid


class ActivityType(Enum):
    """
    Activity types that prove a component is doing real work.
    A component must report activities to generate legitimate heartbeats.
    """

    # Category A: Core Operations (any 1 = valid)
    MESSAGE_PROCESSED = ("msg_proc", ActivityCategory.CATEGORY_A)
    COMMAND_EXECUTED = ("cmd_exec", ActivityCategory.CATEGORY_A)
    STATE_TRANSITION = ("state_trans", ActivityCategory.CATEGORY_A)

    # Category B: I/O Operations (any 1 = valid)
    DATA_SENT = ("data_sent", ActivityCategory.CATEGORY_B)
    DATA_RECEIVED = ("data_recv", ActivityCategory.CATEGORY_B)
    FILE_OPERATION = ("file_op", ActivityCategory.CATEGORY_B)

    # Category C: Health Checks (requires 2+ = valid)
    INTERNAL_CHECK = ("internal_chk", ActivityCategory.CATEGORY_C)
    QUEUE_SERVICED = ("queue_svc", ActivityCategory.CATEGORY_C)
    WATCHDOG_PET = ("wd_pet", ActivityCategory.CATEGORY_C)

    # Category D: Component-Specific
    # FTI specific
    FRAME_CONVERTED = ("frame_conv", ActivityCategory.CATEGORY_D)
    DATA_BRIDGED = ("data_bridge", ActivityCategory.CATEGORY_D)

    # ROC specific
    RULE_EVALUATED = ("rule_eval", ActivityCategory.CATEGORY_D)
    ACTION_DISPATCHED = ("action_disp", ActivityCategory.CATEGORY_D)

    # DIMC specific
    CONVERSION_COMPLETED = ("conv_done", ActivityCategory.CATEGORY_D)
    BACKEND_RESPONSE = ("backend_resp", ActivityCategory.CATEGORY_D)

    # COMC specific
    CHANNEL_ACTIVE = ("chan_active", ActivityCategory.CATEGORY_D)
    PEER_RESPONDED = ("peer_resp", ActivityCategory.CATEGORY_D)

    # Special: Idle acknowledgment (requires proof)
    IDLE_ACKNOWLEDGED = ("idle_ack", ActivityCategory.CATEGORY_A)

    def __init__(self, code: str, category: ActivityCategory):
        self._code = code
        self._category = category

    @property
    def code(self) -> str:
        return self._code

    @property
    def category(self) -> ActivityCategory:
        return self._category


def validate_activities(activities: List[ActivityType]) -> bool:
    """
    Validate if activities are sufficient to prove component is alive.

    Rules:
    - Any 1 Category A activity = valid
    - Any 1 Category B activity = valid
    - 2+ Category C activities = valid
    - Any 1 Category D activity = valid

    Args:
        activities: List of activities reported in this interval

    Returns:
        True if activities prove component is working
    """
    if not activities:
        return False

    cat_a = any(a.category == ActivityCategory.CATEGORY_A for a in activities)
    cat_b = any(a.category == ActivityCategory.CATEGORY_B for a in activities)
    cat_c = sum(1 for a in activities if a.category == ActivityCategory.CATEGORY_C) >= 2
    cat_d = any(a.category == ActivityCategory.CATEGORY_D for a in activities)

    return cat_a or cat_b or cat_c or cat_d


# =============================================================================
# COMPONENT STATE (Based on ROS2 Lifecycle)
# =============================================================================


class ComponentState(IntEnum):
    """
    Component lifecycle states (based on ROS2 Lifecycle).
    These are the 4 primary states a component can be in.
    """

    UNCONFIGURED = 0  # Initial state after spawn
    INACTIVE = 1  # Configured but not active
    ACTIVE = 2  # Running normally
    ERROR = 3  # In error state, needs recovery

    # Additional states for HB subsystem
    SHUTTING_DOWN = 4  # Component is shutting down
    AUTONOMOUS = 5  # Component running without WT (fallback mode)


class TransitionState(IntEnum):
    """
    Transition states during state changes.
    Based on ROS2 lifecycle transition states.
    """

    CONFIGURING = 10
    CLEANING_UP = 11
    ACTIVATING = 12
    DEACTIVATING = 13
    ERROR_PROCESSING = 14
    SHUTTING_DOWN_STATE = 15


# =============================================================================
# HEALTH LEVELS
# =============================================================================


class HealthLevel(IntEnum):
    """
    6-level health classification.
    More granular than simple healthy/degraded/failed.
    """

    OPTIMAL = 0  # Everything perfect
    HEALTHY = 1  # Normal operation
    ACCEPTABLE = 2  # Minor issues, monitoring
    DEGRADED = 3  # Significant issues, may need intervention
    CRITICAL = 4  # Severe issues, intervention required
    FAILED = 5  # Component has failed


class AlertLevel(IntEnum):
    """Alert levels for health status transitions"""

    GREEN = 0  # All good
    YELLOW = 1  # 1 missed HB - watching
    ORANGE = 2  # 2 missed HBs - warning
    RED = 3  # 3 missed HBs - critical
    BLACK = 4  # 4+ missed HBs - failed/reset triggered


# =============================================================================
# HEARTBEAT PACKET STRUCTURE
# =============================================================================


@dataclass
class HeartbeatPacket:
    """
    Binary heartbeat packet structure.
    Total size: 26 bytes (extended format)

    Format:
    - component_id: uint8 (1 byte)
    - timestamp: uint64 (8 bytes) - microseconds since epoch
    - sequence: uint16 (2 bytes) - wraps at 65535
    - state: uint8 (1 byte) - ComponentState
    - health: uint8 (1 byte) - HealthLevel
    - response_time_us: uint32 (4 bytes) - last operation response time
    - error_count: uint16 (2 bytes) - errors since last reset
    - memory_percent: uint8 (1 byte) - 0-100
    - cpu_percent: uint8 (1 byte) - 0-100
    - queue_depth: uint16 (2 bytes) - pending items
    - activity_bitmap: uint16 (2 bytes) - which activities occurred
    - checksum: uint8 (1 byte) - XOR checksum of all bytes
    """

    component_id: int
    timestamp: int
    sequence: int
    state: ComponentState
    health: HealthLevel
    response_time_us: int
    error_count: int
    memory_percent: int
    cpu_percent: int
    queue_depth: int
    activity_bitmap: int
    checksum: int = 0

    # Struct format: little-endian, uint8, uint64, uint16, uint8, uint8, uint32, uint16, uint8, uint8, uint16, uint16, uint8
    STRUCT_FORMAT = "<BQHBBIHBBHHB"
    PACKET_SIZE = 26

    @classmethod
    def from_bytes(cls, data: bytes) -> Optional["HeartbeatPacket"]:
        """Parse heartbeat from raw bytes"""
        if len(data) != cls.PACKET_SIZE:
            return None

        try:
            unpacked = struct.unpack(cls.STRUCT_FORMAT, data)
            packet = cls(
                component_id=unpacked[0],
                timestamp=unpacked[1],
                sequence=unpacked[2],
                state=ComponentState(unpacked[3]),
                health=HealthLevel(unpacked[4]),
                response_time_us=unpacked[5],
                error_count=unpacked[6],
                memory_percent=unpacked[7],
                cpu_percent=unpacked[8],
                queue_depth=unpacked[9],
                activity_bitmap=unpacked[10],
                checksum=unpacked[11],
            )

            # Verify checksum
            if not packet.verify_checksum(data):
                return None

            return packet
        except (struct.error, ValueError):
            return None

    def to_bytes(self) -> bytes:
        """Serialize heartbeat to bytes"""
        # Pack without checksum first
        data = struct.pack(
            "<BQHBBIHBBHH",  # Without final B for checksum
            self.component_id,
            self.timestamp,
            self.sequence,
            int(self.state),
            int(self.health),
            self.response_time_us,
            self.error_count,
            self.memory_percent,
            self.cpu_percent,
            self.queue_depth,
            self.activity_bitmap,
        )

        # Calculate checksum
        self.checksum = self._calculate_checksum(data)

        # Return full packet with checksum
        return data + struct.pack("B", self.checksum)

    def _calculate_checksum(self, data: bytes) -> int:
        """Calculate XOR checksum of data"""
        checksum = 0
        for byte in data:
            checksum ^= byte
        return checksum

    def verify_checksum(self, data: bytes) -> bool:
        """Verify packet checksum"""
        if len(data) != self.PACKET_SIZE:
            return False

        # Checksum of all bytes including checksum byte should be 0
        calculated = self._calculate_checksum(data[:-1])
        return calculated == data[-1]


# =============================================================================
# STARTUP HANDSHAKE
# =============================================================================


@dataclass
class StartupPing:
    """Startup ping from agent to receiver"""

    component_id: int
    timestamp: int
    magic: int = 0x4842  # Magic number to identify ping ('HB' in ASCII)

    STRUCT_FORMAT = "<BQH"
    PACKET_SIZE = 11
    MAGIC_NUMBER = 0x4842  # 'HB' in ASCII

    @classmethod
    def from_bytes(cls, data: bytes) -> Optional["StartupPing"]:
        if len(data) != cls.PACKET_SIZE:
            return None
        try:
            unpacked = struct.unpack(cls.STRUCT_FORMAT, data)
            if unpacked[2] != cls.MAGIC_NUMBER:
                return None
            return cls(component_id=unpacked[0], timestamp=unpacked[1], magic=unpacked[2])
        except struct.error:
            return None

    def to_bytes(self) -> bytes:
        return struct.pack(self.STRUCT_FORMAT, self.component_id, self.timestamp, self.MAGIC_NUMBER)


@dataclass
class StartupAck:
    """Acknowledgment from receiver to agent"""

    component_id: int
    timestamp: int
    port_assigned: int
    magic: int = 0x4841  # 'HA' for Heartbeat Ack

    STRUCT_FORMAT = "<BQHH"
    PACKET_SIZE = 13
    MAGIC_NUMBER = 0x4841

    @classmethod
    def from_bytes(cls, data: bytes) -> Optional["StartupAck"]:
        if len(data) != cls.PACKET_SIZE:
            return None
        try:
            unpacked = struct.unpack(cls.STRUCT_FORMAT, data)
            if unpacked[3] != cls.MAGIC_NUMBER:
                return None
            return cls(
                component_id=unpacked[0],
                timestamp=unpacked[1],
                port_assigned=unpacked[2],
                magic=unpacked[3],
            )
        except struct.error:
            return None

    def to_bytes(self) -> bytes:
        return struct.pack(
            self.STRUCT_FORMAT,
            self.component_id,
            self.timestamp,
            self.port_assigned,
            self.MAGIC_NUMBER,
        )


# =============================================================================
# COMPONENT ID MAPPING
# =============================================================================


class ComponentID:
    """Component ID assignments"""

    FTI = 1
    ROC = 2
    DIMC = 3
    COMC = 4
    ROS2_BRIDGE = 5
    UE5_BRIDGE = 6
    HB_SUBSYSTEM = 7  # HB subsystem itself (for watchdog)
    WT_CORE = 8  # Webthread Core

    BY_NAME = {
        "FTI": 1,
        "ROC": 2,
        "DIMC": 3,
        "COMC": 4,
        "ROS2Bridge": 5,
        "UE5Bridge": 6,
        "HBSubsystem": 7,
        "WTCore": 8,
    }

    BY_ID = {v: k for k, v in BY_NAME.items()}

    # Priority order (higher = more critical)
    PRIORITY = {
        "WTCore": 100,
        "HBSubsystem": 90,
        "FTI": 80,
        "ROC": 70,
        "DIMC": 60,
        "COMC": 50,
        "ROS2Bridge": 40,
        "UE5Bridge": 40,
    }


# =============================================================================
# HEALTH STATUS STRUCTURES
# =============================================================================


@dataclass
class ComponentHealthStatus:
    """Detailed health status for a component"""

    component_id: int
    component_name: str
    state: ComponentState
    health: HealthLevel
    alert_level: AlertLevel
    last_heartbeat_time: float
    last_sequence: int
    consecutive_misses: int
    response_time_avg_ms: float
    error_count: int
    recovery_attempts: int
    memory_percent: int
    cpu_percent: int
    queue_depth: int
    last_activities: List[ActivityType]
    warnings: List[str]
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "component_id": self.component_id,
            "component_name": self.component_name,
            "state": self.state.name,
            "health": self.health.name,
            "alert_level": self.alert_level.name,
            "last_heartbeat_time": self.last_heartbeat_time,
            "last_sequence": self.last_sequence,
            "consecutive_misses": self.consecutive_misses,
            "response_time_avg_ms": self.response_time_avg_ms,
            "error_count": self.error_count,
            "recovery_attempts": self.recovery_attempts,
            "memory_percent": self.memory_percent,
            "cpu_percent": self.cpu_percent,
            "queue_depth": self.queue_depth,
            "last_activities": [a.code for a in self.last_activities],
            "warnings": self.warnings,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ComponentHealthStatus":
        """Create from dictionary"""
        return cls(
            component_id=data["component_id"],
            component_name=data["component_name"],
            state=ComponentState[data["state"]],
            health=HealthLevel[data["health"]],
            alert_level=AlertLevel[data["alert_level"]],
            last_heartbeat_time=data["last_heartbeat_time"],
            last_sequence=data["last_sequence"],
            consecutive_misses=data["consecutive_misses"],
            response_time_avg_ms=data["response_time_avg_ms"],
            error_count=data["error_count"],
            recovery_attempts=data["recovery_attempts"],
            memory_percent=data["memory_percent"],
            cpu_percent=data["cpu_percent"],
            queue_depth=data["queue_depth"],
            last_activities=[],  # Activities need special handling
            warnings=data["warnings"],
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )


# =============================================================================
# CIRCUIT BREAKER STATES
# =============================================================================


class CircuitBreakerState(Enum):
    """Circuit breaker states from failsafe-go pattern"""

    CLOSED = "closed"  # Normal operation, requests allowed
    OPEN = "open"  # Failures exceeded, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerStatus:
    """Circuit breaker status for a component"""

    component_name: str
    state: CircuitBreakerState
    failure_count: int
    success_count: int
    last_failure_time: float
    last_success_time: float
    open_until: float  # When circuit will transition to half-open
    half_open_successes: int  # Successes needed in half-open state


# =============================================================================
# FAILURE SCENARIOS
# =============================================================================


class FailureType(Enum):
    """Types of failures that can be detected"""

    HEARTBEAT_TIMEOUT = "hb_timeout"
    SEQUENCE_GAP = "seq_gap"
    HEALTH_DEGRADED = "health_degraded"
    HIGH_LATENCY = "high_latency"
    HIGH_MEMORY = "high_memory"
    HIGH_CPU = "high_cpu"
    QUEUE_OVERFLOW = "queue_overflow"
    STATE_ERROR = "state_error"
    ACTIVITY_MISSING = "activity_missing"
    RATE_ANOMALY = "rate_anomaly"  # HBs coming too fast or too slow
    CHECKSUM_ERROR = "checksum_error"
    STARTUP_FAILURE = "startup_failure"
    RECOVERY_EXHAUSTED = "recovery_exhausted"


@dataclass
class FailureEvent:
    """Recorded failure event"""

    failure_type: FailureType
    component_name: str
    timestamp: float
    severity: HealthLevel
    details: str
    recovery_action: Optional[str] = None
    resolved: bool = False
    resolved_at: Optional[float] = None


# =============================================================================
# SEQUENCE NUMBER HANDLING
# =============================================================================


def is_sequence_gap(prev_seq: int, curr_seq: int) -> bool:
    """
    Check if there's a gap in sequence numbers.
    Handles 16-bit rollover correctly.

    Args:
        prev_seq: Previous sequence number (0-65535)
        curr_seq: Current sequence number (0-65535)

    Returns:
        True if there's a gap (missed heartbeats)
    """
    # Handle rollover: 65534 → 65535 → 0 → 1 is valid
    if curr_seq == 0 and prev_seq >= 65530:
        return False  # Valid rollover

    if curr_seq < prev_seq and curr_seq < 10 and prev_seq > 65525:
        return False  # Valid rollover window

    expected = (prev_seq + 1) % 65536
    return curr_seq != expected


def calculate_sequence_gap(prev_seq: int, curr_seq: int) -> int:
    """
    Calculate the number of missed heartbeats.

    Args:
        prev_seq: Previous sequence number
        curr_seq: Current sequence number

    Returns:
        Number of missed heartbeats
    """
    if curr_seq >= prev_seq:
        return curr_seq - prev_seq - 1
    else:
        # Rollover case
        return (65536 - prev_seq - 1) + curr_seq


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def get_timestamp_us() -> int:
    """Get current timestamp in microseconds"""
    return int(time.time() * 1_000_000)


def timestamp_to_datetime(timestamp_us: int) -> datetime:
    """Convert microsecond timestamp to datetime"""
    return datetime.fromtimestamp(timestamp_us / 1_000_000)


def activity_to_bitmap(activities: List[ActivityType]) -> int:
    """Convert list of activities to bitmap"""
    # Use first 16 activity types for bitmap
    activity_list = list(ActivityType)[:16]
    bitmap = 0
    for i, activity in enumerate(activity_list):
        if activity in activities:
            bitmap |= 1 << i
    return bitmap


def bitmap_to_activities(bitmap: int) -> List[ActivityType]:
    """Convert bitmap back to activity list"""
    activity_list = list(ActivityType)[:16]
    activities = []
    for i, activity in enumerate(activity_list):
        if bitmap & (1 << i):
            activities.append(activity)
    return activities
