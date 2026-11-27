#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
version=1.15.0
digest=0ec2e5b2c3cd82b7106d19cb42d8466450730b8cb7a9e85af712be38bf4523a1
env_dir="$PWD/.venv-quality"
if [ ! -x "$env_dir/bin/python" ]; then
    echo "Create the quality environment first." >&2
    exit 1
fi
if [ "$(uname -s)" != Linux ] || [ "$(uname -m)" != x86_64 ] || [ -n "${TERMUX_VERSION:-}" ] || [[ "${PREFIX:-}" == */com.termux/files/usr ]]; then
    echo "Automatic Doxygen installation is supported on Linux x86-64 only. Use Doxygen $version from a trusted platform package or run documentation checks in CI." >&2
    exit 1
fi
check_version() {
    local actual
    actual="$("$1" --version)" || return 1
    echo "Doxygen version: $actual"
    if [[ ! "$actual" =~ ^1\.15\.0([[:space:]]|$) ]]; then
        echo "Expected Doxygen $version, got $actual" >&2
        return 1
    fi
}
tools_dir="$env_dir/tools"
target="$tools_dir/doxygen-$version"
mkdir -p "$tools_dir"
if [ ! -x "$target/bin/doxygen" ] || [ "$(cat "$target/.archive-sha256" 2>/dev/null || true)" != "$digest" ]; then
    work="$(mktemp -d "$tools_dir/.doxygen.XXXXXX")"
    trap 'rm -rf "$work"' EXIT
    archive="$work/doxygen.tar.gz"
    curl --fail --location --retry 3 --proto '=https' \
        "https://github.com/doxygen/doxygen/releases/download/Release_1_15_0/doxygen-$version.linux.bin.tar.gz" -o "$archive"
    printf '%s  %s\n' "$digest" "$archive" | sha256sum --check -
    mkdir "$work/extracted"
    tar -xzf "$archive" -C "$work/extracted" --strip-components=1
    check_version "$work/extracted/bin/doxygen"
    printf '%s\n' "$digest" > "$work/extracted/.archive-sha256"
    rm -rf "$target"
    mv "$work/extracted" "$target"
fi
check_version "$target/bin/doxygen"
ln -sfn "../tools/doxygen-$version/bin/doxygen" "$env_dir/bin/doxygen"
echo "Installed quality Doxygen $version"
