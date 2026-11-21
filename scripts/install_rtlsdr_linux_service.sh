#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="$UNIT_DIR/libsdrforge.service"
ACTION="${1:-install}"
BOOT_MODE="${2:-login}"
if [[ "$ACTION" == "install" && "$BOOT_MODE" != "login" && "$BOOT_MODE" != "--boot" ]]; then
  echo "Usage: $0 install [--boot] | uninstall" >&2
  exit 2
fi
case "$ACTION" in
  install)
    [[ -x "$ROOT/.venv/bin/python" ]] || { echo "Run bash scripts/install_rtlsdr_linux.sh first" >&2; exit 1; }
    # The transport service requires pyzmq even when installed independently.
    # Repair missing Python dependencies using the canonical Linux installer,
    # without repeating apt operations or creating an alternate environment.
    if ! "$ROOT/.venv/bin/python" -c 'import sdrforge, zmq, sounddevice' >/dev/null 2>&1; then
      echo "Installing missing SDRForge transport dependencies into $ROOT/.venv"
      "$ROOT/.venv/bin/python" -m pip install -e "$ROOT[rtl,zmq,audio]"
    fi
    "$ROOT/.venv/bin/python" -c 'import sdrforge, zmq' || {
      echo "SDRForge transport dependencies unavailable; run scripts/install_rtlsdr_linux.sh" >&2
      exit 1
    }
    command -v systemctl >/dev/null || { echo "systemctl not available" >&2; exit 1; }
    mkdir -p "$UNIT_DIR"
    # systemd specifier escaping: quote paths for spaces, %% for literal percent.
    escape_path() { local s="${1//%/%%}"; printf '%s' "${s// /\\x20}"; }
    PY="$(escape_path "$ROOT/.venv/bin/python")"
    DIR="$(escape_path "$ROOT")"
    ENTRY="$(escape_path "$ROOT/examples/live_transport_server.py")"
    REGION_LOADER="$(escape_path "$ROOT/scripts/run_radio_region_server.sh")"
    cat > "$UNIT" <<EOF
[Unit]
Description=libSDRForge REST, rigctl and ZMQ service
After=default.target

[Service]
Type=simple
WorkingDirectory=$DIR
ExecStart=/usr/bin/bash $REGION_LOADER $PY -u $ENTRY
Restart=on-failure
RestartSec=3
TimeoutStopSec=15

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now libsdrforge.service
    if [[ "$BOOT_MODE" == "--boot" ]]; then
      command -v loginctl >/dev/null || {
        echo "loginctl unavailable; service enabled for login startup only" >&2
        exit 1
      }
      if ! loginctl show-user "$(id -un)" -p Linger --value | grep -qx yes; then
        echo "Enabling user lingering for boot-time service startup..."
        if ! loginctl enable-linger "$(id -un)"; then
          echo "Could not enable lingering automatically." >&2
          echo "Run: sudo loginctl enable-linger $(id -un)" >&2
          exit 1
        fi
      fi
    fi
    echo "Installed and started $UNIT"
    echo "Startup: $([[ "$BOOT_MODE" == "--boot" ]] && echo 'system boot (lingering enabled)' || echo 'user login')"
    echo "Status: systemctl --user status libsdrforge.service"
    echo "Logs: journalctl --user -u libsdrforge.service -f"
    ;;
  uninstall)
    systemctl --user disable --now libsdrforge.service || true
    rm -f "$UNIT"
    systemctl --user daemon-reload
    ;;
  *) echo "Usage: $0 install [--boot] | uninstall" >&2; exit 2 ;;
esac
