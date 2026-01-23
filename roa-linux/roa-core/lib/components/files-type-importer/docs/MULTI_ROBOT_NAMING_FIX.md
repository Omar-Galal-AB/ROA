# Multi-Robot Naming Convention Fix

## Problem Statement

When importing multiple robots of the same family (e.g., UR10, UR18, UR20), they all share identical link names from their URDF files:
- `base_link`
- `shoulder_link`
- `forearm_link`
- `wrist_1_link`
- `wrist_2_link`
- `wrist_3_link`

This caused the UE5 assembler to match the wrong robot's actors when creating physics constraints and positioning parts.

## Solution: Robot-Prefixed Mesh Naming

### What Changed

**urdf_converter.py** - USD mesh names now include robot name prefix:
- Old format: `shoulder_link_visual`
- New format: `ur18_shoulder_link_visual`

**urdf_robot_assembler.py** - Actor matching with 3-phase priority:
1. **Robot-prefixed names** (highest priority): Matches `ur18_shoulder_link_visual`
2. **Position clustering**: Groups actors by proximity to reference position
3. **Standard names** (fallback): Matches `shoulder_link_visual` for backward compatibility

**UE5 generated script** - Updated actor search patterns to prioritize robot-prefixed names

### USD customData Metadata

Each USD file now includes:
```
customData = {
    robot_name = "UR18 Robot"
    robot_prefix = "ur18_robot"  # Sanitized name for actor matching
    mesh_naming_convention = "ur18_robot_<link_name>_visual"
}
```

## File Changes

### 1. urdf_converter.py

**Location**: `lib/components/files-type-importer/src/python/Converters/urdf_converter.py`

```python
# Store robot name for mesh naming
self._current_robot_name = self._sanitize_name(urdf_robot_name)

# Visual mesh naming
robot_prefix = getattr(self, '_current_robot_name', '')
if robot_prefix:
    visual_name = f"{robot_prefix}_{safe_name}_visual"
else:
    visual_name = f"{safe_name}_visual"  # Fallback

# Collision mesh naming
if robot_prefix:
    collision_name = f"{robot_prefix}_{safe_name}_collision"
else:
    collision_name = f"{safe_name}_collision"  # Fallback
```

### 2. urdf_robot_assembler.py

**Location**: `lib/components/files-type-importer/src/python/UE5/urdf_robot_assembler.py`

```python
def find_robot_actors(robot_name: str = "", link_names: List[str] = None, 
                      reference_position: List[float] = None, 
                      position_tolerance: float = 500.0) -> Dict[str, List[Any]]:
    """
    Multi-robot support with 3-phase matching:
    1. Robot-prefixed names (e.g., "ur18_shoulder_link_visual")
    2. Position clustering (actors near reference_position)
    3. Standard names (backward compatibility)
    """
```

## Example Usage

### Multi-Robot Scene

When you have UR10 and UR18 in the same scene:

**UR18 actors** (after USD import):
- `ur18_robot_base_link_visual`
- `ur18_robot_shoulder_link_visual`
- `ur18_robot_forearm_link_visual`

**UR10 actors** (after USD import):
- `ur10_robot_base_link_visual`
- `ur10_robot_shoulder_link_visual`
- `ur10_robot_forearm_link_visual`

The assembler will now correctly match only the UR18 actors when assembling the UR18 robot.

### Assembler Call

```python
from ROA.urdf_robot_assembler import assemble_robot

# Assembles only UR18 parts (uses robot-prefixed names)
assemble_robot("D:/ROA/output/ur18_hierarchy.json")
```

## Backward Compatibility

The fix is fully backward compatible:
- New USD files use robot-prefixed names
- Assembler falls back to standard names if no prefixed matches found
- Single-robot scenes work unchanged

## Testing

1. Convert a URDF with robot name "UR18 Robot":
   ```
   python fti_convert.py ur18.urdf output.usd "UR18 Robot"
   ```

2. Check USD mesh names include prefix:
   ```
   usdcat output_assembled.usda | grep "visual"
   # Should show: ur18_robot_shoulder_link_visual, etc.
   ```

3. Import multiple robots into UE5 level

4. Run assembler - each robot's parts should be matched correctly

## Related Files

- [MULTI_ROBOT_NAMING_SOLUTION.md](../../docs/MULTI_ROBOT_NAMING_SOLUTION.md) - Initial analysis
- [ROBOT_JOINTS_AND_CONSTRAINTS_RESEARCH.md](/home/myws/roa/ROBOT_JOINTS_AND_CONSTRAINTS_RESEARCH.md) - Physics constraints research
