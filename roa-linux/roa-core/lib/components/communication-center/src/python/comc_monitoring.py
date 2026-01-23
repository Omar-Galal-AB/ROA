"""
COMC Advanced Monitoring System
================================
Comprehensive monitoring for the Communication Center component.

This module addresses critical monitoring gaps:
1. Connection Health Monitoring - Track connections to all components
2. Message Flow Monitoring - Track message rates, latencies, losses
3. Robot Fleet Monitoring - Real-time fleet status tracking
4. Anomaly Detection - Detect unusual patterns
5. Performance Metrics - Response times, throughput
6. Alert System - Configurable alerts with escalation
7. Diagnostic Tools - Self-diagnosis and recovery hints

Integration with:
- HB Subsystem (via COMCHBAgent)
- Observability Stack (via ROAObservability)
- Health Monitor (basic metrics)
"""

import time
import threading
import logging
import json
import statistics
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from collections import deque
from datetime import datetime, timedelta


# =============================================================================
# ENUMS AND TYPES
# =============================================================================

class AlertSeverity(IntEnum):
    """Alert severity levels"""
    DEBUG = 0
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4


class ConnectionState(Enum):
    """Connection states for component links"""
    UNKNOWN = "unknown"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"
    FAILED = "failed"


class MonitoringCategory(Enum):
    """Categories of monitoring"""
    CONNECTION = "connection"
    MESSAGE_FLOW = "message_flow"
    FLEET = "fleet"
    PERFORMANCE = "performance"
    ANOMALY = "anomaly"
    SYSTEM = "system"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ConnectionHealth:
    """Health status of a connection to another component"""
    component_name: str
    state: ConnectionState = ConnectionState.UNKNOWN
    last_message_time: float = 0.0
    last_response_time_ms: float = 0.0
    message_count: int = 0
    error_count: int = 0
    consecutive_failures: int = 0
    latency_samples: deque = field(default_factory=lambda: deque(maxlen=100))
    
    @property
    def avg_latency_ms(self) -> float:
        if not self.latency_samples:
            return 0.0
        return statistics.mean(self.latency_samples)
    
    @property
    def latency_p95_ms(self) -> float:
        if len(self.latency_samples) < 2:
            return 0.0
        sorted_samples = sorted(self.latency_samples)
        idx = int(len(sorted_samples) * 0.95)
        return sorted_samples[min(idx, len(sorted_samples) - 1)]
    
    @property
    def error_rate(self) -> float:
        if self.message_count == 0:
            return 0.0
        return self.error_count / self.message_count


@dataclass
class MessageFlowStats:
    """Statistics for message flow on a topic/channel"""
    topic_name: str
    direction: str  # "inbound" or "outbound"
    message_count: int = 0
    bytes_total: int = 0
    last_message_time: float = 0.0
    rate_samples: deque = field(default_factory=lambda: deque(maxlen=60))  # Last minute
    latency_samples: deque = field(default_factory=lambda: deque(maxlen=100))
    error_count: int = 0
    dropped_count: int = 0
    
    @property
    def messages_per_second(self) -> float:
        if len(self.rate_samples) < 2:
            return 0.0
        time_span = self.rate_samples[-1][0] - self.rate_samples[0][0]
        if time_span <= 0:
            return 0.0
        msg_count = sum(s[1] for s in self.rate_samples)
        return msg_count / time_span
    
    @property
    def avg_latency_ms(self) -> float:
        if not self.latency_samples:
            return 0.0
        return statistics.mean(self.latency_samples)


@dataclass
class RobotMonitoringState:
    """Monitoring state for a single robot"""
    robot_id: str
    last_seen: float = 0.0
    message_count: int = 0
    position_updates: int = 0
    command_count: int = 0
    error_count: int = 0
    state: str = "unknown"
    health: str = "unknown"
    is_responsive: bool = True
    last_position: Optional[Tuple[float, float, float]] = None
    velocity: Optional[Tuple[float, float, float]] = None


@dataclass
class Alert:
    """Alert record"""
    id: str
    timestamp: float
    severity: AlertSeverity
    category: MonitoringCategory
    title: str
    message: str
    source: str
    data: Dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False
    resolved: bool = False
    resolution_time: Optional[float] = None


@dataclass
class AnomalyRecord:
    """Detected anomaly"""
    id: str
    timestamp: float
    anomaly_type: str
    description: str
    metric_name: str
    expected_value: float
    actual_value: float
    deviation_percent: float
    is_active: bool = True


# =============================================================================
# CONNECTION MONITOR
# =============================================================================

class ConnectionMonitor:
    """
    Monitors connections to all ROA components.
    
    Tracks:
    - DIMC connection (position data flow)
    - ROC connection (commands and status)
    - FTI connection (file type data)
    - Webthread connection (health reporting)
    - UE5 Bridge connection (simulation data)
    - HB Subsystem connection (heartbeats)
    """
    
    # Timeout thresholds (seconds)
    THRESHOLDS = {
        'DIMC': {'warning': 1.0, 'critical': 3.0},
        'ROC': {'warning': 2.0, 'critical': 5.0},
        'FTI': {'warning': 5.0, 'critical': 10.0},
        'Webthread': {'warning': 1.5, 'critical': 4.0},
        'UE5Bridge': {'warning': 2.0, 'critical': 5.0},
        'HBSubsystem': {'warning': 0.5, 'critical': 1.0},
    }
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("ConnectionMonitor")
        self.connections: Dict[str, ConnectionHealth] = {}
        self._lock = threading.RLock()
        
        # Initialize known connections
        for component in self.THRESHOLDS.keys():
            self.connections[component] = ConnectionHealth(component_name=component)
    
    def record_message(
        self,
        component: str,
        latency_ms: float = 0.0,
        success: bool = True,
        bytes_size: int = 0
    ):
        """Record a message exchange with a component."""
        with self._lock:
            if component not in self.connections:
                self.connections[component] = ConnectionHealth(component_name=component)
            
            conn = self.connections[component]
            conn.last_message_time = time.time()
            conn.message_count += 1
            
            if latency_ms > 0:
                conn.latency_samples.append(latency_ms)
                conn.last_response_time_ms = latency_ms
            
            if success:
                conn.consecutive_failures = 0
                if conn.state in [ConnectionState.DISCONNECTED, ConnectionState.FAILED]:
                    conn.state = ConnectionState.CONNECTED
                    self.logger.info(f"Connection to {component} restored")
            else:
                conn.error_count += 1
                conn.consecutive_failures += 1
    
    def check_connection_health(self, component: str) -> ConnectionState:
        """Check and update connection health for a component."""
        with self._lock:
            if component not in self.connections:
                return ConnectionState.UNKNOWN
            
            conn = self.connections[component]
            thresholds = self.THRESHOLDS.get(component, {'warning': 2.0, 'critical': 5.0})
            
            time_since_last = time.time() - conn.last_message_time
            
            if conn.last_message_time == 0:
                conn.state = ConnectionState.UNKNOWN
            elif time_since_last > thresholds['critical']:
                conn.state = ConnectionState.DISCONNECTED
            elif time_since_last > thresholds['warning']:
                conn.state = ConnectionState.DEGRADED
            elif conn.consecutive_failures >= 3:
                conn.state = ConnectionState.FAILED
            elif conn.error_rate > 0.1:  # >10% error rate
                conn.state = ConnectionState.DEGRADED
            else:
                conn.state = ConnectionState.CONNECTED
            
            return conn.state
    
    def get_all_health(self) -> Dict[str, Dict[str, Any]]:
        """Get health status of all connections."""
        with self._lock:
            result = {}
            for name, conn in self.connections.items():
                self.check_connection_health(name)
                result[name] = {
                    'state': conn.state.value,
                    'last_message_age_s': time.time() - conn.last_message_time if conn.last_message_time else -1,
                    'avg_latency_ms': round(conn.avg_latency_ms, 2),
                    'p95_latency_ms': round(conn.latency_p95_ms, 2),
                    'message_count': conn.message_count,
                    'error_rate': round(conn.error_rate * 100, 2),
                    'consecutive_failures': conn.consecutive_failures,
                }
            return result
    
    def is_healthy(self) -> bool:
        """Check if all critical connections are healthy."""
        critical_components = ['DIMC', 'Webthread', 'HBSubsystem']
        with self._lock:
            for comp in critical_components:
                state = self.check_connection_health(comp)
                if state in [ConnectionState.DISCONNECTED, ConnectionState.FAILED]:
                    return False
            return True


# =============================================================================
# MESSAGE FLOW MONITOR
# =============================================================================

class MessageFlowMonitor:
    """
    Monitors message flow rates and detects anomalies.
    
    Features:
    - Per-topic rate tracking
    - Latency percentiles
    - Drop detection
    - Rate anomaly detection
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("MessageFlowMonitor")
        self.topics: Dict[str, MessageFlowStats] = {}
        self._lock = threading.RLock()
        self._rate_baselines: Dict[str, float] = {}  # Expected rates
    
    def record_message(
        self,
        topic: str,
        direction: str,
        size_bytes: int = 0,
        latency_ms: float = 0.0,
        was_dropped: bool = False,
        had_error: bool = False
    ):
        """Record a message on a topic."""
        with self._lock:
            key = f"{topic}:{direction}"
            if key not in self.topics:
                self.topics[key] = MessageFlowStats(topic_name=topic, direction=direction)
            
            stats = self.topics[key]
            now = time.time()
            
            stats.message_count += 1
            stats.bytes_total += size_bytes
            stats.last_message_time = now
            stats.rate_samples.append((now, 1))
            
            if latency_ms > 0:
                stats.latency_samples.append(latency_ms)
            
            if was_dropped:
                stats.dropped_count += 1
            
            if had_error:
                stats.error_count += 1
    
    def set_rate_baseline(self, topic: str, direction: str, expected_rate_hz: float):
        """Set expected message rate for anomaly detection."""
        key = f"{topic}:{direction}"
        self._rate_baselines[key] = expected_rate_hz
    
    def check_rate_anomaly(self, topic: str, direction: str) -> Optional[float]:
        """
        Check if message rate is anomalous.
        
        Returns:
            Deviation percentage if anomaly detected, None otherwise
        """
        key = f"{topic}:{direction}"
        if key not in self._rate_baselines or key not in self.topics:
            return None
        
        expected = self._rate_baselines[key]
        actual = self.topics[key].messages_per_second
        
        if expected == 0:
            return None
        
        deviation = abs(actual - expected) / expected
        if deviation > 0.5:  # >50% deviation
            return deviation * 100
        
        return None
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get stats for all topics."""
        with self._lock:
            result = {}
            for key, stats in self.topics.items():
                result[key] = {
                    'topic': stats.topic_name,
                    'direction': stats.direction,
                    'message_count': stats.message_count,
                    'rate_hz': round(stats.messages_per_second, 2),
                    'bytes_total': stats.bytes_total,
                    'avg_latency_ms': round(stats.avg_latency_ms, 2),
                    'dropped': stats.dropped_count,
                    'errors': stats.error_count,
                    'last_message_age_s': round(time.time() - stats.last_message_time, 2) if stats.last_message_time else -1,
                }
            return result


# =============================================================================
# FLEET MONITOR
# =============================================================================

class FleetMonitor:
    """
    Monitors the robot fleet status.
    
    Features:
    - Per-robot health tracking
    - Fleet-wide statistics
    - Unresponsive robot detection
    - Formation tracking
    """
    
    # Robot is considered unresponsive after this time
    UNRESPONSIVE_THRESHOLD_S = 3.0
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("FleetMonitor")
        self.robots: Dict[str, RobotMonitoringState] = {}
        self._lock = threading.RLock()
        self._fleets: Dict[str, List[str]] = {}  # fleet_id -> [robot_ids]
    
    def register_robot(self, robot_id: str):
        """Register a robot for monitoring."""
        with self._lock:
            if robot_id not in self.robots:
                self.robots[robot_id] = RobotMonitoringState(robot_id=robot_id)
                self.logger.info(f"Robot registered for monitoring: {robot_id}")
    
    def unregister_robot(self, robot_id: str):
        """Unregister a robot from monitoring."""
        with self._lock:
            if robot_id in self.robots:
                del self.robots[robot_id]
                self.logger.info(f"Robot unregistered from monitoring: {robot_id}")
    
    def update_robot_position(
        self,
        robot_id: str,
        position: Tuple[float, float, float],
        velocity: Optional[Tuple[float, float, float]] = None
    ):
        """Update robot position."""
        with self._lock:
            if robot_id not in self.robots:
                self.register_robot(robot_id)
            
            robot = self.robots[robot_id]
            robot.last_seen = time.time()
            robot.last_position = position
            robot.position_updates += 1
            robot.is_responsive = True
            
            if velocity:
                robot.velocity = velocity
    
    def update_robot_state(self, robot_id: str, state: str, health: str):
        """Update robot state and health."""
        with self._lock:
            if robot_id not in self.robots:
                self.register_robot(robot_id)
            
            robot = self.robots[robot_id]
            robot.state = state
            robot.health = health
            robot.last_seen = time.time()
    
    def record_robot_message(self, robot_id: str, is_command: bool = False):
        """Record message from/to a robot."""
        with self._lock:
            if robot_id not in self.robots:
                self.register_robot(robot_id)
            
            robot = self.robots[robot_id]
            robot.message_count += 1
            robot.last_seen = time.time()
            robot.is_responsive = True
            
            if is_command:
                robot.command_count += 1
    
    def record_robot_error(self, robot_id: str):
        """Record an error for a robot."""
        with self._lock:
            if robot_id in self.robots:
                self.robots[robot_id].error_count += 1
    
    def check_responsiveness(self) -> List[str]:
        """Check for unresponsive robots."""
        unresponsive = []
        now = time.time()
        
        with self._lock:
            for robot_id, robot in self.robots.items():
                time_since_seen = now - robot.last_seen if robot.last_seen else float('inf')
                
                if time_since_seen > self.UNRESPONSIVE_THRESHOLD_S:
                    robot.is_responsive = False
                    unresponsive.append(robot_id)
                else:
                    robot.is_responsive = True
        
        return unresponsive
    
    def add_to_fleet(self, robot_id: str, fleet_id: str):
        """Add robot to a fleet."""
        with self._lock:
            if fleet_id not in self._fleets:
                self._fleets[fleet_id] = []
            if robot_id not in self._fleets[fleet_id]:
                self._fleets[fleet_id].append(robot_id)
    
    def remove_from_fleet(self, robot_id: str, fleet_id: str):
        """Remove robot from a fleet."""
        with self._lock:
            if fleet_id in self._fleets and robot_id in self._fleets[fleet_id]:
                self._fleets[fleet_id].remove(robot_id)
    
    def get_fleet_status(self) -> Dict[str, Any]:
        """Get comprehensive fleet status."""
        with self._lock:
            unresponsive = self.check_responsiveness()
            
            robot_states = {}
            for robot_id, robot in self.robots.items():
                robot_states[robot_id] = {
                    'state': robot.state,
                    'health': robot.health,
                    'responsive': robot.is_responsive,
                    'last_seen_age_s': round(time.time() - robot.last_seen, 2) if robot.last_seen else -1,
                    'message_count': robot.message_count,
                    'error_count': robot.error_count,
                    'position': robot.last_position,
                }
            
            return {
                'total_robots': len(self.robots),
                'responsive': len(self.robots) - len(unresponsive),
                'unresponsive': len(unresponsive),
                'unresponsive_ids': unresponsive,
                'fleets': {fid: len(rids) for fid, rids in self._fleets.items()},
                'robots': robot_states,
            }


# =============================================================================
# ANOMALY DETECTOR
# =============================================================================

class AnomalyDetector:
    """
    Detects anomalies in COMC operation.
    
    Monitors for:
    - Message rate spikes/drops
    - Latency spikes
    - Connection failures
    - Robot behavior anomalies
    - Resource exhaustion
    """
    
    def __init__(
        self,
        connection_monitor: ConnectionMonitor,
        message_monitor: MessageFlowMonitor,
        fleet_monitor: FleetMonitor,
        logger: Optional[logging.Logger] = None
    ):
        self.logger = logger or logging.getLogger("AnomalyDetector")
        self.connection_monitor = connection_monitor
        self.message_monitor = message_monitor
        self.fleet_monitor = fleet_monitor
        
        self.anomalies: Dict[str, AnomalyRecord] = {}
        self._lock = threading.RLock()
        self._anomaly_counter = 0
        
        # Thresholds
        self.latency_spike_threshold_ms = 100.0
        self.rate_deviation_threshold = 0.5  # 50%
    
    def check_all_anomalies(self) -> List[AnomalyRecord]:
        """Run all anomaly checks and return new anomalies."""
        new_anomalies = []
        
        # Check connection anomalies
        for name, health in self.connection_monitor.connections.items():
            if health.consecutive_failures >= 3:
                anomaly = self._create_anomaly(
                    anomaly_type="connection_failures",
                    description=f"Component {name} has {health.consecutive_failures} consecutive failures",
                    metric_name=f"connection.{name}.failures",
                    expected_value=0,
                    actual_value=health.consecutive_failures
                )
                new_anomalies.append(anomaly)
            
            if health.avg_latency_ms > self.latency_spike_threshold_ms:
                anomaly = self._create_anomaly(
                    anomaly_type="latency_spike",
                    description=f"Component {name} avg latency is {health.avg_latency_ms:.1f}ms",
                    metric_name=f"connection.{name}.latency_ms",
                    expected_value=self.latency_spike_threshold_ms,
                    actual_value=health.avg_latency_ms
                )
                new_anomalies.append(anomaly)
        
        # Check message flow anomalies
        for key, stats in self.message_monitor.topics.items():
            deviation = self.message_monitor.check_rate_anomaly(stats.topic_name, stats.direction)
            if deviation:
                anomaly = self._create_anomaly(
                    anomaly_type="rate_deviation",
                    description=f"Topic {stats.topic_name} rate deviation: {deviation:.1f}%",
                    metric_name=f"topic.{key}.rate",
                    expected_value=self.message_monitor._rate_baselines.get(key, 0),
                    actual_value=stats.messages_per_second
                )
                new_anomalies.append(anomaly)
        
        # Check fleet anomalies
        unresponsive = self.fleet_monitor.check_responsiveness()
        if unresponsive:
            anomaly = self._create_anomaly(
                anomaly_type="unresponsive_robots",
                description=f"{len(unresponsive)} robots unresponsive: {unresponsive}",
                metric_name="fleet.unresponsive_count",
                expected_value=0,
                actual_value=len(unresponsive)
            )
            new_anomalies.append(anomaly)
        
        return new_anomalies
    
    def _create_anomaly(
        self,
        anomaly_type: str,
        description: str,
        metric_name: str,
        expected_value: float,
        actual_value: float
    ) -> AnomalyRecord:
        """Create a new anomaly record."""
        with self._lock:
            self._anomaly_counter += 1
            anomaly_id = f"anomaly_{self._anomaly_counter}_{int(time.time())}"
            
            deviation = 0.0
            if expected_value != 0:
                deviation = abs(actual_value - expected_value) / expected_value * 100
            
            anomaly = AnomalyRecord(
                id=anomaly_id,
                timestamp=time.time(),
                anomaly_type=anomaly_type,
                description=description,
                metric_name=metric_name,
                expected_value=expected_value,
                actual_value=actual_value,
                deviation_percent=deviation
            )
            
            self.anomalies[anomaly_id] = anomaly
            self.logger.warning(f"Anomaly detected: {description}")
            
            return anomaly
    
    def resolve_anomaly(self, anomaly_id: str):
        """Mark an anomaly as resolved."""
        with self._lock:
            if anomaly_id in self.anomalies:
                self.anomalies[anomaly_id].is_active = False
    
    def get_active_anomalies(self) -> List[AnomalyRecord]:
        """Get all active anomalies."""
        with self._lock:
            return [a for a in self.anomalies.values() if a.is_active]


# =============================================================================
# ALERT MANAGER
# =============================================================================

class AlertManager:
    """
    Manages alerts with escalation and acknowledgment.
    
    Features:
    - Configurable alert thresholds
    - Alert deduplication
    - Escalation rules
    - Alert history
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("AlertManager")
        self.alerts: Dict[str, Alert] = {}
        self.alert_history: deque = deque(maxlen=1000)
        self._lock = threading.RLock()
        self._alert_counter = 0
        self._callbacks: List[Callable[[Alert], None]] = []
        
        # Deduplication window (seconds)
        self.dedup_window = 60.0
        self._recent_alerts: Dict[str, float] = {}  # fingerprint -> timestamp
    
    def register_callback(self, callback: Callable[[Alert], None]):
        """Register callback for new alerts."""
        self._callbacks.append(callback)
    
    def create_alert(
        self,
        severity: AlertSeverity,
        category: MonitoringCategory,
        title: str,
        message: str,
        source: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Optional[Alert]:
        """Create a new alert (with deduplication)."""
        # Check deduplication
        fingerprint = f"{category.value}:{title}:{source}"
        now = time.time()
        
        with self._lock:
            if fingerprint in self._recent_alerts:
                if now - self._recent_alerts[fingerprint] < self.dedup_window:
                    return None  # Duplicate alert
            
            self._alert_counter += 1
            alert_id = f"alert_{self._alert_counter}_{int(now)}"
            
            alert = Alert(
                id=alert_id,
                timestamp=now,
                severity=severity,
                category=category,
                title=title,
                message=message,
                source=source,
                data=data or {}
            )
            
            self.alerts[alert_id] = alert
            self.alert_history.append(alert)
            self._recent_alerts[fingerprint] = now
            
            # Log alert
            log_method = {
                AlertSeverity.DEBUG: self.logger.debug,
                AlertSeverity.INFO: self.logger.info,
                AlertSeverity.WARNING: self.logger.warning,
                AlertSeverity.ERROR: self.logger.error,
                AlertSeverity.CRITICAL: self.logger.critical,
            }.get(severity, self.logger.warning)
            
            log_method(f"ALERT [{severity.name}] {title}: {message}")
            
            # Notify callbacks
            for callback in self._callbacks:
                try:
                    callback(alert)
                except Exception as e:
                    self.logger.error(f"Alert callback error: {e}")
            
            return alert
    
    def acknowledge_alert(self, alert_id: str):
        """Acknowledge an alert."""
        with self._lock:
            if alert_id in self.alerts:
                self.alerts[alert_id].acknowledged = True
    
    def resolve_alert(self, alert_id: str):
        """Resolve an alert."""
        with self._lock:
            if alert_id in self.alerts:
                self.alerts[alert_id].resolved = True
                self.alerts[alert_id].resolution_time = time.time()
    
    def get_active_alerts(self, severity: Optional[AlertSeverity] = None) -> List[Alert]:
        """Get active (unresolved) alerts."""
        with self._lock:
            alerts = [a for a in self.alerts.values() if not a.resolved]
            if severity:
                alerts = [a for a in alerts if a.severity >= severity]
            return sorted(alerts, key=lambda a: a.severity, reverse=True)
    
    def get_alert_summary(self) -> Dict[str, int]:
        """Get count of alerts by severity."""
        with self._lock:
            summary = {s.name: 0 for s in AlertSeverity}
            for alert in self.alerts.values():
                if not alert.resolved:
                    summary[alert.severity.name] += 1
            return summary


# =============================================================================
# DIAGNOSTIC TOOLS
# =============================================================================

class DiagnosticTools:
    """
    Self-diagnosis and recovery hints.
    
    Features:
    - Connection diagnostics
    - Message flow diagnostics
    - Performance diagnostics
    - Recovery suggestions
    """
    
    def __init__(
        self,
        connection_monitor: ConnectionMonitor,
        message_monitor: MessageFlowMonitor,
        fleet_monitor: FleetMonitor,
        logger: Optional[logging.Logger] = None
    ):
        self.logger = logger or logging.getLogger("DiagnosticTools")
        self.connection_monitor = connection_monitor
        self.message_monitor = message_monitor
        self.fleet_monitor = fleet_monitor
    
    def run_full_diagnostic(self) -> Dict[str, Any]:
        """Run complete diagnostic check."""
        return {
            'timestamp': time.time(),
            'connection_health': self._diagnose_connections(),
            'message_flow': self._diagnose_message_flow(),
            'fleet_status': self._diagnose_fleet(),
            'overall_health': self._assess_overall_health(),
            'recommendations': self._generate_recommendations(),
        }
    
    def _diagnose_connections(self) -> Dict[str, Any]:
        """Diagnose connection health."""
        health = self.connection_monitor.get_all_health()
        issues = []
        
        for name, status in health.items():
            if status['state'] in ['disconnected', 'failed']:
                issues.append({
                    'component': name,
                    'issue': 'Connection lost',
                    'severity': 'critical',
                    'suggestion': f"Check if {name} service is running. Verify network connectivity."
                })
            elif status['state'] == 'degraded':
                issues.append({
                    'component': name,
                    'issue': 'Connection degraded',
                    'severity': 'warning',
                    'suggestion': f"High latency or errors on {name}. Check for network congestion."
                })
        
        return {
            'status': health,
            'issues': issues,
            'healthy': len(issues) == 0
        }
    
    def _diagnose_message_flow(self) -> Dict[str, Any]:
        """Diagnose message flow."""
        stats = self.message_monitor.get_all_stats()
        issues = []
        
        for key, topic_stats in stats.items():
            if topic_stats['dropped'] > 0:
                issues.append({
                    'topic': topic_stats['topic'],
                    'issue': f"Dropped {topic_stats['dropped']} messages",
                    'severity': 'warning',
                    'suggestion': "Increase queue size or reduce message rate"
                })
            
            if topic_stats['avg_latency_ms'] > 50:
                issues.append({
                    'topic': topic_stats['topic'],
                    'issue': f"High latency ({topic_stats['avg_latency_ms']:.1f}ms)",
                    'severity': 'warning',
                    'suggestion': "Optimize message processing or check system load"
                })
        
        return {
            'stats': stats,
            'issues': issues,
            'healthy': len(issues) == 0
        }
    
    def _diagnose_fleet(self) -> Dict[str, Any]:
        """Diagnose fleet status."""
        status = self.fleet_monitor.get_fleet_status()
        issues = []
        
        if status['unresponsive'] > 0:
            issues.append({
                'issue': f"{status['unresponsive']} robots unresponsive",
                'robot_ids': status['unresponsive_ids'],
                'severity': 'critical',
                'suggestion': "Check robot connectivity and power status"
            })
        
        for robot_id, robot_status in status['robots'].items():
            if robot_status['health'] == 'error':
                issues.append({
                    'robot': robot_id,
                    'issue': 'Robot in error state',
                    'severity': 'error',
                    'suggestion': f"Check robot {robot_id} logs for details"
                })
        
        return {
            'status': status,
            'issues': issues,
            'healthy': len(issues) == 0
        }
    
    def _assess_overall_health(self) -> str:
        """Assess overall COMC health."""
        conn_healthy = self.connection_monitor.is_healthy()
        unresponsive = self.fleet_monitor.check_responsiveness()
        
        if not conn_healthy:
            return "CRITICAL"
        elif len(unresponsive) > 0:
            return "DEGRADED"
        else:
            return "HEALTHY"
    
    def _generate_recommendations(self) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []
        
        # Check connections
        health = self.connection_monitor.get_all_health()
        for name, status in health.items():
            if status['state'] == 'disconnected':
                recommendations.append(f"Restart connection to {name}")
            elif status['p95_latency_ms'] > 100:
                recommendations.append(f"Investigate high latency on {name} connection")
        
        # Check fleet
        unresponsive = self.fleet_monitor.check_responsiveness()
        if unresponsive:
            recommendations.append(f"Investigate unresponsive robots: {unresponsive}")
        
        # Check message flow
        for key, stats in self.message_monitor.topics.items():
            if stats.dropped_count > 10:
                recommendations.append(f"Consider increasing buffer size for {stats.topic_name}")
        
        return recommendations


# =============================================================================
# MAIN MONITORING SYSTEM
# =============================================================================

class COMCMonitoringSystem:
    """
    Unified COMC Monitoring System.
    
    Integrates all monitoring components and provides a single interface
    for comprehensive COMC health monitoring.
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("COMCMonitoring")
        
        # Initialize components
        self.connection_monitor = ConnectionMonitor(logger)
        self.message_monitor = MessageFlowMonitor(logger)
        self.fleet_monitor = FleetMonitor(logger)
        self.anomaly_detector = AnomalyDetector(
            self.connection_monitor,
            self.message_monitor,
            self.fleet_monitor,
            logger
        )
        self.alert_manager = AlertManager(logger)
        self.diagnostics = DiagnosticTools(
            self.connection_monitor,
            self.message_monitor,
            self.fleet_monitor,
            logger
        )
        
        # Background monitoring thread
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_interval = 1.0  # seconds
        
        self.logger.info("COMC Monitoring System initialized")
    
    def start(self):
        """Start background monitoring."""
        if self._running:
            return
        
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.name = "COMCMonitoring"
        self._monitor_thread.start()
        self.logger.info("COMC Monitoring System started")
    
    def stop(self):
        """Stop background monitoring."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2.0)
        self.logger.info("COMC Monitoring System stopped")
    
    def _monitor_loop(self):
        """Background monitoring loop."""
        while self._running:
            try:
                # Check for anomalies
                anomalies = self.anomaly_detector.check_all_anomalies()
                
                # Generate alerts for new anomalies
                for anomaly in anomalies:
                    severity = AlertSeverity.WARNING
                    if anomaly.deviation_percent > 100:
                        severity = AlertSeverity.ERROR
                    if anomaly.anomaly_type in ['connection_failures', 'unresponsive_robots']:
                        severity = AlertSeverity.CRITICAL
                    
                    self.alert_manager.create_alert(
                        severity=severity,
                        category=MonitoringCategory.ANOMALY,
                        title=anomaly.anomaly_type,
                        message=anomaly.description,
                        source="anomaly_detector",
                        data={'anomaly_id': anomaly.id}
                    )
                
            except Exception as e:
                self.logger.error(f"Monitor loop error: {e}")
            
            time.sleep(self._monitor_interval)
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive monitoring status."""
        return {
            'timestamp': time.time(),
            'overall_health': self.diagnostics._assess_overall_health(),
            'connections': self.connection_monitor.get_all_health(),
            'message_flow': self.message_monitor.get_all_stats(),
            'fleet': self.fleet_monitor.get_fleet_status(),
            'active_anomalies': len(self.anomaly_detector.get_active_anomalies()),
            'alerts': self.alert_manager.get_alert_summary(),
        }
    
    def get_full_diagnostic(self) -> Dict[str, Any]:
        """Get full diagnostic report."""
        return self.diagnostics.run_full_diagnostic()
    
    # === Convenience methods for recording events ===
    
    def record_component_message(
        self,
        component: str,
        latency_ms: float = 0.0,
        success: bool = True
    ):
        """Record message exchange with a component."""
        self.connection_monitor.record_message(component, latency_ms, success)
    
    def record_topic_message(
        self,
        topic: str,
        direction: str,
        size_bytes: int = 0,
        latency_ms: float = 0.0
    ):
        """Record message on a topic."""
        self.message_monitor.record_message(topic, direction, size_bytes, latency_ms)
    
    def record_robot_activity(
        self,
        robot_id: str,
        position: Optional[Tuple[float, float, float]] = None,
        state: Optional[str] = None,
        health: Optional[str] = None
    ):
        """Record robot activity."""
        if position:
            self.fleet_monitor.update_robot_position(robot_id, position)
        if state or health:
            self.fleet_monitor.update_robot_state(
                robot_id,
                state or "unknown",
                health or "unknown"
            )
