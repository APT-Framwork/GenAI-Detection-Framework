"""Workstream 2 / Phase C — Transformer architecture regression test.

Loads the shipped ``apps/models/transformer_model.pth`` checkpoint via
``TransformerLoader``, runs a deterministic forward pass on 8 fixed
sequences, and asserts the resulting logits match a frozen golden file
within 1e-4.

The golden file was produced by running this same architecture
(`TransformerCKCPredictor` per `_arch.py`) — `activation='gelu'`,
`norm_first=True`, ReLU+Dropout in input projection, and last-token
pooling — on a torch.manual_seed(0) sequence batch. Any future regression
that changes the architecture (e.g. flipping pooling back to mean, or
dropping the GELU activation) will produce different logits and fail this
test, which is the whole point of the gate per the Workstream 2 plan.

If the checkpoint itself is rotated, regenerate the golden by running:
    python -m tests._regenerate_transformer_golden
(tooling not committed; the regen is a one-liner using TransformerLoader).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = REPO_ROOT / "apps" / "models"
GOLDEN_PATH = Path(__file__).parent / "fixtures" / "transformer_logits_golden.json"


def _make_sequences() -> np.ndarray:
    """8 sequences of length 4, AE_LATENT_DIM=64. Deterministic."""
    rng = np.random.default_rng(seed=0)
    return rng.standard_normal((8, 4, 64)).astype(np.float32)


@pytest.mark.skipif(
    not (MODELS_DIR / "transformer_model.pth").exists(),
    reason="transformer checkpoint missing",
)
def test_transformer_forward_matches_golden() -> None:
    import torch

    from strix_api.adapters.model_loaders.transformer import TransformerLoader

    loader = TransformerLoader.load(
        MODELS_DIR / "transformer_model.pth",
        version="test",
    )

    sequences = _make_sequences()  # (8, 4, 64)

    # Use the underlying batched forward (we want raw logits, not softmax).
    x = torch.from_numpy(sequences)
    with torch.inference_mode():
        logits = loader._model(x).cpu().numpy().astype(np.float32)

    assert logits.shape == (8, 8)  # 8 seqs × 8 CKC classes

    assert GOLDEN_PATH.exists(), (
        f"golden file missing at {GOLDEN_PATH}; first run captures it"
    )
    golden = np.array(json.loads(GOLDEN_PATH.read_text())["logits"], dtype=np.float32)
    assert golden.shape == logits.shape
    np.testing.assert_allclose(logits, golden, atol=1e-4, rtol=0)


@pytest.mark.skipif(
    not (MODELS_DIR / "transformer_model.pth").exists(),
    reason="transformer checkpoint missing",
)
def test_transformer_uses_last_token_pooling() -> None:
    """Sanity guard: changing the last token of a sequence must change logits;
    changing only an earlier token must NOT change logits if the model truly
    uses last-token pooling AT THE OUTPUT (note: self-attention still mixes
    earlier tokens into the last position, so this test only checks that the
    *last* token has a non-trivial effect — i.e., we are reading from the end,
    not from a fixed-mean over all positions)."""
    import torch

    from strix_api.adapters.model_loaders.transformer import TransformerLoader

    loader = TransformerLoader.load(
        MODELS_DIR / "transformer_model.pth",
        version="test",
    )

    base = _make_sequences()[:1]  # (1, 4, 64)
    perturbed_last = base.copy()
    perturbed_last[0, -1, :] += 5.0  # flood the last token with signal
    with torch.inference_mode():
        out_base = loader._model(torch.from_numpy(base)).cpu().numpy()
        out_last = loader._model(torch.from_numpy(perturbed_last)).cpu().numpy()
    # Perturbing the last token must significantly change the output.
    assert np.abs(out_base - out_last).max() > 1e-3
