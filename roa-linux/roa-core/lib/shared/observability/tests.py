"""
ROA Observability Integration Tests
====================================
Tests for the complete observability stack
"""

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

# Add parent directory to path for package imports
_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# Import from package
from observability.config import (
    LoggingConfig,
    ObservabilityConfig,
    get_component_config,
)
from observability.health import (
    HealthCheck,
    HealthStatus,
    create_connection_check,
    create_memory_check,
)
from observability.mcap_recorder import MCAPRecorder, ROAEventRecorder
from observability.metrics import MetricsServer, ROAMetrics
from observability.observability import ROAObservability, setup_observability
from observability.structured_logger import ROALogger, get_logger
from observability.tracing import ROATracer


class TestStructuredLogger(unittest.TestCase):
    """Test structured logging"""

    def test_logger_creation(self):
        """Test logger can be created"""
        logger = get_logger("test_component")
        self.assertIsNotNone(logger)

    def test_json_logging(self):
        """Test JSON log output"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = LoggingConfig(
                log_dir=tmpdir,
                json_format=True,
                console_output=False,
            )

            logger = ROALogger("test", config=config)
            logger.info("Test message", extra={"key": "value"})

            # Check log file was created
            log_files = list(Path(tmpdir).glob("*.log"))
            self.assertEqual(len(log_files), 1)

            # Verify JSON format
            with open(log_files[0], "r") as f:
                line = f.readline()
                log_entry = json.loads(line)
                self.assertEqual(log_entry["message"], "Test message")
                self.assertEqual(log_entry["component"], "test")

    def test_context_manager(self):
        """Test context-based logging"""
        logger = ROALogger("test")

        with logger.context(trace_id="abc123", request_id="req1"):
            # Context should be available
            pass


class TestMetrics(unittest.TestCase):
    """Test Prometheus metrics"""

    _test_counter = 0

    @classmethod
    def _unique_name(cls):
        cls._test_counter += 1
        return f"metrics_test_{cls._test_counter}_{int(time.time()*1000)}"

    def test_metrics_creation(self):
        """Test metrics can be created"""
        metrics = ROAMetrics(self._unique_name())
        self.assertIsNotNone(metrics)

    def test_heartbeat_metrics(self):
        """Test heartbeat recording"""
        metrics = ROAMetrics(self._unique_name())
        metrics.record_heartbeat("target1", latency=0.005)
        # No assertion - just verify no exception

    def test_request_timing(self):
        """Test request timing context manager"""
        metrics = ROAMetrics(self._unique_name())

        with metrics.time_request("process", "api") as timer:
            time.sleep(0.01)
            timer.status = "success"

        # No assertion - just verify no exception

    def test_custom_metrics(self):
        """Test custom metric registration"""
        metrics = ROAMetrics(self._unique_name())

        counter = metrics.register_counter(
            "custom_counter",
            "Test counter",
            ["label1"],
        )
        counter.labels(label1="value").inc()


class TestTracing(unittest.TestCase):
    """Test OpenTelemetry tracing"""

    def test_tracer_creation(self):
        """Test tracer can be created"""
        tracer = ROATracer("test_component")
        self.assertIsNotNone(tracer)

    def test_span_creation(self):
        """Test span creation"""
        tracer = ROATracer("test")

        with tracer.start_span("test_operation") as span:
            span.set_attribute("key", "value")

    def test_nested_spans(self):
        """Test nested spans"""
        tracer = ROATracer("test")

        with tracer.start_span("parent"):
            with tracer.start_span("child"):
                pass

    def test_trace_decorator(self):
        """Test trace decorator"""
        tracer = ROATracer("test")

        @tracer.trace("decorated_function")
        def test_func():
            return "result"

        result = test_func()
        self.assertEqual(result, "result")


class TestHealthCheck(unittest.TestCase):
    """Test health checking"""

    def test_health_creation(self):
        """Test health check creation"""
        health = HealthCheck("test_component")
        self.assertIsNotNone(health)

    def test_status_transitions(self):
        """Test status transitions"""
        health = HealthCheck("test")

        health.set_initializing()
        self.assertEqual(health.get_status().status, HealthStatus.INITIALIZING)

        health.set_healthy()
        self.assertEqual(health.get_status().status, HealthStatus.HEALTHY)

        health.set_degraded()
        self.assertEqual(health.get_status().status, HealthStatus.DEGRADED)

    def test_simple_check_registration(self):
        """Test simple health check registration"""
        health = HealthCheck("test")

        health.register_simple_check("always_pass", lambda: True)
        health.register_simple_check("always_fail", lambda: False)

        results = health.run_all_checks()
        self.assertEqual(len(results), 2)

    def test_dependencies(self):
        """Test dependency tracking"""
        health = HealthCheck("test")

        health.add_dependency("dep1")
        health.add_dependency("dep2")

        health.update_dependency("dep1", HealthStatus.HEALTHY)
        health.update_dependency("dep2", HealthStatus.UNHEALTHY)

        status = health.get_status()
        self.assertIn("dep1", status.dependencies)
        self.assertIn("dep2", status.dependencies)


class TestMCAPRecorder(unittest.TestCase):
    """Test MCAP recording"""

    def test_recorder_creation(self):
        """Test recorder creation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from observability.config import MCAPConfig

            config = MCAPConfig(output_dir=tmpdir)
            recorder = MCAPRecorder("test", config=config)
            self.assertIsNotNone(recorder)

    def test_recording_lifecycle(self):
        """Test recording start/stop"""
        try:
            import mcap
        except ImportError:
            self.skipTest("mcap not installed")

        with tempfile.TemporaryDirectory() as tmpdir:
            from observability.config import MCAPConfig

            config = MCAPConfig(output_dir=tmpdir)
            recorder = MCAPRecorder("test", config=config)

            filepath = recorder.start_recording()
            self.assertTrue(filepath.endswith(".mcap"))

            stats = recorder.stop_recording()
            self.assertIsNotNone(stats)
            self.assertTrue(os.path.exists(filepath))


class TestROAObservability(unittest.TestCase):
    """Test unified observability"""

    _test_counter = 0

    @classmethod
    def _unique_name(cls):
        cls._test_counter += 1
        return f"obs_test_{cls._test_counter}_{int(time.time()*1000)}"

    def test_observability_creation(self):
        """Test observability creation"""
        obs = ROAObservability(self._unique_name())
        self.assertIsNotNone(obs)
        self.assertIsNotNone(obs.logger)
        self.assertIsNotNone(obs.metrics)
        self.assertIsNotNone(obs.tracer)
        self.assertIsNotNone(obs.health)

    def test_lifecycle(self):
        """Test start/stop lifecycle"""
        obs = ROAObservability(self._unique_name())
        obs.start(start_metrics_server=False, start_health_server=False)
        obs.set_ready()
        obs.stop()

    def test_context_manager(self):
        """Test context manager usage"""
        with ROAObservability(self._unique_name()) as obs:
            obs.logger.info("Test message")

    def test_setup_helper(self):
        """Test setup helper function"""
        obs = setup_observability(self._unique_name(), "1.0.0")
        self.assertIsNotNone(obs)
        obs.stop()


class TestConfig(unittest.TestCase):
    """Test configuration"""

    def test_default_config(self):
        """Test default configuration"""
        config = ObservabilityConfig()
        self.assertEqual(config.component_name, "roa-component")

    def test_component_config(self):
        """Test component-specific config"""
        config = get_component_config("webthread")
        self.assertEqual(config.component_name, "webthread")
        self.assertEqual(config.metrics.port, 9091)

    def test_env_config(self):
        """Test environment configuration"""
        os.environ["ROA_OBS_COMPONENT_NAME"] = "env_test"
        os.environ["ROA_OBS_METRICS_PORT"] = "9999"

        config = ObservabilityConfig.from_env()
        self.assertEqual(config.component_name, "env_test")
        self.assertEqual(config.metrics.port, 9999)

        # Cleanup
        del os.environ["ROA_OBS_COMPONENT_NAME"]
        del os.environ["ROA_OBS_METRICS_PORT"]


class TestIntegration(unittest.TestCase):
    """Integration tests"""

    def test_full_stack(self):
        """Test full observability stack"""
        obs = ROAObservability("integration_test", "1.0.0")
        obs.start(
            start_metrics_server=False,
            start_health_server=False,
            start_recording=False,
        )

        try:
            # Log
            obs.logger.info("Integration test started")

            # Metrics
            obs.metrics.request_total.labels(
                method="test",
                status="success",
                source="test",
            ).inc()

            # Trace
            with obs.tracer.start_span("integration_test") as span:
                span.set_attribute("test", True)
                time.sleep(0.01)

            # Health
            obs.health.set_healthy()
            status = obs.health.get_status()
            self.assertEqual(status.status, HealthStatus.HEALTHY)

            obs.logger.info("Integration test completed")

        finally:
            obs.stop()


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestStructuredLogger))
    suite.addTests(loader.loadTestsFromTestCase(TestMetrics))
    suite.addTests(loader.loadTestsFromTestCase(TestTracing))
    suite.addTests(loader.loadTestsFromTestCase(TestHealthCheck))
    suite.addTests(loader.loadTestsFromTestCase(TestMCAPRecorder))
    suite.addTests(loader.loadTestsFromTestCase(TestROAObservability))
    suite.addTests(loader.loadTestsFromTestCase(TestConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
