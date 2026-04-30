"""Workstream 2 / Phase D — VAE calibrator validation.

The Phase A artifact ``vae_calibrator.pkl`` (extracted from
``probability_calibrators.pkl['Beta-VAE (Top 25)']``) is a fitted
``LogisticRegression`` mapping recon-loss → P(malicious). The Phase A
notebook noted a sklearn version skew (pickled on 1.7.x/1.8.x, runtime
1.6.1). This test validates that ``predict_proba`` actually returns
sensible probabilities at runtime and that they match values produced
directly from the underlying ``coef_/intercept_`` (i.e. the LR is intact
and the pickled object is operational).

If this test fails, the calibrator must be refit in the runtime sklearn
version (per Phase D fallback in the plan); update the MANIFEST sha256
afterwards.
"""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = REPO_ROOT / "apps" / "models"
CALIB_PATH = MODELS_DIR / "preprocess" / "vae_calibrator.pkl"


@pytest.mark.skipif(not CALIB_PATH.exists(), reason="Phase A calibrator missing")
def test_calibrator_predict_proba_matches_manual_sigmoid() -> None:
    """100 samples spanning the typical recon-loss range. predict_proba(class=1)
    should equal sigmoid(coef_ * x + intercept_) within 1e-3 (loose to absorb
    any sklearn-version-skew internal numerical wiggles)."""
    cal = joblib.load(CALIB_PATH)
    if not hasattr(cal, "multi_class"):
        cal.multi_class = "auto"

    rng = np.random.default_rng(seed=0)
    # Recon loss in [0, 5] — covers benign (<0.5) through malicious (>2).
    scores = rng.uniform(0.0, 5.0, size=100).astype(np.float32).reshape(-1, 1)

    probs = cal.predict_proba(scores)[:, 1]
    assert probs.shape == (100,)
    assert ((probs >= 0.0) & (probs <= 1.0)).all()

    # Manual: P(class=1) = sigmoid(w * x + b)
    w = float(cal.coef_[0, 0])
    b = float(cal.intercept_[0])
    expected = 1.0 / (1.0 + np.exp(-(w * scores[:, 0] + b)))
    mae = float(np.mean(np.abs(probs - expected)))
    assert mae < 1e-3, f"predict_proba diverges from raw sigmoid: MAE={mae}"


@pytest.mark.skipif(not CALIB_PATH.exists(), reason="Phase A calibrator missing")
def test_calibrator_is_monotonic_increasing() -> None:
    """Higher recon-loss must imply higher P(malicious). If the LR coef_ ever
    flipped sign during refit, this would catch it."""
    cal = joblib.load(CALIB_PATH)
    if not hasattr(cal, "multi_class"):
        cal.multi_class = "auto"

    xs = np.linspace(0.0, 5.0, 50, dtype=np.float32).reshape(-1, 1)
    p = cal.predict_proba(xs)[:, 1]
    assert np.all(np.diff(p) >= -1e-6), "calibrator not monotonic in recon loss"
    # And the slope is non-trivial (not collapsed to ~0.5 across the range).
    assert p[-1] - p[0] > 0.05


@pytest.mark.skipif(not CALIB_PATH.exists(), reason="Phase A calibrator missing")
def test_vae_loader_uses_calibrator_predict_proba() -> None:
    """Phase D guard: the VAE loader must NOT use a heuristic
    ``sigmoid(2*(recon+0.05*center_dist)-1)`` formula; it must call the
    calibrator's ``predict_proba``. We assert by source-grep."""
    src = (
        REPO_ROOT
        / "apps"
        / "api"
        / "src"
        / "strix_api"
        / "adapters"
        / "model_loaders"
        / "vae.py"
    ).read_text()
    # Must call the calibrator
    assert "predict_proba" in src
    # Must not contain the deprecated heuristic
    assert "0.05*center_dist" not in src
    assert "0.05 * center_dist" not in src
