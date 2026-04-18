"""`RawAlert → 55-dim feature vector` pipeline.

This is the single place that touches SecBERT + the two PCAs + the scaler.
All heavy-weight state (tokenizer, BERT model, PCA weights, scaler means)
is loaded ONCE at worker startup via `build_pipeline()`.

Layer contract: this module is an adapter — it's allowed to import torch,
sklearn, and transformers. `core/` calls it indirectly via a `Protocol`
(not imported here; types are `np.ndarray` in and out).

Canonical 55-col layout (numeric SecBERT — AE/VAE path):
    [0..22]  = 23 individual features (FeatureEngineerNoLeakage)
    [23..38] = 16 log_secbert_emb_{0..15}    (SecBERT(full_log) → log_pca)
    [39..54] = 16 cmd_secbert_emb_{0..15}    (SecBERT(command)  → cmd_pca)

The GNN uses a DIFFERENT ordering (alphabetical SecBERT). `gnn_features`
on `PreprocessingPipeline` gives that permutation for the inference worker
to apply before calling the GNN forward pass.
"""

from __future__ import annotations

import hashlib
import json
import pickle
import time
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from strix_api.api.errors import ModelRegistryError
from strix_api.core.constants import FEATURE_VECTOR_DIM
from strix_api.core.feature_engineer import FeatureEngineerNoLeakage
from strix_api.core.raw_alert import RawAlert
from strix_api.observability import (
    cache_hits_total,
    cache_misses_total,
    get_logger,
    normalizer_duration_seconds,
)

if TYPE_CHECKING:  # keep heavy imports out of the import-time cost
    pass

log = get_logger("strix_api.adapters.preprocessing_pipeline")

SECBERT_MODEL_ID = "jackaduma/SecBERT"
SECBERT_HIDDEN_SIZE = 768
SECBERT_MAX_TOKENS = 128
SECBERT_TRUNCATE_CHARS = 2000
_LRU_MAX = 10_000  # §7.2 "SecBERT embeddings" row


# ---------------------------------------------------------------- data classes


@dataclass(frozen=True)
class VaeCalibrators:
    """Wrapper around the 4-key probability_calibrators.pkl dict.

    The plan (§5.14) picks one key for the live VAE; we default to
    `Beta-VAE (Top 25)` — the one that matches `apps/models/vae_model.pth`
    (byte-identical to origin/models:beta_vae_top25_features_32dim.pth).
    """

    mapping: dict[str, Any]
    active_key: str = "Beta-VAE (Top 25)"

    @property
    def active(self) -> Any:
        if self.active_key not in self.mapping:
            raise ModelRegistryError(
                f"calibrator key {self.active_key!r} not found in "
                f"probability_calibrators.pkl (keys: {list(self.mapping)})"
            )
        return self.mapping[self.active_key]


@dataclass(frozen=True)
class GnnMetadata:
    """Typed wrapper around gnn_metadata.pkl."""

    features: list[str]       # 55 col names in GNN's alphabetical SecBERT order
    scaler_55: Any            # StandardScaler with n_features_in_=55 (sliced)
    threshold: float          # Part-1 threshold; unused on the plan's 13-dim state path
    rule_level_included: bool
    metrics: dict[str, float]
    raw_metadata: dict[str, Any]


# ---------------------------------------------------------------- SecBERT wrapper


class _SecBertEmbedder:
    """Stateless apart from the loaded model weights.

    `embed_one(text)` is LRU-cached by SHA-1(text) — Wazuh emits many
    identical `full_log` strings (same decoder firing). Big hit-rate
    win at the normalizer p50 per §7.2.
    """

    def __init__(self, tokenizer: Any, model: Any, device: str) -> None:
        self._tokenizer = tokenizer
        self._model = model
        self._device = device
        # The LRU cache is instance-scoped; reset on re-instantiation (tests).
        self._cache: dict[str, np.ndarray] = {}

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha1(text.encode("utf-8", "replace"), usedforsecurity=False).hexdigest()

    def _clean(self, text: str | None) -> str:
        if not text or not text.strip():
            return "[EMPTY]"
        return text[:SECBERT_TRUNCATE_CHARS]

    def embed_one(self, text: str) -> np.ndarray:
        """768-dim mean-pooled embedding for a single text."""
        import torch  # lazy

        cleaned = self._clean(text)
        k = self._key(cleaned)

        hit = self._cache.get(k)
        if hit is not None:
            cache_hits_total.labels(cache="secbert").inc()
            return hit
        cache_misses_total.labels(cache="secbert").inc()

        if len(self._cache) >= _LRU_MAX:
            # Cheap LRU-ish: drop ~10% oldest (insertion order in dict).
            for stale in list(self._cache.keys())[: _LRU_MAX // 10]:
                self._cache.pop(stale, None)

        with torch.no_grad():
            enc = self._tokenizer(
                [cleaned],
                padding=True,
                truncation=True,
                max_length=SECBERT_MAX_TOKENS,
                return_tensors="pt",
            ).to(self._device)
            out = self._model(**enc)
            hidden = out.last_hidden_state  # (1, T, 768)
            mask = enc["attention_mask"].unsqueeze(-1).float()  # (1, T, 1)
            summed = (hidden * mask).sum(dim=1)
            counts = mask.sum(dim=1).clamp(min=1e-9)
            pooled = (summed / counts).cpu().numpy().astype(np.float32)[0]

        self._cache[k] = pooled
        return pooled


# ---------------------------------------------------------------- pipeline


class PreprocessingPipeline:
    """Assemble all preprocessing into one callable.

    Workers hold one instance. The per-alert hot path is `.transform(alert)`
    which is CPU-bound (torch forward is the long pole) — run it via
    `asyncio.to_thread()` per §7.5.
    """

    def __init__(
        self,
        *,
        secbert: _SecBertEmbedder,
        log_pca: Any,
        cmd_pca: Any,
        scaler_55: Any,
        canonical_order: list[str],
        calibrators: VaeCalibrators,
        gnn: GnnMetadata,
    ) -> None:
        self._secbert = secbert
        self._log_pca = log_pca
        self._cmd_pca = cmd_pca
        self._scaler = scaler_55
        self._engineer = FeatureEngineerNoLeakage()

        # Canonical order in AE/VAE space (numeric SecBERT).
        self.canonical_order = tuple(canonical_order)
        if len(self.canonical_order) != FEATURE_VECTOR_DIM:
            raise ModelRegistryError(
                f"selected_features_top25.json reports {len(canonical_order)} cols, "
                f"expected {FEATURE_VECTOR_DIM}"
            )

        self.calibrators = calibrators
        self.gnn = gnn

        # Permutation: 55-dim canonical (numeric) → GNN ordering (alphabetical).
        # Worker applies this with np.take(vec, perm) before the GNN forward pass.
        if len(gnn.features) != FEATURE_VECTOR_DIM:
            raise ModelRegistryError(
                f"gnn_metadata.features has {len(gnn.features)} entries, "
                f"expected {FEATURE_VECTOR_DIM}"
            )
        try:
            self.gnn_permutation = np.array(
                [self.canonical_order.index(c) for c in gnn.features],
                dtype=np.int64,
            )
        except ValueError as exc:  # pragma: no cover — static data
            raise ModelRegistryError(
                "gnn_metadata.features and selected_features_top25 have different sets"
            ) from exc

    # ---- hot path -----------------------------------------------------

    def transform(self, alert: RawAlert) -> np.ndarray:
        """RawAlert → scaled 55-dim vector (canonical/numeric order)."""
        # 23 individuals
        t0 = time.perf_counter()
        individuals = self._engineer.to_array(alert)
        normalizer_duration_seconds.labels(stage="individuals").observe(
            time.perf_counter() - t0
        )

        # SecBERT(cmd) + SecBERT(log)
        cmd_text, log_text = self._engineer.text_inputs(alert)
        t1 = time.perf_counter()
        cmd_768 = self._secbert.embed_one(cmd_text)
        log_768 = self._secbert.embed_one(log_text)
        normalizer_duration_seconds.labels(stage="secbert").observe(
            time.perf_counter() - t1
        )

        # PCA
        t2 = time.perf_counter()
        cmd_16 = self._cmd_pca.transform(cmd_768.reshape(1, -1)).astype(np.float32)[0]
        log_16 = self._log_pca.transform(log_768.reshape(1, -1)).astype(np.float32)[0]
        normalizer_duration_seconds.labels(stage="pca").observe(
            time.perf_counter() - t2
        )

        # Assemble — canonical order is 23 individuals + 16 log + 16 cmd
        vec = np.concatenate([individuals, log_16, cmd_16]).astype(np.float32)
        if vec.shape != (FEATURE_VECTOR_DIM,):  # defensive
            raise RuntimeError(f"unexpected feature vector shape: {vec.shape}")

        # Scale
        t3 = time.perf_counter()
        scaled = self._scaler.transform(vec.reshape(1, -1)).astype(np.float32)[0]
        normalizer_duration_seconds.labels(stage="scale").observe(
            time.perf_counter() - t3
        )

        return scaled

    def transform_for_gnn(self, scaled_canonical: np.ndarray) -> np.ndarray:
        """Permute a canonical (numeric-order) vector into GNN ordering.

        Expects a VECTOR already scaled (we use the AE/VAE scaler). The GNN
        was trained against the same data means/stds, same scaler — just
        different column ordering. So the AE/VAE-scaled vector re-permuted
        is exactly what the GNN expects.
        """
        return scaled_canonical[self.gnn_permutation]

    # ---- warm-up ------------------------------------------------------

    def warmup(self) -> None:
        """Run one synthetic alert through every stage (§5.9).

        Triggers any lazy JIT compilation and BatchNorm stats so the first
        real alert doesn't eat the cost.
        """
        from datetime import datetime

        from strix_api.core.raw_alert import (
            AgentInfo,
            DataInfo,
            RuleInfo,
            SyscheckInfo,
        )
        from strix_api.core.raw_alert import (
            RawAlert as _RawAlert,
        )

        dummy = _RawAlert(
            alert_id="warmup-0",
            occurred_at=datetime.now(UTC),
            decoder_name="auditd",
            location="/var/log/audit/audit.log",
            full_log="warmup alert for pipeline",
            agent=AgentInfo(agent_id="warmup"),
            rule=RuleInfo(rule_id="0", firedtimes=1),
            data=DataInfo(command="echo warmup"),
            syscheck=SyscheckInfo(),
        )
        t0 = time.perf_counter()
        v = self.transform(dummy)
        dt = time.perf_counter() - t0
        log.info(
            "preprocessing_warmup_ok",
            elapsed_ms=round(dt * 1000, 1),
            vector_shape=v.shape,
            vector_dtype=str(v.dtype),
        )


# ---------------------------------------------------------------- builder


def build_pipeline(
    models_dir: Path,
    *,
    device: str = "cpu",
    warmup: bool = True,
) -> PreprocessingPipeline:
    """Load every preprocessing artifact from disk and return a ready pipeline.

    Raises `ModelRegistryError` on any missing / corrupt / mismatched file.
    """
    from transformers import AutoModel, AutoTokenizer  # noqa: F401 — lazy

    required = {
        "secbert_log_pca": "secbert_log_pca.pkl",
        "secbert_cmd_pca": "secbert_cmd_pca.pkl",
        "standard_scaler": "standard_scaler.pkl",
        "calibrators":     "probability_calibrators.pkl",
        "gnn_metadata":    "gnn_metadata.pkl",
        "canonical_json":  "selected_features_top25.json",
    }
    for key, fname in required.items():
        p = models_dir / fname
        if not p.exists():
            raise ModelRegistryError(f"required preprocessing artifact missing: {p}")

    log.info("loading_secbert", model_id=SECBERT_MODEL_ID, device=device)
    tokenizer = AutoTokenizer.from_pretrained(SECBERT_MODEL_ID)
    model = AutoModel.from_pretrained(SECBERT_MODEL_ID).to(device)
    model.eval()
    if model.config.hidden_size != SECBERT_HIDDEN_SIZE:  # pragma: no cover
        raise ModelRegistryError(
            f"SecBERT hidden_size = {model.config.hidden_size}, expected {SECBERT_HIDDEN_SIZE}"
        )
    secbert = _SecBertEmbedder(tokenizer, model, device)

    log_pca = _load_pickle(models_dir / required["secbert_log_pca"], "PCA")
    cmd_pca = _load_pickle(models_dir / required["secbert_cmd_pca"], "PCA")
    scaler_55 = _load_pickle(models_dir / required["standard_scaler"], "StandardScaler")
    _check_pca(log_pca, "log")
    _check_pca(cmd_pca, "cmd")
    _check_scaler(scaler_55, expected_dim=FEATURE_VECTOR_DIM)

    calib_raw = _load_pickle(models_dir / required["calibrators"], "dict")
    if not isinstance(calib_raw, dict):
        raise ModelRegistryError("probability_calibrators.pkl is not a dict")
    calibrators = VaeCalibrators(mapping=calib_raw)
    _ = calibrators.active  # raises if key missing

    gnn_raw = _load_pickle(models_dir / required["gnn_metadata"], "dict")
    gnn = _build_gnn_meta(gnn_raw)

    canonical = json.loads((models_dir / required["canonical_json"]).read_text())
    canonical_order: list[str] = canonical["all_selected_columns"]

    pipe = PreprocessingPipeline(
        secbert=secbert,
        log_pca=log_pca,
        cmd_pca=cmd_pca,
        scaler_55=scaler_55,
        canonical_order=canonical_order,
        calibrators=calibrators,
        gnn=gnn,
    )

    if warmup:
        pipe.warmup()

    log.info(
        "preprocessing_pipeline_ready",
        canonical_cols=len(canonical_order),
        gnn_cols=len(gnn.features),
        vae_calibrator=calibrators.active_key,
        gnn_threshold=gnn.threshold,
    )
    return pipe


# ---------------------------------------------------------------- loaders


def _load_pickle(path: Path, expected_kind: str) -> Any:
    """Load a pickle and surface a useful error on corruption."""
    try:
        with path.open("rb") as f:
            return pickle.load(f)
    except Exception as exc:
        raise ModelRegistryError(
            f"failed to load {path.name} (expected {expected_kind}): {exc}"
        ) from exc


def _check_pca(pca: Any, label: str) -> None:
    from sklearn.decomposition import PCA as _PCA

    if not isinstance(pca, _PCA):
        raise ModelRegistryError(f"{label} pca is {type(pca).__name__}, expected sklearn PCA")
    if pca.n_components_ != 16:
        raise ModelRegistryError(
            f"{label} pca has n_components_={pca.n_components_}, expected 16"
        )
    if pca.n_features_in_ != SECBERT_HIDDEN_SIZE:
        raise ModelRegistryError(
            f"{label} pca has n_features_in_={pca.n_features_in_}, "
            f"expected {SECBERT_HIDDEN_SIZE} (SecBERT hidden size)"
        )


def _check_scaler(scaler: Any, *, expected_dim: int) -> None:
    from sklearn.preprocessing import StandardScaler as _Scaler

    if not isinstance(scaler, _Scaler):
        raise ModelRegistryError(
            f"standard_scaler.pkl is {type(scaler).__name__}, expected StandardScaler"
        )
    if scaler.n_features_in_ != expected_dim:
        raise ModelRegistryError(
            f"standard_scaler.pkl fit on {scaler.n_features_in_} features, "
            f"expected {expected_dim}"
        )


def _build_gnn_meta(raw: dict[str, Any]) -> GnnMetadata:
    from sklearn.preprocessing import StandardScaler as _Scaler

    required_keys = {"features", "scaler", "threshold"}
    missing = required_keys - raw.keys()
    if missing:
        raise ModelRegistryError(f"gnn_metadata.pkl missing keys: {sorted(missing)}")

    features: list[str] = list(raw["features"])
    if len(features) != FEATURE_VECTOR_DIM:
        raise ModelRegistryError(
            f"gnn_metadata features has {len(features)} entries, expected {FEATURE_VECTOR_DIM}"
        )

    src_scaler = raw["scaler"]
    # Part 2 retraining in the notebook slices X_scaled[:, :-1]; we do the
    # equivalent here by taking the first 55 entries of the 56-dim scaler.
    sliced = _Scaler()
    if src_scaler.n_features_in_ == 56:
        sliced.mean_ = src_scaler.mean_[:55].astype(np.float64)
        sliced.scale_ = src_scaler.scale_[:55].astype(np.float64)
        sliced.var_ = src_scaler.var_[:55].astype(np.float64)
    elif src_scaler.n_features_in_ == 55:
        sliced.mean_ = src_scaler.mean_.astype(np.float64)
        sliced.scale_ = src_scaler.scale_.astype(np.float64)
        sliced.var_ = src_scaler.var_.astype(np.float64)
    else:
        raise ModelRegistryError(
            f"gnn_metadata scaler has n_features_in_={src_scaler.n_features_in_}, "
            f"expected 55 or 56"
        )
    sliced.n_features_in_ = 55
    sliced.feature_names_in_ = np.array(features, dtype=object)
    if hasattr(src_scaler, "n_samples_seen_"):
        sliced.n_samples_seen_ = src_scaler.n_samples_seen_
    sliced.with_mean = True
    sliced.with_std = True
    sliced.copy = True

    return GnnMetadata(
        features=features,
        scaler_55=sliced,
        threshold=float(raw["threshold"]),
        rule_level_included=bool(raw.get("rule_level_included", False)),
        metrics=dict(raw.get("metrics", {})),
        raw_metadata=raw,
    )


__all__ = [
    "GnnMetadata",
    "PreprocessingPipeline",
    "VaeCalibrators",
    "build_pipeline",
]
