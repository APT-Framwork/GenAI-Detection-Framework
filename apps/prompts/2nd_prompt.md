You're working in the STRIX monorepo. Your job this session is to plan the Wazuh integration so its log output matches the exact schema our ML models were trained on. Do NOT write production code yet — the deliverable is a setup plan + config files.

## Context
- The platform's ML models (AE, VAE, Transformer, GNN) were trained on a specific dataset in `apps/data/`.
- For inference on live data to work, Wazuh's parsed logs must land in the same column schema as that training dataset.
- Trained models are exported in `apps/models/`.

## Step 1 — Inspect the training dataset

Open the dataset in `apps/data/` and produce a complete column inventory:
- Every column name
- Data type (numeric, categorical, timestamp, IP, text, etc.)
- Example values (2-3 per column)
- Which columns are labels/targets vs. features
- Any columns that are clearly derived (e.g. aggregated counts, time deltas)

Save this as `docs/DATASET_SCHEMA.md`.

## Step 2 — Map Wazuh output to our schema

For each column in the training dataset, determine:
- Is this directly available in standard Wazuh alert/log output? (e.g. `agent.ip`, `rule.id`, `data.srcip`)
- Does it need to be extracted from Wazuh's JSON fields via a decoder or rule?
- Does it need to be engineered post-ingestion (e.g. rolling counts, session aggregations)?
- Does Wazuh simply not produce it, meaning we need another source or have to drop it?

Produce a mapping table: `training_column → wazuh_source → transformation_needed`.

Save this as `docs/WAZUH_MAPPING.md`.

## Step 3 — Propose the ingestion pipeline

Describe (don't implement) the pipeline:
- How Wazuh forwards alerts (Filebeat? direct API? webhook?)
- Where logs land (Kafka? Redis stream? direct HTTP to FastAPI?)
- Where schema transformation happens (a normalization service)
- Where aggregated/engineered features are computed (sliding windows, session state)
- Final shape that gets pushed into the inference services

Include a simple ASCII diagram of the flow. Save as `docs/INGESTION_PIPELINE.md`.

## Step 4 — Wazuh config drafts

Draft the config snippets that would be needed:
- Custom decoder(s) if any columns need extraction from raw log messages
- Custom rules if we need to tag events in specific ways
- Output/forwarder config

Put these in `config/wazuh/` as draft files (clearly marked DRAFT at the top). Do not deploy anything.

## Constraints
- Do NOT modify the dataset or notebooks.
- Do NOT write the inference backend yet — that's a later session.
- Ask me before making any assumption about infrastructure (cloud, on-prem, containers).