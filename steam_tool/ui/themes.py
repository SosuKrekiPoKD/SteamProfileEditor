DARK_THEME = """
QWidget {
    background-color: #1a1a2e;
    color: #e0e0e0;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #1a1a2e;
}

QTabWidget::pane {
    border: 1px solid #2a2a4a;
    background-color: #16213e;
    border-radius: 4px;
}

QTabBar::tab {
    background-color: #1a1a2e;
    color: #8888aa;
    padding: 8px 20px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    border: 1px solid #2a2a4a;
    border-bottom: none;
}

QTabBar::tab:selected {
    background-color: #16213e;
    color: #ffffff;
    border-bottom: 2px solid #0f3460;
}

QTabBar::tab:hover {
    background-color: #1f2b4d;
    color: #cccccc;
}

QPushButton {
    background-color: #0f3460;
    color: #ffffff;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #1a4a7a;
}

QPushButton:pressed {
    background-color: #0a2540;
}

QPushButton:disabled {
    background-color: #2a2a4a;
    color: #666688;
}

QPushButton#dangerBtn {
    background-color: #8b0000;
}

QPushButton#dangerBtn:hover {
    background-color: #a00000;
}

QPushButton#successBtn {
    background-color: #006400;
}

QPushButton#successBtn:hover {
    background-color: #008000;
}

QLineEdit, QSpinBox, QTextEdit, QPlainTextEdit {
    background-color: #0f1a30;
    color: #e0e0e0;
    border: 1px solid #2a2a4a;
    padding: 6px;
    border-radius: 4px;
}

QLineEdit:focus, QSpinBox:focus {
    border: 1px solid #0f3460;
}

QTableWidget {
    background-color: #0f1a30;
    color: #e0e0e0;
    border: 1px solid #2a2a4a;
    gridline-color: #2a2a4a;
    border-radius: 4px;
}

QTableWidget::item {
    padding: 4px;
}

QTableWidget::item:selected {
    background-color: #0f3460;
}

QHeaderView::section {
    background-color: #1a1a2e;
    color: #8888aa;
    padding: 6px;
    border: 1px solid #2a2a4a;
    font-weight: bold;
}

QCheckBox {
    color: #e0e0e0;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #2a2a4a;
    border-radius: 3px;
    background-color: #0f1a30;
}

QCheckBox::indicator:checked {
    background-color: #0f3460;
    border-color: #0f3460;
}

QLabel {
    color: #e0e0e0;
}

QGroupBox {
    border: 1px solid #2a2a4a;
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 16px;
    color: #8888aa;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

QProgressBar {
    border: 1px solid #2a2a4a;
    border-radius: 4px;
    text-align: center;
    background-color: #0f1a30;
    color: #ffffff;
    height: 20px;
}

QProgressBar::chunk {
    background-color: #0f3460;
    border-radius: 3px;
}

QScrollBar:vertical {
    background-color: #1a1a2e;
    width: 10px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background-color: #2a2a4a;
    border-radius: 5px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #3a3a6a;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QSlider::groove:horizontal {
    background-color: #2a2a4a;
    height: 6px;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background-color: #0f3460;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}

QToolTip {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #2a2a4a;
    padding: 4px;
}
"""

LIGHT_THEME = """
QWidget {
    background-color: #f5f5f5;
    color: #333333;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #f5f5f5;
}

QTabWidget::pane {
    border: 1px solid #d0d0d0;
    background-color: #ffffff;
    border-radius: 4px;
}

QTabBar::tab {
    background-color: #e8e8e8;
    color: #666666;
    padding: 8px 20px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    border: 1px solid #d0d0d0;
    border-bottom: none;
}

QTabBar::tab:selected {
    background-color: #ffffff;
    color: #333333;
    border-bottom: 2px solid #1976d2;
}

QTabBar::tab:hover {
    background-color: #f0f0f0;
    color: #333333;
}

QPushButton {
    background-color: #1976d2;
    color: #ffffff;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #1e88e5;
}

QPushButton:pressed {
    background-color: #1565c0;
}

QPushButton:disabled {
    background-color: #cccccc;
    color: #888888;
}

QPushButton#dangerBtn {
    background-color: #d32f2f;
}

QPushButton#dangerBtn:hover {
    background-color: #e53935;
}

QPushButton#successBtn {
    background-color: #388e3c;
}

QPushButton#successBtn:hover {
    background-color: #43a047;
}

QLineEdit, QSpinBox, QTextEdit, QPlainTextEdit {
    background-color: #ffffff;
    color: #333333;
    border: 1px solid #d0d0d0;
    padding: 6px;
    border-radius: 4px;
}

QLineEdit:focus, QSpinBox:focus {
    border: 1px solid #1976d2;
}

QTableWidget {
    background-color: #ffffff;
    color: #333333;
    border: 1px solid #d0d0d0;
    gridline-color: #e0e0e0;
    border-radius: 4px;
}

QTableWidget::item {
    padding: 4px;
}

QTableWidget::item:selected {
    background-color: #bbdefb;
    color: #333333;
}

QHeaderView::section {
    background-color: #f5f5f5;
    color: #666666;
    padding: 6px;
    border: 1px solid #d0d0d0;
    font-weight: bold;
}

QCheckBox {
    color: #333333;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #d0d0d0;
    border-radius: 3px;
    background-color: #ffffff;
}

QCheckBox::indicator:checked {
    background-color: #1976d2;
    border-color: #1976d2;
}

QLabel {
    color: #333333;
}

QGroupBox {
    border: 1px solid #d0d0d0;
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 16px;
    color: #666666;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

QProgressBar {
    border: 1px solid #d0d0d0;
    border-radius: 4px;
    text-align: center;
    background-color: #e0e0e0;
    color: #333333;
    height: 20px;
}

QProgressBar::chunk {
    background-color: #1976d2;
    border-radius: 3px;
}

QScrollBar:vertical {
    background-color: #f5f5f5;
    width: 10px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background-color: #c0c0c0;
    border-radius: 5px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #a0a0a0;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QSlider::groove:horizontal {
    background-color: #d0d0d0;
    height: 6px;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background-color: #1976d2;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}

QToolTip {
    background-color: #ffffff;
    color: #333333;
    border: 1px solid #d0d0d0;
    padding: 4px;
}
"""
