#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Source from SDRForge launchers to load persistent, optional radio-region settings.
# This is data-only configuration: never execute shell code from the config file.
sdrforge_load_radio_region() {
    local config="${SDRFORGE_REGION_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/sdrforge/radio-region.conf}"
    [[ -f "$config" ]] || return 0
    local key value
    while IFS='=' read -r key value || [[ -n "$key" ]]; do
        case "$key" in
            SDRFORGE_RADIO_ROOT)
                if [[ -z "${SDRFORGE_RADIO_ROOT:-}" && -n "$value" ]]; then
                    export SDRFORGE_RADIO_ROOT="$value"
                fi
                ;;
            SDRFORGE_RADIO_LOCALE)
                if [[ -z "${SDRFORGE_RADIO_LOCALE:-}" && -n "$value" ]]; then
                    export SDRFORGE_RADIO_LOCALE="$value"
                fi
                ;;
        esac
    done < "$config"
}
