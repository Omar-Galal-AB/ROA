# Metrics Server Quick Reference

## Start Metrics Server

```python
from observability import MetricsServer

server = MetricsServer(port=9090)
server.start()
```

## Stop Metrics Server

```python
server.stop()
```

## Context Manager

```python
with MetricsServer(port=9090) as server:
    # Server running
    pass
# Server automatically stopped
```

## Configuration

```python
server = MetricsServer(
    port=9090,              # Port (default: 9090)
    host="0.0.0.0",         # Host (default: all interfaces)
    enable_compression=True, # Gzip compression
    enable_cors=True,        # CORS headers
)
```

## Check Server Status

```python
server.is_running()  # Returns True/False
server.get_url()     # Returns "http://0.0.0.0:9090/metrics"
```

## Endpoints

- `GET /metrics` - Prometheus metrics
- `GET /health` - Health check (JSON)
- `GET /` - Alias for /metrics

## Test Endpoints

```bash
# Get metrics
curl http://localhost:9090/metrics

# Health check
curl http://localhost:9090/health | jq .

# With compression
curl -H "Accept-Encoding: gzip" http://localhost:9090/metrics | gunzip
```

## Prometheus Configuration

```yaml
scrape_configs:
  - job_name: 'roa-component'
    static_configs:
      - targets: ['localhost:9090']
    scrape_interval: 15s
```

## Port Assignments

| Component  | Metrics Port | Health Port |
|------------|--------------|-------------|
| Webthread  | 9090         | 10090       |
| DIMC       | 9091         | 10091       |
| ROC        | 9092         | 10092       |
| COMC       | 9093         | 10093       |
| FTI        | 9094         | 10094       |

## Common Issues

**Port in use:**
```python
server = MetricsServer(port=9091)  # Try different port
```

**Prometheus client missing:**
```bash
pip install prometheus-client
```

**Firewall blocking:**
```bash
# Allow port
sudo ufw allow 9090/tcp
```

## Integration with ROAObservability

```python
from observability import ROAObservability

obs = ROAObservability(component_name="webthread")
obs.start(start_metrics_server=True)
# Metrics server automatically started on port 9090
```
