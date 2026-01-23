# ROA Project - AI Agent Instructions

## Project Overview

ROA (Robot Operator Assistant) bridges **ROS2/Gazebo simulation** with **Unreal Engine 5** for real-time robot control in construction scenarios. **Cross-platform architecture**: WSL2/Linux (services) ↔ Windows (UE5 runtime).

**Tech Stack**: Python 3.10+ (ROS2) + C++ (UE5 plugins) | Ubuntu 22.04 (WSL2), UE5 5.6+, ROS2 Humble LTS

## Critical Path Knowledge

### ❌ NEVER Access (Archived/Unused)
- `/home/D/ROA/Storage_NOT USED/` - Old backups and deprecated implementations
- `/home/myws/roa/Storage_NOT_USED/` - Archived ROA V1 designs

### ✅ Active Development Paths
| Component | Path | Purpose |
|-----------|------|---------|
| **FTI Core** | `roa_linux/roa-core/lib/components/files-type-importer/src/python/` | URDF→USD converter, IPC service |
| **UE5 Python** | `UE5_Projects/ROA_V1/Content/Python/ROA/` | Import workflow, physics setup |
| **UE5 Plugin** | `UE5_Projects/ROA_V1/Plugins/ROA_PlugIn/Source/ROA/` | C++ network server, actors |
| **IPC Shared** | `/mnt/d/ROA/.ipc/` (Linux) / `D:\ROA\.ipc\` (Windows) | File-based IPC channel |
| **Components** | `roa_linux/roa-core/lib/components/{fti,dimc,roc,comc,webthread}/` | 5 microservices |

## Architecture (Microservices)

```
┌────────────────────────────────────────────────┐
│         WEBTHREAD (Central Coordinator)        │
│    ROS2 ↔ UE5 Bridge + Health Monitoring      │
└──────────┬─────────────┬──────────┬────────────┘
           ↓             ↓          ↓            ↓
      ┌───────┐     ┌───────┐  ┌──────┐    ┌──────┐
      │  FTI  │     │ DIMC  │  │ ROC  │    │ COMC │
      │3D Imp │     │Spatial│  │Ctrl  │    │Multi │
      │  ✅   │     │  📋   │  │ 📋   │    │ 📋   │
      └───────┘     └───────┘  └──────┘    └──────┘
```

**Component Status**:
- **FTI** (Files Type Importer): ✅ Production (30 tests passing, 80%+ coverage)
- **DIMC** (Dimensions Collector): 📋 Planned (spatial tracking, obstacle detection)
- **ROC** (Robot Controller): 📋 Planned (dual-mode control: RPM manual + ADM strategic)
- **COMC** (Communication Center): 📋 Planned (multi-robot coordination)
- **Webthread**: 🔄 Partial (structure created, integration layer needs completion)

## File-Based IPC (WSL ↔ Windows Bridge)

**Critical Design**: inotify doesn't work on `/mnt/*` NTFS mounts, so we use **adaptive file-polling** instead.

### IPC Structure
```
D:\ROA\.ipc\               (Windows) or /mnt/d/ROA/.ipc/ (WSL)
├── requests/              UE5 → Linux: {uuid}.request.json
├── responses/             Linux → UE5: {uuid}.response.json
├── progress/              Real-time progress updates
└── service.status         Heartbeat file (updated every 5s)
```

### Atomic Write Pattern (CRITICAL)
```python
# Always write via .tmp → rename for atomic completion
with open(f"{path}.tmp", 'w') as f:
    json.dump(data, f)
os.rename(f"{path}.tmp", path)  # Atomic on same filesystem
```

**Polling Strategy**: Adaptive (100ms when active requests, 1s when idle)  
**Protocol**: JSON with `protocol_version: "1.0.0"` field  
**Docs**: `files-type-importer/src/python/IPC_ARCHITECTURE.md`

## FTI Pipeline (Complete Implementation)

**Purpose**: Convert robot URDF/XACRO → USD with physics → Import to UE5

### Python API (Linux Side)
```python
from Converters.urdf_converter import URDFConverter
converter = URDFConverter()
result = converter.convert(input_path, output_path, robot_name)
# Returns: ConversionResult(success, output_path, hierarchy, metadata)
```

### Output Files
- `{robot}_assembled.usd` - Single USD with full robot + physics schema
- `{robot}_hierarchy.json` - Part tree structure for assembly
- `{robot}_ue5_rebuild_hierarchy.py` - UE5 post-import script

### USD Physics Schema Applied
```python
# FTI embeds these schemas in assembled USD:
UsdPhysics.Scene              # Gravity -980 cm/s², Z-up
UsdPhysics.RevoluteJoint      # Rotational joints
UsdPhysics.PrismaticJoint     # Linear joints
UsdPhysics.DriveAPI           # Motor: stiffness, damping, maxForce
PhysicsCollisionAPI           # Collision meshes
FilteredPairsAPI              # Self-collision exclusions
```

## UE5 Integration (Windows Side)

### GUI Entry Points
File menu (Editor > File > ROA FTI Import):
- `fti_import_usd()` - Import pre-converted assembled USD
- `fti_convert_urdf()` - Trigger conversion via IPC, then import

### Key Python Modules (`Content/Python/ROA/`)
| Module | Purpose |
|--------|---------|
| `ue5_import_workflow.py` | Orchestrates full import (scenarios: MANUAL_IMPORT, DIRECT_CONVERT) |
| `physics_constraint_setup.py` | Parses USD physics prims → UE5 PhysicsConstraintActors |
| `ue5_hierarchy_assembler.py` | Post-import: build actor hierarchy, attach constraints |
| `editor_menu.py` | Registers File menu actions |

### UE5 Import Pipeline Selection
**MUST USE**: "Default USD Pipeline for Asset Import (InterchangeUsdPipeline)"  
**AVOID**: `InterchangeGenericAssetsPipeline` - strips UsdPhysics metadata!

## Dual-Port Network Architecture (Firewall Workaround)

**Problem**: Windows Firewall blocks WSL → Windows inbound connections  
**Solution**: Two-port system (command + response channels)

```bash
# WSL Terminal: Start socat relays
WINDOWS_IP=$(ip route show | grep default | awk '{print $3}')

# Port 9876: Commands (WSL → Windows)
socat TCP-LISTEN:9876,fork,reuseaddr TCP:$WINDOWS_IP:9876 &

# Port 9877: Responses (Windows → WSL, future)
socat TCP-LISTEN:9877,fork,reuseaddr TCP:127.0.0.1:9877 &
```

**UE5 C++ Plugin** (`ROA_PlugIn/Source/ROA/Private/ROANetworkServer.cpp`):
- Listens on port 9876 for commands
- Parses JSON-line protocol: `{"command": "connect|spawn|status"}\n`
- See `DUAL_PORT_ARCHITECTURE.md` for full flow

## Development Workflows

### Build & Start Services
```bash
# 1. Install ROA (one-time setup)
cd /home/myws/roa/roa_linux
sudo ./install.sh  # Creates /opt/roa, symlinks to /usr/local/bin/roa

# 2. Start FTI IPC service (manual)
python roa-core/lib/components/files-type-importer/src/python/roa_ipc_service.py

# 3. Launch main GUI (after install)
roa  # Future: launches NiceGUI dashboard
```

### Testing Strategy
```bash
# FTI unit tests (30 tests, 80%+ coverage target)
cd roa_linux/roa-core/lib/components/files-type-importer
python -m pytest tests/ -v
python -m pytest tests/test_urdf_converter.py -v -k test_ur30

# Integration tests
python /home/D/ROA/output-tests/test_fti_pipeline.py  # End-to-end URDF→USD

# UE5 connection diagnostic
cd /home/myws/roa/roa_linux/roa-core/lib/components/webthread
python3 -m src.python.UE5Bridge.connection_monitor  # Expects UE5 running
```

### UE5 Plugin Rebuild (Windows PowerShell)
```powershell
cd D:\ROA\UE5_Projects\ROA_V1
powershell -ExecutionPolicy Bypass -File .\rebuild_plugin.ps1
# Wait for "BUILD COMPLETE" before launching UE5
```

## Component Development Standards

### Three-Way Validation Framework (Apply to ALL features)
1. **Code Validation** - Syntax, imports, type hints, function signatures
2. **Data Flow Validation** - Stage-by-stage transformations, schema compliance (especially USD)
3. **Integration Validation** - Entry points wired, GUI accessible, end-to-end test

### New Component Checklist (DIMC, ROC, COMC pattern)
Follow FTI structure:
```
components/{component_name}/
├── README.md                      # Component overview, API docs
├── src/python/
│   ├── {component}_main.py        # Primary logic
│   ├── {component}_ros2_node.py   # ROS2 integration
│   └── Config/                    # JSON configs
├── tests/
│   ├── test_{component}.py        # Unit tests (target 80%+)
│   └── test_{component}_integration.py
└── INTEGRATION_GUIDE.md           # ROS2 topics, services, dependencies
```

**ROS2 Integration**:
- Topic: `/roa/{component}/status` (std_msgs/String, JSON payload)
- Service: `/roa/{component}/check_status` (returns health, uptime)
- Message example: `{"status": "running", "uptime": 123.45, "errors": []}`

**Webthread Coordination**: Components register with Webthread on startup (Phase 3 sequence)

## ROS2 Conventions

**Naming**:
- Topics: `/roa/<component>/<topic>` (e.g., `/roa/fti/conversion_complete`)
- Services: `/roa/<component>/<service>` (e.g., `/roa/dimc/get_dimensions`)
- Nodes: `roa_<component>_node`

**Message Format**: `std_msgs/String` with JSON payload (not custom .msg for MVP speed)

## Key Design Decisions (WHY, not just WHAT)

1. **USD as intermediate format** - Native UE5 Interchange support, preserves physics schema (UsdPhysics), avoids Datasmith limitations
2. **File-polling over inotify** - WSL2 `/mnt/*` NTFS mounts don't propagate inotify events across kernel boundary
3. **5-strategy actor discovery** - UE5 import mangles names unpredictably (e.g., `base_link` → `base_link1`, `SM_base_link`), so try: exact, suffix, prefix, contains, fuzzy
4. **Dual control modes** - RPM (Role Playing Mode, direct joystick) for manual fine-tuning + ADM (Auto Driven Mode, RTS-style) for strategic task queuing
5. **Collision sensors on ALL parts** - Not just gripper; every robot component tracks obstacles for comprehensive safety
6. **Adaptive controller UI** - All robot part types pre-coded (arms, grippers, mobile bases, etc.), dynamically show/hide based on URDF joint analysis

## Essential Documentation Map

**Start Here**:
- `roa_linux/docs/AI_CONTEXT.md` - 500 lines, comprehensive system guide
- `roa_linux/docs/ARCHITECTURE.md` - Component deep-dives, integration flows
- `.github/copilot-instructions.md` - This file (keep updated!)

**Deep Dives**:
- `files-type-importer/src/python/IPC_ARCHITECTURE.md` - File-based IPC protocol spec
- `roa_linux/docs/DESIGN_DECISIONS.md` - Why certain approaches were chosen
- `DUAL_PORT_ARCHITECTURE.md` - Network firewall bypass solution
- `QUICK_START_AFTER_REBUILD.md` - Step-by-step startup for testing

**Session Context**:
- `roa/AI-Assistant-History-Chat/` - Recent development sessions, debugging notes

## Universal Robot Examples

Test data: `universal_robot-Examples/` and `universal_robot-noetic-devel/`
- UR series: UR3, UR5, UR10, UR30 (industrial arms)
- Includes URDF + XACRO + MoveIt configs
- Use `ur30_moveit_config/` for FTI testing (complex 6-DOF arm)
