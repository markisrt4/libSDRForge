#!/data/data/com.termux/files/usr/bin/bash
# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
set -euo pipefail

mkdir -p "$HOME/.termux/tasker"
cat > "$HOME/.termux/tasker/orc-sdr-attach" <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
# Android Companion triggers this through Termux RUN_COMMAND.
# This script does not seize a dongle already in use by another process.
LOG="$HOME/.termux/orc-sdr-attach.log"
{
  printf '%s: RTL-SDR attachment handoff received\n' "$(date -Is)"
  if ! command -v termux-usb >/dev/null 2>&1; then
    echo "Install termux-api and the Termux:API Android app first"
    exit 1
  fi
  termux-usb -l
  echo "Handoff received. Run libSDRForge's run_rtlsdr_termux.sh to acquire USB FD."
} >> "$LOG" 2>&1
EOF
chmod 700 "$HOME/.termux/tasker/orc-sdr-attach"
echo "Installed $HOME/.termux/tasker/orc-sdr-attach"
echo "Enable allow-external-apps=true in ~/.termux/termux.properties and restart Termux."
