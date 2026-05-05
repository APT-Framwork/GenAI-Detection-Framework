#!/usr/bin/env bash
# =============================================================================
# recon_burst.sh — pre-implant reconnaissance burst against victim hosts.
#
# Runs INSIDE strix_attacker. The simulator drives it via:
#     docker exec strix_attacker /opt/recon_burst.sh victim1 victim2
#
# What it produces (and why each step matters for stage-1 telemetry):
#
#   1. nmap port scan      — covers TCP/22,80,443 + a thin top-100 sweep.
#                            Real packets land on the victim; sshd logs
#                            connection bursts → Wazuh stock rule 5712 fires
#                            → STRIX rule 100051 chains → tagged T1595.
#
#   2. SSH invalid-user    — explicit attempts with bogus usernames. sshd
#      enumeration           writes "Invalid user X from <attacker>" → Wazuh
#                            rule 5710 fires → STRIX rule 100050 chains →
#                            tagged T1595.002. This is the loud one, gives
#                            a clean per-event ckc_stage=1 signal even if
#                            nmap somehow doesn't.
#
#   3. HTTP URI sweep      — best-effort: only generates alerts if any of
#      (best-effort)         the victims runs a web server. Most lab images
#                            don't, so we don't depend on it for stage-1
#                            output, but it's free signal when present.
#
# Tuning:
#   RECON_SSH_ATTEMPTS  — count of bogus-user SSH attempts per victim
#                          (default 12). Higher = louder but takes longer.
#   RECON_BURST_SECONDS — soft cap on total time spent (default 30s);
#                          reaching the cap stops further attempts.
# =============================================================================
set -uo pipefail   # NOT -e: each probe is allowed to fail individually

VICTIMS=("$@")
if [[ ${#VICTIMS[@]} -eq 0 ]]; then
  echo "[recon_burst] usage: $0 <victim1> [victim2 ...]" >&2
  exit 1
fi

ATTEMPTS="${RECON_SSH_ATTEMPTS:-12}"
DEADLINE=$(( $(date +%s) + ${RECON_BURST_SECONDS:-30} ))

# Bogus-user dictionary. Picked to look like a real recon attempt — admin
# accounts, common service users, "test" accounts. NONE exist on the
# victim images, so every attempt fails with rule-5710 "Invalid user".
USERS=(admin oracle ftp postgres mysql backup test guest deploy svc git ubuntu)

log() { echo "[$(date +%H:%M:%S)] $*"; }

# --- 1) nmap ----------------------------------------------------------------
log "phase 1/3: nmap port scan against ${VICTIMS[*]}"
for v in "${VICTIMS[@]}"; do
  [[ $(date +%s) -ge $DEADLINE ]] && break
  # -Pn  : skip ICMP host-up check (lab containers may not respond to ping)
  # -sT  : full TCP connect — auditd-visible from the victim's sshd process
  # --top-ports 100 + 22,80,443 : explicit common ports + a small sweep
  # -T4  : aggressive timing; we don't care about IDS evasion in the demo
  # --max-retries 1 : keep the burst tight
  nmap -Pn -sT -T4 --max-retries 1 \
       -p 22,80,443,$(seq -s, 1 100 | head -c 200) "$v" >/dev/null 2>&1 \
    && log "  nmap $v OK" \
    || log "  nmap $v rc=$?"
done

# --- 2) SSH invalid-user enumeration ---------------------------------------
log "phase 2/3: SSH invalid-user enumeration ($ATTEMPTS attempts/victim)"
for v in "${VICTIMS[@]}"; do
  [[ $(date +%s) -ge $DEADLINE ]] && break
  fired=0
  for u in "${USERS[@]}"; do
    [[ $fired -ge $ATTEMPTS ]] && break
    [[ $(date +%s) -ge $DEADLINE ]] && break
    # PreferredAuthentications=password keeps us off pubkey path → forces
    # a real password prompt, which sshd refuses and logs "Invalid user".
    # BatchMode=yes avoids interactive password prompts hanging forever.
    ssh \
      -o StrictHostKeyChecking=no \
      -o UserKnownHostsFile=/dev/null \
      -o BatchMode=yes \
      -o ConnectTimeout=2 \
      -o PreferredAuthentications=password \
      -o PubkeyAuthentication=no \
      -o GSSAPIAuthentication=no \
      "$u@$v" 'true' </dev/null >/dev/null 2>&1
    fired=$(( fired + 1 ))
  done
  log "  ssh@$v fired $fired probes"
done

# --- 3) HTTP URI sweep (best-effort) ---------------------------------------
log "phase 3/3: HTTP URI sweep (best-effort)"
PATHS=(/admin /phpmyadmin /.env /wp-login.php /server-status /actuator /config /backup)
for v in "${VICTIMS[@]}"; do
  [[ $(date +%s) -ge $DEADLINE ]] && break
  for p in "${PATHS[@]}"; do
    [[ $(date +%s) -ge $DEADLINE ]] && break
    curl -s --max-time 2 -o /dev/null -w "" "http://$v$p" 2>/dev/null || true
  done
done

log "recon burst complete"
