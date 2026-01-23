"""
hb_receiver.py
ROA - Robot Operations & Automation
Heartbeat Receiver - Multi-port UDP receiver with per-component threads

The HB Receiver listens for heartbeats on dedicated ports (one per component).
Each port has its own receiver thread for isolation. Integrates with
overload protection to prevent flooding.

Key Features:
- Multi-port architecture (6 dedicated ports)
- Per-component receiver threads
- Startup handshake with agents
- Overload protection integration
- Sequence gap detection
- Metric collection
"""

import logging
import queue
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .hb_types import (
    AlertLevel,
    ComponentHealthStatus,
    ComponentID,
    ComponentState,
    FailureEvent,
    FailureType,
    HBPorts,
    HBTiming,
    HealthLevel,
    HeartbeatPacket,
    StartupAck,
    StartupPing,
    bitmap_to_activities,
    calculate_sequence_gap,
    get_timestamp_us,
    is_sequence_gap,
)
from .overload_protection import OverloadProtector, OverloadProtectorFactory


@dataclass
class ReceiverStats:
    """Statistics for a single receiver"""

    component_name: str
    port: int
    packets_received: int = 0
    packets_invalid: int = 0
    packets_dropped: int = 0  # Due to overload
    sequence_gaps: int = 0
    checksum_errors: int = 0
    last_packet_time: float = 0.0
    handshakes_completed: int = 0
    started_at: float = field(default_factory=time.time)


class ComponentReceiver:
    """
    Receiver thread for a single component.

    Each component has its own dedicated receiver on a specific port.
    This provides isolation - one component's flood can't affect others.
    """

    def __init__(
        self,
        component_name: str,
        port: int,
        on_heartbeat: Callable[[HeartbeatPacket], None],
        on_failure: Callable[[FailureEvent], None],
        bind_address: str = "127.0.0.1",
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize ComponentReceiver.

        Args:
            component_name: Name of the component this receives for
            port: UDP port to listen on
            on_heartbeat: Callback when valid heartbeat received
            on_failure: Callback when failure detected
            bind_address: Address to bind to
            logger: Optional logger
        """
        self.component_name = component_name
        self.component_id = ComponentID.BY_NAME.get(component_name, 0)
        self.port = port
        self.bind_address = bind_address
        self.on_heartbeat = on_heartbeat
        self.on_failure = on_failure

        self.logger = logger or logging.getLogger(f"HBReceiver.{component_name}")

        # State
        self._running = False
        self._socket: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Tracking
        self._last_sequence: Optional[int] = None
        self._last_heartbeat_time: float = 0.0
        self._agent_address: Optional[tuple] = None

        # Stats
        self.stats = ReceiverStats(component_name, port)

        # Overload protection
        self.protector = OverloadProtectorFactory.create(component_name)
        self.protector.on_rejection(self._on_overload_rejection)

    def start(self) -> bool:
        """
        Start the receiver.

        Returns:
            True if started successfully
        """
        if self._running:
            return True

        try:
            # Create and bind socket
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.settimeout(0.1)  # 100ms timeout for clean shutdown
            self._socket.bind((self.bind_address, self.port))

            # Start receiver thread
            self._running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._receive_loop, daemon=True)
            self._thread.name = f"HBRecv-{self.component_name}"
            self._thread.start()

            self.logger.info(f"Started receiver for {self.component_name} on port {self.port}")
            return True

        except socket.error as e:
            self.logger.error(f"Failed to start receiver: {e}")
            return False

    def stop(self):
        """Stop the receiver"""
        if not self._running:
            return

        self.logger.info(f"Stopping receiver for {self.component_name}")

        self._running = False
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

        if self._socket:
            try:
                self._socket.close()
            except:
                pass
            self._socket = None

    def is_running(self) -> bool:
        """Check if receiver is running"""
        return self._running

    def get_last_heartbeat_time(self) -> float:
        """Get time of last received heartbeat"""
        return self._last_heartbeat_time

    def _receive_loop(self):
        """Main receive loop"""
        self.logger.debug("Receive loop started")

        while self._running and not self._stop_event.is_set():
            try:
                # Receive packet
                try:
                    data, addr = self._socket.recvfrom(128)
                except socket.timeout:
                    continue

                # Process packet
                self._process_packet(data, addr)

            except Exception as e:
                if self._running:
                    self.logger.error(f"Error in receive loop: {e}")

        self.logger.debug("Receive loop ended")

    def _process_packet(self, data: bytes, addr: tuple):
        """
        Process received packet.

        Args:
            data: Raw packet data
            addr: Sender address
        """
        # Check for startup ping first
        if len(data) == StartupPing.PACKET_SIZE:
            ping = StartupPing.from_bytes(data)
            if ping and ping.component_id == self.component_id:
                self._handle_startup_ping(ping, addr)
                return

        # Must be heartbeat packet
        if len(data) != HeartbeatPacket.PACKET_SIZE:
            self.stats.packets_invalid += 1
            return

        # Apply overload protection
        if not self.protector.try_acquire():
            self.stats.packets_dropped += 1
            return

        start_time = time.time()

        try:
            # Parse packet
            packet = HeartbeatPacket.from_bytes(data)

            if packet is None:
                self.stats.packets_invalid += 1
                self.stats.checksum_errors += 1
                self._report_failure(FailureType.CHECKSUM_ERROR, "Invalid checksum")
                return

            # Verify component ID
            if packet.component_id != self.component_id:
                self.stats.packets_invalid += 1
                return

            # Check for sequence gaps
            if self._last_sequence is not None:
                if is_sequence_gap(self._last_sequence, packet.sequence):
                    gap = calculate_sequence_gap(self._last_sequence, packet.sequence)
                    self.stats.sequence_gaps += 1
                    self._report_failure(
                        FailureType.SEQUENCE_GAP,
                        f"Missed {gap} heartbeats (seq {self._last_sequence} -> {packet.sequence})",
                    )

            self._last_sequence = packet.sequence

            # Update tracking
            self.stats.packets_received += 1
            self._last_heartbeat_time = time.time()
            self.stats.last_packet_time = self._last_heartbeat_time
            self._agent_address = addr

            # Invoke callback
            self.on_heartbeat(packet)

        finally:
            elapsed_ms = (time.time() - start_time) * 1000
            self.protector.release(elapsed_ms)

    def _handle_startup_ping(self, ping: StartupPing, addr: tuple):
        """Handle startup ping from agent"""
        self.logger.info(f"Received startup ping from {addr}")

        # Send acknowledgment
        ack = StartupAck(
            component_id=self.component_id,
            timestamp=get_timestamp_us(),
            port_assigned=self.port,
        )

        try:
            self._socket.sendto(ack.to_bytes(), addr)
            self._agent_address = addr
            self.stats.handshakes_completed += 1
            self.logger.info(f"Handshake completed with {self.component_name} agent at {addr}")
        except socket.error as e:
            self.logger.error(f"Failed to send startup ack: {e}")

    def _on_overload_rejection(self, reason: str):
        """Handle overload rejection"""
        self._report_failure(
            FailureType.RATE_ANOMALY,
            f"Overload protection triggered: {reason}",
            severity=HealthLevel.DEGRADED,
        )

    def _report_failure(
        self,
        failure_type: FailureType,
        details: str,
        severity: HealthLevel = HealthLevel.ACCEPTABLE,
    ):
        """Report a failure event"""
        event = FailureEvent(
            failure_type=failure_type,
            component_name=self.component_name,
            timestamp=time.time(),
            severity=severity,
            details=details,
        )

        try:
            self.on_failure(event)
        except Exception as e:
            self.logger.error(f"Error in failure callback: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get receiver statistics"""
        return {
            "component_name": self.stats.component_name,
            "port": self.stats.port,
            "running": self._running,
            "packets_received": self.stats.packets_received,
            "packets_invalid": self.stats.packets_invalid,
            "packets_dropped": self.stats.packets_dropped,
            "sequence_gaps": self.stats.sequence_gaps,
            "checksum_errors": self.stats.checksum_errors,
            "last_packet_time": self.stats.last_packet_time,
            "handshakes_completed": self.stats.handshakes_completed,
            "uptime_seconds": time.time() - self.stats.started_at,
            "overload_metrics": self.protector.get_metrics(),
        }


class HBReceiver:
    """
    Multi-port Heartbeat Receiver.

    Manages multiple ComponentReceivers, one per component.
    This is the main entry point for receiving heartbeats.

    Usage:
        receiver = HBReceiver()
        receiver.on_heartbeat(my_hb_handler)
        receiver.on_failure(my_failure_handler)
        receiver.start()

        # Later
        receiver.stop()
    """

    def __init__(self, bind_address: str = "127.0.0.1", logger: Optional[logging.Logger] = None):
        """
        Initialize HBReceiver.

        Args:
            bind_address: Address to bind receivers to
            logger: Optional logger
        """
        self.bind_address = bind_address
        self.logger = logger or logging.getLogger("HBReceiver")

        # Receivers (one per component)
        self._receivers: Dict[str, ComponentReceiver] = {}

        # Callbacks
        self._heartbeat_callbacks: List[Callable[[str, HeartbeatPacket], None]] = []
        self._failure_callbacks: List[Callable[[FailureEvent], None]] = []

        # Heartbeat queue for aggregator
        self.heartbeat_queue: queue.Queue = queue.Queue(maxsize=1000)

        # Failure queue for aggregator
        self.failure_queue: queue.Queue = queue.Queue(maxsize=100)

        # Timeout detector thread
        self._timeout_thread: Optional[threading.Thread] = None
        self._running = False
        self._stop_event = threading.Event()

        # Track last heartbeat times for timeout detection
        self._last_hb_times: Dict[str, float] = {}
        self._alert_levels: Dict[str, AlertLevel] = {}

        self.logger.info("HBReceiver initialized")

    def start(self) -> bool:
        """
        Start all component receivers.

        Returns:
            True if all started successfully
        """
        self.logger.info("Starting HB Receiver...")

        success = True

        # Create and start receiver for each component
        for component_name, port in HBPorts.BY_COMPONENT.items():
            receiver = ComponentReceiver(
                component_name=component_name,
                port=port,
                on_heartbeat=lambda pkt, cn=component_name: self._on_component_heartbeat(cn, pkt),
                on_failure=self._on_component_failure,
                bind_address=self.bind_address,
                logger=logging.getLogger(f"HBReceiver.{component_name}"),
            )

            if receiver.start():
                self._receivers[component_name] = receiver
                self._last_hb_times[component_name] = 0.0
                self._alert_levels[component_name] = AlertLevel.GREEN
            else:
                self.logger.error(f"Failed to start receiver for {component_name}")
                success = False

        # Start timeout detector
        self._running = True
        self._stop_event.clear()
        self._timeout_thread = threading.Thread(target=self._timeout_loop, daemon=True)
        self._timeout_thread.name = "HBTimeoutDetector"
        self._timeout_thread.start()

        if success:
            self.logger.info(f"HB Receiver started with {len(self._receivers)} component receivers")

        return success

    def stop(self):
        """Stop all receivers"""
        self.logger.info("Stopping HB Receiver...")

        self._running = False
        self._stop_event.set()

        # Stop timeout thread
        if self._timeout_thread and self._timeout_thread.is_alive():
            self._timeout_thread.join(timeout=1.0)

        # Stop all component receivers
        for receiver in self._receivers.values():
            receiver.stop()

        self._receivers.clear()
        self.logger.info("HB Receiver stopped")

    def is_running(self) -> bool:
        """Check if receiver is running"""
        return self._running

    # =========================================================================
    # CALLBACKS
    # =========================================================================

    def on_heartbeat(self, callback: Callable[[str, HeartbeatPacket], None]):
        """
        Register callback for heartbeat reception.

        Args:
            callback: Function(component_name, packet)
        """
        self._heartbeat_callbacks.append(callback)

    def on_failure(self, callback: Callable[[FailureEvent], None]):
        """
        Register callback for failure events.

        Args:
            callback: Function(failure_event)
        """
        self._failure_callbacks.append(callback)

    # =========================================================================
    # INTERNAL HANDLERS
    # =========================================================================

    def _on_component_heartbeat(self, component_name: str, packet: HeartbeatPacket):
        """Handle heartbeat from component receiver"""
        # Update last HB time
        self._last_hb_times[component_name] = time.time()

        # Reset alert level on successful HB
        if self._alert_levels.get(component_name) != AlertLevel.GREEN:
            self.logger.info(f"{component_name} heartbeat restored")
        self._alert_levels[component_name] = AlertLevel.GREEN

        # Queue for aggregator
        try:
            self.heartbeat_queue.put_nowait((component_name, packet))
        except queue.Full:
            self.logger.warning("Heartbeat queue full, dropping oldest")
            try:
                self.heartbeat_queue.get_nowait()
                self.heartbeat_queue.put_nowait((component_name, packet))
            except:
                pass

        # Invoke callbacks
        for callback in self._heartbeat_callbacks:
            try:
                callback(component_name, packet)
            except Exception as e:
                self.logger.error(f"Error in heartbeat callback: {e}")

    def _on_component_failure(self, event: FailureEvent):
        """Handle failure from component receiver"""
        # Queue for aggregator
        try:
            self.failure_queue.put_nowait(event)
        except queue.Full:
            self.logger.warning("Failure queue full, dropping oldest")
            try:
                self.failure_queue.get_nowait()
                self.failure_queue.put_nowait(event)
            except:
                pass

        # Invoke callbacks
        for callback in self._failure_callbacks:
            try:
                callback(event)
            except Exception as e:
                self.logger.error(f"Error in failure callback: {e}")

    def _timeout_loop(self):
        """Check for heartbeat timeouts"""
        self.logger.debug("Timeout detector started")
        check_interval = HBTiming.TARGET_INTERVAL_MS / 1000.0

        while self._running and not self._stop_event.is_set():
            try:
                now = time.time()

                for component_name, last_time in self._last_hb_times.items():
                    if last_time == 0:
                        continue  # Never received HB yet

                    elapsed_ms = (now - last_time) * 1000

                    # Determine alert level based on elapsed time
                    old_alert = self._alert_levels.get(component_name, AlertLevel.GREEN)
                    new_alert = self._calculate_alert_level(elapsed_ms)

                    if new_alert != old_alert:
                        self._alert_levels[component_name] = new_alert
                        self._on_alert_change(component_name, old_alert, new_alert, elapsed_ms)

            except Exception as e:
                self.logger.error(f"Error in timeout loop: {e}")

            self._stop_event.wait(check_interval)

        self.logger.debug("Timeout detector ended")

    def _calculate_alert_level(self, elapsed_ms: float) -> AlertLevel:
        """Calculate alert level based on time since last heartbeat"""
        if elapsed_ms < HBTiming.YELLOW_THRESHOLD_MS:
            return AlertLevel.GREEN
        elif elapsed_ms < HBTiming.ORANGE_THRESHOLD_MS:
            return AlertLevel.YELLOW
        elif elapsed_ms < HBTiming.RED_THRESHOLD_MS:
            return AlertLevel.ORANGE
        elif elapsed_ms < HBTiming.RESET_THRESHOLD_MS:
            return AlertLevel.RED
        else:
            return AlertLevel.BLACK

    def _on_alert_change(
        self,
        component_name: str,
        old_alert: AlertLevel,
        new_alert: AlertLevel,
        elapsed_ms: float,
    ):
        """Handle alert level change"""
        self.logger.warning(
            f"{component_name} alert: {old_alert.name} -> {new_alert.name} "
            f"(no HB for {elapsed_ms:.0f}ms)"
        )

        # Determine failure type and severity
        if new_alert == AlertLevel.BLACK:
            failure_type = FailureType.HEARTBEAT_TIMEOUT
            severity = HealthLevel.FAILED
        elif new_alert == AlertLevel.RED:
            failure_type = FailureType.HEARTBEAT_TIMEOUT
            severity = HealthLevel.CRITICAL
        elif new_alert == AlertLevel.ORANGE:
            failure_type = FailureType.HEARTBEAT_TIMEOUT
            severity = HealthLevel.DEGRADED
        else:
            failure_type = FailureType.HEARTBEAT_TIMEOUT
            severity = HealthLevel.ACCEPTABLE

        # Report failure
        event = FailureEvent(
            failure_type=failure_type,
            component_name=component_name,
            timestamp=time.time(),
            severity=severity,
            details=f"No heartbeat for {elapsed_ms:.0f}ms (alert: {new_alert.name})",
        )

        self._on_component_failure(event)

    # =========================================================================
    # STATUS & METRICS
    # =========================================================================

    def get_alert_level(self, component_name: str) -> AlertLevel:
        """Get current alert level for a component"""
        return self._alert_levels.get(component_name, AlertLevel.GREEN)

    def get_all_alert_levels(self) -> Dict[str, AlertLevel]:
        """Get alert levels for all components"""
        return self._alert_levels.copy()

    def get_component_stats(self, component_name: str) -> Optional[Dict[str, Any]]:
        """Get stats for a specific component receiver"""
        receiver = self._receivers.get(component_name)
        if receiver:
            return receiver.get_stats()
        return None

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get stats for all component receivers"""
        return {name: receiver.get_stats() for name, receiver in self._receivers.items()}

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of receiver status"""
        total_received = sum(r.stats.packets_received for r in self._receivers.values())
        total_dropped = sum(r.stats.packets_dropped for r in self._receivers.values())
        total_invalid = sum(r.stats.packets_invalid for r in self._receivers.values())

        return {
            "running": self._running,
            "num_receivers": len(self._receivers),
            "total_packets_received": total_received,
            "total_packets_dropped": total_dropped,
            "total_packets_invalid": total_invalid,
            "alert_levels": {k: v.name for k, v in self._alert_levels.items()},
            "last_hb_times": self._last_hb_times.copy(),
        }
