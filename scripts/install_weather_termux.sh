#!/usr/bin/env bash
# Termux NOAA weather speech setup; no sudo or Linux-specific paths.
set -euo pipefail
if [[ -z "${PREFIX:-}" || "${PREFIX}" != *com.termux* ]]; then
  echo "This installer must run in Termux." >&2
  exit 1
fi
pkg install -y espeak ffmpeg
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "Vosk has no compatible PyPI distribution for this Termux Python 3.14 environment."
echo "Installing base libSDRForge without Vosk. Offline WAV transcription will remain unavailable."
echo "Optional --model-url downloads model files only; it does not enable Vosk."
exec bash "$ROOT/scripts/install_weather.sh" --skip-vosk "$@"
