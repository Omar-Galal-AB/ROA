# Mock ROS2 System

Simulates ROS2 pub/sub without requiring ROS2 installation.

## Usage

```python
from mock_ros2 import MockNode, ControlCommand, SpatialData

# Create node
node = MockNode('my_node')

# Create publisher
pub = node.create_publisher(ControlCommand, '/commands', 10)

# Create subscriber
def callback(msg):
    print(f"Received: {msg.robot_id}")

sub = node.create_subscription(SpatialData, '/spatial_data', callback, 10)

# Publish message
msg = ControlCommand()
msg.robot_id = "robot_001"
msg.command_type = "position"
pub.publish(msg)
```

## Features

- ✅ Topic pub/sub simulation
- ✅ Service client/server simulation
- ✅ QoS simulation
- ✅ Thread-safe operations
- ✅ All ROA message types included
