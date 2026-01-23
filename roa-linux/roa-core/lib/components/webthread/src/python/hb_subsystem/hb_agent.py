"""
hb_agent.py
ROA - Robot Operations & Automation
Heartbeat Agent - Embedded in each component for legitimate heartbeat generation

This agent is embedded in each component and generates heartbeats ONLY when
real work is being done. This prevents "fake" heartbeats from timer-based
systems where a dead component might still send heartbeats.

Key Features:
- Activity-based heartbeat generation (proof of work)
- Startup handshake with receiver
- Idle acknowledgment for legitimate idle periods
- Sequence number management with rollover handling
- Resource usage tracking (memory, CPU, queue depth)
"""

import socket
import threading
import time
import psutil
import os
import logging
from typing import Optional, List, Callable, Dict, Any
from collections import deque
from dataclasses import dataclass

from .hb_types import (
    ActivityType, ActivityCategory, validate_activities,
    ComponentState, HealthLevel,
    HeartbeatPacket, StartupPing, StartupAck,
    HBTiming, HBPorts, ComponentID,
    get_timestamp_us, activity_to_bitmap
)


@dataclass
class ActivityRecord:
    """Record of a single activity"""
    activity_type: ActivityType
    timestamp: float
    proof: Optional[str] = None  # Optional proof data


class HBAgentState:
    """Thread-safe state container for HB Agent"""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._activities: deque = deque(maxlen=100)  # Last 100 activities
        self._last_activity_time: float = 0.0
        self._activity_count: int = 0
        self._current_state: ComponentState = ComponentState.UNCONFIGURED
        self._current_health: HealthLevel = HealthLevel.OPTIMAL
        self._error_count: int = 0
        self._last_response_time_us: int = 0
        self._queue_depth: int = 0
        self._sequence: int = 0
        self._is_idle: bool = False
        self._idle_reason: str = ""
        
    def record_activity(self, activity: ActivityType, proof: Optional[str] = None):
        """Thread-safe activity recording"""
        with self._lock:
            record = ActivityRecord(activity, time.time(), proof)
            self._activities.append(record)
            self._last_activity_time = time.time()
            self._activity_count += 1
            # Only reset idle if this is not an idle acknowledgment
            if activity != ActivityType.IDLE_ACKNOWLEDGED:
                self._is_idle = False
    
    def get_recent_activities(self, window_ms: float) -> List[ActivityType]:
        """Get activities within time window"""
        with self._lock:
            cutoff = time.time() - (window_ms / 1000.0)
            return [
                r.activity_type for r in self._activities 
                if r.timestamp >= cutoff
            ]
    
    def has_recent_activity(self, window_ms: float) -> bool:
        """Check if any activity occurred within window"""
        with self._lock:
            return (time.time() - self._last_activity_time) * 1000 < window_ms
    
    def set_idle(self, reason: str):
        """Mark component as legitimately idle"""
        with self._lock:
            self._is_idle = True
            self._idle_reason = reason
    
    def is_idle(self) -> bool:
        """Check if component is in idle state"""
        with self._lock:
            return self._is_idle
    
    def get_idle_reason(self) -> str:
        """Get reason for idle state"""
        with self._lock:
            return self._idle_reason
    
    def next_sequence(self) -> int:
        """Get and increment sequence number (wraps at 65535)"""
        with self._lock:
            seq = self._sequence
            self._sequence = (self._sequence + 1) % 65536
            return seq
    
    def set_state(self, state: ComponentState):
        with self._lock:
            self._current_state = state
    
    def get_state(self) -> ComponentState:
        with self._lock:
            return self._current_state
    
    def set_health(self, health: HealthLevel):
        with self._lock:
            self._current_health = health
    
    def get_health(self) -> HealthLevel:
        with self._lock:
            return self._current_health
    
    def increment_error(self):
        with self._lock:
            self._error_count += 1
    
    def get_error_count(self) -> int:
        with self._lock:
            return self._error_count
    
    def reset_errors(self):
        with self._lock:
            self._error_count = 0
    
    def set_response_time(self, time_us: int):
        with self._lock:
            self._last_response_time_us = time_us
    
    def get_response_time(self) -> int:
        with self._lock:
            return self._last_response_time_us
    
    def set_queue_depth(self, depth: int):
        with self._lock:
            self._queue_depth = depth
    
    def get_queue_depth(self) -> int:
        with self._lock:
            return self._queue_depth


class HBAgent:
    """
    Heartbeat Agent - Embedded in each component.
    
    Generates legitimate heartbeats only when real work is being done.
    A component that is dead cannot generate heartbeats because it cannot
    call report_activity().
    
    Usage:
        agent = HBAgent('FTI')
        agent.start()
        
        # In your component code, after doing work:
        agent.report_activity(ActivityType.MESSAGE_PROCESSED)
        
        # When legitimately idle:
        agent.report_idle("waiting_for_input")
        
        # On shutdown:
        agent.stop()
    """
    
    def __init__(
        self,
        component_name: str,
        receiver_host: str = '127.0.0.1',
        receiver_port: Optional[int] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize HB Agent.
        
        Args:
            component_name: Name of the component (e.g., 'FTI', 'ROC')
            receiver_host: HB receiver host address
            receiver_port: HB receiver port (auto-assigned if None)
            logger: Optional logger instance
        """
        self.component_name = component_name
        self.component_id = ComponentID.BY_NAME.get(component_name, 0)
        self.receiver_host = receiver_host
        self.receiver_port = receiver_port or HBPorts.BY_COMPONENT.get(component_name, HBPorts.BASE_PORT)
        
        self.logger = logger or logging.getLogger(f"HBAgent.{component_name}")
        
        # State
        self.state = HBAgentState()
        self._running = False
        self._connected = False
        self._autonomous_mode = False
        
        # Threading
        self._hb_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Socket
        self._socket: Optional[socket.socket] = None
        
        # Callbacks
        self._on_autonomous_mode: Optional[Callable[[], None]] = None
        self._on_connection_lost: Optional[Callable[[], None]] = None
        self._on_connection_restored: Optional[Callable[[], None]] = None
        
        # Metrics
        self._hb_sent_count = 0
        self._hb_skipped_count = 0
        self._last_hb_time = 0.0
        
        # Process handle for resource monitoring
        self._process = psutil.Process(os.getpid())
        
        self.logger.info(f"HBAgent initialized for {component_name} (ID: {self.component_id})")
    
    # =========================================================================
    # PUBLIC API - Activity Reporting
    # =========================================================================
    
    def report_activity(self, activity_type: ActivityType, proof: Optional[str] = None):
        """
        Report that the component performed real work.
        
        This is the core of the "legitimate heartbeat" system.
        Call this after completing actual work.
        
        Args:
            activity_type: Type of activity performed
            proof: Optional proof data (e.g., message ID, operation result)
        """
        self.state.record_activity(activity_type, proof)
        self.logger.debug(f"Activity recorded: {activity_type.code}")
    
    def report_idle(self, reason: str):
        """
        Report that the component is legitimately idle.
        
        This allows the component to keep sending heartbeats during
        intentional idle periods (e.g., waiting for work).
        
        Args:
            reason: Reason for being idle (e.g., "no_pending_conversions")
        """
        self.state.set_idle(reason)
        self.state.record_activity(ActivityType.IDLE_ACKNOWLEDGED, proof=reason)
        self.logger.debug(f"Idle acknowledged: {reason}")
    
    def report_error(self, error: Optional[Exception] = None):
        """Report an error occurred"""
        self.state.increment_error()
        if error:
            self.logger.warning(f"Error reported: {error}")
    
    def set_state(self, state: ComponentState):
        """Update component state"""
        old_state = self.state.get_state()
        self.state.set_state(state)
        if old_state != state:
            self.state.record_activity(ActivityType.STATE_TRANSITION, 
                                       proof=f"{old_state.name}->{state.name}")
            self.logger.info(f"State transition: {old_state.name} -> {state.name}")
    
    def set_health(self, health: HealthLevel):
        """Update component health level"""
        self.state.set_health(health)
    
    def set_response_time(self, time_us: int):
        """Update last operation response time in microseconds"""
        self.state.set_response_time(time_us)
    
    def set_queue_depth(self, depth: int):
        """Update current queue depth"""
        self.state.set_queue_depth(depth)
    
    # =========================================================================
    # PUBLIC API - Lifecycle
    # =========================================================================
    
    def start(self) -> bool:
        """
        Start the HB Agent.
        
        Performs startup handshake with receiver, then begins heartbeat loop.
        
        Returns:
            True if started successfully
        """
        if self._running:
            self.logger.warning("HB Agent already running")
            return True
        
        self.logger.info("Starting HB Agent...")
        
        # Create UDP socket
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.settimeout(0.1)  # 100ms timeout for receives
        except socket.error as e:
            self.logger.error(f"Failed to create socket: {e}")
            return False
        
        # Perform startup handshake
        if not self._startup_handshake():
            self.logger.warning("Startup handshake failed, proceeding anyway (receiver may start later)")
            # Don't fail completely - receiver might start later
        
        # Start heartbeat thread
        self._running = True
        self._stop_event.clear()
        self._hb_thread = threading.Thread(target=self._hb_loop, daemon=True)
        self._hb_thread.name = f"HBAgent-{self.component_name}"
        self._hb_thread.start()
        
        self.state.set_state(ComponentState.ACTIVE)
        self.logger.info("HB Agent started successfully")
        return True
    
    def stop(self):
        """Stop the HB Agent"""
        if not self._running:
            return
        
        self.logger.info("Stopping HB Agent...")
        
        self._running = False
        self._stop_event.set()
        
        # Wait for thread to finish
        if self._hb_thread and self._hb_thread.is_alive():
            self._hb_thread.join(timeout=1.0)
        
        # Close socket
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
            self._socket = None
        
        self.state.set_state(ComponentState.SHUTTING_DOWN)
        self.logger.info("HB Agent stopped")
    
    def is_running(self) -> bool:
        """Check if agent is running"""
        return self._running
    
    def is_connected(self) -> bool:
        """Check if connected to receiver"""
        return self._connected
    
    def is_autonomous(self) -> bool:
        """Check if in autonomous mode (WT unreachable)"""
        return self._autonomous_mode
    
    # =========================================================================
    # CALLBACKS
    # =========================================================================
    
    def on_autonomous_mode(self, callback: Callable[[], None]):
        """Register callback for when autonomous mode is triggered"""
        self._on_autonomous_mode = callback
    
    def on_connection_lost(self, callback: Callable[[], None]):
        """Register callback for when connection to receiver is lost"""
        self._on_connection_lost = callback
    
    def on_connection_restored(self, callback: Callable[[], None]):
        """Register callback for when connection is restored"""
        self._on_connection_restored = callback
    
    # =========================================================================
    # METRICS
    # =========================================================================
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get agent metrics"""
        return {
            'component_name': self.component_name,
            'component_id': self.component_id,
            'running': self._running,
            'connected': self._connected,
            'autonomous_mode': self._autonomous_mode,
            'hb_sent_count': self._hb_sent_count,
            'hb_skipped_count': self._hb_skipped_count,
            'last_hb_time': self._last_hb_time,
            'current_state': self.state.get_state().name,
            'current_health': self.state.get_health().name,
            'error_count': self.state.get_error_count(),
        }
    
    # =========================================================================
    # INTERNAL - Startup Handshake
    # =========================================================================
    
    def _startup_handshake(self) -> bool:
        """
        Perform startup handshake with receiver.
        
        Sends startup ping and waits for acknowledgment.
        Retries up to 3 times.
        
        Returns:
            True if handshake successful
        """
        for attempt in range(3):
            try:
                # Send startup ping
                ping = StartupPing(
                    component_id=self.component_id,
                    timestamp=get_timestamp_us()
                )
                self._socket.sendto(
                    ping.to_bytes(),
                    (self.receiver_host, self.receiver_port)
                )
                self.logger.debug(f"Sent startup ping (attempt {attempt + 1})")
                
                # Wait for acknowledgment
                try:
                    data, addr = self._socket.recvfrom(64)
                    ack = StartupAck.from_bytes(data)
                    
                    if ack and ack.component_id == self.component_id:
                        self._connected = True
                        self.logger.info(f"Startup handshake successful, port: {ack.port_assigned}")
                        return True
                except socket.timeout:
                    self.logger.debug(f"Handshake timeout (attempt {attempt + 1})")
                    continue
                
            except socket.error as e:
                self.logger.warning(f"Handshake error: {e}")
                time.sleep(0.1)
        
        return False
    
    # =========================================================================
    # INTERNAL - Heartbeat Loop
    # =========================================================================
    
    def _hb_loop(self):
        """
        Main heartbeat loop.
        
        Only sends heartbeats when there's recent activity (or idle acknowledged).
        This ensures heartbeats are "legitimate" - a dead component cannot send them.
        """
        self.logger.debug("Heartbeat loop started")
        interval_s = HBTiming.TARGET_INTERVAL_MS / 1000.0
        consecutive_send_failures = 0
        
        while self._running and not self._stop_event.is_set():
            loop_start = time.time()
            
            try:
                # Check if we should send a heartbeat
                should_send = self._should_send_heartbeat()
                
                if should_send:
                    success = self._send_heartbeat()
                    if success:
                        self._hb_sent_count += 1
                        consecutive_send_failures = 0
                        self._last_hb_time = time.time()
                    else:
                        consecutive_send_failures += 1
                else:
                    self._hb_skipped_count += 1
                    self.logger.debug("Heartbeat skipped - no recent activity")
                
                # Check for autonomous mode trigger
                if consecutive_send_failures >= 20:  # ~500ms of failures
                    if not self._autonomous_mode:
                        self._enter_autonomous_mode()
                
            except Exception as e:
                self.logger.error(f"Error in HB loop: {e}")
                self.state.increment_error()
            
            # Sleep for remaining interval time
            elapsed = time.time() - loop_start
            sleep_time = max(0, interval_s - elapsed)
            if sleep_time > 0:
                self._stop_event.wait(sleep_time)
        
        self.logger.debug("Heartbeat loop ended")
    
    def _should_send_heartbeat(self) -> bool:
        """
        Determine if we should send a heartbeat.
        
        Only returns True if there's been recent activity or
        the component has acknowledged being idle.
        
        Returns:
            True if heartbeat should be sent
        """
        # Get recent activities
        activities = self.state.get_recent_activities(HBTiming.ACTIVITY_WINDOW_MS)
        
        # Validate activities
        if validate_activities(activities):
            return True
        
        # Check for idle acknowledgment
        if self.state.is_idle():
            return True
        
        return False
    
    def _send_heartbeat(self) -> bool:
        """
        Build and send heartbeat packet.
        
        Returns:
            True if sent successfully
        """
        if not self._socket:
            return False
        
        try:
            # Get resource usage
            mem_percent, cpu_percent = self._get_resource_usage()
            
            # Get recent activities for bitmap
            activities = self.state.get_recent_activities(HBTiming.ACTIVITY_WINDOW_MS)
            activity_bitmap = activity_to_bitmap(activities)
            
            # Build packet
            packet = HeartbeatPacket(
                component_id=self.component_id,
                timestamp=get_timestamp_us(),
                sequence=self.state.next_sequence(),
                state=self.state.get_state(),
                health=self.state.get_health(),
                response_time_us=self.state.get_response_time(),
                error_count=min(self.state.get_error_count(), 65535),  # Cap at uint16 max
                memory_percent=mem_percent,
                cpu_percent=cpu_percent,
                queue_depth=min(self.state.get_queue_depth(), 65535),
                activity_bitmap=activity_bitmap
            )
            
            # Send
            self._socket.sendto(
                packet.to_bytes(),
                (self.receiver_host, self.receiver_port)
            )
            
            return True
            
        except socket.error as e:
            self.logger.warning(f"Failed to send heartbeat: {e}")
            return False
    
    def _get_resource_usage(self) -> tuple:
        """Get current memory and CPU usage as percentages (0-100)"""
        try:
            mem_percent = int(self._process.memory_percent())
            cpu_percent = int(self._process.cpu_percent(interval=None))  # Non-blocking
            return (
                min(max(mem_percent, 0), 100),
                min(max(cpu_percent, 0), 100)
            )
        except:
            return (0, 0)
    
    def _enter_autonomous_mode(self):
        """Enter autonomous mode when WT/receiver is unreachable"""
        self.logger.warning("Entering autonomous mode - receiver unreachable")
        self._autonomous_mode = True
        self.state.set_state(ComponentState.AUTONOMOUS)
        
        if self._on_autonomous_mode:
            try:
                self._on_autonomous_mode()
            except Exception as e:
                self.logger.error(f"Error in autonomous mode callback: {e}")
        
        if self._on_connection_lost:
            try:
                self._on_connection_lost()
            except Exception as e:
                self.logger.error(f"Error in connection lost callback: {e}")


# =============================================================================
# CONVENIENCE CONTEXT MANAGER
# =============================================================================

class ActivityScope:
    """
    Context manager for automatic activity reporting.
    
    Usage:
        with ActivityScope(agent, ActivityType.MESSAGE_PROCESSED) as scope:
            # Do work
            result = process_message(msg)
            scope.set_proof(result.id)
    """
    
    def __init__(self, agent: HBAgent, activity_type: ActivityType):
        self.agent = agent
        self.activity_type = activity_type
        self.start_time = 0.0
        self.proof: Optional[str] = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Calculate response time
        elapsed_us = int((time.time() - self.start_time) * 1_000_000)
        self.agent.set_response_time(elapsed_us)
        
        # Report activity
        if exc_type is None:
            self.agent.report_activity(self.activity_type, self.proof)
        else:
            self.agent.report_error(exc_val)
        
        return False  # Don't suppress exceptions
    
    def set_proof(self, proof: str):
        """Set proof data for the activity"""
        self.proof = proof


# =============================================================================
# IDLE MONITOR
# =============================================================================

class IdleMonitor:
    """
    Monitors for idle conditions and auto-acknowledges.
    
    Useful when you want the component to auto-acknowledge idle
    based on queue depth or time since last activity.
    """
    
    def __init__(
        self,
        agent: HBAgent,
        idle_threshold_ms: float = 500,  # Consider idle after 500ms
        auto_acknowledge: bool = True
    ):
        self.agent = agent
        self.idle_threshold_ms = idle_threshold_ms
        self.auto_acknowledge = auto_acknowledge
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._stop_event = threading.Event()
    
    def start(self):
        """Start idle monitoring"""
        if self._running:
            return
        
        self._running = True
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.name = f"IdleMonitor-{self.agent.component_name}"
        self._monitor_thread.start()
    
    def stop(self):
        """Stop idle monitoring"""
        self._running = False
        self._stop_event.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)
    
    def _monitor_loop(self):
        """Monitor for idle conditions"""
        while self._running and not self._stop_event.is_set():
            try:
                # Check if no recent activity
                if not self.agent.state.has_recent_activity(self.idle_threshold_ms):
                    if self.auto_acknowledge and not self.agent.state.is_idle():
                        # Auto-acknowledge idle
                        self.agent.report_idle("auto_idle_detected")
                
            except Exception:
                pass
            
            self._stop_event.wait(0.1)  # Check every 100ms
