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

from .dimc_ue5_connector import (
    DIMCUe5Connector,
    ConnectionState,
    ConnectionConfig,
    LidarScanData,
    ObstacleData,
)
from .connection_monitor import (
    ConnectionMonitor,
    ConnectionHealth,
    MonitorConfig,
    HealthMetrics,
)

__all__ = [
    # Connector
    'DIMCUe5Connector',
    'ConnectionState',
    'ConnectionConfig',
    # Data types
    'LidarScanData',
    'ObstacleData',
    # Monitor
    'ConnectionMonitor',
    'ConnectionHealth',
    'MonitorConfig',
    'HealthMetrics',
]
