#!/usr/bin/env bash
# Extract native Vosk libraries from a locally supplied Android AAR.
# Usage: bash scripts/install_vosk_native_termux.sh /path/to/vosk-android.aar
# No APK, wheel, or arbitrary remote executable is downloaded.
set -euo pipefail
if [[ "${PREFIX:-}" != *com.termux* ]]; then
  echo "Run this script inside Termux." >&2; exit 2
fi
if [[ $# -ne 1 || ! -f "$1" ]]; then
  echo "Usage: bash scripts/install_vosk_native_termux.sh /path/to/vosk-android.aar" >&2
  exit 2
fi
for cmd in python readelf; do
  if ! command -v "$cmd" >/dev/null; then
    echo "Missing $cmd. Install with: pkg install python binutils" >&2
    exit 1
  fi
done
DEST="$HOME/.local/lib/sdrforge-vosk"
mkdir -p "$DEST"
python - "$1" "$DEST" <<'PY'
import pathlib, shutil, sys, zipfile
archive, dest = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
with zipfile.ZipFile(archive) as zf:
    names = set(zf.namelist())
    prefix = "jni/arm64-v8a/"
    primary = prefix + "libvosk.so"
    if primary not in names:
        raise SystemExit("AAR does not contain jni/arm64-v8a/libvosk.so")
    extracted = []
    for name in sorted(names):
        if name.startswith(prefix) and name.endswith(".so") and "/" not in name[len(prefix):]:
            target = dest / pathlib.Path(name).name
            with zf.open(name) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            extracted.append(target)
    print("Extracted:", *(str(path) for path in extracted), sep="\n  ")
PY
if ! readelf -h "$DEST/libvosk.so" | grep -Eq 'Machine:.*AArch64'; then
  echo "ERROR: library is not ELF AArch64" >&2; exit 1
fi
echo "=== Native dependencies ==="
readelf -d "$DEST/libvosk.so" | grep NEEDED || true
echo "=== Vosk C API symbols ==="
if command -v nm >/dev/null; then
  nm -D "$DEST/libvosk.so" 2>/dev/null | grep -E ' vosk_(model_new|recognizer_new|recognizer_accept_waveform)$' || true
fi
echo "=== Loader smoke test ==="
LD_LIBRARY_PATH="$DEST${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" python - "$DEST/libvosk.so" <<'PY'
import ctypes, sys
try:
    library = ctypes.CDLL(sys.argv[1])
    for symbol in ("vosk_model_new", "vosk_recognizer_new", "vosk_recognizer_accept_waveform"):
        getattr(library, symbol)
except (OSError, AttributeError) as exc:
    raise SystemExit(f"FAILED: {exc}\nThis AAR may require Android-specific libraries or dependencies.") from exc
print("PASS: libvosk.so loaded and required C API symbols resolved")
PY
echo "Native library ready: $DEST/libvosk.so"
echo "Next: python -m sdrforge.weather.offline_wav weather_16k.wav --model \"\$HOME/models/vosk-model-small-en-us-0.15\" --vosk-library \"$DEST/libvosk.so\" --location Detroit"
