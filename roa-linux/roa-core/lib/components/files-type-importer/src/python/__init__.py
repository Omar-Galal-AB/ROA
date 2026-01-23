"""
Files Type Importer (FTI) - Python Module
Automated import of robot 3D models into Unreal Engine 5

This module provides format conversion utilities and import coordination
for various 3D file formats including URDF, STL, OBJ, FBX, DAE, STEP, and IGES.
"""

__version__ = "0.1.0"
__author__ = "ROA Development Team"

from .file_type_importer import FileTypeImporter
from .format_detector import FormatDetector

__all__ = [
    "FileTypeImporter",
    "FormatDetector",
]
