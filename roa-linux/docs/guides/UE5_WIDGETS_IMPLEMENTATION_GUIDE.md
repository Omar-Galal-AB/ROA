# UE5 Widgets Implementation Guide for ROA
**Date**: 2025-12-13  
**Purpose**: Guide for implementing UE5 C++ widgets without requiring local UE5 installation

---

## Overview

This guide explains how to create UE5 widget code structure that can be developed in this environment and will compile when integrated with actual UE5. The widgets will use mock UE5 APIs for testing.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    ROA UE5 Widgets                      │
│              (Can be developed here!)                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │ ROC Widgets  │  │   Webthread  │  │ FTI/DIMC    │ │
│  │              │  │   Widgets    │  │  Widgets    │ │
│  │ • Control UI │  │ • Monitor UI │  │ • Import UI │ │
│  │ • Sliders    │  │ • Status     │  │ • Tracking  │ │
│  │ • Safety     │  │ • Logs       │  │             │ │
│  └──────────────┘  └──────────────┘  └─────────────┘ │
│                                                         │
│  ┌─────────────────────────────────────────────────┐  │
│  │         Mock UE5 API (for testing)              │  │
│  │  (Replaced with real UE5 SDK during build)      │  │
│  └─────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## Widget Components

### 1. ROC (Robot Operator Controller) Widgets

#### ROCControlPanel
**Purpose**: Main robot control interface

**Features:**
- Robot selector dropdown
- Joint control sliders (6-8 joints)
- Position/Velocity/Torque mode selection
- Real-time position display
- Safety status indicators

**Files:**
- `components/robot-operator-controller/src/ue5/Public/ROCControlPanel.h`
- `components/robot-operator-controller/src/ue5/Private/ROCControlPanel.cpp`

#### ROCSliderWidget
**Purpose**: Individual joint control slider

**Features:**
- Value slider (0-100%)
- Current value display
- Min/Max range display
- Safety zone visualization (yellow/red)
- Lock/unlock capability

#### ROCSafetyOverlay
**Purpose**: Visual safety warnings

**Features:**
- Collision warnings (yellow/red alerts)
- Distance to obstacles
- Safety zone visualization
- Emergency stop button

#### ROCPathVisualizer
**Purpose**: 3D path visualization in viewport

**Features:**
- Render planned paths
- Show waypoints
- Obstacle visualization
- Current robot position marker

---

### 2. Webthread Monitoring Widgets

#### WebthreadStatusPanel
**Purpose**: System status dashboard

**Features:**
- Component health indicators
- CPU/Memory usage graphs
- ROS2 topic status
- Error log display
- Connection status (FTI/DIMC/ROC/COMC)

**Files:**
- `components/webthread/src/ue5/Public/WebthreadStatusPanel.h`
- `components/webthread/src/ue5/Private/WebthreadStatusPanel.cpp`

#### WebthreadLogViewer
**Purpose**: Real-time log viewer

**Features:**
- Scrolling log display
- Severity filtering (Info/Warning/Error)
- Search functionality
- Auto-scroll toggle
- Export logs button

---

### 3. FTI (Files Type Importer) Widgets

#### FTIImportPanel
**Purpose**: Robot model import interface

**Features:**
- File browser
- Format detector display
- Import progress bar
- Preview of imported model
- Import settings (Individual/Assembly)

---

### 4. DIMC (Dimensions Collector) Widgets

#### DIMCTrackingPanel
**Purpose**: Real-time dimension display

**Features:**
- Robot position display (X, Y, Z)
- Orientation display
- Bounding box dimensions
- Distance to other robots
- Movement delta display

---

## Implementation Strategy

### Phase 1: Mock UE5 API (Current - Can do here)

Create mock UE5 classes that simulate the real API:

```cpp
// mock_ue5_api.h
namespace MockUE5 {
    class Widget {
    public:
        virtual void NativeTick(float DeltaTime) {}
        virtual void NativeConstruct() {}
    };
    
    class Slider : public Widget {
    public:
        float Value;
        float MinValue;
        float MaxValue;
        
        void SetValue(float NewValue) { Value = NewValue; }
        float GetValue() const { return Value; }
    };
    
    class TextBlock : public Widget {
    public:
        std::string Text;
        void SetText(const std::string& NewText) { Text = NewText; }
    };
    
    class Button : public Widget {
    public:
        std::function<void()> OnClicked;
        void Click() { if (OnClicked) OnClicked(); }
    };
}
```

### Phase 2: Widget Implementation (Current - Can do here)

Implement widgets using mock API:

```cpp
// ROCControlPanel.h
#ifdef MOCK_UE5
    #include "mock_ue5_api.h"
    using namespace MockUE5;
#else
    #include "Components/Widget.h"
    #include "Components/Slider.h"
    #include "Components/TextBlock.h"
    #include "Components/Button.h"
#endif

class ROCControlPanel : public Widget {
private:
    Slider* Joint1Slider;
    Slider* Joint2Slider;
    TextBlock* StatusText;
    Button* EmergencyStopButton;
    
public:
    ROCControlPanel();
    virtual ~ROCControlPanel();
    
    void NativeTick(float DeltaTime) override;
    void NativeConstruct() override;
    
    void UpdateJointSliders(const std::vector<float>& positions);
    void SetSafetyStatus(const std::string& status);
    void OnEmergencyStopClicked();
};
```

### Phase 3: ROS2 Integration (Current - Can do here)

Connect widgets to ROS2 topics:

```cpp
// ROCControlPanel.cpp
#include <rclcpp/rclcpp.hpp>
#include "roc_interfaces/msg/joint_command.hpp"

void ROCControlPanel::NativeTick(float DeltaTime) {
    // Read ROS2 messages
    auto spatial_data = ros2_bridge_->GetLatestSpatialData();
    
    // Update UI
    if (spatial_data) {
        UpdateJointSliders(spatial_data->joint_positions);
    }
    
    // Check safety status
    auto safety_status = ros2_bridge_->GetSafetyStatus();
    if (safety_status) {
        SetSafetyStatus(safety_status->level);
    }
}

void ROCControlPanel::OnEmergencyStopClicked() {
    // Publish emergency stop command
    auto msg = roc_interfaces::msg::EmergencyStop();
    msg.robot_id = current_robot_id_;
    msg.timestamp = ros2_bridge_->GetCurrentTime();
    
    emergency_stop_publisher_->publish(msg);
}
```

### Phase 4: Real UE5 Integration (After local testing)

Replace mock with real UE5 SDK:
- Remove `#ifdef MOCK_UE5` preprocessor directives
- Link against actual UE5 SDK
- Compile as UE5 plugin

---

## Testing Without UE5

### Unit Tests for Widgets

```cpp
// test_roc_control_panel.cpp
#include "gtest/gtest.h"
#include "ROCControlPanel.h"

TEST(ROCControlPanel, InitializesCorrectly) {
    ROCControlPanel panel;
    EXPECT_NE(panel.Joint1Slider, nullptr);
    EXPECT_NE(panel.Joint2Slider, nullptr);
}

TEST(ROCControlPanel, UpdatesJointSliders) {
    ROCControlPanel panel;
    std::vector<float> positions = {0.5, 1.0, 0.0, 0.5, 0.0, 0.0};
    
    panel.UpdateJointSliders(positions);
    
    EXPECT_FLOAT_EQ(panel.Joint1Slider->GetValue(), 0.5);
    EXPECT_FLOAT_EQ(panel.Joint2Slider->GetValue(), 1.0);
}

TEST(ROCControlPanel, EmergencyStopWorks) {
    ROCControlPanel panel;
    bool stop_called = false;
    
    panel.OnEmergencyStopClicked = [&stop_called]() {
        stop_called = true;
    };
    
    panel.EmergencyStopButton->Click();
    EXPECT_TRUE(stop_called);
}
```

### Integration Tests

```cpp
// test_widget_ros2_integration.cpp
TEST(WidgetIntegration, ReceivesROS2Data) {
    // Create mock ROS2 node
    auto node = std::make_shared<MockROS2Node>();
    
    // Create widget with ROS2 bridge
    ROCControlPanel panel(node);
    
    // Publish test data
    auto msg = roc_interfaces::msg::JointState();
    msg.position = {0.1, 0.2, 0.3, 0.4, 0.5, 0.6};
    node->PublishJointState(msg);
    
    // Tick widget
    panel.NativeTick(0.016);  // 60 FPS
    
    // Verify UI updated
    EXPECT_FLOAT_EQ(panel.Joint1Slider->GetValue(), 0.1);
}
```

---

## Directory Structure

```
components/
├── robot-operator-controller/
│   ├── src/
│   │   └── ue5/
│   │       ├── Public/
│   │       │   ├── ROCControlPanel.h
│   │       │   ├── ROCSliderWidget.h
│   │       │   ├── ROCSafetyOverlay.h
│   │       │   ├── ROCPathVisualizer.h
│   │       │   └── ROCROS2Bridge.h
│   │       ├── Private/
│   │       │   ├── ROCControlPanel.cpp
│   │       │   ├── ROCSliderWidget.cpp
│   │       │   ├── ROCSafetyOverlay.cpp
│   │       │   ├── ROCPathVisualizer.cpp
│   │       │   └── ROCROS2Bridge.cpp
│   │       └── ROC.Build.cs  (UE5 build script)
│   └── tests/
│       └── ue5_widgets/
│           ├── test_roc_control_panel.cpp
│           ├── test_roc_slider.cpp
│           └── test_ros2_bridge.cpp
│
├── webthread/
│   ├── src/
│   │   └── ue5/
│   │       ├── Public/
│   │       │   ├── WebthreadStatusPanel.h
│   │       │   ├── WebthreadLogViewer.h
│   │       │   └── WebthreadROS2Bridge.h
│   │       └── Private/
│   │           ├── WebthreadStatusPanel.cpp
│   │           ├── WebthreadLogViewer.cpp
│   │           └── WebthreadROS2Bridge.cpp
│
└── mock_ue5/  (NEW - for testing without UE5)
    ├── include/
    │   ├── mock_ue5_api.h
    │   ├── mock_widget.h
    │   ├── mock_slate.h
    │   └── mock_ros2_bridge.h
    └── src/
        ├── mock_ue5_api.cpp
        └── mock_widget.cpp
```

---

## Build System

### CMakeLists.txt for Mock Build

```cmake
cmake_minimum_required(VERSION 3.16)
project(ROA_UE5_Widgets_Mock)

set(CMAKE_CXX_STANDARD 17)

# Include directories
include_directories(
    ${CMAKE_SOURCE_DIR}/components/mock_ue5/include
    ${CMAKE_SOURCE_DIR}/components/robot-operator-controller/src/ue5/Public
)

# Define MOCK_UE5 preprocessor flag
add_compile_definitions(MOCK_UE5)

# Build ROC widgets with mock
add_library(roc_widgets_mock
    components/robot-operator-controller/src/ue5/Private/ROCControlPanel.cpp
    components/robot-operator-controller/src/ue5/Private/ROCSliderWidget.cpp
    components/robot-operator-controller/src/ue5/Private/ROCROS2Bridge.cpp
    components/mock_ue5/src/mock_ue5_api.cpp
)

# Tests
enable_testing()
find_package(GTest REQUIRED)

add_executable(widget_tests
    components/robot-operator-controller/tests/ue5_widgets/test_roc_control_panel.cpp
)

target_link_libraries(widget_tests
    roc_widgets_mock
    GTest::GTest
    GTest::Main
)

add_test(NAME widget_tests COMMAND widget_tests)
```

### UE5 Plugin Build Script (for real UE5)

```csharp
// ROC.Build.cs
using UnrealBuildTool;

public class ROC : ModuleRules
{
    public ROC(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(new string[] {
            "Core",
            "CoreUObject",
            "Engine",
            "InputCore",
            "Slate",
            "SlateCore",
            "UMG"
        });

        PrivateDependencyModuleNames.AddRange(new string[] {
            // ROS2 plugin (if using UE5 ROS2 integration)
            "ROS2"
        });
    }
}
```

---

## Qt Designer Integration

When you provide `.ui` files from Qt Designer:

1. **Conversion to UE5 Slate/UMG**
   - Qt layouts → UE5 Canvas/Vertical/Horizontal Box
   - Qt widgets → UE5 equivalent widgets
   - Signals/slots → UE5 delegates

2. **Automated Conversion Tool**
   ```python
   # ui_to_ue5_converter.py
   import xml.etree.ElementTree as ET
   
   def convert_qt_ui_to_ue5(qt_ui_file):
       tree = ET.parse(qt_ui_file)
       root = tree.getroot()
       
       # Parse Qt UI
       widgets = parse_qt_widgets(root)
       
       # Generate UE5 C++ code
       cpp_code = generate_ue5_widget_code(widgets)
       
       return cpp_code
   ```

3. **Widget Mapping**
   ```
   Qt Widget         →  UE5 Widget
   ─────────────────────────────────────
   QPushButton       →  UButton
   QSlider           →  USlider
   QLabel            →  UTextBlock
   QLineEdit         →  UEditableTextBox
   QComboBox         →  UComboBoxString
   QCheckBox         →  UCheckBox
   QProgressBar      →  UProgressBar
   QTextEdit         →  UMultiLineEditableTextBox
   ```

---

## Next Steps

1. **Create Mock UE5 API** (Phase 1)
   - Basic widget classes
   - Slate/UMG simulation
   - Event system

2. **Implement ROC Widgets** (Phase 2)
   - Control panel
   - Sliders
   - Safety overlay
   - Path visualizer

3. **Add ROS2 Integration** (Phase 3)
   - Bridge classes
   - Topic subscribers/publishers
   - Data conversion

4. **Test with Mocks** (Phase 4)
   - Unit tests
   - Integration tests
   - Performance tests

5. **Prepare for UE5 Integration** (Phase 5)
   - Build scripts
   - Plugin metadata
   - Documentation

---

## Benefits of This Approach

✅ **Develop without UE5** - Can write and test widget code here  
✅ **Rapid iteration** - No UE5 compile times during development  
✅ **Unit testable** - Can test widget logic with Google Test  
✅ **ROS2 integration** - Connect to real ROS2 topics for testing  
✅ **Easy transition** - Remove `MOCK_UE5` flag when ready for real UE5  

---

## Summary

- UE5 widgets CAN be developed here using mock APIs
- Full widget logic and ROS2 integration can be implemented
- Comprehensive testing without requiring UE5 installation
- Seamless transition to real UE5 when ready
- Qt Designer `.ui` files can be converted to UE5 widgets

---

**Ready to Implement**: Yes - Mock API framework can be created immediately  
**Estimated Effort**: 1-2 weeks for complete widget implementation  
**Next Action**: Create mock_ue5 module and start implementing ROC widgets
