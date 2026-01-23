"""
Component State Machine

Manages COMC component states and transitions for health monitoring and recovery.
"""

from enum import Enum
from typing import Optional
import time


class ComponentState(Enum):
    """Component operational states."""
    DISCONNECTED = "disconnected"  # Not connected to Webthread
    CONNECTING = "connecting"      # Attempting connection
    IDLE = "idle"                  # Connected but no robots active
    ACTIVE = "active"              # Actively coordinating robots
    DEGRADED = "degraded"          # Operational but with issues
    ERROR = "error"                # Error state, attempting recovery
    SHUTDOWN = "shutdown"          # Shutting down


class COMCStateMachine:
    """
    State machine for COMC component lifecycle management.
    """
    
    # Valid state transitions
    VALID_TRANSITIONS = {
        ComponentState.DISCONNECTED: [ComponentState.CONNECTING, ComponentState.SHUTDOWN],
        ComponentState.CONNECTING: [ComponentState.IDLE, ComponentState.ERROR, ComponentState.DISCONNECTED],
        ComponentState.IDLE: [ComponentState.ACTIVE, ComponentState.DEGRADED, ComponentState.ERROR, ComponentState.SHUTDOWN],
        ComponentState.ACTIVE: [ComponentState.IDLE, ComponentState.DEGRADED, ComponentState.ERROR, ComponentState.SHUTDOWN],
        ComponentState.DEGRADED: [ComponentState.ACTIVE, ComponentState.IDLE, ComponentState.ERROR, ComponentState.SHUTDOWN],
        ComponentState.ERROR: [ComponentState.IDLE, ComponentState.CONNECTING, ComponentState.SHUTDOWN],
        ComponentState.SHUTDOWN: []  # Terminal state
    }
    
    def __init__(self, logger):
        """
        Initialize state machine.
        
        Args:
            logger: ROS2 logger instance
        """
        self.logger = logger
        self.current_state = ComponentState.DISCONNECTED
        self.previous_state: Optional[ComponentState] = None
        self.state_enter_time = time.time()
        self.error_count = 0
        self.error_streak = 0  # Consecutive errors
        self.max_error_streak = 3  # Shutdown after 3 consecutive errors
        
    def transition_to(self, new_state: ComponentState) -> bool:
        """
        Attempt to transition to a new state.
        
        Args:
            new_state: Target state
            
        Returns:
            True if transition successful, False if invalid
        """
        if new_state == self.current_state:
            self.logger.debug(f"Already in state {new_state.value}")
            return True
            
        if new_state not in self.VALID_TRANSITIONS[self.current_state]:
            self.logger.error(
                f"Invalid transition: {self.current_state.value} → {new_state.value}"
            )
            return False
            
        # Log transition
        self.logger.info(
            f"State transition: {self.current_state.value} → {new_state.value}"
        )
        
        # Update states
        self.previous_state = self.current_state
        self.current_state = new_state
        self.state_enter_time = time.time()
        
        # Handle error streak
        if new_state == ComponentState.ERROR:
            self.error_count += 1
            self.error_streak += 1
            
            if self.error_streak >= self.max_error_streak:
                self.logger.error(
                    f"Error streak reached {self.max_error_streak}, forcing shutdown"
                )
                self.transition_to(ComponentState.SHUTDOWN)
        else:
            # Reset error streak on successful transition
            if self.previous_state == ComponentState.ERROR:
                self.error_streak = 0
                
        return True
        
    def get_state(self) -> ComponentState:
        """Get current state."""
        return self.current_state
        
    def get_time_in_state(self) -> float:
        """Get time spent in current state (seconds)."""
        return time.time() - self.state_enter_time
        
    def can_coordinate(self) -> bool:
        """Check if COMC can coordinate robots in current state."""
        return self.current_state in [
            ComponentState.IDLE,
            ComponentState.ACTIVE,
            ComponentState.DEGRADED
        ]
        
    def should_retry_connection(self) -> bool:
        """Check if should retry connection to Webthread."""
        return self.current_state in [
            ComponentState.DISCONNECTED,
            ComponentState.CONNECTING,
            ComponentState.ERROR
        ]
        
    def is_healthy(self) -> bool:
        """Check if component is in healthy state."""
        return self.current_state in [
            ComponentState.IDLE,
            ComponentState.ACTIVE
        ]
        
    def get_status_string(self) -> str:
        """Get human-readable status string."""
        status_map = {
            ComponentState.DISCONNECTED: "DISCONNECTED",
            ComponentState.CONNECTING: "CONNECTING",
            ComponentState.IDLE: "HEALTHY",
            ComponentState.ACTIVE: "HEALTHY",
            ComponentState.DEGRADED: "DEGRADED",
            ComponentState.ERROR: "ERROR",
            ComponentState.SHUTDOWN: "SHUTDOWN"
        }
        return status_map.get(self.current_state, "UNKNOWN")
