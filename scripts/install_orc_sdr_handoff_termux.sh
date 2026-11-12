#!/data/data/com.termux/files/usr/bin/bash
# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
set -euo pipefail

mkdir -p "$HOME/.termux/tasker"
cat > "$HOME/.termux/tasker/orc-sdr-attach" <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="$HOME/src/libSDRForge"
STATE="$HOME/.termux/orc-sdr"
mkdir -p "$STATE"
exec >> "$HOME/.termux/orc-sdr-attach.log" 2>&1
echo "$(date -Is): RTL-SDR attachment handoff received"
if ! command -v termux-usb >/dev/null 2>&1; then
  echo "Termux USB API unavailable"
  exit 1
fi
termux-usb -l
if [[ ! -f "$ROOT/scripts/orc_sdr_session_termux.sh" ]]; then
  echo "Missing libSDRForge session manager at $ROOT"
  exit 1
fi
exec bash "$ROOT/scripts/orc_sdr_session_termux.sh" start
EOF
chmod 700 "$HOME/.termux/tasker/orc-sdr-attach"
echo "Installed $HOME/.termux/tasker/orc-sdr-attach"
echo "Requires Termux:API, termux-api, and allow-external-apps=true in ~/.termux/termux.properties."
