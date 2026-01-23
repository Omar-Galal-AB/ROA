"""
Robot Registry Module for ROC.

Manages robot state tracking, registration, and multi-robot coordination.
"""

from .robot_manager import RobotManager
from .robot_state import JointState, RobotState, RobotStatus

__all__ = [
    "RobotState",
    "JointState",
    "RobotStatus",
    "RobotManager",
]
