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


# Canonical 55-column feature ordering — copied verbatim from
# `feature_selection_final.ipynb` (the same notebook cell that fit
# `standard_scaler.pkl`/`scaler_55.pkl`). The order is load-bearing: the
# trained StandardScaler's mean_/scale_ are positional, and any permutation
# silently corrupts every downstream model output.
#
# Mirror of `apps/models/selected_features_top25.json['all_selected_columns']`.
# Layout: [0..22] 23 individuals, [23..38] log_secbert_emb_0..15,
#         [39..54] cmd_secbert_emb_0..15.
FEATURE_COLUMNS: list[str] = [
    # 23 individuals (FeatureEngineerNoLeakage canonical order)
    "decoder_auditd",
    "firedtimes",
    "location__var_log_audit_audit.log",
    "srcip_is_private",
    "decoder_web-accesslog",
    "location__var_log_apache2_access.log",
    "firedtimes_log",
    "path_is_missing",
    "has_md5",
    "cmd_length",
    "has_sha256",
    "syscheck_added",
    "cmd_is_missing",
    "decoder_dpkg-decoder",
    "syscheck_deleted",
    "path_depth",
    "syscheck_modified",
    "location__var_log_auth.log",
    "decoder_syscheck_deleted",
    "path_is_sensitive",
    "decoder_syscheck_integrity_changed",
    "location_syscheck",
    "path_is_temp",
    # 16 log_secbert PCA dims
    "log_secbert_emb_0",
    "log_secbert_emb_1",
    "log_secbert_emb_2",
    "log_secbert_emb_3",
    "log_secbert_emb_4",
    "log_secbert_emb_5",
    "log_secbert_emb_6",
    "log_secbert_emb_7",
    "log_secbert_emb_8",
    "log_secbert_emb_9",
    "log_secbert_emb_10",
    "log_secbert_emb_11",
    "log_secbert_emb_12",
    "log_secbert_emb_13",
    "log_secbert_emb_14",
    "log_secbert_emb_15",
    # 16 cmd_secbert PCA dims
    "cmd_secbert_emb_0",
    "cmd_secbert_emb_1",
    "cmd_secbert_emb_2",
    "cmd_secbert_emb_3",
    "cmd_secbert_emb_4",
    "cmd_secbert_emb_5",
    "cmd_secbert_emb_6",
    "cmd_secbert_emb_7",
    "cmd_secbert_emb_8",
    "cmd_secbert_emb_9",
    "cmd_secbert_emb_10",
    "cmd_secbert_emb_11",
    "cmd_secbert_emb_12",
    "cmd_secbert_emb_13",
    "cmd_secbert_emb_14",
    "cmd_secbert_emb_15",
]


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

    features: list[str]  # 55 col names in GNN's alphabetical SecBERT order
    scaler_55: Any  # StandardScaler with n_features_in_=55 (sliced)
    threshold: float  # Part-1 threshold; unused on the plan's 13-dim state path
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
        cmd_dominant_16: np.ndarray | None = None,
    ) -> None:
        self._secbert = secbert
        self._log_pca = log_pca
        self._cmd_pca = cmd_pca
        self._scaler = scaler_55
        self._engineer = FeatureEngineerNoLeakage()
        # Empirical dominant cmd_secbert 16-vec (93.8% of training rows).
        # Used as the substitute for missing/empty commands — see
        # `_cmd_secbert_for` for the reasoning.
        self._cmd_dominant_16 = (
            None
            if cmd_dominant_16 is None
            else np.asarray(cmd_dominant_16, dtype=np.float32).copy()
        )

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

    # cmd_secbert path is split out so the unit test can inspect the
    # pre-scaler 16-d vec directly and so missing-cmd fallback is explicit.
    def _cmd_secbert_for(self, alert: RawAlert) -> np.ndarray:
        """16-d cmd_secbert PCA output for one alert (PRE-scaler).

        Notebook canonical recipe was "[EMPTY] → SecBERT → PCA" for missing
        commands. In training that recipe collapsed ~93.8% of rows onto a
        single dominant 16-vec (visible in `secbert_cmd_embeddings.parquet`).
        Runtime SecBERT([EMPTY]) lands on a DIFFERENT 16-vec — cosine sim
        ~0.685 with the training dominant — almost certainly because the
        SecBERT checkpoint shipped by HuggingFace today differs from what
        the notebook fit against. The downstream scaler has scale_≈0.12 on
        cmd_secbert_emb_7, so a 0.685-cosine drift becomes ±28 SD. Substitute
        the dominant vec when the alert has no command — that is the
        empirical training behavior, modulo the SecBERT-version drift.
        """
        cmd = alert.data.command
        if (cmd is None or not cmd.strip()) and self._cmd_dominant_16 is not None:
            return self._cmd_dominant_16.copy()
        cmd_text, _ = self._engineer.text_inputs(alert)
        cmd_768 = self._secbert.embed_one(cmd_text)
        return self._cmd_pca.transform(cmd_768.reshape(1, -1)).astype(np.float32)[0]

    def transform(self, alert: RawAlert) -> np.ndarray:
        """RawAlert → scaled 55-dim vector (canonical/numeric order)."""
        # 23 individuals
        t0 = time.perf_counter()
        individuals = self._engineer.to_array(alert)
        normalizer_duration_seconds.labels(stage="individuals").observe(time.perf_counter() - t0)

        # SecBERT(log) — log_secbert is naturally diverse in training
        # (only 0.5% dominance) so runtime SecBERT output is in-distribution.
        _, log_text = self._engineer.text_inputs(alert)
        t1 = time.perf_counter()
        log_768 = self._secbert.embed_one(log_text)
        normalizer_duration_seconds.labels(stage="secbert").observe(time.perf_counter() - t1)

        # PCA
        t2 = time.perf_counter()
        cmd_16 = self._cmd_secbert_for(alert)
        log_16 = self._log_pca.transform(log_768.reshape(1, -1)).astype(np.float32)[0]
        normalizer_duration_seconds.labels(stage="pca").observe(time.perf_counter() - t2)

        # Assemble — canonical order is 23 individuals + 16 log + 16 cmd
        vec = np.concatenate([individuals, log_16, cmd_16]).astype(np.float32)
        if vec.shape != (FEATURE_VECTOR_DIM,):  # defensive
            raise RuntimeError(f"unexpected feature vector shape: {vec.shape}")

        # Scale
        t3 = time.perf_counter()
        scaled = self._scaler.transform(vec.reshape(1, -1)).astype(np.float32)[0]
        normalizer_duration_seconds.labels(stage="scale").observe(time.perf_counter() - t3)

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
        "calibrators": "probability_calibrators.pkl",
        "gnn_metadata": "gnn_metadata.pkl",
        "canonical_json": "selected_features_top25.json",
    }
    for key, fname in required.items():
        p = models_dir / fname
        if not p.exists():
            raise ModelRegistryError(f"required preprocessing artifact missing: {p}")

    # Phase E: prefer Workstream-2/Phase-A's clean Part-2 metadata
    # (`preprocess/gnn_propagation_metadata.pkl` — 55-col scaler, threshold
    # 0.7743 from the "NO RULE LEVEL" retrain). Fall back to the legacy
    # 56-col `gnn_metadata.pkl` (with threshold 0.918 from Part-1) only if
    # the Phase-A artifact is absent.
    gnn_propagation_path = models_dir / "preprocess" / "gnn_propagation_metadata.pkl"

    # Hermetic SecBERT load: prefer the locally-saved weights at
    # `apps/models/preprocess/secbert/` so runtime never re-downloads the HF
    # checkpoint (which can silently rev under us — that drift caused the
    # PCA-16 cmd_secbert mismatch). Fall back to HF only if the local dir
    # is missing (e.g. fresh checkout that hasn't run the export yet).
    secbert_local = models_dir / "preprocess" / "secbert"
    secbert_tokenizer_local = models_dir / "preprocess" / "secbert_tokenizer"
    if secbert_local.is_dir() and (secbert_local / "config.json").exists():
        secbert_model_src = str(secbert_local)
        secbert_tok_src = (
            str(secbert_tokenizer_local)
            if secbert_tokenizer_local.is_dir()
            else str(secbert_local)
        )
        log.info(
            "loading_secbert",
            model_src=secbert_model_src,
            tokenizer_src=secbert_tok_src,
            device=device,
            hermetic=True,
        )
    else:
        secbert_model_src = SECBERT_MODEL_ID
        secbert_tok_src = SECBERT_MODEL_ID
        log.warning(
            "loading_secbert_from_hub",
            model_id=SECBERT_MODEL_ID,
            note="local secbert/ weights missing — runtime will hit the hub",
        )
    tokenizer = AutoTokenizer.from_pretrained(secbert_tok_src)
    model = AutoModel.from_pretrained(secbert_model_src).to(device)
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

    if gnn_propagation_path.exists():
        # Phase A artifact was saved with joblib (compressed); the legacy
        # `gnn_metadata.pkl` is plain pickle. Use joblib here.
        import joblib  # noqa: PLC0415 — adapter-layer import is allowed

        try:
            gnn_raw = joblib.load(gnn_propagation_path)
        except Exception as exc:
            raise ModelRegistryError(
                f"failed to load {gnn_propagation_path.name}: {exc}"
            ) from exc
        gnn = _build_gnn_meta(gnn_raw)
        log.info(
            "gnn_metadata_source",
            path=str(gnn_propagation_path),
            threshold=gnn.threshold,
            note="Phase-A propagation metadata (no-rule-level, 55-col, threshold 0.7743)",
        )
    else:
        gnn_raw = _load_pickle(models_dir / required["gnn_metadata"], "dict")
        gnn = _build_gnn_meta(gnn_raw)
        log.warning(
            "gnn_metadata_source_legacy",
            path=str(models_dir / required["gnn_metadata"]),
            threshold=gnn.threshold,
            note="falling back to legacy gnn_metadata.pkl — run Phase A export",
        )

    canonical = json.loads((models_dir / required["canonical_json"]).read_text())
    canonical_order: list[str] = canonical["all_selected_columns"]
    # Drift guard: the in-code FEATURE_COLUMNS list is the authoritative,
    # explicit ordering used at training; the JSON shipped alongside the
    # scaler must agree. If they ever drift, fail loud at startup rather
    # than silently mis-ordering features into the StandardScaler.
    if canonical_order != FEATURE_COLUMNS:
        raise ModelRegistryError(
            "selected_features_top25.json all_selected_columns does not match "
            "FEATURE_COLUMNS (training-notebook canonical order). Refusing to "
            "load: a permuted scaler input would corrupt every model output."
        )

    # Empirical training-dominant cmd_secbert vec (Phase G — see
    # `_cmd_secbert_for` for the why). Optional; if absent we fall back to
    # the pure SecBERT path which we know lands far from training.
    cmd_dominant_16: np.ndarray | None = None
    dom_path = models_dir / "preprocess" / "secbert_dominant_vectors.json"
    if dom_path.exists():
        try:
            dom = json.loads(dom_path.read_text())
            cmd_dominant_16 = np.array(dom["cmd_dominant_16"], dtype=np.float32)
            if cmd_dominant_16.shape != (16,):
                raise ValueError(f"cmd_dominant_16 wrong shape: {cmd_dominant_16.shape}")
            log.info(
                "secbert_cmd_dominant_loaded",
                path=str(dom_path),
                count=int(dom.get("cmd_dominant_count", -1)),
                total=int(dom.get("cmd_total", -1)),
            )
        except Exception as exc:
            raise ModelRegistryError(
                f"failed to load {dom_path.name}: {exc}"
            ) from exc
    else:
        log.warning(
            "secbert_cmd_dominant_missing",
            path=str(dom_path),
            note="missing-cmd alerts will use SecBERT([EMPTY]) which drifts from training",
        )

    pipe = PreprocessingPipeline(
        secbert=secbert,
        log_pca=log_pca,
        cmd_pca=cmd_pca,
        scaler_55=scaler_55,
        canonical_order=canonical_order,
        calibrators=calibrators,
        gnn=gnn,
        cmd_dominant_16=cmd_dominant_16,
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
        raise ModelRegistryError(f"{label} pca has n_components_={pca.n_components_}, expected 16")
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
            f"standard_scaler.pkl fit on {scaler.n_features_in_} features, expected {expected_dim}"
        )
    # Hot-path callers pass NumPy arrays (no column names). The scaler was fit
    # on a pandas DataFrame, so sklearn's _check_feature_names emits a per-row
    # UserWarning. Drop the recorded names; we never use them.
    if hasattr(scaler, "feature_names_in_"):
        del scaler.feature_names_in_


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
    # Phase A's `gnn_propagation_metadata.pkl` ships a clean 55-col scaler;
    # the legacy `gnn_metadata.pkl` ships the Part-1 56-col scaler that we
    # slice down to 55 (matches notebook's `X_scaled[:, :-1]`).
    sliced = _Scaler()
    if src_scaler.n_features_in_ == 55:
        sliced.mean_ = src_scaler.mean_.astype(np.float64)
        sliced.scale_ = src_scaler.scale_.astype(np.float64)
        sliced.var_ = src_scaler.var_.astype(np.float64)
    elif src_scaler.n_features_in_ == 56:
        sliced.mean_ = src_scaler.mean_[:55].astype(np.float64)
        sliced.scale_ = src_scaler.scale_[:55].astype(np.float64)
        sliced.var_ = src_scaler.var_[:55].astype(np.float64)
    else:
        raise ModelRegistryError(
            f"gnn_metadata scaler has n_features_in_={src_scaler.n_features_in_}, expected 55 or 56"
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
    "FEATURE_COLUMNS",
    "GnnMetadata",
    "PreprocessingPipeline",
    "VaeCalibrators",
    "build_pipeline",
]
