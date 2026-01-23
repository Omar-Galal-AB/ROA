"""
DIMC UE5 Connector - Bridge between WSL Python and UE5 ADimensionsCollector

This module provides bidirectional communication with the UE5 C++ plugin
for receiving LIDAR sensor data and sending configuration commands.

Architecture:
- Dual-port design: Port 9876 (Request) + Port 9877 (Response)
- Length-prefixed JSON protocol
- Asynchronous send/receive threads
- Heartbeat-based connection monitoring

Data Flow:
- UE5 → WSL: LIDAR hits, obstacle detections, sensor readings
- WSL → UE5: Configuration updates, scan parameters, zone settings
"""

import os
import sys
import json
import time
import uuid
import socket
import logging
import threading
from enum import Enum, auto
from queue import Queue, Empty
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
from datetime import datetime


class ConnectionState(Enum):
    """Connection state enumeration."""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    RECONNECTING = auto()
    ERROR = auto()


@dataclass
class ConnectionConfig:
    """Configuration for UE5 connection."""
    # Network settings
    host: str = "127.0.0.1"
    request_port: int = 9876   # Port for sending requests to UE5
    response_port: int = 9877  # Port for receiving responses from UE5
    
    # Timeouts
    connect_timeout: float = 5.0
    receive_timeout: float = 10.0
    send_timeout: float = 5.0
    command_timeout: float = 30.0
    
    # Heartbeat
    heartbeat_interval: float = 2.0
    heartbeat_timeout: float = 10.0
    
    # Reconnection
    reconnect_enabled: bool = True
    reconnect_delay: float = 1.0
    reconnect_max_delay: float = 30.0
    reconnect_backoff: float = 2.0
    max_reconnect_attempts: int = 10
    
    # Buffer sizes
    receive_buffer_size: int = 65536
    send_queue_size: int = 100


@dataclass
class LidarScanData:
    """LIDAR scan data from UE5."""
    timestamp: float
    scan_id: str
    robot_id: str
    hit_points: List[Dict[str, float]]  # [{x, y, z, distance, angle}]
    num_rays: int
    max_range: float
    field_of_view: float
    origin: Dict[str, float]  # {x, y, z}
    rotation: Dict[str, float]  # {pitch, yaw, roll}


@dataclass
class ObstacleData:
    """Obstacle detection data from UE5."""
    timestamp: float
    obstacle_id: str
    position: Dict[str, float]  # {x, y, z}
    dimensions: Dict[str, float]  # {width, height, depth}
    velocity: Dict[str, float]  # {vx, vy, vz}
    angular_velocity: Dict[str, float]  # {wx, wy, wz}
    classification: str
    confidence: float
    distance: float


class DIMCUe5Connector:
    """
    Main connector for DIMC ↔ UE5 communication.
    
    Implements the Bridge subsystem for the Dimensions Collector component,
    handling all data exchange with the ADimensionsCollector UE5 plugin.
    """
    
    def __init__(self, config: Optional[ConnectionConfig] = None, logger: Optional[logging.Logger] = None):
        """Initialize the UE5 connector."""
        self.config = config or ConnectionConfig()
        self.logger = logger or logging.getLogger(__name__)
        
        # Connection state
        self.state = ConnectionState.DISCONNECTED
        self.connected = False
        self.running = False
        
        # Sockets
        self.request_socket: Optional[socket.socket] = None
        self.response_socket: Optional[socket.socket] = None
        
        # Threading
        self.send_queue: Queue = Queue(maxsize=self.config.send_queue_size)
        self.pending_responses: Dict[str, Queue] = {}
        self._lock = threading.RLock()
        
        # Threads
        self._send_thread: Optional[threading.Thread] = None
        self._receive_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._reconnect_thread: Optional[threading.Thread] = None
        
        # Callbacks
        self.event_callbacks: Dict[str, Callable] = {}
        self.on_lidar_scan: Optional[Callable[[LidarScanData], None]] = None
        self.on_obstacle_detected: Optional[Callable[[ObstacleData], None]] = None
        self.on_connection_state_changed: Optional[Callable[[ConnectionState], None]] = None
        
        # Statistics
        self.last_heartbeat: float = 0
        self.messages_sent: int = 0
        self.messages_received: int = 0
        self.reconnect_count: int = 0
        self.last_error: Optional[str] = None
        
    def connect(self) -> bool:
        """
        Connect to UE5 ADimensionsCollector plugin.
        
        Returns:
            True if connection successful, False otherwise.
        """
        if self.connected:
            self.logger.warning("Already connected to UE5")
            return True
            
        self._set_state(ConnectionState.CONNECTING)
        
        try:
            # Create request socket (for sending commands to UE5)
            self.request_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.request_socket.settimeout(self.config.connect_timeout)
            self.request_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            
            self.logger.info(f"Connecting to UE5 request port {self.config.host}:{self.config.request_port}")
            self.request_socket.connect((self.config.host, self.config.request_port))
            
            # Create response socket (for receiving data from UE5)
            self.response_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.response_socket.settimeout(self.config.receive_timeout)
            self.response_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            
            self.logger.info(f"Connecting to UE5 response port {self.config.host}:{self.config.response_port}")
            self.response_socket.connect((self.config.host, self.config.response_port))
            
            # Start communication threads
            self.running = True
            self.connected = True
            self._start_threads()
            
            self._set_state(ConnectionState.CONNECTED)
            self.logger.info("Successfully connected to UE5 ADimensionsCollector")
            
            # Send initial handshake
            self._send_handshake()
            
            return True
            
        except socket.timeout:
            self.last_error = "Connection timeout"
            self.logger.error(f"Connection timeout to UE5")
            self._set_state(ConnectionState.ERROR)
            return False
            
        except ConnectionRefusedError:
            self.last_error = "Connection refused - UE5 not running?"
            self.logger.error("Connection refused - is UE5 running with ADimensionsCollector?")
            self._set_state(ConnectionState.ERROR)
            return False
            
        except Exception as e:
            self.last_error = str(e)
            self.logger.error(f"Failed to connect to UE5: {e}")
            self._set_state(ConnectionState.ERROR)
            return False
            
    def disconnect(self):
        """Disconnect from UE5."""
        self.logger.info("Disconnecting from UE5...")
        
        self.running = False
        self.connected = False
        
        # Send disconnect message
        try:
            self._send_message_internal({
                "message_type": "DISCONNECT",
                "command": "disconnect",
                "payload": {"reason": "DIMC shutdown"}
            })
        except:
            pass
        
        # Stop threads
        self._stop_threads()
        
        # Close sockets
        if self.request_socket:
            try:
                self.request_socket.close()
            except:
                pass
            self.request_socket = None
            
        if self.response_socket:
            try:
                self.response_socket.close()
            except:
                pass
            self.response_socket = None
            
        self._set_state(ConnectionState.DISCONNECTED)
        self.logger.info("Disconnected from UE5")
        
    def send_command(self, command: str, payload: Dict[str, Any] = None, 
                     timeout: float = None) -> Optional[Dict[str, Any]]:
        """
        Send a command to UE5 and wait for response.
        
        Args:
            command: Command name (e.g., "configure_lidar", "set_scan_rate")
            payload: Command payload data
            timeout: Response timeout (uses config default if None)
            
        Returns:
            Response payload or None if failed.
        """
        if not self.connected:
            self.logger.error("Cannot send command - not connected to UE5")
            return None
            
        message_id = str(uuid.uuid4())
        timeout = timeout or self.config.command_timeout
        
        # Create response queue
        response_queue: Queue = Queue()
        self.pending_responses[message_id] = response_queue
        
        # Build message
        message = {
            "message_id": message_id,
            "timestamp": time.time(),
            "message_type": "COMMAND",
            "command": command,
            "payload": payload or {}
        }
        
        try:
            # Queue the message
            self.send_queue.put(message, timeout=1.0)
            
            # Wait for response
            try:
                response = response_queue.get(timeout=timeout)
                return response.get("payload")
            except Empty:
                self.logger.error(f"Command timeout: {command}")
                return None
                
        finally:
            # Cleanup
            self.pending_responses.pop(message_id, None)
            
    def send_event(self, event: str, data: Dict[str, Any] = None):
        """
        Send an event to UE5 (fire-and-forget, no response expected).
        
        Args:
            event: Event name
            data: Event data
        """
        if not self.connected:
            return
            
        message = {
            "message_id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "message_type": "EVENT",
            "command": event,
            "payload": data or {}
        }
        self.send_queue.put(message)
        
    def register_event_callback(self, event: str, callback: Callable):
        """
        Register a callback for UE5 events.
        
        Args:
            event: Event name to listen for
            callback: Function to call when event received
        """
        self.event_callbacks[event] = callback
        
    def unregister_event_callback(self, event: str):
        """Unregister an event callback."""
        self.event_callbacks.pop(event, None)
        
    # =========================================================================
    # DIMC-Specific Commands
    # =========================================================================
    
    def configure_lidar(self, num_rays: int = 360, max_range: float = 5000.0,
                        fov: float = 360.0, scan_rate: float = 10.0) -> bool:
        """
        Configure LIDAR parameters on UE5.
        
        Args:
            num_rays: Number of rays in scan (default 360)
            max_range: Maximum detection range in cm (default 5000)
            fov: Field of view in degrees (default 360)
            scan_rate: Scans per second (default 10)
            
        Returns:
            True if configuration successful.
        """
        response = self.send_command("configure_lidar", {
            "num_rays": num_rays,
            "max_range": max_range,
            "field_of_view": fov,
            "scan_rate": scan_rate
        })
        return response is not None and response.get("success", False)
        
    def set_detection_zone(self, zone_id: str, shape: str, 
                           dimensions: Dict[str, float],
                           position: Dict[str, float]) -> bool:
        """
        Configure a detection zone on UE5.
        
        Args:
            zone_id: Unique zone identifier
            shape: Zone shape ("sphere", "box", "cylinder")
            dimensions: Zone dimensions
            position: Zone center position
            
        Returns:
            True if zone configured successfully.
        """
        response = self.send_command("set_detection_zone", {
            "zone_id": zone_id,
            "shape": shape,
            "dimensions": dimensions,
            "position": position
        })
        return response is not None and response.get("success", False)
        
    def request_scan(self) -> Optional[LidarScanData]:
        """
        Request immediate LIDAR scan from UE5.
        
        Returns:
            LidarScanData if successful, None otherwise.
        """
        response = self.send_command("request_scan", {})
        if response and "scan_data" in response:
            return self._parse_lidar_scan(response["scan_data"])
        return None
        
    def get_obstacles(self) -> List[ObstacleData]:
        """
        Get current obstacle list from UE5.
        
        Returns:
            List of detected obstacles.
        """
        response = self.send_command("get_obstacles", {})
        if response and "obstacles" in response:
            return [self._parse_obstacle(o) for o in response["obstacles"]]
        return []
        
    def set_robot_transform(self, robot_id: str, position: Dict[str, float],
                            rotation: Dict[str, float]) -> bool:
        """
        Update robot transform on UE5 (for sensor origin).
        
        Args:
            robot_id: Robot identifier
            position: Position {x, y, z}
            rotation: Rotation {pitch, yaw, roll}
            
        Returns:
            True if update successful.
        """
        response = self.send_command("set_robot_transform", {
            "robot_id": robot_id,
            "position": position,
            "rotation": rotation
        })
        return response is not None and response.get("success", False)
        
    def get_sensor_status(self) -> Dict[str, Any]:
        """
        Get LIDAR sensor status from UE5.
        
        Returns:
            Sensor status dictionary.
        """
        return self.send_command("get_sensor_status", {}) or {}
        
    # =========================================================================
    # Connection Status
    # =========================================================================
    
    def is_connected(self) -> bool:
        """Check if connected to UE5."""
        return self.connected
        
    def get_state(self) -> ConnectionState:
        """Get current connection state."""
        return self.state
        
    def get_statistics(self) -> Dict[str, Any]:
        """Get connection statistics."""
        return {
            "state": self.state.name,
            "connected": self.connected,
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "reconnect_count": self.reconnect_count,
            "last_heartbeat": self.last_heartbeat,
            "last_error": self.last_error
        }
        
    # =========================================================================
    # Private Methods
    # =========================================================================
    
    def _set_state(self, state: ConnectionState):
        """Update connection state and notify callback."""
        old_state = self.state
        self.state = state
        
        if old_state != state and self.on_connection_state_changed:
            try:
                self.on_connection_state_changed(state)
            except Exception as e:
                self.logger.error(f"State change callback error: {e}")
                
    def _start_threads(self):
        """Start communication threads."""
        self._send_thread = threading.Thread(target=self._send_loop, daemon=True)
        self._send_thread.start()
        
        self._receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._receive_thread.start()
        
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()
        
    def _stop_threads(self):
        """Stop communication threads."""
        # Wait for threads to finish
        for thread in [self._send_thread, self._receive_thread, 
                       self._heartbeat_thread, self._reconnect_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=2.0)
                
    def _send_loop(self):
        """Thread loop for sending messages."""
        while self.running:
            try:
                # Get message from queue
                message = self.send_queue.get(timeout=0.1)
                self._send_message_internal(message)
                
            except Empty:
                continue
            except Exception as e:
                if self.running:
                    self.logger.error(f"Send error: {e}")
                    self._trigger_reconnect()
                break
                
    def _send_message_internal(self, message: Dict):
        """Send a message over the request socket."""
        if not self.request_socket:
            return
            
        try:
            json_data = json.dumps(message)
            data = json_data.encode('utf-8')
            
            # Send with length prefix (4 bytes, big-endian)
            length = len(data)
            self.request_socket.sendall(length.to_bytes(4, byteorder='big') + data)
            
            self.messages_sent += 1
            
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            raise
            
    def _receive_loop(self):
        """Thread loop for receiving messages."""
        while self.running:
            try:
                # Read length prefix (4 bytes)
                length_data = self._recv_exact(4)
                if not length_data:
                    if self.running:
                        self._trigger_reconnect()
                    break
                    
                length = int.from_bytes(length_data, byteorder='big')
                
                # Sanity check
                if length > self.config.receive_buffer_size:
                    self.logger.error(f"Message too large: {length} bytes")
                    continue
                    
                # Read message data
                data = self._recv_exact(length)
                if not data:
                    if self.running:
                        self._trigger_reconnect()
                    break
                    
                # Parse JSON
                message = json.loads(data.decode('utf-8'))
                self.messages_received += 1
                
                # Handle message
                self._handle_message(message)
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.logger.error(f"Receive error: {e}")
                    self._trigger_reconnect()
                break
                
    def _recv_exact(self, num_bytes: int) -> Optional[bytes]:
        """Receive exact number of bytes from response socket."""
        if not self.response_socket:
            return None
            
        data = b''
        while len(data) < num_bytes:
            try:
                chunk = self.response_socket.recv(num_bytes - len(data))
                if not chunk:
                    return None
                data += chunk
            except socket.timeout:
                if not self.running:
                    return None
                continue
        return data
        
    def _handle_message(self, message: Dict):
        """Handle received message from UE5."""
        msg_type = message.get("message_type")
        msg_id = message.get("message_id")
        command = message.get("command")
        payload = message.get("payload", {})
        
        if msg_type == "RESPONSE":
            # Handle response to pending command
            if msg_id in self.pending_responses:
                self.pending_responses[msg_id].put(message)
                
        elif msg_type == "EVENT":
            # Handle events from UE5
            self._handle_event(command, payload)
            
        elif msg_type == "DATA":
            # Handle streaming data from UE5
            self._handle_data(command, payload)
            
        elif msg_type == "ERROR":
            self.logger.error(f"UE5 error: {payload}")
            
    def _handle_event(self, event: str, payload: Dict):
        """Handle event from UE5."""
        # Check for registered callback
        if event in self.event_callbacks:
            try:
                self.event_callbacks[event](payload)
            except Exception as e:
                self.logger.error(f"Event callback error ({event}): {e}")
                
        # Handle specific DIMC events
        if event == "lidar_scan":
            if self.on_lidar_scan:
                scan_data = self._parse_lidar_scan(payload)
                self.on_lidar_scan(scan_data)
                
        elif event == "obstacle_detected":
            if self.on_obstacle_detected:
                obstacle = self._parse_obstacle(payload)
                self.on_obstacle_detected(obstacle)
                
    def _handle_data(self, data_type: str, payload: Dict):
        """Handle streaming data from UE5."""
        if data_type == "lidar_stream":
            if self.on_lidar_scan:
                scan_data = self._parse_lidar_scan(payload)
                self.on_lidar_scan(scan_data)
                
    def _parse_lidar_scan(self, data: Dict) -> LidarScanData:
        """Parse LIDAR scan data from UE5 format."""
        return LidarScanData(
            timestamp=data.get("timestamp", time.time()),
            scan_id=data.get("scan_id", str(uuid.uuid4())),
            robot_id=data.get("robot_id", "default"),
            hit_points=data.get("hit_points", []),
            num_rays=data.get("num_rays", 0),
            max_range=data.get("max_range", 5000.0),
            field_of_view=data.get("field_of_view", 360.0),
            origin=data.get("origin", {"x": 0, "y": 0, "z": 0}),
            rotation=data.get("rotation", {"pitch": 0, "yaw": 0, "roll": 0})
        )
        
    def _parse_obstacle(self, data: Dict) -> ObstacleData:
        """Parse obstacle data from UE5 format."""
        return ObstacleData(
            timestamp=data.get("timestamp", time.time()),
            obstacle_id=data.get("obstacle_id", str(uuid.uuid4())),
            position=data.get("position", {"x": 0, "y": 0, "z": 0}),
            dimensions=data.get("dimensions", {"width": 0, "height": 0, "depth": 0}),
            velocity=data.get("velocity", {"vx": 0, "vy": 0, "vz": 0}),
            angular_velocity=data.get("angular_velocity", {"wx": 0, "wy": 0, "wz": 0}),
            classification=data.get("classification", "unknown"),
            confidence=data.get("confidence", 0.0),
            distance=data.get("distance", 0.0)
        )
        
    def _heartbeat_loop(self):
        """Send periodic heartbeat to maintain connection."""
        while self.connected and self.running:
            try:
                time.sleep(self.config.heartbeat_interval)
                
                if self.connected:
                    self.send_event("heartbeat", {
                        "timestamp": time.time(),
                        "component": "DIMC",
                        "status": "alive"
                    })
                    self.last_heartbeat = time.time()
                    
            except Exception as e:
                self.logger.error(f"Heartbeat error: {e}")
                break
                
    def _send_handshake(self):
        """Send initial handshake to UE5."""
        self.send_event("handshake", {
            "component": "DIMC",
            "version": "2.0",
            "capabilities": ["lidar", "obstacle_detection", "proximity_monitoring"],
            "timestamp": time.time()
        })
        
    def _trigger_reconnect(self):
        """Trigger reconnection attempt."""
        if not self.config.reconnect_enabled or self._reconnect_thread:
            return
            
        self.connected = False
        self._set_state(ConnectionState.RECONNECTING)
        
        self._reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
        self._reconnect_thread.start()
        
    def _reconnect_loop(self):
        """Attempt to reconnect with exponential backoff."""
        delay = self.config.reconnect_delay
        attempts = 0
        
        while self.running and attempts < self.config.max_reconnect_attempts:
            attempts += 1
            self.reconnect_count += 1
            
            self.logger.info(f"Reconnection attempt {attempts}/{self.config.max_reconnect_attempts}")
            
            # Clean up old sockets
            self.disconnect()
            
            # Wait before attempting
            time.sleep(delay)
            
            # Try to connect
            if self.connect():
                self.logger.info("Reconnection successful")
                self._reconnect_thread = None
                return
                
            # Increase delay with exponential backoff
            delay = min(delay * self.config.reconnect_backoff, self.config.reconnect_max_delay)
            
        self.logger.error("Max reconnection attempts reached")
        self._set_state(ConnectionState.ERROR)
        self._reconnect_thread = None
