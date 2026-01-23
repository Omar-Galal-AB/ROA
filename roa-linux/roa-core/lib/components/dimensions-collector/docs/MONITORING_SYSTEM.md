# DIMC Monitoring System Documentation

## Overview

The DIMC Monitoring System provides comprehensive health and performance monitoring for the Dimensions Collector component. It tracks system resources, subsystem health, performance metrics, data quality, and generates alerts for operational issues.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     DIMCMonitoringSystem                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐    │
│  │ PerformanceProfiler │  │DataQualityMonitor│  │   RateLimiter   │    │
│  │                 │  │                 │  │                 │    │
│  │ - profile()     │  │ - record_message│  │ - allow()       │    │
│  │ - get_stats()   │  │ - check_quality │  │ - get_rate()    │    │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    Alert System                               │  │
│  │  - Alert generation with severity levels                     │  │
│  │  - Cooldown to prevent alert storms                          │  │
│  │  - Acknowledgment and resolution tracking                    │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                  Subsystem Health Tracking                    │  │
│  │  - Bridge, Heartbeat, Sensors, Obstacle Detection            │  │
│  │  - ROS2 Publisher, Tracking, Measurement                     │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                  Resource Monitoring                          │  │
│  │  - CPU usage (via psutil)                                    │  │
│  │  - Memory usage                                               │  │
│  │  - Thread count                                               │  │
│  │  - Open files, network connections                           │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. DIMCMonitoringSystem

The main coordinator class that manages all monitoring functionality.

```python
from dimc_monitoring import DIMCMonitoringSystem, MonitoringConfig

# Create with custom configuration
config = MonitoringConfig(
    health_check_interval=5.0,
    resource_check_interval=10.0,
    cpu_warning_percent=70.0,
    cpu_critical_percent=90.0
)

monitoring = DIMCMonitoringSystem(config=config)

# Set up callbacks
monitoring.on_alert = my_alert_handler
monitoring.on_status_change = my_status_handler

# Start monitoring
monitoring.start()

# Get status
status = monitoring.get_status()
print(f"Overall health: {status['overall_status']}")

# Stop when done
monitoring.stop()
```

### 2. PerformanceProfiler

Profile critical code paths to track timing metrics.

```python
from dimc_monitoring import PerformanceProfiler

profiler = PerformanceProfiler()

# Profile a code section
with profiler.profile("update_loop"):
    # ... critical code ...
    pass

# Get statistics
stats = profiler.get_stats("update_loop")
print(f"Average: {stats.avg_time_ms:.2f}ms, P95: {stats.p95_time_ms:.2f}ms")

# Or record timing directly
profiler.record_timing("operation_name", elapsed_ms)

# Get all stats
all_stats = profiler.get_all_stats()
for name, s in all_stats.items():
    print(f"{name}: {s.call_count} calls, avg {s.avg_time_ms:.2f}ms")
```

### 3. DataQualityMonitor

Track data quality metrics from various sources.

```python
from dimc_monitoring import DataQualityMonitor, MonitoringConfig

config = MonitoringConfig(
    data_staleness_threshold_ms=1000.0,
    validation_warning_rate=0.95
)
monitor = DataQualityMonitor(config)

# Record messages
monitor.record_message("bridge", valid=True, latency_ms=15.0)
monitor.record_message("bridge", valid=True, latency_ms=12.0)
monitor.record_message("bridge", valid=False, latency_ms=5.0)  # Invalid

# Check quality
status, message = monitor.check_quality("bridge")
print(f"Status: {status.value}, Message: {message}")

# Get metrics
metrics = monitor.get_metrics("bridge")
print(f"Validation rate: {metrics.validation_rate:.1%}")
print(f"Average latency: {metrics.avg_latency_ms:.1f}ms")
```

### 4. RateLimiter

Protect against data flooding using sliding window algorithm.

```python
from dimc_monitoring import RateLimiter

limiter = RateLimiter(max_per_second=100, window_seconds=1.0)

# Check if message should be processed
if limiter.allow():
    process_message(msg)
else:
    log.warning("Message dropped due to rate limiting")

# Check current rate
current_rate = limiter.get_current_rate()
print(f"Current rate: {current_rate:.1f} msg/sec")

# Check how many dropped
dropped = limiter.get_dropped_count()
print(f"Dropped messages: {dropped}")
```

## Configuration

### MonitoringConfig

| Parameter | Default | Description |
|-----------|---------|-------------|
| `health_check_interval` | 5.0 | Seconds between health checks |
| `resource_check_interval` | 10.0 | Seconds between resource checks |
| `performance_report_interval` | 60.0 | Seconds between perf reports |
| `cpu_warning_percent` | 70.0 | CPU warning threshold |
| `cpu_critical_percent` | 90.0 | CPU critical threshold |
| `memory_warning_percent` | 70.0 | Memory warning threshold |
| `memory_critical_percent` | 85.0 | Memory critical threshold |
| `thread_warning_count` | 50 | Thread warning threshold |
| `thread_critical_count` | 100 | Thread critical threshold |
| `data_staleness_threshold_ms` | 1000.0 | Stale data threshold |
| `validation_warning_rate` | 0.95 | Validation warning threshold |
| `validation_critical_rate` | 0.80 | Validation critical threshold |
| `latency_warning_ms` | 50.0 | Latency warning threshold |
| `latency_critical_ms` | 200.0 | Latency critical threshold |
| `alert_cooldown_seconds` | 60.0 | Cooldown between same alerts |
| `max_alerts_stored` | 1000 | Maximum alerts to store |
| `max_messages_per_second` | 1000 | Default rate limit |
| `rate_limit_window_seconds` | 1.0 | Rate limit window |

## Enums

### SubsystemStatus

```python
class SubsystemStatus(Enum):
    HEALTHY = "healthy"      # All good
    DEGRADED = "degraded"    # Some issues, but functional
    UNHEALTHY = "unhealthy"  # Significant problems
    OFFLINE = "offline"      # Not responding
    UNKNOWN = "unknown"      # No data yet
```

### AlertSeverity

```python
class AlertSeverity(Enum):
    INFO = "info"          # Informational
    WARNING = "warning"    # Warning, attention needed
    ERROR = "error"        # Error, action required
    CRITICAL = "critical"  # Critical, immediate action needed
```

### AlertCategory

```python
class AlertCategory(Enum):
    PERFORMANCE = "performance"    # Performance issues
    CONNECTION = "connection"      # Connection problems
    DATA_QUALITY = "data_quality"  # Data quality issues
    RESOURCE = "resource"          # Resource exhaustion
    SUBSYSTEM = "subsystem"        # Subsystem health
    SAFETY = "safety"              # Safety-related alerts
```

## Alert System

### Generating Alerts

```python
# From monitoring system
monitoring.generate_alert(
    severity="warning",
    category="performance",
    source="sensor_receiver",
    message="High latency detected",
    data={"latency_ms": 150}
)
```

### Retrieving Alerts

```python
# Get all alerts
alerts = monitoring.get_alerts()

# Filter by severity
critical_alerts = monitoring.get_alerts(severity=AlertSeverity.CRITICAL)

# Get only unacknowledged
unacked = monitoring.get_alerts(unacknowledged_only=True)

# Limit results
recent = monitoring.get_alerts(limit=10)
```

### Acknowledging Alerts

```python
# Acknowledge an alert
monitoring.acknowledge_alert("DIMC-000123")

# Resolve an alert
monitoring.resolve_alert("DIMC-000123")
```

## Status and Diagnostics API

### get_status()

Returns high-level health status.

```python
status = monitoring.get_status()
# {
#     "overall_status": "healthy",
#     "uptime_seconds": 3600.5,
#     "subsystems": {
#         "bridge": {"status": "healthy", ...},
#         "heartbeat": {"status": "healthy", ...},
#         ...
#     },
#     "resources": {
#         "cpu_percent": 25.5,
#         "memory_percent": 45.2,
#         ...
#     },
#     "alerts": {
#         "total": 10,
#         "unacknowledged": 2,
#         "unresolved": 3
#     }
# }
```

### get_diagnostics()

Returns comprehensive diagnostic data.

```python
diagnostics = monitoring.get_diagnostics()
# {
#     "status": {...},
#     "performance": {
#         "update_loop": {"avg_time_ms": 5.2, "p95_time_ms": 12.1, ...},
#         ...
#     },
#     "data_quality": {
#         "bridge": {"validation_rate": 0.99, "avg_latency_ms": 15.2, ...},
#         ...
#     },
#     "rate_limiters": {
#         "sensor_data": {"current_rate": 50.2, "dropped_count": 0},
#         ...
#     },
#     "recent_alerts": [...]
# }
```

## Integration with DIMC Core

The monitoring system is integrated into DimensionsCollector:

```python
# In dimc_core.py
class DimensionsCollector:
    def __init__(self):
        self.monitoring = DIMCMonitoringSystem(config=mon_config)
        
    def start(self):
        # Start monitoring
        if self._monitoring_enabled:
            self.monitoring.start()
            
    def stop(self):
        # Stop monitoring
        if self.monitoring:
            self.monitoring.stop()
            
    def get_status(self):
        # Delegate to monitoring
        if self.monitoring:
            return self.monitoring.get_status()
```

## Best Practices

1. **Profile Critical Paths**: Use the profiler for update loops, sensor processing, and obstacle detection.

2. **Track Data Quality**: Record message validity and latency from all data sources.

3. **Use Rate Limiting**: Protect against data flooding from faulty sensors or bridges.

4. **Configure Thresholds**: Adjust thresholds based on your deployment's normal operating range.

5. **Handle Alerts**: Set up callbacks to forward alerts to external monitoring systems.

6. **Regular Status Checks**: Periodically check `is_healthy()` for quick health verification.

## Troubleshooting

### High CPU Alerts
- Check performance profiler for slow operations
- Review rate limiter statistics for flooding
- Consider reducing update rates

### Data Quality Issues
- Check bridge connection status
- Verify sensor data sources
- Look for network issues

### Memory Growth
- Review alert storage (max_alerts_stored)
- Check for resource leaks in profiler samples
- Monitor robot registry size

## Dependencies

- **Required**: Python 3.8+
- **Optional**: `psutil` for system resource monitoring

Without psutil, resource monitoring will be disabled but other features work normally.

```bash
pip install psutil  # Optional but recommended
```
