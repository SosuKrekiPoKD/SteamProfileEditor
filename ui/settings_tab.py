import json
import os
import subprocess
import sys
import threading

import requests

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSpinBox, QCheckBox, QGroupBox, QComboBox, QProgressBar,
    QScrollArea,
)
from PyQt5.QtCore import pyqtSignal, QObject

from core.account_manager import AccountManager
from core.proxy_manager import ProxyManager


class _ProxyCheckSignals(QObject):
    progress = pyqtSignal(int)
    log_ok = pyqtSignal(str)
    log_fail = pyqtSignal(str)
    finished = pyqtSignal(str, int, int)  # result_text, valid, invalid


class SettingsTab(QWidget):
    theme_changed = pyqtSignal(str)  # "dark" or "light"

    def __init__(self, proxy_manager: ProxyManager, account_manager: AccountManager = None,
                 log_widget=None, data_dir: str = None, parent=None):
        super().__init__(parent)
        self.proxy_manager = proxy_manager
        self.account_manager = account_manager
        self.log_widget = log_widget
        self._config_path = os.path.join(data_dir, "config.json") if data_dir else None
        self._loading_config = False
        self._init_ui()

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

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

        # Accounts group
        acc_group = QGroupBox("Accounts")
        acc_layout = QVBoxLayout()

        acc_btn_row = QHBoxLayout()
        self.btn_open_accounts = QPushButton("Open accounts.txt")
        self.btn_open_accounts.clicked.connect(self._open_accounts_file)
        acc_btn_row.addWidget(self.btn_open_accounts)

        self.btn_open_mafiles = QPushButton("Open maFiles folder")
        self.btn_open_mafiles.clicked.connect(self._open_mafiles_folder)
        acc_btn_row.addWidget(self.btn_open_mafiles)

        self.btn_refresh_accounts = QPushButton("Refresh accounts")
        self.btn_refresh_accounts.setObjectName("successBtn")
        self.btn_refresh_accounts.clicked.connect(self._refresh_accounts)
        acc_btn_row.addWidget(self.btn_refresh_accounts)

        acc_btn_row.addStretch()
        acc_layout.addLayout(acc_btn_row)

        self.label_accounts_status = QLabel("Accounts: 0")
        acc_layout.addWidget(self.label_accounts_status)

        acc_group.setLayout(acc_layout)
        layout.addWidget(acc_group)

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

        # Save settings on value changes
        self.spin_threads.valueChanged.connect(self._save_config)
        self.spin_delay.valueChanged.connect(self._save_config)

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

        scroll.setWidget(scroll_content)
        outer.addWidget(scroll)

    def _on_theme_change(self, text: str):
        self.theme_changed.emit(text.lower())

    def _on_multithread_toggle(self, checked: bool):
        self.spin_threads.setEnabled(checked)
        if not checked:
            self.spin_threads.setValue(1)
        self._save_config()

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
            from concurrent.futures import ThreadPoolExecutor, as_completed

            total = self.proxy_manager.count
            self.proxy_manager.load()

            # Build list of all proxies to check
            proxies_to_check = []
            for i in range(total):
                proxy = self.proxy_manager.acquire()
                if proxy is None:
                    break
                proxies_to_check.append((i, proxy))

            valid = 0
            invalid = 0
            checked = 0
            lock = threading.Lock()

            def _check_one(item):
                idx, proxy = item
                ok = _test_proxy(proxy)
                proxy_str = proxy.get("http", "?").replace("http://", "")
                return idx, ok, proxy_str

            workers = min(20, total)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_check_one, item): item for item in proxies_to_check}
                for future in as_completed(futures):
                    idx, ok, proxy_str = future.result()
                    with lock:
                        checked += 1
                        if ok:
                            valid += 1
                            signals.log_ok.emit(
                                f"[OK] Proxy {idx+1}/{total}: {proxy_str}"
                            )
                        else:
                            invalid += 1
                            signals.log_fail.emit(
                                f"[FAIL] Proxy {idx+1}/{total}: {proxy_str} — not working"
                            )
                        signals.progress.emit(checked)

            result_text = (
                f"<span style='color: #00cc00;'>Valid: {valid}</span> | "
                f"<span style='color: #ff4444;'>Invalid: {invalid}</span> | "
                f"Total: {total}"
            )
            signals.finished.emit(result_text, valid, invalid)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def _refresh_accounts(self):
        if not self.account_manager:
            return
        accounts = self.account_manager.load()
        total = len(accounts)
        with_mafile = sum(1 for a in accounts if a.has_mafile)
        without_mafile = total - with_mafile
        self.label_accounts_status.setText(
            f"Accounts: {total} ({with_mafile} with maFile, {without_mafile} without)"
        )
        if self.log_widget:
            self.log_widget.smart_log(
                f"[INFO] Accounts refreshed: {total} total "
                f"({with_mafile} with maFile, {without_mafile} without)"
            )

    def _open_accounts_file(self):
        if not self.account_manager:
            return
        path = self.account_manager.accounts_file
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write("")
        self._open_path(path)

    def _open_mafiles_folder(self):
        if not self.account_manager:
            return
        path = self.account_manager.mafiles_dir
        os.makedirs(path, exist_ok=True)
        self._open_path(path)

    @staticmethod
    def _open_path(path: str):
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def _save_config(self):
        if not self._config_path or self._loading_config:
            return
        config = {
            "multithread": self.cb_multithread.isChecked(),
            "threads": self.spin_threads.value(),
            "delay": self.spin_delay.value(),
        }
        try:
            os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except Exception:
            pass

    def _load_config(self):
        if not self._config_path or not os.path.exists(self._config_path):
            return
        self._loading_config = True
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            self.spin_delay.setValue(config.get("delay", 5))
            threads = config.get("threads", 1)
            if config.get("multithread"):
                self.cb_multithread.setChecked(True)
                self.spin_threads.setEnabled(True)
            if threads >= 1:
                self.spin_threads.setValue(threads)
        except Exception:
            pass
        finally:
            self._loading_config = False

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
