#!/data/data/com.termux/files/usr/bin/bash
# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${1:-}"
if [[ -z "$APP" ]]; then
    echo "Usage: $0 <python-script> [arguments...]" >&2
    exit 2
fi
if [[ $# -gt 0 ]]; then shift; fi
if [[ ! -f "$APP" ]]; then
    echo "Python application not found: $APP" >&2
    exit 2
fi

# A USB bus/device address changes after reattachment. Enumerate every run.
# Refuse ambiguous selections rather than opening the wrong USB peripheral.
if [[ -n "${SDRFORGE_USB_DEVICE:-}" ]]; then
    DEVICE="$SDRFORGE_USB_DEVICE"
else
    DEVICE="$(termux-usb -l | python -c '
import json, os, sys
devices = json.load(sys.stdin)
if not isinstance(devices, list):
    sys.exit("Unexpected termux-usb device listing")
if len(devices) == 1:
    print(devices[0])
    sys.exit(0)
matches = []
for path in devices:
    try:
        parts = path.strip("/").split("/")
        bus, dev = int(parts[-2]), int(parts[-1])
        root = f"/sys/bus/usb/devices"
        for entry in os.scandir(root):
            try:
                with open(entry.path + "/busnum") as f:
                    b = int(f.read())
                with open(entry.path + "/devnum") as f:
                    d = int(f.read())
                if (b, d) != (bus, dev):
                    continue
                with open(entry.path + "/idVendor") as f:
                    vid = f.read().strip().lower()
                with open(entry.path + "/idProduct") as f:
                    pid = f.read().strip().lower()
                if vid == "0bda" and pid in ("2832", "2838"):
                    matches.append(path)
            except (OSError, ValueError):
                continue
    except (ValueError, IndexError):
        continue
if len(matches) == 1:
    print(matches[0])
else:
    sys.exit("Unable to uniquely identify RTL-SDR; termux-usb returned "
             + repr(devices)
             + "; set SDRFORGE_USB_DEVICE=/dev/bus/usb/... explicitly")
')"
fi

# Collect GPS before USB handoff, never inside the authorized subprocess.
LOCATION_JSON=""
if [[ "$APP" == *rds_iq_replay.py && "${1:-}" == "capture" ]]; then
    WANT_LOCATION=1
    for ARG in "$@"; do
        [[ "$ARG" == "--no-location" ]] && WANT_LOCATION=0
    done
    if [[ "$WANT_LOCATION" == 1 ]]; then
        LOCATION_JSON="$(PYTHONPATH="$ROOT/src" python -c 'import json
from examples.rds_iq_replay import capture_location
print(json.dumps(capture_location()))' 2>/dev/null)" || LOCATION_JSON=""
        if [[ -z "$LOCATION_JSON" ]]; then
            LOCATION_JSON='{"status":"unavailable","reason":"launcher GPS lookup failed"}'
        fi
        echo "GPS lookup finished (coordinates omitted)"
    fi
fi

echo "Requesting Android USB permission for $DEVICE"
termux-usb -r "$DEVICE"
echo "Starting libSDRForge IQ capture through authorized USB FD"
printf -v CMD "env PYTHONPATH=%q" "$ROOT/src"
if [[ -n "$LOCATION_JSON" ]]; then
    printf -v QUOTED "%q" "$LOCATION_JSON"
    CMD+=" SDRFORGE_CAPTURE_LOCATION_JSON=$QUOTED"
fi
printf -v QUOTED "%q" "$APP"
CMD+=" python -u $QUOTED"
for ARG in "$@"; do
    printf -v QUOTED "%q" "$ARG"
    CMD+=" $QUOTED"
done
termux-usb -E -e "$CMD" "$DEVICE"
