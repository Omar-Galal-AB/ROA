# Dependencies & Attributions

This document lists all external projects, libraries, plugins, and frameworks that ROA depends on or learned from.

---

## Table of Contents
1. [Projects ROA Learned From](#projects-roa-learned-from)
2. [Core Dependencies](#core-dependencies)
3. [UE5 Plugin Dependencies](#ue5-plugin-dependencies)
4. [Python Dependencies](#python-dependencies)
5. [Build & Development Tools](#build--development-tools)
6. [Optional Dependencies](#optional-dependencies)

---

## Projects ROA Learned From

ROA's architecture and design were informed by comprehensive research of 12+ open-source robotics and simulation projects. For detailed analysis, see [roa-linux/docs/SIMILAR_PROJECTS_RESEARCH.md](roa-linux/docs/SIMILAR_PROJECTS_RESEARCH.md).

### Major Influences

| Project | What We Learned | Applied To |
|---------|-----------------|------------|
| **ROS2 Control** | Plugin-based architecture, hardware abstraction | ROC component architecture |
| **MoveIt 2** | Collision mesh handling, path planning | Evade subsystem, ADM mode |
| **Nav2** | Behavior trees, local/global planning split | Evade system, recovery behaviors |
| **Gazebo** | Physics simulation, SDF format | UE5 physics parameters, FTI |
| **USD (Pixar)** | Universal 3D interchange format | FTI conversion pipeline |
| **PyBullet** | URDF as universal format | FTI prioritizes URDF |
| **Foxglove Studio** | Modern ROS visualization UI | Dashboard design patterns |
| **RViz2** | 3D robot visualization | UE5 visualization approach |
| **ros_gz_bridge** | Sim/real bridge patterns | WEBTHREAD bridge architecture |
| **rosbridge_suite** | WebSocket ROS bridge | Network protocol design |

**Full Research Report:** [roa-linux/docs/SIMILAR_PROJECTS_RESEARCH.md](roa-linux/docs/SIMILAR_PROJECTS_RESEARCH.md) (873 lines)

---

## Core Dependencies

### ROS2 Ecosystem (Optional)

ROA includes mock ROS2 implementations for standalone operation, but full ROS2 integration requires:

- **ROS2 Humble** (LTS) - Robot Operating System 2
  - License: Apache 2.0
  - Website: https://docs.ros.org/en/humble/
  - Used for: Inter-process communication, lifecycle management
  - Required for: Full ROS integration, hardware robot control

### Fast-DDS (Embedded in UE5 Plugin)

- **Fast-DDS** (eProsima)
  - Version: 2.10+ (bundled with ROS2 Humble)
  - License: Apache 2.0
  - GitHub: https://github.com/eProsima/Fast-DDS
  - Used for: Native DDS communication in UE5 plugin (<5ms latency)
  - Integration: See [ue5-plugin/ThirdParty/INTEGRATION_GUIDE.md](ue5-plugin/ThirdParty/INTEGRATION_GUIDE.md)

### rclcpp (Embedded in UE5 Plugin)

- **rclcpp** (ROS Client Library C++)
  - Version: ROS2 Humble
  - License: Apache 2.0
  - GitHub: https://github.com/ros2/rclcpp
  - Used for: Native ROS2 nodes in UE5
  - Integration: See [ue5-plugin/ThirdParty/INTEGRATION_GUIDE.md](ue5-plugin/ThirdParty/INTEGRATION_GUIDE.md)

---

## UE5 Plugin Dependencies

### Required UE5 Plugins

ROA requires these Unreal Engine plugins to be enabled:

| Plugin | Source | Purpose | Required |
|--------|--------|---------|----------|
| **PythonScriptPlugin** | Built-in UE5 | Python integration for URDF processing | ✅ Yes |
| **ROA** | This Repository | Main ROA plugin | ✅ Yes |

### UE5 Engine Version

- **Unreal Engine 5.6+**
  - License: Unreal Engine EULA
  - Website: https://www.unrealengine.com/
  - Required for: 3D visualization, physics simulation

### C++ Compiler

- **Visual Studio 2022** (Windows)
  - License: Microsoft EULA
  - Required for: UE5 plugin compilation
  - Components: Desktop development with C++, Game development with C++

---

## Python Dependencies

### Core Python Packages

From [roa-linux/roa-core/requirements.txt](roa-linux/roa-core/requirements.txt):

#### Scientific Computing
- **numpy** ≥1.20.0 - Array operations, math
- **matplotlib** ≥3.3.0 - Data visualization

#### Controller Support
- **pydualsense** ≥0.6.0 - DualSense controller support
- **pygame** ≥2.0.0 - Game controller input
- **approxeng.input** ≥2.3.0 - Controller abstraction layer
- **evdev** ≥1.4.0 (Linux only) - Low-level input device access
- **pynput** ≥1.7.0 - Keyboard/mouse input

#### GUI
- **PyQt6** ≥6.4.0 - Primary Qt bindings
- **PyQt5** ≥5.15.0 - Fallback Qt bindings

#### Testing & Quality
- **pytest** ≥6.2.0 - Test framework
- **pytest-cov** ≥2.12.0 - Code coverage
- **black** ≥21.6b0 - Code formatter
- **flake8** ≥3.9.0 - Linter
- **mypy** ≥0.910 - Type checker
- **isort** ≥5.9.0 - Import sorter

### Python Version

- **Python 3.10+**
  - License: PSF License
  - Website: https://python.org/

---

## Build & Development Tools

### Linux/WSL2

- **Ubuntu 22.04+** - Primary development platform
- **CMake 3.20+** - Build system (if building ROS2 from source)
- **Git** - Version control
- **curl/wget** - Downloading dependencies

### Windows

- **PowerShell 5.1+** - Script execution
- **Visual Studio 2022** - C++ compilation
- **.NET Framework 4.8+** - Build tools dependency

---

## Optional Dependencies

### Observability Stack (Monitoring)

Located in `roa-linux/config/observability/`:

- **Grafana** - Metrics dashboard
  - License: AGPL 3.0
  - Website: https://grafana.com/
  
- **Prometheus** - Time-series database
  - License: Apache 2.0
  - Website: https://prometheus.io/
  
- **Loki** - Log aggregation
  - License: AGPL 3.0
  - Website: https://grafana.com/oss/loki/

### ROS2 Tools (Optional)

- **colcon** - ROS2 build tool
- **rosdep** - Dependency management
- **ros2_control** - Hardware interface framework
- **MoveIt 2** - Motion planning (future integration)

### 3D File Format Tools

- **xacro** - URDF macro processor (embedded in plugin)
  - License: BSD
  - GitHub: https://github.com/ros/xacro
  
- **USD Python** - Universal Scene Description
  - License: Modified Apache 2.0
  - GitHub: https://github.com/PixarAnimationStudios/USD

---

## Third-Party Assets & Libraries

### Bundled Python (UE5 Plugin)

The UE5 plugin bundles a minimal Python 3.10+ runtime for URDF/XACRO processing:

- **Location:** `ue5-plugin/ThirdParty/Python/`
- **Setup:** See [ue5-plugin/ThirdParty/setup_bundled_python.ps1](ue5-plugin/ThirdParty/setup_bundled_python.ps1)
- **Includes:** Python interpreter + xacro package

### Robot Models (Separate Repository)

Pre-configured robot models (URDF/meshes) are in the `robot-models/` folder:

- **Size:** ~1GB (recommend Git LFS)
- **Sources:** 
  - Champ robots (quadrupeds)
  - TurtleBot3
  - Franka Panda
  - Universal Robots (UR3/UR5/UR10)
  - Unitree quadrupeds
  - Drones
- **License:** Various (see individual robot model licenses)
- **Catalog:** [robot-models/ROBOT_MODELS_CATALOG.md](robot-models/ROBOT_MODELS_CATALOG.md)

---

## License Summary

| Component | License | Commercial Use |
|-----------|---------|----------------|
| ROA (this project) | MIT | ✅ Yes |
| ROS2 Humble | Apache 2.0 | ✅ Yes |
| Fast-DDS | Apache 2.0 | ✅ Yes |
| Unreal Engine 5 | UE EULA | ⚠️ Conditional |
| Python packages | Various (mostly MIT/BSD/Apache) | ✅ Yes |
| Grafana/Loki | AGPL 3.0 | ⚠️ See AGPL terms |

**Note:** Always review individual license files for authoritative licensing terms.

---

## Acknowledgments

ROA would not exist without the incredible work of the open-source robotics community. Special thanks to:

- **Open Robotics** - ROS2, Gazebo, and the entire ROS ecosystem
- **eProsima** - Fast-DDS for high-performance DDS
- **Pixar Animation Studios** - Universal Scene Description (USD)
- **Epic Games** - Unreal Engine 5
- **MoveIt maintainers** - Motion planning inspiration
- **All contributors** to the projects listed in SIMILAR_PROJECTS_RESEARCH.md

---

**Document Version:** 1.0  
**Last Updated:** 2026-01-23  
**Maintained By:** ROA Development Team  
**Status:** Complete

For questions about dependencies, see:
- [CONTRIBUTING.md](CONTRIBUTING.md) for development setup
- [README.md](README.md) for installation instructions
- [roa-linux/docs/SIMILAR_PROJECTS_RESEARCH.md](roa-linux/docs/SIMILAR_PROJECTS_RESEARCH.md) for research details
