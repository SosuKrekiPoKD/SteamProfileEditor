import threading

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSpinBox, QProgressBar, QGroupBox, QCheckBox, QScrollArea,
    QGridLayout,
)
from PyQt5.QtCore import QObject, pyqtSignal

from core.account_manager import AccountManager
from core.proxy_manager import ProxyManager
from core.friends_service import add_friends_between_accounts
from ui.log_widget import LogWidget


class _FriendSignals(QObject):
    """Thread-safe signals for friends worker."""
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    finished = pyqtSignal()


class FriendsTab(QWidget):
    def __init__(self, account_manager: AccountManager, proxy_manager: ProxyManager,
                 log_widget: LogWidget, get_thread_settings=None, parent=None):
        super().__init__(parent)
        self.account_manager = account_manager
        self.proxy_manager = proxy_manager
        self.log_widget = log_widget
        self.get_thread_settings = get_thread_settings
        self._cancel_event = threading.Event()
        self._account_checkboxes = []

        # Signals for thread-safe UI updates
        self._signals = _FriendSignals()
        self._signals.log.connect(self.log_widget.smart_log)
        self._signals.progress.connect(self._on_progress)
        self._signals.finished.connect(self._on_finished)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        header = QLabel("Friend Management")
        header.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(header)

        desc = QLabel(
            "Add friends between selected accounts. Each account gets a random "
            "number of friends in the specified range. Already existing friends "
            "from the selection are replaced with other random accounts."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888;")
        layout.addWidget(desc)

        # === Account selection ===
        acc_group = QGroupBox("Select accounts")
        acc_outer = QVBoxLayout()

        acc_btn_row = QHBoxLayout()
        self.btn_select_all = QPushButton("Select All")
        self.btn_select_all.clicked.connect(self._select_all)
        acc_btn_row.addWidget(self.btn_select_all)

        self.btn_deselect_all = QPushButton("Deselect All")
        self.btn_deselect_all.clicked.connect(self._deselect_all)
        acc_btn_row.addWidget(self.btn_deselect_all)

        acc_btn_row.addStretch()
        acc_outer.addLayout(acc_btn_row)

        self._acc_scroll = QScrollArea()
        self._acc_scroll.setWidgetResizable(True)
        self._acc_scroll.setMaximumHeight(120)
        self._acc_container = QWidget()
        self._acc_layout = QGridLayout(self._acc_container)
        self._acc_layout.setSpacing(4)
        self._acc_scroll.setWidget(self._acc_container)
        acc_outer.addWidget(self._acc_scroll)

        self.label_selected = QLabel("Selected: 0 / 0")
        acc_outer.addWidget(self.label_selected)

        acc_group.setLayout(acc_outer)
        layout.addWidget(acc_group)

        # === Range settings ===
        range_group = QGroupBox("Friends per account")
        range_layout = QHBoxLayout()

        range_layout.addWidget(QLabel("Min:"))
        self.spin_min = QSpinBox()
        self.spin_min.setRange(1, 1000)
        self.spin_min.setValue(5)
        range_layout.addWidget(self.spin_min)

        range_layout.addWidget(QLabel("Max:"))
        self.spin_max = QSpinBox()
        self.spin_max.setRange(1, 1000)
        self.spin_max.setValue(10)
        range_layout.addWidget(self.spin_max)

        range_layout.addStretch()
        range_group.setLayout(range_layout)
        layout.addWidget(range_group)

        # Progress
        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        # Buttons
        btn_layout = QHBoxLayout()

        self.btn_start = QPushButton("Start Adding Friends")
        self.btn_start.setObjectName("successBtn")
        self.btn_start.clicked.connect(self._start)
        btn_layout.addWidget(self.btn_start)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("dangerBtn")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)
        btn_layout.addWidget(self.btn_cancel)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch()

    def refresh_accounts(self):
        for cb in self._account_checkboxes:
            self._acc_layout.removeWidget(cb)
            cb.deleteLater()
        self._account_checkboxes.clear()

        accounts = self.account_manager.accounts
        cols = 3
        for i, acc in enumerate(accounts):
            cb = QCheckBox(acc.username)
            cb.setChecked(True)
            cb.toggled.connect(self._update_selected_count)
            self._acc_layout.addWidget(cb, i // cols, i % cols)
            self._account_checkboxes.append(cb)

        self._update_selected_count()

        count = len(accounts)
        self.spin_min.setMaximum(max(1, count - 1))
        self.spin_max.setMaximum(max(1, count - 1))

    def _update_selected_count(self):
        total = len(self._account_checkboxes)
        selected = sum(1 for cb in self._account_checkboxes if cb.isChecked())
        self.label_selected.setText(f"Selected: {selected} / {total}")

    def _select_all(self):
        for cb in self._account_checkboxes:
            cb.setChecked(True)

    def _deselect_all(self):
        for cb in self._account_checkboxes:
            cb.setChecked(False)

    def _get_selected_accounts(self):
        selected = []
        accounts = self.account_manager.accounts
        for i, cb in enumerate(self._account_checkboxes):
            if cb.isChecked() and i < len(accounts):
                selected.append(accounts[i])
        return selected

    def _on_progress(self, current, total):
        self.progress.setMaximum(total)
        self.progress.setValue(current)

    def _on_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)

    def _start(self):
        selected = self._get_selected_accounts()
        if len(selected) < 2:
            self.log_widget.append_error("[ERROR] Need at least 2 selected accounts.")
            return

        min_friends = self.spin_min.value()
        max_friends = self.spin_max.value()

        if min_friends > max_friends:
            self.log_widget.append_error("[ERROR] Min friends cannot be greater than max.")
            return

        if max_friends >= len(selected):
            max_friends = len(selected) - 1
            self.log_widget.smart_log(
                f"[INFO] Adjusted max to {max_friends} (selected accounts - 1)"
            )

        _, use_proxies = 1, False
        if self.get_thread_settings:
            _, use_proxies = self.get_thread_settings()

        self._cancel_event.clear()
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress.setValue(0)

        # Use signals so callbacks are thread-safe
        signals = self._signals

        def _log(msg):
            signals.log.emit(msg)

        def _progress(current, total):
            signals.progress.emit(current, total)

        def _run():
            add_friends_between_accounts(
                accounts=selected,
                min_friends=min_friends,
                max_friends=max_friends,
                proxy_manager=self.proxy_manager if use_proxies else None,
                use_proxies=use_proxies,
                log_callback=_log,
                progress_callback=_progress,
                cancel_event=self._cancel_event,
            )
            signals.finished.emit()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def _cancel(self):
        self._cancel_event.set()
        self.log_widget.append_error("[CANCELLED] Friend adding cancelled.")
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
