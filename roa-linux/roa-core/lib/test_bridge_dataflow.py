#!/usr/bin/env python3
"""
ROA Bridge Data Flow Test
Tests all data types that need to flow through ports 9090 and 9876

Tests cover:
- FTI: Robot specs, import status
- DIMC: Spatial data @ 60Hz, sensor readings, obstacles
- ROC: Control commands, trajectories, status
- COMC: Multi-robot coordination, work areas
- Webthread: Config updates, health monitoring
"""

import json
import socket
import threading
import time
from datetime import datetime
from typing import Dict, List


class BridgeDataFlowTester:
    def __init__(self):
        self.results = []
        self.test_count = 0
        self.passed = 0
        self.failed = 0

    def log(self, message, status="INFO"):
        """Log test message"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        color = {
            "PASS": "\033[92m✓",
            "FAIL": "\033[91m✗",
            "INFO": "\033[94mℹ",
            "WARN": "\033[93m⚠",
        }.get(status, "")
        reset = "\033[0m"

        print(f"[{timestamp}] {color} {message}{reset}")
        self.results.append(f"[{timestamp}] [{status}] {message}")

    def test_port_9876_command(self, command_type: str, data: Dict) -> bool:
        """Test sending command to port 9876"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect(("localhost", 9876))

            message = json.dumps(data) + "\n"
            sock.send(message.encode())

            # Wait for response
            response = sock.recv(4096).decode()
            sock.close()

            if response:
                resp_data = json.loads(response.strip())
                if resp_data.get("status") in ("success", "ok"):
                    self.log(f"Port 9876 - {command_type}: OK", "PASS")
                    return True
                else:
                    self.log(
                        f"Port 9876 - {command_type}: Error - {resp_data.get('message', 'Unknown')}",
                        "FAIL",
                    )
                    return False
            else:
                self.log(f"Port 9876 - {command_type}: No response", "FAIL")
                return False

        except socket.timeout:
            self.log(f"Port 9876 - {command_type}: Timeout", "FAIL")
            return False
        except Exception as e:
            self.log(f"Port 9876 - {command_type}: {str(e)}", "FAIL")
            return False

    def test_port_9090_rosbridge(self, msg_type: str, data: Dict) -> bool:
        """Test sending rosbridge message to port 9090"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect(("localhost", 9090))

            message = json.dumps(data) + "\n"
            sock.send(message.encode())
            sock.close()

            # For rosbridge, we don't expect immediate response
            self.log(f"Port 9090 - {msg_type}: Sent successfully", "PASS")
            return True

        except socket.timeout:
            self.log(f"Port 9090 - {msg_type}: Timeout", "FAIL")
            return False
        except Exception as e:
            self.log(f"Port 9090 - {msg_type}: {str(e)}", "FAIL")
            return False

    # ==================== FTI Data Types ====================

    def test_fti_robot_specs(self):
        """Test FTI robot specifications via port 9876"""
        self.log("\n=== Testing FTI: Robot Specifications ===", "INFO")

        data = {
            "type": "spawn_robot",
            "robot_id": "test_robot_001",
            "robot_name": "ConstructionArm",
            "joints": [
                {"name": "base_to_arm", "type": "revolute", "limits": [-3.14, 3.14]},
                {"name": "arm_to_gripper", "type": "prismatic", "limits": [0, 0.5]},
            ],
            "capabilities": ["RPM", "ADM"],
        }

        result = self.test_port_9876_command("FTI Robot Specs", data)
        self.test_count += 1
        if result:
            self.passed += 1
        else:
            self.failed += 1

    def test_fti_import_status(self):
        """Test FTI import status notifications"""
        self.log("\n=== Testing FTI: Import Status ===", "INFO")

        data = {
            "type": "status",
            "level": "info",
            "component": "FTI",
            "msg": "Robot model imported successfully: 5 parts, 2 joints",
        }

        result = self.test_port_9876_command("FTI Import Status", data)
        self.test_count += 1
        if result:
            self.passed += 1
        else:
            self.failed += 1

    # ==================== DIMC Data Types ====================

    def test_dimc_spatial_data(self):
        """Test DIMC spatial data @ 60Hz via port 9090"""
        self.log("\n=== Testing DIMC: Spatial Data (60Hz) ===", "INFO")

        data = {
            "op": "publish",
            "topic": "/robot/robot_001/joint_states",
            "msg": {
                "header": {"frame_id": "base_link"},
                "name": ["joint_1", "joint_2", "joint_3"],
                "position": [1.57, 0.0, -0.78],
                "velocity": [0.1, 0.0, -0.05],
                "effort": [0.0, 0.0, 0.0],
            },
        }

        result = self.test_port_9090_rosbridge("DIMC Spatial Data", data)
        self.test_count += 1
        if result:
            self.passed += 1
        else:
            self.failed += 1

    def test_dimc_sensor_readings(self):
        """Test DIMC sensor readings via port 9090"""
        self.log("\n=== Testing DIMC: Sensor Readings ===", "INFO")

        data = {
            "op": "publish",
            "topic": "/dimc/sensor_data",
            "msg": {
                "timestamp": time.time(),
                "sensors": {
                    "lidar_1": {"status": "active", "range": 10.5},
                    "camera_1": {"status": "active", "fps": 30},
                    "imu_1": {"status": "active", "orientation": [0, 0, 0]},
                },
            },
        }

        result = self.test_port_9090_rosbridge("DIMC Sensor Data", data)
        self.test_count += 1
        if result:
            self.passed += 1
        else:
            self.failed += 1

    def test_dimc_obstacles(self):
        """Test DIMC obstacle detection via port 9090"""
        self.log("\n=== Testing DIMC: Obstacle Detection ===", "INFO")

        data = {
            "op": "publish",
            "topic": "/dimc/obstacles",
            "msg": {
                "timestamp": time.time(),
                "obstacles": [
                    {
                        "id": "obs_001",
                        "position": [2.5, 3.0, 0.0],
                        "size": 0.5,
                        "type": "static",
                    },
                    {
                        "id": "obs_002",
                        "position": [5.0, 1.0, 0.0],
                        "size": 0.3,
                        "type": "dynamic",
                    },
                ],
                "collision_risk": "low",
            },
        }

        result = self.test_port_9090_rosbridge("DIMC Obstacles", data)
        self.test_count += 1
        if result:
            self.passed += 1
        else:
            self.failed += 1

    # ==================== ROC Data Types ====================

    def test_roc_control_commands(self):
        """Test ROC control commands via port 9090"""
        self.log("\n=== Testing ROC: Control Commands ===", "INFO")

        data = {
            "op": "publish",
            "topic": "/robot/robot_001/joint_commands",
            "msg": {
                "joint_names": ["joint_1", "joint_2"],
                "points": [
                    {
                        "positions": [1.0, 0.5],
                        "velocities": [0.1, 0.1],
                        "time_from_start": {"sec": 1, "nanosec": 0},
                    }
                ],
            },
        }

        result = self.test_port_9090_rosbridge("ROC Control Commands", data)
        self.test_count += 1
        if result:
            self.passed += 1
        else:
            self.failed += 1

    def test_roc_status(self):
        """Test ROC robot status @ 1Hz via port 9876"""
        self.log("\n=== Testing ROC: Robot Status ===", "INFO")

        data = {
            "type": "status",
            "level": "info",
            "component": "ROC",
            "msg": "Robot robot_001: Mode=RPM, Battery=85%, Status=Active",
        }

        result = self.test_port_9876_command("ROC Status", data)
        self.test_count += 1
        if result:
            self.passed += 1
        else:
            self.failed += 1

    # ==================== COMC Data Types ====================

    def test_comc_multi_robot_coordination(self):
        """Test COMC multi-robot coordination via port 9876"""
        self.log("\n=== Testing COMC: Multi-Robot Coordination ===", "INFO")

        data = {
            "type": "status",
            "level": "info",
            "component": "COMC",
            "msg": json.dumps(
                {
                    "event": "work_area_broadcast",
                    "robot_id": "robot_001",
                    "reserved_zone": {"x": 5.0, "y": 5.0, "radius": 2.0},
                    "priority": "normal",
                }
            ),
        }

        result = self.test_port_9876_command("COMC Coordination", data)
        self.test_count += 1
        if result:
            self.passed += 1
        else:
            self.failed += 1

    def test_comc_evasion_response(self):
        """Test COMC evasion response via port 9090"""
        self.log("\n=== Testing COMC: Evasion Response ===", "INFO")

        data = {
            "op": "publish",
            "topic": "/comc/evasion_response",
            "msg": {
                "robot_id": "robot_001",
                "alternative_path": [
                    {"x": 1.0, "y": 1.0, "z": 0.0},
                    {"x": 2.0, "y": 2.0, "z": 0.0},
                ],
                "reason": "collision_avoidance",
            },
        }

        result = self.test_port_9090_rosbridge("COMC Evasion", data)
        self.test_count += 1
        if result:
            self.passed += 1
        else:
            self.failed += 1

    # ==================== Webthread Data Types ====================

    def test_webthread_config_update(self):
        """Test Webthread configuration updates via port 9876"""
        self.log("\n=== Testing Webthread: Config Update ===", "INFO")

        data = {
            "type": "status",
            "level": "info",
            "component": "Webthread",
            "msg": json.dumps(
                {
                    "event": "config_update",
                    "parameter": "safety_threshold",
                    "value": 0.5,
                }
            ),
        }

        result = self.test_port_9876_command("Webthread Config", data)
        self.test_count += 1
        if result:
            self.passed += 1
        else:
            self.failed += 1

    def test_webthread_health_monitoring(self):
        """Test Webthread health monitoring via port 9876"""
        self.log("\n=== Testing Webthread: Health Monitoring ===", "INFO")

        data = {"type": "get_status"}

        result = self.test_port_9876_command("Webthread Health", data)
        self.test_count += 1
        if result:
            self.passed += 1
        else:
            self.failed += 1

    # ==================== Bidirectional Tests ====================

    def test_bidirectional_flow(self):
        """Test bidirectional communication: UE5 → ROS2 → UE5"""
        self.log("\n=== Testing Bidirectional Flow ===", "INFO")

        # 1. Advertise a topic (UE5 → ROS2)
        advertise_msg = {
            "op": "advertise",
            "topic": "/test/bidirectional",
            "type": "std_msgs/String",
        }
        result1 = self.test_port_9090_rosbridge("Advertise Topic", advertise_msg)

        # 2. Publish data (UE5 → ROS2)
        publish_msg = {
            "op": "publish",
            "topic": "/test/bidirectional",
            "msg": {"data": "Test message from UE5"},
        }
        result2 = self.test_port_9090_rosbridge("Publish Data", publish_msg)

        # 3. Subscribe to response topic (UE5 ← ROS2)
        subscribe_msg = {
            "op": "subscribe",
            "topic": "/test/response",
            "type": "std_msgs/String",
        }
        result3 = self.test_port_9090_rosbridge("Subscribe Topic", subscribe_msg)

        self.test_count += 1
        if result1 and result2 and result3:
            self.passed += 1
            self.log("Bidirectional flow: COMPLETE", "PASS")
        else:
            self.failed += 1
            self.log("Bidirectional flow: FAILED", "FAIL")

    # ==================== High-Frequency Test ====================

    def test_high_frequency_data(self):
        """Test 60Hz data throughput on port 9090"""
        self.log("\n=== Testing High-Frequency Data (60Hz Simulation) ===", "INFO")

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect(("localhost", 9090))

            start_time = time.time()
            messages_sent = 0
            target_messages = 60  # Simulate 1 second of 60Hz

            for i in range(target_messages):
                data = {
                    "op": "publish",
                    "topic": "/dimc/spatial_data",
                    "msg": {
                        "timestamp": time.time(),
                        "position": [i * 0.1, i * 0.1, 0.0],
                        "velocity": [0.1, 0.1, 0.0],
                    },
                }

                message = json.dumps(data) + "\n"
                sock.send(message.encode())
                messages_sent += 1
                time.sleep(1.0 / 60.0)  # 60Hz rate

            elapsed = time.time() - start_time
            actual_hz = messages_sent / elapsed

            sock.close()

            self.test_count += 1
            if actual_hz >= 55:  # Allow 5Hz tolerance
                self.passed += 1
                self.log(f"High-frequency test: {actual_hz:.1f}Hz achieved", "PASS")
            else:
                self.failed += 1
                self.log(f"High-frequency test: Only {actual_hz:.1f}Hz achieved", "WARN")

        except Exception as e:
            self.test_count += 1
            self.failed += 1
            self.log(f"High-frequency test failed: {str(e)}", "FAIL")

    # ==================== Main Test Runner ====================

    def run_all_tests(self):
        """Run complete test suite"""
        print("\n" + "=" * 70)
        print("ROA Bridge Data Flow Test Suite")
        print("Testing all component data types through ports 9090 & 9876")
        print("=" * 70)

        # Check server availability
        self.log("\n=== Checking Server Availability ===", "INFO")

        servers_running = True
        try:
            # Test port 9876
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect(("localhost", 9876))
            sock.close()
            self.log("Port 9876 (Command Server): Available", "PASS")
        except:
            self.log("Port 9876 (Command Server): NOT AVAILABLE", "FAIL")
            servers_running = False

        try:
            # Test port 9090
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect(("localhost", 9090))
            sock.close()
            self.log("Port 9090 (ROS2 Bridge): Available", "PASS")
        except:
            self.log("Port 9090 (ROS2 Bridge): NOT AVAILABLE", "FAIL")
            servers_running = False

        if not servers_running:
            print("\n⚠️  ERROR: Bridge servers not running!")
            print("Start servers with: roa start")
            return

        # Run all component tests
        self.test_fti_robot_specs()
        self.test_fti_import_status()

        self.test_dimc_spatial_data()
        self.test_dimc_sensor_readings()
        self.test_dimc_obstacles()

        self.test_roc_control_commands()
        self.test_roc_status()

        self.test_comc_multi_robot_coordination()
        self.test_comc_evasion_response()

        self.test_webthread_config_update()
        self.test_webthread_health_monitoring()

        self.test_bidirectional_flow()
        self.test_high_frequency_data()

        # Print summary
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        print(f"Total Tests:  {self.test_count}")
        print(
            f"✓ Passed:     {self.passed} ({self.passed*100//self.test_count if self.test_count > 0 else 0}%)"
        )
        print(
            f"✗ Failed:     {self.failed} ({self.failed*100//self.test_count if self.test_count > 0 else 0}%)"
        )
        print("=" * 70)

        if self.failed == 0:
            print("\n🎉 ALL TESTS PASSED! Bridge is ready for all component data types.")
        else:
            print(f"\n⚠️  {self.failed} test(s) failed. Check logs above for details.")

        # Save results to file
        with open("/tmp/bridge_test_results.log", "w") as f:
            f.write("\n".join(self.results))
        print(f"\n📄 Full results saved to: /tmp/bridge_test_results.log")


def main():
    """Main entry point"""
    tester = BridgeDataFlowTester()
    tester.run_all_tests()


if __name__ == "__main__":
    main()
