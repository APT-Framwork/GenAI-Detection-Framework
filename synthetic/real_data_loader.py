"""
Real Data Sequence Builder (Variable Length)
=============================================

Builds VARIABLE-length attack sequences from real Wazuh data.
Each attack sequence ends with S7 and follows natural CKC progression.
Benign sequences use ACTUAL benign data (malicious=0) from the parquet.

Uses the CORRECT 55 feature columns from data_loader.py.
"""

import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# Import the CORRECT feature columns from the existing data_loader
from synthetic.data_loader import FEATURE_COLUMNS, CKC_STAGE_MAP, ATTACK_PATTERNS


# CKC stage string to integer mapping
CKC_MAP = {'S1': 1, 'S2': 2, 'S3': 3, 'S4': 4, 'S5': 5, 'S6': 6, 'S7': 7}

MACHINE_POOL = ['machine-1', 'machine-2', 'machine-3', 'Machine-1-New', 'ubuntu']


def parse_kibana_timestamp(ts_str):
    """Parse Kibana-format timestamp: 'Jan 3, 2024 @ 17:32:37.462'"""
    if pd.isna(ts_str):
        return pd.NaT
    ts_str = str(ts_str).replace(' @ ', ' ')
    for fmt in [
        '%b %d, %Y %H:%M:%S.%f',
        '%b %d, %Y %H:%M:%S',
        '%b  %d %H:%M:%S',
    ]:
        try:
            return pd.Timestamp(datetime.strptime(ts_str, fmt))
        except ValueError:
            continue
    try:
        return pd.Timestamp(pd.to_datetime(ts_str))
    except Exception:
        return pd.NaT


def load_real_data(
    xlsx_path: str = None,
    feature_parquet_path: str = None,
    labels_parquet_path: str = None,
):
    """
    Load and merge real data from xlsx (timestamps/CKC) and parquet (features).

    Returns:
        mal_merged: DataFrame with timestamp, ckc_stage, machine_name, + 55 features (malicious only)
        benign_features: DataFrame with 55 features (benign only, for benign sequences)
    """
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    if xlsx_path is None:
        xlsx_path = os.path.join(root, 'combined_dataset_final_mal_sum.xlsx')
    if feature_parquet_path is None:
        feature_parquet_path = os.path.join(root, 'feature_selection_outputs2', 'feature_matrix_no_leakage.parquet')
    if labels_parquet_path is None:
        labels_parquet_path = os.path.join(root, 'feature_selection_outputs2', 'labels.parquet')

    # Load xlsx with timestamps + CKC (malicious only)
    print("[Real] Loading malicious alerts from xlsx...")
    xlsx_df = pd.read_excel(xlsx_path)
    print(f"       Shape: {xlsx_df.shape}")

    # Parse timestamps
    print("[Real] Parsing timestamps...")
    xlsx_df['timestamp'] = xlsx_df['_source.@timestamp'].apply(parse_kibana_timestamp)

    # Parse CKC stages
    xlsx_df['ckc_stage'] = xlsx_df['cyber_kill_chain_summary'].map(CKC_MAP).fillna(0).astype(int)

    # Machine names
    xlsx_df['machine_name'] = xlsx_df.get('_source.agent.name', 'machine-1')

    # Sort by timestamp
    xlsx_df = xlsx_df.sort_values('timestamp').reset_index(drop=True)

    # Load features from parquet
    print("[Real] Loading features from parquet...")
    feat_df = pd.read_parquet(feature_parquet_path)
    labels_df = pd.read_parquet(labels_parquet_path)

    # Check feature overlap with model's expected features
    available_feats = [c for c in FEATURE_COLUMNS if c in feat_df.columns]
    missing_feats = [c for c in FEATURE_COLUMNS if c not in feat_df.columns]
    print(f"       Features found: {len(available_feats)}/55")
    if missing_feats:
        print(f"       Missing: {missing_feats}")

    # ─── MALICIOUS DATA (for attack sequences) ───
    mal_mask = labels_df['malicious'] == 1
    mal_features = feat_df.loc[mal_mask].reset_index(drop=True)
    print(f"       Malicious rows in parquet: {len(mal_features)}")
    print(f"       Malicious rows in xlsx: {len(xlsx_df)}")

    min_len = min(len(xlsx_df), len(mal_features))
    if len(xlsx_df) != len(mal_features):
        print(f"[Real] WARNING: Row count mismatch, using first {min_len}")

    # Build malicious merged dataframe
    mal_merged = pd.DataFrame()
    mal_merged['timestamp'] = xlsx_df['timestamp'].iloc[:min_len].values
    mal_merged['ckc_stage'] = xlsx_df['ckc_stage'].iloc[:min_len].values
    mal_merged['machine_name'] = xlsx_df['machine_name'].iloc[:min_len].values

    for col in FEATURE_COLUMNS:
        if col in mal_features.columns:
            mal_merged[col] = mal_features[col].iloc[:min_len].values
        else:
            mal_merged[col] = 0.0

    mal_merged = mal_merged.dropna(subset=['timestamp']).reset_index(drop=True)
    mal_merged = mal_merged.sort_values('timestamp').reset_index(drop=True)

    print(f"[Real] Malicious CKC distribution:")
    for stage, count in sorted(mal_merged['ckc_stage'].value_counts().items()):
        print(f"       S{stage}: {count}")

    # ─── BENIGN DATA (for benign sequences) ───
    ben_mask = labels_df['malicious'] == 0
    ben_features = feat_df.loc[ben_mask].reset_index(drop=True)
    print(f"[Real] Benign rows in parquet: {len(ben_features)}")

    # Build benign dataframe with just features
    benign_df = pd.DataFrame()
    for col in FEATURE_COLUMNS:
        if col in ben_features.columns:
            benign_df[col] = ben_features[col].values
        else:
            benign_df[col] = 0.0

    return mal_merged, benign_df


def build_real_sequences(
    mal_merged: pd.DataFrame,
    benign_df: pd.DataFrame,
    num_sequences: int = 500,
    benign_ratio: float = 0.2,
    min_steps: int = 5,
    max_steps: int = 30,
    seed: int = 42,
) -> List[Dict]:
    """
    Build VARIABLE-length attack sequences from time-ordered real data.

    Attack sequences:
    - For each S7 alert, look backwards in time to find preceding alerts
    - Build a natural chain of 5-30 steps ending with S7
    - Maintain real temporal ordering

    Benign sequences:
    - Variable-length (5-15 steps) from actual benign rows
    """
    rng = np.random.default_rng(seed)

    # Data is already sorted by timestamp
    s7_mask = mal_merged['ckc_stage'] == 7
    s7_indices = mal_merged[s7_mask].index.values
    print(f"[Real Sequences] S7 alerts available: {len(s7_indices)}")

    if len(s7_indices) == 0:
        print("[Real Sequences] ERROR: No S7 alerts found!")
        return []

    # Pre-index by CKC stage for fallback sampling
    stage_groups = {}
    for stage in range(1, 8):
        mask = mal_merged['ckc_stage'] == stage
        if mask.any():
            stage_groups[stage] = mal_merged[mask].index.values

    sequences = []
    seq_lengths = []

    # ─── ATTACK SEQUENCES (variable length, ending with S7) ───
    n_attack = num_sequences
    for i in range(n_attack):
        # Pick a random S7 alert as the endpoint
        s7_idx = rng.choice(s7_indices)
        s7_row = mal_merged.iloc[s7_idx]
        s7_time = s7_row['timestamp']

        # Find ALL malicious alerts BEFORE this S7 in time
        before_mask = mal_merged.index < s7_idx  # Data is time-sorted
        preceding_indices = mal_merged[before_mask].index.values

        # Choose a random sequence length between min_steps and max_steps
        seq_len = int(rng.integers(min_steps, max_steps + 1))

        if len(preceding_indices) >= seq_len - 1:
            # Enough: sample (seq_len - 1) from preceding alerts
            chosen_indices = rng.choice(preceding_indices, size=seq_len - 1, replace=False)
            chosen_indices = np.sort(chosen_indices)
        else:
            # Not enough: use all available + pad from other stages
            chosen_indices = preceding_indices.copy()
            remaining = seq_len - 1 - len(chosen_indices)
            if remaining > 0:
                weighted_stages = [1, 3, 3, 4, 4, 5, 5, 3, 4, 3]
                fill_indices = []
                for _ in range(remaining):
                    stage = rng.choice(weighted_stages)
                    if stage in stage_groups:
                        fill_indices.append(rng.choice(stage_groups[stage]))
                if fill_indices:
                    chosen_indices = np.sort(
                        np.concatenate([chosen_indices, np.array(fill_indices)])
                    )

        # Build the sequence
        step_rows = []
        step_stages = []
        step_timestamps = []
        step_machines = []

        for idx in chosen_indices:
            row = mal_merged.iloc[idx]
            step_rows.append(row[FEATURE_COLUMNS].values.astype(np.float32))
            step_stages.append(int(row['ckc_stage']))
            step_timestamps.append(row['timestamp'])
            step_machines.append(str(row['machine_name']))

        # Add the S7 endpoint (always last)
        step_rows.append(s7_row[FEATURE_COLUMNS].values.astype(np.float32))
        step_stages.append(7)
        step_timestamps.append(s7_time)
        step_machines.append(str(s7_row['machine_name']))

        # Sort by timestamp for temporal order
        order = np.argsort(
            [t.timestamp() if pd.notna(t) else 0 for t in step_timestamps]
        )
        step_rows = [step_rows[j] for j in order]
        step_stages = [step_stages[j] for j in order]
        step_timestamps = [step_timestamps[j] for j in order]
        step_machines = [step_machines[j] for j in order]

        actual_len = len(step_rows)
        seq_lengths.append(actual_len)

        sequences.append({
            'features': np.array(step_rows),
            'ckc_stages': step_stages,
            'timestamps': step_timestamps,
            'machine_names': step_machines,
            'sequence_id': f'real_atk_{i}',
            'label': 1,
        })

    # ─── BENIGN SEQUENCES (variable length, from ACTUAL benign data) ───
    n_benign = max(1, int(num_sequences * benign_ratio))
    print(f"[Real Sequences] Building {n_benign} benign sequences "
          f"from actual benign data...")

    for i in range(n_benign):
        # Variable length for benign too (5-15 steps)
        ben_len = int(rng.integers(5, 16))
        indices = rng.choice(len(benign_df), size=ben_len, replace=False)

        benign_rows = []
        benign_ts = []
        benign_machines = []

        for idx in sorted(indices):
            row = benign_df.iloc[idx]
            benign_rows.append(row[FEATURE_COLUMNS].values.astype(np.float32))
            benign_ts.append(
                pd.Timestamp('2024-01-01') + pd.Timedelta(hours=int(idx))
            )
            benign_machines.append(rng.choice(MACHINE_POOL))

        # Sort by timestamp
        order = np.argsort([t.timestamp() for t in benign_ts])
        benign_rows = [benign_rows[j] for j in order]
        benign_ts = [benign_ts[j] for j in order]
        benign_machines = [benign_machines[j] for j in order]

        seq_lengths.append(ben_len)

        sequences.append({
            'features': np.array(benign_rows),
            'ckc_stages': [0] * ben_len,
            'timestamps': benign_ts,
            'machine_names': benign_machines,
            'sequence_id': f'real_ben_{i}',
            'label': 0,
        })

    rng.shuffle(sequences)

    n_atk = sum(1 for s in sequences if s['label'] == 1)
    n_ben = sum(1 for s in sequences if s['label'] == 0)
    avg_len = np.mean(seq_lengths)
    min_l = np.min(seq_lengths)
    max_l = np.max(seq_lengths)
    print(f"[Real Sequences] Built {len(sequences)} sequences "
          f"({n_atk} attack, {n_ben} benign)")
    print(f"[Real Sequences] Step lengths: avg={avg_len:.1f}, "
          f"min={min_l}, max={max_l}")

    return sequences


if __name__ == '__main__':
    print("=" * 70)
    print("REAL DATA SEQUENCE BUILDER - TEST")
    print("=" * 70)

    mal_merged, benign_df = load_real_data()
    sequences = build_real_sequences(mal_merged, benign_df, num_sequences=10)

    for s in sequences[:5]:
        label = "ATK" if s['label'] == 1 else "BEN"
        print(f"  [{label}] {len(s['ckc_stages'])} steps, "
              f"stages: {s['ckc_stages']}, "
              f"shape: {s['features'].shape}")
