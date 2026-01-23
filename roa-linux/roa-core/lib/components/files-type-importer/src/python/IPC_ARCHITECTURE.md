# ROA File-Based IPC Architecture

## Overview

This document describes the File-Based IPC architecture for communication between:
- **ROA Linux Service** (Python) - Runs in WSL/Linux, converts URDF/XACRO to USD
- **ROA UE5 Plugin** (C++) - Runs in Windows/UE5, submits requests, imports results

## Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│                          UE5 (Windows)                                      │
│  ┌─────────────────────┐         ┌────────────────────────────────────┐    │
│  │   ROA UE5 Plugin    │         │         UE5 Import Pipeline        │    │
│  │                     │         │                                    │    │
│  │  ┌───────────────┐  │         │  ┌──────────────────────────────┐  │    │
│  │  │  IPC Client   │  │         │  │   Interchange (USD Import)   │  │    │
│  │  │  (C++/Python) │──┼─────────┼──│                              │  │    │
│  │  └───────────────┘  │         │  └──────────────────────────────┘  │    │
│  │         │           │         │              │                      │    │
│  │         │ submit    │         │              │ import              │    │
│  │         │ request   │         │              │                      │    │
│  │         ▼           │         │              ▼                      │    │
│  │  ┌───────────────┐  │         │  ┌──────────────────────────────┐  │    │
│  │  │ Progress/     │  │         │  │   Hierarchy Assembler        │  │    │
│  │  │ Response      │  │         │  │   (Python - PostImport)      │  │    │
│  │  │ Monitor       │  │         │  └──────────────────────────────┘  │    │
│  │  └───────────────┘  │         │                                    │    │
│  └─────────────────────┘         └────────────────────────────────────┘    │
│              │                                                              │
└──────────────┼──────────────────────────────────────────────────────────────┘
               │
               │  File-Based IPC
               │  D:\ROA\.ipc\
               │
┌──────────────┼──────────────────────────────────────────────────────────────┐
│              │                                                              │
│              ▼                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    D:\ROA\.ipc\ (Shared Folder)                      │   │
│  │                                                                       │   │
│  │  requests/              responses/           progress/                │   │
│  │  ├── {uuid}.request.tmp ├── {uuid}.ack       ├── {uuid}.progress.json│   │
│  │  └── {uuid}.request.json└── {uuid}.response.json                     │   │
│  │                                                                       │   │
│  │  service.status         config.json          .lock                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│              │                                                              │
│              │  Polling (not inotify - doesn't work on /mnt/*)             │
│              ▼                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     ROA Linux Service                                │   │
│  │                                                                       │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────┐  │   │
│  │  │  Request    │  │  Converter  │  │  FileTypeImporter           │  │   │
│  │  │  Processor  │──│  Dispatcher │──│  (URDF/XACRO → USD)         │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────────┘  │   │
│  │         │                                                            │   │
│  │         │ heartbeat                                                  │   │
│  │         ▼                                                            │   │
│  │  ┌─────────────┐                                                     │   │
│  │  │  Heartbeat  │                                                     │   │
│  │  │  Writer     │                                                     │   │
│  │  └─────────────┘                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│                          WSL/Linux                                           │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Protocol Version

**Current Version: 1.0.0**

All requests and responses include `protocol_version` field for compatibility checking.

## Folder Structure

```
D:\ROA\.ipc\
├── requests/                  # UE5 → Linux: conversion requests
│   ├── {uuid}.request.tmp     # Temp file during write (ignored)
│   └── {uuid}.request.json    # Complete request (atomic rename)
├── responses/                 # Linux → UE5: conversion results
│   ├── {uuid}.ack             # Immediate acknowledgement
│   └── {uuid}.response.json   # Final result
├── progress/                  # Linux → UE5: progress updates
│   └── {uuid}.progress.json   # Real-time progress
├── service.status             # Service heartbeat (updated every 5s)
├── config.json                # User configuration
└── .lock                      # Service singleton lock
```

## Request Format

```json
{
  "protocol_version": "1.0.0",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "request_type": "convert",
  "created_at": "2026-01-05T14:30:00.000Z",
  "timeout_ms": 60000,
  "input": {
    "path": "D:\\Robots\\ur3.xacro",
    "format": "xacro",
    "file_hash": "sha256:abc123..."
  },
  "output": {
    "directory": "D:\\ROA\\Outputs",
    "name_prefix": "ur3_robot",
    "formats": ["usd", "ue5_script"]
  },
  "options": {
    "include_collision": true,
    "include_visual": true,
    "scale_factor": 1.0,
    "package_paths": ["D:\\ros_packages\\ur_description"]
  }
}
```

## Response Format

### Success Response
```json
{
  "protocol_version": "1.0.0",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": true,
  "status": "success",
  "completed_at": "2026-01-05T14:30:15.000Z",
  "duration_ms": 15000,
  "outputs": {
    "parts_usd": {
      "linux_path": "/mnt/d/ROA/Outputs/ur3_robot_parts.usd",
      "windows_path": "D:\\ROA\\Outputs\\ur3_robot_parts.usd",
      "size_bytes": 2850000
    },
    "assembled_usd": {
      "linux_path": "/mnt/d/ROA/Outputs/ur3_robot_assembled.usd",
      "windows_path": "D:\\ROA\\Outputs\\ur3_robot_assembled.usd",
      "size_bytes": 2850000
    },
    "ue5_script": {
      "linux_path": "/mnt/d/ROA/Outputs/ur3_robot_ue5_rebuild_hierarchy.py",
      "windows_path": "D:\\ROA\\Outputs\\ur3_robot_ue5_rebuild_hierarchy.py",
      "size_bytes": 5700
    }
  },
  "metadata": {
    "robot_name": "ur3",
    "link_count": 11,
    "joint_count": 10,
    "mesh_count": 8,
    "warnings": []
  }
}
```

### Error Response
```json
{
  "protocol_version": "1.0.0",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": false,
  "status": "failed",
  "completed_at": "2026-01-05T14:30:05.000Z",
  "error": {
    "code": "E2003",
    "message": "Mesh file 'arm_link.stl' not found",
    "recoverable": true,
    "suggestion": "Check that the mesh file exists at the specified path"
  }
}
```

## Service Status (Heartbeat)

```json
{
  "status": "running",
  "pid": 12345,
  "last_heartbeat": "2026-01-05T14:30:05Z",
  "pending_requests": ["uuid1", "uuid2"],
  "processed_count": 42,
  "failed_count": 2,
  "uptime_seconds": 3600.0,
  "version": "1.0.0"
}
```

## Gap Fixes Implemented

| Gap ID | Category | Issue | Solution |
|--------|----------|-------|----------|
| 1.1 | Protocol | No versioning | Added `protocol_version` to all messages |
| 1.2 | Protocol | No validation | Added JSON schema validation |
| 1.3 | Protocol | Partial file reads | Atomic write: `.tmp` → rename |
| 1.4 | Protocol | No acknowledgement | Two-phase: `.ack` then `.response` |
| 2.1 | File Watching | inotify fails on /mnt/* | Uses polling instead |
| 2.2 | File Watching | Poll interval trade-off | Adaptive polling (fast→slow) |
| 3.1 | Service | No auto-start | `wsl -e` launch from UE5 |
| 3.2 | Service | Orphan requests | Graceful shutdown, pending list |
| 3.3 | Service | Stale heartbeat | 5-second heartbeat updates |
| 4.1 | Errors | No error format | Standardized error codes |
| 4.2 | Errors | No timeouts | Request-level timeout |
| 4.3 | Errors | Duplicate requests | Hash-based deduplication |
| 5.1 | Paths | Spaces in paths | Always quote paths |
| 5.2 | Paths | Unicode paths | Force UTF-8 encoding |
| 5.3 | Paths | Symlink issues | Resolve to real path |
| 6.1 | Security | Path traversal | Pattern validation |
| 6.2 | Security | Invalid file types | Extension whitelist |
| 8.1 | UE5 | No Interchange pipeline | Plugin auto-creates |
| 8.2 | UE5 | Manual script run | PostImport hook |
| 8.3 | UE5 | No progress UI | Progress file monitoring |

## Files Created

```
/home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python/
├── IPC/
│   ├── __init__.py          # Module exports
│   ├── ipc_protocol.py      # Request/Response schemas
│   └── ipc_client.py        # Client library
├── UE5/
│   ├── __init__.py          # Module exports
│   └── ue5_hierarchy_assembler.py  # Hierarchy reconstruction
├── Utils/
│   └── path_handler.py      # Path handling with security (updated)
├── roa_ipc_service.py       # Main service
├── service_manager.py       # Service lifecycle
└── tests/
    └── test_ipc_integration.py  # Integration tests
```

## Usage

### Starting the Service (Linux)

```bash
# Direct start
python3 roa_ipc_service.py

# With custom IPC path
python3 roa_ipc_service.py --ipc-path "D:\MyROA\.ipc"

# As daemon with auto-restart
python3 service_manager.py daemon
```

### Starting from Windows (PowerShell)

```powershell
# Manual start via WSL
wsl -e python3 /path/to/roa_ipc_service.py

# Or use generated script
.\start_roa_service.ps1
```

### Using from UE5 Python

```python
from IPC import UE5IPCClient

# Create client (auto-starts service if needed)
client = UE5IPCClient()

# Convert a robot
response = client.convert_and_wait(
    input_path=r"D:\Robots\ur3.xacro",
    output_directory=r"D:\ROA\Outputs",
    name_prefix="ur3_robot"
)

if response.success:
    # Get paths
    paths = client.get_usd_paths(response.outputs)
    print(f"USD: {paths['assembled_usd']}")
```

### Hierarchy Assembly (UE5)

```python
from UE5 import assemble_from_usd_path

# After USD import completes
assemble_from_usd_path(r"D:\ROA\Outputs\ur3_robot_assembled.usd")
```

## Testing

```bash
cd /home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python
PYTHONPATH="$PWD" python3 tests/test_ipc_integration.py
```

## Error Codes

| Code | Name | Description |
|------|------|-------------|
| E1001 | INVALID_JSON | Request is not valid JSON |
| E1002 | MISSING_FIELD | Required field missing |
| E1003 | INVALID_PATH | Path validation failed |
| E1004 | UNSUPPORTED_FORMAT | File format not supported |
| E1005 | PROTOCOL_MISMATCH | Protocol version incompatible |
| E2001 | FILE_NOT_FOUND | Input file not found |
| E2002 | FILE_ACCESS_DENIED | Cannot read file |
| E2003 | MESH_NOT_FOUND | Referenced mesh not found |
| E2004 | OUTPUT_WRITE_FAILED | Cannot write output |
| E3001 | XACRO_EXPANSION_FAILED | XACRO processing failed |
| E3002 | URDF_PARSE_FAILED | URDF parsing failed |
| E3003 | USD_GENERATION_FAILED | USD generation failed |
| E3004 | MESH_LOAD_FAILED | Mesh loading failed |
| E4001 | TIMEOUT | Request timed out |
| E4002 | SERVICE_BUSY | Service overloaded |
| E4003 | INTERNAL_ERROR | Unexpected error |
| E5001 | PATH_TRAVERSAL | Security: path traversal |
| E5002 | INVALID_FILE_TYPE | Security: invalid extension |
