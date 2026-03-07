import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from PyQt5.QtCore import QObject, pyqtSignal

from core.account_manager import Account
from core.proxy_manager import ProxyManager
from core.steam_auth import SteamSession, SteamAuthError


class TaskSignals(QObject):
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # current, total
    finished = pyqtSignal()
    error = pyqtSignal(str, str)  # account, error message


class TaskExecutor:
    """Executes tasks across accounts with optional multi-threading and proxies."""

    def __init__(self, proxy_manager: ProxyManager):
        self.proxy_manager = proxy_manager
        self.signals = TaskSignals()
        self._cancel = threading.Event()
        self._executor: Optional[ThreadPoolExecutor] = None

    def cancel(self):
        self._cancel.set()

    def _run_for_account(self, account: Account, task_func: Callable,
                         use_proxies: bool = False, **task_kwargs):
        """Run a single task for a single account."""
        if self._cancel.is_set():
            return account.username, "Cancelled"

        proxy = None
        if use_proxies:
            proxy = self.proxy_manager.acquire()
            if proxy is None:
                return account.username, "No available proxy"

        max_retries = 3 if use_proxies else 1
        last_error = ""

        for attempt in range(max_retries):
            if self._cancel.is_set():
                return account.username, "Cancelled"
            try:
                session = SteamSession(
                    username=account.username,
                    password=account.password,
                    mafile_data=account.mafile_data if account.has_mafile else None,
                    proxy=proxy,
                    log_callback=lambda msg: self.signals.log.emit(msg),
                )
                session.login()
                result = task_func(session, account, **task_kwargs)
                self.signals.log.emit(f"[OK] {account.username}: {result}")
                return account.username, result
            except (SteamAuthError, Exception) as e:
                last_error = str(e)
                self.signals.log.emit(
                    f"[RETRY] {account.username}: {last_error} "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                if use_proxies and proxy:
                    proxy = self.proxy_manager.release_and_get_next(proxy)
                    if proxy is None:
                        break

        self.signals.error.emit(account.username, last_error)
        self.signals.log.emit(f"[FAIL] {account.username}: {last_error}")
        return account.username, f"Failed: {last_error}"

    def execute(self, accounts: list, task_func: Callable,
                threads: int = 1, use_proxies: bool = False, **task_kwargs):
        """Execute task_func for each account using ThreadPoolExecutor."""
        self._cancel.clear()
        total = len(accounts)
        completed = 0

        self.signals.log.emit(f"Starting task for {total} accounts ({threads} threads)...")

        self._executor = ThreadPoolExecutor(max_workers=threads)
        futures = {
            self._executor.submit(
                self._run_for_account, acc, task_func, use_proxies, **task_kwargs
            ): acc
            for acc in accounts
        }

        for future in as_completed(futures):
            if self._cancel.is_set():
                break
            completed += 1
            self.signals.progress.emit(completed, total)

        self._executor.shutdown(wait=False)
        self._executor = None
        self.signals.finished.emit()
        self.signals.log.emit("Task finished.")

    def execute_sequential(self, accounts: list, task_funcs: list,
                           delay: int = 5, use_proxies: bool = False):
        """
        Execute ALL tasks for one account, then wait delay, then next account.
        task_funcs: list of (name, callable) tuples.
        """
        self._cancel.clear()
        total = len(accounts) * len(task_funcs)
        completed = 0

        self.signals.log.emit(
            f"Starting {len(task_funcs)} tasks for {len(accounts)} accounts "
            f"(sequential, {delay}s delay)..."
        )

        for i, account in enumerate(accounts):
            if self._cancel.is_set():
                break

            # Wait before next account (skip first)
            if i > 0 and delay > 0:
                self.signals.log.emit(f"--- Waiting {delay}s before next account ---")
                for _ in range(delay):
                    if self._cancel.is_set():
                        break
                    time.sleep(1)
                if self._cancel.is_set():
                    break

            self.signals.log.emit(f"\n=== Account: {account.username} ({i+1}/{len(accounts)}) ===")

            # Login once for all tasks
            proxy = None
            if use_proxies:
                proxy = self.proxy_manager.acquire()

            session = None
            try:
                session = SteamSession(
                    username=account.username,
                    password=account.password,
                    mafile_data=account.mafile_data if account.has_mafile else None,
                    proxy=proxy,
                    log_callback=lambda msg: self.signals.log.emit(msg),
                )
                session.login()
            except (SteamAuthError, Exception) as e:
                self.signals.log.emit(f"[FAIL] {account.username}: login failed: {e}")
                self.signals.error.emit(account.username, str(e))
                completed += len(task_funcs)
                self.signals.progress.emit(completed, total)
                continue

            # Run all tasks on this account
            log_cb = lambda msg: self.signals.log.emit(msg)
            for task_name, task_func in task_funcs:
                if self._cancel.is_set():
                    break
                try:
                    result = task_func(session, account, log_callback=log_cb)
                    self.signals.log.emit(f"[OK] {account.username}: {result}")
                except Exception as e:
                    self.signals.log.emit(f"[FAIL] {account.username} ({task_name}): {e}")
                    self.signals.error.emit(account.username, str(e))
                completed += 1
                self.signals.progress.emit(completed, total)

        self.signals.finished.emit()
        self.signals.log.emit("Task finished.")
