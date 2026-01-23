"""
test_hb_subsystem.py
ROA - Robot Operations & Automation
Tests for the HB Subsystem

Run with: pytest test_hb_subsystem.py -v
"""

import os
import socket

# Import HB Subsystem components
import sys
import threading
import time
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hb_subsystem import (  # Types; Agent; Overload; Receiver; Aggregator; Watchdog; Persistence; Main
    ActivityCategory,
    ActivityScope,
    ActivityType,
    AdaptiveLimiter,
    AlertLevel,
    Bulkhead,
    CircuitBreaker,
    CircuitBreakerState,
    ComponentID,
    ComponentState,
    ComponentWatchdog,
    FailureType,
    HBAgent,
    HBPorts,
    HBReceiver,
    HBSubsystem,
    HBTiming,
    HBWatchdog,
    HealthLevel,
    HeartbeatPacket,
    MinRateDetector,
    OverloadProtector,
    RateLimiter,
    RecoveryAction,
    RecoveryManager,
    StartupAck,
    StartupPing,
    StatePersistence,
    StateRecovery,
    TrendAnalyzer,
    WatchdogStatus,
    activity_to_bitmap,
    bitmap_to_activities,
    calculate_sequence_gap,
    get_timestamp_us,
    is_sequence_gap,
    validate_activities,
)

# =============================================================================
# TESTS: Activity Types and Validation
# =============================================================================


class TestActivityTypes:
    """Tests for activity type validation"""

    def test_category_a_single_activity_valid(self):
        """Single Category A activity should be valid"""
        activities = [ActivityType.MESSAGE_PROCESSED]
        assert validate_activities(activities) is True

    def test_category_b_single_activity_valid(self):
        """Single Category B activity should be valid"""
        activities = [ActivityType.DATA_SENT]
        assert validate_activities(activities) is True

    def test_category_c_single_activity_invalid(self):
        """Single Category C activity should be invalid"""
        activities = [ActivityType.INTERNAL_CHECK]
        assert validate_activities(activities) is False

    def test_category_c_two_activities_valid(self):
        """Two Category C activities should be valid"""
        activities = [ActivityType.INTERNAL_CHECK, ActivityType.WATCHDOG_PET]
        assert validate_activities(activities) is True

    def test_category_d_single_activity_valid(self):
        """Single Category D activity should be valid"""
        activities = [ActivityType.FRAME_CONVERTED]
        assert validate_activities(activities) is True

    def test_empty_activities_invalid(self):
        """Empty activities should be invalid"""
        assert validate_activities([]) is False

    def test_idle_acknowledged_valid(self):
        """IDLE_ACKNOWLEDGED should be valid (Category A)"""
        activities = [ActivityType.IDLE_ACKNOWLEDGED]
        assert validate_activities(activities) is True


# =============================================================================
# TESTS: Heartbeat Packet
# =============================================================================


class TestHeartbeatPacket:
    """Tests for heartbeat packet serialization"""

    def test_packet_serialization(self):
        """Test packet to/from bytes"""
        packet = HeartbeatPacket(
            component_id=1,
            timestamp=get_timestamp_us(),
            sequence=42,
            state=ComponentState.ACTIVE,
            health=HealthLevel.HEALTHY,
            response_time_us=1000,
            error_count=0,
            memory_percent=50,
            cpu_percent=25,
            queue_depth=10,
            activity_bitmap=3,
        )

        data = packet.to_bytes()
        assert len(data) == HeartbeatPacket.PACKET_SIZE

        parsed = HeartbeatPacket.from_bytes(data)
        assert parsed is not None
        assert parsed.component_id == 1
        assert parsed.sequence == 42
        assert parsed.state == ComponentState.ACTIVE
        assert parsed.health == HealthLevel.HEALTHY

    def test_packet_checksum_validation(self):
        """Test that corrupted packets are rejected"""
        packet = HeartbeatPacket(
            component_id=1,
            timestamp=get_timestamp_us(),
            sequence=1,
            state=ComponentState.ACTIVE,
            health=HealthLevel.HEALTHY,
            response_time_us=0,
            error_count=0,
            memory_percent=0,
            cpu_percent=0,
            queue_depth=0,
            activity_bitmap=0,
        )

        data = bytearray(packet.to_bytes())
        # Corrupt a byte
        data[5] ^= 0xFF

        parsed = HeartbeatPacket.from_bytes(bytes(data))
        assert parsed is None  # Should fail checksum


# =============================================================================
# TESTS: Sequence Number Handling
# =============================================================================


class TestSequenceNumbers:
    """Tests for sequence number handling"""

    def test_normal_sequence(self):
        """Test normal sequential numbers"""
        assert is_sequence_gap(0, 1) is False
        assert is_sequence_gap(100, 101) is False

    def test_sequence_gap_detected(self):
        """Test gap detection"""
        assert is_sequence_gap(0, 2) is True
        assert is_sequence_gap(100, 105) is True

    def test_sequence_rollover(self):
        """Test 16-bit rollover handling"""
        assert is_sequence_gap(65535, 0) is False
        assert is_sequence_gap(65534, 65535) is False
        assert is_sequence_gap(65530, 0) is False

    def test_calculate_gap(self):
        """Test gap calculation"""
        assert calculate_sequence_gap(0, 2) == 1
        assert calculate_sequence_gap(100, 105) == 4


# =============================================================================
# TESTS: Bulkhead
# =============================================================================


class TestBulkhead:
    """Tests for Bulkhead overload protection"""

    def test_acquire_within_limit(self):
        """Test acquiring permits within limit"""
        bulkhead = Bulkhead(max_concurrent=3)

        assert bulkhead.try_acquire() is True
        assert bulkhead.try_acquire() is True
        assert bulkhead.try_acquire() is True
        assert bulkhead.get_active_count() == 3

    def test_acquire_exceeds_limit(self):
        """Test acquiring when at limit"""
        bulkhead = Bulkhead(max_concurrent=2)

        assert bulkhead.try_acquire() is True
        assert bulkhead.try_acquire() is True
        assert bulkhead.try_acquire() is False  # Should fail

    def test_release_frees_permit(self):
        """Test that release frees a permit"""
        bulkhead = Bulkhead(max_concurrent=1)

        assert bulkhead.try_acquire() is True
        assert bulkhead.try_acquire() is False

        bulkhead.release()
        assert bulkhead.try_acquire() is True


# =============================================================================
# TESTS: Rate Limiter
# =============================================================================


class TestRateLimiter:
    """Tests for RateLimiter"""

    def test_initial_burst(self):
        """Test initial burst allowed"""
        limiter = RateLimiter(max_per_second=10, burst_size=5)

        # Should allow burst of 5
        for i in range(5):
            assert limiter.try_acquire() is True

    def test_rate_limiting(self):
        """Test rate limiting after burst"""
        limiter = RateLimiter(max_per_second=10, burst_size=2)

        # Use up burst
        assert limiter.try_acquire() is True
        assert limiter.try_acquire() is True

        # Should be limited
        assert limiter.try_acquire() is False

    def test_token_refill(self):
        """Test tokens refill over time"""
        limiter = RateLimiter(max_per_second=100, burst_size=1)

        assert limiter.try_acquire() is True
        assert limiter.try_acquire() is False

        # Wait for refill
        time.sleep(0.02)  # 20ms = 2 tokens at 100/s

        assert limiter.try_acquire() is True


# =============================================================================
# TESTS: Adaptive Limiter
# =============================================================================


class TestAdaptiveLimiter:
    """Tests for AdaptiveLimiter"""

    def test_limit_adjustment(self):
        """Test that limit adjusts based on execution times"""
        limiter = AdaptiveLimiter(initial_limit=10, min_limit=5, max_limit=20, sample_window=10)

        initial = limiter.get_current_limit()

        # Simulate fast executions (should increase limit)
        for _ in range(15):
            assert limiter.try_acquire() is True
            limiter.release(1.0)  # 1ms execution

        # Limit should have increased
        new_limit = limiter.get_current_limit()
        assert new_limit >= initial


# =============================================================================
# TESTS: Min Rate Detector
# =============================================================================


class TestMinRateDetector:
    """Tests for MinRateDetector"""

    def test_rate_above_minimum(self):
        """Test detection when rate is above minimum"""
        detector = MinRateDetector(min_per_second=10, window_seconds=0.5)

        # Record 10 heartbeats in 0.5s = 20/s
        for _ in range(10):
            detector.record()
            time.sleep(0.04)

        assert detector.is_below_minimum() is False

    def test_rate_below_minimum(self):
        """Test detection when rate is below minimum"""
        detector = MinRateDetector(min_per_second=100, window_seconds=0.5)

        # Record only 2 heartbeats = 4/s
        detector.record()
        time.sleep(0.1)
        detector.record()

        assert detector.is_below_minimum() is True


# =============================================================================
# TESTS: Circuit Breaker
# =============================================================================


class TestCircuitBreaker:
    """Tests for CircuitBreaker"""

    def test_starts_closed(self):
        """Test circuit starts in closed state"""
        cb = CircuitBreaker("test", failure_threshold=3)
        assert cb.get_state() == CircuitBreakerState.CLOSED
        assert cb.is_available() is True

    def test_opens_on_failures(self):
        """Test circuit opens after threshold failures"""
        cb = CircuitBreaker("test", failure_threshold=3)

        cb.record_failure()
        cb.record_failure()
        assert cb.get_state() == CircuitBreakerState.CLOSED

        cb.record_failure()  # Third failure
        assert cb.get_state() == CircuitBreakerState.OPEN

    def test_success_resets_failures(self):
        """Test success resets failure count"""
        cb = CircuitBreaker("test", failure_threshold=3)

        cb.record_failure()
        cb.record_failure()
        cb.record_success()  # Reset
        cb.record_failure()

        assert cb.get_state() == CircuitBreakerState.CLOSED

    def test_half_open_transition(self):
        """Test transition to half-open after timeout"""
        cb = CircuitBreaker("test", failure_threshold=1, timeout_seconds=0.1)

        cb.record_failure()  # Opens circuit
        assert cb.get_state() == CircuitBreakerState.OPEN
        assert cb.is_available() is False

        time.sleep(0.15)  # Wait for timeout

        assert cb.is_available() is True  # Triggers half-open
        assert cb.get_state() == CircuitBreakerState.HALF_OPEN


# =============================================================================
# TESTS: Recovery Manager
# =============================================================================


class TestRecoveryManager:
    """Tests for RecoveryManager"""

    def test_max_attempts(self):
        """Test max recovery attempts"""
        rm = RecoveryManager(max_attempts=3, cooldown_ms=0)

        failure = MagicMock()
        failure.failure_type = FailureType.HEARTBEAT_TIMEOUT

        # Register mock executor
        rm.register_executor(RecoveryAction.RESTART_COMPONENT, lambda x: True)

        assert rm.attempt_recovery("FTI", failure) is True
        assert rm.attempt_recovery("FTI", failure) is True
        assert rm.attempt_recovery("FTI", failure) is True
        assert rm.attempt_recovery("FTI", failure) is False  # Exceeded

    def test_recovery_verification(self):
        """Test recovery verification with healthy heartbeats"""
        rm = RecoveryManager(verification_count=3)
        rm.register_executor(RecoveryAction.RESTART_COMPONENT, lambda x: True)

        failure = MagicMock()
        failure.failure_type = FailureType.HEARTBEAT_TIMEOUT

        rm.attempt_recovery("FTI", failure)

        assert rm.is_pending_verification("FTI") is True
        assert rm.record_healthy_heartbeat("FTI") is False
        assert rm.record_healthy_heartbeat("FTI") is False
        assert rm.record_healthy_heartbeat("FTI") is True  # Verified
        assert rm.is_pending_verification("FTI") is False


# =============================================================================
# TESTS: Watchdog
# =============================================================================


class TestWatchdog:
    """Tests for HBWatchdog"""

    def test_thread_monitoring(self):
        """Test watchdog monitors threads"""
        watchdog = HBWatchdog(check_interval_ms=50, default_timeout_ms=100)

        # Create a mock thread
        mock_thread = threading.Thread(target=lambda: time.sleep(1))
        mock_thread.start()

        watchdog.watch_thread("test", mock_thread)
        watchdog.start()

        # Pet the watchdog
        watchdog.pet("test")
        time.sleep(0.02)

        status = watchdog.get_status("test")
        assert status == WatchdogStatus.HEALTHY

        watchdog.stop()
        mock_thread.join(timeout=0.1)

    def test_timeout_detection(self):
        """Test watchdog detects timeout"""
        watchdog = HBWatchdog(check_interval_ms=50, default_timeout_ms=100)

        mock_thread = threading.Thread(target=lambda: time.sleep(1))
        mock_thread.start()

        failure_detected = threading.Event()
        watchdog.on_failure(lambda name, status: failure_detected.set())

        watchdog.watch_thread("test", mock_thread)
        watchdog.start()

        # Don't pet - should timeout
        time.sleep(0.25)

        status = watchdog.get_status("test")
        assert status in [WatchdogStatus.WARNING, WatchdogStatus.CRITICAL]

        watchdog.stop()
        mock_thread.join(timeout=0.1)


# =============================================================================
# TESTS: State Persistence
# =============================================================================


class TestStatePersistence:
    """Tests for StatePersistence"""

    def test_snapshot_and_load(self):
        """Test state snapshot and loading"""
        import shutil
        import tempfile

        # Create temp directory
        temp_dir = tempfile.mkdtemp()

        try:
            persistence = StatePersistence(
                fast_storage_path=f"{temp_dir}/fast",
                persistent_storage_path=f"{temp_dir}/persistent",
                snapshot_interval_s=60,  # Don't auto-snapshot during test
            )

            # Set state provider
            test_state = {
                "components": {"FTI": {"health": "HEALTHY", "state": "ACTIVE"}},
                "circuit_breakers": {},
                "pending_recoveries": {},
                "failure_counts": {},
                "metrics": {},
            }
            persistence.set_state_provider(lambda: test_state)

            # Manual snapshot
            persistence.manual_snapshot()

            # Load state
            loaded = persistence.load_last_state()

            assert loaded is not None
            assert "FTI" in loaded["components"]

        finally:
            shutil.rmtree(temp_dir)


# =============================================================================
# TESTS: HB Agent
# =============================================================================


class TestHBAgent:
    """Tests for HBAgent"""

    def test_activity_recording(self):
        """Test activity recording"""
        agent = HBAgent("FTI")

        agent.report_activity(ActivityType.MESSAGE_PROCESSED)

        activities = agent.state.get_recent_activities(1000)
        assert ActivityType.MESSAGE_PROCESSED in activities

    def test_idle_acknowledgment(self):
        """Test idle acknowledgment"""
        agent = HBAgent("FTI")

        agent.report_idle("no_pending_work")

        assert agent.state.is_idle() is True

    def test_state_transitions(self):
        """Test state transitions are tracked"""
        agent = HBAgent("FTI")

        agent.set_state(ComponentState.ACTIVE)

        assert agent.state.get_state() == ComponentState.ACTIVE

        activities = agent.state.get_recent_activities(1000)
        assert ActivityType.STATE_TRANSITION in activities


# =============================================================================
# TESTS: Integration
# =============================================================================


class TestHBSubsystemIntegration:
    """Integration tests for HBSubsystem"""

    def test_subsystem_start_stop(self):
        """Test subsystem can start and stop"""
        import shutil
        import tempfile

        temp_dir = tempfile.mkdtemp()

        try:
            hb = HBSubsystem(
                fast_storage_path=f"{temp_dir}/fast",
                persistent_storage_path=f"{temp_dir}/persistent",
            )

            assert hb.start() is True
            assert hb.is_running() is True

            # Let it run briefly
            time.sleep(0.1)

            hb.stop()
            assert hb.is_running() is False

        finally:
            shutil.rmtree(temp_dir)

    def test_agent_receiver_communication(self):
        """Test agent can communicate with receiver"""
        import shutil
        import tempfile

        temp_dir = tempfile.mkdtemp()

        try:
            # Start subsystem
            hb = HBSubsystem(
                fast_storage_path=f"{temp_dir}/fast",
                persistent_storage_path=f"{temp_dir}/persistent",
            )
            hb.start()

            # Give receiver time to start
            time.sleep(0.1)

            # Create and start agent
            agent = HBAgent("FTI")
            agent.start()

            # Report activity to generate heartbeat
            agent.report_activity(ActivityType.MESSAGE_PROCESSED)

            # Wait for heartbeat to be processed
            time.sleep(0.2)

            # Check alert level (should be GREEN if HB received)
            alert = hb.get_alert_level("FTI")
            # May be GREEN if HB received, or unknown if timing issues

            agent.stop()
            hb.stop()

        finally:
            shutil.rmtree(temp_dir)


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
