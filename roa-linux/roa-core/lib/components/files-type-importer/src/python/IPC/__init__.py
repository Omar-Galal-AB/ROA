"""
ROA IPC Module - File-Based Inter-Process Communication

This module provides reliable IPC between:
- ROA Linux Service (Python) - Converts URDF/XACRO to USD
- ROA UE5 Plugin (C++) - Submits requests, imports results

Architecture:
    Uses file-based IPC over a shared folder (e.g., D:\ROA\.ipc)
    accessible from both Windows and WSL.

Protocol Version: 1.0.0

Components:
- ipc_protocol: Request/Response schemas and atomic file operations
- ipc_client: Client library for submitting requests
- ipc_service: Linux service that processes requests

Gap Fixes Implemented:
- Polling-based file watching (inotify doesn't work on /mnt/*)
- Atomic writes via .tmp → rename pattern
- Request acknowledgement and deduplication
- Heartbeat-based health monitoring
- Timeout handling
- Security validation
"""

from .ipc_client import ROAIPCClient, ServiceInfo, UE5IPCClient
from .ipc_protocol import (  # Version; Enums; Data classes; Path management; Utilities
    PROTOCOL_VERSION,
    AtomicFileWriter,
    ConversionOptions,
    ErrorCode,
    InputSpec,
    IPCPaths,
    IPCProgress,
    IPCRequest,
    IPCResponse,
    OutputFile,
    OutputSpec,
    RequestDeduplicator,
    RequestType,
    ResponseStatus,
    ServiceStatus,
    cleanup_request,
    read_request,
    write_ack,
    write_progress,
    write_request,
    write_response,
)

__all__ = [
    # Version
    "PROTOCOL_VERSION",
    # Enums
    "RequestType",
    "ResponseStatus",
    "ErrorCode",
    # Data classes
    "IPCRequest",
    "IPCResponse",
    "IPCProgress",
    "ServiceStatus",
    "OutputFile",
    "InputSpec",
    "OutputSpec",
    "ConversionOptions",
    # Path management
    "IPCPaths",
    # Utilities
    "AtomicFileWriter",
    "RequestDeduplicator",
    "write_request",
    "write_response",
    "write_progress",
    "write_ack",
    "read_request",
    "cleanup_request",
    # Client
    "ROAIPCClient",
    "UE5IPCClient",
    "ServiceInfo",
]
