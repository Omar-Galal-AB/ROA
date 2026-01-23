#!/usr/bin/env python3
"""
ROA Main Application Entry Point
Robot Operator Application - Unified Interface
"""

import sys
import os
import argparse
import subprocess
import time
import json
from pathlib import Path


# ============================================================================
# FTI IPC Service Manager - Auto-start and Log Management
# ============================================================================

# FTI Service log file path (accessible by GUI terminal)
FTI_SERVICE_LOG = "/tmp/roa_fti_service.log"

# IPC folder path
IPC_FOLDER = "/mnt/d/ROA/.ipc"


def get_fti_service_status() -> dict:
    """
    Check if FTI IPC service is running and return status info.
    
    Returns:
        dict with keys: running (bool), pid (int or None), uptime (str), last_heartbeat (float)
    """
    status = {
        "running": False,
        "pid": None,
        "uptime": "N/A",
        "last_heartbeat": 0,
        "message": "Not running"
    }
    
    # Check service.status file
    service_status_file = Path(IPC_FOLDER) / "service.status"
    if service_status_file.exists():
        try:
            with open(service_status_file, 'r') as f:
                data = json.load(f)
            
            # Parse timestamp - could be Unix float or ISO string in "last_heartbeat"
            timestamp = data.get("timestamp", 0)
            if not timestamp:
                # Try parsing last_heartbeat as ISO string
                last_hb_str = data.get("last_heartbeat", "")
                if last_hb_str and isinstance(last_hb_str, str):
                    from datetime import datetime
                    try:
                        dt = datetime.fromisoformat(last_hb_str.replace('Z', '+00:00'))
                        timestamp = dt.timestamp()
                    except:
                        pass
            
            # Check file modification time as fallback
            if not timestamp or timestamp < 1577836800:  # Before year 2020
                timestamp = service_status_file.stat().st_mtime
            
            age = time.time() - timestamp
            
            # Check service status field
            service_status_str = data.get("status", "unknown")
            
            # If status file is recent (< 30 seconds) AND status is "running", service is running
            if age < 30 and service_status_str in ("running", "idle", "processing"):
                status["running"] = True
                status["pid"] = data.get("pid")
                status["last_heartbeat"] = timestamp
                status["message"] = f"Running (PID: {status['pid']}, status {age:.1f}s ago)"
                
                # Calculate uptime from uptime_seconds field or file age
                uptime_secs = data.get("uptime_seconds", age)
                if uptime_secs < 60:
                    status["uptime"] = f"{uptime_secs:.0f}s"
                elif uptime_secs < 3600:
                    status["uptime"] = f"{uptime_secs / 60:.1f}m"
                else:
                    status["uptime"] = f"{uptime_secs / 3600:.1f}h"
            elif age < 30:
                # Status file recent but service says stopped
                status["message"] = f"Service status: {service_status_str}"
            else:
                status["message"] = f"Stale status ({age:.0f}s old) - may not be running"
        except Exception as e:
            status["message"] = f"Error reading status: {e}"
    
    return status


def ensure_fti_service_running(auto_shutdown_delay: int = 300) -> bool:
    """
    Ensure the FTI IPC service is running. Start it if not.
    
    This is called automatically when ROA starts.
    The service will auto-shutdown after 'auto_shutdown_delay' seconds of no client activity.
    
    Args:
        auto_shutdown_delay: Seconds to wait before auto-shutdown (default 5 minutes)
    
    Returns:
        True if service is running (or was started), False on failure
    """
    # First check if already running
    status = get_fti_service_status()
    if status["running"]:
        print(f"  [OK] FTI IPC Service already running ({status['message']})")
        return True
    
    # Locate the service script
    fti_service_script = Path(__file__).parent / "components" / "files-type-importer" / "src" / "python" / "roa_ipc_service.py"
    
    if not fti_service_script.exists():
        print(f"  [ERROR] FTI service script not found: {fti_service_script}")
        return False
    
    # Ensure IPC folder exists
    ipc_path = Path(IPC_FOLDER)
    try:
        ipc_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"  [WARNING] Could not create IPC folder: {e}")
    
    # Start the service in background with log output
    print(f"  [STARTING] FTI IPC Service...")
    print(f"             Log file: {FTI_SERVICE_LOG}")
    
    try:
        # Write startup header to log file
        with open(FTI_SERVICE_LOG, 'a') as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"FTI IPC Service starting at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*60}\n")
        
        # Start the service with --log-file argument
        process = subprocess.Popen(
            [
                sys.executable,
                str(fti_service_script),
                "--debug",
                "--log-file", FTI_SERVICE_LOG,
                "--auto-shutdown-delay", str(auto_shutdown_delay)
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # Detach from parent process group
            cwd=str(fti_service_script.parent)
        )
        
        print(f"             PID: {process.pid}")
        
        # Wait for service to become ready (use get_fti_service_status for proper detection)
        for i in range(15):  # Wait up to 15 seconds
            time.sleep(1)
            status = get_fti_service_status()
            if status["running"]:
                print(f"  [OK] FTI IPC Service started successfully (PID: {process.pid})")
                return True
            print(f"             Waiting for service... ({i+1}/15)")
        
        # Final check - sometimes takes a bit longer
        status = get_fti_service_status()
        if status["running"]:
            print(f"  [OK] FTI IPC Service started successfully (PID: {process.pid})")
            return True
        
        print(f"  [WARNING] FTI Service may not have started correctly (status: {status['message']})")
        return False
        
    except Exception as e:
        print(f"  [ERROR] Failed to start FTI service: {e}")
        return False


def stop_fti_service() -> bool:
    """
    Stop the FTI IPC service if running.
    
    Returns:
        True if stopped or wasn't running, False on error
    """
    status = get_fti_service_status()
    if not status["running"]:
        print("  [OK] FTI service is not running")
        return True
    
    pid = status.get("pid")
    if pid:
        try:
            os.kill(pid, 15)  # SIGTERM
            print(f"  [OK] Sent SIGTERM to FTI service (PID: {pid})")
            
            # Wait for it to stop
            for _ in range(10):
                time.sleep(0.5)
                try:
                    os.kill(pid, 0)  # Check if still running
                except OSError:
                    print("  [OK] FTI service stopped")
                    return True
            
            # Force kill if still running
            os.kill(pid, 9)  # SIGKILL
            print("  [OK] FTI service force-killed")
            return True
        except Exception as e:
            print(f"  [ERROR] Failed to stop FTI service: {e}")
            return False
    else:
        print("  [WARNING] No PID found for FTI service")
        return True


# ============================================================================
# Main Application Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='ROA - Robot Operator Application'
    )
    parser.add_argument(
        '--mode',
        choices=['standalone', 'ue5'],
        default='standalone',
        help='Operating mode'
    )
    parser.add_argument(
        '--config',
        type=Path,
        help='Configuration file path'
    )
    parser.add_argument(
        '--component',
        choices=['webthread', 'fti', 'roc', 'dimc', 'comc', 'ros2', 'bridge', 'all'],
        default='all',
        help='Launch specific component'
    )
    parser.add_argument(
        '--no-gui',
        action='store_true',
        help='Run without GUI (terminal only)'
    )
    parser.add_argument(
        '--ros2-native',
        action='store_true',
        help='Use native ROS2 DDS instead of TCP bridge (v0.2)'
    )
    parser.add_argument(
        '--robot-id',
        type=str,
        default='robot_0',
        help='Robot identifier for ROS2 topics'
    )
    
    args = parser.parse_args()
    
    print("="*50)
    print("ROA - Robot Operator Application")
    print("Version: 0.2.0-alpha")
    print("="*50)
    print()
    print(f"Mode: {args.mode}")
    print(f"Component: {args.component}")
    if args.ros2_native:
        print(f"ROS2 Mode: Native DDS (robot_id={args.robot_id})")
    print()
    
    # ========================================================================
    # Auto-start FTI IPC Service (runs in background)
    # ========================================================================
    print("Checking FTI IPC Service...")
    fti_started = ensure_fti_service_running(auto_shutdown_delay=300)
    if not fti_started:
        print("  [WARNING] FTI service may not be available. File imports may fail.")
    print()
    
    # Launch ROS2 native bridge if requested
    if args.ros2_native or args.component == 'ros2':
        print("Launching ROA ROS2 Native Bridge...")
        print()
        try:
            from components.ros2_native import ROABridgeNode
            import rclpy
            
            print(f"Starting ROS2 node for robot: {args.robot_id}")
            rclpy.init()
            
            node = ROABridgeNode(robot_id=args.robot_id, enable_logging=True)
            
            print()
            print("="*50)
            print("ROS2 Bridge Active")
            print("="*50)
            print(f"Robot ID: {args.robot_id}")
            print(f"Listening: /robot/{args.robot_id}/joint_states")
            print(f"Publishing: /robot/{args.robot_id}/joint_commands")
            print()
            print("Press Ctrl+C to stop")
            print()
            
            try:
                rclpy.spin(node)
            except KeyboardInterrupt:
                print("\nShutting down ROS2 bridge...")
            finally:
                node.destroy_node()
                rclpy.shutdown()
            
            return 0
            
        except ImportError as e:
            print(f"ERROR: Could not launch ROS2 bridge: {e}")
            print()
            print("Missing ROS2 dependencies. Please install:")
            print("  sudo apt install ros-humble-rclpy")
            print("  sudo apt install ros-humble-sensor-msgs ros-humble-trajectory-msgs")
            print()
            return 1
        except Exception as e:
            print(f"ERROR: Failed to launch ROS2 bridge: {e}")
            import traceback
            traceback.print_exc()
            return 1
    
    # Launch Bridge Manager if requested
    if args.component == 'bridge':
        print("Launching Bridge Server Manager...")
        print()
        from components.bridge_manager import BridgeManager
        bridge = BridgeManager()
        
        while True:
            print("\n" + "="*50)
            print("ROA Bridge Server Manager")
            print("="*50)
            
            status, msg = bridge.status()
            print(msg)
            print()
            print("Commands:")
            print("  1) Start bridge server")
            print("  2) Stop bridge server")
            print("  3) Restart bridge server")
            print("  4) View log")
            print("  5) Exit")
            print()
            
            choice = input("Select option: ").strip()
            
            if choice == '1':
                print("\nStarting bridge server...")
                success, msg = bridge.start()
                print(msg)
            elif choice == '2':
                print("\nStopping bridge server...")
                success, msg = bridge.stop()
                print(msg)
            elif choice == '3':
                print("\nRestarting bridge server...")
                success, msg = bridge.restart()
                print(msg)
            elif choice == '4':
                print("\nBridge Server Log:")
                print("-" * 50)
                success, log = bridge.get_log()
                print(log)
                input("\nPress Enter to continue...")
            elif choice == '5':
                print("\nExiting...")
                return 0
            else:
                print("\nInvalid option")
        
        return 0
    
    # Launch GUI if not disabled
    if not args.no_gui and args.component in ['webthread', 'roc', 'all']:
        print("Launching ROA GUI Components...")
        print()
        try:
            from PyQt6.QtWidgets import QApplication
            
            # Import dark theme
            ui_path = os.path.join(os.path.dirname(__file__), 'ui')
            sys.path.insert(0, ui_path)
            try:
                from dark_theme import DARK_THEME
            except ImportError:
                DARK_THEME = ""
            
            # Create Qt Application
            app = QApplication(sys.argv)
            
            # Apply dark theme globally
            if DARK_THEME:
                app.setStyleSheet(DARK_THEME)
                print("[Dark theme applied]")
                print()
            
            # Launch components based on selection
            windows = []
            
            if args.component in ['roc', 'all']:
                print("Loading Robot Operator Controller...")
                roc_path = os.path.join(os.path.dirname(__file__), 'components', 'robot-operator-controller', 'standalone')
                sys.path.insert(0, roc_path)
                try:
                    from roc_desktop import ROCMainWindow
                    roc_window = ROCMainWindow()
                    roc_window.show()
                    windows.append(roc_window)
                    print("  [OK] Robot Operator Controller loaded")
                except Exception as e:
                    print(f"  [ERROR] Failed to load ROC: {e}")
                    import traceback
                    traceback.print_exc()
            
            if args.component in ['webthread', 'all']:
                print("Loading Webthread Monitor...")
                webthread_path = os.path.join(os.path.dirname(__file__), 'components', 'webthread', 'standalone')
                sys.path.insert(0, webthread_path)
                try:
                    from webthread_monitor import WebthreadMonitorUI
                    webthread_window = WebthreadMonitorUI()
                    webthread_window.show()
                    windows.append(webthread_window)
                    print("  [OK] Webthread Monitor loaded")
                except Exception as e:
                    print(f"  [ERROR] Failed to load Webthread: {e}")
            
            if not windows:
                print()
                print("ERROR: No GUI components could be loaded!")
                input("Press Enter to exit...")
                return 1
            
            print()
            print(f"GUI launched successfully! ({len(windows)} window(s) open)")
            print("Check the GUI windows for the application interface.")
            print()
            
            # Run Qt event loop
            return app.exec()
            
        except ImportError as e:
            print(f"ERROR: Could not launch GUI: {e}")
            print()
            print("Missing dependencies. Attempting to install PyQt6...")
            print()
            import subprocess
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "PyQt6"])
                print()
                print("PyQt6 installed successfully!")
                print("Please restart ROA to use the GUI.")
                print()
            except Exception as install_error:
                print(f"Failed to install PyQt6: {install_error}")
                print()
                print("Please manually install: pip install PyQt6")
                print()
            input("Press Enter to exit...")
            return 1
        except Exception as e:
            print(f"ERROR: Failed to launch GUI: {e}")
            print()
            import traceback
            traceback.print_exc()
            return 1
    else:
        print("Running in terminal-only mode...")
        print()
        print("Current infrastructure ready:")
        print("  [OK] Mock ROS2 system")
        print("  [OK] Mock UE5 system")
        print("  [OK] Testing framework")
        print("  [OK] CI/CD pipeline")
        print()
        print("To launch GUI, run:")
        print("  roa --component roc        (Robot Operator Controller)")
        print("  roa --component webthread  (Webthread Monitor)")
        print("  roa --component all        (All components)")
        print()
        input("Press Enter to exit...")
        return 0

if __name__ == '__main__':
    sys.exit(main())
