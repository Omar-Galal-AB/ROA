#!/usr/bin/env python3
"""
XACRO Processor - Expands XACRO files to URDF using ROS2 xacro package

XACRO files contain macros and parameterization that must be expanded
to produce valid URDF. This processor handles:
- XACRO macro expansion
- Parameter substitution  
- Include resolution
- Conditional blocks
- Custom ROS package path resolution

This runs on Linux/WSL where ROS2 is available.
"""

import os
import sys
import subprocess
import tempfile
import shutil
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Tuple, Callable, List

# Add ROS2 Python packages to path if not already available
# This ensures xacro can be imported even when ROS2 setup.bash isn't sourced
ROS2_PYTHON_PATHS = [
    '/opt/ros/humble/lib/python3.10/site-packages',
    '/opt/ros/humble/local/lib/python3.10/dist-packages',
    '/opt/ros/galactic/lib/python3.8/site-packages',
    '/opt/ros/foxy/lib/python3.8/site-packages',
]

for ros_path in ROS2_PYTHON_PATHS:
    if os.path.exists(ros_path) and ros_path not in sys.path:
        sys.path.insert(0, ros_path)

# Try to import xacro directly (preferred)
try:
    import xacro
    XACRO_AVAILABLE = True
except ImportError:
    XACRO_AVAILABLE = False

# Try ROS2 xacro as fallback
try:
    from ament_index_python.packages import get_package_share_directory
    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False


# Default ROS package search paths - automatically search these locations
DEFAULT_ROS_PACKAGE_PATHS = [
    '/home/myws/ros_packages',           # Custom packages directory
    '/opt/ros/humble/share',              # ROS2 Humble
    '/opt/ros/galactic/share',            # ROS2 Galactic
    '/opt/ros/foxy/share',                # ROS2 Foxy
    '/mnt/c/ros2-windows/share',          # Windows ROS2 via WSL
]


class XacroProcessor:
    """
    Processes XACRO files and expands them to URDF.
    
    Supports multiple backends:
    1. Direct xacro Python module (fastest)
    2. ROS2 xacro command line
    3. Manual XML macro expansion (limited)
    
    Features:
    - Custom ROS package path resolution for $(find package_name)
    - Automatic package discovery in configured directories
    - Support for packages outside standard ROS installation
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.temp_dir = self.config.get('temp_dir', '/tmp/xacro_processing')
        self.progress_callback: Optional[Callable] = None
        self.log_callback: Optional[Callable] = None
        
        # Custom ROS package paths
        self.ros_package_paths: List[str] = self.config.get(
            'ros_package_paths', 
            DEFAULT_ROS_PACKAGE_PATHS.copy()
        )
        
        # Package cache: package_name -> path
        self._package_cache: Dict[str, str] = {}
        
        # Create temp directory
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Detect available backends
        self.backends = self._detect_backends()
        
        # Discover packages in configured paths
        self._discover_packages()
    
    def add_package_path(self, path: str):
        """Add a custom ROS package search path."""
        if path not in self.ros_package_paths:
            self.ros_package_paths.append(path)
            self._discover_packages()
    
    def register_package(self, package_name: str, package_path: str):
        """Manually register a package name to path mapping."""
        self._package_cache[package_name] = package_path
        self._log(f"Registered package: {package_name} -> {package_path}")
    
    def _discover_packages(self):
        """Discover ROS packages in configured search paths."""
        for search_path in self.ros_package_paths:
            if not os.path.exists(search_path):
                continue
            
            # Look for package.xml files (standard ROS package marker)
            for entry in os.listdir(search_path):
                package_dir = os.path.join(search_path, entry)
                if os.path.isdir(package_dir):
                    package_xml = os.path.join(package_dir, 'package.xml')
                    if os.path.exists(package_xml):
                        self._package_cache[entry] = package_dir
                        self._log(f"Discovered package: {entry} at {package_dir}")
    
    def get_package_path(self, package_name: str) -> Optional[str]:
        """Get the path for a ROS package."""
        # Check cache first
        if package_name in self._package_cache:
            return self._package_cache[package_name]
        
        # Try ament_index if available
        if ROS2_AVAILABLE:
            try:
                path = get_package_share_directory(package_name)
                self._package_cache[package_name] = path
                return path
            except:
                pass
        
        # Search in configured paths
        for search_path in self.ros_package_paths:
            candidate = os.path.join(search_path, package_name)
            if os.path.isdir(candidate):
                self._package_cache[package_name] = candidate
                return candidate
        
        return None
    
    def _setup_xacro_substitution_args(self) -> Dict[str, str]:
        """
        Create substitution args for xacro with custom find function.
        This enables $(find package_name) to resolve using our package cache.
        """
        # Set up environment for xacro to find packages
        substitution_args = {}
        
        # Create a custom substitution context
        for pkg_name, pkg_path in self._package_cache.items():
            substitution_args[f'find_{pkg_name}'] = pkg_path
        
        return substitution_args
        
    def _detect_backends(self) -> Dict[str, bool]:
        """Detect which XACRO processing backends are available."""
        backends = {
            'xacro_python': XACRO_AVAILABLE,
            'ros2_command': self._check_ros2_xacro(),
            'subprocess': self._check_subprocess_xacro(),
        }
        self._log(f"Available backends: {backends}")
        return backends
    
    def _check_ros2_xacro(self) -> bool:
        """Check if ROS2 xacro command is available."""
        try:
            result = subprocess.run(
                ['ros2', 'run', 'xacro', 'xacro', '--help'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False
    
    def _check_subprocess_xacro(self) -> bool:
        """Check if xacro can be run as subprocess."""
        try:
            result = subprocess.run(
                ['xacro', '--help'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False
    
    def _log(self, message: str, level: str = 'info'):
        """Log a message."""
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        formatted = f"[{timestamp}] XACRO: {message}"
        print(formatted, flush=True)
        if self.log_callback:
            self.log_callback(message, level)
    
    def _update_progress(self, progress: float, message: str):
        """Update progress (0-100)."""
        self._log(f"Progress {progress:.0f}%: {message}")
        if self.progress_callback:
            self.progress_callback(progress, message)
    
    def process(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        xacro_args: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Process a XACRO file and produce URDF.
        
        Args:
            input_path: Path to input .xacro file
            output_path: Path for output .urdf file (auto-generated if None)
            xacro_args: Arguments to pass to XACRO (e.g., {'robot_name': 'ur5'})
            
        Returns:
            Tuple of (success, message, urdf_content_or_path)
        """
        self._update_progress(0, "Starting XACRO processing")
        
        # Validate input
        input_path = os.path.abspath(input_path)
        if not os.path.exists(input_path):
            return False, f"Input file not found: {input_path}", None
        
        if not input_path.endswith('.xacro'):
            self._log(f"Warning: File does not have .xacro extension: {input_path}", 'warning')
        
        # Generate output path if not provided
        if output_path is None:
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            output_path = os.path.join(self.temp_dir, f"{base_name}.urdf")
        
        output_path = os.path.abspath(output_path)
        self._update_progress(10, "Validated paths")
        
        # Set working directory to input file's directory for includes
        original_cwd = os.getcwd()
        input_dir = os.path.dirname(input_path)
        
        try:
            os.chdir(input_dir)
            self._update_progress(20, "Processing XACRO macros")
            
            # Try backends in order of preference
            if self.backends.get('xacro_python'):
                success, message, content = self._process_with_python_xacro(
                    input_path, output_path, xacro_args
                )
            elif self.backends.get('ros2_command'):
                success, message, content = self._process_with_ros2_command(
                    input_path, output_path, xacro_args
                )
            elif self.backends.get('subprocess'):
                success, message, content = self._process_with_subprocess(
                    input_path, output_path, xacro_args
                )
            else:
                return False, "No XACRO backend available. Install xacro: pip install xacro", None
            
            if success:
                self._update_progress(100, "XACRO processing complete")
            
            return success, message, content
            
        except Exception as e:
            return False, f"XACRO processing error: {str(e)}", None
        finally:
            os.chdir(original_cwd)
    
    def _process_with_python_xacro(
        self,
        input_path: str,
        output_path: str,
        xacro_args: Optional[Dict[str, str]]
    ) -> Tuple[bool, str, Optional[str]]:
        """Process using xacro Python module directly with custom package paths."""
        self._log("Using Python xacro module")
        self._update_progress(40, "Expanding macros with Python xacro")
        
        try:
            # Build mappings for xacro arguments
            mappings = xacro_args or {}
            
            # Import xacro.substitution_args to monkey-patch _eval_find
            import xacro.substitution_args as subst_args
            
            # Store original _eval_find function
            original_eval_find = subst_args._eval_find
            
            # Create custom _eval_find that uses our package cache
            def custom_eval_find(pkg):
                """Custom $(find pkg) resolver that uses our package cache."""
                # First check our custom package cache
                pkg_path = self.get_package_path(pkg)
                if pkg_path:
                    self._log(f"Resolved $(find {pkg}) -> {pkg_path}")
                    return pkg_path
                
                # Fall back to original ament_index resolution
                try:
                    result = original_eval_find(pkg)
                    return result
                except Exception as e:
                    # Provide helpful error with available packages
                    available = list(self._package_cache.keys())
                    raise Exception(
                        f"Package '{pkg}' not found. "
                        f"Available packages: {available[:10]}{'...' if len(available) > 10 else ''}"
                    ) from e
            
            # Monkey-patch the _eval_find function in xacro.substitution_args
            subst_args._eval_find = custom_eval_find
            
            try:
                # Process the XACRO file
                doc = xacro.process_file(input_path, mappings=mappings)
                urdf_content = doc.toprettyxml(indent='  ')
                
                self._update_progress(70, "Writing URDF output")
                
                # Write output file
                with open(output_path, 'w') as f:
                    f.write(urdf_content)
                
                self._update_progress(90, "Validating output")
                
                return True, f"Successfully converted to {output_path}", output_path
                
            finally:
                # Restore original _eval_find function
                subst_args._eval_find = original_eval_find
            
        except Exception as e:
            error_msg = str(e)
            # Provide helpful error message for package not found
            if 'not found' in error_msg.lower() or 'package' in error_msg.lower():
                available_packages = list(self._package_cache.keys())
                error_msg += f"\n\nAvailable packages: {available_packages}"
                error_msg += f"\nSearch paths: {self.ros_package_paths}"
            return False, f"Python xacro error: {error_msg}", None
    
    def _process_with_ros2_command(
        self,
        input_path: str,
        output_path: str,
        xacro_args: Optional[Dict[str, str]]
    ) -> Tuple[bool, str, Optional[str]]:
        """Process using ROS2 xacro command."""
        self._log("Using ROS2 xacro command")
        self._update_progress(40, "Running ros2 run xacro xacro")
        
        try:
            # Build command
            cmd = ['ros2', 'run', 'xacro', 'xacro', input_path, '-o', output_path]
            
            # Add arguments
            if xacro_args:
                for key, value in xacro_args.items():
                    cmd.append(f'{key}:={value}')
            
            # Run command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                return False, f"ROS2 xacro error: {result.stderr}", None
            
            self._update_progress(90, "Validating output")
            
            if os.path.exists(output_path):
                return True, f"Successfully converted to {output_path}", output_path
            else:
                return False, "Output file was not created", None
                
        except subprocess.TimeoutExpired:
            return False, "XACRO processing timed out", None
        except Exception as e:
            return False, f"ROS2 command error: {str(e)}", None
    
    def _process_with_subprocess(
        self,
        input_path: str,
        output_path: str,
        xacro_args: Optional[Dict[str, str]]
    ) -> Tuple[bool, str, Optional[str]]:
        """Process using standalone xacro command."""
        self._log("Using xacro subprocess")
        self._update_progress(40, "Running xacro command")
        
        try:
            # Build command - output to stdout then write
            cmd = ['xacro', input_path]
            
            # Add arguments
            if xacro_args:
                for key, value in xacro_args.items():
                    cmd.append(f'{key}:={value}')
            
            # Run command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                return False, f"xacro error: {result.stderr}", None
            
            self._update_progress(70, "Writing URDF output")
            
            # Write output
            with open(output_path, 'w') as f:
                f.write(result.stdout)
            
            self._update_progress(90, "Validating output")
            
            return True, f"Successfully converted to {output_path}", output_path
            
        except subprocess.TimeoutExpired:
            return False, "XACRO processing timed out", None
        except Exception as e:
            return False, f"Subprocess error: {str(e)}", None
    
    def process_from_content(
        self,
        xacro_content: str,
        robot_name: str,
        xacro_args: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, str, str]:
        """
        Process XACRO content (received over network) and return URDF content.
        
        Args:
            xacro_content: Raw XACRO XML content
            robot_name: Name for temp files
            xacro_args: Arguments to pass to XACRO
            
        Returns:
            Tuple of (success, message, urdf_content)
        """
        # Write to temp file
        temp_xacro = os.path.join(self.temp_dir, f"{robot_name}.xacro")
        with open(temp_xacro, 'w') as f:
            f.write(xacro_content)
        
        # Process
        success, message, output_path = self.process(
            temp_xacro,
            xacro_args=xacro_args
        )
        
        if not success:
            return False, message, ""
        
        # Read result
        with open(output_path, 'r') as f:
            urdf_content = f.read()
        
        return True, message, urdf_content
    
    def cleanup(self):
        """Clean up temporary files."""
        if os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except:
                pass


# Command-line interface for testing or direct use
if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='XACRO to URDF converter')
    parser.add_argument('input', help='Input XACRO file path')
    parser.add_argument('output', nargs='?', help='Output URDF file path (optional)')
    parser.add_argument('--args', nargs='*', help='XACRO arguments as key:=value')
    
    args = parser.parse_args()
    
    # Parse XACRO arguments
    xacro_args = {}
    if args.args:
        for arg in args.args:
            if ':=' in arg:
                key, value = arg.split(':=', 1)
                xacro_args[key] = value
    
    print(f"ROA XACRO Processor: Converting {args.input} to {args.output or 'auto'}")
    
    processor = XacroProcessor()
    success, message, output = processor.process(
        args.input,
        args.output,
        xacro_args if xacro_args else None
    )
    
    if success:
        print(f"✅ {message}")
        sys.exit(0)
    else:
        print(f"❌ Error: {message}")
        sys.exit(1)
