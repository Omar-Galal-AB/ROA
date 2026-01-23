"""
DIMC - Dimensions Collector Component v2.0

Public API for ROA components to interact with DIMC.
Supports COMC requirements for multi-robot coordination.

Subsystem Agents:
- Bridge: UE5 ↔ WSL data exchange (UE5Bridge/)
- Heartbeat: Health status and lifecycle management (dimc_heartbeat.py)
- Monitoring: Comprehensive health and performance monitoring (dimc_monitoring.py)
"""

from .dimc_api import (  # Sub-APIs; Data types - Recommendations; Data types - COMC (Section 2)
    DIMC_API,
    PROXIMITY_CAUTION,
    PROXIMITY_CRITICAL,
    PROXIMITY_WARNING,
    CalibrationResult,
    CoordinationAPI,
    EnvironmentScan,
    EvadeAPI,
    EvadeRecommendation,
    FleetDistanceData,
    FleetPositionData,
    ProximityAlert,
    SensorAPI,
    TrackingAPI,
    get_dimc_instance,
    reset_dimc_instance,
)
from .dimc_core import CollisionRisk, RobotDimensions, RobotInfo, RobotType
from .sensor_simulation import (
    LidarScanData,
    ObstacleData,
    ObstacleDimensions,
    ObstacleType,
    SensorType,
)

# Bridge Subsystem (UE5 ↔ WSL data exchange)
try:
    from .UE5Bridge import (
        ConnectionConfig,
        ConnectionHealth,
        ConnectionMonitor,
        ConnectionState,
        DIMCUe5Connector,
        HealthMetrics,
        MonitorConfig,
    )

    _BRIDGE_EXPORTS = [
        "DIMCUe5Connector",
        "ConnectionState",
        "ConnectionConfig",
        "ConnectionMonitor",
        "ConnectionHealth",
        "MonitorConfig",
        "HealthMetrics",
    ]
except ImportError:
    _BRIDGE_EXPORTS = []

# Heartbeat Subsystem (Health status monitoring)
try:
    from .dimc_heartbeat import (
        ComponentHealth,
        DIMCHeartbeat,
        DIMCHeartbeatMonitor,
        HeartbeatConfig,
        HeartbeatData,
        HeartbeatState,
    )

    _HEARTBEAT_EXPORTS = [
        "DIMCHeartbeat",
        "DIMCHeartbeatMonitor",
        "HeartbeatState",
        "ComponentHealth",
        "HeartbeatConfig",
        "HeartbeatData",
    ]
except ImportError:
    _HEARTBEAT_EXPORTS = []

# Monitoring Subsystem (Comprehensive health and performance monitoring)
try:
    from .dimc_monitoring import (
        Alert,
        AlertCategory,
        AlertSeverity,
        DataQualityMonitor,
        DIMCMonitoringSystem,
        MonitoringConfig,
        PerformanceProfiler,
        RateLimiter,
        SubsystemStatus,
    )

    _MONITORING_EXPORTS = [
        "DIMCMonitoringSystem",
        "MonitoringConfig",
        "SubsystemStatus",
        "AlertSeverity",
        "AlertCategory",
        "Alert",
        "PerformanceProfiler",
        "DataQualityMonitor",
        "RateLimiter",
    ]
except ImportError:
    _MONITORING_EXPORTS = []

__version__ = "2.0.0"
__all__ = [
    # Main API
    "DIMC_API",
    "get_dimc_instance",
    "reset_dimc_instance",
    # Sub-APIs
    "EvadeAPI",
    "TrackingAPI",
    "CoordinationAPI",
    "SensorAPI",
    # Data types - Recommendations
    "EvadeRecommendation",
    "EnvironmentScan",
    "CalibrationResult",
    # Data types - Core
    "RobotType",
    "RobotDimensions",
    "RobotInfo",
    "CollisionRisk",
    # Data types - Sensors
    "LidarScanData",
    "ObstacleData",
    "ObstacleDimensions",
    "ObstacleType",
    "SensorType",
    # Data types - COMC (Section 2)
    "ProximityAlert",
    "FleetPositionData",
    "FleetDistanceData",
    "PROXIMITY_CRITICAL",
    "PROXIMITY_CAUTION",
    "PROXIMITY_WARNING",
    # Bridge Subsystem
    *_BRIDGE_EXPORTS,
    # Heartbeat Subsystem
    *_HEARTBEAT_EXPORTS,
    # Monitoring Subsystem
    *_MONITORING_EXPORTS,
]
