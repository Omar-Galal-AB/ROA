#!/usr/bin/env python3
"""
ROC UI WebSocket Server
Bridges React UI with ROC Python backend via WebSocket

Usage:
    python roc_ui_server.py
    python roc_ui_server.py --port 9878 --host 0.0.0.0
"""

import argparse
import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Set

try:
    import websockets
    from websockets.server import WebSocketServerProtocol
except ImportError:
    print("Please install websockets: pip install websockets")
    exit(1)

logger = logging.getLogger(__name__)


@dataclass
class RobotState:
    """Robot state data structure"""

    id: str
    name: str
    status: str = "online"  # online, warning, offline
    battery: float = 100.0
    temperature: float = 40.0
    heartbeat: float = 95.0
    errors: int = 0
    position_x: float = 0.0
    position_y: float = 0.0
    position_z: float = 0.0
    joints: list = None

    def __post_init__(self):
        if self.joints is None:
            self.joints = [0.0] * 6

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "battery": round(self.battery, 1),
            "temperature": round(self.temperature, 1),
            "heartbeat": round(self.heartbeat, 1),
            "errors": self.errors,
            "position": {
                "x": self.position_x,
                "y": self.position_y,
                "z": self.position_z,
            },
            "joints": self.joints,
        }


class ROCUIServer:
    """
    WebSocket server for ROC UI communication.

    Handles bidirectional communication between React UI and ROC backend.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 9878):
        self.host = host
        self.port = port
        self.clients: Set[WebSocketServerProtocol] = set()
        self.robots: Dict[str, RobotState] = {}
        self.selected_robot: Optional[str] = None
        self.roc_coordinator = None  # Will be set when integrated with ROC

        # Initialize mock robots for testing
        self._init_mock_robots()

    def _init_mock_robots(self):
        """Initialize mock robots for standalone testing"""
        mock_robots = [
            RobotState("ROBOT-01", "Alpha Scout", "online", 87, 45, 98, 0),
            RobotState("ROBOT-02", "Beta Heavy", "online", 72, 52, 95, 0),
            RobotState("ROBOT-03", "Gamma Arm", "warning", 34, 68, 78, 2),
            RobotState("ROBOT-04", "Delta Drone", "online", 91, 38, 100, 0),
            RobotState("ROBOT-05", "Epsilon Loader", "online", 65, 48, 92, 0),
        ]
        for robot in mock_robots:
            self.robots[robot.id] = robot

    async def register(self, websocket: WebSocketServerProtocol):
        """Register new UI client"""
        self.clients.add(websocket)
        logger.info(
            f"UI client connected from {websocket.remote_address}. Total: {len(self.clients)}"
        )

        # Send current robot list
        await self._send_robot_list(websocket)

    async def unregister(self, websocket: WebSocketServerProtocol):
        """Unregister UI client"""
        self.clients.discard(websocket)
        logger.info(f"UI client disconnected. Total: {len(self.clients)}")

    async def _send_robot_list(self, websocket: WebSocketServerProtocol):
        """Send full robot list to a client"""
        robots = [r.to_dict() for r in self.robots.values()]
        await websocket.send(
            json.dumps(
                {
                    "type": "robot_list",
                    "payload": robots,
                    "timestamp": int(datetime.now().timestamp() * 1000),
                }
            )
        )

    async def broadcast(self, message: dict):
        """Send message to all connected UI clients"""
        if not self.clients:
            return

        msg = json.dumps(message)
        await asyncio.gather(*[client.send(msg) for client in self.clients], return_exceptions=True)

    async def broadcast_robot_state(self, robot_id: str):
        """Broadcast updated robot state to all clients"""
        if robot_id in self.robots:
            await self.broadcast(
                {
                    "type": "robot_state",
                    "payload": self.robots[robot_id].to_dict(),
                    "timestamp": int(datetime.now().timestamp() * 1000),
                }
            )

    async def handle_message(self, websocket: WebSocketServerProtocol, message: str):
        """Handle incoming message from UI"""
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")
            payload = data.get("payload", {})
            request_id = data.get("requestId")

            logger.debug(f"Received: {msg_type} - {payload}")

            # Handle different message types
            handler = getattr(self, f"_handle_{msg_type}", None)
            if handler:
                result = await handler(payload)

                # Send acknowledgment
                await websocket.send(
                    json.dumps(
                        {
                            "type": "command_ack",
                            "payload": {
                                "command": msg_type,
                                "success": True,
                                "result": result,
                            },
                            "requestId": request_id,
                            "timestamp": int(datetime.now().timestamp() * 1000),
                        }
                    )
                )
            else:
                logger.warning(f"Unknown message type: {msg_type}")
                await websocket.send(
                    json.dumps(
                        {
                            "type": "error",
                            "payload": {"message": f"Unknown command: {msg_type}"},
                            "requestId": request_id,
                        }
                    )
                )

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            await websocket.send(
                json.dumps({"type": "error", "payload": {"message": "Invalid JSON"}})
            )
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await websocket.send(json.dumps({"type": "error", "payload": {"message": str(e)}}))

    # ==================== Command Handlers ====================

    async def _handle_get_robots(self, payload: dict) -> dict:
        """Handle get_robots command"""
        return {"count": len(self.robots)}

    async def _handle_select_robot(self, payload: dict) -> dict:
        """Handle robot selection"""
        robot_id = payload.get("robotId")
        if robot_id in self.robots:
            self.selected_robot = robot_id
            logger.info(f"Selected robot: {robot_id}")
            return {"selected": robot_id}
        else:
            raise ValueError(f"Robot not found: {robot_id}")

    async def _handle_move_robot(self, payload: dict) -> dict:
        """Handle robot movement command"""
        robot_id = payload.get("robotId")
        direction = payload.get("direction")
        speed = payload.get("speed", 1.0)

        if robot_id not in self.robots:
            raise ValueError(f"Robot not found: {robot_id}")

        robot = self.robots[robot_id]

        # Simulate movement (in real implementation, forward to ROC)
        move_delta = speed * 0.5
        if direction == "forward":
            robot.position_y += move_delta
        elif direction == "back":
            robot.position_y -= move_delta
        elif direction == "left":
            robot.position_x -= move_delta
        elif direction == "right":
            robot.position_x += move_delta

        logger.info(f"Move {robot_id} {direction} @ {speed}")

        # Broadcast updated state
        await self.broadcast_robot_state(robot_id)

        # TODO: Forward to actual ROC coordinator
        # if self.roc_coordinator:
        #     await self.roc_coordinator.move_robot(robot_id, direction, speed)

        return {"moved": direction}

    async def _handle_move_arm(self, payload: dict) -> dict:
        """Handle arm joint movement"""
        robot_id = payload.get("robotId")
        joint = payload.get("joint", 0)
        delta = payload.get("delta", 0)

        if robot_id not in self.robots:
            raise ValueError(f"Robot not found: {robot_id}")

        robot = self.robots[robot_id]

        # Simulate joint movement
        if 0 <= joint < len(robot.joints):
            robot.joints[joint] += delta
            # Clamp to limits
            robot.joints[joint] = max(-180, min(180, robot.joints[joint]))

        logger.info(f"Arm {robot_id} joint {joint} delta {delta}")

        # Broadcast updated state
        await self.broadcast_robot_state(robot_id)

        return {"joint": joint, "angle": robot.joints[joint]}

    async def _handle_set_joint(self, payload: dict) -> dict:
        """Handle direct joint position setting"""
        robot_id = payload.get("robotId")
        joint = payload.get("joint", 0)
        angle = payload.get("angle", 0)

        if robot_id not in self.robots:
            raise ValueError(f"Robot not found: {robot_id}")

        robot = self.robots[robot_id]

        if 0 <= joint < len(robot.joints):
            robot.joints[joint] = max(-180, min(180, angle))

        await self.broadcast_robot_state(robot_id)

        return {"joint": joint, "angle": robot.joints[joint]}

    async def _handle_emergency_stop(self, payload: dict) -> dict:
        """Handle emergency stop command"""
        robot_id = payload.get("robotId", "ALL")
        reason = payload.get("reason", "User triggered")

        logger.warning(f"🚨 EMERGENCY STOP: {robot_id} - {reason}")

        if robot_id == "ALL":
            for robot in self.robots.values():
                robot.status = "offline"
            await self.broadcast(
                {
                    "type": "robot_list",
                    "payload": [r.to_dict() for r in self.robots.values()],
                }
            )
        elif robot_id in self.robots:
            self.robots[robot_id].status = "offline"
            await self.broadcast_robot_state(robot_id)

        # TODO: Forward to actual ROC coordinator

        return {"stopped": robot_id}

    async def _handle_set_mode(self, payload: dict) -> dict:
        """Handle control mode change"""
        robot_id = payload.get("robotId")
        mode = payload.get("mode")  # RPM or ADM

        logger.info(f"Set mode {robot_id} to {mode}")

        # TODO: Forward to ROC coordinator

        return {"mode": mode}

    async def _handle_set_gripper(self, payload: dict) -> dict:
        """Handle gripper strength setting"""
        robot_id = payload.get("robotId")
        strength = payload.get("strength", 50)

        logger.info(f"Gripper {robot_id} strength {strength}")

        # TODO: Forward to ROC coordinator

        return {"strength": strength}

    async def _handle_ping(self, payload: dict) -> dict:
        """Handle ping/pong for connection testing"""
        return {"pong": True}

    # ==================== Server Lifecycle ====================

    async def handler(self, websocket: WebSocketServerProtocol, path: str = "/"):
        """Handle WebSocket connection"""
        await self.register(websocket)
        try:
            async for message in websocket:
                await self.handle_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister(websocket)

    async def state_update_loop(self):
        """Periodically update and broadcast robot states (simulation)"""
        import random

        while True:
            await asyncio.sleep(1.5)

            # Simulate state changes
            for robot in self.robots.values():
                if robot.status == "online":
                    # Simulate heartbeat fluctuation
                    robot.heartbeat = max(60, min(100, robot.heartbeat + random.uniform(-5, 5)))

                    # Simulate battery drain
                    robot.battery = max(0, robot.battery - random.uniform(0, 0.05))

                    # Simulate temperature
                    robot.temperature = max(30, min(80, robot.temperature + random.uniform(-1, 1)))

                    # Check for warnings
                    if robot.battery < 20 or robot.temperature > 70:
                        robot.status = "warning"

            # Broadcast updates to all clients
            if self.clients:
                for robot in self.robots.values():
                    await self.broadcast_robot_state(robot.id)

    async def start(self):
        """Start the WebSocket server"""
        logger.info(f"Starting ROC UI Server on ws://{self.host}:{self.port}")

        # Start state update loop
        asyncio.create_task(self.state_update_loop())

        # Start WebSocket server
        async with websockets.serve(self.handler, self.host, self.port):
            logger.info(f"ROC UI Server running. Connect UI to ws://{self.host}:{self.port}")
            await asyncio.Future()  # Run forever


def main():
    parser = argparse.ArgumentParser(description="ROC UI WebSocket Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=9878, help="Port to listen on")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [ROC-UI] %(levelname)s: %(message)s",
    )

    server = ROCUIServer(host=args.host, port=args.port)

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")


if __name__ == "__main__":
    main()
