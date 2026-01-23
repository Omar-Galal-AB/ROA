"""
ROC (Robot Operator Controller) - Main ROS2 Node

This is the main entry point for the Robot Operator Controller component.
It manages robot control in both RPM (Role Playing Mode) and ADM (Auto Driven Mode).

Author: ROA Development Team
Date: 2025-11-16
"""

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy
from enum import Enum
import yaml
import os
from pathlib import Path

# Import integration handlers
from integration_handlers import (
    FTIIntegrationHandler,
    DIMCIntegrationHandler,
    COMCIntegrationHandler,
    WebthreadIntegrationHandler
)


class ROCState(Enum):
    """ROC component states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    IDLE = "idle"
    RPM_ACTIVE = "rpm_active"
    ADM_ACTIVE = "adm_active"
    MOVING = "moving"
    EXECUTING = "executing"
    ERROR = "error"
    RESET = "reset"
    CHECK = "check"
    SHUTDOWN = "shutdown"


class ControlMode(Enum):
    """Robot control modes"""
    RPM = "RPM"  # Role Playing Mode - Direct manual control
    ADM = "ADM"  # Auto Driven Mode - Strategic autonomous control


class SafetyLevel(Enum):
    """Safety levels for robot operation"""
    FRAGILE = "Fragile"     # 60% speed, 10mm margin
    STANDARD = "Standard"   # 100% speed, 5mm margin
    ROBUST = "Robust"       # 120% speed, 2mm margin


class ROCNode(Node):
    """
    Robot Operator Controller - Main ROS2 Node
    
    Manages universal robot control with dual modes (RPM/ADM),
    multi-robot support, safety system, and path planning.
    """
    
    def __init__(self):
        super().__init__('robot_operator_controller')
        
        # Node initialization
        self.get_logger().info("Initializing Robot Operator Controller (ROC)...")
        
        # State management
        self.state = ROCState.DISCONNECTED
        self.control_mode = ControlMode.RPM
        self.safety_level = SafetyLevel.STANDARD
        
        # Robot management
        self.robots = {}  # robot_id -> robot_info
        self.active_robot = None
        
        # Configuration
        self.config = self._load_config()
        
        # Callback groups for parallel processing
        self.control_group = MutuallyExclusiveCallbackGroup()
        self.sensor_group = ReentrantCallbackGroup()
        self.service_group = MutuallyExclusiveCallbackGroup()
        
        # QoS profiles
        self.reliable_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            depth=10
        )
        
        self.sensor_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            durability=QoSDurabilityPolicy.VOLATILE,
            depth=1
        )
        
        # Initialize integration handlers
        self._init_integration_handlers()
        
        # Initialize components
        self._init_publishers()
        self._init_subscribers()
        self._init_services()
        self._init_timers()
        
        # Control loop
        self.update_rate = self.config.get('control', {}).get('update_rate', 60)
        self.control_timer = self.create_timer(
            1.0 / self.update_rate,
            self._control_loop,
            callback_group=self.control_group
        )
        
        # Transition to connecting state
        self._transition_state(ROCState.CONNECTING)
        self.get_logger().info("ROC Node initialized successfully")
    
    def _load_config(self):
        """Load ROC configuration from YAML file"""
        config_path = Path(__file__).parent.parent.parent / 'Config' / 'roc_config.yaml'
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                self.get_logger().info(f"Loaded configuration from {config_path}")
                return config.get('roc', {})
        else:
            self.get_logger().warn(f"Config file not found: {config_path}, using defaults")
            return self._default_config()
    
    def _default_config(self):
        """Default configuration if file not found"""
        return {
            'node_name': 'robot_operator_controller',
            'update_rate': 60,
            'control': {
                'latency_target': 20,
                'max_robots': 8,
                'default_mode': 'RPM'
            },
            'safety': {
                'default_level': 'Standard',
                'emergency_stop_decel': 2.0,
                'collision_check_rate': 60
            },
            'path_planning': {
                'algorithm': 'A*',
                'max_planning_time': 5.0,
                'replanning_rate': 2
            },
            'ui': {
                'interface_type': 'standalone',
                'update_rate': 30,
                'show_overlay': True
            }
        }
    
    def _init_integration_handlers(self):
        """Initialize integration handlers for other components"""
        self.get_logger().info("Initializing integration handlers...")
        
        # FTI Integration - Robot specifications
        self.fti_handler = FTIIntegrationHandler(
            self,
            on_robot_specs_callback=self._on_robot_specs_received
        )
        
        # DIMC Integration - Spatial data and obstacles
        self.dimc_handler = DIMCIntegrationHandler(
            self,
            on_spatial_data_callback=self._on_spatial_data_received,
            on_obstacle_callback=self._on_obstacle_detected
        )
        
        # COMC Integration - Multi-robot coordination
        self.comc_handler = COMCIntegrationHandler(
            self,
            on_evasion_response_callback=self._on_evasion_response_received,
            on_coordination_update_callback=self._on_coordination_update_received
        )
        
        # Webthread Integration - System coordination
        self.webthread_handler = WebthreadIntegrationHandler(
            self,
            on_config_update_callback=self._on_config_update_received
        )
        
        self.get_logger().info("Integration handlers initialized successfully")
    
    # Integration handler callbacks
    
    def _on_robot_specs_received(self, robot_spec: dict):
        """
        Callback when robot specifications are received from FTI.
        
        Args:
            robot_spec: Robot specification dictionary
        """
        robot_id = robot_spec.get('robot_id')
        robot_name = robot_spec.get('robot_name')
        
        # Store robot information
        self.robots[robot_id] = {
            'spec': robot_spec,
            'position': None,
            'state': 'idle',
            'mode': None
        }
        
        self.get_logger().info(
            f"Registered robot: {robot_name} ({robot_id}) with {robot_spec.get('dof')} DOF"
        )
        
        # If this is the first robot, make it active
        if self.active_robot is None:
            self.active_robot = robot_id
            self.get_logger().info(f"Set active robot: {robot_id}")
    
    def _on_spatial_data_received(self, spatial_info: dict):
        """
        Callback when spatial data is received from DIMC.
        
        Args:
            spatial_info: Spatial information dictionary
        """
        robot_id = spatial_info.get('robot_id')
        
        if robot_id in self.robots:
            # Update robot position
            self.robots[robot_id]['position'] = spatial_info.get('position')
            self.robots[robot_id]['boundaries'] = spatial_info.get('boundaries')
            
            # Log periodically (not every update to avoid spam)
            # self.get_logger().debug(f"Updated position for {robot_id}")
    
    def _on_obstacle_detected(self, obstacle_info: dict):
        """
        Callback when obstacle is detected by DIMC.
        
        Args:
            obstacle_info: Obstacle information dictionary
        """
        robot_id = obstacle_info.get('robot_id')
        distance = obstacle_info.get('distance')
        
        self.get_logger().warn(
            f"Obstacle detected for {robot_id} at distance {distance:.3f}m"
        )
        
        # TODO: Trigger safety response based on distance
        # - Check against safety level thresholds
        # - Trigger auto-stop if needed
        # - Update UI warnings
    
    def _on_evasion_response_received(self, evasion_response: dict):
        """
        Callback when evasion response is received from COMC.
        
        Args:
            evasion_response: Evasion response dictionary
        """
        robot_id = evasion_response.get('robot_id')
        approved = evasion_response.get('approved')
        path = evasion_response.get('path', [])
        
        if approved:
            self.get_logger().info(
                f"Evasion approved for {robot_id}, path has {len(path)} waypoints"
            )
            # TODO: Update robot path with evasion path
        else:
            self.get_logger().warn(
                f"Evasion denied for {robot_id}, stopping movement"
            )
            # TODO: Stop robot movement
    
    def _on_coordination_update_received(self, coordination_data: dict):
        """
        Callback when coordination update is received from COMC.
        
        Args:
            coordination_data: Coordination update dictionary
        """
        self.get_logger().debug("Received coordination update from COMC")
        # TODO: Process coordination updates (work areas, robot states, etc.)
    
    def _on_config_update_received(self, config_data: dict):
        """
        Callback when configuration update is received from Webthread.
        
        Args:
            config_data: Configuration update dictionary
        """
        self.get_logger().info("Received configuration update from Webthread")
        
        # Update configuration dynamically
        if 'safety_level' in config_data:
            new_level = config_data['safety_level']
            if new_level in ['Fragile', 'Standard', 'Robust']:
                self.safety_level = SafetyLevel(new_level)
                self.get_logger().info(f"Safety level updated to: {new_level}")

    
    def _init_publishers(self):
        """Initialize ROS2 publishers"""
        # Status publisher (1 Hz)
        # self.status_pub = self.create_publisher(
        #     ROCStatus, '/roc/status', self.reliable_qos
        # )
        
        # Robot state publisher (60 Hz)
        # self.robot_state_pub = self.create_publisher(
        #     RobotState, '/roc/robot_state', self.sensor_qos
        # )
        
        # Command feedback publisher (on-event)
        # self.command_feedback_pub = self.create_publisher(
        #     CommandFeedback, '/roc/command_feedback', self.reliable_qos
        # )
        
        self.get_logger().info("Publishers initialized")
    
    def _init_subscribers(self):
        """Initialize ROS2 subscribers"""
        # Robot specifications from FTI (on-import)
        # self.robot_specs_sub = self.create_subscription(
        #     RobotSpecs, '/fti/robot_specs',
        #     self._robot_specs_callback,
        #     self.reliable_qos,
        #     callback_group=self.sensor_group
        # )
        
        # Spatial data from DIMC (60 Hz)
        # self.spatial_data_sub = self.create_subscription(
        #     SpatialData, '/dimc/spatial_data',
        #     self._spatial_data_callback,
        #     self.sensor_qos,
        #     callback_group=self.sensor_group
        # )
        
        # Robot status from COMC (20 Hz)
        # self.robot_status_sub = self.create_subscription(
        #     RobotStatus, '/comc/robot_status',
        #     self._robot_status_callback,
        #     self.sensor_qos,
        #     callback_group=self.sensor_group
        # )
        
        self.get_logger().info("Subscribers initialized")
    
    def _init_services(self):
        """Initialize ROS2 services"""
        # Service to switch control mode (RPM/ADM)
        # self.set_mode_srv = self.create_service(
        #     SetMode, '/roc/set_mode',
        #     self._set_mode_callback,
        #     callback_group=self.service_group
        # )
        
        # Service to change safety level
        # self.set_safety_srv = self.create_service(
        #     SetSafetyLevel, '/roc/set_safety_level',
        #     self._set_safety_callback,
        #     callback_group=self.service_group
        # )
        
        # Service to queue commands
        # self.queue_command_srv = self.create_service(
        #     QueueCommand, '/roc/queue_command',
        #     self._queue_command_callback,
        #     callback_group=self.service_group
        # )
        
        # Emergency stop service
        # self.emergency_stop_srv = self.create_service(
        #     Trigger, '/roc/emergency_stop',
        #     self._emergency_stop_callback,
        #     callback_group=self.service_group
        # )
        
        # Health check service
        # self.health_check_srv = self.create_service(
        #     Trigger, '/roc/health_check',
        #     self._health_check_callback,
        #     callback_group=self.service_group
        # )
        
        self.get_logger().info("Services initialized")
    
    def _init_timers(self):
        """Initialize periodic timers"""
        # Status update timer (1 Hz)
        self.status_timer = self.create_timer(1.0, self._status_update)
        
        # Health check timer (1 Hz)
        self.health_timer = self.create_timer(1.0, self._health_check)
    
    def _control_loop(self):
        """Main control loop - runs at update_rate Hz (default 60 Hz)"""
        if self.state == ROCState.IDLE:
            # Ready but no active commands
            pass
        
        elif self.state == ROCState.RPM_ACTIVE:
            # Execute RPM mode control
            self._execute_rpm_control()
        
        elif self.state == ROCState.ADM_ACTIVE:
            # Execute ADM mode control
            self._execute_adm_control()
        
        elif self.state == ROCState.MOVING or self.state == ROCState.EXECUTING:
            # Robot is executing commands
            self._monitor_execution()
        
        elif self.state == ROCState.ERROR:
            # Error state - attempt recovery
            self._handle_error()
    
    def _execute_rpm_control(self):
        """Execute Role Playing Mode control"""
        # TODO: Implement RPM control logic
        # - Read keyboard/mouse inputs
        # - Translate to robot commands
        # - Apply safety checks
        # - Send to ROS2 Control
        pass
    
    def _execute_adm_control(self):
        """Execute Auto Driven Mode control"""
        # TODO: Implement ADM control logic
        # - Process task queue
        # - Execute path planning
        # - Monitor autonomous execution
        # - Handle re-planning
        pass
    
    def _monitor_execution(self):
        """Monitor command execution"""
        # TODO: Monitor robot movement/task execution
        # - Check if target reached
        # - Monitor for obstacles
        # - Update progress
        pass
    
    def _handle_error(self):
        """Handle error state"""
        # TODO: Implement error recovery
        # - Diagnose error type
        # - Attempt recovery
        # - Reset if needed
        pass
    
    def _status_update(self):
        """Publish status update (1 Hz)"""
        # Publish status to Webthread
        if hasattr(self, 'webthread_handler'):
            self.webthread_handler.publish_status(
                state=self.state.value,
                mode=self.control_mode.value,
                robot_count=len(self.robots),
                safety_level=self.safety_level.value,
                additional_info={
                    'active_robot': self.active_robot
                }
            )
        
        self.get_logger().debug(
            f"ROC Status: {self.state.value}, Mode: {self.control_mode.value}, "
            f"Robots: {len(self.robots)}, Safety: {self.safety_level.value}"
        )
    
    def _health_check(self):
        """Perform health check (1 Hz)"""
        # TODO: Check component health
        # - Verify connections
        # - Check resource usage
        # - Monitor latency
        
        # Transition from CONNECTING to IDLE after initialization
        if self.state == ROCState.CONNECTING:
            self._transition_state(ROCState.IDLE)
    
    def _transition_state(self, new_state: ROCState):
        """Transition to new state with logging"""
        old_state = self.state
        self.state = new_state
        self.get_logger().info(f"State transition: {old_state.value} -> {new_state.value}")
    
    def shutdown(self):
        """Graceful shutdown"""
        self.get_logger().info("Shutting down ROC node...")
        self._transition_state(ROCState.SHUTDOWN)
        
        # Stop control loop
        if hasattr(self, 'control_timer'):
            self.control_timer.cancel()
        
        # Emergency stop all robots
        self._emergency_stop_all()
        
        self.get_logger().info("ROC node shutdown complete")
    
    def _emergency_stop_all(self):
        """Emergency stop for all robots"""
        self.get_logger().warn("Emergency stop triggered for all robots")
        # TODO: Send emergency stop to all robots
        pass


def main(args=None):
    """Main entry point"""
    rclpy.init(args=args)
    
    try:
        # Create node
        roc_node = ROCNode()
        
        # Use multi-threaded executor for parallel callback processing
        executor = MultiThreadedExecutor()
        executor.add_node(roc_node)
        
        try:
            # Spin the executor
            executor.spin()
        except KeyboardInterrupt:
            pass
        finally:
            # Cleanup
            roc_node.shutdown()
            roc_node.destroy_node()
    
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()
