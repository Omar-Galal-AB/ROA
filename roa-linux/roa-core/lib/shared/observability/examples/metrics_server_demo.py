#!/usr/bin/env python3
"""
ROA Metrics Server Demo
========================

Demonstrates the HTTP metrics server with various features:
- /metrics endpoint for Prometheus scraping
- /health endpoint for health checks
- Gzip compression
- CORS support
- Custom metrics
- Multiple endpoints

Usage:
    python3 metrics_server_demo.py
    
    Then in another terminal:
    curl http://localhost:9090/metrics
    curl http://localhost:9090/health
    curl -H "Accept-Encoding: gzip" http://localhost:9090/metrics | gunzip
"""

import time
import random
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from observability import (
    ROAMetrics,
    MetricsServer,
)


def main():
    print("=" * 70)
    print("ROA Metrics Server Demo")
    print("=" * 70)
    
    # Create metrics instance
    print("\n1. Creating metrics...")
    metrics = ROAMetrics(component_name="demo")
    
    # Register some custom metrics
    print("2. Registering custom metrics...")
    demo_counter = metrics.register_counter(
        "demo_requests_total",
        "Total demo requests",
        ["endpoint", "status"],
    )
    
    demo_latency = metrics.register_histogram(
        "demo_request_latency_seconds",
        "Demo request latency",
        ["endpoint"],
        buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
    )
    
    active_connections = metrics.register_gauge(
        "demo_active_connections",
        "Active connections",
    )
    
    # Start metrics server
    print(f"3. Starting metrics server on port 9090...")
    server = MetricsServer(
        port=9090,
        host="0.0.0.0",
        enable_compression=True,
        enable_cors=True,
    )
    
    try:
        server.start()
        print(f"✅ Server started: {server.get_url()}")
        print(f"   Status: {server}")
    except RuntimeError as e:
        print(f"❌ Failed to start server: {e}")
        print("\nTip: Try a different port if 9090 is in use:")
        print("     server = MetricsServer(port=9091)")
        return
    
    # Display endpoints
    print("\n" + "=" * 70)
    print("Available Endpoints:")
    print("=" * 70)
    print(f"📊 Metrics:  http://localhost:9090/metrics")
    print(f"❤️  Health:   http://localhost:9090/health")
    print()
    print("Try these commands in another terminal:")
    print("  curl http://localhost:9090/metrics")
    print("  curl http://localhost:9090/health")
    print("  curl -H 'Accept-Encoding: gzip' http://localhost:9090/metrics | gunzip")
    print()
    
    # Simulate some activity
    print("=" * 70)
    print("Simulating Activity (Ctrl+C to stop)")
    print("=" * 70)
    
    endpoints = ["/api/status", "/api/robots", "/api/telemetry", "/api/health"]
    statuses = ["success", "error"]
    
    try:
        iteration = 0
        while True:
            iteration += 1
            
            # Simulate requests
            endpoint = random.choice(endpoints)
            status = random.choice(statuses) if random.random() > 0.9 else "success"
            latency = random.uniform(0.01, 0.5) if status == "success" else random.uniform(1.0, 3.0)
            
            demo_counter.labels(endpoint=endpoint, status=status).inc()
            demo_latency.labels(endpoint=endpoint).observe(latency)
            
            # Update active connections
            active_connections.set(random.randint(5, 50))
            
            # Update heartbeat
            metrics.heartbeat_total.labels(component="demo", target="system").inc()
            
            # Log activity
            if iteration % 10 == 0:
                print(f"  [{iteration:4d}] Simulated {endpoint} ({status}) - {latency:.3f}s")
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping server...")
        server.stop()
        print("✅ Server stopped")
        print("\nFinal metrics:")
        print(f"  - Total iterations: {iteration}")
        print(f"  - Server was running: {server.is_running()}")


if __name__ == "__main__":
    main()
