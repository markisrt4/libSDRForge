#!/usr/bin/env bash
# Termux NOAA weather speech setup with native Android Vosk.
set -euo pipefail
if [[ "${PREFIX:-}" != *com.termux* ]]; then
  echo "This installer must run in native Termux." >&2
  exit 1
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_URL="https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
MODEL_DIR="$HOME/models"
VOSK_VERSION="0.3.75"
SKIP_MODEL=0
while (( $# )); do
  case "$1" in
    --model-url) MODEL_URL="${2:?missing model URL}"; shift 2 ;;
    --model-dir) MODEL_DIR="${2:?missing model directory}"; shift 2 ;;
    --vosk-version) VOSK_VERSION="${2:?missing version}"; shift 2 ;;
    --skip-model) SKIP_MODEL=1; shift ;;
    -h|--help)
      echo "Usage: bash scripts/install_weather_termux.sh [--model-url HTTPS_ZIP_URL] [--model-dir DIR] [--vosk-version VERSION] [--skip-model]"
      echo "Installs libSDRForge, native Android Vosk, and the small English model unless --skip-model is given."
      exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
pkg install -y espeak ffmpeg curl binutils
bash "$ROOT/scripts/install_weather.sh" --skip-vosk
bash "$ROOT/scripts/fetch_vosk_android_termux.sh" "$VOSK_VERSION"
MODEL_PATH="$MODEL_DIR/vosk-model-small-en-us-0.15"
if (( ! SKIP_MODEL )); then
  if [[ -d "$MODEL_PATH" ]]; then
    echo "Existing Vosk model: $MODEL_PATH (skipping download)"
  else
    bash "$ROOT/scripts/install_weather.sh" --skip-vosk --model-url "$MODEL_URL" --model-dir "$MODEL_DIR"
  fi
fi
echo "Native Vosk: $HOME/.local/lib/sdrforge-vosk/libvosk.so"
echo "Model: $MODEL_PATH"
echo 'Run: python -m sdrforge.weather.offline_wav weather_16k.wav --model "$HOME/models/vosk-model-small-en-us-0.15" --vosk-library "$HOME/.local/lib/sdrforge-vosk/libvosk.so" --location Detroit'
