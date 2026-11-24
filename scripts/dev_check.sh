#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
mode="${1:---all}"
case "$mode" in
    --all|--lint|--format|--test) ;;
    *) echo "Usage: bash scripts/dev_check.sh [--all|--lint|--format|--test]" >&2; exit 2 ;;
esac
if [ "$#" -gt 0 ]; then shift; fi
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
log_dir="${XDG_CACHE_HOME:-$HOME/.cache}/sdrforge"
mkdir -p "$log_dir" || exit 1
log="$log_dir/dev-check.log"
run_checks() {
    local rc=0
    echo "=== Python environment ==="
    command -v python
    python -c 'from pathlib import Path; import sdrforge; p = Path(sdrforge.__file__).resolve(); print(p); assert p.is_relative_to(Path("src").resolve()), "Not importing checkout"' || return 1
    if [ "$mode" = --all ] || [ "$mode" = --lint ]; then
        ruff check "${@:-.}" || rc=1
    fi
    if [ "$mode" = --all ] || [ "$mode" = --format ]; then
        ruff format --check "${@:-.}" || rc=1
    fi
    if [ "$mode" = --all ] || [ "$mode" = --test ]; then
        python -m pytest tests/unit/ -q || rc=1
    fi
    return "$rc"
}
run_checks "$@" 2>&1 | tee "$log"
rc=$?
if command -v termux-clipboard-set >/dev/null 2>&1; then
    termux-clipboard-set < "$log" || true
elif [ -n "${WAYLAND_DISPLAY:-}" ] && command -v wl-copy >/dev/null 2>&1; then
    wl-copy < "$log" || true
elif [ -n "${DISPLAY:-}" ] && command -v xclip >/dev/null 2>&1; then
    xclip -selection clipboard < "$log" || true
fi
echo "Log saved to $log"
exit "$rc"
