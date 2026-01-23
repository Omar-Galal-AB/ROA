"""
HB Subsystem - Heartbeat Monitoring for ROA
ROA - Robot Operations & Automation

The HB (Heartbeat) Subsystem is responsible for monitoring component health
through legitimate activity-based heartbeats. It is a subsystem of the
Webthread (WT) component.

Key Features:
- Legitimate heartbeats based on actual work (proof of work)
- Multi-port architecture (6 dedicated ports for 6 components)
- Circuit breakers per component
- Overload protection (Bulkhead + Rate Limiter + Adaptive Limiter)
- Automatic recovery orchestration
- State persistence and crash recovery

Architecture:
    +------------------+
    |   WT Core        |
    |   (Webthread)    |
    +--------+---------+
             |
    +--------v---------+
    |   HB Subsystem   |
    |  +-------------+ |
    |  | HB Receiver | |  (Multi-port UDP, 9877-9882)
    |  +------+------+ |
    |         |        |
    |  +------v------+ |
    |  | Aggregator  | |  (Circuit breakers, trends)
    |  +------+------+ |
    |         |        |
    |  +------v------+ |
    |  | Watchdog    | |  (Self-monitoring)
    |  +-------------+ |
    +------------------+

Component Ports:
    - FTI:        9877
    - ROC:        9878
    - DIMC:       9879
    - COMC:       9880
    - ROS2Bridge: 9881
    - UE5Bridge:  9882

Usage:
    from hb_subsystem import HBSubsystem, HBAgent, ActivityType
    
    # In Webthread Core:
    hb = HBSubsystem()
    hb.start()
    
    # In Components:
    agent = HBAgent('FTI')
    agent.start()
    agent.report_activity(ActivityType.MESSAGE_PROCESSED)
"""

# Main subsystem
from .hb_subsystem import HBSubsystem, create_hb_subsystem

# Agent for components
from .hb_agent import HBAgent, ActivityScope, IdleMonitor

# Types and constants
from .hb_types import (
    # Timing
    HBTiming,
    HBPorts,
    
    # Activity
    ActivityType,
    ActivityCategory,
    validate_activities,
    
    # States
    ComponentState,
    TransitionState,
    HealthLevel,
    AlertLevel,
    
    # Packets
    HeartbeatPacket,
    StartupPing,
    StartupAck,
    
    # Health status
    ComponentHealthStatus,
    ComponentID,
    
    # Circuit breaker
    CircuitBreakerState,
    CircuitBreakerStatus,
    
    # Failures
    FailureType,
    FailureEvent,
    
    # Utilities
    is_sequence_gap,
    calculate_sequence_gap,
    get_timestamp_us,
    activity_to_bitmap,
    bitmap_to_activities,
)

# Overload protection
from .overload_protection import (
    Bulkhead,
    RateLimiter,
    AdaptiveLimiter,
    MinRateDetector,
    OverloadProtector,
    OverloadProtectorFactory,
    BulkheadFullError,
    RateLimitExceededError,
)

# Receiver
from .hb_receiver import HBReceiver, ComponentReceiver

# Health aggregation
from .health_aggregator import (
    HealthAggregator,
    CircuitBreaker,
    RecoveryManager,
    RecoveryAction,
    RecoveryAttempt,
    TrendAnalyzer,
    FailureScenarioHandler,
)

# Watchdog
from .hb_watchdog import HBWatchdog, ComponentWatchdog, WatchdogStatus

# Persistence
from .state_persistence import StatePersistence, StateRecovery

__all__ = [
    # Main
    'HBSubsystem',
    'create_hb_subsystem',
    
    # Agent
    'HBAgent',
    'ActivityScope',
    'IdleMonitor',
    
    # Types
    'HBTiming',
    'HBPorts',
    'ActivityType',
    'ActivityCategory',
    'validate_activities',
    'ComponentState',
    'TransitionState',
    'HealthLevel',
    'AlertLevel',
    'HeartbeatPacket',
    'StartupPing',
    'StartupAck',
    'ComponentHealthStatus',
    'ComponentID',
    'CircuitBreakerState',
    'CircuitBreakerStatus',
    'FailureType',
    'FailureEvent',
    'is_sequence_gap',
    'calculate_sequence_gap',
    'get_timestamp_us',
    'activity_to_bitmap',
    'bitmap_to_activities',
    
    # Overload
    'Bulkhead',
    'RateLimiter',
    'AdaptiveLimiter',
    'MinRateDetector',
    'OverloadProtector',
    'OverloadProtectorFactory',
    'BulkheadFullError',
    'RateLimitExceededError',
    
    # Receiver
    'HBReceiver',
    'ComponentReceiver',
    
    # Aggregator
    'HealthAggregator',
    'CircuitBreaker',
    'RecoveryManager',
    'RecoveryAction',
    'RecoveryAttempt',
    'TrendAnalyzer',
    'FailureScenarioHandler',
    
    # Watchdog
    'HBWatchdog',
    'ComponentWatchdog',
    'WatchdogStatus',
    
    # Persistence
    'StatePersistence',
    'StateRecovery',
]

__version__ = '1.0.0'
