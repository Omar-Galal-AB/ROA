"""
ROA Dark Theme Stylesheet
Modern dark theme with cyan accents matching the Windows version
"""

DARK_THEME = """
/* Main Window */
QMainWindow {
    background-color: #1a1a2e;
}

/* All Widgets Base */
QWidget {
    background-color: #1a1a2e;
    color: #ecf0f1;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 10pt;
}

/* Group Boxes */
QGroupBox {
    background-color: #2a2a3e;
    border: 2px solid #3a3a4e;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 15px;
    font-weight: bold;
    color: #00d4ff;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 5px 10px;
    color: #00d4ff;
}

/* Labels */
QLabel {
    background-color: transparent;
    color: #ecf0f1;
    padding: 2px;
}

/* Buttons */
QPushButton {
    background-color: #3a3a4e;
    color: #ffffff;
    border: 2px solid #4a4a5e;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #4a4a5e;
    border-color: #00d4ff;
}

QPushButton:pressed {
    background-color: #2a2a3e;
}

QPushButton:disabled {
    background-color: #2a2a3e;
    color: #555566;
    border-color: #3a3a4e;
}

/* Emergency Stop Button */
QPushButton#stopButton {
    background-color: #c0392b;
    color: #ffffff;
    border: 2px solid #e74c3c;
    font-size: 14pt;
    font-weight: bold;
    min-height: 60px;
}

QPushButton#stopButton:hover {
    background-color: #e74c3c;
}

QPushButton#stopButton:pressed {
    background-color: #a93226;
}

/* Start/Stop Buttons */
QPushButton#startButton {
    background-color: #27ae60;
    border-color: #2ecc71;
}

QPushButton#startButton:hover {
    background-color: #2ecc71;
}

QPushButton#stopButtonSmall {
    background-color: #c0392b;
    border-color: #e74c3c;
}

QPushButton#stopButtonSmall:hover {
    background-color: #e74c3c;
}

/* Sliders */
QSlider::groove:horizontal {
    background: #2a2a3e;
    height: 8px;
    border-radius: 4px;
    border: 1px solid #3a3a4e;
}

QSlider::handle:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #00d4ff, stop:1 #0099cc);
    border: 2px solid #00d4ff;
    width: 18px;
    margin: -6px 0;
    border-radius: 9px;
}

QSlider::handle:horizontal:hover {
    background: #00d4ff;
    border-color: #ffffff;
}

QSlider::add-page:horizontal {
    background: #2a2a3e;
}

QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #00d4ff, stop:1 #0099cc);
    border-radius: 4px;
}

/* ComboBox */
QComboBox {
    background-color: #2a2a3e;
    color: #ecf0f1;
    border: 2px solid #3a3a4e;
    border-radius: 6px;
    padding: 6px;
    min-width: 120px;
}

QComboBox:hover {
    border-color: #00d4ff;
}

QComboBox::drop-down {
    border: none;
    width: 30px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid #00d4ff;
}

QComboBox QAbstractItemView {
    background-color: #2a2a3e;
    color: #ecf0f1;
    selection-background-color: #00d4ff;
    selection-color: #1a1a2e;
    border: 2px solid #3a3a4e;
}

/* SpinBox / DoubleSpinBox */
QSpinBox, QDoubleSpinBox {
    background-color: #2a2a3e;
    color: #ecf0f1;
    border: 2px solid #3a3a4e;
    border-radius: 6px;
    padding: 4px;
}

QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: #00d4ff;
}

QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    background-color: #3a3a4e;
    border: none;
    width: 20px;
}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #00d4ff;
}

/* TextEdit / PlainTextEdit */
QTextEdit, QPlainTextEdit {
    background-color: #1a1a2e;
    color: #ecf0f1;
    border: 2px solid #3a3a4e;
    border-radius: 6px;
    padding: 8px;
    selection-background-color: #00d4ff;
    selection-color: #1a1a2e;
}

/* ListWidget */
QListWidget {
    background-color: #1a1a2e;
    color: #ecf0f1;
    border: 2px solid #3a3a4e;
    border-radius: 6px;
    padding: 4px;
}

QListWidget::item {
    padding: 8px;
    border-radius: 4px;
}

QListWidget::item:selected {
    background-color: #00d4ff;
    color: #1a1a2e;
}

QListWidget::item:hover {
    background-color: #2a2a3e;
}

/* TableWidget */
QTableWidget {
    background-color: #1a1a2e;
    color: #ecf0f1;
    gridline-color: #3a3a4e;
    border: 2px solid #3a3a4e;
    border-radius: 6px;
}

QTableWidget::item {
    padding: 6px;
}

QTableWidget::item:selected {
    background-color: #00d4ff;
    color: #1a1a2e;
}

QHeaderView::section {
    background-color: #2a2a3e;
    color: #00d4ff;
    padding: 8px;
    border: none;
    border-right: 1px solid #3a3a4e;
    border-bottom: 1px solid #3a3a4e;
    font-weight: bold;
}

/* TabWidget */
QTabWidget::pane {
    background-color: #2a2a3e;
    border: 2px solid #3a3a4e;
    border-radius: 6px;
    top: -2px;
}

QTabBar::tab {
    background-color: #2a2a3e;
    color: #bdc3c7;
    padding: 10px 20px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background-color: #00d4ff;
    color: #1a1a2e;
    font-weight: bold;
}

QTabBar::tab:hover {
    background-color: #3a3a4e;
}

/* ProgressBar */
QProgressBar {
    background-color: #2a2a3e;
    border: 2px solid #3a3a4e;
    border-radius: 6px;
    text-align: center;
    color: #ecf0f1;
    font-weight: bold;
}

QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #00d4ff, stop:1 #0099cc);
    border-radius: 4px;
}

/* CheckBox */
QCheckBox {
    spacing: 8px;
    color: #ecf0f1;
}

QCheckBox::indicator {
    width: 20px;
    height: 20px;
    border: 2px solid #3a3a4e;
    border-radius: 4px;
    background-color: #2a2a3e;
}

QCheckBox::indicator:checked {
    background-color: #00d4ff;
    border-color: #00d4ff;
}

QCheckBox::indicator:hover {
    border-color: #00d4ff;
}

/* StatusBar */
QStatusBar {
    background-color: #16213e;
    color: #ecf0f1;
    border-top: 2px solid #3a3a4e;
}

/* Splitter */
QSplitter::handle {
    background-color: #3a3a4e;
}

QSplitter::handle:hover {
    background-color: #00d4ff;
}

/* ScrollBar */
QScrollBar:vertical {
    background-color: #1a1a2e;
    width: 14px;
    border-radius: 7px;
}

QScrollBar::handle:vertical {
    background-color: #3a3a4e;
    border-radius: 6px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #00d4ff;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background-color: #1a1a2e;
    height: 14px;
    border-radius: 7px;
}

QScrollBar::handle:horizontal {
    background-color: #3a3a4e;
    border-radius: 6px;
    min-width: 30px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #00d4ff;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* Status Labels */
QLabel#statusActive {
    color: #2ecc71;
    font-weight: bold;
}

QLabel#statusInactive {
    color: #95a5a6;
}

QLabel#statusError {
    color: #e74c3c;
    font-weight: bold;
}

QLabel#statusWarning {
    color: #f39c12;
    font-weight: bold;
}

/* Header Labels */
QLabel#headerLabel {
    font-size: 14pt;
    font-weight: bold;
    color: #00d4ff;
    background-color: transparent;
}

QLabel#titleLabel {
    font-size: 16pt;
    font-weight: bold;
    color: #00d4ff;
}
"""
