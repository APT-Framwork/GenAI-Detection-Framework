# Ubuntu victim image.
#
# Installs everything the STRIX ML pipeline expects on an agent host so that
# alerts populate the same `_source.*` fields the models were trained on
# (see docs/WAZUH_MAPPING.md):
#   - wazuh-agent  → ships alerts
#   - auditd       → /var/log/audit/audit.log → data.audit.* features
#   - rsyslog      → /var/log/auth.log, /var/log/syslog, /var/log/dpkg.log
#                    → pam/sudo/sshd/dpkg decoders
#   - sandcat      → fetched at runtime from Caldera (see entrypoint.sh)
#
# The localfiles + syscheck + sca config from
# config/wazuh/ossec-agent-localfiles.xml.draft is merged into ossec.conf at
# runtime so training-schema coverage is preserved.
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    WAZUH_MANAGER=wazuh.manager

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl gnupg ca-certificates lsb-release procps iproute2 sudo \
      net-tools iputils-ping xmlstarlet \
      auditd audispd-plugins rsyslog \
      openssh-server \
      python3 python3-minimal netcat-openbsd \
 && curl -fsSL https://packages.wazuh.com/key/GPG-KEY-WAZUH \
      | gpg --dearmor -o /usr/share/keyrings/wazuh.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/wazuh.gpg] https://packages.wazuh.com/4.x/apt/ stable main" \
      > /etc/apt/sources.list.d/wazuh.list \
 && apt-get update \
 && apt-get install -y wazuh-agent=4.9.2-1 \
 && rm -rf /var/lib/apt/lists/*

# Agent-side localfiles / syscheck / sca fragment — merged into ossec.conf at
# boot so the training-schema features (data.audit.*, syscheck.*, data.sca.*,
# data.srcip, data.command, dpkg decoder) all populate.
COPY localfiles.xml         /opt/strix/localfiles.xml
COPY reformat_sshd_log.py   /opt/strix/reformat_sshd_log.py
COPY entrypoint.sh          /entrypoint.sh
RUN chmod +x /entrypoint.sh /opt/strix/reformat_sshd_log.py

ENTRYPOINT ["/entrypoint.sh"]
