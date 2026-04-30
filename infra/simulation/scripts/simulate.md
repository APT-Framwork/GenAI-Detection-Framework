# `run_full_simulation.py` — tactic & technique coverage

Reference for what [`run_full_simulation.py`](run_full_simulation.py) (invoked via [`infra/scripts/lab_simulate.sh`](../../scripts/lab_simulate.sh)) actually exercises against the STRIX lab.

Source of truth for the plan is the `PLAN` list in `run_full_simulation.py`. This file is the human-readable mirror.

Technique names follow MITRE ATT&CK Enterprise (https://attack.mitre.org/techniques/enterprise/).

Paper reference: Karim, S.S. et al. (2024). *APT and intrusion detection evaluation dataset for Linux systems 2024*, Data in Brief 54, 110290.

---

## Auto-runnable tactics (9)

The script fires these in order, one Caldera operation per tactic, against `group=red`. Each runs for `--budget` seconds (default 90), then drains for `--dwell` seconds (default 30).

### 1. Discovery — `TA0007`

Paper baseline. Heavy auditd `execve` signal feeding `data.audit.command` and the `cmd_*` engineered features.

| Technique  | MITRE name                                          |
|------------|-----------------------------------------------------|
| T1033      | System Owner/User Discovery                         |
| T1057      | Process Discovery                                   |
| T1083      | File and Directory Discovery                        |
| T1087.001  | Account Discovery: Local Account                    |
| T1069.001  | Permission Groups Discovery: Local Groups           |

**Adversary:** stockpile `Discovery` (preferred) → `Enumerator` → `Terminal` → ad-hoc fallback.

---

### 2. Defense Evasion — `TA0005`

Log clearing + tool tampering. Exercises FIM (`syscheck.*`) plus audit `unlink`/`open` syscalls.

| Technique  | MITRE name                                          |
|------------|-----------------------------------------------------|
| T1070.003  | Indicator Removal: Clear Command History            |
| T1070.004  | Indicator Removal: File Deletion                    |
| T1027      | Obfuscated Files or Information                     |
| T1562.001  | Impair Defenses: Disable or Modify Tools            |

**Adversary:** stockpile `Defense Evasion` (preferred) → `Undercover` → ad-hoc fallback.

---

### 3. Persistence — `TA0003`

Account creation, cron edits, systemd unit drops, login-script tampering.

| Technique  | MITRE name                                          |
|------------|-----------------------------------------------------|
| T1136.001  | Create Account: Local Account                       |
| T1098      | Account Manipulation                                |
| T1037      | Boot or Logon Initialization Scripts                |
| T1543.002  | Create or Modify System Process: Systemd Service    |
| T1053.003  | Scheduled Task/Job: Cron                            |

**Adversary:** stockpile `Stowaway` (preferred) → `Persistence` → ad-hoc fallback.

---

### 4. Privilege Escalation — `TA0004`

`sudo`/`SUID` abuse and exploit-driven escalation.

| Technique  | MITRE name                                                              |
|------------|-------------------------------------------------------------------------|
| T1548.003  | Abuse Elevation Control Mechanism: Sudo and Sudo Caching                |
| T1068      | Exploitation for Privilege Escalation                                   |
| T1548.001  | Abuse Elevation Control Mechanism: Setuid and Setgid                    |

**Adversary:** stockpile `Privileged Operations` / `Privileged` if installed → otherwise **ad-hoc** built from any linux-tagged abilities matching the technique IDs.

---

### 5. Credential Access — `TA0006`

Password guessing, `/etc/shadow` scraping, credential-in-file hunts.

| Technique  | MITRE name                                                          |
|------------|---------------------------------------------------------------------|
| T1110.001  | Brute Force: Password Guessing                                      |
| T1003.008  | OS Credential Dumping: `/etc/passwd` and `/etc/shadow`              |
| T1552.001  | Unsecured Credentials: Credentials In Files                         |
| T1003      | OS Credential Dumping (parent)                                      |

**Adversary:** stockpile `Credential Access` / `Brute Force` if installed → otherwise **ad-hoc**.

---

### 6. Lateral Movement — `TA0008`

SSH pivot to a second host on the lab network.

| Technique  | MITRE name                                          |
|------------|-----------------------------------------------------|
| T1021.004  | Remote Services: SSH                                |
| T1021      | Remote Services (parent)                            |

**Adversary:** stockpile `Lateral Movement (SSH)` / `Lateral Movement` if installed → otherwise **ad-hoc**.
*Note:* substring/fuzzy match is intentionally disabled here — the stockpile carries `Lateral Movement - Certutil` and `Lateral Movement - Esentutl`, both Windows-only.

---

### 7. Collection — `TA0009`

Stages sensitive files under `/tmp/staged/` → FIM (`syscheck_added`, `path_is_temp`).

| Technique  | MITRE name                                          |
|------------|-----------------------------------------------------|
| T1005      | Data from Local System                              |
| T1560.001  | Archive Collected Data: Archive via Utility         |
| T1119      | Automated Collection                                |

**Adversary:** stockpile `Collection` (preferred) → `Thief` → ad-hoc fallback.

---

### 8. Exfiltration — `TA0010`

Outbound transfer over an unencrypted protocol (FTP) — populates `data.srcip` and trips `srcip_is_private=0`.

| Technique  | MITRE name                                                                            |
|------------|---------------------------------------------------------------------------------------|
| T1048      | Exfiltration Over Alternative Protocol                                                |
| T1048.003  | Exfiltration Over Alternative Protocol: Exfiltration Over Unencrypted Non-C2 Protocol |
| T1041      | Exfiltration Over C2 Channel                                                          |

**Adversary:** stockpile `Advanced Thief via FTP` (preferred) → `Advanced Thief` → `Thief` → ad-hoc.
*Note:* without an FTP receiver on `strix_lab_net` the link itself fails (`rc ≠ 0`), but the audit signal still produces alerts. Spin up a receiver if you want the full chain to succeed:

```bash
docker run -d --name strix_ftp_sink --network strix_lab_net -p 2121:21 \
  -e FTP_USER=red -e FTP_PASS=red delfer/alpine-ftp-server
```

---

### 9. Impact — `TA0040`

Data destruction / manipulation. **Destructive-flavoured** — keep `--budget` short. Stockpile `Ransack` operates in `/tmp` only.

| Technique  | MITRE name                                          |
|------------|-----------------------------------------------------|
| T1485      | Data Destruction                                    |
| T1565.001  | Data Manipulation: Stored Data Manipulation         |
| T1486      | Data Encrypted for Impact                           |

**Adversary:** stockpile `Ransack`.

---

## Cross-cutting — implicit on every tactic

### Command and Scripting Interpreter — `TA0002`

| Technique  | MITRE name                                          |
|------------|-----------------------------------------------------|
| T1059.004  | Command and Scripting Interpreter: Unix Shell       |

Every Caldera ability is a shell snippet — every operation feeds `data.command` and SecBERT. Use `--obfuscator base64jumble` to drive `cmd_base64` / `cmd_eval_exec` features and stress the SecBERT embedding path.

---

## APT-group emulation (4)

The script can replay an APT group's TTPs as an **ordered tactic chain** — same firing logic as the per-tactic mode, just reordered to match how that group operates in the wild. Mappings come from [`docs/CALDERA_MITRE_SIMULATION_GUIDE.md` §6](../../../docs/CALDERA_MITRE_SIMULATION_GUIDE.md). Initial Access, Reconnaissance, and C2 contact-switching steps are dropped from each chain (manual setup — see "Not auto-runnable" below).

Run with `--apt <name>` (or `--apt all`). List with `--list-apts`.

```bash
bash infra/scripts/lab_simulate.sh --apt APT41
bash infra/scripts/lab_simulate.sh --apt APT29        # auto-applies base64jumble
bash infra/scripts/lab_simulate.sh --apt all          # all four, back to back
```

### APT41 — Chinese state/financial actor

> *Paper: "commonly used as backdoor/rootkit and for exfiltration commonly uses Rsync and Exfil."*

Default obfuscator: `plain-text`.

| Step | Tactic                | MITRE techniques                                                |
|:----:|-----------------------|-----------------------------------------------------------------|
| 1    | Persistence           | T1136.001 Create Account: Local Account                         |
| 2    | Privilege Escalation  | T1068 Exploitation for Privilege Escalation                     |
| 3    | Defense Evasion       | T1070.004 Indicator Removal: File Deletion                      |
| 4    | Discovery             | T1083 File and Directory Discovery                              |
| 5    | Collection            | T1005 Data from Local System                                    |
| 6    | Exfiltration          | T1048 Exfiltration Over Alternative Protocol (rsync signature)  |

*Dropped vs paper:* Initial Access (T1190 Apache Struts), Execution (T1059.004 explicit), C2 (T1105 wget payload).

---

### APT28 — Sofacy / Fancy Bear (Russian GRU)

> *Paper: "searches and actively exploits known vulnerabilities, then tries to establish remote access, perform file manipulations, and data exfiltration."*

Default obfuscator: `plain-text`.

| Step | Tactic                | MITRE techniques                                                |
|:----:|-----------------------|-----------------------------------------------------------------|
| 1    | Discovery             | T1083 / T1057 / T1082 (file/process/system info)                |
| 2    | Privilege Escalation  | T1068 Exploitation for Privilege Escalation                     |
| 3    | Defense Evasion       | T1070.004 / T1036.005 (file deletion + masquerading)            |
| 4    | Collection            | T1005 Data from Local System                                    |
| 5    | Exfiltration          | T1041 Exfiltration Over C2 Channel (curl POST signature)        |

*Dropped vs paper:* Reconnaissance (T1595.002 active scanning), Initial Access (manual CVE exploit).

---

### APT29 — Cozy Bear (Russian SVR)

> *Paper: "stealthy adversary group … utilizes different undetected malwares and custom tools for performing specific tasks like lateral movement, privilege escalation."*

Default obfuscator: **`base64jumble`** (auto-applied in `--apt APT29`) to drive `cmd_base64` / `cmd_eval_exec` features and exercise SecBERT against obfuscated commands.

| Step | Tactic                | MITRE techniques                                                |
|:----:|-----------------------|-----------------------------------------------------------------|
| 1    | Persistence           | T1098 Account Manipulation, T1136 Create Account                |
| 2    | Defense Evasion       | T1562.001 Disable/Modify Tools, T1070 Indicator Removal         |
| 3    | Lateral Movement      | T1021.004 Remote Services: SSH                                  |
| 4    | Privilege Escalation  | T1548.003 Sudo and Sudo Caching                                 |
| 5    | Discovery             | T1083 / T1033 (file + user discovery)                           |

*Dropped vs paper:* Initial Access (T1566 phishing), C2 (T1071.004 DNS contact switch).

---

### Turla — Snake / Uroburos (Russian government, Linux focus)

> *Paper: "diverse options for persistence via backdoor. It searches for the credentials and other sensitive information."*

Default obfuscator: `plain-text`.

| Step | Tactic                | MITRE techniques                                                |
|:----:|-----------------------|-----------------------------------------------------------------|
| 1    | Persistence           | T1037 Boot/Logon Init Scripts, T1136 Create Account             |
| 2    | Privilege Escalation  | T1548.003 Sudo and Sudo Caching                                 |
| 3    | Credential Access     | T1003.008 `/etc/shadow` dump, T1110.001 Password Guessing       |
| 4    | Discovery             | T1057 Process Discovery, T1082 System Info                      |
| 5    | Collection            | T1005 Data from Local System                                    |
| 6    | Defense Evasion       | T1070.006 Timestomp                                             |

*Dropped vs paper:* Initial Access (T1078 valid-accounts SSH login — needs pre-seeded creds).

---

### What the platform sees from APT mode vs flat-tactic mode

Same `alerts → detections → attack_chains → dqn_actions` writes. The **difference** is:

- **Tactic ordering** matters for `attack_chains.max_ckc_stage` — the Cyber Kill Chain mapper rewards a Discovery → … → Exfiltration progression. Random tactic order tops out earlier in CKC.
- The **GNN** sees a coherent host-graph evolution (one APT chain == one logical campaign on each victim).
- The **Transformer kill-chain predictor** has a real labelled trajectory to learn from instead of an unordered bag of tactics.

So `--apt APT41` and the same set of tactics fired alphabetically will produce **different** ML outputs even with identical Caldera abilities — order is part of the signal.

---

## Not auto-runnable (manual setup required)

| Tactic                       | Reason                                                                                 |
|------------------------------|----------------------------------------------------------------------------------------|
| Initial Access — `TA0001`    | T1190 (Exploit Public-Facing Application, e.g. Apache Struts CVE-2017-5638) needs a vulhub container on `strix_lab_net`. See [`docs/CALDERA_MITRE_SIMULATION_GUIDE.md` §5.2](../../../docs/CALDERA_MITRE_SIMULATION_GUIDE.md). |
| Reconnaissance — `TA0043`    | Pre-implant phase. Caldera is post-implant by design — out of scope.                   |
| Command & Control — `TA0011` | Sandcat *is* the C2 channel — every ability uses it implicitly (T1071.001 HTTP beacon). No separate tactic needed. |

---

## Adversary resolution algorithm (per tactic)

1. **Exact-name lookup** in the stockpile (case-insensitive) against the `stockpile_names` list.
2. If not found → **ad-hoc construction**:
   - `GET /api/v2/abilities`.
   - Filter to abilities whose `technique_id` matches one of the tactic's `technique_ids` (subtechnique-aware: `T1003` matches `T1003.008`).
   - Filter further to `executors[].platform ∈ {linux, darwin}`.
   - Pick **one** ability per technique (first match wins).
   - `POST /api/v2/adversaries` with `atomic_ordering = [picked_ability_ids]`, then run an op against that transient adversary.
3. If no abilities match at all → **skip with warning** (logged in the tactic result; final report shows `skipped:no-linux-abilities-for-T#### …`).

Substring/fuzzy stockpile matching is **deliberately disabled** to prevent pulling Windows-only adversaries (e.g. `Lateral Movement - Certutil`) when only the Linux variant is wanted.

---

## What the script writes to Postgres per fired tactic

Per Caldera link that produces an audit `EXECVE` matching `key=audit-wazuh-x`:

- **1 row in `alerts`** — skeleton FK target (`raw_jsonb={}` is by design until Phase 5+)
- **1 row in `detections`** — full 5-model output: AE, VAE, Transformer, GNN, DQN state vector
- **0..1 row in `attack_chains`** — new chain opened or existing chain extended (`step_count` / `max_ckc_stage` updated)
- **1 row in `dqn_actions`** — one of `NO_OP`, `NOTIFY`, `BLOCK_USER_IP`, `ISOLATE_HOST`

The final report card prints per-tactic deltas across all four tables plus the DQN action mix and CKC stage histogram.

---

## Quick command reference

```bash
# Full real-time run — all 9 paper tactics, per-tactic + final report
bash infra/scripts/lab_simulate.sh

# Plan only, fire nothing (resolves stockpile vs ad-hoc per tactic)
bash infra/scripts/lab_simulate.sh --dry-run

# Just current platform state
bash infra/scripts/lab_simulate.sh --report-only

# Stockpile inventory (live Caldera GET)
bash infra/scripts/lab_simulate.sh --list

# APT-group emulation
bash infra/scripts/lab_simulate.sh --list-apts
bash infra/scripts/lab_simulate.sh --apt APT41
bash infra/scripts/lab_simulate.sh --apt APT29        # auto-applies base64jumble
bash infra/scripts/lab_simulate.sh --apt all          # all four, back to back

# Subset / pacing / obfuscator overrides
bash infra/scripts/lab_simulate.sh --only Discovery,Collection,Exfiltration
bash infra/scripts/lab_simulate.sh --budget 120 --dwell 45
bash infra/scripts/lab_simulate.sh --obfuscator base64jumble    # SecBERT stress
```
