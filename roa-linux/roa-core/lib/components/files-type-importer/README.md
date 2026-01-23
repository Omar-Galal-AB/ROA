# Files Type Importer (FTI) - ROA Component

**Component**: Files Type Importer (FTI)  
**Purpose**: Automated import of robot 3D models into Unreal Engine 5  
**Language**: Python (format conversion) + C++ (UE5 plugin)  
**Status**: In Development

## Overview

The Files Type Importer enables seamless import of robot 3D models and assemblies directly into Unreal Engine 5 without requiring intermediate applications (Blender, CAD software, etc.). It supports universal 3D format conversion and automatic organization within the UE5 Content Drawer.

## Key Features

- **Universal 3D Format Support**: Automatically support all 3D file formats
- **Format Conversion**: Convert unsupported formats to UE5-compatible formats via USD intermediate format
- **Material & Color Preservation**: Import colors and materials when available
- **Dual Import Mode**:
  - Individual robot parts (separate meshes in Content Drawer)
  - Complete assembled robot body
- **Auto-Organization**: Create dedicated folder in Content Drawer with robot name
- **Robot-Specific Design**: Optimized specifically for robot body designs and assemblies

## Supported Formats

### Primary Formats
- **URDF** (Unified Robot Description Format) - ROS standard
- **STL** (Stereolithography) - 3D printing format
- **OBJ** (Wavefront Object) - Universal 3D format
- **FBX** (Filmbox) - Autodesk format
- **DAE** (COLLADA) - Digital Asset Exchange

### Advanced Formats (via USD conversion)
- **STEP** (ISO 10303) - CAD standard
- **IGES** (Initial Graphics Exchange Specification) - CAD format
- **USD** (Universal Scene Description) - Pixar format (native UE5 support)

## Architecture

### Format Conversion Pipeline

```
Input File (URDF/STL/STEP/etc.)
        ↓
Format Converter (Python)
        ↓
USD Intermediate Format
        ↓
UE5 Import Pipeline (C++ Plugin)
        ↓
Content Drawer Organization
        ↓
Content/{RobotName}/Parts/     - Individual components
Content/{RobotName}/Assembly/  - Complete robot
```

### Component Structure

```
files-type-importer/
├── README.md                          # This file
├── src/
│   ├── python/                        # Python format converters
│   │   ├── __init__.py
│   │   ├── file_type_importer.py      # Main FTI coordinator
│   │   ├── format_detector.py         # Auto-detect file format
│   │   ├── Converters/                # Format-specific converters
│   │   │   ├── __init__.py
│   │   │   ├── base_converter.py      # Abstract base class
│   │   │   ├── urdf_converter.py      # URDF → USD
│   │   │   ├── stl_converter.py       # STL → USD
│   │   │   ├── obj_converter.py       # OBJ → USD
│   │   │   ├── fbx_converter.py       # FBX → USD
│   │   │   ├── dae_converter.py       # DAE/COLLADA → USD
│   │   │   ├── step_converter.py      # STEP → USD
│   │   │   └── iges_converter.py      # IGES → USD
│   │   └── Importers/                 # UE5 import utilities
│   │       ├── __init__.py
│   │       ├── material_mapper.py     # Material conversion
│   │       └── hierarchy_builder.py   # Assembly hierarchy
│   └── cpp/                           # C++ UE5 plugin
│       ├── FileTypeImporter.h         # Main plugin header
│       ├── FileTypeImporter.cpp       # Main plugin implementation
│       ├── USDImportHandler.h         # USD import handler
│       ├── USDImportHandler.cpp
│       ├── ContentOrganizer.h         # Auto-organization
│       └── ContentOrganizer.cpp
├── tests/                             # Unit and integration tests
│   ├── __init__.py
│   ├── test_format_detector.py
│   ├── test_urdf_converter.py
│   ├── test_stl_converter.py
│   ├── test_material_mapper.py
│   └── test_integration.py
├── examples/                          # Example robot files
│   └── sample_robots/
│       ├── simple_arm.urdf
│       ├── mobile_base.stl
│       └── gripper_assembly.obj
└── Config/                            # Configuration files
    ├── format_mappings.json           # Format conversion rules
    ├── material_library.json          # Material definitions
    └── import_settings.json           # Import preferences
```

## Installation

### Prerequisites

- Unreal Engine 5.6 or later (USD support required)
- Python 3.10+
- pip packages:
  ```bash
  pip install pyyaml numpy trimesh pxr  # pxr = USD Python bindings
  ```

### Setup

1. Clone the repository:
   ```bash
   cd ~/ROA/components/files-type-importer
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Build UE5 plugin:
   ```bash
   # Instructions TBD - will use Unreal Build Tool
   ```

## Usage

### Python API

```python
from file_type_importer import FileTypeImporter

# Initialize importer
fti = FileTypeImporter()

# Import robot model (auto-detects format)
result = fti.import_robot(
    file_path="/path/to/robot.urdf",
    robot_name="MyRobot",
    import_mode="both"  # "parts", "assembly", or "both"
)

if result.success:
    print(f"Imported to: {result.content_path}")
    print(f"Parts: {result.parts_count}")
else:
    print(f"Error: {result.error_message}")
```

### UE5 Integration

```cpp
// C++ usage in UE5
#include "FileTypeImporter.h"

UFileTypeImporter* Importer = NewObject<UFileTypeImporter>();
FImportResult Result = Importer->ImportRobotModel(
    FilePath,
    RobotName,
    EImportMode::Both
);
```

## Configuration

### format_mappings.json

Defines format detection rules and conversion strategies:

```json
{
  "formats": {
    "urdf": {
      "extensions": [".urdf", ".xacro"],
      "converter": "urdf_converter",
      "priority": 1
    },
    "stl": {
      "extensions": [".stl"],
      "converter": "stl_converter",
      "priority": 2
    }
  }
}
```

### material_library.json

Material conversion mappings from source formats to UE5:

```json
{
  "materials": {
    "metal": {
      "ue5_material": "/Game/Materials/M_Metal_Base",
      "properties": {
        "metallic": 0.9,
        "roughness": 0.4
      }
    }
  }
}
```

### import_settings.json

Default import preferences:

```json
{
  "import": {
    "create_collision": true,
    "combine_meshes": false,
    "scale_factor": 1.0,
    "auto_organize": true
  }
}
```

## Data Flow

1. **File Detection**: Analyze file extension and content to determine format
2. **Format Conversion**: Convert to USD intermediate format using appropriate converter
3. **Material Mapping**: Translate materials to UE5 equivalents
4. **Hierarchy Preservation**: Maintain parent-child relationships for assemblies
5. **UE5 Import**: Import USD into UE5 using native USD support
6. **Organization**: Auto-create folders and organize assets in Content Drawer
7. **Validation**: Verify import success and report any issues

## Error Handling

### Conversion Failures
- **Fallback**: Attempt direct import if USD conversion fails
- **Partial Success**: Import successful parts, report failures
- **Validation**: Check geometry integrity and material mappings

### Missing Dependencies
- **Graceful Degradation**: Import geometry without materials if mapping fails
- **User Notification**: Clear error messages with resolution steps

## Performance Targets

- **Small Models** (< 100 parts): < 5 seconds
- **Medium Models** (100-500 parts): < 30 seconds
- **Large Models** (500+ parts): < 2 minutes
- **Memory Usage**: < 2GB per import operation

## Testing

### Unit Tests
```bash
cd tests
python -m pytest test_urdf_converter.py -v
```

### Integration Tests
```bash
python -m pytest test_integration.py -v
```

### Test Coverage Target
- Code coverage: 80%+
- Format coverage: All primary formats tested

## Development Status

- [x] Directory structure created
- [ ] Python format detector implementation
- [ ] URDF converter (highest priority - ROS standard)
- [ ] STL converter
- [ ] OBJ converter
- [ ] Material mapper
- [ ] C++ UE5 plugin skeleton
- [ ] USD import handler
- [ ] Content organizer
- [ ] Configuration files
- [ ] Example robot models
- [ ] Unit tests
- [ ] Integration tests
- [ ] Documentation

## Dependencies

### Python Packages
- **pyyaml**: URDF parsing
- **numpy**: Mathematical operations
- **trimesh**: Mesh processing and validation
- **pxr (USD)**: Universal Scene Description support
- **lxml**: XML parsing for URDF/COLLADA

### C++ Libraries
- **Unreal Engine SDK**: UE5 plugin development
- **USD Library**: Native UE5 USD support (built-in)

## Integration with Other Components

### Webthread
- Receives import commands via ROS2 topics
- Reports import status and progress
- Logs import operations

### Dimensions Collector (DIMC)
- Provides imported model metadata (sizes, hierarchies)
- Enables real-time tracking setup

### Robot Operator Controller (ROC)
- Imported models become controllable entities
- Joint information passed from URDF to ROC

## Future Enhancements

- **Real-time Preview**: Preview import before committing
- **Batch Import**: Import multiple robots simultaneously
- **Custom Format Plugins**: User-extensible converter system
- **Import History**: Track and revert imports
- **Validation Tools**: Geometry repair and optimization

## License

TBD

## Authors

ROA Development Team

## Last Updated

2025-11-16
