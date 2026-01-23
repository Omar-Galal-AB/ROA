# ROS2 Native Integration Guide

**For:** ROA v0.2 Plugin  
**Purpose:** Instructions for integrating rclcpp and Fast-DDS ThirdParty libraries

---

## Overview

ROA v0.2 uses embedded ROS2 libraries (rclcpp + Fast-DDS) for native DDS communication with <5ms latency.

This guide explains how to obtain and integrate these libraries into the UE5 plugin.

---

## Option 1: Pre-built Windows Binaries (Recommended)

### 1. Download ROS2 Humble for Windows

```powershell
# Download ROS2 Humble Windows binary
# https://github.com/ros2/ros2/releases

# Extract to C:\ros2_humble
# Folder structure:
C:\ros2_humble\
├── bin\          # DLLs
├── include\      # Headers
├── lib\          # .lib files
├── share\        # CMake configs
└── tools\
```

### 2. Extract Required Libraries

**Copy to Plugin ThirdParty:**

```powershell
# Create ThirdParty structure
mkdir Plugins/ROA_PlugIn/ThirdParty/rclcpp
mkdir Plugins/ROA_PlugIn/ThirdParty/FastDDS

# Copy rclcpp
xcopy /E /I C:\ros2_humble\include\rclcpp Plugins/ROA_PlugIn/ThirdParty/rclcpp/include/rclcpp
xcopy /E /I C:\ros2_humble\include\rcl Plugins/ROA_PlugIn/ThirdParty/rclcpp/include/rcl
xcopy /E /I C:\ros2_humble\include\rmw Plugins/ROA_PlugIn/ThirdParty/rclcpp/include/rmw
xcopy C:\ros2_humble\lib\rclcpp*.lib Plugins/ROA_PlugIn/ThirdParty/rclcpp/lib\
xcopy C:\ros2_humble\bin\rclcpp*.dll Plugins/ROA_PlugIn/ThirdParty/rclcpp/bin\

# Copy Fast-DDS
xcopy /E /I C:\ros2_humble\include\fastdds Plugins/ROA_PlugIn/ThirdParty/FastDDS/include/fastdds
xcopy /E /I C:\ros2_humble\include\fastrtps Plugins/ROA_PlugIn/ThirdParty/FastDDS/include/fastrtps
xcopy C:\ros2_humble\lib\fastrtps*.lib Plugins/ROA_PlugIn/ThirdParty/FastDDS/lib\
xcopy C:\ros2_humble\bin\fastrtps*.dll Plugins/ROA_PlugIn/ThirdParty/FastDDS/bin\
```

### 3. Final ThirdParty Structure

```
Plugins/ROA_PlugIn/ThirdParty/
├── rclcpp/
│   ├── include/
│   │   ├── rclcpp/
│   │   ├── rcl/
│   │   └── rmw/
│   ├── lib/
│   │   ├── rclcpp.lib
│   │   ├── rcl.lib
│   │   └── rmw.lib
│   └── bin/
│       ├── rclcpp.dll
│       ├── rcl.dll
│       └── rmw.dll
└── FastDDS/
    ├── include/
    │   ├── fastdds/
    │   └── fastrtps/
    ├── lib/
    │   └── fastrtps.lib
    └── bin/
        └── fastrtps.dll
```

---

## Option 2: Build from Source (Advanced)

### Prerequisites

- Visual Studio 2022
- CMake 3.20+
- Python 3.10+

### Build ROS2 from Source

```bash
# Follow official guide:
# https://docs.ros.org/en/humble/Installation/Windows-Development-Setup.html

# Clone repos
mkdir C:\ros2_humble_src
cd C:\ros2_humble_src
vcs import --input https://raw.githubusercontent.com/ros2/ros2/humble/ros2.repos

# Build
colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release

# Extract libraries (same as Option 1)
```

---

## Option 3: Use ROA Pre-packaged (Future)

```bash
# When available, download pre-configured ThirdParty package
# https://github.com/Omar-Galal-AB/ROA/releases/ThirdParty-v0.2.0.zip

# Extract to Plugins/ROA_PlugIn/ThirdParty/
```

---

## Integration Steps

### 1. Update ROA.Build.cs

The build file has been prepared with ThirdParty paths:

```csharp
// File: Source/ROA/ROA.Build.cs

// ThirdParty rclcpp
PublicIncludePaths.Add(Path.Combine(ThirdPartyPath, "rclcpp", "include"));
PublicAdditionalLibraries.Add(Path.Combine(ThirdPartyPath, "rclcpp", "lib", "rclcpp.lib"));
RuntimeDependencies.Add(Path.Combine(ThirdPartyPath, "rclcpp", "bin", "rclcpp.dll"));

// ThirdParty Fast-DDS
PublicIncludePaths.Add(Path.Combine(ThirdPartyPath, "FastDDS", "include"));
PublicAdditionalLibraries.Add(Path.Combine(ThirdPartyPath, "FastDDS", "lib", "fastrtps.lib"));
RuntimeDependencies.Add(Path.Combine(ThirdPartyPath, "FastDDS", "bin", "fastrtps.dll"));
```

### 2. Verify Integration

**Test Compilation:**

```cpp
// In any .cpp file:
#include <rclcpp/rclcpp.hpp>

void TestROS2()
{
    // If this compiles, rclcpp is integrated correctly
    rclcpp::init(0, nullptr);
    auto node = std::make_shared<rclcpp::Node>("test_node");
    UE_LOG(LogTemp, Log, TEXT("ROS2 initialized successfully!"));
    rclcpp::shutdown();
}
```

### 3. Enable Native Mode

**In ROS2Context.cpp:**

```cpp
bool FROS2Context::IsNativeModeAvailable() const
{
    // Change from:
    return false;
    
    // To:
    return true;  // rclcpp is now available!
}
```

---

## Troubleshooting

### "Cannot open include file: 'rclcpp/rclcpp.hpp'"

**Solution:** Check ThirdParty/rclcpp/include path exists and is added to PublicIncludePaths

### "LNK2019: unresolved external symbol"

**Solution:** Verify .lib files in ThirdParty/rclcpp/lib and paths in ROA.Build.cs

### "DLL not found" at runtime

**Solution:** Ensure DLLs are in ThirdParty/*/bin and RuntimeDependencies are set

### WSL/Linux Build

For Linux builds (WSL development):

```bash
# Install ROS2 Humble normally
sudo apt install ros-humble-desktop

# Plugin will use system ROS2 libraries
# No ThirdParty folder needed on Linux
```

---

## Current Status

**As of v0.2.0-alpha:**
- ✓ ThirdParty folder structure created
- ✓ Build.cs prepared for integration
- ✓ Stub implementation functional (TCP fallback)
- ⏳ Awaiting library files (user must obtain from ROS2)
- ⏳ Native mode disabled until libraries added

**Next Steps:**
1. User obtains ROS2 libraries (Option 1 recommended)
2. Place in ThirdParty folders
3. Rebuild plugin
4. Test native mode

---

## Testing Native ROS2

**After integration, test with:**

```cpp
// In any Blueprint or C++

// 1. Check native mode available
bool bAvailable = FROS2Context::Get().IsNativeModeAvailable();
// Should return true

// 2. Spawn robot with ROS2 node
AROARobotActor* Robot = World->SpawnActor<AROARobotActor>();
auto NodeComp = Robot->AddComponent<UROS2NodeComponent>();
// Should create native rclcpp::Node

// 3. Test publisher
auto PubComp = Robot->AddComponent<UROS2PublisherComponent>();
PubComp->TopicName = "/test";
PubComp->MessageType = "std_msgs/msg/String";
// Should create native rclcpp::Publisher

// 4. Verify from WSL
ros2 topic list
// Should see /test

ros2 topic echo /test
// Should receive messages from UE5
```

---

## Support

For issues:
- Check [GitHub Issues](https://github.com/Omar-Galal-AB/ROA/issues)
- ROS2 Humble docs: https://docs.ros.org/en/humble/
- Fast-DDS docs: https://fast-dds.docs.eprosima.com/

