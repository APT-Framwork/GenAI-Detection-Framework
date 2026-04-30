"""Smoke test for Workstream 2 / Phase A preprocessing artifacts.

Checks that every artifact under ``apps/models/preprocess/`` exists,
has the expected shape/keys, and matches the sha256 recorded in
``apps/models/MANIFEST.json``.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = REPO_ROOT / "apps" / "models"
MANIFEST_PATH = MODELS_DIR / "MANIFEST.json"


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    if p.is_dir():
        for f in sorted(p.rglob("*")):
            if f.is_file():
                h.update(f.relative_to(p).as_posix().encode())
                h.update(f.read_bytes())
        return h.hexdigest()
    h.update(p.read_bytes())
    return h.hexdigest()


@pytest.fixture(scope="module")
def manifest() -> dict:
    assert MANIFEST_PATH.is_file(), f"missing {MANIFEST_PATH}"
    return json.loads(MANIFEST_PATH.read_text())


@pytest.fixture(scope="module")
def manifest_by_path(manifest: dict) -> dict[str, dict]:
    return {a["path"]: a for a in manifest["artifacts"]}


EXPECTED_PATHS = {
    "preprocess/scaler_55.pkl",
    "preprocess/pca_log_secbert.pkl",
    "preprocess/pca_cmd_secbert.pkl",
    "preprocess/vae_calibrator.pkl",
    "preprocess/gnn_propagation_metadata.pkl",
    "preprocess/secbert_tokenizer/",
}


def test_manifest_lists_all_artifacts(manifest_by_path: dict[str, dict]) -> None:
    missing = EXPECTED_PATHS - set(manifest_by_path.keys())
    assert not missing, f"MANIFEST.json missing entries: {missing}"


@pytest.mark.parametrize("rel_path", sorted(EXPECTED_PATHS))
def test_artifact_sha256_matches_manifest(
    rel_path: str, manifest_by_path: dict[str, dict]
) -> None:
    abs_path = MODELS_DIR / rel_path
    assert abs_path.exists(), f"artifact missing on disk: {abs_path}"
    expected = manifest_by_path[rel_path]["sha256"]
    actual = _sha256(abs_path)
    assert actual == expected, f"sha256 mismatch for {rel_path}: {actual} != {expected}"


def test_scaler_55_shape() -> None:
    sc = joblib.load(MODELS_DIR / "preprocess" / "scaler_55.pkl")
    assert sc.n_features_in_ == 55
    assert sc.mean_.shape == (55,)
    assert sc.scale_.shape == (55,)


def test_pca_log_secbert_shape() -> None:
    p = joblib.load(MODELS_DIR / "preprocess" / "pca_log_secbert.pkl")
    assert p.n_components == 16
    assert p.n_features_in_ == 768  # SecBERT hidden size


def test_pca_cmd_secbert_shape() -> None:
    p = joblib.load(MODELS_DIR / "preprocess" / "pca_cmd_secbert.pkl")
    assert p.n_components == 16
    assert p.n_features_in_ == 768


def test_vae_calibrator_is_fitted_lr() -> None:
    cal = joblib.load(MODELS_DIR / "preprocess" / "vae_calibrator.pkl")
    # sklearn LogisticRegression fitted on scalar input -> coef_.shape == (1, 1)
    assert hasattr(cal, "coef_") and hasattr(cal, "intercept_")
    assert cal.coef_.shape == (1, 1)
    # Sanity-check predict_proba works (best-effort — pickled with newer sklearn
    # may be missing `multi_class` attribute under older runtime).
    import numpy as np

    if not hasattr(cal, "multi_class"):
        cal.multi_class = "auto"
    try:
        probs = cal.predict_proba(np.array([[0.0], [1.0], [5.0]]))
        assert probs.shape == (3, 2)
        assert ((probs >= 0) & (probs <= 1)).all()
    except AttributeError as exc:  # pragma: no cover - sklearn version skew
        pytest.skip(f"sklearn version skew prevents predict_proba: {exc}")


def test_gnn_propagation_metadata_shape() -> None:
    meta = joblib.load(
        MODELS_DIR / "preprocess" / "gnn_propagation_metadata.pkl"
    )
    assert isinstance(meta, dict)
    for k in ("features", "rule_level_included", "scaler", "threshold", "model_params"):
        assert k in meta, f"missing key {k}"
    assert len(meta["features"]) == 55
    assert meta["rule_level_included"] is False
    assert meta["scaler"].n_features_in_ == 55
    # Threshold from notebook FINAL TEST RESULTS (NO RULE LEVEL): 0.7743
    assert abs(float(meta["threshold"]) - 0.7743) < 1e-4
    mp = meta["model_params"]
    assert mp["in_ch"] == 55
    assert mp["hid"] == 128
    assert mp["layers"] == 3


def test_secbert_tokenizer_loads() -> None:
    from transformers import AutoTokenizer

    tok_dir = MODELS_DIR / "preprocess" / "secbert_tokenizer"
    assert tok_dir.is_dir()
    tok = AutoTokenizer.from_pretrained(tok_dir.as_posix())
    out = tok("ls -la /etc/passwd", return_tensors="pt", truncation=True, max_length=32)
    assert "input_ids" in out
    assert out["input_ids"].shape[0] == 1
    assert out["input_ids"].shape[1] >= 1
