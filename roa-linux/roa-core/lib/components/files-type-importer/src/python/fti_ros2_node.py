"""
ROS2 Integration for Files Type Importer (FTI)
Provides ROS2 service interface for robot model import

v3.2 - Added COMC support:
- /fti/get_robot_specs service for retrieving robot specifications
- Robot specs cache for fast lookup
- COMC-compatible data export

v3.4 - Added real-time hot-reload:
- File watcher for automatic re-import on URDF/SDF changes
- Configurable watch directories
- Debounced reload (500ms) to avoid rapid triggers
- /fti/enable_watch and /fti/disable_watch services
"""

import json
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Set

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger

# File watching
try:
    from watchdog.events import FileModifiedEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

# Add parent directory to import FTI modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from file_type_importer import FileTypeImporter, ImportResult
from fti_data_export import FTIDataExporter


class FTIStatus:
    """Status constants for FTI"""

    NOT_STARTED = "not_started"
    INITIALIZING = "initializing"
    READY = "ready"
    IMPORTING = "importing"
    WATCHING = "watching"  # v3.4: New state for file watching
    ERROR = "error"


# v3.4: File watcher event handler
class URDFFileWatcher(FileSystemEventHandler if WATCHDOG_AVAILABLE else object):
    """
    File system event handler for URDF/SDF hot-reload (v3.4).

    Watches for modifications to robot description files and triggers
    re-import with debouncing to avoid rapid successive reloads.
    """

    def __init__(self, fti_node: "FTINode", debounce_ms: int = 500):
        if WATCHDOG_AVAILABLE:
            super().__init__()
        self.fti_node = fti_node
        self.debounce_ms = debounce_ms
        self._last_event_time: Dict[str, float] = {}
        self._watched_extensions = {".urdf", ".xacro", ".sdf", ".world"}
        self._lock = threading.Lock()

    def on_modified(self, event):
        """Handle file modification events with debouncing."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Only process robot description files
        if file_path.suffix.lower() not in self._watched_extensions:
            return

        with self._lock:
            current_time = time.time()
            last_time = self._last_event_time.get(str(file_path), 0)

            # Debounce: ignore events within debounce_ms of each other
            if (current_time - last_time) * 1000 < self.debounce_ms:
                return

            self._last_event_time[str(file_path)] = current_time

        # Trigger reload in FTI node
        self.fti_node.get_logger().info(f"[HotReload] Detected change: {file_path.name}")
        self.fti_node.trigger_hot_reload(str(file_path))


class FTINode(Node):
    """
    ROS2 Node for Files Type Importer integration with Webthread and COMC.

    Provides services and topics for robot model import operations.
    Includes /fti/get_robot_specs service for COMC coordination.

    v3.4: Supports real-time hot-reload of URDF/SDF files.
    """

    def __init__(self):
        """Initialize the FTI ROS2 node."""
        super().__init__("fti_node")

        # Initialize File Type Importer and Data Exporter
        self.fti = FileTypeImporter()
        self.data_exporter = FTIDataExporter()
        self.status = FTIStatus.INITIALIZING

        # Robot specs cache: {robot_id: {specs_data, hierarchy_data, import_result}}
        self._robot_cache: Dict[str, Dict] = {}

        # Create services
        self.import_service = self.create_service(
            Trigger,  # Using Trigger for now, will create custom srv later
            "fti/check_status",
            self.check_status_callback,
        )

        # NEW: Create robot specs service for COMC
        self.specs_service = self.create_service(
            Trigger,  # Uses Trigger: request is empty, response has success+message
            "fti/get_robot_specs",
            self.get_robot_specs_callback,
        )

        # Create publishers
        self.status_publisher = self.create_publisher(String, "fti/status", 10)

        self.result_publisher = self.create_publisher(String, "fti/import_result", 10)

        # NEW: Publisher for robot specs (for COMC to subscribe)
        self.specs_publisher = self.create_publisher(String, "fti/robot_specs", 10)

        # Create subscribers
        self.command_subscriber = self.create_subscription(
            String, "fti/import_command", self.import_command_callback, 10
        )

        # NEW: Subscriber for robot specs requests (alternative to service)
        self.specs_request_subscriber = self.create_subscription(
            String,
            "fti/get_robot_specs_request",
            self.get_robot_specs_request_callback,
            10,
        )

        # v3.4: File watcher for hot-reload
        self._file_observer: Optional["Observer"] = None
        self._watched_paths: Set[str] = set()
        self._file_to_robot_map: Dict[str, str] = {}  # Maps file paths to robot names

        # v3.4: Create hot-reload services
        if WATCHDOG_AVAILABLE:
            self.enable_watch_service = self.create_service(
                Trigger, "fti/enable_watch", self.enable_watch_callback
            )
            self.disable_watch_service = self.create_service(
                Trigger, "fti/disable_watch", self.disable_watch_callback
            )

            # v3.4: Publisher for hot-reload events
            self.reload_publisher = self.create_publisher(String, "fti/hot_reload", 10)

        # Publish initial status
        self.status = FTIStatus.READY
        self.publish_status()

        watchdog_status = "enabled" if WATCHDOG_AVAILABLE else "disabled (install watchdog)"
        self.get_logger().info(
            f"FTI Node initialized and ready (COMC + HotReload: {watchdog_status})"
        )

    def publish_status(self):
        """Publish current FTI status."""
        msg = String()
        msg.data = json.dumps(
            {
                "component": "FTI",
                "status": self.status,
                "supported_formats": self.fti.get_supported_formats(),
            }
        )
        self.status_publisher.publish(msg)

    def check_status_callback(self, request, response):
        """
        Service callback to check FTI status.

        Args:
            request: Service request
            response: Service response

        Returns:
            Response with status information
        """
        response.success = self.status == FTIStatus.READY
        response.message = json.dumps(
            {
                "status": self.status,
                "supported_formats": self.fti.get_supported_formats(),
            }
        )
        return response

    # ==================== v3.4: HOT-RELOAD METHODS ====================

    def enable_watch_callback(self, request, response):
        """
        Service callback to enable file watching for hot-reload (v3.4).

        Watches all directories containing previously imported robots.
        """
        if not WATCHDOG_AVAILABLE:
            response.success = False
            response.message = json.dumps(
                {"error": "watchdog package not installed. Run: pip install watchdog"}
            )
            return response

        try:
            if self._file_observer is not None:
                response.success = True
                response.message = json.dumps(
                    {
                        "message": "File watcher already running",
                        "watched_paths": list(self._watched_paths),
                    }
                )
                return response

            # Create and start observer
            self._file_observer = Observer()
            event_handler = URDFFileWatcher(self)

            # Watch directories of all imported files
            for file_path in self._file_to_robot_map.keys():
                dir_path = str(Path(file_path).parent)
                if dir_path not in self._watched_paths:
                    self._file_observer.schedule(event_handler, dir_path, recursive=True)
                    self._watched_paths.add(dir_path)
                    self.get_logger().info(f"[HotReload] Watching: {dir_path}")

            self._file_observer.start()
            self.status = FTIStatus.WATCHING
            self.publish_status()

            response.success = True
            response.message = json.dumps(
                {
                    "message": "File watcher started",
                    "watched_paths": list(self._watched_paths),
                }
            )
            self.get_logger().info("[HotReload] File watcher enabled")

        except Exception as e:
            response.success = False
            response.message = json.dumps({"error": str(e)})
            self.get_logger().error(f"[HotReload] Failed to start watcher: {e}")

        return response

    def disable_watch_callback(self, request, response):
        """Service callback to disable file watching (v3.4)."""
        try:
            if self._file_observer is not None:
                self._file_observer.stop()
                self._file_observer.join(timeout=2.0)
                self._file_observer = None
                self._watched_paths.clear()

                self.status = FTIStatus.READY
                self.publish_status()

                response.success = True
                response.message = json.dumps({"message": "File watcher stopped"})
                self.get_logger().info("[HotReload] File watcher disabled")
            else:
                response.success = True
                response.message = json.dumps({"message": "File watcher was not running"})
        except Exception as e:
            response.success = False
            response.message = json.dumps({"error": str(e)})

        return response

    def trigger_hot_reload(self, file_path: str):
        """
        Trigger a hot-reload for a modified file (v3.4).

        Called by URDFFileWatcher when a file change is detected.
        """
        robot_name = self._file_to_robot_map.get(file_path)

        if not robot_name:
            # Try to find by matching directory
            file_dir = str(Path(file_path).parent)
            for cached_path, cached_robot in self._file_to_robot_map.items():
                if str(Path(cached_path).parent) == file_dir:
                    robot_name = cached_robot
                    file_path = cached_path  # Use the originally imported file
                    break

        if not robot_name:
            self.get_logger().warning(f"[HotReload] No robot mapping for: {file_path}")
            return

        self.get_logger().info(f"[HotReload] Re-importing: {robot_name} from {file_path}")

        # Perform re-import
        try:
            result = self.fti.import_robot(
                file_path=file_path, robot_name=robot_name, import_mode="both"
            )

            if result.success:
                # Update cache
                hierarchy_data = getattr(result, "hierarchy", None)
                comc_specs = self.data_exporter.export_for_comc(result, hierarchy_data)

                self._robot_cache[robot_name] = {
                    "specs": comc_specs,
                    "hierarchy": hierarchy_data,
                    "import_result": result,
                }

                # Publish reload event
                if hasattr(self, "reload_publisher"):
                    reload_msg = String()
                    reload_msg.data = json.dumps(
                        {
                            "event": "hot_reload",
                            "robot_name": robot_name,
                            "file_path": file_path,
                            "success": True,
                            "timestamp": time.time(),
                        }
                    )
                    self.reload_publisher.publish(reload_msg)

                self.get_logger().info(f"[HotReload] Successfully reloaded: {robot_name}")
            else:
                self.get_logger().error(f"[HotReload] Failed: {result.error_message}")

        except Exception as e:
            self.get_logger().error(f"[HotReload] Exception during reload: {e}")

    def add_watch_path(self, file_path: str, robot_name: str):
        """
        Add a file to the watch list (v3.4).

        Called after successful import to enable hot-reload for the file.
        """
        self._file_to_robot_map[file_path] = robot_name

        # If watcher is running, add new directory
        if self._file_observer is not None and WATCHDOG_AVAILABLE:
            dir_path = str(Path(file_path).parent)
            if dir_path not in self._watched_paths:
                event_handler = URDFFileWatcher(self)
                self._file_observer.schedule(event_handler, dir_path, recursive=True)
                self._watched_paths.add(dir_path)
                self.get_logger().info(f"[HotReload] Added watch: {dir_path}")

    # ==================== END HOT-RELOAD METHODS ====================

    def import_command_callback(self, msg):
        """
        Topic callback to handle import commands.

        Args:
            msg: String message with JSON import command
        """
        try:
            command = json.loads(msg.data)

            # Extract command parameters
            file_path = command.get("file_path")
            robot_name = command.get("robot_name")
            import_mode = command.get("import_mode", "both")

            if not file_path:
                self.get_logger().error("Import command missing file_path")
                return

            # Update status
            self.status = FTIStatus.IMPORTING
            self.publish_status()

            # Perform import
            self.get_logger().info(f"Importing robot: {robot_name} from {file_path}")
            result = self.fti.import_robot(
                file_path=file_path, robot_name=robot_name, import_mode=import_mode
            )

            # Cache robot data for COMC
            if result.success:
                hierarchy_data = getattr(result, "hierarchy", None)
                robot_id = robot_name or result.robot_name

                # Generate COMC specs
                comc_specs = self.data_exporter.export_for_comc(result, hierarchy_data)

                # Cache for future requests
                self._robot_cache[robot_id] = {
                    "specs": comc_specs,
                    "hierarchy": hierarchy_data,
                    "import_result": result,
                }

                # Publish specs for COMC
                self.publish_robot_specs(robot_id, comc_specs)

                # v3.4: Register file for hot-reload
                self.add_watch_path(file_path, robot_id)

                self.get_logger().info(f"Cached robot specs for COMC: {robot_id}")

            # Publish result
            self.publish_import_result(result)

            # Update status (preserve WATCHING if watcher is running)
            if result.success:
                self.status = FTIStatus.WATCHING if self._file_observer else FTIStatus.READY
            else:
                self.status = FTIStatus.ERROR
            self.publish_status()

        except Exception as e:
            self.get_logger().error(f"Error processing import command: {e}")
            self.status = FTIStatus.ERROR
            self.publish_status()

    def get_robot_specs_callback(self, request, response):
        """
        Service callback to get robot specs for COMC.

        Returns all cached robot specs in JSON format.
        For specific robot, use get_robot_specs_request topic.

        Args:
            request: Service request (empty for Trigger)
            response: Service response

        Returns:
            Response with all robot specs
        """
        try:
            if not self._robot_cache:
                response.success = False
                response.message = json.dumps({"error": "No robots imported yet", "robots": []})
                return response

            # Return all cached robot specs
            all_specs = {
                robot_id: cache_entry["specs"]
                for robot_id, cache_entry in self._robot_cache.items()
            }

            response.success = True
            response.message = json.dumps({"robot_count": len(all_specs), "robots": all_specs})

            self.get_logger().info(f"Returned specs for {len(all_specs)} robots")
            return response

        except Exception as e:
            response.success = False
            response.message = json.dumps({"error": str(e)})
            return response

    def get_robot_specs_request_callback(self, msg):
        """
        Topic callback to handle robot specs requests.

        Request format: {"robot_id": "robot_name"} or {"all": true}

        Args:
            msg: String message with JSON request
        """
        try:
            request = json.loads(msg.data)

            if request.get("all", False):
                # Return all robots
                for robot_id, cache_entry in self._robot_cache.items():
                    self.publish_robot_specs(robot_id, cache_entry["specs"])
            else:
                # Return specific robot
                robot_id = request.get("robot_id")
                if robot_id and robot_id in self._robot_cache:
                    self.publish_robot_specs(robot_id, self._robot_cache[robot_id]["specs"])
                else:
                    self.get_logger().warning(f"Robot not found in cache: {robot_id}")
                    # Publish empty response
                    empty_specs = {
                        "robot_id": robot_id,
                        "error": "Robot not found in FTI cache",
                        "available_robots": list(self._robot_cache.keys()),
                    }
                    self.publish_robot_specs(robot_id, empty_specs)

        except Exception as e:
            self.get_logger().error(f"Error processing specs request: {e}")

    def publish_robot_specs(self, robot_id: str, specs: Dict):
        """
        Publish robot specs to ROS2 topic for COMC.

        Args:
            robot_id: Robot identifier
            specs: COMC-compatible robot specs dictionary
        """
        msg = String()
        msg.data = json.dumps(specs)
        self.specs_publisher.publish(msg)
        self.get_logger().debug(f"Published specs for robot: {robot_id}")

    def publish_import_result(self, result: ImportResult):
        """
        Publish import result to ROS2 topic.

        Args:
            result: ImportResult from FTI
        """
        msg = String()
        msg.data = json.dumps(
            {
                "success": result.success,
                "robot_name": result.robot_name,
                "content_path": result.content_path,
                "parts_count": result.parts_count,
                "assembly_path": result.assembly_path,
                "parts_paths": result.parts_paths,
                "error_message": result.error_message,
                "warnings": result.warnings,
            }
        )
        self.result_publisher.publish(msg)

        if result.success:
            self.get_logger().info(f"Import successful: {result.robot_name}")
        else:
            self.get_logger().error(f"Import failed: {result.error_message}")


def main(args=None):
    """Main entry point for FTI ROS2 node."""
    rclpy.init(args=args)

    fti_node = FTINode()

    try:
        rclpy.spin(fti_node)
    except KeyboardInterrupt:
        pass
    finally:
        fti_node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
