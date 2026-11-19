#!/usr/bin/env bash
# Diagnose Vosk feasibility on native Termux without changing packages.
set -uo pipefail
if [[ "${PREFIX:-}" != *com.termux* ]]; then
  echo "Run this script inside native Termux." >&2
  exit 2
fi
echo "=== Termux platform ==="
uname -m
python - <<'PY'
import platform, sys, sysconfig, importlib.util, ctypes.util
print("Python:", sys.version.split()[0])
print("Platform:", sys.platform, platform.machine())
print("SOABI:", sysconfig.get_config_var("SOABI"))
print("Vosk Python package:", "present" if importlib.util.find_spec("vosk") else "missing")
print("libvosk lookup:", ctypes.util.find_library("vosk") or "not found")
PY
echo
echo "=== Termux packages matching vosk/kaldi ==="
pkg search vosk 2>&1 || true
pkg search kaldi 2>&1 || true
echo
echo "=== Native library candidates ==="
for root in "$PREFIX/lib" "$HOME/.local/lib" "$HOME/src"; do
  if [[ -d "$root" ]]; then
    find "$root" -maxdepth 4 \( -name 'libvosk.so*' -o -name 'libkaldi*.so*' \) -print 2>/dev/null | head -30
  fi
done
echo
echo "=== Vosk import probe ==="
python - <<'PY'
try:
    import vosk
    print("Vosk import: OK", getattr(vosk, "__file__", ""))
except Exception as exc:
    print("Vosk import: FAILED:", type(exc).__name__, str(exc))
PY
echo
echo "No changes made. Native Android/Termux compatibility is not implied by an available model ZIP."
