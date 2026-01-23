"""
ROA UE5 Module - Utilities for UE5 integration

This module provides tools for:
- Hierarchy assembly after USD import
- Post-import hooks
- Complete import workflows for manual and direct convert scenarios
- UE5-specific utilities
- URDF robot assembly in UE5

Components:
- ue5_hierarchy_assembler: Reconstructs robot hierarchies after import
- ue5_import_workflow: Complete import workflow manager
- urdf_robot_assembler: Assembles robot parts in UE5 from hierarchy JSON
- editor_menu: UE5 editor menu integration
"""

# Optional imports for UE5-specific modules (may not be available in WSL)
try:
    from .urdf_robot_assembler import URDFRobotAssembler
    URDF_ASSEMBLER_AVAILABLE = True
except ImportError:
    URDF_ASSEMBLER_AVAILABLE = False

try:
    from .editor_menu import register_menus
    EDITOR_MENU_AVAILABLE = True
except ImportError:
    EDITOR_MENU_AVAILABLE = False

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
    
    # URDF Robot Assembler (optional - UE5 only)
    'URDF_ASSEMBLER_AVAILABLE',
    'EDITOR_MENU_AVAILABLE',
]

# Conditionally add UE5-specific exports
if URDF_ASSEMBLER_AVAILABLE:
    __all__.append('URDFRobotAssembler')
if EDITOR_MENU_AVAILABLE:
    __all__.append('setup_roa_menu')
