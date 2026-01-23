# ROA XACRO Remote Processing Architecture

## Overview

This document describes the XACRO remote processing system that allows UE5 on Windows to convert XACRO files using the ROS2 xacro package available on Linux/WSL.

## Problem Statement

The error you encountered:
```
Error: XACRO processing failed
Details: substitution args not supported: No module named 'ament_index_python'
```

This occurs because:
1. **Windows has limited ROS2 packages** - `ament_index_python` is a ROS2 dependency
2. **XACRO requires ROS2 infrastructure** - The `xacro` package needs ROS2's parameter substitution
3. **Remote processing was not configured** - The bridge between UE5 and Linux wasn't established

## Solution Architecture

```
┌─────────────────────────────────────┐
│  Windows (UE5 Plugin)               │
│  ┌─────────────────────────────────┐│
│  │ 1. User imports .xacro file     ││
│  │ 2. Plugin detects XACRO format  ││
│  │ 3. Sends to Linux via TCP:9876  ││
│  │ 4. Receives progress updates    ││
│  │ 5. Gets converted URDF/USD back ││
│  └─────────────────────────────────┘│
└───────────────┬─────────────────────┘
                │ TCP (JSON + newline)
                ▼
┌─────────────────────────────────────┐
│  Linux/WSL (ROA Backend)            │
│  ┌─────────────────────────────────┐│
│  │ roa_command_server.py :9876     ││
│  │   ├─ convert_xacro_file         ││
│  │   ├─ convert_xacro (content)    ││
│  │   ├─ upload_xacro (chunked)     ││
│  │   └─ get_fti_status             ││
│  └───────────────┬─────────────────┘│
│                  │                   │
│  ┌───────────────▼─────────────────┐│
│  │ xacro_processor.py              ││
│  │   ├─ Python xacro module ✓      ││
│  │   ├─ ros2 run xacro xacro ✓     ││
│  │   └─ subprocess xacro ✓         ││
│  └───────────────┬─────────────────┘│
│                  │                   │
│  ┌───────────────▼─────────────────┐│
│  │ urdf_converter.py               ││
│  │   └─ Converts URDF → USD        ││
│  └─────────────────────────────────┘│
└─────────────────────────────────────┘
```

## New Components Created

### 1. xacro_processor.py
**Location:** `lib/components/files-type-importer/src/python/xacro_processor.py`

Features:
- **3 backends** for XACRO expansion:
  1. Python `xacro` module (fastest, preferred)
  2. `ros2 run xacro xacro` command
  3. Standalone `xacro` subprocess
- **Progress callbacks** for UI updates
- **Automatic include resolution** (changes to input file directory)
- **XACRO argument support** (`key:=value` mappings)

Usage:
```python
from xacro_processor import XacroProcessor

processor = XacroProcessor()
success, message, urdf_path = processor.process(
    '/path/to/robot.xacro',
    '/path/to/output.urdf',
    xacro_args={'robot_name': 'ur5'}
)
```

### 2. XACRO Commands in roa_command_server.py
**Location:** `lib/roa_command_server.py`

New command handlers:

#### `convert_xacro_file`
For files already on Linux:
```json
{
    "type": "convert_xacro_file",
    "input_path": "/path/to/robot.xacro",
    "output_path": "/path/to/robot.urdf",
    "xacro_args": {"arg1": "value1"}
}
```

#### `convert_xacro`
For embedded content (Windows → Linux):
```json
{
    "type": "convert_xacro",
    "robot_name": "ur5",
    "xacro_content": "<base64-encoded XACRO XML>",
    "xacro_args": {}
}
```

#### `upload_xacro`
For large files (chunked upload):
```json
// Step 1: Start session
{"type": "upload_xacro", "action": "start", "robot_name": "ur5", "total_size": 12345}

// Step 2: Send chunks
{"type": "upload_xacro", "action": "chunk", "session_id": "xxx", "data": "<base64>", "index": 0}

// Step 3: Complete
{"type": "upload_xacro", "action": "complete", "session_id": "xxx"}
```

#### `get_fti_status`
Check FTI availability:
```json
{"type": "get_fti_status"}

// Response:
{
    "status": "success",
    "fti": {
        "available": true,
        "xacro_processor": true,
        "supported_formats": ["urdf", "xacro", "stl", "obj", "dae"],
        "output_formats": ["urdf", "usd"],
        "active_sessions": 0
    }
}
```

### 3. FTI-Webthread Bridge
**Location:** `lib/components/files-type-importer/src/python/fti_webthread_bridge.py`

Features:
- **Heartbeat mechanism** (500ms interval)
- **Component registration** with Webthread
- **Conversion progress streaming**
- **Status updates** (idle, converting, error)
- **Auto-reconnection** on connection loss

Usage:
```python
from fti_webthread_bridge import FTIWithBridge

fti = FTIWithBridge({'webthread_host': 'localhost', 'webthread_port': 9876})
fti.start()

# Convert with progress reporting
success, msg, path = fti.convert_xacro('/path/to/robot.xacro')

# Full pipeline: XACRO → URDF → USD
success, msg, usd_path = fti.convert_xacro_to_usd(
    '/path/to/robot.xacro',
    '/path/to/output.usda',
    'robot_name'
)
```

### 4. URDF Converter XACRO Support
**Location:** `lib/components/files-type-importer/src/python/Converters/urdf_converter.py`

The URDF converter now:
1. **Detects XACRO files** by extension or content (`<xacro:`, `${`, etc.)
2. **Auto-expands XACRO** before parsing
3. **Converts to USD** with full hierarchy and physics

```python
from Converters.urdf_converter import URDFConverter

converter = URDFConverter()
# Works with both .urdf and .xacro files!
result = converter.convert('/path/to/robot.xacro', '/path/to/output.usda', 'robot')
```

## Protocol for UE5 Plugin Integration

### Sending XACRO for Conversion

```cpp
// 1. Check FTI availability
SendCommand("{\"type\": \"get_fti_status\"}");

// 2. Convert file (if on shared filesystem)
SendCommand("{\"type\": \"convert_xacro_file\", \"input_path\": \"/path/to/robot.xacro\"}");

// 3. Or send content
FString XacroContent = ReadFile(XacroPath);
FString Base64Content = FBase64::Encode(XacroContent);
SendCommand(FString::Printf(TEXT(
    "{\"type\": \"convert_xacro\", \"robot_name\": \"%s\", \"xacro_content\": \"%s\"}"
), *RobotName, *Base64Content));
```

### Receiving Progress Updates

```cpp
void OnMessageReceived(const FString& Message)
{
    TSharedPtr<FJsonObject> Json;
    if (FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Message), Json))
    {
        FString Status = Json->GetStringField("status");
        
        if (Status == "progress")
        {
            float Progress = Json->GetNumberField("progress");
            FString Msg = Json->GetStringField("message");
            UpdateProgressBar(Progress, Msg);
        }
        else if (Status == "success")
        {
            FString URDFContent = FBase64::Decode(Json->GetStringField("urdf_content"));
            ProcessURDF(URDFContent);
        }
        else if (Status == "error")
        {
            ShowError(Json->GetStringField("message"));
        }
    }
}
```

## Testing

### Test XACRO Processor
```bash
cd /home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python
python3 xacro_processor.py /path/to/robot.xacro /path/to/output.urdf
```

### Test Command Server
```bash
# Start server
cd /home/myws/roa/roa_linux/roa-core/lib
python3 roa_command_server.py --port 9876

# In another terminal, test commands
echo '{"type": "get_fti_status"}' | nc localhost 9876
echo '{"type": "convert_xacro_file", "input_path": "/tmp/test.xacro"}' | nc localhost 9876
```

### Test Full Pipeline
```bash
cd /home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python
python3 -c "
from Converters.urdf_converter import URDFConverter
conv = URDFConverter()
result = conv.convert('/tmp/test.xacro', '/tmp/test.usda', 'test_robot')
print(f'Success: {result.success}')
"
```

## What the UE5 Plugin Needs

The Windows-side UE5 plugin needs to:

1. **Try local conversion first** (if xacro is available locally)
2. **Fall back to remote** via TCP:9876 to Linux/WSL
3. **Handle progress updates** from the `progress` status messages
4. **Display errors** from `error` status messages
5. **Decode base64 results** for `urdf_content` field

The error dialog you showed should be updated to show:
- Current conversion backend being tried
- Progress bar during conversion
- Actual error details from Linux

## Files Changed

| File | Change |
|------|--------|
| `roa_command_server.py` | Added XACRO conversion commands |
| `xacro_processor.py` | NEW - XACRO expansion with 3 backends |
| `fti_webthread_bridge.py` | NEW - FTI ↔ Webthread connection |
| `urdf_converter.py` | Added auto-XACRO detection and expansion |

## Status: ✅ COMPLETE

All components are implemented and tested:
- ✅ XACRO processor with Python xacro module
- ✅ Command server accepts XACRO commands
- ✅ Progress streaming implemented
- ✅ URDF converter auto-expands XACRO
- ✅ Full XACRO → URDF → USD pipeline works
