"""
COMC Message Protocol
=====================
Message versioning, schema validation, and integrity verification.

This module addresses the gap of unstructured JSON messages with:
1. Message versioning for backward compatibility
2. Schema validation for type safety
3. Checksum verification for integrity
4. Message envelope with metadata

Usage:
    # Create a message
    msg = COMCMessage.create(
        message_type="work_area_update",
        payload={"robot_id": "robot_1", "center": {...}},
        sender_id="comc_node_1"
    )
    
    # Serialize to JSON
    json_str = msg.to_json()
    
    # Parse and validate
    parsed = COMCMessage.from_json(json_str)
    if parsed.validate():
        process_message(parsed)
"""

import json
import time
import hashlib
import uuid
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from abc import ABC, abstractmethod


# =============================================================================
# VERSION AND CONSTANTS
# =============================================================================

PROTOCOL_VERSION = "1.0.0"
PROTOCOL_MAGIC = "COMC"


class MessageType(Enum):
    """Supported message types"""
    # Coordination messages
    WORK_AREA_UPDATE = "work_area_update"
    WORK_AREA_CONFLICT = "work_area_conflict"
    PROXIMITY_ALERT = "proximity_alert"
    
    # Task messages
    TASK_REQUEST = "task_request"
    TASK_RESPONSE = "task_response"
    TASK_STATUS = "task_status"
    
    # Path messages
    PATH_RESERVATION = "path_reservation"
    PATH_CONFLICT = "path_conflict"
    EVASION_INTENT = "evasion_intent"
    
    # Fleet messages
    FLEET_DISCOVERY = "fleet_discovery"
    FLEET_JOIN = "fleet_join"
    FLEET_LEAVE = "fleet_leave"
    
    # Health messages
    HEALTH_STATUS = "health_status"
    HEARTBEAT = "heartbeat"
    
    # Control messages
    EMERGENCY_STOP = "emergency_stop"
    RESUME = "resume"
    
    # Resource messages
    RESOURCE_LOCK_REQUEST = "resource_lock_request"
    RESOURCE_LOCK_RESPONSE = "resource_lock_response"
    RESOURCE_UNLOCK = "resource_unlock"


# =============================================================================
# MESSAGE ENVELOPE
# =============================================================================

@dataclass
class MessageEnvelope:
    """
    Message envelope with metadata for all COMC messages.
    Provides versioning, integrity, and routing information.
    """
    # Protocol info
    magic: str = PROTOCOL_MAGIC
    version: str = PROTOCOL_VERSION
    
    # Message identity
    message_id: str = ""
    message_type: str = ""
    
    # Routing
    sender_id: str = ""
    target_id: str = ""  # Empty for broadcast
    
    # Timing
    timestamp: float = 0.0
    ttl_seconds: float = 30.0  # Time-to-live
    
    # Integrity
    checksum: str = ""
    
    # Payload
    payload: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.message_id:
            self.message_id = str(uuid.uuid4())
        if self.timestamp == 0.0:
            self.timestamp = time.time()
    
    def calculate_checksum(self) -> str:
        """Calculate SHA256 checksum of payload"""
        payload_str = json.dumps(self.payload, sort_keys=True)
        return hashlib.sha256(payload_str.encode()).hexdigest()[:16]
    
    def verify_checksum(self) -> bool:
        """Verify the message checksum"""
        if not self.checksum:
            return True  # No checksum to verify
        return self.checksum == self.calculate_checksum()
    
    def is_expired(self) -> bool:
        """Check if message has expired based on TTL"""
        return time.time() > self.timestamp + self.ttl_seconds
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)
    
    def to_json(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MessageEnvelope':
        """Create from dictionary"""
        return cls(**data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'MessageEnvelope':
        """Parse from JSON string"""
        data = json.loads(json_str)
        return cls.from_dict(data)


# =============================================================================
# SCHEMA DEFINITIONS
# =============================================================================

class SchemaField:
    """Field definition for schema validation"""
    def __init__(self, name: str, field_type: type, required: bool = True,
                 default: Any = None, validator: callable = None):
        self.name = name
        self.field_type = field_type
        self.required = required
        self.default = default
        self.validator = validator
    
    def validate(self, value: Any) -> Tuple[bool, str]:
        """Validate a value against this field"""
        if value is None:
            if self.required:
                return False, f"Field '{self.name}' is required"
            return True, ""
        
        # Type check
        if not isinstance(value, self.field_type):
            # Allow int for float
            if self.field_type == float and isinstance(value, (int, float)):
                pass
            else:
                return False, f"Field '{self.name}' expected {self.field_type.__name__}, got {type(value).__name__}"
        
        # Custom validator
        if self.validator:
            try:
                if not self.validator(value):
                    return False, f"Field '{self.name}' failed custom validation"
            except Exception as e:
                return False, f"Field '{self.name}' validator error: {e}"
        
        return True, ""


class MessageSchema:
    """Schema definition for a message type"""
    def __init__(self, message_type: MessageType, fields: List[SchemaField]):
        self.message_type = message_type
        self.fields = {f.name: f for f in fields}
    
    def validate(self, payload: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate payload against schema.
        
        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []
        
        # Check required fields
        for name, field in self.fields.items():
            value = payload.get(name)
            valid, error = field.validate(value)
            if not valid:
                errors.append(error)
        
        return len(errors) == 0, errors


# =============================================================================
# SCHEMA REGISTRY
# =============================================================================

class SchemaRegistry:
    """Registry of all message schemas"""
    
    _schemas: Dict[MessageType, MessageSchema] = {}
    
    @classmethod
    def register(cls, schema: MessageSchema):
        """Register a message schema"""
        cls._schemas[schema.message_type] = schema
    
    @classmethod
    def get(cls, message_type: MessageType) -> Optional[MessageSchema]:
        """Get schema for message type"""
        return cls._schemas.get(message_type)
    
    @classmethod
    def validate(cls, message_type: MessageType, payload: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate payload against registered schema"""
        schema = cls.get(message_type)
        if not schema:
            return True, []  # No schema, pass through
        return schema.validate(payload)


# =============================================================================
# REGISTER DEFAULT SCHEMAS
# =============================================================================

def _init_schemas():
    """Initialize default message schemas"""
    
    # Work Area Update
    SchemaRegistry.register(MessageSchema(
        MessageType.WORK_AREA_UPDATE,
        [
            SchemaField("robot_id", str),
            SchemaField("center", dict),  # {x, y, z}
            SchemaField("dimensions", dict),  # {x, y, z}
            SchemaField("priority", (int, float), required=False, default=2.0),
            SchemaField("timestamp", float, required=False),
        ]
    ))
    
    # Proximity Alert
    SchemaRegistry.register(MessageSchema(
        MessageType.PROXIMITY_ALERT,
        [
            SchemaField("source_robot_id", str),
            SchemaField("target_robot_id", str),
            SchemaField("current_distance", float),
            SchemaField("approach_velocity", float),
            SchemaField("severity", str, validator=lambda x: x in ["warning", "caution", "critical"]),
            SchemaField("time_to_collision", float, required=False),
            SchemaField("recommended_action", str, required=False),
        ]
    ))
    
    # Task Request
    SchemaRegistry.register(MessageSchema(
        MessageType.TASK_REQUEST,
        [
            SchemaField("robot_id", str),
            SchemaField("task_type", str),
            SchemaField("required_resources", list),
            SchemaField("priority", int, validator=lambda x: 0 <= x <= 4),
        ]
    ))
    
    # Path Reservation
    SchemaRegistry.register(MessageSchema(
        MessageType.PATH_RESERVATION,
        [
            SchemaField("robot_id", str),
            SchemaField("path", list),  # List of {x, y, z}
            SchemaField("duration_seconds", float),
            SchemaField("priority", int, required=False),
        ]
    ))
    
    # Fleet Discovery
    SchemaRegistry.register(MessageSchema(
        MessageType.FLEET_DISCOVERY,
        [
            SchemaField("robot_id", str),
            SchemaField("robot_type", str, required=False),
            SchemaField("capabilities", list, required=False),
            SchemaField("position", dict, required=False),
        ]
    ))
    
    # Health Status
    SchemaRegistry.register(MessageSchema(
        MessageType.HEALTH_STATUS,
        [
            SchemaField("component", str),
            SchemaField("robot_id", str),
            SchemaField("status", str, validator=lambda x: x in ["HEALTHY", "DEGRADED", "ERROR", "SHUTTING_DOWN"]),
            SchemaField("timestamp", float),
            SchemaField("active_robots", int, required=False),
            SchemaField("conflicts", int, required=False),
        ]
    ))
    
    # Resource Lock Request
    SchemaRegistry.register(MessageSchema(
        MessageType.RESOURCE_LOCK_REQUEST,
        [
            SchemaField("robot_id", str),
            SchemaField("resource_id", str),
            SchemaField("lock_duration", float, required=False, default=30.0),
            SchemaField("priority", int, required=False, default=2),
        ]
    ))
    
    # Emergency Stop
    SchemaRegistry.register(MessageSchema(
        MessageType.EMERGENCY_STOP,
        [
            SchemaField("robot_id", str),
            SchemaField("reason", str),
            SchemaField("level", str, validator=lambda x: x in ["soft", "hard", "emergency"]),
            SchemaField("triggered_by", str, required=False),
        ]
    ))

# Initialize schemas on module load
_init_schemas()


# =============================================================================
# COMC MESSAGE CLASS
# =============================================================================

class COMCMessage:
    """
    High-level COMC message with full protocol support.
    
    Usage:
        # Create message
        msg = COMCMessage.create(
            message_type=MessageType.WORK_AREA_UPDATE,
            payload={"robot_id": "robot_1", ...},
            sender_id="comc_node_1"
        )
        
        # Validate
        if msg.validate():
            json_str = msg.to_json()
        
        # Parse
        received = COMCMessage.from_json(json_str)
        if received.is_valid and not received.is_expired:
            process(received.payload)
    """
    
    def __init__(self, envelope: MessageEnvelope):
        self.envelope = envelope
        self._validation_errors: List[str] = []
        self._is_valid: Optional[bool] = None
    
    @classmethod
    def create(cls, message_type: MessageType, payload: Dict[str, Any],
               sender_id: str, target_id: str = "",
               ttl_seconds: float = 30.0) -> 'COMCMessage':
        """
        Create a new COMC message.
        
        Args:
            message_type: Type of message
            payload: Message payload
            sender_id: Sender identifier
            target_id: Target identifier (empty for broadcast)
            ttl_seconds: Time-to-live in seconds
            
        Returns:
            COMCMessage instance
        """
        envelope = MessageEnvelope(
            message_type=message_type.value,
            payload=payload,
            sender_id=sender_id,
            target_id=target_id,
            ttl_seconds=ttl_seconds
        )
        # Calculate checksum
        envelope.checksum = envelope.calculate_checksum()
        
        return cls(envelope)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'COMCMessage':
        """Parse message from JSON string"""
        envelope = MessageEnvelope.from_json(json_str)
        return cls(envelope)
    
    @classmethod
    def from_legacy_json(cls, json_str: str, message_type: MessageType,
                         sender_id: str = "unknown") -> 'COMCMessage':
        """
        Parse legacy (non-envelope) JSON message.
        Provides backward compatibility with old message format.
        
        Args:
            json_str: Raw JSON payload
            message_type: Message type
            sender_id: Sender ID to use
            
        Returns:
            COMCMessage instance
        """
        payload = json.loads(json_str)
        return cls.create(message_type, payload, sender_id)
    
    def validate(self) -> bool:
        """
        Validate message structure and payload.
        
        Returns:
            True if message is valid
        """
        if self._is_valid is not None:
            return self._is_valid
        
        self._validation_errors = []
        
        # Check magic
        if self.envelope.magic != PROTOCOL_MAGIC:
            self._validation_errors.append(f"Invalid magic: {self.envelope.magic}")
        
        # Check version compatibility
        if not self._is_version_compatible(self.envelope.version):
            self._validation_errors.append(f"Incompatible version: {self.envelope.version}")
        
        # Verify checksum
        if not self.envelope.verify_checksum():
            self._validation_errors.append("Checksum verification failed")
        
        # Validate payload against schema
        try:
            msg_type = MessageType(self.envelope.message_type)
            valid, errors = SchemaRegistry.validate(msg_type, self.envelope.payload)
            if not valid:
                self._validation_errors.extend(errors)
        except ValueError:
            self._validation_errors.append(f"Unknown message type: {self.envelope.message_type}")
        
        self._is_valid = len(self._validation_errors) == 0
        return self._is_valid
    
    def _is_version_compatible(self, version: str) -> bool:
        """Check if message version is compatible"""
        try:
            msg_major = int(version.split('.')[0])
            our_major = int(PROTOCOL_VERSION.split('.')[0])
            # Major version must match
            return msg_major == our_major
        except (ValueError, IndexError):
            return False
    
    @property
    def is_valid(self) -> bool:
        """Check if message is valid (runs validation if needed)"""
        if self._is_valid is None:
            self.validate()
        return self._is_valid
    
    @property
    def is_expired(self) -> bool:
        """Check if message has expired"""
        return self.envelope.is_expired()
    
    @property
    def validation_errors(self) -> List[str]:
        """Get validation errors"""
        if self._is_valid is None:
            self.validate()
        return self._validation_errors
    
    @property
    def message_type(self) -> Optional[MessageType]:
        """Get message type enum"""
        try:
            return MessageType(self.envelope.message_type)
        except ValueError:
            return None
    
    @property
    def payload(self) -> Dict[str, Any]:
        """Get message payload"""
        return self.envelope.payload
    
    @property
    def sender_id(self) -> str:
        """Get sender ID"""
        return self.envelope.sender_id
    
    @property
    def message_id(self) -> str:
        """Get message ID"""
        return self.envelope.message_id
    
    @property
    def timestamp(self) -> float:
        """Get message timestamp"""
        return self.envelope.timestamp
    
    def to_json(self) -> str:
        """Serialize to JSON string"""
        return self.envelope.to_json()
    
    def to_legacy_json(self) -> str:
        """
        Serialize payload only (for backward compatibility).
        
        Returns:
            JSON string of payload only
        """
        return json.dumps(self.envelope.payload)


# =============================================================================
# MESSAGE FACTORY
# =============================================================================

class MessageFactory:
    """
    Factory for creating typed COMC messages.
    Provides convenience methods for common message types.
    """
    
    @staticmethod
    def work_area_update(robot_id: str, center: Tuple[float, float, float],
                         dimensions: Tuple[float, float, float],
                         priority: float = 2.0) -> COMCMessage:
        """Create a work area update message"""
        return COMCMessage.create(
            message_type=MessageType.WORK_AREA_UPDATE,
            payload={
                "robot_id": robot_id,
                "center": {"x": center[0], "y": center[1], "z": center[2]},
                "dimensions": {"x": dimensions[0], "y": dimensions[1], "z": dimensions[2]},
                "priority": priority,
                "timestamp": time.time()
            },
            sender_id=robot_id
        )
    
    @staticmethod
    def proximity_alert(source_robot: str, target_robot: str,
                        distance: float, approach_velocity: float,
                        severity: str, ttc: float = None,
                        action: str = None) -> COMCMessage:
        """Create a proximity alert message"""
        payload = {
            "source_robot_id": source_robot,
            "target_robot_id": target_robot,
            "current_distance": distance,
            "approach_velocity": approach_velocity,
            "severity": severity,
            "timestamp": time.time()
        }
        if ttc is not None:
            payload["time_to_collision"] = ttc
        if action:
            payload["recommended_action"] = action
        
        return COMCMessage.create(
            message_type=MessageType.PROXIMITY_ALERT,
            payload=payload,
            sender_id=source_robot,
            ttl_seconds=5.0  # Short TTL for alerts
        )
    
    @staticmethod
    def emergency_stop(robot_id: str, reason: str, level: str,
                       triggered_by: str = None) -> COMCMessage:
        """Create an emergency stop message"""
        payload = {
            "robot_id": robot_id,
            "reason": reason,
            "level": level,
            "timestamp": time.time()
        }
        if triggered_by:
            payload["triggered_by"] = triggered_by
        
        return COMCMessage.create(
            message_type=MessageType.EMERGENCY_STOP,
            payload=payload,
            sender_id=robot_id,
            ttl_seconds=10.0
        )
    
    @staticmethod
    def fleet_discovery(robot_id: str, robot_type: str = None,
                        capabilities: List[str] = None,
                        position: Tuple[float, float, float] = None) -> COMCMessage:
        """Create a fleet discovery message"""
        payload = {
            "robot_id": robot_id,
            "timestamp": time.time()
        }
        if robot_type:
            payload["robot_type"] = robot_type
        if capabilities:
            payload["capabilities"] = capabilities
        if position:
            payload["position"] = {"x": position[0], "y": position[1], "z": position[2]}
        
        return COMCMessage.create(
            message_type=MessageType.FLEET_DISCOVERY,
            payload=payload,
            sender_id=robot_id
        )
    
    @staticmethod
    def resource_lock_request(robot_id: str, resource_id: str,
                               duration: float = 30.0,
                               priority: int = 2) -> COMCMessage:
        """Create a resource lock request message"""
        return COMCMessage.create(
            message_type=MessageType.RESOURCE_LOCK_REQUEST,
            payload={
                "robot_id": robot_id,
                "resource_id": resource_id,
                "lock_duration": duration,
                "priority": priority,
                "timestamp": time.time()
            },
            sender_id=robot_id
        )
    
    @staticmethod
    def health_status(component: str, robot_id: str, status: str,
                      active_robots: int = 0, conflicts: int = 0,
                      additional_info: Dict = None) -> COMCMessage:
        """Create a health status message"""
        payload = {
            "component": component,
            "robot_id": robot_id,
            "status": status,
            "timestamp": time.time(),
            "active_robots": active_robots,
            "conflicts": conflicts
        }
        if additional_info:
            payload.update(additional_info)
        
        return COMCMessage.create(
            message_type=MessageType.HEALTH_STATUS,
            payload=payload,
            sender_id=robot_id
        )
