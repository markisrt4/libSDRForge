#!/data/data/com.termux/files/usr/bin/bash
# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SMOKE="${1:-$HOME/sdrforge_fd_smoke.py}"
if [[ ! -f "$SMOKE" ]]; then
    echo "Smoke test not found: $SMOKE" >&2
    exit 2
fi

# A USB bus/device address changes after reattachment. Enumerate every run.
# Refuse ambiguous selections rather than opening the wrong USB peripheral.
if [[ -n "${SDRFORGE_USB_DEVICE:-}" ]]; then
    DEVICE="$SDRFORGE_USB_DEVICE"
else
    DEVICE="$(termux-usb -l | python -c '
import json, sys
devices = json.load(sys.stdin)
if not isinstance(devices, list) or len(devices) != 1:
    sys.exit("Expected exactly one USB device; set SDRFORGE_USB_DEVICE=/dev/bus/usb/... to select explicitly")
print(devices[0])
')"
fi

echo "Requesting Android USB permission for $DEVICE"
termux-usb -r "$DEVICE"
echo "Starting libSDRForge IQ capture through authorized USB FD"
termux-usb -E -e "env PYTHONPATH=$ROOT/src python -u $SMOKE" "$DEVICE"
