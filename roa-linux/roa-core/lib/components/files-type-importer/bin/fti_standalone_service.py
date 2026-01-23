"""
fti_standalone_service.py
ROA - Robot Operations & Automation

Standalone FTI IPC Service Launcher
Can run independently of the main ROA application.

This allows users to:
1. Start FTI service without launching the full ROA app
2. Use UE5 plugin for conversions without ROA running
3. Use FTI GUI independently

Usage:
    python fti_standalone_service.py [--port 9877] [--ipc-folder /path/to/.ipc]
    
Author: ROA Team
"""

import os
import sys
import argparse
import logging
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

# Add the FTI modules to path
SCRIPT_DIR = Path(__file__).parent.absolute()
FTI_PYTHON_DIR = SCRIPT_DIR.parent / "src" / "python"
if FTI_PYTHON_DIR.exists():
    sys.path.insert(0, str(FTI_PYTHON_DIR))


class FTIStandaloneService:
    """
    Standalone FTI Service Manager
    
    Provides a lightweight way to run the FTI conversion service
    without the full ROA application stack.
    """
    
    DEFAULT_PORT = 9877
    DEFAULT_IPC_FOLDER_LINUX = "/tmp/roa_ipc"
    DEFAULT_IPC_FOLDER_WINDOWS = "D:/ROA/.ipc"
    
    def __init__(self, 
                 port: int = DEFAULT_PORT,
                 ipc_folder: Optional[str] = None,
                 verbose: bool = False):
        """
        Initialize standalone service.
        
        Args:
            port: TCP port for socket-based IPC (not used for file-based IPC)
            ipc_folder: Folder for file-based IPC communication
            verbose: Enable verbose logging
        """
        self.port = port
        self.verbose = verbose
        
        # Determine IPC folder based on platform
        if ipc_folder:
            self.ipc_folder = Path(ipc_folder)
        elif os.name == 'nt':  # Windows
            self.ipc_folder = Path(self.DEFAULT_IPC_FOLDER_WINDOWS)
        else:  # Linux/WSL
            self.ipc_folder = Path(self.DEFAULT_IPC_FOLDER_LINUX)
        
        # Service state
        self.running = False
        self.service_thread: Optional[threading.Thread] = None
        self.service_process: Optional[subprocess.Popen] = None
        
        # Setup logging
        log_level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s [FTI-Standalone] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        self.logger = logging.getLogger(__name__)
    
    def _ensure_ipc_folder(self):
        """Create IPC folder structure if needed."""
        folders = ['requests', 'responses', 'progress', 'status']
        for folder in folders:
            (self.ipc_folder / folder).mkdir(parents=True, exist_ok=True)
        self.logger.info(f"IPC folder ready: {self.ipc_folder}")
    
    def _find_service_script(self) -> Optional[Path]:
        """Find the roa_ipc_service.py script."""
        # Try relative to this script
        candidates = [
            FTI_PYTHON_DIR / "roa_ipc_service.py",
            SCRIPT_DIR / "roa_ipc_service.py",
            SCRIPT_DIR.parent / "src" / "python" / "roa_ipc_service.py",
            Path("/opt/roa/lib/components/files-type-importer/src/python/roa_ipc_service.py"),
        ]
        
        for candidate in candidates:
            if candidate.exists():
                return candidate
        
        return None
    
    def start(self) -> bool:
        """
        Start the standalone FTI service.
        
        Returns:
            True if started successfully
        """
        if self.running:
            self.logger.warning("Service already running")
            return True
        
        self.logger.info("=" * 60)
        self.logger.info("Starting FTI Standalone Service")
        self.logger.info("=" * 60)
        
        # Ensure IPC folder exists
        self._ensure_ipc_folder()
        
        # Find service script
        service_script = self._find_service_script()
        if not service_script:
            self.logger.error("Could not find roa_ipc_service.py")
            return False
        
        self.logger.info(f"Using service script: {service_script}")
        
        # Check if Python is available
        python_cmd = sys.executable
        
        # Build command
        cmd = [
            python_cmd,
            str(service_script),
            "--start",
            "--ipc-folder", str(self.ipc_folder),
        ]
        
        if self.verbose:
            cmd.append("--verbose")
        
        self.logger.info(f"Starting service: {' '.join(cmd)}")
        
        try:
            # Start service process
            self.service_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # Start output monitor thread
            self.service_thread = threading.Thread(
                target=self._monitor_output,
                daemon=True
            )
            self.service_thread.start()
            
            # Give it a moment to start
            time.sleep(1)
            
            if self.service_process.poll() is None:
                self.running = True
                self.logger.info("FTI Service started successfully")
                self.logger.info(f"  PID: {self.service_process.pid}")
                self.logger.info(f"  IPC Folder: {self.ipc_folder}")
                return True
            else:
                self.logger.error(f"Service exited with code: {self.service_process.returncode}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to start service: {e}")
            return False
    
    def _monitor_output(self):
        """Monitor service output and log it."""
        if not self.service_process or not self.service_process.stdout:
            return
        
        for line in iter(self.service_process.stdout.readline, ''):
            if line:
                # Remove trailing newline and log
                self.logger.info(f"[Service] {line.rstrip()}")
            if not self.running:
                break
    
    def stop(self):
        """Stop the FTI service."""
        if not self.running:
            return
        
        self.logger.info("Stopping FTI Service...")
        self.running = False
        
        if self.service_process:
            # Send SIGTERM
            self.service_process.terminate()
            
            # Wait for graceful shutdown
            try:
                self.service_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if needed
                self.service_process.kill()
                self.service_process.wait()
            
            self.logger.info("FTI Service stopped")
    
    def is_running(self) -> bool:
        """Check if service is running."""
        if not self.running or not self.service_process:
            return False
        return self.service_process.poll() is None
    
    def get_status(self) -> dict:
        """Get service status."""
        return {
            "running": self.is_running(),
            "pid": self.service_process.pid if self.service_process else None,
            "ipc_folder": str(self.ipc_folder),
            "port": self.port,
        }
    
    def wait(self):
        """Wait for service to complete."""
        if self.service_process:
            self.service_process.wait()


def create_windows_shortcut(target_dir: str = None):
    """
    Create a Windows shortcut/batch file for easy startup.
    
    Args:
        target_dir: Directory to create shortcut in (default: Desktop)
    """
    if target_dir is None:
        target_dir = Path.home() / "Desktop"
    
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    
    batch_content = f'''@echo off
echo Starting ROA FTI Standalone Service...
echo.
cd /d "{SCRIPT_DIR}"
python fti_standalone_service.py --verbose
pause
'''
    
    batch_file = target_dir / "Start_FTI_Service.bat"
    with open(batch_file, 'w') as f:
        f.write(batch_content)
    
    print(f"Created shortcut: {batch_file}")


def main():
    parser = argparse.ArgumentParser(
        description="ROA FTI Standalone Service - Run conversion service without ROA app"
    )
    
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=FTIStandaloneService.DEFAULT_PORT,
        help=f"Service port (default: {FTIStandaloneService.DEFAULT_PORT})"
    )
    
    parser.add_argument(
        "--ipc-folder", "-i",
        type=str,
        default=None,
        help="IPC folder path (default: platform-specific)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    parser.add_argument(
        "--create-shortcut",
        action="store_true",
        help="Create Windows desktop shortcut and exit"
    )
    
    args = parser.parse_args()
    
    if args.create_shortcut:
        create_windows_shortcut()
        return
    
    # Create and start service
    service = FTIStandaloneService(
        port=args.port,
        ipc_folder=args.ipc_folder,
        verbose=args.verbose
    )
    
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\nShutdown requested...")
        service.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    if service.start():
        print()
        print("=" * 60)
        print("FTI Standalone Service is running")
        print("=" * 60)
        print()
        print("You can now:")
        print("  1. Use the FTI GUI to convert robot files")
        print("  2. Use the UE5 plugin to import robots")
        print("  3. Send IPC requests directly")
        print()
        print("Press Ctrl+C to stop the service")
        print()
        
        # Wait for service
        service.wait()
    else:
        print("Failed to start FTI service")
        sys.exit(1)


if __name__ == "__main__":
    main()
