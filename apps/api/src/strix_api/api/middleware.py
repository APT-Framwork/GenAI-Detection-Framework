"""Auth + CSRF middleware (P4-9 / P4-10).

Two responsibilities:

1. **Authentication** — every request to a path under `/api/v1/` MUST carry
   a valid access token (Bearer header OR `strix_access` cookie), with the
   following exceptions whitelisted:
     /health, /metrics, /api/v1/openapi.json, /api/v1/docs, /api/v1/redoc,
     /api/v1/auth/login, /api/v1/auth/refresh, /api/v1/auth/logout

2. **CSRF (double-submit)** — on every mutating method (POST/PUT/PATCH/DELETE)
   the `X-CSRF-Token` header must equal the `strix_csrf` cookie. Routes
   under `/api/v1/auth/*` are exempt (the user has no CSRF token before login).

The dev-skip is honored only when `ENV=dev` and `AUTH_DEV_SKIP_AUTH=true`,
matching the dependency-injection helper.
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from strix_api.api.errors import Problem
from strix_api.services.auth import (
    CsrfMismatchError,
    InvalidTokenError,
    decode_token,
    verify_csrf,
)
from strix_api.settings import Settings, get_settings

# Anything under these path PREFIXES is exempt from auth (everyone can hit them).
_AUTH_EXEMPT_PREFIXES: tuple[str, ...] = (
    "/health",
    "/metrics",
    "/api/v1/openapi.json",
    "/api/v1/docs",
    "/api/v1/redoc",
    "/docs",  # FastAPI's default docs alias
    "/redoc",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/api/v1/auth/logout",
)

# CSRF is checked only for mutating methods.
_CSRF_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# CSRF is exempt under /api/v1/auth/* (user has no CSRF token until they log in).
_CSRF_EXEMPT_PREFIXES: tuple[str, ...] = ("/api/v1/auth/",)

_ACCESS_COOKIE = "strix_access"
_CSRF_COOKIE = "strix_csrf"
_CSRF_HEADER = "X-CSRF-Token"


def _problem_response(
    request: Request,
    status_code: int,
    title: str,
    code: str,
    detail: str | None = None,
) -> JSONResponse:
    body = Problem(
        type="about:blank",
        title=title,
        status=status_code,
        detail=detail,
        instance=str(request.url),
        code=code,
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(exclude_none=True),
        media_type="application/problem+json",
    )


def _path_in(prefixes: Iterable[str], path: str) -> bool:
    return any(path == p or path.startswith(p + "/") or path.startswith(p) for p in prefixes)


class AuthMiddleware(BaseHTTPMiddleware):
    """Reject requests that don't carry a valid access token (with whitelist)."""

    def __init__(self, app: ASGIApp, *, settings: Settings | None = None) -> None:
        super().__init__(app)
        self._settings = settings or get_settings()

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> JSONResponse:
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if _path_in(_AUTH_EXEMPT_PREFIXES, path):
            return await call_next(request)

        # Dev shortcut — synthetic admin so /docs + curl work without login.
        if self._settings.auth.dev_skip_auth and self._settings.env == "dev":
            return await call_next(request)

        # Pull token from header OR cookie.
        token: str | None = None
        authz = request.headers.get("Authorization") or request.headers.get("authorization")
        if authz and authz.lower().startswith("bearer "):
            token = authz.split(" ", 1)[1].strip() or None
        if not token:
            token = request.cookies.get(_ACCESS_COOKIE)

        if not token:
            return _problem_response(
                request,
                status.HTTP_401_UNAUTHORIZED,
                "Unauthorized",
                "MISSING_TOKEN",
                "no access token in Authorization header or strix_access cookie",
            )

        try:
            principal = decode_token(
                settings=self._settings.auth,
                token=token,
                expected_typ="access",
            )
        except InvalidTokenError as exc:
            return _problem_response(
                request,
                status.HTTP_401_UNAUTHORIZED,
                "Unauthorized",
                exc.code,
                exc.detail,
            )

        # Stash on the request scope so route handlers / deps can read it
        # without re-decoding the token.
        request.state.principal = principal
        return await call_next(request)


class CsrfMiddleware(BaseHTTPMiddleware):
    """Double-submit-token check on mutating methods."""

    def __init__(self, app: ASGIApp, *, settings: Settings | None = None) -> None:
        super().__init__(app)
        self._settings = settings or get_settings()

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> JSONResponse:
        method = request.method.upper()
        if method not in _CSRF_METHODS:
            return await call_next(request)

        path = request.url.path
        if _path_in(_AUTH_EXEMPT_PREFIXES, path) or _path_in(_CSRF_EXEMPT_PREFIXES, path):
            return await call_next(request)

        if self._settings.auth.dev_skip_auth and self._settings.env == "dev":
            return await call_next(request)

        try:
            verify_csrf(
                header_value=request.headers.get(_CSRF_HEADER),
                cookie_value=request.cookies.get(_CSRF_COOKIE),
            )
        except CsrfMismatchError as exc:
            return _problem_response(
                request,
                status.HTTP_403_FORBIDDEN,
                "CSRF Mismatch",
                exc.code,
                exc.detail,
            )

        return await call_next(request)


def install_middleware(app: FastAPI, *, settings: Settings | None = None) -> None:
    """Install in the order the request flows: outermost = AuthMiddleware,
    then CsrfMiddleware. Starlette runs them OUTSIDE-IN on the request and
    INSIDE-OUT on the response, so AuthMiddleware sees the token first."""
    s = settings or get_settings()
    # Order matters: last `add_middleware` wraps OUTERMOST.
    app.add_middleware(CsrfMiddleware, settings=s)
    app.add_middleware(AuthMiddleware, settings=s)


__all__ = ["AuthMiddleware", "CsrfMiddleware", "install_middleware"]
