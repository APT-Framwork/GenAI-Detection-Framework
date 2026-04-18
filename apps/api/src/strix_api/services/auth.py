"""Authentication primitives — password hashing, JWT, CSRF.

Two token kinds (§5.12):
  - access  : short-lived (15 min), JWT, sent in `Authorization: Bearer …`
              OR in an httpOnly cookie `strix_access`. Carries `sub`, `role`,
              `jti` (token id), `typ='access'`.
  - refresh : long-lived (7 d), JWT, sent in httpOnly+SameSite cookie
              `strix_refresh`. Carries `sub`, `jti`, `typ='refresh'`.

CSRF: when the browser stores tokens in cookies we use the
**double-submit-token** pattern (P4-9). On login, set a non-httpOnly cookie
`strix_csrf` to a random token. Mutating requests (POST/PUT/PATCH/DELETE)
must echo this token in the `X-CSRF-Token` header. The middleware enforces
equality. GET/HEAD requests are exempt.

Phase 8 will lift refresh `jti`s into a Redis revocation list so we can
log a user out across all devices. For now refresh tokens are stateless —
revocation = wait for expiry.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from strix_api.api.errors import StrixError
from strix_api.settings import AuthSettings

# ---------------------------------------------------------------- typed errors


class AuthError(StrixError):
    status_code = 401
    title = "Unauthorized"
    code = "UNAUTHORIZED"


class InvalidCredentialsError(AuthError):
    code = "INVALID_CREDENTIALS"


class TokenExpiredError(AuthError):
    code = "TOKEN_EXPIRED"


class InvalidTokenError(AuthError):
    code = "INVALID_TOKEN"


class CsrfMismatchError(StrixError):
    status_code = 403
    title = "CSRF Mismatch"
    code = "CSRF_MISMATCH"


class ForbiddenError(StrixError):
    status_code = 403
    title = "Forbidden"
    code = "FORBIDDEN"


class EmailAlreadyRegisteredError(StrixError):
    status_code = 409
    title = "Email already registered"
    code = "EMAIL_ALREADY_REGISTERED"


# ---------------------------------------------------------------- model


TokenType = Literal["access", "refresh"]


@dataclass(frozen=True)
class Principal:
    """Whoever the JWT says is making the request."""

    user_id: UUID
    role: str  # 'admin' | 'analyst'
    jti: UUID
    expires_at: datetime
    token_type: TokenType


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    csrf_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime


# ---------------------------------------------------------------- password


_HASHER = PasswordHasher()


def hash_password(plain: str) -> str:
    return _HASHER.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        _HASHER.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except Exception:  # malformed hash, etc.
        return False
    return True


def needs_rehash(hashed: str) -> bool:
    """True when argon2 parameters in the stored hash are outdated."""
    try:
        return _HASHER.check_needs_rehash(hashed)
    except Exception:
        return False


# ---------------------------------------------------------------- JWT


_ALG = "HS256"


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _encode(
    *,
    settings: AuthSettings,
    user_id: UUID,
    role: str,
    jti: UUID,
    typ: TokenType,
    expires_at: datetime,
) -> str:
    if settings.jwt_secret is None:
        raise StrixError("JWT secret not configured (AUTH_JWT_SECRET)")
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "jti": str(jti),
        "typ": typ,
        "iat": int(_now_utc().timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=_ALG)


def issue_token_pair(
    *,
    settings: AuthSettings,
    user_id: UUID,
    role: str,
) -> TokenPair:
    now = _now_utc()
    access_exp = now + timedelta(minutes=settings.jwt_access_ttl_minutes)
    refresh_exp = now + timedelta(days=settings.jwt_refresh_ttl_days)

    access_jti = uuid4()
    refresh_jti = uuid4()

    return TokenPair(
        access_token=_encode(
            settings=settings,
            user_id=user_id,
            role=role,
            jti=access_jti,
            typ="access",
            expires_at=access_exp,
        ),
        refresh_token=_encode(
            settings=settings,
            user_id=user_id,
            role=role,
            jti=refresh_jti,
            typ="refresh",
            expires_at=refresh_exp,
        ),
        csrf_token=secrets.token_urlsafe(32),
        access_expires_at=access_exp,
        refresh_expires_at=refresh_exp,
    )


def decode_token(
    *,
    settings: AuthSettings,
    token: str,
    expected_typ: TokenType,
) -> Principal:
    if settings.jwt_secret is None:
        raise StrixError("JWT secret not configured (AUTH_JWT_SECRET)")
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[_ALG],
            options={"require": ["sub", "role", "jti", "typ", "exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError(f"invalid token: {exc}") from exc

    typ = payload.get("typ")
    if typ != expected_typ:
        raise InvalidTokenError(f"expected {expected_typ} token, got {typ!r}")

    try:
        user_id = UUID(payload["sub"])
        jti = UUID(payload["jti"])
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError(f"malformed token fields: {exc}") from exc

    return Principal(
        user_id=user_id,
        role=str(payload["role"]),
        jti=jti,
        expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
        token_type=typ,
    )


# ---------------------------------------------------------------- RBAC


_VALID_ROLES = frozenset({"admin", "analyst"})


def require_role(principal: Principal, *allowed: str) -> None:
    """Raise ForbiddenError when `principal.role` is not in `allowed`."""
    if not allowed:
        raise ValueError("require_role: at least one allowed role")
    for role in allowed:
        if role not in _VALID_ROLES:
            raise ValueError(f"unknown role in allow-list: {role!r}")
    if principal.role not in allowed:
        raise ForbiddenError(
            f"role {principal.role!r} not permitted (requires one of: {sorted(allowed)})"
        )


# ---------------------------------------------------------------- CSRF


def verify_csrf(*, header_value: str | None, cookie_value: str | None) -> None:
    """Double-submit-token check.

    Both header and cookie must be present + non-empty + equal in
    constant time. Raises CsrfMismatchError otherwise.
    """
    if not header_value or not cookie_value:
        raise CsrfMismatchError("CSRF token missing from header or cookie")
    if not secrets.compare_digest(header_value, cookie_value):
        raise CsrfMismatchError("CSRF token mismatch")


__all__ = [
    "AuthError",
    "CsrfMismatchError",
    "EmailAlreadyRegisteredError",
    "ForbiddenError",
    "InvalidCredentialsError",
    "InvalidTokenError",
    "Principal",
    "TokenExpiredError",
    "TokenPair",
    "TokenType",
    "decode_token",
    "hash_password",
    "issue_token_pair",
    "needs_rehash",
    "require_role",
    "verify_csrf",
    "verify_password",
]
