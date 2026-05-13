"""Cross-reference benign_events.jsonl sidecars with the alerts table to
produce ground-truth (alert_id, label) pairs for VAE calibrator refit.

Labeling rules:
  label=0 (benign):   alert occurred within MATCH_WINDOW_S of a JSONL entry
                      on the same host
  label=1 (malicious): alert is in the pre-benign-collection time window
                      AND has at least one MITRE technique tag
  label=skip:         any alert that doesn't satisfy either rule (ambiguous)

Outputs:
  /tmp/strix_calib/labeled.csv   (alert_id, occurred_at, host, label)
  + a summary printed to stdout

Run:  apps/api/.venv/bin/python infra/scripts/calibration_label_jsonl.py
"""

from __future__ import annotations

import bisect
import csv
import json
import os
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


CALIB_DIR = Path("/tmp/strix_calib")
MATCH_WINDOW_S = 5.0  # alert.occurred_at within ±MATCH_WINDOW_S of jsonl.ts

# Wazuh agent_id → JSONL host name mapping (from `agent_control -l`).
# Wazuh enrolled victim2 as agent 001 and victim1 as agent 002 (inverse of
# the container names!), so JSONL "victim1" must match DB agent "002" and
# JSONL "victim2" must match DB agent "001".
AGENT_TO_JSONL_HOST = {
    "001": "victim2",
    "002": "victim1",
}

# Read the benign-collection start timestamp (from earlier launch step)
BENIGN_START_RAW = Path("/tmp/strix_benign_snap.txt").read_text().strip()
BENIGN_START = datetime.fromisoformat(BENIGN_START_RAW.replace("Z", "+00:00"))


PSQL_CMD = [
    "docker", "exec", "-i", "strix_postgres",
    "psql",
    "-U", os.environ.get("DB_USER", "strix"),
    "-d", os.environ.get("DB_NAME", "strix"),
    "-At", "-F", "\t",
    "-c",
]


def query_csv(sql: str) -> list[list[str]]:
    out = subprocess.check_output(PSQL_CMD + [sql]).decode()
    return [line.split("\t") for line in out.strip().splitlines() if line]


# ----------------------- step 1: load JSONL sidecars -----------------------

def load_jsonl_index() -> dict[str, list[float]]:
    """Returns {host_name: [unix_ts, ...]} sorted ascending for bisect lookup.

    Note: JSONL `host` field is the short victim name ("victim1"), but the
    alerts table stores host_id (UUID). We carry the short name through to
    the matching step where we join alerts with hosts.host_name.
    """
    idx: dict[str, list[float]] = defaultdict(list)
    for fn in sorted(CALIB_DIR.glob("benign_*.jsonl")):
        with fn.open() as fp:
            for line in fp:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                ts = rec.get("ts")
                host = rec.get("host")
                if not ts or not host:
                    continue
                t = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                idx[host].append(t)
    for h in idx:
        idx[h].sort()
    return idx


def matches_benign(host: str, alert_ts: float, idx: dict[str, list[float]]) -> bool:
    """True if there's a JSONL entry within ±MATCH_WINDOW_S of alert_ts."""
    arr = idx.get(host)
    if not arr:
        return False
    # bisect for the first entry >= alert_ts - window; check both sides.
    lo = alert_ts - MATCH_WINDOW_S
    hi = alert_ts + MATCH_WINDOW_S
    i = bisect.bisect_left(arr, lo)
    return i < len(arr) and arr[i] <= hi


# ----------------------- step 2: pull alerts in the time window -----------

ALERT_QUERY = """
SELECT
    a.alert_id,
    EXTRACT(EPOCH FROM a.occurred_at)::float                AS ts,
    h.agent_name                                              AS host_name,
    COALESCE(array_length(a.mitre_techniques, 1), 0)         AS n_mitre
FROM alerts a
JOIN hosts h ON h.host_id = a.host_id
ORDER BY a.occurred_at;
"""


# ----------------------- step 3: label -----------------------------------

def main() -> None:
    print(f"Benign collection started at: {BENIGN_START}")
    print(f"Match window: ±{MATCH_WINDOW_S}s")
    print()

    idx = load_jsonl_index()
    n_jsonl = sum(len(v) for v in idx.values())
    print(f"Loaded JSONL sidecars: {n_jsonl:,} entries across hosts {list(idx.keys())}")
    print()

    rows = query_csv(ALERT_QUERY)
    print(f"Loaded {len(rows):,} alerts from DB")
    print()

    benign_start_ts = BENIGN_START.timestamp()
    labels: list[tuple[str, float, str, int]] = []  # (alert_id, ts, host, label)
    stats: Counter[str] = Counter()

    for r in rows:
        alert_id, ts_str, agent_id, n_mitre_str = r
        ts = float(ts_str)
        n_mitre = int(n_mitre_str) if n_mitre_str else 0

        # Map agent ID to the JSONL host name (Wazuh's enrollment order
        # inverted the container names).
        host_name = AGENT_TO_JSONL_HOST.get(agent_id, agent_id)

        in_benign_window = ts >= benign_start_ts

        if in_benign_window and matches_benign(host_name, ts, idx):
            # Strong evidence of benign: JSONL-matched event during the
            # benign-only collection window.
            labels.append((alert_id, ts, host_name, 0))
            stats["benign_jsonl_match"] += 1
        elif not in_benign_window and n_mitre > 0:
            # Pre-benign-window event with MITRE tag — these are Caldera-
            # driven and the labeling-rule errors are negligible.
            labels.append((alert_id, ts, host_name, 1))
            stats["malicious_pre_window_mitre"] += 1
        elif not in_benign_window and n_mitre == 0:
            # Pre-window, no MITRE — likely Wazuh housekeeping; ambiguous.
            stats["skip_pre_window_no_mitre"] += 1
        elif in_benign_window and not matches_benign(host_name, ts, idx):
            # During benign window but unmatched — could be yacine's diag
            # commands or wazuh-internal events; ambiguous.
            stats["skip_in_window_unmatched"] += 1

    print("Labeling outcome:")
    for k, v in stats.most_common():
        print(f"  {k:<30}  {v:>8,}")
    print()

    n_ben = sum(1 for _, _, _, l in labels if l == 0)
    n_mal = sum(1 for _, _, _, l in labels if l == 1)
    print(f"Labels:  malicious={n_mal:,}   benign={n_ben:,}")
    print()

    if n_ben == 0:
        print("✗ No benign matches. Possible causes:")
        print("  - Alert occurred_at and JSONL ts are not within ±MATCH_WINDOW_S")
        print("  - hosts table is missing host_name entries")
        print("  - JSONL files are empty")
        return

    if n_ben < 500:
        print(f"⚠ {n_ben} benign labels — below target of 500. Calibration will be tight.")
    else:
        print(f"✓ {n_ben} benign labels — proceeding.")

    # Save labels for next phase
    out = CALIB_DIR / "labeled.csv"
    with out.open("w", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(["alert_id", "occurred_at_unix", "host_name", "label"])
        w.writerows(labels)
    print(f"  → wrote {len(labels):,} labeled rows to {out}")


if __name__ == "__main__":
    main()
