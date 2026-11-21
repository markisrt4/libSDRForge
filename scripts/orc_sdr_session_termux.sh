#!/data/data/com.termux/files/usr/bin/bash
# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/radio_region_env.sh
source "$ROOT/scripts/radio_region_env.sh"
sdrforge_load_radio_region
STATE="$HOME/.termux/orc-sdr"
mkdir -p "$STATE"
PID="$STATE/launcher.pid"
STATUS="$STATE/status"
LOG="$STATE/session.log"
STOP="$STATE/stop.request"
RECEIVER_PID="$STATE/receiver.pid"
running() { [[ -f "$PID" ]] && kill -0 "$(cat "$PID")" 2>/dev/null; }
case "${1:-status}" in
  status)
    if running; then printf "launcher pid=%s state=" "$(cat "$PID")"; cat "$STATUS" 2>/dev/null || echo starting; else cat "$STATUS" 2>/dev/null || echo stopped; fi
    ;;
  stop)
    if running || [[ -f "$RECEIVER_PID" ]]; then
      touch "$STOP"
      # The managed live server uses its own graceful shutdown endpoint.
      # Only request shutdown while our authorized launcher is still alive.
      if running && curl -fsS --max-time 2 http://127.0.0.1:5570/v1/receiver \
          | python -c 'import json,sys; sys.exit(0 if json.load(sys.stdin).get("source_type") == "rtl_sdr" else 1)' 2>/dev/null; then
        curl -fsS --max-time 3 -X POST http://127.0.0.1:5570/v1/server/shutdown >/dev/null || true
      fi
      if [[ -f "$RECEIVER_PID" ]]; then
        target="$(cat "$RECEIVER_PID")"
        if [[ "$target" =~ ^[0-9]+$ ]] && ps -p "$target" -o args= 2>/dev/null | grep -q 'orc_sdr_idle.py'; then
          kill -TERM "$target" 2>/dev/null || true
        fi
      fi
      echo "Stop requested; waiting for receiver cleanup"
    else
      echo stopped > "$STATUS"
    fi
    ;;
  start)
    if running; then echo "SDR session already running"; exit 0; fi
    # Atomic directory prevents two simultaneous attachment intents from racing.
    if ! mkdir "$STATE/start.lock" 2>/dev/null; then echo "SDR startup already pending"; exit 0; fi
    trap 'rmdir "$STATE/start.lock" 2>/dev/null || true' EXIT
    if running; then exit 0; fi
    if ! command -v termux-usb >/dev/null; then echo "termux-usb missing" > "$STATUS"; exit 1; fi
    rm -f "$STOP" "$RECEIVER_PID"
    echo authorizing > "$STATUS"
    (
      echo "$BASHPID" > "$PID"
      trap 'rm -f "$PID"' EXIT
      DEVICES="$(termux-usb -l)"
      DEVICE="$(printf '%s' "$DEVICES" | python -c 'import json,sys; x=json.load(sys.stdin); assert isinstance(x,list) and len(x)==1, "Expected exactly one USB device"; print(x[0])')"
      echo "Requesting USB permission for $DEVICE"
      termux-usb -r "$DEVICE"
      # An authorized USB descriptor must be handed to the actual radio server.
      # Stop supervised simulation before binding the shared REST/ZMQ/rigctl ports.
      SERVICE="${PREFIX:-/data/data/com.termux/files/usr}/var/service/openroadcode-sdrforge"
      if [[ -d "$SERVICE" ]]; then
        sv down "$SERVICE"
      fi
      for _ in $(seq 1 40); do
        if ! curl -fsS --max-time 1 http://127.0.0.1:5570/v1/health >/dev/null 2>&1; then
          break
        fi
        sleep 0.25
      done
      if curl -fsS --max-time 1 http://127.0.0.1:5570/v1/health >/dev/null 2>&1; then
        echo "Another SDRForge server owns port 5570; refusing USB launch" >&2
        echo "error: existing server" > "$STATUS"
        exit 1
      fi
      echo starting > "$STATUS"
      # termux-usb splits -e arguments itself; embedded shell quotes become literal path characters.
      HANDOFF="env PYTHONPATH=$ROOT/src"
      for KEY in SDRFORGE_RADIO_ROOT SDRFORGE_RADIO_LOCALE; do
        if [[ -n "${!KEY:-}" ]]; then
          printf -v VALUE_Q '%q' "${!KEY}"
          HANDOFF+=" $KEY=$VALUE_Q"
        fi
      done
      HANDOFF+=" python -u $ROOT/examples/live_transport_server.py --frequency 104.3 --warmup 0"
      termux-usb -E -e "$HANDOFF" "$DEVICE"
      echo stopped > "$STATUS"
    ) >> "$LOG" 2>&1 &
    echo "SDR session startup requested"
    ;;
  *) echo "Usage: $0 {start|stop|status}" >&2; exit 2 ;;
esac
