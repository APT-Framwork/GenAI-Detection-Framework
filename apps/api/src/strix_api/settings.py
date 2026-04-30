"""Hierarchical settings loaded once from environment / .env file.

Every component takes `Settings` via dependency injection; nothing reads
`os.environ` directly. Missing required keys cause the process to refuse
to boot (per P0-6).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DB_")

    host: str = "postgres"
    port: int = 5432
    name: str = "strix"
    user: str = "strix"
    password: SecretStr
    pool_size: int = 10
    max_overflow: int = 5
    pool_timeout_seconds: float = 2.0
    pool_recycle_seconds: int = 300

    @property
    def dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.name}"
        )

    @property
    def sync_dsn(self) -> str:
        """Used by Alembic."""
        return (
            f"postgresql://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.name}"
        )


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_")

    host: str = "redis"
    port: int = 6379
    db: int = 0
    password: SecretStr | None = None
    # Inference reads batches of 64 features and fans out per-task; each task
    # does several pipelined Redis ops. 20 was too small — pool exhaustion
    # surfaced as `Too many connections` after B1 made errors visible.
    max_connections: int = 200

    @property
    def url(self) -> str:
        auth = f":{self.password.get_secret_value()}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


class ModelRegistrySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MODELS_")

    # Absolute path preferred; defaults to repo apps/models/ when dev-running.
    path: Path = Path("/app/models")
    registry_file: str = "registry.json"
    # If True, compute and verify SHA-256 of every .pth/.pkl at boot.
    verify_checksums: bool = True

    @property
    def registry_path(self) -> Path:
        return self.path / self.registry_file


class WazuhSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WAZUH_")

    raw_stream: str = "strix:alerts:raw"
    raw_stream_maxlen: int = 1_000_000
    consumer_group: str = "strix-normalizer"


class ThreatIntelSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="THREAT_INTEL_")

    hibp_api_key: SecretStr | None = None
    hibp_user_agent: str = "strix-platform/1.0"
    virustotal_api_key: SecretStr | None = None
    # Circuit-breaker tuning (applies to all upstreams)
    breaker_fail_max: int = 5
    breaker_reset_timeout_seconds: int = 30


class LlmSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLM_")

    anthropic_api_key: SecretStr | None = None
    sentinel_model: str = "claude-opus-4-7"  # Opus 4.7 per §5.14
    livefeed_model: str = "claude-haiku-4-5-20251001"  # Haiku 4.5
    sentinel_cache_ttl_seconds: int = 300  # LLM_SENTINEL_RESULT_TTL_SECONDS
    livefeed_lru_size: int = 10_000  # LLM_LIVE_FEED_SUMMARY_CACHE_SIZE


class InferenceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INFERENCE_")

    num_shards: int = 4
    shard_id: int | None = None  # set per-worker replica
    # Batching defaults (§7.3)
    ae_batch_max: int = 32
    ae_batch_wait_ms: int = 20
    vae_batch_max: int = 32
    vae_batch_wait_ms: int = 20
    transformer_batch_max: int = 8
    transformer_batch_wait_ms: int = 30
    dqn_batch_max: int = 16
    dqn_batch_wait_ms: int = 10


class ObservabilitySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OBS_")

    log_level: str = "INFO"
    log_json: bool = True
    metrics_port: int = 9090
    tracing_enabled: bool = False
    otlp_endpoint: str | None = None


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_")

    # Phase 0 ships DEV_SKIP_AUTH only — real auth in Phase 4 (P4-9/10/11).
    dev_skip_auth: bool = False
    jwt_secret: SecretStr | None = None
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 7
    # Applying ISOLATE_HOST / BLOCK_USER_IP automatically. Hard-off in 1.0 (§12 Q3).
    auto_response_enabled: bool = False


class PushSettings(BaseSettings):
    """Expo push notifications (M0-B6).

    ``enabled`` defaults to False so tests and default stack boot don't
    touch Expo's API. Flip to True in prod once the mobile app is
    registering tokens; no key is strictly required (Expo's push API is
    public), but setting ``access_token`` switches on enhanced security.
    """

    model_config = SettingsConfigDict(env_prefix="PUSH_")

    enabled: bool = False
    access_token: SecretStr | None = None


class Settings(BaseSettings):
    """Top-level app settings. Read once at import time; inject elsewhere."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["dev", "staging", "prod"] = "dev"
    service_name: str = "strix-api"

    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    models: ModelRegistrySettings = Field(default_factory=ModelRegistrySettings)
    wazuh: WazuhSettings = Field(default_factory=WazuhSettings)
    threat_intel: ThreatIntelSettings = Field(default_factory=ThreatIntelSettings)
    llm: LlmSettings = Field(default_factory=LlmSettings)
    inference: InferenceSettings = Field(default_factory=InferenceSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    push: PushSettings = Field(default_factory=PushSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Single cached Settings instance — use this via FastAPI `Depends`."""
    return Settings()  # type: ignore[call-arg]
