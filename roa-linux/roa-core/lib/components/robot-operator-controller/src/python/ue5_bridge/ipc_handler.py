"""
UE5 IPC Handler - TCP communication layer for UE5 <-> Linux ROC.

Uses the existing ROA dual-port TCP bridge:
- Port 9876: UE5 -> Linux (receive commands)
- Port 9877: Linux -> UE5 (send responses)
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Dict, List, Optional, Any
from datetime import datetime


class ConnectionState(Enum):
    """Connection state enumeration."""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    RECONNECTING = auto()
    ERROR = auto()


@dataclass
class IPCConfig:
    """IPC configuration settings."""
    receive_port: int = 9876
    send_port: int = 9877
    ue5_host: str = "localhost"
    connection_timeout_ms: int = 5000
    message_timeout_ms: int = 1000
    heartbeat_interval_ms: int = 1000
    receive_buffer_bytes: int = 8192
    send_buffer_bytes: int = 8192
    max_reconnect_attempts: int = 5
    reconnect_delay_ms: int = 1000


@dataclass
class IPCMessage:
    """Represents an IPC message."""
    type: str
    data: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    message_id: str = ""
    
    def to_json(self) -> str:
        """Serialize message to JSON string."""
        payload = {
            "type": self.type,
            **self.data,
            "timestamp": self.timestamp
        }
        if self.message_id:
            payload["message_id"] = self.message_id
        return json.dumps(payload)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'IPCMessage':
        """Deserialize message from JSON string."""
        data = json.loads(json_str)
        msg_type = data.pop("type", "unknown")
        timestamp = data.pop("timestamp", time.time())
        message_id = data.pop("message_id", "")
        return cls(
            type=msg_type,
            data=data,
            timestamp=timestamp,
            message_id=message_id
        )


MessageCallback = Callable[[IPCMessage], None]


class UE5IPCHandler:
    """
    Handles IPC communication with UE5 ROC plugin.
    
    Provides async TCP communication over the dual-port bridge,
    message serialization, callback registration, and heartbeat management.
    """
    
    def __init__(self, config: Optional[IPCConfig] = None):
        """
        Initialize IPC handler.
        
        Args:
            config: IPC configuration settings. Uses defaults if None.
        """
        self.config = config or IPCConfig()
        self.logger = logging.getLogger(__name__)
        
        # Connection state
        self._state = ConnectionState.DISCONNECTED
        self._receive_reader: Optional[asyncio.StreamReader] = None
        self._receive_writer: Optional[asyncio.StreamWriter] = None
        self._send_reader: Optional[asyncio.StreamReader] = None
        self._send_writer: Optional[asyncio.StreamWriter] = None
        
        # Message handling
        self._callbacks: Dict[str, List[MessageCallback]] = {}
        self._pending_responses: Dict[str, asyncio.Future] = {}
        self._message_queue: asyncio.Queue = asyncio.Queue()
        
        # Heartbeat tracking
        self._last_heartbeat_received: float = 0.0
        self._last_heartbeat_sent: float = 0.0
        
        # Background tasks
        self._receive_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Statistics
        self._messages_sent = 0
        self._messages_received = 0
        self._reconnect_count = 0
    
    @property
    def state(self) -> ConnectionState:
        """Get current connection state."""
        return self._state
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to UE5."""
        return self._state == ConnectionState.CONNECTED
    
    @property
    def heartbeat_healthy(self) -> bool:
        """Check if heartbeat is within acceptable range."""
        if self._last_heartbeat_received == 0:
            return False
        elapsed = time.time() - self._last_heartbeat_received
        return elapsed < (self.config.heartbeat_interval_ms * 3 / 1000)
    
    async def connect(self) -> bool:
        """
        Establish connection to UE5.
        
        Returns:
            True if connection successful, False otherwise.
        """
        if self._state == ConnectionState.CONNECTED:
            return True
        
        self._state = ConnectionState.CONNECTING
        self.logger.info(f"Connecting to UE5 at {self.config.ue5_host}")
        
        try:
            # Set up receive connection (UE5 -> Linux on port 9876)
            # Note: We listen as a server since UE5 connects to us
            receive_server = await asyncio.start_server(
                self._handle_receive_connection,
                host='0.0.0.0',
                port=self.config.receive_port
            )
            self.logger.info(f"Listening for UE5 on port {self.config.receive_port}")
            
            # Set up send connection (Linux -> UE5 on port 9877)
            # We connect to UE5's listening port
            timeout = self.config.connection_timeout_ms / 1000
            try:
                self._send_reader, self._send_writer = await asyncio.wait_for(
                    asyncio.open_connection(
                        self.config.ue5_host,
                        self.config.send_port
                    ),
                    timeout=timeout
                )
                self.logger.info(f"Connected to UE5 send port {self.config.send_port}")
            except asyncio.TimeoutError:
                self.logger.warning(
                    f"Timeout connecting to UE5 send port, will retry on demand"
                )
            
            self._state = ConnectionState.CONNECTED
            self._running = True
            
            # Start background tasks
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            self.logger.info("UE5 IPC connection established")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to connect to UE5: {e}")
            self._state = ConnectionState.ERROR
            return False
    
    async def _handle_receive_connection(
        self, 
        reader: asyncio.StreamReader, 
        writer: asyncio.StreamWriter
    ):
        """Handle incoming connection from UE5."""
        self._receive_reader = reader
        self._receive_writer = writer
        
        peer = writer.get_extra_info('peername')
        self.logger.info(f"UE5 connected from {peer}")
        
        # Start receive loop for this connection
        try:
            await self._receive_loop()
        except Exception as e:
            self.logger.error(f"Receive loop error: {e}")
        finally:
            writer.close()
            await writer.wait_closed()
    
    async def disconnect(self):
        """Gracefully disconnect from UE5."""
        self.logger.info("Disconnecting from UE5")
        self._running = False
        
        # Cancel background tasks
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Close connections
        if self._send_writer:
            self._send_writer.close()
            await self._send_writer.wait_closed()
        
        if self._receive_writer:
            self._receive_writer.close()
            await self._receive_writer.wait_closed()
        
        self._state = ConnectionState.DISCONNECTED
        self.logger.info("Disconnected from UE5")
    
    async def send_message(self, message: IPCMessage) -> bool:
        """
        Send message to UE5.
        
        Args:
            message: Message to send.
            
        Returns:
            True if sent successfully, False otherwise.
        """
        if not self._send_writer:
            self.logger.warning("Cannot send message: not connected")
            return False
        
        try:
            json_data = message.to_json()
            # Add newline delimiter
            data = (json_data + "\n").encode('utf-8')
            
            self._send_writer.write(data)
            await self._send_writer.drain()
            
            self._messages_sent += 1
            self.logger.debug(f"Sent message: {message.type}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            return False
    
    async def send_command_approved(
        self, 
        robot_id: str, 
        commands: List[Dict[str, Any]]
    ) -> bool:
        """Send command approved response to UE5."""
        message = IPCMessage(
            type="command_approved",
            data={
                "robot_id": robot_id,
                "commands": commands
            }
        )
        return await self.send_message(message)
    
    async def send_command_rejected(
        self,
        robot_id: str,
        command_id: str,
        joint_name: str,
        reason: str
    ) -> bool:
        """Send command rejected response to UE5."""
        message = IPCMessage(
            type="command_rejected",
            data={
                "robot_id": robot_id,
                "command_id": command_id,
                "joint_name": joint_name,
                "reason": reason
            }
        )
        return await self.send_message(message)
    
    async def send_safety_alert(
        self,
        robot_id: str,
        alert_type: str,
        severity: str,
        message_text: str
    ) -> bool:
        """Send safety alert to UE5."""
        message = IPCMessage(
            type="safety_alert",
            data={
                "robot_id": robot_id,
                "alert_type": alert_type,
                "severity": severity,
                "message": message_text
            }
        )
        return await self.send_message(message)
    
    async def send_state_update(
        self,
        robot_id: str,
        mode: str,
        status: str,
        safety_status: Dict[str, Any]
    ) -> bool:
        """Send state update to UE5."""
        message = IPCMessage(
            type="state_update",
            data={
                "robot_id": robot_id,
                "mode": mode,
                "status": status,
                "safety_status": safety_status
            }
        )
        return await self.send_message(message)
    
    async def send_heartbeat_ack(self) -> bool:
        """Send heartbeat acknowledgment to UE5."""
        message = IPCMessage(
            type="heartbeat_ack",
            data={"source": "linux"}
        )
        self._last_heartbeat_sent = time.time()
        return await self.send_message(message)
    
    def register_callback(self, message_type: str, callback: MessageCallback):
        """
        Register callback for specific message type.
        
        Args:
            message_type: Type of message to handle.
            callback: Function to call when message received.
        """
        if message_type not in self._callbacks:
            self._callbacks[message_type] = []
        self._callbacks[message_type].append(callback)
        self.logger.debug(f"Registered callback for {message_type}")
    
    def unregister_callback(self, message_type: str, callback: MessageCallback):
        """Unregister a callback."""
        if message_type in self._callbacks:
            try:
                self._callbacks[message_type].remove(callback)
            except ValueError:
                pass
    
    async def _receive_loop(self):
        """Background loop to receive messages from UE5."""
        while self._running and self._receive_reader:
            try:
                # Read until newline delimiter
                data = await asyncio.wait_for(
                    self._receive_reader.readline(),
                    timeout=self.config.message_timeout_ms / 1000
                )
                
                if not data:
                    self.logger.warning("Connection closed by UE5")
                    break
                
                # Parse message
                json_str = data.decode('utf-8').strip()
                if not json_str:
                    continue
                
                message = IPCMessage.from_json(json_str)
                self._messages_received += 1
                
                # Handle heartbeat
                if message.type == "heartbeat":
                    self._last_heartbeat_received = time.time()
                    await self.send_heartbeat_ack()
                    continue
                
                # Dispatch to callbacks
                await self._dispatch_message(message)
                
            except asyncio.TimeoutError:
                # Normal timeout, continue loop
                continue
            except json.JSONDecodeError as e:
                self.logger.error(f"Invalid JSON received: {e}")
            except Exception as e:
                self.logger.error(f"Error in receive loop: {e}")
                break
    
    async def _dispatch_message(self, message: IPCMessage):
        """Dispatch message to registered callbacks."""
        callbacks = self._callbacks.get(message.type, [])
        
        if not callbacks:
            self.logger.warning(f"No callbacks for message type: {message.type}")
            return
        
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(message)
                else:
                    callback(message)
            except Exception as e:
                self.logger.error(f"Callback error for {message.type}: {e}")
    
    async def _heartbeat_loop(self):
        """Background loop to monitor heartbeat health."""
        interval = self.config.heartbeat_interval_ms / 1000
        
        while self._running:
            await asyncio.sleep(interval)
            
            if not self.heartbeat_healthy and self._last_heartbeat_received > 0:
                elapsed = time.time() - self._last_heartbeat_received
                self.logger.warning(
                    f"Heartbeat timeout: {elapsed:.1f}s since last heartbeat"
                )
                # Could trigger reconnection or alert here
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get IPC statistics."""
        return {
            "state": self._state.name,
            "messages_sent": self._messages_sent,
            "messages_received": self._messages_received,
            "reconnect_count": self._reconnect_count,
            "last_heartbeat": self._last_heartbeat_received,
            "heartbeat_healthy": self.heartbeat_healthy
        }
