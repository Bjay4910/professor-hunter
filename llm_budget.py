"""
Single choke point for every paid Anthropic API call.

Every model call in the app (Haiku in tools.py, Sonnet in agent.py) goes through
`LLMBudget.create()`. The SDK's own automatic retries are disabled
(`max_retries=0`) so that every HTTP attempt, including retries, is made here
and counted against the same per-run limits.

Limits (override with environment variables):
  LLM_MAX_CALLS_PER_RUN          max request attempts per search, retries included
  LLM_MAX_OUTPUT_TOKENS_PER_RUN  max sum of `max_tokens` reserved per search
  LLM_MAX_RETRIES                retries per call on 429 / 5xx / connection errors
"""

import os
import time
import threading

from anthropic import (
    Anthropic,
    APIConnectionError,
    APIStatusError,
    RateLimitError,
)


class BudgetExceeded(RuntimeError):
    """Raised when a call would go over the per-run limits."""


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


_client = None
_client_lock = threading.Lock()


def get_client() -> Anthropic:
    """One shared client for the whole app, with SDK auto-retry turned off."""
    global _client
    with _client_lock:
        if _client is None:
            _client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"), max_retries=0)
        return _client


class LLMBudget:
    def __init__(self, max_calls=None, max_output_tokens=None, max_retries=None, api_key=None):
        # A visitor's own key gets its own client, never the shared singleton,
        # and is kept only on that client object for the length of one search.
        self._client = Anthropic(api_key=api_key, max_retries=0) if api_key else None
        self.max_calls = max_calls if max_calls is not None else _env_int("LLM_MAX_CALLS_PER_RUN", 80)
        self.max_output_tokens = (
            max_output_tokens if max_output_tokens is not None
            else _env_int("LLM_MAX_OUTPUT_TOKENS_PER_RUN", 40000)
        )
        self.max_retries = max_retries if max_retries is not None else _env_int("LLM_MAX_RETRIES", 1)

        self.calls = 0                 # attempts made (retries included)
        self.reserved_output_tokens = 0
        self.input_tokens = 0          # measured from response.usage
        self.output_tokens = 0
        self.skipped = 0               # calls refused because of the limits
        # Headroom held back by intermediate (Haiku) steps for the final call.
        self.reserve_calls = 0
        self.reserve_tokens = 0
        self._lock = threading.Lock()

    # -- accounting ---------------------------------------------------------

    def can_afford(self, max_tokens: int, keep_calls: int = 0, keep_tokens: int = 0) -> bool:
        """True if one more attempt of `max_tokens` fits, leaving the given reserve."""
        return (
            self.calls + 1 + keep_calls <= self.max_calls
            and self.reserved_output_tokens + max_tokens + keep_tokens <= self.max_output_tokens
        )

    def _reserve(self, max_tokens: int, keep_calls: int, keep_tokens: int) -> None:
        with self._lock:
            if not self.can_afford(max_tokens, keep_calls, keep_tokens):
                self.skipped += 1
                raise BudgetExceeded(
                    f"LLM budget reached: {self.calls}/{self.max_calls} calls, "
                    f"{self.reserved_output_tokens}/{self.max_output_tokens} output tokens reserved"
                )
            self.calls += 1
            self.reserved_output_tokens += max_tokens

    # -- the only place a paid request is sent -----------------------------

    def create(self, *, max_tokens: int, keep_calls: int = 0, keep_tokens: int = 0, **kwargs):
        """
        Wrapper around client.messages.create. Each attempt (first try and each
        retry) is reserved against the budget before it is sent.
        `keep_calls` / `keep_tokens` hold back headroom for a later call
        (used so Haiku steps can't starve the final Sonnet call).
        """
        attempt = 0
        while True:
            self._reserve(max_tokens, keep_calls, keep_tokens)
            try:
                resp = (self._client or get_client()).messages.create(max_tokens=max_tokens, **kwargs)
            except (RateLimitError, APIConnectionError) as e:
                err = e
            except APIStatusError as e:
                if e.status_code < 500:
                    raise
                err = e
            else:
                usage = getattr(resp, "usage", None)
                if usage is not None:
                    with self._lock:
                        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
                        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
                return resp

            attempt += 1
            if attempt > self.max_retries:
                raise err
            time.sleep(min(2 ** attempt, 10))

    def summary(self) -> str:
        return (
            f"LLM usage: {self.calls}/{self.max_calls} calls (retries included), "
            f"{self.input_tokens} input + {self.output_tokens} output tokens measured, "
            f"{self.reserved_output_tokens}/{self.max_output_tokens} output tokens reserved, "
            f"{self.skipped} calls skipped by limit"
        )
