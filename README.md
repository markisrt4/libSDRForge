# libSDRForge

**An open-source, library-first toolkit for software-defined radio reception and digital signal processing.**

libSDRForge will provide reusable SDR receivers, demodulation, protocol
decoding, and diagnostics independent of any particular application. Its first
extraction target is the validated native FM stereo and RDS implementation in
[OpenRoadCode](https://github.com/markisrt4/OpenRoadCode).

**Status:** Working RTL-SDR WFM mono/stereo/RDS pipeline, hardware-free tests,
standalone WAV recorder, and an initial high-level session API.

## Goals

- Hardware-independent IQ processing with deterministic offline testing.
- Optional hardware acquisition adapters, starting with RTL-SDR.
- AM, NFM, stereo FM and RDS support extracted from working ORC code.
- Portability to Linux, Raspberry Pi, and Android/Termux.
- A small stable public API and optional accelerated DSP implementations.

## Design

```text
OpenRoadCode / command-line tools / other applications
                         |
                    Receiver API
                         |
          Models, DSP and protocol decoders
                         |
               IQ source interfaces
                         |
              Optional device adapters
```

OpenRoadCode continues to own service lifecycle, UI, audio routing and
resource arbitration. libSDRForge must not depend on OpenRoadCode.

## Python API

```python
from sdrforge import RadioSession

with RadioSession(frequency_hz=104_300_000, rds_enabled=True) as radio:
    for frame in radio.stream():
        audio = frame.audio  # 48 kHz float32 PCM, two channels
        metadata = frame.rds
        print(radio.status)
```

`RadioSession` manages RTL-SDR setup, RF warmup, timestamp/drop detection,
and DSP resets. Inject a custom `SdrSourceIf` for hardware-free testing.
The current session is WFM-only and does not yet provide automatic reconnect,
audio playback buffering, or multi-channel orchestration.

## Live FM playback on Termux

The optional example uses `ffplay` as a raw 48 kHz PCM sink. Install a Termux
FFmpeg build that includes `ffplay`, then run the example inside an authorized
`termux-usb -E` session using the USB-FD launcher:

```bash
cd ~/src/libSDRForge
bash scripts/test_rtlsdr_termux.sh \
  "$PWD/examples/rtl_fm_live.py" --frequency 104.3 --mono --auto-gain
```

Async IQ acquisition is the default. Stop with Ctrl+C. The example reports
queue depth, dropped IQ blocks and discontinuities every five seconds.
If `ffplay` is unavailable, the script reports that before opening the radio.
Audio output depends on the local Termux audio environment; it is not
provided by the core library. The first live example does not implement
USB reconnect or audio underrun recovery.

## Development

Requires Python 3.11+.

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

For the full set of Linux CI checks:

```bash
python -m pip install -e ".[dev,quality]"
python -m ruff check src tests
python -m mypy
python -m build
```

Hardware is not needed for the initial tests. Termux support and
platform-specific build availability must be validated during extraction.

## Roadmap

1. Audit ORC SDR modules and established DSP/hardware libraries.
2. Define public IQ source, receiver, audio, RDS and diagnostics contracts.
3. Extract the validated DSP/RDS algorithms and corresponding tests.
4. Add optional RTL-SDR adapter and independent command-line examples.
5. Integrate ORC against the library and remove duplicates after regression testing.

See [the migration map](docs/extraction-map.md) and [AGENTS.md](AGENTS.md)
for details.

## License

Apache-2.0 for the repository. Existing ORC source files carry MIT notices
which must be preserved when code is extracted.
