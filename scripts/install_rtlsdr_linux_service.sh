#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="$UNIT_DIR/libsdrforge.service"
ACTION="${1:-install}"
case "$ACTION" in
  install)
    [[ -x "$ROOT/.venv/bin/python" ]] || { echo "Run bash scripts/install_rtlsdr_linux.sh first" >&2; exit 1; }
    command -v systemctl >/dev/null || { echo "systemctl not available" >&2; exit 1; }
    mkdir -p "$UNIT_DIR"
    # systemd specifier escaping: quote paths for spaces, %% for literal percent.
    escape_path() { local s="${1//%/%%}"; printf '%s' "${s// /\\x20}"; }
    PY="$(escape_path "$ROOT/.venv/bin/python")"
    DIR="$(escape_path "$ROOT")"
    ENTRY="$(escape_path "$ROOT/examples/live_transport_server.py")"
    cat > "$UNIT" <<EOF
[Unit]
Description=libSDRForge REST, rigctl and ZMQ service
After=default.target

[Service]
Type=simple
WorkingDirectory=$DIR
ExecStart=$PY -u $ENTRY
Restart=on-failure
RestartSec=3
TimeoutStopSec=15

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    echo "Installed $UNIT"
    echo "Start: systemctl --user enable --now libsdrforge.service"
    echo "Logs: journalctl --user -u libsdrforge.service -f"
    ;;
  uninstall)
    systemctl --user disable --now libsdrforge.service || true
    rm -f "$UNIT"
    systemctl --user daemon-reload
    ;;
  *) echo "Usage: $0 [install|uninstall]" >&2; exit 2 ;;
esac
