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
constraints="$PWD/requirements/quality-constraints.txt"
extras="dev,quality"
if [ -n "${TERMUX_VERSION:-}" ] || [[ "${PREFIX:-}" == */com.termux/files/usr ]]; then
    if [ ! -x "$PREFIX/bin/ruff" ]; then
        echo "Install native packages: pkg install python-numpy python-scipy ruff" >&2
        exit 1
    fi
    extras="dev,quality-termux"
    ln -sfn "$PREFIX/bin/ruff" "$env_dir/bin/ruff"
    "$env_dir/bin/ruff" --version
    constraints="$(mktemp "${TMPDIR:-$PREFIX/tmp}/sdrforge-constraints.XXXXXX")"
    trap 'rm -f "$constraints"' EXIT
    grep -Ev '^(numpy|scipy)==' requirements/quality-constraints.txt > "$constraints"
    "$env_dir/bin/python" - "$PREFIX/bin/python" "$constraints" <<'PY'
import importlib
import json
import pathlib
import subprocess
import sys
import sysconfig

native_python, constraints = sys.argv[1:]
native_info = json.loads(subprocess.check_output(
    [native_python, "-c", "import json, sys, sysconfig; print(json.dumps([list(sys.version_info[:2]), sysconfig.get_config_var('SOABI'), sysconfig.get_path('purelib')]))"],
    text=True,
))
if native_info[:2] != [list(sys.version_info[:2]), sysconfig.get_config_var("SOABI")]:
    raise SystemExit("Native Python ABI differs from quality environment; recreate with Termux Python.")
native_site = pathlib.Path(native_info[2])
site = pathlib.Path(sysconfig.get_path("purelib"))
sources = []
for name in ("numpy", "scipy"):
    metadata = list(native_site.glob(f"{name}-*.dist-info"))
    package = native_site / name
    if not package.is_dir() or len(metadata) != 1:
        raise SystemExit(f"Install native python-{name} with pkg first.")
    sources.extend([package, *metadata, *native_site.glob(f"{name}.libs")])
for source in sources:
    target = site / source.name
    if target.exists() and not target.is_symlink():
        raise SystemExit(f"Existing package at {target}; recreate .venv-quality.")
for source in sources:
    target = site / source.name
    if target.is_symlink():
        target.unlink()
    target.symlink_to(source, target_is_directory=True)
with open(constraints, "a", encoding="utf-8") as output:
    for name in ("numpy", "scipy"):
        module = importlib.import_module(name)
        print(f"Using native {name} {module.__version__}")
        output.write(f"{name}=={module.__version__}\n")
PY
fi
"$env_dir/bin/python" -m pip --isolated install --upgrade -c "$constraints" -e ".[$extras]"
"$env_dir/bin/python" -m pip check

# Keep unsupported platforms usable for Python-only quality checks.
if [ "${QUALITY_SKIP_DOXYGEN:-0}" != 1 ]; then
    if [ "$(uname -s)" = Linux ] && [ "$(uname -m)" = x86_64 ] && [ -z "${TERMUX_VERSION:-}" ] && [[ "${PREFIX:-}" != */com.termux/files/usr ]]; then
        bash scripts/install_quality_doxygen.sh
    else
        echo "Skipping automatic Doxygen provisioning on this platform; use CI for documentation checks."
    fi
fi
