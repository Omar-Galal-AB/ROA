"""
ue5_connector.py
ROA - Robot Operations & Automation
UE5 connection handler for Webthread
"""

import socket
import json
import logging
import threading
import time
import uuid
from typing import Optional, Dict, Any, Callable
from queue import Queue, Empty


class UE5Connector:
    """
    Manages connection to Unreal Engine 5
    
    Handles communication with UE5 for:
    - Sending commands from ROS2 to UE5
    - Receiving simulation data from UE5
    - Synchronizing state between ROS2 and UE5
    """

    def __init__(self, host: str = "localhost", port: int = 9876):
        """
        Initialize UE5 connector
        
        Args:
            host: UE5 host address
            port: UE5 communication port
        """
        self.logger = logging.getLogger(__name__)
        self.host = host
        self.port = port
        self.connected = False
        self.socket: Optional[socket.socket] = None
        
        # Threading
        self.receive_thread: Optional[threading.Thread] = None
        self.send_thread: Optional[threading.Thread] = None
        self.running = False
        
        # Message handling
        self.send_queue: Queue = Queue()
        self.pending_responses: Dict[str, Queue] = {}
        self.event_callbacks: Dict[str, Callable] = {}
        
        # Connection state
        self.session_id: Optional[str] = None
        self.last_heartbeat = 0.0
        
        self.logger.info(f"UE5Connector created: {host}:{port}")

    def connect(self, timeout: float = 5.0) -> bool:
        """
        Establish connection to UE5
        
        Args:
            timeout: Connection timeout in seconds
            
        Returns:
            True if successful, False otherwise
        """
        if self.connected:
            self.logger.warning("Already connected to UE5")
            return True
            
        try:
            # Create TCP socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(timeout)
            
            # Connect to UE5 server
            self.logger.info(f"Connecting to UE5 at {self.host}:{self.port}...")
            self.socket.connect((self.host, self.port))
            self.socket.settimeout(None)  # Set to blocking mode after connection
            
            # Start communication threads
            self.running = True
            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.send_thread = threading.Thread(target=self._send_loop, daemon=True)
            self.receive_thread.start()
            self.send_thread.start()
            
            # Send connect command
            response = self.send_command("connect", {"client_type": "webthread", "version": "0.1.0"})
            if response and response.get("status") == "success":
                self.session_id = response.get("session_id")
                self.connected = True
                self.logger.info(f"Connected to UE5 (session: {self.session_id})")
                
                # Start heartbeat
                threading.Thread(target=self._heartbeat_loop, daemon=True).start()
                return True
            else:
                self.logger.error("Connection handshake failed")
                self.disconnect()
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to connect to UE5: {e}")
            if self.socket:
                self.socket.close()
                self.socket = None
            return False

    def disconnect(self):
        """Disconnect from UE5"""
        if not self.connected:
            return
            
        try:
            # Send disconnect command
            if self.socket:
                try:
                    self.send_command("disconnect", {}, timeout=1.0)
                except:
                    pass
            
            # Stop threads
            self.running = False
            self.connected = False
            
            # Close socket
            if self.socket:
                self.socket.close()
                self.socket = None
            
            # Wait for threads
            if self.receive_thread and self.receive_thread.is_alive():
                self.receive_thread.join(timeout=2.0)
            if self.send_thread and self.send_thread.is_alive():
                self.send_thread.join(timeout=2.0)
            
            self.logger.info("Disconnected from UE5")
            
        except Exception as e:
            self.logger.error(f"Error during UE5 disconnect: {e}")

    def send_command(self, command: str, params: Optional[Dict] = None, timeout: float = 5.0) -> Optional[Dict]:
        """
        Send command to UE5 and wait for response
        
        Args:
            command: Command name
            params: Optional command parameters
            timeout: Response timeout in seconds
            
        Returns:
            Response payload or None on error
        """
        if not self.connected:
            self.logger.warning("Not connected to UE5")
            return None
        
        try:
            # Create message
            message_id = str(uuid.uuid4())
            message = {
                "message_id": message_id,
                "timestamp": time.time(),
                "message_type": "REQUEST",
                "command": command,
                "payload": params or {}
            }
            
            # Create response queue
            response_queue = Queue()
            self.pending_responses[message_id] = response_queue
            
            # Send message
            self.send_queue.put(message)
            self.logger.debug(f"Sent command to UE5: {command}")
            
            # Wait for response
            try:
                response = response_queue.get(timeout=timeout)
                del self.pending_responses[message_id]
                return response.get("payload", {})
            except Empty:
                self.logger.error(f"Command timeout: {command}")
                if message_id in self.pending_responses:
                    del self.pending_responses[message_id]
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to send command to UE5: {e}")
            return None

    def send_event(self, event: str, data: Optional[Dict] = None):
        """
        Send event to UE5 (no response expected)
        
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
        """Register callback for UE5 events"""
        self.event_callbacks[event] = callback

    def get_simulation_data(self) -> Optional[Dict[str, Any]]:
        """Get current simulation data from UE5"""
        return self.send_command("get_simulation_state", {})

    def is_connected(self) -> bool:
        """Check if connected to UE5"""
        return self.connected

    def _send_loop(self):
        """Thread loop for sending messages"""
        while self.running:
            try:
                # Get message from queue
                message = self.send_queue.get(timeout=0.1)
                
                # Serialize to JSON
                json_data = json.dumps(message)
                
                # Send with length prefix (4 bytes)
                data = json_data.encode('utf-8')
                length = len(data)
                self.socket.sendall(length.to_bytes(4, byteorder='big') + data)
                
            except Empty:
                continue
            except Exception as e:
                if self.running:
                    self.logger.error(f"Send error: {e}")
                    self.connected = False
                break

    def _receive_loop(self):
        """Thread loop for receiving messages"""
        while self.running:
            try:
                # Read length prefix (4 bytes)
                length_data = self._recv_exact(4)
                if not length_data:
                    break
                    
                length = int.from_bytes(length_data, byteorder='big')
                
                # Read message data
                data = self._recv_exact(length)
                if not data:
                    break
                
                # Parse JSON
                message = json.loads(data.decode('utf-8'))
                self._handle_message(message)
                
            except Exception as e:
                if self.running:
                    self.logger.error(f"Receive error: {e}")
                    self.connected = False
                break

    def _recv_exact(self, num_bytes: int) -> Optional[bytes]:
        """Receive exact number of bytes"""
        data = b''
        while len(data) < num_bytes:
            chunk = self.socket.recv(num_bytes - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def _handle_message(self, message: Dict):
        """Handle received message"""
        msg_type = message.get("message_type")
        msg_id = message.get("message_id")
        
        if msg_type == "RESPONSE":
            # Handle response to pending request
            if msg_id in self.pending_responses:
                self.pending_responses[msg_id].put(message)
                
        elif msg_type == "EVENT":
            # Handle event from UE5
            event = message.get("command")
            if event in self.event_callbacks:
                try:
                    self.event_callbacks[event](message.get("payload", {}))
                except Exception as e:
                    self.logger.error(f"Event callback error ({event}): {e}")
                    
        elif msg_type == "ERROR":
            self.logger.error(f"UE5 error: {message.get('payload', {})}")

    def _heartbeat_loop(self):
        """Send periodic heartbeat"""
        while self.connected and self.running:
            try:
                time.sleep(2.0)
                if self.connected:
                    self.send_event("heartbeat", {"timestamp": time.time()})
                    self.last_heartbeat = time.time()
            except:
                break
