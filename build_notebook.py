"""Build the Benign_Malicious_Generation.ipynb notebook."""
import json

cells = []

def add_md(source):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": [line + "\n" for line in source.split("\n")]})

def add_code(source):
    lines = source.split("\n")
    src = [line + "\n" for line in lines]
    if src:
        src[-1] = src[-1].rstrip("\n")
    cells.append({
        "cell_type": "code",
        "execution_count": None,
        "metadata": {"vscode": {"languageId": "python"}},
        "outputs": [],
        "source": src
    })

# ═══════════════════════════════════════════════════════════════
# CELL 1 — Markdown header
# ═══════════════════════════════════════════════════════════════
add_md("""# Synthetic Alert Generation — Benign + Malicious
## ReALTabFormer Pipeline

**Goal**: Generate a balanced synthetic dataset:
- **90,000 synthetic benign alerts** (from new benign-trained RTF models)
- **30,000 synthetic malicious alerts** (from existing CKC-trained RTF models)
- **120,000 total** → reverse-mapped to original dataset columns

**Data Sources**:
- `combined_dataset_final.xlsx` → ~90K benign rows for training benign models
- `malicious_realtabformer_filtered.xlsx` → existing malicious RTF models
- SecBERT embeddings for text decoding""")

# ═══════════════════════════════════════════════════════════════
# CELL 2 — Imports & warnings
# ═══════════════════════════════════════════════════════════════
add_code("""# ============================================================================
# WARNING SUPPRESSION & ENVIRONMENT SETUP
# ============================================================================
import os, sys, warnings

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['CUDA_VISIBLE_DEVICES'] = os.environ.get('CUDA_VISIBLE_DEVICES', '0')
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GLOG_minloglevel'] = '3'
os.environ['ABSL_MIN_LOG_LEVEL'] = '3'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
os.environ['WANDB_DISABLED'] = 'true'
os.environ['WANDB_MODE'] = 'disabled'
os.environ['JAX_PLATFORMS'] = ''

warnings.filterwarnings('ignore')
if not sys.warnoptions:
    warnings.simplefilter("ignore")

import logging
logging.getLogger().setLevel(logging.ERROR)
for name in ['absl', 'tensorflow', 'transformers', 'realtabformer']:
    logging.getLogger(name).setLevel(logging.ERROR)

try:
    import tensorflow as tf
    tf.get_logger().setLevel('ERROR')
    tf.autograph.set_verbosity(0)
except ImportError:
    pass

print("All warning suppressions activated")""")

# ═══════════════════════════════════════════════════════════════
# CELL 3 — Core imports
# ═══════════════════════════════════════════════════════════════
add_code("""# ============================================================================
# CORE IMPORTS
# ============================================================================
import json, re, math, types, pickle, secrets
from pathlib import Path
from glob import glob
from datetime import datetime
from collections import Counter, defaultdict

import numpy as np
import pandas as pd
import torch
import matplotlib.pyplot as plt

from sklearn.decomposition import PCA, TruncatedSVD
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, f1_score
from sklearn.manifold import TSNE
from tqdm.auto import tqdm

from realtabformer import REaLTabFormer
from transformers import GPT2Config, GPT2LMHeadModel

SECBERT_AVAILABLE = False
try:
    from sentence_transformers import SentenceTransformer
    SECBERT_AVAILABLE = True
except ImportError:
    pass

device = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f"Device: {device}")
if device == 'cuda':
    print(f"   GPU: {torch.cuda.get_device_name(0)}")
    print(f"   VRAM: {torch.cuda.get_device_properties(0).total_mem / 1e9:.1f} GB")
print(f"SecBERT available: {SECBERT_AVAILABLE}")""")

# ═══════════════════════════════════════════════════════════════
# CELL 4 — Configuration
# ═══════════════════════════════════════════════════════════════
add_code(r"""# ============================================================================
# CONFIGURATION
# ============================================================================

PARENT_DIR = r'c:\Users\KassoussiOussama-PFE\Downloads\pfe'
OUTPUT_DIR = r'D:\PFE_BENIGN_MAL'
os.makedirs(OUTPUT_DIR, exist_ok=True)

CONFIG = {
    # Data paths
    'combined_data_path': os.path.join(PARENT_DIR, 'combined_dataset_final.xlsx'),
    'malicious_data_path': os.path.join(PARENT_DIR, 'malicious_realtabformer_filtered.xlsx'),
    'embeddings_path': os.path.join(PARENT_DIR, 'realtabformer_output', 'secbert_embeddings.pkl'),
    # Existing malicious models (from CKC notebook)
    'malicious_model_dir': os.path.join(r'D:\PFE_CKC', 'ckc_models'),
    # Benign model dirs
    'benign_checkpoints_dir': os.path.join(OUTPUT_DIR, 'benign_checkpoints'),
    'benign_model_dir': os.path.join(OUTPUT_DIR, 'benign_models'),
    # Training
    'epochs': 150, 'batch_size': 32, 'gradient_accumulation_steps': 4,
    'logging_steps': 100, 'save_steps': 500, 'train_size': 0.95,
    'random_seed': 42,
    # Generation targets
    'n_benign_target': 90_000,
    'n_malicious_target': 30_000,
    'oversample_factor': 1.3,   # generate 30% more than target, then sample down
    # SecBERT
    'secbert_model': 'jackaduma/SecBERT',
    'n_pca_dims': 16,
    'device': device,
}

# Top 25 distinct features (same as CKC notebook)
TOP_25_FEATURES = [
    'log_secbert_embedding',
    'decoder_auditd',
    'firedtimes',
    'location__var_log_audit_audit.log',
    'srcip_is_private',
    'decoder_web-accesslog',
    'location__var_log_apache2_access.log',
    'firedtimes_log',
    'path_is_missing',
    'has_md5',
    'cmd_length',
    'has_sha256',
    'syscheck_added',
    'cmd_is_missing',
    'decoder_dpkg-decoder',
    'syscheck_deleted',
    'path_depth',
    'syscheck_modified',
    'location__var_log_auth.log',
    'cmd_secbert_embedding',
    'decoder_syscheck_deleted',
    'path_is_sensitive',
    'decoder_syscheck_integrity_changed',
    'location_syscheck',
    'path_is_temp',
]

N_PCA = CONFIG['n_pca_dims']

def expand_feature_list(features):
    expanded = []
    for f in features:
        if f == 'log_secbert_embedding':
            expanded.extend([f'log_secbert_emb_{i}' for i in range(N_PCA)])
        elif f == 'cmd_secbert_embedding':
            expanded.extend([f'cmd_secbert_emb_{i}' for i in range(N_PCA)])
        else:
            expanded.append(f)
    return expanded

TOP_25_COLUMNS = expand_feature_list(TOP_25_FEATURES)

print(f"CONFIG:")
print(f"   Top 25 features -> {len(TOP_25_COLUMNS)} DataFrame columns")
print(f"   Benign target:    {CONFIG['n_benign_target']:,}")
print(f"   Malicious target: {CONFIG['n_malicious_target']:,}")
print(f"   Total target:     {CONFIG['n_benign_target'] + CONFIG['n_malicious_target']:,}")
print(f"   Output: {OUTPUT_DIR}")""")

# ═══════════════════════════════════════════════════════════════
# CELL 5 — Load data & engineer features
# ═══════════════════════════════════════════════════════════════
add_code("""# ============================================================================
# LOAD COMBINED DATASET & ENGINEER TOP 25 FEATURES (BOTH CLASSES)
# ============================================================================

print("=" * 70)
print("LOADING COMBINED DATASET & ENGINEERING FEATURES")
print("=" * 70)

# 1. Load combined dataset
combined_df = pd.read_excel(CONFIG['combined_data_path'], sheet_name='Sheet1')
print(f"   Combined data: {combined_df.shape[0]:,} rows x {combined_df.shape[1]} cols")

for col in combined_df.select_dtypes(include='object').columns:
    mask = combined_df[col].isin([' ', '  ', ''])
    combined_df.loc[mask, col] = np.nan

# Split benign / malicious
benign_raw = combined_df[combined_df['malicious'] == 0].copy().reset_index(drop=True)
malicious_raw = combined_df[combined_df['malicious'] == 1].copy().reset_index(drop=True)
print(f"   Benign:    {len(benign_raw):,} rows")
print(f"   Malicious: {len(malicious_raw):,} rows")

# 2. Load SecBERT embeddings (computed on ALL 115K rows)
print(f"\\nLoading SecBERT embeddings...")
with open(CONFIG['embeddings_path'], 'rb') as f:
    text_embeddings = pickle.load(f)

for col, emb in text_embeddings.items():
    if emb is not None:
        print(f"   {col}: shape={emb.shape}")

# 3. PCA reduce embeddings (fit on full dataset)
log_emb_raw = text_embeddings.get('_source.rule.description')
cmd_emb_raw = text_embeddings.get('_source.data.command')

RANDOM_SEED = CONFIG['random_seed']

pca_log = PCA(n_components=N_PCA, random_state=RANDOM_SEED)
log_emb_pca = pca_log.fit_transform(log_emb_raw)
print(f"\\n   Log embeddings: {log_emb_raw.shape[1]}D -> {N_PCA}D (var: {pca_log.explained_variance_ratio_.sum():.3f})")

pca_cmd = PCA(n_components=N_PCA, random_state=RANDOM_SEED)
cmd_emb_pca = pca_cmd.fit_transform(cmd_emb_raw)
print(f"   Cmd embeddings: {cmd_emb_raw.shape[1]}D -> {N_PCA}D (var: {pca_cmd.explained_variance_ratio_.sum():.3f})")

# 4. Engineer features for FULL dataset first (to get correct benign indices)
def engineer_features(raw_df, log_pca, cmd_pca, label):
    df = pd.DataFrame(index=raw_df.index)
    for feat in TOP_25_FEATURES:
        if feat == 'log_secbert_embedding':
            for i in range(N_PCA):
                df[f'log_secbert_emb_{i}'] = log_pca[:, i]
        elif feat == 'cmd_secbert_embedding':
            for i in range(N_PCA):
                df[f'cmd_secbert_emb_{i}'] = cmd_pca[:, i]
        elif feat == 'firedtimes':
            df[feat] = raw_df['_source.rule.firedtimes'].fillna(0).astype(float)
        elif feat == 'firedtimes_log':
            df[feat] = np.log1p(raw_df['_source.rule.firedtimes'].fillna(0).astype(float))
        elif feat == 'cmd_length':
            df[feat] = raw_df['_source.data.command'].fillna('').astype(str).str.len()
        elif feat == 'path_depth':
            df[feat] = raw_df['_source.syscheck.path'].fillna('').astype(str).str.count('/').astype(int)
        elif feat.startswith('decoder_'):
            decoder_name = feat.replace('decoder_', '')
            df[feat] = (raw_df['_source.decoder.name'].astype(str) == decoder_name).astype(int)
        elif feat.startswith('location_'):
            loc_name = feat.replace('location_', '').replace('_', '/')
            df[feat] = raw_df['_source.location'].astype(str).str.contains(loc_name, na=False).astype(int)
        elif feat == 'srcip_is_private':
            def _is_private(ip):
                if pd.isna(ip): return 0
                s = str(ip)
                return int(s.startswith('10.') or s.startswith('192.168.') or
                          (s.startswith('172.') and len(s.split('.'))>1 and 16<=int(s.split('.')[1])<=31))
            df[feat] = raw_df['_source.data.srcip'].apply(_is_private)
        elif feat == 'has_md5':
            df[feat] = raw_df['_source.syscheck.md5_after'].notna().astype(int)
        elif feat == 'has_sha256':
            df[feat] = raw_df['_source.syscheck.sha256_after'].notna().astype(int)
        elif feat == 'syscheck_added':
            df[feat] = (raw_df['_source.syscheck.event'].astype(str).str.lower() == 'added').astype(int)
        elif feat == 'syscheck_deleted':
            df[feat] = (raw_df['_source.syscheck.event'].astype(str).str.lower() == 'deleted').astype(int)
        elif feat == 'syscheck_modified':
            df[feat] = (raw_df['_source.syscheck.event'].astype(str).str.lower() == 'modified').astype(int)
        elif feat == 'path_is_missing':
            df[feat] = raw_df['_source.syscheck.path'].isna().astype(int)
        elif feat == 'path_is_sensitive':
            sensitive_dirs = ['/etc', '/root', '/var/log', '/boot', '/usr/sbin']
            df[feat] = raw_df['_source.syscheck.path'].fillna('').astype(str).apply(
                lambda p: int(any(d in p for d in sensitive_dirs)))
        elif feat == 'path_is_temp':
            df[feat] = raw_df['_source.syscheck.path'].fillna('').astype(str).apply(
                lambda p: int('/tmp' in p or '/temp' in p))
        elif feat == 'cmd_is_missing':
            df[feat] = raw_df['_source.data.command'].isna().astype(int)

    # Add command column for training (text)
    df['_source.data.command'] = raw_df['_source.data.command'].fillna('').astype(str).str[:300]
    df['_source.data.command'] = df['_source.data.command'].replace({'nan': '', 'None': '', 'NaN': ''})

    # Source type
    SOURCE_TYPES = {
        'network':  ['_source.data.protocol', '_source.data.srcip', '_source.data.url'],
        'syscheck': ['_source.syscheck.event', '_source.syscheck.path'],
        'sca':      ['_source.data.sca.check.result'],
        'audit':    ['_source.data.audit.syscall', '_source.data.audit.exe'],
    }
    raw_df = raw_df.copy()
    raw_df['_source_type'] = 'base'
    for stype, detect_cols in SOURCE_TYPES.items():
        existing = [c for c in detect_cols if c in raw_df.columns]
        if existing:
            msk = raw_df[existing].notna().any(axis=1)
            raw_df.loc[msk, '_source_type'] = stype
    df['_source_type'] = raw_df['_source_type'].values

    print(f"   [{label}] Engineered: {df.shape[0]:,} rows x {df.shape[1]} cols")
    return df

# Get indices for benign and malicious in the combined array
benign_idx = combined_df[combined_df['malicious'] == 0].index.values
malicious_idx = combined_df[combined_df['malicious'] == 1].index.values

# Engineer features for each class using correct embedding slices
benign_eng = engineer_features(benign_raw, log_emb_pca[benign_idx], cmd_emb_pca[benign_idx], 'BENIGN')
malicious_eng = engineer_features(malicious_raw, log_emb_pca[malicious_idx], cmd_emb_pca[malicious_idx], 'MALICIOUS')

# Save PCA models
pca_models = {'log': pca_log, 'cmd': pca_cmd}
with open(os.path.join(OUTPUT_DIR, 'pca_models.pkl'), 'wb') as f:
    pickle.dump(pca_models, f)
print(f"\\nPCA models saved")

# Source type distribution
for label, df_eng in [('BENIGN', benign_eng), ('MALICIOUS', malicious_eng)]:
    print(f"\\n   {label} source types:")
    for st, cnt in df_eng['_source_type'].value_counts().items():
        print(f"      {st}: {cnt:,}")""")

# ═══════════════════════════════════════════════════════════════
# CELL 6 — Stratify benign data
# ═══════════════════════════════════════════════════════════════
add_code("""# ============================================================================
# STRATIFIED PREPROCESSING — BENIGN DATA FOR TRAINING
# ============================================================================

print("=" * 70)
print("BUILDING STRATIFIED TRAINING DATASETS — BENIGN")
print("=" * 70)

LOG_EMB_COLS = [f'log_secbert_emb_{i}' for i in range(N_PCA)]
CMD_EMB_COLS = [f'cmd_secbert_emb_{i}' for i in range(N_PCA)]

# For benign: no CKC/MITRE columns needed
UNIVERSAL_FEATURES_BENIGN = (
    LOG_EMB_COLS + CMD_EMB_COLS +
    ['firedtimes', 'firedtimes_log', 'cmd_length', 'cmd_is_missing',
     '_source.data.command']
)

SOURCE_SPECIFIC = {
    'network':  ['srcip_is_private', 'decoder_web-accesslog', 'location__var_log_apache2_access.log'],
    'syscheck': ['syscheck_added', 'syscheck_deleted', 'syscheck_modified',
                 'path_is_missing', 'path_depth', 'path_is_sensitive', 'path_is_temp',
                 'has_md5', 'has_sha256',
                 'decoder_syscheck_deleted', 'decoder_syscheck_integrity_changed', 'location_syscheck'],
    'audit':    ['decoder_auditd', 'location__var_log_audit_audit.log'],
    'sca':      [],
    'base':     ['decoder_dpkg-decoder', 'location__var_log_auth.log'],
}

def preprocess_stratum(df_sub, columns, name):
    existing = [c for c in columns if c in df_sub.columns]
    df = df_sub[existing].copy()
    col_types = {'text': [], 'categorical': [], 'numeric': []}

    for col in df.columns:
        dtype = df[col].dtype
        n_unique = df[col].nunique()
        if dtype == 'object':
            if n_unique > 100:
                col_types['text'].append(col)
                max_len = 300 if 'command' in col else 150
                df[col] = df[col].fillna('').astype(str).str[:max_len]
                df[col] = df[col].replace({'nan': '', 'None': '', 'NaN': ''})
            else:
                col_types['categorical'].append(col)
                df[col] = df[col].fillna('MISSING').astype(str)
        elif dtype in ['int64', 'float64', 'int32', 'float32']:
            if n_unique <= 20:
                col_types['categorical'].append(col)
                df[col] = df[col].fillna(-1).astype(int).astype(str)
            else:
                col_types['numeric'].append(col)
        else:
            col_types['categorical'].append(col)
            df[col] = df[col].fillna('MISSING').astype(str)

    print(f"   {name.upper()}: {df.shape[0]:,} rows x {df.shape[1]} cols "
          f"(text:{len(col_types['text'])} cat:{len(col_types['categorical'])} num:{len(col_types['numeric'])})")
    return df, col_types

benign_strata = {}
for stype in ['network', 'syscheck', 'sca', 'audit', 'base']:
    subset = benign_eng[benign_eng['_source_type'] == stype].copy()
    if len(subset) == 0:
        print(f"   {stype}: 0 rows -- skipping")
        continue
    cols = UNIVERSAL_FEATURES_BENIGN + SOURCE_SPECIFIC.get(stype, [])
    cols = [c for c in cols if c in benign_eng.columns]
    df_proc, col_types = preprocess_stratum(subset, cols, f'benign_{stype}')
    benign_strata[stype] = {
        'df': df_proc, 'col_types': col_types,
        'all_cols': list(df_proc.columns), 'n_rows': len(df_proc),
    }

print(f"\\nBENIGN STRATA SUMMARY:")
total_rows = sum(s['n_rows'] for s in benign_strata.values())
for stype, info in benign_strata.items():
    pct = info['n_rows'] / total_rows * 100
    print(f"   {stype:>10}: {info['n_rows']:>6,} rows x {len(info['all_cols']):>2} cols ({pct:.1f}%)")
print(f"   {'TOTAL':>10}: {total_rows:>6,} rows")
print("=" * 70)""")

# ═══════════════════════════════════════════════════════════════
# CELL 7 — GPU utilities
# ═══════════════════════════════════════════════════════════════
add_code("""# ============================================================================
# GPU-OPTIMIZED SENSITIVITY THRESHOLD + TRAINING UTILITIES
# ============================================================================

def gpu_manhattan_distances(X, Y, device='cuda', batch_size=2000):
    X_t = torch.tensor(X, dtype=torch.float32, device=device)
    Y_t = torch.tensor(Y, dtype=torch.float32, device=device)
    if X_t.shape[0] * Y_t.shape[0] > 100_000_000:
        distances = np.zeros((X_t.shape[0], Y_t.shape[0]), dtype=np.float32)
        for i in range(0, X_t.shape[0], batch_size):
            batch = X_t[i:min(i + batch_size, X_t.shape[0])]
            distances[i:i+len(batch)] = torch.cdist(batch, Y_t, p=1).cpu().numpy()
        return distances
    return torch.cdist(X_t, Y_t, p=1).cpu().numpy()

def fast_preprocess_for_threshold(data, embedding_pca_dims=50, verbose=False):
    features = []
    numeric_cols = data.select_dtypes(include=['number']).columns.tolist()
    if numeric_cols:
        numeric_data = data[numeric_cols].fillna(0).values
        features.append(StandardScaler().fit_transform(numeric_data))
    cat_cols = data.select_dtypes(include=['object', 'category']).columns.tolist()
    low_card = [c for c in cat_cols if data[c].nunique() <= 100]
    if low_card:
        cat_feats = np.hstack([data[c].astype('category').cat.codes.values.reshape(-1,1) for c in low_card]).astype(np.float32)
        features.append(StandardScaler().fit_transform(cat_feats))
    if features:
        combined = np.hstack(features).astype(np.float32)
    else:
        combined = np.zeros((len(data), 1), dtype=np.float32)
    return np.nan_to_num(combined, nan=0.0)

def compute_sensitivity_threshold_fast(train_data, num_bootstrap=200, frac=0.165,
                                        qt_max=0.05, qt_interval=500, quantile=0.95,
                                        max_col_nums=50, device='cuda'):
    preprocessed = fast_preprocess_for_threshold(train_data)
    n_samples = len(preprocessed)
    indices = np.arange(n_samples)
    np.random.seed(42)
    values = []
    for _ in tqdm(range(num_bootstrap), desc="   Bootstrap", leave=False):
        train_idx, test_idx = train_test_split(indices, test_size=2*frac)
        split = len(test_idx) // 2
        syn_idx, tst_idx = test_idx[:split], test_idx[split:]
        orig, syn, tst = preprocessed[train_idx], preprocessed[syn_idx], preprocessed[tst_idx]
        if orig.shape[1] >= max_col_nums:
            tsvd = TruncatedSVD(n_components=max(5, math.ceil(orig.shape[1]**0.5)))
            orig = tsvd.fit_transform(orig)
            tst = tsvd.transform(tst)
            syn = tsvd.transform(syn)
        td = gpu_manhattan_distances(orig, tst, device=device)
        sd = gpu_manhattan_distances(orig, syn, device=device)
        t_min, s_min = td.min(axis=1), sd.min(axis=1)
        tr_t, tr_s = td.min(axis=0), sd.min(axis=0)
        fltr = (s_min == 0) & (t_min == 0)
        t_min, s_min = t_min[~fltr], s_min[~fltr]
        t_min = np.concatenate([t_min, tr_t])
        s_min = np.concatenate([s_min, tr_s])
        quantiles = np.linspace(0, qt_max, qt_interval)
        stat = np.mean((s_min.reshape(1,-1) <= np.quantile(t_min, quantiles).reshape(-1,1)).mean(axis=1) - quantiles)
        values.append(stat)
    threshold = np.quantile(values, quantile)
    return {'threshold': threshold, 'mean': np.mean(values), 'values': values}

def patched_save(self, path, allow_overwrite=False):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    rtf_attrs = {}
    for key, value in self.__dict__.items():
        if key.startswith('_') and key != '_column_order': continue
        if key in ['model', 'trainer', 'tokenizer', 'data_collator']: continue
        try:
            json.dumps(value, default=str)
            if isinstance(value, Path): rtf_attrs[key] = value.as_posix()
            elif hasattr(value, '__class__') and value.__class__.__name__ == 'Dataset': continue
            else: rtf_attrs[key] = value
        except (TypeError, ValueError): continue
    for attr in ["checkpoints_dir", "samples_save_dir", "full_save_dir"]:
        if attr in rtf_attrs and hasattr(rtf_attrs[attr], 'as_posix'):
            rtf_attrs[attr] = rtf_attrs[attr].as_posix()
    def json_enc(obj):
        if isinstance(obj, Path): return obj.as_posix()
        if hasattr(obj, 'tolist'): return obj.tolist()
        return str(obj)
    (path / "rtf_config.json").write_text(json.dumps(rtf_attrs, default=json_enc, indent=2))
    if hasattr(self, 'model') and self.model is not None: self.model.save_pretrained(path)
    if hasattr(self, 'tokenizer') and self.tokenizer is not None: self.tokenizer.save_pretrained(path)

print("GPU optimization & training utilities loaded")""")

# ═══════════════════════════════════════════════════════════════
# CELL 8 — Markdown: Training
# ═══════════════════════════════════════════════════════════════
add_md("""## Phase 1: Train Benign RTF Models
Train 5 ReALTabFormer models (one per source type) on the ~90K benign rows.
Skip this cell if models are already trained — use the loader cell below.""")

# ═══════════════════════════════════════════════════════════════
# CELL 9 — Train benign models
# ═══════════════════════════════════════════════════════════════
add_code("""# ============================================================================
# TRAIN REaLTabFormer — BENIGN MODELS (ONE PER SOURCE TYPE)
# ============================================================================

print("=" * 70)
print("TRAINING BENIGN REaLTabFormer MODELS")
print("=" * 70)

os.makedirs(CONFIG['benign_checkpoints_dir'], exist_ok=True)
os.makedirs(CONFIG['benign_model_dir'], exist_ok=True)

benign_trained_models = {}
benign_training_times = {}
benign_thresholds = {}

try:
    from realtabformer.rtf_analyze import SyntheticDataBench
except ImportError:
    try:
        import realtabformer.realtabformer as rtf_module
        SyntheticDataBench = rtf_module.SyntheticDataBench
    except:
        SyntheticDataBench = None

for stype, info in benign_strata.items():
    df_train = info['df']
    n_rows = info['n_rows']
    n_cols = len(info['all_cols'])

    print(f"\\n{'=' * 70}")
    print(f"TRAINING: BENIGN_{stype.upper()} ({n_rows:,} rows x {n_cols} cols)")
    print(f"{'=' * 70}")

    if n_rows < 200:
        epochs = min(CONFIG['epochs'], 300)
        batch_size = min(CONFIG['batch_size'], max(8, n_rows // 4))
    elif n_rows < 1000:
        epochs, batch_size = CONFIG['epochs'], min(CONFIG['batch_size'], 16)
    else:
        epochs, batch_size = CONFIG['epochs'], CONFIG['batch_size']

    print(f"   Epochs: {epochs}  |  Batch size: {batch_size}")

    ckpt_dir = os.path.join(CONFIG['benign_checkpoints_dir'], stype)
    os.makedirs(ckpt_dir, exist_ok=True)

    print(f"   Computing sensitivity threshold...")
    threshold_result = compute_sensitivity_threshold_fast(df_train, num_bootstrap=200, device=device)
    THRESHOLD = threshold_result['threshold']
    benign_thresholds[stype] = THRESHOLD
    print(f"   Threshold: {THRESHOLD:.6f}")

    if SyntheticDataBench:
        def make_patched(thresh_val, thresh_vals):
            def patched(*args, **kwargs):
                return thresh_vals if kwargs.get('return_values', False) else thresh_val
            return patched
        SyntheticDataBench.compute_sensitivity_threshold = staticmethod(
            make_patched(THRESHOLD, threshold_result['values'])
        )

    model = REaLTabFormer(
        model_type='tabular',
        gradient_accumulation_steps=CONFIG['gradient_accumulation_steps'],
        logging_steps=CONFIG['logging_steps'],
        save_steps=CONFIG['save_steps'],
        epochs=epochs, batch_size=batch_size,
        train_size=CONFIG['train_size'],
        random_state=CONFIG['random_seed'],
        checkpoints_dir=ckpt_dir,
    )
    model.training_args_kwargs.pop('overwrite_output_dir', None)
    model.save = types.MethodType(patched_save, model)

    latest_ckpt = None
    ckpt_pattern = os.path.join(ckpt_dir, "checkpoint-*")
    if glob(ckpt_pattern):
        ckpts = sorted([d for d in glob(ckpt_pattern) if os.path.isdir(d)],
                       key=lambda x: int(x.split('-')[-1]))
        if ckpts:
            latest_ckpt = ckpts[-1]
            print(f"   Resuming from: {os.path.basename(latest_ckpt)}")

    train_start = datetime.now()
    try:
        model.fit(df_train, device=device,
                  resume_from_checkpoint=latest_ckpt, gen_kwargs={})
        duration = (datetime.now() - train_start).total_seconds() / 60
        print(f"   Done in {duration:.1f} min")
        benign_trained_models[stype] = model
        benign_training_times[stype] = duration
    except Exception as e:
        print(f"   FAILED: {e}")
        import traceback; traceback.print_exc()

# Save benign models
print(f"\\n{'=' * 70}")
print(f"SAVING {len(benign_trained_models)} BENIGN MODELS")
print("=" * 70)

for stype, model in benign_trained_models.items():
    model_path = os.path.join(CONFIG['benign_model_dir'], f'model_{stype}')
    model.save(model_path)
    print(f"   {stype}: {model_path}")

# Save strata metadata
strata_meta = {}
for stype, info in benign_strata.items():
    strata_meta[stype] = {
        'n_rows': info['n_rows'], 'columns': info['all_cols'],
        'col_types': info['col_types'],
        'training_time_min': benign_training_times.get(stype, 0),
    }
with open(os.path.join(CONFIG['benign_model_dir'], 'strata_metadata.json'), 'w') as f:
    json.dump(strata_meta, f, indent=2, default=str)

print(f"\\nTRAINING COMPLETE: {len(benign_trained_models)}/{len(benign_strata)} models")
for stype, dur in benign_training_times.items():
    print(f"   {stype:>10}: {dur:.1f} min (threshold={benign_thresholds.get(stype,0):.6f})")
print(f"   {'TOTAL':>10}: {sum(benign_training_times.values()):.1f} min")
print("=" * 70)""")

# ═══════════════════════════════════════════════════════════════
# CELL 10 — Load models (both benign and malicious)
# ═══════════════════════════════════════════════════════════════
add_code("""# ============================================================================
# LOAD ALL MODELS (Benign + Malicious) — skip training after kernel restart
# ============================================================================

print("=" * 70)
print("LOADING ALL MODELS FROM DISK")
print("=" * 70)

def load_rtf_from_patched_save(model_dir):
    model_dir = Path(model_dir)
    rtf_config = json.loads((model_dir / 'rtf_config.json').read_text())
    rtf = REaLTabFormer(model_type=rtf_config.get('model_type', 'tabular'))
    gpt2_cfg = GPT2Config.from_pretrained(str(model_dir))
    for k, v in rtf_config.items():
        if k == 'tabular_config':
            v = gpt2_cfg
        elif k in ['checkpoints_dir', 'samples_save_dir', 'full_save_dir']:
            v = Path(v) if v else v
        elif k == 'vocab':
            v['id2token'] = {int(ii): vv for ii, vv in v['id2token'].items()}
        elif k == 'col_idx_ids':
            v = {int(ii): vv for ii, vv in v.items()}
        setattr(rtf, k, v)
    rtf.model = GPT2LMHeadModel.from_pretrained(str(model_dir))
    return rtf

# Load benign models
benign_trained_models = {}
print("\\n--- BENIGN MODELS ---")
for stype in benign_strata.keys():
    model_path = os.path.join(CONFIG['benign_model_dir'], f'model_{stype}')
    if os.path.exists(model_path):
        try:
            model = load_rtf_from_patched_save(model_path)
            benign_trained_models[stype] = model
            print(f'   {stype}: loaded')
        except Exception as e:
            print(f'   {stype}: FAILED — {e}')
    else:
        print(f'   {stype}: not found')

# Load malicious models (from CKC notebook)
# Need malicious strata info first
UNIVERSAL_FEATURES_MAL = (
    LOG_EMB_COLS + CMD_EMB_COLS +
    ['firedtimes', 'firedtimes_log', 'cmd_length', 'cmd_is_missing',
     'cyber_kill_chain_summary', '_source.rule.mitre.tactic', '_source.rule.mitre.id',
     '_source.data.command']
)

# Build malicious strata (for model compatibility)
malicious_eng_full = malicious_eng.copy()
malicious_eng_full['cyber_kill_chain_summary'] = malicious_raw.get('cyber_kill_chain_summary', 'MISSING')
malicious_eng_full['_source.rule.mitre.tactic'] = malicious_raw['_source.rule.mitre.tactic'].fillna('MISSING')
malicious_eng_full['_source.rule.mitre.id'] = malicious_raw['_source.rule.mitre.id'].fillna('MISSING')

malicious_strata = {}
for stype in ['network', 'syscheck', 'sca', 'audit', 'base']:
    subset = malicious_eng_full[malicious_eng_full['_source_type'] == stype].copy()
    if len(subset) == 0:
        continue
    cols = UNIVERSAL_FEATURES_MAL + SOURCE_SPECIFIC.get(stype, [])
    cols = [c for c in cols if c in malicious_eng_full.columns]
    df_proc, col_types = preprocess_stratum(subset, cols, f'mal_{stype}')
    malicious_strata[stype] = {
        'df': df_proc, 'col_types': col_types,
        'all_cols': list(df_proc.columns), 'n_rows': len(df_proc),
    }

malicious_trained_models = {}
print("\\n--- MALICIOUS MODELS ---")
for stype in malicious_strata.keys():
    model_path = os.path.join(CONFIG['malicious_model_dir'], f'model_{stype}')
    if os.path.exists(model_path):
        try:
            model = load_rtf_from_patched_save(model_path)
            malicious_trained_models[stype] = model
            print(f'   {stype}: loaded')
        except Exception as e:
            print(f'   {stype}: FAILED — {e}')
    else:
        print(f'   {stype}: not found')

print(f'\\nLoaded: {len(benign_trained_models)} benign + {len(malicious_trained_models)} malicious models')
print('=' * 70)""")

# ═══════════════════════════════════════════════════════════════
# CELL 11 — Markdown: Generation
# ═══════════════════════════════════════════════════════════════
add_md("""## Phase 2: Generate 90K Benign + 30K Malicious Synthetic Rows
Generate rows using both sets of models, proportioned by source type.""")

# ═══════════════════════════════════════════════════════════════
# CELL 12 — Generate rows
# ═══════════════════════════════════════════════════════════════
add_code("""# ============================================================================
# GENERATE SYNTHETIC ROW POOLS — BENIGN + MALICIOUS
# ============================================================================

print("=" * 70)
print("GENERATING SYNTHETIC ROWS")
print("=" * 70)

def generate_pool(models, strata, target_n, label, oversample=1.3):
    pool = {}
    total_real = sum(s['n_rows'] for s in strata.values())
    total_gen = 0

    for stype, model in models.items():
        # Proportional generation: each source type keeps its proportion
        proportion = strata[stype]['n_rows'] / total_real
        n_gen = max(200, int(target_n * oversample * proportion))

        print(f"\\n   [{label}] {stype.upper()}: generating {n_gen:,} rows "
              f"({proportion*100:.1f}% of {target_n:,})...")
        try:
            synth_df = model.sample(n_samples=n_gen, device=device)
            synth_df['source_type'] = stype
            synth_df['malicious'] = 1 if label == 'MALICIOUS' else 0
            pool[stype] = synth_df
            total_gen += len(synth_df)
            print(f"      Generated {len(synth_df):,} rows x {len(synth_df.columns)} cols")
        except Exception as e:
            print(f"      FAILED: {e}")

    return pool, total_gen

# Generate benign rows
print("\\n--- GENERATING BENIGN ROWS ---")
benign_pool, n_benign_gen = generate_pool(
    benign_trained_models, benign_strata,
    CONFIG['n_benign_target'], 'BENIGN', CONFIG['oversample_factor']
)

# Generate malicious rows
print("\\n--- GENERATING MALICIOUS ROWS ---")
malicious_pool, n_mal_gen = generate_pool(
    malicious_trained_models, malicious_strata,
    CONFIG['n_malicious_target'], 'MALICIOUS', CONFIG['oversample_factor']
)

# Combine pools
all_benign = pd.concat(benign_pool.values(), ignore_index=True)
all_malicious = pd.concat(malicious_pool.values(), ignore_index=True)

print(f"\\n{'=' * 70}")
print(f"RAW GENERATION SUMMARY:")
print(f"   Benign pool:    {len(all_benign):,} rows")
print(f"   Malicious pool: {len(all_malicious):,} rows")

# Downsample to exact targets
if len(all_benign) > CONFIG['n_benign_target']:
    all_benign = all_benign.sample(n=CONFIG['n_benign_target'], random_state=42).reset_index(drop=True)
    print(f"   Benign downsampled to: {len(all_benign):,}")

if len(all_malicious) > CONFIG['n_malicious_target']:
    all_malicious = all_malicious.sample(n=CONFIG['n_malicious_target'], random_state=42).reset_index(drop=True)
    print(f"   Malicious downsampled to: {len(all_malicious):,}")

# Final combined
final_synth = pd.concat([all_benign, all_malicious], ignore_index=True)
print(f"\\nFINAL SYNTHETIC DATASET: {len(final_synth):,} rows")
print(f"   Benign:    {(final_synth['malicious']==0).sum():,}")
print(f"   Malicious: {(final_synth['malicious']==1).sum():,}")

print(f"\\nSource type distribution:")
for label_val, label_name in [(0, 'Benign'), (1, 'Malicious')]:
    sub = final_synth[final_synth['malicious'] == label_val]
    print(f"   {label_name}:")
    for st, cnt in sub['source_type'].value_counts().items():
        print(f"      {st}: {cnt:,}")
print("=" * 70)""")

# ═══════════════════════════════════════════════════════════════
# CELL 13 — Markdown: Decode
# ═══════════════════════════════════════════════════════════════
add_md("""## Phase 3: Decode Embeddings & Reverse-Map to Original Columns""")

# ═══════════════════════════════════════════════════════════════
# CELL 14 — Decode embeddings
# ═══════════════════════════════════════════════════════════════
add_code("""# ============================================================================
# DECODE EMBEDDING COLUMNS TO NEAREST REAL TEXT (Cosine Similarity)
# ============================================================================

print("=" * 70)
print("DECODING EMBEDDINGS -> TEXT")
print("=" * 70)

# Load SecBERT model
secbert_model = None
if SECBERT_AVAILABLE:
    print("Loading SecBERT...")
    try:
        secbert_model = SentenceTransformer(CONFIG['secbert_model'])
        print(f"   SecBERT loaded: {CONFIG['secbert_model']}")
    except:
        secbert_model = SentenceTransformer('all-MiniLM-L6-v2')
        print("   Fallback: all-MiniLM-L6-v2")
    if device == 'cuda':
        secbert_model = secbert_model.to(torch.device(device))

# Reference texts from combined dataset (both benign and malicious)
original_texts = combined_df['_source.rule.description'].fillna('').astype(str)
valid_mask = ~original_texts.isin(['', 'nan', 'None', 'NaN', 'MISSING'])
valid_texts = original_texts[valid_mask].values
valid_emb_768 = log_emb_raw[valid_mask.values]

unique_texts, unique_idx = np.unique(valid_texts, return_index=True)
unique_emb_768 = valid_emb_768[unique_idx]
unique_emb_pca = pca_log.transform(unique_emb_768)

print(f"   Reference texts: {len(unique_texts)} unique")

# Decode log embeddings for synthetic data
emb_cols = sorted([c for c in final_synth.columns if c.startswith('log_secbert_emb_')])
if emb_cols:
    synth_emb_matrix = np.zeros((len(final_synth), N_PCA))
    for col in emb_cols:
        dim = int(col.split('_')[-1])
        if dim < N_PCA:
            synth_emb_matrix[:, dim] = pd.to_numeric(final_synth[col], errors='coerce').fillna(0).values

    sims = cosine_similarity(synth_emb_matrix, unique_emb_pca)
    nearest_idx = sims.argmax(axis=1)
    nearest_texts = unique_texts[nearest_idx]
    mean_sim = sims.max(axis=1).mean()

    final_synth['rule_description'] = nearest_texts
    print(f"   Log embedding decoded: mean cosine sim = {mean_sim:.4f}")

# Fill missing commands from original data by matching source type
cmd_col = '_source.data.command'
if cmd_col in final_synth.columns:
    cmd_vals = final_synth[cmd_col].fillna('').astype(str)
    n_missing = (cmd_vals.str.len() == 0).sum() + cmd_vals.isin(['MISSING','nan','None']).sum()
    print(f"   Commands: {n_missing} missing")

    if n_missing > 0:
        orig_cmds = combined_df[cmd_col].fillna('').astype(str)
        valid_cmd_mask = orig_cmds.str.len() > 3
        cmd_by_type = defaultdict(list)
        combined_df_temp = combined_df.copy()
        SOURCE_TYPES_DET = {
            'network':  ['_source.data.protocol', '_source.data.srcip', '_source.data.url'],
            'syscheck': ['_source.syscheck.event', '_source.syscheck.path'],
            'sca':      ['_source.data.sca.check.result'],
            'audit':    ['_source.data.audit.syscall', '_source.data.audit.exe'],
        }
        combined_df_temp['_source_type'] = 'base'
        for st, dc in SOURCE_TYPES_DET.items():
            ex = [c for c in dc if c in combined_df_temp.columns]
            if ex:
                combined_df_temp.loc[combined_df_temp[ex].notna().any(axis=1), '_source_type'] = st
        for idx in combined_df_temp[valid_cmd_mask].index:
            stype = combined_df_temp.at[idx, '_source_type']
            cmd_by_type[stype].append(orig_cmds[idx])

        filled = 0
        for idx in final_synth.index:
            val = str(final_synth.at[idx, cmd_col])
            if val in ['', 'MISSING', 'nan', 'None']:
                stype = final_synth.at[idx, 'source_type']
                if stype in cmd_by_type and cmd_by_type[stype]:
                    final_synth.at[idx, cmd_col] = np.random.choice(cmd_by_type[stype])
                    filled += 1
        print(f"   Filled {filled} missing commands")

print("=" * 70)""")

# ═══════════════════════════════════════════════════════════════
# CELL 15 — Reverse map to original columns
# ═══════════════════════════════════════════════════════════════
add_code("""# ============================================================================
# REVERSE MAP: Features -> Original Dataset Columns
# ============================================================================

print("=" * 70)
print("REVERSE MAPPING TO ORIGINAL COLUMNS")
print("=" * 70)

def safe_col(col_name, df):
    if col_name in df.columns:
        return pd.to_numeric(df[col_name], errors='coerce').fillna(0)
    return pd.Series(0, index=df.index)

# Start with metadata
reverse_df = pd.DataFrame(index=final_synth.index)
reverse_df['malicious'] = final_synth['malicious']
reverse_df['source_type'] = final_synth['source_type']

# 1. _source.decoder.name
decoder_map = {
    'decoder_auditd': 'auditd',
    'decoder_web-accesslog': 'web-accesslog',
    'decoder_dpkg-decoder': 'dpkg-decoder',
    'decoder_syscheck_deleted': 'syscheck_deleted',
    'decoder_syscheck_integrity_changed': 'syscheck_integrity_changed',
}
reverse_df['_source.decoder.name'] = np.nan
for feat, name in decoder_map.items():
    mask = safe_col(feat, final_synth) >= 0.5
    reverse_df.loc[mask, '_source.decoder.name'] = name

# 2. _source.rule.firedtimes
reverse_df['_source.rule.firedtimes'] = safe_col('firedtimes', final_synth).clip(lower=0).round().astype(int)

# 3. _source.location
location_map = {
    'location__var_log_audit_audit.log': '/var/log/audit/audit.log',
    'location__var_log_apache2_access.log': '/var/log/apache2/access.log',
    'location__var_log_auth.log': '/var/log/auth.log',
    'location_syscheck': 'syscheck',
}
reverse_df['_source.location'] = np.nan
for feat, loc in location_map.items():
    mask = safe_col(feat, final_synth) >= 0.5
    reverse_df.loc[mask, '_source.location'] = loc

# 4. _source.data.srcip
real_ips = combined_df['_source.data.srcip'].dropna().unique()
private_ips = [ip for ip in real_ips
               if str(ip).startswith(('10.','192.168.','172.16.','172.17.',
                                      '172.18.','172.19.','172.20.','172.21.',
                                      '172.22.','172.23.','172.24.','172.25.',
                                      '172.26.','172.27.','172.28.','172.29.',
                                      '172.30.','172.31.'))]
if not private_ips:
    private_ips = ['10.0.0.1', '192.168.1.1']

ip_mask = safe_col('srcip_is_private', final_synth) >= 0.5
reverse_df['_source.data.srcip'] = np.nan
reverse_df.loc[ip_mask, '_source.data.srcip'] = [
    np.random.choice(private_ips) for _ in range(ip_mask.sum())]

# 5. _source.syscheck.path
real_paths = combined_df['_source.syscheck.path'].dropna().astype(str).unique()
_sensitive_dirs = ['/etc', '/root', '/var/log', '/boot', '/usr/sbin']
_temp_dirs = ['/tmp', '/temp']
_sens_pool = [p for p in real_paths if any(d in p for d in _sensitive_dirs)]
_temp_pool = [p for p in real_paths if any(d in p for d in _temp_dirs)]
_other_pool = [p for p in real_paths if p not in _sens_pool and p not in _temp_pool]

path_missing = safe_col('path_is_missing', final_synth)
path_depth = safe_col('path_depth', final_synth)
path_temp = safe_col('path_is_temp', final_synth)
path_sens = safe_col('path_is_sensitive', final_synth)

def pick_path(i):
    if path_missing.iloc[i] >= 0.5:
        return np.nan
    depth = int(max(path_depth.iloc[i], 1))
    if path_temp.iloc[i] >= 0.5:
        pool = [p for p in _temp_pool if p.count('/') == depth] or _temp_pool
    elif path_sens.iloc[i] >= 0.5:
        pool = [p for p in _sens_pool if p.count('/') == depth] or _sens_pool
    else:
        pool = [p for p in _other_pool if p.count('/') == depth] or _other_pool or list(real_paths)
    return np.random.choice(pool) if pool else np.nan

print("   Reverse-mapping syscheck paths...")
reverse_df['_source.syscheck.path'] = [pick_path(i) for i in tqdm(range(len(final_synth)), desc='   Paths')]

# 6. _source.syscheck.md5_after
md5_mask = safe_col('has_md5', final_synth) >= 0.5
reverse_df['_source.syscheck.md5_after'] = np.nan
reverse_df.loc[md5_mask, '_source.syscheck.md5_after'] = [
    secrets.token_hex(16) for _ in range(md5_mask.sum())]

# 7. _source.syscheck.sha256_after
sha_mask = safe_col('has_sha256', final_synth) >= 0.5
reverse_df['_source.syscheck.sha256_after'] = np.nan
reverse_df.loc[sha_mask, '_source.syscheck.sha256_after'] = [
    secrets.token_hex(32) for _ in range(sha_mask.sum())]

# 8. _source.syscheck.event
event_map = {'syscheck_added': 'added', 'syscheck_deleted': 'deleted', 'syscheck_modified': 'modified'}
reverse_df['_source.syscheck.event'] = np.nan
for feat, ev in event_map.items():
    mask = safe_col(feat, final_synth) >= 0.5
    reverse_df.loc[mask, '_source.syscheck.event'] = ev

# 9. _source.data.command
if '_source.data.command' in final_synth.columns:
    reverse_df['_source.data.command'] = final_synth['_source.data.command']

# 10. _source.rule.description
if 'rule_description' in final_synth.columns:
    reverse_df['_source.rule.description'] = final_synth['rule_description']

# 11. MITRE columns (malicious only)
if '_source.rule.mitre.tactic' in final_synth.columns:
    reverse_df['_source.rule.mitre.tactic'] = final_synth['_source.rule.mitre.tactic']
else:
    reverse_df['_source.rule.mitre.tactic'] = np.nan

if '_source.rule.mitre.id' in final_synth.columns:
    reverse_df['_source.rule.mitre.id'] = final_synth['_source.rule.mitre.id']
else:
    reverse_df['_source.rule.mitre.id'] = np.nan

# Clean MITRE for benign (should be NaN)
reverse_df.loc[reverse_df['malicious'] == 0, '_source.rule.mitre.tactic'] = np.nan
reverse_df.loc[reverse_df['malicious'] == 0, '_source.rule.mitre.id'] = np.nan

# Summary
orig_cols = [c for c in reverse_df.columns if c.startswith('_source.')]
print(f"\\nREVERSE-MAPPED DATASET:")
print(f"   Shape: {reverse_df.shape[0]:,} rows x {reverse_df.shape[1]} cols")
print(f"   Benign:    {(reverse_df['malicious']==0).sum():,}")
print(f"   Malicious: {(reverse_df['malicious']==1).sum():,}")
print(f"   Original columns ({len(orig_cols)}):")
for c in orig_cols:
    nn = reverse_df[c].notna().sum()
    print(f"     {c}: {nn}/{len(reverse_df)} ({nn/len(reverse_df)*100:.1f}%)")

print("=" * 70)""")

# ═══════════════════════════════════════════════════════════════
# CELL 16 — Save outputs
# ═══════════════════════════════════════════════════════════════
add_code("""# ============================================================================
# SAVE FINAL DATASET
# ============================================================================

print("=" * 70)
print("SAVING FINAL COMBINED DATASET")
print("=" * 70)

save_dir = Path(OUTPUT_DIR)

# Save full dataset
reverse_df.to_csv(save_dir / 'synthetic_benign_malicious.csv', index=False)
reverse_df.to_excel(save_dir / 'synthetic_benign_malicious.xlsx', index=False, engine='openpyxl')
print(f"   Full dataset saved: {len(reverse_df):,} rows")

# Save benign only
benign_out = reverse_df[reverse_df['malicious'] == 0]
benign_out.to_csv(save_dir / 'synthetic_benign_only.csv', index=False)
print(f"   Benign only: {len(benign_out):,} rows")

# Save malicious only
mal_out = reverse_df[reverse_df['malicious'] == 1]
mal_out.to_csv(save_dir / 'synthetic_malicious_only.csv', index=False)
print(f"   Malicious only: {len(mal_out):,} rows")

# Save metadata
metadata = {
    'total_rows': len(reverse_df),
    'n_benign': int((reverse_df['malicious']==0).sum()),
    'n_malicious': int((reverse_df['malicious']==1).sum()),
    'columns': list(reverse_df.columns),
    'source_type_distribution': {
        'benign': reverse_df[reverse_df['malicious']==0]['source_type'].value_counts().to_dict(),
        'malicious': reverse_df[reverse_df['malicious']==1]['source_type'].value_counts().to_dict(),
    },
    'generation_date': datetime.now().isoformat(),
}
with open(save_dir / 'generation_metadata.json', 'w') as f:
    json.dump(metadata, f, indent=2, default=str)

print(f"\\nAll outputs saved to: {OUTPUT_DIR}")
print("=" * 70)""")

# ═══════════════════════════════════════════════════════════════
# CELL 17 — Summary & visualization
# ═══════════════════════════════════════════════════════════════
add_code("""# ============================================================================
# DATASET SUMMARY & VISUALIZATION
# ============================================================================

fig, axes = plt.subplots(1, 3, figsize=(18, 5))

# 1. Class distribution
class_counts = reverse_df['malicious'].value_counts().sort_index()
bars = axes[0].bar(['Benign (0)', 'Malicious (1)'],
                   [class_counts.get(0, 0), class_counts.get(1, 0)],
                   color=['#2ecc71', '#e74c3c'])
for bar in bars:
    axes[0].text(bar.get_x() + bar.get_width()/2., bar.get_height() + 500,
                 f'{int(bar.get_height()):,}', ha='center', fontweight='bold')
axes[0].set_title('Class Distribution', fontweight='bold')
axes[0].set_ylabel('Count')

# 2. Source type distribution
src_benign = reverse_df[reverse_df['malicious']==0]['source_type'].value_counts()
src_mal = reverse_df[reverse_df['malicious']==1]['source_type'].value_counts()
all_types = sorted(set(src_benign.index) | set(src_mal.index))
x = np.arange(len(all_types))
w = 0.35
axes[1].bar(x - w/2, [src_benign.get(t, 0) for t in all_types], w, label='Benign', color='#2ecc71')
axes[1].bar(x + w/2, [src_mal.get(t, 0) for t in all_types], w, label='Malicious', color='#e74c3c')
axes[1].set_xticks(x)
axes[1].set_xticklabels(all_types, rotation=45)
axes[1].legend()
axes[1].set_title('Source Type Distribution', fontweight='bold')

# 3. Non-null coverage
cols_to_check = [c for c in reverse_df.columns if c.startswith('_source.')]
coverage = [(c.replace('_source.',''), reverse_df[c].notna().mean()*100) for c in cols_to_check]
coverage.sort(key=lambda x: x[1], reverse=True)
axes[2].barh([c[0] for c in coverage], [c[1] for c in coverage], color='#3498db')
axes[2].set_xlim(0, 105)
axes[2].set_title('Column Coverage (%)', fontweight='bold')

plt.tight_layout()
save_dir = Path(OUTPUT_DIR)
plt.savefig(save_dir / 'dataset_summary.png', dpi=150, bbox_inches='tight')
plt.show()
print(f"\\nDashboard saved to {OUTPUT_DIR}/dataset_summary.png")

# Show sample
print(f"\\nSample benign rows:")
display(reverse_df[reverse_df['malicious']==0].head(5))
print(f"\\nSample malicious rows:")
display(reverse_df[reverse_df['malicious']==1].head(5))""")

# ═══════════════════════════════════════════════════════════════
# Build notebook JSON
# ═══════════════════════════════════════════════════════════════
nb = {
    "nbformat": 4,
    "nbformat_minor": 2,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3"
        },
        "language_info": {
            "name": "python",
            "version": "3.10.0"
        }
    },
    "cells": cells
}

with open(r'c:\Users\KassoussiOussama-PFE\Downloads\pfe\Benign_Malicious_Generation.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)

print(f"Notebook created with {len(cells)} cells")
