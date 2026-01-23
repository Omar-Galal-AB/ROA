#!/usr/bin/env python3
"""
ROA Command Server - Receives commands from UE5 on port 9876
Part of the dual-port rosbridge architecture
"""

import socket
import json
import threading
import argparse
import sys
import os
import base64
import tempfile
from datetime import datetime
from pathlib import Path

# Import XACRO processor
sys.path.insert(0, str(Path(__file__).parent / 'components' / 'files-type-importer' / 'src' / 'python'))
try:
    from xacro_processor import XacroProcessor
    XACRO_AVAILABLE = True
except ImportError:
    XACRO_AVAILABLE = False
    print("Warning: XACRO processor not available")


class ROACommandServer:
    def __init__(self, host='0.0.0.0', port=9876):
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False
        self.clients = []
        self.client_info = {}  # Track client addresses
        self.message_log_file = '/tmp/roa_messages.log'
        self.heartbeat_file = '/tmp/roa_component_heartbeats.json'
        self.xacro_processor = None
        self.xacro_sessions = {}  # Track ongoing XACRO conversions
        
        # Component heartbeat tracking
        self.component_heartbeats = {
            'wsl': {},    # WSL-side components (FTI, DIMC, ROC, COMC, etc.)
            'plugin': {}  # UE5 Plugin components (ROAModule, NetworkClient, etc.)
        }
        
        # Initialize XACRO processor if available
        if XACRO_AVAILABLE:
            self.xacro_processor = XacroProcessor()
        
        # Clear message log on start
        with open(self.message_log_file, 'w') as f:
            f.write('')
        
        # Initialize heartbeat file
        self._save_heartbeats()
        
    def log_message(self, direction, message, client_addr=None):
        """Log message to file for GUI display"""
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        
        # Determine source - localhost = GUI test, other = real UE5
        source = "UE5"
        if client_addr:
            ip = client_addr[0] if isinstance(client_addr, tuple) else str(client_addr)
            if ip in ('127.0.0.1', 'localhost', '::1'):
                source = "TEST"
        
        if direction == "out":
            arrow = f"-> TO {source}"
        else:
            arrow = f"<- FROM {source}"
        
        try:
            with open(self.message_log_file, 'a') as f:
                f.write(f"[{timestamp}] {arrow}: {message}\n")
        except:
            pass
        
    def log(self, message):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] {message}", flush=True)
        
    def start(self):
        """Start the command server"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.running = True
            
            self.log(f"✅ ROA Command Server listening on {self.host}:{self.port}")
            self.log(f"Waiting for UE5 connections...")
            
            while self.running:
                try:
                    self.server_socket.settimeout(1.0)
                    client_socket, address = self.server_socket.accept()
                    self.log(f"🔗 Client connected from {address}")
                    
                    # Handle client in separate thread
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, address),
                        daemon=True
                    )
                    client_thread.start()
                    self.clients.append(client_socket)
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        self.log(f"❌ Accept error: {e}")
                        
        except Exception as e:
            self.log(f"❌ Server error: {e}")
            sys.exit(1)
            
    def handle_client(self, client_socket, address):
        """Handle commands from a connected UE5 client"""
        buffer = ""
        # Store client address for logging
        self.client_info[id(client_socket)] = address
        
        try:
            while self.running:
                try:
                    data = client_socket.recv(4096).decode('utf-8')
                    if not data:
                        break
                        
                    buffer += data
                    
                    # Process complete JSON messages (newline delimited)
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()
                        
                        if line:
                            self.log_message('in', line, address)
                            self.process_command(line, client_socket, address)
                            
                except socket.timeout:
                    continue
                except Exception as e:
                    self.log(f"❌ Receive error from {address}: {e}")
                    break
                    
        finally:
            self.log(f"🔌 Client disconnected: {address}")
            client_socket.close()
            if client_socket in self.clients:
                self.clients.remove(client_socket)
                
    def process_command(self, message, client_socket, address=None):
        """Process command from UE5"""
        try:
            command = json.loads(message)
            # Support both 'type' (our format) and 'op' (rosbridge format)
            cmd_type = command.get('type') or command.get('op', 'unknown')
            
            self.log(f"📥 Command received: {cmd_type}")
            
            # Handle different command types
            if cmd_type == 'spawn_robot':
                self.handle_spawn_robot(command, client_socket, address)
            elif cmd_type == 'destroy_robot':
                self.handle_destroy_robot(command, client_socket, address)
            elif cmd_type == 'get_status':
                self.handle_get_status(command, client_socket, address)
            elif cmd_type == 'ping':
                # Support rosbridge-style ping with id
                ping_id = command.get('id', '')
                self.send_response(client_socket, {'op': 'pong', 'id': ping_id, 'status': 'ok'}, address)
            elif cmd_type == 'status':
                # UE5 sending status update - acknowledge it
                level = command.get('level', 'info')
                msg = command.get('msg', '')
                self.log(f"📊 UE5 Status [{level}]: {msg}")
                self.send_response(client_socket, {'status': 'ok', 'received': cmd_type}, address)
            # XACRO conversion commands
            elif cmd_type == 'convert_xacro':
                self.handle_convert_xacro(command, client_socket, address)
            elif cmd_type == 'convert_xacro_file':
                self.handle_convert_xacro_file(command, client_socket, address)
            elif cmd_type == 'upload_xacro':
                self.handle_upload_xacro(command, client_socket, address)
            elif cmd_type == 'get_fti_status':
                self.handle_get_fti_status(command, client_socket, address)
            # Heartbeat commands
            elif cmd_type == 'heartbeat':
                self.handle_heartbeat(command, client_socket, address)
            elif cmd_type == 'component_register':
                self.handle_component_register(command, client_socket, address)
            elif cmd_type == 'get_component_status':
                self.handle_get_component_status(command, client_socket, address)
            else:
                self.log(f"⚠️  Unknown command type: {cmd_type}")
                self.send_response(client_socket, {'status': 'error', 'message': f'Unknown command: {cmd_type}'}, address)
                
        except json.JSONDecodeError as e:
            self.log(f"❌ JSON decode error: {e}")
            self.send_response(client_socket, {'status': 'error', 'message': 'Invalid JSON'}, address)
        except Exception as e:
            self.log(f"❌ Command processing error: {e}")
            self.send_response(client_socket, {'status': 'error', 'message': str(e)}, address)
            
    def handle_spawn_robot(self, command, client_socket, address=None):
        """Handle robot spawn command"""
        robot_id = command.get('robot_id', 'unknown')
        self.log(f"🤖 Spawn robot: {robot_id}")
        # TODO: Implement robot spawning logic
        self.send_response(client_socket, {'status': 'success', 'robot_id': robot_id}, address)
        
    def handle_destroy_robot(self, command, client_socket, address=None):
        """Handle robot destroy command"""
        robot_id = command.get('robot_id', 'unknown')
        self.log(f"💥 Destroy robot: {robot_id}")
        # TODO: Implement robot destruction logic
        self.send_response(client_socket, {'status': 'success', 'robot_id': robot_id}, address)
    
    def handle_convert_xacro(self, command, client_socket, address=None):
        """
        Handle XACRO conversion request with embedded content.
        
        Expected command format:
        {
            "type": "convert_xacro",
            "robot_name": "ur5",
            "xacro_content": "base64-encoded XACRO content",
            "xacro_args": {"arg1": "value1"},  # optional
            "output_format": "urdf" | "usd"    # optional, default urdf
        }
        """
        if not XACRO_AVAILABLE or not self.xacro_processor:
            self.send_response(client_socket, {
                'status': 'error',
                'message': 'XACRO processor not available on server',
                'code': 'XACRO_UNAVAILABLE'
            }, address)
            return
        
        robot_name = command.get('robot_name', 'robot')
        xacro_content_b64 = command.get('xacro_content', '')
        xacro_args = command.get('xacro_args', {})
        output_format = command.get('output_format', 'urdf')
        
        self.log(f"📦 XACRO conversion request for: {robot_name}")
        
        # Send progress update
        self.send_response(client_socket, {
            'status': 'progress',
            'progress': 10,
            'message': 'Received XACRO content, starting conversion'
        }, address)
        
        try:
            # Decode base64 content
            xacro_content = base64.b64decode(xacro_content_b64).decode('utf-8')
            
            self.send_response(client_socket, {
                'status': 'progress',
                'progress': 30,
                'message': 'Processing XACRO macros'
            }, address)
            
            # Process XACRO
            success, message, urdf_content = self.xacro_processor.process_from_content(
                xacro_content, robot_name, xacro_args
            )
            
            if not success:
                self.send_response(client_socket, {
                    'status': 'error',
                    'message': message,
                    'code': 'XACRO_PROCESSING_FAILED'
                }, address)
                return
            
            self.send_response(client_socket, {
                'status': 'progress',
                'progress': 80,
                'message': 'XACRO expanded, preparing result'
            }, address)
            
            # Encode result
            urdf_content_b64 = base64.b64encode(urdf_content.encode('utf-8')).decode('utf-8')
            
            # TODO: If output_format == 'usd', run URDF converter here
            
            self.send_response(client_socket, {
                'status': 'success',
                'robot_name': robot_name,
                'urdf_content': urdf_content_b64,
                'output_format': 'urdf',
                'message': 'XACRO conversion complete'
            }, address)
            
            self.log(f"✅ XACRO conversion successful for: {robot_name}")
            
        except Exception as e:
            self.log(f"❌ XACRO conversion error: {e}")
            self.send_response(client_socket, {
                'status': 'error',
                'message': str(e),
                'code': 'XACRO_EXCEPTION'
            }, address)
    
    def handle_convert_xacro_file(self, command, client_socket, address=None):
        """
        Handle XACRO conversion for a file path (Linux-side file).
        
        Expected command format:
        {
            "type": "convert_xacro_file",
            "input_path": "/path/to/robot.xacro",
            "output_path": "/path/to/robot.urdf",  # optional
            "xacro_args": {"arg1": "value1"}       # optional
        }
        """
        if not XACRO_AVAILABLE or not self.xacro_processor:
            self.send_response(client_socket, {
                'status': 'error',
                'message': 'XACRO processor not available on server',
                'code': 'XACRO_UNAVAILABLE'
            }, address)
            return
        
        input_path = command.get('input_path', '')
        output_path = command.get('output_path')
        xacro_args = command.get('xacro_args', {})
        
        if not input_path:
            self.send_response(client_socket, {
                'status': 'error',
                'message': 'input_path is required',
                'code': 'MISSING_INPUT'
            }, address)
            return
        
        self.log(f"📁 XACRO file conversion: {input_path}")
        
        # Send progress
        self.send_response(client_socket, {
            'status': 'progress',
            'progress': 20,
            'message': f'Processing {os.path.basename(input_path)}'
        }, address)
        
        try:
            success, message, result_path = self.xacro_processor.process(
                input_path, output_path, xacro_args
            )
            
            if success:
                self.send_response(client_socket, {
                    'status': 'success',
                    'output_path': result_path,
                    'message': message
                }, address)
                self.log(f"✅ XACRO file conversion successful: {result_path}")
            else:
                self.send_response(client_socket, {
                    'status': 'error',
                    'message': message,
                    'code': 'XACRO_PROCESSING_FAILED'
                }, address)
                
        except Exception as e:
            self.log(f"❌ XACRO file conversion error: {e}")
            self.send_response(client_socket, {
                'status': 'error',
                'message': str(e),
                'code': 'XACRO_EXCEPTION'
            }, address)
    
    def handle_upload_xacro(self, command, client_socket, address=None):
        """
        Handle chunked XACRO file upload for large files.
        
        Protocol:
        1. Client sends: {"type": "upload_xacro", "robot_name": "ur5", "action": "start", "total_size": 12345}
        2. Server responds: {"status": "ready", "session_id": "xxx"}
        3. Client sends chunks: {"type": "upload_xacro", "session_id": "xxx", "action": "chunk", "data": "base64...", "index": 0}
        4. Server acknowledges each chunk
        5. Client sends: {"type": "upload_xacro", "session_id": "xxx", "action": "complete"}
        6. Server processes and returns result
        """
        action = command.get('action', 'start')
        
        if action == 'start':
            # Start new upload session
            import uuid
            session_id = str(uuid.uuid4())[:8]
            robot_name = command.get('robot_name', 'robot')
            total_size = command.get('total_size', 0)
            
            self.xacro_sessions[session_id] = {
                'robot_name': robot_name,
                'total_size': total_size,
                'chunks': [],
                'received_size': 0
            }
            
            self.send_response(client_socket, {
                'status': 'ready',
                'session_id': session_id,
                'message': 'Upload session started'
            }, address)
            
        elif action == 'chunk':
            session_id = command.get('session_id', '')
            if session_id not in self.xacro_sessions:
                self.send_response(client_socket, {
                    'status': 'error',
                    'message': 'Invalid session ID',
                    'code': 'INVALID_SESSION'
                }, address)
                return
            
            chunk_data = command.get('data', '')
            session = self.xacro_sessions[session_id]
            session['chunks'].append(chunk_data)
            session['received_size'] += len(base64.b64decode(chunk_data))
            
            progress = min(90, int(session['received_size'] / max(1, session['total_size']) * 90))
            
            self.send_response(client_socket, {
                'status': 'received',
                'chunk_index': len(session['chunks']) - 1,
                'progress': progress
            }, address)
            
        elif action == 'complete':
            session_id = command.get('session_id', '')
            if session_id not in self.xacro_sessions:
                self.send_response(client_socket, {
                    'status': 'error',
                    'message': 'Invalid session ID',
                    'code': 'INVALID_SESSION'
                }, address)
                return
            
            session = self.xacro_sessions[session_id]
            
            # Combine chunks
            full_content = b''
            for chunk in session['chunks']:
                full_content += base64.b64decode(chunk)
            
            xacro_content = full_content.decode('utf-8')
            robot_name = session['robot_name']
            
            # Clean up session
            del self.xacro_sessions[session_id]
            
            # Process XACRO (same as handle_convert_xacro)
            if not XACRO_AVAILABLE or not self.xacro_processor:
                self.send_response(client_socket, {
                    'status': 'error',
                    'message': 'XACRO processor not available',
                    'code': 'XACRO_UNAVAILABLE'
                }, address)
                return
            
            try:
                success, message, urdf_content = self.xacro_processor.process_from_content(
                    xacro_content, robot_name
                )
                
                if success:
                    urdf_content_b64 = base64.b64encode(urdf_content.encode('utf-8')).decode('utf-8')
                    self.send_response(client_socket, {
                        'status': 'success',
                        'robot_name': robot_name,
                        'urdf_content': urdf_content_b64,
                        'message': 'XACRO conversion complete'
                    }, address)
                else:
                    self.send_response(client_socket, {
                        'status': 'error',
                        'message': message,
                        'code': 'XACRO_PROCESSING_FAILED'
                    }, address)
                    
            except Exception as e:
                self.send_response(client_socket, {
                    'status': 'error',
                    'message': str(e),
                    'code': 'XACRO_EXCEPTION'
                }, address)
    
    def handle_get_fti_status(self, command, client_socket, address=None):
        """
        Get FTI (Files Type Importer) component status.
        Reports XACRO processor availability and conversion capabilities.
        """
        status = {
            'status': 'success',
            'fti': {
                'available': True,
                'xacro_processor': XACRO_AVAILABLE,
                'supported_formats': ['urdf', 'xacro', 'stl', 'obj', 'dae'],
                'output_formats': ['urdf', 'usd'],
                'active_sessions': len(self.xacro_sessions)
            }
        }
        self.send_response(client_socket, status, address)
        
    def handle_get_status(self, command, client_socket, address=None):
        """Handle status request"""
        status = {
            'status': 'success',
            'server': 'roa_command_server',
            'clients': len(self.clients),
            'running': self.running
        }
        self.send_response(client_socket, status, address)
    
    def handle_heartbeat(self, command, client_socket, address=None):
        """
        Handle heartbeat from components (WSL or Plugin side).
        
        Expected format:
        {
            "type": "heartbeat",
            "source": "wsl" | "plugin",
            "component_id": "FTI" | "ROAModule" | etc.,
            "timestamp": 1234567890.123,
            "status": {
                "state": "healthy",
                "response_time": 0.5,
                "errors": 0
            }
        }
        """
        import time
        
        source = command.get('source', 'wsl')  # Default to wsl
        component_id = command.get('component_id', 'unknown')
        timestamp = command.get('timestamp', time.time())
        status = command.get('status', {})
        
        # Validate source
        if source not in ['wsl', 'plugin']:
            source = 'plugin' if address and address[0] not in ('127.0.0.1', '::1') else 'wsl'
        
        # Update heartbeat record
        self.component_heartbeats[source][component_id] = {
            'timestamp': timestamp,
            'response_time': status.get('response_time', 0),
            'state': status.get('state', 'healthy'),
            'errors': status.get('errors', 0),
            'last_message': status.get('message', '')
        }
        
        # Save to file for GUI to read
        self._save_heartbeats()
        
        # Send acknowledgment
        self.send_response(client_socket, {
            'status': 'ok',
            'type': 'heartbeat_ack',
            'component_id': component_id
        }, address)
    
    def handle_component_register(self, command, client_socket, address=None):
        """
        Handle component registration.
        
        Expected format:
        {
            "type": "component_register",
            "source": "wsl" | "plugin",
            "component_id": "FTI",
            "component_name": "Files Type Importer",
            "capabilities": ["xacro", "urdf", "usd"]
        }
        """
        import time
        
        source = command.get('source', 'wsl')
        component_id = command.get('component_id', 'unknown')
        component_name = command.get('component_name', component_id)
        capabilities = command.get('capabilities', [])
        
        if source not in ['wsl', 'plugin']:
            source = 'wsl'
        
        self.log(f"📝 Component registered: {component_id} ({source}) - {capabilities}")
        
        # Initialize heartbeat entry
        self.component_heartbeats[source][component_id] = {
            'timestamp': time.time(),
            'response_time': 0,
            'state': 'registered',
            'errors': 0,
            'name': component_name,
            'capabilities': capabilities
        }
        
        self._save_heartbeats()
        
        self.send_response(client_socket, {
            'status': 'ok',
            'type': 'register_ack',
            'component_id': component_id
        }, address)
    
    def handle_get_component_status(self, command, client_socket, address=None):
        """Return all component heartbeat status."""
        self.send_response(client_socket, {
            'status': 'success',
            'components': self.component_heartbeats
        }, address)
    
    def _save_heartbeats(self):
        """Save heartbeat data to JSON file for GUI."""
        try:
            with open(self.heartbeat_file, 'w') as f:
                json.dump(self.component_heartbeats, f, indent=2)
        except Exception as e:
            self.log(f"⚠️ Failed to save heartbeats: {e}")
        
    def send_response(self, client_socket, response, address=None):
        """Send JSON response to client"""
        try:
            response_str = json.dumps(response) + '\n'
            self.log_message('out', response_str.strip(), address)
            client_socket.sendall(response_str.encode('utf-8'))
        except Exception as e:
            self.log(f"❌ Send response error: {e}")
            
    def stop(self):
        """Stop the server"""
        self.log("🛑 Stopping command server...")
        self.running = False
        
        # Close all client connections
        for client in self.clients[:]:
            try:
                client.close()
            except:
                pass
                
        if self.server_socket:
            self.server_socket.close()
            
        self.log("✅ Command server stopped")

def main():
    parser = argparse.ArgumentParser(description='ROA Command Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=9876, help='Port to listen on')
    args = parser.parse_args()
    
    server = ROACommandServer(host=args.host, port=args.port)
    
    try:
        server.start()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        server.stop()
        sys.exit(0)

if __name__ == '__main__':
    main()
