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

from .blocking_task_manager import (
    BlockingTaskManager,
    Mission,
    Task,
    TaskPriority,
    TaskQueue,
    TaskState,
    TaskType,
)
from .comc_api import COMCApi, COMCStatus, RobotSummary
from .emergency_stop import (
    EmergencyStopSystem,
    EvasionVector,
    StopLevel,
    StopReason,
    StopState,
    ZoneBasedStop,
)
from .enhanced_comc_coordinator import (
    CoordinationConfig,
    CoordinationMode,
    EnhancedCOMCCoordinator,
)
from .enhanced_state_tracker import (
    CoordinationState,
    EnhancedStateTracker,
    HealthStatus,
    OperationalState,
    Position2D,
    RobotFullState,
    StateChangeEvent,
    Velocity2D,
)
from .mapf_solver import (
    CBSMAPFSolver,
    Conflict,
    MAPFRequest,
    MAPFService,
    MAPFSolution,
    PathNode,
    SimpleMAPFSolver,
    TimedPath,
)
from .path_conflict_detector import (
    ConflictPriority,
    ConflictType,
    CriticalSection,
    PathConflictDetector,
    RobotPath,
)

# Core modules
from .robot_interface import RobotActionClient, RobotData, RobotInterface, RobotState

# Convenience exports
__all__ = [
    # Main API
    "COMCApi",
    "COMCStatus",
    "RobotSummary",
    # Coordinator
    "EnhancedCOMCCoordinator",
    "CoordinationMode",
    "CoordinationConfig",
    # Robot Interface
    "RobotInterface",
    "RobotState",
    "RobotData",
    # Path Conflict
    "PathConflictDetector",
    "CriticalSection",
    "ConflictType",
    # Emergency Stop
    "EmergencyStopSystem",
    "StopReason",
    "StopLevel",
    "ZoneBasedStop",
    # Task Manager
    "BlockingTaskManager",
    "Task",
    "TaskType",
    "TaskPriority",
    "Mission",
    # State Tracker
    "EnhancedStateTracker",
    "OperationalState",
    "CoordinationState",
    "HealthStatus",
    "RobotFullState",
    # MAPF
    "MAPFService",
    "MAPFSolution",
    "TimedPath",
    "PathNode",
]
