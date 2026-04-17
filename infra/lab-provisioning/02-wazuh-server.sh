#!/usr/bin/env bash
# Wazuh SIEM server: all-in-one install (Manager + Indexer + Dashboard + Filebeat).
# Reference: https://documentation.wazuh.com/current/quickstart.html
#
# Usage:  sudo ./02-wazuh-server.sh
set -euo pipefail

WAZUH_VERSION="${WAZUH_VERSION:-4.9}"
INSTALL_DIR="/root/wazuh-install"

[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }

mkdir -p "${INSTALL_DIR}"
cd "${INSTALL_DIR}"

echo "[*] Opening Wazuh ports in UFW"
ufw allow 1514/udp    # agents -> manager (events)
ufw allow 1514/tcp
ufw allow 1515/tcp    # agent registration
ufw allow 55000/tcp   # Wazuh REST API
ufw allow 9200/tcp    # Indexer (OpenSearch)
ufw allow 443/tcp     # Dashboard

if [[ ! -f wazuh-install.sh ]]; then
  echo "[*] Downloading wazuh-install.sh (${WAZUH_VERSION})"
  curl -sO "https://packages.wazuh.com/${WAZUH_VERSION}/wazuh-install.sh"
  curl -sO "https://packages.wazuh.com/${WAZUH_VERSION}/config.yml"
fi

if [[ -f /var/ossec/bin/wazuh-control ]]; then
  echo "[=] Wazuh manager already installed; skipping installer."
else
  echo "[*] Running all-in-one installer (this takes 5-10 minutes)"
  bash wazuh-install.sh -a
fi

echo
echo "[*] Extracting generated passwords"
if [[ -f wazuh-install-files.tar ]]; then
  tar -xf wazuh-install-files.tar -C "${INSTALL_DIR}" 2>/dev/null || true
fi

LAN_IP=$(hostname -I | awk '{print $1}')
echo
echo "=============================================================="
echo "  Wazuh Dashboard:  https://${LAN_IP}"
echo "  Indexer API:      https://${LAN_IP}:9200"
echo "  Wazuh API:        https://${LAN_IP}:55000"
echo "  Credentials file: ${INSTALL_DIR}/wazuh-install-files/wazuh-passwords.txt"
echo "                    (or inside wazuh-install-files.tar)"
echo "=============================================================="
echo
echo "[+] Wazuh server setup complete."
echo "    Next: run 02-victim.sh on each victim with WAZUH_MANAGER=${LAN_IP}"

###############################################################################
# Deploy STRIX custom rules (Caldera/APT-aware overlay on top of MITRE defaults)
###############################################################################
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_RULES_SRC="${SCRIPT_DIR}/wazuh/local_rules.xml"
LOCAL_RULES_DST="/var/ossec/etc/rules/local_rules.xml"
if [[ -f "${LOCAL_RULES_SRC}" ]]; then
  echo "[*] Installing STRIX local_rules.xml -> ${LOCAL_RULES_DST}"
  [[ -f "${LOCAL_RULES_DST}" ]] && cp "${LOCAL_RULES_DST}" "${LOCAL_RULES_DST}.bak.$(date +%s)"
  install -m 0640 -o root -g wazuh "${LOCAL_RULES_SRC}" "${LOCAL_RULES_DST}"
else
  echo "[!] ${LOCAL_RULES_SRC} not found — skipping custom rules"
fi

echo "[*] Restarting manager to load rules"
systemctl restart wazuh-manager || true
