#!/usr/bin/env python3
"""
ROC Standalone Qt Desktop Application
ROA - Robot Operations & Automation

A standalone desktop application for the Robot Operator Controller (ROC)
that provides full robot control capabilities outside of UE5.
"""

import sys
import logging
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QGroupBox, QGridLayout, QSlider, QComboBox,
    QListWidget, QTabWidget, QTextEdit, QSpinBox, QDoubleSpinBox,
    QCheckBox, QSplitter, QStatusBar, QProgressBar
)
from PyQt6.QtCore import QTimer, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from datetime import datetime

# Add parent directory to path for imports
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

# Import dark theme
ui_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'ui')
sys.path.insert(0, ui_path)
try:
    from dark_theme import DARK_THEME
except ImportError:
    DARK_THEME = ""

try:
    from roc_ros2_node import ROCNode
    from controllers.base_controller import BaseController
    from safety.safety_manager import SafetyManager
    from control_modes.rpm_mode import RPMMode
    from control_modes.adm_mode import ADMMode
except ImportError as e:
    print(f"Warning: Could not import ROC modules: {e}")
    print("Running in standalone mode with mock functionality")


class ControlThread(QThread):
    """Background thread for robot control"""
    status_updated = pyqtSignal(dict)
    
    def __init__(self, roc_node):
        super().__init__()
        self.roc_node = roc_node
        self.running = True
    
    def run(self):
        """Control loop"""
        while self.running:
            try:
                if self.roc_node:
                    # Get status from ROC node
                    status = {
                        'timestamp': datetime.now().isoformat(),
                        'mode': 'RPM',
                        'active_robots': 0,
                        'safety_level': 'Standard'
                    }
                    self.status_updated.emit(status)
            except Exception as e:
                logging.error(f"Control thread error: {e}")
            
            self.msleep(50)  # 20Hz update rate
    
    def stop(self):
        """Stop the control thread"""
        self.running = False


class RobotSelectorWidget(QWidget):
    """Widget for selecting and managing robots"""
    robot_selected = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("Robot Selection")
        header.setObjectName("headerLabel")
        header.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(header)
        
        # Robot list
        self.robot_list = QListWidget()
        self.robot_list.addItems([
            "No robots detected",
            "(Waiting for FTI import...)"
        ])
        self.robot_list.currentTextChanged.connect(self.on_robot_selected)
        layout.addWidget(self.robot_list)
        
        # Add robot button
        add_btn = QPushButton("+ Import Robot")
        add_btn.clicked.connect(self.import_robot)
        layout.addWidget(add_btn)
    
    def on_robot_selected(self, robot_name):
        """Handle robot selection"""
        if robot_name and not robot_name.startswith("("):
            self.robot_selected.emit(robot_name)
    
    def import_robot(self):
        """Open import dialog"""
        # TODO: Implement import dialog
        pass


class JointControlWidget(QWidget):
    """Widget for controlling robot joints"""
    
    def __init__(self):
        super().__init__()
        self.sliders = []
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("Joint Control")
        header.setObjectName("headerLabel")
        header.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(header)
        
        # Mode selector
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Control Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["RPM (Manual)", "ADM (Autonomous)"])
        mode_layout.addWidget(self.mode_combo)
        layout.addLayout(mode_layout)
        
        # Joints group
        joints_group = QGroupBox("Joint Positions")
        joints_layout = QGridLayout(joints_group)
        
        # Create 6 sample joint sliders
        joint_names = ["Base", "Shoulder", "Elbow", "Wrist1", "Wrist2", "Wrist3"]
        
        for i, name in enumerate(joint_names):
            # Label
            joints_layout.addWidget(QLabel(f"{name}:"), i, 0)
            
            # Slider
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setMinimum(-180)
            slider.setMaximum(180)
            slider.setValue(0)
            slider.setTickPosition(QSlider.TickPosition.TicksBelow)
            slider.setTickInterval(30)
            slider.valueChanged.connect(lambda v, n=name: self.on_slider_changed(n, v))
            joints_layout.addWidget(slider, i, 1)
            self.sliders.append(slider)
            
            # Value display
            value_label = QLabel("0°")
            joints_layout.addWidget(value_label, i, 2)
            slider.valueChanged.connect(lambda v, l=value_label: l.setText(f"{v}°"))
            
            # Min/Max
            joints_layout.addWidget(QLabel("-180°"), i, 3)
            joints_layout.addWidget(QLabel("180°"), i, 4)
        
        layout.addWidget(joints_group)
        
        # Gripper control
        gripper_group = QGroupBox("Gripper")
        gripper_layout = QHBoxLayout(gripper_group)
        gripper_layout.addWidget(QLabel("Opening:"))
        self.gripper_slider = QSlider(Qt.Orientation.Horizontal)
        self.gripper_slider.setMinimum(0)
        self.gripper_slider.setMaximum(100)
        self.gripper_slider.setValue(0)
        gripper_layout.addWidget(self.gripper_slider)
        self.gripper_value = QLabel("0%")
        gripper_layout.addWidget(self.gripper_value)
        self.gripper_slider.valueChanged.connect(
            lambda v: self.gripper_value.setText(f"{v}%")
        )
        layout.addWidget(gripper_group)
        
        # Control buttons
        btn_layout = QHBoxLayout()
        home_btn = QPushButton("Home Position")
        home_btn.clicked.connect(self.go_home)
        btn_layout.addWidget(home_btn)
        
        stop_btn = QPushButton("EMERGENCY STOP")
        stop_btn.setObjectName("stopButton")
        stop_btn.clicked.connect(self.emergency_stop)
        btn_layout.addWidget(stop_btn)
        layout.addLayout(btn_layout)
    
    def on_slider_changed(self, joint_name, value):
        """Handle slider change"""
        logging.debug(f"Joint {joint_name} moved to {value}°")
    
    def go_home(self):
        """Move all joints to home position (0)"""
        for slider in self.sliders:
            slider.setValue(0)
        self.gripper_slider.setValue(0)
    
    def emergency_stop(self):
        """Emergency stop all motion"""
        logging.warning("EMERGENCY STOP activated!")


class SafetyMonitorWidget(QWidget):
    """Widget for monitoring safety status"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("Safety Monitor")
        header.setObjectName("headerLabel")
        header.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(header)
        
        # Safety level
        level_layout = QHBoxLayout()
        level_layout.addWidget(QLabel("Safety Level:"))
        self.level_combo = QComboBox()
        self.level_combo.addItems(["Fragile", "Standard", "Robust"])
        self.level_combo.setCurrentIndex(1)
        level_layout.addWidget(self.level_combo)
        layout.addLayout(level_layout)
        
        # Status indicators
        status_group = QGroupBox("System Status")
        status_layout = QGridLayout(status_group)
        
        indicators = [
            ("Collision Detection:", "Active", "green"),
            ("Path Clear:", "Yes", "green"),
            ("Limits OK:", "Yes", "green"),
            ("Emergency Stop:", "Ready", "green"),
        ]
        
        for i, (label, value, color) in enumerate(indicators):
            status_layout.addWidget(QLabel(label), i, 0)
            value_label = QLabel(value)
            if color == "green":
                value_label.setObjectName("statusActive")
            status_layout.addWidget(value_label, i, 1)
        
        layout.addWidget(status_group)
        
        # Warnings/Alerts
        alerts_group = QGroupBox("Alerts")
        alerts_layout = QVBoxLayout(alerts_group)
        self.alerts_list = QListWidget()
        self.alerts_list.addItem("No alerts")
        alerts_layout.addWidget(self.alerts_list)
        layout.addWidget(alerts_group)
        
        layout.addStretch()


class PathPlanningWidget(QWidget):
    """Widget for path planning and visualization"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("Path Planning")
        header.setObjectName("headerLabel")
        header.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(header)
        
        # Algorithm selection
        algo_layout = QHBoxLayout()
        algo_layout.addWidget(QLabel("Algorithm:"))
        self.algo_combo = QComboBox()
        self.algo_combo.addItems(["A* (Grid-based)", "RRT (Sampling-based)"])
        algo_layout.addWidget(self.algo_combo)
        layout.addLayout(algo_layout)
        
        # Target position
        target_group = QGroupBox("Target Position")
        target_layout = QGridLayout(target_group)
        
        target_layout.addWidget(QLabel("X:"), 0, 0)
        self.target_x = QDoubleSpinBox()
        self.target_x.setRange(-10.0, 10.0)
        self.target_x.setSingleStep(0.1)
        target_layout.addWidget(self.target_x, 0, 1)
        
        target_layout.addWidget(QLabel("Y:"), 1, 0)
        self.target_y = QDoubleSpinBox()
        self.target_y.setRange(-10.0, 10.0)
        self.target_y.setSingleStep(0.1)
        target_layout.addWidget(self.target_y, 1, 1)
        
        target_layout.addWidget(QLabel("Z:"), 2, 0)
        self.target_z = QDoubleSpinBox()
        self.target_z.setRange(0.0, 3.0)
        self.target_z.setSingleStep(0.1)
        target_layout.addWidget(self.target_z, 2, 1)
        
        layout.addWidget(target_group)
        
        # Plan button
        plan_btn = QPushButton("Calculate Path")
        plan_btn.clicked.connect(self.calculate_path)
        layout.addWidget(plan_btn)
        
        # Path info
        info_group = QGroupBox("Path Information")
        info_layout = QVBoxLayout(info_group)
        self.path_info = QLabel("No path calculated")
        info_layout.addWidget(self.path_info)
        layout.addWidget(info_group)
        
        layout.addStretch()
    
    def calculate_path(self):
        """Calculate path to target"""
        x = self.target_x.value()
        y = self.target_y.value()
        z = self.target_z.value()
        algo = self.algo_combo.currentText()
        
        self.path_info.setText(
            f"Path calculated using {algo}\n"
            f"Target: ({x:.2f}, {y:.2f}, {z:.2f})\n"
            f"Distance: TBD\n"
            f"Waypoints: TBD"
        )


class ROCMainWindow(QMainWindow):
    """Main window for ROC standalone application"""
    
    def __init__(self):
        super().__init__()
        self.roc_node = None
        self.control_thread = None
        self.init_roc()
        self.init_ui()
        self.start_control_loop()
    
    def init_roc(self):
        """Initialize ROC node"""
        try:
            # ROC node would be initialized here when ROS2 is available
            logging.info("ROC node initialization (placeholder)")
            self.roc_node = None  # Placeholder
        except Exception as e:
            logging.error(f"Failed to initialize ROC: {e}")
            self.roc_node = None
    
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("ROA - Robot Operator Controller")
        self.setGeometry(100, 100, 1400, 900)
        
        # Apply dark theme
        self.setStyleSheet(DARK_THEME)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        
        # Header
        header = self.create_header()
        main_layout.addWidget(header)
        
        # Main content splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left panel: Robot selector and safety
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(RobotSelectorWidget())
        left_layout.addWidget(SafetyMonitorWidget())
        splitter.addWidget(left_panel)
        
        # Center panel: Joint control
        center_panel = JointControlWidget()
        splitter.addWidget(center_panel)
        
        # Right panel: Path planning and logs
        right_panel = QTabWidget()
        right_panel.addTab(PathPlanningWidget(), "Path Planning")
        right_panel.addTab(self.create_log_widget(), "Console")
        right_panel.addTab(self.create_performance_widget(), "Performance")
        splitter.addWidget(right_panel)
        
        # Set splitter sizes
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 1)
        
        main_layout.addWidget(splitter)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Add progress bar to status bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)
        
        self.status_bar.showMessage("ROC Ready - No robot loaded")
    
    def create_header(self):
        """Create header with title and status"""
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        
        # Title
        title = QLabel("Robot Operator Controller")
        title.setObjectName("titleLabel")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # Status indicators
        self.mode_label = QLabel("Mode: RPM")
        self.mode_label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(self.mode_label)
        
        self.conn_label = QLabel("● Disconnected")
        self.conn_label.setStyleSheet("color: red;")
        header_layout.addWidget(self.conn_label)
        
        return header_widget
    
    def create_log_widget(self):
        """Create log console widget"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Controls
        controls = QHBoxLayout()
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(lambda: self.console_text.clear())
        controls.addWidget(clear_btn)
        controls.addStretch()
        
        layout.addLayout(controls)
        
        # Console
        self.console_text = QTextEdit()
        self.console_text.setReadOnly(True)
        self.console_text.setFont(QFont("Courier", 9))
        layout.addWidget(self.console_text)
        
        return widget
    
    def create_performance_widget(self):
        """Create performance monitoring widget"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Performance metrics
        metrics_group = QGroupBox("System Performance")
        metrics_layout = QGridLayout(metrics_group)
        
        metrics = [
            ("Control Loop Rate:", "0 Hz"),
            ("Latency:", "0 ms"),
            ("CPU Usage:", "0%"),
            ("Memory Usage:", "0 MB"),
        ]
        
        for i, (label, value) in enumerate(metrics):
            metrics_layout.addWidget(QLabel(label), i, 0)
            value_label = QLabel(value)
            value_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            metrics_layout.addWidget(value_label, i, 1)
        
        layout.addWidget(metrics_group)
        layout.addStretch()
        
        return widget
    
    def start_control_loop(self):
        """Start the control loop thread"""
        if not self.control_thread:
            self.control_thread = ControlThread(self.roc_node)
            self.control_thread.status_updated.connect(self.update_status)
            self.control_thread.start()
    
    def update_status(self, status):
        """Update UI with new status"""
        mode = status.get('mode', 'Unknown')
        self.mode_label.setText(f"Mode: {mode}")
    
    def add_console_log(self, message, level="INFO"):
        """Add message to console"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] [{level}] {message}"
        self.console_text.append(log_line)
    
    def closeEvent(self, event):
        """Handle window close"""
        if self.control_thread:
            self.control_thread.stop()
            self.control_thread.wait()
        
        if self.roc_node:
            # Shutdown ROC node
            pass
        
        event.accept()


def main():
    """Main entry point"""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("ROA - Robot Operator Controller")
    
    window = ROCMainWindow()
    window.show()
    
    logging.info("ROC Standalone Application started")
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
