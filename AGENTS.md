# AGENTS.md - libSDRForge development guide

## Mission

Build a standalone, library-first SDR toolkit for Linux, Raspberry Pi, and
Android/Termux. Follow the `libMusicForge` project conventions. No ORC-specific
services, UI, or audio routing in the library.

## Architecture

- Use `src/sdrforge/` with capability-based interfaces, typed domain models,
  hardware adapters, DSP components, receiver facades, RDS protocol decoding,
  and diagnostics.
- Keep basic DSP and offline tests usable without RTL-SDR hardware or USB drivers.
- Do not import OpenRoadCode `controllers`, `hardware_io`, or UI modules.
- Keep hardware adapter dependencies optional, and support synthetic or recorded
  IQ input.
- Preserve validated DSP behavior during extraction. Do not rewrite filters,
  timing loops, or demodulators merely to move modules.
- Keep the public receiver facade small and avoid premature API promises.
- Keep ORC service lifecycle, audio routing, resource scheduling, and UI in ORC.
- Check license obligations before copying code; retain existing MIT notices
  from ORC source files in any extracted copies.

## Before making changes

1. Inspect existing modules, documentation, and tests.
2. Work on a feature branch and use pull requests for substantive changes.
3. Add deterministic offline tests for any public behavior.
4. Update installation docs and examples when APIs change.
5. Avoid unnecessary frameworks, runtime services, and mandatory hardware tools.
6. Never merge directly into `main` without explicit authorization.

## CI and Codex cost policy

- Do not run tests, lint, type checks, builds, or benchmarks in a Codex cloud VM
  unless the user explicitly authorizes that specific execution.
- Write tests and let GitHub Actions run them on Ubuntu runners.
- Perform RF/USB hardware tests only on the user's physical devices.
- Read CI logs and fix targeted failures rather than running VM test loops.
- Report exactly which tests were run and passed; do not infer a green result.

## Extraction gates

1. Audit ORC DSP code and third-party alternatives.
2. Define minimal source, receiver, PCM, metadata, diagnostics interfaces.
3. Extract algorithms and unit tests without behavior changes.
4. Extract optional RTL-SDR hardware adapter and standalone examples.
5. Integrate ORC against libSDRForge and remove duplication only after CI
   and real-device regression testing.

## Termux diagnostic output and clipboard

- When providing Termux diagnostics for the user to paste into chat, keep **actual stdout and stderr** visible and copy the output (not the command text) to the Android clipboard.
- For ordinary, non-hardware diagnostics, `2>&1 | tee >(termux-clipboard-set)` may be used. Be mindful that pipelines and process substitution affect process lifetime and may obscure exit codes.
- **Never use a live clipboard pipeline such as `tee >(termux-clipboard-set)` around USB-sensitive commands**, including `termux-usb` authorization/handoff, RTL-SDR capture, or other hardware launchers. This pattern has caused the RTL-SDR Termux launcher to hang.
- For USB-sensitive commands, first redirect stdout and stderr to a log; wait until the hardware command exits; then display the log and copy it with a bounded timeout. Report the hardware exit status separately from clipboard status.
- Generic safe example:
  ```bash
  LOG="$HOME/hardware_diagnostic.log"
  hardware_command > "$LOG" 2>&1
  STATUS=$?
  cat "$LOG"
  echo "Hardware exit status: $STATUS"
  timeout 5 termux-clipboard-set < "$LOG"
  echo "Clipboard exit status: $?"
  ```
- For libSDRForge IQ captures, prefer `bash scripts/run_rtlsdr_termux_logged.sh examples/rds_iq_replay.py capture --frequency 94.7 --seconds 3 --acquisition-mode async --output "$HOME/probe.iq"` from the libSDRForge repository. Do not add a live `tee` pipeline around this wrapper.
- Finish Termux:API GPS lookup before entering the USB-authorized capture subprocess. Never expose GPS coordinates in diagnostic logs by default.
- On Termux, RTL-SDR hardware acquisition must use **async** mode, never sync.
