"""
COMC (Communication Center) Enhanced Package

Multi-robot coordination and communication system based on:
- REMROC coordinator pattern
- Open-RMF fleet adapter
- Karelics Task Manager

Modules:
- robot_interface: Per-robot action clients and publishers
- path_conflict_detector: Critical section detection
- emergency_stop: Safety and collision avoidance
- blocking_task_manager: Task execution with blocking
- enhanced_state_tracker: Centralized state management
- mapf_solver: Multi-agent path finding
- enhanced_comc_coordinator: Main coordinator node
- comc_api: High-level API

Quick Start:
    from comc_enhanced import COMCApi
    
    api = COMCApi()
    api.register_robot('robot1')
    api.register_robot('robot2')
    
    # Navigate
    api.navigate('robot1', 5.0, 3.0)
    
    # Check conflicts
    conflicts = api.get_conflicts()
    
    # Emergency stop
    api.stop('robot1')
    api.resume('robot1')
    
    # Fleet status
    summary = api.get_fleet_summary()
"""

__version__ = "2.0.0"
__author__ = "ROA Team"

# Core modules
from .robot_interface import (
    RobotInterface,
    RobotState,
    RobotData,
    RobotActionClient
)

from .path_conflict_detector import (
    PathConflictDetector,
    CriticalSection,
    ConflictType,
    ConflictPriority,
    RobotPath
)

from .emergency_stop import (
    EmergencyStopSystem,
    StopReason,
    StopLevel,
    StopState,
    EvasionVector,
    ZoneBasedStop
)

from .blocking_task_manager import (
    BlockingTaskManager,
    Task,
    TaskType,
    TaskState,
    TaskPriority,
    Mission,
    TaskQueue
)

from .enhanced_state_tracker import (
    EnhancedStateTracker,
    OperationalState,
    CoordinationState,
    HealthStatus,
    RobotFullState,
    Position2D,
    Velocity2D,
    StateChangeEvent
)

from .mapf_solver import (
    MAPFService,
    MAPFSolution,
    MAPFRequest,
    TimedPath,
    PathNode,
    Conflict,
    SimpleMAPFSolver,
    CBSMAPFSolver
)

from .enhanced_comc_coordinator import (
    EnhancedCOMCCoordinator,
    CoordinationMode,
    CoordinationConfig
)

from .comc_api import (
    COMCApi,
    COMCStatus,
    RobotSummary
)

# Convenience exports
__all__ = [
    # Main API
    'COMCApi',
    'COMCStatus',
    'RobotSummary',
    
    # Coordinator
    'EnhancedCOMCCoordinator',
    'CoordinationMode',
    'CoordinationConfig',
    
    # Robot Interface
    'RobotInterface',
    'RobotState',
    'RobotData',
    
    # Path Conflict
    'PathConflictDetector',
    'CriticalSection',
    'ConflictType',
    
    # Emergency Stop
    'EmergencyStopSystem',
    'StopReason',
    'StopLevel',
    'ZoneBasedStop',
    
    # Task Manager
    'BlockingTaskManager',
    'Task',
    'TaskType',
    'TaskPriority',
    'Mission',
    
    # State Tracker
    'EnhancedStateTracker',
    'OperationalState',
    'CoordinationState',
    'HealthStatus',
    'RobotFullState',
    
    # MAPF
    'MAPFService',
    'MAPFSolution',
    'TimedPath',
    'PathNode',
]
