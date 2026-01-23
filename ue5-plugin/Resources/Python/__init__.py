"""
ROA UE5 Module - Utilities for UE5 integration

This module provides tools for:
- Hierarchy assembly after USD import
- Post-import hooks
- Complete import workflows for manual and direct convert scenarios
- Physics constraint setup from USD Physics schema
- UE5-specific utilities
- URDF robot assembly in UE5

Components:
- ue5_hierarchy_assembler: Reconstructs robot hierarchies after import
- ue5_import_workflow: Complete import workflow manager
- physics_constraint_setup: Creates PhysicsConstraintComponents from USD Physics
- urdf_robot_assembler: Assembles robot parts in UE5 from hierarchy JSON
- editor_menu: UE5 editor menu integration
"""

# Optional imports for UE5-specific modules (may not be available in WSL)
try:
    from .urdf_robot_assembler import (
        assemble_robot,
        assemble_all,
        list_robots,
        reset_robot,
        PYCO,
    )
    URDF_ASSEMBLER_AVAILABLE = True
except ImportError as e:
    print(f"[ROA] urdf_robot_assembler not available: {e}")
    URDF_ASSEMBLER_AVAILABLE = False
except Exception as e:
    print(f"[ROA] urdf_robot_assembler failed to load: {e}")
    URDF_ASSEMBLER_AVAILABLE = False

# Robot Blueprint Factory (UE5 only)
try:
    from .robot_blueprint_factory import (
        create_robot_blueprint,
        spawn_robot,
        list_robot_blueprints,
        create_blueprint_from_scene,
        bp,  # Short alias
        sr,  # Short alias
        lbp,  # Short alias
    )
    BLUEPRINT_FACTORY_AVAILABLE = True
except ImportError as e:
    print(f"[ROA] robot_blueprint_factory not available: {e}")
    BLUEPRINT_FACTORY_AVAILABLE = False
except Exception as e:
    print(f"[ROA] robot_blueprint_factory failed to load: {e}")
    BLUEPRINT_FACTORY_AVAILABLE = False

try:
    from .editor_menu import register_menus
    EDITOR_MENU_AVAILABLE = True
    # The editor_menu module will auto-register on import via _on_module_load()
    # But we also explicitly call it here to ensure menus are registered
    print("[ROA] Editor menu module imported, calling register_menus()...")
    register_menus()
except ImportError as e:
    print(f"[ROA] Editor menu not available: {e}")
    EDITOR_MENU_AVAILABLE = False
except Exception as e:
    print(f"[ROA] Editor menu failed to load: {e}")
    EDITOR_MENU_AVAILABLE = False

# Physics constraint setup (works in both WSL and UE5)
try:
    from .physics_constraint_setup import (
        JointType,
        JointDriveParams,
        JointLimits,
        PhysicsJointData,
        PhysicsSceneData,
        FilteredPairsData,
        parse_usd_physics_joints,
        parse_usd_physics_scene,
        parse_usd_filtered_pairs,
        create_physics_constraints,
        setup_physics_from_usd,
    )
    PHYSICS_SETUP_AVAILABLE = True
except ImportError:
    PHYSICS_SETUP_AVAILABLE = False

from .ue5_hierarchy_assembler import (
    # Data classes
    LinkTransform,
    LinkInfo,
    RobotHierarchy,
    
    # Functions
    read_usd_metadata,
    is_roa_generated_usd,
    assemble_hierarchy,
    assemble_from_usd_path,
    assemble_from_metadata_string,
    create_postimport_script,
)

from .ue5_import_workflow import (
    # Enums
    ImportScenario,
    
    # Data classes
    RobotImportConfig,
    RobotImportResult,
    
    # Main workflow class
    UE5ImportWorkflow,
    
    # Convenience functions
    import_robot,
    convert_robot,
)

__all__ = [
    # Hierarchy Assembler
    'LinkTransform',
    'LinkInfo', 
    'RobotHierarchy',
    'read_usd_metadata',
    'is_roa_generated_usd',
    'assemble_hierarchy',
    'assemble_from_usd_path',
    'assemble_from_metadata_string',
    'create_postimport_script',
    
    # Import Workflow
    'ImportScenario',
    'RobotImportConfig',
    'RobotImportResult',
    'UE5ImportWorkflow',
    'import_robot',
    'convert_robot',
    
    # Physics Constraint Setup
    'PHYSICS_SETUP_AVAILABLE',
    
    # URDF Robot Assembler (optional - UE5 only)
    'URDF_ASSEMBLER_AVAILABLE',
    'EDITOR_MENU_AVAILABLE',
]

# Conditionally add UE5-specific exports
if URDF_ASSEMBLER_AVAILABLE:
    __all__.extend(['assemble_robot', 'assemble_all', 'list_robots', 'reset_robot', 'PYCO'])
if EDITOR_MENU_AVAILABLE:
    __all__.append('register_menus')
if PHYSICS_SETUP_AVAILABLE:
    __all__.extend([
        'JointType',
        'JointDriveParams',
        'JointLimits',
        'PhysicsJointData',
        'parse_usd_physics_joints',
        'create_physics_constraints',
        'setup_physics_from_usd',
    ])
if BLUEPRINT_FACTORY_AVAILABLE:
    __all__.extend([
        'create_robot_blueprint',
        'spawn_robot', 
        'list_robot_blueprints',
        'create_blueprint_from_scene',
        'bp', 'sr', 'lbp',
    ])
