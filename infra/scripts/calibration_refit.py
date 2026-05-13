"""Phase 2 + 3 + 4: feature extraction → calibrator refit → deployment.

Given the labeled.csv from `calibration_label_jsonl.py`:

  Phase 2 — for each labeled alert_id, pull raw JSON from the Wazuh manager's
            alerts.json, parse it, run preprocessing + VAE forward, record
            (label, recon_loss).
  Phase 3 — fit LogisticRegression on the lab distribution. Hold out 20% for
            validation. Report ROC-AUC + calibration plot points.
  Phase 4 — patch probability_calibrators.pkl with a new key
            'Beta-VAE (Top 25) lab-refit'. DOES NOT auto-switch the active
            calibrator — operator must edit the registry to pick it up.
"""

from __future__ import annotations

import csv
import json
import pickle
import shutil
import subprocess
from pathlib import Path

import numpy as np
import torch

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

# --- repo modules ---
from strix_api.adapters.wazuh_adapter import WazuhAlertAdapter
from strix_api.adapters.preprocessing_pipeline import build_pipeline
from strix_api.adapters.model_loaders.vae import VaeLoader

REPO = Path(__file__).resolve().parents[2]
CALIB = Path("/tmp/strix_calib")
ALERTS_PATH_IN_MANAGER = "/var/ossec/logs/alerts/alerts.json"
MODELS_DIR = REPO / "apps" / "models"
PIPELINE_ARTIFACTS = MODELS_DIR / "preprocess"
VAE_PATH = MODELS_DIR / "vae_model.pth"
CALIBRATORS_PATH = MODELS_DIR / "probability_calibrators.pkl"


# ============================================================================
# Phase 2 — pull raw JSON + extract recon_loss for each labeled alert
# ============================================================================

def load_labeled() -> list[tuple[str, int]]:
    """Returns [(alert_id, label), ...] from labeled.csv."""
    out: list[tuple[str, int]] = []
    with (CALIB / "labeled.csv").open() as fp:
        r = csv.reader(fp)
        next(r)  # header
        for row in r:
            out.append((row[0], int(row[3])))
    return out


def fetch_raw_alerts(alert_ids: set[str]) -> dict[str, dict]:
    """Stream alerts.json from the Wazuh manager and pluck the JSON for each
    alert_id of interest. Returns {alert_id: raw_json}."""
    print(f"  streaming alerts.json from manager (filtering {len(alert_ids):,} alert_ids)…")
    proc = subprocess.Popen(
        ["docker", "exec", "strix_wazuh_manager", "cat", ALERTS_PATH_IN_MANAGER],
        stdout=subprocess.PIPE,
    )
    found: dict[str, dict] = {}
    n_scanned = 0
    assert proc.stdout is not None
    for line in proc.stdout:
        n_scanned += 1
        if n_scanned % 10_000 == 0:
            print(f"    scanned {n_scanned:,} lines, found {len(found):,}/{len(alert_ids):,}")
        try:
            doc = json.loads(line)
        except Exception:
            continue
        aid = doc.get("id")
        if aid in alert_ids:
            found[aid] = doc
            if len(found) == len(alert_ids):
                break
    proc.terminate()
    proc.wait()
    print(f"  scanned {n_scanned:,} lines total; matched {len(found):,}/{len(alert_ids):,}")
    return found


def main() -> None:
    print("=" * 70)
    print("PHASE 2: feature extraction + VAE recon_loss for labeled alerts")
    print("=" * 70)

    # Step 1: labeled set
    labels_list = load_labeled()
    print(f"  loaded {len(labels_list):,} labeled rows from labeled.csv")
    label_map = dict(labels_list)
    alert_ids = set(label_map)
    print()

    # Step 2: pull raw JSON
    raw = fetch_raw_alerts(alert_ids)
    if not raw:
        print("  ✗ no raw alerts matched — exiting")
        return
    print()

    # Step 3: bootstrap pipeline + VAE
    print("  bootstrapping preprocessing pipeline + VAE…")
    pipe = build_pipeline(models_dir=MODELS_DIR)
    vae = VaeLoader.load(VAE_PATH, calibrator=pipe.calibrators.active, device="cpu")
    adapter = WazuhAlertAdapter()
    print("  ✓ pipeline + VAE ready")
    print()

    # Step 4: for each alert, transform → 55-dim → VAE forward → recon_loss
    print("  processing alerts (recon_loss per event)…")
    rows: list[dict] = []
    n_ok, n_err = 0, 0
    for i, (aid, doc) in enumerate(raw.items()):
        if i % 500 == 0 and i > 0:
            print(f"    {i:,}/{len(raw):,} ({n_ok} ok, {n_err} err)")
        try:
            alert = adapter.parse(doc)
            vec = pipe.transform(alert)  # (55,)
            out = vae.batch_forward(vec.reshape(1, -1))
            rows.append({
                "alert_id": aid,
                "label": label_map[aid],
                "recon_loss": float(out.recon_loss[0]),
                "vae_prob_old": float(out.malicious_prob[0]),
                "vae_uncert": float(out.uncertainty[0]),
            })
            n_ok += 1
        except Exception as exc:
            n_err += 1
            if n_err <= 3:
                print(f"    err on {aid}: {type(exc).__name__}: {exc}")
    print(f"  ✓ extracted {n_ok:,} rows ({n_err} errors)")
    print()

    if n_ok < 200:
        print("  ✗ too few rows for a sensible fit. Exiting.")
        return

    # Save raw extraction (so subsequent runs can skip Phase 2)
    out_csv = CALIB / "features.csv"
    with out_csv.open("w", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=["alert_id", "label", "recon_loss", "vae_prob_old", "vae_uncert"])
        w.writeheader()
        w.writerows(rows)
    print(f"  → saved features to {out_csv}")
    print()

    # ========================================================================
    # Phase 3 — fit calibrator
    # ========================================================================
    print("=" * 70)
    print("PHASE 3: fit new LogisticRegression on lab distribution")
    print("=" * 70)

    X = np.array([[r["recon_loss"]] for r in rows], dtype=np.float64)
    y = np.array([r["label"] for r in rows], dtype=np.int64)

    print(f"  total samples: {len(y):,}   malicious: {(y == 1).sum():,}   benign: {(y == 0).sum():,}")

    # Class-balanced split. With our ~3300 benign / ~12000 malicious, we want
    # stratification so the validation set isn't degenerate.
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"  train: {len(y_tr):,}   test: {len(y_te):,}")

    # Train. class_weight='balanced' compensates for the class imbalance.
    new_cal = LogisticRegression(class_weight="balanced", max_iter=1000)
    new_cal.fit(X_tr, y_tr)
    print(f"  fit complete  coef={new_cal.coef_[0][0]:.4f}  intercept={new_cal.intercept_[0]:.4f}")

    # Compare to the OLD calibrator
    with CALIBRATORS_PATH.open("rb") as fp:
        cals = pickle.load(fp)
    old_cal = cals["Beta-VAE (Top 25)"]
    print(f"  old calibrator coef={old_cal.coef_[0][0]:.4f}  intercept={old_cal.intercept_[0]:.4f}")
    print()

    # Validate both on the test set
    p_old = old_cal.predict_proba(X_te)[:, 1]
    p_new = new_cal.predict_proba(X_te)[:, 1]
    auc_old = roc_auc_score(y_te, p_old)
    auc_new = roc_auc_score(y_te, p_new)
    print(f"  ROC-AUC on test (higher = better):")
    print(f"    OLD calibrator: {auc_old:.4f}")
    print(f"    NEW calibrator: {auc_new:.4f}")
    print()

    # Mean prob per class — sanity check on direction
    print("  Mean P(malicious) by class on test:")
    print(f"    OLD: MAL={p_old[y_te == 1].mean():.4f}   BEN={p_old[y_te == 0].mean():.4f}   (want MAL >> BEN)")
    print(f"    NEW: MAL={p_new[y_te == 1].mean():.4f}   BEN={p_new[y_te == 0].mean():.4f}")
    print()

    # ========================================================================
    # Phase 4 — patch probability_calibrators.pkl
    # ========================================================================
    print("=" * 70)
    print("PHASE 4: deploy (save under new key, do NOT switch active)")
    print("=" * 70)

    # Backup
    backup_path = CALIBRATORS_PATH.with_suffix(".pkl.bak")
    if not backup_path.exists():
        shutil.copy2(CALIBRATORS_PATH, backup_path)
        print(f"  ✓ backed up old calibrators to {backup_path}")

    # Inject new key
    cals["Beta-VAE (Top 25) lab-refit"] = new_cal
    with CALIBRATORS_PATH.open("wb") as fp:
        pickle.dump(cals, fp)
    print(f"  ✓ wrote new calibrator under key 'Beta-VAE (Top 25) lab-refit'")
    print(f"  keys now in probability_calibrators.pkl:")
    for k in cals.keys():
        c = cals[k]
        marker = " ← active" if k == "Beta-VAE (Top 25)" else ""
        print(f"    {k}{marker}")
    print()

    print("=" * 70)
    print("DONE")
    print("=" * 70)
    print()
    print(f"  New calibrator (coef, intercept) = ({new_cal.coef_[0][0]:.3f}, {new_cal.intercept_[0]:.3f})")
    print(f"  Old calibrator (coef, intercept) = ({old_cal.coef_[0][0]:.3f}, {old_cal.intercept_[0]:.3f})")
    print(f"  Sign flip detected: {(new_cal.coef_[0][0] * old_cal.coef_[0][0]) < 0}")
    print()
    print("  To switch the active calibrator to the lab-refit version, edit:")
    print("    apps/api/src/strix_api/adapters/preprocessing_pipeline.py")
    print('    change   active_key: str = "Beta-VAE (Top 25)"')
    print('    to       active_key: str = "Beta-VAE (Top 25) lab-refit"')
    print("  Then restart honcho.")


if __name__ == "__main__":
    main()
