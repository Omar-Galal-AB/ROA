"""
DIMC Core - Main Dimensions Collector Coordinator v2.0

Coordinates all tracking, measurement, sensor, and obstacle detection operations.
Receives data from UE5 C++ plugin via ROA Bridge.

ARCHITECTURE NOTE:
- All sensing (LIDAR raycast, obstacle detection) happens in UE5/C++
- This Python layer receives processed data and coordinates ROS2 publishing
- ROS2 publishing happens on Linux side only

Integrated with ROA Observability Stack for metrics, logging, and tracing.
"""

import json
import logging
import math
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml

# Import Observability
try:
    # Add shared observability to path
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    _shared_path = os.path.abspath(os.path.join(_current_dir, "..", "..", "..", "..", "shared"))
    if _shared_path not in sys.path:
        sys.path.insert(0, _shared_path)

    from observability import (
        HealthCheck,
    )
    from observability import HealthStatus as ObsHealthStatus
    from observability import (
        ROAEventRecorder,
        ROALogger,
        ROAMetrics,
        ROAObservability,
        ROATracer,
    )

    OBSERVABILITY_AVAILABLE = True
except ImportError as e:
    logging.debug(f"Observability not available for DIMC: {e}")
    OBSERVABILITY_AVAILABLE = False

from .Export.csv_exporter import CsvExporter
from .Export.json_exporter import JsonExporter
from .Export.rosbag_exporter import RosbagExporter
from .Measurement.bounds_calculator import BoundsCalculator
from .Measurement.safety_zones import SafetyZoneCalculator
from .Measurement.size_measurer import SizeMeasurer
from .obstacle_detection import CollisionRisk, ObstacleDetection
from .ros2_publisher import DIMCPublisher
from .sensor_simulation import (
    LidarScanData,
    ObstacleData,
    ObstacleType,
    SensorDataReceiver,
    SensorType,
)
from .Tracking.delta_calculator import DeltaCalculator
from .Tracking.distance_calculator import DistanceCalculator
from .Tracking.orientation_tracker import OrientationTracker

# Import subsystems
from .Tracking.position_tracker import PositionTracker

# Import Bridge subsystem (UE5 ↔ WSL data exchange)
try:
    from .UE5Bridge import (
        ConnectionHealth,
        ConnectionMonitor,
        ConnectionState,
        DIMCUe5Connector,
    )

    BRIDGE_AVAILABLE = True
except ImportError as e:
    logging.debug(f"UE5 Bridge not available: {e}")
    BRIDGE_AVAILABLE = False
    DIMCUe5Connector = None
    ConnectionState = None
    ConnectionMonitor = None
    ConnectionHealth = None

# Import Heartbeat subsystem (Health status monitoring)
try:
    from .dimc_heartbeat import (
        ComponentHealth,
        DIMCHeartbeat,
        DIMCHeartbeatMonitor,
        HeartbeatState,
    )

    HEARTBEAT_AVAILABLE = True
except ImportError as e:
    logging.debug(f"Heartbeat agent not available: {e}")
    HEARTBEAT_AVAILABLE = False
    DIMCHeartbeat = None
    DIMCHeartbeatMonitor = None
    HeartbeatState = None
    ComponentHealth = None

# Import Monitoring System
try:
    from .dimc_monitoring import (
        AlertCategory,
        AlertSeverity,
        DIMCMonitoringSystem,
        MonitoringConfig,
        SubsystemStatus,
    )

    MONITORING_AVAILABLE = True
except ImportError as e:
    logging.debug(f"Monitoring system not available: {e}")
    MONITORING_AVAILABLE = False
    DIMCMonitoringSystem = None
    MonitoringConfig = None
    SubsystemStatus = None


class RobotType(Enum):
    """Robot type classification - matches C++ ERobotType"""

    INDUSTRIAL_ARM = "IndustrialArm"
    MOBILE_ROBOT = "MobileRobot"
    HUMANOID = "Humanoid"
    DRONE = "Drone"
    SINGLE_ACTUATOR = "SingleActuator"
    COLLABORATIVE = "Collaborative"
    GENERIC = "Generic"


@dataclass
class RobotDimensions:
    """Robot dimensions - matches C++ FRobotDimensions"""

    width: float = 0.0
    height: float = 0.0
    length: float = 0.0
    radius: float = 0.0
    volume: float = 0.0
    mass: float = 0.0
    reach: float = 0.0  # For arms


@dataclass
class RobotInfo:
    """Complete robot information"""

    robot_id: str
    robot_type: RobotType
    position: Tuple[float, float, float]  # meters
    orientation: Tuple[float, float, float, float]  # Quaternion (x, y, z, w)
    velocity: Tuple[float, float, float]  # m/s
    dimensions: RobotDimensions
    timestamp: float

    # FTI data flags
    has_urdf_dimensions: bool = False
    has_urdf_sensors: bool = False
    has_urdf_safety_zones: bool = False


class DimensionsCollector:
    """
    Main DIMC coordinator class v2.0

    Receives data from UE5 C++ plugin (ADimensionsCollector).
    Manages tracking, measurement, and ROS2 publishing.
    Provides API for Evade subsystem, ROC, and other ROA components.
    """

    def __init__(self, config_path: Optional[Path] = None, enable_obs: bool = True):
        """
        Initialize Dimensions Collector

        Args:
            config_path: Path to configuration directory (default: Config/)
            enable_obs: Enable Observability (default True)
        """
        self.logger = self._setup_logging()
        self.config_path = config_path or Path(__file__).parent.parent.parent / "Config"
        self.config = self._load_configuration()

        # Observability
        self._observability: Optional["ROAObservability"] = None
        self._obs_enabled = enable_obs and OBSERVABILITY_AVAILABLE

        if self._obs_enabled:
            self._init_observability()

        # Initialize subsystems
        self.position_tracker = PositionTracker(self.config.get("tracking", {}).get("position", {}))
        self.orientation_tracker = OrientationTracker(
            self.config.get("tracking", {}).get("orientation", {})
        )
        self.delta_calculator = DeltaCalculator(self.config.get("tracking", {}).get("velocity", {}))
        self.distance_calculator = DistanceCalculator(
            self.config.get("tracking", {}).get("distance", {})
        )

        self.size_measurer = SizeMeasurer(self.config.get("measurement", {}))
        self.bounds_calculator = BoundsCalculator(self.config.get("measurement", {}))
        self.safety_zone_calculator = SafetyZoneCalculator(
            self.config.get("measurement", {}).get("safety_margin", 0.1)
        )

        # Exporters
        export_config = self.config.get("export", {})
        self.rosbag_exporter = RosbagExporter(export_config.get("rosbag", {}))
        self.json_exporter = JsonExporter(export_config.get("json", {}))
        self.csv_exporter = CsvExporter(export_config.get("csv", {}))

        # Sensor data receiver (receives data from C++ plugin)
        self.sensor_receiver = SensorDataReceiver(self.config)

        # Obstacle detection (uses sensor receiver)
        self.obstacle_detection = ObstacleDetection(self.config, self.sensor_receiver)

        # ROS2 publisher (Linux side only)
        self.ros2_publisher: Optional[DIMCPublisher] = None

        # Robot registry with thread-safe access
        self.robots: Dict[str, Dict] = {}
        self._robots_lock = threading.RLock()  # Reentrant lock for nested access

        # Monitoring zones (from COMC)
        self.monitoring_zones: Dict[str, Dict] = {}

        # Bridge subsystem (UE5 ↔ WSL data exchange)
        self.ue5_connector: Optional["DIMCUe5Connector"] = None
        self.connection_monitor: Optional["ConnectionMonitor"] = None
        self._bridge_enabled = BRIDGE_AVAILABLE and self.config.get("bridge", {}).get(
            "enabled", True
        )

        # Heartbeat subsystem (Health status monitoring)
        self.heartbeat: Optional["DIMCHeartbeat"] = None
        self.heartbeat_monitor: Optional["DIMCHeartbeatMonitor"] = None
        self._heartbeat_enabled = HEARTBEAT_AVAILABLE and self.config.get("heartbeat", {}).get(
            "enabled", True
        )

        # Monitoring System (comprehensive health and performance monitoring)
        self.monitoring: Optional["DIMCMonitoringSystem"] = None
        self._monitoring_enabled = MONITORING_AVAILABLE and self.config.get("monitoring", {}).get(
            "enabled", True
        )

        # Degradation state
        self._degraded = False
        self._degradation_reason: Optional[str] = None

        # Statistics
        self._stats = {
            "messages_received": 0,
            "messages_processed": 0,
            "updates_total": 0,
            "errors_total": 0,
            "validation_failures": 0,
            "start_time": None,
        }

        # State
        self.initialized = False
        self.update_rate = self.config.get("update_rate_hz", 60)
        self.last_update_time = 0.0

        self.logger.info("DimensionsCollector v2.0 initialized")

    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        logger = logging.getLogger("DIMC")
        logger.setLevel(logging.INFO)

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        return logger

    def _load_configuration(self) -> Dict:
        """Load all configuration files with validation"""
        config = {}

        # Load dimc_settings.json
        settings_file = self.config_path / "dimc_settings.json"
        if settings_file.exists():
            try:
                with open(settings_file, "r") as f:
                    config.update(json.load(f))
            except json.JSONDecodeError as e:
                self.logger.error(f"Invalid JSON in {settings_file}: {e}")

        # Load tracking_params.yaml
        tracking_file = self.config_path / "tracking_params.yaml"
        if tracking_file.exists():
            try:
                with open(tracking_file, "r") as f:
                    yaml_config = yaml.safe_load(f)
                    if yaml_config:
                        config.update(yaml_config)
            except yaml.YAMLError as e:
                self.logger.error(f"Invalid YAML in {tracking_file}: {e}")

        # Load export_config.json
        export_file = self.config_path / "export_config.json"
        if export_file.exists():
            try:
                with open(export_file, "r") as f:
                    config["export"] = json.load(f)
            except json.JSONDecodeError as e:
                self.logger.error(f"Invalid JSON in {export_file}: {e}")

        # Validate and apply defaults
        config = self._validate_configuration(config)

        return config

    def _validate_configuration(self, config: Dict) -> Dict:
        """
        Validate configuration and apply defaults.

        Args:
            config: Raw configuration dictionary

        Returns:
            Validated configuration with defaults applied
        """
        # Define schema with defaults
        defaults = {
            "update_rate_hz": 60,
            "coordinate_frame": "world",
            "measurement_type": "both",
            "safety_margin_meters": 0.1,
            "enable_export": True,
            "export_interval_seconds": 60,
            "max_robots": 10,
            "logging": {"enabled": True, "level": "INFO", "file": "dimc.log"},
            "bridge": {
                "enabled": True,
                "host": "127.0.0.1",
                "request_port": 9876,
                "response_port": 9877,
                "auto_connect": True,
                "reconnect_enabled": True,
            },
            "heartbeat": {
                "enabled": True,
                "interval": 5.0,
                "ipc_path": "/mnt/d/ROA/.ipc",
            },
            "monitoring": {
                "enabled": True,
                "health_check_interval": 5.0,
                "resource_check_interval": 10.0,
            },
            "proximity": {"critical_m": 0.5, "caution_m": 1.0, "warning_m": 2.0},
            "collision": {
                "critical_threshold": 0.9,
                "high_threshold": 0.7,
                "medium_threshold": 0.4,
            },
        }

        # Deep merge defaults with provided config
        validated = self._deep_merge(defaults, config)

        # Validate specific fields
        if not isinstance(validated["update_rate_hz"], (int, float)):
            self.logger.warning(f"Invalid update_rate_hz, using default 60")
            validated["update_rate_hz"] = 60
        elif validated["update_rate_hz"] <= 0 or validated["update_rate_hz"] > 1000:
            self.logger.warning(f"update_rate_hz out of range (0-1000), using 60")
            validated["update_rate_hz"] = 60

        if not isinstance(validated["max_robots"], int):
            validated["max_robots"] = 10
        elif validated["max_robots"] <= 0 or validated["max_robots"] > 100:
            self.logger.warning(f"max_robots out of range (1-100), using 10")
            validated["max_robots"] = 10

        return validated

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two dictionaries, with override taking precedence."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    # =========================================================================
    # INPUT VALIDATION HELPERS
    # =========================================================================

    def _validate_position(self, position: Any) -> Optional[Tuple[float, float, float]]:
        """
        Validate position tuple.

        Args:
            position: Position data to validate

        Returns:
            Validated (x, y, z) tuple or None if invalid
        """
        if position is None:
            return None

        try:
            if not isinstance(position, (list, tuple)) or len(position) != 3:
                return None

            x, y, z = float(position[0]), float(position[1]), float(position[2])

            # Check for NaN or Infinity
            if math.isnan(x) or math.isnan(y) or math.isnan(z):
                self.logger.warning("Position contains NaN values")
                return None
            if math.isinf(x) or math.isinf(y) or math.isinf(z):
                self.logger.warning("Position contains Infinity values")
                return None

            # Reasonable bounds check (1km range)
            MAX_COORD = 1000.0
            if abs(x) > MAX_COORD or abs(y) > MAX_COORD or abs(z) > MAX_COORD:
                self.logger.warning(f"Position out of bounds: ({x}, {y}, {z})")
                return None

            return (x, y, z)
        except (TypeError, ValueError) as e:
            self.logger.warning(f"Invalid position format: {e}")
            return None

    def _validate_orientation(
        self, orientation: Any
    ) -> Optional[Tuple[float, float, float, float]]:
        """
        Validate quaternion orientation.

        Args:
            orientation: Orientation data to validate

        Returns:
            Validated (x, y, z, w) quaternion or None if invalid
        """
        if orientation is None:
            return None

        try:
            if not isinstance(orientation, (list, tuple)) or len(orientation) != 4:
                return None

            x, y, z, w = (
                float(orientation[0]),
                float(orientation[1]),
                float(orientation[2]),
                float(orientation[3]),
            )

            # Check for NaN
            if any(math.isnan(v) for v in (x, y, z, w)):
                self.logger.warning("Orientation contains NaN values")
                return None

            # Quaternion should be normalized (magnitude ~1.0)
            magnitude = math.sqrt(x * x + y * y + z * z + w * w)
            if magnitude < 0.9 or magnitude > 1.1:
                # Auto-normalize if close enough
                if magnitude > 0.1:
                    x, y, z, w = (
                        x / magnitude,
                        y / magnitude,
                        z / magnitude,
                        w / magnitude,
                    )
                else:
                    self.logger.warning(f"Invalid quaternion magnitude: {magnitude}")
                    return None

            return (x, y, z, w)
        except (TypeError, ValueError) as e:
            self.logger.warning(f"Invalid orientation format: {e}")
            return None

    def _validate_velocity(self, velocity: Any) -> Tuple[float, float, float]:
        """
        Validate velocity tuple.

        Args:
            velocity: Velocity data to validate

        Returns:
            Validated (vx, vy, vz) tuple or (0, 0, 0) if invalid
        """
        if velocity is None:
            return (0.0, 0.0, 0.0)

        try:
            if not isinstance(velocity, (list, tuple)) or len(velocity) != 3:
                return (0.0, 0.0, 0.0)

            vx, vy, vz = float(velocity[0]), float(velocity[1]), float(velocity[2])

            # Check for NaN
            if any(math.isnan(v) for v in (vx, vy, vz)):
                return (0.0, 0.0, 0.0)

            # Reasonable velocity bounds (100 m/s)
            MAX_VEL = 100.0
            vx = max(-MAX_VEL, min(MAX_VEL, vx))
            vy = max(-MAX_VEL, min(MAX_VEL, vy))
            vz = max(-MAX_VEL, min(MAX_VEL, vz))

            return (vx, vy, vz)
        except (TypeError, ValueError):
            return (0.0, 0.0, 0.0)

    def _validate_robot_data(self, robot_id: str, state: Dict) -> Optional[Dict]:
        """
        Validate incoming robot state data from C++ plugin.

        Args:
            robot_id: Robot identifier
            state: State dictionary from C++ plugin

        Returns:
            Validated state dictionary or None if critical validation fails
        """
        if not isinstance(state, dict):
            self._stats["validation_failures"] += 1
            return None

        validated = {}

        # Validate required position
        position = self._validate_position(state.get("position"))
        if position is None:
            self._stats["validation_failures"] += 1
            self.logger.warning(f"Robot {robot_id}: Invalid or missing position")
            return None
        validated["position"] = position

        # Validate orientation (required)
        orientation = self._validate_orientation(state.get("orientation"))
        if orientation is None:
            # Use identity quaternion as fallback
            orientation = (0.0, 0.0, 0.0, 1.0)
            self.logger.debug(f"Robot {robot_id}: Using default orientation")
        validated["orientation"] = orientation

        # Validate optional velocity
        validated["velocity"] = self._validate_velocity(state.get("velocity"))
        validated["angular_velocity"] = self._validate_velocity(state.get("angular_velocity"))

        # Pass through optional sensor data (validated separately)
        if "lidar_scan" in state:
            validated["lidar_scan"] = state["lidar_scan"]
        if "obstacles" in state:
            validated["obstacles"] = state["obstacles"]
        if "sensor_name" in state:
            validated["sensor_name"] = state["sensor_name"]

        return validated

    def _init_observability(self):
        """Initialize ROA Observability for DIMC"""
        try:
            self._observability = ROAObservability(
                component_name="dimc",
                service_version="1.0.0",
                auto_start=False,
            )

            # Register DIMC-specific metrics
            self._register_dimc_metrics()

            self.logger.info("DIMC Observability initialized")
        except Exception as e:
            self.logger.warning(f"Failed to initialize DIMC Observability: {e}")
            self._observability = None
            self._obs_enabled = False

    def _register_dimc_metrics(self):
        """Register DIMC-specific observability metrics"""
        if not self._observability:
            return

        metrics = self._observability.metrics

        # Tracking metrics
        self._position_updates = metrics.register_counter(
            "dimc_position_updates_total",
            "Total position updates processed",
            ["robot_id"],
        )

        self._tracking_latency = metrics.register_histogram(
            "dimc_tracking_latency_seconds",
            "Position tracking processing latency",
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1],
        )

        # Sensor metrics
        self._sensor_readings = metrics.register_counter(
            "dimc_sensor_readings_total",
            "Total sensor readings processed",
            ["sensor_type"],
        )

        # Obstacle detection metrics
        self._obstacles_detected = metrics.register_counter(
            "dimc_obstacles_detected_total",
            "Total obstacles detected",
            ["severity"],
        )

        self._obstacle_distance = metrics.register_histogram(
            "dimc_obstacle_distance_meters",
            "Distance to detected obstacles",
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
        )

        # Robot registry metrics
        self._active_robots = metrics.register_gauge(
            "dimc_active_robots",
            "Number of active robots being tracked",
        )

        # Export metrics
        self._exports_total = metrics.register_counter(
            "dimc_exports_total",
            "Total data exports",
            ["format", "status"],
        )

    def start(self):
        """Start DIMC with observability, Bridge, Heartbeat, and Monitoring agents"""
        self._stats["start_time"] = time.time() if "time" in dir() else __import__("time").time()

        # Start Observability
        if self._obs_enabled and self._observability:
            self._observability.start()
            self._observability.health.set_healthy()
            self._observability.logger.info(
                "DIMC started", extra={"component": "dimc", "action": "start"}
            )

        # Start Monitoring System
        if self._monitoring_enabled and MONITORING_AVAILABLE:
            self._start_monitoring()

        # Start Heartbeat agent
        if self._heartbeat_enabled and HEARTBEAT_AVAILABLE:
            self._start_heartbeat()

        # Start Bridge agent
        if self._bridge_enabled and BRIDGE_AVAILABLE:
            self._start_bridge()

        self.logger.info("DIMC started")

    def _start_monitoring(self):
        """Initialize and start Monitoring System."""
        try:
            from .dimc_monitoring import DIMCMonitoringSystem, MonitoringConfig

            # Configure monitoring
            mon_cfg = self.config.get("monitoring", {})
            mon_config = MonitoringConfig(
                health_check_interval=mon_cfg.get("health_check_interval", 5.0),
                resource_check_interval=mon_cfg.get("resource_check_interval", 10.0),
                performance_report_interval=mon_cfg.get("performance_report_interval", 60.0),
                cpu_warning_percent=mon_cfg.get("cpu_warning_percent", 70.0),
                cpu_critical_percent=mon_cfg.get("cpu_critical_percent", 90.0),
                memory_warning_percent=mon_cfg.get("memory_warning_percent", 70.0),
                memory_critical_percent=mon_cfg.get("memory_critical_percent", 85.0),
            )

            # Create and start monitoring system
            self.monitoring = DIMCMonitoringSystem(config=mon_config, logger=self.logger)
            self.monitoring.on_alert = self._on_monitoring_alert
            self.monitoring.on_status_change = self._on_monitoring_status_change
            self.monitoring.start()

            self.logger.info("Monitoring System started")

        except Exception as e:
            self.logger.error(f"Failed to start Monitoring System: {e}")
            self.monitoring = None

    def _on_monitoring_alert(self, alert):
        """Handle alerts from monitoring system."""
        # Forward to heartbeat if available
        if self.heartbeat and alert.severity.value in ("error", "critical"):
            from .dimc_heartbeat import ComponentHealth

            self.heartbeat.update_health(
                (
                    ComponentHealth.DEGRADED
                    if alert.severity.value == "error"
                    else ComponentHealth.UNHEALTHY
                ),
                alert.message,
            )

    def _on_monitoring_status_change(self, old_status, new_status):
        """Handle monitoring status changes."""
        self.logger.info(f"Monitoring status changed: {old_status.value} -> {new_status.value}")

    def _start_heartbeat(self):
        """Initialize and start Heartbeat agent."""
        try:
            from .dimc_heartbeat import (
                ComponentHealth,
                DIMCHeartbeat,
                DIMCHeartbeatMonitor,
                HeartbeatConfig,
            )

            # Configure heartbeat
            hb_config = HeartbeatConfig(
                ipc_base_path=self.config.get("heartbeat", {}).get("ipc_path", "/mnt/d/ROA/.ipc"),
                heartbeat_interval=self.config.get("heartbeat", {}).get("interval", 5.0),
                component_name="DIMC",
                component_version="2.0",
            )

            # Create and start heartbeat agent
            self.heartbeat = DIMCHeartbeat(config=hb_config, logger=self.logger)
            self.heartbeat.on_health_changed = self._on_heartbeat_health_changed
            self.heartbeat.start()

            # Create heartbeat monitor for tracking other components
            self.heartbeat_monitor = DIMCHeartbeatMonitor(config=hb_config, logger=self.logger)
            self.heartbeat_monitor.on_client_dead = self._on_component_dead
            self.heartbeat_monitor.start()

            self.logger.info("Heartbeat agent started")

        except Exception as e:
            self.logger.error(f"Failed to start Heartbeat agent: {e}")
            self.heartbeat = None
            self.heartbeat_monitor = None

    def _start_bridge(self):
        """Initialize and start UE5 Bridge agent."""
        try:
            from .UE5Bridge import (
                ConnectionConfig,
                ConnectionMonitor,
                DIMCUe5Connector,
                MonitorConfig,
            )

            # Configure bridge
            bridge_cfg = self.config.get("bridge", {})
            conn_config = ConnectionConfig(
                host=bridge_cfg.get("host", "127.0.0.1"),
                request_port=bridge_cfg.get("request_port", 9876),
                response_port=bridge_cfg.get("response_port", 9877),
                heartbeat_interval=bridge_cfg.get("heartbeat_interval", 2.0),
                reconnect_enabled=bridge_cfg.get("reconnect_enabled", True),
            )

            # Create connector
            self.ue5_connector = DIMCUe5Connector(config=conn_config, logger=self.logger)

            # Set up callbacks for LIDAR and obstacle data
            self.ue5_connector.on_lidar_scan = self._on_lidar_scan_received
            self.ue5_connector.on_obstacle_detected = self._on_obstacle_received
            self.ue5_connector.on_connection_state_changed = self._on_bridge_connection_changed

            # Create connection monitor
            monitor_config = MonitorConfig(
                health_check_interval=bridge_cfg.get("health_check_interval", 5.0),
                latency_check_interval=bridge_cfg.get("latency_check_interval", 10.0),
            )
            self.connection_monitor = ConnectionMonitor(
                connector=self.ue5_connector, config=monitor_config, logger=self.logger
            )

            # Connect to UE5 (non-blocking, will reconnect if failed)
            if bridge_cfg.get("auto_connect", True):
                if self.ue5_connector.connect():
                    self.logger.info("UE5 Bridge connected")
                    self.connection_monitor.start()
                else:
                    self.logger.warning("UE5 Bridge connection failed, will retry")
            else:
                self.logger.info("UE5 Bridge initialized (manual connect mode)")

        except Exception as e:
            self.logger.error(f"Failed to start Bridge agent: {e}")
            self.ue5_connector = None
            self.connection_monitor = None

    def _on_heartbeat_health_changed(self, old_health, new_health):
        """Handle heartbeat health status change."""
        self.logger.info(f"DIMC health changed: {old_health.name} -> {new_health.name}")

        # Update observability if available
        if self._obs_enabled and self._observability:
            if new_health.name == "HEALTHY":
                self._observability.health.set_healthy()
            elif new_health.name == "DEGRADED":
                self._observability.health.set_degraded("Component health degraded")
            else:
                self._observability.health.set_unhealthy("Component unhealthy")

    def _on_component_dead(self, client_info):
        """Handle another component becoming unresponsive."""
        self.logger.warning(f"Component dead: {client_info.component} ({client_info.client_id})")

    def _on_bridge_connection_changed(self, state):
        """
        Handle bridge connection state change with graceful degradation.

        Args:
            state: ConnectionState enum value
        """
        self.logger.info(f"UE5 Bridge connection state: {state.name}")

        # Update degradation state
        if state.name in ("DISCONNECTED", "ERROR"):
            self._degraded = True
            self._degradation_reason = f"UE5 Bridge {state.name.lower()}"
            self.logger.warning(f"DIMC entering degraded mode: {self._degradation_reason}")

            # In degraded mode, DIMC can still:
            # - Serve cached position data (from last update)
            # - Provide distance calculations between robots
            # - Export historical data
            # BUT sensor data (LIDAR, obstacles) will be stale

        elif state.name == "CONNECTED":
            if self._degraded:
                self.logger.info("DIMC recovering from degraded mode")
            self._degraded = False
            self._degradation_reason = None

        elif state.name == "RECONNECTING":
            self._degraded = True
            self._degradation_reason = "UE5 Bridge reconnecting"

        # Update heartbeat health based on bridge state
        if self.heartbeat:
            from .dimc_heartbeat import ComponentHealth

            if state.name == "CONNECTED":
                self.heartbeat.update_health(ComponentHealth.HEALTHY, "Bridge connected")
            elif state.name == "RECONNECTING":
                self.heartbeat.update_health(ComponentHealth.DEGRADED, "Bridge reconnecting")
            elif state.name in ("DISCONNECTED", "ERROR"):
                self.heartbeat.update_health(
                    ComponentHealth.DEGRADED,
                    f"Bridge {state.name.lower()} - degraded mode",
                )

        # Update monitoring system if available
        if self.monitoring:
            from .dimc_monitoring import AlertCategory, AlertSeverity, SubsystemStatus

            if state.name == "CONNECTED":
                self.monitoring.update_subsystem_status("bridge", SubsystemStatus.HEALTHY)
            elif state.name == "RECONNECTING":
                self.monitoring.update_subsystem_status("bridge", SubsystemStatus.DEGRADED)
            elif state.name in ("DISCONNECTED", "ERROR"):
                self.monitoring.update_subsystem_status("bridge", SubsystemStatus.UNHEALTHY)
                self.monitoring.add_alert(
                    category=AlertCategory.CONNECTIVITY,
                    severity=AlertSeverity.WARNING,
                    message=f"UE5 Bridge {state.name.lower()} - sensor data unavailable",
                    source="bridge",
                )

    def _on_lidar_scan_received(self, scan_data):
        """Handle LIDAR scan data received from UE5 Bridge."""
        # Forward to sensor receiver for processing
        if self.sensor_receiver:
            self.sensor_receiver.receive_lidar_scan(
                {
                    "timestamp": scan_data.timestamp,
                    "scan_id": scan_data.scan_id,
                    "robot_id": scan_data.robot_id,
                    "hit_points": scan_data.hit_points,
                    "num_rays": scan_data.num_rays,
                    "max_range": scan_data.max_range,
                    "field_of_view": scan_data.field_of_view,
                    "origin": scan_data.origin,
                    "rotation": scan_data.rotation,
                }
            )

        # Update metrics
        if self._obs_enabled and hasattr(self, "_sensor_readings"):
            self._sensor_readings.inc(labels={"sensor_type": "lidar"})

    def _on_obstacle_received(self, obstacle_data):
        """Handle obstacle detection from UE5 Bridge."""
        # Forward to obstacle detection for processing
        if self.obstacle_detection:
            self.obstacle_detection.process_obstacle(
                {
                    "obstacle_id": obstacle_data.obstacle_id,
                    "position": obstacle_data.position,
                    "dimensions": obstacle_data.dimensions,
                    "velocity": obstacle_data.velocity,
                    "angular_velocity": obstacle_data.angular_velocity,
                    "classification": obstacle_data.classification,
                    "confidence": obstacle_data.confidence,
                    "distance": obstacle_data.distance,
                }
            )

        # Update metrics
        if self._obs_enabled and hasattr(self, "_obstacles_detected"):
            severity = (
                "critical"
                if obstacle_data.distance < 0.5
                else "warning" if obstacle_data.distance < 1.0 else "info"
            )
            self._obstacles_detected.inc(labels={"severity": severity})

    def stop(self):
        """Stop DIMC and all subsystem agents"""
        self.logger.info("Stopping DIMC...")

        # Stop Monitoring System
        if self.monitoring:
            self.monitoring.stop()
            self.monitoring = None
            self.logger.info("Monitoring System stopped")

        # Stop Bridge agent
        if self.connection_monitor:
            self.connection_monitor.stop()
            self.connection_monitor = None

        if self.ue5_connector:
            self.ue5_connector.disconnect()
            self.ue5_connector = None
            self.logger.info("UE5 Bridge stopped")

        # Stop Heartbeat agent
        if self.heartbeat_monitor:
            self.heartbeat_monitor.stop()
            self.heartbeat_monitor = None

        if self.heartbeat:
            self.heartbeat.stop()
            self.heartbeat = None
            self.logger.info("Heartbeat agent stopped")

        # Stop Observability
        if self._obs_enabled and self._observability:
            self._observability.logger.info(
                "DIMC stopping", extra={"component": "dimc", "action": "stop"}
            )
            self._observability.health.set_shutting_down()
            self._observability.stop()

        self.logger.info("DIMC stopped")

    def initialize(self) -> bool:
        """
        Initialize DIMC and all subsystems

        This includes:
        - Sensor simulation layer
        - Obstacle detection (Evade subsystem)
        - Environment scanning service
        - ROS2 publisher

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            self.logger.info("Initializing DIMC subsystems...")

            # Initialize sensor simulation layer
            if self.config.get("sensor_simulation", True):
                self.logger.info("Initializing sensor simulation layer...")
                # Sensor simulation is already initialized in __init__
                self.logger.info("Sensor simulation layer ready")

            # Initialize obstacle detection for Evade subsystem
            if self.config.get("obstacle_detection", True):
                self.logger.info("Initializing obstacle detection (Evade subsystem)...")
                # Obstacle detection is already initialized in __init__
                self.logger.info("Obstacle detection ready for Evade subsystem")

            # Initialize ROS2 publisher if available
            try:
                self.ros2_publisher = DIMCPublisher(self.config)
                self.logger.info("ROS2 publisher initialized")
            except Exception as e:
                self.logger.warning(f"ROS2 publisher not available: {e}")
                self.ros2_publisher = None

            self.initialized = True
            self.logger.info("DIMC initialization complete")
            return True

        except Exception as e:
            self.logger.error(f"DIMC initialization failed: {e}")
            return False

    def register_robot(self, robot_id: str, actor_data: Dict) -> bool:
        """
        Register a robot for tracking (thread-safe).

        Called when FTI imports a robot. Receives FTI-extracted data.

        Args:
            robot_id: Unique robot identifier
            actor_data: Data from FTI/C++ including:
                - position: (x, y, z) in meters
                - orientation: (x, y, z, w) quaternion
                - robot_type: ERobotType value
                - dimensions: FRobotDimensions data
                - sensors: List of FSensorDefinition data
                - safety_zones: List of FSafetyZoneConfig data
                - data_flags: FDIMCDataFlags indicating what came from URDF

        Returns:
            True if registration successful
        """
        # Validate robot_id
        if not robot_id or not isinstance(robot_id, str):
            self.logger.error("Invalid robot_id provided")
            return False

        # Check max robots limit
        max_robots = self.config.get("max_robots", 10)
        with self._robots_lock:
            if len(self.robots) >= max_robots and robot_id not in self.robots:
                self.logger.error(f"Cannot register robot: max limit ({max_robots}) reached")
                return False

        try:
            self.logger.info(f"Registering robot: {robot_id}")

            # Parse robot type
            robot_type_str = actor_data.get("robot_type", "Generic")
            try:
                robot_type = RobotType(robot_type_str)
            except ValueError:
                robot_type = RobotType.GENERIC

            # Parse dimensions (convert cm to m if needed)
            dims_data = actor_data.get("dimensions", {})
            scale = 0.01 if actor_data.get("units", "cm") == "cm" else 1.0
            dimensions = RobotDimensions(
                width=dims_data.get("width", 0) * scale,
                height=dims_data.get("height", 0) * scale,
                length=dims_data.get("length", 0) * scale,
                radius=dims_data.get("radius", 0) * scale,
                volume=dims_data.get("volume", 0) * (scale**3),
                mass=dims_data.get("mass", 0),  # kg, no scaling
                reach=dims_data.get("reach", 0) * scale,
            )

            # Parse data flags
            data_flags = actor_data.get("data_flags", {})

            # Validate and get initial position/orientation
            initial_position = self._validate_position(actor_data.get("position"))
            if initial_position is None:
                initial_position = (0.0, 0.0, 0.0)

            initial_orientation = self._validate_orientation(actor_data.get("orientation"))
            if initial_orientation is None:
                initial_orientation = (0.0, 0.0, 0.0, 1.0)

            # Thread-safe robot registry update
            with self._robots_lock:
                self.robots[robot_id] = {
                    "robot_type": robot_type,
                    "actor_data": actor_data,
                    "dimensions": dimensions,
                    "registered_at": datetime.now().isoformat(),
                    "last_update": 0.0,
                    "data_flags": data_flags,
                    "current_state": {
                        "position": initial_position,
                        "orientation": initial_orientation,
                        "velocity": (0.0, 0.0, 0.0),
                        "angular_velocity": (0.0, 0.0, 0.0),
                    },
                    # ROC/COMC integration fields
                    "roc_status": "UNKNOWN",
                    "control_mode": "UNKNOWN",
                    "estopped": False,
                    "comc_priority": 5,
                    "fleet_id": None,
                    "in_coordinated_fleet": False,
                    "joint_states": {},
                    "joint_states_timestamp": 0.0,
                }

            # Initialize tracking for this robot
            self.position_tracker.add_robot(robot_id, initial_position)
            self.orientation_tracker.add_robot(robot_id, initial_orientation)
            self.delta_calculator.add_robot(robot_id)

            # Calculate bounds and safety zones
            mesh_data = actor_data.get("mesh_data", {})
            bounds = self.bounds_calculator.calculate(mesh_data)

            # Use URDF safety zones or calculate from dimensions
            if data_flags.get("has_safety_zones", False):
                safety_zones = actor_data.get("safety_zones", [])
            else:
                safety_zone = self.safety_zone_calculator.calculate(bounds)
                safety_zones = [safety_zone]

            with self._robots_lock:
                self.robots[robot_id]["bounds"] = bounds
                self.robots[robot_id]["safety_zones"] = safety_zones

            # Register for obstacle detection (for Evade subsystem)
            self.obstacle_detection.register_robot(robot_id, safety_zones)
            self.obstacle_detection.update_robot_position(robot_id, initial_position)
            self.logger.debug(f"Registered {robot_id} for obstacle detection")

            # Publish registration event to ROS2
            if self.ros2_publisher:
                self.ros2_publisher.publish_robot_registration(
                    robot_id,
                    {
                        "width": dimensions.width,
                        "height": dimensions.height,
                        "length": dimensions.length,
                        "radius": dimensions.radius,
                        "robot_type": robot_type.value,
                    },
                )

            # Update observability metrics
            if self._obs_enabled and hasattr(self, "_active_robots"):
                with self._robots_lock:
                    self._active_robots.set(len(self.robots))

            self.logger.info(f"Robot {robot_id} registered successfully (type: {robot_type.value})")
            return True

        except Exception as e:
            self.logger.error(f"Failed to register robot {robot_id}: {e}")
            self._stats["errors_total"] += 1
            return False

    def unregister_robot(self, robot_id: str) -> bool:
        """
        Unregister a robot from tracking (thread-safe).

        Performs complete cleanup of all subsystems.

        Args:
            robot_id: Robot identifier to unregister

        Returns:
            True if unregistration successful
        """
        with self._robots_lock:
            if robot_id not in self.robots:
                self.logger.warning(f"Robot {robot_id} not registered, cannot unregister")
                return False

            self.logger.info(f"Unregistering robot: {robot_id}")
            del self.robots[robot_id]

        # Cleanup all subsystems (outside lock to prevent deadlock)
        try:
            # Tracking cleanup
            self.position_tracker.remove_robot(robot_id)
            self.orientation_tracker.remove_robot(robot_id)
            self.delta_calculator.remove_robot(robot_id)

            # Distance calculator cleanup
            if hasattr(self.distance_calculator, "remove_robot"):
                self.distance_calculator.remove_robot(robot_id)

            # Obstacle detection cleanup
            self.obstacle_detection.unregister_robot(robot_id)

            # Sensor receiver cleanup
            if hasattr(self.sensor_receiver, "unregister_robot"):
                self.sensor_receiver.unregister_robot(robot_id)

            # ROS2 publisher cleanup
            if self.ros2_publisher and hasattr(self.ros2_publisher, "unregister_robot"):
                self.ros2_publisher.unregister_robot(robot_id)

            # Update observability metrics
            if self._obs_enabled and hasattr(self, "_active_robots"):
                with self._robots_lock:
                    self._active_robots.set(len(self.robots))

            self.logger.info(f"Robot {robot_id} unregistered successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error during unregister cleanup for {robot_id}: {e}")
            self._stats["errors_total"] += 1
            return True  # Robot was removed from registry

    def update(self, current_time: float, robot_data: Dict[str, Dict]) -> None:
        """
        Main update loop - receives data from C++ plugin (thread-safe).

        Args:
            current_time: Current timestamp in seconds
            robot_data: Dictionary of robot_id -> current state data from C++
                Each entry contains:
                - position: (x, y, z) in meters
                - orientation: (x, y, z, w) quaternion
                - velocity: (vx, vy, vz) in m/s
                - angular_velocity: (wx, wy, wz) in rad/s (COMC requirement)
                - lidar_scan: Optional LIDAR scan data from C++
                - obstacles: Optional obstacle data from C++
        """
        if not self.initialized:
            return

        # Validate input
        if not isinstance(robot_data, dict):
            self.logger.error("Invalid robot_data: expected dictionary")
            self._stats["validation_failures"] += 1
            return

        self._stats["messages_received"] += 1
        self.last_update_time = current_time

        # Get snapshot of registered robots (thread-safe)
        with self._robots_lock:
            registered_robots = set(self.robots.keys())

        # Update tracking for each robot
        for robot_id, state in robot_data.items():
            if robot_id not in registered_robots:
                continue

            # Validate incoming state data
            validated_state = self._validate_robot_data(robot_id, state)
            if validated_state is None:
                self.logger.debug(f"Skipping invalid data for {robot_id}")
                continue

            position = validated_state["position"]
            orientation = validated_state["orientation"]
            velocity = validated_state["velocity"]
            angular_velocity = validated_state["angular_velocity"]

            try:
                # Update position and orientation
                self.position_tracker.update(robot_id, position, current_time)
                self.orientation_tracker.update(robot_id, orientation, current_time)

                # Calculate velocity/delta if not provided
                if velocity == (0.0, 0.0, 0.0) and "velocity" not in state:
                    velocity = self.delta_calculator.calculate(robot_id, position, current_time)

                # Process LIDAR scan data from C++
                if "lidar_scan" in validated_state:
                    self.sensor_receiver.receive_lidar_scan(
                        robot_id,
                        validated_state.get("sensor_name", "DefaultLidar"),
                        validated_state["lidar_scan"],
                    )

                    # Update observability metrics
                    if self._obs_enabled and hasattr(self, "_sensor_readings"):
                        self._sensor_readings.inc({"sensor_type": "lidar"})

                # Process obstacle data from C++
                if "obstacles" in validated_state:
                    obstacles = self.obstacle_detection.receive_obstacle_data(
                        robot_id, validated_state["obstacles"]
                    )
                    with self._robots_lock:
                        if robot_id in self.robots:
                            self.robots[robot_id]["obstacles"] = obstacles

                    # Update observability metrics
                    if self._obs_enabled and hasattr(self, "_obstacles_detected"):
                        collision_cfg = self.config.get("collision", {})
                        high_threshold = collision_cfg.get("high_threshold", 0.7)
                        for obs in obstacles:
                            severity = "high" if obs.collision_risk >= high_threshold else "low"
                            self._obstacles_detected.inc({"severity": severity})
                            if hasattr(self, "_obstacle_distance"):
                                self._obstacle_distance.observe(obs.distance)

                # Update obstacle detection with current position
                self.obstacle_detection.update_robot_position(robot_id, position)

                # Store latest state (thread-safe)
                with self._robots_lock:
                    if robot_id in self.robots:
                        self.robots[robot_id]["last_update"] = current_time
                        self.robots[robot_id]["current_state"] = {
                            "position": position,
                            "orientation": orientation,
                            "velocity": velocity,
                            "angular_velocity": angular_velocity,
                        }

                # Update observability metrics
                if self._obs_enabled and hasattr(self, "_position_updates"):
                    self._position_updates.inc({"robot_id": robot_id})

                # Publish to ROS2 (per-robot topics)
                if self.ros2_publisher:
                    self.ros2_publisher.publish_pose(robot_id, position, orientation, current_time)
                    self.ros2_publisher.publish_velocity(
                        robot_id, velocity, current_time, angular_velocity
                    )

                    # Publish LIDAR scan if available
                    lidar_scan = self.sensor_receiver.get_latest_lidar_scan(robot_id)
                    if lidar_scan:
                        self.ros2_publisher.publish_lidar_scan(robot_id, lidar_scan)

                self._stats["messages_processed"] += 1

            except Exception as e:
                self.logger.error(f"Error updating robot {robot_id}: {e}")
                self._stats["errors_total"] += 1

        self._stats["updates_total"] += 1

        # ===== COMC Fleet-wide Publishing (Section 2.5) =====

        # Thread-safe access for fleet-wide operations
        with self._robots_lock:
            robot_count = len(self.robots)
            robots_snapshot = {
                rid: dict(self.robots[rid])
                for rid in self.robots
                if "current_state" in self.robots[rid]
            }

        # Publish fleet positions @ 10 Hz
        if self.ros2_publisher and robots_snapshot:
            self.ros2_publisher.publish_fleet_positions(robots_snapshot, current_time)

        # Update inter-robot distances and publish @ 5 Hz
        if robot_count > 1:
            distances = self.distance_calculator.calculate_all_distances(
                {rid: data["current_state"]["position"] for rid, data in robots_snapshot.items()}
            )

            if self.ros2_publisher:
                self.ros2_publisher.publish_distances(distances, current_time)

        # Publish obstacles @ 10 Hz
        if self.ros2_publisher:
            all_obstacles = []
            for robot_id in robots_snapshot:
                obstacles = self.sensor_receiver.get_latest_obstacles(robot_id)
                for obs in obstacles:
                    all_obstacles.append(
                        {
                            "obstacle_id": obs.obstacle_id,
                            "type": obs.obstacle_type.value,
                            "position": obs.position,
                            "dimensions": {
                                "width": obs.dimensions.width,
                                "height": obs.dimensions.height,
                                "depth": obs.dimensions.depth,
                            },
                            "velocity": obs.relative_velocity,
                            "collision_risk": obs.collision_risk,
                        }
                    )

            if all_obstacles:
                self.ros2_publisher.publish_obstacles(all_obstacles, current_time)

    def get_position(self, robot_id: str) -> Optional[Tuple[float, float, float]]:
        """
        Get current position of a robot (thread-safe).

        Args:
            robot_id: Robot identifier

        Returns:
            (x, y, z) position tuple or None if not found
        """
        with self._robots_lock:
            if robot_id in self.robots and "current_state" in self.robots[robot_id]:
                return self.robots[robot_id]["current_state"]["position"]
        return None

    def get_orientation(self, robot_id: str) -> Optional[Tuple[float, float, float, float]]:
        """
        Get current orientation of a robot (thread-safe).

        Args:
            robot_id: Robot identifier

        Returns:
            (x, y, z, w) quaternion or None if not found
        """
        with self._robots_lock:
            if robot_id in self.robots and "current_state" in self.robots[robot_id]:
                return self.robots[robot_id]["current_state"]["orientation"]
        return None

    def get_velocity(self, robot_id: str) -> Optional[Tuple[float, float, float]]:
        """
        Get current velocity of a robot (thread-safe).

        Args:
            robot_id: Robot identifier

        Returns:
            (vx, vy, vz) velocity tuple or None if not found
        """
        with self._robots_lock:
            if robot_id in self.robots and "current_state" in self.robots[robot_id]:
                return self.robots[robot_id]["current_state"]["velocity"]
        return None

    def get_dimensions(self, robot_id: str) -> Optional[RobotDimensions]:
        """
        Get dimensions of a robot (thread-safe).

        Args:
            robot_id: Robot identifier

        Returns:
            RobotDimensions object or None
        """
        with self._robots_lock:
            if robot_id in self.robots:
                return self.robots[robot_id].get("dimensions")
        return None

    def get_distance(self, robot_id_1: str, robot_id_2: str) -> Optional[float]:
        """
        Get distance between two robots (thread-safe).

        Args:
            robot_id_1: First robot identifier
            robot_id_2: Second robot identifier

        Returns:
            Distance in meters or None if robots not found
        """
        pos1 = self.get_position(robot_id_1)
        pos2 = self.get_position(robot_id_2)

        if pos1 and pos2:
            return self.distance_calculator.calculate_distance(pos1, pos2)
        return None

    def get_robot_info(self, robot_id: str) -> Optional[RobotInfo]:
        """
        Get complete information about a robot (thread-safe).

        Args:
            robot_id: Robot identifier

        Returns:
            RobotInfo object or None if not found
        """
        with self._robots_lock:
            if robot_id not in self.robots:
                return None

            robot = self.robots[robot_id]
            if "current_state" not in robot:
                return None

            state = robot["current_state"]
            data_flags = robot.get("data_flags", {})

            return RobotInfo(
                robot_id=robot_id,
                robot_type=robot.get("robot_type", RobotType.GENERIC),
                position=state["position"],
                orientation=state["orientation"],
                velocity=state["velocity"],
                dimensions=robot.get("dimensions", RobotDimensions()),
                timestamp=robot["last_update"],
                has_urdf_dimensions=data_flags.get("has_dimensions", False),
                has_urdf_sensors=data_flags.get("has_sensors", False),
                has_urdf_safety_zones=data_flags.get("has_safety_zones", False),
            )

    def get_all_robots(self) -> List[str]:
        """Get list of all registered robot IDs (thread-safe)."""
        with self._robots_lock:
            return list(self.robots.keys())

    def export_to_rosbag(self, filename: str) -> bool:
        """
        Export data to ROS bag file.

        Args:
            filename: Output filename

        Returns:
            True if export successful
        """
        try:
            self.logger.info(f"Exporting to ROS bag: {filename}")
            with self._robots_lock:
                robots_copy = {rid: dict(data) for rid, data in self.robots.items()}
            result = self.rosbag_exporter.export(robots_copy, filename)

            # Update metrics
            if self._obs_enabled and hasattr(self, "_exports_total"):
                status = "success" if result else "failed"
                self._exports_total.inc({"format": "rosbag", "status": status})

            return result
        except Exception as e:
            self.logger.error(f"ROS bag export failed: {e}")
            if self._obs_enabled and hasattr(self, "_exports_total"):
                self._exports_total.inc({"format": "rosbag", "status": "error"})
            return False

    def export_to_json(self, filename: str) -> bool:
        """
        Export data to JSON file.

        Args:
            filename: Output filename

        Returns:
            True if export successful
        """
        try:
            self.logger.info(f"Exporting to JSON: {filename}")
            with self._robots_lock:
                robots_copy = {rid: dict(data) for rid, data in self.robots.items()}
            result = self.json_exporter.export(robots_copy, filename)

            # Update metrics
            if self._obs_enabled and hasattr(self, "_exports_total"):
                status = "success" if result else "failed"
                self._exports_total.inc({"format": "json", "status": status})

            return result
        except Exception as e:
            self.logger.error(f"JSON export failed: {e}")
            if self._obs_enabled and hasattr(self, "_exports_total"):
                self._exports_total.inc({"format": "json", "status": "error"})
            return False

    def export_to_csv(self, filename: str) -> bool:
        """
        Export data to CSV file.

        Args:
            filename: Output filename

        Returns:
            True if export successful
        """
        try:
            self.logger.info(f"Exporting to CSV: {filename}")
            with self._robots_lock:
                robots_copy = {rid: dict(data) for rid, data in self.robots.items()}
            result = self.csv_exporter.export(robots_copy, filename)

            # Update metrics
            if self._obs_enabled and hasattr(self, "_exports_total"):
                status = "success" if result else "failed"
                self._exports_total.inc({"format": "csv", "status": status})

            return result
        except Exception as e:
            self.logger.error(f"CSV export failed: {e}")
            if self._obs_enabled and hasattr(self, "_exports_total"):
                self._exports_total.inc({"format": "csv", "status": "error"})
            return False

    def get_obstacles(self, robot_id: str) -> List[ObstacleData]:
        """
        Get detected obstacles for a robot (for Evade subsystem)

        Args:
            robot_id: Robot identifier

        Returns:
            List of ObstacleData objects with positions, distances, and risk levels
        """
        return self.obstacle_detection.get_current_obstacles(robot_id)

    def get_collision_risk(self, robot_id: str) -> CollisionRisk:
        """
        Get collision risk level for a robot

        Args:
            robot_id: Robot identifier

        Returns:
            CollisionRisk enum value
        """
        return self.obstacle_detection.get_collision_risk_level(robot_id)

    def get_evade_recommendation(self, robot_id: str) -> Dict:
        """
        Get Evade action recommendation based on current obstacles

        Args:
            robot_id: Robot identifier

        Returns:
            Recommendation dict with action, slowdown_factor, reason
        """
        return self.obstacle_detection.get_evade_recommendation(robot_id)

    def is_path_clear(
        self, robot_id: str, direction: Tuple[float, float, float], distance: float
    ) -> bool:
        """
        Check if path is clear for robot in given direction (for Evade subsystem)

        Args:
            robot_id: Robot identifier
            direction: Normalized direction vector
            distance: Distance to check

        Returns:
            True if path is clear (no high-risk obstacles)
        """
        return self.obstacle_detection.is_path_clear(robot_id, direction, distance)

    def calibrate_evade_subsystem(self, robot_id: str) -> Dict:
        """
        Calibrate obstacle detection for Evade subsystem

        Called during Webthread initialization (startup phase)

        Args:
            robot_id: Robot identifier

        Returns:
            Calibration results dictionary
        """
        return self.obstacle_detection.calibrate_for_evade(robot_id)

    def get_environment_scan(self, robot_id: str) -> Dict:
        """
        Get comprehensive environment scan for robot (for ADM mode navigation).

        Thread-safe.

        Args:
            robot_id: Robot identifier

        Returns:
            Environment scan data including LIDAR, obstacles and safe zones
        """
        with self._robots_lock:
            if robot_id not in self.robots or "current_state" not in self.robots[robot_id]:
                return {}
            state = dict(self.robots[robot_id]["current_state"])

        obstacles = self.obstacle_detection.get_current_obstacles(robot_id)
        lidar_scan = self.sensor_receiver.get_latest_lidar_scan(robot_id)

        return {
            "robot_id": robot_id,
            "timestamp": self.last_update_time,
            "position": state["position"],
            "orientation": state["orientation"],
            "velocity": state["velocity"],
            "obstacles": [
                {
                    "id": o.obstacle_id,
                    "type": o.obstacle_type.value,
                    "position": o.position,
                    "distance": o.distance,
                    "collision_risk": o.collision_risk,
                }
                for o in obstacles
            ],
            "lidar_available": lidar_scan is not None,
            "lidar_ray_count": len(lidar_scan.ranges) if lidar_scan else 0,
            "collision_risk_level": self.obstacle_detection.get_collision_risk_level(
                robot_id
            ).value,
            "safe_to_move": self.obstacle_detection.get_collision_risk_level(robot_id)
            in [CollisionRisk.LOW, CollisionRisk.NONE],
        }

    def get_lidar_scan(
        self, robot_id: str, sensor_name: str = "DefaultLidar"
    ) -> Optional[LidarScanData]:
        """
        Get latest LIDAR scan for a robot.

        Args:
            robot_id: Robot identifier
            sensor_name: Sensor name

        Returns:
            LidarScanData or None
        """
        return self.sensor_receiver.get_latest_lidar_scan(robot_id, sensor_name)

    def shutdown(self) -> None:
        """Shutdown DIMC and cleanup all resources (thread-safe)."""
        self.logger.info("Shutting down DIMC v2.0...")

        # Stop background agents first
        self.stop()

        # Stop ROS2 publisher
        if self.ros2_publisher:
            try:
                self.ros2_publisher.shutdown()
            except Exception as e:
                self.logger.error(f"Error shutting down ROS2 publisher: {e}")
            self.ros2_publisher = None

        # Shutdown obstacle detection
        if self.obstacle_detection:
            try:
                self.obstacle_detection.shutdown()
            except Exception as e:
                self.logger.error(f"Error shutting down obstacle detection: {e}")

        # Cleanup sensor receiver
        if hasattr(self.sensor_receiver, "shutdown"):
            try:
                self.sensor_receiver.shutdown()
            except Exception as e:
                self.logger.error(f"Error shutting down sensor receiver: {e}")

        # Cleanup tracking subsystems
        if hasattr(self.position_tracker, "shutdown"):
            self.position_tracker.shutdown()
        if hasattr(self.orientation_tracker, "shutdown"):
            self.orientation_tracker.shutdown()
        if hasattr(self.delta_calculator, "shutdown"):
            self.delta_calculator.shutdown()
        if hasattr(self.distance_calculator, "shutdown"):
            self.distance_calculator.shutdown()

        # Cleanup exporters
        if hasattr(self.rosbag_exporter, "shutdown"):
            self.rosbag_exporter.shutdown()
        if hasattr(self.json_exporter, "shutdown"):
            self.json_exporter.shutdown()
        if hasattr(self.csv_exporter, "shutdown"):
            self.csv_exporter.shutdown()

        # Clear robot registry (thread-safe)
        with self._robots_lock:
            self.robots.clear()

        # Stop observability
        if self._obs_enabled and self._observability:
            try:
                self._observability.stop()
            except Exception as e:
                self.logger.error(f"Error stopping observability: {e}")

        self.initialized = False
        self.logger.info("DIMC shutdown complete")

    # =========================================================================
    # STATUS & DIAGNOSTICS METHODS
    # =========================================================================

    def is_degraded(self) -> bool:
        """
        Check if DIMC is in degraded mode.

        Returns:
            True if degraded (Bridge disconnected, sensors unavailable)
        """
        return self._degraded

    def get_degradation_reason(self) -> Optional[str]:
        """
        Get reason for degradation if applicable.

        Returns:
            Degradation reason or None if healthy
        """
        return self._degradation_reason

    def get_status(self) -> Dict[str, Any]:
        """
        Get overall DIMC status for health monitoring.

        Returns:
            Status dictionary with health, subsystems, statistics
        """
        import time

        # Determine overall health (consider degradation)
        if self._degraded:
            overall_health = "degraded"
        elif self.monitoring:
            status = self.monitoring.get_status()
            overall_health = status.get("overall_status", "unknown")
        elif self.heartbeat:
            overall_health = (
                self.heartbeat.health.name.lower()
                if hasattr(self.heartbeat.health, "name")
                else "unknown"
            )
        else:
            overall_health = "healthy" if self.initialized else "unknown"

        # Get subsystem statuses
        subsystems = {}

        # Bridge status
        if self.ue5_connector:
            subsystems["bridge"] = {
                "status": "healthy" if self.ue5_connector.is_connected() else "offline",
                "connected": self.ue5_connector.is_connected(),
                "state": (
                    self.ue5_connector.get_state().name
                    if hasattr(self.ue5_connector.get_state(), "name")
                    else "unknown"
                ),
                "messages_sent": self.ue5_connector.messages_sent,
                "messages_received": self.ue5_connector.messages_received,
                "reconnect_count": self.ue5_connector.reconnect_count,
            }
        else:
            subsystems["bridge"] = {
                "status": "disabled" if not self._bridge_enabled else "unavailable"
            }

        # Heartbeat status
        if self.heartbeat:
            subsystems["heartbeat"] = self.heartbeat.get_status()
        else:
            subsystems["heartbeat"] = {
                "status": "disabled" if not self._heartbeat_enabled else "unavailable"
            }

        # Monitoring status
        if self.monitoring:
            subsystems["monitoring"] = self.monitoring.get_status()
        else:
            subsystems["monitoring"] = {
                "status": "disabled" if not self._monitoring_enabled else "unavailable"
            }

        # Observability status
        subsystems["observability"] = {
            "enabled": self._obs_enabled,
            "available": OBSERVABILITY_AVAILABLE,
        }

        # Core subsystems
        subsystems["sensor_receiver"] = {
            "status": "healthy",
            "active_sensors": len(getattr(self.sensor_receiver, "active_sensors", [])),
        }
        subsystems["obstacle_detection"] = {
            "status": "healthy" if self.obstacle_detection.enabled else "disabled",
            "tracked_robots": len(self.obstacle_detection.known_robots),
        }
        subsystems["ros2_publisher"] = {
            "status": "healthy" if self.ros2_publisher else "unavailable"
        }

        # Statistics
        uptime = time.time() - self._stats["start_time"] if self._stats["start_time"] else 0

        with self._robots_lock:
            robot_count = len(self.robots)

        return {
            "overall_health": overall_health,
            "degraded": self._degraded,
            "degradation_reason": self._degradation_reason,
            "initialized": self.initialized,
            "uptime_seconds": uptime,
            "robot_count": robot_count,
            "update_rate_hz": self.update_rate,
            "last_update_time": self.last_update_time,
            "subsystems": subsystems,
            "statistics": {
                "messages_received": self._stats["messages_received"],
                "messages_processed": self._stats["messages_processed"],
                "updates_total": self._stats["updates_total"],
                "errors_total": self._stats["errors_total"],
                "validation_failures": self._stats["validation_failures"],
            },
        }

    def get_diagnostics(self) -> Dict[str, Any]:
        """
        Get comprehensive diagnostic data for debugging.

        Returns:
            Diagnostics dictionary with all subsystem details
        """
        diagnostics = {
            "status": self.get_status(),
            "config": {
                "config_path": str(self.config_path),
                "bridge_enabled": self._bridge_enabled,
                "heartbeat_enabled": self._heartbeat_enabled,
                "monitoring_enabled": self._monitoring_enabled,
                "observability_enabled": self._obs_enabled,
            },
            "robots": {
                robot_id: {
                    "type": (
                        self.robots[robot_id].get("robot_type", "unknown").value
                        if hasattr(self.robots[robot_id].get("robot_type"), "value")
                        else str(self.robots[robot_id].get("robot_type", "unknown"))
                    ),
                    "registered_at": self.robots[robot_id].get("registered_at"),
                    "last_update": self.robots[robot_id].get("last_update"),
                    "roc_status": self.robots[robot_id].get("roc_status", "unknown"),
                    "control_mode": self.robots[robot_id].get("control_mode", "unknown"),
                    "in_fleet": self.robots[robot_id].get("in_coordinated_fleet", False),
                }
                for robot_id in self.robots
            },
        }

        # Add monitoring diagnostics
        if self.monitoring:
            diagnostics["monitoring"] = self.monitoring.get_diagnostics()

        # Add bridge diagnostics
        if self.ue5_connector:
            diagnostics["bridge"] = self.ue5_connector.get_statistics()

        # Add connection monitor diagnostics
        if self.connection_monitor:
            diagnostics["connection_monitor"] = self.connection_monitor.get_statistics()

        return diagnostics

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get performance statistics.

        Returns:
            Statistics dictionary
        """
        import time

        stats = {
            "uptime_seconds": (
                time.time() - self._stats["start_time"] if self._stats["start_time"] else 0
            ),
            "messages": {
                "received": self._stats["messages_received"],
                "processed": self._stats["messages_processed"],
                "errors": self._stats["errors_total"],
            },
            "updates": {
                "total": self._stats["updates_total"],
                "rate_hz": self.update_rate,
            },
            "robots": {
                "count": len(self.robots),
                "active": sum(1 for r in self.robots.values() if r.get("roc_status") == "ACTIVE"),
            },
        }

        # Add performance stats from monitoring
        if self.monitoring:
            perf_stats = self.monitoring.profiler.get_all_stats()
            stats["performance"] = {
                name: {
                    "call_count": s.call_count,
                    "avg_time_ms": s.avg_time_ms,
                    "max_time_ms": s.max_time_ms,
                }
                for name, s in perf_stats.items()
            }

        return stats

    def get_alerts(self, severity: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get monitoring alerts.

        Args:
            severity: Filter by severity
            limit: Maximum alerts to return

        Returns:
            List of alert dictionaries
        """
        if self.monitoring:
            from .dimc_monitoring import AlertSeverity

            sev = AlertSeverity(severity) if severity else None
            return self.monitoring.get_alerts(severity=sev, limit=limit)
        return []

    def acknowledge_alert(self, alert_id: str) -> bool:
        """
        Acknowledge an alert.

        Args:
            alert_id: Alert identifier

        Returns:
            True if acknowledged
        """
        if self.monitoring:
            return self.monitoring.acknowledge_alert(alert_id)
        return False

    def is_healthy(self) -> bool:
        """
        Quick health check.

        Returns:
            True if DIMC is healthy
        """
        if self.monitoring:
            from .dimc_monitoring import SubsystemStatus

            return self.monitoring._overall_status == SubsystemStatus.HEALTHY
        if self.heartbeat:
            from .dimc_heartbeat import ComponentHealth

            return self.heartbeat.health == ComponentHealth.HEALTHY
        return self.initialized

    def get_bridge_status(self) -> Dict[str, Any]:
        """
        Get UE5 Bridge connection status.

        Returns:
            Bridge status dictionary
        """
        if not self.ue5_connector:
            return {
                "available": False,
                "enabled": self._bridge_enabled,
                "reason": "Not initialized" if self._bridge_enabled else "Disabled",
            }

        return {
            "available": True,
            "connected": self.ue5_connector.is_connected(),
            "state": self.ue5_connector.get_state().name,
            "statistics": self.ue5_connector.get_statistics(),
            "last_heartbeat": self.ue5_connector.last_heartbeat,
            "last_error": self.ue5_connector.last_error,
        }

    def get_heartbeat_status(self) -> Dict[str, Any]:
        """
        Get Heartbeat agent status.

        Returns:
            Heartbeat status dictionary
        """
        if not self.heartbeat:
            return {
                "available": False,
                "enabled": self._heartbeat_enabled,
                "reason": "Not initialized" if self._heartbeat_enabled else "Disabled",
            }

        return self.heartbeat.get_status()
