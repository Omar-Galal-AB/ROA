"""
component_starter.py
ROA - Robot Operations & Automation
Component startup coordination
"""

import logging
import time
from enum import Enum
from typing import Dict, List, Optional

import yaml

from .connection_monitor import ConnectionStatus, UE5ConnectionMonitor


class ComponentStatus(Enum):
    """Component status enumeration"""

    NOT_STARTED = "not_started"
    STARTING = "starting"
    READY = "ready"
    FAILED = "failed"


class ComponentStarter:
    """
    Coordinates startup of ROA components
    """

    def __init__(self, config_path: str = "./Config/roa_component_config.yaml"):
        """
        Initialize Component Starter

        Args:
            config_path: Path to component configuration file
        """
        self.logger = logging.getLogger(__name__)
        self.config_path = config_path
        self.config = {}
        self.component_statuses: Dict[str, ComponentStatus] = {}
        self.ue5_monitor: Optional[UE5ConnectionMonitor] = None

        self.logger.info("ComponentStarter initialized")

    def load_config(self) -> bool:
        """Load component configuration"""
        try:
            with open(self.config_path, "r") as f:
                self.config = yaml.safe_load(f)
            self.logger.info(f"Loaded component config from {self.config_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to load component config: {e}")
            return False

    def start_component(self, component_name: str) -> bool:
        """
        Start a specific component

        Args:
            component_name: Name of component to start

        Returns:
            True if successful
        """
        self.logger.info(f"Starting component: {component_name}")
        self.component_statuses[component_name] = ComponentStatus.STARTING

        try:
            # TODO: Implement actual component startup logic
            time.sleep(0.5)  # Simulate startup time

            self.component_statuses[component_name] = ComponentStatus.READY
            self.logger.info(f"Component {component_name} started successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to start component {component_name}: {e}")
            self.component_statuses[component_name] = ComponentStatus.FAILED
            return False

    def check_ue5_connection(
        self,
        host: str = "localhost",
        port: int = 9876,
        max_attempts: int = 3,
        retry_delay: float = 2.0,
    ) -> bool:
        """
        Check UE5 connection before starting components

        Args:
            host: UE5 host address
            port: UE5 communication port
            max_attempts: Maximum connection attempts
            retry_delay: Delay between retries

        Returns:
            True if connection successful
        """
        self.logger.info("=" * 60)
        self.logger.info("  Checking UE5 Connection")
        self.logger.info("=" * 60)

        self.ue5_monitor = UE5ConnectionMonitor(host, port)

        if self.ue5_monitor.wait_for_connection(max_attempts, retry_delay):
            self.logger.info("✓ UE5 connection verified")
            return True
        else:
            self.logger.error("✗ UE5 connection failed")
            print("\n" + self.ue5_monitor.get_diagnostic_report())
            return False

    def start_all_components(self) -> bool:
        """
        Start all components in correct order

        Returns:
            True if all components started successfully
        """
        if not self.load_config():
            return False

        # Check UE5 connection first
        ue5_config = self.config.get("ue5_connection", {})
        if ue5_config.get("check_on_startup", True):
            host = ue5_config.get("host", "localhost")
            port = ue5_config.get("port", 9876)
            max_attempts = ue5_config.get("max_attempts", 3)
            retry_delay = ue5_config.get("retry_delay", 2.0)

            if not self.check_ue5_connection(host, port, max_attempts, retry_delay):
                if ue5_config.get("required", True):
                    self.logger.error("UE5 connection required but unavailable - aborting startup")
                    return False
                else:
                    self.logger.warning("UE5 connection unavailable but not required - continuing")

        components = self.config.get("components", {})

        # Sort by startup priority
        sorted_components = sorted(
            components.items(), key=lambda x: x[1].get("startup_priority", 999)
        )

        success_count = 0
        for comp_name, comp_config in sorted_components:
            if comp_config.get("enabled", True):
                if self.start_component(comp_name.upper()):
                    success_count += 1

        total_enabled = sum(1 for _, cfg in sorted_components if cfg.get("enabled", True))
        failure_tolerance = self.config.get("startup", {}).get("failure_tolerance", 0)

        # Allow some failures based on failure_tolerance
        min_required = total_enabled - failure_tolerance
        success = success_count >= min_required

        if success:
            self.logger.info(f"Component startup complete: {success_count}/{total_enabled} started")
        else:
            self.logger.error(
                f"Component startup failed: only {success_count}/{total_enabled} started"
            )

        return success

    def get_component_status(self, component_name: str) -> ComponentStatus:
        """Get status of a component"""
        return self.component_statuses.get(component_name, ComponentStatus.NOT_STARTED)

    def get_all_statuses(self) -> Dict[str, ComponentStatus]:
        """Get statuses of all components"""
        return self.component_statuses.copy()

    def verify_all_ready(self) -> bool:
        """Verify all components are ready"""
        for comp_name, status in self.component_statuses.items():
            if status != ComponentStatus.READY:
                self.logger.warning(f"Component {comp_name} not ready: {status.value}")
                return False

        self.logger.info("All components verified ready")
        return True
