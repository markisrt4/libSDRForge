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
