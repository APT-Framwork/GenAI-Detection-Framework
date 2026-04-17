#!/usr/bin/env bash
# Attacker VM: installs Docker and runs the Caldera C2 container.
# Idempotent: safe to re-run.
#
# Usage:  sudo ./01-attacker-caldera.sh
# Env:
#   CALDERA_DIR             default: /opt/caldera
#   CALDERA_PORT            default: 8888
#   CALDERA_RED_PASSWORD    if unset, prompts interactively
#   CALDERA_BLUE_PASSWORD   if unset, prompts interactively
set -euo pipefail

CALDERA_DIR="${CALDERA_DIR:-/opt/caldera}"
CALDERA_PORT="${CALDERA_PORT:-8888}"

[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }

###############################################################################
# Collect new Caldera credentials up-front (human interaction step).
# We apply them after first boot once conf/local.yml is generated.
###############################################################################
prompt_password() {
  local label="$1" var
  local p1="" p2=""
  while :; do
    read -rsp "  New password for '${label}' user: " p1; echo
    read -rsp "  Confirm password for '${label}' user: " p2; echo
    if [[ -z "$p1" ]]; then
      echo "  !! empty password rejected, try again"; continue
    fi
    if [[ "$p1" != "$p2" ]]; then
      echo "  !! passwords do not match, try again"; continue
    fi
    printf -v "$2" '%s' "$p1"
    break
  done
}

echo "[*] Caldera credential setup (human interaction required)"
if [[ -z "${CALDERA_RED_PASSWORD:-}" ]]; then
  prompt_password "red"  CALDERA_RED_PASSWORD
fi
if [[ -z "${CALDERA_BLUE_PASSWORD:-}" ]]; then
  prompt_password "blue" CALDERA_BLUE_PASSWORD
fi

echo "[*] Installing Docker engine"
if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu $(. /etc/os-release; echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
fi

echo "[*] Opening Caldera ports in UFW"
ufw allow "${CALDERA_PORT}/tcp"   # Web UI + HTTP contact
ufw allow 7010/tcp                # HTTP contact (alt)
ufw allow 7011/udp                # UDP contact
ufw allow 7012/tcp                # TCP contact
ufw allow 8080/tcp                # payload staging HTTP server (Paper 1)

echo "[*] Cloning / updating Caldera in ${CALDERA_DIR}"
if [[ ! -d "${CALDERA_DIR}/.git" ]]; then
  git clone https://github.com/mitre/caldera.git --recursive "${CALDERA_DIR}"
else
  git -C "${CALDERA_DIR}" pull --recurse-submodules
fi

echo "[*] Building Caldera image (full variant)"
cd "${CALDERA_DIR}"
docker build --build-arg VARIANT=full -t caldera:local .

echo "[*] Persistent dirs for conf + data"
mkdir -p "${CALDERA_DIR}/persist/conf" "${CALDERA_DIR}/persist/data"

echo "[*] (Re)starting caldera container"
docker rm -f caldera 2>/dev/null || true
docker run -d --name caldera --restart unless-stopped \
  -p ${CALDERA_PORT}:8888 \
  -p 7010:7010 -p 7011:7011/udp -p 7012:7012 \
  -v "${CALDERA_DIR}/persist/conf":/usr/src/app/conf \
  -v "${CALDERA_DIR}/persist/data":/usr/src/app/data \
  caldera:local

###############################################################################
# Wait for Caldera to generate conf/local.yml, then rewrite the user passwords
# and restart the container so the new creds take effect.
###############################################################################
LOCAL_YML="${CALDERA_DIR}/persist/conf/local.yml"
echo "[*] Waiting for Caldera to generate ${LOCAL_YML} ..."
for i in $(seq 1 60); do
  [[ -s "$LOCAL_YML" ]] && break
  sleep 2
done
if [[ ! -s "$LOCAL_YML" ]]; then
  echo "[!] Timed out waiting for local.yml. Check: docker logs caldera" >&2
  exit 1
fi

echo "[*] Ensuring python3 + PyYAML are available for YAML patching"
apt-get install -y python3 python3-yaml >/dev/null

echo "[*] Rewriting red/blue passwords in local.yml"
CALDERA_RED_PASSWORD="${CALDERA_RED_PASSWORD}" \
CALDERA_BLUE_PASSWORD="${CALDERA_BLUE_PASSWORD}" \
LOCAL_YML="${LOCAL_YML}" \
python3 - <<'PY'
import os, yaml, sys, shutil
path = os.environ["LOCAL_YML"]
red  = os.environ["CALDERA_RED_PASSWORD"]
blue = os.environ["CALDERA_BLUE_PASSWORD"]
shutil.copy2(path, path + ".bak")
with open(path) as f:
    cfg = yaml.safe_load(f) or {}
users = cfg.setdefault("users", {})
# Caldera v5 layout: users: { red: {red: <pw>}, blue: {blue: <pw>} }
users.setdefault("red",  {})["red"]  = red
users.setdefault("blue", {})["blue"] = blue
with open(path, "w") as f:
    yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)
print(f"[+] Updated users in {path} (backup at {path}.bak)")
PY
chmod 600 "$LOCAL_YML"

echo "[*] Restarting caldera to apply new credentials"
docker restart caldera >/dev/null

###############################################################################
# Payload staging HTTP server (Syed et al. 2025 — Attack Box hosts file share)
###############################################################################
PAYLOAD_DIR="${CALDERA_DIR}/payloads"
mkdir -p "${PAYLOAD_DIR}"
cat >/etc/systemd/system/strix-payload-server.service <<EOF
[Unit]
Description=STRIX payload staging HTTP server (red-team file share)
After=network-online.target

[Service]
Type=simple
WorkingDirectory=${PAYLOAD_DIR}
ExecStart=/usr/bin/python3 -m http.server 8080 --bind 0.0.0.0
Restart=always

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now strix-payload-server.service

LAN_IP=$(hostname -I | awk '{print $1}')
echo
echo "=============================================================="
echo "  Caldera UI:       http://${LAN_IP}:${CALDERA_PORT}"
echo "  Payload staging:  http://${LAN_IP}:8080/   (drop files in ${PAYLOAD_DIR})"
echo "  Users:            red  (new password set)"
echo "                    blue (new password set)"
echo "  Config:           ${LOCAL_YML}  (mode 600, backup: ${LOCAL_YML}.bak)"
echo "  API key:          grep api_key_red ${LOCAL_YML}"
echo "=============================================================="
echo
echo "[+] Attacker setup complete."
echo "    Next: on each victim run 03-victim.sh with CALDERA_SERVER=http://${LAN_IP}:${CALDERA_PORT}"
