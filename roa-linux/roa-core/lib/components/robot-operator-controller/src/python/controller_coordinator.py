"""
Controller Coordinator - Integrates all motion controllers for ROC.

Bridges:
- BaseController (base class)
- ArmController (6-DOF arm joints)
- GripperController (gripper open/close)
- MobileController (mobile base movement)
- SafetyCoordinator (velocity limits)
- TaskExecutor (autonomous commands)

This was identified as a critical gap - Controllers existed but were orphaned.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from .controllers.arm_controller import ArmController
from .controllers.base_controller import BaseController, ControllerState
from .controllers.gripper_controller import GripperController
from .controllers.mobile_controller import MobileController


class ControllerType(Enum):
    """Types of controllers."""

    ARM = auto()
    GRIPPER = auto()
    MOBILE = auto()


@dataclass
class JointTarget:
    """Target position for a joint."""

    joint_name: str
    target_position: float
    velocity_limit: Optional[float] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class MotionCommand:
    """Motion command for execution."""

    robot_id: str
    controller_type: ControllerType
    command: Dict[str, Any]
    priority: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class ControllerCoordinatorConfig:
    """Configuration for controller coordinator."""

    # Command queue limits
    max_queue_depth: int = 100
    command_timeout_s: float = 5.0

    # Interpolation
    interpolation_rate_hz: float = 60.0
    max_position_delta: float = 0.1  # rad/step

    # Safety integration
    apply_velocity_limits: bool = True
    check_limits_before_execute: bool = True

    # Controller timeouts
    arm_timeout_s: float = 10.0
    gripper_timeout_s: float = 5.0
    mobile_timeout_s: float = 30.0


class ControllerCoordinator:
    """
    Coordinates all motion controllers for a multi-robot system.

    Responsibilities:
    - Manage controller lifecycles
    - Route commands to appropriate controllers
    - Apply safety velocity limits
    - Coordinate multi-controller motions
    - Report controller status to coordinator
    """

    def __init__(
        self,
        config: Optional[ControllerCoordinatorConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize controller coordinator.

        Args:
            config: Configuration
            logger: Logger instance
        """
        self.config = config or ControllerCoordinatorConfig()
        self.logger = logger or logging.getLogger(__name__)

        # Controllers per robot
        self._arm_controllers: Dict[str, ArmController] = {}
        self._gripper_controllers: Dict[str, GripperController] = {}
        self._mobile_controllers: Dict[str, MobileController] = {}

        # Command queues per robot
        self._command_queues: Dict[str, asyncio.Queue] = {}

        # Execution tasks
        self._execution_tasks: Dict[str, asyncio.Task] = {}

        # Current velociy multipliers from safety
        self._velocity_multipliers: Dict[str, float] = {}

        # Callbacks
        self._on_motion_complete: List[Callable[[str, ControllerType, bool], None]] = []
        self._on_error: List[Callable[[str, ControllerType, str], None]] = []

        # State
        self._running = False
        self._interpolation_task: Optional[asyncio.Task] = None

        # Statistics
        self._commands_executed = 0
        self._commands_failed = 0

        self.logger.info("ControllerCoordinator initialized")

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self):
        """Start controller coordinator."""
        self._running = True

        # Start interpolation loop
        interval = 1.0 / self.config.interpolation_rate_hz
        self._interpolation_task = asyncio.create_task(self._interpolation_loop(interval))

        self.logger.info("ControllerCoordinator started")

    async def stop(self):
        """Stop controller coordinator."""
        self._running = False

        # Cancel interpolation
        if self._interpolation_task:
            self._interpolation_task.cancel()
            try:
                await self._interpolation_task
            except asyncio.CancelledError:
                pass

        # Cancel execution tasks
        for task in self._execution_tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Stop all controllers
        for robot_id in list(self._arm_controllers.keys()):
            await self._stop_robot_controllers(robot_id)

        self.logger.info("ControllerCoordinator stopped")

    # =========================================================================
    # Robot Registration
    # =========================================================================

    def register_robot(
        self,
        robot_id: str,
        has_arm: bool = True,
        has_gripper: bool = True,
        has_mobile_base: bool = False,
        arm_joint_count: int = 6,
        gripper_joint_count: int = 2,
    ):
        """
        Register a robot and create its controllers.

        Args:
            robot_id: Robot identifier
            has_arm: Whether robot has arm
            has_gripper: Whether robot has gripper
            has_mobile_base: Whether robot has mobile base
            arm_joint_count: Number of arm joints
            gripper_joint_count: Number of gripper joints
        """
        if has_arm:
            self._arm_controllers[robot_id] = ArmController(
                robot_id=robot_id, joint_count=arm_joint_count
            )

        if has_gripper:
            self._gripper_controllers[robot_id] = GripperController(
                robot_id=robot_id, joint_count=gripper_joint_count
            )

        if has_mobile_base:
            self._mobile_controllers[robot_id] = MobileController(robot_id=robot_id)

        # Create command queue
        self._command_queues[robot_id] = asyncio.Queue(maxsize=self.config.max_queue_depth)

        # Initialize velocity multiplier
        self._velocity_multipliers[robot_id] = 1.0

        # Start command executor
        self._execution_tasks[robot_id] = asyncio.create_task(self._command_executor(robot_id))

        self.logger.info(f"Registered robot {robot_id} with controllers")

    def unregister_robot(self, robot_id: str):
        """Unregister a robot and remove its controllers."""
        # Cancel executor
        if robot_id in self._execution_tasks:
            self._execution_tasks[robot_id].cancel()
            del self._execution_tasks[robot_id]

        # Remove controllers
        self._arm_controllers.pop(robot_id, None)
        self._gripper_controllers.pop(robot_id, None)
        self._mobile_controllers.pop(robot_id, None)

        # Remove queue
        self._command_queues.pop(robot_id, None)
        self._velocity_multipliers.pop(robot_id, None)

        self.logger.info(f"Unregistered robot {robot_id}")

    async def _stop_robot_controllers(self, robot_id: str):
        """Stop all controllers for a robot."""
        if robot_id in self._arm_controllers:
            await self._arm_controllers[robot_id].stop()
        if robot_id in self._gripper_controllers:
            await self._gripper_controllers[robot_id].stop()
        if robot_id in self._mobile_controllers:
            await self._mobile_controllers[robot_id].stop()

    # =========================================================================
    # Command Execution
    # =========================================================================

    async def execute_arm_command(
        self,
        robot_id: str,
        joint_positions: Dict[str, float],
        velocity_scale: float = 1.0,
        priority: int = 0,
    ) -> bool:
        """
        Execute arm motion command.

        Args:
            robot_id: Robot identifier
            joint_positions: Dict of joint_name -> target_position
            velocity_scale: Velocity scaling factor
            priority: Command priority

        Returns:
            True if command was queued
        """
        if robot_id not in self._arm_controllers:
            self.logger.error(f"No arm controller for {robot_id}")
            return False

        command = MotionCommand(
            robot_id=robot_id,
            controller_type=ControllerType.ARM,
            command={
                "joint_positions": joint_positions,
                "velocity_scale": velocity_scale,
            },
            priority=priority,
        )

        try:
            await self._command_queues[robot_id].put(command)
            return True
        except asyncio.QueueFull:
            self.logger.warning(f"Command queue full for {robot_id}")
            return False

    async def execute_gripper_command(
        self,
        robot_id: str,
        position: float,
        force: Optional[float] = None,
        priority: int = 0,
    ) -> bool:
        """
        Execute gripper command.

        Args:
            robot_id: Robot identifier
            position: Target position (0.0=closed, 1.0=open)
            force: Gripping force (optional)
            priority: Command priority

        Returns:
            True if command was queued
        """
        if robot_id not in self._gripper_controllers:
            self.logger.error(f"No gripper controller for {robot_id}")
            return False

        command = MotionCommand(
            robot_id=robot_id,
            controller_type=ControllerType.GRIPPER,
            command={"position": position, "force": force},
            priority=priority,
        )

        try:
            await self._command_queues[robot_id].put(command)
            return True
        except asyncio.QueueFull:
            self.logger.warning(f"Command queue full for {robot_id}")
            return False

    async def execute_mobile_command(
        self,
        robot_id: str,
        linear_velocity: Tuple[float, float, float],
        angular_velocity: float,
        duration_s: Optional[float] = None,
        priority: int = 0,
    ) -> bool:
        """
        Execute mobile base command.

        Args:
            robot_id: Robot identifier
            linear_velocity: (x, y, z) velocity
            angular_velocity: Rotation velocity
            duration_s: Duration (None for continuous)
            priority: Command priority

        Returns:
            True if command was queued
        """
        if robot_id not in self._mobile_controllers:
            self.logger.error(f"No mobile controller for {robot_id}")
            return False

        command = MotionCommand(
            robot_id=robot_id,
            controller_type=ControllerType.MOBILE,
            command={
                "linear_velocity": linear_velocity,
                "angular_velocity": angular_velocity,
                "duration_s": duration_s,
            },
            priority=priority,
        )

        try:
            await self._command_queues[robot_id].put(command)
            return True
        except asyncio.QueueFull:
            self.logger.warning(f"Command queue full for {robot_id}")
            return False

    async def _command_executor(self, robot_id: str):
        """Command execution loop for a robot."""
        queue = self._command_queues.get(robot_id)
        if not queue:
            return

        while self._running:
            try:
                command = await asyncio.wait_for(queue.get(), timeout=1.0)

                success = await self._execute_command(command)

                if success:
                    self._commands_executed += 1
                else:
                    self._commands_failed += 1

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Command executor error: {e}")

    async def _execute_command(self, command: MotionCommand) -> bool:
        """Execute a single motion command."""
        robot_id = command.robot_id

        # Get velocity multiplier from safety
        velocity_mult = self._velocity_multipliers.get(robot_id, 1.0)

        if velocity_mult <= 0:
            self.logger.warning(f"Motion blocked by safety for {robot_id}")
            return False

        try:
            if command.controller_type == ControllerType.ARM:
                return await self._execute_arm(robot_id, command.command, velocity_mult)
            elif command.controller_type == ControllerType.GRIPPER:
                return await self._execute_gripper(robot_id, command.command)
            elif command.controller_type == ControllerType.MOBILE:
                return await self._execute_mobile(robot_id, command.command, velocity_mult)
        except Exception as e:
            self.logger.error(f"Command execution error: {e}")
            self._notify_error(robot_id, command.controller_type, str(e))
            return False

        return False

    async def _execute_arm(self, robot_id: str, command: Dict, velocity_mult: float) -> bool:
        """Execute arm command."""
        controller = self._arm_controllers.get(robot_id)
        if not controller:
            return False

        joint_positions = command.get("joint_positions", {})
        velocity_scale = command.get("velocity_scale", 1.0) * velocity_mult

        success = await controller.move_to_joints(joint_positions, velocity_scale=velocity_scale)

        self._notify_completion(robot_id, ControllerType.ARM, success)
        return success

    async def _execute_gripper(self, robot_id: str, command: Dict) -> bool:
        """Execute gripper command."""
        controller = self._gripper_controllers.get(robot_id)
        if not controller:
            return False

        position = command.get("position", 0.0)
        force = command.get("force")

        success = await controller.set_position(position, force=force)

        self._notify_completion(robot_id, ControllerType.GRIPPER, success)
        return success

    async def _execute_mobile(self, robot_id: str, command: Dict, velocity_mult: float) -> bool:
        """Execute mobile base command."""
        controller = self._mobile_controllers.get(robot_id)
        if not controller:
            return False

        linear = command.get("linear_velocity", (0, 0, 0))
        angular = command.get("angular_velocity", 0)
        duration = command.get("duration_s")

        # Apply velocity multiplier
        linear = tuple(v * velocity_mult for v in linear)
        angular = angular * velocity_mult

        success = await controller.move(
            linear_velocity=linear, angular_velocity=angular, duration_s=duration
        )

        self._notify_completion(robot_id, ControllerType.MOBILE, success)
        return success

    # =========================================================================
    # Interpolation Loop
    # =========================================================================

    async def _interpolation_loop(self, interval: float):
        """
        Interpolation loop for smooth motion.

        This runs at high frequency to interpolate between
        current and target positions.
        """
        while self._running:
            try:
                for robot_id, controller in self._arm_controllers.items():
                    if controller.state == ControllerState.MOVING:
                        velocity_mult = self._velocity_multipliers.get(robot_id, 1.0)
                        await controller.interpolation_step(
                            dt=interval, velocity_scale=velocity_mult
                        )

                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Interpolation error: {e}")
                await asyncio.sleep(interval)

    # =========================================================================
    # Safety Integration
    # =========================================================================

    def set_velocity_multiplier(self, robot_id: str, multiplier: float):
        """
        Set velocity multiplier from safety system.

        Args:
            robot_id: Robot identifier
            multiplier: Velocity multiplier (0.0 to 1.0)
        """
        self._velocity_multipliers[robot_id] = max(0.0, min(1.0, multiplier))

    def emergency_stop(self, robot_id: str):
        """Emergency stop a robot."""
        # Stop all controllers immediately
        if robot_id in self._arm_controllers:
            self._arm_controllers[robot_id].emergency_stop()
        if robot_id in self._gripper_controllers:
            self._gripper_controllers[robot_id].emergency_stop()
        if robot_id in self._mobile_controllers:
            self._mobile_controllers[robot_id].emergency_stop()

        # Clear command queue
        if robot_id in self._command_queues:
            queue = self._command_queues[robot_id]
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

        # Set velocity to zero
        self._velocity_multipliers[robot_id] = 0.0

        self.logger.warning(f"Emergency stop for {robot_id}")

    def emergency_stop_all(self):
        """Emergency stop all robots."""
        for robot_id in list(self._arm_controllers.keys()):
            self.emergency_stop(robot_id)

    # =========================================================================
    # Direct Access
    # =========================================================================

    def get_arm_controller(self, robot_id: str) -> Optional[ArmController]:
        """Get arm controller for a robot."""
        return self._arm_controllers.get(robot_id)

    def get_gripper_controller(self, robot_id: str) -> Optional[GripperController]:
        """Get gripper controller for a robot."""
        return self._gripper_controllers.get(robot_id)

    def get_mobile_controller(self, robot_id: str) -> Optional[MobileController]:
        """Get mobile controller for a robot."""
        return self._mobile_controllers.get(robot_id)

    def get_joint_positions(self, robot_id: str) -> Dict[str, float]:
        """Get current joint positions for a robot."""
        controller = self._arm_controllers.get(robot_id)
        if controller:
            return controller.get_joint_positions()
        return {}

    def get_gripper_position(self, robot_id: str) -> float:
        """Get current gripper position."""
        controller = self._gripper_controllers.get(robot_id)
        if controller:
            return controller.get_position()
        return 0.0

    # =========================================================================
    # Callbacks
    # =========================================================================

    def _notify_completion(self, robot_id: str, controller_type: ControllerType, success: bool):
        """Notify motion completion."""
        for callback in self._on_motion_complete:
            try:
                callback(robot_id, controller_type, success)
            except Exception as e:
                self.logger.error(f"Completion callback error: {e}")

    def _notify_error(self, robot_id: str, controller_type: ControllerType, error: str):
        """Notify motion error."""
        for callback in self._on_error:
            try:
                callback(robot_id, controller_type, error)
            except Exception as e:
                self.logger.error(f"Error callback error: {e}")

    def on_motion_complete(self, callback: Callable[[str, ControllerType, bool], None]):
        """Register motion complete callback."""
        self._on_motion_complete.append(callback)

    def on_error(self, callback: Callable[[str, ControllerType, str], None]):
        """Register error callback."""
        self._on_error.append(callback)

    # =========================================================================
    # Status
    # =========================================================================

    def get_controller_status(self, robot_id: str) -> Dict[str, Any]:
        """Get status of all controllers for a robot."""
        status = {"robot_id": robot_id}

        if robot_id in self._arm_controllers:
            controller = self._arm_controllers[robot_id]
            status["arm"] = {
                "state": controller.state.name,
                "joints": controller.get_joint_positions(),
            }

        if robot_id in self._gripper_controllers:
            controller = self._gripper_controllers[robot_id]
            status["gripper"] = {
                "state": controller.state.name,
                "position": controller.get_position(),
            }

        if robot_id in self._mobile_controllers:
            controller = self._mobile_controllers[robot_id]
            status["mobile"] = {"state": controller.state.name}

        status["velocity_multiplier"] = self._velocity_multipliers.get(robot_id, 1.0)

        return status

    def get_status(self) -> Dict[str, Any]:
        """Get overall coordinator status."""
        return {
            "running": self._running,
            "robot_count": len(self._arm_controllers),
            "arm_controllers": len(self._arm_controllers),
            "gripper_controllers": len(self._gripper_controllers),
            "mobile_controllers": len(self._mobile_controllers),
            "statistics": {
                "commands_executed": self._commands_executed,
                "commands_failed": self._commands_failed,
            },
        }
