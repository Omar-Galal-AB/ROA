"""
Input Validation for FTI

Comprehensive pre-flight validation for input files and configurations.
Catches errors early before expensive conversion operations.
"""

import logging
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""

    ERROR = "error"  # Blocks processing
    WARNING = "warning"  # Continues with caution
    INFO = "info"  # Informational only


@dataclass
class ValidationIssue:
    """A single validation issue."""

    severity: ValidationSeverity
    code: str
    message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "file_path": self.file_path,
            "line": self.line_number,
            "suggestion": self.suggestion,
        }


@dataclass
class ValidationResult:
    """Result of validation check."""

    valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    file_info: Dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.ERROR]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]

    def add_issue(self, issue: ValidationIssue):
        self.issues.append(issue)
        if issue.severity == ValidationSeverity.ERROR:
            self.valid = False

    def add_error(self, code: str, message: str, **kwargs):
        self.add_issue(
            ValidationIssue(severity=ValidationSeverity.ERROR, code=code, message=message, **kwargs)
        )

    def add_warning(self, code: str, message: str, **kwargs):
        self.add_issue(
            ValidationIssue(
                severity=ValidationSeverity.WARNING,
                code=code,
                message=message,
                **kwargs,
            )
        )

    def add_info(self, code: str, message: str, **kwargs):
        self.add_issue(
            ValidationIssue(severity=ValidationSeverity.INFO, code=code, message=message, **kwargs)
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "issues": [i.to_dict() for i in self.issues],
            "file_info": self.file_info,
        }


class PreflightValidator:
    """
    Pre-flight validation for FTI input files.

    Performs comprehensive checks before conversion:
    - File existence and accessibility
    - File format validation
    - XML/structure validation for URDF/SDF
    - Mesh file availability
    - Configuration validation
    - Resource availability (textures, materials)
    """

    # Supported file extensions by format
    SUPPORTED_FORMATS = {
        "urdf": [".urdf"],
        "xacro": [".xacro"],
        "sdf": [".sdf", ".world"],
        "stl": [".stl"],
        "obj": [".obj"],
        "dae": [".dae"],
        "fbx": [".fbx"],
        "step": [".step", ".stp"],
        "iges": [".iges", ".igs"],
        "gltf": [".gltf", ".glb"],
        "usd": [".usd", ".usda", ".usdc"],
    }

    # Maximum file sizes (bytes)
    MAX_FILE_SIZES = {
        "urdf": 50 * 1024 * 1024,  # 50 MB
        "stl": 500 * 1024 * 1024,  # 500 MB
        "obj": 500 * 1024 * 1024,  # 500 MB
        "dae": 200 * 1024 * 1024,  # 200 MB
        "fbx": 500 * 1024 * 1024,  # 500 MB
        "step": 1000 * 1024 * 1024,  # 1 GB
    }

    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize validator."""
        self.logger = logger or logging.getLogger(__name__)

    def validate(
        self,
        file_path: str,
        config: Optional[Dict] = None,
        deep_validation: bool = True,
    ) -> ValidationResult:
        """
        Validate an input file.

        Args:
            file_path: Path to file to validate
            config: Optional configuration to validate against
            deep_validation: Perform deep content validation

        Returns:
            ValidationResult with issues found
        """
        result = ValidationResult(valid=True)

        # Basic file checks
        self._validate_file_exists(file_path, result)
        if not result.valid:
            return result

        self._validate_file_readable(file_path, result)
        self._validate_file_size(file_path, result)

        # Detect and validate format
        file_format = self._detect_format(file_path)
        result.file_info["detected_format"] = file_format

        if file_format is None:
            result.add_error(
                "UNSUPPORTED_FORMAT",
                f"Unsupported file format: {Path(file_path).suffix}",
                file_path=file_path,
                suggestion="Supported formats: URDF, XACRO, STL, OBJ, DAE, FBX, STEP, IGES, glTF",
            )
            return result

        # Format-specific validation
        if deep_validation:
            if file_format in ["urdf", "xacro"]:
                self._validate_urdf(file_path, result)
            elif file_format == "sdf":
                self._validate_sdf(file_path, result)
            elif file_format == "stl":
                self._validate_stl(file_path, result)
            elif file_format == "obj":
                self._validate_obj(file_path, result)
            elif file_format == "dae":
                self._validate_dae(file_path, result)

        # Config validation
        if config:
            self._validate_config(config, result)

        return result

    def validate_batch(
        self, file_paths: List[str], config: Optional[Dict] = None
    ) -> Dict[str, ValidationResult]:
        """
        Validate multiple files.

        Args:
            file_paths: List of file paths
            config: Shared configuration

        Returns:
            Dict mapping file paths to results
        """
        results = {}
        for path in file_paths:
            results[path] = self.validate(path, config)
        return results

    def _validate_file_exists(self, file_path: str, result: ValidationResult):
        """Check if file exists."""
        path = Path(file_path)

        if not path.exists():
            result.add_error(
                "FILE_NOT_FOUND",
                f"File not found: {file_path}",
                file_path=file_path,
                suggestion="Check the file path and ensure the file exists",
            )
        elif path.is_dir():
            result.add_error(
                "IS_DIRECTORY",
                f"Path is a directory, not a file: {file_path}",
                file_path=file_path,
            )

        result.file_info["path"] = str(path.absolute())
        result.file_info["name"] = path.name
        result.file_info["extension"] = path.suffix.lower()

    def _validate_file_readable(self, file_path: str, result: ValidationResult):
        """Check if file is readable."""
        try:
            with open(file_path, "rb") as f:
                f.read(1024)  # Try reading first 1KB
        except PermissionError:
            result.add_error(
                "PERMISSION_DENIED",
                f"No read permission for file: {file_path}",
                file_path=file_path,
            )
        except Exception as e:
            result.add_error("READ_ERROR", f"Cannot read file: {e}", file_path=file_path)

    def _validate_file_size(self, file_path: str, result: ValidationResult):
        """Check file size."""
        path = Path(file_path)
        size = path.stat().st_size
        result.file_info["size_bytes"] = size
        result.file_info["size_mb"] = round(size / (1024 * 1024), 2)

        # Check against format-specific limits
        ext = path.suffix.lower()
        for format_name, extensions in self.SUPPORTED_FORMATS.items():
            if ext in extensions:
                max_size = self.MAX_FILE_SIZES.get(format_name, 500 * 1024 * 1024)
                if size > max_size:
                    result.add_warning(
                        "FILE_TOO_LARGE",
                        f"File size ({size / 1024 / 1024:.1f} MB) exceeds recommended limit "
                        f"({max_size / 1024 / 1024:.0f} MB)",
                        file_path=file_path,
                        suggestion="Consider splitting into smaller files or simplifying the model",
                    )
                break

        if size == 0:
            result.add_error("EMPTY_FILE", "File is empty", file_path=file_path)

    def _detect_format(self, file_path: str) -> Optional[str]:
        """Detect file format."""
        ext = Path(file_path).suffix.lower()

        for format_name, extensions in self.SUPPORTED_FORMATS.items():
            if ext in extensions:
                return format_name

        return None

    def _validate_urdf(self, file_path: str, result: ValidationResult):
        """Validate URDF/XACRO file."""
        try:
            # Check for XACRO content
            with open(file_path, "r") as f:
                content = f.read()

            is_xacro = any(x in content for x in ["xmlns:xacro", "<xacro:", "${"])
            result.file_info["is_xacro"] = is_xacro

            if is_xacro:
                result.add_info(
                    "XACRO_DETECTED",
                    "File contains XACRO macros that will be expanded",
                    file_path=file_path,
                )
                # Can't fully validate XACRO without expansion
                return

            # Parse XML
            try:
                tree = ET.parse(file_path)
                root = tree.getroot()
            except ET.ParseError as e:
                result.add_error(
                    "XML_PARSE_ERROR",
                    f"Invalid XML: {e}",
                    file_path=file_path,
                    suggestion="Check XML syntax and encoding",
                )
                return

            # Check root element
            if root.tag != "robot":
                result.add_error(
                    "INVALID_URDF_ROOT",
                    f"Root element must be 'robot', found '{root.tag}'",
                    file_path=file_path,
                )
                return

            # Get robot name
            robot_name = root.get("name", "")
            result.file_info["robot_name"] = robot_name

            if not robot_name:
                result.add_warning(
                    "MISSING_ROBOT_NAME",
                    "Robot element has no 'name' attribute",
                    file_path=file_path,
                )

            # Count elements
            links = root.findall(".//link")
            joints = root.findall(".//joint")
            result.file_info["link_count"] = len(links)
            result.file_info["joint_count"] = len(joints)

            if len(links) == 0:
                result.add_error("NO_LINKS", "URDF has no link elements", file_path=file_path)

            # Validate mesh references
            mesh_dir = Path(file_path).parent
            mesh_elements = root.findall(".//mesh")
            missing_meshes = []

            for mesh in mesh_elements:
                filename = mesh.get("filename", "")
                if filename:
                    # Handle ROS package:// URLs
                    if filename.startswith("package://"):
                        result.add_info(
                            "PACKAGE_URL",
                            f"Package URL found: {filename}",
                            file_path=file_path,
                        )
                    elif filename.startswith("file://"):
                        mesh_path = Path(filename[7:])
                        if not mesh_path.exists():
                            missing_meshes.append(filename)
                    else:
                        # Relative path
                        mesh_path = mesh_dir / filename
                        if not mesh_path.exists():
                            # Try parent directories
                            found = False
                            for parent in mesh_dir.parents:
                                test_path = parent / filename
                                if test_path.exists():
                                    found = True
                                    break
                            if not found:
                                missing_meshes.append(filename)

            if missing_meshes:
                result.add_warning(
                    "MISSING_MESHES",
                    f"Referenced mesh files not found: {', '.join(missing_meshes[:5])}"
                    + (f" and {len(missing_meshes) - 5} more" if len(missing_meshes) > 5 else ""),
                    file_path=file_path,
                    suggestion="Ensure mesh files are in the correct relative paths",
                )

            # Check for common issues
            self._check_urdf_common_issues(root, file_path, result)

        except Exception as e:
            result.add_error("VALIDATION_ERROR", f"Error validating URDF: {e}", file_path=file_path)

    def _check_urdf_common_issues(self, root: ET.Element, file_path: str, result: ValidationResult):
        """Check for common URDF issues."""
        links = root.findall(".//link")
        joints = root.findall(".//joint")

        # Build link name set
        link_names = set()
        for link in links:
            name = link.get("name", "")
            if name in link_names:
                result.add_error(
                    "DUPLICATE_LINK",
                    f"Duplicate link name: {name}",
                    file_path=file_path,
                )
            link_names.add(name)

        # Check joints reference valid links
        for joint in joints:
            parent = joint.find("parent")
            child = joint.find("child")

            if parent is not None:
                parent_link = parent.get("link", "")
                if parent_link and parent_link not in link_names:
                    result.add_error(
                        "INVALID_PARENT_LINK",
                        f"Joint '{joint.get('name')}' references non-existent parent link '{parent_link}'",
                        file_path=file_path,
                    )

            if child is not None:
                child_link = child.get("link", "")
                if child_link and child_link not in link_names:
                    result.add_error(
                        "INVALID_CHILD_LINK",
                        f"Joint '{joint.get('name')}' references non-existent child link '{child_link}'",
                        file_path=file_path,
                    )

        # Check for visual geometry
        visual_count = len(root.findall(".//visual"))
        if visual_count == 0:
            result.add_warning(
                "NO_VISUALS",
                "URDF has no visual geometry elements",
                file_path=file_path,
                suggestion="Add <visual> elements for rendering",
            )

        result.file_info["visual_count"] = visual_count
        result.file_info["collision_count"] = len(root.findall(".//collision"))

    def _validate_sdf(self, file_path: str, result: ValidationResult):
        """Validate SDF file."""
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()

            if root.tag != "sdf":
                result.add_error(
                    "INVALID_SDF_ROOT",
                    f"Root element must be 'sdf', found '{root.tag}'",
                    file_path=file_path,
                )
                return

            # Check version
            version = root.get("version", "")
            result.file_info["sdf_version"] = version

            # Count models
            models = root.findall(".//model")
            result.file_info["model_count"] = len(models)

            if len(models) == 0:
                result.add_warning(
                    "NO_MODELS",
                    "SDF file contains no model elements",
                    file_path=file_path,
                )

        except ET.ParseError as e:
            result.add_error("XML_PARSE_ERROR", f"Invalid XML: {e}", file_path=file_path)

    def _validate_stl(self, file_path: str, result: ValidationResult):
        """Validate STL file."""
        try:
            with open(file_path, "rb") as f:
                header = f.read(80)

            # Check for ASCII STL
            try:
                header_str = header.decode("ascii").strip().lower()
                is_ascii = header_str.startswith("solid")
            except:
                is_ascii = False

            result.file_info["stl_format"] = "ascii" if is_ascii else "binary"

            # For binary STL, read triangle count
            if not is_ascii:
                with open(file_path, "rb") as f:
                    f.seek(80)
                    import struct

                    try:
                        triangle_count = struct.unpack("<I", f.read(4))[0]
                        result.file_info["triangle_count"] = triangle_count

                        if triangle_count == 0:
                            result.add_error(
                                "EMPTY_STL",
                                "STL file has no triangles",
                                file_path=file_path,
                            )
                        elif triangle_count > 5000000:
                            result.add_warning(
                                "HIGH_POLY_COUNT",
                                f"Very high polygon count ({triangle_count:,}), may be slow to process",
                                file_path=file_path,
                            )
                    except:
                        pass

        except Exception as e:
            result.add_error("STL_READ_ERROR", f"Error reading STL: {e}", file_path=file_path)

    def _validate_obj(self, file_path: str, result: ValidationResult):
        """Validate OBJ file."""
        try:
            vertex_count = 0
            face_count = 0
            has_normals = False
            has_uvs = False
            material_libs = []

            with open(file_path, "r", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("v "):
                        vertex_count += 1
                    elif line.startswith("f "):
                        face_count += 1
                    elif line.startswith("vn "):
                        has_normals = True
                    elif line.startswith("vt "):
                        has_uvs = True
                    elif line.startswith("mtllib "):
                        material_libs.append(line[7:].strip())

            result.file_info["vertex_count"] = vertex_count
            result.file_info["face_count"] = face_count
            result.file_info["has_normals"] = has_normals
            result.file_info["has_uvs"] = has_uvs
            result.file_info["material_libs"] = material_libs

            if vertex_count == 0:
                result.add_error("EMPTY_OBJ", "OBJ file has no vertices", file_path=file_path)

            if face_count == 0:
                result.add_error("NO_FACES", "OBJ file has no faces", file_path=file_path)

            # Check for MTL files
            obj_dir = Path(file_path).parent
            for mtl in material_libs:
                mtl_path = obj_dir / mtl
                if not mtl_path.exists():
                    result.add_warning(
                        "MISSING_MTL",
                        f"Material library not found: {mtl}",
                        file_path=file_path,
                    )

        except Exception as e:
            result.add_error("OBJ_READ_ERROR", f"Error reading OBJ: {e}", file_path=file_path)

    def _validate_dae(self, file_path: str, result: ValidationResult):
        """Validate COLLADA DAE file."""
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()

            # Handle namespace
            ns = {"c": "http://www.collada.org/2005/11/COLLADASchema"}

            # Remove namespace for simpler queries if needed
            tag = root.tag
            if "}" in tag:
                result.file_info["collada_version"] = root.get("version", "unknown")

            # Count geometries
            geom_count = len(
                root.findall(".//{http://www.collada.org/2005/11/COLLADASchema}geometry")
            )
            result.file_info["geometry_count"] = geom_count

            if geom_count == 0:
                result.add_warning(
                    "NO_GEOMETRY",
                    "DAE file has no geometry elements",
                    file_path=file_path,
                )

        except ET.ParseError as e:
            result.add_error("XML_PARSE_ERROR", f"Invalid XML in DAE: {e}", file_path=file_path)

    def _validate_config(self, config: Dict, result: ValidationResult):
        """Validate configuration options."""
        # Check scale factor
        scale = config.get("scale_factor", 1.0)
        if scale <= 0:
            result.add_error("INVALID_SCALE", f"Scale factor must be positive, got {scale}")
        elif scale > 1000:
            result.add_warning("LARGE_SCALE", f"Scale factor {scale} is very large")

        # Check output path
        output_path = config.get("output_path")
        if output_path:
            output_dir = Path(output_path).parent
            if not output_dir.exists():
                result.add_info(
                    "OUTPUT_DIR_CREATE",
                    f"Output directory will be created: {output_dir}",
                )


# Convenience function
def validate_file(file_path: str, config: Optional[Dict] = None) -> ValidationResult:
    """Validate a file for FTI processing."""
    validator = PreflightValidator()
    return validator.validate(file_path, config)
