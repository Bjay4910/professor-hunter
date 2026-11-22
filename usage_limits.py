"""
Search limits for the shared (host-paid) API key.

  - Per visitor: SESSION_SEARCH_LIMIT searches per browser session (default 5).
  - Global:      DAILY_SEARCH_LIMIT searches per UTC day across all visitors (default 100).

Searches run with the visitor's own Anthropic key skip both caps.

The daily counter lives in this process's memory: it resets when the app
restarts and is not shared between multiple app processes.
"""

import os
import threading
from datetime import datetime, timezone

SESSION_COUNT_KEY = "_searches_this_session"


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, default))
        return value if value >= 0 else default
    except (TypeError, ValueError):
        return default


def session_limit() -> int:
    return _env_int("SESSION_SEARCH_LIMIT", 5)


def daily_limit() -> int:
    return _env_int("DAILY_SEARCH_LIMIT", 100)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class DailyCounter:
    """Thread-safe count of shared-key searches for the current UTC day."""

    def __init__(self, today_fn=_today):
        self._today_fn = today_fn
        self._day = today_fn()
        self._count = 0
        self._lock = threading.Lock()

    def _roll(self):
        today = self._today_fn()
        if today != self._day:
            self._day, self._count = today, 0

    def count(self) -> int:
        with self._lock:
            self._roll()
            return self._count

    def try_consume(self, limit: int) -> bool:
        with self._lock:
            self._roll()
            if self._count >= limit:
                return False
            self._count += 1
            return True


# One counter per app process, shared by every browser session.
DAILY_COUNTER = DailyCounter()


def looks_like_api_key(key: str) -> bool:
    return bool(key) and key.strip().startswith("sk-ant-") and len(key.strip()) > 20


def check_and_consume(session_state, own_key: str = "", counter: DailyCounter = None):
    """
    Decide whether a search may run, and count it if it uses the shared key.
    Returns (allowed: bool, message: str). `message` never contains the key.
    """
    if own_key:
        if not looks_like_api_key(own_key):
            return False, "That doesn't look like an Anthropic API key (it should start with `sk-ant-`)."
        return True, ""

    counter = counter or DAILY_COUNTER
    used = session_state.get(SESSION_COUNT_KEY, 0)
    if used >= session_limit():
        return False, (
            f"You've used all {session_limit()} free searches for this session. "
            "Add your own Anthropic API key in the sidebar to keep searching."
        )
    if not counter.try_consume(daily_limit()):
        return False, (
            f"The free daily limit of {daily_limit()} searches has been reached. "
            "Try again tomorrow, or add your own Anthropic API key in the sidebar."
        )
    session_state[SESSION_COUNT_KEY] = used + 1
    return True, ""


def remaining_this_session(session_state) -> int:
    return max(0, session_limit() - session_state.get(SESSION_COUNT_KEY, 0))


def redact(text: str, secret: str) -> str:
    """Remove a secret from text before it is logged or shown."""
    if secret:
        text = text.replace(secret, "[redacted]")
    return text
