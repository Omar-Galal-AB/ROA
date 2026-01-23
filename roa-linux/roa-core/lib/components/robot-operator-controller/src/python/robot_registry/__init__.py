"""
Robot Registry Module for ROC.

Manages robot state tracking, registration, and multi-robot coordination.
"""

from .robot_state import RobotState, JointState, RobotStatus
from .robot_manager import RobotManager

__all__ = [
    'RobotState',
    'JointState',
    'RobotStatus',
    'RobotManager',
]
