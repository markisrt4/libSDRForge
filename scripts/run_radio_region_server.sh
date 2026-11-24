#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Start a process with optional persistent radio-region settings.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/radio_region_env.sh
source "$ROOT/scripts/radio_region_env.sh"
sdrforge_load_radio_region
exec "$@"
