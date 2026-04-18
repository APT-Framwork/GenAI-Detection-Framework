#!/usr/bin/env python3
"""Dump STRIX API OpenAPI spec to disk without booting uvicorn.

Usage:
    python infra/scripts/dump_openapi.py apps/web/lib/openapi.json

CI runs this after every backend change and commits the result; the frontend
then regenerates `apps/web/lib/api-types.ts` via `pnpm gen:api-types:offline`.
Drift between the committed spec and the freshly-generated one fails CI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure local src/ is importable when running from repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "apps" / "api" / "src"))

from strix_api.main import create_app  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <output-path>", file=sys.stderr)
        return 2

    target = Path(sys.argv[1])
    target.parent.mkdir(parents=True, exist_ok=True)

    app = create_app()
    spec = app.openapi()
    target.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
    print(f"wrote {target} ({target.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
