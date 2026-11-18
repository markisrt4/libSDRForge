#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
DEV=0
NO_APT=0
CHECK=0
SERVICE=0

usage() {
  cat <<'EOF'
Usage: scripts/install_rtlsdr_linux.sh [--dev] [--no-apt] [--check] [--service] [--help]
  --dev      Include test and quality dependencies
  --no-apt   Skip operating-system package installation
  --check    Verify existing installation without changing it
  --service  Install a systemd user service (does not start it)
  --help     Show this message
EOF
}
while (($#)); do
  case "$1" in
    --dev) DEV=1 ;;
    --no-apt) NO_APT=1 ;;
    --check) CHECK=1 ;;
    --service) SERVICE=1 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

check_install() {
  local failed=0
  if [[ ! -x "$VENV/bin/python" ]]; then
    echo "FAIL: missing virtual environment at $VENV" >&2
    return 1
  fi
  if ! "$VENV/bin/python" -c 'import sdrforge, numpy, scipy, zmq, sounddevice; print("PASS: Python package and ZeroMQ imports")'; then
    failed=1
  fi
  if ! "$VENV/bin/python" - <<'PY'
import ctypes.util
import sys
if ctypes.util.find_library("rtlsdr"):
    print("PASS: librtlsdr available")
else:
    print("FAIL: librtlsdr shared library missing", file=sys.stderr)
    sys.exit(1)
PY
  then
    failed=1
  fi
  for cmd in rtl_test ffplay; do
    if command -v "$cmd" >/dev/null 2>&1; then
      echo "PASS: $cmd available"
    else
      echo "FAIL: $cmd missing" >&2
      failed=1
    fi
  done
  return "$failed"
}

if ((CHECK)); then
  check_install
  exit $?
fi

if (( ! NO_APT )); then
  if [[ ! -r /etc/os-release ]]; then
    echo "Cannot identify Linux distribution. Use --no-apt to manage system packages yourself." >&2
    exit 1
  fi
  # shellcheck disable=SC1091
  source /etc/os-release
  if [[ " ${ID:-} ${ID_LIKE:-} " != *" debian "* && " ${ID:-} ${ID_LIKE:-} " != *" ubuntu "* ]]; then
    echo "Automatic system installation supports Debian/Ubuntu only; use --no-apt." >&2
    exit 1
  fi
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "apt-get not available; use --no-apt." >&2
    exit 1
  fi
  SUDO=()
  if ((EUID != 0)); then
    command -v sudo >/dev/null 2>&1 || { echo "sudo is required for apt installation" >&2; exit 1; }
    SUDO=(sudo)
  fi
  "${SUDO[@]}" apt-get update
  "${SUDO[@]}" apt-get install -y \
    python3 python3-venv python3-dev git build-essential pkg-config \
    libusb-1.0-0-dev librtlsdr-dev rtl-sdr usbutils ffmpeg \
    libfftw3-dev libasound2-dev libportaudio2 portaudio19-dev libzmq3-dev
fi

if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --upgrade pip
extras='rtl,zmq,audio'
if ((DEV)); then extras='rtl,zmq,dev,quality'; fi
"$VENV/bin/python" -m pip install -e "$ROOT[$extras]"
check_install
if ((SERVICE)); then
  bash "$ROOT/scripts/install_rtlsdr_linux_service.sh" install
fi
echo "Installation complete. Run: $ROOT/scripts/run_rtlsdr_linux.sh $ROOT/examples/rtl_fm_live.py --frequency 104.3 --mono --auto-gain --acquisition-mode async"
