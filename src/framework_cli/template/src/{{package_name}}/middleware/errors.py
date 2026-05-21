"""Global exception handling → RFC 7807 Problem Details (application/problem+json).

Registered on the app by `register_exception_handlers`. Three handlers give every error class
a consistent body: unhandled exceptions (500, detail never leaked), HTTPException (its status +
detail), and request validation errors (422 + the field errors). Each response carries the
request correlation id (read from request.state, set by ObservabilityMiddleware) so a failing
response is traceable to its logs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from ..logging_config import get_logger
from ..observability.recoverability import recoverability

if TYPE_CHECKING:
    from fastapi import FastAPI

_PROBLEM_MEDIA_TYPE = "application/problem+json"
_log = get_logger()


def _problem(
    *, status: int, title: str, detail: str, request: Request, **extra: Any
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
    }
    cid = getattr(request.state, "correlation_id", None)
    if cid:
        body["correlation_id"] = cid
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type=_PROBLEM_MEDIA_TYPE)


async def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    recoverability.record_unhandled_exception()
    _log.error(
        "unhandled_exception",
        error_type=type(exc).__name__,
        method=request.method,
        path=request.url.path,
    )
    # Never leak internal exception text to the client.
    return _problem(
        status=500,
        title="Internal Server Error",
        detail="An unexpected error occurred.",
        request=request,
    )


async def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # registered only for this type
    detail = exc.detail if isinstance(exc.detail, str) else "HTTP error"
    return _problem(
        status=exc.status_code,
        title=detail,
        detail=detail,
        request=request,
    )


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # registered only for this type
    return _problem(
        status=422,
        title="Unprocessable Entity",
        detail="Request validation failed.",
        request=request,
        errors=exc.errors(),
    )


def register_exception_handlers(app: "FastAPI") -> None:
    """Wire the RFC 7807 handlers onto the app. Call once in create_app."""
    app.add_exception_handler(Exception, handle_unhandled_exception)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
