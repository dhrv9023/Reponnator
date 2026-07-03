"""
utils/rate_limiter.py — GitHub API Rate Limit Handler

Tracks the current rate-limit state from PyGithub responses and automatically
pauses execution when the remaining quota is critically low.

Usage:
    from utils.rate_limiter import RateLimiter
    limiter = RateLimiter(github_client)  # pass authenticated Github() object
    limiter.check_and_wait()              # call before any API operation
"""

import time
import threading
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Optional

from github import Github, GithubException, RateLimitExceededException

from utils.logger import get_logger

logger = get_logger(__name__)


class RateLimitStatus:
    """Snapshot of the current GitHub API rate limit state."""

    __slots__ = ("limit", "remaining", "reset_at", "used")

    def __init__(self, limit: int, remaining: int, reset_at: datetime, used: int) -> None:
        self.limit = limit
        self.remaining = remaining
        self.reset_at = reset_at
        self.used = used

    def seconds_until_reset(self) -> float:
        """Return seconds remaining until the rate-limit window resets."""
        now = datetime.now(tz=timezone.utc)
        delta = (self.reset_at - now).total_seconds()
        return max(0.0, delta)

    def __repr__(self) -> str:
        return (
            f"RateLimitStatus(remaining={self.remaining}/{self.limit}, "
            f"resets_in={self.seconds_until_reset():.0f}s)"
        )


class RateLimiter:
    """
    Thread-safe GitHub API rate limit manager.

    Wraps a :class:`github.Github` instance and provides:
    - Proactive pre-request checking (``check_and_wait``).
    - Automatic refresh of the rate-limit state from API responses.
    - A ``@rate_limited`` decorator factory for wrapping API callables.
    - Detailed logging of wait periods and quota consumption.

    Args:
        github_client: An authenticated (or anonymous) :class:`github.Github` object.
        buffer: Pause execution when ``remaining`` drops below this threshold.
    """

    def __init__(self, github_client: Github, buffer: int = 10) -> None:
        from config import RATE_LIMIT_BUFFER
        self._gh = github_client
        self._buffer = buffer or RATE_LIMIT_BUFFER
        self._lock = threading.Lock()
        self._status: Optional[RateLimitStatus] = None
        self._refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_and_wait(self) -> None:
        """
        Block the calling thread until the rate-limit quota is safe to use.

        If the remaining quota is at or below the configured buffer, compute
        how long to wait for the window to reset and sleep accordingly.
        """
        with self._lock:
            status = self._fetch_status()

        if status.remaining <= self._buffer:
            wait_seconds = status.seconds_until_reset() + 2  # small safety margin
            logger.warning(
                "GitHub API rate limit low (%d/%d remaining). "
                "Waiting %.0f seconds until reset at %s.",
                status.remaining,
                status.limit,
                wait_seconds,
                status.reset_at.strftime("%H:%M:%S UTC"),
            )
            for remaining_wait in range(int(wait_seconds), 0, -15):
                logger.info("Rate limit reset in ~%d seconds…", remaining_wait)
                time.sleep(min(15, remaining_wait))
            logger.info("Rate limit window has reset. Resuming.")
            self._refresh()

    def get_rate_limit_status(self) -> dict[str, Any]:
        """
        Return current rate-limit state as a plain dictionary.

        Returns:
            Dict with keys: ``remaining``, ``limit``, ``used``,
            ``reset_time`` (ISO-8601 string), ``seconds_until_reset``.
        """
        status = self._fetch_status()
        return {
            "remaining": status.remaining,
            "limit": status.limit,
            "used": status.used,
            "reset_time": status.reset_at.isoformat(),
            "seconds_until_reset": round(status.seconds_until_reset(), 1),
        }

    def update_from_exception(self, exc: GithubException) -> None:
        """
        Handle an unexpected rate-limit exception returned mid-request.

        Call this inside an ``except RateLimitExceededException`` block so
        the limiter can immediately refresh its internal state and wait.

        Args:
            exc: The caught :class:`github.RateLimitExceededException`.
        """
        logger.error(
            "Unexpected rate-limit exception encountered: %s. "
            "Refreshing quota state and waiting.",
            exc,
        )
        self._refresh()
        self.check_and_wait()

    def rate_limited(self, func: Callable) -> Callable:
        """
        Decorator: call ``check_and_wait`` before each invocation of *func*.

        Usage::

            @limiter.rate_limited
            def fetch_something():
                ...

        Args:
            func: The callable to wrap.

        Returns:
            Wrapped callable with automatic rate-limit guarding.
        """
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            self.check_and_wait()
            try:
                result = func(*args, **kwargs)
                self._refresh_if_stale()
                return result
            except RateLimitExceededException as exc:
                self.update_from_exception(exc)
                # Retry once after waiting
                return func(*args, **kwargs)
        return wrapper

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        """Fetch current rate-limit data from the GitHub API."""
        try:
            rl = self._gh.get_rate_limit()
            # PyGithub 2.x: RateLimitOverview exposes resources.core
            # PyGithub 1.x: exposed rl.core directly — support both
            if hasattr(rl, "resources") and hasattr(rl.resources, "core"):
                core = rl.resources.core
            elif hasattr(rl, "core"):
                core = rl.core
            else:
                raise AttributeError("Unrecognised rate-limit response structure.")
            self._status = RateLimitStatus(
                limit=core.limit,
                remaining=core.remaining,
                reset_at=core.reset.replace(tzinfo=timezone.utc),
                used=core.limit - core.remaining,
            )
            logger.debug(
                "Rate limit refreshed: %d/%d remaining, resets in %.0fs.",
                self._status.remaining,
                self._status.limit,
                self._status.seconds_until_reset(),
            )
        except GithubException as exc:
            logger.warning("Could not refresh rate limit status: %s", exc)
            if self._status is None:
                # Create a safe default so we never operate with None
                self._status = RateLimitStatus(
                    limit=60,
                    remaining=60,
                    reset_at=datetime.now(tz=timezone.utc),
                    used=0,
                )

    def _refresh_if_stale(self) -> None:
        """Periodically re-sync rate-limit state (every 50 decrements)."""
        if self._status is not None:
            self._status.remaining -= 1
            if self._status.remaining % 50 == 0:
                self._refresh()

    def _fetch_status(self) -> RateLimitStatus:
        """Return current status, refreshing if not yet initialised."""
        if self._status is None:
            self._refresh()
        assert self._status is not None  # guaranteed by _refresh()
        return self._status
