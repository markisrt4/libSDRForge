#!/data/data/com.termux/files/usr/bin/bash
# SPDX-License-Identifier: MIT
# Run the authorized USB capture without a live stdout pipeline.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="${SDRFORGE_CAPTURE_LOG:-$HOME/sdrforge_capture.log}"
"$ROOT/scripts/run_rtlsdr_termux.sh" "$@" >"$LOG" 2>&1
STATUS=$?
cat "$LOG"
printf 'Capture exit status: %s\n' "$STATUS"
if command -v termux-clipboard-set >/dev/null 2>&1; then
    timeout 5 termux-clipboard-set < "$LOG"
    CLIP_STATUS=$?
    printf 'Clipboard exit status: %s\n' "$CLIP_STATUS"
fi
exit "$STATUS"
