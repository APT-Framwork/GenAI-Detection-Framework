# Prompt 1 — Full AI Brain Walkthrough

You're working in the STRIX monorepo. Your job this session is to build deep, accurate understanding of the entire ML/RL detection system by reading every notebook AND every file in the RL agent project. Do NOT write any implementation code. The deliverable is a single markdown document.

## Mandatory prerequisite reading (READ THESE FIRST, BEFORE ANYTHING ELSE)

These two documents describe the system end-to-end and define the ground-truth architecture. Every decision you make later must be consistent with them:

1. `apps/models/rl_agent/AGENT_ARCHITECTURE.md` — complete data journey, all 4 detection models, the RL agent, reward function, training pipeline
2. `apps/models/rl_agent/ARCHITECTURE.md` — diagrams of model interactions, state construction, training loop

After reading these, you should understand:
- Wazuh alerts → 55-dim feature vector (16 log SecBERT PCA + 16 cmd SecBERT PCA + 4 numerical + 19 binary)
- AE, VAE, Transformer, GNN all consume the 55-dim vector (except Transformer which consumes AE's 64-dim latent)
- Their outputs fuse into a 13-dim state vector
- A DQN agent consumes the 13-dim state and outputs 1 of 5 actions
- The system processes **sequences** of alerts as episodes, not individual alerts in isolation

## Where things live

- Notebooks: `apps/notebooks/`
- Dataset: `apps/data/` (expect `combined_dataset_final.xlsx`, ~115k alerts)
- Exported model weights: `apps/models/`
- Full RL agent codebase: `apps/models/rl_agent/` (this is actual runnable code — read it, don't just skim)

## Part A — Walk through the notebooks (in this order)

1. **Preprocessing + MITRE → CKC mapping** (do this FIRST, everything downstream depends on it):
   - `preprocessing_dataset.ipynb`

2. **AE (Regularized Autoencoder)** — all three, they build on each other:
   - `TP1_AE_FeatureSelection.ipynb`
   - `feature_selection.ipynb`
   - `feature_selection_final.ipynb`

3. **VAE (Beta-VAE)**:
   - `TP2_VAE_FeatureSelection.ipynb`

4. **Transformer (CKC next-stage predictor)**:
   - `TP2_MLA_TE.ipynb` — focus especially on the feature selection section

5. **GNN (GraphSAGE propagation detector)**:
   - `GNN_Network_Propagation.ipynb`

For EACH notebook, extract and document:
- **Purpose** — what problem this model solves in the platform
- **Input features** — the exact final list of columns fed into the model. Reconcile the notebook's final feature list against the 55-dim schema described in AGENT_ARCHITECTURE.md. Flag any discrepancies.
- **Feature engineering** — for each feature, note whether it was:
  - taken directly from the raw dataset (and from which raw column),
  - engineered/derived (exact transformation, formula, or logic),
  - text-embedded (which SecBERT variant, what PCA dimension),
  - binary-flagged (the exact condition that sets it to 1),
  - encoded (one-hot, label, scaling — name the fitted object)
- **Preprocessing pipeline** — order of transformations, all fitted objects (scalers, encoders, PCA, SecBERT tokenizer) that must be reused at inference time. Check `apps/models/` for exported versions of these objects.
- **Model architecture** — layers, sizes, activations, loss, any hyperparameters that matter for inference. Cross-check against the definitions in `apps/models/rl_agent/models/*_loader.py`.
- **Output** — exact shape, meaning, value range of what the model returns
- **Exported artifact** — filename in `apps/models/`, weight format (.pth/.pkl), whether a scaler/encoder was exported alongside

## Part B — Walk through the RL agent codebase

Read every Python file under `apps/models/rl_agent/`. For each of these, summarize what it does and how it fits into the system:

- `env/apt_env.py` — the RL environment. Document:
  - Exact 13-dim state vector construction (which output from which model → which index)
  - The 5 actions and what they mean
  - The full reward function (all branches, all CKC-stage-dependent values)
  - Episode termination conditions
  - How `reset()` and `step()` work
- `rl/dqn_agent.py` — the DQN agent. Document:
  - Q-network architecture
  - Replay buffer mechanics
  - Target network update schedule
  - Epsilon-greedy schedule
  - How to load `outputs/agent_best.pth` for inference
- `models/autoencoder_loader.py`, `models/vae_loader.py`, `models/transformer_loader.py`, `models/gnn_loader.py` — the inference wrappers. For each:
  - Exact model class (layer sizes, activations)
  - `load_model()` signature and what it expects
  - `predict()` / inference method signature, input shape, output shape
  - Which weight file in `apps/models/` it loads
- `synthetic/data_loader.py` and `synthetic/real_data_loader.py` — data loading and sequence construction. Document:
  - The canonical list of 55 feature column names (this is the ground-truth schema)
  - How real sequences are built from the dataset (grouping, time-ordering, attack vs benign)
  - Sequence length ranges (5–30 for attacks, 5–15 for benign)
- `train.py`, `evaluate_real.py`, `evaluate_scaling.py`, `ablation_study.py`, `inspect_alerts.py` — briefly describe each

## Part C — MITRE → CKC mapping (critical deliverable)

From `preprocessing_dataset.ipynb`, extract the full mapping from MITRE ATT&CK technique/tactic values to the 8 CKC stages (Benign/S0, S1 Reconnaissance, S2 Weaponization, S3 Delivery, S4 Exploitation, S5 Installation, S6 C2, S7 Actions on Objectives).

Produce this as a clean lookup table (both a JSON file AND a markdown table). This mapping will be reused across the backend.

## Part D — End-to-end data flow trace

Write a concrete worked example. Take ONE real alert from the dataset and trace it through the entire pipeline:

```
Raw Wazuh alert (JSON)
  → parsed fields (list them)
  → SecBERT embeddings (note the two fields embedded, their PCA reduction)
  → binary flag computation (show a few)
  → numerical feature computation
  → final 55-dim vector (give a shape/example)
  → AE inference → anomaly_score, recon_error, 64-dim latent
  → VAE inference → malicious_prob, uncertainty
  → Transformer inference (needs sequence context — explain how)
  → GNN inference (needs graph context — explain how)
  → 13-dim state vector (show which index gets which value)
  → DQN action selection
```

This trace is the single most important deliverable — everything downstream of this session will use it as the contract for the inference pipeline.

## Final output

Write everything into `docs/MODELS_REFERENCE.md` at the repo root. Structure:

1. System overview (1-2 paragraphs, reference the two architecture MDs)
2. Canonical 55-dim feature schema (the ground-truth list, with descriptions)
3. One section per model (AE, VAE, Transformer, GNN) — Part A + Part B merged
4. RL environment section (state construction, actions, reward)
5. DQN agent section (architecture, inference-only loading)
6. MITRE → CKC mapping (table + reference to the JSON file you saved)
7. End-to-end data flow trace (Part D)
8. Discrepancies / open questions — anything in the notebooks that contradicts `AGENT_ARCHITECTURE.md` or the loader code

Also save the MITRE→CKC mapping as `docs/mitre_to_ckc.json`.

Be precise — the next session will use this document to plan backend implementation, so ambiguity now means bugs later. When two sources conflict (notebook vs loader vs architecture doc), flag it explicitly and trust the loader code since that's what actually runs.

Do not modify any notebooks or the rl_agent code. Read-only + two output files (`docs/MODELS_REFERENCE.md`, `docs/mitre_to_ckc.json`).