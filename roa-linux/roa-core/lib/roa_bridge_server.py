#!/usr/bin/env python3
"""
ROA Bridge Server - rosbridge-compatible server for UE5 communication
Accepts JSON over TCP, publishes to ROS2 topics
"""

import socket
import json
import threading
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory
from std_msgs.msg import Header

class ROABridgeServer(Node):
    def __init__(self, robot_id='robot_0', tcp_port=9090):
        super().__init__(f'roa_bridge_{robot_id}')
        
        self.robot_id = robot_id
        self.tcp_port = tcp_port
        self.running = True
        self.message_log_file = '/tmp/roa_messages.log'
        
        # ROS2 Publishers (for messages FROM UE5)
        self.joint_state_pub = self.create_publisher(
            JointState,
            f'/robot/{robot_id}/joint_states',
            10
        )
        
        # ROS2 Subscribers (for messages TO UE5)
        self.joint_cmd_sub = self.create_subscription(
            JointTrajectory,
            f'/robot/{robot_id}/joint_commands',
            self.joint_command_callback,
            10
        )
        
        # TCP Client connection
        self.client_socket = None
        self.client_lock = threading.Lock()
        
        # Stats
        self.states_received = 0
        self.commands_sent = 0
        
        self.get_logger().info(f'ROA Bridge Server initialized for robot: {robot_id}')
        self.get_logger().info(f'  - TCP Port: {tcp_port}')
        self.get_logger().info(f'  - Publishing: /robot/{robot_id}/joint_states')
        self.get_logger().info(f'  - Subscribing: /robot/{robot_id}/joint_commands')
        
    def joint_command_callback(self, msg):
        """Forward ROS2 commands to UE5 via TCP"""
        with self.client_lock:
            if self.client_socket:
                try:
                    # Convert to rosbridge-compatible JSON
                    cmd = {
                        "op": "publish",
                        "topic": f"/robot/{self.robot_id}/joint_commands",
                        "msg": {
                            "joint_names": list(msg.joint_names),
                            "points": [{
                                "positions": list(p.positions),
                                "velocities": list(p.velocities),
                                "time_from_start": {
                                    "sec": p.time_from_start.sec,
                                    "nanosec": p.time_from_start.nanosec
                                }
                            } for p in msg.points]
                        }
                    }
                    self.client_socket.send((json.dumps(cmd) + '\n').encode())
                    self.commands_sent += 1
                except Exception as e:
                    self.get_logger().error(f'Failed to send command: {e}')
                    
    def log_message(self, direction, message):
        """Log message to file for GUI display"""
        from datetime import datetime
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        arrow = "→ TO ROS2" if direction == "out" else "← FROM UE5"
        try:
            with open(self.message_log_file, 'a') as f:
                f.write(f"[{timestamp}] {arrow}: {message[:200]}\n")
        except:
            pass
                    
    def handle_message(self, data):
        """Handle rosbridge-protocol message from UE5"""
        try:
            self.log_message('in', data)
            msg = json.loads(data)
            op = msg.get('op', '')
            
            if op == 'advertise':
                # UE5 advertising a topic - just acknowledge
                topic = msg.get('topic', '')
                self.get_logger().info(f'UE5 advertising: {topic}')
                
            elif op == 'publish':
                # UE5 publishing data
                topic = msg.get('topic', '')
                ros_msg = msg.get('msg', {})
                
                if 'joint_states' in topic:
                    self.publish_joint_state(ros_msg)
                else:
                    self.get_logger().warn(f'Unknown topic: {topic}')
                    
            elif op == 'subscribe':
                # UE5 wants to receive from a topic
                topic = msg.get('topic', '')
                self.get_logger().info(f'UE5 subscribing to: {topic}')
                
            else:
                self.get_logger().warn(f'Unknown op: {op}')
                
        except json.JSONDecodeError as e:
            self.get_logger().error(f'JSON parse error: {e}')
            
    def publish_joint_state(self, msg_data):
        """Publish JointState to ROS2"""
        js = JointState()
        js.header.stamp = self.get_clock().now().to_msg()
        js.header.frame_id = msg_data.get('header', {}).get('frame_id', 'base_link')
        js.name = msg_data.get('name', [])
        js.position = msg_data.get('position', [])
        js.velocity = msg_data.get('velocity', [])
        js.effort = msg_data.get('effort', [])
        
        self.joint_state_pub.publish(js)
        self.log_message('out', f'Published JointState: {js.name}')
        self.states_received += 1
        
    def run_tcp_server(self):
        """TCP server thread"""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('0.0.0.0', self.tcp_port))
        server.listen(1)
        server.settimeout(1.0)
        
        self.get_logger().info(f'TCP server listening on port {self.tcp_port}')
        
        while self.running:
            try:
                client, addr = server.accept()
                self.get_logger().info(f'UE5 connected from {addr}')
                
                with self.client_lock:
                    self.client_socket = client
                
                buffer = ''
                while self.running:
                    try:
                        data = client.recv(8192).decode()
                        if not data:
                            break
                        
                        buffer += data
                        
                        # Process complete JSON messages (newline delimited)
                        while '\n' in buffer:
                            line, buffer = buffer.split('\n', 1)
                            if line.strip():
                                self.handle_message(line)
                                
                    except socket.timeout:
                        continue
                    except Exception as e:
                        self.get_logger().error(f'Receive error: {e}')
                        break
                        
                with self.client_lock:
                    self.client_socket = None
                client.close()
                self.get_logger().info('UE5 disconnected')
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.get_logger().error(f'TCP error: {e}')
                    
        server.close()
        
    def print_stats(self):
        """Print periodic stats"""
        self.get_logger().info(
            f'Stats - Received: {self.states_received} states, Sent: {self.commands_sent} commands'
        )

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--robot-id', default='robot_0')
    parser.add_argument('--port', type=int, default=9090)
    args = parser.parse_args()
    
    rclpy.init()
    
    node = ROABridgeServer(args.robot_id, args.port)
    
    # Start TCP server thread
    tcp_thread = threading.Thread(target=node.run_tcp_server, daemon=True)
    tcp_thread.start()
    
    # Stats timer
    stats_timer = node.create_timer(1.0, node.print_stats)
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.running = False
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
