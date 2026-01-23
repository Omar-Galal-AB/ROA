"""
Material Mapper - Maps source materials to UE5 materials
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class MaterialMapper:
    """
    Maps materials from source formats to Unreal Engine 5 materials.

    Handles material conversion for:
    - Colors (RGBA)
    - Textures
    - Physical properties (metallic, roughness, etc.)
    """

    def __init__(self, material_library_path: Optional[str] = None):
        """
        Initialize the material mapper.

        Args:
            material_library_path: Optional path to material library JSON
        """
        self.material_library = self._load_material_library(material_library_path)

    def _load_material_library(self, library_path: Optional[str]) -> Dict:
        """
        Load the material library configuration.

        Args:
            library_path: Path to material library JSON

        Returns:
            Material library dictionary
        """
        if library_path and Path(library_path).exists():
            with open(library_path, "r") as f:
                return json.load(f)

        # Return default library if file not found
        return {
            "materials": {
                "default": {
                    "ue5_material": "/Game/Materials/M_Default_Base",
                    "properties": {"metallic": 0.0, "roughness": 0.5, "specular": 0.3},
                    "color_default": [0.7, 0.7, 0.7, 1.0],
                }
            }
        }

    def map_material(
        self,
        source_material: str,
        source_color: Optional[List[float]] = None,
        source_texture: Optional[str] = None,
    ) -> Dict:
        """
        Map a source material to UE5 material.

        Args:
            source_material: Name of source material
            source_color: Optional RGBA color [r, g, b, a]
            source_texture: Optional texture file path

        Returns:
            Dictionary with UE5 material information
        """
        # Check if we have a predefined mapping
        material_name = source_material.lower()
        if material_name in self.material_library["materials"]:
            ue5_material = self.material_library["materials"][material_name].copy()
        else:
            # Use default material
            ue5_material = self.material_library["materials"]["default"].copy()

        # Override with source color if provided
        if source_color:
            ue5_material["color"] = source_color

        # Add texture if provided
        if source_texture:
            ue5_material["texture"] = source_texture

        return ue5_material

    def map_color(self, rgba: List[float]) -> Tuple[float, float, float, float]:
        """
        Map and validate RGBA color values.

        Args:
            rgba: Color as [r, g, b, a] list

        Returns:
            Tuple of (r, g, b, a) floats in range 0-1
        """
        if len(rgba) < 3:
            return (0.7, 0.7, 0.7, 1.0)  # Default gray

        r = max(0.0, min(1.0, rgba[0]))
        g = max(0.0, min(1.0, rgba[1]))
        b = max(0.0, min(1.0, rgba[2]))
        a = max(0.0, min(1.0, rgba[3] if len(rgba) > 3 else 1.0))

        return (r, g, b, a)

    def get_default_material(self) -> Dict:
        """
        Get the default UE5 material.

        Returns:
            Default material dictionary
        """
        return self.material_library["materials"]["default"].copy()
