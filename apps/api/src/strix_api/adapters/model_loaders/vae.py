"""VAE loader (BetaVAE) — uses the fitted calibrator for malicious_prob (§5.10).

Public API:
    loader = VaeLoader.load(path, calibrator=pipe.calibrators.active)
    out    = loader.batch_forward(np_batch)            # → VaeBatchOutput
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch

from strix_api.adapters.model_loaders._arch import BetaVAE
from strix_api.api.errors import ModelRegistryError
from strix_api.core.constants import FEATURE_VECTOR_DIM
from strix_api.observability import get_logger

log = get_logger("strix_api.adapters.model_loaders.vae")

_LATENT_DIM_DEFAULT = 32  # matches the apps/models/vae_model.pth checkpoint


@dataclass(frozen=True)
class VaeBatchOutput:
    malicious_prob: np.ndarray  # (B,) — calibrated [0,1]; from probability_calibrators.pkl
    uncertainty: np.ndarray  # (B,) — mean of latent log_var (proxy for confidence)
    recon_loss: np.ndarray  # (B,) — per-sample MSE
    z_mean: np.ndarray  # (B, latent_dim)


class VaeLoader:
    """BetaVAE wrapper. Probability calibration is delegated to a
    `LogisticRegression`-shaped object (fit on the training-time recon-loss
    distribution); see `probability_calibrators.pkl` key 'Beta-VAE (Top 25)'."""

    def __init__(
        self,
        model: BetaVAE,
        *,
        calibrator: Any,
        device: torch.device,
        version: str,
    ) -> None:
        self._model = model
        self._calibrator = calibrator
        self._device = device
        self.version = version

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        calibrator: Any,
        expected_input_dim: int = FEATURE_VECTOR_DIM,
        device: str = "cpu",
        version: str = "v1",
    ) -> VaeLoader:
        if not path.exists():
            raise ModelRegistryError(f"VAE checkpoint missing: {path}")
        if calibrator is None:
            raise ModelRegistryError(
                "VAE requires a calibrator (probability_calibrators.pkl 'Beta-VAE (Top 25)')"
            )

        dev = torch.device(device)
        sd = torch.load(path, map_location=dev, weights_only=False)
        if isinstance(sd, dict) and "model_state_dict" in sd:
            sd = sd["model_state_dict"]
        if isinstance(sd, dict) and "state_dict" in sd:
            sd = sd["state_dict"]

        first_w = sd.get("encoder_l1.weight")
        if first_w is None:
            raise ModelRegistryError(
                "VAE state_dict missing 'encoder_l1.weight' — wrong architecture? "
                "(expected BetaVAE per TP2_VAE_FeatureSelection.ipynb)"
            )
        actual_in = first_w.shape[1]
        if actual_in != expected_input_dim:
            raise ModelRegistryError(f"VAE input_dim={actual_in}, expected {expected_input_dim}")

        fc_z = sd.get("fc_z_mean.weight")
        latent = fc_z.shape[0] if fc_z is not None else _LATENT_DIM_DEFAULT
        if "center" not in sd:
            raise ModelRegistryError(
                "VAE state_dict has no `center` parameter — expected BetaVAE, not plain SIEMVAE"
            )

        model = BetaVAE(input_dim=actual_in, latent_dim=latent, dropout_rate=0.3)
        model.load_state_dict(sd, strict=True)
        model.to(dev).eval()

        log.info(
            "vae_loaded",
            path=str(path),
            input_dim=actual_in,
            latent_dim=latent,
            version=version,
            device=str(dev),
            calibrator_kind=type(calibrator).__name__,
        )

        loader = cls(model, calibrator=calibrator, device=dev, version=version)
        loader._warmup()
        return loader

    @torch.inference_mode()
    def batch_forward(self, batch: np.ndarray) -> VaeBatchOutput:
        if batch.ndim != 2 or batch.shape[1] != FEATURE_VECTOR_DIM:
            raise ValueError(f"VAE expects shape (B, {FEATURE_VECTOR_DIM}), got {batch.shape}")
        x = torch.from_numpy(batch.astype(np.float32, copy=False)).to(self._device)
        recon, z_mean, z_log_var = self._model(x)

        recon_loss = (recon - x).pow(2).mean(dim=1)  # (B,)
        # Uncertainty proxy: mean over latent dims of log_var; higher → less confident
        uncertainty = z_log_var.mean(dim=1)

        # Calibrate scalar recon-loss → P(malicious).
        # `predict_proba(scores.reshape(-1,1))[:, 1]` matches the notebook's
        # cell 22: `cal_beta_reduced.fit(scores.reshape(-1,1), y_true)`.
        scores = recon_loss.cpu().numpy().astype(np.float32, copy=False)
        probs = self._calibrator.predict_proba(scores.reshape(-1, 1))[:, 1]

        return VaeBatchOutput(
            malicious_prob=probs.astype(np.float32, copy=False),
            uncertainty=uncertainty.cpu().numpy().astype(np.float32, copy=False),
            recon_loss=scores,
            z_mean=z_mean.cpu().numpy().astype(np.float32, copy=False),
        )

    def _warmup(self) -> None:
        self.batch_forward(np.zeros((2, FEATURE_VECTOR_DIM), dtype=np.float32))


__all__ = ["VaeBatchOutput", "VaeLoader"]
