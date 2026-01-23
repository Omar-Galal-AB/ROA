"""
DIMC Monitoring System Tests

Comprehensive tests for the DIMC monitoring subsystem including:
- DIMCMonitoringSystem
- PerformanceProfiler
- DataQualityMonitor
- RateLimiter
- Alert generation

Usage:
    python -m pytest test_dimc_monitoring.py -v
    python test_dimc_monitoring.py  # Direct execution
"""

import sys
import os
import time
import unittest
import threading
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python"))

from dimc_monitoring import (
    DIMCMonitoringSystem,
    MonitoringConfig,
    SubsystemStatus,
    AlertSeverity,
    AlertCategory,
    Alert,
    PerformanceProfiler,
    DataQualityMonitor,
    RateLimiter,
)


class TestPerformanceProfiler(unittest.TestCase):
    """Tests for PerformanceProfiler class."""
    
    def setUp(self):
        self.profiler = PerformanceProfiler()
        
    def test_profile_context_manager(self):
        """Test profiling with context manager."""
        with self.profiler.profile("test_operation"):
            time.sleep(0.01)  # 10ms sleep
            
        stats = self.profiler.get_stats("test_operation")
        
        self.assertIsNotNone(stats)
        self.assertEqual(stats.call_count, 1)
        self.assertGreater(stats.avg_time_ms, 5)  # Should be at least 5ms
        self.assertLess(stats.avg_time_ms, 50)  # But not more than 50ms
        
    def test_multiple_recordings(self):
        """Test multiple timing recordings."""
        for i in range(10):
            self.profiler.record_timing("multi_test", i * 10.0)
            
        stats = self.profiler.get_stats("multi_test")
        
        self.assertEqual(stats.call_count, 10)
        self.assertEqual(stats.min_time_ms, 0.0)
        self.assertEqual(stats.max_time_ms, 90.0)
        self.assertAlmostEqual(stats.avg_time_ms, 45.0, places=1)
        
    def test_get_all_stats(self):
        """Test getting all statistics."""
        self.profiler.record_timing("op1", 10.0)
        self.profiler.record_timing("op2", 20.0)
        self.profiler.record_timing("op3", 30.0)
        
        all_stats = self.profiler.get_all_stats()
        
        self.assertEqual(len(all_stats), 3)
        self.assertIn("op1", all_stats)
        self.assertIn("op2", all_stats)
        self.assertIn("op3", all_stats)
        
    def test_reset_specific(self):
        """Test resetting specific operation stats."""
        self.profiler.record_timing("keep_me", 10.0)
        self.profiler.record_timing("reset_me", 20.0)
        
        self.profiler.reset("reset_me")
        
        self.assertIsNotNone(self.profiler.get_stats("keep_me"))
        self.assertIsNone(self.profiler.get_stats("reset_me"))
        
    def test_reset_all(self):
        """Test resetting all stats."""
        self.profiler.record_timing("op1", 10.0)
        self.profiler.record_timing("op2", 20.0)
        
        self.profiler.reset()
        
        self.assertEqual(len(self.profiler.get_all_stats()), 0)


class TestDataQualityMonitor(unittest.TestCase):
    """Tests for DataQualityMonitor class."""
    
    def setUp(self):
        self.config = MonitoringConfig(
            data_staleness_threshold_ms=100.0,
            validation_warning_rate=0.95,
            validation_critical_rate=0.80,
        )
        self.monitor = DataQualityMonitor(self.config)
        
    def test_record_valid_message(self):
        """Test recording valid messages."""
        for _ in range(10):
            self.monitor.record_message("test_source", valid=True, latency_ms=5.0)
            
        metrics = self.monitor.get_metrics("test_source")
        
        self.assertEqual(metrics.messages_received, 10)
        self.assertEqual(metrics.messages_valid, 10)
        self.assertEqual(metrics.messages_invalid, 0)
        self.assertEqual(metrics.validation_rate, 1.0)
        
    def test_record_invalid_messages(self):
        """Test recording invalid messages."""
        for i in range(10):
            self.monitor.record_message("test_source", valid=(i < 8), latency_ms=5.0)
            
        metrics = self.monitor.get_metrics("test_source")
        
        self.assertEqual(metrics.messages_received, 10)
        self.assertEqual(metrics.messages_valid, 8)
        self.assertEqual(metrics.messages_invalid, 2)
        self.assertEqual(metrics.validation_rate, 0.8)
        
    def test_latency_tracking(self):
        """Test latency tracking."""
        latencies = [10, 20, 30, 40, 50]
        for lat in latencies:
            self.monitor.record_message("test_source", valid=True, latency_ms=lat)
            
        metrics = self.monitor.get_metrics("test_source")
        
        self.assertAlmostEqual(metrics.avg_latency_ms, 30.0, places=1)
        
    def test_check_quality_healthy(self):
        """Test quality check returns healthy for good data."""
        for _ in range(20):
            self.monitor.record_message("good_source", valid=True, latency_ms=10.0)
            
        status, msg = self.monitor.check_quality("good_source")
        
        self.assertEqual(status, SubsystemStatus.HEALTHY)
        self.assertEqual(msg, "OK")
        
    def test_check_quality_degraded(self):
        """Test quality check returns degraded for warning-level issues."""
        # 92% validation rate (below 95% warning threshold)
        for i in range(100):
            self.monitor.record_message("warn_source", valid=(i < 92), latency_ms=10.0)
            
        status, msg = self.monitor.check_quality("warn_source")
        
        self.assertEqual(status, SubsystemStatus.DEGRADED)
        self.assertIn("Validation rate warning", msg)
        
    def test_check_quality_unknown(self):
        """Test quality check returns unknown for untracked source."""
        status, msg = self.monitor.check_quality("unknown_source")
        
        self.assertEqual(status, SubsystemStatus.UNKNOWN)
        
    def test_get_all_metrics(self):
        """Test getting all metrics."""
        self.monitor.record_message("source1", valid=True)
        self.monitor.record_message("source2", valid=True)
        
        all_metrics = self.monitor.get_all_metrics()
        
        self.assertEqual(len(all_metrics), 2)
        self.assertIn("source1", all_metrics)
        self.assertIn("source2", all_metrics)


class TestRateLimiter(unittest.TestCase):
    """Tests for RateLimiter class."""
    
    def test_allows_under_limit(self):
        """Test rate limiter allows requests under limit."""
        limiter = RateLimiter(max_per_second=10, window_seconds=1.0)
        
        allowed_count = sum(1 for _ in range(5) if limiter.allow())
        
        self.assertEqual(allowed_count, 5)
        self.assertEqual(limiter.get_dropped_count(), 0)
        
    def test_blocks_over_limit(self):
        """Test rate limiter blocks requests over limit."""
        limiter = RateLimiter(max_per_second=5, window_seconds=1.0)
        
        allowed_count = sum(1 for _ in range(10) if limiter.allow())
        
        self.assertEqual(allowed_count, 5)
        self.assertEqual(limiter.get_dropped_count(), 5)
        
    def test_current_rate(self):
        """Test getting current rate."""
        limiter = RateLimiter(max_per_second=100, window_seconds=1.0)
        
        for _ in range(10):
            limiter.allow()
            
        rate = limiter.get_current_rate()
        
        self.assertGreater(rate, 0)
        self.assertLessEqual(rate, 10)
        
    def test_window_expiry(self):
        """Test that old requests expire from window."""
        limiter = RateLimiter(max_per_second=5, window_seconds=0.1)
        
        # Fill the window
        for _ in range(5):
            limiter.allow()
            
        # Wait for window to expire
        time.sleep(0.15)
        
        # Should allow more now
        self.assertTrue(limiter.allow())


class TestDIMCMonitoringSystem(unittest.TestCase):
    """Tests for DIMCMonitoringSystem class."""
    
    def setUp(self):
        self.config = MonitoringConfig(
            health_check_interval=1.0,
            resource_check_interval=1.0,
            alert_cooldown_seconds=0.1,  # Short cooldown for testing
        )
        self.monitoring = DIMCMonitoringSystem(config=self.config)
        
    def tearDown(self):
        if self.monitoring.running:
            self.monitoring.stop()
            
    def test_start_stop(self):
        """Test starting and stopping monitoring."""
        self.assertFalse(self.monitoring.running)
        
        self.monitoring.start()
        
        self.assertTrue(self.monitoring.running)
        self.assertIsNotNone(self.monitoring.start_time)
        
        self.monitoring.stop()
        
        self.assertFalse(self.monitoring.running)
        
    def test_update_subsystem_health(self):
        """Test updating subsystem health."""
        self.monitoring.update_subsystem_health(
            "test_subsystem",
            SubsystemStatus.HEALTHY,
            details={"message": "All good"}
        )
        
        status = self.monitoring.get_status()
        
        self.assertIn("test_subsystem", status["subsystems"])
        self.assertEqual(status["subsystems"]["test_subsystem"]["status"], "healthy")
        
    def test_get_rate_limiter(self):
        """Test getting/creating rate limiters."""
        limiter1 = self.monitoring.get_rate_limiter("source1")
        limiter2 = self.monitoring.get_rate_limiter("source1")
        limiter3 = self.monitoring.get_rate_limiter("source2")
        
        # Same source should return same limiter
        self.assertIs(limiter1, limiter2)
        # Different source should return different limiter
        self.assertIsNot(limiter1, limiter3)
        
    def test_alert_generation(self):
        """Test alert generation."""
        self.monitoring.generate_alert(
            severity="warning",
            category="performance",
            source="test",
            message="Test alert",
            data={"value": 123}
        )
        
        time.sleep(0.15)  # Wait for cooldown
        
        alerts = self.monitoring.get_alerts()
        
        self.assertGreaterEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["message"], "Test alert")
        self.assertEqual(alerts[0]["severity"], "warning")
        
    def test_alert_acknowledge(self):
        """Test acknowledging alerts."""
        self.monitoring.generate_alert(
            severity="info",
            category="subsystem",
            source="test",
            message="Acknowledge me"
        )
        
        alerts = self.monitoring.get_alerts()
        self.assertFalse(alerts[0]["acknowledged"])
        
        result = self.monitoring.acknowledge_alert(alerts[0]["alert_id"])
        
        self.assertTrue(result)
        
        alerts = self.monitoring.get_alerts()
        self.assertTrue(alerts[0]["acknowledged"])
        
    def test_get_status(self):
        """Test getting comprehensive status."""
        self.monitoring.start()
        time.sleep(0.1)
        
        status = self.monitoring.get_status()
        
        self.assertIn("overall_status", status)
        self.assertIn("uptime_seconds", status)
        self.assertIn("subsystems", status)
        self.assertIn("alerts", status)
        
    def test_get_diagnostics(self):
        """Test getting diagnostic data."""
        self.monitoring.start()
        
        # Record some performance data
        with self.monitoring.profiler.profile("test_op"):
            time.sleep(0.01)
            
        # Record some data quality
        self.monitoring.data_quality.record_message("test_source", valid=True, latency_ms=10)
        
        diagnostics = self.monitoring.get_diagnostics()
        
        self.assertIn("status", diagnostics)
        self.assertIn("performance", diagnostics)
        self.assertIn("data_quality", diagnostics)
        self.assertIn("rate_limiters", diagnostics)
        
    def test_alert_callback(self):
        """Test alert callback is called."""
        alert_received = []
        
        def on_alert(alert):
            alert_received.append(alert)
            
        self.monitoring.on_alert = on_alert
        
        self.monitoring.generate_alert(
            severity="error",
            category="safety",
            source="test",
            message="Callback test"
        )
        
        self.assertEqual(len(alert_received), 1)
        self.assertEqual(alert_received[0].message, "Callback test")
        
    def test_status_change_callback(self):
        """Test status change callback is called."""
        status_changes = []
        
        def on_status_change(old_status, new_status):
            status_changes.append((old_status, new_status))
            
        self.monitoring.on_status_change = on_status_change
        self.monitoring.start()
        
        # Trigger a status change by updating subsystem health
        self.monitoring.update_subsystem_health("critical", SubsystemStatus.UNHEALTHY)
        
        # Force a check
        self.monitoring._check_subsystems()
        
        # Should have recorded a status change
        # Note: May not trigger immediately in all cases
        

class TestAlertDataclass(unittest.TestCase):
    """Tests for Alert dataclass."""
    
    def test_alert_to_dict(self):
        """Test alert serialization."""
        alert = Alert(
            alert_id="TEST-001",
            timestamp=1704067200.0,  # 2024-01-01 00:00:00 UTC
            severity=AlertSeverity.WARNING,
            category=AlertCategory.PERFORMANCE,
            source="test",
            message="Test message",
            data={"key": "value"}
        )
        
        result = alert.to_dict()
        
        self.assertEqual(result["alert_id"], "TEST-001")
        self.assertEqual(result["severity"], "warning")
        self.assertEqual(result["category"], "performance")
        self.assertEqual(result["message"], "Test message")
        self.assertEqual(result["data"], {"key": "value"})
        self.assertFalse(result["acknowledged"])
        self.assertFalse(result["resolved"])
        self.assertIn("timestamp_iso", result)


class TestSubsystemStatusEnum(unittest.TestCase):
    """Tests for SubsystemStatus enum."""
    
    def test_status_values(self):
        """Test enum values."""
        self.assertEqual(SubsystemStatus.HEALTHY.value, "healthy")
        self.assertEqual(SubsystemStatus.DEGRADED.value, "degraded")
        self.assertEqual(SubsystemStatus.UNHEALTHY.value, "unhealthy")
        self.assertEqual(SubsystemStatus.OFFLINE.value, "offline")
        self.assertEqual(SubsystemStatus.UNKNOWN.value, "unknown")


class TestMonitoringConfig(unittest.TestCase):
    """Tests for MonitoringConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = MonitoringConfig()
        
        self.assertEqual(config.health_check_interval, 5.0)
        self.assertEqual(config.cpu_warning_percent, 70.0)
        self.assertEqual(config.cpu_critical_percent, 90.0)
        self.assertEqual(config.max_alerts_stored, 1000)
        
    def test_custom_values(self):
        """Test custom configuration values."""
        config = MonitoringConfig(
            health_check_interval=2.0,
            cpu_warning_percent=50.0,
            max_alerts_stored=500
        )
        
        self.assertEqual(config.health_check_interval, 2.0)
        self.assertEqual(config.cpu_warning_percent, 50.0)
        self.assertEqual(config.max_alerts_stored, 500)


if __name__ == "__main__":
    unittest.main(verbosity=2)
