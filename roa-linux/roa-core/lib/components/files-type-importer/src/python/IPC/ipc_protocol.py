#!/usr/bin/env python3
"""
ROA IPC Protocol - Request/Response Schema and Validation

This module defines the protocol for File-Based IPC between:
- ROA Linux Service (Python) - Processes conversion requests
- ROA UE5 Plugin (C++) - Submits requests, receives responses

Protocol Version: 1.0.0

Features:
- Strict JSON schema validation
- Atomic file operations (write .tmp → rename to .json)
- Request deduplication via content hash
- Timeout handling
- Error response format

Gap Fixes Implemented:
- Gap 1.1: Protocol versioning
- Gap 1.2: Schema validation  
- Gap 1.3: Atomic writes (no partial reads)
- Gap 4.1: Standardized error format
- Gap 4.2: Request-level timeouts
- Gap 4.3: Deduplication by file hash
"""

import os
import json
import hashlib
import uuid
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field, asdict, fields
from enum import Enum
import logging
import tempfile
import fcntl  # For file locking on Linux

logger = logging.getLogger(__name__)

# Protocol version - increment on breaking changes
PROTOCOL_VERSION = "1.0.0"

# Default timeout for requests (60 seconds)
DEFAULT_TIMEOUT_MS = 60000

# Maximum request age before considered stale (5 minutes)
MAX_REQUEST_AGE_SECONDS = 300


class RequestType(Enum):
    """Types of requests supported."""
    CONVERT = "convert"           # Convert URDF/XACRO/SDF to USD
    CONVERT_XACRO = "convert_xacro"  # Convert XACRO to URDF only (for UE5 plugin)
    VALIDATE = "validate"         # Validate file without conversion
    QUERY_FORMATS = "query_formats"  # Get supported formats
    HEALTH_CHECK = "health_check"    # Check service status
    CANCEL = "cancel"               # Cancel a pending request
    # Extended types for UE5 workflows (backward-compatible)
    PREPARE_FOR_UE5 = "prepare_for_ue5"      # Add assembly metadata/script to existing USD
    CONVERT_AND_PREPARE = "convert_and_prepare"  # Convert then add UE5 assembly metadata


class ResponseStatus(Enum):
    """Response status codes."""
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    INVALID_REQUEST = "invalid_request"


class ErrorCode(Enum):
    """Standardized error codes."""
    # Validation errors (1xxx)
    INVALID_JSON = "E1001"
    MISSING_FIELD = "E1002"
    INVALID_PATH = "E1003"
    UNSUPPORTED_FORMAT = "E1004"
    PROTOCOL_MISMATCH = "E1005"
    
    # File errors (2xxx)
    FILE_NOT_FOUND = "E2001"
    FILE_ACCESS_DENIED = "E2002"
    MESH_NOT_FOUND = "E2003"
    OUTPUT_WRITE_FAILED = "E2004"
    
    # Conversion errors (3xxx)
    XACRO_EXPANSION_FAILED = "E3001"
    URDF_PARSE_FAILED = "E3002"
    USD_GENERATION_FAILED = "E3003"
    MESH_LOAD_FAILED = "E3004"
    
    # System errors (4xxx)
    TIMEOUT = "E4001"
    SERVICE_BUSY = "E4002"
    INTERNAL_ERROR = "E4003"
    
    # Security errors (5xxx)
    PATH_TRAVERSAL = "E5001"
    INVALID_FILE_TYPE = "E5002"


@dataclass
class InputSpec:
    """Input file specification."""
    path: str                         # Windows or Linux path
    format: Optional[str] = None      # Force format (auto-detect if None)
    file_hash: Optional[str] = None   # SHA256 hash for deduplication
    
    def compute_hash(self) -> str:
        """Compute SHA256 hash of input file."""
        if self.file_hash:
            return self.file_hash
        
        try:
            # Normalize path for Linux access
            from Utils.path_handler import get_path_handler
            handler = get_path_handler()
            linux_path = handler.to_linux_path(self.path)
            
            sha256 = hashlib.sha256()
            with open(linux_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    sha256.update(chunk)
            self.file_hash = f"sha256:{sha256.hexdigest()}"
            return self.file_hash
        except Exception as e:
            logger.warning(f"Could not compute hash for {self.path}: {e}")
            return ""


@dataclass
class OutputSpec:
    """Output specification."""
    directory: str                    # Output directory (Windows path for UE5)
    name_prefix: str                  # Output file name prefix
    formats: List[str] = field(default_factory=lambda: ["usd", "ue5_script"])


@dataclass
class ConversionOptions:
    """Conversion options."""
    include_collision: bool = True
    include_visual: bool = True
    scale_factor: float = 1.0
    package_paths: List[str] = field(default_factory=list)
    optimize_meshes: bool = True
    generate_ue5_script: bool = True


@dataclass
class IPCRequest:
    """
    IPC Request format.
    
    This is what UE5 Plugin writes to the requests/ folder.
    """
    request_id: str
    request_type: str
    input: Dict[str, Any]
    output: Dict[str, Any]
    options: Dict[str, Any] = field(default_factory=dict)
    protocol_version: str = PROTOCOL_VERSION
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    
    @classmethod
    def create_convert_request(
        cls,
        input_path: str,
        output_directory: str,
        name_prefix: str,
        options: Optional[ConversionOptions] = None
    ) -> "IPCRequest":
        """Create a conversion request."""
        options = options or ConversionOptions()
        
        input_spec = InputSpec(path=input_path)
        input_spec.compute_hash()
        
        output_spec = OutputSpec(
            directory=output_directory,
            name_prefix=name_prefix
        )
        
        return cls(
            request_id=str(uuid.uuid4()),
            request_type=RequestType.CONVERT.value,
            input=asdict(input_spec),
            output=asdict(output_spec),
            options=asdict(options)
        )
    
    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON."""
        return json.dumps(asdict(self), indent=indent)
    
    @classmethod
    def from_json(cls, json_str: str) -> "IPCRequest":
        """Deserialize from JSON with flexible field handling."""
        data = json.loads(json_str)
        
        # Handle UE5 plugin format which sends source_file/output_dir directly
        # instead of nested input/output objects
        if 'source_file' in data and 'input' not in data:
            data['input'] = {'path': data.pop('source_file')}
        if 'output_file' in data and 'output' not in data:
            data['output'] = {'path': data.pop('output_file')}
        if 'output_dir' in data and 'output' not in data:
            data['output'] = {'directory': data.pop('output_dir')}
        elif 'output_dir' in data and 'output' in data:
            # Merge output_dir into existing output
            data['output']['directory'] = data.pop('output_dir')
        
        # Handle format field -> used by FTI for format hints
        if 'format' in data and 'input' in data:
            data['input']['format'] = data.pop('format')
        
        # Ensure input/output exist as empty dicts if missing
        if 'input' not in data:
            data['input'] = {}
        if 'output' not in data:
            data['output'] = {}
            
        # Handle 'command' field being used instead of 'request_type'
        if 'command' in data and 'request_type' not in data:
            data['request_type'] = data.pop('command')
        
        # Remove any extra fields not in dataclass
        valid_fields = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        
        return cls(**filtered_data)
    
    @property
    def data(self) -> Dict[str, Any]:
        """Return raw request data for flexible access."""
        return {
            'input': self.input,
            'output': self.output,
            'options': self.options,
        }
    
    def validate(self) -> Tuple[bool, Optional[str]]:
        """
        Validate the request.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Protocol version check
        if self.protocol_version != PROTOCOL_VERSION:
            major_request = self.protocol_version.split('.')[0]
            major_current = PROTOCOL_VERSION.split('.')[0]
            if major_request != major_current:
                return False, f"Protocol version mismatch: {self.protocol_version} vs {PROTOCOL_VERSION}"
        
        # Request ID
        if not self.request_id:
            return False, "Missing request_id"
        
        # Request type
        try:
            RequestType(self.request_type)
        except ValueError:
            return False, f"Invalid request_type: {self.request_type}"
        
        # Input validation by request type
        if self.request_type == RequestType.CONVERT.value:
            # Standard convert requires input.path and output.directory
            if not self.input or not self.input.get('path'):
                return False, "Missing input.path"
            if not self.output or not self.output.get('directory'):
                return False, "Missing output.directory"
        elif self.request_type == RequestType.CONVERT_XACRO.value:
            # XACRO to URDF conversion needs input.path, output.path is optional
            if not self.input or not self.input.get('path'):
                return False, "Missing input.path for XACRO conversion"
        elif self.request_type == RequestType.PREPARE_FOR_UE5.value:
            # Preparing existing USD only needs input.path
            if not self.input or not self.input.get('path'):
                return False, "Missing input.path"
            # output.directory is optional here
        elif self.request_type == RequestType.CONVERT_AND_PREPARE.value:
            # Convert then prepare needs both input.path and output.directory
            if not self.input or not self.input.get('path'):
                return False, "Missing input.path"
            if not self.output or not self.output.get('directory'):
                return False, "Missing output.directory"
        
        return True, None


@dataclass
class OutputFile:
    """Information about an output file."""
    linux_path: str
    windows_path: str
    size_bytes: int


@dataclass
class IPCResponse:
    """
    IPC Response format.
    
    This is what Linux service writes to the responses/ folder.
    """
    request_id: str
    success: bool
    protocol_version: str = PROTOCOL_VERSION
    completed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    duration_ms: int = 0
    status: str = ResponseStatus.SUCCESS.value
    outputs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[Dict[str, Any]] = None
    
    @classmethod
    def create_success(
        cls,
        request_id: str,
        outputs: Dict[str, Any],
        metadata: Dict[str, Any],
        duration_ms: int
    ) -> "IPCResponse":
        """Create a success response."""
        # Handle both dataclass instances and dicts in outputs
        processed_outputs = {}
        for name, of in outputs.items():
            if hasattr(of, '__dataclass_fields__'):
                # It's a dataclass, convert to dict
                processed_outputs[name] = asdict(of)
            elif isinstance(of, dict):
                # It's already a dict, use as-is
                processed_outputs[name] = of
            else:
                # Unknown type, convert to string
                processed_outputs[name] = str(of)
        
        return cls(
            request_id=request_id,
            success=True,
            status=ResponseStatus.SUCCESS.value,
            duration_ms=duration_ms,
            outputs=processed_outputs,
            metadata=metadata
        )
    
    @classmethod
    def create_error(
        cls,
        request_id: str,
        error_code: ErrorCode,
        message: str,
        details: Optional[Dict] = None,
        recoverable: bool = False,
        suggestion: Optional[str] = None
    ) -> "IPCResponse":
        """Create an error response."""
        return cls(
            request_id=request_id,
            success=False,
            status=ResponseStatus.FAILED.value,
            error={
                "code": error_code.value,
                "message": message,
                "details": details or {},
                "recoverable": recoverable,
                "suggestion": suggestion
            }
        )
    
    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON."""
        return json.dumps(asdict(self), indent=indent)
    
    @classmethod
    def from_json(cls, json_str: str) -> "IPCResponse":
        """Deserialize from JSON."""
        data = json.loads(json_str)
        return cls(**data)


@dataclass
class IPCProgress:
    """
    Progress update format.
    
    Written to progress/ folder during conversion.
    """
    request_id: str
    percent: float                    # 0.0 to 100.0
    stage: str                        # Current stage description
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON."""
        return json.dumps(asdict(self), indent=indent)


@dataclass
class ServiceStatus:
    """
    Service status/heartbeat format.
    
    Written to service.status every 5 seconds.
    """
    status: str = "running"
    pid: int = 0
    last_heartbeat: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    pending_requests: List[str] = field(default_factory=list)
    processed_count: int = 0
    failed_count: int = 0
    uptime_seconds: float = 0.0
    version: str = PROTOCOL_VERSION
    
    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON."""
        return json.dumps(asdict(self), indent=indent)
    
    @classmethod
    def from_json(cls, json_str: str) -> "ServiceStatus":
        """Deserialize from JSON."""
        data = json.loads(json_str)
        return cls(**data)


class AtomicFileWriter:
    """
    Atomic file writer - prevents partial reads.
    
    Implements: Gap 1.3 fix
    
    Usage:
        with AtomicFileWriter(path) as writer:
            writer.write(content)
        # File is now atomically visible
    """
    
    def __init__(self, target_path: str):
        self.target_path = Path(target_path)
        self.temp_path = self.target_path.with_suffix('.tmp')
        self._file = None
    
    def __enter__(self):
        # Ensure parent directory exists
        self.target_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.temp_path, 'w', encoding='utf-8')
        return self
    
    def write(self, content: str):
        """Write content to temp file."""
        self._file.write(content)
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._file.close()
        
        if exc_type is None:
            # Success - atomic rename
            shutil.move(str(self.temp_path), str(self.target_path))
            logger.debug(f"Atomically wrote: {self.target_path}")
        else:
            # Error - clean up temp file
            try:
                self.temp_path.unlink()
            except:
                pass
        
        return False  # Don't suppress exceptions


class RequestDeduplicator:
    """
    Request deduplicator - prevents duplicate processing.
    
    Implements: Gap 4.3 fix
    """
    
    def __init__(self, ttl_seconds: int = 300):
        self.ttl_seconds = ttl_seconds
        self.recent_hashes: Dict[str, Tuple[str, datetime]] = {}
    
    def check(self, request: IPCRequest) -> Tuple[bool, Optional[str]]:
        """
        Check if request is a duplicate.
        
        Returns:
            Tuple of (is_new, existing_request_id)
        """
        # Skip deduplication for non-file requests (health_check, validate, etc.)
        if request.request_type in ('health_check', 'query_formats', 'cancel'):
            return True, None  # Always process these as new
        
        # Skip if no input path (nothing to deduplicate)
        input_path = request.input.get('path', '')
        if not input_path:
            return True, None
        
        # Clean expired entries
        now = datetime.now(timezone.utc)
        self.recent_hashes = {
            h: (rid, ts) for h, (rid, ts) in self.recent_hashes.items()
            if (now - ts).total_seconds() < self.ttl_seconds
        }
        
        # Compute hash of input
        file_hash = request.input.get('file_hash', '')
        if not file_hash:
            try:
                input_spec = InputSpec(path=input_path, format=request.input.get('format'))
                file_hash = input_spec.compute_hash()
            except Exception as e:
                logger.warning(f"Could not compute file hash: {e}")
                return True, None  # Can't deduplicate, treat as new
        
        if file_hash in self.recent_hashes:
            existing_id, _ = self.recent_hashes[file_hash]
            logger.info(f"Duplicate request detected: {request.request_id} -> {existing_id}")
            return False, existing_id
        
        # Record this request
        self.recent_hashes[file_hash] = (request.request_id, now)
        return True, None
    
    def remove(self, request_id: str):
        """
        Remove a request from the deduplication cache.
        Used when a failed request should be reprocessed.
        """
        # Find and remove the hash entry for this request_id
        hash_to_remove = None
        for file_hash, (rid, _) in self.recent_hashes.items():
            if rid == request_id:
                hash_to_remove = file_hash
                break
        if hash_to_remove:
            del self.recent_hashes[hash_to_remove]
            logger.info(f"Removed {request_id} from deduplication cache")


class IPCPaths:
    """
    IPC folder structure management.
    
    Default structure:
        D:\ROA\.ipc\
        ├── requests\
        ├── responses\
        ├── progress\
        ├── errors\
        ├── service.status
        └── config.json
    """
    
    def __init__(self, base_path: str = None):
        """
        Initialize IPC paths.
        
        Args:
            base_path: Base IPC folder (Windows path)
                       Default: D:\ROA\.ipc
        """
        if base_path is None:
            # Default Windows path
            base_path = r"D:\ROA\.ipc"
        
        self.base_path_windows = base_path
        
        # Convert to Linux path for local operations
        try:
            from Utils.path_handler import get_path_handler
            handler = get_path_handler()
            self.base_path_linux = handler.to_linux_path(base_path)
        except:
            # Fallback: assume WSL mount
            if base_path.startswith('D:'):
                self.base_path_linux = '/mnt/d' + base_path[2:].replace('\\', '/')
            else:
                self.base_path_linux = base_path
        
        self._base = Path(self.base_path_linux)
    
    @property
    def requests_dir(self) -> Path:
        return self._base / "requests"
    
    @property
    def responses_dir(self) -> Path:
        return self._base / "responses"
    
    @property
    def progress_dir(self) -> Path:
        return self._base / "progress"
    
    @property
    def errors_dir(self) -> Path:
        return self._base / "errors"
    
    @property
    def service_status_file(self) -> Path:
        return self._base / "service.status"
    
    @property
    def config_file(self) -> Path:
        return self._base / "config.json"
    
    @property
    def lock_file(self) -> Path:
        return self._base / ".lock"
    
    def ensure_directories(self):
        """Create all required directories."""
        for d in [self.requests_dir, self.responses_dir, 
                  self.progress_dir, self.errors_dir]:
            d.mkdir(parents=True, exist_ok=True)
        logger.info(f"IPC directories ensured at: {self._base}")
    
    def get_request_path(self, request_id: str) -> Path:
        return self.requests_dir / f"{request_id}.request.json"
    
    def get_request_tmp_path(self, request_id: str) -> Path:
        return self.requests_dir / f"{request_id}.request.tmp"
    
    def get_ack_path(self, request_id: str) -> Path:
        return self.responses_dir / f"{request_id}.ack"
    
    def get_response_path(self, request_id: str) -> Path:
        return self.responses_dir / f"{request_id}.response.json"
    
    def get_progress_path(self, request_id: str) -> Path:
        return self.progress_dir / f"{request_id}.progress.json"
    
    def get_error_path(self, request_id: str) -> Path:
        return self.errors_dir / f"{request_id}.error.json"


def write_request(paths: IPCPaths, request: IPCRequest) -> bool:
    """
    Write a request file atomically.
    
    Args:
        paths: IPC paths configuration
        request: Request to write
        
    Returns:
        True if successful
    """
    try:
        paths.ensure_directories()
        target = paths.get_request_path(request.request_id)
        
        with AtomicFileWriter(str(target)) as writer:
            writer.write(request.to_json())
        
        logger.info(f"Wrote request: {request.request_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to write request: {e}")
        return False


def write_response(paths: IPCPaths, response: IPCResponse) -> bool:
    """
    Write a response file atomically.
    
    Args:
        paths: IPC paths configuration
        response: Response to write
        
    Returns:
        True if successful
    """
    try:
        target = paths.get_response_path(response.request_id)
        
        with AtomicFileWriter(str(target)) as writer:
            writer.write(response.to_json())
        
        logger.info(f"Wrote response: {response.request_id} (success={response.success})")
        return True
    except Exception as e:
        logger.error(f"Failed to write response: {e}")
        return False


def write_progress(paths: IPCPaths, progress: IPCProgress) -> bool:
    """
    Write a progress file atomically.
    
    Args:
        paths: IPC paths configuration
        progress: Progress update to write
        
    Returns:
        True if successful
    """
    try:
        target = paths.get_progress_path(progress.request_id)
        
        with AtomicFileWriter(str(target)) as writer:
            writer.write(progress.to_json())
        
        return True
    except Exception as e:
        logger.error(f"Failed to write progress: {e}")
        return False


def write_ack(paths: IPCPaths, request_id: str) -> bool:
    """
    Write an acknowledgement file.
    
    This tells UE5 that the request was received and is being processed.
    
    Args:
        paths: IPC paths configuration
        request_id: ID of the acknowledged request
        
    Returns:
        True if successful
    """
    try:
        ack_path = paths.get_ack_path(request_id)
        ack_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(ack_path, 'w') as f:
            f.write(datetime.now(timezone.utc).isoformat())
        
        logger.debug(f"Wrote ack: {request_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to write ack: {e}")
        return False


def read_request(paths: IPCPaths, request_id: str) -> Optional[IPCRequest]:
    """
    Read a request file.
    
    Args:
        paths: IPC paths configuration
        request_id: ID of the request to read
        
    Returns:
        IPCRequest if successful, None otherwise
    """
    try:
        request_path = paths.get_request_path(request_id)
        
        if not request_path.exists():
            return None
        
        with open(request_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return IPCRequest.from_json(content)
    except Exception as e:
        logger.error(f"Failed to read request {request_id}: {e}")
        return None


def cleanup_request(paths: IPCPaths, request_id: str):
    """
    Clean up all files associated with a request.
    
    Called after response is sent.
    """
    files_to_remove = [
        paths.get_request_path(request_id),
        paths.get_ack_path(request_id),
        paths.get_progress_path(request_id),
    ]
    
    for f in files_to_remove:
        try:
            if f.exists():
                f.unlink()
        except Exception as e:
            logger.warning(f"Could not remove {f}: {e}")


if __name__ == "__main__":
    # Test the protocol
    logging.basicConfig(level=logging.DEBUG)
    
    # Create a test request
    request = IPCRequest.create_convert_request(
        input_path=r"D:\Robots\ur3\ur3.xacro",
        output_directory=r"D:\ROA\Outputs",
        name_prefix="ur3_robot"
    )
    
    print("=== REQUEST ===")
    print(request.to_json())
    
    # Validate
    is_valid, error = request.validate()
    print(f"\nValidation: valid={is_valid}, error={error}")
    
    # Create test paths
    paths = IPCPaths()
    print(f"\nIPC Base (Linux): {paths.base_path_linux}")
    print(f"IPC Base (Windows): {paths.base_path_windows}")
    print(f"Requests dir: {paths.requests_dir}")
    
    # Create a success response
    response = IPCResponse.create_success(
        request_id=request.request_id,
        outputs={
            "parts_usd": OutputFile(
                linux_path="/mnt/d/ROA/Outputs/ur3_robot_parts.usd",
                windows_path=r"D:\ROA\Outputs\ur3_robot_parts.usd",
                size_bytes=2850000
            )
        },
        metadata={
            "robot_name": "ur3",
            "link_count": 11,
            "joint_count": 10
        },
        duration_ms=15000
    )
    
    print("\n=== RESPONSE ===")
    print(response.to_json())
    
    # Create an error response
    error_response = IPCResponse.create_error(
        request_id=request.request_id,
        error_code=ErrorCode.MESH_NOT_FOUND,
        message="Mesh file 'arm_link.stl' not found",
        recoverable=True,
        suggestion="Check that the mesh file exists at the specified path"
    )
    
    print("\n=== ERROR RESPONSE ===")
    print(error_response.to_json())
