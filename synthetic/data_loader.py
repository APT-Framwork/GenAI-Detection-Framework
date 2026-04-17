"""
APT Data Loader
================

Loads both real and synthetic datasets for the RL APT detection system.

Data Sources:
- combined_dataset_final.xlsx     → Real SIEM alerts (raw features need engineering)
- synthetic_benign_malicious_final.xlsx → Synthetic alerts from ReALTabFormer (pre-processed)

Handles:
- Feature extraction (55 columns from 25 selected features)
- CKC stage mapping (string → int)
- Timestamp generation via Poisson process (date_generateur logic)
- Machine name assignment for synthetic data
- Sequence grouping for RL episodes
"""

import os
import math
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta


# ============================================================================
# 25 Features → 55 Columns
# ============================================================================

TOP_25_FEATURES = [
    'log_secbert_embedding',
    'decoder_auditd', 'firedtimes', 'location__var_log_audit_audit.log',
    'srcip_is_private', 'decoder_web-accesslog',
    'location__var_log_apache2_access.log', 'firedtimes_log',
    'path_is_missing', 'has_md5', 'cmd_length', 'has_sha256',
    'syscheck_added', 'cmd_is_missing', 'decoder_dpkg-decoder',
    'syscheck_deleted', 'path_depth', 'syscheck_modified',
    'location__var_log_auth.log',
    'cmd_secbert_embedding',
    'decoder_syscheck_deleted', 'path_is_sensitive',
    'decoder_syscheck_integrity_changed', 'location_syscheck', 'path_is_temp',
]

N_PCA = 16


def expand_feature_list(features: List[str]) -> List[str]:
    """Expand embedding feature names to their PCA column names."""
    expanded = []
    for f in features:
        if f == 'log_secbert_embedding':
            expanded.extend([f'log_secbert_emb_{i}' for i in range(N_PCA)])
        elif f == 'cmd_secbert_embedding':
            expanded.extend([f'cmd_secbert_emb_{i}' for i in range(N_PCA)])
        else:
            expanded.append(f)
    return expanded


# All 55 numeric feature columns
FEATURE_COLUMNS = expand_feature_list(TOP_25_FEATURES)

# CKC stage mapping (string label → integer)
CKC_STAGE_MAP = {
    'Benign': 0, 'benign': 0,
    'Unknown': -1,  # Malicious but stage assigned by sequence pattern
    'unknown': -1,
    'S1': 1, 'S2': 2, 'S3': 3, 'S4': 4,
    'S5': 5, 'S6': 6, 'S7': 7,
}

# 7-step attack sequence patterns (matching CKC progression)
# Each value is (is_malicious, ckc_stage) — 0=benign, 1-7=S1..S7
ATTACK_PATTERNS = [
    # Full CKC attack chain (S1 → S7)
    [1, 2, 3, 4, 5, 6, 7],          # Full 7-stage APT
    [0, 1, 3, 4, 5, 6, 7],          # Starts benign, then full chain
    [0, 0, 1, 4, 5, 6, 7],          # Late reconnaissance
    [0, 0, 0, 4, 5, 6, 7],          # Direct exploitation
    # Partial attacks
    [0, 0, 1, 3, 4, 0, 0],          # Recon+Delivery+Exploit, then stopped
    [0, 1, 1, 3, 4, 5, 0],          # Detected at installation
    [0, 0, 0, 0, 1, 3, 4],          # Very late detection
    # Lateral movement focused
    [0, 4, 5, 5, 6, 6, 7],          # Post-exploitation lateral
    [0, 0, 5, 5, 5, 6, 7],          # Heavy lateral movement
    # Benign sequences
    [0, 0, 0, 0, 0, 0, 0],          # Fully benign
    [0, 0, 0, 0, 0, 0, 0],          # Fully benign (duplicate for balance)
    # Mixed / intermittent
    [0, 1, 0, 0, 4, 5, 7],          # Intermittent attack
    [0, 0, 0, 4, 0, 6, 7],          # Stealthy with gaps
    [1, 0, 3, 0, 5, 0, 7],          # Alternating pattern
]

# MITRE Tactic ID → CKC stage (from preprocessing_dataset.ipynb)
TACTIC_MAPPING = {
    'TA0043': 1,  # Reconnaissance → S1
    'TA0001': 3,  # Initial Access → S3 Delivery
    'TA0002': 4,  # Execution → S4 Exploitation
    'TA0003': 5,  # Persistence → S5 Installation
    'TA0004': 4,  # Privilege Escalation → S4
    'TA0005': 5,  # Defense Evasion → S5
    'TA0006': 7,  # Credential Access → S7
    'TA0007': 7,  # Discovery → S7
    'TA0008': 5,  # Lateral Movement → S5
    'TA0009': 7,  # Collection → S7
    'TA0011': 6,  # Command and Control → S6
    'TA0040': 7,  # Impact → S7
}

# MITRE Technique ID → CKC stage (override rules from notebook)
TECHNIQUE_MAPPING = {
    'T1595': 1, 'T1595.002': 1,  # Scanning → S1
    'T1190': 4,                    # Exploit Public App → S4
    'T1078': 3,                    # Valid Accounts → S3
    'T1059': 4, 'T1059.007': 4, 'T1059.004': 4,  # Scripting → S4
    'T1110.001': 1,                # Password Guessing → S1
    'T1105': 3,                    # Ingress Tool Transfer → S3
    'T1136': 5, 'T1098': 5,       # Account ops → S5
    'T1222.002': 5, 'T1036.005': 5,  # File perm / masquerade → S5
    'T1068': 4, 'T1548.003': 4, 'T1106': 4,  # Priv esc → S4
    'T1083': 7, 'T1057': 7, 'T1082': 7,  # Discovery → S7
    'T1049': 7, 'T1033': 7, 'T1040': 7,
    'T1021': 5, 'T1021.004': 5,   # Remote Services → S5
    'T1005': 7, 'T1565.001': 7, 'T1485': 7,  # Collection/Impact → S7
    'T1562.001': 5,                # Disable Tools → S5
    'T1070.004': 7, 'T1070.006': 7,  # Anti-forensics → S7
}

# Merge into a single lookup (keep old name for backward compat)
MITRE_ID_TO_CKC = {**TACTIC_MAPPING, **TECHNIQUE_MAPPING}

# Machine name pool for synthetic data
MACHINE_POOL = [f'machine-{i}' for i in range(1, 9)]
USER_POOL = ['root', 'admin', 'user1', 'user2', 'wazuh', 'www-data', 'none']
IP_POOL = ['192.168.1.1', '192.168.1.2', '10.0.0.1', '10.0.0.5',
           '172.16.0.1', '172.16.0.2', 'none']


# ============================================================================
# Poisson Process Timestamp Generator (from date_generateur.ipynb)
# ============================================================================

T_DWELL_SECONDS = 11 * 24 * 3600  # 950,400 seconds (Mandiant median)

LAMBDA_DICT = {
    "Command and Scripting Interpreter": 0.509 / T_DWELL_SECONDS,
    "Remote Services": 0.353 / T_DWELL_SECONDS,
    "File and Directory Discovery": 0.342 / T_DWELL_SECONDS,
    "System Information Discovery": 0.316 / T_DWELL_SECONDS,
    "File Deletion": 0.252 / T_DWELL_SECONDS,
    "Ingress Tool Transfer": 0.249 / T_DWELL_SECONDS,
    "System Owner/User Discovery": 0.225 / T_DWELL_SECONDS,
    "Exploit Public-Facing Application": 0.222 / T_DWELL_SECONDS,
    "Valid Accounts": 0.208 / T_DWELL_SECONDS,
    "Process Discovery": 0.207 / T_DWELL_SECONDS,
    "Disable/Modify Tools": 0.133 / T_DWELL_SECONDS,
    "SSH": 0.129 / T_DWELL_SECONDS,
    "Password Guessing": 0.034 / T_DWELL_SECONDS,
    "Data Destruction": 0.032 / T_DWELL_SECONDS,
    "Create Account": 0.030 / T_DWELL_SECONDS,
}

# CKC stage → default lambda
CKC_LAMBDA = {
    0: 0.300 / T_DWELL_SECONDS,  # Benign (fast)
    1: 0.200 / T_DWELL_SECONDS,  # Reconnaissance
    2: 0.100 / T_DWELL_SECONDS,  # Weaponization
    3: 0.250 / T_DWELL_SECONDS,  # Delivery
    4: 0.300 / T_DWELL_SECONDS,  # Exploitation
    5: 0.150 / T_DWELL_SECONDS,  # Installation
    6: 0.200 / T_DWELL_SECONDS,  # C&C
    7: 0.050 / T_DWELL_SECONDS,  # Actions on Objectives
}

CAMPAIGN_MODES = {
    "stealth": 0.1, "slow": 0.3, "normal": 1.0,
    "fast": 3.0, "blitz": 10.0,
}


def generate_timestamps(
    ckc_stages: List[int],
    start_datetime: datetime = None,
    campaign_mode: str = "normal",
    seed: Optional[int] = None,
) -> List[pd.Timestamp]:
    """
    Generate realistic timestamps for a sequence of CKC stages
    using a Poisson process model.

    Args:
        ckc_stages: List of CKC stage integers
        start_datetime: Starting timestamp
        campaign_mode: Speed of attack progression
        seed: Random seed

    Returns:
        List of pd.Timestamp objects
    """
    if start_datetime is None:
        start_datetime = datetime(2024, 1, 1)

    rng = np.random.default_rng(seed)
    scale = 1.0 / CAMPAIGN_MODES.get(campaign_mode, 1.0)

    timestamps = []
    current_time = 0.0

    for i, stage in enumerate(ckc_stages):
        if i == 0:
            timestamps.append(start_datetime)
            continue

        lam = CKC_LAMBDA.get(stage, 1e-7)
        lam = max(lam, 1e-12)

        U = rng.uniform(0, 1)
        delta_t = -math.log(U) / lam
        delta_t *= scale

        # Add noise
        noise = rng.normal(0, delta_t * 0.1)
        delta_t = max(delta_t + noise, 1.0)

        current_time += delta_t
        timestamps.append(start_datetime + timedelta(seconds=current_time))

    return [pd.Timestamp(t) for t in timestamps]


# ============================================================================
# APTDataLoader
# ============================================================================

class APTDataLoader:
    """
    Unified data loader for RL APT detection system.
    Loads both real and synthetic datasets.
    """

    def __init__(
        self,
        synthetic_path: Optional[str] = None,
        real_data_path: Optional[str] = None,
        campaign_mode: str = "normal",
        seed: int = 42,
    ):
        """
        Initialize the data loader.

        Args:
            synthetic_path: Path to synthetic_benign_malicious_final.xlsx
            real_data_path: Path to combined_dataset_final.xlsx
            campaign_mode: Campaign mode for timestamp generation
            seed: Random seed
        """
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

        if synthetic_path is None:
            synthetic_path = os.path.join(root_dir, 'synthetic_benign_malicious_final.xlsx')
        if real_data_path is None:
            real_data_path = os.path.join(root_dir, 'combined_dataset_final.xlsx')

        self.synthetic_path = synthetic_path
        self.real_data_path = real_data_path
        self.campaign_mode = campaign_mode
        self.seed = seed
        self.rng = np.random.default_rng(seed)

        self.synthetic_df = None
        self.real_df = None
        self.combined_df = None

    def load_synthetic_data(self) -> pd.DataFrame:
        """
        Load synthetic data from synthetic_benign_malicious_final.xlsx.
        Each row is an individual alert (step_idx=1 always).
        'Benign' = benign, 'Unknown' = malicious (from ReALTabFormer).
        Adds timestamps and machine names for GNN graph building.
        """
        if not os.path.exists(self.synthetic_path):
            raise FileNotFoundError(f"Synthetic data not found: {self.synthetic_path}")

        print(f"[Data] Loading synthetic data: {os.path.basename(self.synthetic_path)}")
        df = pd.read_excel(self.synthetic_path)
        print(f"       Shape: {df.shape}")

        # Map CKC stages: Benign=0, Unknown=-1 (malicious, stage set by pattern later)
        df['ckc_stage_int'] = df['ckc_stage'].map(CKC_STAGE_MAP).fillna(0).astype(int)

        # Set label: Unknown(-1) is malicious
        df['label'] = (df['ckc_stage'] != 'Benign').astype(int)

        # Generate timestamps spread over a year
        n = len(df)
        base_time = datetime(2024, 1, 1)
        # Spread alerts uniformly, then add noise
        offsets = np.sort(self.rng.uniform(0, 365 * 24 * 3600, size=n))
        df['timestamp'] = [pd.Timestamp(base_time + timedelta(seconds=float(s))) for s in offsets]

        # Assign machine names
        df['machine_name'] = self.rng.choice(MACHINE_POOL, size=n)

        # Assign user and IP
        df['src_user'] = self.rng.choice(USER_POOL, size=n)
        df['src_ip'] = self.rng.choice(IP_POOL, size=n)

        self.synthetic_df = df
        n_malicious = df['label'].sum()
        print(f"       Benign: {n - n_malicious}, Malicious: {n_malicious}")
        return df

    def load_real_data(self) -> pd.DataFrame:
        """
        Load real data from combined_dataset_final.xlsx.
        Engineers the 55 features from raw SIEM columns.
        """
        if not os.path.exists(self.real_data_path):
            print(f"[Data] Real data not found: {self.real_data_path}")
            return None

        print(f"[Data] Loading real data: {os.path.basename(self.real_data_path)}")
        df = pd.read_excel(self.real_data_path)
        print(f"       Shape: {df.shape}")

        # Check which of the 55 feature columns exist
        available = [c for c in FEATURE_COLUMNS if c in df.columns]
        missing = [c for c in FEATURE_COLUMNS if c not in df.columns]

        if len(available) < 10:
            print(f"[Data] Warning: Only {len(available)}/55 feature columns found in real data")
            print(f"       Missing: {missing[:10]}...")

        # Fill missing columns with 0
        for col in missing:
            df[col] = 0.0

        # Extract timestamp
        if '_source.@timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['_source.@timestamp'], errors='coerce')
        elif '_source.predecoder.timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['_source.predecoder.timestamp'], errors='coerce')
        else:
            df['timestamp'] = pd.Timestamp('2024-01-01') + pd.to_timedelta(np.arange(len(df)), unit='min')

        # Extract machine name
        if '_source.agent.name' in df.columns:
            df['machine_name'] = df['_source.agent.name'].fillna('unknown')
        elif '_source.predecoder.hostname' in df.columns:
            df['machine_name'] = df['_source.predecoder.hostname'].fillna('unknown')
        else:
            df['machine_name'] = 'machine-1'

        # Extract user and IP
        df['src_user'] = df.get('_source.data.srcuser', pd.Series(['none'] * len(df))).fillna('none')
        df['src_ip'] = df.get('_source.data.srcip', pd.Series(['none'] * len(df))).fillna('none')

        # Label
        if 'malicious' in df.columns:
            df['label'] = df['malicious'].astype(int)
        else:
            df['label'] = 0

        # CKC stage (cyber_kill_chain_tactic contains 'S1'...'S7' strings)
        if 'cyber_kill_chain_tactic' in df.columns:
            df['ckc_stage_int'] = df['cyber_kill_chain_tactic'].map(CKC_STAGE_MAP).fillna(0).astype(int)
        else:
            df['ckc_stage_int'] = 0

        # Create sequence_id from agent id (group by machine + time window)
        df['sequence_id'] = 'real_' + df.index.astype(str)

        self.real_df = df
        print(f"       Available features: {len(available)}/55, "
              f"Malicious: {df['label'].sum()}/{len(df)}")
        return df

    def load_all(self) -> pd.DataFrame:
        """Load both datasets and combine."""
        syn_df = self.load_synthetic_data()
        real_df = self.load_real_data()

        dfs = [syn_df]
        if real_df is not None:
            dfs.append(real_df)

        # Ensure consistent columns
        common_cols = ['sequence_id', 'timestamp', 'machine_name', 'src_user', 'src_ip',
                       'ckc_stage_int', 'label'] + FEATURE_COLUMNS
        for df in dfs:
            for col in common_cols:
                if col not in df.columns:
                    df[col] = 0 if col not in ['sequence_id', 'machine_name', 'src_user', 'src_ip'] else 'unknown'

        self.combined_df = pd.concat([df[common_cols] for df in dfs], ignore_index=True)
        print(f"\n[Data] Combined: {len(self.combined_df):,} rows "
              f"({len(syn_df)} synthetic + {len(real_df) if real_df is not None else 0} real)")
        return self.combined_df

    def get_feature_matrix(self, df: pd.DataFrame = None) -> np.ndarray:
        """Extract the 55 feature columns as a numpy array."""
        if df is None:
            df = self.combined_df
        if df is None:
            raise ValueError("No data loaded. Call load_all() first.")
        return df[FEATURE_COLUMNS].values.astype(np.float32)

    def get_training_sequences(
        self,
        source: str = 'synthetic',
        min_length: int = 3,
        max_length: int = 30,
        num_sequences: int = 500,
    ) -> List[Dict]:
        """
        Get sequences for RL training episodes.

        Since the synthetic data has one alert per row (no multi-step sequences),
        this method constructs artificial sequences by sampling benign and malicious
        alerts according to predefined attack patterns.

        Args:
            source: 'synthetic', 'real', or 'both'
            min_length: Minimum sequence length
            max_length: Maximum sequence length
            num_sequences: Number of sequences to generate

        Returns:
            List of sequence dicts
        """
        if source == 'synthetic':
            df = self.synthetic_df
        elif source == 'real':
            df = self.real_df
        else:
            df = self.combined_df

        if df is None:
            raise ValueError(f"Data source '{source}' not loaded")

        # First try existing multi-step sequences
        existing_sequences = []
        for seq_id, group in df.groupby('sequence_id'):
            if len(group) >= min_length:
                group = group.sort_values('timestamp') if 'timestamp' in group.columns else group
                if len(group) > max_length:
                    group = group.head(max_length)

                features = group[FEATURE_COLUMNS].values.astype(np.float32)
                ckc_stages = group['ckc_stage_int'].tolist()
                timestamps = group['timestamp'].tolist() if 'timestamp' in group.columns else [None] * len(group)
                machines = group['machine_name'].tolist() if 'machine_name' in group.columns else ['machine-1'] * len(group)

                existing_sequences.append({
                    'features': features,
                    'ckc_stages': ckc_stages,
                    'timestamps': timestamps,
                    'machine_names': machines,
                    'sequence_id': seq_id,
                    'label': int(any(s > 0 for s in ckc_stages)),
                })

        if existing_sequences:
            print(f"[Data] Found {len(existing_sequences)} existing multi-step sequences")
            return existing_sequences

        # Construct 7-step sequences from individual alerts
        print(f"[Data] Constructing {num_sequences} x 7-step sequences from individual alerts...")

        # Split data by label (benign vs malicious/Unknown)
        benign_df = df[df['label'] == 0]
        malicious_df = df[df['label'] == 1]

        if len(benign_df) == 0:
            benign_df = df.head(len(df) // 2)
        if len(malicious_df) == 0:
            malicious_df = df.tail(len(df) // 2)

        benign_indices = benign_df.index.values
        malicious_indices = malicious_df.index.values

        sequences = []
        rng = np.random.default_rng(self.seed)

        for i in range(num_sequences):
            # Choose a random 7-step attack pattern
            pattern = list(ATTACK_PATTERNS[rng.integers(len(ATTACK_PATTERNS))])

            # Sample alerts for each step
            step_features = []
            step_stages = []
            for ckc_stage in pattern:
                if ckc_stage == 0:
                    # Benign step
                    idx = rng.choice(benign_indices)
                else:
                    # Malicious step — sample from Unknown alerts
                    idx = rng.choice(malicious_indices)
                step_features.append(df.loc[idx, FEATURE_COLUMNS].values.astype(np.float32))
                step_stages.append(ckc_stage)

            features = np.array(step_features)

            # Generate timestamps via Poisson process
            timestamps = generate_timestamps(
                step_stages,
                start_datetime=datetime(2024, 1, 1) + timedelta(days=rng.uniform(0, 365)),
                campaign_mode=self.campaign_mode,
                seed=i + self.seed,
            )

            # Assign machines (lateral movement at S5/S6 stages)
            primary_machine = rng.choice(MACHINE_POOL)
            machines = []
            for stage in step_stages:
                if stage in (5, 6):  # Lateral movement / C&C may cross machines
                    machines.append(rng.choice(MACHINE_POOL))
                else:
                    machines.append(primary_machine)

            sequences.append({
                'features': features,
                'ckc_stages': step_stages,
                'timestamps': timestamps,
                'machine_names': machines,
                'sequence_id': f'gen_{i}',
                'label': int(any(s > 0 for s in step_stages)),
            })

        n_attack = sum(1 for s in sequences if s['label'] == 1)
        print(f"[Data] Created {len(sequences)} sequences "
              f"({n_attack} attack, {len(sequences) - n_attack} benign, 7 steps each)")
        return sequences

    def get_combined_dataframe(self) -> pd.DataFrame:
        """Get the combined DataFrame for GNN graph building."""
        if self.combined_df is None:
            self.load_all()
        return self.combined_df


# Example usage and testing
if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("APT DATA LOADER - TEST")
    print("=" * 70)

    try:
        loader = APTDataLoader()

        # Load synthetic
        syn_df = loader.load_synthetic_data()
        print(f"\n  Synthetic columns: {list(syn_df.columns[:10])}...")
        print(f"  Timestamp range: {syn_df['timestamp'].min()} to {syn_df['timestamp'].max()}")
        print(f"  Machines: {syn_df['machine_name'].unique()[:5]}")

        # Load sequences
        sequences = loader.get_training_sequences(source='synthetic', min_length=3)
        if sequences:
            seq = sequences[0]
            print(f"\n  First sequence: id={seq['sequence_id']}")
            print(f"    Features shape: {seq['features'].shape}")
            print(f"    CKC stages: {seq['ckc_stages']}")
            print(f"    Machines: {seq['machine_names']}")
            print(f"    Timestamps: {seq['timestamps'][:3]}...")

        print("\n  [OK] Data loader working correctly")
    except Exception as e:
        print(f"  [ERROR] {e}")
        import traceback
        traceback.print_exc()
