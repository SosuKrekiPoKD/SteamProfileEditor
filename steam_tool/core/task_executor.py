import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from PyQt5.QtCore import QObject, pyqtSignal

from core.account_manager import Account
from core.proxy_manager import ProxyManager
from core.steam_auth import SteamSession, SteamAuthError


MAX_PROXY_RETRIES = 3


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
        # Per-account results: {username: {"status": "ok"/"failed", "results": [...], "error": "..."}}
        self.results = {}
        self._results_lock = threading.Lock()

    def cancel(self):
        self._cancel.set()

    def clear_results(self):
        with self._results_lock:
            self.results.clear()

    def _store_result(self, username, status, results=None, error=None):
        with self._results_lock:
            self.results[username] = {
                "status": status,
                "results": results or [],
                "error": error or "",
            }

    def _merge_result(self, username, new_task_results, login_failed=False, login_error=""):
        """Merge retry results into existing results for an account."""
        with self._results_lock:
            prev = self.results.get(username, {})
            prev_results = {r["task"]: r for r in prev.get("results", [])}

            if login_failed:
                # Login failed again — keep all previous results, mark overall as failed
                self.results[username] = {
                    "status": "failed",
                    "results": list(prev_results.values()),
                    "error": login_error,
                }
                return

            # Update with new retry results
            for new_r in new_task_results:
                prev_results[new_r["task"]] = new_r

            merged = list(prev_results.values())
            all_ok = all(r["status"] == "ok" for r in merged)

            self.results[username] = {
                "status": "ok" if all_ok else "partial",
                "results": merged,
                "error": "",
            }

    def _process_account(self, account, task_funcs, use_proxies, index, total_accounts):
        """Process all tasks for a single account with proxy rotation on login failure."""
        total_tasks = len(task_funcs)
        task_results = []

        self.signals.log.emit(f"\n=== Account: {account.username} ({index+1}/{total_accounts}) ===")

        proxy = None
        if use_proxies:
            proxy = self.proxy_manager.acquire()

        # Login with retry on proxy failure
        session = None
        retries = MAX_PROXY_RETRIES if use_proxies else 1
        last_error = ""

        for attempt in range(retries):
            if self._cancel.is_set():
                self._store_result(account.username, "failed", error="Cancelled")
                return
            try:
                session = SteamSession(
                    username=account.username,
                    password=account.password,
                    mafile_data=account.mafile_data if account.has_mafile else None,
                    proxy=proxy,
                    log_callback=lambda msg: self.signals.log.emit(msg),
                )
                session.login()
                break  # login success
            except (SteamAuthError, Exception) as e:
                last_error = str(e)
                session = None
                if attempt < retries - 1 and use_proxies:
                    self.signals.log.emit(
                        f"[RETRY] {account.username}: login failed ({last_error}), "
                        f"switching proxy (attempt {attempt + 1}/{retries})..."
                    )
                    proxy = self.proxy_manager.get_different(proxy)
                    if proxy is None:
                        self.signals.log.emit(
                            f"[FAIL] {account.username}: no more proxies available"
                        )
                        break

        if session is None:
            self.signals.log.emit(f"[FAIL] {account.username}: login failed: {last_error}")
            self.signals.error.emit(account.username, last_error)
            self._store_result(account.username, "failed", error=f"Login failed: {last_error}")
            for _ in range(total_tasks):
                self.signals.progress.emit(0, 0)
            return

        # Execute all tasks for this account
        log_cb = lambda msg: self.signals.log.emit(msg)
        all_ok = True
        for task_name, task_func in task_funcs:
            if self._cancel.is_set():
                break
            try:
                result = task_func(session, account, log_callback=log_cb)
                self.signals.log.emit(f"[OK] {account.username}: {result}")
                task_results.append({"task": task_name, "status": "ok", "result": str(result)})
            except Exception as e:
                all_ok = False
                self.signals.log.emit(f"[FAIL] {account.username} ({task_name}): {e}")
                self.signals.error.emit(account.username, str(e))
                task_results.append({"task": task_name, "status": "failed", "error": str(e)})
            self.signals.progress.emit(0, 0)

        status = "ok" if all_ok else "partial"
        self._store_result(account.username, status, results=task_results)

    def execute_sequential(self, accounts: list, task_funcs: list,
                           delay: int = 5, use_proxies: bool = False,
                           threads: int = 1):
        """
        Execute ALL tasks for each account.
        threads=1: sequential (one by one with delay).
        threads>1: parallel (multiple accounts at once via ThreadPoolExecutor).
        """
        self._cancel.clear()
        self.clear_results()

        if threads > 1:
            # --- Parallel mode ---
            self.signals.log.emit(
                f"Starting {len(task_funcs)} tasks for {len(accounts)} accounts "
                f"({threads} threads, parallel)..."
            )

            self._executor = ThreadPoolExecutor(max_workers=threads)
            futures = []
            for i, account in enumerate(accounts):
                if self._cancel.is_set():
                    break
                fut = self._executor.submit(
                    self._process_account, account, task_funcs,
                    use_proxies, i, len(accounts),
                )
                futures.append(fut)

            for fut in as_completed(futures):
                if self._cancel.is_set():
                    break

            self._executor.shutdown(wait=True)
            self._executor = None

        else:
            # --- Sequential mode ---
            self.signals.log.emit(
                f"Starting {len(task_funcs)} tasks for {len(accounts)} accounts "
                f"(sequential, {delay}s delay)..."
            )

            for i, account in enumerate(accounts):
                if self._cancel.is_set():
                    break

                if i > 0 and delay > 0:
                    self.signals.log.emit(f"--- Waiting {delay}s before next account ---")
                    for _ in range(delay):
                        if self._cancel.is_set():
                            break
                        time.sleep(1)
                    if self._cancel.is_set():
                        break

                self._process_account(account, task_funcs, use_proxies, i, len(accounts))

        # Log summary
        self._log_summary()
        self.signals.finished.emit()
        self.signals.log.emit("Task finished.")

    def _log_summary(self):
        """Log per-account summary after all tasks complete."""
        if not self.results:
            return

        ok_accounts = []
        partial_accounts = []
        failed_accounts = []

        for username, data in self.results.items():
            if data["status"] == "ok":
                details = ", ".join(r["result"] for r in data["results"] if r.get("result"))
                ok_accounts.append(f"{username}: {details}" if details else username)
            elif data["status"] == "partial":
                ok_tasks = [r["task"] for r in data["results"] if r["status"] == "ok"]
                fail_tasks = [f'{r["task"]} ({r["error"]})' for r in data["results"] if r["status"] == "failed"]
                parts = []
                if ok_tasks:
                    parts.append(f"OK: {', '.join(ok_tasks)}")
                if fail_tasks:
                    parts.append(f"FAILED: {', '.join(fail_tasks)}")
                partial_accounts.append(f"{username}: {'; '.join(parts)}")
            else:
                failed_accounts.append(f"{username}: {data['error']}")

        self.signals.log.emit("\n" + "=" * 50)
        self.signals.log.emit("SUMMARY")
        self.signals.log.emit("=" * 50)

        if ok_accounts:
            self.signals.log.emit(f"\n[OK] Successful ({len(ok_accounts)}):")
            for line in ok_accounts:
                self.signals.log.emit(f"  + {line}")

        if partial_accounts:
            self.signals.log.emit(f"\n[WARN] Partial ({len(partial_accounts)}):")
            for line in partial_accounts:
                self.signals.log.emit(f"  ~ {line}")

        if failed_accounts:
            self.signals.log.emit(f"\n[FAIL] Failed ({len(failed_accounts)}):")
            for line in failed_accounts:
                self.signals.log.emit(f"  - {line}")

        total = len(self.results)
        self.signals.log.emit(
            f"\nTotal: {total} accounts | "
            f"OK: {len(ok_accounts)} | Partial: {len(partial_accounts)} | Failed: {len(failed_accounts)}"
        )
        self.signals.log.emit("=" * 50)

    def get_failed_usernames(self) -> list:
        """Return list of usernames that failed or had partial results."""
        failed = []
        with self._results_lock:
            for username, data in self.results.items():
                if data["status"] in ("failed", "partial"):
                    failed.append(username)
        return failed

    def get_failed_task_names(self, username: str) -> list:
        """Return list of task names that failed for a specific account."""
        with self._results_lock:
            data = self.results.get(username, {})
            if data.get("status") == "failed":
                # Login failed — return all task names from results (or empty if none stored)
                return [r["task"] for r in data.get("results", [])]
            return [r["task"] for r in data.get("results", []) if r["status"] == "failed"]

    def build_retry_plan(self, accounts: list, task_func_map: dict) -> list:
        """Build retry plan: [(account, [(task_name, task_func)])] for failed items only.

        task_func_map: {task_name: task_func} from the original action list.
        """
        plan = []
        with self._results_lock:
            for account in accounts:
                data = self.results.get(account.username)
                if not data or data["status"] == "ok":
                    continue

                if data["status"] == "failed":
                    # Login failed — retry all original tasks
                    tasks = [(name, func) for name, func in task_func_map.items()
                             if func is not None]
                    if tasks:
                        plan.append((account, tasks))
                elif data["status"] == "partial":
                    # Only retry failed tasks
                    failed_names = {r["task"] for r in data["results"]
                                    if r["status"] == "failed"}
                    tasks = [(name, func) for name, func in task_func_map.items()
                             if name in failed_names]
                    if tasks:
                        plan.append((account, tasks))
        return plan

    def _process_account_retry(self, account, task_funcs, use_proxies, index, total):
        """Process retry for a single account — only runs specified failed tasks, merges results."""
        self.signals.log.emit(f"\n=== Retry: {account.username} ({index+1}/{total}) ===")

        proxy = None
        if use_proxies:
            proxy = self.proxy_manager.acquire()

        # Login
        session = None
        retries = MAX_PROXY_RETRIES if use_proxies else 1
        last_error = ""

        for attempt in range(retries):
            if self._cancel.is_set():
                return
            try:
                session = SteamSession(
                    username=account.username,
                    password=account.password,
                    mafile_data=account.mafile_data if account.has_mafile else None,
                    proxy=proxy,
                    log_callback=lambda msg: self.signals.log.emit(msg),
                )
                session.login()
                break
            except (SteamAuthError, Exception) as e:
                last_error = str(e)
                session = None
                if attempt < retries - 1 and use_proxies:
                    self.signals.log.emit(
                        f"[RETRY] {account.username}: login failed ({last_error}), "
                        f"switching proxy (attempt {attempt + 1}/{retries})..."
                    )
                    proxy = self.proxy_manager.get_different(proxy)
                    if proxy is None:
                        break

        if session is None:
            self.signals.log.emit(f"[FAIL] {account.username}: login failed: {last_error}")
            self._merge_result(account.username, [], login_failed=True,
                               login_error=f"Login failed: {last_error}")
            for _ in task_funcs:
                self.signals.progress.emit(0, 0)
            return

        # Execute only the failed tasks
        log_cb = lambda msg: self.signals.log.emit(msg)
        new_results = []
        for task_name, task_func in task_funcs:
            if self._cancel.is_set():
                break
            try:
                result = task_func(session, account, log_callback=log_cb)
                self.signals.log.emit(f"[OK] {account.username}: {result}")
                new_results.append({"task": task_name, "status": "ok", "result": str(result)})
            except Exception as e:
                self.signals.log.emit(f"[FAIL] {account.username} ({task_name}): {e}")
                new_results.append({"task": task_name, "status": "failed", "error": str(e)})
            self.signals.progress.emit(0, 0)

        self._merge_result(account.username, new_results)

    def execute_retry(self, retry_plan, delay=5, use_proxies=False, threads=1):
        """Execute retry plan: [(account, [(task_name, task_func)])]."""
        self._cancel.clear()
        total = len(retry_plan)

        if not retry_plan:
            self.signals.log.emit("Nothing to retry.")
            self.signals.finished.emit()
            return

        task_count = sum(len(tasks) for _, tasks in retry_plan)
        self.signals.log.emit(
            f"Retrying {task_count} failed tasks on {total} accounts..."
        )

        if threads > 1:
            self._executor = ThreadPoolExecutor(max_workers=threads)
            futures = []
            for i, (account, tasks) in enumerate(retry_plan):
                if self._cancel.is_set():
                    break
                fut = self._executor.submit(
                    self._process_account_retry, account, tasks,
                    use_proxies, i, total,
                )
                futures.append(fut)
            for fut in as_completed(futures):
                if self._cancel.is_set():
                    break
            self._executor.shutdown(wait=True)
            self._executor = None
        else:
            for i, (account, tasks) in enumerate(retry_plan):
                if self._cancel.is_set():
                    break
                if i > 0 and delay > 0:
                    self.signals.log.emit(f"--- Waiting {delay}s before next account ---")
                    for _ in range(delay):
                        if self._cancel.is_set():
                            break
                        time.sleep(1)
                    if self._cancel.is_set():
                        break
                self._process_account_retry(account, tasks, use_proxies, i, total)

        self._log_summary()
        self.signals.finished.emit()
        self.signals.log.emit("Task finished.")
