"""
ue5_import_workflow.py
ROA - Robot Operations & Automation

UE5 Import Workflow Manager
Handles both manual import and direct convert scenarios.

Scenarios:
1. Manual Import: User converted externally, imports assembled USD into UE5
2. Direct Convert: User triggers conversion from within UE5 plugin

Author: ROA Team
"""

import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# UE5 imports (available when running inside Unreal)
try:
    import unreal

    IN_UNREAL = True
except ImportError:
    IN_UNREAL = False

    # Mock for testing outside UE5
    class unreal:
        @staticmethod
        def log(msg):
            print(f"[UE5] {msg}")

        @staticmethod
        def log_warning(msg):
            print(f"[UE5 WARNING] {msg}")

        @staticmethod
        def log_error(msg):
            print(f"[UE5 ERROR] {msg}")


class ImportScenario(Enum):
    """Import workflow scenario"""

    MANUAL_IMPORT = "manual"  # User imports pre-converted USD
    DIRECT_CONVERT = "direct"  # Plugin triggers conversion


@dataclass
class RobotImportConfig:
    """Configuration for robot import"""

    # Source
    source_file: str = ""  # URDF/XACRO or assembled USD path

    # UE5 Destination
    content_path: str = "/Game/Robots"  # Base content folder
    robot_folder: str = ""  # Robot-specific subfolder (auto-generated if empty)

    # Assembly Options
    auto_assemble: bool = True  # Run hierarchy assembly after import
    generate_blueprint: bool = True  # Create Blueprint from assembled robot
    setup_physics: bool = True  # Configure physics constraints
    setup_collision: bool = True  # Apply collision settings

    # Advanced
    import_materials: bool = True  # Import/apply materials
    preserve_hierarchy: bool = True  # Keep URDF hierarchy structure
    scale_factor: float = 100.0  # URDF meters → UE5 centimeters


@dataclass
class RobotImportResult:
    """Result of robot import operation"""

    success: bool = False
    robot_name: str = ""
    scenario: ImportScenario = ImportScenario.MANUAL_IMPORT

    # Paths
    content_folder: str = ""  # /Game/Robots/ur3
    assembled_actor_path: str = ""  # Path to assembled actor in level
    blueprint_path: str = ""  # Path to generated Blueprint

    # Statistics
    mesh_count: int = 0
    link_count: int = 0
    joint_count: int = 0

    # Issues
    warnings: List[str] = field(default_factory=list)
    error_message: str = ""


class UE5ImportWorkflow:
    """
    Manages robot import workflows in UE5.

    Supports two scenarios:
    1. Manual Import: User already converted with FTI, imports USD into UE5
    2. Direct Convert: Plugin calls FTI service, converts, and imports
    """

    # File patterns for auto-discovery
    ASSEMBLED_USD_SUFFIX = "_assembled.usd"
    HIERARCHY_SCRIPT_SUFFIX = "_ue5_hierarchy.py"
    MESHES_FOLDER = "meshes"

    # USD metadata keys (from FTI converter)
    USD_EXPORT_SOURCE_KEY = "export_source"
    USD_ROBOT_NAME_KEY = "robot_name"
    USD_HIERARCHY_KEY = "hierarchy"
    FTI_EXPORT_SOURCE = "ROA_URDF_Converter"

    def __init__(self, config: Optional[RobotImportConfig] = None):
        """
        Initialize import workflow.

        Args:
            config: Import configuration (uses defaults if None)
        """
        self.config = config or RobotImportConfig()
        self.logger = logging.getLogger(__name__)
        self.result = RobotImportResult()

    # ═══════════════════════════════════════════════════════════════════════
    # Scenario 1: Manual Import (User imports pre-converted USD)
    # ═══════════════════════════════════════════════════════════════════════

    def import_from_assembled_usd(self, usd_path: str) -> RobotImportResult:
        """
        Import robot from pre-converted assembled USD file.

        This is Scenario 1: User converted externally and imports the result.

        The workflow:
        1. Validate USD is from FTI (check customData)
        2. Find companion hierarchy script in same folder
        3. Find mesh files in meshes/ subfolder
        4. Create content folder in UE5
        5. Import all meshes
        6. Run hierarchy assembly script
        7. Optionally generate Blueprint

        Args:
            usd_path: Path to the assembled USD file

        Returns:
            Import result with paths and statistics
        """
        self.result = RobotImportResult(scenario=ImportScenario.MANUAL_IMPORT)

        try:
            unreal.log(f"═══════════════════════════════════════════════════════")
            unreal.log(f"ROA FTI: Starting Manual Import Workflow")
            unreal.log(f"Source: {usd_path}")
            unreal.log(f"═══════════════════════════════════════════════════════")

            # Step 1: Validate the USD file
            if not self._validate_fti_usd(usd_path):
                return self.result

            # Step 2: Extract robot info and find companion files
            source_folder = Path(usd_path).parent
            robot_name = self._extract_robot_name(usd_path)
            self.result.robot_name = robot_name

            unreal.log(f"Robot name: {robot_name}")

            # Step 3: Find hierarchy script
            hierarchy_script = self._find_hierarchy_script(source_folder, robot_name)
            if not hierarchy_script and self.config.auto_assemble:
                self.result.warnings.append(
                    f"Hierarchy script not found: {robot_name}{self.HIERARCHY_SCRIPT_SUFFIX}"
                )

            # Step 4: Find mesh files
            mesh_folder = source_folder / self.MESHES_FOLDER
            mesh_files = self._find_mesh_files(mesh_folder)
            self.result.mesh_count = len(mesh_files)

            unreal.log(f"Found {len(mesh_files)} mesh files")

            # Step 5: Create UE5 content folder
            content_folder = self._create_content_folder(robot_name)
            self.result.content_folder = content_folder

            # Step 6: Import all meshes into UE5
            imported_assets = self._import_meshes(mesh_files, content_folder)

            # Step 7: Import the assembled USD
            assembled_asset = self._import_assembled_usd(usd_path, content_folder)

            # Step 8: Run hierarchy assembly
            if self.config.auto_assemble and hierarchy_script:
                self._run_hierarchy_assembly(hierarchy_script, robot_name)
            elif self.config.auto_assemble:
                # Try to assemble from USD metadata directly
                self._assemble_from_usd_metadata(usd_path, robot_name)

            # Step 9: Generate Blueprint if requested
            if self.config.generate_blueprint:
                self._generate_robot_blueprint(robot_name, content_folder)

            # Success!
            self.result.success = True

            # v3.0: Display enhanced info if available
            v3_info = self._get_v3_info(source_folder, robot_name)

            unreal.log(f"═══════════════════════════════════════════════════════")
            unreal.log(f"ROA FTI: Import Complete!")
            unreal.log(f"  Robot: {robot_name}")
            unreal.log(f"  Meshes: {self.result.mesh_count}")
            unreal.log(f"  Content: {content_folder}")
            if v3_info:
                unreal.log(f"  Robot Type: {v3_info.get('robot_type', 'unknown')}")
                unreal.log(f"  Submechanisms: {v3_info.get('submechanism_count', 0)}")
                unreal.log(f"  IK Available: {v3_info.get('ik_available', False)}")
            unreal.log(f"═══════════════════════════════════════════════════════")

        except Exception as e:
            self.result.error_message = str(e)
            unreal.log_error(f"Import failed: {e}")

        return self.result

    def _get_v3_info(self, folder: Path, robot_name: str) -> Optional[Dict[str, Any]]:
        """Load v3.0 info from hierarchy JSON if available."""
        try:
            # Try to find hierarchy JSON
            json_patterns = [
                folder / f"{robot_name}_hierarchy.json",
                folder / f"{robot_name}_hierarchy_data.json",
                folder / "hierarchy.json",
            ]

            for json_path in json_patterns:
                if json_path.exists():
                    with open(json_path, "r") as f:
                        data = json.load(f)

                    version = data.get("version", "2.0")
                    if version.startswith("3"):
                        submech = data.get("submechanisms", {})
                        ik_config = data.get("ik_config", {})
                        return {
                            "version": version,
                            "robot_type": submech.get("robot_type", "unknown"),
                            "submechanism_count": len(submech.get("groups", [])),
                            "ik_available": any(cfg.get("available") for cfg in ik_config.values()),
                            "enhanced_joints_count": len(data.get("enhanced_joints", [])),
                        }
                    return None
        except Exception:
            pass
        return None

    # ═══════════════════════════════════════════════════════════════════════
    # Scenario 2: Direct Convert (Plugin triggers FTI conversion)
    # ═══════════════════════════════════════════════════════════════════════

    def convert_and_import(
        self, source_file: str, fti_service_url: str = "localhost:9877"
    ) -> RobotImportResult:
        """
        Convert source file (URDF/XACRO) and import into UE5.

        This is Scenario 2: One-click convert + import from UE5.

        The workflow:
        1. Validate source file exists
        2. Connect to FTI IPC service
        3. Send conversion request
        4. Wait for conversion completion
        5. Import the generated USD and meshes
        6. Run hierarchy assembly
        7. Generate Blueprint

        Args:
            source_file: Path to URDF, XACRO, or other supported format
            fti_service_url: FTI IPC service address

        Returns:
            Import result with paths and statistics
        """
        self.result = RobotImportResult(scenario=ImportScenario.DIRECT_CONVERT)

        try:
            unreal.log(f"═══════════════════════════════════════════════════════")
            unreal.log(f"ROA FTI: Starting Direct Convert Workflow")
            unreal.log(f"Source: {source_file}")
            unreal.log(f"═══════════════════════════════════════════════════════")

            # Step 1: Validate source file
            if not Path(source_file).exists():
                self.result.error_message = f"Source file not found: {source_file}"
                unreal.log_error(self.result.error_message)
                return self.result

            # Extract robot name from source
            robot_name = Path(source_file).stem
            self.result.robot_name = robot_name

            # Step 2: Prepare output location (temp folder or specified)
            output_folder = self._prepare_conversion_output(robot_name)

            # Step 3: Call FTI service for conversion
            unreal.log("Sending conversion request to FTI service...")
            conversion_result = self._call_fti_service(source_file, output_folder, fti_service_url)

            if not conversion_result.get("success"):
                self.result.error_message = conversion_result.get("error", "Conversion failed")
                unreal.log_error(self.result.error_message)
                return self.result

            # Step 4: Get the output USD path
            output_usd = conversion_result.get("output_file")
            if not output_usd:
                self.result.error_message = "No output file from conversion"
                return self.result

            unreal.log(f"Conversion complete: {output_usd}")

            # v3.0: Log enhanced metadata if available
            metadata = conversion_result.get("metadata", {})
            if metadata:
                submech = metadata.get("submechanisms", {})
                if submech.get("available"):
                    unreal.log(f"  Robot Type: {submech.get('robot_type', 'unknown')}")
                    unreal.log(f"  Submechanisms: {submech.get('count', 0)}")
                if metadata.get("ik_available"):
                    unreal.log(f"  IK Solver: Available")
                if metadata.get("hierarchy_path_windows"):
                    unreal.log(f"  Hierarchy JSON: {metadata.get('hierarchy_path_windows')}")

            # Step 5: Now import using Scenario 1 workflow
            # This reuses all the import logic
            return self.import_from_assembled_usd(output_usd)

        except Exception as e:
            self.result.error_message = str(e)
            unreal.log_error(f"Convert and import failed: {e}")

        return self.result

    # ═══════════════════════════════════════════════════════════════════════
    # Helper Methods
    # ═══════════════════════════════════════════════════════════════════════

    def _validate_fti_usd(self, usd_path: str) -> bool:
        """Check if USD file is from FTI converter."""
        if not Path(usd_path).exists():
            self.result.error_message = f"USD file not found: {usd_path}"
            unreal.log_error(self.result.error_message)
            return False

        # Try to read USD metadata
        try:
            from pxr import Usd

            stage = Usd.Stage.Open(usd_path)
            if not stage:
                self.result.error_message = "Failed to open USD stage"
                return False

            root_prim = stage.GetDefaultPrim()
            if not root_prim:
                # Try first prim
                for prim in stage.TraverseAll():
                    root_prim = prim
                    break

            if root_prim:
                custom_data = root_prim.GetCustomData()
                export_source = custom_data.get(self.USD_EXPORT_SOURCE_KEY, "")

                if export_source != self.FTI_EXPORT_SOURCE:
                    self.result.warnings.append(
                        f"USD not from FTI (export_source={export_source}). "
                        "Assembly may not work correctly."
                    )
                else:
                    unreal.log("✓ Validated FTI-generated USD")
                    return True

        except ImportError:
            # pxr not available - skip validation
            self.result.warnings.append("USD validation skipped (pxr not available)")

        except Exception as e:
            self.result.warnings.append(f"USD validation warning: {e}")

        return True  # Proceed anyway with warnings

    def _extract_robot_name(self, usd_path: str) -> str:
        """Extract robot name from USD path or metadata."""
        path = Path(usd_path)
        name = path.stem

        # Remove _assembled suffix if present
        if name.endswith("_assembled"):
            name = name[:-10]

        return name

    def _find_hierarchy_script(self, folder: Path, robot_name: str) -> Optional[Path]:
        """Find the hierarchy assembly Python script."""
        # Try exact match first
        script_path = folder / f"{robot_name}{self.HIERARCHY_SCRIPT_SUFFIX}"
        if script_path.exists():
            unreal.log(f"✓ Found hierarchy script: {script_path.name}")
            return script_path

        # Try pattern match
        for py_file in folder.glob("*_ue5_hierarchy.py"):
            unreal.log(f"✓ Found hierarchy script: {py_file.name}")
            return py_file

        return None

    def _find_mesh_files(self, mesh_folder: Path) -> List[Path]:
        """Find all mesh files in the meshes folder."""
        mesh_files = []

        if not mesh_folder.exists():
            unreal.log_warning(f"Meshes folder not found: {mesh_folder}")
            return mesh_files

        # Support multiple formats
        for ext in ["*.usd", "*.usda", "*.usdc", "*.fbx", "*.obj"]:
            mesh_files.extend(mesh_folder.glob(ext))

        return sorted(mesh_files)

    def _create_content_folder(self, robot_name: str) -> str:
        """Create the content folder in UE5."""
        folder_path = f"{self.config.content_path}/{robot_name}"

        if IN_UNREAL:
            # Create folder via UE5 API
            editor_asset_lib = unreal.EditorAssetLibrary()
            if not editor_asset_lib.does_directory_exist(folder_path):
                editor_asset_lib.make_directory(folder_path)
                unreal.log(f"✓ Created content folder: {folder_path}")
            else:
                unreal.log(f"✓ Using existing folder: {folder_path}")

        return folder_path

    def _import_meshes(self, mesh_files: List[Path], content_folder: str) -> List[str]:
        """
        Import mesh files into UE5, organizing into Visual and Collision subfolders.

        Folder structure:
            {content_folder}/
                Meshes/
                    Visual/      <- Visual meshes (for rendering)
                    Collision/   <- Collision meshes (for physics)

        Mesh classification:
        - Files with '_collision' or 'collision_' in name → Collision/
        - All other meshes → Visual/
        """
        imported = []

        if not IN_UNREAL:
            unreal.log(f"[Mock] Would import {len(mesh_files)} meshes")
            return imported

        # Create organized folder structure
        editor_asset_lib = unreal.EditorAssetLibrary()

        meshes_folder = f"{content_folder}/Meshes"
        visual_folder = f"{meshes_folder}/Visual"
        collision_folder = f"{meshes_folder}/Collision"

        # Create all required folders
        for folder in [meshes_folder, visual_folder, collision_folder]:
            if not editor_asset_lib.does_directory_exist(folder):
                editor_asset_lib.make_directory(folder)
                unreal.log(f"  Created folder: {folder}")

        # Classify and organize meshes
        visual_meshes = []
        collision_meshes = []

        for mesh_file in mesh_files:
            mesh_name_lower = mesh_file.stem.lower()

            # Classify based on naming convention
            if "_collision" in mesh_name_lower or "collision_" in mesh_name_lower:
                collision_meshes.append(mesh_file)
            else:
                visual_meshes.append(mesh_file)

        unreal.log(f"  Visual meshes: {len(visual_meshes)}")
        unreal.log(f"  Collision meshes: {len(collision_meshes)}")

        # Import visual meshes
        if visual_meshes:
            visual_tasks = []
            for mesh_file in visual_meshes:
                task = unreal.AssetImportTask()
                task.filename = str(mesh_file)
                task.destination_path = visual_folder
                task.destination_name = mesh_file.stem
                task.replace_existing = True
                task.automated = True
                task.save = True
                visual_tasks.append(task)

            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(visual_tasks)

            for task in visual_tasks:
                if task.imported_object_paths:
                    imported.extend(task.imported_object_paths)
                    unreal.log(f"    Visual: {task.destination_name}")

        # Import collision meshes
        if collision_meshes:
            collision_tasks = []
            for mesh_file in collision_meshes:
                task = unreal.AssetImportTask()
                task.filename = str(mesh_file)
                task.destination_path = collision_folder
                task.destination_name = mesh_file.stem
                task.replace_existing = True
                task.automated = True
                task.save = True
                collision_tasks.append(task)

            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(collision_tasks)

            for task in collision_tasks:
                if task.imported_object_paths:
                    imported.extend(task.imported_object_paths)
                    unreal.log(f"    Collision: {task.destination_name}")

        return imported

    def _import_assembled_usd(self, usd_path: str, content_folder: str) -> Optional[str]:
        """Import the assembled USD file."""
        if not IN_UNREAL:
            unreal.log(f"[Mock] Would import assembled USD: {usd_path}")
            return None

        task = unreal.AssetImportTask()
        task.filename = usd_path
        task.destination_path = content_folder
        task.destination_name = Path(usd_path).stem
        task.replace_existing = True
        task.automated = True
        task.save = True

        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

        if task.imported_object_paths:
            unreal.log(f"✓ Imported assembled USD")
            return task.imported_object_paths[0]

        return None

    def _run_hierarchy_assembly(self, script_path: Path, robot_name: str):
        """Execute the hierarchy assembly Python script."""
        unreal.log(f"Running hierarchy assembly script...")

        if not IN_UNREAL:
            unreal.log(f"[Mock] Would execute: {script_path}")
            return

        try:
            # Execute the script in UE5 Python environment
            with open(script_path, "r") as f:
                script_content = f.read()

            exec(script_content, {"__name__": "__main__"})
            unreal.log(f"✓ Hierarchy assembly complete")

        except Exception as e:
            self.result.warnings.append(f"Hierarchy assembly error: {e}")
            unreal.log_warning(f"Hierarchy assembly error: {e}")

    def _assemble_from_usd_metadata(self, usd_path: str, robot_name: str):
        """Assemble hierarchy using USD embedded metadata."""
        unreal.log("Attempting assembly from USD metadata...")

        try:
            # Import our assembler module
            import ue5_hierarchy_assembler as roa

            success = roa.assemble_from_usd_path(usd_path, name_prefix=f"{robot_name}_")

            if success:
                unreal.log("✓ Hierarchy assembled from USD metadata")
            else:
                self.result.warnings.append("Hierarchy assembly from metadata failed")

        except ImportError:
            self.result.warnings.append("ue5_hierarchy_assembler module not found")
        except Exception as e:
            self.result.warnings.append(f"Assembly from metadata error: {e}")

    def _generate_robot_blueprint(self, robot_name: str, content_folder: str):
        """Generate a Blueprint from the assembled robot."""
        unreal.log("Generating robot Blueprint...")

        if not IN_UNREAL:
            unreal.log(f"[Mock] Would generate Blueprint: BP_{robot_name}")
            return

        try:
            # Find the assembled actor in the level
            actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            all_actors = actor_subsystem.get_all_level_actors()

            robot_actor = None
            for actor in all_actors:
                if robot_name.lower() in actor.get_actor_label().lower():
                    robot_actor = actor
                    break

            if not robot_actor:
                self.result.warnings.append(
                    "Could not find assembled actor for Blueprint generation"
                )
                return

            # Generate Blueprint using editor utilities
            blueprint_path = f"{content_folder}/BP_{robot_name}"

            # Use the Blueprint factory
            factory = unreal.BlueprintFactory()
            factory.set_editor_property("parent_class", unreal.Actor)

            asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
            blueprint = asset_tools.create_asset(
                f"BP_{robot_name}", content_folder, unreal.Blueprint, factory
            )

            if blueprint:
                self.result.blueprint_path = blueprint_path
                unreal.log(f"✓ Generated Blueprint: {blueprint_path}")

        except Exception as e:
            self.result.warnings.append(f"Blueprint generation error: {e}")

    def _prepare_conversion_output(self, robot_name: str) -> str:
        """Prepare output folder for conversion."""
        import tempfile

        # Create temp folder for conversion output
        output_dir = Path(tempfile.gettempdir()) / "roa_fti" / robot_name
        output_dir.mkdir(parents=True, exist_ok=True)

        return str(output_dir)

    def _call_fti_service(
        self, source_file: str, output_folder: str, service_url: str
    ) -> Dict[str, Any]:
        """
        Call FTI IPC service for conversion.

        Args:
            source_file: Path to source URDF/XACRO
            output_folder: Where to write output
            service_url: FTI service address

        Returns:
            Conversion result dict with success, output_file, error
        """
        import json
        import socket

        try:
            # Parse service URL
            host, port = service_url.split(":")
            port = int(port)

            # Create request
            request = {
                "protocol_version": "1.0.0",
                "command": "convert",
                "source_file": source_file,
                "output_dir": output_folder,
                "format": "usd",
                "options": {"embed_hierarchy": True, "generate_ue5_script": True},
            }

            # Connect and send request
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(60.0)  # 60 second timeout for conversion
            sock.connect((host, port))

            sock.sendall(json.dumps(request).encode() + b"\n")

            # Receive response
            response_data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response_data += chunk
                if b"\n" in response_data:
                    break

            sock.close()

            response = json.loads(response_data.decode().strip())
            return response

        except Exception as e:
            return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience Functions for UE5 Python Console
# ═══════════════════════════════════════════════════════════════════════════════


def import_robot(usd_path: str, **kwargs) -> RobotImportResult:
    """
    Quick import function for UE5 Python console.

    Usage in UE5:
        import ue5_import_workflow as fti
        result = fti.import_robot("D:/Robots/ur3_assembled.usd")
    """
    config = RobotImportConfig(**kwargs)
    workflow = UE5ImportWorkflow(config)
    return workflow.import_from_assembled_usd(usd_path)


def convert_robot(urdf_path: str, **kwargs) -> RobotImportResult:
    """
    Quick convert + import function for UE5 Python console.

    Usage in UE5:
        import ue5_import_workflow as fti
        result = fti.convert_robot("D:/URDFs/ur3.urdf")
    """
    config = RobotImportConfig(**kwargs)
    workflow = UE5ImportWorkflow(config)
    return workflow.convert_and_import(urdf_path)


# ═══════════════════════════════════════════════════════════════════════════════
# Standalone Testing
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    print("UE5 Import Workflow - Test Mode")
    print("=" * 60)

    if len(sys.argv) < 2:
        print("Usage: python ue5_import_workflow.py <usd_or_urdf_file>")
        print()
        print("This simulates the import workflow outside of UE5.")
        sys.exit(1)

    source_file = sys.argv[1]

    if source_file.endswith(".usd") or source_file.endswith(".usda"):
        print(f"Scenario 1: Manual Import")
        print(f"Source: {source_file}")

        workflow = UE5ImportWorkflow()
        result = workflow.import_from_assembled_usd(source_file)

    else:
        print(f"Scenario 2: Direct Convert")
        print(f"Source: {source_file}")

        workflow = UE5ImportWorkflow()
        result = workflow.convert_and_import(source_file)

    print()
    print("Result:")
    print(f"  Success: {result.success}")
    print(f"  Robot: {result.robot_name}")
    print(f"  Scenario: {result.scenario.value}")
    print(f"  Content Folder: {result.content_folder}")
    print(f"  Meshes: {result.mesh_count}")

    if result.warnings:
        print(f"  Warnings:")
        for w in result.warnings:
            print(f"    - {w}")

    if result.error_message:
        print(f"  Error: {result.error_message}")
