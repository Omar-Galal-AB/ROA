"""
ROC Event Recorder - Centralized event and alert system.

Provides:
- Structured event recording with severity levels
- Alert generation and callbacks
- Event history with queryable storage
- Event export for debugging and auditing

Based on ROAEventRecorder pattern from shared observability.
"""

import asyncio
import json
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Set


class EventSeverity(Enum):
    """Event severity levels."""
    DEBUG = 0
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4


class EventCategory(Enum):
    """Event categories for filtering."""
    SAFETY = "safety"
    MODE = "mode"
    COMMAND = "command"
    CONNECTION = "connection"
    HEALTH = "health"
    ROBOT = "robot"
    INTEGRATION = "integration"
    SYSTEM = "system"


@dataclass
class ROCEvent:
    """Structured event record."""
    event_id: str
    timestamp: float
    category: EventCategory
    severity: EventSeverity
    event_type: str  # e.g., "estop_triggered", "mode_changed"
    message: str
    robot_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = "roc"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "timestamp_iso": datetime.fromtimestamp(self.timestamp).isoformat(),
            "category": self.category.value,
            "severity": self.severity.name,
            "event_type": self.event_type,
            "message": self.message,
            "robot_id": self.robot_id,
            "data": self.data,
            "source": self.source
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


@dataclass
class AlertConfig:
    """Configuration for alert thresholds."""
    # Severity thresholds for alerts
    alert_on_warning: bool = True
    alert_on_error: bool = True
    alert_on_critical: bool = True
    
    # Rate limiting
    max_alerts_per_minute: int = 60
    duplicate_suppression_seconds: float = 5.0
    
    # Categories to alert on
    alert_categories: Set[EventCategory] = field(default_factory=lambda: {
        EventCategory.SAFETY,
        EventCategory.CONNECTION,
        EventCategory.HEALTH
    })


@dataclass
class EventRecorderConfig:
    """Configuration for EventRecorder."""
    # History settings
    max_events: int = 10000
    max_events_per_category: int = 1000
    
    # Persistence
    persist_events: bool = False
    event_log_dir: str = "/tmp/roc_events"
    
    # Alert configuration
    alerts: AlertConfig = field(default_factory=AlertConfig)
    
    # Export
    enable_json_export: bool = True


AlertCallback = Callable[[ROCEvent], None]


class ROCEventRecorder:
    """
    Centralized event recording and alert system for ROC.
    
    Responsibilities:
    - Record structured events with severity and category
    - Maintain queryable event history
    - Generate alerts for critical events
    - Support event callbacks for external consumers
    - Export events for debugging/auditing
    
    Usage:
        recorder = ROCEventRecorder()
        
        # Record events
        recorder.record_safety_event(
            "estop_triggered",
            "Emergency stop activated",
            robot_id="robot_0",
            severity=EventSeverity.CRITICAL
        )
        
        # Register alert callback
        recorder.on_alert(lambda event: send_to_ui(event))
        
        # Query history
        events = recorder.get_events_by_category(EventCategory.SAFETY)
    """
    
    def __init__(
        self,
        config: Optional[EventRecorderConfig] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize EventRecorder.
        
        Args:
            config: Recorder configuration
            logger: Logger instance
        """
        self.config = config or EventRecorderConfig()
        self.logger = logger or logging.getLogger(__name__)
        
        # Event storage
        self._events: Deque[ROCEvent] = deque(maxlen=self.config.max_events)
        self._events_by_category: Dict[EventCategory, Deque[ROCEvent]] = {
            cat: deque(maxlen=self.config.max_events_per_category)
            for cat in EventCategory
        }
        
        # Alert callbacks
        self._alert_callbacks: List[AlertCallback] = []
        
        # Rate limiting
        self._alert_count_minute = 0
        self._alert_minute_start = time.time()
        self._recent_alerts: Dict[str, float] = {}  # event_type -> last_time
        
        # Statistics
        self._stats = {
            "total_events": 0,
            "events_by_severity": {s.name: 0 for s in EventSeverity},
            "events_by_category": {c.value: 0 for c in EventCategory},
            "alerts_generated": 0,
            "alerts_suppressed": 0
        }
        
        # Persistence
        if self.config.persist_events:
            self._event_log_path = Path(self.config.event_log_dir)
            self._event_log_path.mkdir(parents=True, exist_ok=True)
        
        self.logger.info("ROCEventRecorder initialized")
    
    # =========================================================================
    # EVENT RECORDING
    # =========================================================================
    
    def record_event(
        self,
        category: EventCategory,
        event_type: str,
        message: str,
        severity: EventSeverity = EventSeverity.INFO,
        robot_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> ROCEvent:
        """
        Record a generic event.
        
        Args:
            category: Event category
            event_type: Specific event type
            message: Human-readable message
            severity: Event severity
            robot_id: Optional robot identifier
            data: Additional event data
            
        Returns:
            Created event record
        """
        event = ROCEvent(
            event_id=str(uuid.uuid4())[:8],
            timestamp=time.time(),
            category=category,
            severity=severity,
            event_type=event_type,
            message=message,
            robot_id=robot_id,
            data=data or {}
        )
        
        # Store event
        self._events.append(event)
        self._events_by_category[category].append(event)
        
        # Update stats
        self._stats["total_events"] += 1
        self._stats["events_by_severity"][severity.name] += 1
        self._stats["events_by_category"][category.value] += 1
        
        # Log based on severity
        log_msg = f"[{category.value}] {event_type}: {message}"
        if severity == EventSeverity.DEBUG:
            self.logger.debug(log_msg)
        elif severity == EventSeverity.INFO:
            self.logger.info(log_msg)
        elif severity == EventSeverity.WARNING:
            self.logger.warning(log_msg)
        elif severity == EventSeverity.ERROR:
            self.logger.error(log_msg)
        elif severity == EventSeverity.CRITICAL:
            self.logger.critical(log_msg)
        
        # Persist if enabled
        if self.config.persist_events:
            self._persist_event(event)
        
        # Check if alert needed
        self._maybe_generate_alert(event)
        
        return event
    
    # =========================================================================
    # CONVENIENCE METHODS BY CATEGORY
    # =========================================================================
    
    def record_safety_event(
        self,
        event_type: str,
        message: str,
        robot_id: Optional[str] = None,
        severity: EventSeverity = EventSeverity.WARNING,
        **data
    ) -> ROCEvent:
        """Record a safety-related event."""
        return self.record_event(
            EventCategory.SAFETY, event_type, message,
            severity, robot_id, data
        )
    
    def record_mode_event(
        self,
        event_type: str,
        message: str,
        robot_id: Optional[str] = None,
        severity: EventSeverity = EventSeverity.INFO,
        **data
    ) -> ROCEvent:
        """Record a mode change event."""
        return self.record_event(
            EventCategory.MODE, event_type, message,
            severity, robot_id, data
        )
    
    def record_command_event(
        self,
        event_type: str,
        message: str,
        robot_id: Optional[str] = None,
        severity: EventSeverity = EventSeverity.DEBUG,
        **data
    ) -> ROCEvent:
        """Record a command-related event."""
        return self.record_event(
            EventCategory.COMMAND, event_type, message,
            severity, robot_id, data
        )
    
    def record_connection_event(
        self,
        event_type: str,
        message: str,
        severity: EventSeverity = EventSeverity.INFO,
        **data
    ) -> ROCEvent:
        """Record a connection-related event."""
        return self.record_event(
            EventCategory.CONNECTION, event_type, message,
            severity, None, data
        )
    
    def record_health_event(
        self,
        event_type: str,
        message: str,
        severity: EventSeverity = EventSeverity.WARNING,
        **data
    ) -> ROCEvent:
        """Record a health-related event."""
        return self.record_event(
            EventCategory.HEALTH, event_type, message,
            severity, None, data
        )
    
    def record_robot_event(
        self,
        event_type: str,
        message: str,
        robot_id: str,
        severity: EventSeverity = EventSeverity.INFO,
        **data
    ) -> ROCEvent:
        """Record a robot lifecycle event."""
        return self.record_event(
            EventCategory.ROBOT, event_type, message,
            severity, robot_id, data
        )
    
    def record_integration_event(
        self,
        event_type: str,
        message: str,
        severity: EventSeverity = EventSeverity.INFO,
        **data
    ) -> ROCEvent:
        """Record an integration event."""
        return self.record_event(
            EventCategory.INTEGRATION, event_type, message,
            severity, None, data
        )
    
    def record_system_event(
        self,
        event_type: str,
        message: str,
        severity: EventSeverity = EventSeverity.INFO,
        **data
    ) -> ROCEvent:
        """Record a system event."""
        return self.record_event(
            EventCategory.SYSTEM, event_type, message,
            severity, None, data
        )
    
    # =========================================================================
    # ALERT SYSTEM
    # =========================================================================
    
    def on_alert(self, callback: AlertCallback):
        """
        Register alert callback.
        
        Called when an event meets alert criteria.
        
        Args:
            callback: Function to call with alert event
        """
        self._alert_callbacks.append(callback)
    
    def _maybe_generate_alert(self, event: ROCEvent):
        """Check if event should generate an alert."""
        config = self.config.alerts
        
        # Check severity threshold
        should_alert = False
        if event.severity == EventSeverity.WARNING and config.alert_on_warning:
            should_alert = True
        elif event.severity == EventSeverity.ERROR and config.alert_on_error:
            should_alert = True
        elif event.severity == EventSeverity.CRITICAL and config.alert_on_critical:
            should_alert = True
        
        # Check category
        if event.category not in config.alert_categories:
            should_alert = False
        
        if not should_alert:
            return
        
        # Rate limiting
        current_time = time.time()
        
        # Reset minute counter if needed
        if current_time - self._alert_minute_start > 60:
            self._alert_count_minute = 0
            self._alert_minute_start = current_time
        
        # Check rate limit
        if self._alert_count_minute >= config.max_alerts_per_minute:
            self._stats["alerts_suppressed"] += 1
            return
        
        # Check duplicate suppression
        last_alert_time = self._recent_alerts.get(event.event_type, 0)
        if current_time - last_alert_time < config.duplicate_suppression_seconds:
            self._stats["alerts_suppressed"] += 1
            return
        
        # Generate alert
        self._alert_count_minute += 1
        self._recent_alerts[event.event_type] = current_time
        self._stats["alerts_generated"] += 1
        
        # Call callbacks
        for callback in self._alert_callbacks:
            try:
                callback(event)
            except Exception as e:
                self.logger.error(f"Alert callback error: {e}")
    
    # =========================================================================
    # QUERY METHODS
    # =========================================================================
    
    def get_events(
        self,
        limit: int = 100,
        min_severity: EventSeverity = EventSeverity.DEBUG
    ) -> List[ROCEvent]:
        """
        Get recent events.
        
        Args:
            limit: Maximum events to return
            min_severity: Minimum severity filter
            
        Returns:
            List of events (newest first)
        """
        events = [
            e for e in self._events
            if e.severity.value >= min_severity.value
        ]
        return list(reversed(events[-limit:]))
    
    def get_events_by_category(
        self,
        category: EventCategory,
        limit: int = 100
    ) -> List[ROCEvent]:
        """
        Get events by category.
        
        Args:
            category: Event category
            limit: Maximum events to return
            
        Returns:
            List of events (newest first)
        """
        events = list(self._events_by_category[category])
        return list(reversed(events[-limit:]))
    
    def get_events_by_robot(
        self,
        robot_id: str,
        limit: int = 100
    ) -> List[ROCEvent]:
        """
        Get events for a specific robot.
        
        Args:
            robot_id: Robot identifier
            limit: Maximum events to return
            
        Returns:
            List of events (newest first)
        """
        events = [e for e in self._events if e.robot_id == robot_id]
        return list(reversed(events[-limit:]))
    
    def get_events_since(
        self,
        since_timestamp: float,
        limit: int = 1000
    ) -> List[ROCEvent]:
        """
        Get events since a timestamp.
        
        Args:
            since_timestamp: Unix timestamp
            limit: Maximum events to return
            
        Returns:
            List of events (oldest first)
        """
        events = [e for e in self._events if e.timestamp >= since_timestamp]
        return events[:limit]
    
    def search_events(
        self,
        event_type: Optional[str] = None,
        category: Optional[EventCategory] = None,
        min_severity: Optional[EventSeverity] = None,
        robot_id: Optional[str] = None,
        since: Optional[float] = None,
        limit: int = 100
    ) -> List[ROCEvent]:
        """
        Search events with multiple filters.
        
        Args:
            event_type: Filter by event type (partial match)
            category: Filter by category
            min_severity: Minimum severity
            robot_id: Filter by robot
            since: Events after this timestamp
            limit: Maximum results
            
        Returns:
            List of matching events
        """
        results = []
        
        for event in reversed(list(self._events)):
            if len(results) >= limit:
                break
            
            # Apply filters
            if event_type and event_type not in event.event_type:
                continue
            if category and event.category != category:
                continue
            if min_severity and event.severity.value < min_severity.value:
                continue
            if robot_id and event.robot_id != robot_id:
                continue
            if since and event.timestamp < since:
                continue
            
            results.append(event)
        
        return results
    
    # =========================================================================
    # PERSISTENCE
    # =========================================================================
    
    def _persist_event(self, event: ROCEvent):
        """Write event to log file."""
        try:
            date_str = datetime.fromtimestamp(event.timestamp).strftime("%Y-%m-%d")
            log_file = self._event_log_path / f"roc_events_{date_str}.jsonl"
            
            with open(log_file, "a") as f:
                f.write(event.to_json() + "\n")
        except Exception as e:
            self.logger.error(f"Failed to persist event: {e}")
    
    def export_events(
        self,
        filepath: str,
        events: Optional[List[ROCEvent]] = None
    ) -> bool:
        """
        Export events to JSON file.
        
        Args:
            filepath: Output file path
            events: Events to export (defaults to all)
            
        Returns:
            True if successful
        """
        try:
            if events is None:
                events = list(self._events)
            
            data = {
                "export_time": datetime.now().isoformat(),
                "event_count": len(events),
                "events": [e.to_dict() for e in events]
            }
            
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
            
            self.logger.info(f"Exported {len(events)} events to {filepath}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to export events: {e}")
            return False
    
    # =========================================================================
    # STATUS
    # =========================================================================
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get event recorder statistics."""
        return {
            **self._stats,
            "current_event_count": len(self._events),
            "events_per_category": {
                cat.value: len(self._events_by_category[cat])
                for cat in EventCategory
            }
        }
    
    def clear_history(self):
        """Clear all event history."""
        self._events.clear()
        for cat in EventCategory:
            self._events_by_category[cat].clear()
        self.logger.info("Event history cleared")
