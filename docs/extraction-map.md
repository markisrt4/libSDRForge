# OpenRoadCode to libSDRForge migration map

The implementation baseline is OpenRoadCode `native-sdr-radio` with 102 DSP
unit tests reported passing on the hardware owner's Ubuntu checkout.

| Source in ORC | Destination in libSDRForge |
| --- | --- |
| `hardware_io/sdr/sdr_types.py` | `models/` |
| `hardware_io/sdr/sdr_source_if.py` | `interfaces/` |
| `hardware_io/sdr/rtl_sdr_source.py` | `adapters/` (optional) |
| `controllers/radio/dsp/digital_downconverter.py` | `dsp/` |
| `controllers/radio/dsp/fm_multiplex_discriminator.py` | `dsp/` |
| `controllers/radio/dsp/fm_stereo_decoder.py` | `dsp/` |
| `controllers/radio/dsp/channelized_*demodulator.py` | `receivers/` |
| `controllers/radio/dsp/rds_*.py` | `protocols/rds/` |
| `controllers/radio/rds_receiver_controller.py` | `protocols/rds/` |
| `controllers/radio/virtual_receiver_manager.py` | `core/` |
| `controllers/radio/multi_mode_radio_receiver.py` | `receivers/` |
| `controllers/radio/dsp/channel_rf_telemetry.py` | `diagnostics/` |
| `controllers/radio/dsp/rds_signal_diagnostics.py` | `diagnostics/` |
| `controllers/radio/dsp_performance_monitor.py` | `diagnostics/` |
| `controllers/radio/dsp/unit_test/` | `tests/` |
| `controllers/radio/native_radio_service.py` | Stays in ORC |
| `controllers/radio/radio_audio_session.py` | Stays in ORC |
| `hardware_io/audio/`, ORC UI and bridge | Stay in ORC |

## Third-party alternatives

- **liquid-dsp**: candidate for native speedups after independent benchmarking.
- **SoapySDR**: candidate for a future optional hardware backend.
- **GNU Radio**: alternative signal framework, not a mandatory dependency.
- **librtlsdr/pyrtlsdr**: compare against the current RTL-SDR adapter.
- **csdr**: lightweight signal-processing alternative, not initially required.

Do not change validated DSP algorithms during the move. First achieve
independent offline CI, then migrate ORC imports, then remove duplication.

## Extraction progress (2026-11-10)

First batch copied to `src/sdrforge/`: IQ models, SDR source interface,
DigitalDownconverter, FmMultiplexDiscriminator, FmStereoDecoder, and their
three original offline test modules. Algorithm bodies are unchanged; imports
now reference the standalone package. ORC copies remain untouched.

**Verification pending:** GitHub Actions must validate the migrated tests,
static checks, and package build. No local or Codex VM tests were run.

Next: extract RDS signal-processing stages and their tests, then complete
receiver composition and optional RTL-SDR hardware support.
