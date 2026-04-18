"""Drift KL math + monitoring routes (P8-5)."""

from __future__ import annotations

import math
import os

import pytest
from fastapi.testclient import TestClient

from strix_api.services.drift_service import (
    histogram,
    kl_divergence,
    load_baseline,
)


# ---- KL math ----------------------------------------------------------


def test_kl_identical_distributions_is_zero() -> None:
    a = [10, 20, 30, 40]
    assert kl_divergence(a, a) < 1e-6


def test_kl_is_non_negative() -> None:
    a = [1, 2, 3, 4]
    b = [4, 3, 2, 1]
    assert kl_divergence(a, b) >= 0
    assert kl_divergence(b, a) >= 0


def test_kl_increases_as_distributions_diverge() -> None:
    base = [1, 1, 1, 1]
    close = [1, 1, 2, 1]
    far = [10, 0, 0, 1]
    assert kl_divergence(close, base) < kl_divergence(far, base)


def test_kl_handles_zero_buckets_gracefully() -> None:
    """Laplace smoothing prevents log(0) — finite, non-negative result."""
    out = kl_divergence([0, 0, 5, 0], [1, 1, 1, 1])
    assert math.isfinite(out)
    assert out >= 0


def test_kl_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        kl_divergence([1, 2], [1, 2, 3])


# ---- histogram --------------------------------------------------------


def test_histogram_has_10_bins() -> None:
    assert len(histogram([0.5])) == 10


def test_histogram_clips_out_of_range() -> None:
    hist = histogram([-1.0, 0.0, 0.5, 1.0, 1.5, 99.0])
    # -1.0 → bin 0, 0.0 → bin 0, 0.5 → bin 5, 1.0 → bin 9, 1.5 → bin 9, 99 → bin 9
    assert sum(hist) == 6
    assert hist[0] == 2
    assert hist[5] == 1
    assert hist[9] == 3


def test_histogram_skips_nans_and_nones() -> None:
    hist = histogram([0.5, None, float("nan"), 0.7])  # type: ignore[list-item]
    assert sum(hist) == 2


# ---- baseline loader -------------------------------------------------


def test_load_baseline_missing_file_returns_empty(tmp_path) -> None:
    assert load_baseline(tmp_path) == {}


def test_load_baseline_skips_wrong_shape(tmp_path) -> None:
    (tmp_path / "drift_baseline.json").write_text(
        '{"models": {"AE": [1, 2, 3], "VAE": ' + str([1] * 10) + "}}"
    )
    out = load_baseline(tmp_path)
    assert "AE" not in out  # 3 entries, not 10
    assert "VAE" in out and len(out["VAE"]) == 10


# ---- monitoring routes ------------------------------------------------


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("DB_PASSWORD", "test")
    # Override registry path to the real apps/models/ so the monitoring
    # routes find registry.json in the test sandbox (default = /app/models
    # is the Docker container path).
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[4]
    os.environ["MODELS_PATH"] = str(repo_root / "apps" / "models")
    from strix_api.settings import get_settings
    get_settings.cache_clear()
    from strix_api.main import create_app
    return TestClient(create_app(), raise_server_exceptions=False)


def test_models_route_reads_registry(client: TestClient) -> None:
    resp = client.get("/api/v1/monitoring/models")
    assert resp.status_code == 200
    body = resp.json()
    # registry.json has 5 models — AE, VAE, TRANSFORMER, GNN, DQN
    names = {m["name"] for m in body["models"]}
    assert names == {"AE", "VAE", "TRANSFORMER", "GNN", "DQN"}


def test_drift_route_returns_empty_in_sandbox(client: TestClient) -> None:
    resp = client.get("/api/v1/monitoring/drift?windowMinutes=60")
    assert resp.status_code == 200
    assert resp.json() == {"windowMinutes": 60, "items": []}


def test_drift_rejects_window_out_of_range(client: TestClient) -> None:
    resp = client.get("/api/v1/monitoring/drift?windowMinutes=99999")
    assert resp.status_code == 422


def test_retrain_endpoint_returns_advisory(client: TestClient) -> None:
    resp = client.post("/api/v1/monitoring/models/retrain")
    assert resp.status_code == 202
    body = resp.json()
    assert body["accepted"] is False
    assert "post-1.0" in body["message"].lower() or "1.0" in body["message"]


def test_composite_accuracy_returns_placeholder(client: TestClient) -> None:
    resp = client.get("/api/v1/monitoring/composite-accuracy")
    assert resp.status_code == 200
    assert "value" in resp.json()
    assert "computedAt" in resp.json()
