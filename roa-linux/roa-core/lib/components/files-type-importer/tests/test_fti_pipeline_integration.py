#!/usr/bin/env python3
"""
FTI Pipeline Integration Tests

Tests the complete pipeline from GUI to assembled robot:
1. FTI GUI Panel interaction
2. IPC Bridge communication
3. Pipeline Orchestrator execution
4. Full end-to-end flow

Run with: pytest test_fti_pipeline_integration.py -v
"""

import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Add paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "webthread" / "src" / "python"))

# Import modules under test
from fti_ipc_bridge import (
    ConversionProgress,
    ConversionResult,
    ConversionState,
    FTIIPCBridge,
)
from fti_pipeline_orchestrator import (
    FTIPipelineOrchestrator,
    PipelineConfig,
    PipelineProgress,
    PipelineStage,
    PipelineStatus,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def temp_ipc_folder():
    """Create a temporary IPC folder structure"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create folder structure
        folders = ["requests", "responses", "progress", "ack", "commands"]
        for folder in folders:
            os.makedirs(os.path.join(tmpdir, folder), exist_ok=True)
        yield tmpdir


@pytest.fixture
def sample_urdf_file(temp_ipc_folder):
    """Create a sample URDF file for testing"""
    urdf_content = """<?xml version="1.0"?>
<robot name="test_robot">
    <link name="base_link">
        <visual>
            <geometry>
                <box size="0.1 0.1 0.1"/>
            </geometry>
        </visual>
        <collision>
            <geometry>
                <box size="0.1 0.1 0.1"/>
            </geometry>
        </collision>
    </link>
    
    <link name="link1">
        <visual>
            <geometry>
                <cylinder length="0.2" radius="0.05"/>
            </geometry>
        </visual>
    </link>
    
    <joint name="joint1" type="revolute">
        <parent link="base_link"/>
        <child link="link1"/>
        <origin xyz="0 0 0.1" rpy="0 0 0"/>
        <axis xyz="0 0 1"/>
        <limit lower="-3.14" upper="3.14" effort="100" velocity="1"/>
    </joint>
</robot>
"""
    urdf_path = os.path.join(temp_ipc_folder, "test_robot.urdf")
    with open(urdf_path, "w") as f:
        f.write(urdf_content)
    return urdf_path


@pytest.fixture
def ipc_bridge(temp_ipc_folder):
    """Create an IPC bridge with the temp folder"""
    return FTIIPCBridge(temp_ipc_folder)


@pytest.fixture
def mock_service_running(temp_ipc_folder):
    """Create a mock service.status file indicating service is running"""
    status = {
        "status": "running",
        "timestamp": time.time(),
        "started_at": time.time() - 100,
        "version": "1.0.0",
    }
    status_file = os.path.join(temp_ipc_folder, "service.status")
    with open(status_file, "w") as f:
        json.dump(status, f)
    return status_file


# ═══════════════════════════════════════════════════════════════════════════════
# IPC Bridge Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestFTIIPCBridge:
    """Tests for FTI IPC Bridge"""

    def test_init_creates_folders(self, temp_ipc_folder):
        """Test that bridge creates required folders"""
        bridge = FTIIPCBridge(temp_ipc_folder)

        assert os.path.exists(os.path.join(temp_ipc_folder, "requests"))
        assert os.path.exists(os.path.join(temp_ipc_folder, "responses"))
        assert os.path.exists(os.path.join(temp_ipc_folder, "progress"))
        assert os.path.exists(os.path.join(temp_ipc_folder, "ack"))

    def test_service_not_running_without_status_file(self, ipc_bridge):
        """Test that service reports not running without status file"""
        assert not ipc_bridge.is_service_running()

    def test_service_running_with_recent_status(self, ipc_bridge, mock_service_running):
        """Test that service reports running with recent status"""
        assert ipc_bridge.is_service_running()

    def test_service_not_running_with_stale_status(self, temp_ipc_folder):
        """Test that service reports not running with stale status"""
        status = {
            "status": "running",
            "timestamp": time.time() - 60,  # 60 seconds ago (stale)
        }
        status_file = os.path.join(temp_ipc_folder, "service.status")
        with open(status_file, "w") as f:
            json.dump(status, f)

        bridge = FTIIPCBridge(temp_ipc_folder)
        assert not bridge.is_service_running()

    def test_submit_conversion_creates_request_file(self, ipc_bridge, sample_urdf_file):
        """Test that submitting conversion creates a request file"""
        request_id = ipc_bridge.submit_conversion(sample_urdf_file)

        assert request_id is not None
        assert len(request_id) > 0

        request_file = os.path.join(ipc_bridge.ipc_folder, "requests", f"{request_id}.request.json")
        assert os.path.exists(request_file)

        with open(request_file, "r") as f:
            request = json.load(f)

        assert request["request_id"] == request_id
        assert request["source_file"] == os.path.abspath(sample_urdf_file)
        assert request["request_type"] == "convert"

    def test_submit_conversion_with_options(self, ipc_bridge, sample_urdf_file):
        """Test submitting conversion with options"""
        request_id = ipc_bridge.submit_conversion(
            sample_urdf_file,
            output_format="usda",
            mesh_handling="reference",
            auto_assemble=False,
            generate_blueprint=True,
        )

        request_file = os.path.join(ipc_bridge.ipc_folder, "requests", f"{request_id}.request.json")
        with open(request_file, "r") as f:
            request = json.load(f)

        assert request["options"]["output_format"] == "usda"
        assert request["options"]["mesh_handling"] == "reference"
        assert request["options"]["auto_assemble"] == False
        assert request["options"]["generate_blueprint"] == True

    def test_submit_conversion_fails_for_nonexistent_file(self, ipc_bridge):
        """Test that submitting conversion fails for nonexistent file"""
        with pytest.raises(FileNotFoundError):
            ipc_bridge.submit_conversion("/nonexistent/file.urdf")

    def test_get_progress_returns_none_without_file(self, ipc_bridge):
        """Test that get_progress returns None without progress file"""
        progress = ipc_bridge.get_progress("nonexistent-request-id")
        assert progress is None

    def test_get_progress_reads_file(self, temp_ipc_folder, ipc_bridge):
        """Test that get_progress reads progress file correctly"""
        request_id = str(uuid.uuid4())

        progress_data = {
            "request_id": request_id,
            "percent": 50.0,
            "stage": "meshes",
            "message": "Processing mesh files...",
            "started_at": time.time() - 10,
            "updated_at": time.time(),
        }

        progress_file = os.path.join(temp_ipc_folder, "progress", f"{request_id}.progress.json")
        with open(progress_file, "w") as f:
            json.dump(progress_data, f)

        progress = ipc_bridge.get_progress(request_id)

        assert progress is not None
        assert progress.request_id == request_id
        assert progress.percent == 50.0
        assert progress.stage == "meshes"

    def test_get_result_returns_none_without_file(self, ipc_bridge):
        """Test that get_result returns None without response file"""
        result = ipc_bridge.get_result("nonexistent-request-id")
        assert result is None

    def test_get_result_reads_file(self, temp_ipc_folder, ipc_bridge):
        """Test that get_result reads response file correctly"""
        request_id = str(uuid.uuid4())

        response_data = {
            "request_id": request_id,
            "success": True,
            "output_file": "/path/to/output.usd",
            "robot_name": "test_robot",
            "link_count": 2,
            "joint_count": 1,
            "mesh_count": 2,
            "conversion_time": 5.5,
        }

        response_file = os.path.join(temp_ipc_folder, "responses", f"{request_id}.response.json")
        with open(response_file, "w") as f:
            json.dump(response_data, f)

        result = ipc_bridge.get_result(request_id)

        assert result is not None
        assert result.success == True
        assert result.output_file == "/path/to/output.usd"
        assert result.robot_name == "test_robot"
        assert result.link_count == 2
        assert result.joint_count == 1

    def test_cancel_conversion_creates_cancel_file(self, ipc_bridge, sample_urdf_file):
        """Test that cancel creates a cancel request file"""
        request_id = ipc_bridge.submit_conversion(sample_urdf_file)
        result = ipc_bridge.cancel_conversion(request_id)

        assert result == True

        cancel_file = os.path.join(
            ipc_bridge.ipc_folder, "requests", f"cancel_{request_id}.request.json"
        )
        assert os.path.exists(cancel_file)


# ═══════════════════════════════════════════════════════════════════════════════
# Pipeline Orchestrator Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestFTIPipelineOrchestrator:
    """Tests for FTI Pipeline Orchestrator"""

    def test_init_with_default_config(self):
        """Test orchestrator initializes with default config"""
        orchestrator = FTIPipelineOrchestrator()

        assert orchestrator.config is not None
        assert orchestrator.config.output_format == "usd"
        assert orchestrator.config.auto_assemble == True

    def test_init_with_custom_config(self, temp_ipc_folder):
        """Test orchestrator initializes with custom config"""
        config = PipelineConfig(
            ipc_folder=temp_ipc_folder,
            output_format="usda",
            auto_assemble=False,
        )

        orchestrator = FTIPipelineOrchestrator(config)

        assert orchestrator.config.ipc_folder == temp_ipc_folder
        assert orchestrator.config.output_format == "usda"
        assert orchestrator.config.auto_assemble == False

    def test_configure_updates_config(self):
        """Test that configure() updates config values"""
        orchestrator = FTIPipelineOrchestrator()

        orchestrator.configure(
            output_format="usdz",
            generate_blueprint=False,
        )

        assert orchestrator.config.output_format == "usdz"
        assert orchestrator.config.generate_blueprint == False

    def test_initial_status_is_idle(self):
        """Test that initial status is IDLE"""
        orchestrator = FTIPipelineOrchestrator()
        assert orchestrator.get_status() == PipelineStatus.IDLE

    def test_progress_callbacks_registered(self):
        """Test that progress callbacks can be registered"""
        orchestrator = FTIPipelineOrchestrator()
        callback = Mock()

        orchestrator.on_progress(callback)

        assert callback in orchestrator._progress_callbacks

    def test_completion_callbacks_registered(self):
        """Test that completion callbacks can be registered"""
        orchestrator = FTIPipelineOrchestrator()
        callback = Mock()

        orchestrator.on_complete(callback)

        assert callback in orchestrator._completion_callbacks

    def test_error_callbacks_registered(self):
        """Test that error callbacks can be registered"""
        orchestrator = FTIPipelineOrchestrator()
        callback = Mock()

        orchestrator.on_error(callback)

        assert callback in orchestrator._error_callbacks

    def test_start_pipeline_fails_for_nonexistent_file(self, temp_ipc_folder, mock_service_running):
        """Test that pipeline fails for nonexistent source file"""
        config = PipelineConfig(ipc_folder=temp_ipc_folder)
        orchestrator = FTIPipelineOrchestrator(config)

        result = orchestrator.start_pipeline("/nonexistent/file.urdf")

        # Wait for thread to process
        time.sleep(0.5)

        assert orchestrator.get_status() == PipelineStatus.FAILED
        assert "not found" in orchestrator.get_error().lower()

    def test_cancel_sets_status_to_cancelled(self, temp_ipc_folder):
        """Test that cancel sets status to CANCELLED"""
        config = PipelineConfig(ipc_folder=temp_ipc_folder)
        orchestrator = FTIPipelineOrchestrator(config)

        orchestrator._status = PipelineStatus.RUNNING
        orchestrator.cancel()

        assert orchestrator.get_status() == PipelineStatus.CANCELLED

    def test_is_running_returns_correct_status(self, temp_ipc_folder):
        """Test that is_running returns correct status"""
        config = PipelineConfig(ipc_folder=temp_ipc_folder)
        orchestrator = FTIPipelineOrchestrator(config)

        assert not orchestrator.is_running()

        orchestrator._status = PipelineStatus.RUNNING
        assert orchestrator.is_running()

        orchestrator._status = PipelineStatus.COMPLETED
        assert not orchestrator.is_running()


# ═══════════════════════════════════════════════════════════════════════════════
# End-to-End Tests (Mocked Service)
# ═══════════════════════════════════════════════════════════════════════════════


class TestEndToEndPipeline:
    """End-to-end pipeline tests with mocked service"""

    @pytest.fixture
    def mock_successful_conversion(self, temp_ipc_folder):
        """Setup mock for successful conversion"""

        def create_response(request_id):
            # Create progress file
            progress_data = {
                "percent": 100,
                "stage": "complete",
                "message": "Conversion complete",
            }
            progress_file = os.path.join(temp_ipc_folder, "progress", f"{request_id}.progress.json")
            with open(progress_file, "w") as f:
                json.dump(progress_data, f)

            # Create response file
            response_data = {
                "success": True,
                "output_file": os.path.join(temp_ipc_folder, "output", "test_robot.usd"),
                "robot_name": "test_robot",
                "link_count": 2,
                "joint_count": 1,
            }
            response_file = os.path.join(
                temp_ipc_folder, "responses", f"{request_id}.response.json"
            )
            with open(response_file, "w") as f:
                json.dump(response_data, f)

        return create_response

    def test_ipc_bridge_wait_for_completion(
        self,
        temp_ipc_folder,
        ipc_bridge,
        sample_urdf_file,
        mock_service_running,
        mock_successful_conversion,
    ):
        """Test waiting for conversion completion"""
        # Submit request
        request_id = ipc_bridge.submit_conversion(sample_urdf_file)

        # Simulate service processing (in background)
        import threading

        def simulate_conversion():
            time.sleep(0.5)
            mock_successful_conversion(request_id)

        thread = threading.Thread(target=simulate_conversion)
        thread.start()

        # Wait for completion
        result = ipc_bridge.wait_for_completion(request_id, timeout=5)
        thread.join()

        assert result is not None
        assert result.success == True
        assert result.robot_name == "test_robot"

    def test_progress_callback_called(
        self,
        temp_ipc_folder,
        ipc_bridge,
        sample_urdf_file,
        mock_service_running,
        mock_successful_conversion,
    ):
        """Test that progress callback is called"""
        request_id = ipc_bridge.submit_conversion(sample_urdf_file)
        progress_updates = []

        def capture_progress(progress):
            progress_updates.append(progress)

        # Simulate service processing
        import threading

        def simulate_conversion():
            time.sleep(0.3)
            # Write progress
            progress_file = os.path.join(temp_ipc_folder, "progress", f"{request_id}.progress.json")
            with open(progress_file, "w") as f:
                json.dump({"percent": 50, "stage": "meshes", "message": "Processing..."}, f)
            time.sleep(0.3)
            mock_successful_conversion(request_id)

        thread = threading.Thread(target=simulate_conversion)
        thread.start()

        result = ipc_bridge.wait_for_completion(
            request_id, timeout=5, progress_callback=capture_progress
        )
        thread.join()

        assert result is not None
        assert len(progress_updates) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# GUI Integration Tests (Mocked PyQt)
# ═══════════════════════════════════════════════════════════════════════════════


class TestGUIIntegration:
    """Tests for GUI integration (mocked PyQt)"""

    @pytest.fixture
    def mock_qt(self):
        """Mock PyQt6 for testing"""
        with patch.dict(
            sys.modules,
            {
                "PyQt6": MagicMock(),
                "PyQt6.QtWidgets": MagicMock(),
                "PyQt6.QtCore": MagicMock(),
                "PyQt6.QtGui": MagicMock(),
            },
        ):
            yield

    def test_format_detection(self, temp_ipc_folder):
        """Test file format detection logic"""

        # This tests the format detection logic that would be in the GUI
        def detect_format(filepath):
            ext = os.path.splitext(filepath)[1].lower()
            formats = {
                ".urdf": "URDF",
                ".xacro": "XACRO",
                ".sdf": "SDF",
                ".usd": "USD",
                ".usda": "USDA",
                ".usdz": "USDZ",
                ".stl": "STL",
                ".obj": "OBJ",
                ".fbx": "FBX",
            }
            return formats.get(ext, "Unknown")

        assert detect_format("/path/to/robot.urdf") == "URDF"
        assert detect_format("/path/to/robot.xacro") == "XACRO"
        assert detect_format("/path/to/model.sdf") == "SDF"
        assert detect_format("/path/to/scene.usd") == "USD"
        assert detect_format("/path/to/unknown.xyz") == "Unknown"

    def test_urdf_parsing(self, sample_urdf_file):
        """Test URDF parsing for file info"""
        with open(sample_urdf_file, "r") as f:
            content = f.read()

        # Count elements (simplified parsing logic)
        link_count = content.count("<link")
        joint_count = content.count("<joint")

        assert link_count == 2  # base_link and link1
        assert joint_count == 1  # joint1


# ═══════════════════════════════════════════════════════════════════════════════
# Performance Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestPerformance:
    """Performance tests for pipeline components"""

    def test_bridge_creation_time(self, temp_ipc_folder):
        """Test that bridge creation is fast"""
        import timeit

        def create_bridge():
            FTIIPCBridge(temp_ipc_folder)

        time_taken = timeit.timeit(create_bridge, number=100)
        avg_time = time_taken / 100

        assert avg_time < 0.01  # Should be less than 10ms

    def test_request_submission_time(self, ipc_bridge, sample_urdf_file):
        """Test that request submission is fast"""
        import timeit

        def submit_request():
            ipc_bridge.submit_conversion(sample_urdf_file)

        time_taken = timeit.timeit(submit_request, number=10)
        avg_time = time_taken / 10

        assert avg_time < 0.1  # Should be less than 100ms


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
