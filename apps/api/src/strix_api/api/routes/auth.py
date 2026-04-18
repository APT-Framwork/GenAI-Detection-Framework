"""Auth endpoints — login / logout / refresh / me.

All four are CSRF-exempt (login/logout/refresh because the user doesn't
yet have a CSRF token; me because it's a GET). Every other mutating
endpoint in the API picks up the CSRF check from the middleware in
`api/middleware/csrf.py`.

Cookie strategy:
    strix_access   httpOnly  SameSite=Lax  15 min
    strix_refresh  httpOnly  SameSite=Lax  7 d   path=/api/v1/auth/refresh
    strix_csrf     readable  SameSite=Lax  7 d   (frontend echoes via X-CSRF-Token)

In dev (`ENV=dev`) the cookies are NOT marked Secure so they work over
http://localhost. In staging/prod the middleware adds Secure.
"""

from __future__ import annotations

from datetime import UTC
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.api.deps import (
    SettingsDep,
    get_current_principal,
    get_db_session,
)
from strix_api.api.errors import StrixError
from strix_api.api.schemas.auth import (
    DeviceRegisterRequest,
    DeviceResponse,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from strix_api.repositories.push_device_repo import PushDeviceRepo
from strix_api.repositories.user_repo import UserRepo
from strix_api.services.auth import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidTokenError,
    Principal,
    TokenPair,
    decode_token,
    hash_password,
    issue_token_pair,
    needs_rehash,
    verify_password,
)
from strix_api.settings import Settings

router = APIRouter(prefix="/auth", tags=["auth"])

_ACCESS_COOKIE = "strix_access"
_REFRESH_COOKIE = "strix_refresh"
_CSRF_COOKIE = "strix_csrf"
_REFRESH_PATH = "/api/v1/auth/refresh"

_MOBILE_CLIENT_HEADER = "x-client-type"
_MOBILE_CLIENT_VALUE = "mobile"


def _is_mobile_client(request: Request) -> bool:
    """Return True iff the request declares itself a mobile client.

    The web SPA never sends this header, so cookie-based auth remains
    the sole channel for web. Mobile clients add it at bootstrap.
    """
    value = request.headers.get(_MOBILE_CLIENT_HEADER)
    return value is not None and value.strip().lower() == _MOBILE_CLIENT_VALUE


def _set_token_cookies(
    response: Response, *, pair: TokenPair, settings: Settings,
) -> None:
    secure = settings.env != "dev"
    response.set_cookie(
        _ACCESS_COOKIE, pair.access_token,
        max_age=settings.auth.jwt_access_ttl_minutes * 60,
        httponly=True, secure=secure, samesite="lax",
        path="/",
    )
    response.set_cookie(
        _REFRESH_COOKIE, pair.refresh_token,
        max_age=settings.auth.jwt_refresh_ttl_days * 86400,
        httponly=True, secure=secure, samesite="lax",
        path=_REFRESH_PATH,
    )
    # CSRF cookie deliberately NOT httponly — the SPA reads it and echoes
    # the value back as the X-CSRF-Token header.
    response.set_cookie(
        _CSRF_COOKIE, pair.csrf_token,
        max_age=settings.auth.jwt_refresh_ttl_days * 86400,
        httponly=False, secure=secure, samesite="lax",
        path="/",
    )


def _clear_cookies(response: Response, settings: Settings) -> None:
    secure = settings.env != "dev"
    for name, path in (
        (_ACCESS_COOKIE, "/"),
        (_REFRESH_COOKIE, _REFRESH_PATH),
        (_CSRF_COOKIE, "/"),
    ):
        response.delete_cookie(name, path=path, samesite="lax", secure=secure, httponly=False)


# ---- routes ---------------------------------------------------------


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    settings: SettingsDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    """Open self-registration. New users land in `analyst`.

    Issues a session pair on success so the SPA can land directly on the
    dashboard without a second round-trip to /login. Duplicate emails
    return 409 to avoid leaking existence — but we accept that this is
    still observable via the existing /login flow.
    """
    repo = UserRepo(session)
    if await repo.get_by_email(body.email) is not None:
        raise EmailAlreadyRegisteredError("email already registered")
    user = await repo.create(
        email=body.email,
        password_hash=hash_password(body.password),
        role="analyst",
        designation=body.designation,
    )
    await session.commit()
    pair = issue_token_pair(
        settings=settings.auth, user_id=user.user_id, role=user.role,
    )
    _set_token_cookies(response, pair=pair, settings=settings)
    return TokenResponse(
        access_token=pair.access_token,
        expires_in=settings.auth.jwt_access_ttl_minutes * 60,
        refresh_token=pair.refresh_token if _is_mobile_client(request) else None,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    settings: SettingsDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    repo = UserRepo(session)
    user = await repo.get_by_email(body.email)
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise InvalidCredentialsError("invalid email or password")

    if needs_rehash(user.password_hash):
        await repo.update_password(user.user_id, hash_password(body.password))

    pair = issue_token_pair(
        settings=settings.auth, user_id=user.user_id, role=user.role,
    )
    _set_token_cookies(response, pair=pair, settings=settings)
    return TokenResponse(
        access_token=pair.access_token,
        expires_in=settings.auth.jwt_access_ttl_minutes * 60,
        refresh_token=pair.refresh_token if _is_mobile_client(request) else None,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    settings: SettingsDep,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    refresh_cookie: Annotated[str | None, Cookie(alias=_REFRESH_COOKIE)] = None,
    body: RefreshRequest | None = None,
) -> TokenResponse:
    # Cookie takes precedence (web). Body is the mobile fallback.
    token = refresh_cookie or (body.refresh_token if body else None)
    if not token:
        raise InvalidTokenError("refresh token missing")
    try:
        principal: Principal = decode_token(
            settings=settings.auth, token=token, expected_typ="refresh",
        )
    except StrixError:
        raise

    user = await UserRepo(session).get_by_id(principal.user_id)
    if user is None or not user.is_active:
        _clear_cookies(response, settings)
        raise InvalidTokenError("user no longer active")

    pair = issue_token_pair(
        settings=settings.auth, user_id=user.user_id, role=user.role,
    )
    _set_token_cookies(response, pair=pair, settings=settings)
    return TokenResponse(
        access_token=pair.access_token,
        expires_in=settings.auth.jwt_access_ttl_minutes * 60,
        refresh_token=pair.refresh_token if _is_mobile_client(request) else None,
    )


@router.post("/logout")
async def logout(response: Response, settings: SettingsDep) -> dict[str, bool]:
    _clear_cookies(response, settings)
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
async def me(
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MeResponse:
    user = await UserRepo(session).get_by_id(principal.user_id)
    if user is None:
        raise InvalidTokenError("user not found")
    return MeResponse(
        user_id=user.user_id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        designation=user.designation,
    )


# -----------------------------------------------------------------------
# Push device registration (M0-B5)
# -----------------------------------------------------------------------


@router.post("/devices", response_model=DeviceResponse)
async def register_device(
    body: DeviceRegisterRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> DeviceResponse:
    """Register or refresh an Expo push token for the current user.

    Idempotent: repeated calls with the same (user, token) just bump
    ``last_seen_at``. Mobile clients call this after login and again on
    each cold start to prove the token is still live.
    """
    if session is None:
        # Sandbox fallback — echo back a synthetic record.
        from datetime import datetime
        from uuid import uuid4
        now = datetime.now(UTC).isoformat()
        return DeviceResponse(
            device_id=uuid4(),
            expo_push_token=body.expo_push_token,
            platform=body.platform,
            app_version=body.app_version,
            registered_at=now,
            last_seen_at=now,
        )

    repo = PushDeviceRepo(session)
    device = await repo.upsert(
        user_id=principal.user_id,
        expo_push_token=body.expo_push_token,
        platform=body.platform,
        app_version=body.app_version,
    )
    await session.commit()
    return DeviceResponse(
        device_id=device.device_id,
        expo_push_token=device.expo_push_token,
        platform=device.platform,  # type: ignore[arg-type]
        app_version=device.app_version,
        registered_at=device.registered_at.isoformat(),
        last_seen_at=device.last_seen_at.isoformat(),
    )


@router.delete("/devices/{expo_push_token:path}")
async def unregister_device(
    expo_push_token: str,
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> dict[str, int]:
    if session is None:
        return {"deleted": 0}
    deleted = await PushDeviceRepo(session).delete_by_token(
        user_id=principal.user_id,
        expo_push_token=expo_push_token,
    )
    await session.commit()
    return {"deleted": deleted}


@router.get("/devices", response_model=list[DeviceResponse])
async def list_my_devices(
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> list[DeviceResponse]:
    if session is None:
        return []
    devices = await PushDeviceRepo(session).list_for_user(principal.user_id)
    return [
        DeviceResponse(
            device_id=d.device_id,
            expo_push_token=d.expo_push_token,
            platform=d.platform,  # type: ignore[arg-type]
            app_version=d.app_version,
            registered_at=d.registered_at.isoformat(),
            last_seen_at=d.last_seen_at.isoformat(),
        )
        for d in devices
    ]
