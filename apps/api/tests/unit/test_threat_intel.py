"""Phase-6 unit tests — adapters, indicator detection, breaker fallback."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from strix_api.adapters.hibp_adapter import HibpAdapter, HibpError
from strix_api.adapters.virustotal_adapter import (
    VirusTotalAdapter,
    VirusTotalError,
)
from strix_api.services.threat_intel_service import detect_indicator_type
from strix_api.settings import ThreatIntelSettings


# ---- indicator detection ---------------------------------------------


@pytest.mark.parametrize("value, expected", [
    ("alice@example.com", "email"),
    ("bob+test@sub.example.co.uk", "email"),
    ("8.8.8.8", "ip"),
    ("192.168.1.1", "ip"),
    ("2001:0db8:85a3:0000:0000:8a2e:0370:7334", "ip"),
    ("example.com", "domain"),
    ("phish.bad-actor.io", "domain"),
    ("a" * 64, "hash"),
    ("0123456789abcdef" * 4, "hash"),
    ("not an indicator", None),
    ("", None),
    ("   ", None),
])
def test_detect_indicator_type(value: str, expected: str | None) -> None:
    assert detect_indicator_type(value) == expected


def test_detect_distinguishes_hash_from_hex_email_lookalike() -> None:
    # 64-hex-chars classified as hash even if it could also parse otherwise.
    assert detect_indicator_type("a" * 64) == "hash"


# ---- HIBP adapter ----------------------------------------------------


def _ti_settings(*, hibp_key: str | None = "key", vt_key: str | None = "key") -> ThreatIntelSettings:
    return ThreatIntelSettings(
        hibp_api_key=hibp_key,
        hibp_user_agent="strix-test/1.0",
        virustotal_api_key=vt_key,
        breaker_fail_max=3,
        breaker_reset_timeout_seconds=1,
    )


@pytest.mark.asyncio
async def test_hibp_404_is_clean_not_error() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(404))
    client = httpx.AsyncClient(transport=transport)
    try:
        adapter = HibpAdapter(_ti_settings(), client=client)
        out = await adapter.lookup_email("alice@example.com")
        assert out.reputation == "clean"
        assert out.breach_count == 0
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_hibp_200_with_breaches_is_malicious() -> None:
    body = [{"Name": "Adobe", "Domain": "adobe.com"}, {"Name": "Yahoo"}]
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=body))
    client = httpx.AsyncClient(transport=transport)
    try:
        adapter = HibpAdapter(_ti_settings(), client=client)
        out = await adapter.lookup_email("alice@example.com")
        assert out.reputation == "malicious"
        assert out.breach_count == 2
        assert out.breaches[0]["Name"] == "Adobe"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_hibp_429_is_transient_error() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(429))
    client = httpx.AsyncClient(transport=transport)
    try:
        adapter = HibpAdapter(_ti_settings(), client=client)
        with pytest.raises(HibpError) as exc_info:
            await adapter.lookup_email("alice@example.com")
        assert exc_info.value.transient is True
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_hibp_401_is_permanent_error() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(401))
    client = httpx.AsyncClient(transport=transport)
    try:
        adapter = HibpAdapter(_ti_settings(), client=client)
        with pytest.raises(HibpError) as exc_info:
            await adapter.lookup_email("alice@example.com")
        assert exc_info.value.transient is False
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_hibp_breaker_opens_after_repeated_failure() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(500))
    client = httpx.AsyncClient(transport=transport)
    try:
        adapter = HibpAdapter(_ti_settings(), client=client)
        # Trigger fail_max=3 failures
        for _ in range(3):
            with pytest.raises(HibpError):
                await adapter.lookup_email("alice@example.com")
        assert adapter.breaker_state == "open"
        # Subsequent call should fast-fail with breaker error mapped to HibpError.
        with pytest.raises(HibpError):
            await adapter.lookup_email("alice@example.com")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_hibp_no_api_key_is_permanent_error() -> None:
    adapter = HibpAdapter(_ti_settings(hibp_key=None))
    with pytest.raises(HibpError) as exc_info:
        await adapter.lookup_email("alice@example.com")
    assert exc_info.value.transient is False


# ---- VirusTotal adapter ---------------------------------------------


def _vt_response_body(*, malicious: int = 0, suspicious: int = 0, harmless: int = 0) -> dict[str, Any]:
    return {
        "data": {
            "attributes": {
                "last_analysis_stats": {
                    "malicious": malicious, "suspicious": suspicious,
                    "harmless": harmless, "undetected": 1, "timeout": 0,
                },
                "last_analysis_results": {
                    "Engine_A": {"category": "malicious" if malicious else "harmless"},
                },
            }
        }
    }


@pytest.mark.asyncio
async def test_vt_classifies_malicious() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=_vt_response_body(malicious=5)))
    client = httpx.AsyncClient(transport=transport)
    try:
        adapter = VirusTotalAdapter(_ti_settings(), client=client)
        out = await adapter.lookup_ip("8.8.8.8")
        assert out.reputation == "malicious"
        assert out.counts.malicious == 5
        assert out.indicator_type == "ip"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_vt_classifies_suspicious_when_no_malicious() -> None:
    body = _vt_response_body(suspicious=2)
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=body))
    client = httpx.AsyncClient(transport=transport)
    try:
        adapter = VirusTotalAdapter(_ti_settings(), client=client)
        out = await adapter.lookup_domain("evil.example.com")
        assert out.reputation == "suspicious"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_vt_404_is_unknown_not_error() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(404))
    client = httpx.AsyncClient(transport=transport)
    try:
        adapter = VirusTotalAdapter(_ti_settings(), client=client)
        out = await adapter.lookup_hash("a" * 64)
        assert out.reputation == "unknown"
        assert out.counts.malicious == 0
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_vt_breaker_opens_on_repeated_500() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(500))
    client = httpx.AsyncClient(transport=transport)
    try:
        adapter = VirusTotalAdapter(_ti_settings(), client=client)
        for _ in range(3):
            with pytest.raises(VirusTotalError):
                await adapter.lookup_ip("1.2.3.4")
        assert adapter.breaker_state == "open"
    finally:
        await client.aclose()


# ---- file upload route — size cap ------------------------------------


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("DB_PASSWORD", "test")
    from strix_api.main import create_app
    return TestClient(create_app(), raise_server_exceptions=False)


def test_file_upload_rejects_empty(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/threat-intel/files/scan",
        files={"file": ("empty.bin", b"", "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "BAD_REQUEST"


def test_file_upload_rejects_oversized(client: TestClient) -> None:
    huge = b"\x00" * (10 * 1024 * 1024 + 1)   # 10MB + 1 byte
    resp = client.post(
        "/api/v1/threat-intel/files/scan",
        files={"file": ("huge.bin", huge, "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "BAD_REQUEST"


def test_file_upload_returns_synthetic_jobid_without_db(client: TestClient) -> None:
    """Sandbox path: no DB → returns a synthetic accepted response."""
    payload = b"hello world"
    resp = client.post(
        "/api/v1/threat-intel/files/scan",
        files={"file": ("ok.txt", payload, "text/plain")},
    )
    assert resp.status_code == 202
    body = resp.json()
    import hashlib
    assert body["sha256"] == hashlib.sha256(payload).hexdigest()
    assert body["sizeBytes"] == len(payload)
    assert body["status"] == "queued"


def test_iocs_returns_empty_in_sandbox(client: TestClient) -> None:
    resp = client.get("/api/v1/threat-intel/iocs")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"items": [], "total": 0, "page": 1, "limit": 50}


def test_compromised_assets_returns_empty_in_sandbox(client: TestClient) -> None:
    resp = client.get("/api/v1/threat-intel/compromised-assets")
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


def test_vt_scan_rejects_email(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/threat-intel/virustotal/scan",
        json={"indicator": "alice@example.com"},
    )
    assert resp.status_code == 400
    assert "HIBP" in resp.json().get("detail", "")


def test_vt_scan_rejects_garbage_indicator(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/threat-intel/virustotal/scan",
        json={"indicator": "not-a-real-thing"},
    )
    assert resp.status_code == 400
