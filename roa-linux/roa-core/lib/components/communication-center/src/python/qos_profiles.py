"""
QoS Profile Configurations for COMC

Defines Quality of Service policies for different message types
based on their criticality and performance requirements.
"""

from rclpy.duration import Duration
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

# Safety-critical messages (proximity alerts)
# Fast delivery more important than guaranteed delivery
SAFETY_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,  # Speed over guarantee
    durability=DurabilityPolicy.VOLATILE,  # Don't persist
    history=HistoryPolicy.KEEP_LAST,
    depth=1,  # Only latest alert matters
    deadline=Duration(nanoseconds=20_000_000),  # 20ms deadline
)

# Coordination messages (work areas, task coordination)
# Must be reliable, late joiners need the data
COORDINATION_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,  # Must not lose
    durability=DurabilityPolicy.TRANSIENT_LOCAL,  # Late joiners get data
    history=HistoryPolicy.KEEP_LAST,
    depth=10,  # Keep recent updates
)

# Status messages (heartbeats, non-critical status)
STATUS_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)
