#!/usr/bin/env bash
# Ubuntu/Debian/Raspberry Pi OS NOAA weather speech setup.
set -euo pipefail
if ! command -v apt-get >/dev/null 2>&1; then
  echo "This installer requires apt-get (Ubuntu/Debian/Raspberry Pi OS)." >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y espeak-ng ffmpeg
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "$ROOT/scripts/install_weather.sh" "$@"
