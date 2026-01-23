# UE5 Robot Import Workflows

## Overview

The FTI (File Type Importer) plugin supports two workflow scenarios for importing robots into UE5:

1. **Manual Import**: User converts robot files externally, then imports the assembled USD into UE5
2. **Direct Convert**: User triggers conversion directly from the UE5 plugin

Both workflows result in:
- Individual mesh parts imported to `/Game/Robots/{robot_name}/Meshes/`
- Assembled robot actor with proper hierarchy
- Optional Blueprint generation
- Physics constraints configured

---

## Scenario 1: Manual Import Workflow

**Use this when:** You've already converted a URDF/XACRO using the FTI GUI or IPC service outside of UE5.

### Step-by-Step

1. **Convert the Robot** (outside UE5)
   ```
   D:\ROA\output-tests\ur3\
   ├── meshes/
   │   ├── base_link.usd
   │   ├── shoulder_link.usd
   │   ├── upper_arm_link.usd
   │   └── ...
   ├── ur3_assembled.usd          ← Main USD with hierarchy metadata
   └── ur3_ue5_hierarchy.py       ← Companion assembly script
   ```

2. **Import in UE5**
   - Go to: `File → Import into Level...` OR use the FTI panel
   - Browse to: `ur3_assembled.usd`
   - The plugin will:
     - Detect this is an ROA-generated USD (via `customData.export_source`)
     - Auto-find `ur3_ue5_hierarchy.py` in the same folder
     - Import all meshes from `meshes/` subfolder
     - Execute the hierarchy assembly script
     - Create assembled actor in level

3. **Alternative: Python Console**
   ```python
   # In UE5 Python console:
   import ue5_import_workflow as fti
   
   result = fti.import_robot(r"D:\ROA\output-tests\ur3_assembled.usd")
   
   if result.success:
       print(f"Imported {result.robot_name} with {result.mesh_count} meshes")
       print(f"Content folder: {result.content_folder}")
   ```

### Plugin Detection Logic

When you select an assembled USD file, the plugin:

1. Opens the USD and reads `customData` from root prim
2. Checks `export_source == "ROA_URDF_Converter"`
3. Extracts `robot_name`, `hierarchy`, `link_count`, `joint_count`
4. Searches same folder for `{robot_name}_ue5_hierarchy.py`
5. Searches `meshes/` subfolder for individual link USDs

---

## Scenario 2: Direct Convert Workflow

**Use this when:** You want one-click conversion + import from within UE5.

### Step-by-Step

1. **Open FTI Panel**
   - `Window → ROA → FTI Import Panel`

2. **Select Source File**
   - Browse to your URDF/XACRO file: `D:\Robots\ur3.urdf`

3. **Configure Options**
   - ✅ Auto-assemble hierarchy
   - ✅ Generate Blueprint
   - Output format: USD
   - Content path: `/Game/Robots`

4. **Click "Convert & Import"**
   - Plugin sends request to FTI IPC service (WSL)
   - Progress updates appear in the panel
   - When complete:
     - Meshes imported to `/Game/Robots/ur3/Meshes/`
     - Assembled USD imported
     - Hierarchy script executed
     - Blueprint generated at `/Game/Robots/ur3/BP_ur3`

### Behind the Scenes

```
┌──────────────────┐     IPC Request      ┌─────────────────────┐
│   UE5 Plugin     │ ─────────────────────► │   FTI Service      │
│   (Windows)      │                        │   (WSL Linux)      │
└──────────────────┘                        └─────────────────────┘
        │                                            │
        │                                            ▼
        │                                   ┌─────────────────────┐
        │                                   │  URDF → USD         │
        │                                   │  Generate meshes    │
        │                                   │  Embed metadata     │
        │                                   │  Create .py script  │
        │                                   └─────────────────────┘
        │                                            │
        │     IPC Response (output_file path)        │
        │ ◄──────────────────────────────────────────┘
        ▼
┌──────────────────┐
│  Import USD      │
│  Run hierarchy   │
│  Generate BP     │
└──────────────────┘
```

### Alternative: Python Console

```python
# In UE5 Python console:
import ue5_import_workflow as fti

result = fti.convert_robot(
    r"D:\Robots\ur3.urdf",
    auto_assemble=True,
    generate_blueprint=True,
    content_path="/Game/Robots"
)

if result.success:
    print(f"Robot {result.robot_name} ready!")
    print(f"Blueprint: {result.blueprint_path}")
```

---

## Output Structure

After import, your content browser will have:

```
/Game/Robots/ur3/
├── Meshes/
│   ├── base_link          (StaticMesh)
│   ├── shoulder_link      (StaticMesh)
│   ├── upper_arm_link     (StaticMesh)
│   ├── forearm_link       (StaticMesh)
│   ├── wrist_1_link       (StaticMesh)
│   ├── wrist_2_link       (StaticMesh)
│   └── wrist_3_link       (StaticMesh)
├── ur3_assembled          (Level Sequence or Actor)
└── BP_ur3                 (Blueprint)
```

---

## Hierarchy Assembly Details

The hierarchy assembly process:

1. **Find actors by name** - Matches imported mesh actors to URDF link names
2. **Apply parent-child relationships** - Attaches child links to parent links
3. **Set transforms** - Applies joint origin transforms (position + rotation)
4. **Configure joints** - Creates PhysicsConstraint components for each joint

### Transform Conversions

| URDF | UE5 |
|------|-----|
| Meters | Centimeters (×100) |
| Radians | Degrees |
| Roll, Pitch, Yaw | Pitch, Yaw, Roll (reordered) |
| Right-handed | Left-handed (Y-axis flip) |

---

## Configuration

### FTI Import Config

```python
@dataclass
class RobotImportConfig:
    content_path: str = "/Game/Robots"    # Base content folder
    auto_assemble: bool = True            # Run hierarchy assembly
    generate_blueprint: bool = True       # Create Blueprint
    setup_physics: bool = True            # Configure constraints
    setup_collision: bool = True          # Apply collision
    import_materials: bool = True         # Apply materials
    scale_factor: float = 100.0           # Meters → Centimeters
```

### UE5 Project Settings

For automatic PostImport assembly, add to your project's Python startup:

```python
# {Project}/Content/Python/init_unreal.py
import sys
sys.path.append(r"C:\ROA\lib\python\UE5")

# Register PostImport hook
from ue5_import_workflow import UE5ImportWorkflow
```

---

## Troubleshooting

### "Hierarchy script not found"

- Ensure the `.py` file is in the same folder as the assembled USD
- File must be named `{robot_name}_ue5_hierarchy.py`

### "Actors not found for assembly"

- Import the individual meshes first
- Check actor names match URDF link names (with underscore sanitization)

### "FTI IPC service not running"

- Start the service: `python roa_ipc_service.py --start`
- Check the IPC folder exists: `D:\ROA\.ipc`

### "Python plugin not available"

- Enable: Edit → Plugins → Python Editor Script Plugin
- Restart UE5

---

## Python Module API

### Quick Import

```python
import ue5_import_workflow as fti

# Scenario 1: Import pre-converted USD
result = fti.import_robot(r"D:\output\robot_assembled.usd")

# Scenario 2: Convert + import
result = fti.convert_robot(r"D:\source\robot.urdf")
```

### Full Control

```python
from ue5_import_workflow import UE5ImportWorkflow, RobotImportConfig

config = RobotImportConfig(
    content_path="/Game/MyRobots",
    auto_assemble=True,
    generate_blueprint=True,
    setup_physics=True
)

workflow = UE5ImportWorkflow(config)
result = workflow.import_from_assembled_usd(r"D:\output\robot_assembled.usd")

print(f"Success: {result.success}")
print(f"Meshes: {result.mesh_count}")
print(f"Links: {result.link_count}")
print(f"Joints: {result.joint_count}")
print(f"Content: {result.content_folder}")
print(f"Blueprint: {result.blueprint_path}")
```

---

## Related Files

| File | Purpose |
|------|---------|
| `ue5_import_workflow.py` | Main import workflow manager |
| `ue5_hierarchy_assembler.py` | Hierarchy assembly logic |
| `SFTIImportPanel.cpp` | C++ UE5 panel widget |
| `FTIPostImportHook.cpp` | Interchange PostImport integration |
| `urdf_converter.py` | URDF→USD converter with metadata embedding |
