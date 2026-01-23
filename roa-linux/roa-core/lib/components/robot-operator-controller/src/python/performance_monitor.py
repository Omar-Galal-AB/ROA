"""
Performance Monitoring Module

Monitors ROC performance metrics including latency, CPU, memory usage.
Provides warnings when thresholds are exceeded.

Author: ROA Development Team
Date: 2025-11-16
"""

from typing import Dict, Any, List, Optional
import time
import psutil
import threading
from collections import deque


class PerformanceMetrics:
    """Container for performance metrics"""
    
    def __init__(self):
        self.timestamp = time.time()
        self.control_loop_latency = 0.0  # ms
        self.cpu_usage = 0.0  # %
        self.memory_usage = 0.0  # MB
        self.num_robots = 0
        self.commands_per_second = 0.0


class PerformanceMonitor:
    """
    Performance monitoring system
    
    Features:
    - Control loop latency tracking (<20ms target)
    - CPU usage monitoring (<80% warning)
    - Memory usage monitoring (<4GB target)
    - Command throughput tracking
    - Warning generation
    """
    
    def __init__(
        self,
        latency_target_ms: float = 20.0,
        cpu_warning_threshold: float = 80.0,
        memory_warning_mb: float = 4000.0,
        history_size: int = 1000
    ):
        """
        Initialize performance monitor
        
        Args:
            latency_target_ms: Target control loop latency in ms
            cpu_warning_threshold: CPU usage warning threshold (%)
            memory_warning_mb: Memory usage warning threshold (MB)
            history_size: Number of measurements to keep
        """
        self.latency_target_ms = latency_target_ms
        self.cpu_warning_threshold = cpu_warning_threshold
        self.memory_warning_mb = memory_warning_mb
        
        # History
        self.latency_history = deque(maxlen=history_size)
        self.cpu_history = deque(maxlen=history_size)
        self.memory_history = deque(maxlen=history_size)
        
        # Current metrics
        self.current_metrics = PerformanceMetrics()
        
        # Control loop timing
        self.loop_start_time = None
        self.command_count = 0
        self.last_command_time = time.time()
        
        # Process monitoring
        self.process = psutil.Process()
        
        # Warnings
        self.warnings: List[str] = []
        self.warning_lock = threading.Lock()
        
        # Statistics
        self.total_warnings = 0
        self.latency_violations = 0
        self.cpu_violations = 0
        self.memory_violations = 0
    
    def start_control_loop(self):
        """Mark start of control loop iteration"""
        self.loop_start_time = time.time()
    
    def end_control_loop(self):
        """Mark end of control loop iteration and record latency"""
        if self.loop_start_time is None:
            return
        
        # Calculate latency
        latency_s = time.time() - self.loop_start_time
        latency_ms = latency_s * 1000.0
        
        # Record latency
        self.latency_history.append(latency_ms)
        self.current_metrics.control_loop_latency = latency_ms
        
        # Check for violation
        if latency_ms > self.latency_target_ms:
            self.latency_violations += 1
            self._add_warning(
                f"Control loop latency {latency_ms:.2f}ms exceeds target {self.latency_target_ms}ms"
            )
        
        self.loop_start_time = None
    
    def record_command(self):
        """Record command execution"""
        self.command_count += 1
        current_time = time.time()
        
        # Calculate commands per second
        time_diff = current_time - self.last_command_time
        if time_diff >= 1.0:
            self.current_metrics.commands_per_second = self.command_count / time_diff
            self.command_count = 0
            self.last_command_time = current_time
    
    def update_system_metrics(self):
        """Update CPU and memory metrics"""
        # CPU usage
        cpu_percent = self.process.cpu_percent()
        self.cpu_history.append(cpu_percent)
        self.current_metrics.cpu_usage = cpu_percent
        
        # Memory usage
        memory_info = self.process.memory_info()
        memory_mb = memory_info.rss / (1024 * 1024)  # Convert to MB
        self.memory_history.append(memory_mb)
        self.current_metrics.memory_usage = memory_mb
        
        # Check for violations
        if cpu_percent > self.cpu_warning_threshold:
            self.cpu_violations += 1
            self._add_warning(
                f"CPU usage {cpu_percent:.1f}% exceeds threshold {self.cpu_warning_threshold}%"
            )
        
        if memory_mb > self.memory_warning_mb:
            self.memory_violations += 1
            self._add_warning(
                f"Memory usage {memory_mb:.1f}MB exceeds threshold {self.memory_warning_mb}MB"
            )
        
        # Update timestamp
        self.current_metrics.timestamp = time.time()
    
    def set_robot_count(self, count: int):
        """Update number of active robots"""
        self.current_metrics.num_robots = count
    
    def get_current_metrics(self) -> PerformanceMetrics:
        """Get current performance metrics"""
        return self.current_metrics
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get performance statistics"""
        stats = {
            'current': {
                'latency_ms': self.current_metrics.control_loop_latency,
                'cpu_percent': self.current_metrics.cpu_usage,
                'memory_mb': self.current_metrics.memory_usage,
                'commands_per_sec': self.current_metrics.commands_per_second,
                'num_robots': self.current_metrics.num_robots
            },
            'averages': {
                'latency_ms': sum(self.latency_history) / len(self.latency_history) if self.latency_history else 0,
                'cpu_percent': sum(self.cpu_history) / len(self.cpu_history) if self.cpu_history else 0,
                'memory_mb': sum(self.memory_history) / len(self.memory_history) if self.memory_history else 0
            },
            'violations': {
                'latency': self.latency_violations,
                'cpu': self.cpu_violations,
                'memory': self.memory_violations,
                'total': self.latency_violations + self.cpu_violations + self.memory_violations
            },
            'thresholds': {
                'latency_target_ms': self.latency_target_ms,
                'cpu_warning_percent': self.cpu_warning_threshold,
                'memory_warning_mb': self.memory_warning_mb
            }
        }
        
        # Add peak values
        if self.latency_history:
            stats['peaks'] = {
                'latency_ms': max(self.latency_history),
                'cpu_percent': max(self.cpu_history),
                'memory_mb': max(self.memory_history)
            }
        
        return stats
    
    def get_warnings(self, clear: bool = True) -> List[str]:
        """
        Get accumulated warnings
        
        Args:
            clear: Clear warnings after reading
            
        Returns:
            List of warning messages
        """
        with self.warning_lock:
            warnings = self.warnings.copy()
            if clear:
                self.warnings.clear()
            return warnings
    
    def _add_warning(self, message: str):
        """Add warning message"""
        with self.warning_lock:
            # Avoid duplicate warnings
            if message not in self.warnings:
                self.warnings.append(message)
                self.total_warnings += 1
    
    def reset_statistics(self):
        """Reset all statistics"""
        self.latency_violations = 0
        self.cpu_violations = 0
        self.memory_violations = 0
        self.total_warnings = 0
        
        with self.warning_lock:
            self.warnings.clear()
    
    def is_healthy(self) -> bool:
        """
        Check if system is operating within healthy parameters
        
        Returns:
            True if all metrics are within thresholds
        """
        return (
            self.current_metrics.control_loop_latency <= self.latency_target_ms and
            self.current_metrics.cpu_usage <= self.cpu_warning_threshold and
            self.current_metrics.memory_usage <= self.memory_warning_mb
        )
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get overall health status"""
        return {
            'healthy': self.is_healthy(),
            'latency_ok': self.current_metrics.control_loop_latency <= self.latency_target_ms,
            'cpu_ok': self.current_metrics.cpu_usage <= self.cpu_warning_threshold,
            'memory_ok': self.current_metrics.memory_usage <= self.memory_warning_mb,
            'active_warnings': len(self.warnings),
            'total_violations': (
                self.latency_violations +
                self.cpu_violations +
                self.memory_violations
            )
        }
