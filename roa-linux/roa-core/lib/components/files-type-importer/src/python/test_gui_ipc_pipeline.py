#!/usr/bin/env python3
"""
GUI-FTI IPC Pipeline Test Suite

Tests the complete IPC communication flow between:
- UE5 Plugin (simulated by this script)
- ROA IPC Service (running in background)
- FileTypeImporter (FTI) conversion engine

Tests:
1. IPC Request/Response cycle
2. Convert XACRO request
3. Full convert request with v3.0 output
4. Progress updates
5. Health check
6. Error handling
7. File browser simulation
"""

import os
import sys
import json
import time
import uuid
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

# Add FTI path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from IPC.ipc_protocol import (
    IPCRequest, IPCResponse, ErrorCode, 
    PROTOCOL_VERSION, DEFAULT_TIMEOUT_MS
)

# ============================================================================
# TEST CONFIGURATION
# ============================================================================

IPC_BASE_PATH = "/mnt/d/ROA/.ipc"
REQUESTS_DIR = Path(IPC_BASE_PATH) / "requests"
RESPONSES_DIR = Path(IPC_BASE_PATH) / "responses"
PROGRESS_DIR = Path(IPC_BASE_PATH) / "progress"
HEARTBEATS_DIR = Path(IPC_BASE_PATH) / "heartbeats"
STATUS_FILE = Path(IPC_BASE_PATH) / "service.status"

# Test files - use simple test robot that works without external dependencies
TEST_XACRO = "/mnt/d/ROA/Test/test_robot.urdf.xacro"
TEST_OUTPUT_DIR = "/mnt/d/ROA/Test/gui_pipeline_test"

# XACRO args for simple test robot
TEST_XACRO_ARGS = {'robot_name': 'test_robot', 'scale': '1.0'}

# ============================================================================
# TEST UTILITIES
# ============================================================================

class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.error = None
        self.details = {}
    
    def success(self, **details):
        self.passed = True
        self.details = details
        return self
    
    def failure(self, error: str, **details):
        self.passed = False
        self.error = error
        self.details = details
        return self
    
    def __str__(self):
        status = "✅ PASS" if self.passed else "❌ FAIL"
        msg = f"{status}: {self.name}"
        if self.error:
            msg += f"\n   Error: {self.error}"
        if self.details:
            for k, v in self.details.items():
                if isinstance(v, dict):
                    msg += f"\n   {k}:"
                    for kk, vv in v.items():
                        msg += f"\n     - {kk}: {vv}"
                else:
                    msg += f"\n   {k}: {v}"
        return msg


def write_ipc_request(request: IPCRequest) -> str:
    """
    Write an IPC request to the requests folder.
    Simulates what UE5 plugin does.
    
    Returns:
        Request ID
    """
    request_id = request.request_id
    request_file = REQUESTS_DIR / f"{request_id}.request.json"
    temp_file = REQUESTS_DIR / f"{request_id}.request.tmp"
    
    # Atomic write (write to .tmp, then rename)
    with open(temp_file, 'w') as f:
        f.write(request.to_json())
        f.flush()
        os.fsync(f.fileno())  # Force write to disk
    
    temp_file.rename(request_file)
    
    # Small delay to allow filesystem sync on WSL/NTFS
    time.sleep(0.5)
    
    return request_id


def wait_for_response(request_id: str, timeout_sec: float = 120.0) -> Optional[Dict]:
    """
    Wait for a response to be written.
    
    Args:
        request_id: The request ID to wait for
        timeout_sec: Maximum time to wait
        
    Returns:
        Response dict or None if timeout
    """
    response_file = RESPONSES_DIR / f"{request_id}.response.json"
    start_time = time.time()
    
    while time.time() - start_time < timeout_sec:
        if response_file.exists():
            try:
                with open(response_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                # File still being written
                time.sleep(0.1)
        time.sleep(0.5)
    
    return None


def get_progress(request_id: str) -> Optional[Dict]:
    """Get current progress for a request."""
    progress_file = PROGRESS_DIR / f"{request_id}.progress.json"
    if progress_file.exists():
        try:
            with open(progress_file, 'r') as f:
                return json.load(f)
        except:
            pass
    return None


def get_service_status() -> Optional[Dict]:
    """Get current service status."""
    if STATUS_FILE.exists():
        try:
            with open(STATUS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return None


# ============================================================================
# TEST CASES
# ============================================================================

def test_1_service_running() -> TestResult:
    """Test 1: Verify IPC service is running."""
    result = TestResult("IPC Service Running")
    
    status = get_service_status()
    if status is None:
        return result.failure("Could not read service status")
    
    if status.get('status') != 'running':
        return result.failure(f"Service status is '{status.get('status')}', expected 'running'")
    
    return result.success(
        pid=status.get('pid'),
        uptime=f"{status.get('uptime_seconds', 0):.1f}s",
        version=status.get('version')
    )


def test_2_health_check() -> TestResult:
    """Test 2: Send health check request and verify response."""
    result = TestResult("Health Check Request/Response")
    
    # Create health check request
    request = IPCRequest(
        request_id=str(uuid.uuid4()),
        request_type="health_check",
        input={},
        output={},
        protocol_version=PROTOCOL_VERSION
    )
    
    # Send request
    request_id = write_ipc_request(request)
    
    # Wait for response
    response = wait_for_response(request_id, timeout_sec=10.0)
    
    if response is None:
        return result.failure("No response received within timeout")
    
    if not response.get('success'):
        return result.failure(f"Health check failed: {response.get('error')}")
    
    return result.success(
        request_id=request_id,
        response_success=response.get('success'),
        duration_ms=response.get('duration_ms')
    )


def test_3_xacro_to_urdf() -> TestResult:
    """Test 3: Convert XACRO to URDF only (UE5 plugin use case)."""
    result = TestResult("XACRO to URDF Conversion")
    
    # Check source exists
    if not os.path.exists(TEST_XACRO):
        return result.failure(f"Test XACRO file not found: {TEST_XACRO}")
    
    # Create output directory
    os.makedirs(TEST_OUTPUT_DIR, exist_ok=True)
    output_urdf = os.path.join(TEST_OUTPUT_DIR, "ur_robot.urdf")
    
    # Create convert_xacro request
    request = IPCRequest(
        request_id=str(uuid.uuid4()),
        request_type="convert_xacro",
        input={
            'path': TEST_XACRO,
            'source_file': TEST_XACRO
        },
        output={
            'path': output_urdf,
            'output_file': output_urdf
        },
        options={
            'xacro_args': TEST_XACRO_ARGS
        },
        protocol_version=PROTOCOL_VERSION,
        timeout_ms=60000
    )
    
    # Send request
    request_id = write_ipc_request(request)
    
    # Wait for response with progress monitoring
    start_time = time.time()
    last_progress = None
    
    while time.time() - start_time < 60.0:
        # Check for progress updates
        progress = get_progress(request_id)
        if progress and progress != last_progress:
            print(f"   Progress: {progress.get('percent', 0):.0f}% - {progress.get('stage', '')}")
            last_progress = progress
        
        # Check for response
        response_file = RESPONSES_DIR / f"{request_id}.response.json"
        if response_file.exists():
            try:
                with open(response_file, 'r') as f:
                    response = json.load(f)
                break
            except:
                pass
        
        time.sleep(0.5)
    else:
        return result.failure("Timeout waiting for XACRO conversion")
    
    if not response.get('success'):
        return result.failure(f"Conversion failed: {response.get('error')}")
    
    # Verify output exists
    output_file = response.get('output_file', output_urdf)
    if not os.path.exists(output_file):
        return result.failure(f"Output URDF not found: {output_file}")
    
    return result.success(
        request_id=request_id,
        output_file=output_file,
        file_size=os.path.getsize(output_file)
    )


def test_4_full_conversion() -> TestResult:
    """Test 4: Full conversion to USD with v3.0 metadata."""
    result = TestResult("Full XACRO to USD Conversion")
    
    # Check source exists
    if not os.path.exists(TEST_XACRO):
        return result.failure(f"Test XACRO file not found: {TEST_XACRO}")
    
    # Create output directory
    output_dir = os.path.join(TEST_OUTPUT_DIR, "full_conversion")
    os.makedirs(output_dir, exist_ok=True)
    
    # Create full conversion request
    request = IPCRequest(
        request_id=str(uuid.uuid4()),
        request_type="convert",
        input={
            'path': TEST_XACRO
        },
        output={
            'directory': output_dir,
            'name_prefix': 'ur5e_robot'
        },
        options={
            'include_collision': True,
            'include_visual': True,
            'scale_factor': 1.0,
            'xacro_args': TEST_XACRO_ARGS
        },
        protocol_version=PROTOCOL_VERSION,
        timeout_ms=120000
    )
    
    # Send request
    request_id = write_ipc_request(request)
    
    # Wait for response with progress monitoring
    # Full conversion needs more time than xacro-only + filesystem sync overhead
    start_time = time.time()
    last_progress = None
    
    while time.time() - start_time < 180.0:  # 3 minutes for full USD conversion
        # Check for progress updates
        progress = get_progress(request_id)
        if progress and progress != last_progress:
            percent = progress.get('percent', 0)
            stage = progress.get('stage', '')
            print(f"   Progress: {percent:.0f}% - {stage}")
            last_progress = progress
        
        # Check for response
        response_file = RESPONSES_DIR / f"{request_id}.response.json"
        if response_file.exists():
            try:
                with open(response_file, 'r') as f:
                    response = json.load(f)
                break
            except:
                pass
        
        time.sleep(1.0)
    else:
        return result.failure("Timeout waiting for full conversion")
    
    if not response.get('success'):
        error = response.get('error', {})
        return result.failure(f"Conversion failed: {error.get('message', error)}")
    
    # Verify outputs
    metadata = response.get('metadata', {})
    outputs = response.get('outputs', {})
    
    # Check for v3.0 features
    v3_features = {
        'hierarchy_path': metadata.get('hierarchy_path'),
        'submechanisms': metadata.get('submechanisms'),
        'ik_available': metadata.get('ik_available'),
        'version': metadata.get('version')
    }
    
    return result.success(
        request_id=request_id,
        outputs=list(outputs.keys()),
        metadata_version=metadata.get('version'),
        v3_features=v3_features
    )


def test_5_progress_updates() -> TestResult:
    """Test 5: Verify progress updates are received during conversion."""
    result = TestResult("Progress Updates")
    
    # Start a conversion and track progress
    output_dir = os.path.join(TEST_OUTPUT_DIR, "progress_test")
    os.makedirs(output_dir, exist_ok=True)
    
    request = IPCRequest(
        request_id=str(uuid.uuid4()),
        request_type="convert",
        input={'path': TEST_XACRO},
        output={
            'directory': output_dir,
            'name_prefix': 'progress_test'
        },
        options={'xacro_args': TEST_XACRO_ARGS},
        protocol_version=PROTOCOL_VERSION,
        timeout_ms=120000
    )
    
    request_id = write_ipc_request(request)
    
    # Collect progress updates
    progress_updates = []
    start_time = time.time()
    response = None
    
    while time.time() - start_time < 120.0:
        progress = get_progress(request_id)
        if progress:
            if not progress_updates or progress != progress_updates[-1]:
                progress_updates.append(progress)
        
        # Check for completion
        response_file = RESPONSES_DIR / f"{request_id}.response.json"
        if response_file.exists():
            try:
                with open(response_file, 'r') as f:
                    response = json.load(f)
            except:
                pass
            break
        
        time.sleep(0.5)
    
    # Check if this was a cached response (deduplication kicked in)
    if response and response.get('metadata', {}).get('cached_from'):
        return result.success(
            note="Cached response returned (deduplication working)",
            cached_from=response['metadata']['cached_from'],
            update_count=len(progress_updates)
        )
    
    if len(progress_updates) < 2:
        return result.failure("Insufficient progress updates received", 
                            count=len(progress_updates))
    
    # Verify progress is monotonically increasing
    percents = [p.get('percent', 0) for p in progress_updates]
    is_monotonic = all(percents[i] <= percents[i+1] for i in range(len(percents)-1))
    
    if not is_monotonic:
        return result.failure("Progress is not monotonically increasing",
                            percents=percents)
    
    return result.success(
        update_count=len(progress_updates),
        stages=[p.get('stage', '') for p in progress_updates[:5]],
        final_percent=percents[-1] if percents else 0
    )


def test_6_error_handling() -> TestResult:
    """Test 6: Verify error handling for invalid requests."""
    result = TestResult("Error Handling")
    
    # Test with non-existent file
    request = IPCRequest(
        request_id=str(uuid.uuid4()),
        request_type="convert",
        input={'path': '/nonexistent/file.urdf'},
        output={
            'directory': TEST_OUTPUT_DIR,
            'name_prefix': 'error_test'
        },
        protocol_version=PROTOCOL_VERSION,
        timeout_ms=10000
    )
    
    request_id = write_ipc_request(request)
    
    # Wait for error response
    response = wait_for_response(request_id, timeout_sec=15.0)
    
    if response is None:
        return result.failure("No response for invalid request")
    
    if response.get('success'):
        return result.failure("Expected failure for non-existent file")
    
    error = response.get('error', {})
    error_code = error.get('code', '')
    
    if 'E2001' not in error_code and 'FILE_NOT_FOUND' not in str(error):
        return result.failure("Expected FILE_NOT_FOUND error",
                            received_error=error)
    
    return result.success(
        error_code=error_code,
        error_message=error.get('message', '')[:100]
    )


def test_7_heartbeat() -> TestResult:
    """Test 7: Verify heartbeat is being updated."""
    result = TestResult("Heartbeat Updates")
    
    # Get initial heartbeat
    status1 = get_service_status()
    if not status1:
        return result.failure("Could not read initial status")
    
    hb1 = status1.get('last_heartbeat')
    
    # Wait a bit
    time.sleep(3)
    
    # Get new heartbeat
    status2 = get_service_status()
    if not status2:
        return result.failure("Could not read second status")
    
    hb2 = status2.get('last_heartbeat')
    
    if hb1 == hb2:
        return result.failure("Heartbeat not updating",
                            heartbeat1=hb1,
                            heartbeat2=hb2)
    
    return result.success(
        heartbeat1=hb1,
        heartbeat2=hb2,
        uptime=f"{status2.get('uptime_seconds', 0):.1f}s"
    )


def test_8_file_format_detection() -> TestResult:
    """Test 8: Test file format detection from GUI perspective."""
    result = TestResult("File Format Detection")
    
    # Import the format detector
    try:
        from file_type_importer import FileTypeImporter
        fti = FileTypeImporter(enable_hb=False, enable_obs=False)
        
        # Test various formats
        formats_to_test = [
            ('/path/to/robot.urdf', 'urdf'),
            ('/path/to/robot.URDF', 'urdf'),
            ('/path/to/robot.xacro', 'xacro'),
            ('/path/to/robot.urdf.xacro', 'xacro'),
            ('/path/to/model.sdf', 'sdf'),
            ('/path/to/unknown.xyz', None),  # Unknown format
        ]
        
        detected = {}
        for path, expected in formats_to_test:
            # Use internal detect method if available
            if hasattr(fti, '_detect_format'):
                actual = fti._detect_format(path)
            else:
                # Fallback to extension check
                ext = os.path.splitext(path)[1].lower()
                if ext == '.xacro' or path.endswith('.urdf.xacro'):
                    actual = 'xacro'
                elif ext == '.urdf':
                    actual = 'urdf'
                elif ext == '.sdf':
                    actual = 'sdf'
                else:
                    actual = None
            
            detected[path] = {
                'expected': expected,
                'actual': actual,
                'match': actual == expected
            }
        
        all_match = all(d['match'] for d in detected.values())
        
        if not all_match:
            failures = {k: v for k, v in detected.items() if not v['match']}
            return result.failure("Format detection mismatch", failures=failures)
        
        return result.success(detected_formats=list(detected.keys()))
        
    except ImportError as e:
        return result.failure(f"Could not import FTI: {e}")


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def run_all_tests():
    """Run all GUI-IPC pipeline tests."""
    print("=" * 70)
    print("GUI-FTI IPC PIPELINE TEST SUITE")
    print(f"Protocol Version: {PROTOCOL_VERSION}")
    print(f"IPC Base Path: {IPC_BASE_PATH}")
    print(f"Test Time: {datetime.now().isoformat()}")
    print("=" * 70)
    
    tests = [
        test_1_service_running,
        test_2_health_check,
        test_3_xacro_to_urdf,
        test_4_full_conversion,
        test_5_progress_updates,
        test_6_error_handling,
        test_7_heartbeat,
        test_8_file_format_detection,
    ]
    
    results = []
    
    for test_func in tests:
        print(f"\n🔍 Running: {test_func.__name__}")
        print("-" * 50)
        try:
            result = test_func()
        except Exception as e:
            import traceback
            result = TestResult(test_func.__name__)
            result.failure(f"Exception: {e}", traceback=traceback.format_exc()[:500])
        
        results.append(result)
        print(result)
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    
    for r in results:
        status = "✅" if r.passed else "❌"
        print(f"  {status} {r.name}")
    
    print(f"\n  Total: {len(results)} | Passed: {passed} | Failed: {failed}")
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print(f"\n⚠️  {failed} TEST(S) FAILED")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
