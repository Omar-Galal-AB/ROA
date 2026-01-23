#!/usr/bin/env python3
"""
ROA Bridge Manager Component
Controls rosbridge server (start/stop/status)
"""

import os
import signal
import subprocess
from pathlib import Path


class BridgeManager:
    def __init__(self):
        self.bridge_script = Path("/home/myws/roa/roa_linux/roa-core/lib/start_bridge.sh")
        self.stop_script = Path("/home/myws/roa/roa_linux/roa-core/lib/stop_bridge.sh")

    def start(self):
        """Start the rosbridge server"""
        try:
            result = subprocess.run(
                [str(self.bridge_script)], capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0, result.stdout + result.stderr
        except Exception as e:
            return False, str(e)

    def stop(self):
        """Stop the rosbridge server"""
        try:
            result = subprocess.run(
                [str(self.stop_script)], capture_output=True, text=True, timeout=5
            )
            return True, result.stdout + result.stderr
        except Exception as e:
            return False, str(e)

    def restart(self):
        """Restart the rosbridge server"""
        self.stop()
        import time

        time.sleep(1)
        return self.start()

    def status(self):
        """Check bridge server status"""
        try:
            # Check if process is running
            result = subprocess.run(
                ["pgrep", "-f", "roa_bridge_server.py"], capture_output=True, text=True
            )
            is_running = result.returncode == 0

            # Check ports
            port_result = subprocess.run(["ss", "-tuln"], capture_output=True, text=True)
            port_9090 = "9090" in port_result.stdout
            port_9876 = "9876" in port_result.stdout

            status_text = f"Bridge Server: {'RUNNING' if is_running else 'STOPPED'}\n"
            if is_running:
                status_text += f"Port 9090 (rosbridge): {'✓' if port_9090 else '✗'}\n"
                status_text += f"Port 9876 (network):  {'✓' if port_9876 else '✗'}\n"

            return is_running, status_text
        except Exception as e:
            return False, str(e)

    def get_log(self):
        """Get recent log entries"""
        try:
            with open("/tmp/roa_bridge.log", "r") as f:
                lines = f.readlines()
                return True, "".join(lines[-50:])  # Last 50 lines
        except FileNotFoundError:
            return False, "No log file found"
        except Exception as e:
            return False, str(e)
