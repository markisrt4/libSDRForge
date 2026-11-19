#!/usr/bin/env bash
# Download official Vosk Android AAR from Maven Central and inspect its native ABI.
# This does not install Python vosk or download speech models.
set -euo pipefail
VERSION="${1:-0.3.75}"
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Usage: bash scripts/fetch_vosk_android_termux.sh [version]" >&2
  exit 2
fi
if [[ "${PREFIX:-}" != *com.termux* ]]; then
  echo "Run inside native Termux." >&2
  exit 2
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! command -v curl >/dev/null 2>&1; then
  echo "Missing curl: pkg install curl" >&2
  exit 1
fi
ARTIFACT="vosk-android-${VERSION}.aar"
DEST="${HOME}/.cache/sdrforge/vosk"
mkdir -p "$DEST"
URL="https://repo.maven.apache.org/maven2/com/alphacephei/vosk-android/${VERSION}/${ARTIFACT}"
CHECKSUM_URL="${URL}.sha256"
echo "Downloading official Maven Central artifact: $URL"
curl --fail --location --show-error --silent --retry 2 --output "$DEST/$ARTIFACT" "$URL"
echo "Checking Maven Central SHA-256 digest..."
if ! curl --fail --location --show-error --silent --retry 2 --output "$DEST/$ARTIFACT.sha256" "$CHECKSUM_URL"; then
  echo "Maven Central SHA-256 sidecar unavailable; refusing unverified artifact" >&2
  exit 1
fi
python - "$DEST/$ARTIFACT" "$DEST/$ARTIFACT.sha256" <<'PY'
import hashlib, pathlib, sys
artifact, digest = map(pathlib.Path, sys.argv[1:])
expected = digest.read_text().split()[0].strip().lower()
actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
if actual != expected:
    raise SystemExit(f"SHA-256 mismatch: expected {expected}, got {actual}")
print("SHA-256 verified:", actual)
PY
bash "$ROOT/scripts/install_vosk_native_termux.sh" "$DEST/$ARTIFACT"
