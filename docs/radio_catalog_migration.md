# Radio configuration and preset ownership

## Goal

libSDRForge owns the canonical radio band/profile catalog, receiver configuration,
factory presets, and per-user presets. OpenRoadCode and other applications are
clients. UI layout, palette, FFT/waterfall presentation, and navigation remain
application-owned.

This migration must not break the existing rigctl, receiver REST, or ZMQ
telemetry contracts.

## Domain model

- **BandProfile**: stable `key`, `label`, `group`, description, default
  demodulation mode/bandwidth/step, and inclusive minimum/maximum/start
  frequencies. Preserve ORC keys such as `fm_radio`, `weather_band`,
  `airband_am`, and `ham_*` to avoid UI regressions.
- **RadioPreset**: stable `id`, profile key, label, frequency in integer Hz,
  demodulation mode, bandwidth in Hz, step in Hz, provenance
  (`factory`/`user`/`scan`), and owner namespace. The identity must not
  depend on label or frequency, which may be edited or duplicated.
- **ReceiverSettings**: receiver/hardware-specific configuration, distinct
  from profiles and user presets.
- **PresetStoreIf** and **RadioCatalogIf**: hardware-independent interfaces;
  adapters implement JSON/SQLite persistence and installed factory catalogs.
  Neither UI nor REST handler directly edits storage files.

## Storage and migration

Factory catalog ships with libSDRForge as package resources. User changes live
in an XDG/Termux-appropriate writable application-data directory, not in
the repository or factory files. Use atomic persistence and validation.
Support distinct owner namespaces without forcing ORC to manage accounts.

Provide an explicit, idempotent importer for:
- ORC `config/radio/common/*.json` and locale-specific overrides under
  `config/radio/<locale>/*.json`.
- ORC `~/.config/openroadcode/radio_presets.json`.

Import the selected locale's factory profiles and user entries with deterministic
identifiers. Record migration provenance so repeated imports never duplicate
presets. Back up the original data and never delete it automatically.
Do not hard-code Romeo as a universal default.

## Versioned control API

Use `/v1/radio/profiles` to list and inspect available profiles, and
`/v1/radio/presets` for CRUD. Proposed operations:

- `GET /v1/radio/profiles`
- `GET /v1/radio/profiles/{key}`
- `GET /v1/radio/presets?profile_key=...&owner=...`
- `POST /v1/radio/presets` (201, returns assigned stable ID)
- `PATCH /v1/radio/presets/{id}`
- `DELETE /v1/radio/presets/{id}`
- `POST /v1/radio/profiles/{key}/select`
- `POST /v1/radio/presets/{id}/tune`

Reject unsupported modes, invalid bandwidth/step, and out-of-band frequencies
with structured 4xx responses. Prevent mutation of factory presets; user
overrides are separate records. Make selection/tuning state observable through
existing receiver telemetry. Do not couple HTTP handlers to file persistence.

Keep `/v1/rf/config` for RF device settings, not preset management. Existing
rigctl frequency/mode commands must remain operational and consistent with
REST state.

ZMQ emits small catalog/preset change notifications (version, owner/profile,
changed ID) rather than broadcasting entire catalogs on every FFT frame.
Clients fetch full snapshots over REST.

## Rollout

1. Implement validated catalog/preset models, interfaces, storage adapters,
   and unit tests entirely within libSDRForge.
2. Package factory profiles and add explicit, repeatable ORC import CLI.
3. Add REST endpoints and integration tests using simulated receivers.
4. Add catalog change notifications and client reconnection/reload behavior.
5. Replace ORC's catalog loader with an SDRForge REST adapter, retaining a
   read-only legacy fallback during rollout. Keep existing ORC UI value types.
6. Switch ORC preset save/remove and profile selection to SDRForge; test FM,
   HAM/NFM, AIR/AM, WEATHER, scanner, and existing rigctl clients.
7. Remove duplicate ORC configuration/persistence only after migration tests
   and hardware validation pass.

## Test gates

- Package installation works without ORC source checkout.
- Valid/invalid profile and preset schemas, ID stability, duplicates,
  namespace isolation, atomic persistence, and import idempotence.
- REST CRUD and profile tuning work without SDR hardware.
- Existing rigctl clients and receiver status remain unchanged.
- ORC offline/server-unavailable behavior is explicit and does not silently
  overwrite SDRForge data.
- Termux and Linux paths both work; unit tests run on Ubuntu CI.
