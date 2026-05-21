"""structlog configuration and the request correlation-id contextvar.

A correlation id is generated at the request boundary (see middleware/observability.py)
and stored in this contextvar; `add_correlation_id` injects it into every log entry
emitted within that request's async context.
"""

from __future__ import annotations

import contextvars
import logging

import structlog
from opentelemetry import trace

correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)


def add_correlation_id(logger, method_name, event_dict):  # noqa: ANN001, ARG001
    cid = correlation_id_var.get()
    if cid is not None:
        event_dict["correlation_id"] = cid
    return event_dict


def add_trace_context(logger, method_name, event_dict):  # noqa: ANN001, ARG001
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict


def configure_logging(level: str) -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_correlation_id,
            add_trace_context,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric),
        cache_logger_on_first_use=True,
    )


def get_logger() -> structlog.stdlib.BoundLogger:
    return structlog.get_logger()
