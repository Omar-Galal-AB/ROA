# Parallel Mechanism Workaround for UE5

## Problem
USD Physics doesn't support closed kinematic loops. When FTI converts a parallel mechanism (like Stewart platform), USD breaks the loop by excluding joints from articulation.

## Solution Architecture

### Phase 1: FTI Export Enhancement
FTI detects closed loops and exports metadata for UE5 to reconstruct them.

```python
# In urdf_converter.py - detect loops
def _detect_kinematic_loops(self, joints):
    """Detect closed loops using cycle detection in joint graph."""
    graph = {}
    for joint in joints:
        parent = joint.get('parent_link')
        child = joint.get('child_link')
        if parent not in graph:
            graph[parent] = []
        graph[parent].append((child, joint.get('name')))
    
    # Find cycles using DFS
    visited = set()
    rec_stack = set()
    loops = []
    
    def dfs(node, path):
        visited.add(node)
        rec_stack.add(node)
        
        if node in graph:
            for child, joint_name in graph[node]:
                if child not in visited:
                    if dfs(child, path + [joint_name]):
                        return True
                elif child in rec_stack:
                    # Found a cycle!
                    cycle_start = path.index(joint_name) if joint_name in path else 0
                    loops.append(path[cycle_start:] + [joint_name])
                    return True
        
        rec_stack.remove(node)
        return False
    
    for node in graph.keys():
        if node not in visited:
            dfs(node, [])
    
    return loops

# Export loop metadata to USD
def _export_loop_metadata(self, stage, root_prim, loops):
    """Store loop information in USD custom data."""
    root_prim.SetCustomDataByKey('parallel_mechanisms', {
        'loops': [
            {
                'joints': loop,
                'type': 'closed_loop',
                'reconstruction_method': 'physics_constraint'
            }
            for loop in loops
        ]
    })
```

### Phase 2: UE5 Python Sequence (Post-Import)

Create a Python script that runs in UE5 after USD import:

```python
# ue5_reconstruct_loops.py
import unreal

def reconstruct_parallel_mechanisms(actor):
    """
    Reads USD custom data and creates UE5 PhysicsConstraints
    to close kinematic loops.
    """
    # Get USD metadata
    stage = unreal.UsdStage.open_stage(actor.get_usd_source_path())
    root = stage.get_default_prim()
    
    parallel_data = root.get_custom_data_by_key('parallel_mechanisms')
    if not parallel_data:
        return
    
    for loop_info in parallel_data['loops']:
        joints = loop_info['joints']
        
        # Find the "broken" joint (last in loop)
        broken_joint_name = joints[-1]
        
        # Get the two bodies it should connect
        body1 = actor.find_component_by_name(joints[-2])  # Parent of broken joint
        body2 = actor.find_component_by_name(joints[0])   # Start of loop
        
        # Create Physics Constraint to close the loop
        constraint = unreal.PhysicsConstraintComponent()
        constraint.set_constraint_actors(body1, body2)
        
        # Configure constraint based on joint type
        joint_type = get_joint_type(broken_joint_name)  # From USD
        
        if joint_type == 'revolute':
            constraint.set_angular_twist_limit(
                unreal.AngularConstraintMotion.ACM_LIMITED,
                limit_angle=joint_limits['lower']
            )
        elif joint_type == 'prismatic':
            constraint.set_linear_x_limit(
                unreal.LinearConstraintMotion.LCM_LIMITED,
                limit=joint_limits['upper'] - joint_limits['lower']
            )
        
        actor.add_instance_component(constraint)
        
    unreal.log("Reconstructed {} parallel mechanism loops".format(
        len(parallel_data['loops'])
    ))

# Auto-run on USD import
unreal.register_asset_import_callback(
    'UsdStage',
    lambda asset: reconstruct_parallel_mechanisms(asset.get_actor())
)
```

### Usage

1. **FTI exports USD with loop metadata**
   ```bash
   fti_ros2_node import_robot --file stewart_platform.urdf
   # Exports to: robot.usd (with loop metadata)
   ```

2. **UE5 imports USD**
   - Standard USD import in UE5
   - Articulation is broken (expected)

3. **Run Python Sequence**
   ```python
   # In UE5 Python console or on Begin Play
   import ue5_reconstruct_loops
   robot_actor = unreal.EditorLevelLibrary.get_selected_level_actors()[0]
   ue5_reconstruct_loops.reconstruct_parallel_mechanisms(robot_actor)
   ```

4. **Result**
   - Closed loops reconstructed using Chaos constraints
   - Full parallel mechanism simulation

## Limitations

- **Performance**: Chaos constraints are heavier than articulation joints
- **Stability**: May require constraint solver tuning (iterations, damping)
- **Manual trigger**: User must run Python script (could be automated via Blueprint)

## Alternative: External Physics Engine in FTI

Could we run physics simulation IN FTI during conversion?

**No** - FTI is a converter, not a simulator. We would need:
- Full physics engine (PyBullet, MuJoCo)
- Real-time simulation loop
- Export simulation results as animation curves

This defeats the purpose of having physics in UE5.

## Recommendation

**For now**: Implement metadata export in FTI, provide UE5 Python template.
**Future**: Advocate for USD Physics to support closed loops natively.
