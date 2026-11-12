# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Hold an RTL-SDR open until a cooperative stop is requested."""
from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

from sdrforge.adapters import RtlSdrSource


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("Usage: orc_sdr_idle.py STATUS STOP_FILE USB_DEVICE")
    status, stop_file, _usb_device = map(Path, sys.argv[1:])
    receiver_pid = status.parent / "receiver.pid"
    receiver_pid.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    active = True

    def stop(_signum: int, _frame: object) -> None:
        nonlocal active
        active = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    source = RtlSdrSource()
    opened = False
    outcome = "stopped"
    try:
        source.open()
        opened = True
        status.write_text("idle-ready\n", encoding="utf-8")
        while active:
            if stop_file.exists():
                break
            time.sleep(0.5)
    except Exception as exc:
        outcome = f"error: {exc}"
        raise
    finally:
        try:
            if opened:
                source.close()
        finally:
            status.write_text(outcome + "\n", encoding="utf-8")
            receiver_pid.unlink(missing_ok=True)
            stop_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
