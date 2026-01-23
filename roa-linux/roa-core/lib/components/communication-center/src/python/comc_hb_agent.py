"""
comc_hb_agent.py
ROA - Robot Operations & Automation
COMC Heartbeat Agent Integration

This module provides the HB (Heartbeat) subsystem integration for COMC.
It wraps the core HBAgent and provides COMC-specific activity reporting.

Port: 9880 (dedicated to COMC as defined in hb_types.py)
"""

import os
import sys
import logging
import threading
from typing import Optional, Callable, Dict, Any
from enum import Enum

# Add HB subsystem to path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_hb_subsystem_path = os.path.abspath(os.path.join(
    _current_dir, '..', '..', '..', '..', 
    'webthread', 'src', 'python', 'hb_subsystem'
))
if _hb_subsystem_path not in sys.path:
    sys.path.insert(0, _hb_subsystem_path)

try:
    from hb_agent import HBAgent
    from hb_types import (
        HBPorts,
        ActivityType,
        ComponentState,
        HealthLevel
    )
    HB_AVAILABLE = True
except ImportError as e:
    logging.warning(f"HB Subsystem not available: {e}")
    HB_AVAILABLE = False
    
    # Fallback types when HB subsystem not available
    class ActivityType(Enum):
        MESSAGE_PROCESSED = ("msg_proc", 1)
        COMMAND_EXECUTED = ("cmd_exec", 1)
        STATE_TRANSITION = ("state_trans", 1)
        DATA_SENT = ("data_sent", 2)
        DATA_RECEIVED = ("data_recv", 2)
        CHANNEL_ACTIVE = ("chan_active", 4)
        PEER_RESPONDED = ("peer_resp", 4)
        IDLE_ACKNOWLEDGED = ("idle_ack", 1)
        
    class ComponentState(Enum):
        UNKNOWN = 0
        INITIALIZING = 1
        ACTIVE = 2
        IDLE = 3
        BUSY = 4
        ERROR = 5
        SHUTTING_DOWN = 6
        
    class HealthLevel(Enum):
        HEALTHY = 0
        DEGRADED = 1
        UNHEALTHY = 2


class COMCHBAgent:
    """
    COMC Heartbeat Agent - Integrates COMC with the HB Subsystem.
    
    Provides:
    - Automatic heartbeat generation when activities occur
    - COMC-specific activity reporting (channels, peers, coordination)
    - Autonomous mode handling when Webthread is unreachable
    - Connection state callbacks
    
    Usage:
        hb_agent = COMCHBAgent(logger=node.get_logger())
        hb_agent.start()
        
        # After processing a message:
        hb_agent.report_message_processed(message_id="msg_123")
        
        # After coordination:
        hb_agent.report_coordination_activity(robot_count=5)
        
        # When idle:
        hb_agent.report_idle("no_pending_tasks")
        
        # On shutdown:
        hb_agent.stop()
    """
    
    # COMC dedicated port
    COMC_PORT = 9880  # From hb_types.HBPorts.COMC
    
    def __init__(
        self,
        receiver_host: str = '127.0.0.1',
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize COMC HB Agent.
        
        Args:
            receiver_host: HB receiver (Webthread) host address
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger("COMCHBAgent")
        self.receiver_host = receiver_host
        
        self._agent: Optional[HBAgent] = None
        self._running = False
        self._lock = threading.Lock()
        
        # Callbacks
        self._on_autonomous_mode: Optional[Callable[[], None]] = None
        self._on_connection_lost: Optional[Callable[[], None]] = None
        self._on_connection_restored: Optional[Callable[[], None]] = None
        
        # Activity counters (for metrics)
        self._activity_counts = {
            'messages_processed': 0,
            'commands_executed': 0,
            'data_sent': 0,
            'data_received': 0,
            'channels_active': 0,
            'peers_responded': 0,
            'coordination_events': 0,
            'state_transitions': 0,
        }
        
        self.logger.info(f"COMCHBAgent initialized (port: {self.COMC_PORT})")
    
    # =========================================================================
    # LIFECYCLE
    # =========================================================================
    
    def start(self) -> bool:
        """
        Start the COMC HB Agent.
        
        Creates the underlying HBAgent and begins heartbeat transmission.
        
        Returns:
            True if started successfully
        """
        with self._lock:
            if self._running:
                self.logger.warning("COMCHBAgent already running")
                return True
            
            if not HB_AVAILABLE:
                self.logger.warning("HB Subsystem not available, running in standalone mode")
                self._running = True
                return True
            
            try:
                # Create core HBAgent
                self._agent = HBAgent(
                    component_name='COMC',
                    receiver_host=self.receiver_host,
                    receiver_port=self.COMC_PORT,
                    logger=self.logger
                )
                
                # Register callbacks
                if self._on_autonomous_mode:
                    self._agent.on_autonomous_mode(self._on_autonomous_mode)
                if self._on_connection_lost:
                    self._agent.on_connection_lost(self._on_connection_lost)
                if self._on_connection_restored:
                    self._agent.on_connection_restored(self._on_connection_restored)
                
                # Start agent
                if self._agent.start():
                    self._running = True
                    self.logger.info("COMCHBAgent started successfully")
                    return True
                else:
                    self.logger.error("Failed to start COMCHBAgent")
                    return False
                    
            except Exception as e:
                self.logger.error(f"Error starting COMCHBAgent: {e}")
                return False
    
    def stop(self):
        """Stop the COMC HB Agent."""
        with self._lock:
            if not self._running:
                return
            
            if self._agent:
                self._agent.stop()
                self._agent = None
            
            self._running = False
            self.logger.info("COMCHBAgent stopped")
    
    def is_running(self) -> bool:
        """Check if agent is running."""
        return self._running
    
    def is_connected(self) -> bool:
        """Check if connected to HB receiver (Webthread)."""
        if self._agent:
            return self._agent.is_connected()
        return False
    
    def is_autonomous(self) -> bool:
        """Check if in autonomous mode (Webthread unreachable)."""
        if self._agent:
            return self._agent.is_autonomous()
        return True  # Standalone mode = autonomous
    
    # =========================================================================
    # ACTIVITY REPORTING - COMC Specific
    # =========================================================================
    
    def report_message_processed(self, message_id: Optional[str] = None):
        """
        Report that a message was processed.
        Call after handling any incoming message.
        
        Args:
            message_id: Optional message identifier for proof
        """
        self._report_activity(ActivityType.MESSAGE_PROCESSED, proof=message_id)
        self._activity_counts['messages_processed'] += 1
    
    def report_command_executed(self, command: str):
        """
        Report that a command was executed.
        Call after executing coordination commands.
        
        Args:
            command: The command that was executed
        """
        self._report_activity(ActivityType.COMMAND_EXECUTED, proof=command)
        self._activity_counts['commands_executed'] += 1
    
    def report_data_sent(self, destination: Optional[str] = None):
        """
        Report that data was sent to another component or robot.
        
        Args:
            destination: Target component/robot
        """
        self._report_activity(ActivityType.DATA_SENT, proof=destination)
        self._activity_counts['data_sent'] += 1
    
    def report_data_received(self, source: Optional[str] = None):
        """
        Report that data was received from another component or robot.
        
        Args:
            source: Source component/robot
        """
        self._report_activity(ActivityType.DATA_RECEIVED, proof=source)
        self._activity_counts['data_received'] += 1
    
    def report_channel_active(self, channel_id: str):
        """
        Report that a communication channel is active.
        COMC-specific activity.
        
        Args:
            channel_id: The active channel identifier
        """
        self._report_activity(ActivityType.CHANNEL_ACTIVE, proof=channel_id)
        self._activity_counts['channels_active'] += 1
    
    def report_peer_responded(self, peer_id: str):
        """
        Report that a peer robot responded.
        COMC-specific activity.
        
        Args:
            peer_id: The responding peer robot ID
        """
        self._report_activity(ActivityType.PEER_RESPONDED, proof=peer_id)
        self._activity_counts['peers_responded'] += 1
    
    def report_coordination_activity(
        self,
        activity_type: str = "coordination",
        robot_count: int = 0
    ):
        """
        Report general coordination activity.
        
        Args:
            activity_type: Type of coordination (e.g., "work_area", "proximity")
            robot_count: Number of robots involved
        """
        proof = f"{activity_type}:robots={robot_count}"
        self._report_activity(ActivityType.MESSAGE_PROCESSED, proof=proof)
        self._activity_counts['coordination_events'] += 1
    
    def report_state_transition(self, from_state: str, to_state: str):
        """
        Report a state transition.
        
        Args:
            from_state: Previous state
            to_state: New state
        """
        proof = f"{from_state}->{to_state}"
        self._report_activity(ActivityType.STATE_TRANSITION, proof=proof)
        self._activity_counts['state_transitions'] += 1
    
    def report_idle(self, reason: str):
        """
        Report that COMC is legitimately idle.
        
        Args:
            reason: Reason for being idle (e.g., "no_robots_registered")
        """
        if self._agent:
            self._agent.report_idle(reason)
            self.logger.debug(f"Idle reported: {reason}")
    
    def report_error(self, error: Optional[Exception] = None):
        """
        Report an error occurred.
        
        Args:
            error: The exception that occurred
        """
        if self._agent:
            self._agent.report_error(error)
    
    # =========================================================================
    # STATE MANAGEMENT
    # =========================================================================
    
    def set_state(self, state: ComponentState):
        """
        Update component state.
        
        Args:
            state: New component state
        """
        if self._agent:
            self._agent.set_state(state)
        self.logger.debug(f"State set to: {state.name if hasattr(state, 'name') else state}")
    
    def set_health(self, health: HealthLevel):
        """
        Update component health level.
        
        Args:
            health: New health level
        """
        if self._agent:
            self._agent.set_health(health)
    
    def set_queue_depth(self, depth: int):
        """
        Update current queue depth for monitoring.
        
        Args:
            depth: Number of pending items in queue
        """
        if self._agent:
            self._agent.set_queue_depth(depth)
    
    def set_response_time(self, time_us: int):
        """
        Update last operation response time.
        
        Args:
            time_us: Response time in microseconds
        """
        if self._agent:
            self._agent.set_response_time(time_us)
    
    # =========================================================================
    # CALLBACKS
    # =========================================================================
    
    def on_autonomous_mode(self, callback: Callable[[], None]):
        """
        Register callback for when autonomous mode is triggered.
        
        Called when Webthread becomes unreachable and COMC should
        operate independently.
        
        Args:
            callback: Function to call on autonomous mode
        """
        self._on_autonomous_mode = callback
        if self._agent:
            self._agent.on_autonomous_mode(callback)
    
    def on_connection_lost(self, callback: Callable[[], None]):
        """
        Register callback for when connection to Webthread is lost.
        
        Args:
            callback: Function to call on connection lost
        """
        self._on_connection_lost = callback
        if self._agent:
            self._agent.on_connection_lost(callback)
    
    def on_connection_restored(self, callback: Callable[[], None]):
        """
        Register callback for when connection is restored.
        
        Args:
            callback: Function to call on connection restored
        """
        self._on_connection_restored = callback
        if self._agent:
            self._agent.on_connection_restored(callback)
    
    # =========================================================================
    # METRICS
    # =========================================================================
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get agent metrics.
        
        Returns:
            Dictionary of agent metrics
        """
        base_metrics = {
            'running': self._running,
            'connected': self.is_connected(),
            'autonomous': self.is_autonomous(),
            'activity_counts': self._activity_counts.copy(),
        }
        
        if self._agent:
            agent_metrics = self._agent.get_metrics()
            base_metrics.update(agent_metrics)
        
        return base_metrics
    
    # =========================================================================
    # INTERNAL
    # =========================================================================
    
    def _report_activity(self, activity_type: ActivityType, proof: Optional[str] = None):
        """Internal method to report activity to HBAgent."""
        if self._agent:
            self._agent.report_activity(activity_type, proof)
            self.logger.debug(f"Activity reported: {activity_type}")
        elif self._running:
            # Standalone mode - just log
            self.logger.debug(f"Activity (standalone): {activity_type}, proof: {proof}")


# =============================================================================
# CONVENIENCE CONTEXT MANAGER
# =============================================================================

class COMCHBContext:
    """
    Context manager for automatic activity timing.
    
    Usage:
        with COMCHBContext(hb_agent, "process_message") as ctx:
            # Do work
            result = process_message(msg)
            ctx.set_proof(f"msg_id={msg.id}")
    """
    
    def __init__(
        self,
        agent: COMCHBAgent,
        activity_name: str,
        activity_type: ActivityType = ActivityType.COMMAND_EXECUTED
    ):
        self.agent = agent
        self.activity_name = activity_name
        self.activity_type = activity_type
        self._start_time = 0
        self._proof = None
    
    def __enter__(self):
        import time
        self._start_time = time.perf_counter_ns()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        elapsed_us = (time.perf_counter_ns() - self._start_time) // 1000
        
        if exc_type is None:
            # Success
            self.agent._report_activity(
                self.activity_type,
                proof=self._proof or self.activity_name
            )
            self.agent.set_response_time(elapsed_us)
        else:
            # Error occurred
            self.agent.report_error(exc_val)
        
        return False  # Don't suppress exceptions
    
    def set_proof(self, proof: str):
        """Set the proof data for this activity."""
        self._proof = proof
