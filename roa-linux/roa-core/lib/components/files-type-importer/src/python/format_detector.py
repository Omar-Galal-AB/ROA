"""
Format Detector Module
Auto-detects 3D file format from file extension and content analysis
"""

import logging
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class FormatDetector:
    """
    Automatically detects the format of 3D model files.

    Supports detection through:
    - File extension analysis
    - Content/header inspection
    - XML namespace detection (for URDF, DAE)
    """

    # Format definitions with their extensions
    FORMAT_EXTENSIONS = {
        "urdf": [".urdf", ".xacro"],
        "sdf": [".sdf", ".world"],  # SDF/Gazebo world files
        "stl": [".stl"],
        "obj": [".obj"],
        "fbx": [".fbx"],
        "dae": [".dae"],
        "gltf": [".gltf", ".glb"],  # glTF 2.0 (text/binary)
        "step": [".step", ".stp"],
        "iges": [".iges", ".igs"],
        "usd": [".usd", ".usda", ".usdc", ".usdz"],
        "mjcf": [".xml"],  # MuJoCo (detected by content)
    }

    # XML namespace identifiers for XML-based formats
    XML_NAMESPACES = {
        "urdf": "http://www.ros.org",  # URDF typically has robot tag
        "dae": "http://www.collada.org",  # COLLADA namespace
        "sdf": "http://sdformat.org",  # SDF namespace
    }

    def __init__(self):
        """Initialize the format detector."""
        self._reverse_extension_map = self._build_reverse_map()

    def _build_reverse_map(self) -> Dict[str, str]:
        """Build reverse mapping from extension to format name."""
        reverse_map = {}
        for format_name, extensions in self.FORMAT_EXTENSIONS.items():
            for ext in extensions:
                reverse_map[ext.lower()] = format_name
        return reverse_map

    def detect_format(self, file_path: str) -> Optional[str]:
        """
        Detect the format of a 3D model file.

        Args:
            file_path: Path to the 3D model file

        Returns:
            Format name (e.g., 'urdf', 'stl', 'obj') or None if unknown
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # First, try extension-based detection
        format_name = self._detect_by_extension(file_path)
        if format_name:
            # Validate with content inspection for text-based formats
            if format_name in ["urdf", "dae", "obj"]:
                validated_format = self._validate_by_content(file_path, format_name)
                if validated_format:
                    return validated_format
            return format_name

        # If extension detection fails, try content-based detection
        return self._detect_by_content(file_path)

    def _detect_by_extension(self, file_path: str) -> Optional[str]:
        """
        Detect format based on file extension.

        Args:
            file_path: Path to the file

        Returns:
            Format name or None if extension not recognized
        """
        extension = Path(file_path).suffix.lower()
        return self._reverse_extension_map.get(extension)

    def _detect_by_content(self, file_path: str) -> Optional[str]:
        """
        Detect format by inspecting file content.

        Args:
            file_path: Path to the file

        Returns:
            Format name or None if content not recognized
        """
        try:
            # Check if it's a binary or text file
            with open(file_path, "rb") as f:
                header = f.read(100)

            # STL binary detection (starts with "solid " in ASCII or 80-byte header in binary)
            if header.startswith(b"solid "):
                return "stl"

            # Try XML-based format detection
            try:
                tree = ET.parse(file_path)
                root = tree.getroot()

                # Check for URDF (has <robot> root tag)
                if root.tag == "robot":
                    return "urdf"

                # Check for COLLADA/DAE (has COLLADA namespace)
                if "COLLADA" in root.tag or "collada" in root.tag.lower():
                    return "dae"

            except ET.ParseError:
                # Not an XML file, try other detections
                pass

            # Check text-based formats
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    first_lines = [f.readline() for _ in range(5)]
                    content = "".join(first_lines).lower()

                    # OBJ detection (starts with v, vt, vn, f lines)
                    if any(
                        line.startswith(("v ", "vt ", "vn ", "f ")) for line in content.split("\n")
                    ):
                        return "obj"

            except UnicodeDecodeError:
                # Binary format
                pass

        except Exception as e:
            logger.warning(f"Error during content detection: {e}")

        return None

    def _validate_by_content(self, file_path: str, suspected_format: str) -> Optional[str]:
        """
        Validate a suspected format by checking file content.

        Args:
            file_path: Path to the file
            suspected_format: The format suspected from extension

        Returns:
            Validated format name or None if validation fails
        """
        if suspected_format == "urdf":
            try:
                tree = ET.parse(file_path)
                root = tree.getroot()
                if root.tag == "robot":
                    return "urdf"
            except (ET.ParseError, IOError, OSError) as e:
                logger.debug(f"URDF validation failed for {file_path}: {e}")

        elif suspected_format == "dae":
            try:
                tree = ET.parse(file_path)
                root = tree.getroot()
                if "COLLADA" in root.tag or "collada" in root.tag.lower():
                    return "dae"
            except (ET.ParseError, IOError, OSError) as e:
                logger.debug(f"DAE validation failed for {file_path}: {e}")

        elif suspected_format == "obj":
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    # Check first few lines for OBJ-specific syntax
                    for _ in range(10):
                        line = f.readline().strip()
                        if line.startswith(("v ", "vt ", "vn ", "f ", "mtllib ", "usemtl ")):
                            return "obj"
            except (IOError, OSError) as e:
                logger.debug(f"OBJ validation failed for {file_path}: {e}")

        elif suspected_format == "sdf":
            try:
                tree = ET.parse(file_path)
                root = tree.getroot()
                if root.tag == "sdf" or root.tag == "world":
                    return "sdf"
            except (ET.ParseError, IOError, OSError) as e:
                logger.debug(f"SDF validation failed for {file_path}: {e}")

        # If validation fails, return None to trigger further detection
        return None

    def is_supported_format(self, format_name: str) -> bool:
        """
        Check if a format is supported by FTI.

        Args:
            format_name: Name of the format (e.g., 'urdf', 'stl')

        Returns:
            True if format is supported, False otherwise
        """
        return format_name.lower() in self.FORMAT_EXTENSIONS

    def get_supported_formats(self) -> list:
        """
        Get list of all supported formats.

        Returns:
            List of supported format names
        """
        return list(self.FORMAT_EXTENSIONS.keys())

    def get_extensions_for_format(self, format_name: str) -> list:
        """
        Get file extensions for a specific format.

        Args:
            format_name: Name of the format

        Returns:
            List of file extensions (e.g., ['.urdf', '.xacro'])
        """
        return self.FORMAT_EXTENSIONS.get(format_name.lower(), [])
