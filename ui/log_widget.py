import os
import datetime

from PyQt5.QtWidgets import QPlainTextEdit
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtGui import QTextCursor, QTextCharFormat, QColor


class LogWidget(QPlainTextEdit):
    """Read-only log output widget with colored text and file logging.

    Auto-scrolls only if user is at the bottom.
    If user scrolled up to read logs, it stays in place.
    """

    def __init__(self, log_dir: str = "", parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)
        self.setPlaceholderText("Logs will appear here...")

        self._log_dir = log_dir
        self._log_file = os.path.join(log_dir, "logs.txt") if log_dir else ""
        self._error_file = os.path.join(log_dir, "errors.txt") if log_dir else ""

    def _is_scrolled_to_bottom(self) -> bool:
        sb = self.verticalScrollBar()
        return sb.value() >= sb.maximum() - 5

    def _timestamp(self) -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _write_to_file(self, filepath: str, message: str):
        if not filepath:
            return
        try:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(f"[{self._timestamp()}] {message}\n")
        except OSError:
            pass

    @pyqtSlot(str)
    def append_log(self, message: str):
        self._append_colored(message, None)
        self._write_to_file(self._log_file, message)

    @pyqtSlot(str)
    def append_success(self, message: str):
        self._append_colored(message, QColor("#00cc00"))
        self._write_to_file(self._log_file, message)

    @pyqtSlot(str)
    def append_error(self, message: str):
        self._append_colored(message, QColor("#ff4444"))
        self._write_to_file(self._log_file, message)
        self._write_to_file(self._error_file, message)

    def smart_log(self, message: str):
        msg_lower = message.lower()

        error_keywords = [
            "[fail]", "[error]", "[warn]", "failed", "error", "timeout",
            "refused", "denied", "timed out",
            "429", "too many requests", "limited user",
        ]
        success_keywords = [
            "[ok]", "[success]", "accepted", "updated", "uploaded",
            "joined", "created", "logged in",
        ]

        if any(kw in msg_lower for kw in error_keywords):
            self.append_error(message)
        elif any(kw in msg_lower for kw in success_keywords):
            self.append_success(message)
        else:
            self.append_log(message)

    def _append_colored(self, message: str, color):
        # Remember if user was at the bottom before adding text
        was_at_bottom = self._is_scrolled_to_bottom()

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        fmt = QTextCharFormat()
        if color:
            fmt.setForeground(color)

        cursor.insertText(message + "\n", fmt)

        # Only auto-scroll if user was already at the bottom
        if was_at_bottom:
            self.setTextCursor(cursor)
            sb = self.verticalScrollBar()
            sb.setValue(sb.maximum())

    def clear_log(self):
        self.clear()
