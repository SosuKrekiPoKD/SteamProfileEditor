import threading

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox,
    QLabel, QProgressBar, QGroupBox, QGridLayout, QScrollArea,
    QSpinBox,
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject

from core.account_manager import AccountManager
from core.proxy_manager import ProxyManager
from core.task_executor import TaskExecutor
from core.avatar_service import set_random_avatar
from core.community_service import create_random_communities, join_random_communities
from core.profile_service import (
    change_profile_name, change_profile_bio,
    set_random_background, set_random_mini_profile,
    set_random_avatar_frame, set_random_animated_avatar,
)
from core.pointshop_service import claim_free_pointshop_items
from core.friends_service import add_friends_between_accounts
from ui.log_widget import LogWidget


class _FriendSignals(QObject):
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    finished = pyqtSignal()


class ActionsTab(QWidget):
    def __init__(self, account_manager: AccountManager, task_executor: TaskExecutor,
                 log_widget: LogWidget, proxy_manager: ProxyManager = None,
                 get_thread_settings=None, get_delay=None,
                 parent=None):
        super().__init__(parent)
        self.account_manager = account_manager
        self.task_executor = task_executor
        self.log_widget = log_widget
        self.proxy_manager = proxy_manager
        self.get_thread_settings = get_thread_settings
        self.get_delay = get_delay
        self._account_checkboxes = []
        self._signals_connected = False
        self._last_actions = {}  # {task_name: task_func} for retry
        self._last_do_friends = False
        self._last_friends_settings = {}
        self._init_ui()

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)

        header = QLabel("Actions")
        header.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(header)

        # === Account selection group ===
        acc_group = QGroupBox("Select accounts")
        acc_outer = QVBoxLayout()

        # Select all / Deselect all buttons
        acc_btn_row = QHBoxLayout()
        self.btn_select_all = QPushButton("Select All")
        self.btn_select_all.clicked.connect(self._select_all)
        acc_btn_row.addWidget(self.btn_select_all)

        self.btn_deselect_all = QPushButton("Deselect All")
        self.btn_deselect_all.clicked.connect(self._deselect_all)
        acc_btn_row.addWidget(self.btn_deselect_all)

        acc_btn_row.addStretch()
        acc_outer.addLayout(acc_btn_row)

        # Scrollable area with account checkboxes
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

        # === Profile actions group ===
        profile_group = QGroupBox("Profile")
        profile_layout = QGridLayout()

        self.cb_avatar = QCheckBox("Set random avatar")
        self.cb_name = QCheckBox("Set random nickname")
        self.cb_bio = QCheckBox("Set random bio")
        self.cb_background = QCheckBox("Set random background")
        self.cb_mini_profile = QCheckBox("Set random mini-profile background")
        self.cb_avatar_frame = QCheckBox("Set random avatar frame")
        self.cb_animated_avatar = QCheckBox("Set random animated avatar")

        # Mutual exclusion: avatar <-> animated avatar
        self.cb_avatar.toggled.connect(self._on_avatar_toggled)
        self.cb_animated_avatar.toggled.connect(self._on_animated_avatar_toggled)

        profile_layout.addWidget(self.cb_avatar, 0, 0)
        profile_layout.addWidget(self.cb_name, 0, 1)
        profile_layout.addWidget(self.cb_bio, 1, 0)
        profile_layout.addWidget(self.cb_background, 1, 1)
        profile_layout.addWidget(self.cb_mini_profile, 2, 0)
        profile_layout.addWidget(self.cb_avatar_frame, 2, 1)
        profile_layout.addWidget(self.cb_animated_avatar, 3, 0)

        profile_group.setLayout(profile_layout)
        layout.addWidget(profile_group)

        # === Points Shop group ===
        pointshop_group = QGroupBox("Points Shop")
        pointshop_layout = QVBoxLayout()

        self.cb_pointshop = QCheckBox("Claim free Points Shop items (avatars, stickers, frames, etc.)")
        pointshop_layout.addWidget(self.cb_pointshop)

        pointshop_group.setLayout(pointshop_layout)
        layout.addWidget(pointshop_group)

        # === Community actions group ===
        community_group = QGroupBox("Communities")
        community_layout = QGridLayout()

        self.cb_create_community = QCheckBox("Create community")
        self.spin_create_min = QSpinBox()
        self.spin_create_min.setRange(1, 20)
        self.spin_create_min.setValue(1)
        self.spin_create_min.setFixedWidth(50)
        self.spin_create_max = QSpinBox()
        self.spin_create_max.setRange(1, 20)
        self.spin_create_max.setValue(3)
        self.spin_create_max.setFixedWidth(50)

        self.cb_join_community = QCheckBox("Join community")
        self.spin_join_min = QSpinBox()
        self.spin_join_min.setRange(1, 20)
        self.spin_join_min.setValue(1)
        self.spin_join_min.setFixedWidth(50)
        self.spin_join_max = QSpinBox()
        self.spin_join_max.setRange(1, 20)
        self.spin_join_max.setValue(3)
        self.spin_join_max.setFixedWidth(50)

        create_row = QHBoxLayout()
        create_row.addWidget(self.cb_create_community)
        create_row.addWidget(QLabel("Min:"))
        create_row.addWidget(self.spin_create_min)
        create_row.addWidget(QLabel("Max:"))
        create_row.addWidget(self.spin_create_max)
        create_row.addStretch()

        join_row = QHBoxLayout()
        join_row.addWidget(self.cb_join_community)
        join_row.addWidget(QLabel("Min:"))
        join_row.addWidget(self.spin_join_min)
        join_row.addWidget(QLabel("Max:"))
        join_row.addWidget(self.spin_join_max)
        join_row.addStretch()

        community_layout.addLayout(create_row, 0, 0)
        community_layout.addLayout(join_row, 1, 0)

        community_group.setLayout(community_layout)
        layout.addWidget(community_group)

        # === Friends group ===
        friends_group = QGroupBox("Friends")
        friends_layout = QHBoxLayout()

        self.cb_add_friends = QCheckBox("Add friends from account list")
        friends_layout.addWidget(self.cb_add_friends)

        friends_layout.addWidget(QLabel("Min:"))
        self.spin_friends_min = QSpinBox()
        self.spin_friends_min.setRange(1, 1000)
        self.spin_friends_min.setValue(5)
        self.spin_friends_min.setFixedWidth(60)
        friends_layout.addWidget(self.spin_friends_min)

        friends_layout.addWidget(QLabel("Max:"))
        self.spin_friends_max = QSpinBox()
        self.spin_friends_max.setRange(1, 1000)
        self.spin_friends_max.setValue(10)
        self.spin_friends_max.setFixedWidth(60)
        friends_layout.addWidget(self.spin_friends_max)

        friends_layout.addStretch()
        friends_group.setLayout(friends_layout)
        layout.addWidget(friends_group)

        # Progress
        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        # Buttons
        btn_layout = QHBoxLayout()

        self.btn_start = QPushButton("Start")
        self.btn_start.setObjectName("successBtn")
        self.btn_start.clicked.connect(self._start)
        btn_layout.addWidget(self.btn_start)

        self.btn_retry = QPushButton("Retry Failed")
        self.btn_retry.setObjectName("warningBtn")
        self.btn_retry.setEnabled(False)
        self.btn_retry.setToolTip("Retry actions on accounts that failed")
        self.btn_retry.clicked.connect(self._retry_failed)
        btn_layout.addWidget(self.btn_retry)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("dangerBtn")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)
        btn_layout.addWidget(self.btn_cancel)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch()

        scroll.setWidget(scroll_content)
        outer.addWidget(scroll)

    def _on_avatar_toggled(self, checked):
        if checked and self.cb_animated_avatar.isChecked():
            self.cb_animated_avatar.setChecked(False)

    def _on_animated_avatar_toggled(self, checked):
        if checked and self.cb_avatar.isChecked():
            self.cb_avatar.setChecked(False)

    def refresh_accounts(self):
        """Rebuild account checkboxes from account_manager."""
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
        """Return list of accounts that are checked."""
        selected = []
        accounts = self.account_manager.accounts
        for i, cb in enumerate(self._account_checkboxes):
            if cb.isChecked() and i < len(accounts):
                selected.append(accounts[i])
        return selected

    def _select_accounts_by_username(self, usernames: list):
        """Check only accounts whose usernames are in the list."""
        username_set = set(usernames)
        for cb in self._account_checkboxes:
            cb.setChecked(cb.text() in username_set)

    def _on_progress(self, current, total):
        self._completed += 1
        self.progress.setValue(self._completed)

    def _on_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        # Check if there are still failed accounts
        failed = self.task_executor.get_failed_usernames()
        if failed:
            self.btn_retry.setEnabled(True)
        else:
            self.btn_retry.setEnabled(False)

    def _build_actions(self):
        """Build actions list from current checkbox state."""
        used_groups = set()
        create_min = self.spin_create_min.value()
        create_max = max(self.spin_create_max.value(), create_min)
        join_min = self.spin_join_min.value()
        join_max = max(self.spin_join_max.value(), join_min)

        actions = []
        if self.cb_avatar.isChecked():
            actions.append(("Random Avatar", set_random_avatar))
        if self.cb_name.isChecked():
            actions.append(("Random Name", change_profile_name))
        if self.cb_bio.isChecked():
            actions.append(("Random Bio", change_profile_bio))
        if self.cb_background.isChecked():
            actions.append(("Random Background", set_random_background))
        if self.cb_mini_profile.isChecked():
            actions.append(("Random Mini-Profile", set_random_mini_profile))
        if self.cb_avatar_frame.isChecked():
            actions.append(("Random Avatar Frame", set_random_avatar_frame))
        if self.cb_animated_avatar.isChecked():
            actions.append(("Random Animated Avatar", set_random_animated_avatar))
        if self.cb_create_community.isChecked():
            actions.append((
                "Create Community",
                lambda s, a, _cmin=create_min, _cmax=create_max, **kw:
                    create_random_communities(s, a, min_count=_cmin, max_count=_cmax, **kw),
            ))
        if self.cb_join_community.isChecked():
            actions.append((
                "Join Community",
                lambda s, a, _jmin=join_min, _jmax=join_max, **kw:
                    join_random_communities(
                        s, a, min_count=_jmin, max_count=_jmax,
                        used_groups=used_groups, **kw),
            ))
        if self.cb_pointshop.isChecked():
            _ps_cache = {"items": None, "lock": threading.Lock()}
            actions.append((
                "Free Points Shop",
                lambda s, a, _cache=_ps_cache, **kw:
                    claim_free_pointshop_items(s, a, _ps_cache=_cache, **kw),
            ))

        return actions

    def _start(self):
        selected = self._get_selected_accounts()
        if not selected:
            self.log_widget.append_error("[ERROR] No accounts selected.")
            return

        do_friends = self.cb_add_friends.isChecked()
        friends_min = self.spin_friends_min.value()
        friends_max = max(self.spin_friends_max.value(), friends_min)

        actions = self._build_actions()

        if not actions and not do_friends:
            self.log_widget.append_error("[ERROR] No actions selected.")
            return

        # Store action map for retry
        self._last_actions = {name: func for name, func in actions}
        self._last_do_friends = do_friends
        self._last_friends_settings = {"min": friends_min, "max": friends_max}

        self._run_tasks(selected, actions, do_friends, friends_min, friends_max)

    def _retry_failed(self):
        """Retry only the specific failed tasks on accounts that had failures."""
        if not self._last_actions:
            self.log_widget.append_error("[ERROR] No previous actions to retry.")
            return

        all_accounts = list(self.account_manager.accounts)
        retry_plan = self.task_executor.build_retry_plan(all_accounts, self._last_actions)

        if not retry_plan:
            self.log_widget.smart_log("[INFO] Nothing to retry — all tasks succeeded.")
            self.btn_retry.setEnabled(False)
            return

        # Log what we're retrying
        for acc, tasks in retry_plan:
            task_names = ", ".join(name for name, _ in tasks)
            self.log_widget.smart_log(f"[INFO] Retry {acc.username}: {task_names}")

        threads, use_proxies = 1, False
        if self.get_thread_settings:
            threads, use_proxies = self.get_thread_settings()

        delay = 5
        if self.get_delay:
            delay = self.get_delay()

        self.btn_start.setEnabled(False)
        self.btn_retry.setEnabled(False)
        self.btn_cancel.setEnabled(True)

        total_tasks = sum(len(tasks) for _, tasks in retry_plan)
        self.progress.setValue(0)
        self.progress.setMaximum(max(total_tasks, 1))
        self._completed = 0

        # Connect signals only once
        if not self._signals_connected:
            self.task_executor.signals.progress.connect(self._on_progress)
            self.task_executor.signals.finished.connect(self._on_finished)
            self.task_executor.signals.log.connect(self.log_widget.smart_log)
            self._signals_connected = True

        def _run():
            self.task_executor.execute_retry(
                retry_plan,
                delay=delay, use_proxies=use_proxies, threads=threads,
            )

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def _run_tasks(self, selected, actions, do_friends, friends_min, friends_max):
        """Common logic for Start and Retry Failed."""
        threads, use_proxies = 1, False
        if self.get_thread_settings:
            threads, use_proxies = self.get_thread_settings()

        delay = 5
        if self.get_delay:
            delay = self.get_delay()

        self.btn_start.setEnabled(False)
        self.btn_retry.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress.setValue(0)

        progress_total = len(selected) * len(actions)
        if do_friends:
            progress_total += len(selected) * friends_max
        self.progress.setMaximum(max(progress_total, 1))

        self._completed = 0

        # Connect signals only once
        if not self._signals_connected:
            self.task_executor.signals.progress.connect(self._on_progress)
            self.task_executor.signals.finished.connect(self._on_finished)
            self.task_executor.signals.log.connect(self.log_widget.smart_log)
            self._signals_connected = True

        all_accounts = list(self.account_manager.accounts)

        # Signals for friend adding
        self._friend_signals = _FriendSignals()
        self._friend_signals.log.connect(self.log_widget.smart_log)
        self._friend_signals.progress.connect(lambda c, t: self._on_progress(c, t))
        self._friend_signals.finished.connect(self._on_finished)

        def _run():
            if actions:
                self.task_executor.execute_sequential(
                    selected, actions,
                    delay=delay, use_proxies=use_proxies,
                    threads=threads,
                )

            if do_friends:
                cancel_event = self.task_executor._cancel
                add_friends_between_accounts(
                    selected_accounts=selected,
                    all_accounts=all_accounts,
                    min_friends=friends_min,
                    max_friends=friends_max,
                    proxy_manager=self.proxy_manager,
                    use_proxies=use_proxies,
                    log_callback=self._friend_signals.log.emit,
                    progress_callback=self._friend_signals.progress.emit,
                    cancel_event=cancel_event,
                )
                self._friend_signals.finished.emit()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def _cancel(self):
        self.task_executor.cancel()
        self.log_widget.append_error("[CANCELLED] Task cancelled by user.")
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
