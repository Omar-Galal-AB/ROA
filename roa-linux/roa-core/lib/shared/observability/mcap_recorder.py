"""
ROA MCAP Recorder
=================
MCAP recording integration with rosbag2

Features:
- Direct MCAP file writing (standalone mode)
- rosbag2 integration for ROS2 topics
- Automatic file rotation
- Compression support
- Metadata and attachments
"""

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Callable, Dict, List, Optional

try:
    from mcap.well_known import MessageEncoding, SchemaEncoding
    from mcap.writer import Writer as MCAPWriter

    MCAP_AVAILABLE = True
except ImportError:
    MCAP_AVAILABLE = False

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.serialization import serialize_message
    from rosbag2_py import ConverterOptions, SequentialWriter, StorageOptions

    ROSBAG2_AVAILABLE = True
except ImportError:
    ROSBAG2_AVAILABLE = False

from .config import MCAPConfig, ObservabilityConfig


@dataclass
class ChannelInfo:
    """Information about a recording channel"""

    id: int
    topic: str
    message_type: str
    schema_id: int
    encoding: str = "ros2msg"
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class RecordingStats:
    """Statistics about the recording"""

    messages_written: int = 0
    bytes_written: int = 0
    channels: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    file_path: Optional[str] = None

    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0


class MCAPRecorder:
    """
    MCAP Recording Manager

    Provides MCAP file recording for ROA components.
    Can operate in standalone mode (no ROS2) or with rosbag2.

    Usage:
        # Standalone mode
        recorder = MCAPRecorder("webthread")
        recorder.start_recording()

        channel = recorder.register_channel("sensor_data", "SensorMessage")
        recorder.write_message(channel, data)

        recorder.stop_recording()

        # With rosbag2
        recorder = MCAPRecorder("webthread", use_rosbag2=True)
        recorder.start_recording(topics=["/sensor_data", "/robot_state"])
    """

    def __init__(
        self,
        component_name: str,
        config: Optional[MCAPConfig] = None,
        use_rosbag2: bool = False,
    ):
        self.component_name = component_name
        self.config = config or MCAPConfig()
        self.use_rosbag2 = use_rosbag2 and ROSBAG2_AVAILABLE

        self._file: Optional[BinaryIO] = None
        self._writer: Optional["MCAPWriter"] = None
        self._rosbag_writer: Optional["SequentialWriter"] = None

        self._channels: Dict[str, ChannelInfo] = {}
        self._schemas: Dict[str, int] = {}
        self._next_channel_id = 1
        self._next_schema_id = 1

        self._recording = False
        self._stats = RecordingStats()
        self._lock = threading.Lock()

        # Ensure output directory exists
        Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)

    def _generate_filename(self) -> str:
        """Generate recording filename"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(self.config.output_dir, f"roa_{self.component_name}_{timestamp}.mcap")

    # ─── Recording Control ─────────────────────────────────────

    def start_recording(
        self,
        filename: str = None,
        topics: List[str] = None,
        metadata: Dict[str, str] = None,
    ) -> str:
        """
        Start recording

        Args:
            filename: Output filename (auto-generated if not provided)
            topics: Topics to record (rosbag2 mode)
            metadata: Recording metadata

        Returns:
            Path to the recording file
        """
        with self._lock:
            if self._recording:
                raise RuntimeError("Already recording")

            filepath = filename or self._generate_filename()

            if self.use_rosbag2:
                self._start_rosbag2_recording(filepath, topics or [])
            else:
                self._start_standalone_recording(filepath, metadata)

            self._recording = True
            self._stats = RecordingStats(
                start_time=time.time(),
                file_path=filepath,
            )

            return filepath

    def _start_standalone_recording(self, filepath: str, metadata: Dict[str, str] = None):
        """Start standalone MCAP recording"""
        if not MCAP_AVAILABLE:
            raise RuntimeError("mcap package not installed. Run: pip install mcap")

        self._file = open(filepath, "wb")
        self._writer = MCAPWriter(self._file)
        self._writer.start()

        # Build metadata dict
        meta_dict = {
            "roa.component": self.component_name,
            "roa.version": "1.0.0",
            "roa.timestamp": datetime.now().isoformat(),
        }

        # Add custom metadata
        if metadata:
            for key, value in metadata.items():
                meta_dict[key] = json.dumps(value) if not isinstance(value, str) else value

        # Write all metadata as a single entry
        self._writer.add_metadata("roa", meta_dict)

    def _start_rosbag2_recording(self, filepath: str, topics: List[str]):
        """Start rosbag2 recording"""
        if not ROSBAG2_AVAILABLE:
            raise RuntimeError("rosbag2 not available. Ensure ROS2 is installed.")

        storage_options = StorageOptions(
            uri=filepath,
            storage_id="mcap",
        )

        converter_options = ConverterOptions(
            input_serialization_format="cdr",
            output_serialization_format="cdr",
        )

        self._rosbag_writer = SequentialWriter()
        self._rosbag_writer.open(storage_options, converter_options)

        # Topics will be registered as they're encountered

    def stop_recording(self) -> RecordingStats:
        """
        Stop recording

        Returns:
            Recording statistics
        """
        with self._lock:
            if not self._recording:
                return self._stats

            self._stats.end_time = time.time()

            if self._writer:
                self._writer.finish()
                self._file.close()
                self._writer = None
                self._file = None

            if self._rosbag_writer:
                del self._rosbag_writer
                self._rosbag_writer = None

            self._recording = False
            self._channels.clear()
            self._schemas.clear()
            self._next_channel_id = 1
            self._next_schema_id = 1

            return self._stats

    def is_recording(self) -> bool:
        """Check if recording is active"""
        return self._recording

    # ─── Channel Management ────────────────────────────────────

    def register_channel(
        self,
        topic: str,
        message_type: str,
        schema: str = None,
        encoding: str = "json",
        metadata: Dict[str, str] = None,
    ) -> ChannelInfo:
        """
        Register a channel for recording

        Args:
            topic: Topic/channel name
            message_type: Message type name
            schema: Schema definition (JSON Schema, Protobuf, etc.)
            encoding: Message encoding (json, protobuf, ros2msg)
            metadata: Channel metadata

        Returns:
            ChannelInfo for writing messages
        """
        with self._lock:
            if topic in self._channels:
                return self._channels[topic]

            if not self._recording or not self._writer:
                raise RuntimeError("Not recording")

            # Register schema if provided
            schema_id = 0
            if schema:
                schema_key = f"{message_type}:{encoding}"
                if schema_key not in self._schemas:
                    schema_id = self._next_schema_id
                    self._next_schema_id += 1

                    # Map encoding to MCAP schema encoding
                    if encoding == "json":
                        schema_encoding = "jsonschema"
                    elif encoding == "protobuf":
                        schema_encoding = "protobuf"
                    else:
                        schema_encoding = encoding

                    self._writer.register_schema(
                        name=message_type,
                        encoding=schema_encoding,
                        data=schema.encode() if isinstance(schema, str) else schema,
                    )
                    self._schemas[schema_key] = schema_id
                else:
                    schema_id = self._schemas[schema_key]

            # Register channel
            channel_id = self._next_channel_id
            self._next_channel_id += 1

            # Map encoding to MCAP message encoding
            if encoding == "json":
                msg_encoding = "json"
            elif encoding == "protobuf":
                msg_encoding = "protobuf"
            else:
                msg_encoding = encoding

            self._writer.register_channel(
                topic=topic,
                message_encoding=msg_encoding,
                schema_id=schema_id,
                metadata=metadata or {},
            )

            channel = ChannelInfo(
                id=channel_id,
                topic=topic,
                message_type=message_type,
                schema_id=schema_id,
                encoding=encoding,
                metadata=metadata or {},
            )

            self._channels[topic] = channel
            self._stats.channels += 1

            return channel

    # ─── Message Writing ───────────────────────────────────────

    def write_message(
        self,
        channel: ChannelInfo,
        data: Any,
        timestamp: int = None,
        publish_time: int = None,
    ):
        """
        Write a message to the recording

        Args:
            channel: Channel to write to
            data: Message data (will be serialized based on encoding)
            timestamp: Log time in nanoseconds (uses current time if not provided)
            publish_time: Publish time in nanoseconds (uses timestamp if not provided)
        """
        with self._lock:
            if not self._recording or not self._writer:
                return

            # Serialize data
            if channel.encoding == "json":
                if isinstance(data, (dict, list)):
                    payload = json.dumps(data).encode()
                elif isinstance(data, str):
                    payload = data.encode()
                elif isinstance(data, bytes):
                    payload = data
                else:
                    payload = json.dumps(data, default=str).encode()
            elif isinstance(data, bytes):
                payload = data
            else:
                payload = str(data).encode()

            # Generate timestamps
            if timestamp is None:
                timestamp = int(time.time() * 1e9)  # Current time in nanoseconds
            if publish_time is None:
                publish_time = timestamp

            self._writer.add_message(
                channel_id=channel.id,
                log_time=timestamp,
                data=payload,
                publish_time=publish_time,
            )

            self._stats.messages_written += 1
            self._stats.bytes_written += len(payload)

    def write_json(
        self,
        topic: str,
        data: Dict[str, Any],
        message_type: str = "JSONMessage",
    ):
        """
        Convenience method to write JSON data

        Automatically registers channel if needed.
        """
        if topic not in self._channels:
            self.register_channel(topic, message_type, encoding="json")

        self.write_message(self._channels[topic], data)

    # ─── Attachments ───────────────────────────────────────────

    def add_attachment(
        self,
        name: str,
        data: bytes,
        media_type: str = "application/octet-stream",
        log_time: int = None,
    ):
        """
        Add an attachment to the recording

        Useful for configuration files, calibration data, etc.
        """
        with self._lock:
            if not self._recording or not self._writer:
                return

            if log_time is None:
                log_time = int(time.time() * 1e9)

            self._writer.add_attachment(
                log_time=log_time,
                create_time=log_time,
                name=name,
                media_type=media_type,
                data=data,
            )

    def add_attachment_file(self, filepath: str, name: str = None):
        """Add a file as an attachment"""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        # Determine media type
        suffix = path.suffix.lower()
        media_types = {
            ".json": "application/json",
            ".yaml": "application/x-yaml",
            ".yml": "application/x-yaml",
            ".xml": "application/xml",
            ".txt": "text/plain",
            ".csv": "text/csv",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }
        media_type = media_types.get(suffix, "application/octet-stream")

        self.add_attachment(
            name=name or path.name,
            data=path.read_bytes(),
            media_type=media_type,
        )

    # ─── Statistics ────────────────────────────────────────────

    def get_stats(self) -> RecordingStats:
        """Get current recording statistics"""
        with self._lock:
            if self._recording:
                self._stats.end_time = time.time()
            return self._stats

    # ─── Context Manager ───────────────────────────────────────

    def __enter__(self):
        self.start_recording()
        return self

    def __exit__(self, *args):
        self.stop_recording()


# ─── ROA Event Recorder ────────────────────────────────────────


class ROAEventRecorder:
    """
    High-level event recorder for ROA components

    Records component events, state changes, and messages
    with automatic channel management.

    Usage:
        recorder = ROAEventRecorder("webthread")
        recorder.start()

        recorder.record_event("component_started", {"version": "1.0.0"})
        recorder.record_state_change("initializing", "running")
        recorder.record_message("sensor_data", sensor_reading)

        recorder.stop()
    """

    def __init__(self, component_name: str, config: Optional[MCAPConfig] = None):
        self.component_name = component_name
        self._recorder = MCAPRecorder(component_name, config)

        self._event_channel: Optional[ChannelInfo] = None
        self._state_channel: Optional[ChannelInfo] = None
        self._message_channels: Dict[str, ChannelInfo] = {}

    def start(self, filename: str = None) -> str:
        """Start recording"""
        filepath = self._recorder.start_recording(filename)

        # Register standard channels
        self._event_channel = self._recorder.register_channel(
            f"/roa/{self.component_name}/events",
            "ROAEvent",
            encoding="json",
        )

        self._state_channel = self._recorder.register_channel(
            f"/roa/{self.component_name}/state",
            "ROAStateChange",
            encoding="json",
        )

        return filepath

    def stop(self) -> RecordingStats:
        """Stop recording"""
        return self._recorder.stop_recording()

    def record_event(
        self,
        event_type: str,
        data: Dict[str, Any] = None,
        severity: str = "info",
    ):
        """Record an event"""
        if not self._event_channel:
            return

        event = {
            "timestamp": datetime.now().isoformat(),
            "component": self.component_name,
            "event_type": event_type,
            "severity": severity,
            "data": data or {},
        }

        self._recorder.write_message(self._event_channel, event)

    def record_state_change(
        self,
        from_state: str,
        to_state: str,
        reason: str = None,
    ):
        """Record a state change"""
        if not self._state_channel:
            return

        change = {
            "timestamp": datetime.now().isoformat(),
            "component": self.component_name,
            "from_state": from_state,
            "to_state": to_state,
            "reason": reason,
        }

        self._recorder.write_message(self._state_channel, change)

    def record_message(
        self,
        topic: str,
        data: Dict[str, Any],
        message_type: str = "ROAMessage",
    ):
        """Record a custom message"""
        full_topic = f"/roa/{self.component_name}/{topic}"

        if full_topic not in self._message_channels:
            self._message_channels[full_topic] = self._recorder.register_channel(
                full_topic,
                message_type,
                encoding="json",
            )

        self._recorder.write_message(self._message_channels[full_topic], data)

    def record_heartbeat(self, target: str, latency_ms: float):
        """Record a heartbeat event"""
        self.record_event(
            "heartbeat",
            {
                "target": target,
                "latency_ms": latency_ms,
            },
        )

    def record_error(self, error_type: str, message: str, details: Dict[str, Any] = None):
        """Record an error event"""
        self.record_event(
            "error",
            {
                "error_type": error_type,
                "message": message,
                "details": details or {},
            },
            severity="error",
        )

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
