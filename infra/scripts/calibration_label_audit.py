"""Audit lab-collected alerts for calibration refit feasibility.

Reports class balance under a candidate labeling rule and prints a
sample of borderline rows so the operator can sanity-check the rule
before extracting features.

Run:  apps/api/.venv/bin/python infra/scripts/calibration_label_audit.py
"""

from __future__ import annotations

import os
import subprocess
from collections import Counter

# Shell out to `docker exec strix_postgres psql` with CSV output.
# Avoids a python DB-driver dependency (project uses asyncpg, no sync driver).
PSQL_CMD = [
    "docker", "exec", "-i", "strix_postgres",
    "psql",
    "-U", os.environ.get("DB_USER", "strix"),
    "-d", os.environ.get("DB_NAME", "strix"),
    "-At",  # tuples-only, unaligned
    "-F", "\t",  # tab-separated
    "-c",
]


def _query_csv(sql: str) -> list[list[str]]:
    out = subprocess.check_output(PSQL_CMD + [sql]).decode()
    return [line.split("\t") for line in out.strip().splitlines() if line]


# Labeling rule (binary):
#   label = 1 (malicious) if the event has any MITRE technique tag
#   label = 0 (benign)    otherwise
# Rationale: Wazuh's rule decoders are tuned so that attack-pattern rules
# emit a MITRE technique; routine system events do not. If you want a
# stricter rule (e.g. require rule_level>=10 for malicious, or require
# rule.id in a specific 100xxx range for benign), edit the SQL below.
LABEL_QUERY = """
SELECT
    -- ground truth label
    CASE
        WHEN array_length(mitre_techniques, 1) > 0 THEN 1
        ELSE 0
    END                                       AS label,

    -- features available in detections (paired by alert_id)
    d.ae_anomaly_score                        AS ae_score,
    d.ae_recon_error                          AS ae_recon,
    d.vae_malicious_prob                      AS vae_prob,
    d.vae_uncertainty                         AS vae_uncert,
    d.gnn_node_risk                           AS gnn_risk,
    a.mitre_techniques                        AS techniques,
    a.rule_id                                 AS rule_id,
    a.host_id                                 AS host_id
FROM alerts a
JOIN detections d USING (alert_id)
"""


def main() -> None:
    raw = _query_csv(LABEL_QUERY)
    if not raw:
        print("No data in DB — run a simulation first.")
        return

    # Parse rows into typed tuples: (label, ae_score, ae_recon, vae_prob,
    #                                vae_uncert, gnn_risk, techniques, rule_id, host_id)
    rows: list[tuple] = []
    for r in raw:
        def f(x):  # float-or-None
            return None if x in ("", "\\N") else float(x)
        rows.append((int(r[0]), f(r[1]), f(r[2]), f(r[3]), f(r[4]), f(r[5]), r[6], r[7], r[8]))

    labels = [r[0] for r in rows]
    counts = Counter(labels)
    n = len(rows)
    n_mal = counts.get(1, 0)
    n_ben = counts.get(0, 0)

    print("=" * 60)
    print("CALIBRATION LABEL AUDIT")
    print("=" * 60)
    print(f"Total events:    {n:,}")
    print(f"  malicious (1): {n_mal:,}  ({100*n_mal/n:.1f}%)")
    print(f"  benign    (0): {n_ben:,}  ({100*n_ben/n:.1f}%)")
    print()

    # Per-class distribution of the current vae_malicious_prob
    # (this is what the CURRENT calibrator outputs — if the calibrator
    # were correctly calibrated, malicious events should have high prob
    # and benign events should have low prob).
    def stats(values: list[float], k: str) -> None:
        if not values:
            print(f"  {k}: (no data)")
            return
        vs = sorted(values)
        p = lambda q: vs[int(len(vs) * q)]
        print(
            f"  {k}: min={vs[0]:.3f} p25={p(0.25):.3f} p50={p(0.5):.3f} "
            f"p75={p(0.75):.3f} max={vs[-1]:.3f}  mean={sum(vs)/len(vs):.3f}"
        )

    print("Current VAE output distribution by ground-truth label:")
    print("  (calibrator is well-calibrated when MAL>>BEN; inverted when MAL<<BEN)")
    print()
    mal_vae = [r[3] for r in rows if r[0] == 1 and r[3] is not None]
    ben_vae = [r[3] for r in rows if r[0] == 0 and r[3] is not None]
    stats(mal_vae, "MAL vae_prob")
    stats(ben_vae, "BEN vae_prob")
    print()

    print("VAE recon_error (calibrator input) by ground-truth label:")
    mal_ae = [r[2] for r in rows if r[0] == 1 and r[2] is not None]
    ben_ae = [r[2] for r in rows if r[0] == 0 and r[2] is not None]
    stats(mal_ae, "MAL ae_recon")
    stats(ben_ae, "BEN ae_recon")
    print()

    print("GNN node risk by ground-truth label (sanity check — should differ):")
    mal_gnn = [r[4] for r in rows if r[0] == 1 and r[4] is not None]
    ben_gnn = [r[4] for r in rows if r[0] == 0 and r[4] is not None]
    stats(mal_gnn, "MAL gnn_risk")
    stats(ben_gnn, "BEN gnn_risk")
    print()

    # Feasibility verdict
    print("=" * 60)
    print("FEASIBILITY")
    print("=" * 60)
    MIN_PER_CLASS = 500
    if n_mal >= MIN_PER_CLASS and n_ben >= MIN_PER_CLASS:
        print(f"✓ Sufficient samples per class (need ≥{MIN_PER_CLASS} each).")
        print("  Proceed to Phase 2: feature extraction + recon_loss recomputation.")
    else:
        print(f"✗ Need ≥{MIN_PER_CLASS} per class. Currently:")
        print(f"    MAL: {n_mal:,}  (need {max(0, MIN_PER_CLASS - n_mal):,} more)")
        print(f"    BEN: {n_ben:,}  (need {max(0, MIN_PER_CLASS - n_ben):,} more)")
        print("  Suggestion: run benign-only traffic for ~30 min to bulk up class 0.")


if __name__ == "__main__":
    main()
