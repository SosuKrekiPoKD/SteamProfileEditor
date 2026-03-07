import os
import threading
from typing import Optional


class ProxyManager:
    """Thread-safe proxy pool with atomic allocation."""

    def __init__(self, proxies_file: str):
        self.proxies_file = proxies_file
        self._proxies: list[str] = []
        self._used: set[int] = set()
        self._lock = threading.Lock()

    def load(self) -> int:
        self._proxies.clear()
        self._used.clear()
        if not os.path.exists(self.proxies_file):
            return 0
        with open(self.proxies_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self._proxies.append(line)
        return len(self._proxies)

    @property
    def count(self) -> int:
        return len(self._proxies)

    @property
    def available_count(self) -> int:
        with self._lock:
            return len(self._proxies) - len(self._used)

    def acquire(self) -> Optional[dict]:
        """Get next unused proxy. Returns requests-compatible proxy dict or None."""
        with self._lock:
            for i, proxy_str in enumerate(self._proxies):
                if i not in self._used:
                    self._used.add(i)
                    return self._parse_proxy(proxy_str)
        return None

    def release_and_get_next(self, failed_proxy: Optional[dict]) -> Optional[dict]:
        """Mark current proxy as permanently failed and get next unused one."""
        # The failed proxy stays in _used (permanently excluded)
        return self.acquire()

    def reset(self):
        """Reset all proxy usage tracking."""
        with self._lock:
            self._used.clear()

    @staticmethod
    def _parse_proxy(proxy_str: str) -> dict:
        """Parse login:pass@ip:port into requests proxy dict."""
        proxy_str = proxy_str.strip()
        if "@" in proxy_str:
            creds, host = proxy_str.rsplit("@", 1)
            proxy_url = f"http://{creds}@{host}"
        else:
            proxy_url = f"http://{proxy_str}"
        return {
            "http": proxy_url,
            "https": proxy_url,
        }
