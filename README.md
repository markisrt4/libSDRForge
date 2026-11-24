# libSDRForge

## Regional radio profiles and presets

SDRForge ships locale-neutral factory radio profiles. The live REST server can
optionally overlay external JSON profiles from a `common/` directory and a
selected locale directory. External profiles replace matching factory profiles
and their factory presets; unrelated packaged profiles remain available.
**No locale is selected automatically**, and the overlay never writes to the
persistent user preset JSON file.

For example, when OpenRoadCode is checked out alongside libSDRForge:

```bash
python examples/live_transport_server.py --simulate \
  --radio-root ../OpenRoadCode/config/radio --radio-locale romeo
```

For managed Linux or Termux services, the same options can be supplied through
`SDRFORGE_RADIO_ROOT` and `SDRFORGE_RADIO_LOCALE` in the server process
environment. Command-line options override the environment settings. Example:

```bash
export SDRFORGE_RADIO_ROOT="$HOME/src/OpenRoadCode/config/radio"
export SDRFORGE_RADIO_LOCALE=romeo
```

Set these in the environment of the actual service or USB handoff launcher,
not merely in a separate interactive shell. The radio root must exist on the
machine running SDRForge; no locale is assumed when unset.

Use the same flags with the normal hardware-backed server invocation.
The `/v1/radio/profiles` and `/v1/radio/presets` endpoints then expose
regional FM, aviation, and scanner profiles as available in the supplied
configuration. User-created presets remain in the independent SDRForge preset
store (default `~/.config/sdrforge/radio_presets.json`) and are not deleted.
The external directory is an optional compatibility source, not a runtime
dependency on OpenRoadCode.


**A reusable Python software-defined radio toolkit for Linux, Raspberry Pi, and Android/Termux.**

libSDRForge separates IQ acquisition, DSP, and radio decoding from the applications
that use them. The foundation supports **wideband FM (WFM)**, **AM**, and **narrowband FM (NFM)** with 48 kHz PCM output and optional stereo WFM/RDS decoding. It grew out of the SDR
implementation in [OpenRoadCode](https://github.com/markisrt4/OpenRoadCode),
but the library does **not** depend on OpenRoadCode.

**Status: v0.1.0 foundation.** WFM reception, standalone WAV recording, and
live playback have been exercised on Termux with an RTL2832U/R820T dongle.
The Python API and offline DSP tests do not require SDR hardware. Automatic
USB reconnection, production audio output, and the experimental TUI are not
release-ready.

## Features

- **Public receiver API:** `RadioSession.fm(104.3)` accepts familiar MHz values.
- **Mixed-mode DSP:** `MultiModeRadioReceiver` demodulates multiple AM/NFM/WFM channels from one IQ capture.
- **48 kHz PCM:** `RadioFrame.audio` is a NumPy float array; mono or stereo.
- **RDS:** optional station metadata in stereo mode.
- **RTL-SDR adapter:** synchronous or asynchronous IQ acquisition; async is
  recommended for continuous listening.
- **Hardware-independent DSP:** synthetic or recorded IQ can be processed
  without an RTL-SDR dongle.
- **Diagnostics:** processed samples, DSP performance, discontinuities,
  stereo lock, and adapter queue/drop counters.
- **Standalone examples:** WAV recording and live playback via FFplay.

## Requirements and installation

Python **3.11+**, NumPy, and SciPy are required. An RTL-SDR receiver also
requires a compatible `librtlsdr` shared library and attached hardware.
FFplay is **only** needed for the optional live audio example.

```bash
git clone https://github.com/markisrt4/libSDRForge.git
cd libSDRForge
python -m pip install -e .
```

For offline tests and developer tooling:

```bash
python -m pip install -e ".[dev,quality]"
python -m pytest -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy
python -m build
```

Developers who use `pre-commit` can enable the optional local Ruff checks:

```bash
pre-commit install
```

Every non-private module, class, function, method, and property under
`src/sdrforge` must use a `"""!` Doxygen docstring with `@brief`, `@param`,
and `@return` annotations as applicable. Interfaces—including private
`Protocol` and abstract base classes—and all of their callable members must be
documented when introduced. Check documentation coverage and build the HTML API
reference with:

```bash
python scripts/check_docstrings.py
doxygen Doxyfile
```

The generated reference is written to `build/doxygen/html`. GitHub Actions
runs both commands and treats missing docstrings, malformed documentation,
and Doxygen warnings as quality-control failures.

No tests, builds, or benchmarks are automatically run in a Codex VM.
GitHub Actions should run hardware-independent CI on Ubuntu; test USB
behavior only on a physical device.

## Offline NOAA weather speech recognition (optional)

The NOAA WAV transcription CLI uses [Vosk](https://alphacephei.com/vosk/).
Platform installers also install **eSpeak NG** and **FFmpeg** for
generating and converting test audio:

```bash
# Ubuntu / Debian / Raspberry Pi OS
bash scripts/install_weather_linux.sh \
  --model-url "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"

# Android / Termux (installs eSpeak, FFmpeg and base SDRForge, not Vosk)
bash scripts/install_weather_termux.sh
```

Each environment has its **own** `$HOME/models` directory. Installing a
model on an Ubuntu VM does not make it available to Termux. The Termux
installer installs the Termux `espeak` package, FFmpeg, and base libSDRForge.
Vosk has no matching PyPI distribution for the observed Termux Android ARM64 /
Python 3.14 environment, so the Termux script intentionally skips Vosk.
Offline WAV transcription is **not functional on Termux** until a compatible
native Vosk backend is provided. The optional `--model-url` flag downloads
model data only and does not fix the missing native library.

Vosk is **not** part of the base SDR installation. Install the optional
`weather` extra using the repository helper:

```bash
bash scripts/install_weather.sh
# Equivalent: python -m pip install -e ".[weather]"
```

A **local Vosk speech model** is required separately. Choose an English
model from the [official Vosk models list](https://alphacephei.com/vosk/models),
then either extract the model yourself under `~/models/`, or pass its
official HTTPS ZIP download URL to the installer:

```bash
bash scripts/install_weather.sh \
  --model-url "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip" \
  --model-dir "$HOME/models"

python -m sdrforge.weather.offline_wav weather.wav \
  --model "$HOME/models/vosk-model-small-en-us-0.15" \
  --location Detroit
```

The model download is an **explicit one-time setup step**. Subsequent
recognition runs locally with no network requests. The CLI expects a
mono, uncompressed 16-bit PCM WAV. If no model URL is provided, the
installer only installs the Python dependency and does not download
anything. On platforms without a compatible Vosk binary wheel, such
as some Termux/Python combinations, installation may require a
platform-specific Vosk build; Linux and Raspberry Pi should be
validated first.


### Experimental native Vosk C API on Termux

Termux diagnostics confirmed Android aarch64, Python 3.14 and **no** installed
Vosk Python package or `libvosk.so`. The native `VoskNativeAdapter` uses
`ctypes` and does not require the Vosk PyPI wheel. It **does require** a
separately obtained `libvosk.so` compiled for the host Android/Termux ABI;
a Linux aarch64 `.so` is not interchangeable with Android. No compatible
binary or native build has been verified yet.

Once an Android-compatible native library and model are available:

```bash
python -m sdrforge.weather.offline_wav weather_16k.wav \\
  --model "$HOME/models/vosk-model-small-en-us-0.15" \\
  --vosk-library "$HOME/lib/libvosk.so" --location Detroit
```

The preferred source is the official Maven Central Android artifact. On Termux:

```bash
pkg install -y curl binutils
bash scripts/fetch_vosk_android_termux.sh 0.3.75
```

This downloads `com.alphacephei:vosk-android:0.3.75`, checks the
repository's SHA-256 sidecar, then invokes the native loader test. If Maven
Central does not provide that checksum or the artifact lacks an ARM64
library, the script fails explicitly rather than silently using an
unverified/incompatible binary. Passing the loader test still does not
prove that a speech model can initialize or transcribe audio.

To inspect an **existing, trusted Android Vosk AAR** containing the ARM64
shared library, use:

```bash
pkg install -y binutils
bash scripts/install_vosk_native_termux.sh /path/to/vosk-android.aar
```

The script extracts `jni/arm64-v8a/*.so` into
`~/.local/lib/sdrforge-vosk/`, checks the ELF architecture and required
C API symbols, and attempts a dynamic-loader smoke test. It deliberately
does **not** download an unverified binary or claim that every Android AAR
will load inside Termux. Some builds have unresolved Android-specific
libraries or other ABI requirements. Obtain an AAR from a trusted release
source and verify its provenance before running this script.

Do not use `--vosk-library` with a generic Linux binary. Native C API
integration and validation tests are committed, but live recognition on
Termux remains unverified until the shared library is available.

## Quick start: Python API

```python
from sdrforge import RadioSession

# Frequency is in MHz. Auto tuner gain and stereo are the defaults.
with RadioSession.fm(104.3, rds=True) as radio:
    for frame in radio.stream():
        pcm = frame.audio  # NumPy float PCM, 48,000 frames/sec, stereo
        rds = frame.rds  # optional station metadata
        status = radio.status
        print(status.stereo_locked, status.discontinuities)
        # Send pcm to an audio sink, file encoder, or application buffer.
```

For a simple mono receiver:

```python
from sdrforge import RadioSession

with RadioSession.fm(104.3, stereo=False) as radio:
    frame = radio.read()
    print(frame.audio.shape)
```

**API reference:**

| API | Purpose |
| --- | --- |
| `RadioSession.fm(frequency_mhz, stereo=True, rds=False, gain_db=None, source=None, rf_warmup_seconds=2.0)` | Create a WFM session using MHz |
| `RadioSession(frequency_hz=..., mode="stereo", ...)` | Lower-level constructor using Hz |
| `with radio:` / `radio.start()` / `radio.stop()` | Manage device lifecycle |
| `radio.read()` | Decode one IQ block into a `RadioFrame` |
| `radio.stream()` | Iterate decoded frames until stopped |
| `radio.status` | Snapshot of acquisition/DSP and stereo status |
| `radio.source.get_acquisition_stats()` | RTL-SDR queue and dropped-block counters |

`RadioSession.fm()` validates the 87.5–108.0 MHz broadcast band and rejects
RDS in mono mode. `gain_db=None` enables automatic tuner gain. Use
`source=` to inject another implementation of `SdrSourceIf` for testing or
other SDR hardware. The session **does not play sound itself**: applications
own audio buffering, playback, and UI.

For offline DSP, construct a `WbfmReceiver` and call `process(iq_block)`
with `IqBlock` samples. The current DSP pipeline expects **2.4 MSPS
unsigned 8-bit interleaved IQ** and emits 48 kHz audio.

## Mixed-mode reception from shared IQ

The standalone receiver accepts captured IQ blocks supplied by the caller;
it does not open USB hardware, route audio, or manage application workers.

```python
from sdrforge import MultiModeRadioReceiver, RadioChannel

receiver = MultiModeRadioReceiver(stereo_wfm=True, rds_wfm=True)
receiver.add_channel(RadioChannel("fm", 104_300_000, "WFM"))
receiver.add_channel(RadioChannel("weather", 104_900_000, "NFM"))
receiver.add_channel(RadioChannel("airband", 104_500_000, "AM"))

# block: IqBlock of 2.4 MSPS interleaved unsigned 8-bit IQ,
# centered so all configured channels fit in the captured RF span.
pcm_by_channel = receiver.process(block)
fm_pcm = pcm_by_channel["fm"]  # 48 kHz stereo float32
rf_metrics = receiver.telemetry  # uncalibrated spectral estimates
rds_by_channel = receiver.rds_status
```

Use `receiver.retune_channel(name, frequency_hz)` and
`receiver.remove_channel(name)` for per-channel lifecycle.
`receiver.reset(preserve_metadata=True)` clears DSP state after an IQ
discontinuity while retaining published RDS metadata. All requested
channels must fit within the actual source capture bandwidth.

The low-level `AmMonoDemodulator` and `NbfmMonoDemodulator` also
accept raw 2.4 MSPS `IqBlock` data. Channelized counterparts operate
on 240 kSPS complex baseband IQ.

**RF telemetry caveat:** signal power, FFT noise-floor contrast and
estimated SNR are diagnostic measurements, **not calibrated RF SNR**.
The `RdsSignalDiagnostics` rolling multiplex FFT similarly reports
relative 19 kHz pilot and 57 kHz RDS-band energy, not RDS bit-error rate.

## Automated Linux installation (Ubuntu / Debian)

From the currently checked-out branch, install system libraries, create or reuse `.venv`, and install Python dependencies:

```bash
bash scripts/install_rtlsdr_linux.sh --dev
bash scripts/install_rtlsdr_linux.sh --check
```

Omit `--dev` for runtime-only installation. `--no-apt` skips operating-system packages. The installer does not switch Git branches or require attached SDR hardware. It checks that the RTL-SDR shared library and FFplay are installed, but does not attempt live reception.

## Linux / Raspberry Pi: standalone examples

With a working `librtlsdr` installation and attached dongle:

```bash
python examples/rtl_fm_record.py --frequency 104.3 --seconds 10 \
  --mono --auto-gain --acquisition-mode async --output fm.wav

python examples/rtl_fm_live.py --frequency 104.3 \
  --mono --auto-gain --acquisition-mode async
```

The live example uses FFplay for raw 48 kHz signed 16-bit PCM. Use Ctrl+C
to stop. Its diagnostics report IQ queue depth, dropped blocks, and stream
discontinuities. Monitor these values during long sessions: asynchronous
capture prevents synchronous USB read stalls but cannot compensate for a
DSP pipeline that persistently falls behind.

## Linux launcher

On Linux, USB access is handled by librtlsdr and the operating system's
udev permissions. The optional convenience launcher passes the repository
source directory on PYTHONPATH and forwards arguments unchanged:

```bash
bash scripts/run_rtlsdr_linux.sh examples/rds_tmc_live.py --frequency 104.3 --seconds 60
```

No USB-FD forwarding is needed. If the dongle cannot open, verify the
Linux udev rules and device ownership instead of using sudo by default.

## Android / Termux

On Android, ordinary Linux USB enumeration is not sufficient. The supported
experimental path uses **Termux:API USB permission**, `termux-usb`, and a
compatible `librtlsdr` build exposing `rtlsdr_open_fd`. Install Termux:API
and its companion Android application, and ensure the RTL-SDR is visible to
Android's USB host system.

The general-purpose launcher `scripts/run_rtlsdr_termux.sh` enumerates the current USB
device, requests permission, and launches the example with
`TERMUX_USB_FD`. Do not hardcode USB bus/device paths; they change on
reconnection. With more than one attached USB device, explicitly set
`SDRFORGE_USB_DEVICE`.

```bash
cd ~/src/libSDRForge

bash scripts/run_rtlsdr_termux.sh \
  "$PWD/examples/rtl_fm_record.py" \
  --frequency 104.3 --seconds 10 --mono --auto-gain \
  --acquisition-mode async --output "$HOME/fm.wav"

bash scripts/run_rtlsdr_termux.sh \
  "$PWD/examples/rtl_fm_live.py" \
  --frequency 104.3 --mono --auto-gain

bash scripts/run_rtlsdr_termux.sh \
  "$PWD/examples/rds_tmc_live.py" \
  --frequency 104.3 --seconds 60 --acquisition-mode sync \
  --jsonl "$HOME/tmc_live.jsonl"
```

**Troubleshooting:** If `termux-usb -l` reports no device, first check the
USB-C connection, OTG/host support, Android permission prompts, and whether
Android itself enumerates the dongle. This is an Android/USB detection problem
before it is a libSDRForge DSP problem. If permission succeeds but opening
fails, verify that your `librtlsdr` exports `rtlsdr_open_fd`.
If FFplay rejects audio options, confirm the installed build supports
`-ch_layout`. If audio speed or pitch is wrong, verify asynchronous
acquisition rather than changing WAV sample-rate headers.

The `examples/rtl_fm_tui.py` curses prototype is **experimental**.
USB-launched processes may lack interactive terminal input, so the TUI
is not part of the supported v0.1.0 workflow.

## Architecture and development

- [Architecture and interface map](docs/architecture.md)
- [Examples and diagnostics](examples/README.md)
- [Component test guide](component_test/README.md)
- [Contributing](CONTRIBUTING.md)

## Scope and limitations

- **Implemented:** WFM mono/stereo, AM, NFM, multi-channel IQ fanout, optional RDS, RTL-SDR acquisition,
  offline DSP tests, WAV recording, and FFplay live output.
- **Not yet implemented:** high-level AM/NFM device sessions, production
  audio sinks, robust USB hotplug/reconnect, multi-radio orchestration,
  or a production-ready interactive TUI.
- **Performance:** 2.4 MSPS DSP is CPU-intensive. Inspect dropped-block
  counters and processing throughput on each target platform.
- **API stability:** v0.1.0 is an initial foundation; future minor versions
  may refine the interface before a stable 1.0 contract.

## Project and licensing

See [AGENTS.md](AGENTS.md) for development rules and
[docs/extraction-map.md](docs/extraction-map.md) for the ORC extraction plan.

Repository license: **Apache-2.0**. Extracted source files retain
their original MIT copyright notices where applicable.
