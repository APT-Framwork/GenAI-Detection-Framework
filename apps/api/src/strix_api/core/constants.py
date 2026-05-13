"""Hard-coded business constants.

§6.3 is the single source of truth — no magic numbers elsewhere in the
codebase. Tickets that need to mutate these are called out in §10.
"""

from __future__ import annotations

import os
from typing import Final

# ---- Chain lifecycle (§5.4, §6.3) -----------------------------------
# Smoke testing on this lab found AE/VAE/Transformer have an INVERTED
# malice signal (benign rule-80789 → vae_prob ≈ 1.0, attack rule-1001xx → ≈ 0.15);
# only the GNN learned proper labels. So the chain-open gate uses GNN node-risk
# only. AE/VAE thresholds below are kept as INFORMATIONAL anomaly thresholds
# (UI diagnostics + downstream references) — they no longer drive open/skip.
#
# The default 0.7743 is from gnn_propagation_metadata.pkl. Lowered for
# synthetic-traffic testing via STRIX_GNN_OPEN_THRESHOLD — Caldera-driven runs
# leave the env var unset and keep the trained threshold.
CHAIN_OPEN_GNN_THRESHOLD: Final[float] = float(
    os.environ.get("STRIX_GNN_OPEN_THRESHOLD", "0.7743")
)
CHAIN_OPEN_VAE_THRESHOLD: Final[float] = 0.5  # informational / anomaly diagnostic
CHAIN_OPEN_AE_THRESHOLD: Final[float] = 1.0  # informational / anomaly diagnostic

# Demo-tunable: with only 2 victims and high-rate auditd traffic, the
# default 50-step / 120-min binding causes every alert in a run to coalesce
# into one chain per host. Lowering both via env yields a fresh chain per
# tactic, so the FINAL REPORT histogram and the dashboard "rl" stream
# reflect the actual MITRE phases instead of one giant rolled-over session.
CHAIN_IDLE_TIMEOUT_MINUTES: Final[int] = int(
    os.environ.get("STRIX_CHAIN_IDLE_TIMEOUT_MIN", "120")
)
CHAIN_MAX_STEPS: Final[int] = int(
    os.environ.get("STRIX_CHAIN_MAX_STEPS", "50")
)

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

# ---- DQN decision gates (lab-distribution mitigation) ---------------
# The DQN was trained on Linux-APT-Dataset-2024 distribution. On the live
# Caldera lab, two failure modes appear in the data (verified via direct
# postgres queries on a 5-tactic APT29 run):
#
#   STORY 1 — Distribution shift saturates VAE on benign noise. AE
#   reconstruction error climbs to ~44 on lab events (training-time max
#   was ~12). The VAE calibrator is logistic-regression on recon_error,
#   so it pegs to 0.999 → DQN reads "high VAE prob" as "attack" and
#   outputs ISOLATE_HOST on plain auditd events. Observed 97,888 stage-0
#   ISOLATEs with gnn_node_risk = 0 (the GNN — the only correct signal —
#   said "benign", DQN ignored it).
#
#   STORY 2 — Reward shaping at training time taught the DQN that
#   intervention after stage 7 has no value (it can't prevent what
#   already happened). On lab data, Q(ESCALATE | stage=7) is NEGATIVE.
#   2,957 stage-7 events were silently downgraded to LOW_ALERT.
#
# These three gates fix both without retraining. Tunable via env.

# OOD gate: AE recon error above this threshold ⇒ AE/VAE inputs to the
# DQN are unreliable; bypass the DQN and decide on GNN risk only.
# Training-time AE max ≈ 12, lab-time tail ≈ 44, so 8 sits in OOD-only.
DQN_OOD_AE_RECON_THRESHOLD: Final[float] = float(
    os.environ.get("STRIX_DQN_OOD_AE_RECON_THRESHOLD", "8.0")
)

# Q-margin abstention: if max(Q) − second_max(Q) is below this, the
# argmax is essentially noise — force NO_OP. Silent-stage-7 ESCALATE
# bucket had Q-margin 0.18, so 0.4 cleanly gates that out.
DQN_Q_MARGIN_MIN: Final[float] = float(
    os.environ.get("STRIX_DQN_Q_MARGIN_MIN", "0.4")
)

# Stage-7 force-escalate: regardless of DQN output, if the chain lands
# on CKC stage 7 (Action — kill-chain endpoint) and the GNN has any
# meaningful node risk, force ESCALATE. Reverses the negative-Q learned
# behaviour from Story 2.
DQN_STAGE7_FORCE_ESCALATE_GNN_MIN: Final[float] = float(
    os.environ.get("STRIX_DQN_STAGE7_GNN_MIN", "0.5")
)

# Stage-5/6 predetection: the dashboard's whole pitch is "agent intervenes
# BEFORE the chain reaches stage 7". The DQN as trained almost never
# escalates at Install (5) or C2 (6) on this lab — observed 2/2473
# escalates over a 7-min run, both at stage 7. Empirical GNN audit:
#   stage 5 chains: 671/1007 detections have gnn_node_risk >= 0.7743
#   stage 6 chains: similar floor; the lab GNN sits at exactly 0.7743 for
#   >50% of all events, so 0.7743 is the true signal cutoff.
# Default both at CHAIN_OPEN_GNN_THRESHOLD (0.7743). Raise the env var to
# tighten if FP rate is too high.
DQN_STAGE5_PREDETECT_GNN_MIN: Final[float] = float(
    os.environ.get("STRIX_DQN_STAGE5_GNN_MIN", "0.7743")
)
DQN_STAGE6_PREDETECT_GNN_MIN: Final[float] = float(
    os.environ.get("STRIX_DQN_STAGE6_GNN_MIN", "0.7743")
)

# Master kill-switch for the DQN gate ladder. Default ON. Set to "false"
# / "0" to run the system as pure-RL (no overrides) — the DQN's argmax
# ships downstream untouched, even at stage 5+ and under AE OOD spikes.
# Intended for ablation runs.
DQN_GATES_ENABLED: Final[bool] = os.environ.get(
    "STRIX_DQN_GATES_ENABLED", "true"
).strip().lower() not in ("0", "false", "no", "off")
