"""
comc_bridge_agent.py
ROA - Robot Operations & Automation
COMC Bridge Agent for UE5 Communication

This module provides the Bridge subsystem integration for COMC.
It enables COMC to exchange data with the UE5 Plugin (simulation side).

Architecture:
- COMC can either connect to UE5 directly or through Webthread's bridge
- Default mode: Use Webthread bridge (recommended)
- Direct mode: Connect directly to UE5 (for testing/special cases)

Data Flow:
- COMC → Bridge → UE5: Robot states, work areas, proximity alerts
- UE5 → Bridge → COMC: Simulation events, robot spawns, collisions
"""

import os
import sys
import json
import logging
import threading
import time
import socket
from typing import Optional, Dict, Any, Callable, List
from queue import Queue, Empty
from enum import Enum
from dataclasses import dataclass, field
from abc import ABC, abstractmethod


class BridgeMode(Enum):
    """Bridge connection modes"""
    WEBTHREAD = "webthread"  # Route through Webthread bridge (default)
    DIRECT = "direct"        # Connect directly to UE5
    STANDALONE = "standalone"  # Offline mode (no bridge)


class BridgeState(Enum):
    """Bridge connection states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class BridgeMessage:
    """Message structure for bridge communication"""
    message_id: str
    timestamp: float
    source: str  # "comc"
    target: str  # "ue5" or "webthread"
    message_type: str  # "REQUEST", "EVENT", "RESPONSE"
    command: str
    payload: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "target": self.target,
            "message_type": self.message_type,
            "command": self.command,
            "payload": self.payload
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BridgeMessage':
        return cls(
            message_id=data.get("message_id", ""),
            timestamp=data.get("timestamp", 0.0),
            source=data.get("source", ""),
            target=data.get("target", ""),
            message_type=data.get("message_type", ""),
            command=data.get("command", ""),
            payload=data.get("payload", {})
        )


class BridgeTransport(ABC):
    """Abstract base class for bridge transports"""
    
    @abstractmethod
    def connect(self) -> bool:
        pass
    
    @abstractmethod
    def disconnect(self):
        pass
    
    @abstractmethod
    def send(self, message: BridgeMessage) -> bool:
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        pass


class WebthreadBridgeTransport(BridgeTransport):
    """
    Transport that routes through Webthread's bridge.
    Uses IPC (Unix domain sockets on Linux) to communicate with Webthread.
    """
    
    # Default IPC path for Webthread bridge
    DEFAULT_IPC_PATH = "/tmp/roa_webthread_bridge.sock"
    
    def __init__(
        self,
        ipc_path: str = None,
        logger: Optional[logging.Logger] = None
    ):
        self.ipc_path = ipc_path or self.DEFAULT_IPC_PATH
        self.logger = logger or logging.getLogger("WebthreadBridgeTransport")
        self.socket: Optional[socket.socket] = None
        self._connected = False
        self._lock = threading.Lock()
    
    def connect(self) -> bool:
        with self._lock:
            if self._connected:
                return True
            
            try:
                # Create Unix domain socket
                self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.socket.settimeout(5.0)
                self.socket.connect(self.ipc_path)
                self.socket.settimeout(None)
                
                self._connected = True
                self.logger.info(f"Connected to Webthread bridge: {self.ipc_path}")
                return True
                
            except FileNotFoundError:
                self.logger.warning(f"Webthread bridge not available: {self.ipc_path}")
                return False
            except Exception as e:
                self.logger.error(f"Failed to connect to Webthread bridge: {e}")
                return False
    
    def disconnect(self):
        with self._lock:
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
            self._connected = False
            self.logger.info("Disconnected from Webthread bridge")
    
    def send(self, message: BridgeMessage) -> bool:
        if not self._connected or not self.socket:
            return False
        
        try:
            data = message.to_json().encode('utf-8')
            length = len(data)
            self.socket.sendall(length.to_bytes(4, byteorder='big') + data)
            return True
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            self._connected = False
            return False
    
    def is_connected(self) -> bool:
        return self._connected


class DirectUE5Transport(BridgeTransport):
    """
    Transport that connects directly to UE5.
    Uses TCP to communicate with UE5 plugin.
    """
    
    DEFAULT_HOST = "localhost"
    DEFAULT_PORT = 9876
    
    def __init__(
        self,
        host: str = None,
        port: int = None,
        logger: Optional[logging.Logger] = None
    ):
        self.host = host or self.DEFAULT_HOST
        self.port = port or self.DEFAULT_PORT
        self.logger = logger or logging.getLogger("DirectUE5Transport")
        self.socket: Optional[socket.socket] = None
        self._connected = False
        self._lock = threading.Lock()
    
    def connect(self) -> bool:
        with self._lock:
            if self._connected:
                return True
            
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(5.0)
                self.socket.connect((self.host, self.port))
                self.socket.settimeout(None)
                
                self._connected = True
                self.logger.info(f"Connected to UE5: {self.host}:{self.port}")
                return True
                
            except Exception as e:
                self.logger.error(f"Failed to connect to UE5: {e}")
                return False
    
    def disconnect(self):
        with self._lock:
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
            self._connected = False
            self.logger.info("Disconnected from UE5")
    
    def send(self, message: BridgeMessage) -> bool:
        if not self._connected or not self.socket:
            return False
        
        try:
            data = message.to_json().encode('utf-8')
            length = len(data)
            self.socket.sendall(length.to_bytes(4, byteorder='big') + data)
            return True
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            self._connected = False
            return False
    
    def is_connected(self) -> bool:
        return self._connected


class COMCBridgeAgent:
    """
    COMC Bridge Agent - Enables COMC to communicate with UE5.
    
    Features:
    - Sends coordination data to UE5 (work areas, proximity alerts)
    - Receives simulation events from UE5 (robot spawns, collisions)
    - Supports multiple transport modes (Webthread, Direct, Standalone)
    - Event callback registration for incoming UE5 data
    
    Usage:
        bridge = COMCBridgeAgent(mode=BridgeMode.WEBTHREAD)
        bridge.start()
        
        # Send data to UE5
        bridge.send_work_area_update(robot_id="robot_1", area=work_area)
        bridge.send_proximity_alert(alert_data)
        
        # Register for UE5 events
        bridge.on_robot_spawned(handle_spawn)
        bridge.on_collision_detected(handle_collision)
        
        # Shutdown
        bridge.stop()
    """
    
    def __init__(
        self,
        mode: BridgeMode = BridgeMode.WEBTHREAD,
        ue5_host: str = None,
        ue5_port: int = None,
        webthread_ipc_path: str = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize COMC Bridge Agent.
        
        Args:
            mode: Bridge connection mode
            ue5_host: UE5 host (for direct mode)
            ue5_port: UE5 port (for direct mode)
            webthread_ipc_path: IPC path (for webthread mode)
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger("COMCBridgeAgent")
        self.mode = mode
        
        self._transport: Optional[BridgeTransport] = None
        self._state = BridgeState.DISCONNECTED
        self._running = False
        self._lock = threading.Lock()
        
        # Message handling
        self._message_counter = 0
        self._send_queue: Queue = Queue()
        self._send_thread: Optional[threading.Thread] = None
        self._receive_thread: Optional[threading.Thread] = None
        
        # Event callbacks
        self._event_callbacks: Dict[str, List[Callable]] = {
            'robot_spawned': [],
            'robot_removed': [],
            'collision_detected': [],
            'simulation_state_changed': [],
            'ue5_command': [],
        }
        
        # Metrics
        self._messages_sent = 0
        self._messages_received = 0
        self._errors = 0
        self._last_activity = 0.0
        
        # Initialize transport based on mode
        if mode == BridgeMode.WEBTHREAD:
            self._transport = WebthreadBridgeTransport(
                ipc_path=webthread_ipc_path,
                logger=self.logger
            )
        elif mode == BridgeMode.DIRECT:
            self._transport = DirectUE5Transport(
                host=ue5_host,
                port=ue5_port,
                logger=self.logger
            )
        # STANDALONE mode has no transport
        
        self.logger.info(f"COMCBridgeAgent initialized (mode: {mode.value})")
    
    # =========================================================================
    # LIFECYCLE
    # =========================================================================
    
    def start(self) -> bool:
        """
        Start the Bridge Agent.
        
        Returns:
            True if started successfully
        """
        with self._lock:
            if self._running:
                self.logger.warning("Bridge Agent already running")
                return True
            
            if self.mode == BridgeMode.STANDALONE:
                self._running = True
                self._state = BridgeState.CONNECTED
                self.logger.info("Bridge Agent started in standalone mode")
                return True
            
            self._state = BridgeState.CONNECTING
            
            if self._transport and self._transport.connect():
                self._running = True
                self._state = BridgeState.CONNECTED
                
                # Start send thread
                self._send_thread = threading.Thread(target=self._send_loop, daemon=True)
                self._send_thread.name = "COMCBridge-Send"
                self._send_thread.start()
                
                self.logger.info("Bridge Agent started successfully")
                return True
            else:
                self._state = BridgeState.ERROR
                self.logger.warning("Failed to connect bridge, running in degraded mode")
                self._running = True
                return False
    
    def stop(self):
        """Stop the Bridge Agent."""
        with self._lock:
            if not self._running:
                return
            
            self._running = False
            
            # Wait for threads
            if self._send_thread and self._send_thread.is_alive():
                self._send_thread.join(timeout=1.0)
            
            # Disconnect transport
            if self._transport:
                self._transport.disconnect()
            
            self._state = BridgeState.DISCONNECTED
            self.logger.info("Bridge Agent stopped")
    
    def is_running(self) -> bool:
        """Check if agent is running."""
        return self._running
    
    def is_connected(self) -> bool:
        """Check if connected to bridge/UE5."""
        if self.mode == BridgeMode.STANDALONE:
            return True
        return self._transport and self._transport.is_connected()
    
    def get_state(self) -> BridgeState:
        """Get current bridge state."""
        return self._state
    
    # =========================================================================
    # OUTGOING - Send to UE5
    # =========================================================================
    
    def send_work_area_update(
        self,
        robot_id: str,
        area_center: Dict[str, float],
        area_radius: float,
        area_type: str = "dynamic"
    ) -> bool:
        """
        Send work area update to UE5.
        
        Args:
            robot_id: Robot identifier
            area_center: Center point {x, y, z}
            area_radius: Radius in meters
            area_type: Area type (static/dynamic)
            
        Returns:
            True if queued successfully
        """
        return self._send_event("work_area_update", {
            "robot_id": robot_id,
            "center": area_center,
            "radius": area_radius,
            "type": area_type,
            "timestamp": time.time()
        })
    
    def send_proximity_alert(
        self,
        robot_id: str,
        other_robot_id: str,
        distance: float,
        severity: str = "warning"
    ) -> bool:
        """
        Send proximity alert to UE5 for visualization.
        
        Args:
            robot_id: First robot ID
            other_robot_id: Second robot ID
            distance: Distance between robots
            severity: Alert severity (info/warning/critical)
            
        Returns:
            True if queued successfully
        """
        return self._send_event("proximity_alert", {
            "robot_id": robot_id,
            "other_robot_id": other_robot_id,
            "distance": distance,
            "severity": severity,
            "timestamp": time.time()
        })
    
    def send_robot_state(
        self,
        robot_id: str,
        state: str,
        position: Optional[Dict[str, float]] = None,
        velocity: Optional[Dict[str, float]] = None
    ) -> bool:
        """
        Send robot state update to UE5.
        
        Args:
            robot_id: Robot identifier
            state: Current state
            position: Position {x, y, z}
            velocity: Velocity {vx, vy, vz}
            
        Returns:
            True if queued successfully
        """
        return self._send_event("robot_state", {
            "robot_id": robot_id,
            "state": state,
            "position": position,
            "velocity": velocity,
            "timestamp": time.time()
        })
    
    def send_fleet_status(
        self,
        fleet_id: str,
        robot_ids: List[str],
        formation: Optional[str] = None
    ) -> bool:
        """
        Send fleet status to UE5.
        
        Args:
            fleet_id: Fleet identifier
            robot_ids: List of robot IDs in fleet
            formation: Optional formation type
            
        Returns:
            True if queued successfully
        """
        return self._send_event("fleet_status", {
            "fleet_id": fleet_id,
            "robot_ids": robot_ids,
            "formation": formation,
            "robot_count": len(robot_ids),
            "timestamp": time.time()
        })
    
    def send_coordination_event(
        self,
        event_type: str,
        data: Dict[str, Any]
    ) -> bool:
        """
        Send generic coordination event to UE5.
        
        Args:
            event_type: Type of coordination event
            data: Event data
            
        Returns:
            True if queued successfully
        """
        return self._send_event(f"coordination_{event_type}", {
            **data,
            "timestamp": time.time()
        })
    
    # =========================================================================
    # INCOMING - Events from UE5
    # =========================================================================
    
    def on_robot_spawned(self, callback: Callable[[str, Dict], None]):
        """
        Register callback for robot spawn events from UE5.
        
        Args:
            callback: Function(robot_id, spawn_data)
        """
        self._event_callbacks['robot_spawned'].append(callback)
    
    def on_robot_removed(self, callback: Callable[[str], None]):
        """
        Register callback for robot removal events from UE5.
        
        Args:
            callback: Function(robot_id)
        """
        self._event_callbacks['robot_removed'].append(callback)
    
    def on_collision_detected(self, callback: Callable[[str, str, Dict], None]):
        """
        Register callback for collision detection from UE5.
        
        Args:
            callback: Function(robot_id1, robot_id2, collision_data)
        """
        self._event_callbacks['collision_detected'].append(callback)
    
    def on_simulation_state_changed(self, callback: Callable[[str], None]):
        """
        Register callback for simulation state changes.
        
        Args:
            callback: Function(new_state)
        """
        self._event_callbacks['simulation_state_changed'].append(callback)
    
    def on_ue5_command(self, callback: Callable[[str, Dict], None]):
        """
        Register callback for commands from UE5.
        
        Args:
            callback: Function(command, data)
        """
        self._event_callbacks['ue5_command'].append(callback)
    
    # =========================================================================
    # METRICS
    # =========================================================================
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get bridge agent metrics."""
        return {
            'mode': self.mode.value,
            'state': self._state.value,
            'running': self._running,
            'connected': self.is_connected(),
            'messages_sent': self._messages_sent,
            'messages_received': self._messages_received,
            'errors': self._errors,
            'last_activity': self._last_activity,
            'queue_depth': self._send_queue.qsize(),
        }
    
    # =========================================================================
    # INTERNAL
    # =========================================================================
    
    def _send_event(self, command: str, payload: Dict[str, Any]) -> bool:
        """Queue an event message for sending."""
        if not self._running:
            return False
        
        self._message_counter += 1
        message = BridgeMessage(
            message_id=f"comc_{self._message_counter}",
            timestamp=time.time(),
            source="comc",
            target="ue5",
            message_type="EVENT",
            command=command,
            payload=payload
        )
        
        self._send_queue.put(message)
        self._last_activity = time.time()
        return True
    
    def _send_loop(self):
        """Thread loop for sending messages."""
        while self._running:
            try:
                message = self._send_queue.get(timeout=0.1)
                
                if self._transport and self._transport.is_connected():
                    if self._transport.send(message):
                        self._messages_sent += 1
                        self.logger.debug(f"Sent: {message.command}")
                    else:
                        self._errors += 1
                else:
                    # In standalone or disconnected mode, just log
                    self.logger.debug(f"Would send (not connected): {message.command}")
                    self._messages_sent += 1
                    
            except Empty:
                continue
            except Exception as e:
                self.logger.error(f"Send error: {e}")
                self._errors += 1
    
    def _handle_incoming_message(self, data: Dict[str, Any]):
        """Handle incoming message from UE5."""
        try:
            message = BridgeMessage.from_dict(data)
            command = message.command
            payload = message.payload
            
            self._messages_received += 1
            self._last_activity = time.time()
            
            # Dispatch to appropriate callbacks
            if command == "robot_spawned":
                robot_id = payload.get("robot_id")
                for cb in self._event_callbacks['robot_spawned']:
                    cb(robot_id, payload)
                    
            elif command == "robot_removed":
                robot_id = payload.get("robot_id")
                for cb in self._event_callbacks['robot_removed']:
                    cb(robot_id)
                    
            elif command == "collision_detected":
                robot1 = payload.get("robot_id1")
                robot2 = payload.get("robot_id2")
                for cb in self._event_callbacks['collision_detected']:
                    cb(robot1, robot2, payload)
                    
            elif command == "simulation_state":
                state = payload.get("state")
                for cb in self._event_callbacks['simulation_state_changed']:
                    cb(state)
                    
            else:
                # Generic command
                for cb in self._event_callbacks['ue5_command']:
                    cb(command, payload)
                    
        except Exception as e:
            self.logger.error(f"Error handling incoming message: {e}")
            self._errors += 1


# =============================================================================
# HELPER: Create appropriate bridge for environment
# =============================================================================

def create_comc_bridge(
    prefer_webthread: bool = True,
    logger: Optional[logging.Logger] = None
) -> COMCBridgeAgent:
    """
    Factory function to create the appropriate bridge agent.
    
    Tries to connect in order:
    1. Webthread bridge (if available and preferred)
    2. Direct UE5 connection
    3. Standalone mode (fallback)
    
    Args:
        prefer_webthread: Prefer Webthread routing
        logger: Optional logger
        
    Returns:
        Configured COMCBridgeAgent
    """
    import os
    
    if prefer_webthread:
        # Check if Webthread IPC exists
        ipc_path = "/tmp/roa_webthread_bridge.sock"
        if os.path.exists(ipc_path):
            return COMCBridgeAgent(
                mode=BridgeMode.WEBTHREAD,
                logger=logger
            )
    
    # Try direct mode
    return COMCBridgeAgent(
        mode=BridgeMode.STANDALONE,  # Safe fallback
        logger=logger
    )
