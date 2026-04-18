"""Transformer loader (CKC predictor over AE-latent sequences).

Sequence semantics (§5.4):
    The Transformer consumes the rolling list of AE `mu` vectors for the
    current chain (`session:{agent_id}:latents` in Redis), oldest first,
    capped at `CHAIN_MAX_STEPS`. Output is a softmax over 8 CKC stages
    (incl. BENIGN).

§5.10 fixes baked into _arch.TransformerCKCPredictor:
    * `activation='gelu'`
    * `norm_first=True`
    * `input_projection = Linear → LayerNorm → ReLU → Dropout(0.1)`
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

from strix_api.adapters.model_loaders._arch import TransformerCKCPredictor
from strix_api.api.errors import ModelRegistryError
from strix_api.core.constants import AE_LATENT_DIM
from strix_api.observability import get_logger

log = get_logger("strix_api.adapters.model_loaders.transformer")

_NUM_CKC = 8
_D_MODEL = 128
_N_HEADS = 8
_N_LAYERS = 4
_D_FF = 512


@dataclass(frozen=True)
class TransformerOutput:
    pred_ckc: int                 # argmax (0..7)
    confidence: float             # softmax max prob
    probabilities: np.ndarray     # (8,) — full distribution


class TransformerLoader:
    """Sequence-in / class-out predictor."""

    def __init__(
        self,
        model: TransformerCKCPredictor,
        *,
        device: torch.device,
        version: str,
    ) -> None:
        self._model = model
        self._device = device
        self.version = version

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        expected_input_dim: int = AE_LATENT_DIM,
        device: str = "cpu",
        version: str = "v1",
    ) -> TransformerLoader:
        if not path.exists():
            raise ModelRegistryError(f"Transformer checkpoint missing: {path}")

        dev = torch.device(device)
        sd = torch.load(path, map_location=dev, weights_only=False)
        if isinstance(sd, dict) and "model_state_dict" in sd:
            sd = sd["model_state_dict"]
        if isinstance(sd, dict) and "state_dict" in sd:
            sd = sd["state_dict"]

        # Architecture sanity (constraint C1: input must be the AE latent)
        proj_w = sd.get("input_projection.0.weight")
        if proj_w is None:
            raise ModelRegistryError(
                "Transformer state_dict missing 'input_projection.0.weight' — "
                "wrong architecture? (expected TransformerCKCPredictor with "
                "Linear→LayerNorm→ReLU→Dropout input projection)"
            )
        actual_in = proj_w.shape[1]
        if actual_in != expected_input_dim:
            raise ModelRegistryError(
                f"Transformer input_dim={actual_in}, expected {expected_input_dim} "
                "(must equal AE latent dim — see C1)"
            )

        # Check that the saved `transformer_encoder.norm` weights are present —
        # if they aren't, the checkpoint was trained with `norm_first=False`
        # and we'd silently drop the final LayerNorm. Refuse to load.
        if "transformer_encoder.norm.weight" not in sd:
            raise ModelRegistryError(
                "Transformer checkpoint is missing 'transformer_encoder.norm.weight' — "
                "this build expects norm_first=True per §5.10 fix."
            )

        # Detect num_classes from output_head.3.weight
        head_w = sd.get("output_head.3.weight")
        num_classes = head_w.shape[0] if head_w is not None else _NUM_CKC

        # Detect layer count
        layer_count = max(
            (
                int(k.split(".")[2]) for k in sd
                if k.startswith("transformer_encoder.layers.") and k.endswith(".norm1.weight")
            ),
            default=-1,
        ) + 1
        if layer_count <= 0:
            raise ModelRegistryError("could not infer transformer layer count from state_dict")

        model = TransformerCKCPredictor(
            input_dim=actual_in,
            d_model=_D_MODEL,
            n_heads=_N_HEADS,
            n_layers=layer_count,
            d_ff=_D_FF,
            num_classes=num_classes,
            dropout=0.1,
        )
        model.load_state_dict(sd, strict=True)
        model.to(dev).eval()

        log.info(
            "transformer_loaded",
            path=str(path),
            input_dim=actual_in,
            d_model=_D_MODEL,
            n_layers=layer_count,
            num_classes=num_classes,
            version=version,
            device=str(dev),
            activation="gelu",
            norm_first=True,
        )
        loader = cls(model, device=dev, version=version)
        loader._warmup()
        return loader

    @torch.inference_mode()
    def predict_sequence(self, latents: np.ndarray) -> TransformerOutput:
        """`latents` shape (T, AE_LATENT_DIM) — oldest first.

        Returns the predicted next CKC stage + confidence over 8 classes.
        """
        if latents.ndim != 2 or latents.shape[1] != AE_LATENT_DIM:
            raise ValueError(
                f"Transformer expects (T, {AE_LATENT_DIM}); got {latents.shape}"
            )
        if latents.shape[0] == 0:
            raise ValueError("Transformer needs at least 1 latent in the sequence")

        x = torch.from_numpy(latents.astype(np.float32, copy=False)).to(self._device)
        x = x.unsqueeze(0)  # (1, T, 64)
        logits = self._model(x)                       # (1, num_classes)
        probs = torch.softmax(logits, dim=-1)[0]      # (num_classes,)
        pred = int(torch.argmax(probs).item())
        conf = float(probs[pred].item())
        return TransformerOutput(
            pred_ckc=pred,
            confidence=conf,
            probabilities=probs.cpu().numpy().astype(np.float32, copy=False),
        )

    @torch.inference_mode()
    def predict_batch(
        self, sequences: list[np.ndarray]
    ) -> list[TransformerOutput]:
        """Batched sequence inference. Right-pads variable-length sequences.

        Returns one TransformerOutput per input sequence.
        """
        if not sequences:
            return []
        max_t = max(s.shape[0] for s in sequences)
        if max_t == 0:
            raise ValueError("at least one sequence must be non-empty")

        b = len(sequences)
        x = np.zeros((b, max_t, AE_LATENT_DIM), dtype=np.float32)
        # Padding mask: True = ignore that position
        pad_mask = np.ones((b, max_t), dtype=bool)
        for i, seq in enumerate(sequences):
            t = seq.shape[0]
            x[i, :t] = seq.astype(np.float32, copy=False)
            pad_mask[i, :t] = False

        xt = torch.from_numpy(x).to(self._device)
        mask_t = torch.from_numpy(pad_mask).to(self._device)
        logits = self._model(xt, src_key_padding_mask=mask_t)  # (B, num_classes)
        probs = torch.softmax(logits, dim=-1)
        preds = torch.argmax(probs, dim=-1)
        outputs: list[TransformerOutput] = []
        for i in range(b):
            p = int(preds[i].item())
            outputs.append(TransformerOutput(
                pred_ckc=p,
                confidence=float(probs[i, p].item()),
                probabilities=probs[i].cpu().numpy().astype(np.float32, copy=False),
            ))
        return outputs

    def _warmup(self) -> None:
        # 1×3-step sequence — exercises pos encoding, attention, head.
        self.predict_sequence(np.zeros((3, AE_LATENT_DIM), dtype=np.float32))


__all__ = ["TransformerLoader", "TransformerOutput"]
