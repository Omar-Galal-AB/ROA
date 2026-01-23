# UE5 Connection Monitoring

## Overview

The UE5 Connection Monitor automatically validates connectivity between ROA webthread and Unreal Engine 5 during startup. This ensures that communication issues are detected early and provides clear diagnostic information.

## Features

### Automatic Connection Checking
- Runs automatically when webthread starts
- Tests TCP connectivity through socat relay
- Validates protocol handshake with UE5
- Provides detailed diagnostic reports

### Intelligent Retry Logic
- Configurable retry attempts
- Exponential backoff between retries
- Timeout protection

### Clear Diagnostics
When connection fails, the monitor provides actionable information:
- TCP connection status
- Command transmission status
- Response validation
- Troubleshooting recommendations

## Architecture

```
ROA Webthread (WSL)
    ↓
Connection Monitor
    ↓
socat relay (WSL:9876)
    ↓
Windows Network Stack
    ↓
UE5 ROA Plugin (Windows:9876)
```

## Configuration

Edit `Config/roa_component_config.yaml`:

```yaml
ue5_connection:
  check_on_startup: true    # Enable/disable connection check
  required: true            # Abort startup if connection fails
  host: "localhost"         # UE5 host address
  port: 9876               # UE5 port
  max_attempts: 3          # Connection retry attempts
  retry_delay: 2.0         # Seconds between retries
  timeout: 5.0             # Connection timeout
  verbose_diagnostics: true
  log_connection_details: true
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `check_on_startup` | bool | true | Enable connection check during startup |
| `required` | bool | true | Abort startup if connection fails |
| `host` | string | "localhost" | UE5 host address |
| `port` | int | 9876 | UE5 communication port |
| `max_attempts` | int | 3 | Number of connection attempts |
| `retry_delay` | float | 2.0 | Seconds between retry attempts |
| `timeout` | float | 5.0 | Connection timeout in seconds |
| `verbose_diagnostics` | bool | true | Enable detailed diagnostic output |
| `log_connection_details` | bool | true | Log connection details |

## Usage

### As Part of Webthread Startup

The connection monitor runs automatically when webthread starts:

```bash
# Connection check happens automatically
ros2 run webthread webthread_node
```

### Standalone Testing

Test connection independently:

```bash
# Using Python module
cd /home/myws/roa/roa_linux/roa-core/lib/components/webthread
python3 -m src.python.UE5Bridge.connection_monitor

# Using integration test script
./test_ue5_integration.sh
```

### Programmatic Usage

```python
from UE5Bridge.connection_monitor import UE5ConnectionMonitor, ConnectionStatus

# Create monitor
monitor = UE5ConnectionMonitor(host="localhost", port=9876)

# Check connection
status, diagnostics = monitor.check_connection(timeout=5.0)

if status == ConnectionStatus.CONNECTED:
    print("✓ Connected!")
else:
    print("✗ Connection failed")
    print(monitor.get_diagnostic_report())

# Wait for connection with retries
if monitor.wait_for_connection(max_attempts=5, retry_delay=2.0):
    print("Connected after retries")
```

## Diagnostic Report

Sample diagnostic report when UE5 is not responding:

```
============================================================
  UE5 CONNECTION DIAGNOSTIC REPORT
============================================================

Target: localhost:9876
Status: no_response
Last Check: 2025-12-16 08:16:20

✗ CONNECTION FAILED
  Error: No response from UE5

Diagnostics:
  ✓ TCP connection: OK
  ✓ Command sent: OK
  ✗ Response received: NONE
    - Is UE5 in Play mode?
    - Is ROA plugin active?
    - Check UE5 Output Log for errors

============================================================
```

## Connection States

| State | Description | Action Required |
|-------|-------------|-----------------|
| `CONNECTED` | Successfully connected | None - ready to use |
| `NO_RESPONSE` | Connected but no response | Check UE5 Play mode and plugin |
| `CONNECTION_REFUSED` | Port not accessible | Check socat relay |
| `TIMEOUT` | Connection attempt timed out | Check network/firewall |
| `ERROR` | Unexpected error | Check logs for details |

## Troubleshooting

### TCP Connection Refused
**Symptom:** `TCP connection: REFUSED`

**Solutions:**
1. Check if socat relay is running:
   ```bash
   ps aux | grep socat
   ```
2. Start socat relay:
   ```bash
   WINDOWS_IP=$(ip route show | grep default | awk '{print $3}')
   socat -d -d TCP-LISTEN:9876,fork,reuseaddr TCP:$WINDOWS_IP:9876
   ```

### No Response from UE5
**Symptom:** `Response received: NONE`

**Solutions:**
1. Ensure UE5 is running
2. Open ROA_V1 project
3. Click Play button in UE5
4. Verify ROA plugin is enabled:
   - Edit > Plugins
   - Search "ROA"
   - Ensure checkbox is checked
5. Check UE5 Output Log for errors

### Connection Timeout
**Symptom:** `TCP connection: TIMEOUT`

**Solutions:**
1. Check Windows firewall settings
2. Verify WSL networking:
   ```bash
   ip route show
   ```
3. Test direct Windows connection:
   ```bash
   powershell.exe -Command "Test-NetConnection -ComputerName localhost -Port 9876"
   ```

## Integration with Component Starter

The connection monitor is integrated into `ComponentStarter`:

```python
from UE5Bridge.component_starter import ComponentStarter

starter = ComponentStarter()
# Connection check happens automatically in start_all_components()
success = starter.start_all_components()
```

## Testing

### Manual Test
```bash
cd /home/myws/roa/roa_linux/roa-core/lib/components/webthread
./test_ue5_integration.sh
```

### Full Integration Test
```bash
cd /mnt/d/ROA/UE5_Projects/ROA_V1
python3 test_connection.py
```

## Files

| File | Purpose |
|------|---------|
| `src/python/UE5Bridge/connection_monitor.py` | Connection monitoring implementation |
| `src/python/UE5Bridge/component_starter.py` | Integration with component startup |
| `Config/roa_component_config.yaml` | Configuration settings |
| `test_ue5_integration.sh` | Standalone integration test |
| `docs/UE5_CONNECTION_MONITORING.md` | This documentation |

## Protocol

The monitor validates the ROA-UE5 protocol:

### Request (ROA → UE5)
```json
{
  "message_id": "1234567890.123",
  "timestamp": 1234567890.123,
  "message_type": "REQUEST",
  "command": "connect",
  "payload": {
    "client_type": "webthread",
    "version": "0.1.0"
  }
}
```

### Expected Response (UE5 → ROA)
```json
{
  "status": "success",
  "session_id": "uuid-here",
  "timestamp": 1234567890.123
}
```

## Future Enhancements

- Connection health monitoring during runtime
- Automatic reconnection on connection loss
- Metrics collection (latency, uptime)
- Connection quality indicators
- Multiple UE5 instance support

## See Also

- [UE5 Connector Documentation](./UE5_CONNECTOR.md)
- [Component Startup Documentation](./COMPONENT_STARTUP.md)
- [ROA Protocol Specification](/mnt/d/ROA/UE5_Projects/ROA_V1/Guides/COMMUNICATION_PROTOCOL.md)
