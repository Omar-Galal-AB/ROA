"""
Path Conflict Detector

Detects conflicts between robot paths including:
- Path intersection (critical sections)
- Spatial conflicts (robots too close on overlapping paths)
- Temporal conflicts (robots reaching same point at similar times)

Based on REMROC path-based coordination pattern.
"""

import math
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

import rclpy
from geometry_msgs.msg import Point, PoseStamped
from nav_msgs.msg import Path
from rclpy.node import Node


class ConflictType(Enum):
    """Types of path conflicts"""

    NONE = "none"
    INTERSECTION = "intersection"  # Paths cross at a point
    OVERLAP = "overlap"  # Paths share a segment
    MEETING = "meeting"  # Robots will meet head-on
    FOLLOWING = "following"  # One robot following another too closely
    CROSSING = "crossing"  # Paths cross at similar times
    DEADLOCK = "deadlock"  # Mutual blocking


class ConflictPriority(Enum):
    """Priority levels for conflict resolution"""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class CriticalSection:
    """
    A critical section where two robot paths conflict.
    Based on REMROC's critical section detection.
    """

    robot1_id: str
    robot2_id: str

    # Section boundaries (indices into path)
    robot1_start_idx: int
    robot1_end_idx: int
    robot2_start_idx: int
    robot2_end_idx: int

    # Geometric info
    intersection_points: List[Tuple[float, float]] = field(default_factory=list)
    section_length: float = 0.0

    # Conflict type
    conflict_type: ConflictType = ConflictType.INTERSECTION
    priority: ConflictPriority = ConflictPriority.MEDIUM

    # Resolution
    resolved: bool = False
    priority_robot: Optional[str] = None  # Robot that should go first


@dataclass
class RobotPath:
    """Stored path for a robot"""

    robot_id: str
    path: List[Tuple[float, float]]  # List of (x, y) waypoints
    timestamps: Optional[List[float]] = None  # Expected arrival times
    created_at: float = field(default_factory=time.time)

    # Progress tracking
    current_index: int = 0

    def get_remaining_path(self) -> List[Tuple[float, float]]:
        """Get path from current position onwards"""
        return self.path[self.current_index :]


class PathConflictDetector:
    """
    Detects and manages conflicts between robot paths.

    Key Features:
    - Critical section detection (path intersections)
    - Spatial proximity checking
    - Temporal conflict analysis
    - Priority-based resolution suggestions
    """

    # Configuration
    INTERSECTION_THRESHOLD = 0.5  # meters - distance to consider paths intersecting
    FOLLOWING_THRESHOLD = 1.5  # meters - distance for following detection
    SEGMENT_RESOLUTION = 0.1  # meters - resolution for path interpolation
    TIME_CONFLICT_WINDOW = 5.0  # seconds - time window for temporal conflicts

    def __init__(self, logger=None):
        self.logger = logger

        # Stored paths
        self.robot_paths: Dict[str, RobotPath] = {}

        # Active critical sections
        self.critical_sections: List[CriticalSection] = []

        # Robot priorities (higher = more priority)
        self.robot_priorities: Dict[str, int] = {}

        # Lock for thread safety
        self._lock = threading.RLock()

    def set_path(
        self,
        robot_id: str,
        path: List[Tuple[float, float]],
        timestamps: Optional[List[float]] = None,
    ) -> List[CriticalSection]:
        """
        Set/update path for a robot and detect conflicts.

        Args:
            robot_id: Robot identifier
            path: List of (x, y) waypoints
            timestamps: Optional arrival times for temporal conflict detection

        Returns:
            List of detected critical sections involving this robot
        """
        with self._lock:
            # Store path
            self.robot_paths[robot_id] = RobotPath(
                robot_id=robot_id, path=path, timestamps=timestamps
            )

            # Check for conflicts with all other robots
            new_conflicts = []
            for other_id, other_path in self.robot_paths.items():
                if other_id == robot_id:
                    continue

                conflicts = self._detect_conflicts(
                    robot_id,
                    path,
                    timestamps,
                    other_id,
                    other_path.path,
                    other_path.timestamps,
                )
                new_conflicts.extend(conflicts)

            # Update critical sections (remove old ones for this robot, add new)
            self.critical_sections = [
                cs
                for cs in self.critical_sections
                if cs.robot1_id != robot_id and cs.robot2_id != robot_id
            ]
            self.critical_sections.extend(new_conflicts)

            if new_conflicts and self.logger:
                self.logger.info(f"Detected {len(new_conflicts)} conflicts for {robot_id}")

            return new_conflicts

    def clear_path(self, robot_id: str) -> None:
        """Clear path for a robot"""
        with self._lock:
            if robot_id in self.robot_paths:
                del self.robot_paths[robot_id]

            # Remove related critical sections
            self.critical_sections = [
                cs
                for cs in self.critical_sections
                if cs.robot1_id != robot_id and cs.robot2_id != robot_id
            ]

    def update_progress(self, robot_id: str, position: Tuple[float, float]) -> None:
        """Update robot's progress along its path"""
        with self._lock:
            if robot_id not in self.robot_paths:
                return

            path_data = self.robot_paths[robot_id]

            # Find closest point on path
            min_dist = float("inf")
            closest_idx = path_data.current_index

            for i, (px, py) in enumerate(
                path_data.path[path_data.current_index :], start=path_data.current_index
            ):
                dx = position[0] - px
                dy = position[1] - py
                dist = math.sqrt(dx * dx + dy * dy)

                if dist < min_dist:
                    min_dist = dist
                    closest_idx = i

            path_data.current_index = closest_idx

    def _detect_conflicts(
        self,
        robot1_id: str,
        path1: List[Tuple[float, float]],
        times1: Optional[List[float]],
        robot2_id: str,
        path2: List[Tuple[float, float]],
        times2: Optional[List[float]],
    ) -> List[CriticalSection]:
        """
        Detect conflicts between two robot paths.

        Based on REMROC's conflict detection in coordinator_pbc.py
        """
        conflicts = []

        # Find all intersection points
        intersections = self._find_path_intersections(path1, path2)

        if not intersections:
            return conflicts

        # Group nearby intersections into critical sections
        sections = self._group_intersections(intersections)

        for section in sections:
            # Determine conflict type
            conflict_type = self._classify_conflict(
                path1, path2, section["path1_indices"], section["path2_indices"]
            )

            # Determine priority
            priority = self._calculate_priority(path1, path2, section, times1, times2)

            # Create critical section
            cs = CriticalSection(
                robot1_id=robot1_id,
                robot2_id=robot2_id,
                robot1_start_idx=min(section["path1_indices"]),
                robot1_end_idx=max(section["path1_indices"]),
                robot2_start_idx=min(section["path2_indices"]),
                robot2_end_idx=max(section["path2_indices"]),
                intersection_points=section["points"],
                section_length=section["length"],
                conflict_type=conflict_type,
                priority=priority,
                priority_robot=self._resolve_priority(robot1_id, robot2_id, section),
            )

            conflicts.append(cs)

        return conflicts

    def _find_path_intersections(
        self, path1: List[Tuple[float, float]], path2: List[Tuple[float, float]]
    ) -> List[dict]:
        """
        Find all intersection points between two paths.

        Returns list of dicts with:
        - point: (x, y) intersection point
        - path1_idx: index in path1
        - path2_idx: index in path2
        - distance: actual distance between path segments
        """
        intersections = []

        for i in range(len(path1) - 1):
            p1_start = path1[i]
            p1_end = path1[i + 1]

            for j in range(len(path2) - 1):
                p2_start = path2[j]
                p2_end = path2[j + 1]

                # Check segment-segment distance
                dist, closest_point = self._segment_segment_distance(
                    p1_start, p1_end, p2_start, p2_end
                )

                if dist < self.INTERSECTION_THRESHOLD:
                    intersections.append(
                        {
                            "point": closest_point,
                            "path1_idx": i,
                            "path2_idx": j,
                            "distance": dist,
                        }
                    )

        return intersections

    def _segment_segment_distance(
        self,
        p1: Tuple[float, float],
        p2: Tuple[float, float],
        p3: Tuple[float, float],
        p4: Tuple[float, float],
    ) -> Tuple[float, Tuple[float, float]]:
        """
        Compute minimum distance between two line segments.
        Returns (distance, closest_point_on_segment1).
        """
        # Vector from p1 to p2
        d1 = (p2[0] - p1[0], p2[1] - p1[1])
        # Vector from p3 to p4
        d2 = (p4[0] - p3[0], p4[1] - p3[1])
        # Vector from p1 to p3
        r = (p3[0] - p1[0], p3[1] - p1[1])

        a = d1[0] * d1[0] + d1[1] * d1[1]  # |d1|^2
        e = d2[0] * d2[0] + d2[1] * d2[1]  # |d2|^2
        f = d2[0] * r[0] + d2[1] * r[1]  # d2 · r

        # Check for degenerate segments
        EPSILON = 1e-8

        if a <= EPSILON and e <= EPSILON:
            # Both segments are points
            dist = math.sqrt((p3[0] - p1[0]) ** 2 + (p3[1] - p1[1]) ** 2)
            return dist, p1

        if a <= EPSILON:
            # First segment is a point
            s = 0.0
            t = max(0.0, min(1.0, f / e))
        else:
            c = d1[0] * r[0] + d1[1] * r[1]  # d1 · r

            if e <= EPSILON:
                # Second segment is a point
                t = 0.0
                s = max(0.0, min(1.0, -c / a))
            else:
                b = d1[0] * d2[0] + d1[1] * d2[1]  # d1 · d2
                denom = a * e - b * b

                if denom != 0.0:
                    s = max(0.0, min(1.0, (b * f - c * e) / denom))
                else:
                    s = 0.0

                t = (b * s + f) / e

                if t < 0.0:
                    t = 0.0
                    s = max(0.0, min(1.0, -c / a))
                elif t > 1.0:
                    t = 1.0
                    s = max(0.0, min(1.0, (b - c) / a))

        # Closest points
        closest1 = (p1[0] + s * d1[0], p1[1] + s * d1[1])
        closest2 = (p3[0] + t * d2[0], p3[1] + t * d2[1])

        dist = math.sqrt((closest2[0] - closest1[0]) ** 2 + (closest2[1] - closest1[1]) ** 2)

        return dist, closest1

    def _group_intersections(self, intersections: List[dict]) -> List[dict]:
        """
        Group nearby intersections into critical sections.
        """
        if not intersections:
            return []

        sections = []
        used = set()

        for i, inter in enumerate(intersections):
            if i in used:
                continue

            # Start new section
            section = {
                "points": [inter["point"]],
                "path1_indices": [inter["path1_idx"]],
                "path2_indices": [inter["path2_idx"]],
                "length": 0.0,
            }
            used.add(i)

            # Find nearby intersections to group
            for j, other in enumerate(intersections):
                if j in used:
                    continue

                # Check if indices are adjacent
                if (
                    abs(other["path1_idx"] - inter["path1_idx"]) <= 2
                    and abs(other["path2_idx"] - inter["path2_idx"]) <= 2
                ):
                    section["points"].append(other["point"])
                    section["path1_indices"].append(other["path1_idx"])
                    section["path2_indices"].append(other["path2_idx"])
                    used.add(j)

            # Calculate section length
            if len(section["points"]) > 1:
                for k in range(len(section["points"]) - 1):
                    dx = section["points"][k + 1][0] - section["points"][k][0]
                    dy = section["points"][k + 1][1] - section["points"][k][1]
                    section["length"] += math.sqrt(dx * dx + dy * dy)

            sections.append(section)

        return sections

    def _classify_conflict(
        self,
        path1: List[Tuple[float, float]],
        path2: List[Tuple[float, float]],
        indices1: List[int],
        indices2: List[int],
    ) -> ConflictType:
        """
        Classify the type of conflict based on path geometry.
        """
        if len(indices1) < 1 or len(indices2) < 1:
            return ConflictType.NONE

        # Get direction vectors at conflict point
        idx1 = min(indices1)
        idx2 = min(indices2)

        if idx1 + 1 >= len(path1) or idx2 + 1 >= len(path2):
            return ConflictType.INTERSECTION

        dir1 = (
            path1[idx1 + 1][0] - path1[idx1][0],
            path1[idx1 + 1][1] - path1[idx1][1],
        )
        dir2 = (
            path2[idx2 + 1][0] - path2[idx2][0],
            path2[idx2 + 1][1] - path2[idx2][1],
        )

        # Normalize
        len1 = math.sqrt(dir1[0] ** 2 + dir1[1] ** 2)
        len2 = math.sqrt(dir2[0] ** 2 + dir2[1] ** 2)

        if len1 < 1e-6 or len2 < 1e-6:
            return ConflictType.INTERSECTION

        dir1 = (dir1[0] / len1, dir1[1] / len1)
        dir2 = (dir2[0] / len2, dir2[1] / len2)

        # Dot product for angle
        dot = dir1[0] * dir2[0] + dir1[1] * dir2[1]

        if dot < -0.7:  # Roughly opposite directions (> 135 degrees)
            return ConflictType.MEETING
        elif dot > 0.7:  # Same direction (< 45 degrees)
            return ConflictType.FOLLOWING
        else:
            return ConflictType.CROSSING

    def _calculate_priority(
        self,
        path1: List[Tuple[float, float]],
        path2: List[Tuple[float, float]],
        section: dict,
        times1: Optional[List[float]],
        times2: Optional[List[float]],
    ) -> ConflictPriority:
        """
        Calculate priority level for a conflict.
        """
        # Longer overlapping sections are higher priority
        if section["length"] > 2.0:
            return ConflictPriority.CRITICAL
        elif section["length"] > 1.0:
            return ConflictPriority.HIGH

        # Check temporal proximity if timestamps available
        if times1 and times2:
            idx1 = min(section["path1_indices"])
            idx2 = min(section["path2_indices"])

            if idx1 < len(times1) and idx2 < len(times2):
                time_diff = abs(times1[idx1] - times2[idx2])

                if time_diff < 2.0:
                    return ConflictPriority.CRITICAL
                elif time_diff < 5.0:
                    return ConflictPriority.HIGH

        return ConflictPriority.MEDIUM

    def _resolve_priority(self, robot1_id: str, robot2_id: str, section: dict) -> str:
        """
        Determine which robot has priority to go first.
        Uses explicit priorities if set, otherwise by progress.
        """
        # Check explicit priorities
        p1 = self.robot_priorities.get(robot1_id, 0)
        p2 = self.robot_priorities.get(robot2_id, 0)

        if p1 != p2:
            return robot1_id if p1 > p2 else robot2_id

        # Otherwise, robot closer to conflict goes first
        # (This is a simplification - full MAPF would be more sophisticated)
        idx1 = min(section["path1_indices"])
        idx2 = min(section["path2_indices"])

        # Assume lower index means closer (needs path progress tracking for accuracy)
        return robot1_id if idx1 < idx2 else robot2_id

    def get_conflicts_for_robot(self, robot_id: str) -> List[CriticalSection]:
        """Get all conflicts involving a specific robot"""
        with self._lock:
            return [
                cs
                for cs in self.critical_sections
                if cs.robot1_id == robot_id or cs.robot2_id == robot_id
            ]

    def get_all_conflicts(self) -> List[CriticalSection]:
        """Get all active conflicts"""
        with self._lock:
            return list(self.critical_sections)

    def get_unresolved_conflicts(self) -> List[CriticalSection]:
        """Get conflicts that haven't been resolved"""
        with self._lock:
            return [cs for cs in self.critical_sections if not cs.resolved]

    def mark_resolved(self, robot1_id: str, robot2_id: str) -> None:
        """Mark conflict between two robots as resolved"""
        with self._lock:
            for cs in self.critical_sections:
                if (cs.robot1_id == robot1_id and cs.robot2_id == robot2_id) or (
                    cs.robot1_id == robot2_id and cs.robot2_id == robot1_id
                ):
                    cs.resolved = True

    def set_robot_priority(self, robot_id: str, priority: int) -> None:
        """Set explicit priority for a robot (higher = more priority)"""
        with self._lock:
            self.robot_priorities[robot_id] = priority

    def check_immediate_conflict(
        self, robot_id: str, position: Tuple[float, float], threshold: float = 2.0
    ) -> Optional[CriticalSection]:
        """
        Check if robot is about to enter a critical section.

        Args:
            robot_id: Robot to check
            position: Current robot position
            threshold: Distance threshold to conflict

        Returns:
            CriticalSection if robot is approaching one, None otherwise
        """
        with self._lock:
            for cs in self.critical_sections:
                if cs.resolved:
                    continue

                if cs.robot1_id == robot_id:
                    # Check distance to section start
                    if robot_id in self.robot_paths:
                        path = self.robot_paths[robot_id].path
                        if cs.robot1_start_idx < len(path):
                            section_start = path[cs.robot1_start_idx]
                            dist = math.sqrt(
                                (position[0] - section_start[0]) ** 2
                                + (position[1] - section_start[1]) ** 2
                            )
                            if dist < threshold:
                                return cs

                elif cs.robot2_id == robot_id:
                    if robot_id in self.robot_paths:
                        path = self.robot_paths[robot_id].path
                        if cs.robot2_start_idx < len(path):
                            section_start = path[cs.robot2_start_idx]
                            dist = math.sqrt(
                                (position[0] - section_start[0]) ** 2
                                + (position[1] - section_start[1]) ** 2
                            )
                            if dist < threshold:
                                return cs

            return None

    def should_robot_wait(
        self, robot_id: str, position: Tuple[float, float]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if robot should wait for another robot.

        Args:
            robot_id: Robot to check
            position: Current position

        Returns:
            (should_wait, other_robot_id) - True and other robot if should wait
        """
        conflict = self.check_immediate_conflict(robot_id, position)

        if conflict is None:
            return False, None

        if conflict.priority_robot and conflict.priority_robot != robot_id:
            other = conflict.robot1_id if conflict.robot2_id == robot_id else conflict.robot2_id
            return True, other

        return False, None
