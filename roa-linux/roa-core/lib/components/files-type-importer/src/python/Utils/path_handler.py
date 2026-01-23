"""
ROA Path Handler - Smart path detection and conversion for Windows/Linux interop

This module handles:
- Detecting if a path is Windows, WSL mount, or Linux native
- Converting paths between Windows and Linux formats
- Finding the best output path for UE5 accessibility
- Configurable output directories
- Path validation and security checks

Gap Fixes Implemented:
- Gap 5.1: Spaces in paths handling
- Gap 5.2: Unicode in paths handling
- Gap 5.3: Symlink resolution
- Gap 6.1: Path traversal protection
- Gap 6.2: File type validation

Usage:
    from Utils.path_handler import ROAPathHandler

    handler = ROAPathHandler()

    # Normalize any path to Linux format for processing
    linux_path = handler.to_linux_path("D:\\robots\\ur3.xacro")
    # Returns: /mnt/d/robots/ur3.xacro

    # Get Windows path for UE5
    windows_path = handler.to_windows_path("/mnt/d/ROA/Outputs/robot.usd")
    # Returns: D:\\ROA\\Outputs\\robot.usd

    # Validate path is safe (no traversal attacks)
    is_safe = handler.validate_path("/mnt/d/ROA/file.urdf")
"""

import logging
import os
import platform
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# Allowed file extensions for conversion
ALLOWED_EXTENSIONS: Set[str] = {
    # Robot formats
    ".urdf",
    ".xacro",
    ".sdf",
    ".mjcf",
    # USD formats
    ".usd",
    ".usda",
    ".usdc",
    ".usdz",
    # Mesh formats (for package paths)
    ".stl",
    ".obj",
    ".dae",
    ".fbx",
    ".gltf",
    ".glb",
    # Config files
    ".yaml",
    ".yml",
    ".json",
    ".xml",
}

# Dangerous path patterns to block
DANGEROUS_PATTERNS = [
    r"\.\./",  # Parent directory traversal
    r"\.\.$",  # Ends with ..
    r"^/etc/",  # System config
    r"^/proc/",  # Process info
    r"^/sys/",  # System info
    r"^/dev/",  # Devices
    r"^/boot/",  # Boot files
    r"^/root/",  # Root home
    r"/\.ssh/",  # SSH keys
    r"/\.gnupg/",  # GPG keys
]


class PathType(Enum):
    """Type of path detected."""

    WINDOWS_NATIVE = "windows_native"  # D:\folder\file.ext
    WINDOWS_UNC = "windows_unc"  # \\server\share\file.ext
    WSL_MOUNT = "wsl_mount"  # /mnt/c/folder/file.ext
    WSL_CUSTOM_MOUNT = "wsl_custom_mount"  # /home/D/folder (custom automount)
    LINUX_NATIVE = "linux_native"  # /home/user/file.ext
    UNKNOWN = "unknown"


@dataclass
class PathInfo:
    """Information about a detected path."""

    original: str
    path_type: PathType
    linux_path: str
    windows_path: Optional[str]
    drive_letter: Optional[str]
    is_accessible_from_linux: bool
    is_accessible_from_windows: bool
    is_safe: bool = True  # Security validation result
    security_issues: List[str] = field(default_factory=list)


@dataclass
class PathValidationResult:
    """Result of path validation."""

    is_valid: bool
    is_safe: bool
    normalized_path: str
    issues: List[str] = field(default_factory=list)


class ROAPathHandler:
    """
    Smart path handler for ROA that works across Windows and Linux/WSL.

    Automatically detects path types and converts between formats.
    Includes security validation to prevent path traversal attacks.
    """

    # Standard WSL mount point
    WSL_MOUNT_PREFIX = "/mnt/"

    # Custom mount patterns (like /home/D/ mapping to D:\)
    CUSTOM_MOUNT_PATTERNS = {
        "/home/D/": "D:\\",
        "/home/C/": "C:\\",
        "/home/E/": "E:\\",
    }

    # Default output directory (Windows-accessible)
    DEFAULT_OUTPUT_DIR_LINUX = "/mnt/d/ROA/Outputs"
    DEFAULT_OUTPUT_DIR_WINDOWS = "D:\\ROA\\Outputs"

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize the path handler.

        Args:
            config: Optional configuration dictionary with:
                - output_dir_linux: Linux path for outputs
                - output_dir_windows: Windows path for outputs
                - custom_mounts: Dict of custom mount point mappings
        """
        self.config = config or {}

        # Configure output directories
        self.output_dir_linux = self.config.get("output_dir_linux", self.DEFAULT_OUTPUT_DIR_LINUX)
        self.output_dir_windows = self.config.get(
            "output_dir_windows", self.DEFAULT_OUTPUT_DIR_WINDOWS
        )

        # Add any custom mount points from config
        custom_mounts = self.config.get("custom_mounts", {})
        self.custom_mounts = {**self.CUSTOM_MOUNT_PATTERNS, **custom_mounts}

        # Detect current environment
        self.is_wsl = self._detect_wsl()
        self.is_windows = platform.system() == "Windows"
        self.is_linux = platform.system() == "Linux" and not self.is_wsl

        logger.info(
            f"ROAPathHandler initialized - WSL: {self.is_wsl}, "
            f"Windows: {self.is_windows}, Linux: {self.is_linux}"
        )

    def _detect_wsl(self) -> bool:
        """Detect if running inside WSL."""
        if platform.system() != "Linux":
            return False

        # Check for WSL-specific indicators
        try:
            with open("/proc/version", "r") as f:
                version = f.read().lower()
                return "microsoft" in version or "wsl" in version
        except:
            pass

        # Check for WSL interop
        return os.path.exists("/proc/sys/fs/binfmt_misc/WSLInterop")

    def detect_path_type(self, path: str) -> PathType:
        """
        Detect the type of a given path.

        Args:
            path: The path to analyze

        Returns:
            PathType enum indicating the path type
        """
        if not path:
            return PathType.UNKNOWN

        path = path.strip()

        # Windows native path: D:\folder or D:/folder
        if re.match(r"^[A-Za-z]:[/\\]", path):
            return PathType.WINDOWS_NATIVE

        # Windows UNC path: \\server\share
        if path.startswith("\\\\") or path.startswith("//"):
            return PathType.WINDOWS_UNC

        # WSL standard mount: /mnt/c/, /mnt/d/
        if path.startswith(self.WSL_MOUNT_PREFIX):
            remainder = path[len(self.WSL_MOUNT_PREFIX) :]
            if len(remainder) >= 1 and remainder[0].isalpha():
                if len(remainder) == 1 or remainder[1] == "/":
                    return PathType.WSL_MOUNT

        # Custom mount points: /home/D/, /home/C/
        for mount_prefix in self.custom_mounts:
            if path.startswith(mount_prefix):
                return PathType.WSL_CUSTOM_MOUNT

        # Linux native path
        if path.startswith("/"):
            return PathType.LINUX_NATIVE

        return PathType.UNKNOWN

    def to_linux_path(self, path: str) -> str:
        """
        Convert any path to Linux/WSL format.

        Args:
            path: Path in any format

        Returns:
            Path in Linux format (usable from WSL/Linux)
        """
        path_type = self.detect_path_type(path)

        if path_type == PathType.WINDOWS_NATIVE:
            # D:\folder\file → /mnt/d/folder/file
            drive = path[0].lower()
            remainder = path[2:].replace("\\", "/")
            if remainder.startswith("/"):
                remainder = remainder[1:]
            return f"/mnt/{drive}/{remainder}"

        elif path_type == PathType.WINDOWS_UNC:
            # \\server\share → Not directly convertible, return as-is with warning
            logger.warning(f"UNC paths not fully supported: {path}")
            return path.replace("\\", "/")

        elif path_type in (
            PathType.WSL_MOUNT,
            PathType.WSL_CUSTOM_MOUNT,
            PathType.LINUX_NATIVE,
        ):
            # Already Linux format
            return path

        else:
            # Unknown - assume relative path, return as-is
            return path.replace("\\", "/")

    def to_windows_path(self, path: str) -> Optional[str]:
        """
        Convert a path to Windows format if possible.

        Args:
            path: Path in any format

        Returns:
            Path in Windows format, or None if not convertible
        """
        path_type = self.detect_path_type(path)

        if path_type == PathType.WINDOWS_NATIVE:
            # Already Windows format, just normalize slashes
            return path.replace("/", "\\")

        elif path_type == PathType.WINDOWS_UNC:
            return path.replace("/", "\\")

        elif path_type == PathType.WSL_MOUNT:
            # /mnt/d/folder/file → D:\folder\file
            remainder = path[len(self.WSL_MOUNT_PREFIX) :]
            if len(remainder) >= 1:
                drive = remainder[0].upper()
                rest = remainder[1:] if len(remainder) > 1 else ""
                if rest.startswith("/"):
                    rest = rest[1:]
                rest_win = rest.replace("/", "\\")
                return f"{drive}:\\{rest_win}"

        elif path_type == PathType.WSL_CUSTOM_MOUNT:
            # /home/D/folder → D:\folder
            for linux_prefix, windows_prefix in self.custom_mounts.items():
                if path.startswith(linux_prefix):
                    remainder = path[len(linux_prefix) :]
                    remainder_win = remainder.replace("/", "\\")
                    return windows_prefix + remainder_win

        elif path_type == PathType.LINUX_NATIVE:
            # Pure Linux paths are accessible via \\wsl$\distro\path
            # But this requires knowing the distro name
            distro = self._get_wsl_distro_name()
            if distro:
                path_win = path.replace("/", "\\")
                return f"\\\\wsl$\\{distro}{path_win}"
            return None

        return None

    def _get_wsl_distro_name(self) -> Optional[str]:
        """Get the current WSL distribution name."""
        try:
            # Try WSL_DISTRO_NAME environment variable
            distro = os.environ.get("WSL_DISTRO_NAME")
            if distro:
                return distro

            # Try reading from /etc/os-release
            if os.path.exists("/etc/os-release"):
                with open("/etc/os-release") as f:
                    for line in f:
                        if line.startswith("ID="):
                            return line.split("=")[1].strip().strip('"')
        except:
            pass

        return "Ubuntu"  # Default fallback

    def get_path_info(self, path: str) -> PathInfo:
        """
        Get comprehensive information about a path.

        Args:
            path: Path to analyze

        Returns:
            PathInfo dataclass with all path details
        """
        path_type = self.detect_path_type(path)
        linux_path = self.to_linux_path(path)
        windows_path = self.to_windows_path(path)

        # Extract drive letter if applicable
        drive_letter = None
        if path_type == PathType.WINDOWS_NATIVE:
            drive_letter = path[0].upper()
        elif path_type == PathType.WSL_MOUNT:
            drive_letter = path[5].upper() if len(path) > 5 else None
        elif path_type == PathType.WSL_CUSTOM_MOUNT:
            for prefix, win_prefix in self.custom_mounts.items():
                if path.startswith(prefix):
                    drive_letter = win_prefix[0]
                    break

        # Determine accessibility
        is_accessible_from_linux = path_type in (
            PathType.WSL_MOUNT,
            PathType.WSL_CUSTOM_MOUNT,
            PathType.LINUX_NATIVE,
        )
        is_accessible_from_windows = path_type in (
            PathType.WINDOWS_NATIVE,
            PathType.WINDOWS_UNC,
            PathType.WSL_MOUNT,
            PathType.WSL_CUSTOM_MOUNT,
        )

        # Security validation
        is_safe, security_issues = self.validate_path_security(linux_path)

        return PathInfo(
            original=path,
            path_type=path_type,
            linux_path=linux_path,
            windows_path=windows_path,
            drive_letter=drive_letter,
            is_accessible_from_linux=is_accessible_from_linux,
            is_accessible_from_windows=is_accessible_from_windows,
            is_safe=is_safe,
            security_issues=security_issues,
        )

    def validate_path_security(self, path: str) -> Tuple[bool, List[str]]:
        """
        Validate path for security issues.

        Implements: Gap 6.1 fix - path traversal protection

        Args:
            path: Path to validate (should be Linux format)

        Returns:
            Tuple of (is_safe, list_of_issues)
        """
        issues = []

        # Ensure UTF-8 encoding (Gap 5.2 fix)
        if isinstance(path, bytes):
            try:
                path = path.decode("utf-8")
            except UnicodeDecodeError:
                issues.append("Invalid UTF-8 encoding in path")
                return False, issues

        # Check for dangerous patterns
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, path):
                issues.append(f"Dangerous pattern detected: {pattern}")

        # Resolve symlinks and check for traversal (Gap 5.3 fix)
        try:
            # First check if path exists for symlink resolution
            if os.path.exists(path):
                real_path = os.path.realpath(path)
                if real_path != os.path.abspath(path):
                    logger.debug(f"Symlink resolved: {path} -> {real_path}")
                # Re-check dangerous patterns on resolved path
                for pattern in DANGEROUS_PATTERNS:
                    if re.search(pattern, real_path):
                        issues.append(f"Symlink resolves to dangerous location: {real_path}")
        except Exception as e:
            logger.warning(f"Could not resolve path {path}: {e}")

        # Check for null bytes (security issue)
        if "\x00" in path:
            issues.append("Null byte in path")

        return len(issues) == 0, issues

    def validate_file_extension(self, path: str) -> Tuple[bool, Optional[str]]:
        """
        Validate that file has an allowed extension.

        Implements: Gap 6.2 fix - file type validation

        Args:
            path: Path to file

        Returns:
            Tuple of (is_allowed, extension)
        """
        ext = Path(path).suffix.lower()

        if not ext:
            return False, None

        return ext in ALLOWED_EXTENSIONS, ext

    def validate_path(
        self,
        path: str,
        allowed_roots: Optional[List[str]] = None,
        check_extension: bool = True,
    ) -> PathValidationResult:
        """
        Comprehensive path validation.

        Args:
            path: Path to validate
            allowed_roots: Optional list of allowed root directories
            check_extension: Whether to validate file extension

        Returns:
            PathValidationResult with validation details
        """
        issues = []

        # Convert to Linux path for validation
        linux_path = self.to_linux_path(path)

        # Security check
        is_safe, security_issues = self.validate_path_security(linux_path)
        issues.extend(security_issues)

        # Root directory check
        if allowed_roots:
            try:
                if os.path.exists(linux_path):
                    real_path = os.path.realpath(linux_path)
                else:
                    real_path = os.path.abspath(linux_path)

                in_allowed_root = any(
                    real_path.startswith(os.path.realpath(root))
                    for root in allowed_roots
                    if os.path.exists(root)
                )

                if not in_allowed_root:
                    issues.append(f"Path not in allowed roots: {allowed_roots}")
                    is_safe = False
            except Exception as e:
                issues.append(f"Could not validate root: {e}")

        # Extension check
        if check_extension:
            is_allowed_ext, ext = self.validate_file_extension(linux_path)
            if not is_allowed_ext:
                issues.append(f"Extension not allowed: {ext}")

        # Normalize the path (resolve . and ..)
        try:
            normalized = os.path.normpath(linux_path)
        except:
            normalized = linux_path

        return PathValidationResult(
            is_valid=len(issues) == 0,
            is_safe=is_safe,
            normalized_path=normalized,
            issues=issues,
        )

    def safe_path(self, path: str) -> str:
        """
        Get a safe, normalized version of the path.

        Resolves symlinks, normalizes, and validates.

        Args:
            path: Input path

        Returns:
            Safe normalized path

        Raises:
            ValueError: If path is not safe
        """
        validation = self.validate_path(path, check_extension=False)

        if not validation.is_safe:
            raise ValueError(f"Unsafe path: {validation.issues}")

        return validation.normalized_path

    def get_output_path(self, input_path: str, output_filename: str) -> Tuple[str, str]:
        """
        Get the appropriate output path for a converted file.

        Returns paths accessible from both Linux (for saving) and Windows (for UE5).

        Args:
            input_path: Original input file path
            output_filename: Desired output filename

        Returns:
            Tuple of (linux_output_path, windows_output_path)
        """
        # Ensure output directory exists (Linux side)
        os.makedirs(self.output_dir_linux, exist_ok=True)

        linux_output = os.path.join(self.output_dir_linux, output_filename)
        windows_output = self.to_windows_path(linux_output)

        if windows_output is None:
            windows_output = os.path.join(self.output_dir_windows, output_filename)

        return linux_output, windows_output

    def ensure_linux_accessible(self, path: str) -> str:
        """
        Ensure a path is accessible from Linux/WSL.

        For Windows paths, converts to WSL mount format.

        Args:
            path: Any path format

        Returns:
            Linux-accessible path
        """
        return self.to_linux_path(path)

    def ensure_windows_accessible(self, path: str) -> Optional[str]:
        """
        Ensure a path is accessible from Windows.

        For Linux-native paths, may return \\\\wsl$ path.

        Args:
            path: Any path format

        Returns:
            Windows-accessible path, or None if not possible
        """
        return self.to_windows_path(path)


# Singleton instance for easy access
_default_handler: Optional[ROAPathHandler] = None


def get_path_handler(config: Optional[Dict] = None) -> ROAPathHandler:
    """Get or create the default path handler instance."""
    global _default_handler
    if _default_handler is None or config is not None:
        _default_handler = ROAPathHandler(config)
    return _default_handler


# Convenience functions
def to_linux(path: str) -> str:
    """Convert any path to Linux format."""
    return get_path_handler().to_linux_path(path)


def to_windows(path: str) -> Optional[str]:
    """Convert any path to Windows format."""
    return get_path_handler().to_windows_path(path)


def detect_type(path: str) -> PathType:
    """Detect the type of a path."""
    return get_path_handler().detect_path_type(path)


def get_output_paths(input_path: str, output_filename: str) -> Tuple[str, str]:
    """Get Linux and Windows output paths."""
    return get_path_handler().get_output_path(input_path, output_filename)
