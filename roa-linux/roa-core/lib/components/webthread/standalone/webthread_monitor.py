#!/usr/bin/env python3
"""
Webthread Standalone Monitoring Application
ROA - Robot Operations & Automation

A standalone monitoring dashboard for the Webthread component that can run
independently from UE5 to monitor system health, component status, and logs.
"""

import sys
import logging
import time
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton, QGroupBox, QGridLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QStatusBar,
    QSplitter, QTabWidget, QLineEdit, QPlainTextEdit, QFrame,
    QScrollArea, QComboBox, QSpinBox, QSlider
)
from PyQt6.QtCore import QTimer, Qt, QThread, pyqtSignal, QProcess, QRectF
from PyQt6.QtGui import QFont, QColor, QTextCursor, QPainter, QPen, QBrush, QPainterPath
from datetime import datetime
import json

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
    from webthread_core import WebthreadCore, ComponentHealth
    from Logging.logger import setup_roa_logger
    # Optional: ConnectionManager may not exist yet
    try:
        from StatusMonitor.connection_manager import ConnectionManager
    except ImportError:
        ConnectionManager = None
except ImportError as e:
    print(f"Warning: Could not import Webthread modules: {e}")
    print("Running in standalone mode with mock data")
    WebthreadCore = None
    ComponentHealth = None

# Add FTI python path and import protocol/path helpers
fti_py_path = os.path.join(os.path.dirname(__file__), '..', '..', 'files-type-importer', 'src', 'python')
if fti_py_path not in sys.path:
    sys.path.insert(0, fti_py_path)
try:
    from IPC.ipc_protocol import PROTOCOL_VERSION
    from Utils.path_handler import get_path_handler
except Exception:
    PROTOCOL_VERSION = "1.0.0"
    def get_path_handler(*args, **kwargs):
        class _Dummy:
            def to_windows_path(self, p):
                return None
        return _Dummy()

# Import HB Subsystem for GUI display
try:
    from hb_subsystem import (
        HBSubsystem, AlertLevel, HealthLevel, 
        ComponentState, CircuitBreakerState, FailureType
    )
    HB_AVAILABLE = True
except ImportError as e:
    print(f"Note: HB Subsystem not available for GUI: {e}")
    HB_AVAILABLE = False
    AlertLevel = None
    HealthLevel = None


class DraggableTitleBar(QWidget):
    """Custom draggable title bar widget"""
    
    def __init__(self, parent_window):
        super().__init__()
        self._parent_window = parent_window
        self._drag_pos = None
        self._is_maximized = False
    
    def mousePressEvent(self, event):
        """Handle mouse press for dragging"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging"""
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            # If maximized, restore before dragging
            if self._is_maximized:
                self._parent_window._toggle_maximize()
                self._is_maximized = False
            
            delta = event.globalPosition().toPoint() - self._drag_pos
            self._parent_window.move(self._parent_window.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release"""
        self._drag_pos = None
    
    def mouseDoubleClickEvent(self, event):
        """Handle double-click to maximize/restore"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._parent_window._toggle_maximize()
            self._is_maximized = not self._is_maximized


class CircularGauge(QWidget):
    """
    Custom circular gauge widget inspired by Dash DAQ gauges.
    Displays a value as an arc with customizable colors and labels.
    """
    
    def __init__(self, label: str = "", min_val: float = 0, max_val: float = 100, 
                 unit: str = "%", size: int = 120, parent=None):
        super().__init__(parent)
        self._label = label
        self._min_val = min_val
        self._max_val = max_val
        self._value = min_val
        self._unit = unit
        self._size = size
        self._color = QColor("#4CAF50")  # Green by default
        self._bg_color = QColor("#2d2d2d")
        self._text_color = QColor("#ffffff")
        
        self.setMinimumSize(size, size + 30)
        self.setMaximumSize(size, size + 30)
    
    def setValue(self, value: float):
        """Set the gauge value"""
        self._value = max(self._min_val, min(self._max_val, value))
        
        # Auto-color based on value percentage
        percent = (self._value - self._min_val) / (self._max_val - self._min_val)
        if percent >= 0.8:
            self._color = QColor("#4CAF50")  # Green
        elif percent >= 0.5:
            self._color = QColor("#FFC107")  # Yellow
        elif percent >= 0.3:
            self._color = QColor("#FF9800")  # Orange
        else:
            self._color = QColor("#F44336")  # Red
        
        self.update()
    
    def setColor(self, color: QColor):
        """Set gauge color manually"""
        self._color = color
        self.update()
    
    def setLabel(self, label: str):
        """Set gauge label"""
        self._label = label
        self.update()
    
    def paintEvent(self, event):
        """Draw the circular gauge"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Calculate dimensions
        margin = 10
        gauge_size = self._size - 2 * margin
        rect = QRectF(margin, margin, gauge_size, gauge_size)
        
        # Draw background arc
        painter.setPen(QPen(self._bg_color, 12, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, 225 * 16, -270 * 16)
        
        # Draw value arc
        percent = (self._value - self._min_val) / (self._max_val - self._min_val)
        sweep_angle = int(-270 * percent * 16)
        painter.setPen(QPen(self._color, 12, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, 225 * 16, sweep_angle)
        
        # Draw center value
        painter.setPen(self._text_color)
        value_font = QFont("Arial", int(self._size / 5), QFont.Weight.Bold)
        painter.setFont(value_font)
        value_text = f"{self._value:.0f}"
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, value_text)
        
        # Draw unit below value
        unit_font = QFont("Arial", int(self._size / 10))
        painter.setFont(unit_font)
        unit_rect = QRectF(margin, margin + gauge_size / 2 + 15, gauge_size, 20)
        painter.drawText(unit_rect, Qt.AlignmentFlag.AlignCenter, self._unit)
        
        # Draw label at bottom
        label_font = QFont("Arial", 9)
        painter.setFont(label_font)
        label_rect = QRectF(0, self._size, self._size, 25)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, self._label)


class StatusIndicator(QWidget):
    """
    Status indicator widget inspired by Dash DAQ indicators.
    Shows a colored dot with label for status display.
    """
    
    def __init__(self, label: str = "", parent=None):
        super().__init__(parent)
        self._label = label
        self._active = False
        self._color = QColor("#4CAF50")
        self._pulse = False
        
        self.setMinimumSize(80, 50)
        self.setMaximumHeight(50)
    
    def setActive(self, active: bool):
        """Set active state"""
        self._active = active
        self.update()
    
    def setColor(self, color: QColor):
        """Set indicator color"""
        self._color = color
        self.update()
    
    def setLabel(self, label: str):
        """Set label text"""
        self._label = label
        self.update()
    
    def paintEvent(self, event):
        """Draw the indicator"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw indicator circle
        circle_x = self.width() // 2 - 10
        circle_y = 5
        circle_size = 20
        
        if self._active:
            painter.setBrush(QBrush(self._color))
            painter.setPen(QPen(self._color.lighter(150), 2))
        else:
            painter.setBrush(QBrush(QColor("#555")))
            painter.setPen(QPen(QColor("#444"), 2))
        
        painter.drawEllipse(circle_x, circle_y, circle_size, circle_size)
        
        # Draw label
        painter.setPen(QColor("#ccc"))
        label_font = QFont("Arial", 9)
        painter.setFont(label_font)
        label_rect = QRectF(0, circle_y + circle_size + 5, self.width(), 20)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, self._label)


class LogFilterWidget(QWidget):
    """
    Enhanced log filter widget inspired by NiceGUI log viewer.
    Provides filtering by level, source, and text search.
    """
    
    filterChanged = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        
        # Level filter
        layout.addWidget(QLabel("Level:"))
        self.level_filter = QComboBox()
        self.level_filter.addItems(["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "SUCCESS"])
        self.level_filter.setStyleSheet("min-width: 80px;")
        self.level_filter.currentTextChanged.connect(self.filterChanged.emit)
        layout.addWidget(self.level_filter)
        
        # Source filter
        layout.addWidget(QLabel("Source:"))
        self.source_filter = QComboBox()
        self.source_filter.addItems(["ALL", "Bridge", "FTI", "Converter", "Orchestrator", "ROS", "System", "HB"])
        self.source_filter.setStyleSheet("min-width: 100px;")
        self.source_filter.currentTextChanged.connect(self.filterChanged.emit)
        layout.addWidget(self.source_filter)
        
        # Text search
        layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter messages...")
        self.search_input.setStyleSheet("min-width: 200px;")
        self.search_input.textChanged.connect(self.filterChanged.emit)
        layout.addWidget(self.search_input)
        
        # Clear button
        clear_btn = QPushButton("✕")
        clear_btn.setStyleSheet("max-width: 30px; padding: 5px;")
        clear_btn.clicked.connect(self._clear_filters)
        layout.addWidget(clear_btn)
        
        layout.addStretch()
    
    def _clear_filters(self):
        self.level_filter.setCurrentIndex(0)
        self.source_filter.setCurrentIndex(0)
        self.search_input.clear()
    
    def get_filters(self) -> dict:
        """Get current filter settings"""
        return {
            'level': self.level_filter.currentText(),
            'source': self.source_filter.currentText(),
            'search': self.search_input.text().lower()
        }


class MonitorThread(QThread):
    """Background thread for monitoring Webthread"""
    status_updated = pyqtSignal(dict)
    
    def __init__(self, webthread_core):
        super().__init__()
        self.webthread_core = webthread_core
        self.running = True
    
    def run(self):
        """Monitor loop"""
        while self.running:
            try:
                if self.webthread_core:
                    status = self.webthread_core.get_system_status()
                    self.status_updated.emit(status)
            except Exception as e:
                logging.error(f"Monitor thread error: {e}")
            
            self.msleep(3000)  # 3 second update rate (was 500ms - way too fast)
    
    def stop(self):
        """Stop the monitoring thread"""
        self.running = False


class WebthreadMonitorUI(QMainWindow):
    """Main window for Webthread monitoring application"""
    
    def __init__(self):
        super().__init__()
        self.webthread_core = None
        self.monitor_thread = None
        self.init_webthread()
        self.init_ui()
        self.start_monitoring()
    
    def init_webthread(self):
        """Initialize Webthread core"""
        try:
            self.webthread_core = WebthreadCore()
            self.webthread_core.start()
            logging.info("Webthread core initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize Webthread: {e}")
            self.webthread_core = None
    
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("ROA Webthread Monitor (WT + HB Subsystem)")
        self.setGeometry(50, 50, 1920, 1080)  # Much bigger window (Full HD size)
        
        # Enable frameless window with custom title bar for flexible sizing
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        
        # Track dragging for custom title bar
        self._drag_pos = None
        self._is_maximized = False
        
        # Apply dark theme
        self.setStyleSheet(DARK_THEME)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Custom Title Bar
        title_bar = self._create_custom_title_bar()
        main_layout.addWidget(title_bar)
        
        # Content wrapper with margins
        content_wrapper = QWidget()
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(5, 5, 5, 5)
        
        # Header
        header = self.create_header()
        content_layout.addWidget(header)
        
        # Splitter for main content - more flexible with styled handles
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(8)  # Wider handle for easier grabbing
        splitter.setChildrenCollapsible(False)  # Prevent accidental collapse
        splitter.setStyleSheet("""
            QSplitter::handle {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3a3a5e, stop:0.5 #5a5a8e, stop:1 #3a3a5e);
                border-radius: 3px;
            }
            QSplitter::handle:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4a4a6e, stop:0.5 #7a7aae, stop:1 #4a4a6e);
            }
            QSplitter::handle:pressed {
                background: #8a8abe;
            }
        """)
        
        # Top section: Health Status (Main + HB combined)
        health_status_widget = self.create_health_status_widget()
        splitter.addWidget(health_status_widget)
        
        # Bottom section: Tabs for logs and details (Overview moved to Health Status widget)
        tabs = QTabWidget()
        tabs.addTab(self.create_log_widget(), "📋 System Logs")
        tabs.addTab(self.create_stats_widget(), "📊 Statistics")
        tabs.addTab(self.create_connections_widget(), "🔌 Connections")
        tabs.addTab(self.create_fti_status_widget(), "🔄 FTI Status")
        tabs.addTab(self.create_messages_widget(), "🎮 UE5 Messages")
        tabs.addTab(self.create_terminal_widget(), "💻 Terminal")
        splitter.addWidget(tabs)
        
        # Set initial sizes (can be freely adjusted by user)
        splitter.setStretchFactor(0, 3)  # Health Status section
        splitter.setStretchFactor(1, 4)  # Tabs section - give more room
        splitter.setSizes([300, 400])  # Initial pixel sizes
        
        content_layout.addWidget(splitter)
        main_layout.addWidget(content_wrapper)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Webthread Monitor Ready")
        
        # Add resize grip for frameless window
        self._add_resize_grip()
    
    def _create_custom_title_bar(self):
        """Create custom draggable title bar with window controls"""
        # Use DraggableTitleBar class for proper mouse event handling
        title_bar = DraggableTitleBar(self)
        title_bar.setObjectName("titleBar")
        title_bar.setMouseTracking(True)
        title_bar.setFixedHeight(35)
        title_bar.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3a3a5e, stop:1 #2a2a4e);
                border-bottom: 1px solid #4a4a6a;
            }
        """)
        
        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(10, 0, 5, 0)
        layout.setSpacing(5)
        
        # App icon/logo
        logo_label = QLabel("🤖")
        logo_label.setStyleSheet("font-size: 16px; background: transparent; border: none;")
        layout.addWidget(logo_label)
        
        # Title text
        self._title_label = QLabel("ROA Webthread Monitor (WT + HB Subsystem)")
        self._title_label.setStyleSheet("""
            QLabel {
                color: #ddd;
                font-weight: bold;
                font-size: 12px;
                background: transparent;
                border: none;
            }
        """)
        layout.addWidget(self._title_label)
        
        layout.addStretch()
        
        # Window control buttons
        button_style = """
            QPushButton {{
                background-color: {bg};
                color: white;
                border: none;
                border-radius: 3px;
                font-size: 12px;
                font-weight: bold;
                min-width: 30px;
                max-width: 30px;
                min-height: 22px;
                max-height: 22px;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:pressed {{
                background-color: {pressed};
            }}
        """
        
        # Minimize button
        self._minimize_btn = QPushButton("─")
        self._minimize_btn.setStyleSheet(button_style.format(
            bg="transparent", hover="#4a4a6a", pressed="#3a3a5a"
        ))
        self._minimize_btn.setToolTip("Minimize")
        self._minimize_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._minimize_btn.clicked.connect(self.showMinimized)
        layout.addWidget(self._minimize_btn)
        
        # Maximize/Restore button
        self._maximize_btn = QPushButton("□")
        self._maximize_btn.setStyleSheet(button_style.format(
            bg="transparent", hover="#4a4a6a", pressed="#3a3a5a"
        ))
        self._maximize_btn.setToolTip("Maximize")
        self._maximize_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._maximize_btn.clicked.connect(self._toggle_maximize)
        layout.addWidget(self._maximize_btn)
        
        # Close button
        self._close_btn = QPushButton("×")
        self._close_btn.setStyleSheet(button_style.format(
            bg="transparent", hover="#c42b1c", pressed="#a02418"
        ))
        self._close_btn.setToolTip("Close")
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.clicked.connect(self.close)
        layout.addWidget(self._close_btn)
        
        # Store reference to title bar (DraggableTitleBar handles its own mouse events)
        self._title_bar = title_bar
        
        return title_bar
    
    def _toggle_maximize(self):
        """Toggle between maximized and normal window state"""
        if self._is_maximized:
            self.showNormal()
            self._maximize_btn.setText("□")
            self._maximize_btn.setToolTip("Maximize")
            self._is_maximized = False
        else:
            self.showMaximized()
            self._maximize_btn.setText("❐")
            self._maximize_btn.setToolTip("Restore")
            self._is_maximized = True
    
    def _add_resize_grip(self):
        """Add resize grip for frameless window"""
        from PyQt6.QtWidgets import QSizeGrip
        
        # Bottom-right resize grip
        self._size_grip = QSizeGrip(self)
        self._size_grip.setStyleSheet("""
            QSizeGrip {
                background: transparent;
                width: 15px;
                height: 15px;
            }
        """)
    
    def resizeEvent(self, event):
        """Handle resize to reposition size grip"""
        super().resizeEvent(event)
        if hasattr(self, '_size_grip'):
            self._size_grip.move(
                self.width() - self._size_grip.width(),
                self.height() - self._size_grip.height()
            )
    
    def mouseReleaseEvent(self, event):
        """Reset drag position on mouse release"""
        self._drag_pos = None
        super().mouseReleaseEvent(event)
    
    def create_header(self):
        """Create header with system info"""
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setSpacing(10)
        
        # Box 1: Title
        title_frame = QFrame()
        title_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a2a3e, stop:1 #1a1a2e);
                border: 1px solid #3a3a4e;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        title_layout = QVBoxLayout(title_frame)
        title = QLabel("Webthread System Monitor")
        title.setObjectName("titleLabel")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title_layout.addWidget(title)
        header_layout.addWidget(title_frame)
        
        # Box 2: Status (Running + Uptime)
        status_frame = QFrame()
        status_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a2a3e, stop:1 #1a1a2e);
                border: 1px solid #3a3a4e;
                border-radius: 8px;
                padding: 8px 15px;
            }
        """)
        status_layout = QVBoxLayout(status_frame)
        status_layout.setSpacing(3)
        self.status_label = QLabel("● Running")
        self.status_label.setObjectName("statusActive")
        status_layout.addWidget(self.status_label)
        self.uptime_label = QLabel("Uptime: 0s")
        status_layout.addWidget(self.uptime_label)
        header_layout.addWidget(status_frame)
        
        # Box 3: Bridge Server Controls + Network Ports
        bridge_frame = QFrame()
        bridge_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a2a3e, stop:1 #1a1a2e);
                border: 1px solid #3a3a4e;
                border-radius: 8px;
                padding: 8px 12px;
            }
        """)
        bridge_layout = QHBoxLayout(bridge_frame)
        bridge_layout.setSpacing(8)
        
        # Bridge Server Controls (left side) - stacked vertically
        controls_container = QWidget()
        controls_layout = QVBoxLayout(controls_container)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(4)
        
        self.bridge_start_btn = QPushButton("Start Bridge")
        self.bridge_start_btn.setStyleSheet("background-color: #2d5a2d; color: white; font-weight: bold; padding: 4px 8px; font-size: 10px;")
        self.bridge_start_btn.clicked.connect(self.start_bridge)
        controls_layout.addWidget(self.bridge_start_btn)
        
        self.bridge_stop_btn = QPushButton("Stop Bridge")
        self.bridge_stop_btn.setStyleSheet("background-color: #5a2d2d; color: white; font-weight: bold; padding: 4px 8px; font-size: 10px;")
        self.bridge_stop_btn.clicked.connect(self.stop_bridge)
        controls_layout.addWidget(self.bridge_stop_btn)
        
        bridge_layout.addWidget(controls_container)
        
        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #3a3a4e;")
        bridge_layout.addWidget(sep)
        
        # Network Ports Panel (right side) - All ports in grid
        ports_container = QWidget()
        ports_layout = QGridLayout(ports_container)
        ports_layout.setContentsMargins(0, 0, 0, 0)
        ports_layout.setSpacing(2)
        
        # All ports configuration
        self.all_port_labels = {}
        self.port_configs = {
            9090: {'name': 'rosbridge_server', 'row': 0, 'col': 0, 'type': 'bridge'},
            9876: {'name': 'command_server', 'row': 0, 'col': 1, 'type': 'bridge'},
            9877: {'name': 'HB:FTI', 'row': 1, 'col': 0, 'type': 'hb'},
            9878: {'name': 'HB:ROC', 'row': 1, 'col': 1, 'type': 'hb'},
            9879: {'name': 'HB:DIMC', 'row': 1, 'col': 2, 'type': 'hb'},
            9880: {'name': 'HB:COMC', 'row': 2, 'col': 0, 'type': 'hb'},
            9881: {'name': 'HB:ROS2', 'row': 2, 'col': 1, 'type': 'hb'},
            9882: {'name': 'HB:UE5', 'row': 2, 'col': 2, 'type': 'hb'},
        }
        
        # Create interactive labels for ALL ports
        for port, config in self.port_configs.items():
            label = QPushButton(f"● {port}")
            label.setFlat(True)
            label.setStyleSheet("""
                QPushButton {
                    color: #888; 
                    font-weight: bold; 
                    font-size: 10px; 
                    border: none; 
                    text-align: left;
                    padding: 2px 4px;
                }
                QPushButton:hover {
                    color: #00aaff;
                    background-color: rgba(0, 170, 255, 0.1);
                    border-radius: 3px;
                }
                QPushButton:pressed {
                    color: #00ff00;
                }
            """)
            label.setToolTip(f"{config['name']} - Click to toggle")
            label.setCursor(Qt.CursorShape.PointingHandCursor)
            label.clicked.connect(lambda checked, p=port: self._toggle_port(p))
            ports_layout.addWidget(label, config['row'], config['col'])
            self.all_port_labels[port] = label
        
        # Keep backward compatibility
        self.port_9090_label = self.all_port_labels[9090]
        self.port_9876_label = self.all_port_labels[9876]
        self.hb_port_labels = {p: l for p, l in self.all_port_labels.items() if self.port_configs[p]['type'] == 'hb'}
        
        bridge_layout.addWidget(ports_container)
        
        header_layout.addWidget(bridge_frame)
        
        # Box 4: Copy Report
        copy_frame = QFrame()
        copy_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a2a3e, stop:1 #1a1a2e);
                border: 1px solid #3a3a4e;
                border-radius: 8px;
                padding: 8px 12px;
            }
        """)
        copy_layout = QHBoxLayout(copy_frame)
        
        # Copy All Report button
        copy_all_btn = QPushButton("Copy Report")
        copy_all_btn.setStyleSheet("background-color: #2a4a6a; color: white; font-weight: bold; padding: 5px 15px;")
        copy_all_btn.setToolTip("Copy all logs, messages, and terminal output to clipboard")
        copy_all_btn.clicked.connect(self.copy_all_logs)
        copy_layout.addWidget(copy_all_btn)
        
        # Test Data Flow button
        test_dataflow_btn = QPushButton("Test Data Flow")
        test_dataflow_btn.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 5px 15px;")
        test_dataflow_btn.setToolTip("Test all component data types through ports 9090 & 9876")
        test_dataflow_btn.clicked.connect(self.test_data_flow)
        copy_layout.addWidget(test_dataflow_btn)
        
        header_layout.addWidget(copy_frame)
        
        return header_widget
    
    def create_health_status_widget(self):
        """Create unified Health Status section with tabbed Main Status + HB Status panels"""
        
        # INITIALIZE STATUS TRACKING FIRST (before any panels that use them)
        # This ensures overview panel can access these dictionaries
        wsl_components = ['FTI', 'DIMC', 'ROC', 'COMC']
        plugin_components = ['ROAModule', 'ROANetworkServer']
        
        self.wsl_component_status = {comp: {
            'status': 'WAITING',
            'last_hb': 0,
            'missed_hb_count': 0,
            'ever_connected': False,
            'response_time': 0,
            'errors': 0
        } for comp in wsl_components}
        
        self.plugin_component_status = {comp: {
            'status': 'WAITING',
            'last_hb': 0,
            'missed_hb_count': 0,
            'ever_connected': False,
            'response_time': 0,
            'errors': 0
        } for comp in plugin_components}
        
        # Initialize hb_stat_labels dictionary (will be populated by HB detail panel)
        self.hb_stat_labels = {}
        
        # Main container
        container = QGroupBox("Health Status")
        container.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                border: 2px solid #4a4a6a;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px;
                color: #8a8aca;
            }
        """)
        
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        # Use tabs like the bottom section
        health_tabs = QTabWidget()
        health_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #3a3a5a;
                border-radius: 5px;
            }
            QTabBar::tab {
                padding: 6px 15px;
                margin-right: 3px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            QTabBar::tab:selected {
                background-color: #3a3a5a;
                font-weight: bold;
            }
        """)
        
        # Tab 0: System Overview (NEW - Visual gauges inspired by Dash DAQ)
        overview_panel = self._create_system_overview_panel()
        health_tabs.addTab(overview_panel, "📈 Overview")
        
        # Tab 1: Main Status (Quick Overview)
        main_status_panel = self._create_main_status_panel()
        health_tabs.addTab(main_status_panel, "📊 Main Status")
        
        # Tab 2: HB Status (Detailed)
        hb_status_panel = self._create_hb_detail_panel()
        health_tabs.addTab(hb_status_panel, "💓 HB Status")
        
        # Tab 3: FTI Import Panel (NEW - Robot Import Control)
        fti_import_panel = self._create_fti_import_panel()
        health_tabs.addTab(fti_import_panel, "🤖 FTI Import")
        
        main_layout.addWidget(health_tabs)
        
        # Start heartbeat checker timer
        self.heartbeat_timer = QTimer()
        self.heartbeat_timer.timeout.connect(self.check_component_heartbeats)
        self.heartbeat_timer.start(2000)  # Check every 2 seconds
        
        # Start HB status update timer
        self.hb_status_timer = QTimer()
        self.hb_status_timer.timeout.connect(self.update_hb_status)
        self.hb_status_timer.start(2000)
        
        # Initial update
        QTimer.singleShot(500, self.update_hb_status)
        
        return container
    
    def _create_main_status_panel(self):
        """Create Main Status panel with compact component overview"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(2)
        layout.setContentsMargins(3, 3, 3, 3)
        
        # WSL Components (4 main: FTI, DIMC, ROC, COMC)
        wsl_label = QLabel("WSL Components")
        wsl_label.setStyleSheet("color: #5a9aca; font-weight: bold; font-size: 10px;")
        layout.addWidget(wsl_label)
        
        self.component_table = QTableWidget()
        self.component_table.setColumnCount(5)
        self.component_table.setHorizontalHeaderLabels(["Component", "Status", "Resp (ms)", "Errors", "Last HB"])
        self.component_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.component_table.horizontalHeader().setDefaultSectionSize(18)
        self.component_table.setMinimumHeight(60)  # Allow shrinking
        self.component_table.verticalHeader().setDefaultSectionSize(20)
        self.component_table.verticalHeader().setVisible(False)
        self.component_table.setStyleSheet("QHeaderView::section { padding: 2px; height: 18px; }")
        
        # 4 main WSL components
        wsl_components = ['FTI', 'DIMC', 'ROC', 'COMC']
        self.component_table.setRowCount(len(wsl_components))
        for i, comp in enumerate(wsl_components):
            self.component_table.setItem(i, 0, QTableWidgetItem(comp))
            status_item = QTableWidgetItem("WAITING")  # Static initial status
            status_item.setForeground(QColor("#888"))
            self.component_table.setItem(i, 1, status_item)
            self.component_table.setItem(i, 2, QTableWidgetItem("--"))
            self.component_table.setItem(i, 3, QTableWidgetItem("0"))
            self.component_table.setItem(i, 4, QTableWidgetItem("--"))
        
        layout.addWidget(self.component_table)
        
        # Plugin Components (4 main: ROAModule, NetworkClient, XACROHandler, URDFImporter)
        plugin_label = QLabel("Plugin Components (UE5)")
        plugin_label.setStyleSheet("color: #ca9a5a; font-weight: bold; font-size: 10px;")
        layout.addWidget(plugin_label)
        
        self.plugin_component_table = QTableWidget()
        self.plugin_component_table.setColumnCount(5)
        self.plugin_component_table.setHorizontalHeaderLabels(["Component", "Status", "Resp (ms)", "Errors", "Last HB"])
        self.plugin_component_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.plugin_component_table.horizontalHeader().setDefaultSectionSize(18)
        self.plugin_component_table.setMinimumHeight(60)  # Allow shrinking
        self.plugin_component_table.verticalHeader().setDefaultSectionSize(20)
        self.plugin_component_table.verticalHeader().setVisible(False)
        self.plugin_component_table.setStyleSheet("QHeaderView::section { padding: 2px; height: 18px; }")
        
        # 4 main Plugin components
        plugin_components = ['ROAModule', 'NetworkClient', 'XACROHandler', 'URDFImporter']
        self.plugin_component_table.setRowCount(len(plugin_components))
        for i, comp in enumerate(plugin_components):
            self.plugin_component_table.setItem(i, 0, QTableWidgetItem(comp))
            status_item = QTableWidgetItem("WAITING")  # Static initial status
            status_item.setForeground(QColor("#666"))
            self.plugin_component_table.setItem(i, 1, status_item)
            self.plugin_component_table.setItem(i, 2, QTableWidgetItem("--"))
            self.plugin_component_table.setItem(i, 3, QTableWidgetItem("0"))
            self.plugin_component_table.setItem(i, 4, QTableWidgetItem("--"))
        
        layout.addWidget(self.plugin_component_table)
        
        # Status tracking is initialized in create_health_status_widget() before this panel
        
        # Push everything to the top
        layout.addStretch()
        
        return panel
    
    def _create_system_overview_panel(self):
        """
        Create System Overview panel with visual gauges and status indicators.
        Inspired by Dash DAQ dashboard widgets for mission control interfaces.
        """
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Row 1: Main gauges (Health, Active Ports, HB Rate, Uptime)
        gauges_row = QHBoxLayout()
        gauges_row.setSpacing(20)
        
        # System Health Gauge
        self.health_gauge = CircularGauge("System Health", 0, 100, "%", 120)
        self.health_gauge.setValue(0)
        gauges_row.addWidget(self.health_gauge)
        
        # Active Ports Gauge
        self.ports_gauge = CircularGauge("Active Ports", 0, 8, "ports", 120)
        self.ports_gauge.setValue(0)
        gauges_row.addWidget(self.ports_gauge)
        
        # HB Rate Gauge  
        self.hb_rate_gauge = CircularGauge("HB Rate", 0, 10, "Hz", 120)
        self.hb_rate_gauge.setValue(0)
        gauges_row.addWidget(self.hb_rate_gauge)
        
        # Memory Usage Gauge
        self.memory_gauge = CircularGauge("Memory", 0, 100, "%", 120)
        self.memory_gauge.setValue(0)
        gauges_row.addWidget(self.memory_gauge)
        
        gauges_row.addStretch()
        layout.addLayout(gauges_row)
        
        # Row 2: Status indicators for subsystems
        indicators_group = QGroupBox("Subsystem Status")
        indicators_group.setStyleSheet("""
            QGroupBox { 
                font-weight: bold; font-size: 11px; 
                border: 1px solid #3a3a5a; border-radius: 5px; 
                margin-top: 8px; padding-top: 10px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        """)
        indicators_layout = QHBoxLayout(indicators_group)
        indicators_layout.setSpacing(15)
        
        # Create status indicators for each subsystem
        self.status_indicators = {}
        subsystems = ['Bridge', 'FTI', 'DIMC', 'ROC', 'COMC', 'ROS2', 'UE5']
        
        for name in subsystems:
            indicator = StatusIndicator(name)
            indicator.setActive(False)
            indicator.setColor(QColor("#888"))
            self.status_indicators[name] = indicator
            indicators_layout.addWidget(indicator)
        
        indicators_layout.addStretch()
        layout.addWidget(indicators_group)
        
        # Row 3: Quick stats cards
        stats_row = QHBoxLayout()
        stats_row.setSpacing(15)
        
        # Create stat cards
        self.overview_stat_cards = {}
        stat_defs = [
            ("total_hb", "Total HBs", "0", "#4CAF50"),
            ("errors", "Errors", "0", "#F44336"),
            ("warnings", "Warnings", "0", "#FF9800"),
            ("connections", "Connections", "0", "#2196F3"),
            ("uptime", "Uptime", "0s", "#9C27B0"),
        ]
        
        for key, label, default, color in stat_defs:
            card = self._create_stat_card(label, default, color)
            self.overview_stat_cards[key] = card['value_label']
            stats_row.addWidget(card['widget'])
        
        stats_row.addStretch()
        layout.addLayout(stats_row)
        
        layout.addStretch()
        
        # Timer to update overview
        self.overview_timer = QTimer()
        self.overview_timer.timeout.connect(self._update_system_overview)
        self.overview_timer.start(2000)
        
        # Initial update
        QTimer.singleShot(1000, self._update_system_overview)
        
        return panel
    
    def _create_stat_card(self, label: str, value: str, color: str) -> dict:
        """Create a stat card widget"""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a2a3e, stop:1 #1a1a2e);
                border: 1px solid #3a3a5a;
                border-left: 4px solid {color};
                border-radius: 5px;
                padding: 8px;
            }}
        """)
        card.setMinimumWidth(100)
        card.setMaximumWidth(150)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 5, 10, 5)
        card_layout.setSpacing(3)
        
        label_widget = QLabel(label)
        label_widget.setStyleSheet("font-size: 10px; color: #888;")
        card_layout.addWidget(label_widget)
        
        value_widget = QLabel(value)
        value_widget.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {color};")
        card_layout.addWidget(value_widget)
        
        return {'widget': card, 'value_label': value_widget}
    
    def _update_system_overview(self):
        """Update the system overview panel with current data"""
        import subprocess
        
        try:
            # Calculate system health from component status
            wsl_healthy = sum(1 for c in self.wsl_component_status.values() if c['status'] == 'HEALTHY')
            plugin_healthy = sum(1 for c in self.plugin_component_status.values() if c['status'] == 'HEALTHY')
            total_components = len(self.wsl_component_status) + len(self.plugin_component_status)
            health_percent = (wsl_healthy + plugin_healthy) / total_components * 100 if total_components > 0 else 0
            self.health_gauge.setValue(health_percent)
            
            # Count active ports (check both TCP and UDP)
            active_ports = 0
            for port in self.port_configs.keys():
                port_type = self.port_configs[port].get('type', 'bridge')
                
                # Check TCP for bridge ports, UDP for HB ports
                if port_type == 'hb':
                    result = subprocess.run(['ss', '-uln'], capture_output=True, text=True, timeout=2)
                else:
                    result = subprocess.run(['ss', '-tln'], capture_output=True, text=True, timeout=2)
                
                if f":{port}" in result.stdout or f" {port} " in result.stdout:
                    active_ports += 1
            
            self.ports_gauge.setValue(active_ports)
            
            # HB rate from stats
            if hasattr(self, 'hb_stat_labels') and 'hb_rate' in self.hb_stat_labels:
                rate_text = self.hb_stat_labels['hb_rate'].text()
                try:
                    rate = float(rate_text.replace('--', '0'))
                    self.hb_rate_gauge.setValue(rate)
                except ValueError:
                    pass
            
            # Memory usage (from /proc/meminfo or psutil if available)
            try:
                with open('/proc/meminfo', 'r') as f:
                    meminfo = f.read()
                total = int([l for l in meminfo.split('\n') if 'MemTotal' in l][0].split()[1])
                avail = int([l for l in meminfo.split('\n') if 'MemAvailable' in l][0].split()[1])
                mem_percent = (1 - avail / total) * 100
                self.memory_gauge.setValue(mem_percent)
            except Exception:
                pass
            
            # Update status indicators
            for name, indicator in self.status_indicators.items():
                if name in self.wsl_component_status:
                    status = self.wsl_component_status[name]['status']
                elif name in self.plugin_component_status:
                    status = self.plugin_component_status[name]['status']
                elif name == 'Bridge':
                    # Check if bridge ports are active
                    status = 'HEALTHY' if active_ports >= 2 else 'WAITING'
                elif name == 'ROS2':
                    status = 'HEALTHY' if active_ports >= 1 else 'WAITING'
                elif name == 'UE5':
                    # Check plugin status  
                    status = self.plugin_component_status.get('ROAModule', {}).get('status', 'WAITING')
                else:
                    status = 'WAITING'
                
                is_active = status in ['HEALTHY', 'OK']
                indicator.setActive(is_active)
                
                if status == 'HEALTHY':
                    indicator.setColor(QColor("#4CAF50"))
                elif status == 'DEGRADED':
                    indicator.setColor(QColor("#FF9800"))
                elif status == 'MALFUNCTION':
                    indicator.setColor(QColor("#F44336"))
                else:
                    indicator.setColor(QColor("#888"))
            
            # Update stat cards
            if hasattr(self, 'hb_stat_labels'):
                total_hb = self.hb_stat_labels.get('total_hb')
                if total_hb:
                    self.overview_stat_cards['total_hb'].setText(total_hb.text())
            
            # Error/warning counts
            error_count = sum(c['errors'] for c in self.wsl_component_status.values())
            self.overview_stat_cards['errors'].setText(str(error_count))
            
            self.overview_stat_cards['connections'].setText(str(active_ports))
            
            # Uptime from stat labels
            if hasattr(self, 'uptime_label'):
                uptime_text = self.uptime_label.text().replace('Uptime: ', '')
                self.overview_stat_cards['uptime'].setText(uptime_text)
                
        except Exception as e:
            # Silent fail for overview updates
            pass
    
    def _create_hb_detail_panel(self):
        """Create HB Status panel with detailed heartbeat info"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(2)
        layout.setContentsMargins(3, 3, 3, 3)
        
        # HB Status indicator + Refresh button
        header_row = QHBoxLayout()
        self.hb_enabled_label = QLabel("● HB: Checking...")
        self.hb_enabled_label.setStyleSheet("font-weight: bold;")
        header_row.addWidget(self.hb_enabled_label)
        header_row.addStretch()
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setStyleSheet("padding: 2px 6px; font-size: 9px;")
        refresh_btn.clicked.connect(self.update_hb_status)
        header_row.addWidget(refresh_btn)
        layout.addLayout(header_row)
        
        # Two columns: Circuit Breakers + Alerts | Recovery + Stats
        columns = QHBoxLayout()
        
        # Left column: Circuit Breakers and Alert Levels
        left_col = QVBoxLayout()
        
        # Circuit Breakers (compact)
        cb_label = QLabel("Circuit Breakers")
        cb_label.setStyleSheet("color: #9a5aca; font-size: 10px; font-weight: bold;")
        left_col.addWidget(cb_label)
        
        self.cb_table = QTableWidget()
        self.cb_table.setColumnCount(3)
        self.cb_table.setHorizontalHeaderLabels(["Comp", "State", "Fails"])
        self.cb_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.cb_table.setMinimumHeight(50)  # Allow shrinking
        self.cb_table.verticalHeader().setDefaultSectionSize(18)
        self.cb_table.verticalHeader().setVisible(False)
        self.cb_table.setStyleSheet("QHeaderView::section { padding: 2px; height: 18px; }")
        
        components = ['FTI', 'DIMC', 'ROC', 'COMC']
        self.cb_table.setRowCount(len(components))
        for i, comp in enumerate(components):
            self.cb_table.setItem(i, 0, QTableWidgetItem(comp))
            state_item = QTableWidgetItem("CLOSED")
            state_item.setForeground(QColor("#00ff00"))
            self.cb_table.setItem(i, 1, state_item)
            self.cb_table.setItem(i, 2, QTableWidgetItem("0"))
        
        left_col.addWidget(self.cb_table)
        
        # Alert Levels (compact)
        alert_label = QLabel("Alert Levels")
        alert_label.setStyleSheet("color: #ca9a5a; font-size: 10px; font-weight: bold;")
        left_col.addWidget(alert_label)
        
        self.alert_table = QTableWidget()
        self.alert_table.setColumnCount(3)
        self.alert_table.setHorizontalHeaderLabels(["Comp", "Alert", "Health"])
        self.alert_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.alert_table.setMinimumHeight(50)  # Allow shrinking
        self.alert_table.verticalHeader().setDefaultSectionSize(18)
        self.alert_table.verticalHeader().setVisible(False)
        self.alert_table.setStyleSheet("QHeaderView::section { padding: 2px; height: 18px; }")
        
        self.alert_table.setRowCount(len(components))
        for i, comp in enumerate(components):
            self.alert_table.setItem(i, 0, QTableWidgetItem(comp))
            alert_item = QTableWidgetItem("GREEN")
            alert_item.setForeground(QColor("#00ff00"))
            self.alert_table.setItem(i, 1, alert_item)
            health_item = QTableWidgetItem("OK")
            health_item.setForeground(QColor("#00ff00"))
            self.alert_table.setItem(i, 2, health_item)
        
        left_col.addWidget(self.alert_table)
        columns.addLayout(left_col)
        
        # Right column: Recovery History + Receiver Stats
        right_col = QVBoxLayout()
        
        # Recovery History
        recovery_label = QLabel("Recovery History")
        recovery_label.setStyleSheet("color: #5a9aca; font-size: 10px; font-weight: bold;")
        right_col.addWidget(recovery_label)
        
        self.recovery_text = QTextEdit()
        self.recovery_text.setReadOnly(True)
        self.recovery_text.setFont(QFont("Courier", 9))
        self.recovery_text.setMinimumHeight(40)  # Allow shrinking
        self.recovery_text.setPlaceholderText("No recovery attempts yet...")
        right_col.addWidget(self.recovery_text)
        
        # Receiver Statistics
        stats_label = QLabel("Receiver Statistics")
        stats_label.setStyleSheet("color: #5aca9a; font-size: 10px; font-weight: bold;")
        right_col.addWidget(stats_label)
        
        stats_grid = QGridLayout()
        stats_grid.setSpacing(2)
        # Note: self.hb_stat_labels is initialized in create_health_status_widget()
        hb_stats = [
            ("HBs Recv:", "total_hb"), ("HBs/sec:", "hb_rate"),
            ("Timeouts:", "timeouts"), ("Gaps:", "seq_gaps"),
            ("Uptime:", "hb_uptime"),
        ]
        for i, (label, key) in enumerate(hb_stats):
            row, col = i // 2, (i % 2) * 2
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 10px;")
            stats_grid.addWidget(lbl, row, col)
            value_label = QLabel("--")
            value_label.setStyleSheet("font-weight: bold; font-size: 10px;")
            stats_grid.addWidget(value_label, row, col + 1)
            self.hb_stat_labels[key] = value_label
        
        right_col.addLayout(stats_grid)
        right_col.addStretch()
        columns.addLayout(right_col)
        
        layout.addLayout(columns)
        
        # Push everything to the top
        layout.addStretch()
        
        return panel
    
    def _create_fti_import_panel(self):
        """Create FTI Import Panel with file browser, conversion controls, and progress"""
        from PyQt6.QtWidgets import (
            QFileDialog, QProgressBar, QComboBox, QCheckBox, QSizePolicy
        )
        
        panel = QWidget()
        main_layout = QVBoxLayout(panel)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create a vertical splitter for controls vs log
        fti_splitter = QSplitter(Qt.Orientation.Vertical)
        fti_splitter.setHandleWidth(6)
        fti_splitter.setChildrenCollapsible(False)
        fti_splitter.setStyleSheet("""
            QSplitter::handle {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3a3a5e, stop:0.5 #5a5a8e, stop:1 #3a3a5e);
                border-radius: 2px;
                margin: 2px 0;
            }
            QSplitter::handle:hover {
                background: #6a6a9e;
            }
        """)
        
        # ===== TOP SECTION: Controls =====
        controls_widget = QWidget()
        controls_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(controls_widget)
        layout.setSpacing(5)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # ═══════════════════════════════════════════════════════════════════
        # Row 1: File Selection
        # ═══════════════════════════════════════════════════════════════════
        file_section = QGroupBox("📁 File Selection")
        file_section.setStyleSheet("""
            QGroupBox { 
                font-weight: bold; font-size: 11px; 
                border: 1px solid #4a4a6a; border-radius: 5px; 
                margin-top: 8px; padding-top: 10px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        """)
        file_layout = QHBoxLayout(file_section)
        file_layout.setSpacing(8)
        
        # File path entry
        self.fti_file_path = QLineEdit()
        self.fti_file_path.setPlaceholderText("Enter path or use Browse/Paste - supports Windows paths like D:\\ROA\\robots\\...")
        self.fti_file_path.setMinimumWidth(400)
        file_layout.addWidget(self.fti_file_path)
        
        # Browse button (uses Windows file picker via PowerShell)
        browse_btn = QPushButton("📁 Browse")
        browse_btn.setStyleSheet("padding: 5px 12px; background-color: #2d5a2d;")
        browse_btn.setToolTip("Open Windows file picker (shows C:, D: drives)")
        browse_btn.clicked.connect(self._browse_robot_file)
        file_layout.addWidget(browse_btn)
        
        # Paste from clipboard button
        paste_btn = QPushButton("📋 Paste")
        paste_btn.setStyleSheet("padding: 5px 12px; background-color: #3a5a7a;")
        paste_btn.setToolTip("Paste path from clipboard (auto-converts Windows paths)")
        paste_btn.clicked.connect(self._paste_path_from_clipboard)
        file_layout.addWidget(paste_btn)
        
        # Open Explorer button
        explorer_btn = QPushButton("🗂️")
        explorer_btn.setStyleSheet("padding: 5px 10px;")
        explorer_btn.setToolTip("Open Windows Explorer at D:\\ROA")
        explorer_btn.clicked.connect(self._open_windows_explorer)
        file_layout.addWidget(explorer_btn)
        
        # Clear button
        clear_btn = QPushButton("✕")
        clear_btn.setStyleSheet("padding: 5px 10px; color: #ff6666;")
        clear_btn.clicked.connect(lambda: self.fti_file_path.clear())
        file_layout.addWidget(clear_btn)
        
        layout.addWidget(file_section)
        
        # ═══════════════════════════════════════════════════════════════════
        # Row 2: Format Detection + Import Options (side by side)
        # ═══════════════════════════════════════════════════════════════════
        options_row = QHBoxLayout()
        
        # Left: Format Detection Info
        format_section = QGroupBox("🔍 Detected Format")
        format_section.setStyleSheet("""
            QGroupBox { font-weight: bold; font-size: 10px; border: 1px solid #3a3a5a; border-radius: 5px; margin-top: 8px; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        """)
        format_layout = QGridLayout(format_section)
        format_layout.setSpacing(3)
        
        self.fti_format_labels = {}
        format_info = [
            ("Format:", "detected_format"),
            ("Robot Name:", "robot_name"),
            ("Links:", "link_count"),
            ("Joints:", "joint_count"),
            ("Meshes:", "mesh_count"),
        ]
        for i, (label, key) in enumerate(format_info):
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 10px;")
            format_layout.addWidget(lbl, i, 0)
            value_lbl = QLabel("--")
            value_lbl.setStyleSheet("font-weight: bold; font-size: 10px; color: #aaa;")
            format_layout.addWidget(value_lbl, i, 1)
            self.fti_format_labels[key] = value_lbl
        
        options_row.addWidget(format_section)
        
        # Right: Import Options
        import_options_section = QGroupBox("⚙️ Import Options")
        import_options_section.setStyleSheet("""
            QGroupBox { font-weight: bold; font-size: 10px; border: 1px solid #3a3a5a; border-radius: 5px; margin-top: 8px; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        """)
        import_opts_layout = QGridLayout(import_options_section)
        import_opts_layout.setSpacing(3)
        
        # Output format selection
        import_opts_layout.addWidget(QLabel("Output:"), 0, 0)
        self.fti_output_format = QComboBox()
        self.fti_output_format.addItems(["USD (OpenUSD)", "USDA (ASCII)", "USDZ (Package)"])
        self.fti_output_format.setStyleSheet("font-size: 10px;")
        import_opts_layout.addWidget(self.fti_output_format, 0, 1)
        
        # Mesh handling
        import_opts_layout.addWidget(QLabel("Meshes:"), 1, 0)
        self.fti_mesh_handling = QComboBox()
        self.fti_mesh_handling.addItems(["Embed in USD", "Reference External", "Convert to FBX"])
        self.fti_mesh_handling.setStyleSheet("font-size: 10px;")
        import_opts_layout.addWidget(self.fti_mesh_handling, 1, 1)
        
        # Auto-assemble checkbox
        self.fti_auto_assemble = QCheckBox("Auto-assemble in UE5")
        self.fti_auto_assemble.setChecked(True)
        self.fti_auto_assemble.setStyleSheet("font-size: 10px;")
        self.fti_auto_assemble.setToolTip("Automatically reconstruct robot hierarchy after import")
        import_opts_layout.addWidget(self.fti_auto_assemble, 2, 0, 1, 2)
        
        # Generate Blueprint checkbox
        self.fti_generate_bp = QCheckBox("Generate Blueprint")
        self.fti_generate_bp.setChecked(True)
        self.fti_generate_bp.setStyleSheet("font-size: 10px;")
        self.fti_generate_bp.setToolTip("Generate UE5 Blueprint with physics and ROS2 interface")
        import_opts_layout.addWidget(self.fti_generate_bp, 3, 0, 1, 2)
        
        options_row.addWidget(import_options_section)
        layout.addLayout(options_row)
        
        # ═══════════════════════════════════════════════════════════════════
        # Row 3: Convert Buttons (IPC Service is auto-managed in background)
        # ═══════════════════════════════════════════════════════════════════
        action_row = QHBoxLayout()
        
        # Convert Button (big, prominent)
        convert_btn_container = QWidget()
        convert_btn_layout = QHBoxLayout(convert_btn_container)
        convert_btn_layout.setContentsMargins(10, 0, 10, 0)
        convert_btn_layout.setSpacing(10)
        
        # Main Convert button - converts URDF/XACRO to USD
        self.fti_convert_btn = QPushButton("🔄 Convert to USD")
        self.fti_convert_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #27ae60, stop:1 #1e8449);
                color: white;
                font-weight: bold;
                font-size: 13px;
                padding: 10px 20px;
                border-radius: 8px;
                border: 2px solid #1e8449;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2ecc71, stop:1 #27ae60);
            }
            QPushButton:disabled {
                background: #555;
                color: #888;
                border-color: #444;
            }
        """)
        self.fti_convert_btn.setToolTip("Convert URDF/XACRO/SDF to USD format")
        self.fti_convert_btn.clicked.connect(self._start_fti_conversion)
        convert_btn_layout.addWidget(self.fti_convert_btn)
        
        # Prepare for UE5 button - adds Python assembly sequence to USD
        self.fti_prepare_ue5_btn = QPushButton("🎮 Prepare for UE5")
        self.fti_prepare_ue5_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3498db, stop:1 #2980b9);
                color: white;
                font-weight: bold;
                font-size: 13px;
                padding: 10px 20px;
                border-radius: 8px;
                border: 2px solid #2980b9;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5dade2, stop:1 #3498db);
            }
            QPushButton:disabled {
                background: #555;
                color: #888;
                border-color: #444;
            }
        """)
        self.fti_prepare_ue5_btn.setToolTip("Add hierarchy assembly script to USD file for UE5 import (for existing USD files)")
        self.fti_prepare_ue5_btn.clicked.connect(self._prepare_usd_for_ue5)
        convert_btn_layout.addWidget(self.fti_prepare_ue5_btn)
        
        action_row.addWidget(convert_btn_container)
        layout.addLayout(action_row)
        
        # ═══════════════════════════════════════════════════════════════════
        # Row 4: Conversion Progress
        # ═══════════════════════════════════════════════════════════════════
        progress_section = QGroupBox("📊 Conversion Progress")
        progress_section.setStyleSheet("""
            QGroupBox { font-weight: bold; font-size: 10px; border: 1px solid #3a3a5a; border-radius: 5px; margin-top: 8px; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        """)
        progress_layout = QVBoxLayout(progress_section)
        
        # Progress bar
        self.fti_progress_bar = QProgressBar()
        self.fti_progress_bar.setMinimum(0)
        self.fti_progress_bar.setMaximum(100)
        self.fti_progress_bar.setValue(0)
        self.fti_progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #3a3a5a;
                border-radius: 5px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3498db, stop:1 #2980b9);
                border-radius: 4px;
            }
        """)
        progress_layout.addWidget(self.fti_progress_bar)
        
        # Progress status label
        self.fti_progress_status = QLabel("Ready - Select a file to begin")
        self.fti_progress_status.setStyleSheet("font-size: 10px; color: #888;")
        progress_layout.addWidget(self.fti_progress_status)
        
        # Pipeline steps indicator
        pipeline_row = QHBoxLayout()
        self.fti_pipeline_steps = {}
        pipeline_steps = [
            ("Parse", "parse"),
            ("Process XACRO", "xacro"),
            ("Build Hierarchy", "hierarchy"),
            ("Convert Meshes", "meshes"),
            ("Generate USD", "usd"),
            ("IPC Transfer", "ipc"),
            ("UE5 Import", "import"),
            ("Assemble", "assemble"),
        ]
        for label, key in pipeline_steps:
            step_lbl = QLabel(f"○ {label}")
            step_lbl.setStyleSheet("font-size: 9px; color: #555;")
            step_lbl.setToolTip(f"Step: {label}")
            pipeline_row.addWidget(step_lbl)
            self.fti_pipeline_steps[key] = step_lbl
        
        pipeline_row.addStretch()
        progress_layout.addLayout(pipeline_row)
        
        layout.addWidget(progress_section)
        layout.addStretch()  # Push controls up
        
        # Add controls section to splitter
        fti_splitter.addWidget(controls_widget)
        
        # ═══════════════════════════════════════════════════════════════════
        # BOTTOM SECTION: Conversion Log (expandable via splitter)
        # ═══════════════════════════════════════════════════════════════════
        log_section = QGroupBox("📜 Conversion Log (drag handle above to expand)")
        log_section.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        log_section.setStyleSheet("""
            QGroupBox { font-weight: bold; font-size: 10px; border: 1px solid #3a3a5a; border-radius: 5px; margin-top: 8px; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        """)
        log_layout = QVBoxLayout(log_section)
        
        self.fti_log_text = QPlainTextEdit()
        self.fti_log_text.setReadOnly(True)
        self.fti_log_text.setFont(QFont("Courier", 9))
        self.fti_log_text.setMinimumHeight(60)  # Smaller minimum
        self.fti_log_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.fti_log_text.setStyleSheet("background-color: #1a1a2e; color: #ccc;")
        self.fti_log_text.setPlaceholderText("Conversion log will appear here...")
        log_layout.addWidget(self.fti_log_text)
        
        fti_splitter.addWidget(log_section)
        
        # Set splitter proportions: controls get more space initially, log can be expanded
        fti_splitter.setStretchFactor(0, 2)  # Controls
        fti_splitter.setStretchFactor(1, 1)  # Log
        fti_splitter.setSizes([350, 150])  # Initial sizes
        
        main_layout.addWidget(fti_splitter)
        
        # Initialize FTI IPC bridge reference
        self.fti_ipc_bridge = None
        self._current_conversion_id = None
        
        # Note: IPC service is auto-started in main() - no UI timer needed
        
        # File path change triggers format detection
        self.fti_file_path.textChanged.connect(self._detect_file_format)
        
        return panel
    
    def _browse_robot_file(self):
        """Open file browser for robot files - uses Windows Explorer via PowerShell for proper drive access"""
        import subprocess
        import os
        
        self._fti_log("Opening Windows file picker...")
        
        # Use PowerShell to open native Windows file dialog
        # This properly shows C:, D:, and all Windows drives
        ps_script = '''
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = "Select Robot Description File"
$dialog.Filter = "Robot Files (*.urdf;*.xacro;*.sdf;*.stl;*.obj;*.fbx;*.dae)|*.urdf;*.xacro;*.sdf;*.stl;*.obj;*.fbx;*.dae|URDF Files (*.urdf)|*.urdf|XACRO Files (*.xacro)|*.xacro|SDF Files (*.sdf)|*.sdf|Mesh Files (*.stl;*.obj;*.fbx;*.dae)|*.stl;*.obj;*.fbx;*.dae|All Files (*.*)|*.*"
$dialog.InitialDirectory = "D:\\ROA"
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Output $dialog.FileName
}
'''
        
        try:
            # Run PowerShell with the file dialog script
            result = subprocess.run(
                ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', ps_script],
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout for user to select file
            )
            
            if result.returncode == 0 and result.stdout.strip():
                windows_path = result.stdout.strip()
                
                # Convert Windows path to WSL path
                wsl_path = self._windows_to_wsl_path(windows_path)
                
                if wsl_path and os.path.exists(wsl_path):
                    self.fti_file_path.setText(wsl_path)
                    self._fti_log(f"✅ Selected: {os.path.basename(wsl_path)}")
                    self._fti_log(f"   Windows: {windows_path}")
                    self._fti_log(f"   WSL: {wsl_path}")
                else:
                    # Try using the Windows path directly (might work with wslpath)
                    self._fti_log(f"⚠️ Path conversion issue, trying wslpath...")
                    wsl_path = self._convert_with_wslpath(windows_path)
                    if wsl_path:
                        self.fti_file_path.setText(wsl_path)
                        self._fti_log(f"✅ Selected via wslpath: {wsl_path}")
                    else:
                        self._fti_log(f"❌ Could not convert path: {windows_path}")
            else:
                self._fti_log("File selection cancelled")
                
        except subprocess.TimeoutExpired:
            self._fti_log("⚠️ File dialog timed out")
        except FileNotFoundError:
            # PowerShell not available - fallback to Qt dialog
            self._fti_log("⚠️ PowerShell not available, using Qt fallback...")
            self._browse_robot_file_qt_fallback()
        except Exception as e:
            self._fti_log(f"❌ Error opening file picker: {e}")
            self._browse_robot_file_qt_fallback()
    
    def _windows_to_wsl_path(self, windows_path: str) -> str:
        """Convert Windows path (C:\\foo\\bar) to WSL path (/mnt/c/foo/bar)"""
        if not windows_path:
            return ""
        
        # Handle drive letter (e.g., D:\ROA\robots -> /mnt/d/ROA/robots)
        if len(windows_path) >= 2 and windows_path[1] == ':':
            drive_letter = windows_path[0].lower()
            rest_of_path = windows_path[2:].replace('\\', '/')
            return f"/mnt/{drive_letter}{rest_of_path}"
        
        # Already a Unix-style path?
        if windows_path.startswith('/'):
            return windows_path
        
        return windows_path.replace('\\', '/')
    
    def _convert_with_wslpath(self, windows_path: str) -> str:
        """Use wslpath utility to convert Windows path to WSL path"""
        import subprocess
        
        try:
            result = subprocess.run(
                ['wslpath', '-u', windows_path],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        
        return ""
    
    def _browse_robot_file_qt_fallback(self):
        """Fallback Qt file dialog when PowerShell is not available"""
        from PyQt6.QtWidgets import QFileDialog
        import os
        
        file_filter = (
            "Robot Files (*.urdf *.xacro *.sdf *.stl *.obj *.fbx *.dae);;"
            "URDF Files (*.urdf);;"
            "XACRO Files (*.xacro);;"
            "SDF Files (*.sdf);;"
            "Mesh Files (*.stl *.obj *.fbx *.dae);;"
            "All Files (*.*)"
        )
        
        # Try to find best starting directory
        start_dirs = [
            "/mnt/d/ROA",
            "/mnt/c/Users",
            "/mnt/d",
            "/mnt/c",
            os.path.expanduser("~"),
        ]
        
        start_dir = ""
        for d in start_dirs:
            if os.path.exists(d) and os.path.isdir(d):
                start_dir = d
                break
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Robot Description File",
            start_dir,
            file_filter
        )
        
        if file_path:
            self.fti_file_path.setText(file_path)
            self._fti_log(f"Selected file: {file_path}")

    def _prompt_output_destination(self, default_prefix: str):
        """Prompt user for output directory (Windows Explorer first) and name prefix.
        
        Returns tuple (windows_output_dir, name_prefix) or (None, None) if cancelled.
        """
        from PyQt6.QtWidgets import QFileDialog, QInputDialog
        import os
        import subprocess
        
        out_dir_win = None
        
        # Try Windows Explorer (PowerShell FolderBrowserDialog) first
        # Note: This requires Windows GUI to be accessible from WSL
        ps_script = r'''
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::EnableVisualStyles()
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = "Select Output Folder for ROA Conversion"
$dialog.RootFolder = [System.Environment+SpecialFolder]::MyComputer
# Try to set default path - handle if it doesn't exist
try {
    if (Test-Path "D:\ROA\Outputs") {
        $dialog.SelectedPath = "D:\ROA\Outputs"
    } elseif (Test-Path "D:\ROA") {
        $dialog.SelectedPath = "D:\ROA"
    } elseif (Test-Path "D:\") {
        $dialog.SelectedPath = "D:\"
    }
} catch { }
$dialog.ShowNewFolderButton = $true
# Create a hidden parent form to ensure dialog shows in foreground
$form = New-Object System.Windows.Forms.Form
$form.TopMost = $true
$form.StartPosition = 'CenterScreen'
$result = $dialog.ShowDialog($form)
$form.Dispose()
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Output $dialog.SelectedPath
} else {
    Write-Output ""
}
'''
        try:
            self._fti_log("║    Attempting Windows folder dialog...")
            result = subprocess.run(
                ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', ps_script],
                capture_output=True,
                text=True,
                timeout=120  # 2 minutes should be plenty
            )
            if result.returncode == 0:
                path = result.stdout.strip()
                if path and path not in ['', 'False', 'None']:
                    out_dir_win = path
                    self._fti_log(f"║ ✅ Output folder (Windows): {out_dir_win}")
                else:
                    # User cancelled the dialog
                    self._fti_log("║ ⚠️ User cancelled Windows folder dialog")
            else:
                stderr = result.stderr.strip() if result.stderr else "Unknown error"
                self._fti_log(f"║ ⚠️ PowerShell error (rc={result.returncode}): {stderr[:100]}")
        except subprocess.TimeoutExpired:
            self._fti_log("║ ⚠️ Windows folder dialog timed out (>120s)")
            out_dir_win = None
        except FileNotFoundError:
            self._fti_log("║ ⚠️ PowerShell not available, using Qt fallback")
            out_dir_win = None
        except Exception as e:
            self._fti_log(f"║ ⚠️ Windows folder dialog failed: {type(e).__name__}: {e}")
            out_dir_win = None
        
        # Fallback to Qt directory picker (Linux path) and convert to Windows
        if not out_dir_win:
            self._fti_log("║    Falling back to Qt directory picker...")
            # Find a valid starting directory
            start_dirs = [
                "/mnt/d/ROA/Outputs",
                "/mnt/d/ROA",
                "/mnt/d",
                "/mnt/c/Users",
                os.path.expanduser("~")
            ]
            start_dir = ""
            for d in start_dirs:
                if os.path.exists(d) and os.path.isdir(d):
                    start_dir = d
                    break
            
            out_dir_linux = QFileDialog.getExistingDirectory(
                self,
                "Select Output Folder",
                start_dir,
                QFileDialog.Option.ShowDirsOnly
            )
            if not out_dir_linux:
                self._fti_log("║ ⚠️ Output selection cancelled")
                return None, None
            try:
                handler = get_path_handler()
                out_dir_win = handler.to_windows_path(out_dir_linux) or out_dir_linux
            except Exception:
                out_dir_win = out_dir_linux
            self._fti_log(f"║ ✅ Output folder (converted): {out_dir_win}")
        
        # Ask for optional name prefix (keep Qt input for simplicity)
        ok = True
        name_prefix = default_prefix
        try:
            name_prefix, ok = QInputDialog.getText(
                self,
                "Output Name Prefix",
                "Enter file name prefix:",
                text=default_prefix
            )
        except Exception:
            ok = True
            name_prefix = default_prefix
        if not ok or not name_prefix:
            name_prefix = default_prefix
        
        return out_dir_win, name_prefix
    
    def _paste_path_from_clipboard(self):
        """Paste path from clipboard and auto-convert Windows paths to WSL"""
        from PyQt6.QtWidgets import QApplication
        import os
        
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        
        if not text:
            self._fti_log("⚠️ Clipboard is empty")
            return
        
        # Check if it's a Windows path (e.g., D:\ROA\robots\...)
        if len(text) >= 2 and text[1] == ':':
            wsl_path = self._windows_to_wsl_path(text)
            self._fti_log(f"Converting Windows path: {text}")
            self._fti_log(f"  → WSL path: {wsl_path}")
            
            if os.path.exists(wsl_path):
                self.fti_file_path.setText(wsl_path)
                self._fti_log(f"✅ Path set successfully")
            else:
                # Try wslpath as backup
                wsl_path2 = self._convert_with_wslpath(text)
                if wsl_path2 and os.path.exists(wsl_path2):
                    self.fti_file_path.setText(wsl_path2)
                    self._fti_log(f"✅ Path set via wslpath: {wsl_path2}")
                else:
                    # Set anyway - user might fix it
                    self.fti_file_path.setText(wsl_path)
                    self._fti_log(f"⚠️ Path may not exist: {wsl_path}")
        else:
            # Assume it's already a valid path
            self.fti_file_path.setText(text)
            if os.path.exists(text):
                self._fti_log(f"✅ Path pasted: {text}")
            else:
                self._fti_log(f"⚠️ Path pasted (may not exist): {text}")
    
    def _open_windows_explorer(self):
        """Open Windows Explorer at D:\\ROA or a default location"""
        import subprocess
        
        # Try to open at common robot file locations
        paths_to_try = [
            "D:\\ROA",
            "D:\\ROA\\robots",
            "D:\\",
            "C:\\Users",
        ]
        
        for win_path in paths_to_try:
            wsl_path = self._windows_to_wsl_path(win_path)
            import os
            if os.path.exists(wsl_path):
                try:
                    subprocess.Popen(['explorer.exe', win_path])
                    self._fti_log(f"📂 Opened Explorer at: {win_path}")
                    return
                except Exception as e:
                    self._fti_log(f"⚠️ Failed to open Explorer: {e}")
        
        # Fallback: just open explorer
        try:
            subprocess.Popen(['explorer.exe', '.'])
            self._fti_log("📂 Opened Windows Explorer")
        except Exception as e:
            self._fti_log(f"❌ Could not open Explorer: {e}")
    
    def _detect_file_format(self, file_path: str):
        """Detect and display file format information"""
        import os
        
        if not file_path or not os.path.exists(file_path):
            # Reset all format labels
            for key in self.fti_format_labels:
                self.fti_format_labels[key].setText("--")
                self.fti_format_labels[key].setStyleSheet("font-weight: bold; font-size: 10px; color: #aaa;")
            return
        
        ext = os.path.splitext(file_path)[1].lower()
        format_map = {
            '.urdf': 'URDF',
            '.xacro': 'XACRO',
            '.sdf': 'SDF',
            '.stl': 'STL (Mesh)',
            '.obj': 'OBJ (Mesh)',
            '.fbx': 'FBX',
            '.dae': 'COLLADA',
        }
        
        detected = format_map.get(ext, f"Unknown ({ext})")
        self.fti_format_labels['detected_format'].setText(detected)
        self.fti_format_labels['detected_format'].setStyleSheet("font-weight: bold; font-size: 10px; color: #00ff00;")
        
        # For URDF/XACRO, try to parse for more info
        if ext in ['.urdf', '.xacro']:
            self._parse_urdf_info(file_path)
        else:
            # Mesh file - just show basic info
            self.fti_format_labels['robot_name'].setText(os.path.basename(file_path))
            self.fti_format_labels['link_count'].setText("N/A")
            self.fti_format_labels['joint_count'].setText("N/A")
            self.fti_format_labels['mesh_count'].setText("1")
    
    def _parse_urdf_info(self, file_path: str):
        """Parse URDF/XACRO for basic information"""
        import os
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            
            # Simple regex parsing (without full XML parsing)
            import re
            
            # Robot name
            robot_match = re.search(r'<robot[^>]*name=["\']([^"\']+)["\']', content)
            robot_name = robot_match.group(1) if robot_match else os.path.basename(file_path)
            self.fti_format_labels['robot_name'].setText(robot_name)
            
            # Count links
            link_count = len(re.findall(r'<link\s+name=', content))
            self.fti_format_labels['link_count'].setText(str(link_count))
            
            # Count joints
            joint_count = len(re.findall(r'<joint\s+name=', content))
            self.fti_format_labels['joint_count'].setText(str(joint_count))
            
            # Count mesh references
            mesh_count = len(re.findall(r'<mesh\s+filename=', content))
            self.fti_format_labels['mesh_count'].setText(str(mesh_count))
            
            self._fti_log(f"Parsed: {robot_name} ({link_count} links, {joint_count} joints, {mesh_count} meshes)")
            
        except Exception as e:
            self._fti_log(f"Error parsing file: {e}")
            self.fti_format_labels['robot_name'].setText("Parse error")
    
    def _start_ipc_service(self):
        """Start the IPC service"""
        import subprocess
        import os
        
        self._fti_log("Starting IPC service...")
        
        # Absolute path to service manager (correct path structure)
        service_manager_path = "/home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python/service_manager.py"
        
        # Fallback: try relative path from webthread/standalone directory
        if not os.path.exists(service_manager_path):
            # webthread/standalone -> components/files-type-importer/src/python
            relative_path = os.path.join(
                os.path.dirname(__file__), '..', '..',
                'files-type-importer', 'src', 'python', 'service_manager.py'
            )
            if os.path.exists(relative_path):
                service_manager_path = os.path.abspath(relative_path)
        
        if os.path.exists(service_manager_path):
            try:
                # Run synchronously to capture output
                result = subprocess.run(
                    ['python3', service_manager_path, 'start'],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                if result.returncode == 0:
                    self._fti_log("✅ IPC service started successfully")
                else:
                    self._fti_log(f"⚠️ Service start returned code {result.returncode}")
                    if result.stderr:
                        # Log first line of error
                        first_err = result.stderr.split('\n')[0]
                        self._fti_log(f"   Error: {first_err}")
            except subprocess.TimeoutExpired:
                self._fti_log("⚠️ Service start timed out (may still be starting)")
            except Exception as e:
                self._fti_log(f"❌ Failed to start IPC service: {e}")
        else:
            self._fti_log(f"❌ Service manager not found at: {service_manager_path}")
    
    def _stop_ipc_service(self):
        """Stop the IPC service"""
        import subprocess
        import os
        
        self._fti_log("Stopping IPC service...")
        
        # Absolute path to service manager (correct path structure)
        service_manager_path = "/home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python/service_manager.py"
        
        # Fallback: try relative path from webthread/standalone directory
        if not os.path.exists(service_manager_path):
            relative_path = os.path.join(
                os.path.dirname(__file__), '..', '..',
                'files-type-importer', 'src', 'python', 'service_manager.py'
            )
            if os.path.exists(relative_path):
                service_manager_path = os.path.abspath(relative_path)
        
        if os.path.exists(service_manager_path):
            try:
                subprocess.run(['python3', service_manager_path, 'stop'], timeout=5)
                self._fti_log("IPC service stopped")
            except Exception as e:
                self._fti_log(f"Failed to stop IPC service: {e}")
    
    def _prepare_usd_for_ue5(self):
        """
        Prepare an existing USD file for UE5 import.
        
        This adds the ROA hierarchy assembly metadata and Python script
        to an existing USD file so it can be properly reconstructed in UE5.
        """
        import os
        import uuid
        import json
        import time
        
        file_path = self.fti_file_path.text().strip()
        
        if not file_path:
            self._fti_log("❌ No file selected")
            return
        
        if not os.path.exists(file_path):
            self._fti_log(f"❌ File not found: {file_path}")
            return
        
        ext = os.path.splitext(file_path)[1].lower()
        
        # This function is primarily for USD files, but also works for URDF/XACRO
        # by first converting then preparing
        if ext not in ['.usd', '.usda', '.usdc', '.usdz', '.urdf', '.xacro', '.sdf']:
            self._fti_log(f"❌ Unsupported file type: {ext}")
            self._fti_log("   Supported: .usd, .usda, .usdc, .usdz, .urdf, .xacro, .sdf")
            return
        
        self._fti_log(f"🎮 Preparing for UE5: {os.path.basename(file_path)}")
        self.fti_prepare_ue5_btn.setEnabled(False)
        
        # Generate request
        request_id = str(uuid.uuid4())
        self._current_conversion_id = request_id
        
        if ext in ['.usd', '.usda', '.usdc', '.usdz']:
            # USD file - prepare only (no output prompt needed)
            request = {
                "protocol_version": PROTOCOL_VERSION,
                "request_id": request_id,
                "request_type": "prepare_for_ue5",
                "input": {
                    "path": file_path
                },
                "output": {},
                "options": {
                    "add_hierarchy_metadata": True,
                    "generate_assembly_script": True,
                    "auto_assemble": self.fti_auto_assemble.isChecked(),
                    "generate_blueprint": self.fti_generate_bp.isChecked(),
                },
            }
        else:
            # URDF/XACRO/SDF - convert and prepare: ask for output location
            default_prefix = os.path.splitext(os.path.basename(file_path))[0]
            out_dir_win, name_prefix = self._prompt_output_destination(default_prefix)
            if not out_dir_win:
                self.fti_prepare_ue5_btn.setEnabled(True)
                return

            request = {
                "protocol_version": PROTOCOL_VERSION,
                "request_id": request_id,
                "request_type": "convert_and_prepare",
                "input": {
                    "path": file_path
                },
                "output": {
                    "directory": out_dir_win,
                    "name_prefix": name_prefix,
                    "formats": ["usd", "ue5_script"]
                },
                "options": {
                    "mesh_handling": self.fti_mesh_handling.currentText().lower().replace(" ", "_"),
                    "auto_assemble": self.fti_auto_assemble.isChecked(),
                    "generate_blueprint": self.fti_generate_bp.isChecked(),
                    "add_hierarchy_metadata": True,
                    "generate_assembly_script": True,
                    "generate_ue5_script": True
                },
            }
        
        # Write request to IPC folder
        ipc_folder = "/mnt/d/ROA/.ipc" if os.path.exists("/mnt/d/ROA/.ipc") else os.path.expanduser("~/.roa/ipc")
        os.makedirs(os.path.join(ipc_folder, "requests"), exist_ok=True)
        
        request_file = os.path.join(ipc_folder, "requests", f"{request_id}.request.json")
        
        try:
            # Atomic write
            tmp_file = request_file + ".tmp"
            with open(tmp_file, 'w') as f:
                json.dump(request, f, indent=2)
            os.rename(tmp_file, request_file)
            
            self._fti_log(f"✅ Prepare request submitted: {request_id[:8]}...")
            
            if ext in ['.usd', '.usda', '.usdc', '.usdz']:
                self._fti_log("   Adding hierarchy assembly metadata to USD...")
            else:
                self._fti_log("   Will convert and add assembly script...")
            
            # Start progress monitor
            self._start_progress_monitor(request_id)
            
        except Exception as e:
            self._fti_log(f"❌ Failed to submit request: {e}")
            self.fti_prepare_ue5_btn.setEnabled(True)
    
    def _start_fti_conversion(self):
        """Start the FTI conversion pipeline with detailed logging"""
        import os
        import uuid
        import json
        import time
        from datetime import datetime
        
        file_path = self.fti_file_path.text().strip()
        
        # Enhanced logging header
        self._fti_log("╔" + "═" * 60)
        self._fti_log(f"║ 🔧 FTI CONVERSION - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._fti_log("╠" + "═" * 60)
        
        if not file_path:
            self._fti_log("║ ❌ ERROR: No file selected")
            self._fti_log("╚" + "═" * 60)
            return
        
        if not os.path.exists(file_path):
            self._fti_log(f"║ ❌ ERROR: File not found")
            self._fti_log(f"║    Path: {file_path}")
            self._fti_log("╚" + "═" * 60)
            return
        
        # Log input file details
        file_size = os.path.getsize(file_path)
        file_ext = os.path.splitext(file_path)[1]
        self._fti_log("║ 📂 INPUT FILE:")
        self._fti_log(f"║    Path: {file_path}")
        self._fti_log(f"║    Name: {os.path.basename(file_path)}")
        self._fti_log(f"║    Size: {file_size:,} bytes")
        self._fti_log(f"║    Format: {file_ext}")
        
        # Reset progress
        self.fti_progress_bar.setValue(0)
        self._update_pipeline_step("parse", "active")
        self.fti_convert_btn.setEnabled(False)
        
        # Ask output destination
        default_prefix = os.path.splitext(os.path.basename(file_path))[0]
        self._fti_log("╠" + "═" * 60)
        self._fti_log("║ 📍 OUTPUT SELECTION:")
        self._fti_log(f"║    Prompting user for output location...")
        self._fti_log(f"║    Default prefix: {default_prefix}")
        
        out_dir_win, name_prefix = self._prompt_output_destination(default_prefix)
        if not out_dir_win:
            self._fti_log("║ ⚠️ CANCELLED: User cancelled output selection")
            self._fti_log("╚" + "═" * 60)
            self.fti_convert_btn.setEnabled(True)
            return

        self._fti_log(f"║ ✅ Output destination selected:")
        self._fti_log(f"║    Directory: {out_dir_win}")
        self._fti_log(f"║    Name prefix: {name_prefix}")

        # Generate conversion request (protocol-compliant)
        request_id = str(uuid.uuid4())
        self._current_conversion_id = request_id
        
        self._fti_log("╠" + "═" * 60)
        self._fti_log("║ 🎫 REQUEST DETAILS:")
        self._fti_log(f"║    Request ID: {request_id[:8]}...{request_id[-4:]}")
        self._fti_log(f"║    Protocol: {PROTOCOL_VERSION}")
        
        request = {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "request_type": "convert",
            "input": {
                "path": file_path
            },
            "output": {
                "directory": out_dir_win,
                "name_prefix": name_prefix,
                "formats": [self.fti_output_format.currentText().split()[0].lower()]
            },
            "options": {
                "mesh_handling": self.fti_mesh_handling.currentText().lower().replace(" ", "_"),
                "auto_assemble": self.fti_auto_assemble.isChecked(),
                "generate_blueprint": self.fti_generate_bp.isChecked(),
                "generate_ue5_script": True
            },
        }
        
        # Log conversion options
        self._fti_log("║ ⚙️ CONVERSION OPTIONS:")
        self._fti_log(f"║    Output format: {request['output']['formats'][0]}")
        self._fti_log(f"║    Mesh handling: {request['options']['mesh_handling']}")
        self._fti_log(f"║    Auto assemble: {request['options']['auto_assemble']}")
        self._fti_log(f"║    Generate BP: {request['options']['generate_blueprint']}")
        self._fti_log(f"║    UE5 script: {request['options']['generate_ue5_script']}")
        
        # Write request to IPC folder
        ipc_folder = "/mnt/d/ROA/.ipc" if os.path.exists("/mnt/d/ROA/.ipc") else os.path.expanduser("~/.roa/ipc")
        os.makedirs(os.path.join(ipc_folder, "requests"), exist_ok=True)
        
        request_file = os.path.join(ipc_folder, "requests", f"{request_id}.request.json")
        
        self._fti_log("╠" + "═" * 60)
        self._fti_log("║ 📤 SUBMITTING REQUEST:")
        self._fti_log(f"║    IPC folder: {ipc_folder}")
        
        try:
            # Atomic write
            tmp_file = request_file + ".tmp"
            with open(tmp_file, 'w') as f:
                json.dump(request, f, indent=2)
            os.rename(tmp_file, request_file)
            
            self._fti_log(f"║ ✅ Request file written successfully")
            self._fti_log("╠" + "═" * 60)
            self._fti_log("║ ⏳ WAITING FOR IPC SERVICE...")
            self._fti_log("║    Monitoring for response...")
            self._fti_log("╚" + "═" * 60)
            
            # Start progress monitor
            self._start_progress_monitor(request_id)
            
        except Exception as e:
            self._fti_log(f"║ ❌ FAILED TO SUBMIT REQUEST")
            self._fti_log(f"║    Error: {e}")
            self._fti_log("╚" + "═" * 60)
            self.fti_convert_btn.setEnabled(True)
    
    def _start_progress_monitor(self, request_id: str):
        """Start monitoring conversion progress"""
        import os
        import json
        
        ipc_folder = "/mnt/d/ROA/.ipc" if os.path.exists("/mnt/d/ROA/.ipc") else os.path.expanduser("~/.roa/ipc")
        
        def check_progress():
            if self._current_conversion_id != request_id:
                return  # Conversion was cancelled or new one started
            
            # Check for progress file
            progress_file = os.path.join(ipc_folder, "progress", f"{request_id}.progress.json")
            response_file = os.path.join(ipc_folder, "responses", f"{request_id}.response.json")
            
            if os.path.exists(response_file):
                # Conversion complete
                try:
                    with open(response_file, 'r') as f:
                        response = json.load(f)
                    
                    if response.get('success'):
                        self.fti_progress_bar.setValue(100)
                        
                        # Detailed success logging
                        self._fti_log("")
                        self._fti_log("╔" + "═" * 60)
                        self._fti_log("║ ✅ CONVERSION COMPLETE")
                        self._fti_log("╠" + "═" * 60)
                        
                        # Determine output path from structured outputs
                        outputs = response.get('outputs', {}) or {}
                        if isinstance(outputs, dict) and outputs:
                            self._fti_log("║ 📦 OUTPUT FILES:")
                            for key, value in outputs.items():
                                if isinstance(value, dict):
                                    path = value.get('windows_path') or value.get('linux_path') or str(value)
                                elif isinstance(value, str):
                                    path = value
                                else:
                                    path = str(value)
                                self._fti_log(f"║    {key}: {path}")
                        
                        # Log stats if available
                        stats = response.get('stats', {})
                        if stats:
                            self._fti_log("╠" + "═" * 60)
                            self._fti_log("║ 📊 CONVERSION STATS:")
                            for key, value in stats.items():
                                self._fti_log(f"║    {key}: {value}")
                        
                        # Log timing
                        duration = response.get('duration')
                        if duration:
                            self._fti_log("╠" + "═" * 60)
                            self._fti_log(f"║ ⏱️ Duration: {duration:.2f}s")
                        
                        self._fti_log("╚" + "═" * 60)
                        self._mark_all_steps_complete()
                    else:
                        # Detailed error logging
                        self._fti_log("")
                        self._fti_log("╔" + "═" * 60)
                        self._fti_log("║ ❌ CONVERSION FAILED")
                        self._fti_log("╠" + "═" * 60)
                        error_msg = response.get('error', 'Unknown error')
                        error_code = response.get('error_code', 'N/A')
                        self._fti_log(f"║ Error Code: {error_code}")
                        self._fti_log(f"║ Message: {error_msg}")
                        
                        # Log error details if available
                        details = response.get('error_details', {})
                        if details:
                            self._fti_log("╠" + "═" * 60)
                            self._fti_log("║ 🔍 ERROR DETAILS:")
                            for key, value in details.items():
                                self._fti_log(f"║    {key}: {value}")
                        
                        self._fti_log("╚" + "═" * 60)
                    
                    # Re-enable both buttons
                    self.fti_convert_btn.setEnabled(True)
                    self.fti_prepare_ue5_btn.setEnabled(True)
                    self._current_conversion_id = None
                except Exception as e:
                    self._fti_log(f"Error reading response: {e}")
                return
            
            if os.path.exists(progress_file):
                try:
                    with open(progress_file, 'r') as f:
                        progress = json.load(f)
                    
                    percent = progress.get('percent', 0)
                    stage = progress.get('stage', 'processing')
                    message = progress.get('message', '')
                    
                    self.fti_progress_bar.setValue(int(percent))
                    self.fti_progress_status.setText(f"{stage}: {message}")
                    
                    # Update pipeline steps
                    self._update_pipeline_from_stage(stage)
                    
                except Exception:
                    pass
            
            # Continue monitoring
            QTimer.singleShot(500, check_progress)
        
        # Start monitoring
        QTimer.singleShot(500, check_progress)
    
    def _update_pipeline_step(self, step: str, state: str):
        """Update a pipeline step indicator"""
        if step not in self.fti_pipeline_steps:
            return
        
        label = self.fti_pipeline_steps[step]
        step_name = label.text()[2:]  # Remove "○ " prefix
        
        if state == "complete":
            label.setText(f"✓ {step_name}")
            label.setStyleSheet("font-size: 9px; color: #00ff00;")
        elif state == "active":
            label.setText(f"◉ {step_name}")
            label.setStyleSheet("font-size: 9px; color: #3498db;")
        elif state == "error":
            label.setText(f"✗ {step_name}")
            label.setStyleSheet("font-size: 9px; color: #ff4444;")
        else:  # pending
            label.setText(f"○ {step_name}")
            label.setStyleSheet("font-size: 9px; color: #555;")
    
    def _update_pipeline_from_stage(self, stage: str):
        """Update pipeline steps based on current stage"""
        stage_order = ['parse', 'xacro', 'hierarchy', 'meshes', 'usd', 'ipc', 'import', 'assemble']
        stage_map = {
            'parsing': 'parse',
            'xacro_processing': 'xacro',
            'building_hierarchy': 'hierarchy',
            'converting_meshes': 'meshes',
            'generating_usd': 'usd',
            'ipc_transfer': 'ipc',
            'ue5_import': 'import',
            'assembling': 'assemble',
        }
        
        current = stage_map.get(stage, stage)
        
        for step in stage_order:
            if step == current:
                self._update_pipeline_step(step, "active")
                break
            else:
                self._update_pipeline_step(step, "complete")
    
    def _mark_all_steps_complete(self):
        """Mark all pipeline steps as complete"""
        for step in self.fti_pipeline_steps:
            self._update_pipeline_step(step, "complete")
        self.fti_progress_status.setText("✅ Robot import complete!")
        self.fti_progress_status.setStyleSheet("font-size: 10px; color: #00ff00;")
    
    def _fti_log(self, message: str):
        """Add message to FTI log"""
        from datetime import datetime
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.fti_log_text.appendPlainText(f"[{timestamp}] {message}")
        # Scroll to bottom
        scrollbar = self.fti_log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def create_component_status_widget(self):
        """Legacy method - redirects to health status widget"""
        return self.create_health_status_widget()
    
    def create_log_widget(self):
        """
        Create enhanced log viewer widget with filtering capabilities.
        Inspired by NiceGUI log viewer pattern with level/source filtering.
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(5)
        
        # Filter controls row (new - inspired by NiceGUI Test-8)
        self.log_filter = LogFilterWidget()
        self.log_filter.filterChanged.connect(self._apply_log_filter)
        layout.addWidget(self.log_filter)
        
        # Button controls row
        controls = QHBoxLayout()
        
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setStyleSheet("padding: 5px 10px;")
        refresh_btn.clicked.connect(self.update_ui)
        controls.addWidget(refresh_btn)
        
        clear_btn = QPushButton("🗑️ Clear Logs")
        clear_btn.clicked.connect(self._clear_all_logs)
        controls.addWidget(clear_btn)
        
        copy_btn = QPushButton("📋 Copy All")
        copy_btn.setStyleSheet("background-color: #2a4a6a; color: white; padding: 5px 10px;")
        copy_btn.clicked.connect(lambda: self.copy_to_clipboard(self.log_text.toPlainText(), "System Logs"))
        controls.addWidget(copy_btn)
        
        # Export button (new)
        export_btn = QPushButton("💾 Export")
        export_btn.setStyleSheet("background-color: #5a4a2a; color: white; padding: 5px 10px;")
        export_btn.setToolTip("Export logs to file")
        export_btn.clicked.connect(self._export_logs)
        controls.addWidget(export_btn)
        
        # Auto-scroll toggle (new)
        self._auto_scroll = True
        self.auto_scroll_btn = QPushButton("⬇️ Auto-scroll: ON")
        self.auto_scroll_btn.setCheckable(True)
        self.auto_scroll_btn.setChecked(True)
        self.auto_scroll_btn.setStyleSheet("padding: 5px 10px;")
        self.auto_scroll_btn.clicked.connect(self._toggle_auto_scroll)
        controls.addWidget(self.auto_scroll_btn)
        
        controls.addStretch()
        
        # Log stats (new)
        self.log_count_label = QLabel("Logs: 0")
        self.log_count_label.setStyleSheet("color: #888; font-size: 10px;")
        controls.addWidget(self.log_count_label)
        
        layout.addLayout(controls)
        
        # Log text area with enhanced styling
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier", 9))
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a2e;
                color: #ccc;
                border: 1px solid #3a3a5a;
                border-radius: 5px;
            }
        """)
        layout.addWidget(self.log_text)
        
        # Initialize log storage for filtering
        self._log_entries = []  # Store structured log entries
        
        return widget
    
    def _clear_all_logs(self):
        """Clear all logs"""
        self.log_text.clear()
        self._log_entries = []
        self.log_count_label.setText("Logs: 0")
    
    def _toggle_auto_scroll(self):
        """Toggle auto-scroll feature"""
        self._auto_scroll = self.auto_scroll_btn.isChecked()
        status = "ON" if self._auto_scroll else "OFF"
        self.auto_scroll_btn.setText(f"⬇️ Auto-scroll: {status}")
    
    def _apply_log_filter(self):
        """Apply log filters to the log view"""
        if not hasattr(self, '_log_entries'):
            return
        
        filters = self.log_filter.get_filters()
        
        # Filter entries
        filtered = []
        for entry in self._log_entries:
            # Level filter
            if filters['level'] != 'ALL':
                entry_level = entry.get('level', 'INFO').upper()
                if entry_level != filters['level']:
                    continue
            
            # Source filter
            if filters['source'] != 'ALL':
                entry_source = entry.get('source', 'System')
                if entry_source != filters['source']:
                    continue
            
            # Text search
            if filters['search']:
                if filters['search'] not in entry.get('message', '').lower():
                    continue
            
            filtered.append(entry)
        
        # Rebuild log text
        self.log_text.clear()
        for entry in filtered[-500:]:  # Last 500 entries
            self._append_log_entry_to_view(entry)
        
        self.log_count_label.setText(f"Logs: {len(filtered)} (filtered)")
    
    def _append_log_entry_to_view(self, entry: dict):
        """Append a single log entry to the view with color coding"""
        level = entry.get('level', 'INFO').upper()
        timestamp = entry.get('timestamp', '')
        source = entry.get('source', 'System')
        message = entry.get('message', '')
        
        # Color based on level
        level_colors = {
            'DEBUG': '#888888',
            'INFO': '#4CAF50',
            'WARNING': '#FF9800',
            'ERROR': '#F44336',
            'SUCCESS': '#00BCD4',
        }
        color = level_colors.get(level, '#ccc')
        
        # Format log line with HTML
        html = f'<span style="color: #666;">[{timestamp}]</span> '
        html += f'<span style="color: {color}; font-weight: bold;">[{level}]</span> '
        html += f'<span style="color: #5a9aca;">[{source}]</span> '
        html += f'<span style="color: #ccc;">{message}</span>'
        
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)
        self.log_text.insertHtml(html + '<br>')
        
        if self._auto_scroll:
            scrollbar = self.log_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
    
    def _export_logs(self):
        """Export logs to a file"""
        from PyQt6.QtWidgets import QFileDialog
        import os
        
        default_name = f"roa_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Logs",
            os.path.expanduser(f"~/{default_name}"),
            "Text Files (*.txt);;All Files (*.*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w') as f:
                    for entry in self._log_entries:
                        f.write(f"[{entry.get('timestamp', '')}] [{entry.get('level', '')}] [{entry.get('source', '')}] {entry.get('message', '')}\n")
                self.add_log(f"Logs exported to: {file_path}", "INFO", "System")
            except Exception as e:
                self.add_log(f"Failed to export logs: {e}", "ERROR", "System")
    
    def add_log(self, message: str, level: str = "INFO", source: str = "System"):
        """
        Add a structured log entry with level and source.
        Enhanced from simple text logging to support filtering.
        """
        entry = {
            'timestamp': datetime.now().strftime('%H:%M:%S.%f')[:-3],
            'level': level.upper(),
            'source': source,
            'message': message,
        }
        
        # Store in entries list
        if not hasattr(self, '_log_entries'):
            self._log_entries = []
        self._log_entries.append(entry)
        
        # Trim to last 1000 entries
        if len(self._log_entries) > 1000:
            self._log_entries = self._log_entries[-1000:]
        
        # Check if filters match
        if hasattr(self, 'log_filter'):
            filters = self.log_filter.get_filters()
            
            # Check level filter
            if filters['level'] != 'ALL' and level.upper() != filters['level']:
                return  # Don't show filtered entry
            
            # Check source filter
            if filters['source'] != 'ALL' and source != filters['source']:
                return
            
            # Check search filter
            if filters['search'] and filters['search'] not in message.lower():
                return
        
        # Append to view
        self._append_log_entry_to_view(entry)
        
        # Update count
        if hasattr(self, 'log_count_label'):
            self.log_count_label.setText(f"Logs: {len(self._log_entries)}")
    
    def create_stats_widget(self):
        """Create statistics widget"""
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh Statistics")
        refresh_btn.setStyleSheet("padding: 5px 10px;")
        refresh_btn.clicked.connect(self.update_statistics)
        main_layout.addWidget(refresh_btn)
        
        # Statistics grid
        stats_container = QWidget()
        layout = QGridLayout(stats_container)
        main_layout.addWidget(stats_container)
        
        # Statistics labels
        stats = [
            ("Total Components:", "total_components"),
            ("Healthy:", "healthy_components"),
            ("Degraded:", "degraded_components"),
            ("Failed:", "failed_components"),
            ("Total Errors:", "error_count"),
            ("Total Warnings:", "warning_count"),
            ("HB Subsystem:", "hb_status"),
            ("Uptime:", "uptime"),
        ]
        
        self.stat_labels = {}
        for i, (label, key) in enumerate(stats):
            lbl = QLabel(label)
            lbl.setStyleSheet("font-weight: bold;")
            layout.addWidget(lbl, i, 0)
            value_label = QLabel("--")
            value_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            layout.addWidget(value_label, i, 1)
            self.stat_labels[key] = value_label
        
        layout.setRowStretch(len(stats), 1)
        main_layout.addStretch()
        
        # Start stats update timer
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_statistics)
        self.stats_timer.start(3000)  # Update every 3 seconds
        
        # Initial update
        QTimer.singleShot(1000, self.update_statistics)
        
        return widget
    
    def update_statistics(self):
        """Update statistics from WebthreadCore"""
        if not self.webthread_core:
            return
        
        try:
            status = self.webthread_core.get_system_status()
            if status:
                self.stat_labels['total_components'].setText(str(status.get('total_components', 0)))
                
                healthy = status.get('healthy_components', 0)
                self.stat_labels['healthy_components'].setText(str(healthy))
                self.stat_labels['healthy_components'].setStyleSheet("color: #00ff00; font-weight: bold;")
                
                degraded = status.get('degraded_components', 0)
                self.stat_labels['degraded_components'].setText(str(degraded))
                self.stat_labels['degraded_components'].setStyleSheet(f"color: {'#ffaa00' if degraded > 0 else '#888'}; font-weight: bold;")
                
                failed = status.get('failed_components', 0)
                self.stat_labels['failed_components'].setText(str(failed))
                self.stat_labels['failed_components'].setStyleSheet(f"color: {'#ff4444' if failed > 0 else '#888'}; font-weight: bold;")
                
                self.stat_labels['error_count'].setText(str(status.get('error_count', 0)))
                self.stat_labels['warning_count'].setText(str(status.get('warning_count', 0)))
                
                # HB status
                hb_enabled = status.get('hb_enabled', False)
                self.stat_labels['hb_status'].setText("✅ Enabled" if hb_enabled else "❌ Disabled")
                self.stat_labels['hb_status'].setStyleSheet(f"color: {'#00ff00' if hb_enabled else '#ff4444'}; font-weight: bold;")
                
                # Uptime
                uptime = int(status.get('uptime', 0))
                hours = uptime // 3600
                minutes = (uptime % 3600) // 60
                seconds = uptime % 60
                self.stat_labels['uptime'].setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        except Exception as e:
            self.add_log(f"Error updating statistics: {e}", "ERROR")
    
    def update_hb_status(self):
        """Update HB status from WebthreadCore
        
        NOTE: HB should ALWAYS be functioning - it's a core monitoring system.
        If the HB subsystem appears unavailable, we show a warning but assume
        the system is still monitoring via fallback mechanisms.
        """
        if not self.webthread_core:
            # Even without core, HB monitoring continues via file-based fallback
            self.hb_enabled_label.setText("● HB: ACTIVE (Fallback)")
            self.hb_enabled_label.setStyleSheet("color: #ffaa00; font-weight: bold;")
            return
        
        # Check if HB subsystem is available
        hb_subsystem = getattr(self.webthread_core, 'hb_subsystem', None)
        hb_enabled = getattr(self.webthread_core, '_hb_enabled', True)  # Default to True
        
        # HB should always be functioning - if subsystem is not available, use fallback
        if hb_subsystem:
            self.hb_enabled_label.setText("● HB: ACTIVE")
            self.hb_enabled_label.setStyleSheet("color: #00ff00; font-weight: bold;")
            
            # Update circuit breakers
            try:
                cb_states = self.webthread_core.get_circuit_breaker_states() if hasattr(self.webthread_core, 'get_circuit_breaker_states') else {}
                for i in range(self.cb_table.rowCount()):
                    comp = self.cb_table.item(i, 0).text()
                    if comp in cb_states:
                        state = cb_states[comp]
                        state_item = QTableWidgetItem(state)
                        if state == "CLOSED":
                            state_item.setForeground(QColor("#00ff00"))
                        elif state == "HALF_OPEN":
                            state_item.setForeground(QColor("#ffaa00"))
                        else:  # OPEN
                            state_item.setForeground(QColor("#ff4444"))
                        self.cb_table.setItem(i, 1, state_item)
            except Exception as e:
                self.add_log(f"Error updating CB states: {e}", "ERROR")
            
            # Update receiver stats
            try:
                stats = self.webthread_core.get_receiver_stats() if hasattr(self.webthread_core, 'get_receiver_stats') else {}
                if stats:
                    self.hb_stat_labels['total_hb'].setText(str(stats.get('total_received', 0)))
                    self.hb_stat_labels['hb_rate'].setText(f"{stats.get('rate_per_sec', 0):.1f}")
                    self.hb_stat_labels['timeouts'].setText(str(stats.get('timeouts', 0)))
                    self.hb_stat_labels['seq_gaps'].setText(str(stats.get('sequence_gaps', 0)))
                    uptime = stats.get('uptime_seconds', 0)
                    self.hb_stat_labels['hb_uptime'].setText(f"{int(uptime)}s")
            except Exception as e:
                self.add_log(f"Error updating receiver stats: {e}", "ERROR")
            
            # Update recovery history
            try:
                history = self.webthread_core.get_recovery_history() if hasattr(self.webthread_core, 'get_recovery_history') else []
                if history:
                    lines = []
                    for h in history[-5:]:  # Last 5 recoveries
                        if hasattr(h, 'to_dict'):
                            hd = h.to_dict()
                        elif isinstance(h, dict):
                            hd = h
                        else:
                            continue
                        ts = hd.get('timestamp', hd.get('attempt_time', '?'))
                        if isinstance(ts, float):
                            ts = datetime.fromtimestamp(ts).strftime('%H:%M:%S')
                        lines.append(f"[{ts}] {hd.get('component', hd.get('component_name', '?'))}: {hd.get('action', '?')} - {hd.get('result', hd.get('success', '?'))}")
                    self.recovery_text.setPlainText('\n'.join(lines))
                else:
                    self.recovery_text.setPlainText("No recovery attempts yet.")
            except Exception as e:
                self.recovery_text.setPlainText(f"Error: {e}")
            
            # Update Alert Levels table from HB
            try:
                alert_levels = self.webthread_core.get_all_alert_levels() if hasattr(self.webthread_core, 'get_all_alert_levels') else {}
                all_health = self.webthread_core.hb_subsystem.get_all_component_health() if self.webthread_core.hb_subsystem else {}
                
                for i in range(self.alert_table.rowCount()):
                    comp = self.alert_table.item(i, 0).text()
                    
                    # Alert level
                    alert = alert_levels.get(comp, 'GREEN')
                    alert_item = QTableWidgetItem(alert.upper() if isinstance(alert, str) else str(alert))
                    if alert in ['GREEN', 'green']:
                        alert_item.setForeground(QColor("#00ff00"))
                    elif alert in ['YELLOW', 'yellow']:
                        alert_item.setForeground(QColor("#ffff00"))
                    elif alert in ['ORANGE', 'orange']:
                        alert_item.setForeground(QColor("#ffaa00"))
                    else:  # RED
                        alert_item.setForeground(QColor("#ff4444"))
                    self.alert_table.setItem(i, 1, alert_item)
                    
                    # Health status
                    health_status = all_health.get(comp)
                    if health_status:
                        health = health_status.health.value if hasattr(health_status.health, 'value') else str(health_status.health)
                        health_item = QTableWidgetItem(health.upper())
                        if health in ['HEALTHY', 'healthy', 'OK']:
                            health_item.setForeground(QColor("#00ff00"))
                        elif health in ['DEGRADED', 'degraded']:
                            health_item.setForeground(QColor("#ffaa00"))
                        else:
                            health_item.setForeground(QColor("#ff4444"))
                        self.alert_table.setItem(i, 2, health_item)
            except Exception as e:
                pass  # Silent fail for alert levels
                
        else:
            # HB subsystem not fully initialized, but HB monitoring continues via fallback
            # This is NOT an error - file-based HB monitoring is always active
            self.hb_enabled_label.setText("● HB: ACTIVE (File Monitor)")
            self.hb_enabled_label.setStyleSheet("color: #88ff88; font-weight: bold;")
            
            # Try to enable HB subsystem if not already done
            if hasattr(self.webthread_core, 'enable_hb') and not hb_enabled:
                try:
                    self.webthread_core.enable_hb()
                    logging.info("HB subsystem auto-enabled")
                except Exception as e:
                    logging.debug(f"Could not auto-enable HB: {e}")
    
    def create_connections_widget(self):
        """Create connections status widget"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh Connections")
        refresh_btn.setStyleSheet("padding: 5px 10px;")
        refresh_btn.clicked.connect(self.update_connections)
        layout.addWidget(refresh_btn)
        
        self.conn_table = QTableWidget()
        self.conn_table.setColumnCount(3)
        self.conn_table.setHorizontalHeaderLabels(["Connection", "Status", "Details"])
        self.conn_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        # Initialize connections: 2 main + 6 HB ports
        self.conn_table.setRowCount(8)
        
        # Initialize row labels
        connections = [
            ('ROS2', '?', 'Checking...'),
            ('UE5', '?', 'Checking...'),
            ('HB:FTI (9877)', '●', 'Checking...'),
            ('HB:ROC (9878)', '●', 'Checking...'),
            ('HB:DIMC (9879)', '●', 'Checking...'),
            ('HB:COMC (9880)', '●', 'Checking...'),
            ('HB:ROS2 (9881)', '●', 'Checking...'),
            ('HB:UE5 (9882)', '●', 'Checking...'),
        ]
        for i, (name, status, details) in enumerate(connections):
            self.conn_table.setItem(i, 0, QTableWidgetItem(name))
            self.conn_table.setItem(i, 1, QTableWidgetItem(status))
            self.conn_table.setItem(i, 2, QTableWidgetItem(details))
        
        layout.addWidget(self.conn_table)
        
        # Reconnect button
        reconnect_btn = QPushButton("Reconnect UE5")
        reconnect_btn.clicked.connect(self.reconnect_ue5)
        layout.addWidget(reconnect_btn)
        
        return widget
    
    def create_fti_status_widget(self):
        """Create FTI (File Type Importer) status widget"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Header with refresh button
        header = QHBoxLayout()
        header.addWidget(QLabel("<b>File Type Importer (FTI) Status</b>"))
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setStyleSheet("padding: 5px 10px;")
        refresh_btn.clicked.connect(self.update_fti_status)
        header.addWidget(refresh_btn)
        header.addStretch()
        layout.addLayout(header)
        
        # FTI status grid
        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        
        # FTI Status Labels
        fti_stats = [
            ("HB Status:", "fti_hb_status"),
            ("Alert Level:", "fti_alert"),
            ("Last Heartbeat:", "fti_last_hb"),
            ("Response Time:", "fti_response"),
            ("Error Count:", "fti_errors"),
            ("Import Queue:", "fti_queue"),
            ("Last Import:", "fti_last_import"),
            ("XACRO Status:", "fti_xacro"),
        ]
        
        self.fti_labels = {}
        for i, (label, key) in enumerate(fti_stats):
            lbl = QLabel(label)
            lbl.setStyleSheet("font-weight: bold;")
            grid.addWidget(lbl, i, 0)
            value_label = QLabel("--")
            value_label.setFont(QFont("Arial", 10))
            grid.addWidget(value_label, i, 1)
            self.fti_labels[key] = value_label
        
        layout.addWidget(grid_container)
        
        # Import History section
        layout.addWidget(QLabel("<b>Recent Import History</b>"))
        
        self.fti_history_table = QTableWidget()
        self.fti_history_table.setColumnCount(4)
        self.fti_history_table.setHorizontalHeaderLabels(["Timestamp", "File", "Type", "Status"])
        self.fti_history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.fti_history_table.setRowCount(5)
        layout.addWidget(self.fti_history_table)
        
        # URDF/XACRO section
        urdf_group = QWidget()
        urdf_layout = QHBoxLayout(urdf_group)
        urdf_layout.addWidget(QLabel("<b>URDF/XACRO:</b>"))
        self.fti_urdf_status = QLabel("No active conversion")
        urdf_layout.addWidget(self.fti_urdf_status)
        urdf_layout.addStretch()
        layout.addWidget(urdf_group)
        
        layout.addStretch()
        
        # Start FTI update timer
        self.fti_timer = QTimer()
        self.fti_timer.timeout.connect(self.update_fti_status)
        self.fti_timer.start(2000)  # Update every 2 seconds
        
        # Initial update
        QTimer.singleShot(1000, self.update_fti_status)
        
        return widget
    
    def update_fti_status(self):
        """Update FTI status from HB subsystem with fallback to file-based monitoring
        
        Uses same degradation logic as Main Status Panel:
        - WAITING: Initial state
        - HEALTHY: Recent HB
        - DEGRADED: 3 missed HBs
        - MALFUNCTION: 4+ missed HBs
        """
        import time
        import os
        
        # Initialize FTI tracking if not exists
        if not hasattr(self, '_fti_status_tracking'):
            self._fti_status_tracking = {
                'last_hb': 0,
                'missed_hb_count': 0,
                'ever_connected': False,
                'response_time': 0,
                'errors': 0
            }
        
        current_time = time.time()
        hb_interval = 2.0
        fti_health = None
        
        # Try HB subsystem first
        if self.webthread_core and getattr(self.webthread_core, 'hb_subsystem', None):
            try:
                all_health = self.webthread_core.hb_subsystem.get_all_component_health()
                fti_health = all_health.get('FTI')
            except:
                pass
        
        # Fallback: check heartbeat file
        if not fti_health:
            try:
                with open('/tmp/roa_component_heartbeats.json', 'r') as f:
                    heartbeats = json.load(f)
                fti_data = heartbeats.get('wsl', {}).get('FTI', {})
                if fti_data:
                    # Create a mock health object from file data
                    class MockHealth:
                        pass
                    fti_health = MockHealth()
                    fti_health.last_heartbeat_time = fti_data.get('timestamp', 0)
                    fti_health.health = type('Health', (), {'value': fti_data.get('health', 'UNKNOWN')})()
                    fti_health.avg_response_ms = fti_data.get('response_time', 0)
                    fti_health.error_count = fti_data.get('errors', 0)
            except:
                pass
        
        if fti_health:
            last_hb = getattr(fti_health, 'last_heartbeat_time', 0)
            
            if last_hb and last_hb > 0:
                time_since_hb = current_time - last_hb
                missed_hb = max(0, int(time_since_hb / hb_interval) - 1)
                
                # Update tracking
                self._fti_status_tracking['ever_connected'] = True
                self._fti_status_tracking['last_hb'] = last_hb
                self._fti_status_tracking['missed_hb_count'] = missed_hb
                
                # Calculate status with degradation
                status, color = self._calculate_status_from_missed_hb(missed_hb, True)
                self.fti_labels['fti_hb_status'].setText(status)
                self.fti_labels['fti_hb_status'].setStyleSheet(f"color: {color.name()}; font-weight: bold;")
                
                # Last heartbeat
                self.fti_labels['fti_last_hb'].setText(f"{time_since_hb:.1f}s ago")
            else:
                self.fti_labels['fti_hb_status'].setText("WAITING")
                self.fti_labels['fti_hb_status'].setStyleSheet("color: #888; font-weight: bold;")
                self.fti_labels['fti_last_hb'].setText("Never")
            
            # Alert level
            alert_levels = {}
            if self.webthread_core and hasattr(self.webthread_core, 'get_all_alert_levels'):
                try:
                    alert_levels = self.webthread_core.get_all_alert_levels() or {}
                except:
                    pass
            fti_alert = alert_levels.get('FTI', 'GREEN')
            self.fti_labels['fti_alert'].setText(str(fti_alert).upper())
            if str(fti_alert).upper() == 'GREEN':
                self.fti_labels['fti_alert'].setStyleSheet("color: #00ff00;")
            elif str(fti_alert).upper() == 'YELLOW':
                self.fti_labels['fti_alert'].setStyleSheet("color: #ffff00;")
            elif str(fti_alert).upper() == 'ORANGE':
                self.fti_labels['fti_alert'].setStyleSheet("color: #ffaa00;")
            else:
                self.fti_labels['fti_alert'].setStyleSheet("color: #ff4444;")
            
            # Response time
            resp = getattr(fti_health, 'avg_response_ms', 0) or 0
            self.fti_labels['fti_response'].setText(f"{resp:.1f}ms")
            
            # Error count
            errors = getattr(fti_health, 'error_count', 0) or 0
            self.fti_labels['fti_errors'].setText(str(errors))
            if errors > 0:
                self.fti_labels['fti_errors'].setStyleSheet("color: #ff4444;")
            else:
                self.fti_labels['fti_errors'].setStyleSheet("color: #888;")
                
        else:
            # No FTI data available - check our tracking for degradation
            if self._fti_status_tracking['ever_connected']:
                self._fti_status_tracking['missed_hb_count'] += 1
                status, color = self._calculate_status_from_missed_hb(
                    self._fti_status_tracking['missed_hb_count'], True
                )
                self.fti_labels['fti_hb_status'].setText(status)
                self.fti_labels['fti_hb_status'].setStyleSheet(f"color: {color.name()}; font-weight: bold;")
            else:
                self.fti_labels['fti_hb_status'].setText("WAITING")
                self.fti_labels['fti_hb_status'].setStyleSheet("color: #888; font-weight: bold;")
            
            self.fti_labels['fti_alert'].setText("--")
            self.fti_labels['fti_alert'].setStyleSheet("color: #888;")
            self.fti_labels['fti_last_hb'].setText("--")
            self.fti_labels['fti_response'].setText("--")
            self.fti_labels['fti_errors'].setText("--")
        
        # FTI-specific data - check IPC folder for queue info
        try:
            ipc_folder = "/mnt/d/ROA/.ipc" if os.path.exists("/mnt/d/ROA/.ipc") else os.path.expanduser("~/.roa/ipc")
            requests_folder = os.path.join(ipc_folder, "requests")
            if os.path.exists(requests_folder):
                queue_files = [f for f in os.listdir(requests_folder) if f.endswith('.request.json')]
                self.fti_labels['fti_queue'].setText(f"{len(queue_files)} files")
            else:
                self.fti_labels['fti_queue'].setText("0 files")
        except:
            self.fti_labels['fti_queue'].setText("0 files")
        
        self.fti_labels['fti_last_import'].setText("N/A")
        self.fti_labels['fti_xacro'].setText("Idle")
        self.fti_urdf_status.setText("No active XACRO→URDF conversion")
    
    def create_messages_widget(self):
        """Create UE5 message viewer widget"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Controls
        controls = QHBoxLayout()
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet("padding: 5px 10px;")
        refresh_btn.clicked.connect(self.update_messages)
        controls.addWidget(refresh_btn)
        
        clear_btn = QPushButton("Clear Messages")
        clear_btn.clicked.connect(self.clear_messages)
        controls.addWidget(clear_btn)
        
        copy_btn = QPushButton("Copy All")
        copy_btn.setStyleSheet("background-color: #2a4a6a; color: white; padding: 5px 10px;")
        copy_btn.clicked.connect(lambda: self.copy_to_clipboard(self.messages_text.toPlainText(), "UE5 Messages"))
        controls.addWidget(copy_btn)
        
        test_btn = QPushButton("Test UE5 Connection")
        test_btn.setStyleSheet("background-color: #2a5a2a; color: white; padding: 5px 10px;")
        test_btn.setToolTip("Verify UE5 is connected and bridge is functional")
        test_btn.clicked.connect(self.send_test_message)
        controls.addWidget(test_btn)
        
        self.auto_scroll_enabled = True
        auto_scroll_btn = QPushButton("Auto-Scroll: ON")
        def toggle_auto_scroll():
            self.auto_scroll_enabled = not self.auto_scroll_enabled
            auto_scroll_btn.setText(f"Auto-Scroll: {'ON' if self.auto_scroll_enabled else 'OFF'}")
        auto_scroll_btn.clicked.connect(toggle_auto_scroll)
        controls.addWidget(auto_scroll_btn)
        
        self.msg_count_label = QLabel("Messages: 0")
        controls.addWidget(self.msg_count_label)
        
        controls.addStretch()
        layout.addLayout(controls)
        
        # Message text area
        self.messages_text = QTextEdit()
        self.messages_text.setReadOnly(True)
        self.messages_text.setFont(QFont("Courier", 9))
        self.messages_text.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a2e;
                color: #eee;
                border: 1px solid #333;
            }
        """)
        layout.addWidget(self.messages_text)
        
        # Start message update timer
        self.message_timer = QTimer()
        self.message_timer.timeout.connect(self.update_messages)
        self.message_timer.start(2000)  # Update every 2 seconds (was 500ms - too heavy)
        
        self.last_message_pos = 0
        
        return widget
    
    def create_terminal_widget(self):
        """Create terminal widget with command execution"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Quick action buttons - Row 1: General commands
        quick_actions1 = QHBoxLayout()
        
        actions1 = [
            ("🚀 roa start", "roa start"),
            ("🛑 roa stop", "roa stop"),
            ("📋 ros2 topic list", "ros2 topic list"),
            ("👁️ tail bridge log", "tail -20 /tmp/roa_messages.log"),
            ("🔍 ps bridge", "ps aux | grep -E 'roa_bridge|roa_command' | grep -v grep"),
            ("🌐 netstat ports", "ss -tuln | grep -E '9090|9876'"),
        ]
        
        for label, command in actions1:
            btn = QPushButton(label)
            btn.setStyleSheet("padding: 5px; font-size: 10px;")
            btn.clicked.connect(lambda checked, cmd=command: self.run_terminal_command(cmd))
            quick_actions1.addWidget(btn)
        
        layout.addLayout(quick_actions1)
        
        # Quick action buttons - Row 2: FTI Service commands
        quick_actions2 = QHBoxLayout()
        
        fti_actions = [
            ("📜 FTI Logs (live)", "tail -f /tmp/roa_fti_service.log"),
            ("📋 FTI Logs (last 50)", "tail -50 /tmp/roa_fti_service.log"),
            ("🔍 FTI Status", "cat /mnt/d/ROA/.ipc/service.status 2>/dev/null | python3 -m json.tool || echo 'Service not running'"),
            ("🔄 FTI Restart", "pkill -f roa_ipc_service; sleep 1; python3 /home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python/roa_ipc_service.py --debug >> /tmp/roa_fti_service.log 2>&1 &"),
            ("❌ FTI Stop", "pkill -f roa_ipc_service && echo 'FTI Service stopped' || echo 'FTI Service was not running'"),
            ("🔍 FTI Process", "pgrep -af roa_ipc_service || echo 'FTI Service not running'"),
        ]
        
        for label, command in fti_actions:
            btn = QPushButton(label)
            btn.setStyleSheet("padding: 5px; font-size: 10px; background-color: #2a4a5a;")
            btn.clicked.connect(lambda checked, cmd=command: self.run_terminal_command(cmd))
            quick_actions2.addWidget(btn)
        
        layout.addLayout(quick_actions2)
        
        # Terminal output area
        self.terminal_output = QPlainTextEdit()
        self.terminal_output.setReadOnly(True)
        self.terminal_output.setFont(QFont("Courier", 10))
        self.terminal_output.setStyleSheet("""
            QPlainTextEdit {
                background-color: #0c0c0c;
                color: #00ff00;
                border: 1px solid #333;
            }
        """)
        self.terminal_output.setPlaceholderText("Terminal output will appear here...")
        layout.addWidget(self.terminal_output)
        
        # Command input
        input_layout = QHBoxLayout()
        
        prompt = QLabel("$")
        prompt.setStyleSheet("color: #00ff00; font-weight: bold; font-family: Courier;")
        input_layout.addWidget(prompt)
        
        self.terminal_input = QLineEdit()
        self.terminal_input.setPlaceholderText("Enter command and press Enter...")
        self.terminal_input.setFont(QFont("Courier", 10))
        self.terminal_input.setStyleSheet("""
            QLineEdit {
                background-color: #1a1a1a;
                color: #00ff00;
                border: 1px solid #333;
                padding: 5px;
            }
        """)
        self.terminal_input.returnPressed.connect(self.execute_terminal_command)
        input_layout.addWidget(self.terminal_input)
        
        execute_btn = QPushButton("Execute")
        execute_btn.setStyleSheet("background-color: #2a5a2a; color: white; padding: 5px;")
        execute_btn.clicked.connect(self.execute_terminal_command)
        input_layout.addWidget(execute_btn)
        
        refresh_btn = QPushButton("🔄")
        refresh_btn.setToolTip("Refresh status")
        refresh_btn.clicked.connect(self.update_bridge_status)
        input_layout.addWidget(refresh_btn)
        
        copy_term_btn = QPushButton("Copy All")
        copy_term_btn.setStyleSheet("background-color: #2a4a6a; color: white;")
        copy_term_btn.clicked.connect(lambda: self.copy_to_clipboard(self.terminal_output.toPlainText(), "Terminal"))
        input_layout.addWidget(copy_term_btn)
        
        clear_term_btn = QPushButton("Clear")
        clear_term_btn.clicked.connect(lambda: self.terminal_output.clear())
        input_layout.addWidget(clear_term_btn)
        
        layout.addLayout(input_layout)
        
        # Initialize QProcess for command execution
        self.terminal_process = QProcess()
        self.terminal_process.readyReadStandardOutput.connect(self.handle_terminal_output)
        self.terminal_process.readyReadStandardError.connect(self.handle_terminal_error)
        self.terminal_process.finished.connect(self.handle_terminal_finished)
        
        # Command history
        self.command_history = []
        self.history_index = -1
        
        # Setup up/down arrow navigation for command history
        self.terminal_input.keyPressEvent = self.terminal_key_handler
        
        return widget
    
    def terminal_key_handler(self, event):
        """Handle up/down arrow keys for command history"""
        from PyQt6.QtCore import Qt
        
        if event.key() == Qt.Key.Key_Up:
            if self.command_history and self.history_index < len(self.command_history) - 1:
                self.history_index += 1
                self.terminal_input.setText(self.command_history[-(self.history_index + 1)])
        elif event.key() == Qt.Key.Key_Down:
            if self.history_index > 0:
                self.history_index -= 1
                self.terminal_input.setText(self.command_history[-(self.history_index + 1)])
            elif self.history_index == 0:
                self.history_index = -1
                self.terminal_input.clear()
        else:
            # Call the original key handler for other keys
            QLineEdit.keyPressEvent(self.terminal_input, event)
    
    def run_terminal_command(self, command):
        """Run a terminal command (from quick action buttons)"""
        self.terminal_input.setText(command)
        self.execute_terminal_command()
    
    def execute_terminal_command(self):
        """Execute the command in the terminal input"""
        command = self.terminal_input.text().strip()
        if not command:
            return
        
        # Add to history
        if not self.command_history or self.command_history[-1] != command:
            self.command_history.append(command)
        self.history_index = -1
        
        # Display command
        self.append_terminal_output(f"$ {command}\n", "#00aaff")
        
        # Clear input
        self.terminal_input.clear()
        
        # Execute command in bash
        if self.terminal_process.state() == QProcess.ProcessState.Running:
            self.append_terminal_output("⚠️  Previous command still running...\n", "#ffaa00")
            return
        
        # Use bash -c to execute command
        self.terminal_process.start("bash", ["-c", command])
    
    def handle_terminal_output(self):
        """Handle standard output from terminal process"""
        output = self.terminal_process.readAllStandardOutput().data().decode('utf-8', errors='replace')
        self.append_terminal_output(output, "#00ff00")
    
    def handle_terminal_error(self):
        """Handle standard error from terminal process"""
        error = self.terminal_process.readAllStandardError().data().decode('utf-8', errors='replace')
        self.append_terminal_output(error, "#ff6666")
    
    def handle_terminal_finished(self, exit_code, exit_status):
        """Handle terminal process completion"""
        if exit_code != 0:
            self.append_terminal_output(f"\n[Process exited with code {exit_code}]\n", "#ffaa00")
        else:
            self.append_terminal_output("\n", "#00ff00")
    
    def append_terminal_output(self, text, color="#00ff00"):
        """Append text to terminal output with color"""
        cursor = self.terminal_output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # Set text color
        format = cursor.charFormat()
        format.setForeground(QColor(color))
        cursor.setCharFormat(format)
        
        cursor.insertText(text)
        self.terminal_output.setTextCursor(cursor)
        self.terminal_output.ensureCursorVisible()
    
    def update_messages(self):
        """Update message viewer from log file"""
        import subprocess
        try:
            msg_file = '/tmp/roa_messages.log'
            # Read new messages since last check
            result = subprocess.run(
                ['tail', '-n', '50', msg_file],  # Reduced from 100 to 50
                capture_output=True, text=True, timeout=1
            )
            if result.returncode == 0 and result.stdout:
                messages = result.stdout.strip()
                
                # Only update if content changed (avoid unnecessary redraws)
                if hasattr(self, '_last_messages') and self._last_messages == messages:
                    return
                self._last_messages = messages
                
                if messages:
                    # Color code messages
                    formatted = []
                    for line in messages.split('\n'):
                        # Escape HTML
                        line = line.replace('<', '&lt;').replace('>', '&gt;')
                        if 'FROM UE5' in line or 'FROM SERVER' in line or 'TEST <-' in line:
                            formatted.append(f'<span style="color: #00ff00;">{line}</span>')
                        elif 'TO UE5' in line or 'TO ROS2' in line or 'TO SERVER' in line or 'TEST ->' in line:
                            formatted.append(f'<span style="color: #00bfff;">{line}</span>')
                        elif 'ERROR' in line.upper():
                            formatted.append(f'<span style="color: #ff4444;">{line}</span>')
                        else:
                            formatted.append(f'<span style="color: #cccccc;">{line}</span>')
                    
                    # Update count
                    count = len(formatted)
                    self.msg_count_label.setText(f"Messages: {count}")
                    
                    # Only update if changed
                    new_html = '<br>'.join(formatted)
                    self.messages_text.setHtml(new_html)
                    if self.auto_scroll_enabled:
                        scrollbar = self.messages_text.verticalScrollBar()
                        scrollbar.setValue(scrollbar.maximum())
            else:
                # No messages yet - show placeholder
                self.msg_count_label.setText("Messages: 0")
                if not hasattr(self, '_msg_placeholder_shown'):
                    self.messages_text.setHtml('<span style="color: #666;">Waiting for messages from UE5...<br>Make sure UE5 is connected and sending data.</span>')
                    self._msg_placeholder_shown = True
        except Exception as e:
            self.msg_count_label.setText("Messages: 0")
            self.messages_text.setHtml(f'<span style="color: red;">Error reading messages: {e}</span>')
    
    def copy_to_clipboard(self, text, source_name=""):
        """Copy text to clipboard and show confirmation"""
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        
        if source_name:
            self.add_log(f"Copied {source_name} to clipboard ({len(text)} characters)")
        self.status_bar.showMessage(f"Copied to clipboard!", 3000)
    
    def copy_all_logs(self):
        """Copy all logs, messages, and terminal output"""
        from PyQt6.QtWidgets import QApplication
        from datetime import datetime
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        output = []
        output.append(f"=== ROA System Report - {timestamp} ===\n")
        
        # System Logs
        output.append("\n--- SYSTEM LOGS ---\n")
        output.append(self.log_text.toPlainText() or "(empty)")
        
        # UE5 Messages
        output.append("\n\n--- UE5 MESSAGES ---\n")
        output.append(self.messages_text.toPlainText() or "(empty)")
        
        # Terminal Output
        output.append("\n\n--- TERMINAL OUTPUT ---\n")
        output.append(self.terminal_output.toPlainText() or "(empty)")
        
        output.append("\n\n=== END OF REPORT ===")
        
        full_text = '\n'.join(output)
        clipboard = QApplication.clipboard()
        clipboard.setText(full_text)
        
        self.add_log(f"Copied complete system report to clipboard ({len(full_text)} characters)")
        self.status_bar.showMessage("Complete system report copied to clipboard!", 3000)
    
    def start_monitoring(self):
        """Start the monitoring thread"""
        if self.webthread_core and not self.monitor_thread:
            self.monitor_thread = MonitorThread(self.webthread_core)
            self.monitor_thread.status_updated.connect(self.update_status)
            self.monitor_thread.start()
            
            # Update timer for UI
            self.ui_timer = QTimer()
            self.ui_timer.timeout.connect(self.update_ui)
            self.ui_timer.start(1000)  # Update every second
        
        # Bridge status timer
        self.bridge_timer = QTimer()
        self.bridge_timer.timeout.connect(self.update_bridge_status)
        self.bridge_timer.start(5000)  # Update every 5 seconds (was 2s - too many subprocess calls)
        self.update_bridge_status()  # Initial check
        
        # Heartbeat file writer timer (for fallback when HB subsystem writes data)
        self.hb_file_timer = QTimer()
        self.hb_file_timer.timeout.connect(self.write_heartbeat_file)
        self.hb_file_timer.start(2000)  # Write every 2 seconds
    
    def write_heartbeat_file(self):
        """Write heartbeat data to file for fallback/external monitoring"""
        if not self.webthread_core:
            return
        
        try:
            import time
            heartbeats = {'wsl': {}, 'plugin': {}, 'timestamp': time.time()}
            
            # Get WSL component data from HB subsystem
            if hasattr(self.webthread_core, 'hb_subsystem') and self.webthread_core.hb_subsystem:
                hb = self.webthread_core.hb_subsystem
                all_health = hb.get_all_component_health()
                
                for name, status in all_health.items():
                    if status:
                        heartbeats['wsl'][name] = {
                            'timestamp': status.last_heartbeat_time if hasattr(status, 'last_heartbeat_time') else time.time(),
                            'health': status.health.value if hasattr(status.health, 'value') else str(status.health),
                            'response_time': status.response_time_avg_ms if hasattr(status, 'response_time_avg_ms') else 0,
                            'errors': status.error_count if hasattr(status, 'error_count') else 0,
                        }
            
            # Write to file
            with open('/tmp/roa_component_heartbeats.json', 'w') as f:
                json.dump(heartbeats, f)
                
        except Exception as e:
            logging.debug(f"Error writing heartbeat file: {e}")
    
    def clear_messages(self):
        """Clear message log file and display"""
        import subprocess
        try:
            # Clear the log file
            with open('/tmp/roa_messages.log', 'w') as f:
                f.write('')
            self.messages_text.clear()
            self.msg_count_label.setText("Messages: 0")
            self._msg_placeholder_shown = False
            self.add_log("Message log cleared")
        except Exception as e:
            self.add_log(f"Failed to clear messages: {e}", "ERROR")
    
    def send_test_message(self):
        """Test if UE5 is actually connected and functional"""
        try:
            self._run_connection_test()
        except Exception as e:
            self._add_test_result(f"❌ ERROR: Test button failed - {e}")
            self._add_test_result(f"   Exception type: {type(e).__name__}")
            import traceback
            self._add_test_result(f"   {traceback.format_exc()}")
            self._add_test_result("❌ UE5 is OFFLINE or OUT OF REACH (test error)")
    
    def _add_test_result(self, message, is_error=False):
        """Add test result to BOTH System Logs and UE5 Messages tab"""
        # Add to System Logs
        self.add_log(message, "ERROR" if is_error else "INFO")
        
        # Also add to UE5 Messages text area directly so user sees it immediately
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = "#ff4444" if is_error or "❌" in message or "ERROR" in message else "#00ff00" if "✅" in message else "#00bfff"
        html_line = f'<span style="color: {color};">[{timestamp}] {message}</span><br>'
        
        # Append to existing content
        current = self.messages_text.toHtml()
        if "Waiting for messages" in current:
            self.messages_text.setHtml(html_line)
        else:
            self.messages_text.append(f'<span style="color: {color};">[{timestamp}] {message}</span>')
        
        # Scroll to bottom
        if self.auto_scroll_enabled:
            scrollbar = self.messages_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
    
    def _run_connection_test(self):
        """Internal test implementation"""
        import subprocess
        from datetime import datetime
        
        self._add_test_result("=== Testing UE5 Bridge Connection ===")
        
        has_connection = True  # Track overall test status
        
        # Test 1: Check if servers are running
        rosbridge_running = subprocess.run(['pgrep', '-f', 'roa_bridge_server.py'], 
                                          capture_output=True).returncode == 0
        command_running = subprocess.run(['pgrep', '-f', 'roa_command_server.py'], 
                                        capture_output=True).returncode == 0
        
        if not rosbridge_running or not command_running:
            self._add_test_result("❌ FAIL: Bridge servers not running", True)
            self._add_test_result("   Run 'roa start' to start servers", True)
            self._add_test_result("❌ UE5 is OFFLINE or OUT OF REACH (servers not started)", True)
            return
        
        self._add_test_result("✅ Bridge servers are running")
        
        # Test 2: Check for active UE5 connection
        try:
            result = subprocess.run(['ss', '-tn'], capture_output=True, text=True, timeout=2)
            has_connection = ':9876' in result.stdout and 'ESTAB' in result.stdout
            
            if not has_connection:
                self._add_test_result("❌ FAIL: No active UE5 connection detected", True)
                self._add_test_result("   UE5 must be running with ROA plugin loaded", True)
                self._add_test_result("❌ UE5 is OFFLINE or OUT OF REACH (not connected to port 9876)", True)
                return
            
            self._add_test_result("✅ UE5 connection detected (port 9876 ESTABLISHED)")
        except subprocess.TimeoutExpired:
            self._add_test_result("❌ ERROR: Network check timed out", True)
            self._add_test_result("   System may be overloaded", True)
            return
        except Exception as e:
            self._add_test_result(f"❌ ERROR: Connection check failed - {e}", True)
            return
        
        # Test 3: Check for recent UE5 messages
        try:
            with open('/tmp/roa_messages.log', 'r') as f:
                lines = f.readlines()
                
            # Look for non-TEST messages from last 30 seconds
            recent_ue5_messages = []
            now = datetime.now()
            
            for line in lines[-50:]:  # Check last 50 lines
                if 'FROM UE5' in line and 'TEST' not in line:
                    recent_ue5_messages.append(line.strip())
            
            if recent_ue5_messages:
                self._add_test_result(f"✅ UE5 is sending messages ({len(recent_ue5_messages)} recent)")
                self._add_test_result(f"   Last: {recent_ue5_messages[-1][:80]}...")
            else:
                self._add_test_result("❌ ERROR: No UE5 messages detected", True)
                self._add_test_result("   UE5 is connected but NOT sending data", True)
                has_connection = False  # Mark as failed
        except FileNotFoundError:
            self._add_test_result("❌ ERROR: Message log file not found", True)
            self._add_test_result("   Bridge servers may not be logging properly", True)
        except Exception as e:
            self._add_test_result(f"❌ ERROR: Cannot read message log - {e}", True)
        
        # Test 4: Check ROS2 topics (if UE5 is publishing) - skip slow ros2 topic list
        self._add_test_result("⏭️  Skipping ROS2 topic check (performance)")
        
        self._add_test_result("=== Test Complete ===")
        self._add_test_result("🎉 UE5 Bridge is FUNCTIONAL" if has_connection else "❌ UE5 Bridge NOT functional", not has_connection)

    def update_status(self, status):
        """Update display with new status"""
        if not status:
            return
        
        # Update statistics
        for key, label in self.stat_labels.items():
            if key in status:
                label.setText(str(status[key]))
        
        # Update uptime
        uptime = int(status.get('uptime', 0))
        hours = uptime // 3600
        minutes = (uptime % 3600) // 60
        seconds = uptime % 60
        self.uptime_label.setText(f"Uptime: {hours:02d}:{minutes:02d}:{seconds:02d}")
        
        # Update connections table
        self.update_connections()
        
        # Update component table
        components = status.get('components', {})
        self.component_table.setRowCount(len(components))
        
        for i, (name, comp_status) in enumerate(components.items()):
            self.component_table.setItem(i, 0, QTableWidgetItem(name))
            
            # Status with color
            status_text = comp_status.get('status', 'unknown')
            status_item = QTableWidgetItem(status_text.upper())
            
            if status_text == 'healthy':
                status_item.setForeground(QColor("green"))
            elif status_text == 'degraded':
                status_item.setForeground(QColor("orange"))
            elif status_text == 'failed':
                status_item.setForeground(QColor("red"))
            
            self.component_table.setItem(i, 1, status_item)
            
            # Other fields
            self.component_table.setItem(i, 2, QTableWidgetItem(
                f"{comp_status.get('response_time', 0):.2f}"
            ))
            self.component_table.setItem(i, 3, QTableWidgetItem(
                str(comp_status.get('error_count', 0))
            ))
            self.component_table.setItem(i, 4, QTableWidgetItem(
                datetime.now().strftime("%H:%M:%S")
            ))
    
    def check_component_heartbeats(self):
        """Check heartbeats from WSL and Plugin components - uses HB subsystem when available
        
        Status degradation logic:
        - WAITING: Initial state, never received HB
        - HEALTHY: Received HB within timeout
        - DEGRADED: Missed 2-3 HBs (warning state)
        - MALFUNCTION: Missed 4+ HBs (failed state)
        """
        import time
        import subprocess
        
        current_time = time.time()
        hb_interval = 2.0  # Expected HB every 2 seconds
        
        # Check if HB subsystem is active
        hb_active = (self.webthread_core and 
                     getattr(self.webthread_core, '_hb_enabled', False) and
                     getattr(self.webthread_core, 'hb_subsystem', None))
        
        if hb_active:
            # Use HB Subsystem for WSL component status
            self._update_components_from_hb_with_degradation(current_time, hb_interval)
        else:
            # Fallback: Read heartbeat file with degradation tracking
            self._update_components_from_file_with_degradation(current_time, hb_interval)
        
        # Update Plugin components (always from file - they're on Windows/UE5)
        self._update_plugin_components_with_degradation(current_time, hb_interval)
        
        # Update connections table
        try:
            self.update_connections()
        except Exception as e:
            logging.debug(f"Error updating connections: {e}")
    
    def _calculate_status_from_missed_hb(self, missed_count: int, ever_connected: bool) -> tuple:
        """Calculate status and color based on missed heartbeat count
        
        Returns: (status_text, QColor)
        """
        if not ever_connected:
            return ("WAITING", QColor("#888888"))
        elif missed_count == 0:
            return ("HEALTHY", QColor("#00ff00"))
        elif missed_count <= 2:
            return ("HEALTHY", QColor("#88ff88"))  # Slight concern but still healthy
        elif missed_count == 3:
            return ("DEGRADED", QColor("#ffaa00"))  # Warning - degraded
        else:  # missed_count >= 4
            return ("MALFUNCTION", QColor("#ff4444"))  # Failed
    
    def _update_components_from_hb_with_degradation(self, current_time: float, hb_interval: float):
        """Update WSL component table from HB subsystem with degradation logic"""
        try:
            hb = self.webthread_core.hb_subsystem
            
            for i in range(self.component_table.rowCount()):
                comp_name = self.component_table.item(i, 0).text()
                
                # Get health from HB subsystem
                health = self.webthread_core.get_component_health_detailed(comp_name) if hasattr(self.webthread_core, 'get_component_health_detailed') else None
                
                if health:
                    last_hb = health.get('last_heartbeat_time', health.get('last_activity_time', 0))
                    
                    if last_hb > 0:
                        # Calculate missed HBs based on time since last HB
                        time_since_hb = current_time - last_hb
                        missed_hb = max(0, int(time_since_hb / hb_interval) - 1)
                        
                        # Update tracking
                        if comp_name in self.wsl_component_status:
                            self.wsl_component_status[comp_name]['ever_connected'] = True
                            self.wsl_component_status[comp_name]['last_hb'] = last_hb
                            self.wsl_component_status[comp_name]['missed_hb_count'] = missed_hb
                            self.wsl_component_status[comp_name]['response_time'] = health.get('response_time_avg_ms', 0)
                            self.wsl_component_status[comp_name]['errors'] = health.get('error_count', 0)
                        
                        status, color = self._calculate_status_from_missed_hb(missed_hb, True)
                    else:
                        status, color = "WAITING", QColor("#888888")
                    
                    status_item = QTableWidgetItem(status)
                    status_item.setForeground(color)
                    self.component_table.setItem(i, 1, status_item)
                    
                    # Response time from HB
                    resp_time = health.get('response_time_avg_ms', health.get('response_time', 0))
                    self.component_table.setItem(i, 2, QTableWidgetItem(f"{resp_time:.2f}"))
                    
                    # Error count
                    self.component_table.setItem(i, 3, QTableWidgetItem(str(health.get('error_count', 0))))
                    
                    # Last HB time
                    if last_hb:
                        try:
                            self.component_table.setItem(i, 4, QTableWidgetItem(
                                datetime.fromtimestamp(last_hb).strftime("%H:%M:%S")
                            ))
                        except:
                            self.component_table.setItem(i, 4, QTableWidgetItem("--"))
                    else:
                        self.component_table.setItem(i, 4, QTableWidgetItem("--"))
                else:
                    # No HB data - check our tracking for degradation
                    if comp_name in self.wsl_component_status:
                        tracking = self.wsl_component_status[comp_name]
                        if tracking['ever_connected']:
                            # Increment missed HB
                            tracking['missed_hb_count'] += 1
                            status, color = self._calculate_status_from_missed_hb(
                                tracking['missed_hb_count'], True
                            )
                        else:
                            status, color = "WAITING", QColor("#888888")
                    else:
                        status, color = "WAITING", QColor("#888888")
                    
                    status_item = QTableWidgetItem(status)
                    status_item.setForeground(color)
                    self.component_table.setItem(i, 1, status_item)
                    self.component_table.setItem(i, 4, QTableWidgetItem("--"))
        except Exception as e:
            logging.debug(f"Error updating from HB with degradation: {e}")
    
    def _update_components_from_file_with_degradation(self, current_time: float, hb_interval: float):
        """Update WSL component table from heartbeat file with degradation logic"""
        try:
            with open('/tmp/roa_component_heartbeats.json', 'r') as f:
                heartbeats = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            heartbeats = {'wsl': {}, 'plugin': {}}
        
        for i in range(self.component_table.rowCount()):
            comp_name = self.component_table.item(i, 0).text()
            
            if comp_name in heartbeats.get('wsl', {}):
                hb_data = heartbeats['wsl'][comp_name]
                last_hb = hb_data.get('timestamp', 0)
                
                if last_hb > 0:
                    time_since_hb = current_time - last_hb
                    missed_hb = max(0, int(time_since_hb / hb_interval) - 1)
                    
                    # Update tracking
                    if comp_name in self.wsl_component_status:
                        self.wsl_component_status[comp_name]['ever_connected'] = True
                        self.wsl_component_status[comp_name]['last_hb'] = last_hb
                        self.wsl_component_status[comp_name]['missed_hb_count'] = missed_hb
                        self.wsl_component_status[comp_name]['response_time'] = hb_data.get('response_time', 0)
                        self.wsl_component_status[comp_name]['errors'] = hb_data.get('errors', 0)
                    
                    status, color = self._calculate_status_from_missed_hb(missed_hb, True)
                    
                    status_item = QTableWidgetItem(status)
                    status_item.setForeground(color)
                    self.component_table.setItem(i, 1, status_item)
                    self.component_table.setItem(i, 2, QTableWidgetItem(f"{hb_data.get('response_time', 0):.2f}"))
                    self.component_table.setItem(i, 3, QTableWidgetItem(str(hb_data.get('errors', 0))))
                    self.component_table.setItem(i, 4, QTableWidgetItem(
                        datetime.fromtimestamp(last_hb).strftime("%H:%M:%S")
                    ))
                else:
                    status_item = QTableWidgetItem("WAITING")
                    status_item.setForeground(QColor("#888888"))
                    self.component_table.setItem(i, 1, status_item)
                    self.component_table.setItem(i, 4, QTableWidgetItem("--"))
            else:
                # No data - check tracking
                if comp_name in self.wsl_component_status:
                    tracking = self.wsl_component_status[comp_name]
                    if tracking['ever_connected']:
                        tracking['missed_hb_count'] += 1
                        status, color = self._calculate_status_from_missed_hb(
                            tracking['missed_hb_count'], True
                        )
                    else:
                        status, color = "WAITING", QColor("#888888")
                else:
                    status, color = "WAITING", QColor("#888888")
                
                status_item = QTableWidgetItem(status)
                status_item.setForeground(color)
                self.component_table.setItem(i, 1, status_item)
                self.component_table.setItem(i, 4, QTableWidgetItem("--"))
    
    def _update_plugin_components_with_degradation(self, current_time: float, hb_interval: float):
        """Update Plugin component table (UE5/Windows side) with degradation logic"""
        try:
            with open('/tmp/roa_component_heartbeats.json', 'r') as f:
                heartbeats = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            heartbeats = {'wsl': {}, 'plugin': {}}
        
        for i in range(self.plugin_component_table.rowCount()):
            comp_name = self.plugin_component_table.item(i, 0).text()
            
            if comp_name in heartbeats.get('plugin', {}):
                hb_data = heartbeats['plugin'][comp_name]
                last_hb = hb_data.get('timestamp', 0)
                
                if last_hb > 0:
                    time_since_hb = current_time - last_hb
                    missed_hb = max(0, int(time_since_hb / hb_interval) - 1)
                    
                    # Update tracking
                    if comp_name in self.plugin_component_status:
                        self.plugin_component_status[comp_name]['ever_connected'] = True
                        self.plugin_component_status[comp_name]['last_hb'] = last_hb
                        self.plugin_component_status[comp_name]['missed_hb_count'] = missed_hb
                    
                    status, color = self._calculate_status_from_missed_hb(missed_hb, True)
                    
                    status_item = QTableWidgetItem(status)
                    status_item.setForeground(color)
                    self.plugin_component_table.setItem(i, 1, status_item)
                    self.plugin_component_table.setItem(i, 2, QTableWidgetItem(f"{hb_data.get('response_time', 0):.2f}"))
                    self.plugin_component_table.setItem(i, 3, QTableWidgetItem(str(hb_data.get('errors', 0))))
                    self.plugin_component_table.setItem(i, 4, QTableWidgetItem(
                        datetime.fromtimestamp(last_hb).strftime("%H:%M:%S")
                    ))
                else:
                    status_item = QTableWidgetItem("WAITING")
                    status_item.setForeground(QColor("#666666"))
                    self.plugin_component_table.setItem(i, 1, status_item)
                    self.plugin_component_table.setItem(i, 4, QTableWidgetItem("--"))
            else:
                # No data - check tracking
                if comp_name in self.plugin_component_status:
                    tracking = self.plugin_component_status[comp_name]
                    if tracking['ever_connected']:
                        tracking['missed_hb_count'] += 1
                        status, color = self._calculate_status_from_missed_hb(
                            tracking['missed_hb_count'], True
                        )
                    else:
                        status, color = "WAITING", QColor("#666666")
                else:
                    status, color = "WAITING", QColor("#666666")
                
                status_item = QTableWidgetItem(status)
                status_item.setForeground(color)
                self.plugin_component_table.setItem(i, 1, status_item)
                self.plugin_component_table.setItem(i, 4, QTableWidgetItem("--"))
    
    def _update_components_from_hb(self):
        """Update WSL component table from HB subsystem"""
        try:
            hb = self.webthread_core.hb_subsystem
            
            for i in range(self.component_table.rowCount()):
                comp_name = self.component_table.item(i, 0).text()
                
                # Get health from HB subsystem
                health = self.webthread_core.get_component_health_detailed(comp_name) if hasattr(self.webthread_core, 'get_component_health_detailed') else None
                
                if health:
                    # Map HB health level to display
                    hb_health = health.get('health', 'UNKNOWN')
                    if hb_health in ['HEALTHY', 'healthy']:
                        status = "HEALTHY"
                        color = QColor("#00ff00")
                    elif hb_health in ['DEGRADED', 'degraded']:
                        status = "DEGRADED"
                        color = QColor("#ffaa00")
                    elif hb_health in ['CRITICAL', 'FAILED', 'critical', 'failed']:
                        status = "FAILED"
                        color = QColor("#ff4444")
                    else:
                        status = hb_health.upper() if isinstance(hb_health, str) else "UNKNOWN"
                        color = QColor("#888888")
                    
                    status_item = QTableWidgetItem(status)
                    status_item.setForeground(color)
                    self.component_table.setItem(i, 1, status_item)
                    
                    # Response time from HB
                    resp_time = health.get('response_time_avg_ms', health.get('response_time', 0))
                    self.component_table.setItem(i, 2, QTableWidgetItem(f"{resp_time:.2f}"))
                    
                    # Error count
                    self.component_table.setItem(i, 3, QTableWidgetItem(str(health.get('error_count', 0))))
                    
                    # Last HB time
                    last_hb = health.get('last_heartbeat_time', health.get('last_activity_time', 0))
                    if last_hb:
                        try:
                            self.component_table.setItem(i, 4, QTableWidgetItem(
                                datetime.fromtimestamp(last_hb).strftime("%H:%M:%S")
                            ))
                        except:
                            self.component_table.setItem(i, 4, QTableWidgetItem("--"))
                    else:
                        self.component_table.setItem(i, 4, QTableWidgetItem("--"))
                else:
                    # No HB data for this component
                    status_item = QTableWidgetItem("NO HB")
                    status_item.setForeground(QColor("#666666"))
                    self.component_table.setItem(i, 1, status_item)
                    self.component_table.setItem(i, 4, QTableWidgetItem("--"))
        except Exception as e:
            logging.debug(f"Error updating from HB: {e}")
    
    def _update_components_from_file(self):
        """Update WSL component table from heartbeat file (fallback)"""
        import time
        current_time = time.time()
        heartbeat_timeout = 5.0
        
        try:
            with open('/tmp/roa_component_heartbeats.json', 'r') as f:
                heartbeats = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            heartbeats = {'wsl': {}, 'plugin': {}}
        
        for i in range(self.component_table.rowCount()):
            comp_name = self.component_table.item(i, 0).text()
            
            if comp_name in heartbeats.get('wsl', {}):
                hb_data = heartbeats['wsl'][comp_name]
                last_hb = hb_data.get('timestamp', 0)
                age = current_time - last_hb
                
                if age < heartbeat_timeout:
                    status = "HEALTHY"
                    color = QColor("#00ff00")
                    response_time = hb_data.get('response_time', 0)
                elif age < heartbeat_timeout * 2:
                    status = "DEGRADED"
                    color = QColor("#ffaa00")
                    response_time = hb_data.get('response_time', 0)
                else:
                    status = "OFFLINE"
                    color = QColor("#ff4444")
                    response_time = 0
                
                status_item = QTableWidgetItem(status)
                status_item.setForeground(color)
                self.component_table.setItem(i, 1, status_item)
                self.component_table.setItem(i, 2, QTableWidgetItem(f"{response_time:.2f}"))
                self.component_table.setItem(i, 3, QTableWidgetItem(str(hb_data.get('errors', 0))))
                # Last HB time
                if last_hb:
                    self.component_table.setItem(i, 4, QTableWidgetItem(
                        datetime.fromtimestamp(last_hb).strftime("%H:%M:%S")
                    ))
                else:
                    self.component_table.setItem(i, 4, QTableWidgetItem("--"))
            else:
                status_item = QTableWidgetItem("UNKNOWN")
                status_item.setForeground(QColor("#888888"))
                self.component_table.setItem(i, 1, status_item)
                self.component_table.setItem(i, 4, QTableWidgetItem("--"))
    
    def _update_plugin_components(self):
        """Update Plugin component table (UE5/Windows side)"""
        import time
        current_time = time.time()
        heartbeat_timeout = 5.0
        
        try:
            with open('/tmp/roa_component_heartbeats.json', 'r') as f:
                heartbeats = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            heartbeats = {'wsl': {}, 'plugin': {}}
        
        # Update Plugin components
        for i in range(self.plugin_component_table.rowCount()):
            comp_name = self.plugin_component_table.item(i, 0).text()
            
            if comp_name in heartbeats.get('plugin', {}):
                hb_data = heartbeats['plugin'][comp_name]
                last_hb = hb_data.get('timestamp', 0)
                age = current_time - last_hb
                
                if age < heartbeat_timeout:
                    status = "HEALTHY"
                    color = QColor("#00ff00")
                    response_time = hb_data.get('response_time', 0)
                elif age < heartbeat_timeout * 2:
                    status = "DEGRADED"
                    color = QColor("#ffaa00")
                    response_time = hb_data.get('response_time', 0)
                else:
                    status = "OFFLINE"
                    color = QColor("#ff4444")
                    response_time = 0
                
                status_item = QTableWidgetItem(status)
                status_item.setForeground(color)
                self.plugin_component_table.setItem(i, 1, status_item)
                self.plugin_component_table.setItem(i, 2, QTableWidgetItem(f"{response_time:.2f}"))
                self.plugin_component_table.setItem(i, 3, QTableWidgetItem(str(hb_data.get('errors', 0))))
                # Last HB time
                if last_hb:
                    self.plugin_component_table.setItem(i, 4, QTableWidgetItem(
                        datetime.fromtimestamp(last_hb).strftime("%H:%M:%S")
                    ))
                else:
                    self.plugin_component_table.setItem(i, 4, QTableWidgetItem("--"))
            else:
                # No heartbeat - check if UE5 is connected
                ue5_connected = getattr(self, '_ue5_connected_cache', False)
                if ue5_connected:
                    status_item = QTableWidgetItem("WAITING")
                    status_item.setForeground(QColor("#888888"))
                else:
                    status_item = QTableWidgetItem("DISCONNECTED")
                    status_item.setForeground(QColor("#555555"))
                self.plugin_component_table.setItem(i, 1, status_item)
                self.plugin_component_table.setItem(i, 4, QTableWidgetItem("--"))
    
    def update_ue5_status(self):
        """Update UE5 connection status indicator (deprecated - removed from UI)"""
        # This function is kept for compatibility but does nothing
        # The UE5 connector UI was removed in favor of bridge server status
        pass
    
    def update_connections(self):
        """Update connections table"""
        import subprocess
        import socket
        
        # Check ROS2 connection - use fast process check
        ros2_connected = getattr(self, '_ros2_connected_cache', False)
        ros2_details = getattr(self, '_ros2_details_cache', "Not checked")
        
        # Only check ROS2 every 10 seconds (ros2 commands can be slow)
        import time
        last_ros2_check = getattr(self, '_last_ros2_check', 0)
        if time.time() - last_ros2_check > 10:
            try:
                # Method 1: Check for ros2 daemon process (use -E for extended regex)
                result = subprocess.run(['pgrep', '-E', '-f', 'ros2.daemon|_ros2_daemon'], 
                                       capture_output=True, timeout=2)
                ros2_connected = result.returncode == 0
                
                if not ros2_connected:
                    # Method 2: Check for any ros2 related processes
                    result = subprocess.run(['bash', '-c', 'pgrep -f "ros2" 2>/dev/null | head -1'],
                                           capture_output=True, text=True, timeout=2)
                    ros2_connected = result.returncode == 0 and result.stdout.strip() != ""
                
                if ros2_connected:
                    # Get topic count for more details
                    try:
                        result = subprocess.run(['ros2', 'topic', 'list'], 
                                               capture_output=True, text=True, timeout=3)
                        if result.returncode == 0:
                            topics = result.stdout.strip().split('\n')
                            topic_count = len([t for t in topics if t.strip()])
                            ros2_details = f"Running ({topic_count} topics)"
                        else:
                            ros2_details = "Running (processes found)"
                    except:
                        ros2_details = "Running (processes found)"
                else:
                    ros2_details = "Not running"
                
                self._ros2_connected_cache = ros2_connected
                self._ros2_details_cache = ros2_details
                self._last_ros2_check = time.time()
            except subprocess.TimeoutExpired:
                ros2_details = "Check timed out"
            except Exception as e:
                ros2_details = f"Error: {str(e)[:30]}"
        
        ros2_status = "Connected" if ros2_connected else "Not Connected"
        
        # Check UE5 connection - verify actual client connection to command server
        ue5_connected = False
        ue5_details = "172.27.64.1:9876"
        try:
            # Check if command server has active connections
            result = subprocess.run(['ss', '-tn'], capture_output=True, text=True, timeout=1)
            # Look for ESTABLISHED connection to port 9876
            ue5_connected = ':9876' in result.stdout and 'ESTAB' in result.stdout
            if ue5_connected:
                ue5_details = "Connected to command server"
            else:
                ue5_details = "No active connection to port 9876"
        except:
            pass
        
        ue5_status = "Connected" if ue5_connected else "Not Connected"
        
        connections = [
            ("ROS2", ros2_status, ros2_details, ros2_connected),
            ("UE5", ue5_status, ue5_details, ue5_connected),
        ]
        
        for i, (name, status, details, is_connected) in enumerate(connections):
            self.conn_table.setItem(i, 0, QTableWidgetItem(name))
            
            # Create status item with larger symbol
            status_item = QTableWidgetItem("●")
            status_item.setFont(QFont("Arial", 16))
            if is_connected:
                status_item.setForeground(QColor("#00ff00"))  # Bright green
                status_item.setBackground(QColor("#003300"))  # Dark green background
            else:
                status_item.setForeground(QColor("#ff4444"))  # Bright red
                status_item.setBackground(QColor("#330000"))  # Dark red background
            self.conn_table.setItem(i, 1, status_item)
            
            details_item = QTableWidgetItem(f"{status} - {details}")
            self.conn_table.setItem(i, 2, details_item)
        
        # Update HB port status (rows 2-7)
        self._update_hb_port_status()
    
    def _update_hb_port_status(self):
        """Update HB port status in connections table (rows 2-7)"""
        import subprocess
        
        # HB ports configuration
        hb_ports = [
            (2, 'FTI', 9877),
            (3, 'ROC', 9878),
            (4, 'DIMC', 9879),
            (5, 'COMC', 9880),
            (6, 'ROS2', 9881),
            (7, 'UE5', 9882),
        ]
        
        # Check which ports are listening
        listening_ports = set()
        try:
            result = subprocess.run(['ss', '-uln'], capture_output=True, text=True, timeout=1)
            for port in [9877, 9878, 9879, 9880, 9881, 9882]:
                if f':{port}' in result.stdout:
                    listening_ports.add(port)
        except:
            pass
        
        # Get HB receiver stats if available
        receiver_stats = {}
        if self.webthread_core and hasattr(self.webthread_core, 'get_receiver_stats'):
            try:
                receiver_stats = self.webthread_core.get_receiver_stats() or {}
            except:
                pass
        
        for row, comp, port in hb_ports:
            name = f"HB:{comp} ({port})"
            self.conn_table.setItem(row, 0, QTableWidgetItem(name))
            
            is_listening = port in listening_ports
            
            # Get per-component stats
            comp_stats = receiver_stats.get(comp, {})
            hb_count = comp_stats.get('heartbeats_received', 0)
            
            status_item = QTableWidgetItem("●")
            status_item.setFont(QFont("Arial", 12))
            
            if is_listening:
                if hb_count > 0:
                    status_item.setForeground(QColor("#00ff00"))  # Green - active
                    details = f"Listening - {hb_count} HBs received"
                else:
                    status_item.setForeground(QColor("#ffaa00"))  # Orange - listening but no HBs
                    details = "Listening - No HBs yet"
            else:
                status_item.setForeground(QColor("#ff4444"))  # Red - not listening
                details = "Not listening"
            
            self.conn_table.setItem(row, 1, status_item)
            self.conn_table.setItem(row, 2, QTableWidgetItem(details))
    
    def get_ue5_status_text(self) -> str:
        """Get UE5 connection status text"""
        if self.webthread_core and self.webthread_core.is_ue5_connected():
            return "Connected"
        return "Not Connected"
    
    def get_ue5_details(self) -> str:
        """Get UE5 connection details"""
        if self.webthread_core and self.webthread_core.ue5_connector:
            host = self.webthread_core.ue5_host
            port = self.webthread_core.ue5_port
            return f"{host}:{port}"
        return "localhost:9876"
    
    def reconnect_ue5(self):
        """Reconnect to UE5"""
        if self.webthread_core:
            self.add_log("Attempting to reconnect to UE5...")
            if self.webthread_core.reconnect_ue5():
                self.add_log("Successfully reconnected to UE5", "SUCCESS")
                self.update_ue5_status()
                self.update_connections()
            else:
                self.add_log("Failed to reconnect to UE5", "ERROR")
    
    def update_ui(self):
        """Periodic UI updates"""
        # Could add additional UI updates here
        pass
    
    def add_log(self, message, level="INFO", source="System"):
        """Add a log message with filtering support
        
        Args:
            message: The log message text
            level: Log level (DEBUG, INFO, WARNING, ERROR, SUCCESS)
            source: Message source (Bridge, FTI, Converter, Orchestrator, ROS, System, HB)
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Create structured log entry
        entry = {
            'timestamp': timestamp,
            'level': level.upper(),
            'source': source,
            'message': message
        }
        
        # Store entry for filtering
        if hasattr(self, '_log_entries'):
            self._log_entries.append(entry)
            
            # Keep only last 2000 entries
            if len(self._log_entries) > 2000:
                self._log_entries = self._log_entries[-2000:]
        
        # Check if entry passes current filters
        if hasattr(self, 'log_filter'):
            filters = self.log_filter.get_filters()
            
            # Level filter
            if filters['level'] != 'ALL' and entry['level'] != filters['level']:
                return
            
            # Source filter
            if filters['source'] != 'ALL' and entry['source'] != filters['source']:
                return
            
            # Text search
            if filters['search'] and filters['search'] not in entry['message'].lower():
                return
        
        # Add to view
        self._append_log_entry_to_view(entry)
        
        # Update count
        if hasattr(self, 'log_count_label') and hasattr(self, '_log_entries'):
            self.log_count_label.setText(f"Logs: {len(self._log_entries)}")
    
    def start_webthread(self):
        """Start Webthread"""
        if not self.webthread_core:
            self.init_webthread()
        
        if self.webthread_core and not self.webthread_core.monitoring_active:
            self.webthread_core.start()
            self.start_monitoring()
            self.status_label.setText("● Running")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.add_log("Webthread started")
    
    def stop_webthread(self):
        """Stop Webthread"""
        if self.webthread_core and self.webthread_core.monitoring_active:
            self.webthread_core.stop()
            self.status_label.setText("● Stopped")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.add_log("Webthread stopped")
    
    def start_bridge(self):
        """Start the rosbridge server"""
        import subprocess
        self.add_log("Starting bridge servers...")
        try:
            result = subprocess.run(
                ["/home/myws/roa/roa_linux/roa-core/lib/start_bridge.sh"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                self.add_log("✅ Bridge servers started successfully")
                # Log port status
                ports = subprocess.run(["ss", "-tuln"], capture_output=True, text=True)
                if ':9090' in ports.stdout:
                    self.add_log("  Port 9090 (rosbridge): LISTENING")
                if ':9876' in ports.stdout:
                    self.add_log("  Port 9876 (command): LISTENING")
            else:
                self.add_log(f"❌ Bridge start failed: {result.stderr}", "ERROR")
                if result.stdout:
                    self.add_log(f"Output: {result.stdout}")
        except Exception as e:
            self.add_log(f"❌ Failed to start bridge: {e}", "ERROR")
        self.update_bridge_status()
    
    def stop_bridge(self):
        """Stop the rosbridge server"""
        import subprocess
        self.add_log("Stopping bridge servers...")
        try:
            result = subprocess.run(
                ["/home/myws/roa/roa_linux/roa-core/lib/stop_bridge.sh"],
                capture_output=True,
                text=True,
                timeout=5
            )
            self.add_log("✅ Bridge servers stopped")
            if result.stdout:
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        self.add_log(f"  {line}")
        except Exception as e:
            self.add_log(f"❌ Failed to stop bridge: {e}", "ERROR")
        self.update_bridge_status()
    
    def update_bridge_status(self):
        """Update bridge server status indicator (both ports)"""
        import subprocess
        try:
            # Check both servers
            rosbridge_running = subprocess.run(
                ["pgrep", "-f", "roa_bridge_server.py"],
                capture_output=True
            ).returncode == 0
            
            command_running = subprocess.run(
                ["pgrep", "-f", "roa_command_server.py"],
                capture_output=True
            ).returncode == 0
            
            # Track port status for all ports
            self._update_all_port_status()
            
            # Update individual port indicators
            if rosbridge_running:
                self._update_port_label(9090, True)
            else:
                self._update_port_label(9090, False)
            
            if command_running:
                self._update_port_label(9876, True)
            else:
                self._update_port_label(9876, False)
            
            # Update button states based on both servers
            if rosbridge_running and command_running:
                self.bridge_start_btn.setStyleSheet("background-color: #1a4d1a; color: #888; padding: 5px 10px;")
                self.bridge_start_btn.setEnabled(False)
                self.bridge_stop_btn.setStyleSheet("background-color: #8b0000; color: white; font-weight: bold; padding: 5px 10px;")
                self.bridge_stop_btn.setEnabled(True)
            elif rosbridge_running or command_running:
                self.bridge_start_btn.setEnabled(True)
                self.bridge_stop_btn.setEnabled(True)
                self.bridge_start_btn.setStyleSheet("background-color: #4a4a00; color: white; font-weight: bold; padding: 5px 10px;")
                self.bridge_stop_btn.setStyleSheet("background-color: #4a4a00; color: white; font-weight: bold; padding: 5px 10px;")
            else:
                self.bridge_start_btn.setStyleSheet("background-color: #006400; color: white; font-weight: bold; padding: 5px 10px;")
                self.bridge_start_btn.setEnabled(True)
                self.bridge_stop_btn.setStyleSheet("background-color: #3d3d3d; color: #888; padding: 5px 10px;")
                self.bridge_stop_btn.setEnabled(False)
        except Exception as e:
            self._update_port_label(9090, None)  # None = unknown state
            self._update_port_label(9876, None)
    
    def _update_port_label(self, port: int, is_active: bool | None):
        """Update port label style based on status"""
        if not hasattr(self, 'all_port_labels'):
            return
        
        label = self.all_port_labels.get(port)
        if not label:
            return
        
        if is_active is True:
            label.setStyleSheet("""
                QPushButton {
                    color: #00ff00; 
                    font-weight: bold; 
                    font-size: 10px; 
                    border: none; 
                    text-align: left;
                    padding: 2px 4px;
                }
                QPushButton:hover {
                    color: #00ffaa;
                    background-color: rgba(0, 255, 0, 0.1);
                    border-radius: 3px;
                }
            """)
        elif is_active is False:
            label.setStyleSheet("""
                QPushButton {
                    color: #ff4444; 
                    font-weight: bold; 
                    font-size: 10px; 
                    border: none; 
                    text-align: left;
                    padding: 2px 4px;
                }
                QPushButton:hover {
                    color: #ff6666;
                    background-color: rgba(255, 68, 68, 0.1);
                    border-radius: 3px;
                }
            """)
        else:  # Unknown state
            label.setStyleSheet("""
                QPushButton {
                    color: #ffaa00; 
                    font-weight: bold; 
                    font-size: 10px; 
                    border: none; 
                    text-align: left;
                    padding: 2px 4px;
                }
                QPushButton:hover {
                    color: #ffcc00;
                    background-color: rgba(255, 170, 0, 0.1);
                    border-radius: 3px;
                }
            """)
    
    def _update_all_port_status(self):
        """Check and update status of all ports (both TCP and UDP)"""
        import subprocess
        
        if not hasattr(self, 'all_port_labels'):
            return
        
        # Check listening ports using ss command - include both TCP (-t) and UDP (-u)
        try:
            # Get TCP ports
            tcp_result = subprocess.run(['ss', '-tln'], capture_output=True, text=True, timeout=2)
            tcp_output = tcp_result.stdout
            
            # Get UDP ports (HB ports use UDP)
            udp_result = subprocess.run(['ss', '-uln'], capture_output=True, text=True, timeout=2)
            udp_output = udp_result.stdout
            
            # Combine both outputs for port checking
            combined_output = tcp_output + udp_output
            
            for port in self.all_port_labels.keys():
                # Check if port is in LISTEN state (TCP or UDP)
                is_listening = f':{port}' in combined_output or f':{port} ' in combined_output
                if port not in [9090, 9876]:  # HB ports - update them based on actual listening status
                    self._update_port_label(port, is_listening)
        except Exception as e:
            logging.debug(f"Error checking port status: {e}")
    
    def _toggle_port(self, port: int):
        """Toggle port on/off - start or stop the associated service"""
        import subprocess
        
        config = self.port_configs.get(port, {})
        port_type = config.get('type', 'unknown')
        port_name = config.get('name', f'Port {port}')
        
        self.add_log(f"Toggling {port_name} ({port})...")
        
        # Check if port is currently active
        try:
            result = subprocess.run(['ss', '-tuln'], capture_output=True, text=True, timeout=2)
            is_active = f':{port}' in result.stdout
        except:
            is_active = False
        
        if port_type == 'bridge':
            # Bridge ports - use bridge scripts
            if port == 9090:
                if is_active:
                    self.add_log(f"Stopping rosbridge_server (port {port})...")
                    subprocess.run(['pkill', '-f', 'roa_bridge_server.py'], capture_output=True)
                else:
                    self.add_log(f"Starting rosbridge_server (port {port})...")
                    subprocess.Popen(
                        ['python3', '/home/myws/roa/roa_linux/roa-core/lib/roa_bridge_server.py'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
            elif port == 9876:
                if is_active:
                    self.add_log(f"Stopping command_server (port {port})...")
                    subprocess.run(['pkill', '-f', 'roa_command_server.py'], capture_output=True)
                else:
                    self.add_log(f"Starting command_server (port {port})...")
                    subprocess.Popen(
                        ['python3', '/home/myws/roa/roa_linux/roa-core/lib/roa_command_server.py'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
        elif port_type == 'hb':
            # HB ports - start/stop HB receiver for that component
            comp_name = port_name.replace('HB:', '')
            if is_active:
                self.add_log(f"Stopping HB receiver for {comp_name} (port {port})...")
                # The HB subsystem manages these internally
                if self.webthread_core and hasattr(self.webthread_core, 'stop_hb_port'):
                    self.webthread_core.stop_hb_port(port)
                else:
                    self.add_log(f"HB port control not available for port {port}", "WARNING")
            else:
                self.add_log(f"Starting HB receiver for {comp_name} (port {port})...")
                if self.webthread_core and hasattr(self.webthread_core, 'start_hb_port'):
                    self.webthread_core.start_hb_port(port)
                else:
                    self.add_log(f"HB port control not available for port {port}", "WARNING")
        
        # Update status after a short delay
        QTimer.singleShot(500, self.update_bridge_status)
    
    def _update_hb_port_status(self):
        """Update HB port indicators based on HB subsystem status"""
        if not hasattr(self, 'all_port_labels'):
            return
        
        # Check if HB subsystem is active
        hb_active = (self.webthread_core and 
                     getattr(self.webthread_core, '_hb_enabled', False) and
                     getattr(self.webthread_core, 'hb_subsystem', None))
        
        if hb_active:
            # Get receiver stats to check which ports are active
            try:
                stats = self.webthread_core.get_receiver_stats() if hasattr(self.webthread_core, 'get_receiver_stats') else {}
                component_stats = stats.get('components', {})
                
                port_to_comp = {9877: 'FTI', 9878: 'ROC', 9879: 'DIMC', 
                               9880: 'COMC', 9881: 'ROS2Bridge', 9882: 'UE5Bridge'}
                
                for port in [9877, 9878, 9879, 9880, 9881, 9882]:
                    if port in self.all_port_labels:
                        comp = port_to_comp.get(port, '')
                        comp_stat = component_stats.get(comp, {})
                        is_receiving = comp_stat.get('receiving', False)
                        self._update_port_label(port, is_receiving)
            except Exception:
                pass
        else:
            # HB not active - show ports as inactive
            for port in [9877, 9878, 9879, 9880, 9881, 9882]:
                if port in self.all_port_labels:
                    self._update_port_label(port, False)
    
    def test_data_flow(self):
        """Run comprehensive data flow test for all components"""
        import subprocess
        import os
        
        # Check if test file exists
        test_file = "/home/myws/roa/roa_linux/roa-core/lib/test_bridge_dataflow.py"
        if not os.path.exists(test_file):
            self.add_log("❌ Test file not found: test_bridge_dataflow.py", "ERROR")
            self._add_test_result("❌ Test file not found - data flow test unavailable")
            return
        
        self.add_log("🧪 Starting data flow test...")
        self._add_test_result("Testing all component data types...")
        
        # Use QProcess for non-blocking execution that's Qt-safe
        if not hasattr(self, 'dataflow_process'):
            self.dataflow_process = QProcess()
            self.dataflow_process.readyReadStandardOutput.connect(self._handle_dataflow_output)
            self.dataflow_process.readyReadStandardError.connect(self._handle_dataflow_error)
            self.dataflow_process.finished.connect(self._handle_dataflow_finished)
        
        if self.dataflow_process.state() == QProcess.ProcessState.Running:
            self.add_log("⚠️ Test already running, please wait...", "WARNING")
            return
        
        self.dataflow_process.start("python3", [test_file])
    
    def _handle_dataflow_output(self):
        """Handle stdout from data flow test"""
        try:
            output = self.dataflow_process.readAllStandardOutput().data().decode('utf-8', errors='replace')
            for line in output.strip().split('\n'):
                if line.strip():
                    self.add_log(line)
        except Exception as e:
            self.add_log(f"Error reading test output: {e}", "ERROR")
    
    def _handle_dataflow_error(self):
        """Handle stderr from data flow test"""
        try:
            error = self.dataflow_process.readAllStandardError().data().decode('utf-8', errors='replace')
            for line in error.strip().split('\n'):
                if line.strip():
                    self.add_log(f"[stderr] {line}", "WARNING")
        except Exception as e:
            self.add_log(f"Error reading test stderr: {e}", "ERROR")
    
    def _handle_dataflow_finished(self, exit_code, exit_status):
        """Handle data flow test completion"""
        if exit_code == 0:
            self._add_test_result("✅ Data flow test completed successfully")
            self.add_log("✅ Data flow test finished")
        else:
            self._add_test_result(f"⚠️ Data flow test exited with code {exit_code}")
            self.add_log(f"⚠️ Data flow test exited with code {exit_code}", "WARNING")
    
    def closeEvent(self, event):
        """Handle window close"""
        if self.monitor_thread:
            self.monitor_thread.stop()
            self.monitor_thread.wait()
        
        if self.webthread_core:
            self.webthread_core.shutdown()
        
        # Stop FTI IPC service on app close
        _stop_fti_service()
        
        event.accept()


# ============================================================================
# FTI Service Auto-Start (called before GUI starts)
# ============================================================================
FTI_SERVICE_SCRIPT = "/home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python/roa_ipc_service.py"
FTI_SERVICE_LOG = "/tmp/roa_fti_service.log"
IPC_FOLDER = "/mnt/d/ROA/.ipc"


def _get_fti_service_status():
    """Check if FTI IPC service is running by reading status file"""
    import os
    import json
    from datetime import datetime
    
    status_file = os.path.join(IPC_FOLDER, "service.status")
    if not os.path.exists(status_file):
        return {"running": False, "pid": None, "uptime": 0}
    
    try:
        with open(status_file, 'r') as f:
            data = json.load(f)
        
        # Check heartbeat freshness - service uses ISO timestamp in last_heartbeat
        last_hb = data.get('last_heartbeat')
        if last_hb:
            try:
                if isinstance(last_hb, str):
                    if last_hb.endswith('Z'):
                        last_hb = last_hb.replace('Z', '+00:00')
                    hb_dt = datetime.fromisoformat(last_hb)
                    # Compare with current time
                    now = datetime.now(hb_dt.tzinfo) if hb_dt.tzinfo else datetime.now()
                    age = (now - hb_dt.replace(tzinfo=None)).total_seconds()
                else:
                    age = 999
            except:
                age = 999
        else:
            age = 999
        
        is_running = age < 10 and data.get('status') == 'running'
        return {
            "running": is_running,
            "pid": data.get('pid'),
            "uptime": data.get('uptime_seconds', 0)
        }
    except:
        return {"running": False, "pid": None, "uptime": 0}


def _ensure_fti_service_running():
    """Ensure FTI IPC service is running, start if not"""
    import subprocess
    import os
    import time
    
    print("Checking FTI IPC Service...")
    
    status = _get_fti_service_status()
    if status["running"]:
        print(f"  ✓ FTI service already running (PID: {status['pid']}, uptime: {status['uptime']}s)")
        return True
    
    # Service not running - start it
    print("  Starting FTI IPC service...")
    
    if not os.path.exists(FTI_SERVICE_SCRIPT):
        print(f"  ✗ FTI service script not found: {FTI_SERVICE_SCRIPT}")
        return False
    
    # Create IPC folder
    os.makedirs(IPC_FOLDER, exist_ok=True)
    
    try:
        # Start service with logging to file (no auto-shutdown - service stops when app closes)
        cmd = [
            'python3', FTI_SERVICE_SCRIPT,
            '--ipc-path', IPC_FOLDER,
            '--no-auto-shutdown',
            '--log-file', FTI_SERVICE_LOG
        ]
        
        # Start detached
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        
        print(f"  Started FTI service (PID: {process.pid})")
        print(f"  Logs: {FTI_SERVICE_LOG}")
        
        # Wait for service to initialize (check status file or process)
        for i in range(15):  # Up to 7.5 seconds
            time.sleep(0.5)
            status = _get_fti_service_status()
            if status["running"]:
                print(f"  ✓ FTI service is running")
                return True
        
        # Fallback: check if process is still alive
        if process.poll() is None:
            print(f"  ✓ FTI service started (PID: {process.pid})")
            return True
        
        print(f"  ⚠ Service may have failed to start")
        return False
        
    except Exception as e:
        print(f"  ✗ Failed to start FTI service: {e}")
        return False


def _stop_fti_service():
    """Stop the FTI IPC service gracefully"""
    import subprocess
    import os
    import signal
    
    print("Stopping FTI IPC Service...")
    
    # Find and kill the service process
    try:
        result = subprocess.run(
            ['pgrep', '-f', 'roa_ipc_service'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                if pid:
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                        print(f"  Stopped FTI service (PID: {pid})")
                    except (ProcessLookupError, ValueError):
                        pass
        else:
            print("  FTI service was not running")
    except Exception as e:
        print(f"  Warning: Could not stop FTI service: {e}")


def main():
    """Main entry point"""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # ========================================================================
    # Auto-start FTI IPC Service (runs in background)
    # ========================================================================
    _ensure_fti_service_running()
    
    app = QApplication(sys.argv)
    app.setApplicationName("ROA Webthread Monitor")
    
    window = WebthreadMonitorUI()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
