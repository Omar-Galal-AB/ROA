#!/usr/bin/env python3
"""
ROA Smart Converter - Intelligent Cross-Platform Conversion Flow

This module handles the complete intelligent workflow:
1. Detect input file location (Windows, WSL, Linux native)
2. Convert on Linux (where all dependencies exist)
3. Output to shared location accessible from both platforms
4. Notify UE5 ROA Plugin via WebSocket/TCP

Architecture:
    ┌────────────────────────────────────────────────────────────┐
    │  User drops file ─► ROA detects location ─► Convert       │
    │                                               │             │
    │                                               ▼             │
    │  D:\ROA\Outputs\ ◄── Output ◄── USD + metadata             │
    │        │                                                    │
    │        ▼                                                    │
    │  UE5 ROA Plugin ◄── WebSocket notification with Windows    │
    │                     path for immediate import              │
    └────────────────────────────────────────────────────────────┘
"""

import os
import json
import socket
import threading
from pathlib import Path
from typing import Optional, Dict, Tuple, List, Any
from datetime import datetime
from dataclasses import dataclass, field

# Import path handler
try:
    from .path_handler import ROAPathHandler, get_path_handler, PathInfo, PathType
except ImportError:
    from Utils.path_handler import ROAPathHandler, get_path_handler, PathInfo, PathType


@dataclass
class ConversionJob:
    """Represents a conversion job with all relevant paths."""
    job_id: str
    input_path: str
    input_info: PathInfo
    robot_name: str
    output_dir_linux: str
    output_dir_windows: str
    output_files: Dict[str, Dict[str, str]] = field(default_factory=dict)
    status: str = "pending"
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ROASmartConverter:
    """
    Smart converter that handles cross-platform file operations.
    
    Features:
    - Automatic path detection (Windows/WSL/Linux)
    - Conversion on Linux (with all dependencies)
    - Output to shared location
    - UE5 notification via messaging
    """
    
    # Default output directory (shared between WSL and Windows)
    DEFAULT_OUTPUT_DIR = "/home/D/ROA/Outputs"
    DEFAULT_OUTPUT_DIR_WINDOWS = "D:\\ROA\\Outputs"
    
    # UE5 WebSocket settings
    UE5_WEBSOCKET_HOST = "localhost"
    UE5_WEBSOCKET_PORT = 8765
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        
        # Initialize path handler
        path_config = self.config.get('path_config')
        self.path_handler = get_path_handler(path_config)
        
        # Output directory settings
        self.output_dir_linux = self.config.get(
            'output_dir_linux', 
            self.DEFAULT_OUTPUT_DIR
        )
        self.output_dir_windows = self.config.get(
            'output_dir_windows',
            self.DEFAULT_OUTPUT_DIR_WINDOWS
        )
        
        # Ensure output directory exists
        self._ensure_output_dir()
        
        # WebSocket connection
        self.ue5_host = self.config.get('ue5_host', self.UE5_WEBSOCKET_HOST)
        self.ue5_port = self.config.get('ue5_port', self.UE5_WEBSOCKET_PORT)
        
        # Job tracking
        self.jobs: Dict[str, ConversionJob] = {}
        self._job_counter = 0
        self._lock = threading.Lock()
        
        # Converter reference (set externally)
        self._converter = None
    
    def log(self, message: str, level: str = 'info'):
        """Log with timestamp."""
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        prefix = {
            'info': 'ℹ️', 
            'warning': '⚠️', 
            'error': '❌', 
            'success': '✅',
            'robot': '🤖'
        }.get(level, '')
        print(f"[{timestamp}] SmartConverter {prefix}: {message}", flush=True)
    
    def _ensure_output_dir(self):
        """Ensure output directory exists."""
        try:
            Path(self.output_dir_linux).mkdir(parents=True, exist_ok=True)
            self.log(f"Output directory ready: {self.output_dir_linux}")
        except Exception as e:
            self.log(f"Failed to create output directory: {e}", 'warning')
    
    def _generate_job_id(self) -> str:
        """Generate unique job ID."""
        with self._lock:
            self._job_counter += 1
            return f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self._job_counter}"
    
    def set_converter(self, converter):
        """Set the URDF converter to use."""
        self._converter = converter
    
    def analyze_input(self, input_path: str) -> PathInfo:
        """
        Analyze input path and determine its type.
        
        Args:
            input_path: Path to input file (any format)
            
        Returns:
            PathInfo with all path details
        """
        info = self.path_handler.get_path_info(input_path)
        
        self.log(f"Input analysis:")
        self.log(f"  Original: {input_path}")
        self.log(f"  Type: {info.path_type.value}")
        self.log(f"  Linux path: {info.linux_path}")
        self.log(f"  Windows path: {info.windows_path}")
        
        return info
    
    def prepare_conversion(
        self,
        input_path: str,
        robot_name: Optional[str] = None
    ) -> ConversionJob:
        """
        Prepare a conversion job with all paths resolved.
        
        Args:
            input_path: Path to URDF/XACRO file
            robot_name: Optional robot name (auto-detected if not provided)
            
        Returns:
            ConversionJob ready for execution
        """
        # Analyze input path
        input_info = self.analyze_input(input_path)
        
        # Determine robot name from file if not provided
        if robot_name is None:
            robot_name = Path(input_path).stem
            # Remove common suffixes
            for suffix in ['_description', '_robot', '_urdf', '.urdf']:
                if robot_name.endswith(suffix):
                    robot_name = robot_name[:-len(suffix)]
        
        # Create job
        job = ConversionJob(
            job_id=self._generate_job_id(),
            input_path=input_info.linux_path,  # Always use Linux path for conversion
            input_info=input_info,
            robot_name=robot_name,
            output_dir_linux=self.output_dir_linux,
            output_dir_windows=self.output_dir_windows
        )
        
        # Store job
        self.jobs[job.job_id] = job
        
        self.log(f"Prepared job {job.job_id}:", 'robot')
        self.log(f"  Robot: {robot_name}")
        self.log(f"  Input: {input_info.linux_path}")
        self.log(f"  Output: {self.output_dir_linux}")
        
        return job
    
    def execute_conversion(self, job: ConversionJob) -> ConversionJob:
        """
        Execute the conversion on Linux.
        
        Args:
            job: ConversionJob to execute
            
        Returns:
            Updated ConversionJob with results
        """
        if self._converter is None:
            job.status = "error"
            job.error = "No converter set. Call set_converter() first."
            return job
        
        job.status = "converting"
        job.started_at = datetime.now()
        
        self.log(f"Starting conversion: {job.job_id}", 'robot')
        
        try:
            # Build output path (Linux side)
            output_path = os.path.join(
                job.output_dir_linux,
                f"{job.robot_name}.usd"
            )
            
            # Execute conversion
            result = self._converter.convert(
                input_path=job.input_path,
                output_path=output_path,
                robot_name=job.robot_name
            )
            
            if result.success:
                job.status = "completed"
                job.completed_at = datetime.now()
                
                # Build output file info with both Linux and Windows paths
                job.output_files = self._build_output_info(result, job)
                
                self.log(f"Conversion completed: {job.job_id}", 'success')
                self._log_output_files(job)
                
            else:
                job.status = "error"
                job.error = result.error_message
                self.log(f"Conversion failed: {result.error_message}", 'error')
                
        except Exception as e:
            job.status = "error"
            job.error = str(e)
            self.log(f"Conversion exception: {e}", 'error')
        
        return job
    
    def _build_output_info(
        self, 
        result, 
        job: ConversionJob
    ) -> Dict[str, Dict[str, str]]:
        """Build output file info with Windows and Linux paths."""
        output_files = {}
        
        # Parts file
        if hasattr(result, 'parts_file') and result.parts_file:
            linux_path = result.parts_file
            windows_path = self._to_windows_output(linux_path, job)
            output_files['parts'] = {
                'linux': linux_path,
                'windows': windows_path,
                'description': 'Individual parts for customization'
            }
        
        # Assembled file
        if hasattr(result, 'assembled_file') and result.assembled_file:
            linux_path = result.assembled_file
            windows_path = self._to_windows_output(linux_path, job)
            output_files['assembled'] = {
                'linux': linux_path,
                'windows': windows_path,
                'description': 'Complete robot assembly'
            }
        
        # UE5 script
        if hasattr(result, 'ue5_script') and result.ue5_script:
            linux_path = result.ue5_script
            windows_path = self._to_windows_output(linux_path, job)
            output_files['ue5_script'] = {
                'linux': linux_path,
                'windows': windows_path,
                'description': 'UE5 hierarchy reconstruction script'
            }
        
        # Primary output
        if result.output_path:
            linux_path = result.output_path
            windows_path = self._to_windows_output(linux_path, job)
            output_files['primary'] = {
                'linux': linux_path,
                'windows': windows_path
            }
        
        return output_files
    
    def _to_windows_output(self, linux_path: str, job: ConversionJob) -> str:
        """Convert Linux output path to Windows path."""
        # Get filename from linux path
        filename = os.path.basename(linux_path)
        
        # Build Windows path
        win_sep = '\\'
        return f"{job.output_dir_windows}{win_sep}{filename}"
    
    def _log_output_files(self, job: ConversionJob):
        """Log output files info."""
        for file_type, info in job.output_files.items():
            self.log(f"  [{file_type}]:")
            self.log(f"    Linux:   {info.get('linux', 'N/A')}")
            self.log(f"    Windows: {info.get('windows', 'N/A')}")
    
    def notify_ue5(self, job: ConversionJob) -> bool:
        """
        Notify UE5 ROA Plugin about completed conversion.
        
        Sends a message with Windows-accessible paths so UE5 can
        immediately import the converted files.
        
        Args:
            job: Completed ConversionJob
            
        Returns:
            True if notification was sent successfully
        """
        if job.status != "completed":
            self.log(f"Cannot notify UE5 - job not completed: {job.status}", 'warning')
            return False
        
        notification = {
            'type': 'conversion_complete',
            'source': 'roa_smart_converter',
            'job_id': job.job_id,
            'robot_name': job.robot_name,
            'timestamp': datetime.now().isoformat(),
            'files': {
                name: {
                    'path': info.get('windows', ''),
                    'description': info.get('description', '')
                }
                for name, info in job.output_files.items()
            },
            'primary_file': job.output_files.get('assembled', {}).get('windows', ''),
            'action': 'import_assembled'  # Hint to UE5 plugin
        }
        
        return self._send_to_ue5(notification)
    
    def _send_to_ue5(self, message: Dict) -> bool:
        """
        Send message to UE5 ROA Plugin.
        
        Uses TCP socket to connect to Webthread relay which forwards to UE5.
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((self.ue5_host, self.ue5_port))
            
            data = json.dumps(message) + '\n'
            sock.sendall(data.encode('utf-8'))
            
            sock.close()
            self.log(f"Notified UE5: {message.get('type')}", 'success')
            return True
            
        except Exception as e:
            self.log(f"Failed to notify UE5: {e}", 'warning')
            return False
    
    def smart_convert(
        self,
        input_path: str,
        robot_name: Optional[str] = None,
        notify_ue5: bool = True
    ) -> ConversionJob:
        """
        Complete smart conversion flow.
        
        1. Analyze input path
        2. Prepare conversion job
        3. Execute conversion on Linux
        4. Optionally notify UE5
        
        Args:
            input_path: Path to URDF/XACRO (any format)
            robot_name: Optional robot name
            notify_ue5: Whether to notify UE5 plugin
            
        Returns:
            ConversionJob with full results
        """
        self.log("=" * 60)
        self.log("ROA Smart Conversion Starting", 'robot')
        self.log("=" * 60)
        
        # Step 1: Prepare job
        job = self.prepare_conversion(input_path, robot_name)
        
        # Step 2: Execute conversion
        job = self.execute_conversion(job)
        
        # Step 3: Notify UE5 (if successful and requested)
        if job.status == "completed" and notify_ue5:
            self.notify_ue5(job)
        
        self.log("=" * 60)
        self.log(f"Job {job.job_id} finished with status: {job.status}")
        self.log("=" * 60)
        
        return job
    
    def get_ue5_import_command(self, job: ConversionJob) -> str:
        """
        Get the Python command for UE5 to import the converted robot.
        
        Returns:
            Python command string to execute in UE5 Python console
        """
        if job.status != "completed":
            return "# Job not completed"
        
        assembled_path = job.output_files.get('assembled', {}).get('windows', '')
        if not assembled_path:
            return "# No assembled file found"
        
        # Escape backslashes for Python string
        escaped_path = assembled_path.replace('\\', '\\\\')
        
        return f'''# ROA Smart Import - {job.robot_name}
import unreal

# Import assembled robot
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
import_task = unreal.AssetImportTask()
import_task.filename = "{escaped_path}"
import_task.destination_path = "/Game/Robots/{job.robot_name}"
import_task.automated = True
asset_tools.import_asset_tasks([import_task])

print("Imported: {job.robot_name}")
'''


# Convenience function for direct use
def smart_convert(
    input_path: str,
    robot_name: Optional[str] = None,
    converter = None,
    config: Optional[Dict] = None
) -> ConversionJob:
    """
    Convenience function for smart conversion.
    
    Args:
        input_path: Path to URDF/XACRO
        robot_name: Optional robot name
        converter: URDF converter instance
        config: Optional configuration
        
    Returns:
        ConversionJob with results
    """
    smart_converter = ROASmartConverter(config)
    if converter:
        smart_converter.set_converter(converter)
    return smart_converter.smart_convert(input_path, robot_name)


if __name__ == "__main__":
    # Test the smart converter
    print("🔧 ROA Smart Converter Test")
    print("=" * 60)
    
    converter = ROASmartConverter()
    
    # Test path analysis
    test_paths = [
        "D:\\robots\\ur3.xacro",
        "/mnt/d/robots/ur3.xacro",
        "/home/D/ROA/universal_robot-Examples/ur3.urdf",
        "/opt/ros/humble/share/ur_description/urdf/ur3.urdf"
    ]
    
    for path in test_paths:
        print(f"\nAnalyzing: {path}")
        info = converter.analyze_input(path)
        print(f"  Would use Linux path: {info.linux_path}")
        print(f"  UE5 would receive Windows path: {info.windows_path}")
    
    print("\n" + "=" * 60)
    print("Output directory configuration:")
    print(f"  Linux:   {converter.output_dir_linux}")
    print(f"  Windows: {converter.output_dir_windows}")
