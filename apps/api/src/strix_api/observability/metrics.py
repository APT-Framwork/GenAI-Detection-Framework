"""Prometheus metrics.

All metric names live here so §8.2 is the single source of truth. Every
component imports what it needs and instruments inline — no magic.

Metric names follow the `strix_*` prefix convention except the HTTP
histogram, which uses the Prometheus default `http_request_duration_seconds`.
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    make_asgi_app,
)

# ---------------------------------------------------------------- registry
# Use the default global registry so process exporters (gc, cpu) come along
# for free. Tests that need isolation can pass their own `CollectorRegistry`
# to the helpers below.
REGISTRY: CollectorRegistry = CollectorRegistry(auto_describe=True)

# `make_asgi_app()` without a registry argument picks up the default global,
# which includes process exporters. We re-export it so `main.py` can mount it.
metrics_app = make_asgi_app()


# ---------------------------------------------------------------- ingest
alerts_ingested_total = Counter(
    "strix_alerts_ingested_total",
    "Alerts consumed from upstream (Wazuh).",
    ["source"],
)

# ---------------------------------------------------------------- pipeline
normalizer_duration_seconds = Histogram(
    "strix_normalizer_duration_seconds",
    "Time spent in each normalizer stage.",
    ["stage"],  # parse | flatten | secbert | pca | scale
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

inference_duration_seconds = Histogram(
    "strix_inference_duration_seconds",
    "Forward-pass latency per model.",
    ["model"],  # ae | vae | transformer | gnn | dqn
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

inference_batch_size = Histogram(
    "strix_inference_batch_size",
    "Items per inference batch (post-flush).",
    ["model"],
    buckets=(1, 2, 4, 8, 16, 32, 64),
)

# ---------------------------------------------------------------- streams
stream_depth = Gauge(
    "strix_stream_depth",
    "Current length of a Redis stream; alert > 10000 for > 30s.",
    ["stream"],
)

session_active_count = Gauge(
    "strix_session_active_count",
    "Number of open attack chains (session hashes in Redis).",
)

# ---------------------------------------------------------------- chains / DQN
attack_chain_opened_total = Counter(
    "strix_attack_chain_opened_total",
    "Attack chains opened.",
)

attack_chain_closed_total = Counter(
    "strix_attack_chain_closed_total",
    "Attack chains closed.",
    ["close_reason"],  # INTERVENTION | IDLE_TIMEOUT | MAX_STEPS
)

dqn_action_total = Counter(
    "strix_dqn_action_total",
    "DQN decisions emitted.",
    ["action_name"],
)

# ---------------------------------------------------------------- external APIs
external_api_duration_seconds = Histogram(
    "strix_external_api_duration_seconds",
    "Upstream API call latency.",
    ["api"],  # hibp | virustotal | llm
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

external_api_errors_total = Counter(
    "strix_external_api_errors_total",
    "Upstream API failures by kind.",
    ["api", "error_kind"],
)

# ---------------------------------------------------------------- cache
cache_hits_total = Counter(
    "strix_cache_hits_total", "Cache hits.", ["cache"]
)
cache_misses_total = Counter(
    "strix_cache_misses_total", "Cache misses.", ["cache"]
)

# ---------------------------------------------------------------- SSE
sse_clients_active = Gauge(
    "strix_sse_clients_active",
    "Live SSE client connections.",
    ["endpoint"],
)

# ---------------------------------------------------------------- drift (Phase 8 placeholder)
score_distribution_kl_divergence = Gauge(
    "strix_score_distribution_kl_divergence",
    "KL divergence between live score distribution and training baseline.",
    ["model"],
)


__all__ = [
    "CONTENT_TYPE_LATEST",
    "REGISTRY",
    "alerts_ingested_total",
    "attack_chain_closed_total",
    "attack_chain_opened_total",
    "cache_hits_total",
    "cache_misses_total",
    "dqn_action_total",
    "external_api_duration_seconds",
    "external_api_errors_total",
    "generate_latest",
    "inference_batch_size",
    "inference_duration_seconds",
    "metrics_app",
    "normalizer_duration_seconds",
    "score_distribution_kl_divergence",
    "session_active_count",
    "sse_clients_active",
    "stream_depth",
]
