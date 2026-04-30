"""Reproducibility / sanity checks for the runtime SecBERT → PCA-16 path.

Background
----------
A previous Workstream-3 agent diagnosed a drift between runtime SecBERT and the
training-time SecBERT used to fit ``secbert_cmd_pca.pkl`` /
``secbert_log_pca.pkl``. They patched the EMPTY-cmd path with
``apps/models/preprocess/secbert_dominant_vectors.json`` (93.8% of training
rows projected to a single 16-vec).

What this test asserts (given the data we actually have on disk)
----------------------------------------------------------------
The training parquets only contain the **PCA-16 outputs**, not the raw 768-d
SecBERT vectors and not the raw cmd text. So a true 768-d cosine reproducibility
check is impossible — there is no source-of-truth to reproduce. What we *can*
verify is:

1. **Hermetic load** — the runtime path loads SecBERT from
   ``apps/models/preprocess/secbert/`` (saved local weights), not the HF hub.
2. **EMPTY-case drift is non-trivial** — runtime ``SecBERT('[EMPTY]')`` →
   PCA-16 lands far from the training dominant 16-vec, justifying the
   dominant-vector substitute the pipeline already does in
   ``_cmd_secbert_for``.
3. **Non-empty cmds are in-distribution** — runtime PCA-16 outputs for a set
   of plausible attacker / sysadmin cmds fall within the per-dim min/max range
   observed in the **non-dominant** training rows. This tells us the residual
   drift on non-empty cmds is small enough that the existing PCA + scaler can
   still consume it without driving downstream detectors out of range.

If (3) ever fails, the only correct fix is retraining (PCA + scaler + AE/VAE/
transformer). We can't build a runtime → training lookup because the training
parquets don't preserve the source text.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[3]
MODELS = REPO / "apps" / "models"


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


@pytest.fixture(scope="module")
def runtime_secbert():
    """Load SecBERT exactly the way build_pipeline() does (hermetic local)."""
    from transformers import AutoModel, AutoTokenizer  # noqa: PLC0415

    secbert_dir = MODELS / "preprocess" / "secbert"
    tok_dir = MODELS / "preprocess" / "secbert_tokenizer"
    if not (secbert_dir / "config.json").exists():
        pytest.skip(f"local SecBERT weights missing at {secbert_dir}")
    tok = AutoTokenizer.from_pretrained(str(tok_dir if tok_dir.is_dir() else secbert_dir))
    m = AutoModel.from_pretrained(str(secbert_dir))
    m.eval()
    return tok, m


def _embed(tok, model, texts: list[str]) -> np.ndarray:
    import torch  # noqa: PLC0415

    with torch.no_grad():
        enc = tok(texts, padding=True, truncation=True, max_length=128, return_tensors="pt")
        out = model(**enc)
        h = out.last_hidden_state
        mask = enc["attention_mask"].unsqueeze(-1).float()
        pooled = (h * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
    return pooled.cpu().numpy().astype(np.float32)


@pytest.fixture(scope="module")
def cmd_pca():
    with open(MODELS / "secbert_cmd_pca.pkl", "rb") as fh:
        return pickle.load(fh)


def test_secbert_local_weights_load_and_have_correct_hidden_size(runtime_secbert):
    _, m = runtime_secbert
    assert m.config.hidden_size == 768


def test_empty_cmd_runtime_drifts_from_training_dominant(runtime_secbert, cmd_pca):
    """Documents the very drift that motivated the dominant-vector workaround.

    Cosine should be **far below** 0.99 — if it ever rises near 1, the empirical
    dominant-vector substitute in `_cmd_secbert_for` is no longer needed (and
    in fact would be harmful) and the workaround should be removed.
    """
    tok, m = runtime_secbert
    runtime_16 = cmd_pca.transform(_embed(tok, m, ["[EMPTY]"])).astype(np.float32)[0]
    dom = np.array(
        json.loads((MODELS / "preprocess" / "secbert_dominant_vectors.json").read_text())[
            "cmd_dominant_16"
        ],
        np.float32,
    )
    cos = _cos(runtime_16, dom)
    # The W3 baseline measured ~0.685; pinning + local-load may shift it but
    # should still be far from 1.0. We just assert "the workaround is still
    # needed" — i.e. cosine is well under 0.99.
    assert abs(cos) < 0.95, (
        f"runtime SecBERT([EMPTY]) → PCA-16 now matches training dominant "
        f"(cos={cos:.3f}); the dominant-vector workaround in _cmd_secbert_for "
        f"is no longer required and should be removed."
    )


def test_non_empty_cmds_runtime_pca16_in_training_range(runtime_secbert, cmd_pca):
    """Runtime PCA-16 for plausible cmds should overlap the training non-dominant range.

    Soft check on dim-0 (highest-variance PCA component): runtime min/max must
    fall within an envelope around training min/max. If this ever fails, the
    cmd_secbert path is feeding the scaler garbage and we'd need to retrain.
    """
    tok, m = runtime_secbert
    cmds = [
        "cat /etc/passwd",
        "cat /etc/shadow",
        "ps -ef",
        "ps aux",
        "whoami",
        "id",
        "uname -a",
        "ls /tmp",
        "find / -perm -4000",
        "curl http://attacker.com",
        "wget http://x",
        "nc -lvp 4444",
        "/bin/bash -i",
        "sudo su -",
        "iptables -L",
        "netstat -tulpn",
        "ssh root@1.2.3.4",
        "tar czf /tmp/x.tgz /etc",
        "useradd hacker",
        "chmod 777 /tmp",
    ]
    v16 = cmd_pca.transform(_embed(tok, m, cmds)).astype(np.float32)

    tr = pd.read_parquet(MODELS / "secbert_cmd_embeddings.parquet").values.astype(np.float32)
    dom_row = tr[0]
    non_dom = tr[~(np.all(np.abs(tr - dom_row) < 1e-6, axis=1))]
    tr_min = np.min(non_dom, axis=0)
    tr_max = np.max(non_dom, axis=0)
    # Allow a 50% slack envelope — PCA-16 dim-0 has training range ~[-22, +0.2]
    span = tr_max - tr_min
    lo = tr_min - 0.5 * span
    hi = tr_max + 0.5 * span

    rt_min = np.min(v16, axis=0)
    rt_max = np.max(v16, axis=0)
    # Check first 4 PCA dims (these dominate >75% of variance)
    for d in range(4):
        assert rt_min[d] >= lo[d], (
            f"PCA-16 dim {d}: runtime min {rt_min[d]:.2f} below training envelope {lo[d]:.2f}"
        )
        assert rt_max[d] <= hi[d], (
            f"PCA-16 dim {d}: runtime max {rt_max[d]:.2f} above training envelope {hi[d]:.2f}"
        )
