"""
DIMC UE5 Bridge Module

This module provides the bridge layer for communication between
the WSL Python DIMC component and the UE5 C++ ADimensionsCollector plugin.

Subsystem: Bridge
Purpose: Bidirectional data exchange between WSL and UE5

Components:
- DIMCUe5Connector: Main connector for UE5 communication
- ConnectionMonitor: Health monitoring for the bridge connection
- ConnectionConfig: Configuration for connector settings
- MonitorConfig: Configuration for connection monitoring
"""

from .connection_monitor import (
    ConnectionHealth,
    ConnectionMonitor,
    HealthMetrics,
    MonitorConfig,
)
from .dimc_ue5_connector import (
    ConnectionConfig,
    ConnectionState,
    DIMCUe5Connector,
    LidarScanData,
    ObstacleData,
)

__all__ = [
    # Connector
    "DIMCUe5Connector",
    "ConnectionState",
    "ConnectionConfig",
    # Data types
    "LidarScanData",
    "ObstacleData",
    # Monitor
    "ConnectionMonitor",
    "ConnectionHealth",
    "MonitorConfig",
    "HealthMetrics",
]
