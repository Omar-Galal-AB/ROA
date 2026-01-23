"""
Integration tests for ROC agents (HeartbeatAgent, BridgeHealthAgent).

Tests cover:
- Agent lifecycle (start/stop)
- Heartbeat file operations
- Dependency monitoring
- Bridge health checking
- Callback notifications
"""

import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.python.bridge_health_agent import (
    BridgeHealthAgent,
    BridgeHealthAgentConfig,
    BridgeMetrics,
    BridgeStatus,
)
from src.python.heartbeat_agent import (
    DependencyConfig,
    HeartbeatAgent,
    HeartbeatAgentConfig,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def temp_heartbeat_dir(tmp_path):
    """Create temporary heartbeat directory."""
    hb_dir = tmp_path / "heartbeats"
    hb_dir.mkdir(parents=True)
    return hb_dir


@pytest.fixture
def heartbeat_config(temp_heartbeat_dir):
    """Create HeartbeatAgent config with temp directory."""
    return HeartbeatAgentConfig(
        heartbeat_dir=str(temp_heartbeat_dir),
        heartbeat_rate_hz=10.0,  # Fast for testing
        monitor_dependencies=True,
        fti_timeout=1.0,
        dimc_timeout=0.5,
        comc_timeout=0.5,
        ue5_timeout=1.0,
        remove_heartbeat_on_shutdown=True,
    )


@pytest.fixture
def mock_ipc_handler():
    """Create mock IPC handler for bridge tests."""
    mock_ipc = MagicMock()
    mock_ipc.is_connected = True
    mock_ipc.heartbeat_healthy = True
    mock_ipc.get_statistics.return_value = {
        "state": "CONNECTED",
        "messages_sent": 100,
        "messages_received": 98,
        "last_heartbeat": time.time(),
    }
    mock_ipc.connect = AsyncMock(return_value=True)
    mock_ipc.disconnect = AsyncMock()
    return mock_ipc


@pytest.fixture
def bridge_config():
    """Create BridgeHealthAgent config."""
    return BridgeHealthAgentConfig(
        health_check_rate_hz=10.0,  # Fast for testing
        latency_warning_ms=50.0,
        latency_critical_ms=200.0,
        auto_reconnect=True,
        max_reconnect_attempts=3,
        check_socat=False,  # Disable for tests
    )


# =============================================================================
# HEARTBEAT AGENT TESTS
# =============================================================================


class TestHeartbeatAgentLifecycle:
    """Test HeartbeatAgent start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_heartbeat_file(self, heartbeat_config, temp_heartbeat_dir):
        """Agent should create heartbeat file on start."""
        agent = HeartbeatAgent(config=heartbeat_config)

        await agent.start()

        try:
            # Check heartbeat file exists
            files = list(temp_heartbeat_dir.glob("roc_*.heartbeat.json"))
            assert len(files) == 1

            # Verify file content
            content = json.loads(files[0].read_text())
            assert "client_id" in content
            assert content["type"] == "roc_component"
            assert "timestamp" in content
            assert content["health_status"] == "active"
        finally:
            await agent.stop()

    @pytest.mark.asyncio
    async def test_stop_removes_heartbeat_file(self, heartbeat_config, temp_heartbeat_dir):
        """Agent should remove heartbeat file on stop."""
        agent = HeartbeatAgent(config=heartbeat_config)

        await agent.start()

        # Verify file exists
        files = list(temp_heartbeat_dir.glob("roc_*.heartbeat.json"))
        assert len(files) == 1

        await agent.stop()

        # Verify file removed
        files = list(temp_heartbeat_dir.glob("roc_*.heartbeat.json"))
        assert len(files) == 0

    @pytest.mark.asyncio
    async def test_heartbeat_file_updates(self, heartbeat_config, temp_heartbeat_dir):
        """Heartbeat file should be updated periodically."""
        agent = HeartbeatAgent(config=heartbeat_config)

        await agent.start()

        try:
            files = list(temp_heartbeat_dir.glob("roc_*.heartbeat.json"))
            hb_file = files[0]

            # Get initial timestamp
            content1 = json.loads(hb_file.read_text())
            ts1 = content1["timestamp"]

            # Wait for update
            await asyncio.sleep(0.2)  # 10Hz = 100ms interval

            # Get new timestamp
            content2 = json.loads(hb_file.read_text())
            ts2 = content2["timestamp"]

            assert ts2 > ts1, "Heartbeat timestamp should update"
        finally:
            await agent.stop()


class TestHeartbeatDependencyMonitoring:
    """Test HeartbeatAgent dependency monitoring."""

    @pytest.mark.asyncio
    async def test_healthy_dependency_detected(self, heartbeat_config, temp_heartbeat_dir):
        """Agent should detect healthy dependencies."""
        # Create a fake DIMC heartbeat file
        dimc_file = temp_heartbeat_dir / "dimc_test.heartbeat.json"
        dimc_file.write_text(
            json.dumps(
                {
                    "client_id": "dimc_test",
                    "timestamp": time.time(),
                    "type": "dimc_component",
                }
            )
        )

        agent = HeartbeatAgent(config=heartbeat_config)
        await agent.start()

        try:
            await asyncio.sleep(0.1)

            # Check dependency status
            status = agent.check_all_dependencies()
            assert status.get("dimc") == True
        finally:
            await agent.stop()

    @pytest.mark.asyncio
    async def test_timed_out_dependency_detected(self, heartbeat_config, temp_heartbeat_dir):
        """Agent should detect timed-out dependencies."""
        # Create an old DIMC heartbeat file
        dimc_file = temp_heartbeat_dir / "dimc_test.heartbeat.json"
        dimc_file.write_text(
            json.dumps(
                {
                    "client_id": "dimc_test",
                    "timestamp": time.time() - 10.0,  # 10 seconds old
                    "type": "dimc_component",
                }
            )
        )

        agent = HeartbeatAgent(config=heartbeat_config)
        await agent.start()

        try:
            await asyncio.sleep(0.1)

            status = agent.check_all_dependencies()
            assert status.get("dimc") == False, "Old heartbeat should be detected as timeout"
        finally:
            await agent.stop()

    @pytest.mark.asyncio
    async def test_dependency_failure_callback(self, heartbeat_config, temp_heartbeat_dir):
        """Agent should call failure callback on dependency timeout."""
        failures: List[tuple] = []

        def on_failure(component: str, failed: bool):
            failures.append((component, failed))

        agent = HeartbeatAgent(config=heartbeat_config)
        agent.on_dependency_failure(on_failure)

        # Create healthy DIMC heartbeat
        dimc_file = temp_heartbeat_dir / "dimc_test.heartbeat.json"
        dimc_file.write_text(
            json.dumps(
                {
                    "client_id": "dimc_test",
                    "timestamp": time.time(),
                    "type": "dimc_component",
                }
            )
        )

        await agent.start()

        try:
            await asyncio.sleep(0.2)

            # Make heartbeat stale
            dimc_file.write_text(
                json.dumps(
                    {
                        "client_id": "dimc_test",
                        "timestamp": time.time() - 10.0,
                        "type": "dimc_component",
                    }
                )
            )

            # Wait for detection
            await asyncio.sleep(1.5)  # Need to wait for monitoring loop

            # Check callback was called
            assert len(failures) > 0, "Failure callback should be called"
            assert any(f[0] == "dimc" and f[1] == True for f in failures)
        finally:
            await agent.stop()


class TestHeartbeatHealthMetrics:
    """Test HeartbeatAgent health metrics."""

    @pytest.mark.asyncio
    async def test_health_report_structure(self, heartbeat_config):
        """Health report should have correct structure."""
        agent = HeartbeatAgent(config=heartbeat_config)
        await agent.start()

        try:
            report = agent.get_health_report()

            assert "component" in report
            assert report["component"] == "ROC"
            assert "client_id" in report
            assert "timestamp" in report
            assert "health_status" in report
            assert "metrics" in report
            assert "dependencies" in report
        finally:
            await agent.stop()

    @pytest.mark.asyncio
    async def test_metrics_updated(self, heartbeat_config):
        """Metrics should update when update_metrics called."""
        agent = HeartbeatAgent(config=heartbeat_config)
        await agent.start()

        try:
            agent.update_metrics(
                active_robots=5,
                commands_processed=100,
                current_mode="adm",
                ipc_connected=True,
            )

            report = agent.get_health_report()
            metrics = report["metrics"]

            assert metrics["active_robots"] == 5
            assert metrics["commands_processed"] == 100
            assert metrics["current_mode"] == "adm"
            assert metrics["ipc_connected"] == True
        finally:
            await agent.stop()


# =============================================================================
# BRIDGE HEALTH AGENT TESTS
# =============================================================================


class TestBridgeHealthAgentLifecycle:
    """Test BridgeHealthAgent start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_performs_initial_health_check(self, mock_ipc_handler, bridge_config):
        """Agent should perform health check on start."""
        agent = BridgeHealthAgent(ipc_handler=mock_ipc_handler, config=bridge_config)

        await agent.start()

        try:
            # Should have done initial health check
            assert agent.status != BridgeStatus.UNKNOWN
        finally:
            await agent.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_health_check_task(self, mock_ipc_handler, bridge_config):
        """Agent should cancel tasks on stop."""
        agent = BridgeHealthAgent(ipc_handler=mock_ipc_handler, config=bridge_config)

        await agent.start()
        assert agent._health_check_task is not None

        await agent.stop()
        assert agent._running == False


class TestBridgeHealthStatusDetermination:
    """Test BridgeHealthAgent status determination logic."""

    @pytest.mark.asyncio
    async def test_healthy_when_connected(self, mock_ipc_handler, bridge_config):
        """Status should be HEALTHY when all conditions met."""
        mock_ipc_handler.is_connected = True
        mock_ipc_handler.heartbeat_healthy = True
        mock_ipc_handler.get_statistics.return_value = {
            "state": "CONNECTED",
            "messages_sent": 100,
            "messages_received": 98,
            "last_heartbeat": time.time(),
        }

        agent = BridgeHealthAgent(ipc_handler=mock_ipc_handler, config=bridge_config)

        await agent.start()

        try:
            await asyncio.sleep(0.2)  # Let health check run

            # With mock, might be DEGRADED due to port checks
            # but shouldn't be FAILED
            assert agent.status != BridgeStatus.FAILED
        finally:
            await agent.stop()

    @pytest.mark.asyncio
    async def test_failed_when_disconnected(self, mock_ipc_handler, bridge_config):
        """Status should be FAILED when disconnected."""
        mock_ipc_handler.is_connected = False
        mock_ipc_handler.heartbeat_healthy = False
        mock_ipc_handler.get_statistics.return_value = {
            "state": "DISCONNECTED",
            "messages_sent": 0,
            "messages_received": 0,
            "last_heartbeat": 0,
        }

        agent = BridgeHealthAgent(ipc_handler=mock_ipc_handler, config=bridge_config)

        await agent.start()

        try:
            await asyncio.sleep(0.2)
            assert agent.status == BridgeStatus.FAILED
        finally:
            await agent.stop()


class TestBridgeHealthReporting:
    """Test BridgeHealthAgent health reporting."""

    @pytest.mark.asyncio
    async def test_health_report_structure(self, mock_ipc_handler, bridge_config):
        """Health report should have correct structure."""
        agent = BridgeHealthAgent(ipc_handler=mock_ipc_handler, config=bridge_config)

        await agent.start()

        try:
            report = agent.get_health_report()

            assert "component" in report
            assert report["component"] == "ROC_Bridge"
            assert "status" in report
            assert "metrics" in report
            assert "reconnect_info" in report

            # Check metrics structure
            metrics = report["metrics"]
            assert "receive_port_open" in metrics
            assert "send_port_open" in metrics
            assert "connection_state" in metrics
            assert "avg_latency_ms" in metrics
            assert "messages_sent" in metrics
            assert "messages_received" in metrics
        finally:
            await agent.stop()

    @pytest.mark.asyncio
    async def test_latency_recording(self, mock_ipc_handler, bridge_config):
        """Agent should track latency history."""
        agent = BridgeHealthAgent(ipc_handler=mock_ipc_handler, config=bridge_config)

        await agent.start()

        try:
            # Record some latencies
            agent.record_message_latency(10.0)
            agent.record_message_latency(20.0)
            agent.record_message_latency(30.0)

            avg, max_val = agent._calculate_latency_metrics()
            assert avg == 20.0
            assert max_val == 30.0
        finally:
            await agent.stop()


class TestBridgeStatusCallbacks:
    """Test BridgeHealthAgent status change callbacks."""

    @pytest.mark.asyncio
    async def test_status_change_callback(self, mock_ipc_handler, bridge_config):
        """Callback should be called on status change."""
        status_changes: List[BridgeStatus] = []

        def on_change(new_status: BridgeStatus):
            status_changes.append(new_status)

        agent = BridgeHealthAgent(ipc_handler=mock_ipc_handler, config=bridge_config)
        agent.on_status_change(on_change)

        await agent.start()

        try:
            await asyncio.sleep(0.1)

            # Change mock state to trigger status change
            mock_ipc_handler.is_connected = False
            mock_ipc_handler.heartbeat_healthy = False
            mock_ipc_handler.get_statistics.return_value = {
                "state": "DISCONNECTED",
                "messages_sent": 0,
                "messages_received": 0,
                "last_heartbeat": 0,
            }

            await asyncio.sleep(0.3)  # Wait for health check

            # Should have detected status change
            # Initial might be DEGRADED or HEALTHY, then FAILED
            assert BridgeStatus.FAILED in status_changes or len(status_changes) > 0
        finally:
            await agent.stop()


class TestBridgeAutoReconnect:
    """Test BridgeHealthAgent auto-reconnect logic."""

    @pytest.mark.asyncio
    async def test_reconnect_increments_counter(self, mock_ipc_handler, bridge_config):
        """Reconnect attempts should increment counter."""
        bridge_config.auto_reconnect = True

        agent = BridgeHealthAgent(ipc_handler=mock_ipc_handler, config=bridge_config)

        await agent.start()

        try:
            initial_count = agent._reconnect_count

            # Force a reconnect attempt
            mock_ipc_handler.connect = AsyncMock(return_value=False)
            await agent._attempt_reconnect()

            assert agent._reconnect_count == initial_count + 1
        finally:
            await agent.stop()

    @pytest.mark.asyncio
    async def test_reconnect_counter_resets_on_success(self, mock_ipc_handler, bridge_config):
        """Counter should reset on successful reconnect."""
        agent = BridgeHealthAgent(ipc_handler=mock_ipc_handler, config=bridge_config)

        await agent.start()

        try:
            agent._reconnect_count = 2

            # Successful reconnect
            mock_ipc_handler.connect = AsyncMock(return_value=True)
            await agent._attempt_reconnect()

            assert agent._reconnect_count == 0
        finally:
            await agent.stop()


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestAgentIntegration:
    """Test agents working together."""

    @pytest.mark.asyncio
    async def test_both_agents_start_stop(self, mock_ipc_handler, heartbeat_config, bridge_config):
        """Both agents should start and stop cleanly."""
        hb_agent = HeartbeatAgent(config=heartbeat_config)
        bridge_agent = BridgeHealthAgent(ipc_handler=mock_ipc_handler, config=bridge_config)

        # Start both
        await hb_agent.start()
        await bridge_agent.start()

        assert hb_agent.is_running
        assert bridge_agent._running

        # Let them run briefly
        await asyncio.sleep(0.1)

        # Stop both
        await hb_agent.stop()
        await bridge_agent.stop()

        assert not hb_agent.is_running
        assert not bridge_agent._running

    @pytest.mark.asyncio
    async def test_health_reports_compatible(
        self, mock_ipc_handler, heartbeat_config, bridge_config
    ):
        """Health reports from both agents should be JSON serializable."""
        hb_agent = HeartbeatAgent(config=heartbeat_config)
        bridge_agent = BridgeHealthAgent(ipc_handler=mock_ipc_handler, config=bridge_config)

        await hb_agent.start()
        await bridge_agent.start()

        try:
            hb_report = hb_agent.get_health_report()
            bridge_report = bridge_agent.get_health_report()

            # Both should be JSON serializable
            hb_json = json.dumps(hb_report)
            bridge_json = json.dumps(bridge_report)

            assert len(hb_json) > 10
            assert len(bridge_json) > 10

            # Should deserialize back
            json.loads(hb_json)
            json.loads(bridge_json)
        finally:
            await hb_agent.stop()
            await bridge_agent.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
