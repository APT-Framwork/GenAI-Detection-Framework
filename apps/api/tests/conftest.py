"""Global pytest fixtures for the strix-api package."""

from __future__ import annotations

import os

# Required env vars for any Settings() instantiation during collection.
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("ENV", "dev")
# Tests don't need auth — dev_skip_auth is honored only when ENV=dev.
os.environ.setdefault("AUTH_DEV_SKIP_AUTH", "true")
os.environ.setdefault("AUTH_JWT_SECRET", "test-secret-not-for-prod")
