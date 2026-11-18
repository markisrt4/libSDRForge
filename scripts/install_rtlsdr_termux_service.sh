#!/data/data/com.termux/files/usr/bin/bash
# SPDX-License-Identifier: MIT
# Install libSDRForge as a Termux runit service, optionally at Android boot.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACTION="${1:-install}"
BOOT_MODE="${2:---boot}"
SERVICE="openroadcode-sdrforge"
SV_DIR="$PREFIX/etc/sv/$SERVICE"
ACTIVE="$PREFIX/var/service/$SERVICE"
BOOT_DIR="$HOME/.termux/boot"
BOOT_FILE="$BOOT_DIR/20-sdrforge-service"
PY="$ROOT/.venv/bin/python"

usage() {
  echo "Usage: $0 install [--boot|--login] | uninstall | status" >&2
  exit 2
}

case "$ACTION" in
  install)
    [[ "$BOOT_MODE" == "--boot" || "$BOOT_MODE" == "--login" ]] || usage
    command -v pkg >/dev/null || { echo "Run this script in Termux." >&2; exit 1; }
    pkg install -y termux-services
    if [[ ! -x "$PY" ]]; then
      PY="$(command -v python || true)"
    fi
    [[ -n "$PY" && -x "$PY" ]] || { echo "Python unavailable; install libSDRForge first." >&2; exit 1; }
    # PortAudio is a native shared library; Python's sounddevice package
    # cannot provide it on Android. Install both layers automatically.
    pkg install -y portaudio
    if ! PYTHONPATH="$ROOT/src" "$PY" -c 'import sdrforge, zmq, sounddevice' >/dev/null 2>&1; then
      echo "Installing missing SDRForge transport/audio Python dependencies..."
      "$PY" -m pip install -e "$ROOT[zmq,audio]"
    fi
    PYTHONPATH="$ROOT/src" "$PY" -c 'import sdrforge, zmq, sounddevice' || {
      echo "SDRForge transport/audio dependencies are still unavailable." >&2
      echo "Python: $PY" >&2
      exit 1
    }
    [[ -f "$ROOT/examples/live_transport_server.py" ]] || {
      echo "SDRForge server entrypoint missing." >&2; exit 1;
    }
    mkdir -p "$SV_DIR/log" "$PREFIX/var/service" "$BOOT_DIR"
    # A previous install may have left the service disabled by default.
    rm -f "$SV_DIR/down"
    # Quote paths for sh without depending on the current working directory.
    printf -v ROOT_Q '%q' "$ROOT"
    printf -v PY_Q '%q' "$PY"
    cat > "$SV_DIR/run" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
exec 2>&1
cd $ROOT_Q
export PYTHONPATH=$ROOT_Q/src
exec $PY_Q -u $ROOT_Q/examples/live_transport_server.py
EOF
    chmod 755 "$SV_DIR/run"
    # svlogd rotates logs and avoids unbounded output files.
    cat > "$SV_DIR/log/run" <<'EOF'
#!/data/data/com.termux/files/usr/bin/sh
exec /data/data/com.termux/files/usr/bin/svlogd -tt /data/data/com.termux/files/usr/var/log/openroadcode-sdrforge
EOF
    mkdir -p "$PREFIX/var/log/openroadcode-sdrforge"
    chmod 755 "$SV_DIR/log/run"
    if [[ -L "$ACTIVE" ]]; then
      [[ "$(readlink "$ACTIVE")" == "$SV_DIR" ]] || {
        echo "Existing service link points elsewhere: $ACTIVE" >&2; exit 1;
      }
    elif [[ -e "$ACTIVE" ]]; then
      echo "Refusing to overwrite existing service: $ACTIVE" >&2; exit 1
    else
      ln -s "$SV_DIR" "$ACTIVE"
    fi
    # Termux:Boot runs files in ~/.termux/boot after the companion app
    # has been installed and launched once by the user.
    if [[ "$BOOT_MODE" == "--boot" ]]; then
      cat > "$BOOT_FILE" <<'EOF'
#!/data/data/com.termux/files/usr/bin/sh
# Start the Termux runit supervisor on Android boot.
. /data/data/com.termux/files/usr/etc/profile.d/start-services.sh
EOF
      chmod 700 "$BOOT_FILE"
    else
      rm -f "$BOOT_FILE"
    fi
    # Starting runsvdir is idempotent under termux-services.
    if [[ -f "$PREFIX/etc/profile.d/start-services.sh" ]]; then
      # shellcheck disable=SC1091
      . "$PREFIX/etc/profile.d/start-services.sh"
    fi
    # Existing runit supervisors retain their old processes until restarted.
    # Restart the logger first so the new destination becomes active.
    if [[ -d "$ACTIVE/supervise" ]]; then
      sv restart "$ACTIVE/log" || true
      sv restart "$ACTIVE" || true
    fi
    sv up "$ACTIVE" || {
      echo "Service installed. Restart Termux to start its supervisor, then run: sv up $ACTIVE" >&2
      exit 1
    }
    echo "Installed and enabled $SERVICE"
    echo "Status: sv status $ACTIVE"
    echo "Logs: tail -F $PREFIX/var/log/openroadcode-sdrforge/current"
    if [[ "$BOOT_MODE" == "--boot" ]]; then
      echo "Android boot enabled via $BOOT_FILE"
      echo "Install/open Termux:Boot once and allow background operation in Android settings."
    fi
    ;;
  uninstall)
    if [[ -L "$ACTIVE" && "$(readlink "$ACTIVE")" == "$SV_DIR" ]]; then
      sv down "$ACTIVE" || true
      rm -f "$ACTIVE"
    fi
    rm -rf "$SV_DIR"
    rm -f "$BOOT_FILE"
    echo "Removed $SERVICE"
    ;;
  status)
    sv status "$ACTIVE"
    ;;
  *) usage ;;
esac
