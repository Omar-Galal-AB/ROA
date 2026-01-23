#!/usr/bin/env python3
"""
FTI-Webthread Bridge - Connects Files Type Importer to Webthread

This bridge provides:
1. Heartbeat reporting from FTI to Webthread
2. Status updates during file conversions
3. Progress streaming to UE5
4. Direct TCP communication for file operations

Architecture:
    FTI Component ──► FTI Bridge ──► Webthread ──► UE5 Plugin
                                        │
                                        └──► ROS2 Topics
"""

import json
import socket
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "Converters"))


class FTIWebthreadBridge:
    """
    Bridge between FTI and Webthread/UE5.

    Provides:
    - Heartbeat mechanism (every 500ms)
    - Conversion status updates
    - Progress reporting
    - Error propagation
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}

        # Webthread connection settings
        self.webthread_host = self.config.get("webthread_host", "localhost")
        self.webthread_port = self.config.get("webthread_port", 9876)

        # Component identification
        self.component_id = "FTI"
        self.component_name = "Files Type Importer"

        # Connection state
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.running = False

        # Heartbeat
        self.heartbeat_interval = self.config.get("heartbeat_interval", 0.5)
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.last_heartbeat = 0

        # Status tracking
        self.status = {
            "state": "initializing",
            "xacro_available": False,
            "active_conversions": 0,
            "last_conversion": None,
            "error": None,
        }

        # Callbacks
        self.on_command: Optional[Callable] = None
        self.on_connect: Optional[Callable] = None
        self.on_disconnect: Optional[Callable] = None

        # Receive buffer
        self._recv_buffer = ""

    def log(self, message: str, level: str = "info"):
        """Log with timestamp."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        prefix = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "success": "✅"}.get(level, "")
        print(f"[{timestamp}] FTI-Bridge {prefix}: {message}", flush=True)

    def connect(self, max_retries: int = 5, retry_delay: float = 2.0) -> bool:
        """
        Connect to Webthread/Command Server.

        Args:
            max_retries: Maximum connection attempts
            retry_delay: Seconds between retries

        Returns:
            True if connected successfully
        """
        for attempt in range(max_retries):
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(5.0)
                self.socket.connect((self.webthread_host, self.webthread_port))
                self.socket.settimeout(1.0)

                self.connected = True
                self.status["state"] = "connected"
                self.log(
                    f"Connected to Webthread at {self.webthread_host}:{self.webthread_port}",
                    "success",
                )

                # Send registration with source identifier
                self._send_message(
                    {
                        "type": "component_register",
                        "source": "wsl",  # This is a WSL-side component
                        "component_id": self.component_id,
                        "component_name": self.component_name,
                        "capabilities": ["xacro", "urdf", "stl", "obj", "usd"],
                    }
                )

                if self.on_connect:
                    self.on_connect()

                return True

            except Exception as e:
                self.log(
                    f"Connection attempt {attempt + 1}/{max_retries} failed: {e}",
                    "warning",
                )
                if self.socket:
                    self.socket.close()
                    self.socket = None

                if attempt < max_retries - 1:
                    time.sleep(retry_delay)

        self.status["state"] = "disconnected"
        self.status["error"] = "Failed to connect to Webthread"
        return False

    def disconnect(self):
        """Disconnect from Webthread."""
        self.connected = False
        if self.socket:
            try:
                self._send_message(
                    {"type": "component_unregister", "component_id": self.component_id}
                )
                self.socket.close()
            except:
                pass
            self.socket = None

        self.status["state"] = "disconnected"
        self.log("Disconnected from Webthread")

        if self.on_disconnect:
            self.on_disconnect()

    def start(self):
        """Start the bridge (heartbeat thread, receive thread)."""
        self.running = True

        # Start heartbeat thread
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()

        self.log("FTI-Webthread bridge started")

    def stop(self):
        """Stop the bridge."""
        self.running = False
        self.disconnect()
        self.log("FTI-Webthread bridge stopped")

    def _heartbeat_loop(self):
        """Send periodic heartbeats to Webthread."""
        while self.running:
            if self.connected:
                try:
                    self._send_heartbeat()
                except Exception as e:
                    self.log(f"Heartbeat failed: {e}", "warning")
                    self.connected = False

                    # Try to reconnect
                    time.sleep(2)
                    if self.running:
                        self.connect(max_retries=3)

            time.sleep(self.heartbeat_interval)

    def _send_heartbeat(self):
        """Send heartbeat message."""
        heartbeat = {
            "type": "heartbeat",
            "source": "wsl",  # WSL-side component
            "component_id": self.component_id,
            "timestamp": time.time(),
            "status": {
                "state": self.status.get("state", "healthy"),
                "response_time": 0.5,  # Could be calculated
                "errors": 0,
                "message": f"FTI active, xacro={self.status.get('xacro_available', False)}",
            },
        }
        self._send_message(heartbeat)
        self.last_heartbeat = time.time()

    def _send_message(self, message: Dict):
        """Send JSON message to Webthread."""
        if not self.socket or not self.connected:
            return

        try:
            data = json.dumps(message) + "\n"
            self.socket.sendall(data.encode("utf-8"))
        except Exception as e:
            self.log(f"Send failed: {e}", "error")
            self.connected = False
            raise

    def update_status(self, state: str, **kwargs):
        """
        Update component status.

        Args:
            state: Current state (idle, converting, error)
            **kwargs: Additional status fields
        """
        self.status["state"] = state
        for key, value in kwargs.items():
            self.status[key] = value

        # Send status update
        if self.connected:
            try:
                self._send_message(
                    {
                        "type": "status_update",
                        "component_id": self.component_id,
                        "status": self.status,
                    }
                )
            except:
                pass

    def send_conversion_progress(
        self, conversion_id: str, progress: float, message: str, file_name: str = ""
    ):
        """
        Send conversion progress update.

        Args:
            conversion_id: Unique conversion identifier
            progress: Progress percentage (0-100)
            message: Status message
            file_name: Name of file being converted
        """
        if self.connected:
            try:
                self._send_message(
                    {
                        "type": "conversion_progress",
                        "component_id": self.component_id,
                        "conversion_id": conversion_id,
                        "file_name": file_name,
                        "progress": progress,
                        "message": message,
                    }
                )
            except:
                pass

    def send_conversion_complete(
        self,
        conversion_id: str,
        success: bool,
        output_path: str = "",
        error_message: str = "",
        metadata: Optional[Dict] = None,
    ):
        """
        Send conversion completion notification.

        Args:
            conversion_id: Unique conversion identifier
            success: Whether conversion succeeded
            output_path: Path to output file
            error_message: Error message if failed
            metadata: Optional additional metadata (submechanisms, IK, etc.)
        """
        if self.connected:
            try:
                msg = {
                    "type": "conversion_complete",
                    "component_id": self.component_id,
                    "conversion_id": conversion_id,
                    "success": success,
                    "output_path": output_path,
                    "error_message": error_message,
                }
                # Include new FTI v3.0 metadata
                if metadata:
                    msg["metadata"] = metadata
                self._send_message(msg)
            except:
                pass

        # Update status
        self.status["last_conversion"] = {
            "id": conversion_id,
            "success": success,
            "timestamp": time.time(),
        }
        if not success:
            self.status["error"] = error_message


class FTIWithBridge:
    """
    FTI wrapper that includes Webthread bridge integration.

    Use this class instead of direct FTI when you need:
    - Progress reporting to UE5
    - Heartbeat/status monitoring
    - Remote file conversion requests
    - NEW: Submechanism detection and enhanced joints
    - NEW: IK solver configuration
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}

        # Initialize bridge
        self.bridge = FTIWebthreadBridge(config)

        # Import FileTypeImporter (main entry point with all new features)
        try:
            from file_type_importer import FileTypeImporter

            self.fti = FileTypeImporter()
            self.fti_available = True
        except ImportError:
            self.fti = None
            self.fti_available = False

        # Import converters
        try:
            from xacro_processor import XacroProcessor

            self.xacro_processor = XacroProcessor()
            self.bridge.status["xacro_available"] = True
        except ImportError:
            self.xacro_processor = None
            self.bridge.status["xacro_available"] = False

        try:
            from Converters.urdf_converter import URDFConverter

            self.urdf_converter = URDFConverter()
        except ImportError:
            self.urdf_converter = None

        # Conversion counter
        self._conversion_counter = 0

    def start(self):
        """Start FTI with bridge."""
        if self.bridge.connect():
            self.bridge.start()
            self.bridge.update_status("idle")
        else:
            self.bridge.log("Running in standalone mode (no Webthread connection)", "warning")

    def stop(self):
        """Stop FTI."""
        self.bridge.stop()

    def convert_xacro(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        xacro_args: Optional[Dict[str, str]] = None,
    ) -> tuple:
        """
        Convert XACRO file with progress reporting.

        Returns:
            Tuple of (success, message, output_path)
        """
        if not self.xacro_processor:
            return False, "XACRO processor not available", None

        # Generate conversion ID
        self._conversion_counter += 1
        conversion_id = f"xacro_{self._conversion_counter}"
        file_name = Path(input_path).name

        # Update status
        self.bridge.update_status("converting", active_conversions=1)
        self.bridge.send_conversion_progress(
            conversion_id, 0, "Starting XACRO conversion", file_name
        )

        # Set up progress callback
        def progress_callback(progress, message):
            self.bridge.send_conversion_progress(conversion_id, progress, message, file_name)

        self.xacro_processor.progress_callback = progress_callback

        # Run conversion
        success, message, result = self.xacro_processor.process(input_path, output_path, xacro_args)

        # Report completion
        self.bridge.send_conversion_complete(
            conversion_id,
            success,
            result if success else "",
            "" if success else message,
        )

        self.bridge.update_status("idle", active_conversions=0)

        return success, message, result

    def import_robot(
        self,
        file_path: str,
        robot_name: Optional[str] = None,
        output_path: Optional[str] = None,
        import_mode: str = "both",
        xacro_args: Optional[Dict[str, str]] = None,
    ) -> tuple:
        """
        Import robot using full FTI pipeline with enhanced features.

        NEW in v3.0:
        - Submechanism detection (identifies arm as serial chain)
        - Enhanced joint metadata (UE5 constraint parameters)
        - IK solver configuration

        Args:
            file_path: Path to robot file (URDF, XACRO, SDF, etc.)
            robot_name: Optional robot name
            output_path: Optional output directory
            import_mode: 'parts', 'assembly', or 'both'
            xacro_args: Optional dict of XACRO arguments (e.g., {'ur_type': 'ur5'})

        Returns:
            Tuple of (success, message, result_dict)
        """
        if not self.fti_available or not self.fti:
            return False, "FileTypeImporter not available", None

        # Generate conversion ID
        self._conversion_counter += 1
        conversion_id = f"import_{self._conversion_counter}"
        file_name = Path(file_path).name

        # Update status
        self.bridge.update_status("converting", active_conversions=1)
        self.bridge.send_conversion_progress(conversion_id, 0, "Starting robot import", file_name)

        try:
            # Call the main import
            self.bridge.send_conversion_progress(
                conversion_id, 10, "Detecting format...", file_name
            )

            result = self.fti.import_robot(
                file_path=file_path,
                robot_name=robot_name,
                import_mode=import_mode,
                output_path=output_path,
                xacro_args=xacro_args,
            )

            if result.success:
                self.bridge.send_conversion_progress(
                    conversion_id, 90, "Building metadata...", file_name
                )

                # Build enhanced metadata for GUI
                metadata = {
                    "version": "3.0",
                    "robot_name": result.robot_name,
                    "parts_count": result.parts_count,
                    "content_path": result.content_path,
                }

                # Include hierarchy path
                if hasattr(result, "hierarchy_path") and result.hierarchy_path:
                    metadata["hierarchy_path"] = result.hierarchy_path

                # Include submechanism info
                if hasattr(result, "submechanisms") and result.submechanisms:
                    sm_data = result.submechanisms
                    metadata["submechanisms"] = {
                        "available": sm_data.get("available", False),
                        "robot_type": sm_data.get("robot_type", "unknown"),
                        "count": len(sm_data.get("submechanisms", [])),
                    }

                # Include IK info
                if hasattr(result, "ik_available"):
                    metadata["ik_available"] = result.ik_available

                self.bridge.send_conversion_progress(
                    conversion_id, 100, "Import complete!", file_name
                )
                self.bridge.send_conversion_complete(
                    conversion_id, True, result.assembly_path or "", "", metadata
                )
                self.bridge.update_status("idle", active_conversions=0)

                return (
                    True,
                    "Robot imported successfully",
                    {
                        "assembly_path": result.assembly_path,
                        "parts_paths": result.parts_paths,
                        "hierarchy_path": getattr(result, "hierarchy_path", None),
                        "metadata": metadata,
                    },
                )
            else:
                self.bridge.send_conversion_complete(
                    conversion_id, False, "", result.error_message or "Unknown error"
                )
                self.bridge.update_status("idle", active_conversions=0)
                return False, result.error_message or "Import failed", None

        except Exception as e:
            error_msg = str(e)
            self.bridge.send_conversion_complete(conversion_id, False, "", error_msg)
            self.bridge.update_status("idle", active_conversions=0, error=error_msg)
            return False, f"Import error: {error_msg}", None

    def convert_xacro_to_usd(
        self,
        xacro_path: str,
        usd_output_path: str,
        robot_name: str = "robot",
        xacro_args: Optional[Dict[str, str]] = None,
    ) -> tuple:
        """
        Full pipeline: XACRO → URDF → USD

        Returns:
            Tuple of (success, message, usd_path)
        """
        self._conversion_counter += 1
        conversion_id = f"xacro_to_usd_{self._conversion_counter}"
        file_name = Path(xacro_path).name

        self.bridge.update_status("converting", active_conversions=1)

        # Step 1: XACRO → URDF
        self.bridge.send_conversion_progress(
            conversion_id, 10, "Converting XACRO to URDF", file_name
        )

        success, message, urdf_path = self.convert_xacro(xacro_path, xacro_args=xacro_args)
        if not success:
            self.bridge.send_conversion_complete(conversion_id, False, "", message)
            self.bridge.update_status("idle", active_conversions=0)
            return False, f"XACRO conversion failed: {message}", None

        # Step 2: URDF → USD
        self.bridge.send_conversion_progress(conversion_id, 50, "Converting URDF to USD", file_name)

        if not self.urdf_converter:
            self.bridge.send_conversion_complete(
                conversion_id, False, "", "URDF converter not available"
            )
            self.bridge.update_status("idle", active_conversions=0)
            return False, "URDF converter not available", None

        result = self.urdf_converter.convert(urdf_path, usd_output_path, robot_name)

        if result.success:
            self.bridge.send_conversion_progress(
                conversion_id, 100, "Conversion complete", file_name
            )
            self.bridge.send_conversion_complete(conversion_id, True, usd_output_path)
            self.bridge.update_status("idle", active_conversions=0)
            return True, "Successfully converted XACRO to USD", usd_output_path
        else:
            self.bridge.send_conversion_complete(conversion_id, False, "", result.error_message)
            self.bridge.update_status("idle", active_conversions=0)
            return False, f"URDF to USD conversion failed: {result.error_message}", None


# Entry point for standalone testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FTI-Webthread Bridge")
    parser.add_argument("--host", default="localhost", help="Webthread host")
    parser.add_argument("--port", type=int, default=9876, help="Webthread port")
    parser.add_argument("--test", action="store_true", help="Run connection test")

    args = parser.parse_args()

    if args.test:
        bridge = FTIWebthreadBridge({"webthread_host": args.host, "webthread_port": args.port})

        if bridge.connect():
            bridge.start()
            print("Bridge connected. Sending heartbeats every 0.5s. Press Ctrl+C to stop.")

            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                bridge.stop()
        else:
            print("Failed to connect to Webthread")
            sys.exit(1)
    else:
        # Run as FTI with bridge
        fti = FTIWithBridge({"webthread_host": args.host, "webthread_port": args.port})
        fti.start()

        print("FTI with Webthread bridge started. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            fti.stop()
