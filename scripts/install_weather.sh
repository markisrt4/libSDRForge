#!/usr/bin/env bash
# Install offline NOAA speech recognition dependencies and optionally a model.
# Usage: bash scripts/install_weather.sh [--model-url URL] [--model-dir DIR]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_URL=""
SKIP_VOSK=0
MODEL_DIR="${HOME}/models"
while (( $# )); do
  case "$1" in
    --skip-vosk) SKIP_VOSK=1; shift ;;
    --model-url) MODEL_URL="${2:?missing model URL}"; shift 2 ;;
    --model-dir) MODEL_DIR="${2:?missing model directory}"; shift 2 ;;
    -h|--help)
      echo "Usage: bash scripts/install_weather.sh [--model-url HTTPS_ZIP_URL] [--model-dir DIR] [--skip-vosk]"
      echo "Installs the weather extra. A model is downloaded only with --model-url."
      exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

PYTHON="${PYTHON:-python}"
if (( SKIP_VOSK )); then
  "$PYTHON" -m pip install -e "$ROOT"
  echo "Skipping Vosk: native Android/Termux wheel is unavailable for this environment."
else
  "$PYTHON" -m pip install -e "${ROOT}[weather]"
  "$PYTHON" -c 'import vosk; print("Vosk Python package available")'
fi

if [[ -z "$MODEL_URL" ]]; then
  if (( SKIP_VOSK )); then
    echo "Base libSDRForge installed. Offline speech recognition is not available until a compatible Vosk backend is installed."
  else
    echo "Vosk installed. Provide an existing model to --model in the offline WAV CLI."
  fi
  echo "To download a model during setup, rerun with --model-url HTTPS_ZIP_URL."
  exit 0
fi

# Downloads are an explicit setup action. Runtime recognition never downloads.
"$PYTHON" - "$MODEL_URL" "$MODEL_DIR" <<'PY'
from pathlib import Path
import io
import sys
import urllib.parse
import urllib.request
import zipfile

url, destination = sys.argv[1:]
parsed = urllib.parse.urlparse(url)
if parsed.scheme != "https":
    raise SystemExit("Model URL must use HTTPS")
root = Path(destination).expanduser().resolve()
root.mkdir(parents=True, exist_ok=True)
with urllib.request.urlopen(url, timeout=90) as response:
    archive = response.read()
with zipfile.ZipFile(io.BytesIO(archive)) as zf:
    names = zf.namelist()
    if not names or any(
        name.startswith("/") or ".." in Path(name).parts or "\\" in name
        for name in names
    ):
        raise SystemExit("Unsafe or empty model archive")
    top = {Path(name).parts[0] for name in names if Path(name).parts}
    if len(top) != 1:
        raise SystemExit("Model archive must have one top-level directory")
    for member in zf.infolist():
        if member.is_dir():
            continue
        target = (root / member.filename).resolve()
        if not target.is_relative_to(root):
            raise SystemExit("Model archive contains an unsafe path")
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member) as source, target.open("wb") as sink:
            import shutil
            shutil.copyfileobj(source, sink)
    print(f"Model extracted under: {root / next(iter(top))}")
PY
