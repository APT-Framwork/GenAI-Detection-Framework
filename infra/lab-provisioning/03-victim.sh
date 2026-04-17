#!/usr/bin/env bash
# Victim VM: installs Wazuh agent + auditd + deploys Caldera Sandcat agent.
#
# Usage:
#   sudo WAZUH_MANAGER=192.168.56.10 \
#        CALDERA_SERVER=http://192.168.56.10:8888 \
#        ./03-victim.sh
#
# Env:
#   WAZUH_MANAGER      (required) IP/host of the Wazuh manager
#   CALDERA_SERVER     (required) e.g. http://192.168.56.10:8888
#   WAZUH_AGENT_GROUP  default: victims
#   CALDERA_GROUP      default: red
#   SANDCAT_DIR        default: /opt/sandcat
set -euo pipefail

: "${WAZUH_MANAGER:?set WAZUH_MANAGER=<ip>}"
: "${CALDERA_SERVER:?set CALDERA_SERVER=http://<ip>:8888}"
WAZUH_AGENT_GROUP="${WAZUH_AGENT_GROUP:-victims}"
CALDERA_GROUP="${CALDERA_GROUP:-red}"
SANDCAT_DIR="${SANDCAT_DIR:-/opt/sandcat}"
WAZUH_VERSION="${WAZUH_VERSION:-4.9}"

[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }

###############################################################################
# 1. auditd + sysmon-like coverage so Caldera TTPs actually generate events
###############################################################################
echo "[*] Installing auditd"
apt-get update -y
apt-get install -y auditd audispd-plugins curl wget gnupg

cat >/etc/audit/rules.d/caldera.rules <<'EOF'
## Caldera / APT telemetry — aligned with Karim et al. 2024 "33 Linux resources"

# --- processes & syscalls ---
-a exit,always -F arch=b64 -S execve -k proc_exec
-a exit,always -F arch=b32 -S execve -k proc_exec
-a exit,always -F arch=b64 -S connect -k net_connect
-a exit,always -F arch=b64 -S ptrace  -k proc_inject
-a exit,always -F arch=b64 -S setuid -S setgid -S setreuid -S setregid -k priv_change

# --- identity & auth ---
-w /etc/passwd        -p wa -k identity
-w /etc/shadow        -p wa -k identity
-w /etc/group         -p wa -k identity
-w /etc/gshadow       -p wa -k identity
-w /etc/sudoers       -p wa -k sudoers
-w /etc/sudoers.d/    -p wa -k sudoers
-w /etc/pam.d/        -p wa -k pam
-w /etc/ssh/sshd_config -p wa -k sshd_conf

# --- persistence paths ---
-w /etc/crontab        -p wa -k cron
-w /etc/cron.d/        -p wa -k cron
-w /etc/cron.hourly/   -p wa -k cron
-w /etc/cron.daily/    -p wa -k cron
-w /var/spool/cron/    -p wa -k cron
-w /etc/systemd/system/ -p wa -k systemd_unit
-w /lib/systemd/system/ -p wa -k systemd_unit
-w /etc/rc.local       -p wa -k rc_local
-w /etc/init.d/        -p wa -k init_scripts
-w /root/.bashrc       -p wa -k shell_rc
-w /root/.profile      -p wa -k shell_rc

# --- sensitive directories / payload drop zones ---
-w /tmp     -p wa -k tmp_write
-w /dev/shm -p wa -k shm_write
-w /var/tmp -p wa -k tmp_write
-w /opt     -p wa -k opt_write
-w /root/.ssh  -p wa -k ssh_keys
-w /home       -p wa -k home_write

# --- binaries commonly leveraged by APTs (LOLBAS-like) ---
-w /usr/bin/nc         -p x -k tool_exec
-w /usr/bin/ncat       -p x -k tool_exec
-w /usr/bin/wget       -p x -k tool_exec
-w /usr/bin/curl       -p x -k tool_exec
-w /usr/bin/ssh        -p x -k tool_exec
-w /usr/bin/scp        -p x -k tool_exec
-w /usr/bin/rsync      -p x -k tool_exec
-w /usr/bin/base64     -p x -k tool_exec
-w /usr/bin/python3    -p x -k tool_exec
-w /usr/bin/perl       -p x -k tool_exec

# --- log tampering (T1070) ---
-w /var/log/wtmp   -p wa -k log_tamper
-w /var/log/btmp   -p wa -k log_tamper
-w /var/log/lastlog -p wa -k log_tamper
-w /var/log/auth.log -p wa -k log_tamper
EOF
augenrules --load || true
systemctl enable --now auditd

###############################################################################
# 2. Wazuh agent
###############################################################################
if ! command -v /var/ossec/bin/wazuh-control >/dev/null 2>&1; then
  echo "[*] Adding Wazuh apt repo"
  curl -s https://packages.wazuh.com/key/GPG-KEY-WAZUH \
    | gpg --no-default-keyring --keyring gnupg-ring:/usr/share/keyrings/wazuh.gpg --import
  chmod 644 /usr/share/keyrings/wazuh.gpg
  echo "deb [signed-by=/usr/share/keyrings/wazuh.gpg] https://packages.wazuh.com/${WAZUH_VERSION}/apt/ stable main" \
    > /etc/apt/sources.list.d/wazuh.list
  apt-get update -y

  echo "[*] Installing wazuh-agent pointing at ${WAZUH_MANAGER}"
  WAZUH_MANAGER="${WAZUH_MANAGER}" \
  WAZUH_AGENT_GROUP="${WAZUH_AGENT_GROUP}" \
  WAZUH_AGENT_NAME="$(hostname)" \
  apt-get install -y wazuh-agent
else
  echo "[=] wazuh-agent already installed; reconfiguring manager IP"
  sed -i "s|<address>.*</address>|<address>${WAZUH_MANAGER}</address>|" /var/ossec/etc/ossec.conf
fi

echo "[*] Expanding FIM + log source coverage (Karim et al. 33-resource model)"
if ! grep -q "caldera-cmd-monitor" /var/ossec/etc/ossec.conf; then
  cat >>/var/ossec/etc/ossec.conf <<'EOF'
<!-- caldera-cmd-monitor: extended Linux log & command coverage -->
<ossec_config>

  <!-- ========== system / auth / kernel ========== -->
  <localfile><log_format>syslog</log_format><location>/var/log/auth.log</location></localfile>
  <localfile><log_format>syslog</log_format><location>/var/log/syslog</location></localfile>
  <localfile><log_format>syslog</log_format><location>/var/log/kern.log</location></localfile>
  <localfile><log_format>syslog</log_format><location>/var/log/dpkg.log</location></localfile>
  <localfile><log_format>syslog</log_format><location>/var/log/ufw.log</location></localfile>
  <localfile><log_format>syslog</log_format><location>/var/log/cron.log</location></localfile>
  <localfile><log_format>syslog</log_format><location>/var/log/faillog</location></localfile>
  <localfile><log_format>journald</log_format><location>journald</location></localfile>

  <!-- ========== audit (Caldera rules above) ========== -->
  <localfile><log_format>audit</log_format><location>/var/log/audit/audit.log</location></localfile>

  <!-- ========== app logs (present if installed) ========== -->
  <localfile><log_format>apache</log_format><location>/var/log/apache2/access.log</location></localfile>
  <localfile><log_format>apache</log_format><location>/var/log/apache2/error.log</location></localfile>
  <localfile><log_format>syslog</log_format><location>/var/log/nginx/access.log</location></localfile>
  <localfile><log_format>syslog</log_format><location>/var/log/nginx/error.log</location></localfile>

  <!-- ========== periodic command monitoring ========== -->
  <localfile>
    <log_format>full_command</log_format>
    <command>netstat -tulnp</command>
    <alias>listening_ports</alias>
    <frequency>120</frequency>
  </localfile>
  <localfile>
    <log_format>full_command</log_format>
    <command>ss -antp</command>
    <alias>active_connections</alias>
    <frequency>120</frequency>
  </localfile>
  <localfile>
    <log_format>full_command</log_format>
    <command>last -n 20</command>
    <alias>recent_logins</alias>
    <frequency>300</frequency>
  </localfile>
  <localfile>
    <log_format>full_command</log_format>
    <command>ps -eo pid,user,comm,args</command>
    <alias>process_list</alias>
    <frequency>120</frequency>
  </localfile>
  <localfile>
    <log_format>full_command</log_format>
    <command>who -a</command>
    <alias>active_users</alias>
    <frequency>300</frequency>
  </localfile>
  <localfile>
    <log_format>full_command</log_format>
    <command>crontab -l -u root 2>/dev/null; ls -la /etc/cron* 2>/dev/null</command>
    <alias>cron_snapshot</alias>
    <frequency>600</frequency>
  </localfile>

  <!-- ========== syscheck: broad FIM ========== -->
  <syscheck>
    <frequency>600</frequency>
    <scan_on_start>yes</scan_on_start>
    <alert_new_files>yes</alert_new_files>
    <auto_ignore>no</auto_ignore>
    <directories check_all="yes" report_changes="yes" realtime="yes">/etc,/usr/bin,/usr/sbin,/bin,/sbin,/boot</directories>
    <directories check_all="yes" report_changes="yes" realtime="yes">/root,/home</directories>
    <directories check_all="yes" report_changes="yes" realtime="yes">/tmp,/var/tmp,/dev/shm,/opt</directories>
    <directories check_all="yes" realtime="yes">/etc/systemd/system,/lib/systemd/system,/etc/cron.d,/etc/cron.hourly,/etc/cron.daily</directories>
    <ignore>/etc/mtab</ignore>
    <ignore>/etc/hosts.deny</ignore>
    <ignore>/etc/mail/statistics</ignore>
    <ignore>/etc/random-seed</ignore>
    <ignore>/etc/adjtime</ignore>
    <ignore>/etc/httpd/logs</ignore>
    <ignore>/etc/utmpx</ignore>
    <ignore>/etc/wtmpx</ignore>
    <ignore>/etc/cups/certs</ignore>
    <ignore>/etc/dumpdates</ignore>
    <ignore>/etc/svc/volatile</ignore>
  </syscheck>

  <!-- ========== rootcheck: policy & rootkit scans ========== -->
  <rootcheck>
    <disabled>no</disabled>
    <check_files>yes</check_files>
    <check_trojans>yes</check_trojans>
    <check_dev>yes</check_dev>
    <check_sys>yes</check_sys>
    <check_pids>yes</check_pids>
    <check_ports>yes</check_ports>
    <check_if>yes</check_if>
    <frequency>43200</frequency>
  </rootcheck>

</ossec_config>
EOF
fi

systemctl daemon-reload
systemctl enable --now wazuh-agent
systemctl restart wazuh-agent

###############################################################################
# 3. Caldera Sandcat agent
###############################################################################
echo "[*] Fetching Sandcat binary from ${CALDERA_SERVER}"
mkdir -p "${SANDCAT_DIR}"
cd "${SANDCAT_DIR}"

curl -sk -X POST \
  -H "file:sandcat.go" \
  -H "platform:linux" \
  "${CALDERA_SERVER}/file/download" -o sandcat
chmod +x sandcat

echo "[*] Installing sandcat as a systemd service"
cat >/etc/systemd/system/sandcat.service <<EOF
[Unit]
Description=Caldera Sandcat agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=${SANDCAT_DIR}/sandcat -server ${CALDERA_SERVER} -group ${CALDERA_GROUP} -v
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now sandcat.service

echo
echo "=============================================================="
echo "  Host:            $(hostname) ($(hostname -I | awk '{print $1}'))"
echo "  Wazuh manager:   ${WAZUH_MANAGER}"
echo "  Caldera server:  ${CALDERA_SERVER}  (group=${CALDERA_GROUP})"
echo "  Sandcat log:     journalctl -u sandcat -f"
echo "  Wazuh log:       tail -f /var/ossec/logs/ossec.log"
echo "=============================================================="
echo "[+] Victim provisioning complete."
