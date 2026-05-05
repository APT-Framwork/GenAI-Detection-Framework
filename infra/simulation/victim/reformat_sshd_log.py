#!/usr/bin/env python3
"""Tail sshd's bare `-E` output and append syslog-formatted lines to auth.log.

Background:
  sshd in this container logs via `-E /var/log/sshd-bare.log` because
  rsyslog's imuxsock binding silently drops messages here. The bare
  output looks like:
      Invalid user fakeuser from 1.2.3.4 port 5678
  Wazuh's sshd decoder needs the standard syslog prefix:
      Mon DD HH:MM:SS host sshd[pid]: Invalid user fakeuser from ...
  This script bridges the two.

Why Python instead of `tail -F | awk`:
  In the container `tail -F` polls but the awk's stdin stays at pos=0
  for reasons we couldn't pin down (possibly inotify-vs-poll mismatch
  with the volume layer). Python's straightforward seek/read loop is
  predictable and has fflush built in.
"""
from __future__ import annotations

import socket
import sys
import time
from datetime import datetime
from pathlib import Path

SRC = Path("/var/log/sshd-bare.log")
DST = Path("/var/log/auth.log")
HOST = socket.gethostname()


def main() -> int:
    # Ensure the source exists so we can open it without racing sshd.
    SRC.touch(exist_ok=True)
    DST.touch(exist_ok=True)
    with SRC.open("r") as src, DST.open("a", buffering=1) as dst:
        # Skip existing content — only forward new lines, mirroring `tail -n0`.
        src.seek(0, 2)
        while True:
            line = src.readline()
            if not line:
                time.sleep(0.25)
                continue
            ts = datetime.now().strftime("%b %e %H:%M:%S")
            dst.write(f"{ts} {HOST} sshd[1]: {line.rstrip()}\n")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
