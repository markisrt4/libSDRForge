# libSDRForge

**An open-source, library-first toolkit for software-defined radio reception and digital signal processing.**

libSDRForge will provide reusable SDR receivers, demodulation, protocol
decoding, and diagnostics independent of any particular application. Its first
extraction target is the validated native FM stereo and RDS implementation in
[OpenRoadCode](https://github.com/markisrt4/OpenRoadCode).

**Status:** Initial package and CI foundation. DSP and RDS modules have not
yet been extracted.

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
