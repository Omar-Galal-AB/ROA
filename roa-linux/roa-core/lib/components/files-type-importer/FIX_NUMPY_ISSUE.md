# NumPy Binary Incompatibility Issue - SOLUTION

## Problem
```
numpy.dtype size changed, may indicate binary incompatibility. 
Expected 96 from C header, got 88 from PyObject
```

This error occurs when:
1. NumPy 2.x is installed
2. Other packages (scipy, trimesh) were compiled against NumPy 1.x
3. Binary extensions (C/Cython code) can't load due to ABI mismatch

## Root Cause
The system has:
- **NumPy 2.2.6** (detected in error messages)
- **SciPy** compiled for NumPy 1.x (requires 1.17.3-1.25.0)
- **Trimesh** dependencies using incompatible numpy

## SOLUTION 1: Use NumPy 1.x (Recommended)

### Quick Fix
```bash
# Downgrade to NumPy 1.x
pip install --force-reinstall 'numpy<2.0' 'scipy<1.12'

# Verify
python3 -c "import numpy; print(numpy.__version__)"  # Should show 1.26.x
python3 -c "import scipy; print('scipy OK')"
python3 -c "import trimesh; print('trimesh OK')"
```

### Clean Virtual Environment (Best Practice)
```bash
# Create new venv
cd /home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer
python3 -m venv venv_fti
source venv_fti/bin/activate

# Install compatible stack
pip install --upgrade pip
pip install 'numpy<2.0' 'scipy<1.12' trimesh
pip install usd-core  # or build USD from source

# Install other dependencies
pip install PyQt6 lxml pyyaml

# Test
python -c "import numpy, scipy, trimesh; print('All OK')"
```

## SOLUTION 2: Upgrade Everything to NumPy 2.x

```bash
# This requires rebuilding all binary extensions
pip install --force-reinstall --no-cache-dir numpy scipy trimesh

# Note: USD may not support NumPy 2.x yet, check compatibility first
```

## SOLUTION 3: Disable Mesh Optimization (Temporary Workaround)

The `mesh_optimization` module is already optional. To completely bypass numpy/scipy:

1. Edit converter config to disable mesh processing:
```python
# In file_type_importer config
{
  "converter": {
    "use_mesh_optimization": False,
    "skip_mesh_loading": False  # Keep this False to still load meshes
  }
}
```

2. Or use the pre-patched code that already makes mesh_optimization optional

## For the ROA IPC Service

After fixing numpy:
```bash
# Restart the service
python3 /home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python/service_manager.py stop
python3 /home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python/service_manager.py start

# Or use the GUI "Start Service" button
```

## Verification

After applying the fix:
```bash
# Test the converter directly
cd /home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python
python3 << 'PY'
from file_type_importer import FileTypeImporter

fti = FileTypeImporter(enable_hb=False, enable_obs=False)
result = fti.import_robot(
    file_path="/mnt/d/ROA/universal_robot-Examples/ur_description/urdf/ur10e.xacro",
    robot_name="ur10e_test",
    import_mode="both"
)
print(f"Success: {result.success}")
if not result.success:
    print(f"Error: {result.error_message}")
PY
```

## Current Status

The code has been updated to:
1. ✅ Wrap trimesh/numpy imports with clear error messages
2. ✅ Make mesh_optimization optional (won't crash service startup)
3. ✅ Provide detailed guidance when binary incompatibility is detected
4. ⚠️ **Still needs numpy/scipy downgrade** for actual conversion to work

## Next Steps

1. Choose Solution 1 (NumPy 1.x) - Easiest and most compatible
2. Run the commands above
3. Restart IPC service
4. Test conversion via GUI

The GUI will now show clearer feedback about what's happening during service start and conversion.
