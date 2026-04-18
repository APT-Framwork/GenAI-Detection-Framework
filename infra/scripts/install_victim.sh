#!/usr/bin/env bash
# =============================================================================
# STRIX victim VM bootstrap — installs:
#   1. Wazuh Agent  (reports alerts to the manager on VM 1)
#   2. Caldera sandcat agent (so Caldera on VM 2 can drive attacks)
#
# Usage:
#   sudo MANAGER_IP=10.0.0.10 CALDERA_IP=10.0.0.11 ./install_victim.sh
#
# Optional env:
#   AGENT_GROUP   — Wazuh agent group        (default: default)
#   WAZUH_VERSION — Wazuh agent version       (default: 4.9.2-1)
#   CALDERA_GROUP — Caldera operation group  (default: red)
#
# Designed to be idempotent — re-running won't break anything, it just
# updates the manager IP / re-enrolls.
# =============================================================================

set -euo pipefail

: "${MANAGER_IP:?MANAGER_IP env var required (Wazuh manager / VM 1)}"
: "${CALDERA_IP:?CALDERA_IP env var required (Caldera attacker / VM 2)}"

AGENT_GROUP="${AGENT_GROUP:-default}"
WAZUH_VERSION="${WAZUH_VERSION:-4.9.2-1}"
CALDERA_GROUP="${CALDERA_GROUP:-red}"

GREEN='\033[32m'; YELLOW='\033[33m'; RED='\033[31m'; DIM='\033[2m'; RESET='\033[0m'
log() { printf "${GREEN}▶${RESET} %s\n" "$*"; }
warn() { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }
fail() { printf "${RED}✗${RESET} %s\n" "$*"; exit 1; }

if [[ "$EUID" -ne 0 ]]; then
  fail "must run as root (use sudo)"
fi

# ----------------------------------------------------------------------
# 0. Time sync — silently breaks Wazuh enrollment if skewed > 30s
# ----------------------------------------------------------------------
log "Enabling NTP time sync (Wazuh enrollment is timestamp-sensitive)…"
timedatectl set-ntp true || warn "couldn't toggle NTP — check chrony/systemd-timesyncd"

# ----------------------------------------------------------------------
# 1. Wazuh agent
# ----------------------------------------------------------------------
DEB="wazuh-agent_${WAZUH_VERSION}_amd64.deb"
URL="https://packages.wazuh.com/4.x/apt/pool/main/w/wazuh-agent/${DEB}"

log "Downloading Wazuh agent ${WAZUH_VERSION}…"
cd /tmp && curl -sSLO "$URL" || fail "agent download failed: $URL"

log "Installing Wazuh agent (manager=${MANAGER_IP}, group=${AGENT_GROUP})…"
WAZUH_MANAGER="$MANAGER_IP" \
WAZUH_AGENT_GROUP="$AGENT_GROUP" \
  dpkg -i "/tmp/${DEB}"

systemctl daemon-reload
systemctl enable --now wazuh-agent

# Wait for enrollment.
log "Waiting for agent to register with manager…"
for _ in {1..15}; do
  if grep -q "Connected to the server" /var/ossec/logs/ossec.log 2>/dev/null; then
    log "${GREEN}Wazuh agent connected.${RESET}"
    break
  fi
  sleep 2
done
grep -q "Connected to the server" /var/ossec/logs/ossec.log 2>/dev/null \
  || warn "agent not yet connected — check /var/ossec/logs/ossec.log + manager firewall (1514/1515)"

# ----------------------------------------------------------------------
# 2. Caldera sandcat agent (so VM 2 can drive operations against this host)
# ----------------------------------------------------------------------
log "Downloading Caldera sandcat (server=${CALDERA_IP}:8888)…"
SANDCAT_URL="http://${CALDERA_IP}:8888/file/download"

# The X-Header trio tells Caldera which build to compile + return.
curl -sSf -X POST \
  -H "file: sandcat.go" \
  -H "platform: linux" \
  -H "gocat-extensions: shells,proc,donut" \
  "$SANDCAT_URL" -o /usr/local/bin/sandcat \
  || fail "sandcat download failed — is Caldera running on http://${CALDERA_IP}:8888?"

chmod +x /usr/local/bin/sandcat

# Tiny systemd unit so sandcat survives reboots.
cat >/etc/systemd/system/sandcat.service <<EOF
[Unit]
Description=Caldera sandcat agent (lab attack target)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/sandcat -server http://${CALDERA_IP}:8888 -group ${CALDERA_GROUP}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now sandcat

# ----------------------------------------------------------------------
# 3. Done
# ----------------------------------------------------------------------
echo
log "${GREEN}Victim VM ready.${RESET}"
echo "  ${DIM}- Wazuh agent  → ${MANAGER_IP}:1514${RESET}"
echo "  ${DIM}- Sandcat       → ${CALDERA_IP}:8888 (group=${CALDERA_GROUP})${RESET}"
echo
echo "Verify from VM 1 (Wazuh manager):"
echo "  ${DIM}docker exec wazuh.manager /var/ossec/bin/agent_control -l${RESET}"
echo "Verify from VM 2 (Caldera dashboard → Agents tab):"
echo "  ${DIM}you should see one entry per victim with paw, host, group=${CALDERA_GROUP}${RESET}"
