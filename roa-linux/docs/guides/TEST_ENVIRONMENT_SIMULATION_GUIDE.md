# ROA Test Environment Simulation Guide
**Date**: 2025-12-13  
**Purpose**: Simulate UE5 and complete ROA environment for testing without local installation

---

## Overview

This guide explains how to create a complete simulation environment for testing ROA components without requiring UE5, ROS2, or physical robots. The simulation allows full system testing in this development environment.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│           ROA Test Simulation Environment                    │
│        (Runs entirely in this environment!)                  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐ │
│  │  Mock ROS2     │  │   Mock UE5     │  │ Mock Robots  │ │
│  │                │  │                │  │              │ │
│  │ • Topics       │  │ • Scene        │  │ • Kinematics │ │
│  │ • Messages     │  │ • Rendering    │  │ • Physics    │ │
│  │ • Services     │  │ • Input        │  │ • Sensors    │ │
│  └────────────────┘  └────────────────┘  └──────────────┘ │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         ROA Components (Real Code)                    │  │
│  │  FTI │ DIMC │ ROC │ COMC │ Webthread                │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │    Visualization & Testing Tools                      │  │
│  │  • 2D/3D Matplotlib visualization                     │  │
│  │  • Test scenario player                               │  │
│  │  • Performance analyzer                               │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. Mock ROS2 System

**Purpose**: Simulate ROS2 pub/sub without requiring ROS2 installation

**Implementation:**

```python
# mock_ros2.py
import time
import threading
from typing import Dict, List, Callable, Any
from collections import defaultdict
import json

class MockMessage:
    """Base class for all mock ROS2 messages"""
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
    
    def to_dict(self):
        return self.__dict__
    
    def from_dict(self, data):
        self.__dict__.update(data)


class MockPublisher:
    """Simulates ROS2 publisher"""
    def __init__(self, topic_name: str, message_type: type):
        self.topic_name = topic_name
        self.message_type = message_type
        self.subscribers = []
    
    def publish(self, message: MockMessage):
        """Publish message to all subscribers"""
        for callback in self.subscribers:
            callback(message)
    
    def add_subscriber(self, callback: Callable):
        self.subscribers.append(callback)


class MockSubscriber:
    """Simulates ROS2 subscriber"""
    def __init__(self, topic_name: str, message_type: type, callback: Callable):
        self.topic_name = topic_name
        self.message_type = message_type
        self.callback = callback


class MockNode:
    """Simulates ROS2 node"""
    def __init__(self, name: str):
        self.name = name
        self.publishers = {}
        self.subscribers = {}
        self.services = {}
    
    def create_publisher(self, message_type: type, topic_name: str, qos: int = 10):
        """Create publisher"""
        publisher = MockPublisher(topic_name, message_type)
        self.publishers[topic_name] = publisher
        
        # Register with global topic registry
        MockROS2System.register_publisher(topic_name, publisher)
        
        return publisher
    
    def create_subscription(self, message_type: type, topic_name: str, 
                          callback: Callable, qos: int = 10):
        """Create subscription"""
        subscriber = MockSubscriber(topic_name, message_type, callback)
        self.subscribers[topic_name] = subscriber
        
        # Register with global topic registry
        MockROS2System.register_subscriber(topic_name, subscriber)
        
        return subscriber
    
    def spin_once(self, timeout: float = 0.0):
        """Process one round of callbacks"""
        time.sleep(timeout)


class MockROS2System:
    """Global ROS2 system simulator"""
    topics = defaultdict(list)  # topic_name -> list of (publisher, subscribers)
    
    @classmethod
    def register_publisher(cls, topic_name: str, publisher: MockPublisher):
        """Register publisher with system"""
        for subscriber in cls.topics[topic_name]:
            if isinstance(subscriber, MockSubscriber):
                publisher.add_subscriber(subscriber.callback)
    
    @classmethod
    def register_subscriber(cls, topic_name: str, subscriber: MockSubscriber):
        """Register subscriber with system"""
        cls.topics[topic_name].append(subscriber)
        
        # Connect to existing publishers
        for item in cls.topics[topic_name]:
            if isinstance(item, MockPublisher):
                item.add_subscriber(subscriber.callback)
    
    @classmethod
    def clear(cls):
        """Clear all topics (for testing)"""
        cls.topics.clear()


# Mock ROS2 message types
class JointState(MockMessage):
    def __init__(self):
        super().__init__(
            header={},
            name=[],
            position=[],
            velocity=[],
            effort=[]
        )


class SpatialData(MockMessage):
    def __init__(self):
        super().__init__(
            robot_id="",
            position=[0.0, 0.0, 0.0],
            orientation=[0.0, 0.0, 0.0, 1.0],
            velocity=[0.0, 0.0, 0.0]
        )


class ControlCommand(MockMessage):
    def __init__(self):
        super().__init__(
            robot_id="",
            command_type="",
            joint_values=[],
            priority=0
        )
```

### 2. Mock UE5 Scene

**Purpose**: Simulate 3D environment and physics

**Implementation:**

```python
# mock_ue5.py
import numpy as np
from typing import List, Dict, Tuple
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

class MockActor:
    """Simulates UE5 Actor"""
    def __init__(self, name: str, position: np.ndarray = None):
        self.name = name
        self.position = position if position is not None else np.array([0.0, 0.0, 0.0])
        self.rotation = np.array([0.0, 0.0, 0.0])  # Euler angles
        self.velocity = np.array([0.0, 0.0, 0.0])
        self.scale = np.array([1.0, 1.0, 1.0])
        self.mesh = None
    
    def set_location(self, location: np.ndarray):
        self.position = location
    
    def get_location(self) -> np.ndarray:
        return self.position
    
    def add_velocity(self, velocity: np.ndarray, delta_time: float):
        self.velocity += velocity
        self.position += self.velocity * delta_time


class MockRobot(MockActor):
    """Simulates robot actor with kinematics"""
    def __init__(self, name: str, num_joints: int = 6):
        super().__init__(name)
        self.num_joints = num_joints
        self.joint_positions = np.zeros(num_joints)
        self.joint_velocities = np.zeros(num_joints)
        self.joint_limits = [(-np.pi, np.pi)] * num_joints
        self.end_effector_position = np.array([0.0, 0.0, 0.0])
    
    def set_joint_positions(self, positions: List[float]):
        """Set joint positions with limit checking"""
        for i, pos in enumerate(positions):
            if i < self.num_joints:
                # Clamp to limits
                min_limit, max_limit = self.joint_limits[i]
                self.joint_positions[i] = np.clip(pos, min_limit, max_limit)
        
        # Update forward kinematics
        self._update_forward_kinematics()
    
    def _update_forward_kinematics(self):
        """Simple forward kinematics (simplified for simulation)"""
        # For a 6-DOF arm, approximate end effector position
        # This is a simplified model - real robots would use DH parameters
        link_length = 0.5  # meters
        
        x = 0.0
        y = 0.0
        z = 0.0
        
        for i in range(min(3, self.num_joints)):
            angle = self.joint_positions[i]
            x += link_length * np.cos(angle)
            y += link_length * np.sin(angle)
            if i > 0:
                z += link_length * np.sin(angle)
        
        self.end_effector_position = np.array([x, y, z])


class MockWorld:
    """Simulates UE5 World"""
    def __init__(self):
        self.actors = []
        self.robots = []
        self.obstacles = []
        self.current_time = 0.0
        self.delta_time = 0.016  # 60 FPS
    
    def spawn_actor(self, actor_class, name: str, location: np.ndarray = None) -> MockActor:
        """Spawn actor in world"""
        actor = actor_class(name, location)
        self.actors.append(actor)
        
        if isinstance(actor, MockRobot):
            self.robots.append(actor)
        
        return actor
    
    def spawn_robot(self, name: str, num_joints: int = 6, 
                    location: np.ndarray = None) -> MockRobot:
        """Spawn robot in world"""
        robot = MockRobot(name, num_joints)
        if location is not None:
            robot.set_location(location)
        
        self.actors.append(robot)
        self.robots.append(robot)
        
        return robot
    
    def add_obstacle(self, position: np.ndarray, radius: float):
        """Add obstacle to world"""
        obstacle = {
            'position': position,
            'radius': radius
        }
        self.obstacles.append(obstacle)
    
    def tick(self, delta_time: float = None):
        """Update world simulation"""
        if delta_time is None:
            delta_time = self.delta_time
        
        self.current_time += delta_time
        
        # Update all actors
        for actor in self.actors:
            if hasattr(actor, 'velocity'):
                actor.add_velocity(np.array([0.0, 0.0, 0.0]), delta_time)
    
    def check_collision(self, position: np.ndarray, radius: float = 0.1) -> Tuple[bool, float]:
        """Check for collisions"""
        min_distance = float('inf')
        collision = False
        
        for obstacle in self.obstacles:
            dist = np.linalg.norm(position - obstacle['position'])
            min_distance = min(min_distance, dist)
            
            if dist < (radius + obstacle['radius']):
                collision = True
        
        return collision, min_distance
    
    def get_robot_by_name(self, name: str) -> MockRobot:
        """Get robot by name"""
        for robot in self.robots:
            if robot.name == name:
                return robot
        return None


class MockUE5Visualizer:
    """2D/3D visualization of mock world"""
    def __init__(self, world: MockWorld):
        self.world = world
        self.fig = None
        self.ax = None
    
    def setup_2d_view(self):
        """Setup 2D top-down view"""
        self.fig, self.ax = plt.subplots(figsize=(10, 10))
        self.ax.set_xlim(-5, 5)
        self.ax.set_ylim(-5, 5)
        self.ax.set_aspect('equal')
        self.ax.grid(True)
        self.ax.set_xlabel('X (meters)')
        self.ax.set_ylabel('Y (meters)')
        self.ax.set_title('ROA Simulation - Top View')
    
    def update_2d_view(self):
        """Update 2D visualization"""
        self.ax.clear()
        self.ax.set_xlim(-5, 5)
        self.ax.set_ylim(-5, 5)
        self.ax.grid(True)
        
        # Draw obstacles
        for obstacle in self.world.obstacles:
            circle = plt.Circle(
                (obstacle['position'][0], obstacle['position'][1]),
                obstacle['radius'],
                color='red',
                alpha=0.5
            )
            self.ax.add_patch(circle)
        
        # Draw robots
        for robot in self.world.robots:
            # Robot base
            self.ax.plot(robot.position[0], robot.position[1], 'bo', markersize=10)
            self.ax.text(robot.position[0], robot.position[1] + 0.3, robot.name)
            
            # End effector
            ee_world = robot.position + robot.end_effector_position
            self.ax.plot(ee_world[0], ee_world[1], 'go', markersize=8)
            
            # Connect base to end effector
            self.ax.plot([robot.position[0], ee_world[0]], 
                        [robot.position[1], ee_world[1]], 'b-', linewidth=2)
        
        plt.pause(0.01)
    
    def animate(self, duration: float = 10.0):
        """Animate simulation"""
        self.setup_2d_view()
        
        start_time = time.time()
        while time.time() - start_time < duration:
            self.world.tick()
            self.update_2d_view()
        
        plt.show()
```

### 3. Complete Test Environment

**Purpose**: Integrate everything for full system testing

```python
# test_environment.py
import threading
import time
import numpy as np
from mock_ros2 import MockNode, MockROS2System, SpatialData, ControlCommand
from mock_ue5 import MockWorld, MockUE5Visualizer

class ROATestEnvironment:
    """Complete ROA test environment"""
    
    def __init__(self):
        self.world = MockWorld()
        self.ros2_system = MockROS2System()
        self.visualizer = MockUE5Visualizer(self.world)
        
        # Create robots
        self.robots = {}
        
        # ROS2 nodes (simulated)
        self.nodes = {}
        
        # Component states
        self.running = False
        self.simulation_thread = None
    
    def add_robot(self, robot_id: str, num_joints: int = 6, 
                  position: np.ndarray = None):
        """Add robot to simulation"""
        robot = self.world.spawn_robot(robot_id, num_joints, position)
        self.robots[robot_id] = robot
        
        # Create ROS2 publishers for this robot
        self._setup_robot_topics(robot_id)
    
    def _setup_robot_topics(self, robot_id: str):
        """Setup ROS2 topics for robot"""
        # Create node for this robot
        node = MockNode(f"robot_{robot_id}_simulator")
        self.nodes[robot_id] = node
        
        # Publisher for spatial data
        spatial_pub = node.create_publisher(SpatialData, f"/dimc/spatial_data_{robot_id}")
        
        # Subscriber for control commands
        def control_callback(msg):
            robot = self.world.get_robot_by_name(robot_id)
            if robot and msg.command_type == 'position':
                robot.set_joint_positions(msg.joint_values)
        
        node.create_subscription(ControlCommand, f"/roc/commands_{robot_id}", 
                                control_callback)
    
    def add_obstacle(self, position: List[float], radius: float):
        """Add obstacle to world"""
        self.world.add_obstacle(np.array(position), radius)
    
    def start_simulation(self):
        """Start simulation loop"""
        self.running = True
        self.simulation_thread = threading.Thread(target=self._simulation_loop)
        self.simulation_thread.start()
    
    def stop_simulation(self):
        """Stop simulation"""
        self.running = False
        if self.simulation_thread:
            self.simulation_thread.join()
    
    def _simulation_loop(self):
        """Main simulation loop"""
        while self.running:
            # Update world
            self.world.tick()
            
            # Publish spatial data for all robots
            for robot_id, robot in self.robots.items():
                spatial_msg = SpatialData()
                spatial_msg.robot_id = robot_id
                spatial_msg.position = robot.position.tolist()
                spatial_msg.velocity = robot.velocity.tolist()
                
                # Publish
                node = self.nodes.get(robot_id)
                if node and "/dimc/spatial_data_" + robot_id in node.publishers:
                    node.publishers["/dimc/spatial_data_" + robot_id].publish(spatial_msg)
            
            # Sleep for simulation rate (60 Hz)
            time.sleep(0.016)
    
    def visualize(self, duration: float = 10.0):
        """Visualize simulation"""
        self.visualizer.animate(duration)
    
    def run_test_scenario(self, scenario_name: str):
        """Run predefined test scenario"""
        if scenario_name == "single_robot_move":
            self._test_single_robot_move()
        elif scenario_name == "multi_robot_coordination":
            self._test_multi_robot_coordination()
        elif scenario_name == "obstacle_avoidance":
            self._test_obstacle_avoidance()
    
    def _test_single_robot_move(self):
        """Test single robot movement"""
        print("Running: Single Robot Move Test")
        
        # Add robot
        self.add_robot("robot_001", position=np.array([0.0, 0.0, 0.0]))
        
        # Start simulation
        self.start_simulation()
        
        # Send control commands
        time.sleep(1.0)
        
        # Move joints
        control_msg = ControlCommand()
        control_msg.robot_id = "robot_001"
        control_msg.command_type = "position"
        control_msg.joint_values = [0.5, 1.0, 0.0, 0.5, 0.0, 0.0]
        
        # Publish command
        # ... (would go through ROC in real system)
        
        # Visualize
        self.visualizer.setup_2d_view()
        for _ in range(100):
            self.world.tick()
            self.visualizer.update_2d_view()
        
        self.stop_simulation()
        print("Test complete!")
    
    def _test_multi_robot_coordination(self):
        """Test multiple robots"""
        print("Running: Multi-Robot Coordination Test")
        
        # Add 3 robots
        self.add_robot("robot_001", position=np.array([-2.0, 0.0, 0.0]))
        self.add_robot("robot_002", position=np.array([0.0, 0.0, 0.0]))
        self.add_robot("robot_003", position=np.array([2.0, 0.0, 0.0]))
        
        # Start simulation and visualize
        self.start_simulation()
        self.visualizer.setup_2d_view()
        
        for i in range(200):
            self.world.tick()
            self.visualizer.update_2d_view()
        
        self.stop_simulation()
        print("Test complete!")
    
    def _test_obstacle_avoidance(self):
        """Test obstacle avoidance"""
        print("Running: Obstacle Avoidance Test")
        
        # Add robot
        self.add_robot("robot_001", position=np.array([-3.0, 0.0, 0.0]))
        
        # Add obstacles
        self.add_obstacle([0.0, 0.0, 0.0], 0.5)
        self.add_obstacle([1.5, 1.5, 0.0], 0.3)
        
        # Start and visualize
        self.start_simulation()
        self.visualizer.setup_2d_view()
        
        for _ in range(300):
            self.world.tick()
            self.visualizer.update_2d_view()
        
        self.stop_simulation()
        print("Test complete!")


# Example usage
if __name__ == "__main__":
    env = ROATestEnvironment()
    env.run_test_scenario("obstacle_avoidance")
```

---

## Usage Examples

### 1. Test Single Component

```python
# Test ROC with simulated environment
from test_environment import ROATestEnvironment
from components.robot_operator_controller.src.python.roc_ros2_node import ROCNode

# Create environment
env = ROATestEnvironment()
env.add_robot("robot_001")
env.start_simulation()

# Create ROC node (will connect to mock ROS2)
roc = ROCNode()

# Send commands
roc.set_robot_position("robot_001", [0.5, 1.0, 0.0, 0.5, 0.0, 0.0])

# Visualize
env.visualize(duration=5.0)
```

### 2. Test Full System Integration

```python
# Test all components together
env = ROATestEnvironment()

# Add robots and obstacles
env.add_robot("robot_001", position=np.array([0, 0, 0]))
env.add_robot("robot_002", position=np.array([2, 2, 0]))
env.add_obstacle([1, 1, 0], 0.5)

# Start all components
# ... (FTI, DIMC, ROC, COMC, Webthread)

# Run test scenario
env.run_test_scenario("multi_robot_coordination")
```

### 3. Performance Testing

```python
# Test system performance
env = ROATestEnvironment()

# Add many robots
for i in range(8):
    env.add_robot(f"robot_{i:03d}")

# Measure performance
import time
start = time.time()

env.start_simulation()
time.sleep(10.0)  # Run for 10 seconds
env.stop_simulation()

duration = time.time() - start
print(f"Simulated 10 seconds in {duration:.2f} real seconds")
```

---

## Benefits

✅ **No External Dependencies** - Runs entirely in Python  
✅ **Fast Iteration** - Test changes immediately  
✅ **Reproducible** - Controlled test scenarios  
✅ **Visual Feedback** - See robot movements  
✅ **Integration Testing** - Test full ROA system  
✅ **Performance Analysis** - Measure system performance  

---

## Summary

- Complete ROA simulation can run without UE5, ROS2, or robots
- Mock APIs provide realistic testing environment
- 2D/3D visualization shows robot behavior
- All ROA components can be tested together
- Performance and integration testing possible

**Ready to Use**: Yes - Implementation can start immediately  
**Visualization**: Matplotlib for 2D/3D views  
**Next Step**: Create mock_ros2 and mock_ue5 modules
