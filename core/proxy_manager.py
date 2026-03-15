import os
import threading
from typing import Optional


class ProxyManager:
    """Thread-safe proxy pool with round-robin allocation and rotation on failure."""

    def __init__(self, proxies_file: str):
        self.proxies_file = proxies_file
        self._proxies: list[str] = []
        self._index = 0
        self._lock = threading.Lock()

    def load(self) -> int:
        self._proxies.clear()
        self._index = 0
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
        return len(self._proxies)

    def acquire(self) -> Optional[dict]:
        """Get next proxy in round-robin order. Returns requests-compatible proxy dict."""
        with self._lock:
            if not self._proxies:
                return None
            proxy_str = self._proxies[self._index % len(self._proxies)]
            self._index += 1
            return self._parse_proxy(proxy_str)

    def get_different(self, current_proxy: Optional[dict] = None) -> Optional[dict]:
        """Get a different proxy than the current one (for rotation on failure)."""
        if not self._proxies:
            return None
        if len(self._proxies) == 1:
            return self.acquire()  # only one proxy available
        # Get next proxy, which will be different due to round-robin
        return self.acquire()

    def release_and_get_next(self, failed_proxy: Optional[dict]) -> Optional[dict]:
        """Alias for get_different — get next proxy after failure."""
        return self.get_different(failed_proxy)

    def reset(self):
        """Reset round-robin counter."""
        with self._lock:
            self._index = 0

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
