# WAZUH_MAPPING — Training Column → Wazuh Source → Transformation

> **Purpose:** For every column present in the training dataset (`apps/data/dataset.xlsx`), specify how the same value is obtained from a live Wazuh alert stream, and what transformation is required before the inference service consumes it.
>
> Read this alongside [DATASET_SCHEMA.md](./DATASET_SCHEMA.md).

---

## 0. Key insight — the training data IS Wazuh

The training frame is a near-raw dump of the Wazuh `wazuh-alerts-4.x-*` Elasticsearch/OpenSearch index. Every column prefixed `_source.*` is a field of the JSON alert document that Wazuh already emits. **The platform does not need to invent most fields** — it needs to:

1. **Strip the Elasticsearch envelope** (`_index`, `_id`, `_score`, `_version`) from incoming docs.
2. **Flatten** the nested JSON (`_source.rule.mitre.technique` stays a single column) into the same dotted-key layout the training frame uses.
3. **Drop leaky columns** before the model call (same list as training).
4. **Run the `FeatureEngineerNoLeakage` transformer** on the flattened row.

The mapping table below annotates whether each source field is directly available, needs decoder/rule help, needs post-ingestion engineering, or has no Wazuh equivalent.

---

## 1. Transformation categories used in the table below

| Tag | Meaning |
|---|---|
| `DIRECT` | Field is present verbatim on every Wazuh alert JSON. No decoder work. |
| `DECODER_DEPENDENT` | Field only materializes if the matching Wazuh decoder fires for that log source (e.g. `_source.data.audit.*` only for auditd events, `_source.syscheck.*` only for FIM events, `_source.data.sca.*` only for SCA scans). Already true in training data. |
| `RULE_DEPENDENT` | Field only populated when a rule referencing that compliance/MITRE tag fires (e.g. `_source.rule.mitre.*` only when the fired rule has `<mitre>` children). |
| `CUSTOM_DECODER` | Not produced by stock Wazuh — would need a custom decoder to extract (none needed for this dataset). |
| `ENGINEERED` | Computed post-ingestion from one or more direct fields (sliding windows, length, regex flag, etc.). See §4. |
| `LABEL` | Not a feature; produced by preprocessing. Live inference outputs this; does not ingest it. |
| `DROP` | Dead / leaky column. Strip before model call. |

---

## 2. Mapping table — core / envelope / agent / manager

| Training column | Wazuh source | Transformation | Notes |
|---|---|---|---|
| `_index` | ES index name | `DROP` | Envelope — forwarder-level metadata. |
| `_id` | ES document `_id` | `DROP` | Replace with our own event-id during normalization. |
| `_version` | ES document `_version` | `DROP` | Envelope. |
| `_score` | ES search score | `DROP` | Envelope. |
| `_source.@timestamp` | `@timestamp` | `DIRECT` | Training used a Kibana-export string (`"Dec 31, 2023 @ 12:59:55.107"`). Live Wazuh emits ISO-8601 (`2024-01-15T13:22:14.923Z`). Normalizer must parse both with `pd.to_datetime(..., errors='coerce')`. |
| `_source.timestamp` | `timestamp` | `DIRECT` | Duplicate of `@timestamp` in Wazuh — keep for parity. |
| `_source.id` | `id` | `DIRECT` | Wazuh alert ID (e.g. `1704027595.258`). |
| `_source.location` | `location` | `DIRECT` | Path / logical source of the log. Drives one-hot encoding. |
| `_source.full_log` | `full_log` | `DIRECT` | Raw log line. Consumed by SecBERT. |
| `_source.previous_output` | `previous_output` | `DIRECT` | Present for PAM / sudo correlation rules. |
| `_source.previous_log` | `previous_log` | `DIRECT` | Same. |
| `_source.input.type` | `input.type` | `DIRECT` | Always `"log"` in this dataset — effectively constant. |
| `_source.agent.ip` | `agent.ip` | `DIRECT` | |
| `_source.agent.name` | `agent.name` | `DIRECT` | Model saw only 5 values — do NOT one-hot in production (would fail to generalize). |
| `_source.agent.id` | `agent.id` | `DIRECT` | Same. Used as grouping key in GNN and for session aggregation. |
| `_source.manager.name` | `manager.name` | `DIRECT` | Constant in training (`ubuntu`). |

---

## 3. Mapping table — predecoder / decoder / rule

| Training column | Wazuh source | Transformation | Notes |
|---|---|---|---|
| `_source.predecoder.hostname` | `predecoder.hostname` | `DIRECT` | |
| `_source.predecoder.program_name` | `predecoder.program_name` | `DIRECT` | |
| `_source.predecoder.timestamp` | `predecoder.timestamp` | `DIRECT` | |
| `_source.decoder.name` | `decoder.name` | `DIRECT` | Key feature — drives `decoder_*` one-hots. |
| `_source.decoder.parent` | `decoder.parent` | `DIRECT` | |
| `_source.decoder.ftscomment` | `decoder.ftscomment` | `DIRECT` | |
| `_source.decoder` | `decoder` (object, rare) | `DIRECT` | Appears as a JSON literal in a few rows — keep as string. |
| `_source.rule.id` | `rule.id` | `DIRECT` | |
| `_source.rule.level` | `rule.level` | `DIRECT` → then `DROP` | Leaky. Strip at inference time. |
| `_source.rule.firedtimes` | `rule.firedtimes` | `DIRECT` | Coerce to numeric (stored as string in Excel). |
| `_source.rule.description` | `rule.description` | `DIRECT` → then `DROP` | Leaky (attack keywords). |
| `_source.rule.mail` | `rule.mail` | `DIRECT` | Bool string `"True"/"False"`. |
| `_source.rule.groups` | `rule.groups` | `DIRECT` | Serialized list in training (`'["audit","audit_command"]'`). Live Wazuh emits a native array — normalizer should JSON-stringify OR adapt feature engineering to accept arrays. |
| `_source.rule.gdpr` / `pci_dss` / `hipaa` / `tsc` / `nist_800_53` / `gpg13` / `cis` / `cis_csc_v7` / `cis_csc_v8` / `mitre_mitigations` / `nist_sp_800-53` / `soc_2` / `info` / `frequency` | `rule.<compliance_tag>` | `DIRECT` (`RULE_DEPENDENT`) | Wazuh emits whichever compliance tags the fired rule declares. Currently unused in engineered feature set — keep for future. |
| `_source.rule.mitre.technique` / `.tactic` / `.id` | `rule.mitre.*` | `DIRECT` → then `DROP` | Leaky. |
| `_source.rule.mitre_tactics` / `_source.rule.mitre_techniques` | `rule.mitre_tactics` / `_techniques` | `DIRECT` → then `DROP` | Leaky (only populated for malicious-labeled rows — they *define* the label). |

---

## 4. Mapping table — data.audit.* (auditd decoder)

All `_source.data.audit.*` fields are produced by Wazuh's built-in `auditd` decoder when `<localfile>` consumes `/var/log/audit/audit.log`. They are `DECODER_DEPENDENT` — present only for auditd events.

| Training column | Wazuh source | Transformation | Notes |
|---|---|---|---|
| `_source.data.audit.syscall` | `data.audit.syscall` | `DIRECT` | |
| `_source.data.audit.type` | `data.audit.type` | `DIRECT` | e.g. `SYSCALL`, `EXECVE`, `PATH`. |
| `_source.data.audit.exe` | `data.audit.exe` | `DIRECT` | Executable path. |
| `_source.data.audit.command` | `data.audit.command` | `DIRECT` | Short command name (e.g. `mkdir`). Distinct from `_source.data.command`. |
| `_source.data.audit.uid` / `euid` / `suid` / `fsuid` / `auid` / `gid` / `egid` / `sgid` / `fsgid` | `data.audit.*` | `DIRECT` | Numeric strings. |
| `_source.data.audit.pid` / `ppid` | `data.audit.pid` / `ppid` | `DIRECT` | |
| `_source.data.audit.session` / `tty` / `arch` / `cwd` / `success` / `exit` / `key` / `res` / `list` / `id` | `data.audit.*` | `DIRECT` | |
| `_source.data.audit.execve.a0..a7` | `data.audit.execve.a0..a7` | `DIRECT` | Command-line arg captured by EXECVE record. |
| `_source.data.audit.file.inode` / `.mode` / `.name` | `data.audit.file.*` | `DIRECT` | |

**No custom decoder required** — native Wazuh `auditd.xml` decoder already populates all of these. Ensure the agent config has:

```xml
<localfile>
  <log_format>audit</log_format>
  <location>/var/log/audit/audit.log</location>
</localfile>
```

See [config/wazuh/ossec-agent-localfiles.xml.draft](../config/wazuh/ossec-agent-localfiles.xml.draft).

---

## 5. Mapping table — data.sca.* (SCA / CIS benchmark scanner)

All `_source.data.sca.*` fields are `DECODER_DEPENDENT` on the stock `sca` decoder and fire only when Wazuh's SCA module runs a policy.

| Training column | Wazuh source | Transformation | Notes |
|---|---|---|---|
| `_source.data.sca.type` | `data.sca.type` | `DIRECT` | `summary`, `check`, `policy`, … |
| `_source.data.sca.scan_id` / `policy_id` / `policy` | `data.sca.*` | `DIRECT` | |
| `_source.data.sca.score` / `total_checks` / `passed` / `failed` / `invalid` | `data.sca.*` | `DIRECT` | Numeric strings. |
| `_source.data.sca.check.id` / `.title` / `.description` / `.rationale` / `.remediation` / `.result` / `.command` / `.directory` / `.file` / `.reason` / `.references` / `.previous_result` | `data.sca.check.*` | `DIRECT` | |
| `_source.data.sca.check.compliance.<framework>` (15 sub-keys: `cis`, `pci_dss_*`, `nist_*`, `hipaa`, `mitre_*`, `soc_2`, etc.) | `data.sca.check.compliance.*` | `DIRECT` | Lists — JSON-serialize to match training dtype. |
| `_source.data.sca.file` / `.description` | `data.sca.*` | `DIRECT` | |

No SCA fields are consumed by `FeatureEngineerNoLeakage` in the current code — they pass through untouched and are discarded at `fillna(0)` time. Keep the columns; skip them at feature-engineering time.

---

## 6. Mapping table — data.* (non-audit, non-SCA)

| Training column | Wazuh source / decoder | Transformation | Notes |
|---|---|---|---|
| `_source.data.srcip` | `data.srcip` | `DIRECT` | `web-accesslog` / `pam` / `sshd` decoders populate this. Feeds `srcip_is_private` via `ipaddress.ip_address(...).is_private`. |
| `_source.data.srcport` | `data.srcport` | `DIRECT` | Same. Numeric string. |
| `_source.data.srcuser` / `dstuser` | `data.srcuser` / `dstuser` | `DIRECT` | PAM/sudo decoders. |
| `_source.data.tty` / `pwd` / `command` / `shell` / `home` / `logname` / `uid` / `gid` / `euid` / `id` | `data.*` | `DIRECT` | `sudo`/`pam` decoder outputs. `_source.data.command` is the primary text input to SecBERT; do NOT confuse with `_source.data.audit.command` (short name). |
| `_source.data.package` / `arch` / `version` / `dpkg_status` | `data.*` | `DIRECT` | `dpkg-decoder` output. |
| `_source.data.extra_data` / `file` / `title` / `level` | `data.*` | `DIRECT` | Various rule-specific decoders. |
| `_source.data.status` | `data.status` | `DIRECT` | 100% null in training — skip. |
| `_source.data.protocol` | `data.protocol` | `DIRECT` | `web-accesslog` (HTTP method `GET`/`POST`). |
| `_source.data.url` | `data.url` | `DIRECT` | `web-accesslog`. Source for full-URL based features if ever added. |

---

## 7. Mapping table — syscheck.* (File Integrity Monitoring)

`DECODER_DEPENDENT` on Wazuh's built-in syscheck decoder; only populated for FIM events.

| Training column | Wazuh source | Transformation | Notes |
|---|---|---|---|
| `_source.syscheck.path` | `syscheck.path` | `DIRECT` | Drives all `path_*` engineered features. |
| `_source.syscheck.event` | `syscheck.event` | `DIRECT` | Values: `added`, `modified`, `deleted`. Drives `syscheck_{added,modified,deleted}` flags. |
| `_source.syscheck.changed_attributes` | `syscheck.changed_attributes` | `DIRECT` | Serialized list in training. Drives `changed_{size,mtime,md5,sha1,sha256,permission,uid,gid,inode}` flags. |
| `_source.syscheck.md5_after` / `md5_before` / `sha1_after` / `sha1_before` / `sha256_after` / `sha256_before` | `syscheck.*` | `DIRECT` | Drives `has_md5`, `has_sha256` via non-null indicator. |
| `_source.syscheck.size_after` / `size_before` / `mtime_after` / `mtime_before` / `inode_after` / `inode_before` / `mode` / `perm_after` / `perm_before` / `uid_after` / `gid_after` / `uname_after` / `gname_after` | `syscheck.*` | `DIRECT` | Currently unused in engineered features — available for future use. |

Enable syscheck in agent config:

```xml
<syscheck>
  <directories check_all="yes" realtime="yes">/etc,/usr/bin,/usr/sbin,/bin,/sbin</directories>
  <directories check_all="yes" whodata="yes">/var/www</directories>
</syscheck>
```

---

## 8. Engineered features — live computation required

These are **not** Wazuh fields. They are computed per-alert by `FeatureEngineerNoLeakage.transform()` (`apps/notebooks/feature_selection_final.ipynb`, cell 7). The normalization service must reproduce this exact logic.

| Engineered feature(s) | Source column | Transformation |
|---|---|---|
| `hour_of_day`, `day_of_week`, `is_weekend`, `is_night`, `is_business_hours` | `_source.@timestamp` | `pd.to_datetime` then extract `.hour`, `.dayofweek`, and boolean windows (`22-06` night, `9-17` business, `5-6` weekend). |
| `firedtimes`, `firedtimes_log` | `_source.rule.firedtimes` | `pd.to_numeric(errors='coerce').fillna(0)` → `np.log1p`. |
| `ip_is_private`, `ip_is_missing` | `_source.agent.ip` | `ipaddress.ip_address(...).is_private` — returns `1`/`0`/`-1` for private/public/missing. |
| `srcip_is_private`, `srcip_is_missing` | `_source.data.srcip` | Same. |
| `path_depth`, `path_is_sensitive`, `path_is_hidden`, `path_is_suspicious_ext`, `path_is_temp`, `path_is_missing` | `_source.syscheck.path` | Count `/`, substring checks against `{/etc, /var/log, /home, /root, /bin, /sbin, /usr/bin, /tmp, /var/www}`, suffix checks `{.sh, .py, .php, .exe, .bin, .so, .conf, .key, .pem}`, `/.` for hidden, `/tmp` or `/temp` for temp. |
| `cmd_sudo_usage`, `cmd_chmod_usage`, `cmd_wget_curl`, `cmd_nc_netcat`, `cmd_base64`, `cmd_eval_exec`, `cmd_pipe_redirect`, `cmd_hidden_file`, `cmd_cron_at`, `cmd_ssh_scp`, `cmd_python_perl`, `cmd_kill_pkill`, `cmd_rm_delete`, `cmd_cat_less`, `cmd_grep_find`, `cmd_env_export`, `cmd_passwd_shadow`, `cmd_iptables_firewall`, `cmd_dd_disk`, `cmd_tar_zip` | `_source.data.command` | Per-pattern case-insensitive regex match → `1`/`0`. Regex table lifted verbatim from notebook. |
| `cmd_length`, `cmd_has_args`, `cmd_is_missing` | `_source.data.command` | `len(str(x))`, `' -' in x`, `x is null`. |
| `has_md5`, `has_sha256` | `_source.syscheck.md5_after`, `_source.syscheck.sha256_after` | `notna().astype(int)`. |
| `syscheck_added`, `syscheck_modified`, `syscheck_deleted` | `_source.syscheck.event` | Substring match `added`/`modified`/`deleted`. |
| `changed_{size,mtime,md5,sha1,sha256,permission,uid,gid,inode}` | `_source.syscheck.changed_attributes` | Substring check after `fillna('').lower()`. |
| `srcport`, `is_privileged_port`, `is_high_port` | `_source.data.srcport` | Numeric coerce; `< 1024` and `> 49152`. |
| `decoder_<top15>` (one-hot) | `_source.decoder.name` | Equality to pre-frozen top-15 list (§3 in DATASET_SCHEMA). |
| `location_<top15>` (one-hot) | `_source.location` | Equality to pre-frozen top-15 list. |
| `cmd_secbert_emb_0..15` | `_source.data.command` | `SecBERTEmbedder(model_name='jackaduma/SecBERT').embed_texts(...)` → 768-dim → PCA-16. |
| `log_secbert_emb_0..15` | `_source.full_log` | Same SecBERT path. |

> **Critical:** the PCA used to reduce SecBERT from 768 → 16 must be **the same PCA fitted at training time**. The normalization service must load a persisted `PCA` artifact; re-fitting on live traffic drifts the embedding space.
> → Open question for the team: is the SecBERT PCA artifact persisted? It's not in `apps/models/` (only the four `.pth` files are). We will need either the pickled PCA / scaler, or to re-run `feature_selection_final.ipynb` to export them.

---

## 9. Session / temporal aggregates — optional future work

None of the current `FeatureEngineerNoLeakage` features are rolling windows. The GNN model (`gnn_model.pth`) likely operates on per-host attack graphs built by `GNN_Network_Propagation.ipynb` — that notebook should be audited to determine whether it requires the normalization service to maintain session state (sliding counts, graph edges between consecutive alerts per agent). **Flagging as an unknown** — pending model-architecture review in the next session.

Potential aggregates we may need eventually:

- Per-agent alert rate (alerts/sec over N-minute window)
- Per-agent decoder diversity (distinct decoders in window)
- Consecutive-alert deltas (gap since previous alert from same agent)
- Alert-graph edges for GNN inference

These would live in a **stream-processing layer** (Flink / Kafka Streams / a Redis-backed stateful service) between Wazuh and the inference API — addressed in [INGESTION_PIPELINE.md](./INGESTION_PIPELINE.md) once infrastructure assumptions are confirmed.

---

## 10. Summary of per-column transformation counts

| Transformation | Column count | Examples |
|---|---|---|
| `DIRECT` (pass-through from Wazuh) | ~155 | all `_source.*` features kept as-is |
| `DROP` (leaky or envelope) | 11 | `_index`, `_id`, `_score`, `_version`, `rule.level`, `rule.description`, `rule.mitre*` (6 forms) |
| `LABEL` | 6 | `malicious`, `cyber_kill_chain_*` |
| `ENGINEERED` | 11 groups → ~80 derived columns | see §8 |
| `CUSTOM_DECODER` | 0 | None needed — native Wazuh decoders cover the dataset |

**Bottom line:** no custom decoder is required to match the training schema; the entire translation is (a) flatten JSON, (b) drop 11 columns, (c) run the engineered-feature transform.
