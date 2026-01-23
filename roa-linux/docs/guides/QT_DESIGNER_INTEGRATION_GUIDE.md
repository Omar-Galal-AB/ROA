# Qt Designer Integration Guide for ROA
**Date**: 2025-12-13  
**Purpose**: Guide for integrating Qt Designer UI files into ROA components

---

## Overview

This guide explains how to integrate Qt Designer `.ui` files into ROA components (ROC, Webthread). Qt Designer files can be converted to Python code or C++ code for use in ROA.

---

## Qt Designer to Python Workflow

### Step 1: Create UI in Qt Designer

**Example**: ROC Control Panel

```xml
<!-- roc_control_panel.ui -->
<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>ROCControlPanel</class>
 <widget class="QWidget" name="ROCControlPanel">
  <layout class="QVBoxLayout" name="verticalLayout">
   
   <!-- Robot Selector -->
   <widget class="QComboBox" name="robotSelector">
    <property name="toolTip">
     <string>Select robot to control</string>
    </property>
   </widget>
   
   <!-- Control Mode -->
   <widget class="QGroupBox" name="controlModeGroup">
    <property name="title">
     <string>Control Mode</string>
    </property>
    <layout class="QHBoxLayout">
     <widget class="QRadioButton" name="rpmModeRadio">
      <property name="text">
       <string>RPM (Manual)</string>
      </property>
     </widget>
     <widget class="QRadioButton" name="admModeRadio">
      <property name="text">
       <string>ADM (Autonomous)</string>
      </property>
     </widget>
    </layout>
   </widget>
   
   <!-- Joint Control Sliders -->
   <widget class="QGroupBox" name="jointControlGroup">
    <property name="title">
     <string>Joint Control</string>
    </property>
    <layout class="QVBoxLayout">
     
     <!-- Joint 1 -->
     <layout class="QHBoxLayout">
      <widget class="QLabel" name="joint1Label">
       <property name="text">
        <string>Joint 1:</string>
       </property>
      </widget>
      <widget class="QSlider" name="joint1Slider">
       <property name="orientation">
        <enum>Qt::Horizontal</enum>
       </property>
       <property name="minimum">
        <number>-180</number>
       </property>
       <property name="maximum">
        <number>180</number>
       </property>
      </widget>
      <widget class="QLabel" name="joint1Value">
       <property name="text">
        <string>0.0°</string>
       </property>
      </widget>
     </layout>
     
     <!-- Repeat for joints 2-6 -->
     
    </layout>
   </widget>
   
   <!-- Status Display -->
   <widget class="QGroupBox" name="statusGroup">
    <property name="title">
     <string>Status</string>
    </property>
    <layout class="QVBoxLayout">
     <widget class="QTextEdit" name="statusText">
      <property name="readOnly">
       <bool>true</bool>
      </property>
     </widget>
    </layout>
   </widget>
   
   <!-- Control Buttons -->
   <layout class="QHBoxLayout">
    <widget class="QPushButton" name="emergencyStopButton">
     <property name="text">
      <string>Emergency Stop</string>
     </property>
     <property name="styleSheet">
      <string>background-color: red; color: white; font-weight: bold;</string>
     </property>
    </widget>
    <widget class="QPushButton" name="resetButton">
     <property name="text">
      <string>Reset</string>
     </property>
    </widget>
   </layout>
   
  </layout>
 </widget>
</ui>
```

### Step 2: Convert UI to Python

```bash
# Using pyuic5 (for PyQt5)
pyuic5 roc_control_panel.ui -o roc_control_panel_ui.py

# Using pyside6-uic (for PySide6)
pyside6-uic roc_control_panel.ui -o roc_control_panel_ui.py
```

**Generated Python Code:**

```python
# roc_control_panel_ui.py (auto-generated)
from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_ROCControlPanel(object):
    def setupUi(self, ROCControlPanel):
        ROCControlPanel.setObjectName("ROCControlPanel")
        
        # Create widgets
        self.verticalLayout = QtWidgets.QVBoxLayout(ROCControlPanel)
        self.robotSelector = QtWidgets.QComboBox(ROCControlPanel)
        self.controlModeGroup = QtWidgets.QGroupBox(ROCControlPanel)
        # ... etc
        
        self.retranslateUi(ROCControlPanel)
        QtCore.QMetaObject.connectSlotsByName(ROCControlPanel)
    
    def retranslateUi(self, ROCControlPanel):
        _translate = QtCore.QCoreApplication.translate
        ROCControlPanel.setWindowTitle(_translate("ROCControlPanel", "ROC Control Panel"))
        # ... etc
```

### Step 3: Create Application Logic

```python
# roc_control_panel.py
from PyQt5.QtWidgets import QWidget
from roc_control_panel_ui import Ui_ROCControlPanel
import rclpy
from rclpy.node import Node

class ROCControlPanel(QWidget):
    """ROC Control Panel with Qt UI"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Setup UI from Qt Designer
        self.ui = Ui_ROCControlPanel()
        self.ui.setupUi(self)
        
        # Initialize ROS2 node
        rclpy.init()
        self.ros2_node = Node('roc_control_panel')
        
        # Setup ROS2 publishers/subscribers
        self.command_publisher = self.ros2_node.create_publisher(
            ControlCommand, '/roc/commands', 10
        )
        
        # Connect signals to slots
        self.ui.emergencyStopButton.clicked.connect(self.on_emergency_stop)
        self.ui.joint1Slider.valueChanged.connect(self.on_joint1_changed)
        self.ui.robotSelector.currentTextChanged.connect(self.on_robot_changed)
        
        # Setup timer for ROS2 spin
        self.ros2_timer = QtCore.QTimer()
        self.ros2_timer.timeout.connect(self.ros2_spin_once)
        self.ros2_timer.start(16)  # 60 Hz
        
        # Current state
        self.current_robot_id = None
        self.joint_positions = [0.0] * 6
    
    def on_emergency_stop(self):
        """Handle emergency stop button click"""
        msg = EmergencyStopCommand()
        msg.robot_id = self.current_robot_id
        msg.timestamp = self.ros2_node.get_clock().now().to_msg()
        
        self.command_publisher.publish(msg)
        self.ui.statusText.append("EMERGENCY STOP ACTIVATED!")
    
    def on_joint1_changed(self, value):
        """Handle joint 1 slider change"""
        # Convert slider value (-180 to 180) to radians
        angle_rad = value * 3.14159 / 180.0
        self.joint_positions[0] = angle_rad
        
        # Update value label
        self.ui.joint1Value.setText(f"{value}°")
        
        # Send command to robot
        self.send_joint_command()
    
    def on_robot_changed(self, robot_id):
        """Handle robot selection change"""
        self.current_robot_id = robot_id
        self.ui.statusText.append(f"Selected robot: {robot_id}")
    
    def send_joint_command(self):
        """Send joint position command via ROS2"""
        if self.current_robot_id is None:
            return
        
        msg = ControlCommand()
        msg.robot_id = self.current_robot_id
        msg.command_type = "position"
        msg.joint_values = self.joint_positions
        
        self.command_publisher.publish(msg)
    
    def ros2_spin_once(self):
        """Process ROS2 callbacks"""
        rclpy.spin_once(self.ros2_node, timeout_sec=0)
    
    def closeEvent(self, event):
        """Clean up on close"""
        self.ros2_timer.stop()
        self.ros2_node.destroy_node()
        rclpy.shutdown()
        event.accept()


# Main application
if __name__ == '__main__':
    import sys
    from PyQt5.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    panel = ROCControlPanel()
    panel.show()
    sys.exit(app.exec_())
```

---

## Qt Designer to C++ Workflow

### Step 1: Convert UI to C++

```bash
# Using uic (Qt's UI compiler)
uic roc_control_panel.ui -o ui_roc_control_panel.h
```

**Generated C++ Header:**

```cpp
// ui_roc_control_panel.h (auto-generated)
#ifndef UI_ROCCONTROLPANEL_H
#define UI_ROCCONTROLPANEL_H

#include <QtWidgets/QWidget>
#include <QtWidgets/QVBoxLayout>
#include <QtWidgets/QComboBox>
#include <QtWidgets/QSlider>
#include <QtWidgets/QPushButton>

class Ui_ROCControlPanel
{
public:
    QVBoxLayout *verticalLayout;
    QComboBox *robotSelector;
    QSlider *joint1Slider;
    QPushButton *emergencyStopButton;
    
    void setupUi(QWidget *ROCControlPanel)
    {
        // Create and configure widgets
        verticalLayout = new QVBoxLayout(ROCControlPanel);
        robotSelector = new QComboBox(ROCControlPanel);
        verticalLayout->addWidget(robotSelector);
        // ... etc
    }
    
    void retranslateUi(QWidget *ROCControlPanel)
    {
        ROCControlPanel->setWindowTitle(
            QCoreApplication::translate("ROCControlPanel", "ROC Control Panel", nullptr)
        );
    }
};

#endif
```

### Step 2: Create C++ Application

```cpp
// roc_control_panel.h
#ifndef ROC_CONTROL_PANEL_H
#define ROC_CONTROL_PANEL_H

#include <QWidget>
#include <QTimer>
#include <rclcpp/rclcpp.hpp>
#include "ui_roc_control_panel.h"

class ROCControlPanel : public QWidget
{
    Q_OBJECT

public:
    explicit ROCControlPanel(QWidget *parent = nullptr);
    ~ROCControlPanel();

private slots:
    void onEmergencyStopClicked();
    void onJoint1Changed(int value);
    void onRobotChanged(const QString &robot_id);
    void ros2SpinOnce();

private:
    Ui_ROCControlPanel *ui;
    rclcpp::Node::SharedPtr ros2_node_;
    rclcpp::Publisher<ControlCommand>::SharedPtr command_publisher_;
    QTimer *ros2_timer_;
    
    QString current_robot_id_;
    std::vector<double> joint_positions_;
    
    void sendJointCommand();
};

#endif
```

```cpp
// roc_control_panel.cpp
#include "roc_control_panel.h"

ROCControlPanel::ROCControlPanel(QWidget *parent)
    : QWidget(parent)
    , ui(new Ui_ROCControlPanel)
    , joint_positions_(6, 0.0)
{
    // Setup UI
    ui->setupUi(this);
    
    // Initialize ROS2
    rclcpp::init(0, nullptr);
    ros2_node_ = rclcpp::Node::make_shared("roc_control_panel");
    
    command_publisher_ = ros2_node_->create_publisher<ControlCommand>(
        "/roc/commands", 10
    );
    
    // Connect Qt signals to slots
    connect(ui->emergencyStopButton, &QPushButton::clicked,
            this, &ROCControlPanel::onEmergencyStopClicked);
    connect(ui->joint1Slider, &QSlider::valueChanged,
            this, &ROCControlPanel::onJoint1Changed);
    connect(ui->robotSelector, &QComboBox::currentTextChanged,
            this, &ROCControlPanel::onRobotChanged);
    
    // Setup ROS2 timer
    ros2_timer_ = new QTimer(this);
    connect(ros2_timer_, &QTimer::timeout, this, &ROCControlPanel::ros2SpinOnce);
    ros2_timer_->start(16);  // 60 Hz
}

ROCControlPanel::~ROCControlPanel()
{
    ros2_timer_->stop();
    rclcpp::shutdown();
    delete ui;
}

void ROCControlPanel::onEmergencyStopClicked()
{
    auto msg = std::make_unique<EmergencyStopCommand>();
    msg->robot_id = current_robot_id_.toStdString();
    msg->timestamp = ros2_node_->get_clock()->now();
    
    command_publisher_->publish(std::move(msg));
    ui->statusText->append("EMERGENCY STOP ACTIVATED!");
}

void ROCControlPanel::onJoint1Changed(int value)
{
    // Convert to radians
    double angle_rad = value * M_PI / 180.0;
    joint_positions_[0] = angle_rad;
    
    // Update label
    ui->joint1Value->setText(QString::number(value) + "°");
    
    // Send command
    sendJointCommand();
}

void ROCControlPanel::sendJointCommand()
{
    if (current_robot_id_.isEmpty()) return;
    
    auto msg = std::make_unique<ControlCommand>();
    msg->robot_id = current_robot_id_.toStdString();
    msg->command_type = "position";
    msg->joint_values = joint_positions_;
    
    command_publisher_->publish(std::move(msg));
}

void ROCControlPanel::ros2SpinOnce()
{
    rclcpp::spin_some(ros2_node_);
}
```

---

## Qt Designer to UE5 Conversion

**Automated Converter Script:**

```python
# qt_to_ue5_converter.py
import xml.etree.ElementTree as ET
from typing import Dict, List

class QtToUE5Converter:
    """Convert Qt Designer .ui files to UE5 widget code"""
    
    WIDGET_MAPPING = {
        'QPushButton': 'UButton',
        'QSlider': 'USlider',
        'QLabel': 'UTextBlock',
        'QLineEdit': 'UEditableTextBox',
        'QComboBox': 'UComboBoxString',
        'QCheckBox': 'UCheckBox',
        'QRadioButton': 'UCheckBox',  # UE5 uses CheckBox for radio
        'QTextEdit': 'UMultiLineEditableTextBox',
        'QProgressBar': 'UProgressBar',
        'QGroupBox': 'UBorder',  # Or custom widget
    }
    
    def __init__(self, ui_file_path: str):
        self.ui_file = ui_file_path
        self.tree = ET.parse(ui_file_path)
        self.root = self.tree.getroot()
    
    def convert_to_ue5(self) -> Dict[str, str]:
        """Convert Qt UI to UE5 widget code"""
        header_code = self.generate_ue5_header()
        cpp_code = self.generate_ue5_cpp()
        
        return {
            'header': header_code,
            'cpp': cpp_code
        }
    
    def generate_ue5_header(self) -> str:
        """Generate UE5 .h file"""
        class_name = self.root.find(".//class").text
        
        widgets = self.parse_widgets()
        
        header = f"""
// {class_name}.h
// Auto-generated from Qt Designer .ui file

#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "Components/Button.h"
#include "Components/Slider.h"
#include "Components/TextBlock.h"
#include "{class_name}.generated.h"

UCLASS()
class U{class_name} : public UUserWidget
{{
    GENERATED_BODY()

public:
    virtual void NativeConstruct() override;
    virtual void NativeTick(const FGeometry& MyGeometry, float DeltaTime) override;

protected:
"""
        
        # Add widget properties
        for widget in widgets:
            ue5_type = self.WIDGET_MAPPING.get(widget['class'], 'UWidget')
            header += f"    UPROPERTY(meta = (BindWidget))\\n"
            header += f"    {ue5_type}* {widget['name']};\\n\\n"
        
        # Add event handlers
        header += """
    UFUNCTION()
    void OnEmergencyStopClicked();
    
    UFUNCTION()
    void OnSliderValueChanged(float Value);
}};
"""
        
        return header
    
    def generate_ue5_cpp(self) -> str:
        """Generate UE5 .cpp file"""
        class_name = self.root.find(".//class").text
        
        cpp = f"""
// {class_name}.cpp
// Auto-generated from Qt Designer .ui file

#include "{class_name}.h"
#include "Components/Button.h"
#include "Components/Slider.h"

void U{class_name}::NativeConstruct()
{{
    Super::NativeConstruct();
    
    // Bind button events
    if (EmergencyStopButton)
    {{
        EmergencyStopButton->OnClicked.AddDynamic(this, &U{class_name}::OnEmergencyStopClicked);
    }}
    
    // Bind slider events
    if (Joint1Slider)
    {{
        Joint1Slider->OnValueChanged.AddDynamic(this, &U{class_name}::OnSliderValueChanged);
    }}
}}

void U{class_name}::NativeTick(const FGeometry& MyGeometry, float DeltaTime)
{{
    Super::NativeTick(MyGeometry, DeltaTime);
    
    // Update UI based on ROS2 data
    // ...
}}

void U{class_name}::OnEmergencyStopClicked()
{{
    // Handle emergency stop
    UE_LOG(LogTemp, Warning, TEXT("Emergency Stop Clicked!"));
}}

void U{class_name}::OnSliderValueChanged(float Value)
{{
    // Handle slider change
    UE_LOG(LogTemp, Log, TEXT("Slider Value: %f"), Value);
}}
"""
        
        return cpp
    
    def parse_widgets(self) -> List[Dict]:
        """Parse widgets from Qt UI XML"""
        widgets = []
        
        for widget in self.root.findall(".//widget"):
            widget_info = {
                'class': widget.get('class'),
                'name': widget.get('name')
            }
            widgets.append(widget_info)
        
        return widgets


# Usage
if __name__ == '__main__':
    converter = QtToUE5Converter('roc_control_panel.ui')
    code = converter.convert_to_ue5()
    
    # Write files
    with open('ROCControlPanel.h', 'w') as f:
        f.write(code['header'])
    
    with open('ROCControlPanel.cpp', 'w') as f:
        f.write(code['cpp'])
    
    print("Conversion complete!")
```

---

## Integration Workflow

### When You Provide .ui Files

1. **Save .ui file** to appropriate component directory
2. **Run converter** to generate code
3. **Integrate with ROS2** bridge
4. **Test** in mock environment
5. **Deploy** to actual Qt/UE5 when ready

### File Organization

```
components/robot-operator-controller/
├── ui_designs/
│   ├── roc_control_panel.ui      # Qt Designer file
│   ├── roc_safety_panel.ui
│   └── roc_path_planner.ui
├── src/
│   ├── qt/                        # Qt application
│   │   ├── roc_control_panel.py  # Generated + logic
│   │   └── main.py
│   └── ue5/                       # UE5 widgets
│       ├── Public/
│       │   └── ROCControlPanel.h  # Converted from .ui
│       └── Private/
│           └── ROCControlPanel.cpp
```

---

## Summary

- **Qt Designer files (.ui) can be integrated** into ROA
- **Python**: Use pyuic5/pyside6-uic for conversion
- **C++**: Use uic for Qt applications
- **UE5**: Use custom converter script
- **Automatic conversion** saves development time
- **Ready for integration** when you provide .ui files

**Next Steps When You Provide .ui Files:**
1. Place files in appropriate component directory
2. Run conversion scripts
3. Integrate with ROS2 bridge code
4. Test in simulation environment
5. Deploy to production

---

**Ready**: Yes - Can integrate Qt Designer files immediately  
**Tools**: Conversion scripts provided  
**Workflow**: Automated with minimal manual work
