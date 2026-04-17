"""
Quick inspection: show 5 benign + 5 malicious alerts with their features.
"""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from synthetic.data_loader import FEATURE_COLUMNS
from synthetic.real_data_loader import load_real_data

mal_merged, benign_df = load_real_data()

print("\n" + "=" * 90)
print("5 MALICIOUS ALERTS (with CKC stage + first 10 features)")
print("=" * 90)
# Pick 5 from different CKC stages
for stage in [1, 3, 4, 5, 7]:
    row = mal_merged[mal_merged['ckc_stage'] == stage].iloc[0]
    feats = row[FEATURE_COLUMNS].values.astype(float)
    print(f"\n--- CKC Stage S{stage} | timestamp: {row['timestamp']} | machine: {row['machine_name']} ---")
    print(f"  Features (shape={feats.shape}, non-zero={np.count_nonzero(feats)}):")
    for i, col in enumerate(FEATURE_COLUMNS[:10]):
        print(f"    {col:40s} = {feats[i]:.6f}")
    print(f"    ... ({len(FEATURE_COLUMNS)-10} more features)")
    print(f"  Feature stats: min={feats.min():.4f}, max={feats.max():.4f}, mean={feats.mean():.4f}, std={feats.std():.4f}")

print("\n" + "=" * 90)
print("5 BENIGN ALERTS (first 10 features)")
print("=" * 90)
rng = np.random.default_rng(42)
indices = rng.choice(len(benign_df), size=5, replace=False)
for i, idx in enumerate(indices):
    row = benign_df.iloc[idx]
    feats = row[FEATURE_COLUMNS].values.astype(float)
    print(f"\n--- Benign Alert #{i+1} (row {idx}) ---")
    print(f"  Features (shape={feats.shape}, non-zero={np.count_nonzero(feats)}):")
    for j, col in enumerate(FEATURE_COLUMNS[:10]):
        print(f"    {col:40s} = {feats[j]:.6f}")
    print(f"    ... ({len(FEATURE_COLUMNS)-10} more features)")
    print(f"  Feature stats: min={feats.min():.4f}, max={feats.max():.4f}, mean={feats.mean():.4f}, std={feats.std():.4f}")

print("\n" + "=" * 90)
print("FEATURE COLUMN LIST (all 55)")
print("=" * 90)
for i, col in enumerate(FEATURE_COLUMNS):
    print(f"  [{i:2d}] {col}")
