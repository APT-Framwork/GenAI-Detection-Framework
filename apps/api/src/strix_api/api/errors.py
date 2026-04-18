"""Typed exception hierarchy mapped to RFC 7807 Problem+JSON responses.

Coherence-checklist item in §13: every error response must be Problem+JSON
shaped `{ type, title, status, detail, instance, code }`. FastAPI's default
`{ "detail": "..." }` envelope is explicitly rejected — this module owns the
single mapping from typed exceptions to HTTP.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------- Problem+JSON


class Problem(BaseModel):
    """RFC 7807 response body."""

    type: str = Field(default="about:blank")
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    code: str | None = None
    extra: dict[str, Any] | None = None


# ---------------------------------------------------------------- exceptions


class StrixError(Exception):
    """Base class. Subclasses set `status_code`, `title`, `code`."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    title: str = "Internal Server Error"
    code: str = "INTERNAL"
    type_uri: str = "about:blank"

    def __init__(self, detail: str | None = None, extra: dict[str, Any] | None = None):
        self.detail = detail
        self.extra = extra
        super().__init__(detail or self.title)


class NotFoundError(StrixError):
    status_code = status.HTTP_404_NOT_FOUND
    title = "Not Found"
    code = "NOT_FOUND"


class ValidationFailedError(StrixError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    title = "Validation Failed"
    code = "VALIDATION_FAILED"


class UpstreamUnavailableError(StrixError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    title = "Upstream Unavailable"
    code = "UPSTREAM_DOWN"


class ModelRegistryError(StrixError):
    """Model pathology (missing file, checksum mismatch, loader bug)."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    title = "Model Registry Error"
    code = "MODEL_REGISTRY"


class RateLimitedError(StrixError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    title = "Rate Limited"
    code = "RATE_LIMITED"


# ---------------------------------------------------------------- handlers


def _problem_response(
    request: Request,
    status_code: int,
    title: str,
    code: str,
    detail: str | None = None,
    extra: dict[str, Any] | None = None,
    type_uri: str = "about:blank",
) -> JSONResponse:
    body = Problem(
        type=type_uri,
        title=title,
        status=status_code,
        detail=detail,
        instance=str(request.url),
        code=code,
        extra=extra,
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(exclude_none=True),
        media_type="application/problem+json",
    )


async def _strix_exception_handler(request: Request, exc: StrixError) -> JSONResponse:
    return _problem_response(
        request,
        exc.status_code,
        exc.title,
        exc.code,
        detail=exc.detail,
        extra=exc.extra,
        type_uri=exc.type_uri,
    )


async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return _problem_response(
        request,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "Validation Failed",
        "VALIDATION_FAILED",
        detail="Request does not match schema.",
        extra={"errors": exc.errors()},
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Never leak stack traces to clients; logging already captured them.
    return _problem_response(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "Internal Server Error",
        "INTERNAL",
        detail="An unexpected error occurred.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Wire our typed exceptions to Problem+JSON."""

    # Ordering matters: specific before generic.
    handler_strix: Callable[[Request, Exception], Awaitable[JSONResponse]] = (
        _strix_exception_handler  # type: ignore[assignment]
    )
    app.add_exception_handler(StrixError, handler_strix)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
