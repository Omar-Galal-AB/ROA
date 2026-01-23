# DIMC UE5 Bridge Documentation

## Overview

The UE5 Bridge subsystem provides bidirectional communication between the DIMC Python component running in WSL and the ADimensionsCollector C++ plugin running in Unreal Engine 5.

## Architecture

```
┌─────────────────────┐                      ┌─────────────────────┐
│   UE5 (Windows)     │                      │   WSL (Linux)       │
│                     │                      │                     │
│ ┌─────────────────┐ │   TCP Port 9876     │ ┌─────────────────┐ │
│ │ ADimensionsCollector│ ◄──────────────────────│ DIMCUe5Connector│ │
│ │                 │ │   (Requests)         │ │                 │ │
│ │ LIDAR Raycast   │ │                      │ │ Command Sender  │ │
│ │ Obstacle Detect │ │   TCP Port 9877     │ │ Event Handler   │ │
│ │ Sensor Manager  │ ├──────────────────────►│ Data Receiver   │ │
│ └─────────────────┘ │   (Responses/Data)   │ └─────────────────┘ │
│                     │                      │                     │
└─────────────────────┘                      └─────────────────────┘
```

## Protocol

### Message Format

All messages use length-prefixed JSON:

```
[4 bytes: length (big-endian)] [JSON payload]
```

### Message Types

| Type | Direction | Description |
|------|-----------|-------------|
| COMMAND | WSL → UE5 | Request with response expected |
| RESPONSE | UE5 → WSL | Response to a COMMAND |
| EVENT | Both | Fire-and-forget notification |
| DATA | UE5 → WSL | Streaming sensor data |

### Message Structure

```json
{
  "message_id": "uuid",
  "timestamp": 1704067200.0,
  "message_type": "COMMAND|RESPONSE|EVENT|DATA",
  "command": "command_name",
  "payload": {}
}
```

## Components

### DIMCUe5Connector

Main connector class for UE5 communication.

```python
from UE5Bridge import DIMCUe5Connector, ConnectionConfig

# Configure connection
config = ConnectionConfig(
    host="127.0.0.1",
    request_port=9876,
    response_port=9877,
    heartbeat_interval=2.0,
    reconnect_enabled=True
)

# Create connector
connector = DIMCUe5Connector(config=config)

# Set up callbacks
connector.on_lidar_scan = handle_lidar_scan
connector.on_obstacle_detected = handle_obstacle
connector.on_connection_state_changed = handle_state_change

# Connect
if connector.connect():
    print("Connected to UE5!")
    
# Send commands
result = connector.configure_lidar(
    num_rays=360,
    max_range=5000.0,
    fov=360.0,
    scan_rate=10.0
)

# Request scan
scan = connector.request_scan()

# Disconnect
connector.disconnect()
```

### ConnectionMonitor

Monitors bridge connection health.

```python
from UE5Bridge import ConnectionMonitor, MonitorConfig

# Configure monitor
config = MonitorConfig(
    health_check_interval=5.0,
    latency_check_interval=10.0,
    latency_warning_ms=100.0,
    latency_critical_ms=500.0
)

# Create monitor
monitor = ConnectionMonitor(connector, config=config)

# Set up callbacks
monitor.on_health_changed = handle_health_change
monitor.on_alert = handle_alert

# Start monitoring
monitor.start()

# Get metrics
metrics = monitor.get_metrics()
print(f"Latency: {metrics.latency_ms:.1f}ms")
print(f"Quality: {metrics.quality_score:.2f}")

# Get statistics
stats = monitor.get_statistics()

# Stop
monitor.stop()
```

## Configuration

### ConnectionConfig

| Parameter | Default | Description |
|-----------|---------|-------------|
| `host` | "127.0.0.1" | UE5 host address |
| `request_port` | 9876 | Port for sending requests |
| `response_port` | 9877 | Port for receiving data |
| `connect_timeout` | 5.0 | Connection timeout (seconds) |
| `receive_timeout` | 10.0 | Receive timeout (seconds) |
| `send_timeout` | 5.0 | Send timeout (seconds) |
| `command_timeout` | 30.0 | Command response timeout |
| `heartbeat_interval` | 2.0 | Heartbeat interval (seconds) |
| `heartbeat_timeout` | 10.0 | Heartbeat timeout |
| `reconnect_enabled` | True | Enable auto-reconnect |
| `reconnect_delay` | 1.0 | Initial reconnect delay |
| `reconnect_max_delay` | 30.0 | Maximum reconnect delay |
| `reconnect_backoff` | 2.0 | Backoff multiplier |
| `max_reconnect_attempts` | 10 | Max reconnect attempts |
| `receive_buffer_size` | 65536 | Receive buffer size |
| `send_queue_size` | 100 | Send queue size |

### MonitorConfig

| Parameter | Default | Description |
|-----------|---------|-------------|
| `health_check_interval` | 5.0 | Health check interval |
| `latency_check_interval` | 10.0 | Latency check interval |
| `stats_window_seconds` | 60 | Rolling stats window |
| `latency_warning_ms` | 100.0 | Latency warning threshold |
| `latency_critical_ms` | 500.0 | Latency critical threshold |
| `packet_loss_warning_percent` | 5.0 | Packet loss warning |
| `packet_loss_critical_percent` | 20.0 | Packet loss critical |
| `min_messages_per_second` | 1.0 | Minimum expected rate |
| `alert_cooldown_seconds` | 60.0 | Alert cooldown |

## Enums

### ConnectionState

```python
class ConnectionState(Enum):
    DISCONNECTED = auto()  # Not connected
    CONNECTING = auto()    # Connection in progress
    CONNECTED = auto()     # Successfully connected
    RECONNECTING = auto()  # Attempting reconnection
    ERROR = auto()         # Connection error
```

### ConnectionHealth

```python
class ConnectionHealth(Enum):
    HEALTHY = auto()       # All metrics normal
    DEGRADED = auto()      # Some issues but functional
    UNHEALTHY = auto()     # Significant issues
    DISCONNECTED = auto()  # Not connected
```

## Data Types

### LidarScanData

```python
@dataclass
class LidarScanData:
    timestamp: float
    scan_id: str
    robot_id: str
    hit_points: List[Dict[str, float]]  # [{x, y, z, distance, angle}]
    num_rays: int
    max_range: float
    field_of_view: float
    origin: Dict[str, float]  # {x, y, z}
    rotation: Dict[str, float]  # {pitch, yaw, roll}
```

### ObstacleData

```python
@dataclass
class ObstacleData:
    timestamp: float
    obstacle_id: str
    position: Dict[str, float]  # {x, y, z}
    dimensions: Dict[str, float]  # {width, height, depth}
    velocity: Dict[str, float]  # {vx, vy, vz}
    angular_velocity: Dict[str, float]  # {wx, wy, wz}
    classification: str
    confidence: float
    distance: float
```

### HealthMetrics

```python
@dataclass
class HealthMetrics:
    timestamp: float
    health: ConnectionHealth
    latency_ms: float
    packet_loss_percent: float
    messages_per_second: float
    errors_last_minute: int
    uptime_seconds: float
    quality_score: float  # 0.0 to 1.0
```

## DIMC Commands

| Command | Description | Parameters |
|---------|-------------|------------|
| `configure_lidar` | Configure LIDAR | num_rays, max_range, fov, scan_rate |
| `set_detection_zone` | Set detection zone | zone_id, shape, dimensions, position |
| `request_scan` | Request immediate scan | - |
| `get_obstacles` | Get obstacle list | - |
| `set_robot_transform` | Update robot position | robot_id, position, rotation |
| `get_sensor_status` | Get sensor status | - |
| `ping` | Latency check | timestamp |

## Event Callbacks

```python
# LIDAR scan received
def on_lidar_scan(scan_data: LidarScanData):
    print(f"Received scan {scan_data.scan_id} with {scan_data.num_rays} rays")

# Obstacle detected
def on_obstacle_detected(obstacle: ObstacleData):
    print(f"Obstacle {obstacle.obstacle_id} at distance {obstacle.distance:.2f}m")

# Connection state changed
def on_connection_state_changed(state: ConnectionState):
    print(f"Connection state: {state.name}")

# Health changed
def on_health_changed(old_health: ConnectionHealth, new_health: ConnectionHealth):
    print(f"Health: {old_health.name} -> {new_health.name}")

# Alert generated
def on_alert(alert_type: str, message: str, data: Dict):
    print(f"Alert [{alert_type}]: {message}")
```

## Integration with DIMC Core

The bridge is integrated into DimensionsCollector:

```python
class DimensionsCollector:
    def _start_bridge(self):
        from .UE5Bridge import DIMCUe5Connector, ConnectionConfig
        
        config = ConnectionConfig(
            host=self.config.get('bridge', {}).get('host', '127.0.0.1'),
            request_port=self.config.get('bridge', {}).get('request_port', 9876),
            response_port=self.config.get('bridge', {}).get('response_port', 9877)
        )
        
        self.ue5_connector = DIMCUe5Connector(config=config)
        self.ue5_connector.on_lidar_scan = self._on_lidar_scan_received
        self.ue5_connector.on_obstacle_detected = self._on_obstacle_received
        
        self.ue5_connector.connect()
```

## Configuration File

In `Config/dimc_settings.json`:

```json
{
  "bridge": {
    "enabled": true,
    "host": "127.0.0.1",
    "request_port": 9876,
    "response_port": 9877,
    "heartbeat_interval": 2.0,
    "reconnect_enabled": true,
    "auto_connect": true,
    "health_check_interval": 5.0,
    "latency_check_interval": 10.0
  }
}
```

## Troubleshooting

### Connection Refused
- Verify UE5 is running with ADimensionsCollector plugin
- Check firewall settings
- Verify ports are not in use

### High Latency
- Check network connectivity
- Reduce LIDAR ray count
- Increase scan interval

### Frequent Reconnects
- Check UE5 plugin stability
- Verify network reliability
- Increase timeout values

### Message Loss
- Check send queue size
- Verify receive buffer size
- Monitor rate limiting
