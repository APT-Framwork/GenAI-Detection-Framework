# =============================================================================
# strix_attacker — pre-implant reconnaissance source.
#
# Why a dedicated container:
#   * Caldera (strix_caldera) is the post-implant C2 channel. Firing recon
#     traffic from there muddies the demo narrative — a juror sees one
#     attacker box doing both early scanning AND late-stage commands, when
#     the kill chain claims those are different actors / phases.
#   * This box exists ONLY to fire pre-implant probes (nmap, sshd
#     enumeration, web URI sweeps) at the victims. No Sandcat agent, no
#     Caldera connection. Wazuh sees its source IP as "external scanner"
#     and the 100050/100051 local rules tag those events with T1595 —
#     CKC stage 1, true Reconnaissance.
#
# Image is intentionally tiny: alpine + nmap + openssh-client + curl.
# /opt/recon_burst.sh is the entrypoint the simulator shells in to fire.
# =============================================================================
FROM alpine:3.20

RUN apk add --no-cache \
        nmap \
        nmap-scripts \
        openssh-client \
        curl \
        bash \
        coreutils \
    && adduser -D -s /bin/bash attacker

# Recon module gets baked in. The simulator runs:
#   docker exec strix_attacker /opt/recon_burst.sh victim1 victim2
COPY recon_burst.sh /opt/recon_burst.sh
RUN chmod +x /opt/recon_burst.sh

# Container idles forever; the simulator drives activity via `docker exec`.
# Keeps the box ready to fire on demand without a per-run startup hit.
CMD ["sleep", "infinity"]
