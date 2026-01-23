"""
ROA Editor Menu Integration
============================
Adds ROA toolbar with nested menus to UE5 Editor.

Menu Structure:
    ROA (Main Toolbar)
    └── FTI
        ├── Assemble Robot...
        ├── Assemble All Robots
        ├── List Available Robots
        └── Reset Robots

This module integrates with the UE5 Editor to provide easy access
to robot assembly without needing to use the Python console.

Usage:
    This file is auto-loaded when UE5 starts (via init_unreal.py).
    
    Manual loading:
        import ROA.editor_menu
        ROA.editor_menu.register_menus()
"""

import unreal
import os
import json
from typing import Optional, List

# Try to import our assembler
try:
    from . import urdf_robot_assembler as assembler
except ImportError:
    assembler = None


# =============================================================================
# FILE DIALOG UTILITIES
# =============================================================================

def open_file_dialog(
    title: str = "Select File",
    default_path: str = "",
    file_types: str = "All Files (*.*)|*.*"
) -> Optional[str]:
    """
    Open a native file dialog and return the selected file path.
    
    Args:
        title: Dialog window title
        default_path: Initial directory to open
        file_types: Filter string (UE4 format)
        
    Returns:
        Selected file path or None if cancelled
    """
    # Use UE5's file dialog utility
    result = unreal.DesktopPlatformLibrary.open_file_dialog(
        unreal.EditorLevelLibrary.get_editor_world(),
        title,
        default_path,
        "",
        file_types,
        False  # Allow multiple = False
    )
    
    if result and len(result) > 0:
        return result[0]
    return None


def open_hierarchy_file_dialog() -> Optional[str]:
    """
    Open file dialog specifically for hierarchy JSON files.
    
    Returns:
        Path to selected hierarchy JSON file or None
    """
    import tempfile
    
    # Start in temp directory where hierarchy files are saved
    default_path = tempfile.gettempdir()
    
    # Also check ROA output directories
    roa_dirs = [
        "D:/ROA/FTI-Outputs",
        "D:/ROA/output-tests",
    ]
    
    for d in roa_dirs:
        if os.path.isdir(d):
            default_path = d
            break
    
    return open_file_dialog(
        title="Select Robot Hierarchy File",
        default_path=default_path,
        file_types="Hierarchy JSON (*.json)|*.json|All Files (*.*)|*.*"
    )


# =============================================================================
# ASSEMBLY COMMANDS
# =============================================================================

def assemble_robot_from_dialog():
    """
    Open file dialog, let user select hierarchy JSON, then assemble.
    This is the main menu action.
    """
    if assembler is None:
        unreal.log_error("ROA: urdf_robot_assembler module not found!")
        return
    
    print("\n" + "=" * 60)
    print("  ROA Robot Assembler")
    print("=" * 60)
    print("\nOpening file dialog...")
    
    # Try using UE5's built-in dialog first
    try:
        hierarchy_path = open_hierarchy_file_dialog()
    except Exception as e:
        print(f"[WARN] Could not open file dialog: {e}")
        print("[INFO] Falling back to auto-detection...")
        hierarchy_path = None
    
    if not hierarchy_path:
        # Fall back to listing available robots
        print("\n[INFO] No file selected. Available robots:")
        robots = assembler.list_robots()
        
        if robots:
            print("\n[TIP] Use one of these commands in Python console:")
            for r in robots:
                print(f"  assemble_robot('{r}')")
        return
    
    # Validate the file
    if not os.path.isfile(hierarchy_path):
        print(f"[ERROR] File not found: {hierarchy_path}")
        return
    
    if not hierarchy_path.endswith('.json'):
        print(f"[WARN] File may not be a hierarchy JSON: {hierarchy_path}")
    
    # Run assembly
    print(f"\n[INFO] Assembling from: {hierarchy_path}")
    success = assembler.assemble_robot(hierarchy_path, verbose=True)
    
    if success:
        print("\n[SUCCESS] Robot assembled!")
    else:
        print("\n[FAILED] Assembly failed. Check the logs above.")


def assemble_all_robots():
    """
    Auto-detect and assemble all available robots.
    """
    if assembler is None:
        unreal.log_error("ROA: urdf_robot_assembler module not found!")
        return
    
    count = assembler.assemble_all(verbose=True)
    print(f"\n[DONE] Assembled {count} robot(s)")


def list_available_robots():
    """
    List all hierarchy files available for assembly.
    """
    if assembler is None:
        unreal.log_error("ROA: urdf_robot_assembler module not found!")
        return
    
    assembler.list_robots()


def reset_all_robots():
    """
    Reset all robot actors to origin.
    """
    if assembler is None:
        unreal.log_error("ROA: urdf_robot_assembler module not found!")
        return
    
    assembler.reset_robot("")


# =============================================================================
# MENU REGISTRATION
# =============================================================================

# Global reference to keep menu entries alive
_registered_entries = []
_roa_menu = None
_fti_submenu = None


def register_menus():
    """
    Register ROA menu items in the UE5 Editor.
    
    Adds FTI menu items to the existing Window menu for compatibility.
    """
    global _registered_entries
    
    try:
        # Get the tool menus
        tool_menus = unreal.ToolMenus.get()
        
        # Use Window menu which is more stable across UE5 versions
        window_menu = tool_menus.find_menu("LevelEditor.MainMenu.Window")
        
        if not window_menu:
            print("[ROA] Could not find Window menu")
            return False
        
        # =====================================================================
        # Add ROA/FTI section to Window menu
        # =====================================================================
        
        # Add ROA section 
        window_menu.add_section("ROA_FTI", "ROA - Files Type Importer")
        
        # Entry 1: Assemble Robot (with file dialog)
        entry_assemble = unreal.ToolMenuEntry(
            name="FTI_AssembleRobot",
            type=unreal.MultiBlockType.MENU_ENTRY
        )
        entry_assemble.set_label("FTI: Assemble Robot...")
        entry_assemble.set_tool_tip("Select a hierarchy JSON file and assemble the robot in the scene")
        entry_assemble.set_string_command(
            unreal.ToolMenuStringCommandType.PYTHON,
            "",
            "from ROA.editor_menu import assemble_robot_from_dialog; assemble_robot_from_dialog()"
        )
        window_menu.add_menu_entry("ROA_FTI", entry_assemble)
        _registered_entries.append(entry_assemble)
        
        # Entry 2: Assemble All
        entry_all = unreal.ToolMenuEntry(
            name="FTI_AssembleAll",
            type=unreal.MultiBlockType.MENU_ENTRY
        )
        entry_all.set_label("FTI: Assemble All Robots")
        entry_all.set_tool_tip("Auto-detect and assemble all available robots")
        entry_all.set_string_command(
            unreal.ToolMenuStringCommandType.PYTHON,
            "",
            "from ROA.editor_menu import assemble_all_robots; assemble_all_robots()"
        )
        window_menu.add_menu_entry("ROA_FTI", entry_all)
        _registered_entries.append(entry_all)
        
        # Entry 3: List Robots
        entry_list = unreal.ToolMenuEntry(
            name="FTI_ListRobots", 
            type=unreal.MultiBlockType.MENU_ENTRY
        )
        entry_list.set_label("FTI: List Available Robots")
        entry_list.set_tool_tip("Show hierarchy files available for assembly")
        entry_list.set_string_command(
            unreal.ToolMenuStringCommandType.PYTHON,
            "",
            "from ROA.editor_menu import list_available_robots; list_available_robots()"
        )
        window_menu.add_menu_entry("ROA_FTI", entry_list)
        _registered_entries.append(entry_list)
        
        # Entry 4: Reset Robots
        entry_reset = unreal.ToolMenuEntry(
            name="FTI_ResetRobots",
            type=unreal.MultiBlockType.MENU_ENTRY
        )
        entry_reset.set_label("FTI: Reset Robots to Origin")
        entry_reset.set_tool_tip("Reset all robot actors to their origin positions")
        entry_reset.set_string_command(
            unreal.ToolMenuStringCommandType.PYTHON,
            "",
            "from ROA.editor_menu import reset_all_robots; reset_all_robots()"
        )
        window_menu.add_menu_entry("ROA_FTI", entry_reset)
        _registered_entries.append(entry_reset)
        
        # Refresh menus to apply changes
        tool_menus.refresh_all_widgets()
        
        print("[ROA] ✓ FTI menus registered in Window menu!")
        print("[ROA] Look for 'ROA - Files Type Importer' section in Window menu")
        return True
        
    except Exception as e:
        print(f"[ROA] Could not register menus: {e}")
        print("[ROA] Use Python console commands instead:")
        print("  from ROA import assemble_robot, list_robots")
        return False


def unregister_menus():
    """
    Remove ROA menu items from the Editor.
    """
    global _registered_entries
    
    try:
        tool_menus = unreal.ToolMenus.get()
        file_menu = tool_menus.find_menu("LevelEditor.MainMenu.File")
        
        if file_menu:
            # Remove our section
            # Note: UE5 Python API may not support direct removal
            pass
            
        _registered_entries.clear()
        print("[ROA] Editor menus unregistered")
        
    except Exception as e:
        print(f"[ROA] Could not unregister menus: {e}")


# =============================================================================
# AUTO-INITIALIZATION
# =============================================================================

def _on_module_load():
    """
    Called when this module is imported.
    Automatically registers menus if running in Editor.
    """
    try:
        # Check if we're running in the Editor
        if unreal.SystemLibrary.is_running_in_editor():
            print("[ROA] Editor menu module loaded")
            
            # Delay registration slightly to ensure Editor is fully initialized
            # Using an EditorTicker would be ideal, but simple delayed call works for most cases
            try:
                # Try to register menus immediately
                # If Editor isn't ready yet, user can manually call register_menus()
                success = register_menus()
                if success:
                    print("[ROA] ✓ FTI menus auto-registered successfully!")
                else:
                    print("[ROA] Auto-registration deferred. Run 'from ROA.editor_menu import register_menus; register_menus()' to add menu items")
            except Exception as reg_error:
                print(f"[ROA] Auto-registration deferred (reason: {reg_error})")
                print("[ROA] Run 'from ROA.editor_menu import register_menus; register_menus()' to add menu items")
    except Exception as e:
        # Not in Editor or unreal module not fully available
        pass


# Run on import
_on_module_load()


# =============================================================================
# SIMPLE COMMAND INTERFACE
# =============================================================================

# These can be called directly from Python console

def assemble(robot_name: str = ""):
    """
    Quick assembly command.
    
    Usage:
        assemble()          # Opens file dialog or lists available
        assemble("ur18")    # Assembles specific robot
    """
    if not robot_name:
        assemble_robot_from_dialog()
    else:
        if assembler:
            assembler.assemble_robot(robot_name, verbose=True)
        else:
            print("[ERROR] Assembler module not loaded")


# Print usage on import
print("")
print("=" * 50)
print("  ROA Robot Assembler Commands")
print("=" * 50)
print("")
print("  assemble()         - Open dialog or list available")
print("  assemble('ur18')   - Assemble specific robot")
print("  list_available_robots()   - List available robots")
print("  assemble_all_robots()     - Assemble all robots")
print("  reset_all_robots()        - Reset robots to origin")
print("")
