"""
event_recorder.py
ROA - Robot Operations & Automation
Event recording system
"""

import logging
import json
import os
from datetime import datetime
from typing import Dict, Any, List


class EventRecorder:
    """Records system events for later analysis"""

    def __init__(self, log_dir: str = "./Logs"):
        """
        Initialize Event Recorder
        
        Args:
            log_dir: Directory for event logs
        """
        self.logger = logging.getLogger(__name__)
        self.log_dir = log_dir
        self.events: List[Dict[str, Any]] = []
        
        os.makedirs(log_dir, exist_ok=True)
        self.logger.info("EventRecorder initialized")

    def record_event(self, event_type: str, data: Dict[str, Any]):
        """
        Record an event
        
        Args:
            event_type: Type of event
            data: Event data
        """
        event = {
            'timestamp': datetime.now().isoformat(),
            'type': event_type,
            'data': data
        }
        self.events.append(event)
        self.logger.debug(f"Recorded event: {event_type}")

    def save_events(self, filename: Optional[str] = None):
        """Save events to file"""
        if filename is None:
            filename = f"events_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        filepath = os.path.join(self.log_dir, filename)
        
        try:
            with open(filepath, 'w') as f:
                json.dump(self.events, f, indent=2)
            self.logger.info(f"Saved {len(self.events)} events to {filepath}")
        except Exception as e:
            self.logger.error(f"Failed to save events: {e}")

    def clear_events(self):
        """Clear recorded events"""
        self.events.clear()
        self.logger.info("Cleared event history")
