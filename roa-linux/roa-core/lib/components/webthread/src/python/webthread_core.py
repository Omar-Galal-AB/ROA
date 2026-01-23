"""
webthread_core.py
ROA - Robot Operations & Automation
Runtime Webthread core - Continuous monitoring and coordination

This module runs continuously after initialization to monitor component health,
coordinate inter-component communication, handle runtime errors, and manage
graceful degradation.

Now integrated with HB Subsystem for legitimate activity-based heartbeat
monitoring with circuit breakers, trend analysis, and automatic recovery.

Now integrated with ROA Observability Stack for comprehensive monitoring:
- Structured logging (Fluent Bit -> Loki)
- Prometheus metrics
- OpenTelemetry tracing (Tempo)
- Health checks
- MCAP recording
"""

import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

# Import Observability
try:
    # Add shared observability to path
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    _shared_path = os.path.abspath(os.path.join(_current_dir, "..", "..", "..", "..", "shared"))
    if _shared_path not in sys.path:
        sys.path.insert(0, _shared_path)

    from observability import (
        HealthCheck,
    )
    from observability import HealthStatus as ObsHealthStatus
    from observability import (
        ROAEventRecorder,
        ROALogger,
        ROAMetrics,
        ROAObservability,
        ROATracer,
    )

    OBSERVABILITY_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Observability not available: {e}")
    OBSERVABILITY_AVAILABLE = False

# Import HB Subsystem
try:
    from .hb_subsystem import (
        ActivityScope,
        ActivityType,
        AlertLevel,
        ComponentHealthStatus,
        ComponentState,
        FailureEvent,
        HBAgent,
        HBSubsystem,
        HealthLevel,
        RecoveryAction,
    )

    HB_AVAILABLE = True
except ImportError as e:
    logging.warning(f"HB Subsystem not available: {e}")
    HB_AVAILABLE = False

# Import UE5Connector
try:
    # Add UE5Bridge directory to path (it's in the same parent directory as this file)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    ue5bridge_path = os.path.join(current_dir, "UE5Bridge")
    if ue5bridge_path not in sys.path:
        sys.path.insert(0, ue5bridge_path)
    from ue5_connector import UE5Connector

    UE5_AVAILABLE = True
except ImportError as e:
    logging.warning(f"UE5Connector not available: {e}")
    UE5_AVAILABLE = False
    UE5Connector = None


class ComponentHealth(Enum):
    """Component health status"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass
class HealthStatus:
    """Health status information"""

    component_name: str
    status: ComponentHealth
    last_check: datetime
    response_time: float  # ms
    error_count: int
    warnings: List[str]


class WebthreadCore:
    """
    Runtime Webthread Core

    Responsibilities:
    - Monitor component health (500ms intervals)
    - Coordinate inter-component communication
    - Handle runtime errors (different from init errors)
    - Perform graceful degradation if components fail
    - Log system events and diagnostics
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize WebthreadCore

        Args:
            config: Optional configuration dictionary
        """
        self.logger = logging.getLogger(__name__)
        self.config = config or {}

        # Health monitoring
        self.health_check_interval = self.config.get("health_check_interval", 0.5)  # 500ms
        self.component_health: Dict[str, HealthStatus] = {}
        self.monitoring_active = False

        # Component references
        self.components = {
            "FTI": None,  # Files Type Importer
            "DIMC": None,  # Dimensions Collector
            "ROC": None,  # Robot Operator Controller
            "COMC": None,  # Communication Center
            "ROS2Bridge": None,
            "UE5Bridge": None,
        }

        # UE5 Connection
        self.ue5_connector = None
        self.ue5_connected = False

        # Auto-detect Windows host IP if running in WSL
        default_host = self._detect_windows_host() if self._is_wsl() else "localhost"
        self.ue5_host = self.config.get("ue5_host", default_host)
        self.ue5_port = self.config.get("ue5_port", 9876)

        # Callbacks
        self.health_callbacks: List[Callable[[str, HealthStatus], None]] = []
        self.error_callbacks: List[Callable[[str, Exception], None]] = []

        # Runtime state
        self.start_time = time.time()
        self.error_count = 0
        self.warning_count = 0

        # HB Subsystem
        self.hb_subsystem: Optional["HBSubsystem"] = None
        self._hb_enabled = self.config.get("hb_enabled", True) and HB_AVAILABLE

        # WT's own HB agent for self-reporting
        self._wt_agent: Optional["HBAgent"] = None

        # Observability
        self._observability: Optional["ROAObservability"] = None
        self._obs_enabled = (
            self.config.get("observability_enabled", True) and OBSERVABILITY_AVAILABLE
        )

        # Initialize HB Subsystem if available
        if self._hb_enabled:
            self._init_hb_subsystem()

        # Initialize Observability if available
        if self._obs_enabled:
            self._init_observability()

        # Initialize UE5 connector
        if UE5_AVAILABLE:
            self._init_ue5_connector()

        self.logger.info(
            f"WebthreadCore initialized (UE5 target: {self.ue5_host}:{self.ue5_port}, HB: {self._hb_enabled}, OBS: {self._obs_enabled})"
        )

    def _is_wsl(self) -> bool:
        """Check if running in WSL (Windows Subsystem for Linux)"""
        try:
            with open("/proc/version", "r") as f:
                return "microsoft" in f.read().lower() or "wsl" in f.read().lower()
        except:
            return False

    def _detect_windows_host(self) -> str:
        """Detect Windows host IP address from WSL"""
        try:
            # Method 1: Get default gateway (most reliable for WSL2)
            import subprocess

            result = subprocess.run(["ip", "route", "show"], capture_output=True, text=True)
            for line in result.stdout.split("\n"):
                if "default via" in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        windows_ip = parts[2]
                        self.logger.info(f"Detected Windows host IP: {windows_ip}")
                        return windows_ip

            # Method 2: Parse /etc/resolv.conf
            with open("/etc/resolv.conf", "r") as f:
                for line in f:
                    if line.strip().startswith("nameserver"):
                        windows_ip = line.split()[1]
                        self.logger.info(f"Detected Windows host IP from resolv.conf: {windows_ip}")
                        return windows_ip
        except Exception as e:
            self.logger.warning(f"Could not detect Windows host IP: {e}")

        return "localhost"

    def _init_hb_subsystem(self):
        """Initialize the HB Subsystem"""
        try:
            self.hb_subsystem = HBSubsystem(
                bind_address="127.0.0.1", logger=logging.getLogger("WebthreadCore.HB")
            )

            # Register callbacks
            self.hb_subsystem.on_health_change(self._on_hb_health_change)
            self.hb_subsystem.on_critical_failure(self._on_hb_critical_failure)
            self.hb_subsystem.on_hb_subsystem_failure(self._on_hb_subsystem_failure)

            # Register recovery executors
            self.hb_subsystem.register_recovery_executor(
                RecoveryAction.RESTART_COMPONENT, self._execute_restart_recovery
            )
            self.hb_subsystem.register_recovery_executor(
                RecoveryAction.REINITIALIZE, self._execute_reinitialize_recovery
            )
            self.hb_subsystem.register_recovery_executor(
                RecoveryAction.NOTIFY_OPERATOR, self._execute_notify_operator
            )

            self.logger.info("HB Subsystem initialized")

        except Exception as e:
            self.logger.error(f"Failed to initialize HB Subsystem: {e}")
            self.hb_subsystem = None
            self._hb_enabled = False

    def _init_observability(self):
        """Initialize the ROA Observability Stack"""
        try:
            self._observability = ROAObservability(
                component_name="webthread",
                service_version="1.0.0",
                auto_start=False,  # We'll start it in start()
            )

            # Register custom Webthread metrics
            self._register_observability_metrics()

            self.logger.info("Observability initialized for Webthread")

        except Exception as e:
            self.logger.error(f"Failed to initialize Observability: {e}")
            self._observability = None
            self._obs_enabled = False

    def _register_observability_metrics(self):
        """Register Webthread-specific observability metrics"""
        if not self._observability:
            return

        metrics = self._observability.metrics

        # HB Subsystem metrics
        self._hb_heartbeats_received = metrics.register_counter(
            "wt_hb_heartbeats_received_total",
            "Total heartbeats received by Webthread",
            ["component", "source"],
        )

        self._hb_heartbeats_missed = metrics.register_counter(
            "wt_hb_heartbeats_missed_total",
            "Total missed heartbeats by component",
            ["component"],
        )

        self._hb_circuit_breaker = metrics.register_gauge(
            "wt_hb_circuit_breaker_state",
            "Circuit breaker state (0=closed, 1=half-open, 2=open)",
            ["component"],
        )

        # UE5 Bridge metrics
        self._ue5_connected_gauge = metrics.register_gauge(
            "wt_ue5_connected",
            "UE5 connection status (0=disconnected, 1=connected)",
        )

        self._ue5_messages_sent = metrics.register_counter(
            "wt_ue5_messages_sent_total",
            "Total messages sent to UE5",
            ["message_type"],
        )

        # Component health metrics
        self._component_health_gauge = metrics.register_gauge(
            "wt_component_health",
            "Component health (0=unknown, 1=healthy, 2=degraded, 3=failed)",
            ["component"],
        )

        # System metrics
        self._active_components = metrics.register_gauge(
            "wt_active_components",
            "Number of active components",
        )

        self._health_checks_total = metrics.register_counter(
            "wt_health_checks_total",
            "Total health checks performed",
            ["component"],
        )

    def _on_hb_health_change(self, component_name: str, status: "ComponentHealthStatus"):
        """Handle health change from HB Subsystem"""
        # Map HB health to our ComponentHealth
        if status.health.value <= HealthLevel.HEALTHY.value:
            our_status = ComponentHealth.HEALTHY
        elif status.health.value <= HealthLevel.DEGRADED.value:
            our_status = ComponentHealth.DEGRADED
        else:
            our_status = ComponentHealth.FAILED

        # Update our local tracking
        if component_name in self.component_health:
            self.component_health[component_name].status = our_status
            self.component_health[component_name].response_time = status.response_time_avg_ms
            self.component_health[component_name].error_count = status.error_count
            self.component_health[component_name].warnings = status.warnings.copy()
            self.component_health[component_name].last_check = datetime.now()

            # Notify our callbacks
            self._notify_health_change(component_name, self.component_health[component_name])

    def _on_hb_critical_failure(self, component_name: str, failure: "FailureEvent"):
        """Handle critical failure from HB Subsystem"""
        self.logger.error(f"Critical failure in {component_name}: {failure.details}")
        self.error_count += 1

        # Update health
        if component_name in self.component_health:
            self.component_health[component_name].status = ComponentHealth.FAILED
            self.component_health[component_name].error_count += 1
            self.component_health[component_name].warnings.append(failure.details)

        # Notify error callbacks
        error = Exception(failure.details)
        for callback in self.error_callbacks:
            try:
                callback(component_name, error)
            except Exception as e:
                self.logger.error(f"Error in error callback: {e}")

    def _on_hb_subsystem_failure(self, name: str, status):
        """Handle HB subsystem internal failure"""
        self.logger.error(f"HB Subsystem internal failure: {name} is {status.value}")
        # Could trigger fallback to basic monitoring here

    def _execute_restart_recovery(self, component_name: str) -> bool:
        """Execute restart recovery for a component"""
        self.logger.info(f"Executing restart recovery for {component_name}")

        component = self.components.get(component_name)
        if component is None:
            self.logger.warning(f"Component {component_name} not found for restart")
            return False

        try:
            # TODO: Implement actual restart logic
            # For now, just log and return True
            self.logger.info(f"Would restart {component_name} here")
            return True
        except Exception as e:
            self.logger.error(f"Failed to restart {component_name}: {e}")
            return False

    def _execute_reinitialize_recovery(self, component_name: str) -> bool:
        """Execute reinitialization recovery for a component"""
        self.logger.info(f"Executing reinitialize recovery for {component_name}")

        # TODO: Implement actual reinitialize logic
        return True

    def _execute_notify_operator(self, component_name: str) -> bool:
        """Notify operator of component failure"""
        self.logger.critical(
            f"OPERATOR NOTIFICATION: Component {component_name} has exhausted recovery attempts"
        )
        # TODO: Implement actual notification (email, Slack, etc.)
        return True

    def start(self):
        """Start the runtime Webthread monitoring"""
        self.logger.info("Starting Webthread runtime monitoring")
        self.monitoring_active = True

        # Start Observability first (for logging/metrics during startup)
        if self._obs_enabled and self._observability:
            try:
                self._observability.start()
                self._observability.health.set_healthy()
                self._observability.logger.info(
                    "Webthread observability started",
                    extra={"component": "webthread", "action": "start"},
                )
            except Exception as e:
                self.logger.warning(f"Failed to start observability: {e}")
                self._obs_enabled = False

        # Start HB Subsystem (so it's ready for component agents)
        if self._hb_enabled and self.hb_subsystem:
            if not self.hb_subsystem.start():
                self.logger.warning(
                    "HB Subsystem failed to start, falling back to basic monitoring"
                )
                self._hb_enabled = False
            else:
                # Create and start WT's own HB agent for self-reporting
                try:
                    self._wt_agent = HBAgent(
                        component_id="Webthread",
                        target_host="127.0.0.1",
                        target_port=9877,  # WT uses FTI's port for now (could add dedicated port)
                    )
                    self._wt_agent.set_state(ComponentState.ACTIVE)
                    self._wt_agent.start()
                    self.logger.info("WT HB Agent started")
                except Exception as e:
                    self.logger.warning(f"Failed to start WT HB Agent: {e}")

        # Initialize all component health statuses
        for component_name in self.components.keys():
            self.component_health[component_name] = HealthStatus(
                component_name=component_name,
                status=ComponentHealth.UNKNOWN,
                last_check=datetime.now(),
                response_time=0.0,
                error_count=0,
                warnings=[],
            )

            # Update observability metrics
            if self._obs_enabled and hasattr(self, "_component_health_gauge"):
                self._component_health_gauge.labels(component=component_name).set(0)  # UNKNOWN

        # Update active components metric
        if self._obs_enabled and hasattr(self, "_active_components"):
            self._active_components.set(len(self.components))

        self.logger.info("Webthread runtime started successfully")

    def stop(self):
        """Stop the runtime Webthread monitoring"""
        self.logger.info("Stopping Webthread runtime monitoring")
        self.monitoring_active = False

        # Stop WT HB Agent
        if self._wt_agent:
            try:
                self._wt_agent.stop()
                self.logger.info("WT HB Agent stopped")
            except Exception as e:
                self.logger.warning(f"Error stopping WT HB Agent: {e}")

        # Stop HB Subsystem
        if self.hb_subsystem:
            self.hb_subsystem.stop()

        # Stop Observability
        if self._obs_enabled and self._observability:
            try:
                self._observability.logger.info(
                    "Webthread shutting down",
                    extra={"component": "webthread", "action": "shutdown"},
                )
                self._observability.health.set_shutting_down()
                self._observability.stop()
                self.logger.info("Observability stopped")
            except Exception as e:
                self.logger.warning(f"Error stopping observability: {e}")

        self.logger.info("Webthread runtime stopped")

    def monitor_health(self):
        """
        Monitor health of all components

        This should be called periodically (every 500ms)
        When HB subsystem is enabled, most monitoring is handled there.
        This method provides fallback/supplementary monitoring.
        """
        if not self.monitoring_active:
            return

        # Record health check via tracing if available
        tracer_ctx = None
        if self._obs_enabled and self._observability:
            tracer_ctx = self._observability.tracer.start_span("monitor_health")
            tracer_ctx.__enter__()

        try:
            # If HB subsystem is active, it handles most monitoring
            # We only do supplementary checks here
            if self._hb_enabled and self.hb_subsystem:
                # Check HB subsystem health (self-monitoring)
                summary = self.hb_subsystem.get_system_summary()
                if summary.get("overall_health") == "unknown":
                    self.logger.debug(
                        "HB subsystem reports unknown health - components may still be starting"
                    )

                # Update observability metrics from HB data
                if self._obs_enabled:
                    self._update_obs_metrics_from_hb(summary)
                return

            # Fallback: basic monitoring without HB subsystem
            for component_name, component in self.components.items():
                try:
                    # Increment health check counter
                    if self._obs_enabled and hasattr(self, "_health_checks_total"):
                        self._health_checks_total.labels(component=component_name).inc()

                    health_status = self._check_component_health(component_name, component)
                    self.component_health[component_name] = health_status

                    # Update observability health gauge
                    if self._obs_enabled and hasattr(self, "_component_health_gauge"):
                        health_val = {
                            ComponentHealth.UNKNOWN: 0,
                            ComponentHealth.HEALTHY: 1,
                            ComponentHealth.DEGRADED: 2,
                            ComponentHealth.FAILED: 3,
                        }.get(health_status.status, 0)
                        self._component_health_gauge.labels(component=component_name).set(
                            health_val
                        )

                    # Trigger callbacks if health changed
                    if health_status.status != ComponentHealth.HEALTHY:
                        self._notify_health_change(component_name, health_status)

                except Exception as e:
                    self.logger.error(f"Error checking health of {component_name}: {e}")
                    self.component_health[component_name].status = ComponentHealth.FAILED
                    self.component_health[component_name].error_count += 1

                    # Record error in observability
                    if self._obs_enabled and self._observability:
                        self._observability.recorder.record_event(
                            "health_check_error",
                            {
                                "component": component_name,
                                "error": str(e),
                            },
                        )
        finally:
            if tracer_ctx:
                tracer_ctx.__exit__(None, None, None)

    def _update_obs_metrics_from_hb(self, summary: Dict):
        """Update observability metrics from HB subsystem summary"""
        if not self._obs_enabled:
            return

        components = summary.get("components", {})
        for name, data in components.items():
            # Update health gauge
            if hasattr(self, "_component_health_gauge"):
                health_map = {"healthy": 1, "degraded": 2, "failed": 3, "unknown": 0}
                health_val = health_map.get(data.get("health", "unknown"), 0)
                self._component_health_gauge.labels(component=name).set(health_val)

            # Update circuit breaker state
            if hasattr(self, "_hb_circuit_breaker"):
                cb_map = {"closed": 0, "half_open": 1, "open": 2}
                cb_val = cb_map.get(data.get("circuit_breaker", "closed"), 0)
                self._hb_circuit_breaker.labels(component=name).set(cb_val)

    def report_wt_activity(self, activity: "ActivityType"):
        """
        Report WT (Webthread) activity for heartbeat.
        Call this after performing actual work.

        Args:
            activity: The type of activity performed
        """
        if self._wt_agent:
            self._wt_agent.report_activity(activity)

    def get_wt_agent(self) -> Optional["HBAgent"]:
        """Get the WT's HB agent for direct access"""
        return self._wt_agent

    def _check_component_health(self, component_name: str, component) -> HealthStatus:
        """
        Check health of a specific component

        Args:
            component_name: Name of the component
            component: Component instance

        Returns:
            HealthStatus object
        """
        start_time = time.time()

        # Get previous status
        prev_status = self.component_health.get(component_name)
        if prev_status:
            error_count = prev_status.error_count
            warnings = prev_status.warnings.copy()
        else:
            error_count = 0
            warnings = []

        # TODO: Implement actual health check
        # For now, assume healthy if component exists
        status = ComponentHealth.HEALTHY if component else ComponentHealth.UNKNOWN

        response_time = (time.time() - start_time) * 1000  # Convert to ms

        return HealthStatus(
            component_name=component_name,
            status=status,
            last_check=datetime.now(),
            response_time=response_time,
            error_count=error_count,
            warnings=warnings,
        )

    def _notify_health_change(self, component_name: str, health_status: HealthStatus):
        """Notify registered callbacks of health changes"""
        for callback in self.health_callbacks:
            try:
                callback(component_name, health_status)
            except Exception as e:
                self.logger.error(f"Error in health callback: {e}")

    def register_component(self, component_name: str, component_instance):
        """
        Register a component with the Webthread

        Args:
            component_name: Name of the component
            component_instance: Component instance
        """
        # Register both known and unknown components
        self.components[component_name] = component_instance

        # Initialize health status if not exists
        if component_name not in self.component_health:
            self.component_health[component_name] = HealthStatus(
                component_name=component_name,
                status=ComponentHealth.UNKNOWN,
                last_check=datetime.now(),
                response_time=0.0,
                error_count=0,
                warnings=[],
            )

        self.logger.info(f"Registered component: {component_name}")

    def register_health_callback(self, callback: Callable[[str, HealthStatus], None]):
        """Register a callback for health status changes"""
        self.health_callbacks.append(callback)

    def register_error_callback(self, callback: Callable[[str, Exception], None]):
        """Register a callback for errors"""
        self.error_callbacks.append(callback)

    def get_component_health(self, component_name: str) -> Optional[HealthStatus]:
        """Get health status of a specific component"""
        return self.component_health.get(component_name)

    def get_all_health_statuses(self) -> Dict[str, HealthStatus]:
        """Get health statuses of all components"""
        return self.component_health.copy()

    def get_system_status(self) -> Dict:
        """
        Get overall system status

        Returns:
            Dictionary with system status information
        """
        # If HB subsystem active, get comprehensive status from there
        if self._hb_enabled and self.hb_subsystem:
            hb_summary = self.hb_subsystem.get_system_summary()

            return {
                "uptime": time.time() - self.start_time,
                "monitoring_active": self.monitoring_active,
                "hb_enabled": True,
                "overall_health": hb_summary.get("overall_health", "unknown"),
                "total_components": hb_summary.get("total_components", 0),
                "healthy_components": hb_summary.get("healthy_count", 0),
                "degraded_components": hb_summary.get("degraded_count", 0),
                "failed_components": hb_summary.get("failed_count", 0),
                "error_count": self.error_count,
                "warning_count": self.warning_count,
                "hb_subsystem": hb_summary,
                "components": hb_summary.get("component_statuses", {}),
            }

        # Fallback: basic status
        healthy_count = sum(
            1
            for status in self.component_health.values()
            if status.status == ComponentHealth.HEALTHY
        )
        total_count = len(self.component_health)

        return {
            "uptime": time.time() - self.start_time,
            "monitoring_active": self.monitoring_active,
            "hb_enabled": False,
            "total_components": total_count,
            "healthy_components": healthy_count,
            "degraded_components": sum(
                1
                for status in self.component_health.values()
                if status.status == ComponentHealth.DEGRADED
            ),
            "failed_components": sum(
                1
                for status in self.component_health.values()
                if status.status == ComponentHealth.FAILED
            ),
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "components": {
                name: {
                    "status": status.status.value,
                    "response_time": status.response_time,
                    "error_count": status.error_count,
                }
                for name, status in self.component_health.items()
            },
        }

    def _update_component_health(
        self, component_name: str, status: ComponentHealth, response_time: float
    ):
        """
        Update component health status (for testing)

        Args:
            component_name: Name of the component
            status: New health status
            response_time: Response time in ms
        """
        if component_name in self.component_health:
            self.component_health[component_name].status = status
            self.component_health[component_name].response_time = response_time
            self.component_health[component_name].last_check = datetime.now()

            # Notify callbacks
            self._notify_health_change(component_name, self.component_health[component_name])

    def _handle_component_error(self, component_name: str, error: Exception):
        """
        Handle component error (for testing)

        Args:
            component_name: Name of the component
            error: Error that occurred
        """
        self.error_count += 1

        if component_name in self.component_health:
            self.component_health[component_name].error_count += 1

        # Notify error callbacks
        for callback in self.error_callbacks:
            try:
                callback(component_name, error)
            except Exception as e:
                self.logger.error(f"Error in error callback: {e}")

    def handle_component_failure(self, component_name: str, error: Exception):
        """
        Handle component failure with graceful degradation

        Args:
            component_name: Name of the failed component
            error: Exception that caused the failure
        """
        self.logger.error(f"Component {component_name} failed: {error}")
        self.error_count += 1

        # Update health status
        if component_name in self.component_health:
            self.component_health[component_name].status = ComponentHealth.FAILED
            self.component_health[component_name].error_count += 1

        # Notify error callbacks
        for callback in self.error_callbacks:
            try:
                callback(component_name, error)
            except Exception as e:
                self.logger.error(f"Error in error callback: {e}")

        # TODO: Implement graceful degradation logic
        # - Disable dependent features
        # - Notify user
        # - Attempt recovery if possible

    def _init_ue5_connector(self):
        """Initialize UE5 connector and attempt connection"""
        try:
            self.ue5_connector = UE5Connector(host=self.ue5_host, port=self.ue5_port)
            self.logger.info(
                f"UE5Connector initialized (host={self.ue5_host}, port={self.ue5_port})"
            )

            # Attempt to connect
            if self.ue5_connector.connect():
                self.ue5_connected = True
                self.components["UE5Bridge"] = self.ue5_connector
                self.logger.info("Successfully connected to UE5")

                # Update health status
                if "UE5Bridge" in self.component_health:
                    self.component_health["UE5Bridge"].status = ComponentHealth.HEALTHY
            else:
                self.ue5_connected = False
                self.logger.warning("Failed to connect to UE5 - will retry in background")

                # Keep trying in background
                if "UE5Bridge" in self.component_health:
                    self.component_health["UE5Bridge"].status = ComponentHealth.DEGRADED
                    self.component_health["UE5Bridge"].warnings.append(
                        "Not connected - UE5 may not be running"
                    )

        except Exception as e:
            self.logger.error(f"Error initializing UE5 connector: {e}")
            self.ue5_connected = False
            if "UE5Bridge" in self.component_health:
                self.component_health["UE5Bridge"].status = ComponentHealth.FAILED

    def get_ue5_connector(self) -> Optional["UE5Connector"]:
        """Get the UE5 connector instance"""
        return self.ue5_connector

    def is_ue5_connected(self) -> bool:
        """Check if UE5 is connected"""
        return self.ue5_connected and self.ue5_connector is not None

    def reconnect_ue5(self) -> bool:
        """Attempt to reconnect to UE5"""
        if not UE5_AVAILABLE or not self.ue5_connector:
            return False

        try:
            if self.ue5_connector.connect():
                self.ue5_connected = True
                self.logger.info("Reconnected to UE5")
                if "UE5Bridge" in self.component_health:
                    self.component_health["UE5Bridge"].status = ComponentHealth.HEALTHY
                    self.component_health["UE5Bridge"].warnings.clear()
                return True
        except Exception as e:
            self.logger.error(f"Failed to reconnect to UE5: {e}")

        return False

    def shutdown(self):
        """Perform graceful shutdown"""
        self.logger.info("Performing graceful shutdown...")
        self.stop()

        # Disconnect from UE5
        if self.ue5_connector:
            try:
                self.ue5_connector.disconnect()
                self.logger.info("Disconnected from UE5")
            except Exception as e:
                self.logger.error(f"Error disconnecting from UE5: {e}")

        self.logger.info("Shutdown complete")

    # =========================================================================
    # HB SUBSYSTEM API
    # =========================================================================

    def get_hb_subsystem(self) -> Optional["HBSubsystem"]:
        """Get the HB Subsystem instance"""
        return self.hb_subsystem

    def is_hb_enabled(self) -> bool:
        """Check if HB subsystem is enabled and running"""
        return self._hb_enabled and self.hb_subsystem is not None and self.hb_subsystem.is_running()

    def get_component_health_detailed(self, component_name: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed health status for a component from HB subsystem.

        Args:
            component_name: Name of the component

        Returns:
            Detailed health dictionary or None
        """
        if self.hb_subsystem:
            status = self.hb_subsystem.get_component_health(component_name)
            if status:
                return status.to_dict()
        return None

    def get_component_trends(self, component_name: str) -> Dict[str, Any]:
        """
        Get health trend analysis for a component.

        Args:
            component_name: Name of the component

        Returns:
            Trend analysis dictionary
        """
        if self.hb_subsystem:
            return self.hb_subsystem.get_trend_analysis(component_name)
        return {}

    def get_circuit_breaker_states(self) -> Dict[str, str]:
        """Get circuit breaker states for all components"""
        if self.hb_subsystem:
            states = {}
            for name in self.components.keys():
                state = self.hb_subsystem.get_circuit_breaker_state(name)
                if state:
                    states[name] = state.value
            return states
        return {}

    def get_all_alert_levels(self) -> Dict[str, str]:
        """Get alert levels for all components"""
        if self.hb_subsystem:
            alerts = self.hb_subsystem.get_all_alert_levels()
            return {name: level.value for name, level in alerts.items()}
        return {}

    def get_receiver_stats(self) -> Dict[str, Any]:
        """Get HB receiver statistics"""
        if self.hb_subsystem:
            return self.hb_subsystem.get_receiver_stats()
        return {}

    def trigger_manual_snapshot(self) -> bool:
        """Trigger a manual state snapshot"""
        if self.hb_subsystem:
            return self.hb_subsystem.trigger_manual_snapshot()
        return False

    def get_recovery_history(self, component_name: Optional[str] = None) -> List[Any]:
        """Get recovery attempt history"""
        if self.hb_subsystem:
            return self.hb_subsystem.get_recovery_history(component_name)
        return []


def main():
    """Main entry point for standalone testing"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    webthread = WebthreadCore()
    webthread.start()

    try:
        # Simulate monitoring loop
        print("Webthread runtime started. Press Ctrl+C to stop.")
        while True:
            webthread.monitor_health()
            time.sleep(0.5)  # 500ms interval

    except KeyboardInterrupt:
        print("\nShutting down...")
        webthread.shutdown()


if __name__ == "__main__":
    main()
