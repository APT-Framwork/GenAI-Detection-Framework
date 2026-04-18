# DATASET_SCHEMA — Training Data Column Inventory

> **Source file:** `apps/data/dataset.xlsx` (single sheet `Sheet1`)
> **Shape:** 115,726 rows × 176 columns
> **Origin:** "Linux-APT-Dataset-2024" — alerts exported from an Elasticsearch/OpenSearch `wazuh-alerts-4.x-*` index (raw Wazuh alerts wrapped in the standard ES `_source.*` envelope; see `apps/notebooks/preprocessing_dataset.ipynb` for the build pipeline).
> **Coverage:** 5 Wazuh agents (`Machine-1-New` … `Machine-5-New`), 1 manager (`ubuntu`), subnet `192.168.217.0/24`, time range Oct 2023 – Jan 2024.

---

## 1. At-a-glance

| Aspect | Value |
|---|---|
| Total rows | 115,726 |
| Total columns | 176 |
| Primary label | `malicious` ∈ {0, 1} — 90,308 benign / 25,418 malicious (~22% positive) |
| Secondary label | `cyber_kill_chain_tactic` ∈ {S1, S3, S4, S5, S7}, 91,178 nulls (only defined for malicious rows with valid MITRE mapping) |
| Completely empty | `cyber_kill_chain_id` (100% null — drop) |
| Row uniqueness | `_id` is unique per row (Elasticsearch `_id`) |

### CKC label distribution (non-null rows)

| Stage code | Count | Approx. meaning (from `preprocessing_dataset.ipynb` MITRE→CKC mapping) |
|---|---|---|
| S4 | 16,556 | Installation / Exploitation |
| S3 | 4,291  | Delivery |
| S7 | 1,777  | Actions on Objectives / C2 |
| S5 | 1,281  | Command & Control |
| S1 | 643    | Reconnaissance |

### How labels were created (crucial for live-inference mapping)

`malicious` and the `cyber_kill_chain_*` columns are **not native Wazuh fields**. They were synthesized at preprocessing time:

- `malicious = 1` when the alert has non-null `_source.rule.mitre_techniques` **or** `_source.rule.mitre_tactics` (see `preprocessing_dataset.ipynb` cell 52, 54).
- `cyber_kill_chain_tactic` is a mapping of MITRE tactic names → 5-stage CKC bucket (`preprocessing_dataset.ipynb` cell 58–62).

Live inference **cannot** use these as features (they are the targets) — Wazuh does, however, populate `rule.mitre_*` natively whenever a fired rule has `<mitre>` metadata.

---

## 2. Columns that look like sensors but are **excluded** in training (data-leakage guard)

The notebook `apps/notebooks/feature_selection_final.ipynb` (class `FeatureEngineerNoLeakage`, cell 7) deliberately drops these from the feature matrix:

| Column | Why excluded |
|---|---|
| `_source.rule.level` | Wazuh severity is an indirect label (high-severity ≈ malicious) |
| `_source.rule.description` | Contains attack keywords — leaks the target |
| `_source.rule.mitre_tactics` | Present only on malicious rows — defines the label |
| `_source.rule.mitre_techniques` | Same |
| `_source.rule.mitre.tactic` / `.technique` / `.id` | Same (nested form) |

Keep them in the schema for completeness; the **normalization service for live data must also strip them before calling the model.**

---

## 3. Engineered features actually consumed by the models

Models `ae_model.pth`, `vae_model.pth`, `transformer_model.pth`, `gnn_model.pth` (in `apps/models/`) were trained on the output of `FeatureEngineerNoLeakage.transform()`. That output is **NOT** the raw 176-column frame — it is ~70–90 engineered features grouped as follows:

| Group | Engineered features | Source column(s) |
|---|---|---|
| Temporal | `hour_of_day`, `day_of_week`, `is_weekend`, `is_night`, `is_business_hours` | `_source.@timestamp` |
| Rule-frequency | `firedtimes`, `firedtimes_log` | `_source.rule.firedtimes` |
| Agent IP | `ip_is_private`, `ip_is_missing` | `_source.agent.ip` |
| Source IP | `srcip_is_private`, `srcip_is_missing` | `_source.data.srcip` |
| Path | `path_depth`, `path_is_sensitive`, `path_is_hidden`, `path_is_suspicious_ext`, `path_is_temp`, `path_is_missing` | `_source.syscheck.path` |
| Command regex flags | `cmd_sudo_usage`, `cmd_chmod_usage`, `cmd_wget_curl`, `cmd_nc_netcat`, `cmd_base64`, `cmd_eval_exec`, `cmd_pipe_redirect`, `cmd_hidden_file`, `cmd_cron_at`, `cmd_ssh_scp`, `cmd_python_perl`, `cmd_kill_pkill`, `cmd_rm_delete`, `cmd_cat_less`, `cmd_grep_find`, `cmd_env_export`, `cmd_passwd_shadow`, `cmd_iptables_firewall`, `cmd_dd_disk`, `cmd_tar_zip`, `cmd_length`, `cmd_has_args`, `cmd_is_missing` | `_source.data.command` |
| Hash presence | `has_md5`, `has_sha256` | `_source.syscheck.md5_after`, `_source.syscheck.sha256_after` |
| Syscheck event | `syscheck_added`, `syscheck_modified`, `syscheck_deleted` | `_source.syscheck.event` |
| Changed attrs | `changed_size`, `changed_mtime`, `changed_md5`, `changed_sha1`, `changed_sha256`, `changed_permission`, `changed_uid`, `changed_gid`, `changed_inode` | `_source.syscheck.changed_attributes` |
| Port | `srcport`, `is_privileged_port`, `is_high_port` | `_source.data.srcport` |
| Decoder one-hots | `decoder_<top-15 values>` — e.g. `decoder_auditd`, `decoder_web-accesslog`, `decoder_pam`, `decoder_syscheck_*`, `decoder_dpkg-decoder`, `decoder_sudo`, `decoder_sca`, `decoder_ossec`, `decoder_rootcheck`, `decoder_sshd`, `decoder_wazuh`, `decoder_systemd`, `decoder_kernel` | `_source.decoder.name` |
| Location one-hots | `location_<top-15 values>` — e.g. `location__var_log_audit_audit.log`, `location__var_log_apache2_access.log`, `location_syscheck`, `location__var_log_auth.log`, `location__var_log_dpkg.log` | `_source.location` |
| SecBERT text (16-dim each) | `cmd_secbert_emb_0..15`, `log_secbert_emb_0..15` | `_source.data.command`, `_source.full_log` — passed through `jackaduma/SecBERT` + PCA |

**Top-15 decoders observed in training:** `auditd` (77k), `web-accesslog` (27k), `pam` (2.7k), `syscheck_integrity_changed`, `syscheck_new_entry`, `syscheck_deleted`, `dpkg-decoder`, `sudo`, `sca`, `ossec`, `rootcheck`, `sshd`, `wazuh`, `systemd`, `kernel`.

**Top-15 locations observed:** `/var/log/audit/audit.log`, `/var/log/apache2/access.log`, `syscheck`, `/var/log/auth.log`, `/var/log/dpkg.log`, `sca`, `rootcheck`, `/var/log/auth.log.1`, `logcollector`, `wazuh-agent`, `/var/log/syslog`, `netstat listening ports`, `wazuh-monitord`, `wazuh-remoted`, `/var/log/kern.log`.

> Any live alert whose `decoder.name` / `location` falls outside these top-15 sets maps to an all-zeros one-hot vector — same behavior as training.

---

## 4. Raw-column inventory (all 176)

Sparsity legend: **Null %** is out of 115,726 rows. "Role" marks how the column is used downstream.

Type labels are inferred from content; many numeric fields are stored as `object` (string) because Wazuh's JSON export preserves string-encoded numbers — the engineering code coerces with `pd.to_numeric(..., errors='coerce')`.

### envelope

| # | Column | Type | Null % | Uniques | Role | Example |
|---|--------|------|--------|---------|------|---------|
| 1 | `_index` | categorical/text (str) | 0.0% | 24 | metadata (ES envelope — drop) | wazuh-alerts-4.x-2023.12.31 |
| 2 | `_id` | categorical/text (str) | 0.0% | 115726 | metadata (ES envelope — drop) | 1oT1v4wBhmtSw-nf6pI9 |
| 3 | `_version` | numeric (int64) | 0.0% | 1 | metadata (ES envelope — drop) | 1 |
| 4 | `_score` | numeric (int64) | 0.0% | 1 | metadata (ES envelope — drop) | 1 |

### core

| # | Column | Type | Null % | Uniques | Role | Example |
|---|--------|------|--------|---------|------|---------|
| 1 | `_source.full_log` | text (long str) | 0.5% | 104612 | FEATURE (candidate) | type=SYSCALL msg=audit(1704027585.876:12992): arch=c000003e  |
| 2 | `_source.input.type` | categorical/text (str) | 0.0% | 1 | FEATURE (candidate) | log |
| 3 | `_source.@timestamp` | timestamp (str: "Mon DD, YYYY @ HH:MM:SS.mmm") | 0.0% | 87277 | FEATURE (candidate) | Dec 31, 2023 @ 12:59:55.107 |
| 4 | `_source.location` | categorical/text (str) | 0.0% | 19 | FEATURE (candidate) | /var/log/audit/audit.log |
| 5 | `_source.id` | identifier (int/str) | 0.0% | 78985 | FEATURE (candidate) | 1704027595.258 |
| 6 | `_source.timestamp` | timestamp (str: "Mon DD, YYYY @ HH:MM:SS.mmm") | 0.0% | 87277 | FEATURE (candidate) | Dec 31, 2023 @ 12:59:55.107 |
| 7 | `_source.previous_output` | categorical/text (str) | 52.0% | 2342 | FEATURE (candidate) |   |
| 8 | `_source.previous_log` | categorical/text (str) | 53.9% | 63 | FEATURE (candidate) |   |

### agent

| # | Column | Type | Null % | Uniques | Role | Example |
|---|--------|------|--------|---------|------|---------|
| 1 | `_source.agent.ip` | IP address (str) | 0.4% | 7 | FEATURE (candidate) | 192.168.217.133 |
| 2 | `_source.agent.name` | categorical/text (str) | 0.0% | 5 | FEATURE (candidate) | Machine-1-New |
| 3 | `_source.agent.id` | identifier (int/str) | 0.0% | 5 | FEATURE (candidate) | 4 |

### manager

| # | Column | Type | Null % | Uniques | Role | Example |
|---|--------|------|--------|---------|------|---------|
| 1 | `_source.manager.name` | categorical/text (str) | 0.0% | 1 | FEATURE (candidate) | ubuntu |

### predecoder

| # | Column | Type | Null % | Uniques | Role | Example |
|---|--------|------|--------|---------|------|---------|
| 1 | `_source.predecoder.hostname` | categorical/text (str) | 25.4% | 3 | FEATURE (candidate) |   |
| 2 | `_source.predecoder.program_name` | categorical/text (str) | 25.4% | 11 | FEATURE (candidate) |   |
| 3 | `_source.predecoder.timestamp` | timestamp (str: "Mon DD, YYYY @ HH:MM:SS.mmm") | 25.4% | 913 | FEATURE (candidate) |   |

### decoder

| # | Column | Type | Null % | Uniques | Role | Example |
|---|--------|------|--------|---------|------|---------|
| 1 | `_source.decoder.parent` | categorical/text (str) | 25.3% | 11 | FEATURE (candidate) | auditd |
| 2 | `_source.decoder.name` | categorical/text (str) | 0.0% | 19 | FEATURE (candidate) | auditd |
| 3 | `_source.decoder.ftscomment` | categorical/text (str) | 44.7% | 3 | FEATURE (candidate) |   |
| 4 | `_source.decoder` | categorical/text (str) | 95.7% | 20 | FEATURE (candidate) | {"name":"rootcheck"} |

### rule

| # | Column | Type | Null % | Uniques | Role | Example |
|---|--------|------|--------|---------|------|---------|
| 1 | `_source.rule.firedtimes` | categorical/text (str) | 0.0% | 14742 | FEATURE (kept) | 9640 |
| 2 | `_source.rule.mail` | categorical/text (str) | 0.0% | 2 | FEATURE (candidate) | False |
| 3 | `_source.rule.level` | numeric (int) | 0.0% | 11 | FEATURE (excluded in training — leaky) | 3 |
| 4 | `_source.rule.description` | IP address (str) | 0.0% | 468 | FEATURE (excluded in training — leaky) | Audit: Command: /usr/bin/kmod. |
| 5 | `_source.rule.groups` | list (serialized JSON array str) | 0.0% | 44 | FEATURE (candidate) | ["audit","audit_command"] |
| 6 | `_source.rule.id` | identifier (int/str) | 0.0% | 98 | FEATURE (candidate) | 80792 |
| 7 | `_source.rule.gdpr` | categorical/text (str) | 0.3% | 8 | FEATURE (candidate) | ["IV_30.1.g"] |
| 8 | `_source.rule.pci_dss` | categorical/text (str) | 0.3% | 21 | FEATURE (candidate) |   |
| 9 | `_source.rule.hipaa` | IP address (str) | 24.1% | 12 | FEATURE (candidate) |   |
| 10 | `_source.rule.tsc` | categorical/text (str) | 0.6% | 14 | FEATURE (candidate) |   |
| 11 | `_source.rule.nist_800_53` | categorical/text (str) | 0.6% | 20 | FEATURE (candidate) |   |
| 12 | `_source.rule.gpg13` | categorical/text (str) | 24.4% | 14 | FEATURE (candidate) |   |
| 13 | `_source.rule.cis` | categorical/text (str) | 83.4% | 187 | FEATURE (candidate) |   |
| 14 | `_source.rule.cis_csc_v7` | categorical/text (str) | 83.5% | 34 | FEATURE (candidate) |   |
| 15 | `_source.rule.cis_csc_v8` | categorical/text (str) | 83.5% | 24 | FEATURE (candidate) |   |
| 16 | `_source.rule.frequency` | numeric (float64) | 98.0% | 3 | FEATURE (candidate) | 10.0 |
| 17 | `_source.rule.info` | categorical/text (str) | 99.7% | 2 | FEATURE (candidate) | CVE-2014-6278https://cve.mitre.org/cgi-bin/cvename.cgi?name= |
| 18 | `_source.rule.nist_sp_800-53` | categorical/text (str) | 83.6% | 15 | FEATURE (candidate) |   |
| 19 | `_source.rule.soc_2` | categorical/text (str) | 83.5% | 15 | FEATURE (candidate) |   |

### rule-mitre

| # | Column | Type | Null % | Uniques | Role | Example |
|---|--------|------|--------|---------|------|---------|
| 1 | `_source.rule.mitre.technique` | list (serialized JSON array str) | 9.9% | 27 | FEATURE (excluded in training — leaky) |   |
| 2 | `_source.rule.mitre.id` | identifier (int/str) | 9.9% | 27 | FEATURE (excluded in training — leaky) |   |
| 3 | `_source.rule.mitre.tactic` | list (serialized JSON array str) | 9.9% | 21 | FEATURE (excluded in training — leaky) |   |
| 4 | `_source.rule.mitre_mitigations` | categorical/text (str) | 83.6% | 22 | FEATURE (candidate) |   |
| 5 | `_source.rule.mitre_tactics` | list (serialized JSON array str) | 83.5% | 20 | FEATURE (excluded in training — leaky) |   |
| 6 | `_source.rule.mitre_techniques` | list (serialized JSON array str) | 83.5% | 56 | FEATURE (excluded in training — leaky) |   |

### data-audit

| # | Column | Type | Null % | Uniques | Role | Example |
|---|--------|------|--------|---------|------|---------|
| 1 | `_source.data.audit.syscall` | categorical/text (str) | 28.7% | 3 | FEATURE (candidate) | 59 |
| 2 | `_source.data.audit.gid` | categorical/text (str) | 28.7% | 7 | FEATURE (candidate) | 0 |
| 3 | `_source.data.audit.fsgid` | categorical/text (str) | 28.7% | 6 | FEATURE (candidate) | 0 |
| 4 | `_source.data.audit.session` | categorical/text (str) | 28.7% | 98 | FEATURE (candidate) | 2 |
| 5 | `_source.data.audit.pid` | categorical/text (str) | 28.6% | 40481 | FEATURE (candidate) | 14903 |
| 6 | `_source.data.audit.suid` | categorical/text (str) | 28.7% | 2 | FEATURE (candidate) | 0 |
| 7 | `_source.data.audit.type` | categorical/text (str) | 28.6% | 9 | FEATURE (candidate) | SYSCALL |
| 8 | `_source.data.audit.uid` | categorical/text (str) | 28.6% | 7 | FEATURE (candidate) | 0 |
| 9 | `_source.data.audit.egid` | categorical/text (str) | 28.7% | 6 | FEATURE (candidate) | 0 |
| 10 | `_source.data.audit.exe` | categorical/text (str) | 28.7% | 178 | FEATURE (candidate) | /usr/bin/kmod |
| 11 | `_source.data.audit.file.inode` | categorical/text (str) | 28.7% | 519 | FEATURE (candidate) | 262752 |
| 12 | `_source.data.audit.file.mode` | categorical/text (str) | 28.7% | 5 | FEATURE (candidate) | 0100755 |
| 13 | `_source.data.audit.file.name` | categorical/text (str) | 28.7% | 513 | FEATURE (candidate) | /sbin/modinfo |
| 14 | `_source.data.audit.sgid` | categorical/text (str) | 28.7% | 6 | FEATURE (candidate) | 0 |
| 15 | `_source.data.audit.id` | identifier (int/str) | 28.6% | 40241 | FEATURE (candidate) | 12992 |
| 16 | `_source.data.audit.key` | categorical/text (str) | 28.7% | 4 | FEATURE (candidate) | audit-wazuh-c |
| 17 | `_source.data.audit.auid` | categorical/text (str) | 28.6% | 6 | FEATURE (candidate) | 1000 |
| 18 | `_source.data.audit.execve.a1` | categorical/text (str) | 28.7% | 1120 | FEATURE (candidate) | -k |
| 19 | `_source.data.audit.execve.a2` | categorical/text (str) | 28.7% | 8228 | FEATURE (candidate) | 6.2.0-36-generic |
| 20 | `_source.data.audit.execve.a3` | categorical/text (str) | 28.7% | 7360 | FEATURE (candidate) | -F |
| 21 | `_source.data.audit.execve.a4` | categorical/text (str) | 28.7% | 335 | FEATURE (candidate) | firmware |
| 22 | `_source.data.audit.execve.a5` | categorical/text (str) | 28.7% | 3037 | FEATURE (candidate) | /lib/modules/6.2.0-36-generic/kernel/drivers/net/ethernet/3c |
| 23 | `_source.data.audit.execve.a0` | categorical/text (str) | 28.7% | 251 | FEATURE (candidate) | modinfo |
| 24 | `_source.data.audit.euid` | categorical/text (str) | 28.7% | 2 | FEATURE (candidate) | 0 |
| 25 | `_source.data.audit.command` | categorical/text (str) | 28.6% | 427 | FEATURE (candidate) | modinfo |
| 26 | `_source.data.audit.ppid` | categorical/text (str) | 28.7% | 12785 | FEATURE (candidate) | 14207 |
| 27 | `_source.data.audit.fsuid` | categorical/text (str) | 28.7% | 2 | FEATURE (candidate) | 0 |
| 28 | `_source.data.audit.exit` | categorical/text (str) | 28.7% | 4 | FEATURE (candidate) | 0 |
| 29 | `_source.data.audit.cwd` | categorical/text (str) | 28.7% | 30 | FEATURE (candidate) | / |
| 30 | `_source.data.audit.success` | categorical/text (str) | 28.7% | 3 | FEATURE (candidate) | yes |
| 31 | `_source.data.audit.tty` | categorical/text (str) | 28.7% | 7 | FEATURE (candidate) | pts2 |
| 32 | `_source.data.audit.arch` | categorical/text (str) | 28.7% | 2 | FEATURE (candidate) | c000003e |
| 33 | `_source.data.audit.execve.a6` | categorical/text (str) | 28.7% | 209 | FEATURE (candidate) |   |
| 34 | `_source.data.audit.execve.a7` | categorical/text (str) | 28.7% | 166 | FEATURE (candidate) |   |
| 35 | `_source.data.audit.res` | categorical/text (str) | 69.2% | 6 | FEATURE (candidate) |   |
| 36 | `_source.data.audit.list` | categorical/text (str) | 83.9% | 2 | FEATURE (candidate) |   |

### data-sca

| # | Column | Type | Null % | Uniques | Role | Example |
|---|--------|------|--------|---------|------|---------|
| 1 | `_source.data.sca.scan_id` | categorical/text (str) | 76.6% | 24 | FEATURE (mostly unused in engineered set) |   |
| 2 | `_source.data.sca.check.result` | categorical/text (str) | 76.6% | 4 | FEATURE (mostly unused in engineered set) |   |
| 3 | `_source.data.sca.check.remediation` | categorical/text (str) | 76.6% | 188 | FEATURE (mostly unused in engineered set) |   |
| 4 | `_source.data.sca.check.compliance.pci_dss` | list/str (compliance tags) | 93.2% | 2 | FEATURE (mostly unused in engineered set) |   |
| 5 | `_source.data.sca.check.compliance.nist_800_53` | list/str (compliance tags) | 93.2% | 2 | FEATURE (mostly unused in engineered set) |   |
| 6 | `_source.data.sca.check.description` | IP address (str) | 76.6% | 164 | FEATURE (mostly unused in engineered set) |   |
| 7 | `_source.data.sca.check.id` | identifier (int/str) | 76.6% | 187 | FEATURE (mostly unused in engineered set) |   |
| 8 | `_source.data.sca.check.title` | categorical/text (str) | 76.6% | 188 | FEATURE (mostly unused in engineered set) |   |
| 9 | `_source.data.sca.check.rationale` | categorical/text (str) | 76.6% | 172 | FEATURE (mostly unused in engineered set) |   |
| 10 | `_source.data.sca.check.command` | categorical/text (str) | 76.8% | 117 | FEATURE (mostly unused in engineered set) |   |
| 11 | `_source.data.sca.type` | categorical/text (str) | 76.6% | 6 | FEATURE (mostly unused in engineered set) |   |
| 12 | `_source.data.sca.policy` | categorical/text (str) | 76.6% | 6 | FEATURE (mostly unused in engineered set) |   |
| 13 | `_source.data.sca.score` | categorical/text (str) | 77.1% | 10 | FEATURE (mostly unused in engineered set) |   |
| 14 | `_source.data.sca.total_checks` | categorical/text (str) | 77.1% | 4 | FEATURE (mostly unused in engineered set) |   |
| 15 | `_source.data.sca.file` | categorical/text (str) | 77.1% | 5 | FEATURE (mostly unused in engineered set) |   |
| 16 | `_source.data.sca.policy_id` | categorical/text (str) | 77.1% | 4 | FEATURE (mostly unused in engineered set) |   |
| 17 | `_source.data.sca.invalid` | categorical/text (str) | 77.1% | 9 | FEATURE (mostly unused in engineered set) |   |
| 18 | `_source.data.sca.description` | IP address (str) | 77.1% | 4 | FEATURE (mostly unused in engineered set) |   |
| 19 | `_source.data.sca.passed` | categorical/text (str) | 77.1% | 11 | FEATURE (mostly unused in engineered set) |   |
| 20 | `_source.data.sca.failed` | categorical/text (str) | 77.1% | 10 | FEATURE (mostly unused in engineered set) |   |
| 21 | `_source.data.sca.check.previous_result` | categorical/text (str) | 85.3% | 6 | FEATURE (mostly unused in engineered set) |   |
| 22 | `_source.data.sca.check.compliance.cis` | list/str (compliance tags) | 83.4% | 185 | FEATURE (mostly unused in engineered set) |   |
| 23 | `_source.data.sca.check.compliance.cis_csc_v7` | list/str (compliance tags) | 83.5% | 33 | FEATURE (mostly unused in engineered set) |   |
| 24 | `_source.data.sca.check.compliance.cis_csc_v8` | list/str (compliance tags) | 83.5% | 23 | FEATURE (mostly unused in engineered set) |   |
| 25 | `_source.data.sca.check.compliance.cmmc_v2.0` | list/str (compliance tags) | 83.5% | 19 | FEATURE (mostly unused in engineered set) |   |
| 26 | `_source.data.sca.check.compliance.hipaa` | IP address (str) | 83.7% | 13 | FEATURE (mostly unused in engineered set) |   |
| 27 | `_source.data.sca.check.compliance.mitre_mitigations` | list/str (compliance tags) | 83.6% | 20 | FEATURE (mostly unused in engineered set) |   |
| 28 | `_source.data.sca.check.compliance.mitre_tactics` | list/str (compliance tags) | 83.5% | 19 | FEATURE (mostly unused in engineered set) |   |
| 29 | `_source.data.sca.check.compliance.mitre_techniques` | list/str (compliance tags) | 83.5% | 55 | FEATURE (mostly unused in engineered set) |   |
| 30 | `_source.data.sca.check.compliance.nist_sp_800-53` | list/str (compliance tags) | 83.6% | 15 | FEATURE (mostly unused in engineered set) |   |
| 31 | `_source.data.sca.check.compliance.pci_dss_3.2.1` | list/str (compliance tags) | 83.7% | 14 | FEATURE (mostly unused in engineered set) |   |
| 32 | `_source.data.sca.check.compliance.pci_dss_4.0` | list/str (compliance tags) | 83.7% | 14 | FEATURE (mostly unused in engineered set) |   |
| 33 | `_source.data.sca.check.compliance.pci_dss_v3.2.1` | list/str (compliance tags) | 83.8% | 12 | FEATURE (mostly unused in engineered set) |   |
| 34 | `_source.data.sca.check.compliance.pci_dss_v4.0` | list/str (compliance tags) | 83.8% | 11 | FEATURE (mostly unused in engineered set) |   |
| 35 | `_source.data.sca.check.compliance.soc_2` | list/str (compliance tags) | 83.5% | 16 | FEATURE (mostly unused in engineered set) |   |
| 36 | `_source.data.sca.check.directory` | categorical/text (str) | 83.9% | 9 | FEATURE (mostly unused in engineered set) |   |
| 37 | `_source.data.sca.check.file` | categorical/text (str) | 83.8% | 30 | FEATURE (mostly unused in engineered set) |   |
| 38 | `_source.data.sca.check.reason` | categorical/text (str) | 83.9% | 15 | FEATURE (mostly unused in engineered set) |   |
| 39 | `_source.data.sca.check.references` | categorical/text (str) | 83.8% | 24 | FEATURE (mostly unused in engineered set) |   |

### data-other

| # | Column | Type | Null % | Uniques | Role | Example |
|---|--------|------|--------|---------|------|---------|
| 1 | `_source.data.dpkg_status` | categorical/text (str) | 43.5% | 5 | FEATURE (candidate) |   |
| 2 | `_source.data.package` | categorical/text (str) | 43.5% | 253 | FEATURE (candidate) |   |
| 3 | `_source.data.arch` | categorical/text (str) | 43.5% | 3 | FEATURE (candidate) |   |
| 4 | `_source.data.version` | categorical/text (str) | 43.5% | 198 | FEATURE (candidate) |   |
| 5 | `_source.data.srcuser` | categorical/text (str) | 43.8% | 9 | FEATURE (candidate) |   |
| 6 | `_source.data.dstuser` | categorical/text (str) | 25.5% | 14 | FEATURE (candidate) |   |
| 7 | `_source.data.tty` | categorical/text (str) | 44.7% | 17 | FEATURE (candidate) |   |
| 8 | `_source.data.pwd` | categorical/text (str) | 44.7% | 10 | FEATURE (candidate) |   |
| 9 | `_source.data.command` | categorical/text (str) | 44.7% | 1077 | FEATURE (candidate) |   |
| 10 | `_source.data.uid` | categorical/text (str) | 36.0% | 10 | FEATURE (candidate) |   |
| 11 | `_source.data.level` | numeric (int) | 77.1% | 6 | FEATURE (candidate) |   |
| 12 | `_source.data.extra_data` | categorical/text (str) | 61.7% | 7 | FEATURE (candidate) |   |
| 13 | `_source.data.file` | categorical/text (str) | 45.4% | 3 | FEATURE (candidate) |   |
| 14 | `_source.data.title` | categorical/text (str) | 45.4% | 2 | FEATURE (candidate) |   |
| 15 | `_source.data.srcip` | IP address (str) | 13.3% | 4 | FEATURE (candidate) |   |
| 16 | `_source.data.srcport` | port (numeric str) | 36.9% | 244 | FEATURE (candidate) |   |
| 17 | `_source.data.euid` | categorical/text (str) | 83.9% | 2 | FEATURE (candidate) |   |
| 18 | `_source.data.gid` | categorical/text (str) | 91.8% | 4 | FEATURE (candidate) |   |
| 19 | `_source.data.home` | categorical/text (str) | 91.8% | 4 | FEATURE (candidate) |   |
| 20 | `_source.data.id` | identifier (int/str) | 68.2% | 15 | FEATURE (candidate) |   |
| 21 | `_source.data.logname` | categorical/text (str) | 83.9% | 2 | FEATURE (candidate) |   |
| 22 | `_source.data.protocol` | categorical/text (str) | 76.4% | 48 | FEATURE (candidate) | GET |
| 23 | `_source.data.shell` | categorical/text (str) | 91.8% | 4 | FEATURE (candidate) |   |
| 24 | `_source.data.status` | categorical/text (str) | 100.0% | 1 | FEATURE (candidate) | DENIED |
| 25 | `_source.data.url` | categorical/text (str) | 76.4% | 19266 | FEATURE (candidate) | /DVWA/vulnerabilities/xss_r/?name=Arsalan+Shahid%3A%3E%3Cscr |

### syscheck

| # | Column | Type | Null % | Uniques | Role | Example |
|---|--------|------|--------|---------|------|---------|
| 1 | `_source.syscheck.size_before` | categorical/text (str) | 44.3% | 695 | FEATURE (candidate) |   |
| 2 | `_source.syscheck.uname_after` | categorical/text (str) | 43.9% | 6 | FEATURE (candidate) |   |
| 3 | `_source.syscheck.mtime_after` | categorical/text (str) | 43.9% | 365 | FEATURE (candidate) |   |
| 4 | `_source.syscheck.inode_before` | categorical/text (str) | 52.3% | 573 | FEATURE (candidate) |   |
| 5 | `_source.syscheck.size_after` | categorical/text (str) | 43.9% | 1617 | FEATURE (candidate) |   |
| 6 | `_source.syscheck.gid_after` | categorical/text (str) | 43.9% | 7 | FEATURE (candidate) |   |
| 7 | `_source.syscheck.md5_before` | hash (hex str) | 44.3% | 919 | FEATURE (candidate) |   |
| 8 | `_source.syscheck.sha256_before` | hash (hex str) | 44.3% | 919 | FEATURE (candidate) |   |
| 9 | `_source.syscheck.mtime_before` | categorical/text (str) | 44.1% | 165 | FEATURE (candidate) |   |
| 10 | `_source.syscheck.mode` | categorical/text (str) | 43.9% | 3 | FEATURE (candidate) |   |
| 11 | `_source.syscheck.path` | categorical/text (str) | 43.9% | 1809 | FEATURE (candidate) |   |
| 12 | `_source.syscheck.sha1_after` | hash (hex str) | 43.9% | 1955 | FEATURE (candidate) |   |
| 13 | `_source.syscheck.changed_attributes` | list (serialized JSON array str) | 44.0% | 18 | FEATURE (candidate) |   |
| 14 | `_source.syscheck.gname_after` | categorical/text (str) | 43.9% | 8 | FEATURE (candidate) |   |
| 15 | `_source.syscheck.uid_after` | categorical/text (str) | 43.9% | 6 | FEATURE (candidate) |   |
| 16 | `_source.syscheck.perm_after` | categorical/text (str) | 43.9% | 12 | FEATURE (candidate) |   |
| 17 | `_source.syscheck.event` | categorical/text (str) | 43.9% | 4 | FEATURE (candidate) |   |
| 18 | `_source.syscheck.md5_after` | hash (hex str) | 43.9% | 1955 | FEATURE (candidate) |   |
| 19 | `_source.syscheck.sha1_before` | hash (hex str) | 44.3% | 919 | FEATURE (candidate) |   |
| 20 | `_source.syscheck.sha256_after` | hash (hex str) | 43.9% | 1955 | FEATURE (candidate) |   |
| 21 | `_source.syscheck.inode_after` | categorical/text (str) | 43.9% | 1276 | FEATURE (candidate) |   |
| 22 | `_source.syscheck.perm_before` | categorical/text (str) | 75.2% | 2 | FEATURE (candidate) |   |

### labels

| # | Column | Type | Null % | Uniques | Role | Example |
|---|--------|------|--------|---------|------|---------|
| 1 | `malicious` | numeric (int64) | 0.0% | 2 | LABEL / derived at preprocessing | 0 |
| 2 | `cyber_kill_chain_technique` | categorical/text (str) | 78.9% | 5 | LABEL / derived at preprocessing | S4 |
| 3 | `cyber_kill_chain_id` | numeric (float64) | 100.0% | 0 | LABEL / derived at preprocessing |  |
| 4 | `cyber_kill_chain_tactic` | categorical/text (str) | 78.8% | 5 | LABEL / derived at preprocessing | S4 |
| 5 | `cyber_kill_chain_mitre_tactics` | categorical/text (str) | 99.3% | 5 | LABEL / derived at preprocessing | S7 |
| 6 | `cyber_kill_chain_mitre_techniques` | categorical/text (str) | 99.3% | 6 | LABEL / derived at preprocessing | S3 |


---

## 5. Quick caveats for the live-inference mapping

1. **Labels are synthesized** — `malicious` and `cyber_kill_chain_*` do not exist in Wazuh alerts. Live inference outputs them; it does not read them.
2. **Leaky columns must also be stripped at inference time** (see section 2), even though Wazuh produces them.
3. **Training was single-site** — 5 agents, 1 manager, one /24 subnet. `ip_is_private` will evaluate consistently in live data but per-agent one-hots (if any were added) would not generalize. The committed engineering code avoids agent-specific one-hots.
4. **Timestamp format in the export is "Mon DD, YYYY @ HH:MM:SS.mmm"** (Kibana Discover CSV export style). Wazuh native alerts ship ISO-8601 `@timestamp` — the normalization service must parse both. `pd.to_datetime(..., errors='coerce')` already handles both in the training code.
5. **Many columns are mutually exclusive alert-type views** — an `auditd` alert fills `_source.data.audit.*` and leaves `_source.syscheck.*` empty and vice versa. The ML pipeline tolerates this via `fillna(0)` at the end of `transform()`.
6. **`cyber_kill_chain_id` is 100% null — drop it.**
7. **`_source.data.status` has a single observed value ("DENIED")** but is 100% null in this export — don't one-hot it.
