"""Model-registry adapter.

Responsibilities (§5.9):
1. Read `registry.json`.
2. Verify each listed artifact exists on disk.
3. Verify SHA-256 matches (when `MODELS_VERIFY_CHECKSUMS=true`).
4. Surface which preprocessing artifacts are still `MISSING` so worker
   startup aborts with a clear message instead of crashing mid-inference.

Phase 1 onwards wires actual loader classes into this module; for Phase 0
we only validate the manifest.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from strix_api.api.errors import ModelRegistryError
from strix_api.observability import get_logger

log = get_logger("strix_api.adapters.model_registry")


@dataclass(frozen=True)
class ModelEntry:
    key: str
    name: str
    version: str
    file: Path
    weights_sha256: str


@dataclass(frozen=True)
class RegistryState:
    models: dict[str, ModelEntry]
    missing_artifacts: list[str]


def _sha256_of(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def load_registry(
    registry_path: Path, models_dir: Path, *, verify_checksums: bool = True
) -> RegistryState:
    if not registry_path.exists():
        raise ModelRegistryError(f"registry.json missing at {registry_path}")

    data = json.loads(registry_path.read_text())
    models: dict[str, ModelEntry] = {}

    for key, meta in data.get("models", {}).items():
        artifact = models_dir / meta["file"]
        if not artifact.exists():
            raise ModelRegistryError(
                f"model artifact missing: {artifact} (registry key={key})"
            )
        if verify_checksums:
            actual = _sha256_of(artifact)
            expected = meta["weightsSha256"]
            if actual != expected:
                raise ModelRegistryError(
                    f"checksum mismatch for {artifact}: expected {expected}, "
                    f"got {actual}"
                )
        models[key] = ModelEntry(
            key=key,
            name=meta["name"],
            version=meta["version"],
            file=artifact,
            weights_sha256=meta["weightsSha256"],
        )

    missing = [
        f"{key} ({spec.get('file', '?')})"
        for key, spec in data.get("preprocessingArtifacts", {}).items()
        if spec.get("status") == "MISSING"
        or not (models_dir / spec.get("file", "")).exists()
    ]

    if missing:
        log.warning(
            "preprocessing_artifacts_missing",
            missing=missing,
            blocking_phase="P1 onwards (feature engineering cannot run without these)",
        )

    log.info(
        "model_registry_loaded",
        models=[m.key for m in models.values()],
        missing=missing,
        checksums_verified=verify_checksums,
    )

    return RegistryState(models=models, missing_artifacts=missing)


__all__ = ["ModelEntry", "RegistryState", "load_registry"]
