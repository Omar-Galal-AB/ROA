# DIMC Heartbeat System Documentation

## Overview

The Heartbeat subsystem provides health status monitoring and lifecycle management for the Dimensions Collector component. It uses file-based IPC for cross-platform compatibility between WSL and Windows.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Heartbeat System                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────┐    ┌─────────────────────────┐       │
│  │     DIMCHeartbeat       │    │  DIMCHeartbeatMonitor   │       │
│  │                         │    │                         │       │
│  │ - Self-registration     │    │ - Scan for clients      │       │
│  │ - Periodic heartbeat    │    │ - Track client health   │       │
│  │ - Health reporting      │    │ - Detect dead clients   │       │
│  │ - Status updates        │    │ - Auto-shutdown logic   │       │
│  └───────────┬─────────────┘    └───────────┬─────────────┘       │
│              │                               │                     │
│              ▼                               ▼                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │              .ipc/heartbeats/ Directory                      │  │
│  │                                                              │  │
│  │  dimc-abc123.heartbeat.json                                 │  │
│  │  webthread-xyz789.heartbeat.json                            │  │
│  │  fti-qwe456.heartbeat.json                                  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Heartbeat File Format

Each component writes a heartbeat file:

```
.ipc/heartbeats/{component}-{uuid}.heartbeat.json
```

File contents:
```json
{
  "client_id": "dimc-abc12345",
  "component": "DIMC",
  "timestamp": 1704067200.0,
  "timestamp_iso": "2024-01-01T00:00:00+00:00",
  "state": "ACTIVE",
  "health": "HEALTHY",
  "metrics": {
    "robots": 5,
    "messages_processed": 1000,
    "uptime_seconds": 3600
  },
  "capabilities": ["lidar", "obstacle_detection", "proximity_monitoring"]
}
```

## Components

### DIMCHeartbeat

The heartbeat agent for DIMC self-registration and health reporting.

```python
from dimc_heartbeat import DIMCHeartbeat, HeartbeatConfig, ComponentHealth

# Configure
config = HeartbeatConfig(
    ipc_base_path="/mnt/d/ROA/.ipc",
    heartbeat_interval=5.0,
    component_name="DIMC",
    component_version="2.0"
)

# Create heartbeat agent
heartbeat = DIMCHeartbeat(config=config)

# Set up callbacks
heartbeat.on_health_changed = handle_health_change

# Start heartbeat
heartbeat.start()

# Update health when issues occur
heartbeat.update_health(ComponentHealth.DEGRADED, "High latency detected")

# Update metrics periodically
heartbeat.update_metrics({
    "robots": 5,
    "messages_processed": 1000,
    "uptime_seconds": time.time() - start_time
})

# Get status
status = heartbeat.get_status()
print(f"Client ID: {status['client_id']}")
print(f"Health: {status['health']}")

# Stop when done
heartbeat.stop()
```

### DIMCHeartbeatMonitor

Monitor for tracking other components' heartbeats.

```python
from dimc_heartbeat import DIMCHeartbeatMonitor, HeartbeatConfig

# Configure
config = HeartbeatConfig(
    ipc_base_path="/mnt/d/ROA/.ipc",
    check_interval=10.0,
    stale_threshold=15.0,
    dead_threshold=30.0,
    auto_shutdown_enabled=True,
    auto_shutdown_delay=60.0
)

# Create monitor
monitor = DIMCHeartbeatMonitor(config=config)

# Set up callbacks
monitor.on_client_dead = handle_client_dead
monitor.on_shutdown_triggered = handle_shutdown

# Start monitoring
monitor.start()

# Query clients
clients = monitor.get_clients()
for client_id, info in clients.items():
    print(f"{client_id}: {info.state.name}")

# Check if any clients exist
if monitor.has_clients():
    print(f"Active clients: {monitor.get_active_count()}")

# Stop
monitor.stop()
```

## Configuration

### HeartbeatConfig

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ipc_base_path` | "/mnt/d/ROA/.ipc" | Base IPC directory |
| `heartbeat_dir` | "heartbeats" | Heartbeat subdirectory |
| `heartbeat_interval` | 5.0 | Heartbeat write interval |
| `stale_threshold` | 15.0 | Seconds until client is stale |
| `dead_threshold` | 30.0 | Seconds until client is dead |
| `check_interval` | 10.0 | Client check interval |
| `auto_shutdown_enabled` | True | Enable auto-shutdown |
| `auto_shutdown_delay` | 60.0 | Delay before shutdown |
| `component_name` | "DIMC" | Component identifier |
| `component_version` | "2.0" | Component version |
| `status_file_name` | "dimc.status.json" | Status file name |

## Enums

### HeartbeatState

```python
class HeartbeatState(Enum):
    REGISTERED = auto()    # Just registered
    ACTIVE = auto()        # Actively sending heartbeats
    STALE = auto()         # No recent heartbeat
    DEAD = auto()          # Considered dead
    DEREGISTERED = auto()  # Cleanly deregistered
```

### ComponentHealth

```python
class ComponentHealth(Enum):
    HEALTHY = auto()    # All good
    DEGRADED = auto()   # Some issues
    UNHEALTHY = auto()  # Significant problems
    UNKNOWN = auto()    # No health data
```

## Data Types

### HeartbeatData

```python
@dataclass
class HeartbeatData:
    client_id: str
    component: str
    timestamp: float
    state: str
    health: str
    metrics: Dict[str, Any]
    capabilities: List[str]
    
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict) -> 'HeartbeatData': ...
```

### ClientInfo

```python
@dataclass
class ClientInfo:
    client_id: str
    component: str
    registered_at: float
    last_heartbeat: float
    state: HeartbeatState
    health: ComponentHealth
    metadata: Dict[str, Any]
```

## Lifecycle

### Normal Lifecycle

```
┌─────────────┐    ┌──────────┐    ┌────────────┐    ┌──────────────┐
│ REGISTERED  │ ──►│  ACTIVE  │ ──►│  ACTIVE    │ ──►│ DEREGISTERED │
│ (start)     │    │(heartbeat)    │(heartbeat)     │  (stop)      │
└─────────────┘    └──────────┘    └────────────┘    └──────────────┘
```

### Abnormal Lifecycle

```
┌──────────┐    ┌───────┐    ┌───────┐
│  ACTIVE  │ ──►│ STALE │ ──►│ DEAD  │
│          │    │(15s)  │    │(30s)  │
└──────────┘    └───────┘    └───────┘
                     │
                     ▼
              (Client restart)
                     │
                     ▼
              ┌──────────┐
              │  ACTIVE  │
              └──────────┘
```

## Auto-Shutdown Feature

The monitor can trigger component shutdown when no clients remain:

```python
config = HeartbeatConfig(
    auto_shutdown_enabled=True,
    auto_shutdown_delay=60.0  # Wait 60s after last client
)

monitor = DIMCHeartbeatMonitor(config=config)
monitor.on_shutdown_triggered = lambda: print("Shutting down...")
monitor.start()
```

Timeline:
1. Last client deregisters or dies
2. Wait `auto_shutdown_delay` seconds
3. If still no clients, trigger shutdown callback
4. Component can then clean up and exit

## Integration with DIMC Core

```python
class DimensionsCollector:
    def _start_heartbeat(self):
        from .dimc_heartbeat import (
            DIMCHeartbeat, 
            DIMCHeartbeatMonitor,
            HeartbeatConfig
        )
        
        config = HeartbeatConfig(
            ipc_base_path=self.config.get('heartbeat', {}).get('ipc_path'),
            heartbeat_interval=self.config.get('heartbeat', {}).get('interval', 5.0)
        )
        
        # Create and start heartbeat agent
        self.heartbeat = DIMCHeartbeat(config=config)
        self.heartbeat.on_health_changed = self._on_heartbeat_health_changed
        self.heartbeat.start()
        
        # Create and start monitor
        self.heartbeat_monitor = DIMCHeartbeatMonitor(config=config)
        self.heartbeat_monitor.on_client_dead = self._on_component_dead
        self.heartbeat_monitor.start()
```

## Configuration File

In `Config/dimc_settings.json`:

```json
{
  "heartbeat": {
    "enabled": true,
    "ipc_path": "/mnt/d/ROA/.ipc",
    "interval": 5.0,
    "stale_threshold": 15.0,
    "dead_threshold": 30.0,
    "auto_shutdown": true,
    "shutdown_delay": 60.0
  }
}
```

## Event Callbacks

```python
# Health status changed
def on_health_changed(old_health: ComponentHealth, new_health: ComponentHealth):
    print(f"Health: {old_health.name} -> {new_health.name}")

# Client became dead
def on_client_dead(client: ClientInfo):
    print(f"Client died: {client.client_id} ({client.component})")

# Client became stale
def on_client_stale(client: ClientInfo):
    print(f"Client stale: {client.client_id}")

# Shutdown triggered (no more clients)
def on_shutdown_triggered():
    print("No clients remaining, initiating shutdown...")
    cleanup_and_exit()
```

## Troubleshooting

### Heartbeat Files Not Created
- Check IPC directory permissions
- Verify path exists and is writable
- Check for disk space issues

### Client Shown as Dead
- Verify heartbeat interval is shorter than stale threshold
- Check for process hangs or crashes
- Look for file system latency issues

### Auto-Shutdown Not Working
- Verify `auto_shutdown_enabled` is True
- Check `on_shutdown_triggered` callback is set
- Verify all clients properly deregistered

### Cross-Platform Issues
- Ensure IPC path is accessible from both Windows and WSL
- Use `/mnt/d/` paths for Windows drive access from WSL
- Check file timestamp resolution

## Best Practices

1. **Set Appropriate Thresholds**: stale_threshold < dead_threshold
2. **Update Metrics Regularly**: Keep metrics current for debugging
3. **Handle Health Changes**: Update health promptly on issues
4. **Clean Shutdown**: Always call stop() for clean deregistration
5. **Monitor Callback Errors**: Log exceptions in callbacks
