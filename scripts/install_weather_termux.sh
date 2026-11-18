#!/usr/bin/env bash
# Termux NOAA weather speech setup; no sudo or Linux-specific paths.
set -euo pipefail
if [[ -z "${PREFIX:-}" || "${PREFIX}" != *com.termux* ]]; then
  echo "This installer must run in Termux." >&2
  exit 1
fi
pkg install -y espeak ffmpeg
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "Note: Vosk may lack a compatible native Android/Python wheel."
echo "A successful model download alone does not guarantee Vosk works on Termux."
exec bash "$ROOT/scripts/install_weather.sh" "$@"
