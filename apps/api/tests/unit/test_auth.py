"""Auth primitives — password, JWT, CSRF, role-guard."""

from __future__ import annotations

from datetime import UTC, timedelta
from uuid import uuid4

import jwt
import pytest

from strix_api.api.errors import StrixError
from strix_api.services.auth import (
    CsrfMismatchError,
    ForbiddenError,
    InvalidTokenError,
    Principal,
    TokenExpiredError,
    decode_token,
    hash_password,
    issue_token_pair,
    require_role,
    verify_csrf,
    verify_password,
)
from strix_api.settings import AuthSettings


def _settings(**overrides):
    base = dict(
        dev_skip_auth=False,
        jwt_secret="test-secret",
        jwt_access_ttl_minutes=15,
        jwt_refresh_ttl_days=7,
        auto_response_enabled=False,
    )
    base.update(overrides)
    return AuthSettings(**base)


# ---- password hashing -----------------------------------------------


def test_hash_and_verify_roundtrip() -> None:
    h = hash_password("super-secret")
    assert verify_password("super-secret", h)
    assert not verify_password("wrong-password", h)


def test_verify_rejects_malformed_hash() -> None:
    assert not verify_password("anything", "not-a-real-argon2-hash")


# ---- JWT ------------------------------------------------------------


def test_issue_pair_has_three_tokens_and_distinct_jtis() -> None:
    s = _settings()
    pair = issue_token_pair(settings=s, user_id=uuid4(), role="admin")
    assert pair.access_token != pair.refresh_token
    assert pair.csrf_token  # non-empty
    decoded_a = decode_token(settings=s, token=pair.access_token, expected_typ="access")
    decoded_r = decode_token(settings=s, token=pair.refresh_token, expected_typ="refresh")
    assert decoded_a.jti != decoded_r.jti


def test_decode_rejects_wrong_token_type() -> None:
    s = _settings()
    pair = issue_token_pair(settings=s, user_id=uuid4(), role="analyst")
    with pytest.raises(InvalidTokenError):
        decode_token(settings=s, token=pair.refresh_token, expected_typ="access")


def test_decode_rejects_tampered_token() -> None:
    s = _settings()
    pair = issue_token_pair(settings=s, user_id=uuid4(), role="admin")
    tampered = pair.access_token[:-2] + ("AA" if pair.access_token[-2:] != "AA" else "BB")
    with pytest.raises(InvalidTokenError):
        decode_token(settings=s, token=tampered, expected_typ="access")


def test_decode_rejects_expired() -> None:
    s = _settings()
    expired_payload = {
        "sub": str(uuid4()),
        "role": "admin",
        "jti": str(uuid4()),
        "typ": "access",
        "iat": 0,
        "exp": 1,  # 1970
    }
    expired = jwt.encode(expired_payload, "test-secret", algorithm="HS256")
    with pytest.raises(TokenExpiredError):
        decode_token(settings=s, token=expired, expected_typ="access")


def test_role_in_payload_is_returned() -> None:
    s = _settings()
    user_id = uuid4()
    pair = issue_token_pair(settings=s, user_id=user_id, role="analyst")
    p = decode_token(settings=s, token=pair.access_token, expected_typ="access")
    assert p.user_id == user_id
    assert p.role == "analyst"
    assert p.token_type == "access"


def test_missing_secret_errors() -> None:
    s = _settings(jwt_secret=None)
    with pytest.raises(StrixError):
        issue_token_pair(settings=s, user_id=uuid4(), role="admin")


# ---- CSRF -----------------------------------------------------------


def test_csrf_match_succeeds_silently() -> None:
    verify_csrf(header_value="abc-123", cookie_value="abc-123")


def test_csrf_mismatch_raises() -> None:
    with pytest.raises(CsrfMismatchError):
        verify_csrf(header_value="abc", cookie_value="def")


def test_csrf_missing_either_side_raises() -> None:
    with pytest.raises(CsrfMismatchError):
        verify_csrf(header_value=None, cookie_value="x")
    with pytest.raises(CsrfMismatchError):
        verify_csrf(header_value="x", cookie_value=None)
    with pytest.raises(CsrfMismatchError):
        verify_csrf(header_value="", cookie_value="")


# ---- RBAC -----------------------------------------------------------


def _principal(role: str) -> Principal:
    from datetime import datetime

    return Principal(
        user_id=uuid4(),
        role=role,
        jti=uuid4(),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        token_type="access",
    )


def test_require_role_allows_match() -> None:
    require_role(_principal("admin"), "admin")
    require_role(_principal("analyst"), "analyst", "admin")


def test_require_role_rejects_mismatch() -> None:
    with pytest.raises(ForbiddenError):
        require_role(_principal("analyst"), "admin")


def test_require_role_rejects_unknown_allowlist_role() -> None:
    with pytest.raises(ValueError):
        require_role(_principal("admin"), "superuser")


def test_require_role_needs_at_least_one_allowed() -> None:
    with pytest.raises(ValueError):
        require_role(_principal("admin"))
