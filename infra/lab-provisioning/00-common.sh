#!/usr/bin/env bash
# Shared prep: time sync, firewall baseline, utilities.
# Run on EVERY VM (attacker, wazuh server, victims) before its role script.
set -euo pipefail

require_root() {
  if [[ $EUID -ne 0 ]]; then
    echo "[!] Re-run with sudo: sudo $0" >&2
    exit 1
  fi
}
require_root

echo "[*] apt update + base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y curl wget gnupg lsb-release ca-certificates \
                   chrony ufw net-tools jq unzip

echo "[*] Enable chrony (time sync is critical for Caldera<->Wazuh correlation)"
systemctl enable --now chrony
chronyc -a makestep || true

echo "[*] UFW baseline (permissive on LAN, deny from WAN recommended)"
ufw --force reset >/dev/null
ufw default allow outgoing
ufw default deny incoming
ufw allow 22/tcp
# role scripts will open role-specific ports
ufw --force enable

echo "[+] Common prep done on $(hostname) ($(hostname -I | awk '{print $1}'))"
