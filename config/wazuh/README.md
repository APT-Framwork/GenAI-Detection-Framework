# config/wazuh — DRAFT Wazuh configs

> **⚠️ DRAFT. NOTHING IN THIS FOLDER IS DEPLOYED.**
>
> These files describe the *target* Wazuh configuration for STRIX's inference pipeline. They are safe to read/review but must not be copied into a live `/var/ossec/etc/` tree without an explicit deployment plan.
> Cross-reference: [docs/INGESTION_PIPELINE.md](../../docs/INGESTION_PIPELINE.md), [docs/WAZUH_MAPPING.md](../../docs/WAZUH_MAPPING.md).

## Files in this folder

| File | Purpose |
|---|---|
| [ossec-agent-localfiles.xml.draft](ossec-agent-localfiles.xml.draft) | `<localfile>` and `<syscheck>` stanzas each Wazuh agent needs to emit alerts that fully match the training-dataset schema. Drop into `/var/ossec/etc/ossec.conf` on every agent. |
| [manager-custom-rules.xml.draft](manager-custom-rules.xml.draft) | Optional tagging rule so we can filter "STRIX-scored" alerts downstream. No new detections — just a marker. |
| [manager-custom-decoders.xml.draft](manager-custom-decoders.xml.draft) | Placeholder — **none required** for the training schema (all relevant fields are produced by native decoders). Kept as a hook for future sources (e.g. Suricata, custom app logs). |
| [filebeat-alerts-to-redis.yml.draft](filebeat-alerts-to-redis.yml.draft) | Filebeat input → Redis Streams output config. This is what tails `/var/ossec/logs/alerts/alerts.json` and publishes to `strix:alerts:raw`. |
| [manager-ossec-conf.xml.draft](manager-ossec-conf.xml.draft) | Snippet for the manager `ossec.conf` — enables JSON output and sets log rotation boundaries we rely on. |

## Why there is NO custom decoder

See [WAZUH_MAPPING.md §10](../../docs/WAZUH_MAPPING.md#10-summary-of-per-column-transformation-counts): every column in `apps/data/dataset.xlsx` is already produced by Wazuh's built-in decoders (`auditd`, `syscheck`, `pam`, `sudo`, `dpkg-decoder`, `web-accesslog`, `sca`, `ossec`, `rootcheck`, `sshd`, `kernel`). We don't need to write a new decoder — we need to make sure those existing ones have the right inputs (`<localfile>` pointed at the right log sources on every agent), which is what `ossec-agent-localfiles.xml.draft` handles.

## Open question before deployment

Training data was collected with agents forwarding audit.log, apache access.log, auth.log, dpkg.log, syslog, kern.log, and syscheck scans of `/etc /usr/bin /usr/sbin /bin /sbin /var/www`. **Production agents must ingest the same sources or the decoder/location one-hot coverage at inference time will differ from training** — dropping unknowns to all-zeros.
