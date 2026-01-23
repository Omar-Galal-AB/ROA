# ROC UI → UE5 Integration Guide

## Overview

This guide explains how to prepare and integrate the ROC UI (React/TypeScript) into Unreal Engine 5.

---

## Integration Options

### Option A: Web Browser Widget (Recommended for Phase 1)
**Pros:** Uses existing React code, fast iteration, modern UI  
**Cons:** Requires running web server, slight performance overhead

### Option B: Native UMG Widgets (Phase 2)
**Pros:** Native performance, full UE5 integration  
**Cons:** Must rewrite UI in C++/Blueprints, more effort

### Option C: Coherent Gameface (Commercial)
**Pros:** Best of both worlds, HTML5 to native  
**Cons:** Paid license required

---

## Phase 1: Web Browser Widget Integration

### Step 1: Build Production Bundle

```bash
cd ROC_UI
npm install
npm run build
```

This creates a `dist/` folder with optimized static files.

---

### Step 2: Add Communication Layer

Create a WebSocket bridge for React ↔ UE5 communication:

**File: `src/hooks/useROCBridge.ts`**
```typescript
import { useState, useEffect, useCallback } from 'react';

interface ROCMessage {
  type: string;
  payload: any;
}

interface RobotState {
  id: string;
  position: { x: number; y: number; z: number };
  joints: number[];
  status: 'online' | 'warning' | 'offline';
  battery: number;
  temperature: number;
}

export function useROCBridge(serverUrl: string = 'ws://localhost:9878') {
  const [connected, setConnected] = useState(false);
  const [robots, setRobots] = useState<Map<string, RobotState>>(new Map());
  const [ws, setWs] = useState<WebSocket | null>(null);

  useEffect(() => {
    const socket = new WebSocket(serverUrl);
    
    socket.onopen = () => {
      console.log('ROC Bridge connected');
      setConnected(true);
    };

    socket.onmessage = (event) => {
      const msg: ROCMessage = JSON.parse(event.data);
      handleMessage(msg);
    };

    socket.onclose = () => {
      console.log('ROC Bridge disconnected');
      setConnected(false);
    };

    setWs(socket);
    return () => socket.close();
  }, [serverUrl]);

  const handleMessage = (msg: ROCMessage) => {
    switch (msg.type) {
      case 'robot_state':
        setRobots(prev => {
          const newMap = new Map(prev);
          newMap.set(msg.payload.id, msg.payload);
          return newMap;
        });
        break;
      case 'robot_list':
        const newMap = new Map();
        msg.payload.forEach((robot: RobotState) => {
          newMap.set(robot.id, robot);
        });
        setRobots(newMap);
        break;
    }
  };

  // Send control commands to UE5
  const sendCommand = useCallback((command: string, data: any) => {
    if (ws && connected) {
      ws.send(JSON.stringify({
        type: command,
        payload: data,
        timestamp: Date.now()
      }));
    }
  }, [ws, connected]);

  // Control functions
  const moveRobot = (robotId: string, direction: 'forward' | 'back' | 'left' | 'right') => {
    sendCommand('move_robot', { robotId, direction });
  };

  const moveArm = (robotId: string, joint: number, delta: number) => {
    sendCommand('move_arm', { robotId, joint, delta });
  };

  const emergencyStop = (robotId?: string) => {
    sendCommand('emergency_stop', { robotId });
  };

  const selectRobot = (robotId: string) => {
    sendCommand('select_robot', { robotId });
  };

  return {
    connected,
    robots: Array.from(robots.values()),
    moveRobot,
    moveArm,
    emergencyStop,
    selectRobot,
    sendCommand
  };
}
```

---

### Step 3: Update Components to Use Bridge

**File: `src/App.tsx`** (updated)
```typescript
import { useState, useEffect } from 'react';
import { MovementControls } from './components/MovementControls';
import { ArmControls } from './components/ArmControls';
import { LeftTopPanel } from './components/LeftTopPanel';
import { RightTopPanel } from './components/RightTopPanel';
import { useROCBridge } from './hooks/useROCBridge';

export default function App() {
  const [pressedKeys, setPressedKeys] = useState<Set<string>>(new Set());
  const [selectedRobotId, setSelectedRobotId] = useState<string | null>(null);
  
  // Connect to ROC backend (WSL Python or UE5)
  const { 
    connected, 
    robots, 
    moveRobot, 
    moveArm, 
    emergencyStop,
    selectRobot 
  } = useROCBridge();

  // Keyboard handling with actual commands
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();
      setPressedKeys(prev => new Set(prev).add(key));
      
      if (!selectedRobotId) return;
      
      // Movement controls
      if (key === 'w') moveRobot(selectedRobotId, 'forward');
      if (key === 's') moveRobot(selectedRobotId, 'back');
      if (key === 'a') moveRobot(selectedRobotId, 'left');
      if (key === 'd') moveRobot(selectedRobotId, 'right');
      
      // Arm controls
      if (key === 'arrowup') moveArm(selectedRobotId, 0, 5);
      if (key === 'arrowdown') moveArm(selectedRobotId, 0, -5);
      if (key === 'arrowleft') moveArm(selectedRobotId, 1, -5);
      if (key === 'arrowright') moveArm(selectedRobotId, 1, 5);
      
      // Emergency stop
      if (key === ' ') emergencyStop(selectedRobotId);
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      setPressedKeys(prev => {
        const newSet = new Set(prev);
        newSet.delete(e.key.toLowerCase());
        return newSet;
      });
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [selectedRobotId, moveRobot, moveArm, emergencyStop]);

  return (
    <div className="w-screen h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 overflow-hidden relative fixed inset-0">
      {/* Connection Status Indicator */}
      <div className="absolute top-2 left-1/2 transform -translate-x-1/2 z-50">
        <div className={`flex items-center gap-2 px-3 py-1 rounded-full font-mono text-xs ${
          connected 
            ? 'bg-green-500/20 border border-green-500/50 text-green-400'
            : 'bg-red-500/20 border border-red-500/50 text-red-400'
        }`}>
          <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'} animate-pulse`}></div>
          {connected ? 'UE5 CONNECTED' : 'DISCONNECTED'}
        </div>
      </div>

      {/* Background grid effect */}
      <div className="absolute inset-0 opacity-10">
        <div className="absolute inset-0" style={{
          backgroundImage: 'linear-gradient(rgba(59, 130, 246, 0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(59, 130, 246, 0.5) 1px, transparent 1px)',
          backgroundSize: '50px 50px'
        }}></div>
      </div>

      {/* Top Left - Multi Panel */}
      <div className="absolute top-6 left-6 z-10">
        <LeftTopPanel pressedKeys={pressedKeys} />
      </div>

      {/* Top Right - Multi Panel */}
      <div className="absolute top-6 right-6 z-10">
        <RightTopPanel 
          pressedKeys={pressedKeys} 
          robots={robots}
          selectedRobotId={selectedRobotId}
          onSelectRobot={(id) => {
            setSelectedRobotId(id);
            selectRobot(id);
          }}
        />
      </div>

      {/* Bottom Left - WASD Movement Controls */}
      <div className="absolute bottom-6 left-6 z-10">
        <MovementControls pressedKeys={pressedKeys} />
      </div>

      {/* Bottom Right - Arrow Arm Controls */}
      <div className="absolute bottom-6 right-6 z-10">
        <ArmControls pressedKeys={pressedKeys} />
      </div>

      {/* Center Display */}
      <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 text-center">
        <div className="bg-slate-800/40 backdrop-blur-sm border border-blue-500/30 rounded-lg px-6 py-4">
          <h1 className="text-3xl font-mono text-blue-400 mb-1">ROBOT CONTROL SYSTEM</h1>
          <div className="text-cyan-300 font-mono text-xs">
            {selectedRobotId ? `Controlling: ${selectedRobotId}` : 'No Robot Selected'}
          </div>
          <div className="mt-3 flex gap-2 justify-center">
            <div className={`h-1.5 w-1.5 rounded-full ${connected ? 'bg-green-400' : 'bg-red-400'} animate-pulse`}></div>
            <span className={`text-[10px] font-mono ${connected ? 'text-green-400' : 'text-red-400'}`}>
              {connected ? 'SYSTEM ONLINE' : 'SYSTEM OFFLINE'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
```

---

### Step 4: Create Python WebSocket Server (ROC Side)

**File: `roc_ui_server.py`** (in ROC component)
```python
#!/usr/bin/env python3
"""
ROC UI WebSocket Server
Bridges React UI with ROC Python backend
"""

import asyncio
import json
import logging
from typing import Set
import websockets

logger = logging.getLogger(__name__)


class ROCUIServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 9878):
        self.host = host
        self.port = port
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.roc_coordinator = None  # Will be set by ROC

    async def register(self, websocket):
        self.clients.add(websocket)
        logger.info(f"UI client connected. Total: {len(self.clients)}")
        
        # Send current robot list
        if self.roc_coordinator:
            robots = await self._get_robot_list()
            await websocket.send(json.dumps({
                "type": "robot_list",
                "payload": robots
            }))

    async def unregister(self, websocket):
        self.clients.discard(websocket)
        logger.info(f"UI client disconnected. Total: {len(self.clients)}")

    async def broadcast(self, message: dict):
        """Send message to all connected UI clients"""
        if self.clients:
            msg = json.dumps(message)
            await asyncio.gather(
                *[client.send(msg) for client in self.clients],
                return_exceptions=True
            )

    async def handle_message(self, websocket, message: str):
        """Handle incoming message from UI"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            payload = data.get("payload", {})

            if msg_type == "move_robot":
                await self._handle_move(payload)
            elif msg_type == "move_arm":
                await self._handle_arm(payload)
            elif msg_type == "emergency_stop":
                await self._handle_estop(payload)
            elif msg_type == "select_robot":
                await self._handle_select(payload)
            else:
                logger.warning(f"Unknown message type: {msg_type}")

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON: {message}")

    async def _handle_move(self, payload: dict):
        robot_id = payload.get("robotId")
        direction = payload.get("direction")
        logger.info(f"Move {robot_id} {direction}")
        # TODO: Forward to ROC coordinator
        # await self.roc_coordinator.move_robot(robot_id, direction)

    async def _handle_arm(self, payload: dict):
        robot_id = payload.get("robotId")
        joint = payload.get("joint")
        delta = payload.get("delta")
        logger.info(f"Arm {robot_id} joint {joint} delta {delta}")
        # TODO: Forward to ROC coordinator

    async def _handle_estop(self, payload: dict):
        robot_id = payload.get("robotId")
        logger.warning(f"EMERGENCY STOP: {robot_id or 'ALL'}")
        # TODO: Forward to ROC coordinator

    async def _handle_select(self, payload: dict):
        robot_id = payload.get("robotId")
        logger.info(f"Selected robot: {robot_id}")

    async def _get_robot_list(self) -> list:
        """Get list of robots from ROC coordinator"""
        # TODO: Get from actual ROC
        return [
            {"id": "ROBOT-01", "name": "Alpha Scout", "status": "online", 
             "battery": 87, "temperature": 45},
            {"id": "ROBOT-02", "name": "Beta Heavy", "status": "online",
             "battery": 72, "temperature": 52},
        ]

    async def handler(self, websocket, path):
        await self.register(websocket)
        try:
            async for message in websocket:
                await self.handle_message(websocket, message)
        finally:
            await self.unregister(websocket)

    async def start(self):
        logger.info(f"Starting ROC UI Server on ws://{self.host}:{self.port}")
        async with websockets.serve(self.handler, self.host, self.port):
            await asyncio.Future()  # Run forever


async def main():
    logging.basicConfig(level=logging.INFO)
    server = ROCUIServer()
    await server.start()


if __name__ == "__main__":
    asyncio.run(main())
```

---

### Step 5: UE5 Web Browser Widget Setup

In UE5:

1. **Create Widget Blueprint:**
   - Right-click Content Browser → User Interface → Widget Blueprint
   - Name: `WBP_ROCUI`

2. **Add Web Browser:**
   - In Designer, add "Web Browser" widget
   - Set Anchors to fill entire screen
   - Initial URL: `http://localhost:5173` (dev) or `http://localhost:3000` (prod)

3. **Widget Blueprint Code (optional):**
```cpp
// In your C++ code or Blueprint
void UROCUIWidget::NativeConstruct()
{
    Super::NativeConstruct();
    
    if (WebBrowser)
    {
        // For development (Vite dev server)
        WebBrowser->LoadURL(TEXT("http://localhost:5173"));
        
        // For production (built files)
        // WebBrowser->LoadURL(TEXT("file:///D:/ROA/UI/dist/index.html"));
    }
}
```

---

## Phase 2: Native UMG Widgets (Future)

If you need native performance, convert key components to C++:

### Component Mapping:

| React Component | UMG Widget |
|-----------------|------------|
| `MovementControls` | `UROCMovementWidget` |
| `ArmControls` | `UROCArmWidget` |
| `RobotHealth` | `UROCHealthWidget` |
| `ControlSliders` | `UROCSliderWidget` |

### Example C++ Widget:

```cpp
// ROCMovementWidget.h
UCLASS()
class UROCMovementWidget : public UUserWidget
{
    GENERATED_BODY()

public:
    UPROPERTY(meta = (BindWidget))
    UButton* ButtonW;
    
    UPROPERTY(meta = (BindWidget))
    UButton* ButtonA;
    
    UPROPERTY(meta = (BindWidget))
    UButton* ButtonS;
    
    UPROPERTY(meta = (BindWidget))
    UButton* ButtonD;

protected:
    virtual void NativeConstruct() override;
    
    UFUNCTION()
    void OnForwardPressed();
    
    UFUNCTION()
    void OnBackPressed();
    
    // ... etc
};
```

---

## File Structure After Preparation

```
ROC_UI/
├── dist/                      # Production build (after npm run build)
│   ├── index.html
│   ├── assets/
│   └── ...
├── src/
│   ├── App.tsx               # Updated with bridge
│   ├── hooks/
│   │   └── useROCBridge.ts   # NEW: WebSocket bridge
│   ├── components/
│   │   ├── MovementControls.tsx
│   │   ├── ArmControls.tsx
│   │   ├── RobotHealth.tsx
│   │   └── ...
│   └── types/
│       └── roc.ts            # NEW: TypeScript types
├── UE5_INTEGRATION_GUIDE.md  # This file
└── package.json
```

---

## Testing Without UE5

1. **Run React dev server:**
   ```bash
   cd ROC_UI
   npm run dev
   ```

2. **Run Python WebSocket server:**
   ```bash
   python roc_ui_server.py
   ```

3. **Open browser:**
   - `http://localhost:5173`
   - Press WASD/Arrow keys
   - Check console for commands being sent

---

## Summary Checklist

### Before UE5 Integration:

- [ ] Add `useROCBridge.ts` hook
- [ ] Update `App.tsx` with real commands
- [ ] Add connection status indicator
- [ ] Create `roc_ui_server.py` WebSocket server
- [ ] Add TypeScript types for messages
- [ ] Test locally with mock data
- [ ] Build production bundle (`npm run build`)
- [ ] Document WebSocket protocol

### For UE5 Integration:

- [ ] Create Widget Blueprint with Web Browser
- [ ] Configure URL (dev or production)
- [ ] Handle keyboard focus (UI vs game)
- [ ] Connect ROC Python to UI server
- [ ] Test full loop: UI → WebSocket → ROC → UE5

---

## WebSocket Message Protocol

### From UI → Backend:

```json
// Move robot
{"type": "move_robot", "payload": {"robotId": "ROBOT-01", "direction": "forward"}}

// Move arm joint
{"type": "move_arm", "payload": {"robotId": "ROBOT-01", "joint": 0, "delta": 5}}

// Emergency stop
{"type": "emergency_stop", "payload": {"robotId": "ROBOT-01"}}

// Select robot
{"type": "select_robot", "payload": {"robotId": "ROBOT-01"}}
```

### From Backend → UI:

```json
// Single robot state update
{"type": "robot_state", "payload": {
  "id": "ROBOT-01",
  "name": "Alpha Scout",
  "status": "online",
  "battery": 87,
  "temperature": 45,
  "joints": [0, 45, 90, 0, 0, 0]
}}

// Full robot list
{"type": "robot_list", "payload": [
  {"id": "ROBOT-01", "name": "Alpha Scout", ...},
  {"id": "ROBOT-02", "name": "Beta Heavy", ...}
]}
```
