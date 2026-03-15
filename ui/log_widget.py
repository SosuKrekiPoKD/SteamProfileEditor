import os
import datetime

from PyQt5.QtWidgets import QPlainTextEdit
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtGui import QTextCursor, QTextCharFormat, QColor


class LogWidget(QPlainTextEdit):
    """Read-only log output widget with colored text and file logging.

    Auto-scrolls only if user is at the bottom.
    If user scrolled up to read logs, it stays in place.
    Uses signal-driven approach: rangeChanged handles auto-scroll,
    valueChanged tracks whether user scrolled away from bottom.
    """

    def __init__(self, log_dir: str = "", parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)
        self.setPlaceholderText("Logs will appear here...")

        self._log_dir = log_dir
        self._log_file = os.path.join(log_dir, "logs.txt") if log_dir else ""
        self._error_file = os.path.join(log_dir, "errors.txt") if log_dir else ""

        # Auto-scroll state: True = user is at the bottom, scroll with new content
        self._auto_scroll = True
        self._updating = False  # guard against re-entrant signal handling

        sb = self.verticalScrollBar()
        sb.valueChanged.connect(self._on_scroll_value_changed)
        sb.rangeChanged.connect(self._on_scroll_range_changed)

    def _on_scroll_value_changed(self, value):
        """Track whether user scrolled away from bottom."""
        if self._updating:
            return
        sb = self.verticalScrollBar()
        self._auto_scroll = value >= sb.maximum() - 20

    def _on_scroll_range_changed(self, _min, _max):
        """When new content extends the scroll range, auto-scroll if at bottom."""
        if self._auto_scroll:
            self._updating = True
            self.verticalScrollBar().setValue(_max)
            self._updating = False

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

    @pyqtSlot(str)
    def append_info(self, message: str):
        self._append_colored(message, QColor("#4499ff"))
        self._write_to_file(self._log_file, message)

    def smart_log(self, message: str):
        msg_lower = message.lower()

        # Priority 1: explicit tags (most reliable)
        if "[fail]" in msg_lower or "[error]" in msg_lower or "[warn]" in msg_lower:
            self.append_error(message)
        elif "[ok]" in msg_lower or "[success]" in msg_lower:
            self.append_success(message)
        elif "[info]" in msg_lower or "[debug]" in msg_lower:
            self.append_info(message)
        # Priority 2: content-based keywords (fallback)
        elif any(kw in msg_lower for kw in (
            "failed", "error", "timeout", "refused", "denied", "timed out",
            "http 429", "status 429", "too many requests", "limited user",
        )):
            self.append_error(message)
        elif any(kw in msg_lower for kw in (
            "accepted", "updated", "uploaded", "joined", "created", "logged in",
        )):
            self.append_success(message)
        else:
            self.append_log(message)

    def _append_colored(self, message: str, color):
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.End)

        fmt = QTextCharFormat()
        if color:
            fmt.setForeground(color)

        cursor.insertText(message + "\n", fmt)
        # Scrolling is handled by _on_scroll_range_changed signal

    def clear_log(self):
        self._auto_scroll = True
        self.clear()
