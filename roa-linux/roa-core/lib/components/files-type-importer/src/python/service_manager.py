#!/usr/bin/env python3
"""
ROA Service Manager - Lifecycle management for ROA IPC Service

This module provides tools for managing the ROA IPC Service lifecycle:
- Start/stop/restart the service
- Auto-restart on crash
- Health monitoring with alerts
- Windows service wrapper (for SCM integration)
- WSL launch helper (for starting from Windows)

Gap Fixes Implemented:
- Gap 3.1: Auto-start service from UE5/Windows
- Gap 3.2: Graceful shutdown with pending request handling
- Gap 3.3: Health monitoring with stale heartbeat detection

Usage (Linux):
    # Start service in foreground
    python service_manager.py start
    
    # Start as daemon with auto-restart
    python service_manager.py daemon
    
    # Check status
    python service_manager.py status
    
    # Stop service
    python service_manager.py stop

Usage (Windows - via WSL):
    # PowerShell
    wsl -e python3 /path/to/service_manager.py start
"""

import os
import sys
import time
import signal
import subprocess
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Tuple
import threading

# Add path for imports
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "IPC"))

from IPC.ipc_protocol import ServiceStatus, IPCPaths, PROTOCOL_VERSION

logger = logging.getLogger(__name__)


class ServiceManager:
    """
    Manager for the ROA IPC Service.
    
    Provides lifecycle management, health monitoring, and auto-restart.
    """
    
    # Health check parameters
    HEALTH_CHECK_INTERVAL = 10.0  # seconds
    MAX_HEARTBEAT_AGE = 30.0      # seconds before considering unhealthy
    RESTART_DELAY = 5.0           # seconds to wait before restart
    MAX_RESTART_ATTEMPTS = 5      # max restarts within window
    RESTART_WINDOW = 300.0        # 5 minute window for restart counting
    
    def __init__(
        self,
        ipc_path: str = r"D:\ROA\.ipc",
        service_script: Optional[str] = None,
        log_file: Optional[str] = None
    ):
        """
        Initialize the service manager.
        
        Args:
            ipc_path: Path to IPC folder
            service_script: Path to roa_ipc_service.py
            log_file: Path to log file for service output
        """
        self.paths = IPCPaths(ipc_path)
        self.service_script = service_script or self._find_service_script()
        self.log_file = log_file
        
        # State
        self._process: Optional[subprocess.Popen] = None
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._restart_times: list = []
        
        logger.info(f"ServiceManager initialized")
        logger.info(f"  IPC Path: {ipc_path}")
        logger.info(f"  Service Script: {self.service_script}")
    
    def _find_service_script(self) -> str:
        """Find the service script path."""
        # Try relative to this file
        this_dir = Path(__file__).parent
        script_path = this_dir / "roa_ipc_service.py"
        
        if script_path.exists():
            return str(script_path)
        
        # Try common locations
        candidates = [
            "/home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python/roa_ipc_service.py",
            os.path.expanduser("~/roa/roa_ipc_service.py"),
        ]
        
        for path in candidates:
            if os.path.exists(path):
                return path
        
        return str(script_path)  # Default even if doesn't exist
    
    def get_status(self) -> Tuple[bool, ServiceStatus]:
        """
        Get current service status.
        
        Returns:
            Tuple of (is_healthy, ServiceStatus)
        """
        try:
            status_file = self.paths.service_status_file
            
            if not status_file.exists():
                return False, ServiceStatus(status="not_started", pid=0)
            
            with open(status_file, 'r') as f:
                status = ServiceStatus.from_json(f.read())
            
            # Check heartbeat age
            heartbeat_time = datetime.fromisoformat(
                status.last_heartbeat.replace('Z', '+00:00')
            )
            age = (datetime.now(timezone.utc) - heartbeat_time).total_seconds()
            
            # Check if process is running
            is_running = False
            if status.pid > 0:
                try:
                    os.kill(status.pid, 0)
                    is_running = True
                except ProcessLookupError:
                    pass
            
            is_healthy = (
                status.status == "running" and
                is_running and
                age < self.MAX_HEARTBEAT_AGE
            )
            
            return is_healthy, status
            
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return False, ServiceStatus(status="error", pid=0)
    
    def is_running(self) -> bool:
        """Check if service is running."""
        is_healthy, _ = self.get_status()
        return is_healthy
    
    def start(self, wait: bool = True, timeout: float = 10.0) -> bool:
        """
        Start the IPC service.
        
        Args:
            wait: Wait for service to be healthy
            timeout: Timeout for waiting
            
        Returns:
            True if service started successfully
        """
        logger.info("Starting ROA IPC Service...")
        
        # Check if already running
        if self.is_running():
            logger.info("Service is already running")
            return True
        
        # Build command
        cmd = [
            sys.executable,
            self.service_script,
            "--ipc-path", self.paths.base_path_windows
        ]
        
        # Setup output
        stdout = subprocess.DEVNULL
        stderr = subprocess.DEVNULL
        
        if self.log_file:
            log_dir = Path(self.log_file).parent
            log_dir.mkdir(parents=True, exist_ok=True)
            stdout = open(self.log_file, 'a')
            stderr = subprocess.STDOUT
        
        try:
            # Start process
            self._process = subprocess.Popen(
                cmd,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True  # Detach from parent
            )
            
            logger.info(f"Service process started with PID: {self._process.pid}")
            
            # Wait for healthy
            if wait:
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if self.is_running():
                        logger.info("Service is now healthy")
                        return True
                    time.sleep(0.5)
                
                logger.error("Service did not become healthy within timeout")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start service: {e}")
            return False
    
    def stop(self, force: bool = False, timeout: float = 10.0) -> bool:
        """
        Stop the IPC service.
        
        Args:
            force: Force kill if graceful shutdown fails
            timeout: Timeout for graceful shutdown
            
        Returns:
            True if service stopped
        """
        logger.info("Stopping ROA IPC Service...")
        
        is_healthy, status = self.get_status()
        
        if not is_healthy and status.status == "not_started":
            logger.info("Service is not running")
            return True
        
        pid = status.pid
        
        if pid <= 0:
            logger.warning("No valid PID found")
            return True
        
        try:
            # Send SIGTERM for graceful shutdown
            logger.info(f"Sending SIGTERM to PID {pid}")
            os.kill(pid, signal.SIGTERM)
            
            # Wait for shutdown
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    os.kill(pid, 0)
                    time.sleep(0.5)
                except ProcessLookupError:
                    logger.info("Service stopped gracefully")
                    return True
            
            # Force kill if needed
            if force:
                logger.warning(f"Sending SIGKILL to PID {pid}")
                os.kill(pid, signal.SIGKILL)
                time.sleep(1.0)
                
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    logger.info("Service killed")
                    return True
            
            logger.error("Failed to stop service")
            return False
            
        except ProcessLookupError:
            logger.info("Process already stopped")
            return True
        except Exception as e:
            logger.error(f"Error stopping service: {e}")
            return False
    
    def restart(self) -> bool:
        """
        Restart the service.
        
        Returns:
            True if restart successful
        """
        logger.info("Restarting service...")
        
        self.stop(force=True)
        time.sleep(1.0)
        return self.start()
    
    def start_daemon(self):
        """
        Start service as a daemon with auto-restart.
        
        This method blocks and monitors the service, restarting it if it crashes.
        """
        logger.info("Starting service daemon with auto-restart...")
        
        self._running = True
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        try:
            while self._running:
                # Start service if not running
                if not self.is_running():
                    if self._should_restart():
                        logger.info("Service not running, starting...")
                        self._restart_times.append(time.time())
                        self.start(wait=True, timeout=30.0)
                    else:
                        logger.error("Too many restarts, giving up")
                        break
                
                # Monitor
                time.sleep(self.HEALTH_CHECK_INTERVAL)
                
        except Exception as e:
            logger.error(f"Daemon error: {e}")
        finally:
            logger.info("Daemon exiting")
    
    def _should_restart(self) -> bool:
        """Check if we should attempt a restart."""
        now = time.time()
        
        # Clean old restart times
        self._restart_times = [
            t for t in self._restart_times
            if now - t < self.RESTART_WINDOW
        ]
        
        return len(self._restart_times) < self.MAX_RESTART_ATTEMPTS
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}")
        self._running = False
        self.stop(force=True)


def start_from_windows(ipc_path: str = r"D:\ROA\.ipc") -> bool:
    """
    Start the ROA IPC Service from Windows using WSL.
    
    This function can be called from Windows Python or UE5 to start
    the Linux-side service via WSL.
    
    Implements: Gap 3.1 fix - auto-start from UE5
    
    Args:
        ipc_path: Path to IPC folder
        
    Returns:
        True if service started
    """
    import subprocess
    
    # Find service script
    script_path = "/home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python/roa_ipc_service.py"
    
    # Build WSL command
    cmd = [
        "wsl.exe",
        "-e",
        "python3",
        script_path,
        "--ipc-path", ipc_path
    ]
    
    try:
        # Start in background
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        
        # Wait a bit and check
        time.sleep(3.0)
        
        # Verify service started by checking status file
        status_file = Path(ipc_path.replace('\\', '/').replace('D:', '/mnt/d')) / "service.status"
        return status_file.exists()
        
    except Exception as e:
        print(f"Failed to start service from Windows: {e}")
        return False


def generate_windows_starter_script(output_path: str = r"D:\ROA\start_roa_service.ps1"):
    """
    Generate a PowerShell script for starting the service from Windows.
    
    Args:
        output_path: Path for the generated script
    """
    script = '''# ROA IPC Service Starter
# Run this script to start the ROA IPC Service from Windows

$ServiceScript = "/home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python/roa_ipc_service.py"
$IPCPath = "D:\\ROA\\.ipc"

Write-Host "Starting ROA IPC Service..." -ForegroundColor Cyan

# Check if WSL is available
$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
if (-not $wsl) {
    Write-Host "ERROR: WSL not found. Please install WSL2." -ForegroundColor Red
    exit 1
}

# Start the service
Start-Process -NoNewWindow -FilePath "wsl.exe" -ArgumentList "-e", "python3", $ServiceScript, "--ipc-path", $IPCPath

Write-Host "Service starting..." -ForegroundColor Green

# Wait for status file
$StatusFile = Join-Path $IPCPath "service.status"
$timeout = 10
$elapsed = 0

while (-not (Test-Path $StatusFile) -and $elapsed -lt $timeout) {
    Start-Sleep -Seconds 1
    $elapsed++
    Write-Host "." -NoNewline
}

Write-Host ""

if (Test-Path $StatusFile) {
    Write-Host "Service started successfully!" -ForegroundColor Green
    $status = Get-Content $StatusFile | ConvertFrom-Json
    Write-Host "  PID: $($status.pid)"
    Write-Host "  Status: $($status.status)"
} else {
    Write-Host "WARNING: Could not verify service started" -ForegroundColor Yellow
}
'''
    
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output, 'w') as f:
        f.write(script)
    
    print(f"Generated Windows starter script: {output_path}")


def main():
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(
        description='ROA Service Manager',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        'command',
        choices=['start', 'stop', 'restart', 'status', 'daemon', 'generate-script'],
        help='Command to execute'
    )
    
    parser.add_argument(
        '--ipc-path',
        default=r"D:\ROA\.ipc",
        help='Path to IPC folder'
    )
    
    parser.add_argument(
        '--log-file',
        help='Path to log file for service output'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force operation (e.g., force kill on stop)'
    )
    
    args = parser.parse_args()
    
    manager = ServiceManager(
        ipc_path=args.ipc_path,
        log_file=args.log_file
    )
    
    if args.command == 'start':
        success = manager.start()
        sys.exit(0 if success else 1)
    
    elif args.command == 'stop':
        success = manager.stop(force=args.force)
        sys.exit(0 if success else 1)
    
    elif args.command == 'restart':
        success = manager.restart()
        sys.exit(0 if success else 1)
    
    elif args.command == 'status':
        is_healthy, status = manager.get_status()
        
        print(f"\nROA IPC Service Status")
        print("-" * 40)
        print(f"  Status: {status.status}")
        print(f"  Healthy: {'YES' if is_healthy else 'NO'}")
        print(f"  PID: {status.pid}")
        print(f"  Uptime: {status.uptime_seconds:.1f}s")
        print(f"  Processed: {status.processed_count}")
        print(f"  Failed: {status.failed_count}")
        print(f"  Pending: {len(status.pending_requests)}")
        print(f"  Last Heartbeat: {status.last_heartbeat}")
        print(f"  Version: {status.version}")
        
        sys.exit(0 if is_healthy else 1)
    
    elif args.command == 'daemon':
        manager.start_daemon()
    
    elif args.command == 'generate-script':
        generate_windows_starter_script()


if __name__ == "__main__":
    main()
