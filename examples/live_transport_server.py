# SPDX-License-Identifier: MIT
"""Compatibility launcher for the packaged radio server."""

from sdrforge.live_transport_server import IqCapture, LiveRadioControl, main

__all__ = ["IqCapture", "LiveRadioControl", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
