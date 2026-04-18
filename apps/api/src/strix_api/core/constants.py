"""Hard-coded business constants.

§6.3 is the single source of truth — no magic numbers elsewhere in the
codebase. Tickets that need to mutate these are called out in §10.
"""

from __future__ import annotations

from typing import Final

# ---- Chain lifecycle (§5.4, §6.3) -----------------------------------
# ⚠️ PRELIMINARY — recalibrate in P2-9 against ≥1-week real-stream sample.
CHAIN_OPEN_VAE_THRESHOLD: Final[float] = 0.5
CHAIN_OPEN_AE_THRESHOLD: Final[float] = 1.0

CHAIN_IDLE_TIMEOUT_MINUTES: Final[int] = 120  # §12 Q5 (was 30, revised)
CHAIN_MAX_STEPS: Final[int] = 50  # mirrors APTEnvironment.max_steps

# ---- Infection + risk (§6.3) ----------------------------------------
INFECTION_VAE_PROB_THRESHOLD: Final[float] = 0.7

# ---- GNN (§6.3) -----------------------------------------------------
GNN_WINDOW_MINUTES: Final[int] = 60
GNN_SNAPSHOT_INTERVAL_SECONDS: Final[int] = 30

# ---- Global risk (§12 Q4) -------------------------------------------
GLOBAL_RISK_WINDOW_MINUTES: Final[int] = 60
# Coefficients from §4.1 Threat Intensity / Global Risk row
GLOBAL_RISK_COEF_VAE_MEAN: Final[float] = 0.4
GLOBAL_RISK_COEF_GNN_MAX: Final[float] = 0.3
GLOBAL_RISK_COEF_ANOMALY_RATE: Final[float] = 0.2
GLOBAL_RISK_COEF_RISK_GROWTH: Final[float] = 0.1

# ---- LLM caches (§5.14) ---------------------------------------------
LLM_SENTINEL_RESULT_TTL_SECONDS: Final[int] = 300
LLM_LIVE_FEED_SUMMARY_CACHE_SIZE: Final[int] = 10_000

# ---- Feature engineering (§5.10) ------------------------------------
FEATURE_VECTOR_DIM: Final[int] = 55
STATE_VECTOR_DIM: Final[int] = 13
AE_LATENT_DIM: Final[int] = 64
DQN_ACTION_SPACE: Final[int] = 5
