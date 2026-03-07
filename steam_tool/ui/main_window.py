import os

from PyQt5.QtWidgets import (
    QMainWindow, QTabWidget, QVBoxLayout, QWidget, QSplitter,
)
from PyQt5.QtCore import Qt

from core.account_manager import AccountManager
from core.proxy_manager import ProxyManager
from core.task_executor import TaskExecutor
from ui.accounts_tab import AccountsTab
from ui.actions_tab import ActionsTab
from ui.friends_tab import FriendsTab
from ui.settings_tab import SettingsTab
from ui.log_widget import LogWidget
from ui.themes import DARK_THEME, LIGHT_THEME


class MainWindow(QMainWindow):
    def __init__(self, data_dir: str):
        super().__init__()
        self.data_dir = data_dir
        self.current_theme = "dark"

        # Core managers
        self.account_manager = AccountManager(data_dir)
        self.proxy_manager = ProxyManager(os.path.join(data_dir, "proxies.txt"))
        self.task_executor = TaskExecutor(self.proxy_manager)

        self._init_ui()
        self._apply_theme("dark")

        # Initial load
        self.accounts_tab.refresh()
        self.settings_tab.reload_proxies()

    def _init_ui(self):
        self.setWindowTitle("Steam Account Manager")
        self.setMinimumSize(900, 650)
        self.resize(1000, 700)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # Splitter: tabs on top, log on bottom
        splitter = QSplitter(Qt.Vertical)

        # Tab widget
        self.tabs = QTabWidget()

        # Log widget (shared) — writes logs.txt and errors.txt to data/
        self.log_widget = LogWidget(log_dir=self.data_dir)

        # Create tabs
        self.accounts_tab = AccountsTab(self.account_manager)
        self.actions_tab = ActionsTab(
            self.account_manager,
            self.task_executor,
            self.log_widget,
            get_thread_settings=lambda: self.settings_tab.get_thread_settings(),
            get_delay=lambda: self.settings_tab.get_delay(),
        )
        self.friends_tab = FriendsTab(
            self.account_manager,
            self.proxy_manager,
            self.log_widget,
            get_thread_settings=lambda: self.settings_tab.get_thread_settings(),
        )
        self.settings_tab = SettingsTab(self.proxy_manager, log_widget=self.log_widget)

        # Connect signals
        self.settings_tab.theme_changed.connect(self._apply_theme)

        # Add tabs
        self.tabs.addTab(self.accounts_tab, "Accounts")
        self.tabs.addTab(self.actions_tab, "Actions")
        self.tabs.addTab(self.friends_tab, "Friends")
        self.tabs.addTab(self.settings_tab, "Settings")

        # Update friends tab when switching to it
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Allow both widgets to shrink/grow freely
        self.tabs.setMinimumHeight(150)
        self.log_widget.setMinimumHeight(80)

        splitter.addWidget(self.tabs)
        splitter.addWidget(self.log_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([400, 250])
        splitter.setChildrenCollapsible(False)

        main_layout.addWidget(splitter)

    def _on_tab_changed(self, index: int):
        if index == 1:  # Actions tab
            self.actions_tab.refresh_accounts()
        elif index == 2:  # Friends tab
            self.friends_tab.refresh_accounts()

    def _apply_theme(self, theme: str):
        self.current_theme = theme
        if theme == "dark":
            self.setStyleSheet(DARK_THEME)
        else:
            self.setStyleSheet(LIGHT_THEME)
