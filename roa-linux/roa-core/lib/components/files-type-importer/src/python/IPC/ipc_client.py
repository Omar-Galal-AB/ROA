#!/usr/bin/env python3
"""
ROA IPC Client - Client for submitting conversion requests

This module provides a client interface for submitting requests to the
ROA IPC Service and monitoring progress/responses.

Can be used from:
- Python scripts on Windows (direct file access)
- UE5 Python scripts (via Unreal Python)
- Command line tools
- Test scripts

Features:
- Submit conversion requests
- Monitor progress with callbacks
- Wait for completion with timeout
- Service health checking
- Auto-start service (optional)

Gap Fixes Implemented:
- Gap 1.4: Request acknowledgement checking
- Gap 3.1: Auto-start service option
- Gap 4.2: Client-side timeout handling
- Gap 8.3: Progress monitoring for UI

Usage:
    from IPC.ipc_client import ROAIPCClient
    
    # Create client
    client = ROAIPCClient()
    
    # Check service health
    if not client.is_service_running():
        client.start_service()
    
    # Submit conversion request
    request_id = client.submit_conversion(
        input_path=r"D:\\Robots\\ur3.xacro",
        output_directory=r"D:\\ROA\\Outputs",
        name_prefix="ur3_robot"
    )
    
    # Wait for completion with progress callback
    response = client.wait_for_response(
        request_id,
        timeout_seconds=60,
        progress_callback=lambda p: print(f"{p.percent}%: {p.stage}")
    )
    
    if response.success:
        print(f"Converted! USD at: {response.outputs['assembled_usd']['windows_path']}")
    else:
        print(f"Failed: {response.error['message']}")
"""

import os
import sys
import json
import time
import subprocess
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Callable, Dict, Any, Tuple
from dataclasses import dataclass

# Add parent for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from .ipc_protocol import (
    IPCRequest, IPCResponse, IPCProgress, ServiceStatus, IPCPaths,
    ConversionOptions, write_request, PROTOCOL_VERSION
)

logger = logging.getLogger(__name__)


@dataclass
class ServiceInfo:
    """Information about the IPC service."""
    is_running: bool
    status: str
    pid: int
    uptime_seconds: float
    processed_count: int
    failed_count: int
    pending_count: int
    last_heartbeat: Optional[datetime]
    is_healthy: bool  # True if heartbeat is recent


class ROAIPCClient:
    """
    Client for interacting with the ROA IPC Service.
    
    This client can be used from Windows or Linux to submit
    conversion requests and monitor progress.
    """
    
    # Maximum age of heartbeat before considering service unhealthy
    MAX_HEARTBEAT_AGE_SECONDS = 15.0
    
    # Polling interval for progress/response checks
    POLL_INTERVAL = 0.25  # 250ms
    
    def __init__(
        self,
        ipc_path: str = r"D:\ROA\.ipc",
        auto_start: bool = False,
        service_script_path: Optional[str] = None
    ):
        """
        Initialize the IPC client.
        
        Args:
            ipc_path: Path to IPC folder (Windows format)
            auto_start: Automatically start service if not running
            service_script_path: Path to roa_ipc_service.py (for auto-start)
        """
        self.paths = IPCPaths(ipc_path)
        self.auto_start = auto_start
        self.service_script_path = service_script_path or self._find_service_script()
        
        # Detect platform
        self._is_windows = os.name == 'nt'
        
        logger.info(f"ROAIPCClient initialized (Windows: {self._is_windows})")
        logger.info(f"  IPC Path: {ipc_path}")
    
    def _find_service_script(self) -> str:
        """Find the service script path."""
        # Try common locations
        candidates = [
            "/home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python/roa_ipc_service.py",
            "~/roa/roa_ipc_service.py",
        ]
        
        for path in candidates:
            expanded = os.path.expanduser(path)
            if os.path.exists(expanded):
                return expanded
        
        return candidates[0]  # Default
    
    def get_service_info(self) -> ServiceInfo:
        """
        Get information about the IPC service.
        
        Returns:
            ServiceInfo with current service state
        """
        try:
            status_file = self.paths.service_status_file
            
            if not status_file.exists():
                return ServiceInfo(
                    is_running=False,
                    status="not_started",
                    pid=0,
                    uptime_seconds=0,
                    processed_count=0,
                    failed_count=0,
                    pending_count=0,
                    last_heartbeat=None,
                    is_healthy=False
                )
            
            with open(status_file, 'r') as f:
                status = ServiceStatus.from_json(f.read())
            
            # Parse heartbeat time
            last_heartbeat = datetime.fromisoformat(
                status.last_heartbeat.replace('Z', '+00:00')
            )
            
            # Check if healthy (recent heartbeat)
            age = (datetime.now(timezone.utc) - last_heartbeat).total_seconds()
            is_healthy = age < self.MAX_HEARTBEAT_AGE_SECONDS
            
            # Check if process is still running (on Linux)
            if not self._is_windows and status.pid > 0:
                try:
                    os.kill(status.pid, 0)
                except ProcessLookupError:
                    is_healthy = False
            
            return ServiceInfo(
                is_running=status.status == "running" and is_healthy,
                status=status.status,
                pid=status.pid,
                uptime_seconds=status.uptime_seconds,
                processed_count=status.processed_count,
                failed_count=status.failed_count,
                pending_count=len(status.pending_requests),
                last_heartbeat=last_heartbeat,
                is_healthy=is_healthy
            )
        except Exception as e:
            logger.error(f"Error getting service info: {e}")
            return ServiceInfo(
                is_running=False,
                status="error",
                pid=0,
                uptime_seconds=0,
                processed_count=0,
                failed_count=0,
                pending_count=0,
                last_heartbeat=None,
                is_healthy=False
            )
    
    def is_service_running(self) -> bool:
        """Check if the IPC service is running and healthy."""
        return self.get_service_info().is_running
    
    def start_service(self, wait_timeout: float = 10.0) -> bool:
        """
        Start the IPC service.
        
        Implements: Gap 3.1 fix - auto-start from client
        
        Args:
            wait_timeout: Seconds to wait for service to start
            
        Returns:
            True if service started successfully
        """
        logger.info("Starting IPC service...")
        
        if self.is_service_running():
            logger.info("Service already running")
            return True
        
        try:
            if self._is_windows:
                # On Windows, start via WSL
                cmd = [
                    "wsl.exe",
                    "-e",
                    "python3",
                    self.service_script_path
                ]
            else:
                # On Linux, start directly
                cmd = [
                    "python3",
                    self.service_script_path
                ]
            
            # Start in background
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            
            # Wait for service to be ready
            start_time = time.time()
            while time.time() - start_time < wait_timeout:
                if self.is_service_running():
                    logger.info("Service started successfully")
                    return True
                time.sleep(0.5)
            
            logger.error("Service did not start within timeout")
            return False
            
        except Exception as e:
            logger.error(f"Failed to start service: {e}")
            return False
    
    def submit_conversion(
        self,
        input_path: str,
        output_directory: str,
        name_prefix: str,
        options: Optional[ConversionOptions] = None,
        timeout_ms: int = 60000
    ) -> str:
        """
        Submit a conversion request.
        
        Args:
            input_path: Path to input file (URDF, XACRO, etc.)
            output_directory: Directory for output files
            name_prefix: Prefix for output filenames
            options: Conversion options
            timeout_ms: Request timeout in milliseconds
            
        Returns:
            Request ID (UUID string)
            
        Raises:
            RuntimeError: If service is not running and auto_start is False
        """
        # Check service
        if not self.is_service_running():
            if self.auto_start:
                if not self.start_service():
                    raise RuntimeError("Failed to start IPC service")
            else:
                raise RuntimeError("IPC service is not running")
        
        # Create request
        request = IPCRequest.create_convert_request(
            input_path=input_path,
            output_directory=output_directory,
            name_prefix=name_prefix,
            options=options
        )
        request.timeout_ms = timeout_ms
        
        # Write request
        if not write_request(self.paths, request):
            raise RuntimeError("Failed to write request file")
        
        logger.info(f"Submitted request: {request.request_id}")
        return request.request_id
    
    def wait_for_ack(
        self,
        request_id: str,
        timeout_seconds: float = 5.0
    ) -> bool:
        """
        Wait for request acknowledgement.
        
        Implements: Gap 1.4 fix - request acknowledgement
        
        Args:
            request_id: Request ID to wait for
            timeout_seconds: Maximum wait time
            
        Returns:
            True if acknowledged within timeout
        """
        ack_path = self.paths.get_ack_path(request_id)
        start_time = time.time()
        
        while time.time() - start_time < timeout_seconds:
            if ack_path.exists():
                logger.debug(f"Request {request_id} acknowledged")
                return True
            time.sleep(self.POLL_INTERVAL)
        
        logger.warning(f"Request {request_id} not acknowledged within {timeout_seconds}s")
        return False
    
    def get_progress(self, request_id: str) -> Optional[IPCProgress]:
        """
        Get current progress for a request.
        
        Args:
            request_id: Request ID
            
        Returns:
            IPCProgress if available, None otherwise
        """
        try:
            progress_path = self.paths.get_progress_path(request_id)
            
            if not progress_path.exists():
                return None
            
            with open(progress_path, 'r') as f:
                return IPCProgress(**json.load(f))
        except Exception as e:
            logger.debug(f"Could not read progress: {e}")
            return None
    
    def get_response(self, request_id: str) -> Optional[IPCResponse]:
        """
        Get response for a request (non-blocking).
        
        Args:
            request_id: Request ID
            
        Returns:
            IPCResponse if available, None otherwise
        """
        try:
            response_path = self.paths.get_response_path(request_id)
            
            if not response_path.exists():
                return None
            
            with open(response_path, 'r') as f:
                return IPCResponse.from_json(f.read())
        except Exception as e:
            logger.error(f"Could not read response: {e}")
            return None
    
    def wait_for_response(
        self,
        request_id: str,
        timeout_seconds: float = 60.0,
        progress_callback: Optional[Callable[[IPCProgress], None]] = None,
        poll_interval: float = None
    ) -> Optional[IPCResponse]:
        """
        Wait for response with optional progress updates.
        
        Implements: Gap 8.3 fix - progress monitoring
        
        Args:
            request_id: Request ID to wait for
            timeout_seconds: Maximum wait time
            progress_callback: Optional callback for progress updates
            poll_interval: Polling interval (default: 0.25s)
            
        Returns:
            IPCResponse if received, None on timeout
        """
        poll_interval = poll_interval or self.POLL_INTERVAL
        start_time = time.time()
        last_progress_percent = -1
        
        # First wait for ack
        if not self.wait_for_ack(request_id, timeout_seconds=5.0):
            logger.warning("Request not acknowledged, service may be down")
            # Continue anyway in case ack was missed
        
        while time.time() - start_time < timeout_seconds:
            # Check for response
            response = self.get_response(request_id)
            if response is not None:
                logger.info(f"Received response for {request_id}")
                return response
            
            # Check progress
            if progress_callback:
                progress = self.get_progress(request_id)
                if progress and progress.percent != last_progress_percent:
                    last_progress_percent = progress.percent
                    try:
                        progress_callback(progress)
                    except Exception as e:
                        logger.warning(f"Progress callback error: {e}")
            
            time.sleep(poll_interval)
        
        logger.error(f"Timeout waiting for response: {request_id}")
        return None
    
    def convert_and_wait(
        self,
        input_path: str,
        output_directory: str,
        name_prefix: str,
        options: Optional[ConversionOptions] = None,
        timeout_seconds: float = 60.0,
        progress_callback: Optional[Callable[[IPCProgress], None]] = None
    ) -> IPCResponse:
        """
        Convenience method: submit and wait for result.
        
        Args:
            input_path: Path to input file
            output_directory: Output directory
            name_prefix: Output filename prefix
            options: Conversion options
            timeout_seconds: Maximum wait time
            progress_callback: Progress callback
            
        Returns:
            IPCResponse with result or error
        """
        try:
            request_id = self.submit_conversion(
                input_path=input_path,
                output_directory=output_directory,
                name_prefix=name_prefix,
                options=options,
                timeout_ms=int(timeout_seconds * 1000)
            )
            
            response = self.wait_for_response(
                request_id=request_id,
                timeout_seconds=timeout_seconds,
                progress_callback=progress_callback
            )
            
            if response is None:
                # Create timeout response
                from .ipc_protocol import ErrorCode
                return IPCResponse.create_error(
                    request_id=request_id,
                    error_code=ErrorCode.TIMEOUT,
                    message=f"Request timed out after {timeout_seconds}s"
                )
            
            return response
            
        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            from .ipc_protocol import ErrorCode
            return IPCResponse.create_error(
                request_id="unknown",
                error_code=ErrorCode.INTERNAL_ERROR,
                message=str(e)
            )
    
    def health_check(self) -> Tuple[bool, Dict[str, Any]]:
        """
        Perform a health check on the service.
        
        Returns:
            Tuple of (is_healthy, details_dict)
        """
        info = self.get_service_info()
        
        details = {
            'running': info.is_running,
            'healthy': info.is_healthy,
            'status': info.status,
            'pid': info.pid,
            'uptime_seconds': info.uptime_seconds,
            'processed_count': info.processed_count,
            'failed_count': info.failed_count,
            'pending_count': info.pending_count,
            'last_heartbeat': info.last_heartbeat.isoformat() if info.last_heartbeat else None,
            'protocol_version': PROTOCOL_VERSION
        }
        
        return info.is_healthy, details


# UE5-specific client wrapper
class UE5IPCClient(ROAIPCClient):
    """
    UE5-specific IPC client with Unreal Engine integration.
    
    Designed to be used from UE5 Python scripts.
    """
    
    def __init__(self, ipc_path: str = r"D:\ROA\.ipc"):
        super().__init__(ipc_path=ipc_path, auto_start=True)
    
    def convert_for_ue5(
        self,
        input_path: str,
        output_directory: str,
        name_prefix: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Convert a robot file for UE5 import.
        
        Args:
            input_path: Path to input file
            output_directory: Output directory
            name_prefix: Output filename prefix
            progress_callback: Callback with (percent, stage) args
            
        Returns:
            Dict with 'success', 'outputs', 'error' keys
        """
        def _progress_adapter(progress: IPCProgress):
            if progress_callback:
                progress_callback(progress.percent, progress.stage)
        
        response = self.convert_and_wait(
            input_path=input_path,
            output_directory=output_directory,
            name_prefix=name_prefix,
            progress_callback=_progress_adapter
        )
        
        return {
            'success': response.success,
            'outputs': response.outputs,
            'metadata': response.metadata,
            'error': response.error
        }
    
    def get_usd_paths(self, response_outputs: Dict) -> Dict[str, str]:
        """
        Extract Windows paths from response outputs.
        
        Args:
            response_outputs: The 'outputs' dict from response
            
        Returns:
            Dict mapping output type to Windows path
        """
        paths = {}
        for name, info in response_outputs.items():
            if isinstance(info, dict) and 'windows_path' in info:
                paths[name] = info['windows_path']
        return paths


if __name__ == "__main__":
    # Test the client
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(description='ROA IPC Client')
    parser.add_argument('--status', action='store_true', help='Show service status')
    parser.add_argument('--start', action='store_true', help='Start service')
    parser.add_argument('--convert', help='Path to file to convert')
    parser.add_argument('--output', default=r"D:\ROA\Outputs", help='Output directory')
    parser.add_argument('--name', default="robot", help='Output name prefix')
    
    args = parser.parse_args()
    
    client = ROAIPCClient()
    
    if args.status:
        is_healthy, details = client.health_check()
        print(f"\nService Status: {'HEALTHY' if is_healthy else 'UNHEALTHY'}")
        print("-" * 40)
        for key, value in details.items():
            print(f"  {key}: {value}")
    
    elif args.start:
        if client.start_service():
            print("Service started successfully")
        else:
            print("Failed to start service")
            sys.exit(1)
    
    elif args.convert:
        print(f"\nConverting: {args.convert}")
        print(f"Output: {args.output}")
        print(f"Name: {args.name}")
        print("-" * 40)
        
        def progress_cb(p: IPCProgress):
            print(f"  [{p.percent:5.1f}%] {p.stage}")
        
        response = client.convert_and_wait(
            input_path=args.convert,
            output_directory=args.output,
            name_prefix=args.name,
            progress_callback=progress_cb
        )
        
        print("-" * 40)
        if response.success:
            print("SUCCESS!")
            print("\nOutputs:")
            for name, info in response.outputs.items():
                print(f"  {name}: {info.get('windows_path', info)}")
        else:
            print("FAILED!")
            print(f"  Error: {response.error}")
    
    else:
        parser.print_help()
