"""AE loader (RegularizedAutoencoder) — §5.10 fixes applied.

Public API:
    loader = AutoencoderLoader.load(path, expected_input_dim=55)
    out    = loader.batch_forward(np_batch)            # → AeBatchOutput
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

from strix_api.adapters.model_loaders._arch import RegularizedAutoencoder
from strix_api.api.errors import ModelRegistryError
from strix_api.core.constants import AE_LATENT_DIM, FEATURE_VECTOR_DIM
from strix_api.observability import get_logger

log = get_logger("strix_api.adapters.model_loaders.autoencoder")


@dataclass(frozen=True)
class AeBatchOutput:
    """One row per item in the input batch (shape preserved)."""

    latents: np.ndarray  # (B, 64) — `mu` (deterministic in eval mode)
    recon_error: np.ndarray  # (B,)   — per-sample MSE between input/output
    anomaly_score: np.ndarray  # (B,)   — recon_error + 0.1 * ||mu - center||²

    @property
    def batch_size(self) -> int:
        return self.latents.shape[0]


class AutoencoderLoader:
    """Wraps the RegularizedAutoencoder. Stateless except for model weights."""

    def __init__(
        self, model: RegularizedAutoencoder, *, device: torch.device, version: str
    ) -> None:
        self._model = model
        self._device = device
        self.version = version

    # ---- factory ------------------------------------------------------

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        expected_input_dim: int = FEATURE_VECTOR_DIM,
        device: str = "cpu",
        version: str = "v1",
    ) -> AutoencoderLoader:
        if not path.exists():
            raise ModelRegistryError(f"AE checkpoint missing: {path}")

        dev = torch.device(device)
        sd = torch.load(path, map_location=dev, weights_only=False)
        if isinstance(sd, dict) and "model_state_dict" in sd:
            sd = sd["model_state_dict"]
        if isinstance(sd, dict) and "state_dict" in sd:
            sd = sd["state_dict"]

        # Sanity: input_dim must match the canonical 55. If a future model
        # ships with a different input_dim, the registry must be bumped — we
        # refuse to load silently, matching constraint C4.
        first_w = sd.get("encoder_body.0.weight")
        if first_w is None:
            raise ModelRegistryError(
                "AE state_dict missing 'encoder_body.0.weight' — wrong architecture? "
                "(expected RegularizedAutoencoder per TP1_AE_FeatureSelection.ipynb)"
            )
        actual_in = first_w.shape[1]
        if actual_in != expected_input_dim:
            raise ModelRegistryError(f"AE input_dim={actual_in}, expected {expected_input_dim}")

        # Latent dim from fc_mu's output shape
        fc_mu_w = sd.get("fc_mu.weight")
        latent = fc_mu_w.shape[0] if fc_mu_w is not None else AE_LATENT_DIM
        if latent != AE_LATENT_DIM:
            raise ModelRegistryError(
                f"AE latent_dim={latent}, expected {AE_LATENT_DIM} "
                "(Transformer consumes 64-d AE latent — see C1)"
            )

        model = RegularizedAutoencoder(input_dim=actual_in, latent_dim=latent, dropout_rate=0.2)
        model.load_state_dict(sd, strict=True)
        model.to(dev).eval()

        log.info(
            "ae_loaded",
            path=str(path),
            input_dim=actual_in,
            latent_dim=latent,
            version=version,
            device=str(dev),
        )
        loader = cls(model, device=dev, version=version)
        loader._warmup()
        return loader

    # ---- inference (CPU-bound; call via asyncio.to_thread) ------------

    @torch.inference_mode()
    def batch_forward(self, batch: np.ndarray) -> AeBatchOutput:
        """`batch` shape (B, 55) float32 (already scaled by the preprocessor)."""
        if batch.ndim != 2 or batch.shape[1] != FEATURE_VECTOR_DIM:
            raise ValueError(f"AE expects shape (B, {FEATURE_VECTOR_DIM}), got {batch.shape}")
        x = torch.from_numpy(batch.astype(np.float32, copy=False)).to(self._device)
        recon, z, mu, _logvar = self._model(x)

        # Per-sample MSE
        diff = (recon - x).pow(2)
        recon_err = diff.mean(dim=1)

        # Anomaly score: recon + 0.1 * ||mu - center||² (matches loader formula
        # in MODELS_REFERENCE.md §5.10 — kept verbatim even though it differs
        # from the notebook's training-time recon+β·KL).
        center = self._model.center
        center_dist = (mu - center).pow(2).sum(dim=1)
        anomaly_score = recon_err + 0.1 * center_dist

        return AeBatchOutput(
            latents=mu.cpu().numpy().astype(np.float32, copy=False),
            recon_error=recon_err.cpu().numpy().astype(np.float32, copy=False),
            anomaly_score=anomaly_score.cpu().numpy().astype(np.float32, copy=False),
        )

    # ---- warmup -------------------------------------------------------

    def _warmup(self) -> None:
        # 2-row batch so BatchNorm doesn't choke (it requires batch>=2 in train,
        # but we're in eval mode — safe with 1, kept at 2 for symmetry).
        self.batch_forward(np.zeros((2, FEATURE_VECTOR_DIM), dtype=np.float32))


__all__ = ["AeBatchOutput", "AutoencoderLoader"]
