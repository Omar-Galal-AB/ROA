#!/usr/bin/env python3
"""
Complete Metrics Server Integration Example
============================================

Demonstrates full integration of metrics server with:
- Component-specific metrics
- Multiple metric types (counter, gauge, histogram)
- Prometheus scraping
- Health checks
- Graceful shutdown
"""

import time
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from observability import (
    ROAObservability,
    ObservabilityConfig,
    MetricsConfig,
    HealthConfig,
)


class RoboticsComponent:
    """Example robotics component with observability"""
    
    def __init__(self, component_name: str, metrics_port: int):
        self.name = component_name
        
        # Configure observability
        config = ObservabilityConfig(
            metrics=MetricsConfig(
                enabled=True,
                port=metrics_port,
                host="0.0.0.0",
            ),
            health=HealthConfig(
                enabled=True,
                port=metrics_port + 1000,  # e.g., 10090 for metrics on 9090
            ),
        )
        
        # Initialize observability
        self.obs = ROAObservability(
            component_name=component_name,
            config=config,
            service_version="1.0.0",
        )
        
        # Register component-specific metrics
        self._register_metrics()
        
    def _register_metrics(self):
        """Register component-specific metrics"""
        metrics = self.obs.metrics
        
        # Operations counter
        self.operations = metrics.register_counter(
            f"{self.name}_operations_total",
            f"{self.name} operations performed",
            ["operation_type", "status"],
        )
        
        # Processing time histogram
        self.processing_time = metrics.register_histogram(
            f"{self.name}_processing_seconds",
            f"{self.name} processing duration",
            ["operation_type"],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0],
        )
        
        # Active tasks gauge
        self.active_tasks = metrics.register_gauge(
            f"{self.name}_active_tasks",
            f"Number of active {self.name} tasks",
        )
        
        # Queue depth gauge
        self.queue_depth = metrics.register_gauge(
            f"{self.name}_queue_depth",
            f"{self.name} task queue depth",
        )
    
    def start(self):
        """Start component and observability services"""
        print(f"[{self.name}] Starting observability...")
        self.obs.start(
            start_metrics_server=True,
            start_health_server=True,
            start_resource_collector=True,
        )
        print(f"[{self.name}] ✅ Metrics server: http://localhost:{self.obs.config.metrics.port}/metrics")
        print(f"[{self.name}] ✅ Health server:  http://localhost:{self.obs.config.health.port}/health")
    
    def stop(self):
        """Stop component gracefully"""
        print(f"[{self.name}] Stopping...")
        self.obs.stop()
        print(f"[{self.name}] ✅ Stopped")
    
    def simulate_work(self):
        """Simulate component doing work"""
        import random
        
        # Simulate active tasks
        self.active_tasks.set(random.randint(1, 10))
        self.queue_depth.set(random.randint(0, 50))
        
        # Simulate operation
        operation_type = random.choice(["process", "transform", "validate"])
        start_time = time.perf_counter()
        
        # Simulate work with random duration
        work_duration = random.uniform(0.01, 0.5)
        time.sleep(work_duration)
        
        # Record metrics
        duration = time.perf_counter() - start_time
        status = "success" if random.random() > 0.1 else "error"
        
        self.operations.labels(operation_type=operation_type, status=status).inc()
        self.processing_time.labels(operation_type=operation_type).observe(duration)
        
        # Record heartbeat
        self.obs.metrics.heartbeat_total.labels(
            component=self.name,
            target="system",
        ).inc()


def main():
    """Run multi-component observability demo"""
    print("=" * 80)
    print("ROA Multi-Component Metrics Server Demo")
    print("=" * 80)
    print()
    
    # Create multiple components
    components = [
        RoboticsComponent("webthread", 9090),
        RoboticsComponent("dimc", 9091),
        RoboticsComponent("roc", 9092),
    ]
    
    # Start all components
    print("Starting components...")
    print("-" * 80)
    for component in components:
        component.start()
    
    print()
    print("=" * 80)
    print("All components started!")
    print("=" * 80)
    print()
    print("Prometheus scrape configuration:")
    print("-" * 80)
    print("scrape_configs:")
    for component in components:
        print(f"  - job_name: 'roa-{component.name}'")
        print(f"    static_configs:")
        print(f"      - targets: ['localhost:{component.obs.config.metrics.port}']")
    print()
    print("=" * 80)
    print("Available endpoints:")
    print("=" * 80)
    for component in components:
        port = component.obs.config.metrics.port
        health_port = component.obs.config.health.port
        print(f"  {component.name:12s}  http://localhost:{port}/metrics")
        print(f"  {component.name:12s}  http://localhost:{health_port}/health")
    print()
    print("Try these commands:")
    print("  curl http://localhost:9090/metrics | grep roa_")
    print("  curl http://localhost:9091/metrics | grep roa_")
    print("  curl http://localhost:9092/metrics | grep roa_")
    print()
    print("=" * 80)
    print("Simulating work... (Ctrl+C to stop)")
    print("=" * 80)
    
    # Set up signal handler for graceful shutdown
    def signal_handler(sig, frame):
        print("\n\n🛑 Shutting down...")
        for component in components:
            component.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Simulate work
    iteration = 0
    try:
        while True:
            iteration += 1
            
            # Each component does work
            for component in components:
                component.simulate_work()
            
            if iteration % 10 == 0:
                print(f"  [{iteration:4d}] All components active")
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down...")
        for component in components:
            component.stop()


if __name__ == "__main__":
    main()
