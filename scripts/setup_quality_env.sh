#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
unset PYTHONPATH PYTHONHOME
export PYTHONNOUSERSITE=1
env_dir="$PWD/.venv-quality"
if [ ! -f "$env_dir/pyvenv.cfg" ]; then
    "${QUALITY_PYTHON:-python3}" -m venv "$env_dir"
fi
if ! grep -Eiq '^include-system-site-packages *= *false$' "$env_dir/pyvenv.cfg"; then
    echo "Quality environment must not inherit system packages." >&2
    exit 1
fi
"$env_dir/bin/python" -m pip --isolated install --upgrade -c requirements/quality-constraints.txt -e '.[dev,quality]'
"$env_dir/bin/python" -m pip check

# Keep unsupported platforms usable for Python-only quality checks.
if [ "${QUALITY_SKIP_DOXYGEN:-0}" != 1 ]; then
    if [ "$(uname -s)" = Linux ] && [ "$(uname -m)" = x86_64 ] && [ -z "${TERMUX_VERSION:-}" ] && [[ "${PREFIX:-}" != */com.termux/files/usr ]]; then
        bash scripts/install_quality_doxygen.sh
    else
        echo "Skipping automatic Doxygen provisioning on this platform; use CI for documentation checks."
    fi
fi
