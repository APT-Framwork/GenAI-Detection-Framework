# STRIX — ML/RL Detection System Reference

> **Status:** generated 2026-04-17 from a full walk of `apps/notebooks/*` and `RL_agent/*`. Where the notebooks contradict the production loader code, **the loader is what actually runs** — discrepancies are called out explicitly in §11.
>
> **Canonical architecture docs:** [RL_agent/AGENT_ARCHITECTURE.md](../RL_agent/AGENT_ARCHITECTURE.md) and [RL_agent/ARCHITECTURE.md](../RL_agent/ARCHITECTURE.md). This document is an *operational* reference — it does not replace those diagrams, it extends them with the actual column orders, artifact paths, and mismatches that the backend will have to resolve.

---

## 1. System Overview

STRIX detects Advanced Persistent Threats by fusing four specialized detection models (Autoencoder, Beta-VAE, Transformer, GraphSAGE GNN) with a DQN reinforcement-learning agent. Each raw Wazuh alert is converted to a 55-dim feature vector; the AE, VAE, and GNN consume this vector directly, while the Transformer consumes the AE's 64-dim latent. Their outputs fuse into a 13-dim state vector, and a DQN picks one of 5 defensive actions (Monitor → Low Alert → Escalate → Isolate → Block). An episode is a **sequence** of 5–30 alerts for attacks, 5–15 for benign — each alert is one time step. Full data journey and reward function live in [AGENT_ARCHITECTURE.md](../RL_agent/AGENT_ARCHITECTURE.md); model-interaction diagrams live in [ARCHITECTURE.md](../RL_agent/ARCHITECTURE.md).

The ML stack has two distinct training regimes: benign-only reconstruction (AE, VAE) and supervised (Transformer on AE latents, GNN on labeled alert graphs). The RL training mixes 500 synthetic sequences (ReALTabFormer / pattern-generated) with ~600 real-data sequences carved from [RL_agent/data/combined_dataset_final_mal_sum.xlsx](../RL_agent/data/combined_dataset_final_mal_sum.xlsx) ending at S7. The shipped weights in [apps/models/](../apps/models/) — `ae_model.pth`, `vae_model.pth`, `transformer_model.pth`, `gnn_model.pth`, `rl_agent.pth` — correspond to the Top-25-feature variants (AE latent=64, VAE latent=32, Transformer 4-layer, GNN 55-feat no-rule).

---

## 2. Canonical 55-dim Feature Schema

Declared in [RL_agent/synthetic/data_loader.py:31-62](../RL_agent/synthetic/data_loader.py#L31-L62). `TOP_25_FEATURES` is a list of 25 conceptual features; `expand_feature_list()` converts the two `*_secbert_embedding` entries into 16 PCA columns each, yielding 55 total.

### 2.1 Data-loader column order (what the backend produces)

| Idx | Column | Type | Source / formula |
|:---:|:---|:---:|:---|
| 0–15 | `log_secbert_emb_0 … log_secbert_emb_15` | float | SecBERT(`_source.full_log`, max_len=128, mean-pool over last_hidden_state) → PCA-16 |
| 16 | `decoder_auditd` | 0/1 | `_source.decoder.name == "auditd"` |
| 17 | `firedtimes` | int | `_source.rule.firedtimes` |
| 18 | `location__var_log_audit_audit.log` | 0/1 | `_source.location == "/var/log/audit/audit.log"` |
| 19 | `srcip_is_private` | 0/1 | `ipaddress.ip_address(data.srcip).is_private` |
| 20 | `decoder_web-accesslog` | 0/1 | `decoder.name == "web-accesslog"` |
| 21 | `location__var_log_apache2_access.log` | 0/1 | path match on Apache access log |
| 22 | `firedtimes_log` | float | `np.log1p(firedtimes)` |
| 23 | `path_is_missing` | 0/1 | `syscheck.path is null` |
| 24 | `has_md5` | 0/1 | `syscheck.md5_after is not null` |
| 25 | `cmd_length` | int | `len(str(data.command))` |
| 26 | `has_sha256` | 0/1 | `syscheck.sha256_after is not null` |
| 27 | `syscheck_added` | 0/1 | `syscheck.event == "added"` |
| 28 | `cmd_is_missing` | 0/1 | `data.command is null/empty` |
| 29 | `decoder_dpkg-decoder` | 0/1 | `decoder.name == "dpkg-decoder"` |
| 30 | `syscheck_deleted` | 0/1 | `syscheck.event == "deleted"` |
| 31 | `path_depth` | int | `min(path.count("/"), 15)` |
| 32 | `syscheck_modified` | 0/1 | `syscheck.event == "modified"` |
| 33 | `location__var_log_auth.log` | 0/1 | path match on auth log |
| 34–49 | `cmd_secbert_emb_0 … cmd_secbert_emb_15` | float | SecBERT(`_source.data.command`, max_len=128, mean-pool) → PCA-16 |
| 50 | `decoder_syscheck_deleted` | 0/1 | `decoder.name == "syscheck_deleted"` |
| 51 | `path_is_sensitive` | 0/1 | path starts with `/etc`, `/root`, `/boot`, etc. |
| 52 | `decoder_syscheck_integrity_changed` | 0/1 | `decoder.name == "syscheck_integrity_changed"` |
| 53 | `location_syscheck` | 0/1 | `location == "syscheck"` |
| 54 | `path_is_temp` | 0/1 | `path startswith "/tmp"` |

Breakdown: **16 log-SecBERT PCA + 16 cmd-SecBERT PCA + 4 numerical (`firedtimes`, `firedtimes_log`, `cmd_length`, `path_depth`) + 19 binary = 55**.

### 2.2 ⚠️ Column-order mismatch between notebooks and loader

The AE, VAE, and GNN were **all trained with a different column order** from the one in `data_loader.FEATURE_COLUMNS`:

- **Notebook training order:** `[23 individual ranked features]` → `[log_secbert_emb_0..15]` → `[cmd_secbert_emb_0..15]`
- **Loader order (above):** interleaved.

`strict=True` checkpoint loading succeeds (weight *shapes* match) but `encoder.weight[:, j]` is bound to whichever column was at position `j` during training. **Feeding the loader's order at inference permutes inputs relative to training weights → silently broken predictions.** The fix is either to re-order `TOP_25_FEATURES` in `data_loader.py` to match the notebook, or to persist the canonical training order alongside each checkpoint and reindex at inference time. Must be resolved before any backend inference ships.

---

## 3. Autoencoder (AE) — Regularized VAE-style

**Notebooks:** [feature_selection.ipynb](../apps/notebooks/feature_selection.ipynb) (V1, leaky, superseded), [feature_selection_final.ipynb](../apps/notebooks/feature_selection_final.ipynb) (V2, produces 119-feat parquet + SecBERT embeddings), [TP1_AE_FeatureSelection.ipynb](../apps/notebooks/TP1_AE_FeatureSelection.ipynb) (AE training).
**Loader:** [RL_agent/models/autoencoder_loader.py](../RL_agent/models/autoencoder_loader.py).
**Weights:** [apps/models/ae_model.pth](../apps/models/ae_model.pth) (≡ `reg_ae_top25_features.pth`, 501 KB).

### 3.1 Purpose

Reconstruction-based anomaly scorer trained on **benign alerts only** (72,246 train / 18,062 val from the 90,308-benign pool). Produces two outputs for the RL state (`anomaly_score`, `reconstruction_error`) and a **64-dim latent** that is fed into the Transformer.

### 3.2 Input / Preprocessing

- **Input:** 55-dim feature vector (see §2).
- **Scaler:** `sklearn.StandardScaler` fit on the full 55-col matrix (all 115,726 rows, train+mal mixed — no fit-on-train-only). **Not exported** in any notebook → inference blocker.
- **SecBERT:** `jackaduma/SecBERT` (HuggingFace), `AutoTokenizer`, `max_length=128`, `batch_size=64`, **mean pooling over `last_hidden_state`** with attention-mask weighting, then `sklearn.PCA(n_components=16, random_state=42)` per text field. Tokenizer, model cache, and fitted PCA objects are **not exported** → blockers.
- **Binary / numerical:** computed inline in `FeatureEngineerNoLeakage` (V2 notebook).

### 3.3 Model architecture

From [TP1_AE_FeatureSelection.ipynb](../apps/notebooks/TP1_AE_FeatureSelection.ipynb) Cell 9 (`RegularizedAutoencoder`), `input_dim=55, latent_dim=64, dropout=0.2`:

```
encoder_body:
  Linear(55→256) → BatchNorm1d(256) → LeakyReLU(0.2) → Dropout(0.2)
  Linear(256→128) → BatchNorm1d(128) → LeakyReLU(0.2) → Dropout(0.2)
fc_mu:     Linear(128→64)
fc_logvar: Linear(128→64)
decoder:
  Linear(64→128) → BatchNorm1d(128) → LeakyReLU(0.2) → Dropout(0.2)
  Linear(128→256) → BatchNorm1d(256) → LeakyReLU(0.2) → Dropout(0.2)
  Linear(256→55)
center: nn.Parameter(torch.zeros(64))   # learnable
```

Weight init: Kaiming-normal (`nonlinearity='leaky_relu'`), BN weights=1 / bias=0.

### 3.4 Training

- Loss: `L = MSE(x̂,x) + β_eff·KL + γ·‖z − center‖²` with `β=1e-3`, `γ=1e-2`, KL warmup = linear ramp over first 20% of epochs.
- Optimizer: `AdamW(lr=1e-3, weight_decay=1e-5)`; scheduler `ReduceLROnPlateau(factor=0.5, patience=5)`; grad clip `max_norm=1.0`.
- 100 epochs max, early stop patience 15 on val total loss.
- Batch 256, seed 42.
- The learnable `center` starts at zero and converges (via `γ·‖z−center‖²`) to the **centroid of benign-latent embeddings**.

### 3.5 Output / inference contract

Loader method [`AutoencoderLoader.get_anomaly_score`](../RL_agent/models/autoencoder_loader.py#L179):

```python
recon, mu, logvar, z = model(features)          # features: (B, 55) float32
recon_error = mean((features - recon)**2, dim=1)   # (B,)
center_dist = sum((mu - center)**2, dim=1)         # (B,)
anomaly_score = recon_error + 0.1 * center_dist    # (B,)
```

And [`encode`](../RL_agent/models/autoencoder_loader.py#L224) returns `mu` (64-dim, `cpu().numpy()`) — fed to the Transformer.

### 3.6 Evaluation (top-25 variant, from notebook)

ROC-AUC 0.973+, PR-AUC 0.92, balanced-accuracy 0.92 (at Youden-J threshold over the full labeled set — in-sample).

### 3.7 Exported artifacts

| File | Status | Notes |
|:---|:---:|:---|
| `apps/models/ae_model.pth` | ✓ | State-dict, 501 KB. Loader variant `reg_ae_64`. |
| `StandardScaler` (55-col) | **✗** | Blocker: AE weights meaningless without it. |
| `log_secbert_pca_16.pkl` | **✗** | Blocker: PCA fit lives only in `SecBERTEmbedder.pca` attribute, not pickled. |
| `cmd_secbert_pca_16.pkl` | **✗** | Blocker: same. |
| `selected_features_top25.json` | ✓ (in `autoencoder_outputs/`) | Contains canonical training column order. |
| Anomaly threshold | **✗** | Notebook computes `th_reg_reduced` via Youden-J but does not persist it. Must recompute on inference-formula (§3.5) scores. |

---

## 4. Beta-VAE

**Notebook:** [TP2_VAE_FeatureSelection.ipynb](../apps/notebooks/TP2_VAE_FeatureSelection.ipynb).
**Loader:** [RL_agent/models/vae_loader.py](../RL_agent/models/vae_loader.py).
**Weights:** [apps/models/vae_model.pth](../apps/models/vae_model.pth) (≡ `beta_vae_top25_features.pth`).

### 4.1 Purpose

Probabilistic reconstruction model producing `malicious_probability` (calibrated) and `uncertainty` (latent variance) for the RL state. Same 55-dim input, different architecture than AE.

### 4.2 Model architecture

From notebook Part 5 (`BetaVAE`), `input_dim=55, latent_dim=32`:

```
encoder:
  Linear(55→512) → BatchNorm → ReLU → Dropout(0.3)
  Linear(512→256) → BatchNorm → ReLU → Dropout(0.3)
  Linear(256→128) → BatchNorm → ReLU
fc_z_mean:    Linear(128→32)
fc_z_log_var: Linear(128→32)
decoder:
  Linear(32→128) → BN → ReLU → Dropout
  Linear(128→256) → BN → ReLU → Dropout
  Linear(256→512) → BN → ReLU → Dropout
  Linear(512→55)
center: nn.Parameter(torch.zeros(32))   # learnable
```

Weight init: Xavier-normal (Linear), ones/zeros (BN). Total params ≈ 401,815.

### 4.3 Training

- Loss: `L = MSE(x̂,x) + β_eff·KL + γ·‖z − center‖²` with `β=0.5`, `γ=1e-2`, KL warmup `warmup_frac=0.2`.
- Optimizer: `AdamW(lr=1e-3, weight_decay=1e-5)`, `ReduceLROnPlateau(factor=0.5, patience=5)`, grad clip 1.0.
- Batch 256, 100 epochs max, early stop patience 15.
- Trained benign-only (72,246 train / 18,062 val).

### 4.4 Malicious-probability calibration (IMPORTANT)

**Notebook:** fits `sklearn.linear_model.LogisticRegression` on `(anomaly_score → y_malicious)` over the full labeled dataset and pickles it to `probability_calibrators.pkl`. Anomaly score = `MSE(x̂,x) + β·per-sample-KL` (no center term).

**Loader:** ignores the pickled calibrator and applies a **hand-written heuristic**:

```python
combined_score = recon_error + 0.05 * center_dist
malicious_prob = sigmoid(combined_score * 2.0 - 1.0)
uncertainty    = mean(exp(z_log_var), dim=1)
```

The loader's formula has no statistical grounding; the notebook's `probability_calibrators.pkl` is the correct artifact to wire in. **Discrepancy — see §11.**

### 4.5 Variants

Three `MODEL_VARIANTS` are declared in `vae_loader.py`:

| Key | File | Origin |
|:---|:---|:---|
| `beta_vae` | `beta_vae_top25_features.pth` | **Produced by this notebook** (all-data, β=0.5) — default. |
| `beta_vae_32` | `beta_vae_top25_features_32dim.pth` | **Not produced by any notebook in the repo** — provenance unknown. |
| `beta_vae_malicious` | `beta_vae_malicious_only_32dim.pth` | **Not produced by any notebook in the repo** — provenance unknown. |

### 4.6 Evaluation

Top-25 Beta-VAE test metrics (from notebook): ROC-AUC 0.9740, AP 0.9229, F1 0.8636, precision 0.8298, recall 0.9002 (Youden-J threshold; in-sample).

### 4.7 Exported artifacts

| File | Status | Notes |
|:---|:---:|:---|
| `apps/models/vae_model.pth` | ✓ | State-dict. |
| `probability_calibrators.pkl` | ✓ (in notebook `vae_anomaly_detector_outputs/`) | **Not used by the loader** — should be. |
| `StandardScaler` | **✗** | Same blocker as AE (shared preprocessing pipeline). |
| `selected_features_top25.json` | ✓ | |

---

## 5. Transformer — CKC Next-Stage Predictor

**Notebook:** [TP2_MLA_TE.ipynb](../apps/notebooks/TP2_MLA_TE.ipynb).
**Loader:** [RL_agent/models/transformer_loader.py](../RL_agent/models/transformer_loader.py).
**Weights:** [apps/models/transformer_model.pth](../apps/models/transformer_model.pth) (3.5 MB).

### 5.1 Purpose

Given a sequence of AE latent vectors (64-dim) representing alerts seen so far, predict the CKC stage of the **next** alert (`target = ckc[t+seq_length]` with `seq_length=4`). Produces two RL-state values: `predicted_next_ckc_stage ∈ {0..7}` and `prediction_confidence ∈ [0,1]`.

### 5.2 Input

- **Shape:** `(batch, seq_len, 64)` — sequence of `mu` vectors from AE `fc_mu`.
- **Not** raw 55-dim features. The AE is a hard prerequisite.
- Notebook loads pre-computed `latent_vectors.npy` from `autoencoder_outputs/` (offline encode, not live-coupled to AE at train time).
- Sliding-window sequence construction: `seq_length=4`, `stride=1`, single temporal stream (no per-agent grouping — `agent_ids = np.ones(N)` overrides grouping). 115,722 sequences total. 70/15/15 split, seed 42.

### 5.3 Model architecture

From notebook Cell 15 (`CKCTransformer`):

```
input_projection = Sequential(
    Linear(64→128), LayerNorm(128), ReLU, Dropout(0.1)
)
pos_encoder = SinusoidalPositionalEncoding(d_model=128, max_len=500, dropout=0.1)
transformer_encoder = TransformerEncoder(
    num_layers=4,
    norm=LayerNorm(128),
    layer=TransformerEncoderLayer(
        d_model=128, nhead=8, dim_feedforward=512,
        dropout=0.1, activation='gelu',
        batch_first=True, norm_first=True,     # ← PRE-LN
    )
)
pooling: x[:, -1, :]                            # LAST TOKEN, not mean pool
output_head = Sequential(
    Linear(128→64), ReLU, Dropout(0.1), Linear(64→8)
)
```

Weight init: Xavier-uniform (dim > 1). ~810,696 params.

### 5.4 Training

- Loss: `CrossEntropyLoss(weight=class_weights)`. Weights are inverse-frequency per training target:
  `[0.2115, 29.9953, 0.0000, 1.1650, 4.4948, 15.0562, 0.0000, 10.8537]` for classes 0..7.
  **S2 (Weaponization) and S6 (C&C) have weight 0 because they never appear in training data** — the corresponding output heads are never trained and are effectively dead at inference.
- Optimizer: `AdamW(lr=1e-4, weight_decay=1e-5)`.
- Scheduler: `ReduceLROnPlateau(factor=0.5, patience=5)` on val loss.
- Batch 32, 100 epochs max, early stop patience 15. Saved run stopped at epoch 31 (best val loss 0.5748 at epoch 16).
- Grad clip 1.0.

### 5.5 Output / inference contract

[`TransformerLoader.predict_next_stage`](../RL_agent/models/transformer_loader.py#L212):

```python
logits = model(latent_sequence)                         # (1, 8)
probs  = softmax(logits, dim=-1).squeeze(0)             # (8,)
return {
  'predicted_next_ckc_stage': argmax(probs).item(),     # 0..7
  'prediction_confidence':    probs[argmax].item(),
  'stage_name':               CKC_STAGES[argmax],
  'all_probabilities':        probs.cpu().numpy(),
}
```

At step 0 of an episode the env skips the Transformer (`predicted_next_stage = current_ckc`, `confidence = 0.5`) — see [apt_env.py:222-241](../RL_agent/env/apt_env.py#L222-L241).

### 5.6 Evaluation

Weighted test metrics (n=17,359): accuracy 0.8602, weighted-F1 0.8854, weighted-precision 0.9231. Per-class F1: Benign 0.93, S1 0.14, S3 0.83, S4 0.49, S5 0.70, S7 0.48. Macro-F1 only 0.59 — rare classes (S1, S4, S7) substantially underperform.

### 5.7 Exported artifacts

| File | Status | Notes |
|:---|:---:|:---|
| `apps/models/transformer_model.pth` | ✓ | Contains `{'model_state_dict', 'config'}`. Config: `{input_dim:64, d_model:128, n_heads:8, n_encoder_layers:4, dim_feedforward:512, dropout:0.1, num_classes:8, max_seq_length:500, seq_length:4}`. |
| Checkpoint filename | **⚠️** | Loader expects `transformer_next_step_prediction_top25.pth`; backend must either rename the shipped `transformer_model.pth` or pass `model_path=` explicitly. |

---

## 6. GraphSAGE GNN — Propagation / Lateral Movement Detector

**Notebook:** [GNN_Network_Propagation.ipynb](../apps/notebooks/GNN_Network_Propagation.ipynb).
**Loader:** [RL_agent/models/gnn_loader.py](../RL_agent/models/gnn_loader.py).
**Weights:** [apps/models/gnn_model.pth](../apps/models/gnn_model.pth) (≡ `gnn_propagation_best_no_rule.pth`, 55-feature Part-2 variant).

### 6.1 Purpose

Node-level binary classifier on an alert-graph. Emits `risk ∈ [0,1]` per alert; three aggregated statistics feed the RL state: `GNN_node_risk_current_host`, `GNN_neighbor_risk`, `risk_growth`.

### 6.2 Input

- **Node features:** 55-dim (same as AE input, WITHOUT `rule_level` in the shipped Part-2 model). Notebook also trained a 56-feature Part-1 variant *with* `rule_level`; it is NOT what ships.
- **Scaler:** `StandardScaler` fit on the full 56-feature matrix (including `rule_level`), then `rule_level` is sliced off. Loader pads to 56, transforms, and slices back to 55 ([gnn_loader.py:227-237](../RL_agent/models/gnn_loader.py#L227-L237)). Scaler is pickled inside `gnn_propagation_metadata.pkl` (but — see §6.7 — that pickle is **not in the repo**).

### 6.3 Graph construction

[gnn_loader.py:199-352](../RL_agent/models/gnn_loader.py#L199-L352) reproduces the notebook exactly:

| Edge type | Partition | Window | Max fwd neighbors | Cross-machine gate |
|:---|:---|:---:|:---:|:---|
| 1. Intra-machine temporal | `machine_name` | 30 min | 3 | — |
| 2. Cross-machine user | `src_user` where user on ≥2 machines, `≠ 'none'` | 30 min | 5 | `machine[i] != machine[j]` |
| 3. Cross-machine IP | `src_ip` where IP on ≥2 machines, `≠ 'none'/''` | 30 min | 5 | `machine[i] != machine[j]` |
| 4. Self-loops | — | — | — | — |

Every edge is undirected (added both ways). Final graph: 115,726 nodes, 1,303,244 edges (avg degree 11.3).

### 6.4 Model architecture

`APTPropagationGNN`, `in_ch=55, hid=128, layers=3, drop=0.3`:

```
convs: ModuleList[
  SAGEConv(55→128, aggr='mean'),
  SAGEConv(128→128),
  SAGEConv(128→128),
]
bns:   ModuleList[BatchNorm(128), BatchNorm(128), BatchNorm(128)]
forward: for i in range(3):
  x_in = x
  x = bns[i](convs[i](x, edge_index))
  x = F.relu(x)
  if i > 0: x = x + x_in       # residual from layer 1 onwards
  x = F.dropout(x, 0.3, training)
head = Sequential(Linear(128→64), ReLU, Dropout(0.3), Linear(64→1))
output: head(x).squeeze(-1)    # logits
```

Total trainable params ≈ 89,089.

### 6.5 Training

- Loss: `BCEWithLogitsLoss(pos_weight=n_neg/n_pos ≈ 3.56)`.
- Optimizer: `AdamW(lr=1e-3, weight_decay=1e-4)`.
- Scheduler: `CosineAnnealingWarmRestarts(T_0=20, T_mult=2)`.
- Full-batch / full-graph transductive training; node-level stratified split 70/15/15, seed 42.
- 150 epochs, early-stop patience 30 on val F1. Part-2 best at epoch 144, val F1 0.7925.
- Grad clip 1.0.

### 6.6 Decision threshold

`find_balanced_threshold(y, prob, min_recall=0.80)`: walk the PR curve, keep points where `recall ≥ 0.80`, pick the one with max precision. Fallback to argmax-F1 if nothing satisfies min_recall.

- Part-2 (shipped) tuned threshold: **0.7743**, test F1 0.7961, precision 0.7902, recall 0.8020, AUC-ROC 0.9625.
- `gnn_loader.py` default fallback when metadata pickle is missing: **0.918** (the Part-1 threshold). **This will silently collapse recall on the shipped Part-2 weights — see §11.**

### 6.7 RL-state feature extraction

[gnn_loader.py:390-470](../RL_agent/models/gnn_loader.py#L390-L470) (`get_rl_state_features(target_machine, current_time, window_minutes=60)`):

| Feature | Computation |
|:---|:---|
| `GNN_node_risk_current_host` | mean `alert_risk` over nodes where `machine == target_machine ∧ current_time - 60min < ts ≤ current_time` |
| `GNN_neighbor_risk` | mean `alert_risk` over `external_neighbors = unique(dst_nodes[src in host_indices]) \ host_indices` |
| `risk_growth` | `global_risk(t−60m..t) − global_risk(t−120m..t−60m)`; if prev window empty → `global_risk(t)` |

Two redundant notebook features (`global_graph_risk`, `high_risk_ratio`) are dropped by the loader.

### 6.8 Exported artifacts

| File | Status | Notes |
|:---|:---:|:---|
| `apps/models/gnn_model.pth` | ✓ | 55-feat Part-2 checkpoint. **Does not match the loader's default filename** (`gnn_propagation_best_no_rule.pth`). Backend must rename / symlink / pass `model_path=`. |
| `gnn_propagation_metadata.pkl` | **✗** | **Missing from repo.** Must be regenerated with `in_ch=55`, `rule_level_included=False`, Part-2 scaler (refit on 55 cols), `threshold=0.7743`. |

---

## 7. RL Environment

**File:** [RL_agent/env/apt_env.py](../RL_agent/env/apt_env.py).
**State dim:** 13. **Action dim:** 5 discrete.

### 7.1 13-dim State construction

From [`_get_observation()`](../RL_agent/env/apt_env.py#L198):

| Idx | Feature | Source | Range | How computed |
|:---:|:---|:---:|:---:|:---|
| 0 | `anomaly_score` | AE | [0, 10] | `ae.get_anomaly_score(x)['anomaly_score'][0]` |
| 1 | `reconstruction_error` | AE | [0, 10] | `...['reconstruction_error'][0]` |
| 2 | `malicious_probability` | VAE | [0, 1] | `vae.get_malicious_probability(x)['malicious_probability'][0]` |
| 3 | `uncertainty` | VAE | [0, 10] | `...['uncertainty'][0]` |
| 4 | `predicted_next_ckc_stage` | Transformer | [0, 7] | At step 0: `current_ckc`. Else: `transformer.predict_next_stage(ae.encode(seq[:t+1]))['predicted_next_ckc_stage']` |
| 5 | `prediction_confidence` | Transformer | [0, 1] | At step 0: 0.5. Else from transformer result. |
| 6 | `current_ckc_stage` | Ground truth | [0, 7] | `sequence.ckc_stages[t]` |
| 7 | `time_since_first_event` | Temporal | [0, 10] | `(current_time − episode_start).total_seconds() / 3600` (hours) |
| 8 | `time_since_last_event` | Temporal | [0, 10] | `(current_time − last_event_time).total_seconds() / 60` (minutes) |
| 9 | `sequence_length_so_far` | Counter | [0, 100] | `self.current_step` |
| 10 | `gnn_node_risk` | GNN | [0, 1] | `gnn.get_rl_state_features(machine, current_time)['GNN_node_risk_current_host']` |
| 11 | `gnn_neighbor_risk` | GNN | [0, 1] | `...['GNN_neighbor_risk']` |
| 12 | `gnn_risk_growth` | GNN | [-1, 1] | `...['risk_growth']` |

Values are clipped to the `observation_space.Box` bounds before returning.

If GNN loader is `None` or disabled (no PyG install, or no graph built), indices 10–12 default to 0.0.

### 7.2 Action space

```
0: Monitor          — no action
1: Low Alert        — flag for analyst review
2: Escalate to SOC  — intervention, ends episode
3: Isolate Host     — intervention, ends episode
4: Block User/IP    — intervention, ends episode
```

`action ≥ 2` is an **intervention** (`ACTION_ESCALATE`); with `early_stop_on_intervention=True` (training default), the episode terminates.

### 7.3 Reward function

From [`_calculate_reward()`](../RL_agent/env/apt_env.py#L280):

```
intervention (action ≥ 2) on malicious alert:
    S1-S2 → +15.0      (excellent early catch)
    S3    → +10.0      (delivery caught)
    S4    →  +7.0      (exploitation caught)
    S5    →  +3.0      (installation — borderline)
    S6    →  +0.0      (C2 already — too late)
    S7    →  -2.0      (damage done)
    BONUS: +2.0 if action ∈ {Isolate, Block} and stage ≥ S4

intervention on benign alert (false positive):
    action == Escalate        → -2.0
    action ∈ {Isolate, Block} → -3.0  (-2 + -1 aggressive penalty)

Low Alert (action == 1):
    on malicious → +1.0
    on benign    → -0.5

Monitor (action == 0):
    on benign                → 0.0
    on malicious S1-S2       → 0.0
    on malicious S3          → -1.0
    on malicious S4          → -3.0
    on malicious S5          → -5.0
    on malicious S6+         → -8.0

End-of-episode penalty:
    If on last step AND is_malicious AND no prior intervention → reward -= 15.0
```

### 7.4 Episode termination

Triggered by any of:
1. Intervention taken (`action ≥ 2`) AND `early_stop_on_intervention=True`.
2. All alerts in sequence processed (`current_step >= len(sequence_features)`).
3. `current_step >= max_steps` (default 50).

### 7.5 reset() / step() contract

`reset(sequence)` requires:

```python
sequence = {
    'features':      np.ndarray (seq_len, 55),
    'ckc_stages':    list[int],
    'timestamps':    list[pd.Timestamp]  # or None -> auto-generated via Poisson
    'machine_names': list[str],          # optional, defaults to ['machine-1'] * seq_len
}
```

`step(action)` returns `(next_obs, reward, done, info)`. `info` includes `current_ckc_stage`, `action_taken` (name), `sequence_length`, `total_reward`.

---

## 8. DQN Agent

**File:** [RL_agent/rl/dqn_agent.py](../RL_agent/rl/dqn_agent.py).
**Weights:** [apps/models/rl_agent.pth](../apps/models/rl_agent.pth) (≡ `outputs/agent_best.pth`).

### 8.1 Q-Network architecture

```
State(13) → Linear(128) → ReLU → Dropout(0.1)
          → Linear(64)  → ReLU → Dropout(0.1)
          → Linear(5)   → Q-values
```

Simple MLP, no residual or LayerNorm.

### 8.2 Training components

- **Algorithm:** DQN with experience replay + target network, MSE TD loss.
- **Replay buffer:** `deque(maxlen=10_000)`; stores `Transition(state, action, reward, next_state, done)` namedtuples.
- **Target network:** hard copy of Q-net weights every `target_update_freq=100` training steps.
- **Optimizer:** `Adam(lr=1e-4)` by default (training script uses `1e-3` — see note below).
- **Discount γ:** 0.99.
- **Epsilon-greedy:** start 1.0, end 0.01, decay factor 0.995 per episode (`update_epsilon()`).
- **Batch size:** 64. Gradient clip `max_norm=1.0`.

> Note: [train.py:37](../RL_agent/train.py#L37) sets `learning_rate=0.001` while [dqn_agent.py:146](../RL_agent/rl/dqn_agent.py#L146) defaults to `1e-4`. Shipped `rl_agent.pth` was trained with the script's `1e-3`.

### 8.3 Inference-only loading

```python
from rl.dqn_agent import DQNAgent
from env.apt_env import APTEnvironment

agent = DQNAgent(
    state_dim=APTEnvironment.STATE_DIM,   # 13
    action_dim=5,
    hidden_dims=[128, 64],
    device='cpu',
)
agent.load('apps/models/rl_agent.pth')     # or RL_agent/outputs/agent_best.pth

# Inference: disable exploration
agent.epsilon = 0.0
action = agent.select_action(state_vec, training=False)   # 0..4
# Or for full Q-values:
q = agent.get_q_values(state_vec)
```

Checkpoint schema (written by `DQNAgent.save`):

```python
{
  'q_network_state_dict':      ...,
  'target_network_state_dict': ...,
  'optimizer_state_dict':      ...,
  'epsilon':        float,
  'steps_done':     int,
  'episodes_done':  int,
  'hyperparameters': {'state_dim': 13, 'action_dim': 5,
                      'gamma': 0.99, 'batch_size': 64,
                      'target_update_freq': 100}
}
```

### 8.4 Reported performance

From `AGENT_ARCHITECTURE.md` §7 (10k-episode scaling eval): accuracy 84.1%, precision 83.4%, recall 85.0%, F1 0.842, FPR 16.9%, **pre-detection rate 81.0%** (attacks stopped before S5).

---

## 9. MITRE → CKC Mapping

Full data is in [docs/mitre_to_ckc.json](mitre_to_ckc.json). It merges the logic of [preprocessing_dataset.ipynb](../apps/notebooks/preprocessing_dataset.ipynb) with the ID-only port in [RL_agent/synthetic/data_loader.py:97-133](../RL_agent/synthetic/data_loader.py#L97-L133).

### 9.1 Tactic ID → CKC

| Tactic | Name | CKC |
|:---|:---|:---:|
| TA0043 | Reconnaissance | S1 |
| TA0001 | Initial Access | S3 |
| TA0002 | Execution | S4 |
| TA0003 | Persistence | S5 |
| TA0004 | Privilege Escalation | S4 |
| TA0005 | Defense Evasion | S5 |
| TA0006 | Credential Access | S7 |
| TA0007 | Discovery | S7 |
| TA0008 | Lateral Movement | S5 |
| TA0009 | Collection | S7 |
| TA0011 | Command and Control | S6 |
| TA0040 | Impact | S7 |

### 9.2 Technique ID → CKC (overrides tactic)

30 techniques: T1595, T1595.002 → S1; T1190, T1059.*, T1068, T1548.003, T1106 → S4; T1078, T1105 → S3; T1136, T1098, T1021.*, T1222.002, T1036.005, T1562.001 → S5; T1083, T1057, T1082, T1049, T1033, T1040, T1005, T1565.001, T1485, T1070.004, T1070.006 → S7; T1110.001 → S1. Full table in [mitre_to_ckc.json](mitre_to_ckc.json).

### 9.3 Name-based mapping (lowercase; NOT ported to loader)

The preprocessing notebook also accepts name-form MITRE fields (`_source.rule.mitre.tactic` / `.technique`) and maps them via `TACTIC_NAME_MAPPING` and `TECHNIQUE_NAME_MAPPING` (exact match, then substring fallback in insertion order). These dicts are **not present** in `data_loader.py` — any backend that sees name-form MITRE values must re-implement them from the JSON.

### 9.4 Resolution rules

1. **Technique over tactic.** If both present, technique mapping wins.
2. **Earliest-phase wins.** Multiple labels on one row → pick min phase priority (e.g. `[S1, S4, S5] → S1`).
3. **Name match:** exact (lowercase) first, then substring fallback.
4. **`cyber_kill_chain_summary`** column = `min(phase_priority)` across the 4 derived columns.
5. **No match** → `None` → treat as Benign (stage 0).

### 9.5 Known gaps

- **TA0010** (Exfiltration) and **TA0042** (Resource Development) are not mapped — rows carrying only these tactics fall through to Benign. Likely bugs (should be S7 and S2 respectively).
- **S2 (Weaponization)** is never produced by any rule. Downstream models will never see this label from real data (which is why the Transformer's S2 class has zero loss weight).

---

## 10. End-to-End Data Flow Trace

Single alert traced through the production pipeline, based on an S4 Exploitation example from [RL_agent/inspect_alerts.py](../RL_agent/inspect_alerts.py).

```text
─── STEP 1: Raw Wazuh alert (JSON, from SIEM) ─────────────────────────
{
  "_source": {
    "@timestamp":  "2023-10-05T20:22:57.462Z",
    "rule": {
      "id": "5715", "level": 7, "firedtimes": 3,
      "description": "sshd: authentication success",
      "mitre_tactics":   ["TA0001"],          # Initial Access
      "mitre_techniques": ["T1078"],          # Valid Accounts
    },
    "decoder":  {"name": "sshd"},
    "location": "/var/log/auth.log",
    "agent":    {"name": "machine-1", "ip": "192.168.1.100"},
    "data":     {"srcip": "10.0.0.5", "srcuser": "root",
                 "command": "ssh root@target.internal"},
    "syscheck": null
  }
}

─── STEP 2: Parse raw fields ────────────────────────────────────────────
timestamp    = pd.Timestamp("2023-10-05 20:22:57.462")
machine_name = "machine-1"
src_user     = "root"
src_ip       = "10.0.0.5"
decoder      = "sshd"
location     = "/var/log/auth.log"
full_log     = "...sshd: authentication success..."
command      = "ssh root@target.internal"
firedtimes   = 3
path         = null        # no syscheck
md5_after    = null
sha256_after = null

─── STEP 3: SecBERT embedding (two fields, each → PCA-16) ────────────
tokenizer = AutoTokenizer.from_pretrained('jackaduma/SecBERT')
secbert   = AutoModel.from_pretrained('jackaduma/SecBERT')

# full_log → 768-dim via mean-pool(last_hidden_state, attention_mask)
log_emb_768 = mean_pool(secbert(tokenizer(full_log, max_len=128)))
log_emb_16  = log_pca.transform(log_emb_768.reshape(1, -1)).ravel()
# → log_secbert_emb_0..15

cmd_emb_768 = mean_pool(secbert(tokenizer(command, max_len=128)))
cmd_emb_16  = cmd_pca.transform(cmd_emb_768.reshape(1, -1)).ravel()
# → cmd_secbert_emb_0..15

─── STEP 4: Binary flags (19) ────────────────────────────────────────
decoder_auditd                         = 0    # decoder == 'sshd'
decoder_web-accesslog                  = 0
decoder_dpkg-decoder                   = 0
decoder_syscheck_deleted               = 0
decoder_syscheck_integrity_changed     = 0
location__var_log_audit_audit.log      = 0
location__var_log_apache2_access.log   = 0
location__var_log_auth.log             = 1    # matches auth.log
location_syscheck                      = 0
srcip_is_private                       = 1    # 10.0.0.5 is private
path_is_missing                        = 1    # no syscheck
path_is_sensitive                      = 0
path_is_temp                           = 0
has_md5                                = 0
has_sha256                             = 0
syscheck_added                         = 0
syscheck_deleted                       = 0
syscheck_modified                      = 0
cmd_is_missing                         = 0    # command present

─── STEP 5: Numerical (4) ────────────────────────────────────────────
firedtimes      = 3
firedtimes_log  = np.log1p(3)   ≈ 1.386
cmd_length      = len("ssh root@target.internal") = 24
path_depth      = 0             # no path

─── STEP 6: Standardize (StandardScaler fit on 55-col benign+mal) ────
x55_raw    = concat([log_16, cmd_16, 4_numerical, 19_binary],
                    ordered per training-column-layout)  # shape (55,)
x55_scaled = scaler.transform(x55_raw.reshape(1, -1))    # shape (1, 55)
                                                         # float32 is expected

─── STEP 7: AE inference ─────────────────────────────────────────────
ae_out = AutoencoderLoader.get_anomaly_score(x55_scaled)
# recon, mu(64), logvar(64), z(64) = model(x55_scaled)
# recon_error   = mean((x55_scaled - recon)**2, dim=1)   → e.g. 0.87
# center_dist   = sum((mu - model.center)**2, dim=1)     → e.g. 3.42
# anomaly_score = recon_error + 0.1 * center_dist        → e.g. 1.21

latent_64 = AutoencoderLoader.encode(x55_scaled)         # (1, 64), = mu

─── STEP 8: VAE inference ────────────────────────────────────────────
vae_out = VAELoader.get_malicious_probability(x55_scaled)
# recon, z_mean(32), z_log_var(32), z = model(x55_scaled)
# recon_error   = mean((x - recon)**2, dim=1)
# center_dist   = sum((z_mean - model.center)**2, dim=1)
# uncertainty   = mean(exp(z_log_var), dim=1)            → e.g. 1.04
# combined      = recon_error + 0.05 * center_dist
# malicious_prob = sigmoid(2*combined - 1)               → e.g. 0.78

─── STEP 9: Transformer inference (requires sequence context) ────────
# Requires the ENTIRE latent sequence for the current episode so far
seq_so_far   = features[:t+1]                    # (t+1, 55)
latent_seq   = ae.encode(seq_so_far)             # (t+1, 64)  — via fc_mu

# Pad/truncate to expected 64 latent dim (defensive)
if latent_seq.shape[1] < 64: pad to 64
if latent_seq.shape[1] > 64: truncate to 64

tf_out = TransformerLoader.predict_next_stage(latent_seq)
# Forward: input_proj(64→128) + sin pos enc + 4 encoder layers
#          → x[:, -1, :] pool → head(128→64→8) → softmax
# predicted_next_ckc_stage = argmax(probs)                → e.g. 4 (S4)
# prediction_confidence    = probs[argmax]                → e.g. 0.82

At step 0 the env bypasses this and returns (current_ckc, 0.5).

─── STEP 10: GNN inference (requires graph context) ──────────────────
# One-time: build graph on the batch / time-window containing this alert
graph = gnn_loader.build_graph(df_alerts_recent)    # nodes = alerts,
                                                    # edges = intra+user+IP+self
gnn_loader.run_inference(df_alerts_recent)           # logits → sigmoid → alert_risks

# Per-step: extract 3 RL state features for current machine + time
gnn_feats = gnn_loader.get_rl_state_features(
    target_machine='machine-1',
    current_time=pd.Timestamp("2023-10-05 20:22:57.462"),
    window_minutes=60,
)
# gnn_feats = {
#   'GNN_node_risk_current_host': 0.964,
#   'GNN_neighbor_risk':          0.993,
#   'risk_growth':                0.047,
# }

─── STEP 11: 13-dim state vector (clipped to obs-space bounds) ───────
state = np.array([
    1.21,      # [0]  anomaly_score           (AE)
    0.87,      # [1]  reconstruction_error    (AE)
    0.78,      # [2]  malicious_probability   (VAE)
    1.04,      # [3]  uncertainty             (VAE)
    4.0,       # [4]  predicted_next_ckc      (Transformer)
    0.82,      # [5]  prediction_confidence   (Transformer)
    4.0,       # [6]  current_ckc_stage       (ground truth for training;
               #      for live inference: MITRE mapping per §9)
    0.50,      # [7]  time_since_first (hrs)
    0.08,      # [8]  time_since_last  (min)
    5,         # [9]  sequence_length_so_far
    0.964,     # [10] gnn_node_risk
    0.993,     # [11] gnn_neighbor_risk
    0.047,     # [12] gnn_risk_growth
], dtype=np.float32)

─── STEP 12: DQN action selection ─────────────────────────────────────
agent.epsilon = 0.0                      # greedy at inference
action = agent.select_action(state, training=False)
# q_values = q_network(state) ≈ [-4.2, -1.1, 5.8, 7.3, 6.1]
# action   = argmax → 3 (Isolate Host)

Intervention (action ≥ 2) → episode ends.
```

### 10.1 Live-inference note on `current_ckc_stage` (state index 6)

During **training**, `current_ckc_stage` is read from the sequence's ground-truth CKC label. During **live inference**, there is no ground truth — the backend must derive it from the alert's MITRE fields using §9 rules. If no MITRE information is present, the value is `0` (Benign).

---

## 11. Discrepancies & Open Questions

Every item here is a real mismatch between the notebooks / architecture docs and the production loader code. **Trust the loader** (it's what runs), but fix the underlying divergence before backend inference ships.

### 11.1 Blocking — must-fix before inference

| # | Component | Issue | Recommended action |
|:---:|:---|:---|:---|
| 1 | **AE, VAE, GNN** | Feature column order in `data_loader.FEATURE_COLUMNS` differs from the notebook training order. `strict=True` load succeeds because shapes match, but columns are permuted relative to weights → silently broken predictions. | Re-order `TOP_25_FEATURES` in [data_loader.py:31](../RL_agent/synthetic/data_loader.py#L31) to match notebook ordering (`23 individuals → log_secbert → cmd_secbert`), OR persist a canonical column order alongside each checkpoint and reindex at inference. |
| 2 | **AE, VAE** | `StandardScaler` (fit on 55-col matrix) is not exported from any notebook. | Refit and `joblib.dump` it; backend must load and apply before feeding the AE/VAE. |
| 3 | **AE, VAE** | SecBERT PCA-16 reducers (one for log, one for cmd) are not exported — the `SecBERTEmbedder.pca` attributes are discarded after training. | Refit and pickle both PCA objects; also pin the SecBERT HF revision (`jackaduma/SecBERT`). |
| 4 | **AE, VAE** | SecBERT tokenizer + base model are not bundled. | Ship via HuggingFace cache or vendor a local snapshot. |
| 5 | **Transformer** | Loader uses post-LN ReLU; notebook trained **pre-LN GELU** (`norm_first=True, activation='gelu'`). `strict=True` still loads because parameter names are identical, but the forward graph is different → materially wrong predictions. | Fix [`transformer_loader.py:80-86`](../RL_agent/models/transformer_loader.py#L80-L86) to pass `activation='gelu', norm_first=True`. |
| 6 | **Transformer** | Loader's `input_projection` is `Linear → LayerNorm` only; notebook trained `Linear → LayerNorm → ReLU → Dropout(0.1)`. | Add the missing ReLU+Dropout to [`transformer_loader.py:71-74`](../RL_agent/models/transformer_loader.py#L71-L74). |
| 7 | **GNN** | Fallback threshold in [`gnn_loader.py:166`](../RL_agent/models/gnn_loader.py#L166) is `0.918` (Part-1) — the shipped Part-2 model needs **0.7743**. | Fix the fallback OR regenerate `gnn_propagation_metadata.pkl` with `threshold=0.7743`. |
| 8 | **GNN** | `gnn_propagation_metadata.pkl` is not in the repo. Without it, `feature_cols=[]` and `build_graph()` raises `ValueError("No feature columns found")` unless the caller supplies a feature matrix. | Re-run Part-2 of [GNN_Network_Propagation.ipynb](../apps/notebooks/GNN_Network_Propagation.ipynb) cell 8 with `features=selected_cols[:-1]`, `rule_level_included=False`, `model_params.in_ch=55`, `threshold=0.7743`. Ship the pickle. |
| 9 | **Weights filename mismatch** | Loaders expect `reg_ae_top25_features.pth`, `beta_vae_top25_features.pth`, `transformer_next_step_prediction_top25.pth`, `gnn_propagation_best_no_rule.pth`; repo ships `ae_model.pth`, `vae_model.pth`, `transformer_model.pth`, `gnn_model.pth`. | Either rename / symlink in `apps/models/`, or pass `model_path=` explicitly to each loader. |

### 11.2 Non-blocking but worth fixing

| # | Component | Issue | Note |
|:---:|:---|:---|:---|
| 10 | **AE** | Loader uses `ReLU`; notebook trained with `LeakyReLU(0.2)`. | Silent numerical mismatch at inference (eval-mode). Fix activations in [`autoencoder_loader.py:46-53,60-68`](../RL_agent/models/autoencoder_loader.py#L46-L68). |
| 11 | **AE** | Loader anomaly-score formula is `recon + 0.1·center_dist`; notebook training used `recon + β·KL` with β=1e-3 to compute the Youden-J threshold. | Different score scales — any threshold picked in the notebook is invalid for production scoring. Recalibrate. |
| 12 | **VAE** | Loader malicious-probability formula `sigmoid(2·(recon + 0.05·center_dist) − 1)` is a hand-written heuristic. The notebook's actual calibrator is in `probability_calibrators.pkl` (sklearn `LogisticRegression`). | Wire the calibrator into the loader, OR replace the heuristic with Platt/isotonic calibration on held-out validation. |
| 13 | **VAE** | `BetaVAE.center` is `nn.Parameter` (learnable) in notebook but registered as `buffer` in loader. | Functionally harmless at inference (value is loaded from checkpoint either way). |
| 14 | **VAE** | Variants `beta_vae_top25_features_32dim.pth` and `beta_vae_malicious_only_32dim.pth` are declared in `vae_loader.MODEL_VARIANTS` but not produced by any notebook in the repo. | Provenance unknown — either locate training script or drop them from the variants dict. |
| 15 | **Transformer** | `AGENT_ARCHITECTURE.md` says "Mean Pooling" in §4.3, but the actual code (both notebook and loader) uses `x[:, -1, :]` (last-token pooling). | Fix the architecture doc OR retrain with mean pooling. |
| 16 | **Transformer** | Training weights S2 and S6 are exactly 0 (classes never seen in data). Inference will rarely emit these stages. | Expected behavior; document it so downstream doesn't panic. |
| 17 | **DQN** | Training script uses `lr=1e-3`; `DQNAgent.__init__` default is `1e-4`. Shipped `rl_agent.pth` was trained with `1e-3`. | Loader doesn't re-train, so this is informational only. |
| 18 | **MITRE** | Name-based mappings (`TACTIC_NAME_MAPPING`, `TECHNIQUE_NAME_MAPPING`), substring fallback, technique-over-tactic precedence, and earliest-phase-wins reduction are NOT ported to `data_loader.py`. | Re-implement server-side from [mitre_to_ckc.json](mitre_to_ckc.json) for full parity with the preprocessing notebook. |
| 19 | **MITRE** | TA0010 (Exfiltration) and TA0042 (Resource Development) are unmapped — fall through to Benign. | Likely bugs; should map to S7 and S2 respectively. |
| 20 | **Dataset** | `apps/data/dataset.xlsx` is a re-exported Wazuh dump; the ~115k-row, MITRE-annotated file the notebooks were trained on is `combined_dataset_final.xlsx` (not in the repo). `RL_agent/data/combined_dataset_final_mal_sum.xlsx` is the malicious subset used for real-sequence construction. | Training labels were synthesized from MITRE fields per §9 rules — verify data provenance before retraining. |

---

## 12. Appendix — File map

```
apps/
├── data/
│   └── dataset.xlsx                      # re-exported Wazuh dump (not training set)
├── models/
│   ├── ae_model.pth                      # ≡ reg_ae_top25_features.pth
│   ├── vae_model.pth                     # ≡ beta_vae_top25_features.pth
│   ├── transformer_model.pth             # ≡ transformer_next_step_prediction_top25.pth
│   ├── gnn_model.pth                     # ≡ gnn_propagation_best_no_rule.pth
│   └── rl_agent.pth                      # ≡ outputs/agent_best.pth
└── notebooks/
    ├── preprocessing_dataset.ipynb        # MITRE→CKC labels, NO feature engineering
    ├── feature_selection.ipynb            # V1 (leaky, superseded)
    ├── feature_selection_final.ipynb      # V2 leakage-free 119-feat parquet + SecBERT
    ├── TP1_AE_FeatureSelection.ipynb      # AE training (produces the top-25 checkpoint)
    ├── TP2_VAE_FeatureSelection.ipynb     # VAE training + probability calibrator
    ├── TP2_MLA_TE.ipynb                   # Transformer training on AE latents
    └── GNN_Network_Propagation.ipynb      # GraphSAGE training + RL feature extraction

RL_agent/
├── AGENT_ARCHITECTURE.md                  # canonical design doc
├── ARCHITECTURE.md                        # diagrams
├── env/apt_env.py                         # 13-dim state, 5 actions, reward function
├── rl/dqn_agent.py                        # DQN, replay buffer, target net
├── models/
│   ├── autoencoder_loader.py              # RegularizedAE(55→64→55) + get_anomaly_score + encode
│   ├── vae_loader.py                      # BetaVAE(55→32→55) + get_malicious_probability
│   ├── transformer_loader.py              # TransformerCKCPredictor(64→128→8)
│   └── gnn_loader.py                      # APTPropagationGNN + graph construction + RL features
├── synthetic/
│   ├── data_loader.py                     # TOP_25_FEATURES, FEATURE_COLUMNS, MITRE dicts
│   └── real_data_loader.py                # variable-length real-sequence builder
├── train.py                               # DQN training (3000 episodes, mixes real+synthetic)
├── evaluate_real.py                       # 1000-episode evaluation with pre-detection stats
├── evaluate_scaling.py                    # 1K-10K scaling test
├── ablation_study.py                      # ablate each of the 4 models, retrain, compare
└── inspect_alerts.py                      # dump 5 benign + 5 malicious alerts

docs/
├── MODELS_REFERENCE.md                    # this document
└── mitre_to_ckc.json                      # full MITRE → CKC mapping
```
