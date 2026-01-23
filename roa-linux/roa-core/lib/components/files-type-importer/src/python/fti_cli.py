#!/usr/bin/env python3
"""
FTI CLI - Command Line Interface for File Type Importer

Provides standalone conversion capability for 3D robot model files.
Can be run directly without UE5 or the full ROA system.

Usage:
    python fti_cli.py convert input.urdf -o output.usd
    python fti_cli.py convert input.stl -o output.usd --scale 0.001
    python fti_cli.py detect input_file
    python fti_cli.py list-formats
    python fti_cli.py validate input.urdf

Inspired by: onshape-to-robot, phobos CLI
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent))


def get_version():
    """Get FTI version string."""
    return "1.0.0"


def print_header():
    """Print FTI CLI header."""
    print("=" * 60)
    print("  FTI - File Type Importer CLI")
    print(f"  Version: {get_version()}")
    print("  ROA Robotics Framework")
    print("=" * 60)
    print()


def cmd_convert(args):
    """Convert a 3D model file to USD format."""
    from file_type_importer import FileTypeImporter, ImportMode

    print_header()
    print(f"Converting: {args.input}")
    print(f"Output: {args.output or 'auto'}")
    print()

    # Initialize FTI (without HB and observability for CLI mode)
    fti = FileTypeImporter(enable_hb=False, enable_obs=False)

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        input_path = Path(args.input)
        output_path = str(input_path.with_suffix(".usd"))

    # Determine robot name
    robot_name = args.name or Path(args.input).stem.replace("_", "").replace("-", "").title()

    # Perform conversion
    print(f"Robot name: {robot_name}")
    print(f"Import mode: {args.mode}")
    if args.scale != 1.0:
        print(f"Scale factor: {args.scale}")
    print()
    print("Processing...")

    result = fti.import_robot(
        file_path=args.input,
        robot_name=robot_name,
        import_mode=args.mode,
        output_path=output_path,
    )

    if result.success:
        print()
        print("✅ Conversion successful!")
        print(f"   Output: {result.assembly_path or output_path}")
        print(f"   Parts: {result.parts_count}")
        if result.warnings:
            print()
            print("Warnings:")
            for warn in result.warnings:
                print(f"   ⚠️ {warn}")
        return 0
    else:
        print()
        print(f"❌ Conversion failed: {result.error_message}")
        return 1


def cmd_detect(args):
    """Detect the format of a 3D model file."""
    from format_detector import FormatDetector

    print_header()
    print(f"Detecting format: {args.input}")
    print()

    detector = FormatDetector()

    try:
        file_format = detector.detect_format(args.input)
        if file_format:
            print(f"✅ Detected format: {file_format.upper()}")

            # Show additional info
            file_size = os.path.getsize(args.input)
            print(f"   File size: {file_size / 1024:.1f} KB")
            print(f"   Extension: {Path(args.input).suffix}")
        else:
            print("❌ Unknown format")
            return 1
    except FileNotFoundError:
        print(f"❌ File not found: {args.input}")
        return 1
    except Exception as e:
        print(f"❌ Detection error: {e}")
        return 1

    return 0


def cmd_list_formats(args):
    """List all supported file formats."""
    from Converters import CONVERTER_REGISTRY
    from format_detector import FormatDetector

    print_header()
    print("Supported Formats:")
    print()

    detector = FormatDetector()
    formats = detector.FORMAT_EXTENSIONS

    print(f"{'Format':<10} {'Extensions':<25} {'Converter':<15}")
    print("-" * 50)

    for fmt_name, extensions in formats.items():
        ext_str = ", ".join(extensions)
        has_converter = "✅" if fmt_name in CONVERTER_REGISTRY else "❌"
        print(f"{fmt_name.upper():<10} {ext_str:<25} {has_converter:<15}")

    print()
    print("Legend:")
    print("  ✅ = Converter implemented")
    print("  ❌ = Format detected but no converter yet")

    return 0


def cmd_validate(args):
    """Validate a 3D model file without converting."""
    from file_type_importer import FileTypeImporter

    print_header()
    print(f"Validating: {args.input}")
    print()

    fti = FileTypeImporter(enable_hb=False, enable_obs=False)
    result = fti.validate_file(args.input)

    if result["valid"]:
        print("✅ File is valid")
        print(f"   Format: {result['format'].upper()}")
        print(f"   Size: {result['file_size'] / 1024:.1f} KB")
        print(f"   Name: {result['file_name']}")
        return 0
    else:
        print(f"❌ Validation failed: {result['error']}")
        return 1


def cmd_batch(args):
    """Batch convert multiple files."""
    from file_type_importer import FileTypeImporter

    print_header()
    print("Batch Conversion")
    print()

    # Find files matching pattern
    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        print(f"❌ Directory not found: {args.input_dir}")
        return 1

    # Collect files
    patterns = (
        args.patterns.split(",") if args.patterns else ["*.urdf", "*.xacro", "*.stl", "*.obj"]
    )
    files = []
    for pattern in patterns:
        files.extend(input_dir.glob(pattern.strip()))

    if not files:
        print(f"No files found matching patterns: {patterns}")
        return 1

    print(f"Found {len(files)} files to convert")
    print()

    # Setup output directory
    output_dir = Path(args.output_dir) if args.output_dir else input_dir / "converted"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Convert each file
    fti = FileTypeImporter(enable_hb=False, enable_obs=False)

    success_count = 0
    fail_count = 0

    for i, file_path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] Converting: {file_path.name}")

        output_path = str(output_dir / file_path.with_suffix(".usd").name)
        result = fti.import_robot(file_path=str(file_path), output_path=output_path)

        if result.success:
            print(f"         ✅ Success")
            success_count += 1
        else:
            print(f"         ❌ Failed: {result.error_message}")
            fail_count += 1

    print()
    print("=" * 40)
    print(f"Results: {success_count} success, {fail_count} failed")

    return 0 if fail_count == 0 else 1


def cmd_server(args):
    """Start FTI server for standalone operation."""
    print_header()
    print(f"Starting FTI Server on port {args.port}...")

    try:
        from fti_server import FTIServer

        server = FTIServer(port=args.port)
        server.serve()
    except ImportError:
        print("FTI Server module not available. Creating minimal server...")
        # Minimal HTTP server for conversion requests
        from fti_server import create_minimal_server

        create_minimal_server(args.port)
    except KeyboardInterrupt:
        print("\nServer stopped.")

    return 0


def cmd_info(args):
    """Show FTI system information."""
    print_header()
    print("System Information:")
    print()

    # Check Python version
    print(f"Python: {sys.version}")
    print()

    # Check dependencies
    print("Dependencies:")
    deps = [
        ("trimesh", "Mesh processing"),
        ("pxr", "OpenUSD (Pixar)"),
        ("xacro", "XACRO expansion"),
        ("numpy", "Numerical operations"),
    ]

    for module, desc in deps:
        try:
            mod = __import__(module)
            version = getattr(mod, "__version__", "installed")
            print(f"  ✅ {module}: {version} - {desc}")
        except ImportError:
            print(f"  ❌ {module}: NOT INSTALLED - {desc}")

    print()

    # Check FTI components
    print("FTI Components:")
    components = [
        ("file_type_importer", "FileTypeImporter", "Main coordinator"),
        ("format_detector", "FormatDetector", "Format detection"),
        ("Converters.urdf_converter", "URDFConverter", "URDF conversion"),
        ("Converters.stl_converter", "STLConverter", "STL conversion"),
        ("Converters.obj_converter", "OBJConverter", "OBJ conversion"),
        ("xacro_processor", "XacroProcessor", "XACRO expansion"),
    ]

    for module, cls, desc in components:
        try:
            mod = __import__(module, fromlist=[cls])
            print(f"  ✅ {cls}: {desc}")
        except ImportError as e:
            print(f"  ❌ {cls}: {e}")

    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="fti",
        description="FTI - File Type Importer: Convert 3D robot models to USD format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  fti convert robot.urdf -o robot.usd          Convert URDF to USD
  fti convert robot.xacro -o robot.usd         Convert XACRO to USD
  fti convert mesh.stl -o mesh.usd --scale 0.001   Convert STL with scaling
  fti detect input_file                        Detect file format
  fti list-formats                             Show supported formats
  fti validate robot.urdf                      Validate a file
  fti batch ./robots -o ./output               Batch convert directory
  fti server --port 9877                       Start conversion server
  fti info                                     Show system information
        """,
    )

    parser.add_argument("--version", action="version", version=f"FTI {get_version()}")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Convert command
    convert_parser = subparsers.add_parser("convert", help="Convert a 3D model file to USD")
    convert_parser.add_argument("input", help="Input file path")
    convert_parser.add_argument(
        "-o", "--output", help="Output file path (default: same name with .usd)"
    )
    convert_parser.add_argument("-n", "--name", help="Robot name (default: from filename)")
    convert_parser.add_argument(
        "-m",
        "--mode",
        choices=["parts", "assembly", "both"],
        default="both",
        help="Import mode (default: both)",
    )
    convert_parser.add_argument(
        "--scale", type=float, default=1.0, help="Scale factor (default: 1.0)"
    )
    convert_parser.set_defaults(func=cmd_convert)

    # Detect command
    detect_parser = subparsers.add_parser("detect", help="Detect file format")
    detect_parser.add_argument("input", help="Input file path")
    detect_parser.set_defaults(func=cmd_detect)

    # List formats command
    list_parser = subparsers.add_parser("list-formats", help="List supported formats")
    list_parser.set_defaults(func=cmd_list_formats)

    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate a 3D model file")
    validate_parser.add_argument("input", help="Input file path")
    validate_parser.set_defaults(func=cmd_validate)

    # Batch command
    batch_parser = subparsers.add_parser("batch", help="Batch convert multiple files")
    batch_parser.add_argument("input_dir", help="Input directory")
    batch_parser.add_argument(
        "-o", "--output-dir", help="Output directory (default: input_dir/converted)"
    )
    batch_parser.add_argument(
        "-p", "--patterns", help="File patterns (default: *.urdf,*.xacro,*.stl,*.obj)"
    )
    batch_parser.set_defaults(func=cmd_batch)

    # Server command
    server_parser = subparsers.add_parser("server", help="Start FTI conversion server")
    server_parser.add_argument("--port", type=int, default=9877, help="Server port (default: 9877)")
    server_parser.set_defaults(func=cmd_server)

    # Info command
    info_parser = subparsers.add_parser("info", help="Show system information")
    info_parser.set_defaults(func=cmd_info)

    # Parse arguments
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    # Execute command
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
