# libSDRForge

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
python -m mypy
python -m build
```

No tests, builds, or benchmarks are automatically run in a Codex VM.
GitHub Actions should run hardware-independent CI on Ubuntu; test USB
behavior only on a physical device.

## Quick start: Python API

```python
from sdrforge import RadioSession

# Frequency is in MHz. Auto tuner gain and stereo are the defaults.
with RadioSession.fm(104.3, rds=True) as radio:
    for frame in radio.stream():
        pcm = frame.audio  # NumPy float PCM, 48,000 frames/sec, stereo
        rds = frame.rds     # optional station metadata
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
fm_pcm = pcm_by_channel["fm"]       # 48 kHz stereo float32
rf_metrics = receiver.telemetry    # uncalibrated spectral estimates
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

## Android / Termux

On Android, ordinary Linux USB enumeration is not sufficient. The supported
experimental path uses **Termux:API USB permission**, `termux-usb`, and a
compatible `librtlsdr` build exposing `rtlsdr_open_fd`. Install Termux:API
and its companion Android application, and ensure the RTL-SDR is visible to
Android's USB host system.

The helper `scripts/test_rtlsdr_termux.sh` enumerates the current USB
device, requests permission, and launches the example with
`TERMUX_USB_FD`. Do not hardcode USB bus/device paths; they change on
reconnection. With more than one attached USB device, explicitly set
`SDRFORGE_USB_DEVICE`.

```bash
cd ~/src/libSDRForge

bash scripts/test_rtlsdr_termux.sh \
  "$PWD/examples/rtl_fm_record.py" \
  --frequency 104.3 --seconds 10 --mono --auto-gain \
  --acquisition-mode async --output "$HOME/fm.wav"

bash scripts/test_rtlsdr_termux.sh \
  "$PWD/examples/rtl_fm_live.py" \
  --frequency 104.3 --mono --auto-gain
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

## Architecture

```text
OpenRoadCode / CLI / other applications
           |
     RadioSession API
           |
   WbfmReceiver + RDS
           |
   DSP / downconverter
           |
       SdrSourceIf
           |
  RTL-SDR or injected IQ source
```

The library owns radio acquisition, demodulation, and diagnostics.
Applications own presentation, audio routing, process lifecycle,
USB permission UX, and device reconnection policy.

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
