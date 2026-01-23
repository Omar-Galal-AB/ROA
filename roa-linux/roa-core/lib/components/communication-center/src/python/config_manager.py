"""
COMC Configuration Manager

Provides centralized configuration file support for COMC.
This addresses the P3 Gap: No Configuration File Support.

Features:
- YAML-based configuration
- Environment variable overrides
- Runtime configuration updates
- Configuration validation
- Default value management
"""

import os
import threading
from typing import Dict, Any, Optional, List, Callable, TypeVar, Generic
from dataclasses import dataclass, field, asdict
from enum import Enum
import json
import copy


# Check for YAML support
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


T = TypeVar('T')


class ConfigSection(Enum):
    """Configuration sections"""
    GENERAL = "general"
    NETWORKING = "networking"
    SAFETY = "safety"
    MONITORING = "monitoring"
    RESILIENCE = "resilience"
    COORDINATION = "coordination"
    DISCOVERY = "discovery"
    LOGGING = "logging"


@dataclass
class GeneralConfig:
    """General COMC configuration"""
    robot_id: str = ""
    robot_type: str = "generic"
    fleet_id: str = "default"
    node_name: str = "comc_node"
    enable_diagnostics: bool = True
    log_level: str = "INFO"


@dataclass
class NetworkingConfig:
    """Networking configuration"""
    # Port assignments
    comc_hb_port: int = 9880
    dimc_port: int = 9800
    roc_port: int = 9810
    fti_port: int = 9820
    webthread_port: int = 9860
    ue5_bridge_port: int = 9840
    
    # Timeouts (seconds)
    connection_timeout: float = 10.0
    heartbeat_interval: float = 1.0
    heartbeat_timeout: float = 5.0
    
    # Network settings
    multicast_enabled: bool = False
    multicast_group: str = "239.255.0.1"
    buffer_size: int = 65536


@dataclass
class SafetyConfig:
    """Safety-related configuration"""
    # Emergency stop
    enable_emergency_stop: bool = True
    emergency_stop_timeout: float = 0.5
    
    # Proximity thresholds (meters)
    proximity_warning: float = 2.0
    proximity_caution: float = 1.0
    proximity_critical: float = 0.5
    proximity_emergency: float = 0.3
    
    # Time-to-collision thresholds (seconds)
    ttc_warning: float = 5.0
    ttc_caution: float = 3.0
    ttc_critical: float = 1.5
    ttc_emergency: float = 0.5
    
    # Safety margins
    default_safety_margin: float = 0.3
    max_velocity: float = 2.0  # m/s
    max_acceleration: float = 1.0  # m/s²
    
    # Work area
    work_area_check_interval: float = 0.1


@dataclass
class MonitoringConfig:
    """Monitoring configuration"""
    enable_monitoring: bool = True
    metrics_interval: float = 1.0
    health_check_interval: float = 5.0
    
    # Thresholds
    cpu_warning_threshold: float = 80.0
    memory_warning_threshold: float = 80.0
    latency_warning_ms: float = 100.0
    
    # History
    metrics_history_size: int = 1000
    alert_retention_seconds: float = 3600.0
    
    # Stale data
    robot_stale_timeout: float = 30.0


@dataclass
class ResilienceConfig:
    """Resilience configuration"""
    enable_resilience: bool = True
    
    # Circuit breaker
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: float = 30.0
    half_open_max_calls: int = 3
    
    # Retry
    max_retries: int = 3
    retry_delay: float = 1.0
    retry_backoff_multiplier: float = 2.0
    max_retry_delay: float = 30.0
    
    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_window: float = 60.0
    
    # Bulkhead
    max_concurrent_operations: int = 10


@dataclass 
class CoordinationConfig:
    """Task coordination configuration"""
    enable_coordination: bool = True
    
    # Resource locking
    lock_timeout: float = 60.0
    deadlock_detection_interval: float = 10.0
    max_wait_time: float = 10.0
    
    # Task queue
    max_queue_size: int = 100
    queue_timeout: float = 300.0
    
    # Preemption
    enable_preemption: bool = True
    preemption_grace_period: float = 2.0
    
    # MAPF
    enable_mapf: bool = True
    mapf_timeout: float = 5.0


@dataclass
class DiscoveryConfig:
    """Fleet discovery configuration"""
    enable_discovery: bool = True
    
    # Timing
    announce_interval: float = 5.0
    heartbeat_interval: float = 2.0
    discovery_timeout: float = 10.0
    health_timeout: float = 15.0
    lost_timeout: float = 30.0
    cleanup_interval: float = 60.0
    
    # Thresholds
    min_heartbeats_for_active: int = 3


@dataclass
class LoggingConfig:
    """Logging configuration"""
    log_level: str = "INFO"
    log_to_file: bool = False
    log_file_path: str = "/var/log/comc/comc.log"
    max_log_size_mb: int = 100
    log_rotation_count: int = 5
    log_format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


@dataclass
class COMCConfig:
    """Complete COMC configuration"""
    general: GeneralConfig = field(default_factory=GeneralConfig)
    networking: NetworkingConfig = field(default_factory=NetworkingConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    resilience: ResilienceConfig = field(default_factory=ResilienceConfig)
    coordination: CoordinationConfig = field(default_factory=CoordinationConfig)
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


class ConfigurationManager:
    """
    Centralized configuration management for COMC.
    
    Provides:
    - Loading from YAML files
    - Environment variable overrides
    - Runtime updates with validation
    - Change notification callbacks
    """
    
    # Environment variable prefix
    ENV_PREFIX = "COMC_"
    
    # Default config file paths
    DEFAULT_CONFIG_PATHS = [
        "/etc/comc/config.yaml",
        "~/.comc/config.yaml",
        "./config/comc_config.yaml",
        "./comc_config.yaml"
    ]
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration manager.
        
        Args:
            config_path: Optional path to configuration file
        """
        self._config = COMCConfig()
        self._lock = threading.RLock()
        self._callbacks: List[Callable[[str, Any, Any], None]] = []  # (key, old, new)
        self._loaded_from: Optional[str] = None
        
        # Load configuration
        if config_path:
            self.load_from_file(config_path)
        else:
            self._try_load_default()
        
        # Apply environment overrides
        self._apply_environment_overrides()
    
    def _try_load_default(self):
        """Try to load from default config paths"""
        for path in self.DEFAULT_CONFIG_PATHS:
            expanded_path = os.path.expanduser(path)
            if os.path.exists(expanded_path):
                try:
                    self.load_from_file(expanded_path)
                    return
                except Exception:
                    continue
    
    def load_from_file(self, path: str) -> bool:
        """
        Load configuration from file.
        
        Args:
            path: Path to configuration file
            
        Returns:
            True if loaded successfully
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Configuration file not found: {path}")
        
        with self._lock:
            try:
                with open(path, 'r') as f:
                    if path.endswith('.yaml') or path.endswith('.yml'):
                        if not YAML_AVAILABLE:
                            raise ImportError("PyYAML not installed")
                        data = yaml.safe_load(f)
                    elif path.endswith('.json'):
                        data = json.load(f)
                    else:
                        # Try YAML first, then JSON
                        content = f.read()
                        try:
                            if YAML_AVAILABLE:
                                data = yaml.safe_load(content)
                            else:
                                data = json.loads(content)
                        except Exception:
                            data = json.loads(content)
                
                self._apply_dict(data)
                self._loaded_from = path
                return True
                
            except Exception as e:
                raise RuntimeError(f"Failed to load configuration: {e}")
    
    def save_to_file(self, path: str):
        """
        Save configuration to file.
        
        Args:
            path: Path to save configuration
        """
        with self._lock:
            data = self.to_dict()
            
            with open(path, 'w') as f:
                if path.endswith('.yaml') or path.endswith('.yml'):
                    if not YAML_AVAILABLE:
                        raise ImportError("PyYAML not installed")
                    yaml.dump(data, f, default_flow_style=False, sort_keys=False)
                else:
                    json.dump(data, f, indent=2)
    
    def _apply_dict(self, data: Dict[str, Any]):
        """Apply configuration from dictionary"""
        if not data:
            return
        
        for section_name, section_data in data.items():
            if not isinstance(section_data, dict):
                continue
            
            section = getattr(self._config, section_name, None)
            if section is None:
                continue
            
            for key, value in section_data.items():
                if hasattr(section, key):
                    old_value = getattr(section, key)
                    setattr(section, key, value)
                    self._notify_change(f"{section_name}.{key}", old_value, value)
    
    def _apply_environment_overrides(self):
        """Apply environment variable overrides"""
        for key, value in os.environ.items():
            if key.startswith(self.ENV_PREFIX):
                # Convert COMC_SAFETY_PROXIMITY_WARNING to safety.proximity_warning
                config_key = key[len(self.ENV_PREFIX):].lower()
                parts = config_key.split('_', 1)
                
                if len(parts) == 2:
                    section_name, field_name = parts
                    self._set_from_env(section_name, field_name, value)
    
    def _set_from_env(self, section: str, field: str, value: str):
        """Set a config value from environment variable"""
        section_obj = getattr(self._config, section, None)
        if section_obj is None:
            return
        
        if not hasattr(section_obj, field):
            return
        
        current = getattr(section_obj, field)
        
        # Type conversion
        try:
            if isinstance(current, bool):
                new_value = value.lower() in ('true', '1', 'yes', 'on')
            elif isinstance(current, int):
                new_value = int(value)
            elif isinstance(current, float):
                new_value = float(value)
            else:
                new_value = value
            
            old_value = current
            setattr(section_obj, field, new_value)
            self._notify_change(f"{section}.{field}", old_value, new_value)
            
        except (ValueError, TypeError):
            pass  # Skip invalid conversions
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        with self._lock:
            return {
                'general': asdict(self._config.general),
                'networking': asdict(self._config.networking),
                'safety': asdict(self._config.safety),
                'monitoring': asdict(self._config.monitoring),
                'resilience': asdict(self._config.resilience),
                'coordination': asdict(self._config.coordination),
                'discovery': asdict(self._config.discovery),
                'logging': asdict(self._config.logging)
            }
    
    # =========================================================================
    # Getters
    # =========================================================================
    
    @property
    def general(self) -> GeneralConfig:
        """Get general configuration"""
        return self._config.general
    
    @property
    def networking(self) -> NetworkingConfig:
        """Get networking configuration"""
        return self._config.networking
    
    @property
    def safety(self) -> SafetyConfig:
        """Get safety configuration"""
        return self._config.safety
    
    @property
    def monitoring(self) -> MonitoringConfig:
        """Get monitoring configuration"""
        return self._config.monitoring
    
    @property
    def resilience(self) -> ResilienceConfig:
        """Get resilience configuration"""
        return self._config.resilience
    
    @property
    def coordination(self) -> CoordinationConfig:
        """Get coordination configuration"""
        return self._config.coordination
    
    @property
    def discovery(self) -> DiscoveryConfig:
        """Get discovery configuration"""
        return self._config.discovery
    
    @property
    def logging(self) -> LoggingConfig:
        """Get logging configuration"""
        return self._config.logging
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value by dot-notation key.
        
        Args:
            key: Configuration key (e.g., "safety.proximity_warning")
            default: Default value if not found
            
        Returns:
            Configuration value
        """
        with self._lock:
            parts = key.split('.')
            obj = self._config
            
            for part in parts:
                if hasattr(obj, part):
                    obj = getattr(obj, part)
                else:
                    return default
            
            return obj
    
    def set(self, key: str, value: Any) -> bool:
        """
        Set a configuration value by dot-notation key.
        
        Args:
            key: Configuration key
            value: New value
            
        Returns:
            True if set successfully
        """
        with self._lock:
            parts = key.split('.')
            if len(parts) != 2:
                return False
            
            section_name, field_name = parts
            section = getattr(self._config, section_name, None)
            
            if section is None or not hasattr(section, field_name):
                return False
            
            old_value = getattr(section, field_name)
            setattr(section, field_name, value)
            self._notify_change(key, old_value, value)
            return True
    
    # =========================================================================
    # Change Notifications
    # =========================================================================
    
    def on_change(self, callback: Callable[[str, Any, Any], None]):
        """
        Register callback for configuration changes.
        
        Args:
            callback: Function(key, old_value, new_value)
        """
        self._callbacks.append(callback)
    
    def _notify_change(self, key: str, old_value: Any, new_value: Any):
        """Notify callbacks of configuration change"""
        if old_value == new_value:
            return
        
        for callback in self._callbacks:
            try:
                callback(key, old_value, new_value)
            except Exception:
                pass
    
    # =========================================================================
    # Validation
    # =========================================================================
    
    def validate(self) -> List[str]:
        """
        Validate configuration.
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Safety validations
        if self._config.safety.proximity_emergency >= self._config.safety.proximity_critical:
            errors.append("proximity_emergency must be less than proximity_critical")
        
        if self._config.safety.proximity_critical >= self._config.safety.proximity_caution:
            errors.append("proximity_critical must be less than proximity_caution")
        
        if self._config.safety.proximity_caution >= self._config.safety.proximity_warning:
            errors.append("proximity_caution must be less than proximity_warning")
        
        # TTC validations
        if self._config.safety.ttc_emergency >= self._config.safety.ttc_critical:
            errors.append("ttc_emergency must be less than ttc_critical")
        
        # Networking validations
        if self._config.networking.heartbeat_timeout <= self._config.networking.heartbeat_interval:
            errors.append("heartbeat_timeout must be greater than heartbeat_interval")
        
        # Resilience validations
        if self._config.resilience.circuit_breaker_threshold < 1:
            errors.append("circuit_breaker_threshold must be at least 1")
        
        if self._config.resilience.max_retries < 0:
            errors.append("max_retries cannot be negative")
        
        return errors
    
    def get_loaded_from(self) -> Optional[str]:
        """Get path configuration was loaded from"""
        return self._loaded_from


# Default configuration template for file creation
DEFAULT_CONFIG_TEMPLATE = """# COMC Configuration File
# Generated by COMC Configuration Manager

general:
  robot_id: ""
  robot_type: "generic"
  fleet_id: "default"
  node_name: "comc_node"
  enable_diagnostics: true
  log_level: "INFO"

networking:
  comc_hb_port: 9880
  dimc_port: 9800
  roc_port: 9810
  fti_port: 9820
  webthread_port: 9860
  ue5_bridge_port: 9840
  connection_timeout: 10.0
  heartbeat_interval: 1.0
  heartbeat_timeout: 5.0

safety:
  enable_emergency_stop: true
  emergency_stop_timeout: 0.5
  proximity_warning: 2.0
  proximity_caution: 1.0
  proximity_critical: 0.5
  proximity_emergency: 0.3
  ttc_warning: 5.0
  ttc_caution: 3.0
  ttc_critical: 1.5
  ttc_emergency: 0.5
  default_safety_margin: 0.3
  max_velocity: 2.0
  max_acceleration: 1.0

monitoring:
  enable_monitoring: true
  metrics_interval: 1.0
  health_check_interval: 5.0
  cpu_warning_threshold: 80.0
  memory_warning_threshold: 80.0
  latency_warning_ms: 100.0
  metrics_history_size: 1000

resilience:
  enable_resilience: true
  circuit_breaker_threshold: 5
  circuit_breaker_timeout: 30.0
  max_retries: 3
  retry_delay: 1.0
  retry_backoff_multiplier: 2.0
  max_concurrent_operations: 10

coordination:
  enable_coordination: true
  lock_timeout: 60.0
  deadlock_detection_interval: 10.0
  enable_preemption: true
  enable_mapf: true
  mapf_timeout: 5.0

discovery:
  enable_discovery: true
  announce_interval: 5.0
  heartbeat_interval: 2.0
  health_timeout: 15.0
  lost_timeout: 30.0

logging:
  log_level: "INFO"
  log_to_file: false
  log_file_path: "/var/log/comc/comc.log"
  max_log_size_mb: 100
"""


def generate_default_config(output_path: str):
    """Generate a default configuration file"""
    with open(output_path, 'w') as f:
        f.write(DEFAULT_CONFIG_TEMPLATE)
