"""Observability primitives: structured logging, Prometheus metrics."""

from strix_api.observability.logging import configure_logging, get_logger
from strix_api.observability.metrics import (
    alerts_ingested_total,
    attack_chain_closed_total,
    attack_chain_opened_total,
    cache_hits_total,
    cache_misses_total,
    dqn_action_total,
    external_api_duration_seconds,
    external_api_errors_total,
    inference_batch_size,
    inference_duration_seconds,
    metrics_app,
    normalizer_duration_seconds,
    score_distribution_kl_divergence,
    session_active_count,
    sse_clients_active,
    stream_depth,
)

__all__ = [
    "alerts_ingested_total",
    "attack_chain_closed_total",
    "attack_chain_opened_total",
    "cache_hits_total",
    "cache_misses_total",
    "configure_logging",
    "dqn_action_total",
    "external_api_duration_seconds",
    "external_api_errors_total",
    "get_logger",
    "inference_batch_size",
    "inference_duration_seconds",
    "metrics_app",
    "normalizer_duration_seconds",
    "score_distribution_kl_divergence",
    "session_active_count",
    "sse_clients_active",
    "stream_depth",
]
