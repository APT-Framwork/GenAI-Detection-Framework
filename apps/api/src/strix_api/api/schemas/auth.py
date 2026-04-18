"""Auth-tab response schemas."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import EmailStr, Field

from strix_api.api.schemas.common import StrixBase


class LoginRequest(StrixBase):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RegisterRequest(StrixBase):
    """Open self-registration. New users land in the `analyst` role; only
    an existing admin can promote them. The `designation` is a free-form
    label the SOC uses to track callsigns / shift identifiers."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    designation: str | None = Field(default=None, max_length=128)


class TokenResponse(StrixBase):
    access_token: str
    expires_in: int  # seconds until access expires
    token_type: Literal["Bearer"] = "Bearer"
    # Only populated for mobile clients (X-Client-Type: mobile). Web
    # clients never receive this field — they rely exclusively on the
    # httpOnly strix_refresh cookie set by _set_token_cookies().
    refresh_token: str | None = None


class RefreshRequest(StrixBase):
    """Mobile-only refresh payload. Web clients send the refresh token as
    the httpOnly ``strix_refresh`` cookie; mobile clients that can't hold
    cookies reliably pass it in the request body instead.
    """

    refresh_token: str | None = None


class DeviceRegisterRequest(StrixBase):
    expo_push_token: str = Field(min_length=1, max_length=512)
    platform: Literal["ios", "android", "web"]
    app_version: str | None = Field(default=None, max_length=32)


class DeviceResponse(StrixBase):
    device_id: UUID
    expo_push_token: str
    platform: Literal["ios", "android", "web"]
    app_version: str | None
    registered_at: str
    last_seen_at: str


class MeResponse(StrixBase):
    user_id: UUID
    email: str
    role: str
    is_active: bool
    designation: str | None = None


__all__ = [
    "DeviceRegisterRequest",
    "DeviceResponse",
    "LoginRequest",
    "MeResponse",
    "RefreshRequest",
    "RegisterRequest",
    "TokenResponse",
]
