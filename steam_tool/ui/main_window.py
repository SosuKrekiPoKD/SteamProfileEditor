import os

from PyQt5.QtWidgets import (
    QMainWindow, QTabWidget, QVBoxLayout, QWidget,
)

from core.account_manager import AccountManager
from core.proxy_manager import ProxyManager
from core.task_executor import TaskExecutor
from ui.actions_tab import ActionsTab
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
        self.settings_tab._refresh_accounts()
        self.settings_tab.reload_proxies()
        self.settings_tab._load_config()  # after reload_proxies so spin_threads max is set
        # Populate account checkboxes on Actions tab immediately
        self.actions_tab.refresh_accounts()

    def _init_ui(self):
        self.setWindowTitle("Steam Account Manager")
        self.setMinimumSize(700, 500)
        self.resize(950, 680)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # Tab widget (fills entire window)
        self.tabs = QTabWidget()

        # Log widget (shared) — writes logs.txt and errors.txt to data/
        self.log_widget = LogWidget(log_dir=self.data_dir)

        # Create tabs
        self.actions_tab = ActionsTab(
            self.account_manager,
            self.task_executor,
            self.log_widget,
            proxy_manager=self.proxy_manager,
            get_thread_settings=lambda: self.settings_tab.get_thread_settings(),
            get_delay=lambda: self.settings_tab.get_delay(),
        )
        self.settings_tab = SettingsTab(
            self.proxy_manager,
            account_manager=self.account_manager,
            log_widget=self.log_widget,
            data_dir=self.data_dir,
        )

        # Connect signals
        self.settings_tab.theme_changed.connect(self._apply_theme)

        # Add tabs: Actions, Settings, Logs
        self.tabs.addTab(self.actions_tab, "Actions")
        self.tabs.addTab(self.settings_tab, "Settings")
        self.tabs.addTab(self.log_widget, "Logs")

        # Refresh accounts when switching to Actions tab
        self.tabs.currentChanged.connect(self._on_tab_changed)

        main_layout.addWidget(self.tabs)

    def _on_tab_changed(self, index: int):
        if index == 0:  # Actions tab
            self.actions_tab.refresh_accounts()

    def _apply_theme(self, theme: str):
        self.current_theme = theme
        if theme == "dark":
            self.setStyleSheet(DARK_THEME)
        else:
            self.setStyleSheet(LIGHT_THEME)
