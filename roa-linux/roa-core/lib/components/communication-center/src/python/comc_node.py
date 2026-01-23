"""
COMC Node - Communication Center Main Node

Main ROS2 node for multi-robot coordination and communication.
Integrates all subsystems: work areas, proximity, tasks, evasion, and component integration.

Integrated with ROA Observability Stack for metrics, logging, and tracing.
"""

import os
import sys
import logging

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile
from geometry_msgs.msg import Point, Vector3
from std_msgs.msg import Header, String
import json
import time

# Import Observability
try:
    # Add shared observability to path
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    _shared_path = os.path.abspath(os.path.join(_current_dir, '..', '..', '..', '..', 'shared'))
    if _shared_path not in sys.path:
        sys.path.insert(0, _shared_path)
    
    from observability import (
        ROAObservability,
        ROAMetrics,
        ROATracer,
        ROALogger,
        HealthCheck,
        HealthStatus as ObsHealthStatus,
        ROAEventRecorder,
    )
    OBSERVABILITY_AVAILABLE = True
except ImportError as e:
    logging.debug(f"Observability not available for COMC: {e}")
    OBSERVABILITY_AVAILABLE = False

from .qos_profiles import SAFETY_QOS, COORDINATION_QOS, STATUS_QOS
from .work_area_manager import WorkAreaManager
from .proximity_monitor import ProximityMonitor
from .task_coordinator import TaskCoordinator, TaskStatus
from .evade_coordinator import EvadeCoordinator
from .integration_handlers import (
    DIMCIntegrationHandler,
    WebthreadIntegrationHandler,
    ROCIntegrationHandler,
    FTIIntegrationHandler
)
from .state_machine import COMCStateMachine, ComponentState
from .service_handlers import ServiceHandlers
from .health_monitor import HealthMonitor

# Import HB Agent
try:
    from .comc_hb_agent import COMCHBAgent, ActivityType, ComponentState as HBComponentState
    HB_AGENT_AVAILABLE = True
except ImportError as e:
    logging.debug(f"HB Agent not available for COMC: {e}")
    HB_AGENT_AVAILABLE = False

# Import Bridge Agent
try:
    from .comc_bridge_agent import COMCBridgeAgent, BridgeMode, create_comc_bridge
    BRIDGE_AGENT_AVAILABLE = True
except ImportError as e:
    logging.debug(f"Bridge Agent not available for COMC: {e}")
    BRIDGE_AGENT_AVAILABLE = False

# Import Monitoring System
try:
    from .comc_monitoring import COMCMonitoringSystem
    MONITORING_AVAILABLE = True
except ImportError as e:
    logging.debug(f"Monitoring System not available for COMC: {e}")
    MONITORING_AVAILABLE = False

# Import Resilience Module
try:
    from .comc_resilience import COMCResilienceManager, RecoveryProcedure
    RESILIENCE_AVAILABLE = True
except ImportError as e:
    logging.debug(f"Resilience Module not available for COMC: {e}")
    RESILIENCE_AVAILABLE = False

# Import Emergency Stop System (P0 Gap Fix)
try:
    from .emergency_stop import EmergencyStopSystem, StopReason, StopLevel, EvasionVector
    EMERGENCY_STOP_AVAILABLE = True
except ImportError as e:
    logging.debug(f"Emergency Stop System not available for COMC: {e}")
    EMERGENCY_STOP_AVAILABLE = False

# Import MAPF Solver (P0 Gap Fix)
try:
    from .mapf_solver import MAPFSolver, MAPFRequest, MAPFSolution
    MAPF_AVAILABLE = True
except ImportError as e:
    logging.debug(f"MAPF Solver not available for COMC: {e}")
    MAPF_AVAILABLE = False

# Import Path Conflict Detector (P0 Gap Fix)
try:
    from .path_conflict_detector import PathConflictDetector, ConflictType
    PATH_CONFLICT_AVAILABLE = True
except ImportError as e:
    logging.debug(f"Path Conflict Detector not available for COMC: {e}")
    PATH_CONFLICT_AVAILABLE = False

# Import DIMC Notifier (P1 Gap Fix)
try:
    from .dimc_notifier import DIMCNotifier, RobotPriorityLevel
    DIMC_NOTIFIER_AVAILABLE = True
except ImportError as e:
    logging.debug(f"DIMC Notifier not available for COMC: {e}")
    DIMC_NOTIFIER_AVAILABLE = False


class COMCNode(Node):
    """
    Communication Center Node for multi-robot coordination.
    
    Handles:
    - Work area broadcasting and subscription
    - Proximity monitoring and alerts
    - Task coordination
    - Health monitoring integration with Webthread
    - Observability integration
    """
    
    def __init__(self, enable_obs: bool = True):
        super().__init__('communication_center')
        
        # Declare parameters
        self.declare_parameter('robot_id', 'robot_unknown')
        self.declare_parameter('work_area_update_rate', 20.0)  # Hz
        self.declare_parameter('proximity_update_rate', 60.0)  # Hz
        self.declare_parameter('health_check_rate', 2.0)  # Hz
        
        # Get parameters
        self.robot_id = self.get_parameter('robot_id').value
        work_area_rate = self.get_parameter('work_area_update_rate').value
        proximity_rate = self.get_parameter('proximity_update_rate').value
        health_rate = self.get_parameter('health_check_rate').value
        
        self.get_logger().info(f'COMC Node starting for robot: {self.robot_id}')
        
        # Observability
        self._observability = None
        self._obs_enabled = enable_obs and OBSERVABILITY_AVAILABLE
        
        if self._obs_enabled:
            self._init_observability()
        
        # Initialize managers
        self.work_area_manager = WorkAreaManager(self)
        self.work_area_manager.set_robot_id(self.robot_id)
        
        self.proximity_monitor = ProximityMonitor(self)
        self.proximity_monitor.set_robot_id(self.robot_id)
        
        self.task_coordinator = TaskCoordinator(self)
        self.evade_coordinator = EvadeCoordinator(self)
        
        # Initialize state machine and health monitor
        self.state_machine = COMCStateMachine(self.get_logger())
        self.health_monitor = HealthMonitor()
        
        # Initialize HB Agent for heartbeat subsystem integration
        self._hb_agent = None
        if HB_AGENT_AVAILABLE:
            self._init_hb_agent()
        
        # Initialize Bridge Agent for UE5 communication
        self._bridge_agent = None
        if BRIDGE_AGENT_AVAILABLE:
            self._init_bridge_agent()
        
        # Initialize Monitoring System for comprehensive monitoring
        self._monitoring_system = None
        if MONITORING_AVAILABLE:
            self._init_monitoring_system()
        
        # Initialize Resilience Manager for fault tolerance
        self._resilience_manager = None
        if RESILIENCE_AVAILABLE:
            self._init_resilience_manager()
        
        # Initialize Emergency Stop System (P0 Gap Fix)
        self._emergency_stop = None
        if EMERGENCY_STOP_AVAILABLE:
            self._init_emergency_stop()
        
        # Initialize MAPF Solver (P0 Gap Fix)
        self._mapf_solver = None
        self._path_conflict_detector = None
        if MAPF_AVAILABLE:
            self._init_mapf_solver()
        
        # Initialize DIMC Notifier (P1 Gap Fix)
        self._dimc_notifier = None
        if DIMC_NOTIFIER_AVAILABLE:
            self._init_dimc_notifier()
        
        # Initialize integration handlers
        self.dimc_handler = DIMCIntegrationHandler(
            self, self.proximity_monitor, self.evade_coordinator
        )
        self.webthread_handler = WebthreadIntegrationHandler(self)
        self.roc_handler = ROCIntegrationHandler(self, self.evade_coordinator)
        self.fti_handler = FTIIntegrationHandler(self)
        
        # Initialize service handlers
        self.service_handlers = ServiceHandlers(
            self, self.task_coordinator, self.work_area_manager, self.proximity_monitor
        )
        
        # Publishers
        self.work_area_pub = self.create_publisher(
            String,  # Using String with JSON until custom messages are built
            '/robots/work_areas',
            COORDINATION_QOS
        )
        
        self.proximity_alert_pub = self.create_publisher(
            String,  # Using String with JSON until custom messages are built
            '/robots/proximity_alert',
            SAFETY_QOS
        )
        
        self.status_pub = self.create_publisher(
            String,
            f'/comc/{self.robot_id}/status',
            STATUS_QOS
        )
        
        # Subscribers
        self.work_area_sub = self.create_subscription(
            String,
            '/robots/work_areas',
            self.work_area_callback,
            COORDINATION_QOS
        )
        
        # Subscribe to robot positions from DIMC
        self.position_sub = self.create_subscription(
            String,
            f'/robot/{self.robot_id}/pose',
            self.position_callback,
            10
        )
        
        # Timers
        self.work_area_timer = self.create_timer(
            1.0 / work_area_rate,
            self.publish_work_area
        )
        
        self.proximity_timer = self.create_timer(
            1.0 / proximity_rate,
            self.check_proximity
        )
        
        self.health_timer = self.create_timer(
            1.0 / health_rate,
            self.publish_health_status
        )
        
        self.cleanup_timer = self.create_timer(
            5.0,  # Every 5 seconds
            self.cleanup_stale_data
        )
        
        # Deadlock detection timer
        self.deadlock_timer = self.create_timer(
            2.0,  # Every 2 seconds
            self.check_deadlocks
        )
        
        # Transition to IDLE state (connected and ready)
        self.state_machine.transition_to(ComponentState.IDLE)
        
        # Notify HB Agent of state transition
        if self._hb_agent:
            self._hb_agent.report_state_transition("INITIALIZING", "IDLE")
        
        # Start observability and mark healthy
        if self._obs_enabled and self._observability:
            self._observability.start()
            self._observability.health.set_healthy()
            self._observability.logger.info("COMC Node started", 
                extra={"component": "comc", "robot_id": self.robot_id, "action": "start"})
        
        self.get_logger().info('COMC Node initialized successfully')
    
    def _init_observability(self):
        """Initialize ROA Observability for COMC"""
        try:
            self._observability = ROAObservability(
                component_name="comc",
                service_version="1.0.0",
                auto_start=False,
            )
            
            # Register COMC-specific metrics
            self._register_comc_metrics()
            
            self.get_logger().info("COMC Observability initialized")
        except Exception as e:
            self.get_logger().warning(f"Failed to initialize COMC Observability: {e}")
            self._observability = None
            self._obs_enabled = False
    
    def _init_hb_agent(self):
        """Initialize HB (Heartbeat) Agent for health monitoring integration"""
        try:
            self._hb_agent = COMCHBAgent(
                receiver_host='127.0.0.1',
                logger=self.get_logger()
            )
            
            # Register callbacks for autonomous mode
            self._hb_agent.on_autonomous_mode(self._on_hb_autonomous_mode)
            self._hb_agent.on_connection_lost(self._on_hb_connection_lost)
            self._hb_agent.on_connection_restored(self._on_hb_connection_restored)
            
            # Start the HB agent
            if self._hb_agent.start():
                self.get_logger().info("COMC HB Agent started (port 9880)")
            else:
                self.get_logger().warning("COMC HB Agent failed to connect (running standalone)")
                
        except Exception as e:
            self.get_logger().warning(f"Failed to initialize COMC HB Agent: {e}")
            self._hb_agent = None
    
    def _init_bridge_agent(self):
        """Initialize Bridge Agent for UE5 communication"""
        try:
            self._bridge_agent = create_comc_bridge(
                prefer_webthread=True,
                logger=self.get_logger()
            )
            
            # Register callbacks for UE5 events
            self._bridge_agent.on_robot_spawned(self._on_ue5_robot_spawned)
            self._bridge_agent.on_robot_removed(self._on_ue5_robot_removed)
            self._bridge_agent.on_collision_detected(self._on_ue5_collision_detected)
            
            # Start the bridge agent
            if self._bridge_agent.start():
                self.get_logger().info(f"COMC Bridge Agent started (mode: {self._bridge_agent.mode.value})")
            else:
                self.get_logger().warning("COMC Bridge Agent failed to connect")
                
        except Exception as e:
            self.get_logger().warning(f"Failed to initialize COMC Bridge Agent: {e}")
            self._bridge_agent = None
    
    def _on_hb_autonomous_mode(self):
        """Called when Webthread becomes unreachable"""
        self.get_logger().warning("HB: Entering autonomous mode - Webthread unreachable")
        # Continue operating independently
    
    def _on_hb_connection_lost(self):
        """Called when HB connection to Webthread is lost"""
        self.get_logger().warning("HB: Connection to Webthread lost")
    
    def _on_hb_connection_restored(self):
        """Called when HB connection to Webthread is restored"""
        self.get_logger().info("HB: Connection to Webthread restored")
    
    def _on_ue5_robot_spawned(self, robot_id: str, spawn_data: dict):
        """Handle robot spawn event from UE5"""
        self.get_logger().info(f"UE5: Robot spawned - {robot_id}")
        # Register the spawned robot in proximity monitor
        if spawn_data.get('position'):
            pos = spawn_data['position']
            from geometry_msgs.msg import Point
            point = Point(x=pos.get('x', 0), y=pos.get('y', 0), z=pos.get('z', 0))
            self.proximity_monitor.update_robot_position(robot_id, point)
    
    def _on_ue5_robot_removed(self, robot_id: str):
        """Handle robot removal event from UE5"""
        self.get_logger().info(f"UE5: Robot removed - {robot_id}")
        # Remove from tracking
        self.work_area_manager.remove_robot(robot_id)
    
    def _on_ue5_collision_detected(self, robot1: str, robot2: str, collision_data: dict):
        """Handle collision detection from UE5"""
        self.get_logger().warning(f"UE5: Collision detected between {robot1} and {robot2}")
        # Trigger emergency evasion
        self.evade_coordinator.handle_collision(robot1, robot2, collision_data)
    
    def _init_monitoring_system(self):
        """Initialize comprehensive monitoring system for COMC"""
        try:
            self._monitoring_system = COMCMonitoringSystem(
                robot_id=self.robot_id,
                logger=self.get_logger()
            )
            
            # Configure alert callbacks
            self._monitoring_system.alert_manager.register_callback(
                self._on_monitoring_alert
            )
            
            # Register component connections to monitor
            self._register_monitored_connections()
            
            # Start the monitoring system
            if self._monitoring_system.start():
                self.get_logger().info("COMC Monitoring System started")
            else:
                self.get_logger().warning("COMC Monitoring System failed to start")
                
        except Exception as e:
            self.get_logger().warning(f"Failed to initialize COMC Monitoring System: {e}")
            self._monitoring_system = None
    
    def _init_resilience_manager(self):
        """Initialize resilience manager for fault tolerance"""
        try:
            self._resilience_manager = COMCResilienceManager(
                logger=self.get_logger()
            )
            
            # Register recovery procedures for each component
            self._register_recovery_procedures()
            
            self.get_logger().info("COMC Resilience Manager initialized")
                
        except Exception as e:
            self.get_logger().warning(f"Failed to initialize COMC Resilience Manager: {e}")
            self._resilience_manager = None
    
    def _register_monitored_connections(self):
        """Register component connections for monitoring"""
        if not self._monitoring_system:
            return
            
        # Register each component connection
        component_ports = {
            'dimc': 9800,  # DIMC port
            'roc': 9810,   # ROC port
            'fti': 9820,   # FTI port
            'webthread': 9830,  # Webthread port
            'ue5_bridge': 9840,  # UE5 Bridge port
            'hb_subsystem': 9880,  # HB Subsystem port
        }
        
        for name, port in component_ports.items():
            self._monitoring_system.connection_monitor.register_connection(
                name=name,
                host='127.0.0.1',
                port=port
            )
    
    def _register_recovery_procedures(self):
        """Register automated recovery procedures"""
        if not self._resilience_manager:
            return
            
        # Recovery procedure for HB Agent
        if HB_AGENT_AVAILABLE:
            self._resilience_manager.recovery_manager.register_procedure(
                RecoveryProcedure(
                    name='hb_agent_recovery',
                    condition=lambda: self._hb_agent is None or not self._hb_agent.is_connected,
                    action=self._recover_hb_agent,
                    verify=lambda: self._hb_agent is not None and self._hb_agent.is_connected,
                    cooldown=30.0
                )
            )
        
        # Recovery procedure for Bridge Agent
        if BRIDGE_AGENT_AVAILABLE:
            self._resilience_manager.recovery_manager.register_procedure(
                RecoveryProcedure(
                    name='bridge_agent_recovery',
                    condition=lambda: self._bridge_agent is None or not self._bridge_agent.is_connected,
                    action=self._recover_bridge_agent,
                    verify=lambda: self._bridge_agent is not None and self._bridge_agent.is_connected,
                    cooldown=30.0
                )
            )
    
    def _recover_hb_agent(self):
        """Attempt to recover the HB Agent connection"""
        self.get_logger().info("Attempting to recover HB Agent connection...")
        if self._hb_agent:
            self._hb_agent.stop()
        self._init_hb_agent()
    
    def _recover_bridge_agent(self):
        """Attempt to recover the Bridge Agent connection"""
        self.get_logger().info("Attempting to recover Bridge Agent connection...")
        if self._bridge_agent:
            self._bridge_agent.stop()
        self._init_bridge_agent()
    
    def _on_monitoring_alert(self, alert):
        """Handle alerts from the monitoring system"""
        if alert.severity.value >= 3:  # WARNING or higher
            self.get_logger().warning(
                f"Monitoring Alert [{alert.severity.name}]: {alert.message}"
            )
            
            # Record in observability if available
            if self._obs_enabled and self._observability:
                self._observability.record_event(
                    event_type='monitoring_alert',
                    severity=alert.severity.name,
                    message=alert.message,
                    source=alert.source
                )

    # =========================================================================
    # P0 GAP FIX: Emergency Stop System Integration
    # =========================================================================
    
    def _init_emergency_stop(self):
        """Initialize emergency stop system for safety-critical situations"""
        try:
            self._emergency_stop = EmergencyStopSystem(
                robot_interface=None,  # Will be set when robot interface is available
                logger=self.get_logger()
            )
            
            # Register this robot
            self._emergency_stop.register_robot(self.robot_id)
            
            # Register callbacks
            self._emergency_stop.stop_callbacks.append(self._on_emergency_stop)
            self._emergency_stop.resume_callbacks.append(self._on_emergency_resume)
            
            self.get_logger().info("Emergency Stop System initialized")
            
        except Exception as e:
            self.get_logger().warning(f"Failed to initialize Emergency Stop System: {e}")
            self._emergency_stop = None
    
    def _on_emergency_stop(self, robot_id: str, reason, level):
        """Handle emergency stop event"""
        self.get_logger().error(f"EMERGENCY STOP: {robot_id} - Reason: {reason.value}, Level: {level.value}")
        
        # Report to HB agent
        if self._hb_agent:
            self._hb_agent.report_state_transition(
                self.state_machine.get_state().name, "EMERGENCY_STOPPED"
            )
        
        # Record in monitoring
        if self._monitoring_system:
            self._monitoring_system.alert_manager.raise_alert(
                source='emergency_stop',
                message=f'Emergency stop triggered: {reason.value}',
                severity_level=4  # CRITICAL
            )
    
    def _on_emergency_resume(self, robot_id: str):
        """Handle emergency resume event"""
        self.get_logger().info(f"Emergency Stop RESUMED: {robot_id}")
        
        # Report to HB agent
        if self._hb_agent:
            self._hb_agent.report_state_transition(
                "EMERGENCY_STOPPED", self.state_machine.get_state().name
            )
    
    def trigger_emergency_stop(self, reason: str = "manual", level: str = "hard"):
        """
        Public API to trigger emergency stop for this robot.
        
        Args:
            reason: Stop reason (manual, proximity, collision, etc.)
            level: Stop level (soft, hard, emergency)
        """
        if not self._emergency_stop:
            self.get_logger().error("Emergency Stop System not available!")
            return False
        
        reason_enum = StopReason[reason.upper()] if hasattr(StopReason, reason.upper()) else StopReason.MANUAL
        level_enum = StopLevel[level.upper()] if hasattr(StopLevel, level.upper()) else StopLevel.HARD
        
        return self._emergency_stop.emergency_stop(
            self.robot_id, reason_enum, level_enum
        )
    
    def resume_from_emergency(self):
        """Public API to resume from emergency stop"""
        if not self._emergency_stop:
            return False
        return self._emergency_stop.resume(self.robot_id)

    # =========================================================================
    # P0 GAP FIX: MAPF Solver Integration
    # =========================================================================
    
    def _init_mapf_solver(self):
        """Initialize MAPF solver for multi-agent path finding"""
        try:
            self._mapf_solver = MAPFSolver(
                logger=self.get_logger()
            )
            
            # Initialize path conflict detector
            if PATH_CONFLICT_AVAILABLE:
                self._path_conflict_detector = PathConflictDetector(
                    logger=self.get_logger()
                )
            
            # Connect MAPF solver to evade coordinator
            self.evade_coordinator.set_mapf_solver(self._mapf_solver)
            if self._path_conflict_detector:
                self.evade_coordinator.set_path_conflict_detector(self._path_conflict_detector)
            
            self.get_logger().info("MAPF Solver initialized")
            
        except Exception as e:
            self.get_logger().warning(f"Failed to initialize MAPF Solver: {e}")
            self._mapf_solver = None
    
    def request_mapf_solution(self, robot_starts: dict, robot_goals: dict, 
                               priorities: dict = None) -> dict:
        """
        Public API to request MAPF solution for multiple robots.
        
        Args:
            robot_starts: Dict of robot_id -> (x, y) start positions
            robot_goals: Dict of robot_id -> (x, y) goal positions
            priorities: Optional dict of robot_id -> priority
            
        Returns:
            Dict with solution paths or error message
        """
        if not self._mapf_solver:
            return {'success': False, 'error': 'MAPF Solver not available'}
        
        try:
            request = MAPFRequest(
                robot_starts=robot_starts,
                robot_goals=robot_goals,
                robot_priorities=priorities or {}
            )
            solution = self._mapf_solver.solve(request)
            return {
                'success': solution.success,
                'paths': {rid: [(p.x, p.y, p.time) for p in path.waypoints] 
                          for rid, path in solution.paths.items()},
                'makespan': solution.makespan,
                'solve_time': solution.solve_time
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # =========================================================================
    # P1 GAP FIX: DIMC Notifier Integration
    # =========================================================================
    
    def _init_dimc_notifier(self):
        """Initialize DIMC notifier for coordination state updates"""
        try:
            self._dimc_notifier = DIMCNotifier(
                node=self,
                logger=self.get_logger(),
                use_direct_api=False  # Use ROS2 topics
            )
            
            self.get_logger().info("DIMC Notifier initialized")
            
        except Exception as e:
            self.get_logger().warning(f"Failed to initialize DIMC Notifier: {e}")
            self._dimc_notifier = None
    
    def notify_dimc_priority_change(self, robot_id: str, priority: int):
        """
        Notify DIMC of robot priority change for sensing optimization.
        
        Args:
            robot_id: Robot whose priority changed
            priority: New priority level (1=critical, 10=minimal)
        """
        if self._dimc_notifier:
            priority_level = RobotPriorityLevel(min(max(priority, 1), 10))
            self._dimc_notifier.set_robot_priority(robot_id, priority_level)
    
    def notify_dimc_zone_config(self, zone_id: str, bounds: dict, enhanced: bool):
        """
        Notify DIMC of monitoring zone configuration.
        
        Args:
            zone_id: Zone identifier
            bounds: Zone bounds (min_x, max_x, min_y, max_y, min_z, max_z)
            enhanced: Whether enhanced monitoring is needed
        """
        if self._dimc_notifier:
            self._dimc_notifier.set_monitoring_zone(zone_id, bounds, enhanced)

    def _register_comc_metrics(self):
        """Register COMC-specific observability metrics"""
        if not self._observability:
            return
        
        metrics = self._observability.metrics
        
        # Message metrics
        self._messages_sent = metrics.register_counter(
            'comc_messages_sent_total',
            'Total messages sent',
            ['topic', 'type'],
        )
        
        self._messages_received = metrics.register_counter(
            'comc_messages_received_total',
            'Total messages received',
            ['topic', 'type'],
        )
        
        # Proximity metrics
        self._proximity_alerts = metrics.register_counter(
            'comc_proximity_alerts_total',
            'Total proximity alerts triggered',
            ['severity'],
        )
        
        self._known_robots = metrics.register_gauge(
            'comc_known_robots',
            'Number of known robots in the system',
        )
        
        # Task metrics
        self._active_tasks = metrics.register_gauge(
            'comc_active_tasks',
            'Number of active tasks',
        )
        
        self._tasks_completed = metrics.register_counter(
            'comc_tasks_completed_total',
            'Total tasks completed',
            ['status'],
        )
        
        # Evade metrics
        self._evade_maneuvers = metrics.register_counter(
            'comc_evade_maneuvers_total',
            'Total evade maneuvers triggered',
            ['type'],
        )
        
        # State machine metrics
        self._state_transitions = metrics.register_counter(
            'comc_state_transitions_total',
            'Total state transitions',
            ['from_state', 'to_state'],
        )
        
    def position_callback(self, msg: String):
        """
        Callback for robot position updates from DIMC.
        
        Args:
            msg: Position message (JSON format)
        """
        try:
            data = json.loads(msg.data)
            robot_id = data.get('robot_id', self.robot_id)
            
            position = Point()
            position.x = data.get('x', 0.0)
            position.y = data.get('y', 0.0)
            position.z = data.get('z', 0.0)
            
            self.proximity_monitor.update_robot_position(robot_id, position)
            
            # Update velocity if available
            if 'vx' in data:
                velocity = Point()
                velocity.x = data.get('vx', 0.0)
                velocity.y = data.get('vy', 0.0)
                velocity.z = data.get('vz', 0.0)
                self.proximity_monitor.update_robot_velocity(robot_id, velocity)
            
            # Record in monitoring system
            if self._monitoring_system:
                self._monitoring_system.message_flow_monitor.record_message(
                    topic='robot_positions',
                    direction='received'
                )
                self._monitoring_system.fleet_monitor.record_robot_activity(robot_id)
                self._monitoring_system.connection_monitor.record_activity('dimc')
            
            # Report activity to HB agent
            if self._hb_agent:
                self._hb_agent.report_data_received(source=f"DIMC:{robot_id}")
                
        except json.JSONDecodeError as e:
            self.get_logger().error(f'Failed to parse position message: {e}')
            if self._hb_agent:
                self._hb_agent.report_error(e)
            # Record error in monitoring
            if self._monitoring_system:
                self._monitoring_system.alert_manager.raise_alert(
                    source='position_callback',
                    message=f'JSON parse error: {e}',
                    severity_level=2  # ERROR
                )
            
    def work_area_callback(self, msg: String):
        """
        Callback for work area updates from other robots.
        
        Args:
            msg: Work area message (JSON format)
        """
        try:
            data = json.loads(msg.data)
            robot_id = data.get('robot_id')
            
            # Ignore our own broadcasts
            if robot_id == self.robot_id:
                return
                
            center = Point()
            center.x = data['center']['x']
            center.y = data['center']['y']
            center.z = data['center']['z']
            
            dimensions = Vector3()
            dimensions.x = data['dimensions']['x']
            dimensions.y = data['dimensions']['y']
            dimensions.z = data['dimensions']['z']
            
            priority = data.get('priority', 2.0)
            timestamp = data.get('timestamp', time.time())
            
            self.work_area_manager.update_robot_work_area(
                robot_id, center, dimensions, priority, timestamp
            )
            
            # Record in monitoring system
            if self._monitoring_system:
                self._monitoring_system.message_flow_monitor.record_message(
                    topic='work_areas',
                    direction='received'
                )
                self._monitoring_system.fleet_monitor.record_robot_activity(robot_id)
            
            # Report activity to HB agent
            if self._hb_agent:
                self._hb_agent.report_message_processed(message_id=f"work_area:{robot_id}")
            
            # Check for conflicts
            if self.work_area_manager.check_conflict(robot_id):
                self.get_logger().warn(f'Work area conflict detected with {robot_id}')
                # Record conflict in monitoring
                if self._monitoring_system:
                    self._monitoring_system.anomaly_detector.record_anomaly(
                        'work_area_conflict',
                        f'Conflict with robot {robot_id}'
                    )
                
        except (json.JSONDecodeError, KeyError) as e:
            self.get_logger().error(f'Failed to parse work area message: {e}')
            if self._hb_agent:
                self._hb_agent.report_error(e)
            # Record error in monitoring
            if self._monitoring_system:
                self._monitoring_system.alert_manager.raise_alert(
                    source='work_area_callback',
                    message=f'Parse error: {e}',
                    severity_level=2  # ERROR
                )
            
    def publish_work_area(self):
        """Publish this robot's current work area."""
        if not self.work_area_manager.own_work_area:
            # Report idle state when nothing to publish
            if self._hb_agent:
                self._hb_agent.report_idle("no_work_area")
            return
            
        area = self.work_area_manager.own_work_area
        
        # Create JSON message
        msg_data = {
            'robot_id': self.robot_id,
            'center': {
                'x': area['center'].x,
                'y': area['center'].y,
                'z': area['center'].z
            },
            'dimensions': {
                'x': area['dimensions'].x,
                'y': area['dimensions'].y,
                'z': area['dimensions'].z
            },
            'priority': area['priority'],
            'timestamp': time.time()
        }
        
        msg = String()
        msg.data = json.dumps(msg_data)
        self.work_area_pub.publish(msg)
        
        # Record outgoing message in monitoring
        if self._monitoring_system:
            self._monitoring_system.message_flow_monitor.record_message(
                topic='work_areas',
                direction='sent'
            )
        
        # Report activity to HB agent
        if self._hb_agent:
            self._hb_agent.report_data_sent(destination="work_areas")
        
        # Send to UE5 via bridge (with circuit breaker)
        if self._bridge_agent:
            if self._resilience_manager:
                # Use circuit breaker for UE5 bridge calls
                def send_to_bridge():
                    self._bridge_agent.send_work_area_update(
                        robot_id=self.robot_id,
                        area_center=msg_data['center'],
                        area_radius=max(area['dimensions'].x, area['dimensions'].y) / 2.0
                    )
                try:
                    self._resilience_manager.call_with_circuit_breaker(
                        'ue5_bridge', send_to_bridge
                    )
                except Exception as e:
                    self.get_logger().debug(f"UE5 Bridge call skipped: {e}")
            else:
                self._bridge_agent.send_work_area_update(
                    robot_id=self.robot_id,
                    area_center=msg_data['center'],
                    area_radius=max(area['dimensions'].x, area['dimensions'].y) / 2.0
                )
        
    def check_proximity(self):
        """Check proximity to all robots and publish alerts if needed."""
        alerts = self.proximity_monitor.get_all_proximity_alerts()
        
        if not alerts:
            return
        
        for robot_id, distance, velocity, severity in alerts:
            msg_data = {
                'source_robot_id': self.robot_id,
                'target_robot_id': robot_id,
                'current_distance': distance,
                'approach_velocity': velocity,
                'severity': severity,
                'timestamp': time.time()
            }
            
            msg = String()
            msg.data = json.dumps(msg_data)
            self.proximity_alert_pub.publish(msg)
            
            # Record alert in monitoring
            if self._monitoring_system:
                self._monitoring_system.message_flow_monitor.record_message(
                    topic='proximity_alerts',
                    direction='sent'
                )
                # Record critical alerts for anomaly detection
                if severity == 'critical':
                    self._monitoring_system.alert_manager.raise_alert(
                        source='proximity_monitor',
                        message=f'Critical proximity: {robot_id} at {distance:.2f}m',
                        severity_level=3  # WARNING
                    )
            
            if severity == 'critical':
                self.get_logger().error(f'CRITICAL proximity alert: {robot_id} at {distance:.2f}m')
            elif severity == 'caution':
                self.get_logger().warn(f'CAUTION proximity alert: {robot_id} at {distance:.2f}m')
            
            # Send to UE5 via bridge (with circuit breaker if available)
            if self._bridge_agent:
                if self._resilience_manager:
                    def send_alert():
                        self._bridge_agent.send_proximity_alert(
                            robot_id=self.robot_id,
                            other_robot_id=robot_id,
                            distance=distance,
                            severity=severity
                        )
                    try:
                        self._resilience_manager.call_with_circuit_breaker(
                            'ue5_bridge', send_alert
                        )
                    except Exception as e:
                        self.get_logger().debug(f"UE5 Bridge alert skipped: {e}")
                else:
                    self._bridge_agent.send_proximity_alert(
                        robot_id=self.robot_id,
                        other_robot_id=robot_id,
                        distance=distance,
                        severity=severity
                    )
        
        # Report activity to HB agent
        if self._hb_agent and alerts:
            self._hb_agent.report_coordination_activity(
                activity_type="proximity_check",
                robot_count=len(alerts)
            )
                
    def publish_health_status(self):
        """Publish health status to Webthread."""
        conflicts = self.work_area_manager.get_all_conflicts()
        
        # Get task coordination status
        task_info = {
            'active_tasks': len(self.task_coordinator.tasks),
            'resource_locks': len(self.task_coordinator.resource_locks)
        }
        
        # Get health metrics (CPU, memory, uptime)
        health_metrics = self.health_monitor.get_health_metrics()
        task_info.update(health_metrics)
        
        # Record heartbeat
        self.health_monitor.record_heartbeat()
        
        # Update state based on health
        old_state = self.state_machine.get_state()
        if len(conflicts) > 0:
            if old_state == ComponentState.ACTIVE:
                self.state_machine.transition_to(ComponentState.DEGRADED)
                if self._hb_agent:
                    self._hb_agent.report_state_transition("ACTIVE", "DEGRADED")
        else:
            if len(self.work_area_manager.work_areas) > 0:
                if old_state != ComponentState.ACTIVE:
                    self.state_machine.transition_to(ComponentState.ACTIVE)
                    if self._hb_agent:
                        self._hb_agent.report_state_transition(old_state.name, "ACTIVE")
            elif old_state == ComponentState.ACTIVE:
                self.state_machine.transition_to(ComponentState.IDLE)
                if self._hb_agent:
                    self._hb_agent.report_state_transition("ACTIVE", "IDLE")
        
        # Update HB agent queue depth (number of robots being tracked)
        if self._hb_agent:
            self._hb_agent.set_queue_depth(len(self.work_area_manager.work_areas))
        
        # Get status string from state machine
        status = self.state_machine.get_status_string()
        
        # Add monitoring system metrics if available
        if self._monitoring_system:
            monitoring_report = self._monitoring_system.get_summary()
            task_info['monitoring'] = {
                'connection_health': monitoring_report.get('connection_health', {}),
                'message_rates': monitoring_report.get('message_rates', {}),
                'fleet_size': monitoring_report.get('fleet_stats', {}).get('total_robots', 0),
                'active_alerts': monitoring_report.get('active_alerts', 0)
            }
        
        # Add resilience metrics if available
        if self._resilience_manager:
            resilience_report = self._resilience_manager.get_health_summary()
            task_info['resilience'] = {
                'circuit_breakers': resilience_report.get('circuit_breakers', {}),
                'recoveries_attempted': resilience_report.get('recoveries', {}).get('attempts', 0)
            }
            
        self.webthread_handler.publish_health_status(
            status=status,
            active_robots=len(self.work_area_manager.work_areas),
            conflicts=len(conflicts),
            additional_info=task_info
        )
        
    def cleanup_stale_data(self):
        """Clean up stale work area data."""
        self.work_area_manager.cleanup_stale_areas(max_age_seconds=5.0)
        
    def update_own_work_area(self, center: Point, dimensions: Vector3, priority: float = 2.0):
        """
        Update this robot's work area.
        
        Args:
            center: Center point of work area
            dimensions: Width, height, depth in meters
            priority: Task priority (0=lowest, 4=highest)
        """
        self.work_area_manager.update_work_area(center, dimensions, priority)
        
    def check_deadlocks(self):
        """Check for deadlocks in task coordination and evasion."""
        # Check task coordinator deadlocks
        task_deadlocks = self.task_coordinator.check_deadlock()
        if task_deadlocks:
            self.get_logger().error(f"Task deadlock detected: {task_deadlocks}")
            self.task_coordinator.resolve_deadlock(task_deadlocks)
            
            # Record in observability
            if self._obs_enabled and self._observability:
                self._observability.recorder.record_event("deadlock_detected", {
                    "type": "task",
                    "details": str(task_deadlocks),
                })
            
        # Check evasion deadlocks (when multiple robots blocking each other)
        # This is a simplified check - real implementation would be more sophisticated
        active_evasions = list(self.evade_coordinator.evasion_intents.keys())
        if len(active_evasions) >= 2:
            # Check if robots have been evading for too long
            self.evade_coordinator.handle_deadlock(active_evasions)
    
    def destroy_node(self):
        """Override destroy_node to properly cleanup all agents and observability"""
        self.get_logger().info("COMC Node shutting down...")
        
        # Notify HB agent of shutdown
        if self._hb_agent:
            self._hb_agent.report_state_transition(
                self.state_machine.get_state().name, "SHUTTING_DOWN"
            )
            self._hb_agent.stop()
            self.get_logger().info("HB Agent stopped")
        
        # Stop bridge agent
        if self._bridge_agent:
            self._bridge_agent.stop()
            self.get_logger().info("Bridge Agent stopped")
        
        # Stop monitoring system
        if self._monitoring_system:
            self._monitoring_system.stop()
            self.get_logger().info("Monitoring System stopped")
        
        # Resilience manager cleanup (if needed)
        if self._resilience_manager:
            # Get final health status before shutdown
            summary = self._resilience_manager.get_health_summary()
            self.get_logger().info(f"Resilience final status: {summary}")
        
        # Stop observability
        if self._obs_enabled and self._observability:
            self._observability.logger.info("COMC Node shutting down", 
                extra={"component": "comc", "robot_id": self.robot_id, "action": "shutdown"})
            self._observability.health.set_shutting_down()
            self._observability.stop()
        
        super().destroy_node()


def main(args=None):
    """Main entry point for COMC node."""
    rclpy.init(args=args)
    
    node = None
    try:
        node = COMCNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f'Error in COMC node: {e}')
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
