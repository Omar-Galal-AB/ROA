# ROA Complete Observability Stack

## Overview

This document defines the **complete observability and storage architecture** for the Robot Operations Architecture (ROA) system. This stack is built entirely on **open-source, self-hosted components** with no paid services required.

---

## 📋 Complete Tool Inventory

### ✅ INCLUDED (All Free & Open-Source)

| Category | Tool | Purpose | License |
|----------|------|---------|---------|
| **ROS2 Recording** | rosbag2 + MCAP | Record all ROS2 topics to MCAP format | Apache-2.0 |
| **Visualization** | Foxglove Studio (self-hosted) | 3D viz, plots, logs, diagnostics | MPL-2.0 |
| **Live Bridge** | foxglove_bridge | WebSocket bridge for live ROS2 data | MIT |
| **SDK** | foxglove-sdk (Python/C++/Rust) | Write MCAP files, stream to Studio | MIT |
| **MCAP Tools** | mcap CLI | Convert, merge, filter, inspect MCAP files | MIT |
| **Log Collection** | Fluent Bit | Lightweight log processor (70+ plugins) | Apache-2.0 |
| **Log Storage** | Grafana Loki | Log aggregation database | AGPL-3.0 |
| **Metrics Collection** | Grafana Alloy | OpenTelemetry collector | Apache-2.0 |
| **Metrics Storage** | Prometheus | Time-series metrics database | Apache-2.0 |
| **Metrics Scale** | Grafana Mimir | Long-term scalable Prometheus storage | AGPL-3.0 |
| **Dashboards** | Grafana | Visualization and alerting | AGPL-3.0 |
| **Tracing** | Grafana Tempo | Distributed tracing backend | AGPL-3.0 |
| **Auto-Instrument** | Grafana Beyla | Zero-code eBPF instrumentation | Apache-2.0 |
| **Profiling** | Grafana Pyroscope | Continuous profiling | AGPL-3.0 |
| **Load Testing** | k6 | Performance/load testing | AGPL-3.0 |
| **Dashboard Templates** | grafana-dashboards | Pre-built dashboard examples | Apache-2.0 |
| **Elastic Beats** | Filebeat, Metricbeat, etc. | Alternative log/metric shippers | Apache-2.0 |
| **OTel Spec** | OpenTelemetry Specification | Standards reference | Apache-2.0 |

### ❌ EXCLUDED

| Tool | Reason |
|------|--------|
| MARV Robotics | Per user request |
| Deep Lake | Per user request |
| ELK Stack | Per user request |
| Faro Web SDK | For web frontends only (not relevant) |
| Grafana OnCall | Deprecated (entering maintenance mode) |
| Graphite | Legacy, superseded by Prometheus |
| Tanka | Only for Kubernetes config management |

---

## 🏗️ Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              ROA COMPONENTS (ROS2)                                   │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐│
│  │  Webthread   │ │     FTI      │ │    DIMC      │ │     ROC      │ │    COMC      ││
│  │   (Hub)      │ │ (Telemetry)  │ │ (Interface)  │ │  (Control)   │ │   (Comms)    ││
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘│
│         │                │                │                │                │        │
│         └────────────────┴────────────────┼────────────────┴────────────────┘        │
│                                           │                                          │
│                          ┌────────────────┴────────────────┐                         │
│                          ▼                                 ▼                         │
│               ┌─────────────────────┐         ┌─────────────────────┐               │
│               │  ROS2 Topics/Msgs   │         │   ROA Log Files     │               │
│               │  /roa/*, /tf, etc   │         │  ~/.roa/logs/*.log  │               │
│               └──────────┬──────────┘         └──────────┬──────────┘               │
└──────────────────────────┼───────────────────────────────┼──────────────────────────┘
                           │                               │
       ┌───────────────────┼───────────────────────────────┼───────────────────┐
       │                   │                               │                   │
       ▼                   ▼                               ▼                   ▼
┌─────────────┐  ┌─────────────────────┐       ┌─────────────────────┐  ┌─────────────┐
│ rosbag2     │  │  foxglove_bridge    │       │    Fluent Bit       │  │   Beyla     │
│ (MCAP)      │  │  (WebSocket)        │       │  (Log Collector)    │  │  (eBPF)     │
└──────┬──────┘  └──────────┬──────────┘       └──────────┬──────────┘  └──────┬──────┘
       │                    │                             │                    │
       ▼                    ▼                             │                    │
┌─────────────────────────────────────────┐               │                    │
│     ~/.roa/recordings/                  │               │                    │
│     ├── session_20260103_120000.mcap   │               │                    │
│     ├── session_20260103_130000.mcap   │               │                    │
│     └── ...                            │               │                    │
└──────────────────┬──────────────────────┘               │                    │
                   │                                      │                    │
                   ▼                                      │                    │
       ┌───────────────────────────────┐                  │                    │
       │     Foxglove Studio           │                  │                    │
       │     (Self-Hosted Docker)      │                  │                    │
       │     http://localhost:8080     │                  │                    │
       │                               │                  │                    │
       │  ┌───────┐ ┌───────┐ ┌──────┐ │                  │                    │
       │  │ 3D Viz│ │ Plots │ │ Logs │ │                  │                    │
       │  └───────┘ └───────┘ └──────┘ │                  │                    │
       └───────────────────────────────┘                  │                    │
                                                          │                    │
                           ┌──────────────────────────────┴────────────────────┘
                           │
                           ▼
              ┌────────────────────────────────────────────────────────────────┐
              │                    Grafana Alloy                               │
              │              (OpenTelemetry Collector)                         │
              │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
              │  │ Logs Input  │  │Metrics Input│  │Traces Input │             │
              │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
              └─────────┼────────────────┼────────────────┼────────────────────┘
                        │                │                │
        ┌───────────────┼────────────────┼────────────────┼───────────────┐
        │               │                │                │               │
        ▼               ▼                ▼                ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  Loki       │ │ Prometheus  │ │   Mimir     │ │   Tempo     │ │ Pyroscope   │
│  (Logs)     │ │ (Metrics)   │ │(Long-term)  │ │ (Traces)    │ │(Profiling)  │
│  :3100      │ │   :9090     │ │   :9009     │ │   :3200     │ │   :4040     │
└──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
       │               │               │               │               │
       └───────────────┴───────────────┼───────────────┴───────────────┘
                                       │
                                       ▼
                          ┌────────────────────────────┐
                          │         Grafana            │
                          │    (Dashboards & Alerts)   │
                          │    http://localhost:3000   │
                          └────────────────────────────┘
```

---

## 📁 File Structure

```
~/.roa/
├── recordings/                          # MCAP recordings from rosbag2
│   ├── session_20260103_120000/
│   │   ├── metadata.yaml
│   │   └── session_20260103_120000_0.mcap
│   ├── session_20260103_130000/
│   └── ...
├── logs/                                # Application logs
│   ├── webthread.log
│   ├── fti.log
│   ├── dimc.log
│   ├── roc.log
│   └── comc.log
├── metrics/                             # Prometheus metrics (optional local)
├── traces/                              # Tempo traces (optional local)
├── config/
│   ├── fluent-bit/
│   │   ├── fluent-bit.conf
│   │   └── parsers.conf
│   ├── grafana/
│   │   ├── datasources.yaml
│   │   └── dashboards/
│   ├── prometheus/
│   │   └── prometheus.yml
│   ├── loki/
│   │   └── loki-config.yaml
│   ├── tempo/
│   │   └── tempo-config.yaml
│   ├── alloy/
│   │   └── config.alloy
│   └── foxglove/
│       └── default-layout.json
└── docker/
    └── docker-compose.yml               # Full observability stack
```

---

## 🐳 Docker Compose Stack

Create `~/.roa/docker/docker-compose.yml`:

```yaml
version: "3.8"

services:
  # =============================================================================
  # FOXGLOVE STUDIO - ROS2 Visualization (Self-Hosted)
  # =============================================================================
  foxglove-studio:
    image: ghcr.io/foxglove/studio:latest
    container_name: roa-foxglove-studio
    ports:
      - "8080:8080"
    volumes:
      - ../config/foxglove/default-layout.json:/foxglove/default-layout.json:ro
    restart: unless-stopped

  # =============================================================================
  # GRAFANA - Dashboards & Alerting
  # =============================================================================
  grafana:
    image: grafana/grafana:latest
    container_name: roa-grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=roa_admin
      - GF_USERS_ALLOW_SIGN_UP=false
    volumes:
      - grafana_data:/var/lib/grafana
      - ../config/grafana/datasources.yaml:/etc/grafana/provisioning/datasources/datasources.yaml:ro
      - ../config/grafana/dashboards:/etc/grafana/provisioning/dashboards:ro
    depends_on:
      - prometheus
      - loki
      - tempo
    restart: unless-stopped

  # =============================================================================
  # PROMETHEUS - Metrics Database
  # =============================================================================
  prometheus:
    image: prom/prometheus:latest
    container_name: roa-prometheus
    ports:
      - "9090:9090"
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
      - '--web.enable-lifecycle'
      - '--web.enable-remote-write-receiver'
    volumes:
      - prometheus_data:/prometheus
      - ../config/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    restart: unless-stopped

  # =============================================================================
  # LOKI - Log Aggregation
  # =============================================================================
  loki:
    image: grafana/loki:latest
    container_name: roa-loki
    ports:
      - "3100:3100"
    command: -config.file=/etc/loki/local-config.yaml
    volumes:
      - loki_data:/loki
      - ../config/loki/loki-config.yaml:/etc/loki/local-config.yaml:ro
    restart: unless-stopped

  # =============================================================================
  # TEMPO - Distributed Tracing
  # =============================================================================
  tempo:
    image: grafana/tempo:latest
    container_name: roa-tempo
    ports:
      - "3200:3200"   # Tempo HTTP
      - "4317:4317"   # OTLP gRPC
      - "4318:4318"   # OTLP HTTP
      - "9411:9411"   # Zipkin
    command: ["-config.file=/etc/tempo/tempo-config.yaml"]
    volumes:
      - tempo_data:/tmp/tempo
      - ../config/tempo/tempo-config.yaml:/etc/tempo/tempo-config.yaml:ro
    restart: unless-stopped

  # =============================================================================
  # PYROSCOPE - Continuous Profiling
  # =============================================================================
  pyroscope:
    image: grafana/pyroscope:latest
    container_name: roa-pyroscope
    ports:
      - "4040:4040"
    volumes:
      - pyroscope_data:/data
    restart: unless-stopped

  # =============================================================================
  # MIMIR - Long-term Metrics Storage (Optional - for scaling)
  # =============================================================================
  mimir:
    image: grafana/mimir:latest
    container_name: roa-mimir
    ports:
      - "9009:9009"
    command: ["-config.file=/etc/mimir/mimir-config.yaml"]
    volumes:
      - mimir_data:/data
      - ../config/mimir/mimir-config.yaml:/etc/mimir/mimir-config.yaml:ro
    profiles:
      - mimir  # Only start with --profile mimir
    restart: unless-stopped

  # =============================================================================
  # GRAFANA ALLOY - OpenTelemetry Collector
  # =============================================================================
  alloy:
    image: grafana/alloy:latest
    container_name: roa-alloy
    ports:
      - "12345:12345"  # Alloy UI
      - "4320:4317"    # OTLP gRPC (shifted to avoid Tempo conflict)
    command:
      - run
      - /etc/alloy/config.alloy
      - --server.http.listen-addr=0.0.0.0:12345
    environment:
      - LOKI_HOST=loki:3100
      - PROMETHEUS_HOST=prometheus:9090
      - TEMPO_HOST=tempo:4317
      - PYROSCOPE_HOST=pyroscope:4040
    volumes:
      - ../config/alloy/config.alloy:/etc/alloy/config.alloy:ro
    depends_on:
      - loki
      - prometheus
      - tempo
      - pyroscope
    restart: unless-stopped

  # =============================================================================
  # FLUENT BIT - Log Collector
  # =============================================================================
  fluent-bit:
    image: fluent/fluent-bit:latest
    container_name: roa-fluent-bit
    volumes:
      - ../config/fluent-bit/fluent-bit.conf:/fluent-bit/etc/fluent-bit.conf:ro
      - ../config/fluent-bit/parsers.conf:/fluent-bit/etc/parsers.conf:ro
      - ../../logs:/var/log/roa:ro  # Mount ROA logs
    depends_on:
      - loki
    restart: unless-stopped

  # =============================================================================
  # BEYLA - eBPF Auto-Instrumentation (Linux only, requires privileges)
  # =============================================================================
  beyla:
    image: grafana/beyla:latest
    container_name: roa-beyla
    privileged: true
    pid: "host"
    environment:
      - BEYLA_PROMETHEUS_PORT=9400
      - BEYLA_OPEN_PORT=9877-9882  # ROA HB ports
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4317
    network_mode: host
    profiles:
      - beyla  # Only start with --profile beyla
    restart: unless-stopped

volumes:
  grafana_data:
  prometheus_data:
  loki_data:
  tempo_data:
  pyroscope_data:
  mimir_data:
```

---

## ⚙️ Configuration Files

### Fluent Bit Configuration

Create `~/.roa/config/fluent-bit/fluent-bit.conf`:

```ini
[SERVICE]
    Flush        1
    Daemon       Off
    Log_Level    info
    Parsers_File parsers.conf
    HTTP_Server  On
    HTTP_Listen  0.0.0.0
    HTTP_Port    2020
    storage.metrics On

# =============================================================================
# INPUTS - Tail ROA Log Files
# =============================================================================
[INPUT]
    Name              tail
    Tag               roa.webthread
    Path              /var/log/roa/webthread.log
    Parser            roa_log
    Refresh_Interval  5
    Mem_Buf_Limit     5MB

[INPUT]
    Name              tail
    Tag               roa.fti
    Path              /var/log/roa/fti.log
    Parser            roa_log
    Refresh_Interval  5

[INPUT]
    Name              tail
    Tag               roa.dimc
    Path              /var/log/roa/dimc.log
    Parser            roa_log
    Refresh_Interval  5

[INPUT]
    Name              tail
    Tag               roa.roc
    Path              /var/log/roa/roc.log
    Parser            roa_log
    Refresh_Interval  5

[INPUT]
    Name              tail
    Tag               roa.comc
    Path              /var/log/roa/comc.log
    Parser            roa_log
    Refresh_Interval  5

# Collect system metrics
[INPUT]
    Name          cpu
    Tag           roa.metrics.cpu
    Interval_Sec  10

[INPUT]
    Name          mem
    Tag           roa.metrics.mem
    Interval_Sec  10

[INPUT]
    Name          disk
    Tag           roa.metrics.disk
    Interval_Sec  30

# =============================================================================
# FILTERS - Process and enrich logs
# =============================================================================
[FILTER]
    Name          record_modifier
    Match         roa.*
    Record        hostname ${HOSTNAME}
    Record        environment production

[FILTER]
    Name          grep
    Match         roa.*
    Exclude       level DEBUG

# Convert logs to metrics
[FILTER]
    Name          log_to_metrics
    Match         roa.*
    Tag           roa.metrics.logs
    Metric_Mode   counter
    Metric_Name   roa_log_total
    Metric_Description Total number of ROA log entries
    Label_Field   level

# =============================================================================
# OUTPUTS - Send to Loki and Prometheus
# =============================================================================
[OUTPUT]
    Name          loki
    Match         roa.*
    Host          loki
    Port          3100
    Labels        job=roa, component=$TAG[1]
    Label_Keys    $level, $hostname
    Auto_Kubernetes_Labels Off

[OUTPUT]
    Name          prometheus_exporter
    Match         roa.metrics.*
    Host          0.0.0.0
    Port          2021

# Forward to Alloy for OpenTelemetry processing
[OUTPUT]
    Name          opentelemetry
    Match         roa.*
    Host          alloy
    Port          4317
    Logs_uri      /v1/logs
    Tls           Off
    Tls.verify    Off
```

Create `~/.roa/config/fluent-bit/parsers.conf`:

```ini
[PARSER]
    Name        roa_log
    Format      regex
    Regex       ^\[(?<time>[^\]]+)\] \[(?<level>\w+)\] \[(?<component>\w+)\] (?<message>.*)$
    Time_Key    time
    Time_Format %Y-%m-%d %H:%M:%S.%L
    Time_Keep   On

[PARSER]
    Name        roa_hb
    Format      regex
    Regex       ^HB: (?<component>\w+) -> (?<status>\w+) @ (?<time>[^ ]+) \(interval: (?<interval>\d+)ms\)$
    Time_Key    time
    Time_Format %Y-%m-%dT%H:%M:%S.%L
```

### Prometheus Configuration

Create `~/.roa/config/prometheus/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

alerting:
  alertmanagers:
    - static_configs:
        - targets: []

rule_files:
  - /etc/prometheus/rules/*.yml

scrape_configs:
  # Prometheus self-monitoring
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
        labels:
          app: prometheus

  # Grafana
  - job_name: 'grafana'
    static_configs:
      - targets: ['grafana:3000']
        labels:
          app: grafana

  # Fluent Bit metrics
  - job_name: 'fluent-bit'
    static_configs:
      - targets: ['fluent-bit:2020']
        labels:
          app: fluent-bit

  # Alloy
  - job_name: 'alloy'
    static_configs:
      - targets: ['alloy:12345']
        labels:
          app: alloy

  # Loki
  - job_name: 'loki'
    static_configs:
      - targets: ['loki:3100']
        labels:
          app: loki

  # Tempo
  - job_name: 'tempo'
    static_configs:
      - targets: ['tempo:3200']
        labels:
          app: tempo

  # Pyroscope
  - job_name: 'pyroscope'
    static_configs:
      - targets: ['pyroscope:4040']
        labels:
          app: pyroscope

  # Beyla (when enabled)
  - job_name: 'beyla'
    static_configs:
      - targets: ['localhost:9400']
        labels:
          app: beyla

  # ROA Components (expose /metrics endpoints in your components)
  - job_name: 'roa-webthread'
    static_configs:
      - targets: ['host.docker.internal:9800']
        labels:
          app: roa
          component: webthread

  - job_name: 'roa-fti'
    static_configs:
      - targets: ['host.docker.internal:9801']
        labels:
          app: roa
          component: fti

  - job_name: 'roa-dimc'
    static_configs:
      - targets: ['host.docker.internal:9802']
        labels:
          app: roa
          component: dimc
```

### Loki Configuration

Create `~/.roa/config/loki/loki-config.yaml`:

```yaml
auth_enabled: false

server:
  http_listen_port: 3100
  grpc_listen_port: 9096
  log_level: info

common:
  instance_addr: 127.0.0.1
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

query_range:
  results_cache:
    cache:
      embedded_cache:
        enabled: true
        max_size_mb: 100

limits_config:
  metric_aggregation_enabled: true
  retention_period: 720h  # 30 days
  ingestion_rate_mb: 10
  ingestion_burst_size_mb: 20
  max_streams_per_user: 10000

schema_config:
  configs:
    - from: 2020-10-24
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

compactor:
  working_directory: /loki/compactor
  retention_enabled: true
  retention_delete_delay: 2h
  delete_request_store: filesystem

ruler:
  alertmanager_url: http://alertmanager:9093
  storage:
    type: local
    local:
      directory: /loki/rules
  rule_path: /loki/rules-temp
  enable_api: true

analytics:
  reporting_enabled: false
```

### Tempo Configuration

Create `~/.roa/config/tempo/tempo-config.yaml`:

```yaml
server:
  http_listen_port: 3200

distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317
        http:
          endpoint: 0.0.0.0:4318
    zipkin:
      endpoint: 0.0.0.0:9411
    jaeger:
      protocols:
        thrift_http:
          endpoint: 0.0.0.0:14268

ingester:
  trace_idle_period: 10s
  max_block_bytes: 1_000_000
  max_block_duration: 5m

compactor:
  compaction:
    compaction_window: 1h
    max_block_bytes: 100_000_000
    block_retention: 168h  # 7 days
    compacted_block_retention: 1h

storage:
  trace:
    backend: local
    local:
      path: /tmp/tempo/blocks
    wal:
      path: /tmp/tempo/wal
    pool:
      max_workers: 100
      queue_depth: 10000

querier:
  frontend_worker:
    frontend_address: localhost:9095

metrics_generator:
  registry:
    external_labels:
      source: tempo
      cluster: roa-local
  storage:
    path: /tmp/tempo/generator/wal
    remote_write:
      - url: http://prometheus:9090/api/v1/write
        send_exemplars: true

overrides:
  defaults:
    metrics_generator:
      processors: [service-graphs, span-metrics]
```

### Alloy Configuration

Create `~/.roa/config/alloy/config.alloy`:

```alloy
// =============================================================================
// LOGGING - Forward Alloy's own logs to Loki
// =============================================================================
logging {
    level = "info"
    write_to = [loki.process.alloy_logs.receiver]
}

loki.process "alloy_logs" {
    forward_to = [loki.write.loki.receiver]
    
    stage.labels {
        values = {
            level = "",
        }
    }
}

// =============================================================================
// TRACING - Forward Alloy's own traces to Tempo
// =============================================================================
tracing {
    sampling_fraction = 0.1  // 10% sampling in production
    write_to = [otelcol.exporter.otlp.tempo.input]
}

// =============================================================================
// OTEL RECEIVER - Receive telemetry from applications
// =============================================================================
otelcol.receiver.otlp "default" {
    grpc {
        endpoint = "0.0.0.0:4317"
    }
    http {
        endpoint = "0.0.0.0:4318"
    }
    output {
        metrics = [otelcol.processor.batch.default.input]
        logs    = [otelcol.processor.batch.default.input]
        traces  = [otelcol.processor.batch.default.input]
    }
}

// =============================================================================
// OTEL PROCESSOR - Batch for efficiency
// =============================================================================
otelcol.processor.batch "default" {
    output {
        metrics = [otelcol.exporter.prometheus.mimir.input]
        logs    = [otelcol.exporter.loki.loki.input]
        traces  = [otelcol.exporter.otlp.tempo.input]
    }
}

// =============================================================================
// EXPORTERS - Send to backends
// =============================================================================
otelcol.exporter.prometheus "mimir" {
    forward_to = [prometheus.remote_write.mimir.receiver]
}

otelcol.exporter.loki "loki" {
    forward_to = [loki.write.loki.receiver]
}

otelcol.exporter.otlp "tempo" {
    client {
        endpoint = coalesce(sys.env("TEMPO_HOST"), "tempo:4317")
        tls {
            insecure = true
        }
    }
}

// =============================================================================
// PROMETHEUS SCRAPING - Collect metrics from ROA components
// =============================================================================
prometheus.exporter.self "alloy" {}

prometheus.scrape "alloy_self" {
    targets    = prometheus.exporter.self.alloy.targets
    forward_to = [prometheus.remote_write.mimir.receiver]
}

prometheus.remote_write "mimir" {
    endpoint {
        url = string.format(
            "http://%s/api/v1/push",
            coalesce(sys.env("PROMETHEUS_HOST"), "prometheus:9090"),
        )
    }
}

// =============================================================================
// LOKI WRITER
// =============================================================================
loki.write "loki" {
    endpoint {
        url = string.format(
            "http://%s/loki/api/v1/push",
            coalesce(sys.env("LOKI_HOST"), "loki:3100"),
        )
    }
}

// =============================================================================
// PYROSCOPE - Profile collection
// =============================================================================
pyroscope.scrape "default" {
    targets = [
        {"__address__" = "localhost:12345", "service_name" = "alloy"},
    ]
    forward_to = [pyroscope.write.pyroscope.receiver]
}

pyroscope.write "pyroscope" {
    endpoint {
        url = string.format(
            "http://%s",
            coalesce(sys.env("PYROSCOPE_HOST"), "pyroscope:4040"),
        )
    }
}
```

### Grafana Datasources

Create `~/.roa/config/grafana/datasources.yaml`:

```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false

  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    editable: false
    jsonData:
      derivedFields:
        - datasourceUid: tempo
          matcherRegex: "trace_id=(\\w+)"
          name: TraceID
          url: "$${__value.raw}"

  - name: Tempo
    type: tempo
    access: proxy
    url: http://tempo:3200
    uid: tempo
    editable: false
    jsonData:
      tracesToLogsV2:
        datasourceUid: loki
        spanStartTimeShift: "-1h"
        spanEndTimeShift: "1h"
        tags: [{ key: "service.name", value: "component" }]
        filterByTraceID: true
        filterBySpanID: false
      tracesToMetrics:
        datasourceUid: prometheus
        spanStartTimeShift: "-1h"
        spanEndTimeShift: "1h"
        tags: [{ key: "service.name", value: "job" }]
      serviceMap:
        datasourceUid: prometheus
      nodeGraph:
        enabled: true
      lokiSearch:
        datasourceUid: loki

  - name: Pyroscope
    type: grafana-pyroscope-datasource
    access: proxy
    url: http://pyroscope:4040
    editable: false
```

---

## 🦊 Foxglove Integration

### Install ROS2 Foxglove Bridge

```bash
# Ubuntu/Debian
sudo apt install ros-humble-foxglove-bridge

# Or build from source
cd ~/ros2_ws/src
git clone https://github.com/foxglove/ros-foxglove-bridge.git
cd ~/ros2_ws
colcon build --packages-select foxglove_bridge
```

### Run Foxglove Bridge

```bash
# Basic launch
ros2 launch foxglove_bridge foxglove_bridge_launch.xml

# With custom port
ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765

# With authentication
ros2 launch foxglove_bridge foxglove_bridge_launch.xml \
  capabilities:="[clientPublish,parameters,parametersSubscribe,services,connectionGraph]"
```

### Connect Foxglove Studio

1. Open http://localhost:8080 (self-hosted Studio)
2. Click "Open connection"
3. Select "Foxglove WebSocket"
4. Enter: `ws://localhost:8765`
5. Click "Open"

### Record with rosbag2 + MCAP

```bash
# Record all topics to MCAP
ros2 bag record -s mcap -o ~/.roa/recordings/session_$(date +%Y%m%d_%H%M%S) -a

# Record specific ROA topics
ros2 bag record -s mcap -o ~/.roa/recordings/roa_session \
  /roa/heartbeat \
  /roa/status \
  /roa/fti/telemetry \
  /roa/dimc/commands \
  /tf /tf_static

# Snapshot mode (circular buffer)
ros2 bag record -s mcap --max-cache-size 100000000 \
  --storage-preset-profile resilient \
  -o ~/.roa/recordings/snapshot
```

### MCAP CLI Commands

```bash
# Install
pip install mcap-cli
# OR download binary
curl -L https://github.com/foxglove/mcap/releases/latest/download/mcap-linux-amd64 -o mcap
chmod +x mcap

# Info about MCAP file
mcap info recording.mcap

# List topics/channels
mcap list recording.mcap

# Convert ROS1 bag to MCAP
mcap convert input.bag output.mcap

# Merge multiple MCAP files
mcap merge file1.mcap file2.mcap -o merged.mcap

# Filter by topic
mcap filter recording.mcap -o filtered.mcap --include-topic "/roa/*"

# Extract to JSON
mcap cat recording.mcap --json > data.json

# Compress
mcap compress recording.mcap -o compressed.mcap

# Recover corrupted file
mcap recover corrupted.mcap -o recovered.mcap
```

### Foxglove SDK (Python)

```python
#!/usr/bin/env python3
"""ROA Foxglove SDK Example - Write custom MCAP files"""

from foxglove_sdk import Channel, McapWriter, Schema
from foxglove_sdk.schemas import Log, RawMessage
import time
import json

def write_roa_mcap():
    """Write ROA data to MCAP file using Foxglove SDK."""
    
    with McapWriter("roa_custom.mcap") as writer:
        # Define a channel for ROA heartbeat
        hb_schema = Schema(
            name="roa.Heartbeat",
            encoding="json",
            data=json.dumps({
                "type": "object",
                "properties": {
                    "component": {"type": "string"},
                    "status": {"type": "string"},
                    "timestamp": {"type": "number"},
                    "interval_ms": {"type": "integer"}
                }
            }).encode()
        )
        
        hb_channel = Channel(
            topic="/roa/heartbeat",
            message_encoding="json",
            schema=hb_schema
        )
        
        writer.add_channel(hb_channel)
        
        # Write heartbeat messages
        for i in range(100):
            msg = {
                "component": "webthread",
                "status": "alive",
                "timestamp": time.time(),
                "interval_ms": 1000
            }
            writer.write_message(
                channel=hb_channel,
                log_time=int(time.time() * 1e9),
                publish_time=int(time.time() * 1e9),
                data=json.dumps(msg).encode()
            )
            time.sleep(0.1)

if __name__ == "__main__":
    write_roa_mcap()
    print("Created roa_custom.mcap")
```

---

## 🧪 Load Testing with k6

### Install k6

```bash
# Ubuntu/Debian
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
  --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
  | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt update && sudo apt install k6

# Or via Docker
docker pull grafana/k6
```

### ROA Load Test Script

Create `~/.roa/tests/k6_roa_test.js`:

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

// Custom metrics
const roaErrors = new Counter('roa_errors');
const roaLatency = new Trend('roa_latency');
const roaSuccessRate = new Rate('roa_success_rate');

// Test configuration
export const options = {
    stages: [
        { duration: '30s', target: 10 },   // Ramp up to 10 users
        { duration: '1m', target: 10 },    // Stay at 10 users
        { duration: '30s', target: 50 },   // Ramp up to 50 users
        { duration: '2m', target: 50 },    // Stay at 50 users
        { duration: '30s', target: 0 },    // Ramp down
    ],
    thresholds: {
        http_req_duration: ['p(95)<500'],   // 95% of requests under 500ms
        roa_success_rate: ['rate>0.95'],    // 95% success rate
    },
};

const BASE_URL = __ENV.ROA_URL || 'http://localhost:9800';

export default function () {
    // Test Webthread status endpoint
    let statusRes = http.get(`${BASE_URL}/api/status`);
    
    check(statusRes, {
        'status is 200': (r) => r.status === 200,
        'response time < 200ms': (r) => r.timings.duration < 200,
    });
    
    if (statusRes.status === 200) {
        roaSuccessRate.add(1);
    } else {
        roaErrors.add(1);
        roaSuccessRate.add(0);
    }
    
    roaLatency.add(statusRes.timings.duration);
    
    // Test heartbeat endpoint
    let hbRes = http.get(`${BASE_URL}/api/heartbeat`);
    
    check(hbRes, {
        'heartbeat status is 200': (r) => r.status === 200,
        'heartbeat has data': (r) => r.json('components') !== undefined,
    });
    
    sleep(1);
}

export function handleSummary(data) {
    return {
        'stdout': textSummary(data, { indent: ' ', enableColors: true }),
        '~/.roa/results/k6_summary.json': JSON.stringify(data),
    };
}
```

### Run Load Test

```bash
# Basic run
k6 run ~/.roa/tests/k6_roa_test.js

# With Prometheus output
k6 run --out experimental-prometheus-rw \
  -e K6_PROMETHEUS_RW_SERVER_URL=http://localhost:9090/api/v1/write \
  ~/.roa/tests/k6_roa_test.js

# With custom ROA URL
k6 run -e ROA_URL=http://192.168.1.100:9800 ~/.roa/tests/k6_roa_test.js
```

---

## 🚀 Quick Start Commands

### Start Everything

```bash
# Create config directories
mkdir -p ~/.roa/{config/{fluent-bit,grafana/dashboards,prometheus,loki,tempo,alloy,mimir,foxglove},docker,recordings,logs,results}

# Start core stack
cd ~/.roa/docker
docker compose up -d

# Start with all profiles (including Beyla and Mimir)
docker compose --profile beyla --profile mimir up -d

# Check status
docker compose ps

# View logs
docker compose logs -f
```

### Start ROS2 Components

```bash
# Terminal 1: Start Foxglove Bridge
ros2 launch foxglove_bridge foxglove_bridge_launch.xml

# Terminal 2: Start recording
ros2 bag record -s mcap -o ~/.roa/recordings/session_$(date +%Y%m%d_%H%M%S) -a

# Terminal 3: Start ROA
roa start
```

### Access URLs

| Service | URL | Purpose |
|---------|-----|---------|
| Foxglove Studio | http://localhost:8080 | ROS2 visualization |
| Grafana | http://localhost:3000 | Dashboards (admin/roa_admin) |
| Prometheus | http://localhost:9090 | Metrics query |
| Loki | http://localhost:3100 | Log query |
| Tempo | http://localhost:3200 | Trace query |
| Pyroscope | http://localhost:4040 | Profiling |
| Alloy UI | http://localhost:12345 | Collector debug |
| Fluent Bit | http://localhost:2020 | Log collector metrics |

### Stop Everything

```bash
cd ~/.roa/docker
docker compose down

# Remove volumes too
docker compose down -v
```

---

## 📊 Sample Grafana Dashboard

Create `~/.roa/config/grafana/dashboards/roa_overview.json` with panels for:

1. **ROA Component Health** - Status of Webthread, FTI, DIMC, ROC, COMC
2. **Heartbeat Intervals** - Time-series of HB intervals per component
3. **Log Volume** - Logs per second by component
4. **Error Rate** - Errors per component
5. **Trace Duration** - P50/P95/P99 latencies
6. **CPU/Memory Usage** - Resource utilization

---

## 📝 Summary

This stack provides **complete observability** for ROA:

| Pillar | Tool | Storage |
|--------|------|---------|
| **ROS2 Data** | rosbag2 + MCAP | ~/.roa/recordings/ |
| **Visualization** | Foxglove Studio | - |
| **Logs** | Fluent Bit → Loki | Docker volume |
| **Metrics** | Prometheus/Mimir | Docker volume |
| **Traces** | Tempo | Docker volume |
| **Profiling** | Pyroscope | Docker volume |
| **Collection** | Alloy + Beyla | - |
| **Dashboards** | Grafana | Docker volume |
| **Testing** | k6 | ~/.roa/results/ |

**All tools are 100% open-source and self-hosted.** No paid services required.

---

## 🎉 Implementation Status: COMPLETE

### Infrastructure (Docker Compose)

All infrastructure files created at `roa_linux/config/observability/`:

| File | Purpose | Status |
|------|---------|--------|
| `docker-compose.yml` | 10-service observability stack | ✅ |
| `fluent-bit/fluent-bit.conf` | Log collection config | ✅ |
| `prometheus/prometheus.yml` | Metrics scraping | ✅ |
| `prometheus/rules/roa_alerts.yml` | Alert rules | ✅ |
| `loki/loki-config.yaml` | Log storage | ✅ |
| `tempo/tempo-config.yaml` | Trace storage | ✅ |
| `alloy/config.alloy` | OTel collection | ✅ |
| `mimir/mimir-config.yaml` | Long-term metrics | ✅ |
| `grafana/datasources.yaml` | Data sources | ✅ |
| `grafana/dashboards/` | Dashboard definitions | ✅ |
| `k6/roa_load_test.js` | Load testing script | ✅ |
| `roa-observability.sh` | Management script | ✅ |

### Instrumentation (Plugin Side)

Component instrumentation modules at `roa-core/lib/`:

| Component | File | Metrics Port | Health Port | Status |
|-----------|------|--------------|-------------|--------|
| **Shared** | `shared/observability/__init__.py` | - | - | ✅ |
| **Config** | `shared/observability/config.py` | - | - | ✅ |
| **Logger** | `shared/observability/structured_logger.py` | - | - | ✅ |
| **Metrics** | `shared/observability/metrics.py` | - | - | ✅ |
| **Tracing** | `shared/observability/tracing.py` | - | - | ✅ |
| **Health** | `shared/observability/health.py` | - | - | ✅ |
| **MCAP** | `shared/observability/mcap_recorder.py` | - | - | ✅ |
| **Core** | `shared/observability/observability.py` | - | - | ✅ |
| **Webthread** | `components/webthread/*/webthread_observability.py` | 9091 | 8081 | ✅ |
| **FTI** | `components/files-type-importer/*/fti_observability.py` | 9092 | 8082 | ✅ |
| **DIMC** | `components/dimensions-collector/*/dimc_observability.py` | 9093 | 8083 | ✅ |
| **ROC** | `components/robot-operator-controller/*/roc_observability.py` | 9094 | 8084 | ✅ |
| **COMC** | `components/communication-center/*/comc_observability.py` | 9095 | 8085 | ✅ |

### Quick Start

```bash
# 1. Install dependencies
pip install -r roa-core/lib/shared/observability/requirements.txt

# 2. Start infrastructure
cd config/observability
./roa-observability.sh start

# 3. Access dashboards
# Grafana:         http://localhost:3000 (admin/admin)
# Foxglove Studio: http://localhost:8765
# Prometheus:      http://localhost:9090

# 4. Use in your code
from shared.observability import ROAObservability

obs = ROAObservability("my_component", "1.0.0")
obs.start()

obs.logger.info("Hello from ROA!")
obs.metrics.request_total.labels(method="test", status="ok", source="api").inc()

with obs.tracer.start_span("operation"):
    do_work()

obs.stop()
```

### Tests

```bash
cd roa-core/lib/shared/observability
python3 tests.py
```

---

**Linux Side: ✅ COMPLETE**
**Windows Side: Pending (Python code is cross-platform)**
