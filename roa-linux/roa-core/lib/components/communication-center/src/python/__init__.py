"""
COMC - Communication Center Package

Multi-robot coordination and communication system for ROA.
"""

from .comc_node import COMCNode
from .work_area_manager import WorkAreaManager
from .proximity_monitor import ProximityMonitor
from .qos_profiles import SAFETY_QOS, COORDINATION_QOS, STATUS_QOS
from .task_coordinator import TaskCoordinator, TaskPriority, TaskStatus
from .evade_coordinator import EvadeCoordinator
from .integration_handlers import (
    DIMCIntegrationHandler,
    WebthreadIntegrationHandler,
    ROCIntegrationHandler,
    FTIIntegrationHandler
)
from .state_machine import COMCStateMachine, ComponentState
from .service_handlers import ServiceHandlers
from .health_monitor import HealthMonitor, HealthLevel

# HB Agent for Heartbeat Subsystem integration
try:
    from .comc_hb_agent import COMCHBAgent, COMCHBContext
    HB_AGENT_AVAILABLE = True
except ImportError:
    HB_AGENT_AVAILABLE = False

# Bridge Agent for UE5 communication
try:
    from .comc_bridge_agent import (
        COMCBridgeAgent,
        BridgeMode,
        BridgeState,
        create_comc_bridge
    )
    BRIDGE_AGENT_AVAILABLE = True
except ImportError:
    BRIDGE_AGENT_AVAILABLE = False

# DIMC Notifier for DIMC integration
try:
    from .dimc_notifier import DIMCNotifier
    DIMC_NOTIFIER_AVAILABLE = True
except ImportError:
    DIMC_NOTIFIER_AVAILABLE = False

# Advanced Monitoring System
try:
    from .comc_monitoring import (
        COMCMonitoringSystem,
        ConnectionMonitor,
        MessageFlowMonitor,
        FleetMonitor,
        AnomalyDetector,
        AlertManager,
        DiagnosticTools,
        AlertSeverity,
        ConnectionState,
        MonitoringCategory,
    )
    MONITORING_AVAILABLE = True
except ImportError:
    MONITORING_AVAILABLE = False

# Resilience Module
try:
    from .comc_resilience import (
        COMCResilienceManager,
        CircuitBreaker,
        CircuitBreakerConfig,
        CircuitBreakerOpenError,
        RateLimiter,
        RateLimitExceededError,
        RetryHandler,
        RetryConfig,
        Bulkhead,
        BulkheadFullError,
        RecoveryManager,
        RecoveryProcedure,
        with_circuit_breaker,
        with_retry,
        with_rate_limit,
    )
    RESILIENCE_AVAILABLE = True
except ImportError:
    RESILIENCE_AVAILABLE = False

__version__ = '0.2.0'  # Updated version with monitoring and resilience
__all__ = [
    'COMCNode',
    'WorkAreaManager',
    'ProximityMonitor',
    'TaskCoordinator',
    'TaskPriority',
    'TaskStatus',
    'EvadeCoordinator',
    'DIMCIntegrationHandler',
    'WebthreadIntegrationHandler',
    'ROCIntegrationHandler',
    'FTIIntegrationHandler',
    'COMCStateMachine',
    'ComponentState',
    'ServiceHandlers',
    'HealthMonitor',
    'HealthLevel',
    'SAFETY_QOS',
    'COORDINATION_QOS',
    'STATUS_QOS',
    # HB Agent (conditional)
    'COMCHBAgent',
    'COMCHBContext',
    'HB_AGENT_AVAILABLE',
    # Bridge Agent (conditional)
    'COMCBridgeAgent',
    'BridgeMode',
    'BridgeState',
    'create_comc_bridge',
    'BRIDGE_AGENT_AVAILABLE',
    # DIMC Notifier (conditional)
    'DIMCNotifier',
    'DIMC_NOTIFIER_AVAILABLE',
    # Monitoring System (conditional)
    'COMCMonitoringSystem',
    'ConnectionMonitor',
    'MessageFlowMonitor',
    'FleetMonitor',
    'AnomalyDetector',
    'AlertManager',
    'DiagnosticTools',
    'AlertSeverity',
    'ConnectionState',
    'MonitoringCategory',
    'MONITORING_AVAILABLE',
    # Resilience (conditional)
    'COMCResilienceManager',
    'CircuitBreaker',
    'CircuitBreakerConfig',
    'CircuitBreakerOpenError',
    'RateLimiter',
    'RateLimitExceededError',
    'RetryHandler',
    'RetryConfig',
    'Bulkhead',
    'BulkheadFullError',
    'RecoveryManager',
    'RecoveryProcedure',
    'with_circuit_breaker',
    'with_retry',
    'with_rate_limit',
    'RESILIENCE_AVAILABLE',
]
    'DIMC_NOTIFIER_AVAILABLE',
]
