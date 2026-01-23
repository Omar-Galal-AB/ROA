# ROA Examples and Demonstrations

Practical examples showing how to use the ROA infrastructure and testing tools.

## Test Simulation Demo

**File:** `test_simulation_demo.py`

Demonstrates integration of Mock ROS2 and Mock UE5 systems for testing ROA components without external dependencies.

### What it shows:

- ✅ Creating Mock UE5 world with robots and obstacles
- ✅ Setting up Mock ROS2 nodes with publishers/subscribers
- ✅ Simulating DIMC (spatial data publisher)
- ✅ Simulating ROC (control command publisher)
- ✅ Robot kinematics and joint control
- ✅ Collision detection
- ✅ Complete integration without ROS2 or UE5 installed

### Run it:

```bash
cd /home/runner/work/ROA/ROA
pip install numpy
python3 examples/test_simulation_demo.py
```

### Expected output:

```
============================================================
ROA Simulation Demo - Mock ROS2 + Mock UE5
============================================================

[1] Creating Mock UE5 World...
   ✓ Spawned robot: robot_001
   ✓ Added 2 obstacles

[2] Creating Mock ROS2 Nodes...
   ✓ Created DIMC node with spatial data publisher
   ✓ Created ROC node with command publisher
   ✓ Created subscriptions

[3] Running Simulation (5 seconds)...
   → ROC received spatial data: robot=robot_001
   → UE5 received command: robot=robot_001, type=position
   ...

✅ Demo completed successfully!
```

## More Examples Coming Soon

- ROC test integration example
- Qt Designer conversion example
- Multi-robot coordination example
- Path planning visualization example
