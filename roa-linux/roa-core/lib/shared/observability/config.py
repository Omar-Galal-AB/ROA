"""
ROA Observability Configuration
================================
Centralized configuration for all observability components
"""

import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum


class LogLevel(Enum):
    """Log levels"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ExporterType(Enum):
    """Trace exporter types"""
    OTLP = "otlp"
    JAEGER = "jaeger"
    ZIPKIN = "zipkin"
    CONSOLE = "console"
    NONE = "none"


# Get the base path for storage (roa_linux folder)
_BASE_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
_DATA_PATH = os.path.join(_BASE_PATH, "data")


@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: LogLevel = LogLevel.INFO
    log_dir: str = field(default_factory=lambda: os.path.join(_DATA_PATH, "logs"))
    json_format: bool = True
    include_trace_context: bool = True
    max_file_size_mb: int = 100
    backup_count: int = 5
    console_output: bool = True
    
    # Fluent Bit integration
    fluent_bit_host: Optional[str] = None
    fluent_bit_port: int = 24224


@dataclass
class MetricsConfig:
    """Prometheus metrics configuration"""
    enabled: bool = True
    port: int = 9090
    host: str = "0.0.0.0"
    path: str = "/metrics"
    
    # Metric prefixes
    namespace: str = "roa"
    subsystem: Optional[str] = None
    
    # Push gateway for batch jobs
    pushgateway_url: Optional[str] = None
    push_interval_seconds: int = 15


@dataclass
class TracingConfig:
    """OpenTelemetry tracing configuration"""
    enabled: bool = True
    exporter: ExporterType = ExporterType.OTLP
    
    # OTLP endpoint (Tempo/Alloy)
    otlp_endpoint: str = "http://localhost:4317"
    otlp_insecure: bool = True
    
    # Sampling
    sample_rate: float = 1.0  # 1.0 = 100% sampling
    
    # Resource attributes
    service_namespace: str = "roa"
    deployment_environment: str = "development"


@dataclass
class MCAPConfig:
    """MCAP recording configuration"""
    enabled: bool = True
    output_dir: str = field(default_factory=lambda: os.path.join(_DATA_PATH, "recordings"))
    
    # Recording settings
    max_file_size_mb: int = 1024  # 1GB
    split_on_size: bool = True
    compression: str = "zstd"  # zstd, lz4, none
    
    # Topics to record
    record_all_topics: bool = False
    topic_whitelist: list = field(default_factory=list)
    topic_blacklist: list = field(default_factory=list)


@dataclass
class HealthConfig:
    """Health check configuration"""
    enabled: bool = True
    port: int = 8080
    path: str = "/health"
    
    # Health check intervals
    check_interval_seconds: float = 5.0
    unhealthy_threshold: int = 3


@dataclass
class ObservabilityConfig:
    """
    Complete observability configuration
    
    Can be loaded from environment variables or config file
    """
    # Component identification
    component_name: str = "roa-component"
    service_version: str = "1.0.0"
    instance_id: Optional[str] = None
    
    # Sub-configurations
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    tracing: TracingConfig = field(default_factory=TracingConfig)
    mcap: MCAPConfig = field(default_factory=MCAPConfig)
    health: HealthConfig = field(default_factory=HealthConfig)
    
    # Global settings
    debug_mode: bool = False
    
    @classmethod
    def from_env(cls, component_name: str = "roa-component") -> 'ObservabilityConfig':
        """
        Load configuration from environment variables
        
        Environment variable prefix: ROA_OBS_
        """
        def get_env(key: str, default: Any = None) -> Any:
            return os.environ.get(f"ROA_OBS_{key}", default)
        
        def get_env_bool(key: str, default: bool = False) -> bool:
            val = get_env(key, str(default)).lower()
            return val in ('true', '1', 'yes', 'on')
        
        def get_env_int(key: str, default: int = 0) -> int:
            try:
                return int(get_env(key, default))
            except (ValueError, TypeError):
                return default
        
        def get_env_float(key: str, default: float = 0.0) -> float:
            try:
                return float(get_env(key, default))
            except (ValueError, TypeError):
                return default
        
        return cls(
            component_name=get_env("COMPONENT_NAME", component_name),
            service_version=get_env("SERVICE_VERSION", "1.0.0"),
            instance_id=get_env("INSTANCE_ID"),
            debug_mode=get_env_bool("DEBUG", False),
            
            logging=LoggingConfig(
                level=LogLevel(get_env("LOG_LEVEL", "INFO")),
                log_dir=get_env("LOG_DIR", os.path.join(_DATA_PATH, "logs")),
                json_format=get_env_bool("LOG_JSON", True),
                include_trace_context=get_env_bool("LOG_TRACE_CONTEXT", True),
                fluent_bit_host=get_env("FLUENT_BIT_HOST"),
                fluent_bit_port=get_env_int("FLUENT_BIT_PORT", 24224),
            ),
            
            metrics=MetricsConfig(
                enabled=get_env_bool("METRICS_ENABLED", True),
                port=get_env_int("METRICS_PORT", 9090),
                host=get_env("METRICS_HOST", "0.0.0.0"),
                namespace=get_env("METRICS_NAMESPACE", "roa"),
                pushgateway_url=get_env("PUSHGATEWAY_URL"),
            ),
            
            tracing=TracingConfig(
                enabled=get_env_bool("TRACING_ENABLED", True),
                otlp_endpoint=get_env("OTLP_ENDPOINT", "http://localhost:4317"),
                sample_rate=get_env_float("TRACE_SAMPLE_RATE", 1.0),
                deployment_environment=get_env("ENVIRONMENT", "development"),
            ),
            
            mcap=MCAPConfig(
                enabled=get_env_bool("MCAP_ENABLED", True),
                output_dir=get_env("MCAP_OUTPUT_DIR", os.path.join(_DATA_PATH, "recordings")),
                compression=get_env("MCAP_COMPRESSION", "zstd"),
            ),
            
            health=HealthConfig(
                enabled=get_env_bool("HEALTH_ENABLED", True),
                port=get_env_int("HEALTH_PORT", 8080),
                check_interval_seconds=get_env_float("HEALTH_INTERVAL", 5.0),
            ),
        )
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ObservabilityConfig':
        """Load configuration from dictionary"""
        logging_data = data.get('logging', {})
        metrics_data = data.get('metrics', {})
        tracing_data = data.get('tracing', {})
        mcap_data = data.get('mcap', {})
        health_data = data.get('health', {})
        
        return cls(
            component_name=data.get('component_name', 'roa-component'),
            service_version=data.get('service_version', '1.0.0'),
            instance_id=data.get('instance_id'),
            debug_mode=data.get('debug_mode', False),
            logging=LoggingConfig(**logging_data) if logging_data else LoggingConfig(),
            metrics=MetricsConfig(**metrics_data) if metrics_data else MetricsConfig(),
            tracing=TracingConfig(**tracing_data) if tracing_data else TracingConfig(),
            mcap=MCAPConfig(**mcap_data) if mcap_data else MCAPConfig(),
            health=HealthConfig(**health_data) if health_data else HealthConfig(),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Export configuration to dictionary"""
        return {
            'component_name': self.component_name,
            'service_version': self.service_version,
            'instance_id': self.instance_id,
            'debug_mode': self.debug_mode,
            'logging': {
                'level': self.logging.level.value,
                'log_dir': self.logging.log_dir,
                'json_format': self.logging.json_format,
            },
            'metrics': {
                'enabled': self.metrics.enabled,
                'port': self.metrics.port,
                'namespace': self.metrics.namespace,
            },
            'tracing': {
                'enabled': self.tracing.enabled,
                'otlp_endpoint': self.tracing.otlp_endpoint,
                'sample_rate': self.tracing.sample_rate,
            },
            'mcap': {
                'enabled': self.mcap.enabled,
                'output_dir': self.mcap.output_dir,
                'compression': self.mcap.compression,
            },
            'health': {
                'enabled': self.health.enabled,
                'port': self.health.port,
            },
        }


# Default configurations for each component
COMPONENT_DEFAULTS = {
    'webthread': ObservabilityConfig(
        component_name='webthread',
        metrics=MetricsConfig(port=9091, subsystem='webthread'),
        health=HealthConfig(port=8081),
    ),
    'fti': ObservabilityConfig(
        component_name='fti',
        metrics=MetricsConfig(port=9092, subsystem='fti'),
        health=HealthConfig(port=8082),
    ),
    'dimc': ObservabilityConfig(
        component_name='dimc',
        metrics=MetricsConfig(port=9093, subsystem='dimc'),
        health=HealthConfig(port=8083),
    ),
    'roc': ObservabilityConfig(
        component_name='roc',
        metrics=MetricsConfig(port=9094, subsystem='roc'),
        health=HealthConfig(port=8084),
    ),
    'comc': ObservabilityConfig(
        component_name='comc',
        metrics=MetricsConfig(port=9095, subsystem='comc'),
        health=HealthConfig(port=8085),
    ),
}


def get_component_config(component_name: str) -> ObservabilityConfig:
    """Get default configuration for a component"""
    return COMPONENT_DEFAULTS.get(
        component_name.lower(),
        ObservabilityConfig(component_name=component_name)
    )
