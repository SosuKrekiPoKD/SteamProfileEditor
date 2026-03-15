import os
import subprocess
import sys

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QHeaderView, QMessageBox,
)
from PyQt5.QtCore import Qt

from core.account_manager import AccountManager


class AccountsTab(QWidget):
    def __init__(self, account_manager: AccountManager, parent=None):
        super().__init__(parent)
        self.account_manager = account_manager
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header = QLabel("Account Management")
        header.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(header)

        # Buttons row
        btn_layout = QHBoxLayout()

        self.btn_open_accounts = QPushButton("Open accounts.txt")
        self.btn_open_accounts.clicked.connect(self._open_accounts_file)
        btn_layout.addWidget(self.btn_open_accounts)

        self.btn_open_mafiles = QPushButton("Open maFiles folder")
        self.btn_open_mafiles.clicked.connect(self._open_mafiles_folder)
        btn_layout.addWidget(self.btn_open_mafiles)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setObjectName("successBtn")
        self.btn_refresh.clicked.connect(self.refresh)
        btn_layout.addWidget(self.btn_refresh)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Status
        self.label_status = QLabel("Accounts: 0")
        layout.addWidget(self.label_status)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["#", "Login", "SteamID", "maFile"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

    def refresh(self):
        accounts = self.account_manager.load()
        self.table.setRowCount(len(accounts))

        for i, acc in enumerate(accounts):
            self.table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.table.setItem(i, 1, QTableWidgetItem(acc.username))
            self.table.setItem(i, 2, QTableWidgetItem(acc.steam_id or "—"))

            mafile_item = QTableWidgetItem("Yes" if acc.has_mafile else "No")
            if acc.has_mafile:
                mafile_item.setForeground(Qt.green)
            else:
                mafile_item.setForeground(Qt.red)
            self.table.setItem(i, 3, mafile_item)

        self.label_status.setText(f"Accounts: {len(accounts)}")

    def _open_accounts_file(self):
        path = self.account_manager.accounts_file
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write("")
        self._open_file(path)

    def _open_mafiles_folder(self):
        path = self.account_manager.mafiles_dir
        os.makedirs(path, exist_ok=True)
        self._open_file(path)

    @staticmethod
    def _open_file(path: str):
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
