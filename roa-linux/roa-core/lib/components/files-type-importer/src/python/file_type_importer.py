"""
File Type Importer - Main Coordinator Module
Orchestrates the import of robot 3D models into Unreal Engine 5
"""

import os
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

# Support both relative imports (when used as package) and absolute imports (when run standalone)
try:
    from .Converters import (
        DAEConverter,
        FBXConverter,
        GLTFConverter,
        IGESConverter,
        OBJConverter,
        SDFConverter,
        STEPConverter,
        STLConverter,
        URDFConverter,
    )
    from .Converters.parallel_mechanism_exporter import (
        LoopDetector,
        ParallelMechanismExporter,
    )
    from .Converters.submechanism import (
        Submechanism,
        SubmechanismDetector,
        SubmechanismManager,
        SubmechanismType,
        detect_and_create_submechanisms,
    )
    from .format_detector import FormatDetector
    from .Utils.moveit_bridge import (
        ROA_BRIDGE_AVAILABLE,
        IKManager,
        LocalIKSolver,
        MoveItBridge,
        create_ik_manager,
    )
except ImportError:
    from Converters import (
        DAEConverter,
        FBXConverter,
        GLTFConverter,
        IGESConverter,
        OBJConverter,
        SDFConverter,
        STEPConverter,
        STLConverter,
        URDFConverter,
    )
    from format_detector import FormatDetector

    try:
        from Converters.parallel_mechanism_exporter import (
            LoopDetector,
            ParallelMechanismExporter,
        )
    except ImportError:
        ParallelMechanismExporter = None
        LoopDetector = None
    try:
        from Converters.submechanism import (
            Submechanism,
            SubmechanismDetector,
            SubmechanismManager,
            SubmechanismType,
            detect_and_create_submechanisms,
        )
    except ImportError:
        SubmechanismDetector = None
        SubmechanismManager = None
        Submechanism = None
        SubmechanismType = None
        detect_and_create_submechanisms = None
    try:
        from Utils.moveit_bridge import (
            ROA_BRIDGE_AVAILABLE,
            IKManager,
            LocalIKSolver,
            MoveItBridge,
            create_ik_manager,
        )
    except ImportError:
        MoveItBridge = None
        IKManager = None
        LocalIKSolver = None
        create_ik_manager = None
        ROA_BRIDGE_AVAILABLE = False


class ImportMode(Enum):
    """Import mode options for robot models."""

    PARTS = "parts"  # Import individual parts only
    ASSEMBLY = "assembly"  # Import complete assembly only
    BOTH = "both"  # Import both parts and assembly


class ParallelMechanismMode(Enum):
    """How to handle parallel mechanisms (closed kinematic loops)."""

    AUTO = "auto"  # Auto-detect and handle appropriately
    SPLIT = "split"  # Split into multi-file assembly
    BREAK = "break"  # Break loop at arbitrary point (standard USD)
    IGNORE = "ignore"  # Ignore loops, user handles manually


@dataclass
class ImportResult:
    """Result of an import operation."""

    success: bool
    robot_name: str
    content_path: Optional[str] = None
    parts_count: int = 0
    assembly_path: Optional[str] = None
    parts_paths: List[str] = None
    error_message: Optional[str] = None
    warnings: List[str] = None

    def __post_init__(self):
        """Initialize mutable default values."""
        if self.parts_paths is None:
            self.parts_paths = []
        if self.warnings is None:
            self.warnings = []


class FileTypeImporter:
    """
    Main coordinator for importing robot 3D models into UE5.

    This class orchestrates the entire import pipeline:
    1. Format detection
    2. Format conversion (to USD intermediate format)
    3. UE5 import
    4. Content organization
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        enable_hb: bool = False,  # Legacy parameter, kept for backward compatibility
        enable_obs: bool = False,  # Legacy parameter, kept for backward compatibility
    ):
        """
        Initialize the File Type Importer.

        Args:
            config_path: Optional path to configuration directory
            enable_hb: Legacy heartbeat parameter (ignored, for backward compatibility)
            enable_obs: Legacy observability parameter (ignored, for backward compatibility)
        """
        import logging

        self.logger = logging.getLogger(__name__)
        self.format_detector = FormatDetector()
        self.config_path = config_path or self._get_default_config_path()
        self._load_configuration()

        # Log if legacy parameters are used (for debugging)
        if enable_hb or enable_obs:
            self.logger.debug(
                f"Legacy parameters received: enable_hb={enable_hb}, enable_obs={enable_obs} (ignored)"
            )

    def _get_default_config_path(self) -> str:
        """Get the default configuration path."""
        current_dir = Path(__file__).parent.parent.parent
        return str(current_dir / "Config")

    def _load_configuration(self):
        """
        Load configuration files (format mappings, material library, etc.).

        Loads from config_path in order:
        1. import_settings.json - Import behavior settings
        2. format_mappings.json - Custom format→converter mappings
        3. material_library.json - Material presets

        Falls back to defaults if files don't exist.
        """
        import json

        # Default configuration
        self.config = {
            "import": {
                "create_collision": True,
                "combine_meshes": False,
                "scale_factor": 1.0,
                "auto_organize": True,
                "default_physics_type": "kinematic",
                "generate_lods": False,
                "lod_levels": [100, 50, 25],  # Percentages
            },
            "parallel_mechanisms": {
                "mode": "auto",  # auto, split, break, ignore
                "constraint_tolerance": 0.001,
                "prefer_spherical_joints": True,
            },
            "materials": {
                "default_roughness": 0.5,
                "default_metallic": 0.0,
                "use_pbr": True,
            },
            "format_mappings": {},  # Custom format→converter overrides
        }

        config_files = [
            ("import_settings.json", "import"),
            ("parallel_settings.json", "parallel_mechanisms"),
            ("material_library.json", "materials"),
            ("format_mappings.json", "format_mappings"),
        ]

        for filename, config_key in config_files:
            config_file = Path(self.config_path) / filename
            if config_file.exists():
                try:
                    with open(config_file, "r") as f:
                        file_config = json.load(f)
                    if config_key == "format_mappings":
                        self.config[config_key] = file_config
                    else:
                        self.config[config_key].update(file_config)
                    self.logger.debug(f"Loaded config from {filename}")
                except (json.JSONDecodeError, IOError) as e:
                    self.logger.warning(f"Failed to load {filename}: {e}")

        self.logger.info(f"Configuration loaded from {self.config_path}")

    def import_robot(
        self,
        file_path: str,
        robot_name: Optional[str] = None,
        import_mode: str = "both",
        output_path: Optional[str] = None,
        xacro_args: Optional[Dict[str, str]] = None,
    ) -> ImportResult:
        """
        Import a robot model from a 3D file.

        Args:
            file_path: Path to the 3D model file
            robot_name: Name for the robot (auto-generated if not provided)
            import_mode: Import mode - "parts", "assembly", or "both"
            output_path: Optional custom output path in Content Drawer
            xacro_args: Optional dict of XACRO arguments (e.g., {'ur_type': 'ur5'})

        Returns:
            ImportResult with status and details
        """
        # Validate file exists
        if not os.path.exists(file_path):
            return ImportResult(
                success=False,
                robot_name=robot_name or "Unknown",
                error_message=f"File not found: {file_path}",
            )

        # Auto-generate robot name if not provided
        if not robot_name:
            robot_name = self._generate_robot_name(file_path)

        # Detect file format
        try:
            file_format = self.format_detector.detect_format(file_path)
            if not file_format:
                return ImportResult(
                    success=False,
                    robot_name=robot_name,
                    error_message=f"Unknown or unsupported file format: {file_path}",
                )
        except Exception as e:
            return ImportResult(
                success=False,
                robot_name=robot_name,
                error_message=f"Error detecting format: {str(e)}",
            )

        # Convert import mode string to enum
        try:
            mode = ImportMode(import_mode.lower())
        except ValueError:
            return ImportResult(
                success=False,
                robot_name=robot_name,
                error_message=f"Invalid import mode: {import_mode}. Use 'parts', 'assembly', or 'both'",
            )

        # Perform the import
        try:
            result = self._execute_import(
                file_path=file_path,
                file_format=file_format,
                robot_name=robot_name,
                mode=mode,
                output_path=output_path,
                xacro_args=xacro_args,
            )

            # Export metadata for other components if import was successful
            if result.success and hasattr(result, "hierarchy"):
                self._export_metadata_for_integration(result)

            return result

        except Exception as e:
            return ImportResult(
                success=False,
                robot_name=robot_name,
                error_message=f"Import failed: {str(e)}",
            )

    def _generate_robot_name(self, file_path: str) -> str:
        """
        Generate a robot name from the file path.

        Args:
            file_path: Path to the model file

        Returns:
            Generated robot name
        """
        # Use the filename without extension
        return Path(file_path).stem.replace("_", " ").replace("-", " ").title().replace(" ", "")

    def _execute_import(
        self,
        file_path: str,
        file_format: str,
        robot_name: str,
        mode: ImportMode,
        output_path: Optional[str],
        xacro_args: Optional[Dict[str, str]] = None,
    ) -> ImportResult:
        """
        Execute the actual import operation with fallback support.

        Args:
            file_path: Path to the source file
            file_format: Detected format name
            robot_name: Name for the robot
            mode: Import mode enum
            output_path: Optional output path
            xacro_args: Optional dict of XACRO arguments

        Returns:
            ImportResult with operation details
        """
        # Get the appropriate converter
        converter = self._get_converter(file_format)
        if not converter:
            return ImportResult(
                success=False,
                robot_name=robot_name,
                error_message=f"No converter available for format: {file_format}",
            )

        # Determine content path
        if output_path:
            content_path = output_path
        else:
            content_path = f"/Game/Robots/{robot_name}"

        warnings = []

        # Attempt USD conversion
        try:
            conversion_result = self._attempt_conversion(
                file_path=file_path,
                file_format=file_format,
                robot_name=robot_name,
                converter=converter,
                output_path=output_path,  # Pass user's output path
                xacro_args=xacro_args,  # Pass XACRO arguments
            )

            if conversion_result.success:
                # Validate the conversion output
                if hasattr(converter, "validate_output"):
                    if not converter.validate_output(conversion_result.output_path):
                        warnings.append("Conversion validation failed, attempting fallback")
                        return self._fallback_import(
                            file_path, file_format, robot_name, content_path
                        )

                parts_paths = conversion_result.parts
                parts_count = len(conversion_result.parts)
                warnings.extend(conversion_result.warnings)

                return ImportResult(
                    success=True,
                    robot_name=robot_name,
                    content_path=content_path,
                    parts_count=parts_count,
                    assembly_path=conversion_result.output_path,
                    parts_paths=parts_paths,
                    warnings=warnings,
                )
            else:
                # Conversion failed, try fallback
                warnings.append(f"USD conversion failed: {conversion_result.error_message}")
                return self._fallback_import(file_path, file_format, robot_name, content_path)

        except Exception as e:
            warnings.append(f"Conversion error: {str(e)}")
            return self._fallback_import(file_path, file_format, robot_name, content_path)

    def _attempt_conversion(
        self,
        file_path: str,
        file_format: str,
        robot_name: str,
        converter,
        output_path: Optional[str] = None,
        parallel_mode: str = "auto",
        xacro_args: Optional[Dict[str, str]] = None,
    ):
        """
        Attempt to convert the file using the appropriate converter.

        Args:
            file_path: Path to input file
            file_format: Format name
            robot_name: Robot name
            converter: Converter instance
            output_path: Optional user-specified output directory
            parallel_mode: How to handle parallel mechanisms ('auto', 'split', 'break', 'ignore')
            xacro_args: Optional dict of XACRO arguments (e.g., {'ur_type': 'ur5'})

        Returns:
            ConversionResult
        """
        import json
        import os
        import tempfile

        # Use user's output path if provided, otherwise use temp directory
        if output_path:
            # Ensure output directory exists
            os.makedirs(output_path, exist_ok=True)
            usd_output_path = os.path.join(output_path, f"{robot_name}.usd")
            hierarchy_dir = output_path
        else:
            # Fallback to temp directory
            temp_dir = tempfile.gettempdir()
            usd_output_path = os.path.join(temp_dir, f"{robot_name}.usd")
            hierarchy_dir = temp_dir

        self.logger.info(f"Output directory: {os.path.dirname(usd_output_path)}")
        self.logger.info(f"Output USD path: {usd_output_path}")

        # Perform conversion - pass xacro_args if converter supports it
        if hasattr(converter, "convert") and xacro_args:
            # Check if converter accepts xacro_args
            import inspect

            sig = inspect.signature(converter.convert)
            if "xacro_args" in sig.parameters:
                result = converter.convert(
                    file_path, usd_output_path, robot_name, xacro_args=xacro_args
                )
            else:
                result = converter.convert(file_path, usd_output_path, robot_name)
        else:
            result = converter.convert(file_path, usd_output_path, robot_name)

        # Check for parallel mechanisms (closed loops)
        if result.success and hasattr(result, "hierarchy") and result.hierarchy:
            loops = self._detect_closed_loops(result.hierarchy)

            if loops and parallel_mode in ["auto", "split"]:
                self.logger.warning(
                    f"[ParallelMechanism] Detected {len(loops)} closed loop(s). "
                    f"USD Physics doesn't support closed loops - exporting as multi-file assembly."
                )

                # Export as parallel mechanism (multi-file)
                parallel_result = self._export_parallel_mechanism(
                    hierarchy_data=result.hierarchy,
                    output_dir=hierarchy_dir,
                    robot_name=robot_name,
                )

                if parallel_result and parallel_result.get("success"):
                    # Update result with parallel mechanism info
                    result.is_parallel_mechanism = True
                    result.parallel_output = parallel_result
                    result.warnings = result.warnings or []
                    result.warnings.append(
                        f"⚠️ Parallel mechanism detected with {len(loops)} loop(s). "
                        f"Exported as multi-file assembly. "
                        f"Run 'ue5_reconstruct_loops.py' in UE5 after import to enable physics."
                    )
            elif loops and parallel_mode == "break":
                result.warnings = result.warnings or []
                result.warnings.append(
                    f"⚠️ {len(loops)} closed loop(s) detected. "
                    f"USD will break loops at arbitrary points. "
                    f"Physics simulation may be incorrect."
                )

        # Save hierarchy data as JSON for UE5 assembler
        if result.success and hasattr(result, "hierarchy") and result.hierarchy:
            hierarchy_path = os.path.join(hierarchy_dir, f"{robot_name}_hierarchy.json")
            try:
                # Detect submechanisms (kinematic groups)
                submechanisms_data = self._detect_submechanisms(result.hierarchy, robot_name)

                # Enhance joint metadata for physics constraints
                enhanced_joints = self._enhance_joint_metadata(result.hierarchy.get("joints", []))

                # Setup IK manager if available
                ik_info = self._setup_ik_manager(robot_name, submechanisms_data, result.hierarchy)

                hierarchy_data = {
                    "robot_name": robot_name,
                    "source_file": file_path,
                    "export_source": "ROA-FTI",
                    "version": "3.0",  # Version 3.0 includes submechanisms, enhanced joints, IK info
                    "hierarchy": result.hierarchy,
                    # Enhanced joint data with physics constraint parameters
                    "enhanced_joints": enhanced_joints,
                    # Submechanisms for kinematic grouping and IK
                    "submechanisms": submechanisms_data,
                    # IK solver configuration
                    "ik_config": ik_info,
                    # Materials are now included in result.hierarchy:
                    #   - 'materials': dict of material_name -> {'color': [r,g,b,a], 'texture': path}
                    #   - 'link_materials': dict of link_name -> [material_names]
                    # Joints list for physics constraints is in result.hierarchy['joints']:
                    #   - Each joint has: name, type, parent_link, child_link, axis, limits, origin
                }
                with open(hierarchy_path, "w") as f:
                    json.dump(hierarchy_data, f, indent=2)
                # Store the path in result for reference
                result.hierarchy_path = hierarchy_path
                result.submechanisms = submechanisms_data
                result.ik_available = ik_info.get("available", False)
                self.logger.info(f"Saved hierarchy data to: {hierarchy_path}")
                self.logger.info(
                    f"  - Submechanisms: {len(submechanisms_data.get('submechanisms', []))}"
                )
                self.logger.info(f"  - Enhanced joints: {len(enhanced_joints)}")
                self.logger.info(f"  - IK available: {ik_info.get('available', False)}")
            except Exception as e:
                self.logger.warning(f"Failed to save hierarchy JSON: {e}")

        return result

    def _fallback_import(
        self, file_path: str, file_format: str, robot_name: str, content_path: str
    ) -> ImportResult:
        """
        Fallback import method for when USD conversion fails.

        Uses direct import for formats that UE5 can handle natively.

        Args:
            file_path: Path to source file
            file_format: Format name
            robot_name: Robot name
            content_path: Target content path

        Returns:
            ImportResult with fallback status
        """
        # Check if format can be directly imported
        direct_import_formats = ["fbx", "obj", "stl"]

        if file_format in direct_import_formats:
            return ImportResult(
                success=True,
                robot_name=robot_name,
                content_path=content_path,
                parts_count=1,
                assembly_path=file_path,
                parts_paths=[file_path],
                warnings=[
                    f"Using fallback: direct import of {file_format.upper()} file",
                    "USD conversion was skipped or failed",
                ],
            )
        else:
            return ImportResult(
                success=False,
                robot_name=robot_name,
                error_message=f"USD conversion failed and no fallback available for format: {file_format}",
            )

    def _get_converter(self, file_format: str):
        """
        Get the appropriate converter for a file format.

        Uses the centralized CONVERTER_REGISTRY from Converters package
        to ensure consistency across the codebase.

        Args:
            file_format: Name of the format

        Returns:
            Converter instance or None
        """
        # Use the centralized registry from Converters package
        try:
            from .Converters import CONVERTER_REGISTRY, get_converter_class
        except ImportError:
            from Converters import CONVERTER_REGISTRY, get_converter_class

        converter_class = get_converter_class(file_format)
        if converter_class:
            try:
                return converter_class()
            except Exception as e:
                self.logger.error(f"Failed to instantiate {converter_class.__name__}: {e}")
                return None

        self.logger.warning(f"No converter found for format: {file_format}")
        return None

    def batch_import(self, file_paths: List[str], import_mode: str = "both") -> List[ImportResult]:
        """
        Import multiple robot models in batch.

        Args:
            file_paths: List of paths to 3D model files
            import_mode: Import mode for all files

        Returns:
            List of ImportResult objects
        """
        results = []
        for file_path in file_paths:
            result = self.import_robot(file_path=file_path, import_mode=import_mode)
            results.append(result)

        return results

    def get_supported_formats(self) -> List[str]:
        """
        Get list of supported file formats.

        Returns:
            List of format names
        """
        return self.format_detector.get_supported_formats()

    def validate_file(self, file_path: str) -> Dict[str, any]:
        """
        Validate a 3D model file without importing.

        Args:
            file_path: Path to the file

        Returns:
            Validation result dictionary
        """
        if not os.path.exists(file_path):
            return {"valid": False, "error": "File not found"}

        file_format = self.format_detector.detect_format(file_path)
        if not file_format:
            return {"valid": False, "error": "Unknown or unsupported format"}

        return {
            "valid": True,
            "format": file_format,
            "file_size": os.path.getsize(file_path),
            "file_name": os.path.basename(file_path),
        }

    def _export_metadata_for_integration(self, result: ImportResult):
        """
        Export metadata for integration with other ROA components.

        This method prepares data for:
        - DIMC (Dimensions Collector): model hierarchy and parts
        - ROC (Robot Operator Controller): joint definitions
        - Webthread: status and monitoring

        Args:
            result: ImportResult with hierarchy data
        """
        # Store metadata on the result object for access by ROS2 node
        if hasattr(result, "hierarchy"):
            result.metadata_for_dimc = {
                "robot_name": result.robot_name,
                "parts_count": result.parts_count,
                "hierarchy": result.hierarchy,
            }
            result.metadata_for_roc = {
                "robot_name": result.robot_name,
                "joints": [],  # Will be populated from hierarchy
                "hierarchy": result.hierarchy,
            }

    def _detect_closed_loops(self, hierarchy: Dict) -> List[Dict]:
        """
        Detect closed kinematic loops in the robot hierarchy.

        Args:
            hierarchy: Robot hierarchy data with joints

        Returns:
            List of detected loops
        """
        if LoopDetector is None:
            self.logger.debug("LoopDetector not available, skipping loop detection")
            return []

        joints = hierarchy.get("joints", [])
        if not joints:
            return []

        try:
            # LoopDetector.detect_loops is an instance method, not static
            detector = LoopDetector()
            nodes = hierarchy.get("nodes", hierarchy.get("links", {}))
            return detector.detect_loops(joints, nodes)
        except Exception as e:
            self.logger.warning(f"Error detecting closed loops: {e}")
            return []

    def _export_parallel_mechanism(
        self, hierarchy_data: Dict, output_dir: str, robot_name: str
    ) -> Optional[Dict]:
        """
        Export a parallel mechanism as multi-file USD assembly.

        Args:
            hierarchy_data: Robot hierarchy with joints and links
            output_dir: Output directory
            robot_name: Robot name

        Returns:
            Export result or None if failed
        """
        if ParallelMechanismExporter is None:
            self.logger.warning("ParallelMechanismExporter not available")
            return None

        try:
            exporter = ParallelMechanismExporter()
            return exporter.export_parallel_mechanism(
                hierarchy_data=hierarchy_data,
                output_dir=output_dir,
                robot_name=robot_name,
            )
        except Exception as e:
            self.logger.error(f"Failed to export parallel mechanism: {e}")
            return None

    def _detect_submechanisms(self, hierarchy: Dict, robot_name: str) -> Dict:
        """
        Detect submechanisms (kinematic groups) in the robot.

        For serial robots like UR, this identifies the arm as a single serial chain.
        For parallel robots, this identifies independent and coupled groups.

        Args:
            hierarchy: Robot hierarchy data
            robot_name: Robot name

        Returns:
            Submechanism data for hierarchy JSON
        """
        if SubmechanismDetector is None:
            self.logger.debug("SubmechanismDetector not available")
            return {"submechanisms": [], "available": False}

        try:
            # Detect submechanisms from hierarchy
            submechanisms = SubmechanismDetector.detect_submechanisms(hierarchy)

            # Convert to serializable format
            sm_list = []
            for sm in submechanisms:
                sm_data = {
                    "name": sm.name,
                    "type": (sm.type.value if hasattr(sm.type, "value") else str(sm.type)),
                    "joints": sm.joints,
                    "independent_joints": sm.independent_joints,
                    "spanning_tree_joints": sm.spanning_tree_joints,
                    "active_joints": sm.active_joints,
                    "ik_solver_type": sm.ik_solver_type,
                    "has_loop_constraints": len(sm.loop_constraints) > 0,
                    "has_couplings": len(sm.couplings) > 0,
                }
                sm_list.append(sm_data)

            self.logger.info(f"Detected {len(sm_list)} submechanism(s) for {robot_name}")
            for sm in sm_list:
                self.logger.debug(f"  - {sm['name']}: {sm['type']} with {len(sm['joints'])} joints")

            return {
                "submechanisms": sm_list,
                "available": True,
                "robot_type": self._infer_robot_type(sm_list),
            }

        except Exception as e:
            self.logger.warning(f"Error detecting submechanisms: {e}")
            return {"submechanisms": [], "available": False, "error": str(e)}

    def _infer_robot_type(self, submechanisms: List[Dict]) -> str:
        """Infer the overall robot type from submechanisms."""
        if not submechanisms:
            return "unknown"

        types = [sm.get("type", "") for sm in submechanisms]

        if all(t == "serial" for t in types):
            # Check joint count for common robot types
            total_joints = sum(len(sm.get("joints", [])) for sm in submechanisms)
            if total_joints == 6:
                return "6-dof-arm"
            elif total_joints == 7:
                return "7-dof-arm"
            elif total_joints == 4:
                return "scara"
            return "serial-chain"
        elif any(t == "parallel" for t in types):
            return "parallel-mechanism"
        elif any(t == "differential" for t in types):
            return "differential-drive"

        return "hybrid"

    def _enhance_joint_metadata(self, joints: List[Dict]) -> List[Dict]:
        """
        Enhance joint metadata for better physics constraint setup.

        Adds:
        - Constraint type mapping (URDF type → UE5 Physics Constraint)
        - Drive parameters (stiffness, damping)
        - Motion limits in UE5-compatible format
        - Suggested constraint profiles

        Args:
            joints: Original joint list from hierarchy

        Returns:
            Enhanced joint list with physics parameters
        """
        enhanced = []

        # URDF to UE5 constraint mapping
        constraint_mapping = {
            "revolute": {
                "ue5_type": "Hinge",
                "motion": "Angular",
                "locked_axes": ["X", "Y"],  # Only Z (twist) is free
                "default_stiffness": 0.0,  # Free movement
                "default_damping": 10.0,
            },
            "continuous": {
                "ue5_type": "Hinge",
                "motion": "Angular",
                "locked_axes": ["X", "Y"],
                "default_stiffness": 0.0,
                "default_damping": 5.0,
                "unlimited": True,
            },
            "prismatic": {
                "ue5_type": "Slider",
                "motion": "Linear",
                "locked_axes": ["Y", "Z"],  # Only X is free
                "default_stiffness": 0.0,
                "default_damping": 50.0,
            },
            "fixed": {
                "ue5_type": "Fixed",
                "motion": "Locked",
                "locked_axes": ["X", "Y", "Z", "Twist", "Swing1", "Swing2"],
                "default_stiffness": float("inf"),
                "default_damping": 0.0,
            },
            "floating": {
                "ue5_type": "Free",
                "motion": "Free",
                "locked_axes": [],
                "default_stiffness": 0.0,
                "default_damping": 0.0,
            },
            "planar": {
                "ue5_type": "Planar",
                "motion": "Planar",
                "locked_axes": ["Z"],  # Constrained to XY plane
                "default_stiffness": 0.0,
                "default_damping": 10.0,
            },
            "ball": {
                "ue5_type": "BallSocket",
                "motion": "Angular",
                "locked_axes": [],  # All rotations free
                "default_stiffness": 0.0,
                "default_damping": 5.0,
            },
        }

        for joint in joints:
            joint_type = joint.get("type", "fixed").lower()
            mapping = constraint_mapping.get(joint_type, constraint_mapping["fixed"])

            # Get limits - handle None case (fixed joints may have limits=None)
            limits = joint.get("limits") or {}
            lower = limits.get("lower", 0.0) if limits else 0.0
            upper = limits.get("upper", 0.0) if limits else 0.0
            velocity = limits.get("velocity", 1.0) if limits else 1.0
            effort = limits.get("effort", 100.0) if limits else 100.0

            # Get axis
            axis = joint.get("axis", [0, 0, 1])

            # Get origin transform
            origin = joint.get("origin", {"xyz": [0, 0, 0], "rpy": [0, 0, 0]})

            enhanced_joint = {
                # Original data
                "name": joint.get("name"),
                "type": joint_type,
                "parent_link": joint.get("parent_link"),
                "child_link": joint.get("child_link"),
                "axis": axis,
                "origin": origin,
                # UE5 Physics Constraint parameters
                "ue5_constraint": {
                    "type": mapping["ue5_type"],
                    "motion_type": mapping["motion"],
                    "locked_axes": mapping["locked_axes"],
                    # Angular limits (for revolute/continuous)
                    "angular_limits": {
                        "swing1_limit": 0.0,  # Locked
                        "swing2_limit": 0.0,  # Locked
                        "twist_limit_lower": (
                            lower if joint_type in ["revolute", "continuous"] else 0.0
                        ),
                        "twist_limit_upper": (
                            upper if joint_type in ["revolute", "continuous"] else 0.0
                        ),
                        "unlimited_twist": mapping.get("unlimited", False),
                    },
                    # Linear limits (for prismatic)
                    "linear_limits": {
                        "x_limit": upper - lower if joint_type == "prismatic" else 0.0,
                        "y_limit": 0.0,
                        "z_limit": 0.0,
                    },
                    # Drive parameters for motor control
                    "drive": {
                        "enabled": joint_type in ["revolute", "prismatic", "continuous"],
                        "stiffness": mapping["default_stiffness"],
                        "damping": mapping["default_damping"],
                        "max_force": effort,
                        "target_velocity": 0.0,
                        "target_position": 0.0,
                    },
                    # Motor parameters from URDF
                    "motor": {
                        "max_velocity": velocity,
                        "max_effort": effort,
                    },
                },
                # Suggested constraint profile
                "suggested_profile": self._suggest_constraint_profile(joint_type, effort, velocity),
            }

            enhanced.append(enhanced_joint)

        return enhanced

    def _suggest_constraint_profile(self, joint_type: str, effort: float, velocity: float) -> str:
        """Suggest a constraint profile based on joint characteristics."""
        if joint_type == "fixed":
            return "static"
        elif effort > 500:
            return "high_torque"
        elif velocity > 3.0:
            return "high_speed"
        elif joint_type == "continuous":
            return "continuous_rotation"
        else:
            return "standard"

    def _setup_ik_manager(self, robot_name: str, submechanisms_data: Dict, hierarchy: Dict) -> Dict:
        """
        Setup IK manager for the robot.

        Configures IK solvers for each submechanism:
        - MoveIt via ROA Bridge (if available)
        - Local numerical solver (fallback)

        Args:
            robot_name: Robot name
            submechanisms_data: Detected submechanisms
            hierarchy: Robot hierarchy

        Returns:
            IK configuration info
        """
        ik_info = {
            "available": False,
            "solver_type": "none",
            "submechanism_solvers": {},
        }

        if not submechanisms_data.get("available"):
            return ik_info

        submechanisms = submechanisms_data.get("submechanisms", [])
        if not submechanisms:
            return ik_info

        # Check if MoveIt bridge is available
        if ROA_BRIDGE_AVAILABLE and MoveItBridge is not None:
            try:
                # Try to connect to MoveIt
                bridge = MoveItBridge(robot_name=robot_name)
                if bridge.connected:
                    ik_info["available"] = True
                    ik_info["solver_type"] = "moveit"
                    ik_info["bridge_host"] = bridge.bridge_host
                    ik_info["bridge_port"] = bridge.bridge_port

                    for sm in submechanisms:
                        ik_info["submechanism_solvers"][sm["name"]] = "moveit"

                    self.logger.info(f"MoveIt IK available for {robot_name}")
                    return ik_info
            except Exception as e:
                self.logger.debug(f"MoveIt bridge not available: {e}")

        # Fallback to local IK solver
        if IKManager is not None or LocalIKSolver is not None:
            ik_info["available"] = True
            ik_info["solver_type"] = "local_dls"  # Damped Least Squares

            for sm in submechanisms:
                sm_type = sm.get("type", "serial")
                if sm_type == "serial":
                    ik_info["submechanism_solvers"][sm["name"]] = "local_dls"
                else:
                    # Non-serial submechanisms need external solver
                    ik_info["submechanism_solvers"][sm["name"]] = "delegated"

            self.logger.info(f"Local IK solver available for {robot_name}")
        else:
            self.logger.debug("No IK solver available")

        return ik_info
