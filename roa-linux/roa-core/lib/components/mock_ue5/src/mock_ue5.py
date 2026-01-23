"""
Mock UE5 System for Testing ROA Components
Simulates UE5 world and actors without requiring UE5 installation
"""

import time
from typing import Dict, List, Optional, Tuple

import numpy as np


class MockActor:
    """Simulates UE5 Actor"""

    def __init__(self, name: str, position: np.ndarray = None):
        self.name = name
        self.position = position if position is not None else np.array([0.0, 0.0, 0.0])
        self.rotation = np.array([0.0, 0.0, 0.0])  # Euler angles (pitch, yaw, roll)
        self.velocity = np.array([0.0, 0.0, 0.0])
        self.scale = np.array([1.0, 1.0, 1.0])
        self.mesh = None
        self.destroyed = False

    def set_location(self, location: np.ndarray):
        """Set actor location"""
        self.position = np.array(location)

    def get_location(self) -> np.ndarray:
        """Get actor location"""
        return self.position.copy()

    def set_rotation(self, rotation: np.ndarray):
        """Set actor rotation"""
        self.rotation = np.array(rotation)

    def get_rotation(self) -> np.ndarray:
        """Get actor rotation"""
        return self.rotation.copy()

    def add_velocity(self, velocity: np.ndarray, delta_time: float):
        """Add velocity and update position"""
        self.velocity += velocity
        self.position += self.velocity * delta_time

    def destroy(self):
        """Destroy actor"""
        self.destroyed = True


class MockRobot(MockActor):
    """Simulates robot actor with kinematics"""

    def __init__(self, name: str, num_joints: int = 6, position: np.ndarray = None):
        super().__init__(name, position)
        self.num_joints = num_joints
        self.joint_positions = np.zeros(num_joints)
        self.joint_velocities = np.zeros(num_joints)
        self.joint_limits = [(-np.pi, np.pi)] * num_joints
        self.end_effector_position = np.array([0.0, 0.0, 0.0])
        self.gripper_state = 0.0  # 0 = closed, 1 = open

    def set_joint_positions(self, positions: List[float]):
        """Set joint positions with limit checking"""
        for i, pos in enumerate(positions):
            if i < self.num_joints:
                # Clamp to limits
                min_limit, max_limit = self.joint_limits[i]
                self.joint_positions[i] = np.clip(pos, min_limit, max_limit)

        # Update forward kinematics
        self._update_forward_kinematics()

    def set_joint_velocities(self, velocities: List[float], delta_time: float):
        """Set joint velocities and update positions"""
        for i, vel in enumerate(velocities):
            if i < self.num_joints:
                self.joint_velocities[i] = vel
                self.joint_positions[i] += vel * delta_time

                # Enforce limits
                min_limit, max_limit = self.joint_limits[i]
                self.joint_positions[i] = np.clip(self.joint_positions[i], min_limit, max_limit)

        self._update_forward_kinematics()

    def _update_forward_kinematics(self):
        """Simple forward kinematics (simplified for simulation)"""
        # For a 6-DOF arm, approximate end effector position
        # This is a simplified model - real robots would use DH parameters
        link_length = 0.5  # meters

        x = 0.0
        y = 0.0
        z = 0.0

        # Simple kinematic chain
        for i in range(min(3, self.num_joints)):
            angle = self.joint_positions[i]
            if i == 0:  # Base rotation
                x += link_length * np.cos(angle)
                y += link_length * np.sin(angle)
            elif i == 1:  # Shoulder
                x += link_length * np.cos(angle)
                z += link_length * np.sin(angle)
            elif i == 2:  # Elbow
                x += link_length * np.cos(angle)
                z += link_length * np.sin(angle) * 0.5

        self.end_effector_position = self.position + np.array([x, y, z])

    def get_end_effector_position(self) -> np.ndarray:
        """Get end effector position in world coordinates"""
        return self.end_effector_position.copy()

    def open_gripper(self):
        """Open gripper"""
        self.gripper_state = 1.0

    def close_gripper(self):
        """Close gripper"""
        self.gripper_state = 0.0


class MockObstacle:
    """Simulates obstacle in scene"""

    def __init__(self, position: np.ndarray, radius: float):
        self.position = np.array(position)
        self.radius = radius


class MockWorld:
    """Simulates UE5 World"""

    def __init__(self):
        self.actors = []
        self.robots = {}
        self.obstacles = []
        self.current_time = 0.0
        self.delta_time = 0.016  # 60 FPS default
        self.running = False

    def spawn_actor(self, actor_class, name: str, location: np.ndarray = None) -> MockActor:
        """Spawn actor in world"""
        actor = actor_class(name, location)
        self.actors.append(actor)

        if isinstance(actor, MockRobot):
            self.robots[name] = actor

        return actor

    def spawn_robot(self, name: str, num_joints: int = 6, location: np.ndarray = None) -> MockRobot:
        """Spawn robot in world"""
        robot = MockRobot(name, num_joints, location)
        self.actors.append(robot)
        self.robots[name] = robot

        return robot

    def add_obstacle(self, position: np.ndarray, radius: float):
        """Add obstacle to world"""
        obstacle = MockObstacle(position, radius)
        self.obstacles.append(obstacle)
        return obstacle

    def tick(self, delta_time: float = None):
        """Update world simulation"""
        if delta_time is None:
            delta_time = self.delta_time

        self.current_time += delta_time

        # Update all actors
        for actor in self.actors:
            if not actor.destroyed:
                # Apply physics (simplified)
                if hasattr(actor, "velocity") and np.linalg.norm(actor.velocity) > 0:
                    actor.position += actor.velocity * delta_time
                    # Simple friction
                    actor.velocity *= 0.99

    def check_collision(self, position: np.ndarray, radius: float = 0.1) -> Tuple[bool, float]:
        """Check for collisions with obstacles"""
        min_distance = float("inf")
        collision = False

        for obstacle in self.obstacles:
            dist = np.linalg.norm(position - obstacle.position)
            min_distance = min(min_distance, dist)

            if dist < (radius + obstacle.radius):
                collision = True

        return collision, min_distance

    def check_robot_collision(self, robot_name: str) -> Tuple[bool, float]:
        """Check if robot is in collision"""
        if robot_name not in self.robots:
            return False, float("inf")

        robot = self.robots[robot_name]
        return self.check_collision(robot.get_end_effector_position(), 0.1)

    def get_robot_by_name(self, name: str) -> Optional[MockRobot]:
        """Get robot by name"""
        return self.robots.get(name)

    def get_distance_between_robots(self, robot1_name: str, robot2_name: str) -> float:
        """Get distance between two robots"""
        if robot1_name not in self.robots or robot2_name not in self.robots:
            return float("inf")

        robot1 = self.robots[robot1_name]
        robot2 = self.robots[robot2_name]

        return np.linalg.norm(robot1.position - robot2.position)

    def get_all_robots(self) -> List[MockRobot]:
        """Get all robots in world"""
        return list(self.robots.values())

    def clear(self):
        """Clear all actors and obstacles"""
        self.actors.clear()
        self.robots.clear()
        self.obstacles.clear()
        self.current_time = 0.0


class MockWidget:
    """Base class for mock UE5 widgets"""

    def __init__(self):
        self.visible = True
        self.enabled = True
        self.parent = None
        self.children = []

    def set_visibility(self, visible: bool):
        """Set widget visibility"""
        self.visible = visible

    def set_enabled(self, enabled: bool):
        """Set widget enabled state"""
        self.enabled = enabled

    def native_construct(self):
        """Called when widget is constructed"""
        pass

    def native_tick(self, delta_time: float):
        """Called every frame"""
        pass


class MockSlider(MockWidget):
    """Mock slider widget"""

    def __init__(self, min_value: float = 0.0, max_value: float = 1.0):
        super().__init__()
        self.value = 0.0
        self.min_value = min_value
        self.max_value = max_value
        self.on_value_changed = None

    def set_value(self, value: float):
        """Set slider value"""
        self.value = np.clip(value, self.min_value, self.max_value)
        if self.on_value_changed:
            self.on_value_changed(self.value)

    def get_value(self) -> float:
        """Get slider value"""
        return self.value


class MockButton(MockWidget):
    """Mock button widget"""

    def __init__(self, text: str = ""):
        super().__init__()
        self.text = text
        self.on_clicked = None

    def click(self):
        """Simulate button click"""
        if self.enabled and self.on_clicked:
            self.on_clicked()


class MockTextBlock(MockWidget):
    """Mock text display widget"""

    def __init__(self, text: str = ""):
        super().__init__()
        self.text = text

    def set_text(self, text: str):
        """Set text"""
        self.text = text

    def get_text(self) -> str:
        """Get text"""
        return self.text


# Mock UE5 API functions
def get_world():
    """Get current world instance"""
    if not hasattr(get_world, "_world"):
        get_world._world = MockWorld()
    return get_world._world


def spawn_actor(actor_class, location=None, rotation=None):
    """Spawn actor in world"""
    world = get_world()
    return world.spawn_actor(actor_class, f"Actor_{len(world.actors)}", location)
