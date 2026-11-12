# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Hold an authorized RTL-SDR device open without selecting a receive mode."""
from __future__ import annotations

import signal
import sys
import time
from pathlib import Path

from sdrforge.adapters import RtlSdrSource


def main() -> None:
    status = Path(sys.argv[1])
    active = True

    def stop(_signum: int, _frame: object) -> None:
        nonlocal active
        active = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    source = RtlSdrSource()
    try:
        source.open()
        status.write_text("idle-ready\n", encoding="utf-8")
        while active:
            time.sleep(0.5)
    except Exception as exc:
        status.write_text(f"error: {exc}\n", encoding="utf-8")
        raise
    finally:
        source.close()
        if status.read_text(encoding="utf-8").strip() == "idle-ready":
            status.write_text("stopped\n", encoding="utf-8")


if __name__ == "__main__":
    main()
