#!/usr/bin/env python3
"""
ROA IPC Integration Tests

Tests the complete File-Based IPC system:
1. Protocol serialization/deserialization
2. Atomic file operations
3. Path handling with security validation
4. Request/Response flow simulation

Run with:
    python -m pytest test_ipc_integration.py -v

    OR

    python test_ipc_integration.py
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

# Add paths for imports
sys.path.insert(0, str(Path(__file__).parent))

from IPC.ipc_protocol import (
    PROTOCOL_VERSION,
    AtomicFileWriter,
    ConversionOptions,
    ErrorCode,
    IPCPaths,
    IPCProgress,
    IPCRequest,
    IPCResponse,
    OutputFile,
    RequestDeduplicator,
    RequestType,
    ResponseStatus,
    ServiceStatus,
    read_request,
    write_ack,
    write_progress,
    write_request,
    write_response,
)
from Utils.path_handler import (
    ALLOWED_EXTENSIONS,
    DANGEROUS_PATTERNS,
    PathInfo,
    PathType,
    PathValidationResult,
    ROAPathHandler,
)


class TestIPCProtocol(unittest.TestCase):
    """Test IPC protocol serialization and validation."""

    def test_create_convert_request(self):
        """Test creating a conversion request."""
        request = IPCRequest.create_convert_request(
            input_path=r"D:\Robots\ur3.xacro",
            output_directory=r"D:\ROA\Outputs",
            name_prefix="ur3_robot",
        )

        self.assertIsNotNone(request.request_id)
        self.assertEqual(request.request_type, RequestType.CONVERT.value)
        self.assertEqual(request.input["path"], r"D:\Robots\ur3.xacro")
        self.assertEqual(request.output["directory"], r"D:\ROA\Outputs")
        self.assertEqual(request.output["name_prefix"], "ur3_robot")
        self.assertEqual(request.protocol_version, PROTOCOL_VERSION)

    def test_request_validation(self):
        """Test request validation."""
        # Valid request
        request = IPCRequest.create_convert_request(
            input_path=r"D:\test.urdf", output_directory=r"D:\out", name_prefix="robot"
        )
        is_valid, error = request.validate()
        self.assertTrue(is_valid)
        self.assertIsNone(error)

        # Invalid: missing input path
        bad_request = IPCRequest(
            request_id="test",
            request_type="convert",
            input={},
            output={"directory": r"D:\out"},
        )
        is_valid, error = bad_request.validate()
        self.assertFalse(is_valid)
        self.assertIn("input.path", error)

    def test_request_serialization(self):
        """Test JSON serialization roundtrip."""
        request = IPCRequest.create_convert_request(
            input_path=r"D:\Robots\ur3.xacro",
            output_directory=r"D:\ROA\Outputs",
            name_prefix="ur3",
        )

        # Serialize
        json_str = request.to_json()
        self.assertIsInstance(json_str, str)

        # Parse
        data = json.loads(json_str)
        self.assertEqual(data["request_type"], "convert")

        # Deserialize
        restored = IPCRequest.from_json(json_str)
        self.assertEqual(restored.request_id, request.request_id)
        self.assertEqual(restored.input["path"], request.input["path"])

    def test_response_success(self):
        """Test success response creation."""
        response = IPCResponse.create_success(
            request_id="test-123",
            outputs={
                "parts_usd": OutputFile(
                    linux_path="/mnt/d/out/robot_parts.usd",
                    windows_path=r"D:\out\robot_parts.usd",
                    size_bytes=1000000,
                )
            },
            metadata={"robot_name": "ur3", "link_count": 11},
            duration_ms=5000,
        )

        self.assertTrue(response.success)
        self.assertEqual(response.status, ResponseStatus.SUCCESS.value)
        self.assertEqual(response.duration_ms, 5000)
        self.assertIn("parts_usd", response.outputs)

    def test_response_error(self):
        """Test error response creation."""
        response = IPCResponse.create_error(
            request_id="test-123",
            error_code=ErrorCode.FILE_NOT_FOUND,
            message="Mesh not found: arm.stl",
            recoverable=True,
            suggestion="Check package paths",
        )

        self.assertFalse(response.success)
        self.assertEqual(response.status, ResponseStatus.FAILED.value)
        self.assertEqual(response.error["code"], "E2001")
        self.assertEqual(response.error["message"], "Mesh not found: arm.stl")
        self.assertTrue(response.error["recoverable"])


class TestAtomicFileWriter(unittest.TestCase):
    """Test atomic file writing."""

    def setUp(self):
        """Create temp directory."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir)

    def test_atomic_write_success(self):
        """Test successful atomic write."""
        target = os.path.join(self.temp_dir, "test.json")

        with AtomicFileWriter(target) as writer:
            writer.write('{"test": "data"}')

        # File should exist
        self.assertTrue(os.path.exists(target))

        # Temp file should not exist
        self.assertFalse(os.path.exists(target + ".tmp"))

        # Content should be correct
        with open(target) as f:
            self.assertEqual(f.read(), '{"test": "data"}')

    def test_atomic_write_failure(self):
        """Test atomic write cleanup on failure."""
        target = os.path.join(self.temp_dir, "test.json")

        try:
            with AtomicFileWriter(target) as writer:
                writer.write("partial data")
                raise ValueError("Simulated error")
        except ValueError:
            pass

        # Target file should not exist
        self.assertFalse(os.path.exists(target))

        # Temp file should be cleaned up
        self.assertFalse(os.path.exists(target + ".tmp"))

    def test_atomic_write_creates_directories(self):
        """Test that atomic write creates parent directories."""
        target = os.path.join(self.temp_dir, "deep", "nested", "path", "test.json")

        with AtomicFileWriter(target) as writer:
            writer.write('{"nested": true}')

        self.assertTrue(os.path.exists(target))


class TestRequestDeduplicator(unittest.TestCase):
    """Test request deduplication."""

    def test_first_request_is_new(self):
        """Test that first request is considered new."""
        dedup = RequestDeduplicator(ttl_seconds=60)

        request = IPCRequest.create_convert_request(
            input_path=r"D:\test.urdf", output_directory=r"D:\out", name_prefix="robot"
        )
        # Manually set hash for testing
        request.input["file_hash"] = "sha256:abc123"

        is_new, existing_id = dedup.check(request)

        self.assertTrue(is_new)
        self.assertIsNone(existing_id)

    def test_duplicate_request_detected(self):
        """Test that duplicate is detected."""
        dedup = RequestDeduplicator(ttl_seconds=60)

        # First request
        request1 = IPCRequest.create_convert_request(
            input_path=r"D:\test.urdf", output_directory=r"D:\out", name_prefix="robot1"
        )
        request1.input["file_hash"] = "sha256:same_hash"

        is_new, _ = dedup.check(request1)
        self.assertTrue(is_new)

        # Second request with same hash
        request2 = IPCRequest.create_convert_request(
            input_path=r"D:\test.urdf", output_directory=r"D:\out", name_prefix="robot2"
        )
        request2.input["file_hash"] = "sha256:same_hash"

        is_new, existing_id = dedup.check(request2)

        self.assertFalse(is_new)
        self.assertEqual(existing_id, request1.request_id)


class TestIPCPaths(unittest.TestCase):
    """Test IPC path management."""

    def test_path_conversion(self):
        """Test Windows to Linux path conversion."""
        paths = IPCPaths(r"D:\ROA\.ipc")

        self.assertEqual(paths.base_path_windows, r"D:\ROA\.ipc")
        self.assertEqual(paths.base_path_linux, "/mnt/d/ROA/.ipc")

    def test_request_path(self):
        """Test getting request file path."""
        paths = IPCPaths(r"D:\ROA\.ipc")

        request_path = paths.get_request_path("abc-123")

        self.assertTrue(str(request_path).endswith("abc-123.request.json"))

    def test_ensure_directories(self):
        """Test directory creation."""
        temp_dir = tempfile.mkdtemp()
        try:
            paths = IPCPaths(temp_dir)
            paths.ensure_directories()

            self.assertTrue(paths.requests_dir.exists())
            self.assertTrue(paths.responses_dir.exists())
            self.assertTrue(paths.progress_dir.exists())
        finally:
            shutil.rmtree(temp_dir)


class TestPathHandler(unittest.TestCase):
    """Test path handling with security."""

    def setUp(self):
        """Create path handler."""
        self.handler = ROAPathHandler()

    def test_detect_windows_path(self):
        """Test Windows path detection."""
        path_type = self.handler.detect_path_type(r"D:\Robots\ur3.urdf")
        self.assertEqual(path_type, PathType.WINDOWS_NATIVE)

    def test_detect_wsl_mount(self):
        """Test WSL mount path detection."""
        path_type = self.handler.detect_path_type("/mnt/d/Robots/ur3.urdf")
        self.assertEqual(path_type, PathType.WSL_MOUNT)

    def test_detect_linux_native(self):
        """Test Linux native path detection."""
        path_type = self.handler.detect_path_type("/home/user/robots/ur3.urdf")
        self.assertEqual(path_type, PathType.LINUX_NATIVE)

    def test_to_linux_path(self):
        """Test Windows to Linux conversion."""
        linux_path = self.handler.to_linux_path(r"D:\Robots\ur3.urdf")
        self.assertEqual(linux_path, "/mnt/d/Robots/ur3.urdf")

    def test_to_windows_path(self):
        """Test Linux to Windows conversion."""
        windows_path = self.handler.to_windows_path("/mnt/d/Robots/ur3.urdf")
        self.assertEqual(windows_path, r"D:\Robots\ur3.urdf")

    def test_path_info(self):
        """Test comprehensive path info."""
        info = self.handler.get_path_info(r"D:\Robots\ur3.urdf")

        self.assertEqual(info.path_type, PathType.WINDOWS_NATIVE)
        self.assertEqual(info.linux_path, "/mnt/d/Robots/ur3.urdf")
        self.assertEqual(info.windows_path, r"D:\Robots\ur3.urdf")
        self.assertEqual(info.drive_letter, "D")
        self.assertTrue(info.is_accessible_from_windows)

    def test_security_path_traversal(self):
        """Test path traversal detection."""
        is_safe, issues = self.handler.validate_path_security("/mnt/d/../../../etc/passwd")

        self.assertFalse(is_safe)
        self.assertTrue(any("Dangerous pattern" in issue for issue in issues))

    def test_security_sensitive_paths(self):
        """Test sensitive path detection."""
        is_safe, issues = self.handler.validate_path_security("/etc/shadow")
        self.assertFalse(is_safe)

        is_safe, issues = self.handler.validate_path_security("/home/user/.ssh/id_rsa")
        self.assertFalse(is_safe)

    def test_file_extension_validation(self):
        """Test file extension validation."""
        is_allowed, ext = self.handler.validate_file_extension("/path/to/robot.urdf")
        self.assertTrue(is_allowed)
        self.assertEqual(ext, ".urdf")

        is_allowed, ext = self.handler.validate_file_extension("/path/to/file.exe")
        self.assertFalse(is_allowed)

    def test_comprehensive_validation(self):
        """Test comprehensive path validation."""
        result = self.handler.validate_path(
            r"D:\Robots\ur3.urdf",
            allowed_roots=None,  # Skip root check for test
            check_extension=True,
        )

        self.assertTrue(result.is_valid)
        self.assertTrue(result.is_safe)


class TestIPCFileOperations(unittest.TestCase):
    """Test IPC file read/write operations."""

    def setUp(self):
        """Create temp IPC directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.paths = IPCPaths(self.temp_dir)
        self.paths.ensure_directories()

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir)

    def test_write_and_read_request(self):
        """Test writing and reading request."""
        request = IPCRequest.create_convert_request(
            input_path=r"D:\test.urdf", output_directory=r"D:\out", name_prefix="robot"
        )

        # Write
        success = write_request(self.paths, request)
        self.assertTrue(success)

        # Verify file exists
        request_path = self.paths.get_request_path(request.request_id)
        self.assertTrue(request_path.exists())

        # Read
        read_req = read_request(self.paths, request.request_id)
        self.assertIsNotNone(read_req)
        self.assertEqual(read_req.request_id, request.request_id)
        self.assertEqual(read_req.input["path"], request.input["path"])

    def test_write_response(self):
        """Test writing response."""
        response = IPCResponse.create_success(
            request_id="test-123", outputs={}, metadata={"test": True}, duration_ms=1000
        )

        success = write_response(self.paths, response)
        self.assertTrue(success)

        response_path = self.paths.get_response_path("test-123")
        self.assertTrue(response_path.exists())

    def test_write_ack(self):
        """Test writing acknowledgement."""
        success = write_ack(self.paths, "test-456")
        self.assertTrue(success)

        ack_path = self.paths.get_ack_path("test-456")
        self.assertTrue(ack_path.exists())

    def test_write_progress(self):
        """Test writing progress."""
        progress = IPCProgress(request_id="test-789", percent=50.0, stage="Converting meshes")

        success = write_progress(self.paths, progress)
        self.assertTrue(success)

        progress_path = self.paths.get_progress_path("test-789")
        self.assertTrue(progress_path.exists())


class TestServiceStatus(unittest.TestCase):
    """Test service status handling."""

    def test_service_status_serialization(self):
        """Test service status serialization."""
        status = ServiceStatus(
            status="running",
            pid=12345,
            pending_requests=["req1", "req2"],
            processed_count=100,
            failed_count=5,
            uptime_seconds=3600.0,
        )

        json_str = status.to_json()
        data = json.loads(json_str)

        self.assertEqual(data["status"], "running")
        self.assertEqual(data["pid"], 12345)
        self.assertEqual(len(data["pending_requests"]), 2)

    def test_service_status_deserialization(self):
        """Test service status deserialization."""
        json_str = '{"status": "running", "pid": 123, "pending_requests": [], "processed_count": 0, "failed_count": 0, "uptime_seconds": 0.0, "last_heartbeat": "2026-01-05T12:00:00+00:00", "version": "1.0.0"}'

        status = ServiceStatus.from_json(json_str)

        self.assertEqual(status.status, "running")
        self.assertEqual(status.pid, 123)


def run_all_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestIPCProtocol))
    suite.addTests(loader.loadTestsFromTestCase(TestAtomicFileWriter))
    suite.addTests(loader.loadTestsFromTestCase(TestRequestDeduplicator))
    suite.addTests(loader.loadTestsFromTestCase(TestIPCPaths))
    suite.addTests(loader.loadTestsFromTestCase(TestPathHandler))
    suite.addTests(loader.loadTestsFromTestCase(TestIPCFileOperations))
    suite.addTests(loader.loadTestsFromTestCase(TestServiceStatus))

    # Run
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
