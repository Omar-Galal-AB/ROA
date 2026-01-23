"""
Safety Zone Calculator - Calculates safety boundaries around robots
"""

from typing import Dict, Tuple
import logging


class SafetyZoneCalculator:
    """
    Calculates safety zones (boundaries with safety margin) around robots
    """
    
    def __init__(self, safety_margin: float = 0.1):
        """
        Initialize safety zone calculator
        
        Args:
            safety_margin: Safety margin in meters (default: 0.1m = 10cm)
        """
        self.safety_margin = safety_margin
        self.logger = logging.getLogger('DIMC.SafetyZoneCalculator')
        
        self.logger.info(f"SafetyZoneCalculator initialized (margin: {safety_margin}m)")
    
    def calculate(self, bounds: Dict) -> Dict:
        """
        Calculate safety zone from bounding volumes
        
        Args:
            bounds: Bounding volumes (box and sphere)
            
        Returns:
            Safety zone with expanded boundaries
        """
        safety_zone = {
            'box': {},
            'sphere': {},
            'margin': self.safety_margin
        }
        
        # Expand bounding box by safety margin
        if 'box' in bounds:
            box = bounds['box']
            margin = self.safety_margin
            
            # Expand min/max by margin
            safety_zone['box'] = {
                'min': (
                    box['min'][0] - margin,
                    box['min'][1] - margin,
                    box['min'][2] - margin
                ),
                'max': (
                    box['max'][0] + margin,
                    box['max'][1] + margin,
                    box['max'][2] + margin
                ),
                'center': box['center'],
                'extent': (
                    box['extent'][0] + margin,
                    box['extent'][1] + margin,
                    box['extent'][2] + margin
                )
            }
        
        # Expand bounding sphere by safety margin
        if 'sphere' in bounds:
            sphere = bounds['sphere']
            safety_zone['sphere'] = {
                'center': sphere['center'],
                'radius': sphere['radius'] + self.safety_margin
            }
        
        return safety_zone
    
    def check_collision(
        self,
        zone1: Dict,
        zone2: Dict,
        use_box: bool = True
    ) -> bool:
        """
        Check if two safety zones overlap (potential collision)
        
        Args:
            zone1: First safety zone
            zone2: Second safety zone
            use_box: Use box collision (True) or sphere collision (False)
            
        Returns:
            True if zones overlap
        """
        if use_box:
            return self._check_box_collision(zone1['box'], zone2['box'])
        else:
            return self._check_sphere_collision(zone1['sphere'], zone2['sphere'])
    
    def _check_box_collision(self, box1: Dict, box2: Dict) -> bool:
        """
        Check AABB collision between two boxes
        
        Args:
            box1: First bounding box
            box2: Second bounding box
            
        Returns:
            True if boxes overlap
        """
        # Check for separation along each axis
        if box1['max'][0] < box2['min'][0] or box1['min'][0] > box2['max'][0]:
            return False  # Separated along X
        if box1['max'][1] < box2['min'][1] or box1['min'][1] > box2['max'][1]:
            return False  # Separated along Y
        if box1['max'][2] < box2['min'][2] or box1['min'][2] > box2['max'][2]:
            return False  # Separated along Z
        
        return True  # Overlapping
    
    def _check_sphere_collision(self, sphere1: Dict, sphere2: Dict) -> bool:
        """
        Check sphere collision
        
        Args:
            sphere1: First bounding sphere
            sphere2: Second bounding sphere
            
        Returns:
            True if spheres overlap
        """
        # Calculate distance between centers
        dx = sphere2['center'][0] - sphere1['center'][0]
        dy = sphere2['center'][1] - sphere1['center'][1]
        dz = sphere2['center'][2] - sphere1['center'][2]
        distance = (dx**2 + dy**2 + dz**2) ** 0.5
        
        # Check if distance is less than sum of radii
        return distance < (sphere1['radius'] + sphere2['radius'])
    
    def set_safety_margin(self, margin: float) -> None:
        """
        Update safety margin
        
        Args:
            margin: New safety margin in meters
        """
        self.safety_margin = margin
        self.logger.info(f"Safety margin updated to {margin}m")
