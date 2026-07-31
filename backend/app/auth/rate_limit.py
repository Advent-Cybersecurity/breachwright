"""Small bounded login-failure limiter for the single-process application."""

from collections import OrderedDict, deque
from math import ceil
from threading import Lock
import time


class LoginRateLimiter:
    def __init__(
        self,
        max_failures: int = 10,
        window_seconds: int = 300,
        max_keys: int = 5000,
    ):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._failures: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = Lock()

    def _active_failures(self, key: str, now: float) -> deque[float]:
        failures = self._failures.get(key, deque())
        cutoff = now - self.window_seconds
        while failures and failures[0] <= cutoff:
            failures.popleft()
        if failures:
            self._failures[key] = failures
            self._failures.move_to_end(key)
        else:
            self._failures.pop(key, None)
        return failures

    def retry_after(self, key: str, now: float | None = None) -> int | None:
        current = time.monotonic() if now is None else now
        with self._lock:
            failures = self._active_failures(key, current)
            if len(failures) < self.max_failures:
                return None
            return max(1, ceil(failures[0] + self.window_seconds - current))

    def register_attempt(self, key: str, now: float | None = None) -> int | None:
        """Atomically allow and reserve an attempt, or return retry seconds.

        Successful authentication clears the reservation. Failed attempts leave
        it in place, preventing concurrent requests from racing past the limit.
        """
        current = time.monotonic() if now is None else now
        with self._lock:
            failures = self._active_failures(key, current)
            if len(failures) >= self.max_failures:
                return max(
                    1,
                    ceil(failures[0] + self.window_seconds - current),
                )
            if key not in self._failures and len(self._failures) >= self.max_keys:
                self._failures.popitem(last=False)
            failures.append(current)
            self._failures[key] = failures
            self._failures.move_to_end(key)
            return None

    def record_failure(self, key: str, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        with self._lock:
            failures = self._active_failures(key, current)
            if key not in self._failures and len(self._failures) >= self.max_keys:
                self._failures.popitem(last=False)
            failures.append(current)
            self._failures[key] = failures
            self._failures.move_to_end(key)

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


login_rate_limiter = LoginRateLimiter()
