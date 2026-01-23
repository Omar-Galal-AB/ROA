/**
 * ROC TypeScript Type Definitions
 * Shared types between React UI and Python backend
 */

// ==================== Robot Types ====================

export type RobotStatus = 'online' | 'warning' | 'offline' | 'emergency';

export type ControlMode = 'RPM' | 'ADM';  // Role-Playing Mode / Auto-Driven Mode

export type RobotType = 'arm' | 'mobile' | 'hybrid' | 'drone';

export interface Vector3 {
  x: number;
  y: number;
  z: number;
}

export interface Rotation3 {
  roll: number;   // X-axis rotation
  pitch: number;  // Y-axis rotation
  yaw: number;    // Z-axis rotation
}

export interface JointState {
  index: number;
  name: string;
  angle: number;      // Current angle in degrees
  minAngle: number;   // Joint limit min
  maxAngle: number;   // Joint limit max
  velocity: number;   // Current velocity
  torque: number;     // Current torque
}

export interface RobotState {
  // Identity
  id: string;
  name: string;
  type: RobotType;
  
  // Status
  status: RobotStatus;
  controlMode: ControlMode;
  isSelected: boolean;
  
  // Health
  heartbeat: number;      // 0-100 health score
  battery: number;        // 0-100 percentage
  temperature: number;    // Celsius
  errors: number;         // Error count
  warnings: number;       // Warning count
  
  // Position
  position: Vector3;
  rotation: Rotation3;
  velocity: number;       // m/s
  
  // Arm state (if applicable)
  joints?: JointState[];
  gripperStrength?: number;  // 0-100
  
  // Metadata
  lastHeartbeat: number;  // Unix timestamp
  uptime: number;         // Seconds
}

// ==================== Command Types ====================

export type MoveDirection = 'forward' | 'back' | 'left' | 'right' | 'stop';

export interface MoveCommand {
  robotId: string;
  direction: MoveDirection;
  speed: number;  // 0.0 - 1.0
}

export interface ArmCommand {
  robotId: string;
  joint: number;
  delta?: number;   // Relative movement
  angle?: number;   // Absolute position
}

export interface GripperCommand {
  robotId: string;
  strength: number;  // 0-100
  action?: 'open' | 'close' | 'set';
}

export interface EmergencyStopCommand {
  robotId?: string;  // undefined = ALL robots
  reason?: string;
}

export interface ModeChangeCommand {
  robotId: string;
  mode: ControlMode;
}

// ==================== Message Types ====================

export type MessageType = 
  // UI → Backend
  | 'move_robot'
  | 'move_arm'
  | 'set_joint'
  | 'set_gripper'
  | 'emergency_stop'
  | 'select_robot'
  | 'set_mode'
  | 'get_robots'
  | 'ping'
  // Backend → UI
  | 'robot_state'
  | 'robot_list'
  | 'robot_removed'
  | 'command_ack'
  | 'error'
  | 'pong';

export interface ROCMessage<T = any> {
  type: MessageType;
  payload: T;
  timestamp: number;
  requestId?: string;
}

// ==================== UI State Types ====================

export interface UIState {
  selectedRobotId: string | null;
  pressedKeys: Set<string>;
  controlMode: ControlMode;
  showDebug: boolean;
}

export interface PanelConfig {
  visible: boolean;
  position: { x: number; y: number };
  collapsed: boolean;
}

export interface UIConfig {
  panels: {
    movement: PanelConfig;
    arm: PanelConfig;
    health: PanelConfig;
    commands: PanelConfig;
    hardware: PanelConfig;
  };
  theme: 'dark' | 'light';
  keyBindings: Record<string, string>;
}

// ==================== Safety Types ====================

export type SafetyLevel = 'normal' | 'caution' | 'warning' | 'critical';

export interface SafetyAlert {
  id: string;
  robotId: string;
  level: SafetyLevel;
  message: string;
  timestamp: number;
  acknowledged: boolean;
}

export interface ObstacleInfo {
  distance: number;      // Meters
  direction: Vector3;    // Unit vector
  objectType?: string;   // Type of obstacle
}

// ==================== Event Types ====================

export interface RobotEvent {
  type: 'status_change' | 'error' | 'warning' | 'collision' | 'task_complete';
  robotId: string;
  message: string;
  data?: any;
  timestamp: number;
}
