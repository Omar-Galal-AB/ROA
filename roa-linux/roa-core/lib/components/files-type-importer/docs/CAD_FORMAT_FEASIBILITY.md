# CAD Format Support - Feasibility Analysis

## Executive Summary

**CAD support is FEASIBLE** but requires accepting performance and complexity trade-offs.

Since ROA users won't use CAD formats frequently (mainly URDF/USD), we can implement it as:
- **Optional heavy dependency** (only installed when needed)
- **Slower conversion** (acceptable for infrequent use)
- **One-time setup complexity** (worth it for single-platform workflow)

## Implementation Strategy

### Approach: Optional pythonocc-core Dependency

```python
# In FTI, check if CAD support is available
try:
    from OCC.Core.STEPControl import STEPControl_Reader
    from OCC.Core.IGESControl import IGESControl_Reader
    from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
    from OCC.Extend.TopologyUtils import TopologyExplorer
    CAD_SUPPORT = True
except ImportError:
    CAD_SUPPORT = False
    print("CAD formats not available. Install: pip install pythonocc-core")
```

### Installation Steps (One-time)

#### For Users Who Need CAD Support:

**Option 1: Conda (Recommended - Easiest)**
```bash
# pythonocc-core is available via conda-forge
conda install -c conda-forge pythonocc-core
# Size: ~200MB
# Time: 2-5 minutes
```

**Option 2: Pre-built Wheels (Linux/Windows)**
```bash
# Pre-compiled binaries available
pip install pythonocc-core
# Size: ~150MB
# Time: 1-3 minutes
```

**Option 3: Docker Container**
```dockerfile
FROM python:3.10
RUN conda install -c conda-forge pythonocc-core
COPY fti /app/fti
# Ship pre-configured container for CAD users
```

### Conversion Performance

| File Size | Parts | Conversion Time | Acceptable? |
|-----------|-------|-----------------|-------------|
| 5 MB STEP | 10 parts | 5-10 seconds | ✅ Yes - infrequent use |
| 50 MB STEP | 100 parts | 30-60 seconds | ✅ Yes - worth the wait |
| 500 MB STEP | 1000 parts | 5-10 minutes | ⚠️ Slow but usable |

**Key insight**: Since CAD isn't the primary format, users will tolerate slower conversion.

### Implementation Code

```python
# cad_converter.py - New converter class

from pathlib import Path
from typing import Optional
from .base_converter import BaseConverter, ConversionResult

class CADConverter(BaseConverter):
    """
    Converter for CAD formats (STEP, IGES) using pythonocc-core.
    
    OPTIONAL DEPENDENCY - Only loads if pythonocc-core is installed.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        super().__init__(config)
        
        # Check if CAD support is available
        try:
            from OCC.Core.STEPControl import STEPControl_Reader
            self.step_available = True
        except ImportError:
            self.step_available = False
            
        try:
            from OCC.Core.IGESControl import IGESControl_Reader
            self.iges_available = True
        except ImportError:
            self.iges_available = False
        
        self.supported_extensions = []
        if self.step_available:
            self.supported_extensions.extend(['.step', '.stp'])
        if self.iges_available:
            self.supported_extensions.extend(['.iges', '.igs'])
        
        # Tessellation parameters (user-configurable for speed/quality trade-off)
        self.tessellation_quality = config.get('tessellation_quality', 'medium')
        
        # Quality presets
        self.quality_params = {
            'fast': {'linear_deflection': 0.5, 'angular_deflection': 0.5},    # 2x faster
            'medium': {'linear_deflection': 0.1, 'angular_deflection': 0.3},  # Balanced
            'high': {'linear_deflection': 0.01, 'angular_deflection': 0.1},   # 5x slower
        }
    
    def convert(self, input_path: str, output_path: str, robot_name: str) -> ConversionResult:
        """Convert CAD file to USD."""
        
        if not self.step_available and not self.iges_available:
            return ConversionResult(
                success=False,
                error_message=(
                    "CAD support not installed. Run: pip install pythonocc-core\n"
                    "Or use conda: conda install -c conda-forge pythonocc-core"
                )
            )
        
        file_ext = Path(input_path).suffix.lower()
        
        if file_ext in ['.step', '.stp']:
            return self._convert_step(input_path, output_path, robot_name)
        elif file_ext in ['.iges', '.igs']:
            return self._convert_iges(input_path, output_path, robot_name)
    
    def _convert_step(self, input_path: str, output_path: str, robot_name: str):
        """Convert STEP file to USD."""
        from OCC.Core.STEPControl import STEPControl_Reader
        from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
        from OCC.Extend.TopologyUtils import TopologyExplorer
        from OCC.Core.TopoDS import TopoDS_Shape
        
        print(f"[CAD] Loading STEP file: {input_path}")
        print(f"[CAD] This may take 10-60 seconds for large files...")
        
        # Read STEP file
        reader = STEPControl_Reader()
        status = reader.ReadFile(input_path)
        
        if status != 1:  # IFSelect_RetDone
            return ConversionResult(
                success=False,
                error_message=f"Failed to read STEP file: {input_path}"
            )
        
        # Transfer to OpenCASCADE shape
        reader.TransferRoots()
        shape = reader.OneShape()
        
        # Tessellate (convert NURBS surfaces to triangle mesh)
        params = self.quality_params[self.tessellation_quality]
        print(f"[CAD] Tessellating with quality={self.tessellation_quality}...")
        
        mesh_tool = BRepMesh_IncrementalMesh(
            shape, 
            params['linear_deflection'],
            False,  # Relative
            params['angular_deflection'],
            True    # InParallel for speed
        )
        mesh_tool.Perform()
        
        # Extract triangle mesh from all faces
        explorer = TopologyExplorer(shape)
        
        # Create USD stage
        from pxr import Usd, UsdGeom
        stage = Usd.Stage.CreateNew(output_path)
        root_prim = stage.DefinePrim(f'/{robot_name}', 'Xform')
        stage.SetDefaultPrim(root_prim)
        
        part_count = 0
        for face in explorer.faces():
            location = face.Location()
            mesh_data = self._face_to_trimesh(face)
            
            if mesh_data:
                # Create USD mesh for this part
                mesh_path = root_prim.GetPath().AppendChild(f'Part_{part_count}')
                usd_mesh = UsdGeom.Mesh.Define(stage, mesh_path)
                
                # Set mesh data
                usd_mesh.GetPointsAttr().Set(mesh_data['vertices'])
                usd_mesh.GetFaceVertexCountsAttr().Set(mesh_data['face_counts'])
                usd_mesh.GetFaceVertexIndicesAttr().Set(mesh_data['indices'])
                
                part_count += 1
        
        stage.Save()
        print(f"[CAD] Conversion complete: {part_count} parts exported")
        
        return ConversionResult(
            success=True,
            output_path=output_path,
            format='usd',
            parts=[f'Part_{i}' for i in range(part_count)],
            warnings=[
                f"Tessellation quality: {self.tessellation_quality}",
                f"Total parts: {part_count}",
                "No physics or joints (CAD files don't contain kinematic info)"
            ]
        )
    
    def _face_to_trimesh(self, face):
        """Convert OCC face to trimesh-compatible format."""
        from OCC.Core.BRep import BRep_Tool
        
        location = face.Location()
        triangulation = BRep_Tool.Triangulation(face, location)
        
        if triangulation is None:
            return None
        
        # Extract vertices and triangles
        vertices = []
        for i in range(1, triangulation.NbNodes() + 1):
            pnt = triangulation.Node(i)
            vertices.append([pnt.X(), pnt.Y(), pnt.Z()])
        
        indices = []
        face_counts = []
        for i in range(1, triangulation.NbTriangles() + 1):
            tri = triangulation.Triangle(i)
            n1, n2, n3 = tri.Get()
            indices.extend([n1-1, n2-1, n3-1])  # 0-based indexing
            face_counts.append(3)
        
        return {
            'vertices': vertices,
            'indices': indices,
            'face_counts': face_counts
        }
    
    def _convert_iges(self, input_path: str, output_path: str, robot_name: str):
        """Convert IGES - similar to STEP."""
        # Implementation similar to STEP
        pass
```

### Integration into FTI

```python
# In file_type_importer.py

def get_converter_for_file(self, file_path: str):
    """Get appropriate converter based on file extension."""
    ext = Path(file_path).suffix.lower()
    
    # ... existing converters ...
    
    # Try CAD converter (if available)
    if ext in ['.step', '.stp', '.iges', '.igs']:
        from .Converters.cad_converter import CADConverter
        converter = CADConverter(self.config)
        
        if not converter.step_available and not converter.iges_available:
            raise ImportError(
                f"CAD format {ext} requires pythonocc-core.\n"
                "Install with: pip install pythonocc-core\n"
                "Or use conda: conda install -c conda-forge pythonocc-core"
            )
        
        return converter
```

## Limitations & Considerations

### What CAD Files DON'T Have

❌ **No Kinematics** - CAD is pure geometry, no joints or physics
- Users must manually define joints in UE5
- Or provide companion URDF file

❌ **No Materials** - Colors only, no PBR textures
- Surface colors are exported
- No roughness, metallic, etc.

❌ **No Assembly Hierarchy** - Often flattened
- STEP preserves some hierarchy
- IGES usually doesn't

### When to Use CAD Import

✅ **Static Environment Models** - Buildings, furniture, terrain
✅ **Visual-only Robots** - No simulation, just visualization
✅ **One-time Conversion** - Convert to USD, save, never touch CAD again

### Performance Tuning

Users can configure quality vs speed:

```yaml
# fti_config.yaml
cad:
  tessellation_quality: fast    # Options: fast, medium, high
  max_file_size_mb: 100          # Warn if larger
  timeout_seconds: 300           # Abort if takes too long
```

## Cost-Benefit Analysis

| Aspect | Cost | Benefit |
|--------|------|---------|
| **Development** | 3-5 days | One-time investment |
| **Installation** | 200MB disk, 5min setup | Users who need CAD get it |
| **Runtime** | 10-60s per file | Acceptable for infrequent use |
| **Maintenance** | Low (stable API) | pythonocc-core is mature |

## Recommendation

✅ **IMPLEMENT CAD SUPPORT** as optional feature:

1. Keep it separate (cad_converter.py)
2. Make pythonocc-core optional dependency
3. Show clear error message if not installed
4. Document installation in README
5. Add tessellation quality presets

**Rationale**: Since ROA development accepts complexity for capability, and CAD usage is infrequent, the trade-off is acceptable.

## Action Items

- [ ] Create CADConverter class with pythonocc-core
- [ ] Add conda environment file with CAD support
- [ ] Document installation in README
- [ ] Add quality presets (fast/medium/high)
- [ ] Add timeout protection for huge files
- [ ] Test with sample STEP files (robot chassis, etc.)
