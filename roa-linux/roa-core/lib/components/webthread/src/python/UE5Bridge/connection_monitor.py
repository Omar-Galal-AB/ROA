"""
connection_monitor.py
ROA - Robot Operations & Automation
UE5 Connection Health Monitor

Monitors and validates UE5 connection on webthread startup
"""

import socket
import json
import time
import logging
from typing import Optional, Dict, Any, Tuple
from enum import Enum


class ConnectionStatus(Enum):
    """Connection status enumeration"""
    NOT_TESTED = "not_tested"
    CHECKING = "checking"
    CONNECTED = "connected"
    NO_RESPONSE = "no_response"
    CONNECTION_REFUSED = "connection_refused"
    TIMEOUT = "timeout"
    ERROR = "error"


class UE5ConnectionMonitor:
    """
    Monitors UE5 connection health and diagnoses issues
    
    Performs comprehensive connectivity tests:
    - TCP socket connection
    - Protocol handshake
    - Response validation
    - Diagnostic information gathering
    """

    def __init__(self, host: str = "localhost", port: int = 9876):
        """
        Initialize Connection Monitor
        
        Args:
            host: UE5 host address
            port: UE5 communication port
        """
        self.logger = logging.getLogger(__name__)
        self.host = host
        self.port = port
        self.status = ConnectionStatus.NOT_TESTED
        self.last_check_time = 0.0
        self.last_error: Optional[str] = None
        self.diagnostics: Dict[str, Any] = {}
        
        self.logger.info(f"UE5ConnectionMonitor initialized: {host}:{port}")

    def check_connection(self, timeout: float = 5.0) -> Tuple[ConnectionStatus, Dict[str, Any]]:
        """
        Perform comprehensive connection check
        
        Args:
            timeout: Connection timeout in seconds
            
        Returns:
            Tuple of (status, diagnostics_dict)
        """
        self.status = ConnectionStatus.CHECKING
        self.last_check_time = time.time()
        self.diagnostics = {
            "timestamp": self.last_check_time,
            "host": self.host,
            "port": self.port,
            "timeout": timeout
        }
        
        try:
            # Step 1: TCP Connection
            self.logger.info(f"Testing TCP connection to {self.host}:{self.port}...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            
            try:
                sock.connect((self.host, self.port))
                self.diagnostics["tcp_connection"] = "success"
                self.logger.info("✓ TCP connection established")
            except ConnectionRefusedError:
                self.status = ConnectionStatus.CONNECTION_REFUSED
                self.diagnostics["tcp_connection"] = "refused"
                self.last_error = "Connection refused - nothing listening on port"
                sock.close()
                return self.status, self.diagnostics
            except socket.timeout:
                self.status = ConnectionStatus.TIMEOUT
                self.diagnostics["tcp_connection"] = "timeout"
                self.last_error = "Connection timeout"
                sock.close()
                return self.status, self.diagnostics
            
            # Step 2: Send Connect Command
            self.logger.info("Sending connect command...")
            msg = {
                "message_id": str(time.time()),
                "timestamp": time.time(),
                "message_type": "REQUEST",
                "command": "connect",
                "payload": {
                    "client_type": "webthread",
                    "version": "0.1.0"
                }
            }
            
            msg_str = json.dumps(msg) + '\n'
            sock.send(msg_str.encode())
            self.diagnostics["command_sent"] = "success"
            self.logger.info("✓ Connect command sent")
            
            # Step 3: Wait for Response
            self.logger.info(f"Waiting for response ({timeout}s)...")
            sock.settimeout(timeout)
            
            response = b''
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    chunk = sock.recv(1024)
                    if not chunk:
                        break
                    response += chunk
                    if b'\n' in response:
                        break
                except socket.timeout:
                    break
            
            sock.close()
            
            # Step 4: Validate Response
            if response:
                self.diagnostics["response_received"] = True
                self.diagnostics["response_size"] = len(response)
                
                try:
                    response_str = response.decode().strip()
                    response_json = json.loads(response_str)
                    self.diagnostics["response_valid_json"] = True
                    self.diagnostics["response_data"] = response_json
                    
                    # Check if it's a successful connection response
                    if response_json.get("status") == "success":
                        self.status = ConnectionStatus.CONNECTED
                        self.logger.info("✓✓✓ UE5 connection successful!")
                        return self.status, self.diagnostics
                    else:
                        self.logger.warning(f"UE5 responded but status not success: {response_json}")
                        self.status = ConnectionStatus.NO_RESPONSE
                        self.last_error = f"Invalid response status: {response_json.get('status')}"
                        
                except json.JSONDecodeError as e:
                    self.diagnostics["response_valid_json"] = False
                    self.diagnostics["response_raw"] = response[:200].decode('utf-8', errors='replace')
                    self.logger.warning(f"Invalid JSON response: {e}")
                    self.status = ConnectionStatus.NO_RESPONSE
                    self.last_error = "Response not valid JSON"
            else:
                self.diagnostics["response_received"] = False
                self.status = ConnectionStatus.NO_RESPONSE
                self.last_error = "No response from UE5"
                self.logger.warning("✗ No response from UE5")
            
            return self.status, self.diagnostics
            
        except Exception as e:
            self.status = ConnectionStatus.ERROR
            self.last_error = str(e)
            self.diagnostics["error"] = str(e)
            self.logger.error(f"Connection check error: {e}")
            return self.status, self.diagnostics

    def get_diagnostic_report(self) -> str:
        """
        Generate human-readable diagnostic report
        
        Returns:
            Formatted diagnostic report string
        """
        report = []
        report.append("="*60)
        report.append("  UE5 CONNECTION DIAGNOSTIC REPORT")
        report.append("="*60)
        report.append("")
        report.append(f"Target: {self.host}:{self.port}")
        report.append(f"Status: {self.status.value}")
        report.append(f"Last Check: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.last_check_time))}")
        report.append("")
        
        if self.status == ConnectionStatus.CONNECTED:
            report.append("✓ CONNECTION SUCCESSFUL")
            if "response_data" in self.diagnostics:
                session_id = self.diagnostics["response_data"].get("session_id", "N/A")
                report.append(f"  Session ID: {session_id}")
        else:
            report.append("✗ CONNECTION FAILED")
            if self.last_error:
                report.append(f"  Error: {self.last_error}")
            report.append("")
            report.append("Diagnostics:")
            
            tcp_status = self.diagnostics.get("tcp_connection", "not tested")
            if tcp_status == "success":
                report.append("  ✓ TCP connection: OK")
            elif tcp_status == "refused":
                report.append("  ✗ TCP connection: REFUSED")
                report.append("    - Is socat relay running?")
                report.append("    - Run: socat -d -d TCP-LISTEN:9876,fork,reuseaddr TCP:<WINDOWS_IP>:9876")
            elif tcp_status == "timeout":
                report.append("  ✗ TCP connection: TIMEOUT")
                report.append("    - Check network connectivity")
                report.append("    - Verify Windows firewall settings")
            
            if "command_sent" in self.diagnostics:
                report.append("  ✓ Command sent: OK")
                
                if not self.diagnostics.get("response_received", False):
                    report.append("  ✗ Response received: NONE")
                    report.append("    - Is UE5 in Play mode?")
                    report.append("    - Is ROA plugin active?")
                    report.append("    - Check UE5 Output Log for errors")
                elif not self.diagnostics.get("response_valid_json", True):
                    report.append("  ✗ Response format: INVALID")
                    report.append("    - UE5 plugin protocol mismatch")
        
        report.append("")
        report.append("="*60)
        
        return "\n".join(report)

    def wait_for_connection(self, max_attempts: int = 5, retry_delay: float = 2.0) -> bool:
        """
        Wait for UE5 connection with retries
        
        Args:
            max_attempts: Maximum number of connection attempts
            retry_delay: Delay between attempts in seconds
            
        Returns:
            True if connected successfully
        """
        self.logger.info(f"Waiting for UE5 connection (max {max_attempts} attempts)...")
        
        for attempt in range(1, max_attempts + 1):
            self.logger.info(f"Attempt {attempt}/{max_attempts}...")
            
            status, diagnostics = self.check_connection()
            
            if status == ConnectionStatus.CONNECTED:
                self.logger.info("✓ Connection established!")
                return True
            
            if attempt < max_attempts:
                self.logger.warning(f"Connection failed, retrying in {retry_delay}s...")
                time.sleep(retry_delay)
        
        self.logger.error("Failed to establish connection after all attempts")
        return False


def run_connection_test(host: str = "localhost", port: int = 9876) -> bool:
    """
    Run standalone connection test
    
    Args:
        host: UE5 host address
        port: UE5 communication port
        
    Returns:
        True if connection successful
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    monitor = UE5ConnectionMonitor(host, port)
    status, diagnostics = monitor.check_connection()
    
    print("\n" + monitor.get_diagnostic_report())
    
    return status == ConnectionStatus.CONNECTED


if __name__ == "__main__":
    import sys
    
    # Allow host:port override from command line
    host = "localhost"
    port = 9876
    
    if len(sys.argv) > 1:
        if ":" in sys.argv[1]:
            host, port_str = sys.argv[1].split(":")
            port = int(port_str)
        else:
            host = sys.argv[1]
    
    success = run_connection_test(host, port)
    sys.exit(0 if success else 1)
