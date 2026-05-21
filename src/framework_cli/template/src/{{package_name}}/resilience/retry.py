"""Retry with exponential backoff + jitter, built on tenacity.

`with_retry` is a decorator factory. It logs every retry and records recoverability metrics:
each scheduled retry, whether the call eventually recovered (succeeded after >=1 retry), and
whether it exhausted all attempts. Defaults are sensible for an I/O call; override per use.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import TypeVar

from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from ..logging_config import get_logger
from ..observability.recoverability import recoverability

T = TypeVar("T")
_log = get_logger()


def with_retry(
    *,
    max_attempts: int = 3,
    initial_wait: float = 0.1,
    max_wait: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorate a callable to retry on `exceptions` with backoff + jitter.

    Re-raises the original exception once attempts are exhausted (no tenacity wrapper exception).
    """

    def _before_sleep(state: RetryCallState) -> None:
        recoverability.record_retry_attempt()
        _log.warning(
            "retrying",
            attempt=state.attempt_number,
            callable=getattr(state.fn, "__name__", "?"),
        )

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args: object, **kwargs: object) -> T:
            retryer = Retrying(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential_jitter(initial=initial_wait, max=max_wait),
                retry=retry_if_exception_type(exceptions),
                before_sleep=_before_sleep,
                reraise=True,
            )
            try:
                result: T = retryer(fn, *args, **kwargs)
            except exceptions:
                recoverability.record_retry_exhausted()
                raise
            if retryer.statistics.get("attempt_number", 1) > 1:
                recoverability.record_retry_recovered()
            return result

        return wrapper

    return decorator
