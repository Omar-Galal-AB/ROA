"""
Tests for WebthreadCore runtime monitoring
"""

import os
import sys
import time
from datetime import datetime

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "python"))

from webthread_core import ComponentHealth, HealthStatus, WebthreadCore


class TestWebthreadCore:
    """Test cases for WebthreadCore"""

    def test_initialization(self):
        """Test WebthreadCore initialization"""
        core = WebthreadCore()
        assert core is not None
        assert core.monitoring_active is False
        assert len(core.components) == 6  # FTI, DIMC, ROC, COMC, ROS2Bridge, UE5Bridge

    def test_start_monitoring(self):
        """Test starting monitoring"""
        core = WebthreadCore()
        core.start()
        assert core.monitoring_active is True
        assert len(core.component_health) == 6

    def test_stop_monitoring(self):
        """Test stopping monitoring"""
        core = WebthreadCore()
        core.start()
        core.stop()
        assert core.monitoring_active is False

    def test_register_component(self):
        """Test component registration"""
        core = WebthreadCore()

        # Mock component
        class MockComponent:
            def is_healthy(self):
                return True

        mock_comp = MockComponent()
        core.register_component("TestComponent", mock_comp)
        assert "TestComponent" in core.components

    def test_health_callback(self):
        """Test health status callback"""
        core = WebthreadCore()
        callback_called = []

        def health_callback(component_name, health_status):
            callback_called.append(component_name)

        core.register_health_callback(health_callback)
        core.start()

        # Update health status
        core._update_component_health("FTI", ComponentHealth.HEALTHY, 5.0)

        # Callback should have been called
        assert "FTI" in callback_called

    def test_error_callback(self):
        """Test error callback"""
        core = WebthreadCore()
        errors_caught = []

        def error_callback(component_name, error):
            errors_caught.append((component_name, error))

        core.register_error_callback(error_callback)

        # Trigger an error
        test_error = Exception("Test error")
        core._handle_component_error("ROC", test_error)

        assert len(errors_caught) == 1
        assert errors_caught[0][0] == "ROC"

    def test_health_status_creation(self):
        """Test HealthStatus dataclass"""
        status = HealthStatus(
            component_name="FTI",
            status=ComponentHealth.HEALTHY,
            last_check=datetime.now(),
            response_time=10.5,
            error_count=0,
            warnings=[],
        )

        assert status.component_name == "FTI"
        assert status.status == ComponentHealth.HEALTHY
        assert status.response_time == 10.5
        assert status.error_count == 0

    def test_graceful_degradation(self):
        """Test system continues with failed components"""
        core = WebthreadCore()
        core.start()

        # Simulate component failure
        core._update_component_health("COMC", ComponentHealth.FAILED, 0.0)

        # System should still be monitoring
        assert core.monitoring_active is True
        assert core.component_health["COMC"].status == ComponentHealth.FAILED

    def test_config_loading(self):
        """Test configuration loading"""
        config = {"health_check_interval": 1.0, "max_retries": 3}
        core = WebthreadCore(config=config)

        assert core.health_check_interval == 1.0
        assert core.config["max_retries"] == 3

    def test_get_system_status(self):
        """Test getting system status"""
        core = WebthreadCore()
        core.start()

        status = core.get_system_status()

        assert "components" in status
        assert "uptime" in status
        assert "error_count" in status
        assert "warning_count" in status

    def test_component_health_enum(self):
        """Test ComponentHealth enum values"""
        assert ComponentHealth.HEALTHY.value == "healthy"
        assert ComponentHealth.DEGRADED.value == "degraded"
        assert ComponentHealth.FAILED.value == "failed"
        assert ComponentHealth.UNKNOWN.value == "unknown"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
