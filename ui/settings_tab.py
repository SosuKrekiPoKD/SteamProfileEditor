import os
import subprocess
import sys
import threading

import requests

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSpinBox, QCheckBox, QGroupBox, QComboBox, QProgressBar,
)
from PyQt5.QtCore import pyqtSignal, QObject

from core.proxy_manager import ProxyManager


class _ProxyCheckSignals(QObject):
    progress = pyqtSignal(int)
    log_ok = pyqtSignal(str)
    log_fail = pyqtSignal(str)
    finished = pyqtSignal(str, int, int)  # result_text, valid, invalid


class SettingsTab(QWidget):
    theme_changed = pyqtSignal(str)  # "dark" or "light"

    def __init__(self, proxy_manager: ProxyManager, log_widget=None, parent=None):
        super().__init__(parent)
        self.proxy_manager = proxy_manager
        self.log_widget = log_widget
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        header = QLabel("Settings")
        header.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(header)

        # Theme group
        theme_group = QGroupBox("Appearance")
        theme_layout = QHBoxLayout()

        theme_layout.addWidget(QLabel("Theme:"))
        self.combo_theme = QComboBox()
        self.combo_theme.addItems(["Dark", "Light"])
        self.combo_theme.currentTextChanged.connect(self._on_theme_change)
        theme_layout.addWidget(self.combo_theme)
        theme_layout.addStretch()

        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)

        # Threading group
        thread_group = QGroupBox("Threading & Proxies")
        thread_layout = QVBoxLayout()

        # Multi-thread toggle
        row1 = QHBoxLayout()
        self.cb_multithread = QCheckBox("Enable multi-threading")
        self.cb_multithread.toggled.connect(self._on_multithread_toggle)
        row1.addWidget(self.cb_multithread)
        row1.addStretch()
        thread_layout.addLayout(row1)

        # Thread count
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Threads:"))
        self.spin_threads = QSpinBox()
        self.spin_threads.setRange(1, 1)
        self.spin_threads.setValue(1)
        self.spin_threads.setEnabled(False)
        row2.addWidget(self.spin_threads)
        row2.addStretch()
        thread_layout.addLayout(row2)

        # Delay between accounts
        row_delay = QHBoxLayout()
        row_delay.addWidget(QLabel("Delay between accounts (sec):"))
        self.spin_delay = QSpinBox()
        self.spin_delay.setRange(0, 300)
        self.spin_delay.setValue(5)
        self.spin_delay.setToolTip("Пауза в секундах перед обработкой следующего аккаунта")
        row_delay.addWidget(self.spin_delay)
        row_delay.addStretch()
        thread_layout.addLayout(row_delay)

        # Proxy info
        row3 = QHBoxLayout()
        self.label_proxy_info = QLabel("Proxies loaded: 0 | Max threads: 1")
        row3.addWidget(self.label_proxy_info)
        row3.addStretch()
        thread_layout.addLayout(row3)

        # Proxy buttons
        row4 = QHBoxLayout()
        self.btn_open_proxies = QPushButton("Open proxies.txt")
        self.btn_open_proxies.clicked.connect(self._open_proxies_file)
        row4.addWidget(self.btn_open_proxies)

        self.btn_reload_proxies = QPushButton("Reload Proxies")
        self.btn_reload_proxies.clicked.connect(self.reload_proxies)
        row4.addWidget(self.btn_reload_proxies)

        self.btn_check_proxies = QPushButton("Check Proxies")
        self.btn_check_proxies.clicked.connect(self._check_proxies)
        row4.addWidget(self.btn_check_proxies)

        row4.addStretch()
        thread_layout.addLayout(row4)

        # Proxy check progress & result
        self.proxy_progress = QProgressBar()
        self.proxy_progress.setValue(0)
        self.proxy_progress.setVisible(False)
        thread_layout.addWidget(self.proxy_progress)

        self.label_proxy_check = QLabel("")
        self.label_proxy_check.setVisible(False)
        thread_layout.addWidget(self.label_proxy_check)

        thread_group.setLayout(thread_layout)
        layout.addWidget(thread_group)

        # Proxy format help
        help_label = QLabel(
            "Proxy format: login:pass@ip:port (one per line in proxies.txt)"
        )
        help_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(help_label)

        layout.addStretch()

    def _on_theme_change(self, text: str):
        self.theme_changed.emit(text.lower())

    def _on_multithread_toggle(self, checked: bool):
        self.spin_threads.setEnabled(checked)
        if not checked:
            self.spin_threads.setValue(1)

    def reload_proxies(self):
        count = self.proxy_manager.load()
        max_threads = max(1, count)
        self.spin_threads.setMaximum(max_threads)
        self.label_proxy_info.setText(
            f"Proxies loaded: {count} | Max threads: {max_threads}"
        )
        # Reset check result
        self.label_proxy_check.setVisible(False)

    def get_thread_settings(self):
        """Returns (thread_count, use_proxies)."""
        if self.cb_multithread.isChecked():
            return self.spin_threads.value(), True
        return 1, False

    def get_delay(self) -> int:
        """Returns delay in seconds between accounts."""
        return self.spin_delay.value()

    def _check_proxies(self):
        """Check all loaded proxies by making a lightweight HTTP request."""
        count = self.proxy_manager.count
        if count == 0:
            if self.log_widget:
                self.log_widget.append_error("[ERROR] No proxies loaded. Reload first.")
            return

        self.btn_check_proxies.setEnabled(False)
        self.proxy_progress.setVisible(True)
        self.proxy_progress.setMaximum(count)
        self.proxy_progress.setValue(0)
        self.label_proxy_check.setVisible(True)
        self.label_proxy_check.setText("Checking...")

        # Use signals to safely update UI from background thread
        signals = _ProxyCheckSignals()
        signals.progress.connect(self.proxy_progress.setValue)
        if self.log_widget:
            signals.log_ok.connect(self.log_widget.append_success)
            signals.log_fail.connect(self.log_widget.append_error)

        def _on_finished(result_text, valid, invalid):
            total = valid + invalid
            self.label_proxy_check.setText(result_text)
            self.btn_check_proxies.setEnabled(True)
            self.proxy_manager.load()
            if self.log_widget:
                self.log_widget.smart_log(
                    f"Proxy check done: {valid} valid, {invalid} invalid out of {total}"
                )

        signals.finished.connect(_on_finished)

        def _run():
            valid = 0
            invalid = 0
            total = self.proxy_manager.count
            # Reload to reset usage tracking
            self.proxy_manager.load()

            for i in range(total):
                proxy = self.proxy_manager.acquire()
                if proxy is None:
                    break

                ok = _test_proxy(proxy)
                proxy_str = proxy.get("http", "?").replace("http://", "")
                if ok:
                    valid += 1
                    signals.log_ok.emit(
                        f"[OK] Proxy {i+1}/{total}: {proxy_str}"
                    )
                else:
                    invalid += 1
                    signals.log_fail.emit(
                        f"[FAIL] Proxy {i+1}/{total}: {proxy_str} — not working"
                    )

                signals.progress.emit(i + 1)

            result_text = (
                f"<span style='color: #00cc00;'>Valid: {valid}</span> | "
                f"<span style='color: #ff4444;'>Invalid: {invalid}</span> | "
                f"Total: {total}"
            )
            signals.finished.emit(result_text, valid, invalid)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def _open_proxies_file(self):
        path = self.proxy_manager.proxies_file
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write("")
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])


def _test_proxy(proxy_dict):
    """Test a proxy with minimal traffic — HEAD request to Steam."""
    try:
        resp = requests.head(
            "https://steamcommunity.com",
            proxies=proxy_dict,
            timeout=10,
            allow_redirects=True,
        )
        return resp.status_code < 500
    except Exception:
        return False
