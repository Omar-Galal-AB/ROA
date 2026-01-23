# HTTP Metrics Server - Prometheus Endpoint

## Overview

The HTTP metrics server provides a `/metrics` endpoint for Prometheus scraping, enabling complete observability of ROA components.

## Features

✅ **Prometheus-compatible `/metrics` endpoint**  
✅ **Automatic gzip compression** for large payloads  
✅ **CORS support** for web dashboards  
✅ **Health check endpoint** at `/health`  
✅ **Thread-safe operation** with graceful shutdown  
✅ **Custom registry support** for multi-tenant scenarios  
✅ **Error handling** with proper HTTP status codes  

---

## Quick Start

### Basic Usage

```python
from observability import ROAMetrics, MetricsServer

# Create metrics
metrics = ROAMetrics(component_name="webthread")

# Start server
server = MetricsServer(port=9090)
server.start()

# Server is now running at http://0.0.0.0:9090/metrics
# Prometheus can scrape this endpoint
```

### Context Manager

```python
with MetricsServer(port=9090) as server:
    # Server runs in background
    metrics.heartbeat_total.labels(component="demo").inc()
    time.sleep(60)
# Server automatically stopped
```

---

## Endpoints

### GET /metrics

Returns Prometheus metrics in text exposition format.

**Response Headers:**
- `Content-Type: text/plain; version=0.0.4; charset=utf-8`
- `Content-Encoding: gzip` (if compression enabled and supported)
- `Cache-Control: no-cache, no-store, must-revalidate`
- `Access-Control-Allow-Origin: *` (if CORS enabled)

**Example:**
```bash
curl http://localhost:9090/metrics
```

**Response:**
```
# HELP roa_heartbeat_total Heartbeat messages sent
# TYPE roa_heartbeat_total counter
roa_heartbeat_total{component="webthread",target="ros2"} 142.0
roa_heartbeat_total{component="webthread",target="ue5"} 138.0

# HELP roa_component_health Component health status
# TYPE roa_component_health gauge
roa_component_health{component="webthread"} 2.0
roa_component_health{component="dimc"} 2.0
```

### GET /health

Health check endpoint returning JSON status.

**Response:**
```json
{
  "status": "healthy",
  "prometheus_available": true,
  "registry": "default"
}
```

### GET / 

Alias for `/metrics` (convenience).

---

## Configuration

### Server Options

```python
server = MetricsServer(
    port=9090,              # Port to listen on
    host="0.0.0.0",         # Host to bind (0.0.0.0 = all interfaces)
    registry=None,          # Custom registry (optional)
    enable_compression=True, # Gzip compression
    enable_cors=True,        # CORS headers
)
```

### Port Selection

**Default Ports:**
- Webthread: `9090`
- DIMC: `9091`
- ROC: `9092`
- COMC: `9093`
- FTI: `9094`

**Custom Port:**
```python
server = MetricsServer(port=9095)
```

### Custom Registry

For multi-tenant or isolated metric collection:

```python
from prometheus_client import CollectorRegistry

registry = CollectorRegistry()
metrics = ROAMetrics("component", registry=registry)
server = MetricsServer(port=9090, registry=registry)
```

---

## Prometheus Configuration

### scrape_configs Example

```yaml
scrape_configs:
  # ROA Webthread
  - job_name: 'roa-webthread'
    static_configs:
      - targets: ['localhost:9090']
    scrape_interval: 15s
    scrape_timeout: 10s
    metrics_path: /metrics
    
  # ROA DIMC
  - job_name: 'roa-dimc'
    static_configs:
      - targets: ['localhost:9091']
    scrape_interval: 15s
    
  # ROA ROC
  - job_name: 'roa-roc'
    static_configs:
      - targets: ['localhost:9092']
    scrape_interval: 15s
    
  # ROA COMC
  - job_name: 'roa-comc'
    static_configs:
      - targets: ['localhost:9093']
    scrape_interval: 15s
    
  # ROA FTI
  - job_name: 'roa-fti'
    static_configs:
      - targets: ['localhost:9094']
    scrape_interval: 15s
```

### Docker Compose Integration

```yaml
services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
    depends_on:
      - webthread
      - dimc
      - roc
      - comc
      - fti
```

---

## Advanced Features

### Gzip Compression

Automatically compresses responses > 1KB when client sends `Accept-Encoding: gzip`:

```bash
# Request with compression
curl -H "Accept-Encoding: gzip" http://localhost:9090/metrics | gunzip

# Check compression ratio
UNCOMPRESSED=$(curl -s http://localhost:9090/metrics | wc -c)
COMPRESSED=$(curl -s -H "Accept-Encoding: gzip" http://localhost:9090/metrics | wc -c)
echo "Compression ratio: $(($UNCOMPRESSED / $COMPRESSED))x"
```

**Typical savings:** 5-10x reduction in payload size

### CORS Support

Enables access from web dashboards (Grafana, custom UIs):

```javascript
// JavaScript fetch from browser
fetch('http://localhost:9090/metrics')
  .then(response => response.text())
  .then(data => console.log(data));
```

CORS headers:
- `Access-Control-Allow-Origin: *`
- `Access-Control-Allow-Methods: GET, HEAD, OPTIONS`
- `Access-Control-Allow-Headers: Content-Type, Authorization`

**Disable for security:**
```python
server = MetricsServer(port=9090, enable_cors=False)
```

### Query Parameters

Filter metrics by name (Prometheus 2.x+):

```bash
curl "http://localhost:9090/metrics?name[]=roa_heartbeat_total"
```

---

## Integration with ROAObservability

The metrics server is automatically started when using `ROAObservability`:

```python
from observability import ROAObservability

obs = ROAObservability(
    component_name="webthread",
    config=config,
)

# Start all observability services
obs.start(
    start_metrics_server=True,  # ← Starts HTTP metrics server
    start_health_server=True,
    start_resource_collector=True,
)

# Server is now running on config.metrics.port (default: 9090)
```

**Configuration:**
```python
from observability import ObservabilityConfig, MetricsConfig

config = ObservabilityConfig(
    metrics=MetricsConfig(
        enabled=True,
        port=9090,
        host="0.0.0.0",
    ),
)
```

---

## Error Handling

### Port Already in Use

```python
try:
    server = MetricsServer(port=9090)
    server.start()
except RuntimeError as e:
    print(f"Failed to start: {e}")
    # Try alternative port
    server = MetricsServer(port=9091)
    server.start()
```

**Error message:**
```
Port 9090 is already in use. Is another metrics server running?
Try a different port or stop the conflicting process.
```

### Prometheus Client Not Installed

If `prometheus_client` is not installed:

**GET /metrics response:**
```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{
  "error": "Service Unavailable",
  "code": 503,
  "details": "prometheus_client not installed"
}
```

**Fix:**
```bash
pip install prometheus-client
```

---

## Testing

### Manual Testing

```bash
# Test metrics endpoint
curl http://localhost:9090/metrics

# Test health endpoint
curl http://localhost:9090/health | jq .

# Test compression
curl -H "Accept-Encoding: gzip" http://localhost:9090/metrics | gunzip

# Test CORS
curl -I http://localhost:9090/metrics | grep -i access-control
```

### Run Demo

```bash
cd /home/myws/roa/roa_linux/roa-core/lib/shared/observability/examples
python3 metrics_server_demo.py
```

**Output:**
```
======================================================================
ROA Metrics Server Demo
======================================================================

1. Creating metrics...
2. Registering custom metrics...
3. Starting metrics server on port 9090...
✅ Server started: http://0.0.0.0:9090/metrics
   Status: <MetricsServer 0.0.0.0:9090 (running)>

======================================================================
Available Endpoints:
======================================================================
📊 Metrics:  http://localhost:9090/metrics
❤️  Health:   http://localhost:9090/health

Try these commands in another terminal:
  curl http://localhost:9090/metrics
  curl http://localhost:9090/health
```

### Automated Tests

```bash
cd /home/myws/roa/roa_linux/roa-core/lib/shared/observability/examples
./test_metrics_endpoint.sh
```

---

## Performance

### Benchmarks

**Metrics generation:** ~5-10ms for 100 metrics  
**HTTP response time:** ~1-2ms (uncompressed)  
**Compression time:** +2-5ms (gzip enabled)  
**Memory overhead:** ~50-100MB per 10,000 time series  

### Optimization Tips

1. **Use appropriate scrape intervals:**
   - High-frequency metrics (CPU, memory): 5-15s
   - Application metrics: 15-30s
   - Business metrics: 60s+

2. **Limit cardinality:**
   ```python
   # ❌ High cardinality (millions of combinations)
   counter.labels(user_id=user_id, session_id=session_id).inc()
   
   # ✅ Low cardinality
   counter.labels(endpoint=endpoint, status=status).inc()
   ```

3. **Enable compression for large metric sets:**
   ```python
   server = MetricsServer(enable_compression=True)  # 5-10x reduction
   ```

4. **Use histogram buckets wisely:**
   ```python
   # ❌ Too many buckets (high overhead)
   buckets=[0.001, 0.002, 0.003, ..., 10.0]  # 100+ buckets
   
   # ✅ Appropriate buckets
   buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0]  # 6 buckets
   ```

---

## Security Considerations

### Production Deployment

1. **Bind to localhost** if Prometheus is on same host:
   ```python
   server = MetricsServer(host="127.0.0.1", port=9090)
   ```

2. **Disable CORS** in production:
   ```python
   server = MetricsServer(enable_cors=False)
   ```

3. **Use firewall rules** to restrict access:
   ```bash
   # Only allow from Prometheus server
   iptables -A INPUT -p tcp --dport 9090 -s 10.0.0.5 -j ACCEPT
   iptables -A INPUT -p tcp --dport 9090 -j DROP
   ```

4. **Add authentication** (requires reverse proxy):
   ```nginx
   location /metrics {
       auth_basic "Metrics";
       auth_basic_user_file /etc/nginx/.htpasswd;
       proxy_pass http://localhost:9090/metrics;
   }
   ```

---

## Troubleshooting

### Server Won't Start

**Symptom:** `RuntimeError: Port 9090 is already in use`

**Solution:**
```bash
# Check what's using the port
lsof -i :9090
netstat -tulpn | grep 9090

# Use different port
server = MetricsServer(port=9091)
```

### No Metrics Returned

**Symptom:** `/metrics` returns empty or error

**Checks:**
1. Is `prometheus_client` installed?
   ```bash
   pip list | grep prometheus
   ```

2. Are metrics being recorded?
   ```python
   metrics.heartbeat_total.labels(component="test").inc()
   ```

3. Is custom registry being used correctly?
   ```python
   registry = CollectorRegistry()
   metrics = ROAMetrics("test", registry=registry)
   server = MetricsServer(registry=registry)  # Must use same registry
   ```

### High Memory Usage

**Cause:** Too many unique label combinations (high cardinality)

**Solution:**
```python
# Limit label values
valid_endpoints = ['/api/status', '/api/health', '/api/robots']
endpoint = endpoint if endpoint in valid_endpoints else 'other'
counter.labels(endpoint=endpoint).inc()
```

---

## See Also

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/naming/)
- [ROA Observability Stack](../../../docs/ROA_OBSERVABILITY_STACK.md)
- [Metrics Library Reference](./metrics.py)
