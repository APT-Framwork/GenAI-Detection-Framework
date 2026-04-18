"""FastAPI dependency injection providers.

Every request-scoped dep lives here. Tests can override via `app.dependency_overrides`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Awaitable, Callable

from fastapi import Cookie, Depends, Header, Request

from strix_api.api.errors import StrixError
from strix_api.repositories.database import session_scope
from strix_api.services.auth import (
    InvalidTokenError,
    Principal,
    decode_token,
    require_role,
    verify_csrf,
)
from strix_api.settings import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]


# ---- DB session ---------------------------------------------------------


async def get_db_session() -> AsyncIterator[object]:
    """Yields one AsyncSession per request and commits on success.

    Yields `None` if the engine hasn't been initialised — routes are
    expected to fall back to an empty-shape response in that case.
    Useful for unit tests that exercise the route layer without spinning
    up Postgres.
    """
    try:
        async with session_scope() as session:
            yield session
    except RuntimeError:
        # `init_engine(settings)` not called yet — typical in unit tests.
        yield None


# ---- Auth ---------------------------------------------------------------

_ACCESS_COOKIE = "strix_access"
_REFRESH_COOKIE = "strix_refresh"
_CSRF_COOKIE = "strix_csrf"
_CSRF_HEADER = "X-CSRF-Token"


def _extract_access_token(
    request: Request,
    authorization: str | None,
    cookie_token: str | None,
) -> str | None:
    """Bearer header takes priority over the cookie (machines vs browsers)."""
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip() or None
    return cookie_token


async def get_current_principal_optional(
    request: Request,
    settings: SettingsDep,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    access_cookie: Annotated[str | None, Cookie(alias=_ACCESS_COOKIE)] = None,
) -> Principal | None:
    """Returns the principal if the request is authenticated, else None.

    Honors `AUTH_DEV_SKIP_AUTH=true` only when ENV=dev — synthesises a
    pseudo-admin principal so local development against the API doesn't
    need a real login flow. Production refuses to honor the flag.
    """
    if settings.auth.dev_skip_auth and settings.env == "dev":
        from datetime import datetime, timedelta, timezone
        from uuid import UUID

        return Principal(
            user_id=UUID("00000000-0000-0000-0000-00000000beef"),
            role="admin",
            jti=UUID("00000000-0000-0000-0000-00000000feed"),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            token_type="access",
        )

    token = _extract_access_token(request, authorization, access_cookie)
    if not token:
        return None
    try:
        return decode_token(
            settings=settings.auth, token=token, expected_typ="access",
        )
    except StrixError:
        return None


async def get_current_principal(
    principal: Annotated[Principal | None, Depends(get_current_principal_optional)],
) -> Principal:
    if principal is None:
        raise InvalidTokenError("authentication required")
    return principal


# ---- CSRF (mutating routes only — applied via middleware too) ------------


async def enforce_csrf(
    request: Request,
    csrf_header: Annotated[str | None, Header(alias=_CSRF_HEADER)] = None,
    csrf_cookie: Annotated[str | None, Cookie(alias=_CSRF_COOKIE)] = None,
) -> None:
    """Per-route fallback. The middleware does the heavy lifting; this dep
    is a belt-and-suspenders for routes declared outside the middleware
    (e.g. FastAPI testclient bypasses middleware in some setups)."""
    if request.method.upper() in ("GET", "HEAD", "OPTIONS"):
        return
    verify_csrf(header_value=csrf_header, cookie_value=csrf_cookie)


# ---- Role guards --------------------------------------------------------


def role_required(*allowed: str) -> Callable[[Principal], Principal]:
    """Use as `Depends(role_required('admin'))` on protected routes."""

    def _dep(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        require_role(principal, *allowed)
        return principal

    return _dep


# Convenience for the two roles defined in §12 Q8.
require_admin = role_required("admin")
require_analyst_or_admin = role_required("analyst", "admin")


__all__ = [
    "SettingsDep",
    "enforce_csrf",
    "get_current_principal",
    "get_current_principal_optional",
    "get_db_session",
    "require_admin",
    "require_analyst_or_admin",
    "role_required",
]
