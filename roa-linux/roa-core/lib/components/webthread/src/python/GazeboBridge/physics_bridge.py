"""
physics_bridge.py
ROA - Robot Operations & Automation
Physics bridge between Gazebo and UE5

This module manages the physics data flow between Gazebo's physics engine
and UE5's visualization, ensuring accurate robotics simulation when UE5's
Chaos Physics is insufficient.
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum


class PhysicsMode(Enum):
    """Physics computation mode"""
    UE5_ONLY = "ue5_only"          # Use UE5 Chaos Physics only
    GAZEBO_ONLY = "gazebo_only"    # Use Gazebo physics only
    HYBRID = "hybrid"               # Use both with priority system


@dataclass
class PhysicsState:
    """Physics state data"""
    timestamp: float
    positions: Dict[str, List[float]]  # Entity positions (x, y, z)
    orientations: Dict[str, List[float]]  # Entity orientations (quaternion)
    velocities: Dict[str, List[float]]  # Linear velocities
    angular_velocities: Dict[str, List[float]]  # Angular velocities
    forces: Dict[str, List[float]]  # Applied forces
    torques: Dict[str, List[float]]  # Applied torques


class PhysicsBridge:
    """
    Bridges physics computation between Gazebo and UE5
    
    This bridge allows switching between physics engines or running them
    in parallel for validation, ensuring maximum accuracy for robotics
    simulations.
    """

    def __init__(self, mode: PhysicsMode = PhysicsMode.UE5_ONLY):
        """
        Initialize Physics Bridge
        
        Args:
            mode: Physics computation mode
        """
        self.logger = logging.getLogger(__name__)
        self.mode = mode
        self.gazebo_state: Optional[PhysicsState] = None
        self.ue5_state: Optional[PhysicsState] = None
        self.sync_threshold = 0.01  # Position sync threshold in meters
        
        self.logger.info(f"PhysicsBridge initialized in {mode.value} mode")

    def set_mode(self, mode: PhysicsMode):
        """
        Set physics computation mode
        
        Args:
            mode: New physics mode
        """
        self.mode = mode
        self.logger.info(f"Physics mode set to {mode.value}")

    def update_gazebo_state(self, state: PhysicsState):
        """
        Update physics state from Gazebo
        
        Args:
            state: Current Gazebo physics state
        """
        self.gazebo_state = state
        self.logger.debug("Updated Gazebo physics state")

    def update_ue5_state(self, state: PhysicsState):
        """
        Update physics state from UE5
        
        Args:
            state: Current UE5 physics state
        """
        self.ue5_state = state
        self.logger.debug("Updated UE5 physics state")

    def get_authoritative_state(self) -> Optional[PhysicsState]:
        """
        Get the authoritative physics state based on current mode
        
        Returns:
            Authoritative physics state or None
        """
        if self.mode == PhysicsMode.UE5_ONLY:
            return self.ue5_state
        elif self.mode == PhysicsMode.GAZEBO_ONLY:
            return self.gazebo_state
        elif self.mode == PhysicsMode.HYBRID:
            # In hybrid mode, Gazebo is authoritative for physics
            return self.gazebo_state
        return None

    def sync_to_ue5(self) -> bool:
        """
        Synchronize Gazebo physics state to UE5
        
        Returns:
            True if sync successful
        """
        if not self.gazebo_state:
            self.logger.warning("No Gazebo state to sync")
            return False
        
        try:
            # TODO: Send Gazebo state to UE5
            # This would update UE5 entity positions/orientations
            # without affecting UE5's physics computation
            self.logger.debug("Synced Gazebo state to UE5")
            return True
        except Exception as e:
            self.logger.error(f"Failed to sync to UE5: {e}")
            return False

    def sync_from_ue5(self) -> bool:
        """
        Synchronize UE5 physics state to Gazebo
        
        Returns:
            True if sync successful
        """
        if not self.ue5_state:
            self.logger.warning("No UE5 state to sync")
            return False
        
        try:
            # TODO: Send UE5 state to Gazebo
            # This would update Gazebo entity positions/orientations
            self.logger.debug("Synced UE5 state to Gazebo")
            return True
        except Exception as e:
            self.logger.error(f"Failed to sync from UE5: {e}")
            return False

    def compare_states(self) -> Dict[str, Any]:
        """
        Compare Gazebo and UE5 physics states
        
        Returns:
            Dictionary with comparison results
        """
        if not self.gazebo_state or not self.ue5_state:
            return {'error': 'Missing state data'}
        
        comparison = {
            'timestamp_diff': abs(self.gazebo_state.timestamp - self.ue5_state.timestamp),
            'position_diffs': {},
            'orientation_diffs': {},
            'max_position_error': 0.0,
            'entities_in_sync': 0,
            'entities_out_of_sync': 0
        }
        
        # Compare positions for each entity
        for entity_id in self.gazebo_state.positions.keys():
            if entity_id in self.ue5_state.positions:
                gazebo_pos = self.gazebo_state.positions[entity_id]
                ue5_pos = self.ue5_state.positions[entity_id]
                
                # Calculate Euclidean distance
                diff = sum((g - u) ** 2 for g, u in zip(gazebo_pos, ue5_pos)) ** 0.5
                comparison['position_diffs'][entity_id] = diff
                
                if diff > comparison['max_position_error']:
                    comparison['max_position_error'] = diff
                
                if diff <= self.sync_threshold:
                    comparison['entities_in_sync'] += 1
                else:
                    comparison['entities_out_of_sync'] += 1
        
        return comparison

    def validate_physics_accuracy(self) -> bool:
        """
        Validate UE5 physics accuracy against Gazebo
        
        This is useful during development to ensure UE5's Chaos Physics
        is configured correctly for robotics simulation.
        
        Returns:
            True if UE5 physics is within acceptable tolerance
        """
        comparison = self.compare_states()
        
        if 'error' in comparison:
            self.logger.error(f"Validation error: {comparison['error']}")
            return False
        
        max_error = comparison['max_position_error']
        acceptable_error = 0.05  # 5cm maximum error
        
        if max_error > acceptable_error:
            self.logger.warning(
                f"Physics validation failed: max error {max_error:.4f}m exceeds "
                f"threshold {acceptable_error:.4f}m"
            )
            return False
        
        self.logger.info(
            f"Physics validation passed: max error {max_error:.4f}m, "
            f"{comparison['entities_in_sync']} entities in sync"
        )
        return True

    def apply_corrections(self) -> bool:
        """
        Apply corrections to UE5 based on Gazebo physics
        
        In hybrid mode, this corrects UE5 physics drift by periodically
        syncing with Gazebo's more accurate physics.
        
        Returns:
            True if corrections applied successfully
        """
        if self.mode != PhysicsMode.HYBRID:
            self.logger.debug("Corrections only applied in hybrid mode")
            return True
        
        comparison = self.compare_states()
        
        if comparison['entities_out_of_sync'] > 0:
            self.logger.info(
                f"Applying corrections to {comparison['entities_out_of_sync']} entities"
            )
            return self.sync_to_ue5()
        
        return True

    def get_physics_metrics(self) -> Dict[str, Any]:
        """
        Get physics simulation metrics
        
        Returns:
            Dictionary with physics metrics
        """
        metrics = {
            'mode': self.mode.value,
            'gazebo_available': self.gazebo_state is not None,
            'ue5_available': self.ue5_state is not None,
        }
        
        if self.gazebo_state and self.ue5_state:
            comparison = self.compare_states()
            metrics.update({
                'max_position_error': comparison['max_position_error'],
                'entities_in_sync': comparison['entities_in_sync'],
                'entities_out_of_sync': comparison['entities_out_of_sync'],
                'sync_quality': (
                    comparison['entities_in_sync'] / 
                    (comparison['entities_in_sync'] + comparison['entities_out_of_sync'])
                    if (comparison['entities_in_sync'] + comparison['entities_out_of_sync']) > 0
                    else 0.0
                )
            })
        
        return metrics
