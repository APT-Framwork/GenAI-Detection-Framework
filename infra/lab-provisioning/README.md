# STRIX Lab — Final Simulation Plan & Provisioning Scripts

Emulates the 3-tier APT testbed from **Syed et al. (IEEE Networking Letters 2025)** and the Wazuh-centric Linux telemetry approach from **Karim et al. (Data in Brief 2024)**. Produces labeled, MITRE-tagged alerts for the STRIX GenAI detection pipeline.

## Final topology

```
  Attack Box (VM1)            Monitor Box (VM2)            Target Devices (VM3-VM5)
  ┌──────────────────┐        ┌──────────────────────┐     ┌────────────────────────┐
  │ Caldera (Docker) │◄──C2──►│ Wazuh Manager        │◄────│ Wazuh Agent            │
  │   :8888 UI       │        │ Wazuh Indexer :9200  │     │ auditd (50+ rules)     │
  │   :7010-7012 C2  │        │ Wazuh Dashboard :443 │     │ Sandcat (systemd)      │
  │ HTTP payloads    │        │ Filebeat             │     │ FIM + rootcheck        │
  │   :8080          │        │ local_rules.xml      │     │ full_command monitors  │
  └──────────────────┘        └──────────────────────┘     └────────────────────────┘
         │                              ▲
         └──── /api/v2/operations ──────┘ (pulled by STRIX backend)
                                        ▲
                                        │ Indexer _search (pulled by STRIX backend)
                                        ▼
                                ┌──────────────────────┐
                                │  STRIX Backend       │
                                │  (FastAPI + Celery)  │
                                │  correlate + emit WS │
                                └──────────────────────┘
```

## VM inventory — recommended vs minimum

| VM  | Role                         | Required?              | Scripts                                      |
| --- | ---------------------------- | ---------------------- | -------------------------------------------- |
| VM1 | Attacker (Caldera + payload HTTP :8080) | **yes**    | `00-common.sh` → `01-attacker-caldera.sh`    |
| VM2 | Monitor (Wazuh Mgr+Indexer+Dashboard)   | **yes**    | `00-common.sh` → `02-wazuh-server.sh`        |
| VM3 | Victim A (subnet A)                     | **yes**    | `00-common.sh` → `03-victim.sh`              |
| VM4 | Victim B (subnet A)                     | **yes**    | `00-common.sh` → `03-victim.sh`              |
| VM5 | Victim C (subnet B — lateral movement)  | *recommended* | `00-common.sh` → `03-victim.sh`           |
| VM6 | Windows Victim (Sysmon + Wazuh agent)   | optional   | (separate Windows script — not yet written)  |

### If you only have 4 VMs
Combine VM1 and VM2 on a single box: run both `01-attacker-caldera.sh` and `02-wazuh-server.sh` there. You give up isolation (the attacker box is also the SIEM) but it works for a demo. Use VM2/3/4 as victims.

### Minimum to match the papers
- Syed et al.: 1 attacker + ≥1 Windows + ≥1 Linux target + 1 monitor (ELK). We substitute Wazuh for ELK.
- Karim et al.: 1 attacker + 3 Linux endpoints across 2 subnets + 1 SIEM + 1 AV. We skip the AV for the demo; adding it later is trivial.

**Recommendation: 5 VMs** (split attacker/SIEM, 3 Linux victims across 2 subnets). This is the smallest config that stays faithful to both papers.

## Network

Two virtual networks via your hypervisor (VirtualBox host-only / libvirt bridge):
- `192.168.217.0/24` — VM1, VM2, VM3, VM4
- `192.168.158.0/24` — VM5 (reachable from VM1 for C2, from VM2 for agent registration)

Chrony time-sync is enforced by `00-common.sh`. Without it Caldera↔Wazuh timestamp correlation breaks.

## Run order

```bash
# On every VM first
sudo ./00-common.sh

# VM1 (attacker)  — prompts for red/blue passwords
sudo ./01-attacker-caldera.sh

# VM2 (monitor)
sudo ./02-wazuh-server.sh
# Note the generated admin password from /root/wazuh-install/wazuh-install-files.tar

# VM3/VM4/VM5 (victims)
sudo WAZUH_MANAGER=<VM2_IP> \
     CALDERA_SERVER=http://<VM1_IP>:8888 \
     ./03-victim.sh
```

## What each role installs

### VM1 — Attacker
- Docker engine + Caldera `full` image (built locally, persisted `conf/` + `data/`)
- Ports: 8888 (UI), 7010-7012 (agent contacts), 8080 (payload HTTP share)
- Systemd unit `strix-payload-server` hosts `/opt/caldera/payloads`
- Auto-rotates `red` and `blue` default passwords via interactive prompt (or env vars `CALDERA_RED_PASSWORD` / `CALDERA_BLUE_PASSWORD`)

### VM2 — Monitor (Wazuh all-in-one)
- Official `wazuh-install.sh -a` → Manager + Indexer (OpenSearch) + Dashboard + Filebeat
- Ports: 1514/1515 (agents), 55000 (API), 9200 (indexer), 443 (dashboard)
- **Custom overlay**: [`wazuh/local_rules.xml`](wazuh/local_rules.xml) installed into `/var/ossec/etc/rules/local_rules.xml` — Caldera-aware rules on top of Wazuh 4.9's default MITRE ruleset. Covers Discovery, Credential Access, Persistence, Privilege Escalation, Defense Evasion, C2, payload drops.

### VM3-VM5 — Victims
- **auditd**: ~50 rules (Karim et al. "33 resources" pattern) — syscalls (execve, connect, ptrace, setuid), identity files, sudoers/PAM, cron/systemd/rc persistence, payload drop zones, LOLBAS-like tool exec, log tampering
- **Wazuh agent**: expanded `ossec.conf` with
  - Localfile blocks for auth/syslog/kern/dpkg/ufw/cron/journald/apache/nginx
  - Periodic `full_command` monitors (`netstat`, `ss`, `last`, `ps`, `who`, cron snapshot)
  - `syscheck` FIM over `/etc /usr/bin /usr/sbin /bin /sbin /boot /root /home /tmp /var/tmp /dev/shm /opt` plus persistence paths in realtime
  - `rootcheck` (files/trojans/ports/pids)
- **Sandcat** (Caldera agent) as systemd service, group = `red`

## Adversary profiles to run (start set)

Both papers converge on these as high-signal profiles:

1. **APT41** (both papers) — broad coverage, Discovery → Persistence → Exfil.
2. **APT29** (both papers) — stealthy lateral movement, credential access.
3. **APT28** (Karim) — exploit + remote access + data manipulation.
4. **Turla** (Karim) — backdoor persistence, credential search.
5. **Discovery** (Caldera built-in) — smoke test for pipeline.

Caldera ships ATT&CK-mapped implementations of all of these.

## Output schema (STRIX `DetectionEvent`)

Matches the Karim et al. field set — richer than Syed's:

```
id, ts, host, source (wazuh|caldera), severity, rule_id, rule_description,
mitre_tactic, mitre_technique_id, mitre_technique_name,
file_md5, file_sha256, src_ip, src_port, dst_ip, dst_port,
pci_dss, hipaa, nist_800_53,
caldera_operation_id?, caldera_ability_id?, label (benign|simulated_attack|unknown),
raw
```

## Pipeline to STRIX backend (next phase)

1. **Celery `pull_wazuh_alerts`** — polls `wazuh-alerts-*` on VM2:9200, search_after cursor.
2. **Celery `pull_caldera_operations`** — polls VM1:8888 `/api/v2/operations`, caches ability links in Redis.
3. **Correlator** — joins Wazuh alert to Caldera ability by `host + |Δt| ≤ 30s`, sets `label=simulated_attack` + `caldera_*` fields.
4. **Postgres** — canonical `DetectionEvent` table.
5. **Socket.IO `/vigilance`** — emits `new_event` to web + mobile.

## Verification checklist

- [ ] `docker ps` on VM1 shows `caldera` healthy.
- [ ] `curl http://VM1:8080/` returns the payload directory listing.
- [ ] Wazuh Dashboard (`https://VM2`) → Agents shows all victims **Active**.
- [ ] On VM2: `/var/ossec/bin/wazuh-logtest` loads without rule errors.
- [ ] Run Caldera "Discovery" op → within 30s Wazuh Dashboard → Threat Hunting shows alerts with `rule.mitre.id` populated.
- [ ] At least one alert matches a custom `1001xx` rule from `local_rules.xml`.

## Notes

- All scripts are idempotent; safe to re-run.
- Assumes Ubuntu 22.04+ with `apt`.
- Caldera default creds are rotated automatically by `01-attacker-caldera.sh`.
- Wazuh admin passwords live in `/root/wazuh-install/wazuh-install-files.tar` on VM2.
- Windows target script is not provided yet — ask if you want one (PowerShell + Sysmon + Winlogbeat + Wazuh agent MSI).
