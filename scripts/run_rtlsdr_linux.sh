#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${1:-}"
if [[ -z "$APP" ]]; then
    echo "Usage: $0 <python-script> [arguments...]" >&2
    exit 2
fi
shift
if [[ ! -f "$APP" ]]; then
    echo "Python application not found: $APP" >&2
    exit 2
fi

# Linux librtlsdr opens USB directly; udev permissions must already be configured.
PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    echo "Missing SDRForge virtual environment; run: bash scripts/install_rtlsdr_linux.sh" >&2
    exit 1
fi
exec env PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON" -u "$APP" "$@"
