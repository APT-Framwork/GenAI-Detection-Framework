"""Find which 13 features are missing and check if they exist under different names."""
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from synthetic.real_data_loader import FEATURE_COLUMNS

feat_df = pd.read_parquet(r'g:\pfe\MLA_PROJET_RL\feature_selection_outputs2\feature_matrix_no_leakage.parquet')

print("Parquet columns:", len(feat_df.columns))
print()

missing = [c for c in FEATURE_COLUMNS if c not in feat_df.columns]
found = [c for c in FEATURE_COLUMNS if c in feat_df.columns]
print(f"Found: {len(found)}/55")
print(f"Missing 13 features:")
for m in missing:
    print(f"  - {m}")
    # Try to find similar column names
    similar = [c for c in feat_df.columns if m.split('_')[0] in c.lower()]
    if similar:
        print(f"    Similar in parquet: {similar[:3]}")

print("\nAll parquet columns:")
for c in sorted(feat_df.columns):
    print(f"  {c}")
