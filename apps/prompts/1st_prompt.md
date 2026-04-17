You're working in the STRIX monorepo. Your job this session is to build deep, accurate understanding of every ML model in the platform by reading the notebooks one by one. Do NOT write any implementation code. The deliverable is a single markdown document.

## Where things live
- Notebooks: `apps/notebooks/`
- Dataset: `apps/data/`
- Exported trained models: `apps/models/`

## Notebooks to walk through (in this order)

1. **AE (Autoencoder)** — read all three, they build on each other:
   - `TP1_AE_FeatureSelection.ipynb`
   - `feature_selection.ipynb`
   - `feature_selection_final.ipynb`

2. **VAE (Variational Autoencoder)**:
   - `TP2_VAE_FeatureSelection.ipynb`

3. **Transformer**:
   - `TP2_MLA_TE.ipynb` — focus especially on the feature selection section

4. **GNN**:
   - `GNN_Network_Propagation.ipynb`

5. **Preprocessing + MITRE → CKC mapping**:
   - `preprocessing_dataset.ipynb`

## For EACH notebook, extract and document

- **Purpose** — what problem this model solves in the platform
- **Input features used** — the exact final list of columns fed into the model
- **Feature engineering** — for each feature, note whether it was:
  - taken directly from the raw dataset (and from which column),
  - engineered/derived (and the exact transformation, formula, or logic),
  - encoded (one-hot, label, embedding, scaling, etc.)
- **Preprocessing pipeline** — the order of transformations, any fitted objects (scalers, encoders) that must be reused at inference time
- **Model architecture** — layers, sizes, activations, loss, any hyperparameters that matter for inference
- **Output** — what exactly the model returns (shape, meaning, value range). Be explicit about things like:
  - AE: anomaly score, anomaly rate
  - VAE: probability / reconstruction prob
  - GNN: per-node risk, risk growth
  - Transformer: next CKC step prediction
- **Exported artifact** — check `apps/models/` and identify which file corresponds to this model (weights format, filename, whether a scaler/encoder was also exported)
- **Inference requirements** — what a backend service would need to do to load this model and run inference on new Wazuh logs

## Special deliverable: MITRE → CKC mapping

From `preprocessing_dataset.ipynb`, extract the full mapping from MITRE ATT&CK technique/tactic columns to the seven Cyber Kill Chain stages. Produce this as a clean lookup table (JSON or a markdown table). This mapping will be reused across the backend.

## Final output

Write everything into `docs/MODELS_REFERENCE.md` at the repo root. Structure it with one section per model + a final section for the MITRE→CKC mapping. Be precise — the next session will use this document to plan backend implementation, so ambiguity now means bugs later.

Do not modify any notebooks. Do not write any backend/frontend code. Read-only + one markdown file out.