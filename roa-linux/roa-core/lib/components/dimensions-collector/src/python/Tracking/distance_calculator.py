"""
Distance Calculator - Calculates inter-robot distances
"""

import logging
from typing import Dict, Optional, Tuple


class DistanceCalculator:
    """
    Calculates distances between robots
    """

    def __init__(self, config: Dict = None):
        """
        Initialize distance calculator

        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.logger = logging.getLogger("DIMC.DistanceCalculator")

        self.update_rate = self.config.get("update_rate", 20)  # Hz (less frequent)
        self.max_distance = self.config.get("max_distance", 100.0)  # meters

        # Cache of last calculated distances
        self.distance_cache: Dict[Tuple[str, str], float] = {}

        self.logger.info(f"DistanceCalculator initialized (rate: {self.update_rate}Hz)")

    def calculate_distance(
        self, pos1: Tuple[float, float, float], pos2: Tuple[float, float, float]
    ) -> float:
        """
        Calculate Euclidean distance between two positions

        Args:
            pos1: First position (x, y, z)
            pos2: Second position (x, y, z)

        Returns:
            Distance in meters
        """
        dx = pos2[0] - pos1[0]
        dy = pos2[1] - pos1[1]
        dz = pos2[2] - pos1[2]

        return (dx**2 + dy**2 + dz**2) ** 0.5

    def calculate_all_distances(
        self, robot_positions: Dict[str, Tuple[float, float, float]]
    ) -> Dict[Tuple[str, str], float]:
        """
        Calculate distances between all pairs of robots

        Args:
            robot_positions: Dictionary of robot_id -> position

        Returns:
            Dictionary of (robot_id_1, robot_id_2) -> distance
        """
        distances = {}
        robot_ids = list(robot_positions.keys())

        # Calculate pairwise distances
        for i, robot_id_1 in enumerate(robot_ids):
            for robot_id_2 in robot_ids[i + 1 :]:
                pos1 = robot_positions[robot_id_1]
                pos2 = robot_positions[robot_id_2]

                distance = self.calculate_distance(pos1, pos2)

                # Only store if within max distance
                if distance <= self.max_distance:
                    # Store both orderings for easy lookup
                    distances[(robot_id_1, robot_id_2)] = distance
                    distances[(robot_id_2, robot_id_1)] = distance

        # Update cache
        self.distance_cache = distances

        return distances

    def get_distance(self, robot_id_1: str, robot_id_2: str) -> Optional[float]:
        """
        Get cached distance between two robots

        Args:
            robot_id_1: First robot identifier
            robot_id_2: Second robot identifier

        Returns:
            Distance in meters or None if not cached
        """
        return self.distance_cache.get((robot_id_1, robot_id_2))

    def get_nearest_robot(
        self, robot_id: str, robot_positions: Dict[str, Tuple[float, float, float]]
    ) -> Optional[Tuple[str, float]]:
        """
        Find the nearest robot to a given robot

        Args:
            robot_id: Target robot identifier
            robot_positions: Dictionary of robot_id -> position

        Returns:
            (nearest_robot_id, distance) or None if no other robots
        """
        if robot_id not in robot_positions:
            return None

        target_pos = robot_positions[robot_id]
        min_distance = float("inf")
        nearest_robot = None

        for other_id, other_pos in robot_positions.items():
            if other_id == robot_id:
                continue

            distance = self.calculate_distance(target_pos, other_pos)
            if distance < min_distance:
                min_distance = distance
                nearest_robot = other_id

        if nearest_robot:
            return (nearest_robot, min_distance)
        return None
