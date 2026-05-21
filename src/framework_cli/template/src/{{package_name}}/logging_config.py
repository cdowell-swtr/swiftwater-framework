"""structlog configuration and the request correlation-id contextvar.

A correlation id is generated at the request boundary (see middleware/observability.py)
and stored in this contextvar; `add_correlation_id` injects it into every log entry
emitted within that request's async context.
"""

from __future__ import annotations

import contextvars
import logging

import structlog

correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)


def add_correlation_id(logger, method_name, event_dict):  # noqa: ANN001, ARG001
    cid = correlation_id_var.get()
    if cid is not None:
        event_dict["correlation_id"] = cid
    return event_dict


def configure_logging(level: str) -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_correlation_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric),
        cache_logger_on_first_use=True,
    )


def get_logger() -> structlog.stdlib.BoundLogger:
    return structlog.get_logger()
