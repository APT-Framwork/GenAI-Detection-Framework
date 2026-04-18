# Runbook — Wrong model weights loaded

**Symptom:** worker logs `model_registry_loaded` shows a model `version`
or `weightsSha256` that doesn't match what's in source control, OR
predictions look obviously wrong (e.g. every alert flagged malicious).

## Why this can happen

`apps/models/registry.json` lists the SHA-256 of every checkpoint and
the worker calls `load_registry(..., verify_checksums=True)` at boot —
the boot will FAIL (`ModelRegistryError`) if checksums don't match.

So if you see this, one of:
1. Someone bumped `registry.json` without re-uploading the matching `.pth`.
2. The `apps/models/` volume is shared with a different branch.
3. `MODELS_VERIFY_CHECKSUMS=false` was set (DON'T DO THIS in prod).

## Recovery

```bash
# Re-pull the canonical models from origin/Platforme (or whichever branch is the source of truth)
git fetch origin
git checkout origin/Platforme -- apps/models/

# Verify checksums match registry.json
python -c "
from pathlib import Path
from strix_api.adapters.model_registry import load_registry
state = load_registry(Path('apps/models/registry.json'), Path('apps/models'),
                      verify_checksums=True)
print('OK:', [m.name for m in state.models.values()])
"

# Restart workers — they'll re-verify on boot
docker compose -f infra/compose.api.yml --profile workers restart
```

## Hot-swap policy

§5.9 says **hot-swap is not supported in 1.0**. To deploy a new model:
1. Re-train.
2. Copy the new `.pth` into `apps/models/` AND update `registry.json` with the new SHA + `version` bump.
3. Rebuild the worker image.
4. Compose rolling restart.
