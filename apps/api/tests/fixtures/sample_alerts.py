"""Shared alert fixtures for unit/integration tests.

One place so every test works off the same canonical shapes — if Wazuh's
schema drifts we update this file, not scattered literals across tests.
"""

from __future__ import annotations

from typing import Any

#: A minimal but realistic auditd alert that would pass through the pipeline.
SAMPLE_AUDITD_ALERT: dict[str, Any] = {
    "_index": "wazuh-alerts-4.x-2026.04.17",
    "_id": "QKuawJEBxxxxxxxxxxxx",
    "_score": None,
    "_source": {
        "id": "QKuawJEBxxxxxxxxxxxx",
        "@timestamp": "2026-04-17T09:12:34.107Z",
        "agent": {
            "id": "001",
            "name": "Machine-1-New",
            "ip": "10.0.0.11",
        },
        "rule": {
            "id": "80710",
            "firedtimes": 3,
            "level": 10,
            "description": "Suspicious sudo invocation",
            "mitre": {
                "tactic": ["TA0004"],
                "technique": ["T1548.003"],
            },
            "groups": ["audit", "audit_command"],
        },
        "decoder": {"name": "auditd"},
        "location": "/var/log/audit/audit.log",
        "full_log": "type=SYSCALL msg=audit(1713340354.107:12345): arch=c000003e syscall=59 success=yes exit=0",
        "data": {
            "command": "sudo -u root /usr/bin/bash -c 'cat /etc/shadow'",
            "srcip": "10.0.0.42",
            "srcport": "49512",
            "srcuser": "alice",
        },
    },
}

#: An alert for a syscheck integrity change.
SAMPLE_SYSCHECK_ALERT: dict[str, Any] = {
    "_id": "abc123syscheck",
    "_source": {
        "id": "abc123syscheck",
        "@timestamp": "2026-04-17T09:30:00.000Z",
        "agent": {"id": "002", "name": "Machine-2-New", "ip": "10.0.0.12"},
        "rule": {
            "id": "550",
            "firedtimes": 1,
            "level": 7,
            "description": "Integrity checksum changed.",
            "mitre": {"tactic": [], "technique": []},
        },
        "decoder": {"name": "syscheck_integrity_changed"},
        "location": "syscheck",
        "full_log": "File '/etc/passwd' checksum changed.",
        "syscheck": {
            "path": "/etc/passwd",
            "event": "modified",
            "md5_after": "5d41402abc4b2a76b9719d911017c592",
            "sha256_after": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
            "changed_attributes": ["size", "mtime", "md5", "sha256"],
        },
    },
}

#: An alert with all the fields the engineer cares about missing — exercises
#: the "happy path for the unhappy path" (empty/None handling).
SAMPLE_EMPTY_ALERT: dict[str, Any] = {
    "_id": "empty-alert-0",
    "_source": {
        "id": "empty-alert-0",
        "@timestamp": "2026-04-17T10:00:00.000Z",
        "agent": {"id": "003"},
        "rule": {},
        "decoder": {},
    },
}

ALL_FIXTURES: list[dict[str, Any]] = [
    SAMPLE_AUDITD_ALERT,
    SAMPLE_SYSCHECK_ALERT,
    SAMPLE_EMPTY_ALERT,
]
