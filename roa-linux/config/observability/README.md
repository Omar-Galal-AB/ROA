# ROA Observability Stack

Complete observability infrastructure for the Robot Operations Architecture (ROA) system.

## 🎯 What's Included

| Component | Purpose | Port |
|-----------|---------|------|
| **Foxglove Studio** | ROS2 visualization (3D, plots, logs) | 8080 |
| **Grafana** | Dashboards & alerting | 3000 |
| **Prometheus** | Metrics storage | 9090 |
| **Loki** | Log aggregation | 3100 |
| **Tempo** | Distributed tracing | 3200 |
| **Pyroscope** | Continuous profiling | 4040 |
| **Alloy** | OpenTelemetry collector | 12345 |
| **Fluent Bit** | Log collector | 2020 |
| **Mimir** | Long-term metrics (optional) | 9009 |
| **Beyla** | eBPF auto-instrumentation (optional) | 9400 |

## 🚀 Quick Start

```bash
# Start the stack
./roa-observability.sh start

# Start with all optional components
./roa-observability.sh start --all

# Check status
./roa-observability.sh status

# View logs
./roa-observability.sh logs

# Stop
./roa-observability.sh stop
```

## 📁 Directory Structure

```
observability/
├── docker-compose.yml          # Main compose file
├── roa-observability.sh        # Management script
├── alloy/
│   └── config.alloy            # OpenTelemetry collector config
├── fluent-bit/
│   ├── fluent-bit.conf         # Log collection config
│   └── parsers.conf            # Log parsers
├── foxglove/
│   └── default-layout.json     # Default Foxglove layout
├── grafana/
│   ├── datasources.yaml        # Data source provisioning
│   └── dashboards/
│       ├── dashboards.yaml     # Dashboard provisioning
│       └── roa_overview.json   # Main ROA dashboard
├── k6/
│   └── roa_load_test.js        # Load testing script
├── loki/
│   └── loki-config.yaml        # Loki configuration
├── mimir/
│   └── mimir-config.yaml       # Mimir configuration
├── prometheus/
│   ├── prometheus.yml          # Prometheus configuration
│   └── rules/
│       └── roa_alerts.yml      # Alert rules
└── tempo/
    └── tempo-config.yaml       # Tempo configuration
```

## 🔗 Service URLs

After starting, access services at:

- **Foxglove Studio**: http://localhost:8080
- **Grafana**: http://localhost:3000 (admin / roa_admin)
- **Prometheus**: http://localhost:9090
- **Loki**: http://localhost:3100
- **Tempo**: http://localhost:3200
- **Pyroscope**: http://localhost:4040
- **Alloy UI**: http://localhost:12345

## 🦊 Foxglove Integration

### Live Visualization

```bash
# Install Foxglove Bridge
sudo apt install ros-humble-foxglove-bridge

# Start bridge
ros2 launch foxglove_bridge foxglove_bridge_launch.xml

# Open Foxglove Studio
# Connect to: ws://localhost:8765
```

### Record to MCAP

```bash
# Record all topics
ros2 bag record -s mcap -o ~/.roa/recordings/session_$(date +%Y%m%d_%H%M%S) -a

# Record specific topics
ros2 bag record -s mcap /roa/heartbeat /roa/status /tf
```

### MCAP CLI

```bash
# Install
pip install mcap-cli

# Get info
mcap info recording.mcap

# Convert from bag
mcap convert input.bag output.mcap

# Merge files
mcap merge file1.mcap file2.mcap -o merged.mcap
```

## 📊 Grafana Dashboards

Pre-built dashboards in the `ROA` folder:

1. **ROA Overview** - Component health, CPU/memory, logs, traces

### Create Custom Dashboards

1. Open Grafana → Dashboards → New Dashboard
2. Add panels using:
   - **Prometheus** for metrics
   - **Loki** for logs
   - **Tempo** for traces

## 🧪 Load Testing with k6

```bash
# Install k6
sudo apt install k6

# Run load test
k6 run k6/roa_load_test.js

# With Prometheus output
k6 run --out experimental-prometheus-rw k6/roa_load_test.js
```

## 🔧 Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ROA_LOG_DIR` | `~/.roa/logs` | ROA log directory to monitor |
| `ROA_ENV` | `development` | Environment label |
| `ROA_VERSION` | `1.0.0` | Version label |

### Profiles

| Profile | Components | Use Case |
|---------|------------|----------|
| (default) | Core stack | Normal operation |
| `beyla` | + eBPF instrumentation | Auto-trace without code changes |
| `mimir` | + Long-term storage | Multi-year metric retention |

```bash
# Enable profiles
./roa-observability.sh start --profile beyla
./roa-observability.sh start --profile mimir
./roa-observability.sh start --all
```

## 📈 Data Retention

| Data Type | Tool | Retention |
|-----------|------|-----------|
| Metrics | Prometheus | 30 days |
| Metrics (long-term) | Mimir | 1 year |
| Logs | Loki | 30 days |
| Traces | Tempo | 7 days |
| Profiles | Pyroscope | 14 days |

## 🛠️ Troubleshooting

### Check service health

```bash
./roa-observability.sh status
docker logs roa-fluent-bit
docker logs roa-loki
```

### No logs appearing in Loki

1. Check Fluent Bit: `curl http://localhost:2020/api/v1/health`
2. Verify log path: `ls -la ~/.roa/logs/`
3. Check Fluent Bit logs: `docker logs roa-fluent-bit`

### High memory usage

1. Reduce retention periods in configs
2. Limit Loki ingestion rate
3. Enable compaction in Loki/Tempo

### Reset everything

```bash
./roa-observability.sh clean
./roa-observability.sh start
```

## 📚 Documentation

- [Full Architecture Doc](../docs/ROA_OBSERVABILITY_STACK.md)
- [Grafana Docs](https://grafana.com/docs/)
- [Loki Docs](https://grafana.com/docs/loki/)
- [Tempo Docs](https://grafana.com/docs/tempo/)
- [Foxglove Docs](https://docs.foxglove.dev/)
- [Fluent Bit Docs](https://docs.fluentbit.io/)
