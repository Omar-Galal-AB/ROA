import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * ROC Bridge Hook
 * Connects React UI to ROC backend (Python/UE5) via WebSocket
 */

// Message types from/to backend
export interface ROCMessage {
  type: string;
  payload: any;
  timestamp?: number;
}

// Robot state from backend
export interface RobotState {
  id: string;
  name: string;
  status: 'online' | 'warning' | 'offline';
  battery: number;
  temperature: number;
  heartbeat: number;
  errors: number;
  position?: { x: number; y: number; z: number };
  rotation?: { roll: number; pitch: number; yaw: number };
  joints?: number[];
  velocity?: number;
}

// Control command types
export type MoveDirection = 'forward' | 'back' | 'left' | 'right' | 'stop';

interface UseROCBridgeOptions {
  serverUrl?: string;
  autoReconnect?: boolean;
  reconnectInterval?: number;
}

export function useROCBridge(options: UseROCBridgeOptions = {}) {
  const {
    serverUrl = 'ws://localhost:9878',
    autoReconnect = true,
    reconnectInterval = 3000
  } = options;

  const [connected, setConnected] = useState(false);
  const [robots, setRobots] = useState<RobotState[]>([]);
  const [selectedRobotId, setSelectedRobotId] = useState<string | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Connect to WebSocket server
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const socket = new WebSocket(serverUrl);
      wsRef.current = socket;

      socket.onopen = () => {
        console.log('[ROC Bridge] Connected to', serverUrl);
        setConnected(true);
        setLastError(null);
        
        // Request robot list on connect
        socket.send(JSON.stringify({ type: 'get_robots', payload: {} }));
      };

      socket.onmessage = (event) => {
        try {
          const msg: ROCMessage = JSON.parse(event.data);
          handleMessage(msg);
        } catch (e) {
          console.error('[ROC Bridge] Parse error:', e);
        }
      };

      socket.onclose = () => {
        console.log('[ROC Bridge] Disconnected');
        setConnected(false);
        wsRef.current = null;

        // Auto-reconnect
        if (autoReconnect) {
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log('[ROC Bridge] Attempting reconnect...');
            connect();
          }, reconnectInterval);
        }
      };

      socket.onerror = (error) => {
        console.error('[ROC Bridge] Error:', error);
        setLastError('Connection error');
      };

    } catch (e) {
      console.error('[ROC Bridge] Failed to connect:', e);
      setLastError('Failed to connect');
    }
  }, [serverUrl, autoReconnect, reconnectInterval]);

  // Handle incoming messages
  const handleMessage = useCallback((msg: ROCMessage) => {
    switch (msg.type) {
      case 'robot_state':
        // Update single robot state
        setRobots(prev => {
          const idx = prev.findIndex(r => r.id === msg.payload.id);
          if (idx >= 0) {
            const updated = [...prev];
            updated[idx] = { ...updated[idx], ...msg.payload };
            return updated;
          } else {
            return [...prev, msg.payload];
          }
        });
        break;

      case 'robot_list':
        // Replace entire robot list
        setRobots(msg.payload);
        break;

      case 'robot_removed':
        // Remove robot from list
        setRobots(prev => prev.filter(r => r.id !== msg.payload.id));
        break;

      case 'command_ack':
        // Command acknowledged
        console.log('[ROC Bridge] Command acknowledged:', msg.payload);
        break;

      case 'error':
        console.error('[ROC Bridge] Server error:', msg.payload);
        setLastError(msg.payload.message);
        break;

      default:
        console.log('[ROC Bridge] Unknown message type:', msg.type);
    }
  }, []);

  // Send message to backend
  const sendMessage = useCallback((type: string, payload: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type,
        payload,
        timestamp: Date.now()
      }));
      return true;
    }
    console.warn('[ROC Bridge] Not connected, cannot send:', type);
    return false;
  }, []);

  // ==================== Control Commands ====================

  // Move robot (wheels/legs)
  const moveRobot = useCallback((direction: MoveDirection, speed: number = 1.0) => {
    if (!selectedRobotId) {
      console.warn('[ROC Bridge] No robot selected');
      return false;
    }
    return sendMessage('move_robot', {
      robotId: selectedRobotId,
      direction,
      speed
    });
  }, [selectedRobotId, sendMessage]);

  // Move specific robot (override selection)
  const moveRobotById = useCallback((robotId: string, direction: MoveDirection, speed: number = 1.0) => {
    return sendMessage('move_robot', { robotId, direction, speed });
  }, [sendMessage]);

  // Move arm joint
  const moveArm = useCallback((joint: number, delta: number) => {
    if (!selectedRobotId) {
      console.warn('[ROC Bridge] No robot selected');
      return false;
    }
    return sendMessage('move_arm', {
      robotId: selectedRobotId,
      joint,
      delta
    });
  }, [selectedRobotId, sendMessage]);

  // Set joint position directly
  const setJointPosition = useCallback((joint: number, angle: number) => {
    if (!selectedRobotId) return false;
    return sendMessage('set_joint', {
      robotId: selectedRobotId,
      joint,
      angle
    });
  }, [selectedRobotId, sendMessage]);

  // Emergency stop
  const emergencyStop = useCallback((robotId?: string) => {
    return sendMessage('emergency_stop', {
      robotId: robotId || selectedRobotId || 'ALL'
    });
  }, [selectedRobotId, sendMessage]);

  // Select robot
  const selectRobot = useCallback((robotId: string) => {
    setSelectedRobotId(robotId);
    sendMessage('select_robot', { robotId });
  }, [sendMessage]);

  // Set control mode (RPM/ADM)
  const setControlMode = useCallback((mode: 'RPM' | 'ADM') => {
    if (!selectedRobotId) return false;
    return sendMessage('set_mode', {
      robotId: selectedRobotId,
      mode
    });
  }, [selectedRobotId, sendMessage]);

  // Gripper control
  const setGripper = useCallback((strength: number) => {
    if (!selectedRobotId) return false;
    return sendMessage('set_gripper', {
      robotId: selectedRobotId,
      strength: Math.max(0, Math.min(100, strength))
    });
  }, [selectedRobotId, sendMessage]);

  // Get current selected robot data
  const selectedRobot = robots.find(r => r.id === selectedRobotId) || null;

  // Connect on mount
  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  return {
    // Connection state
    connected,
    lastError,
    connect,

    // Robot data
    robots,
    selectedRobot,
    selectedRobotId,

    // Control functions
    selectRobot,
    moveRobot,
    moveRobotById,
    moveArm,
    setJointPosition,
    emergencyStop,
    setControlMode,
    setGripper,

    // Raw message sending
    sendMessage
  };
}
