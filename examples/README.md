# libSDRForge examples

Run from the repository root after installing the library with
`python -m pip install -e .`. The [main README](../README.md) covers RTL-SDR
setup, optional dependencies, and Termux launchers.

## Radio and transport

| Example | Use it to |
| --- | --- |
| [rtl_fm_live.py](rtl_fm_live.py) | Play live FM audio with FFplay. |
| [rtl_fm_record.py](rtl_fm_record.py) | Record demodulated stereo FM audio to WAV. |
| [rtl_fm_tui.py](rtl_fm_tui.py) | Tune and listen from an interactive terminal. |
| [live_transport_server.py](live_transport_server.py) | Serve a physical receiver over REST, rigctl and ZeroMQ. The service installers use this entry point. |
| [fm_station_scan.py](fm_station_scan.py) | Survey an FM band using one USB session. |
| [wbfm_signal_survey.py](wbfm_signal_survey.py) | Compare relative RF quality from saved IQ. |

## RDS and NOAA weather

| Example | Use it to |
| --- | --- |
| [rds_tmc_live.py](rds_tmc_live.py) | Observe RDS groups and TMC candidates from a live receiver or saved IQ. |
| [rds_tmc_scan.py](rds_tmc_scan.py) | Inspect decoded RDS groups in JSONL for potential TMC activity. |
| [rds_iq_replay.py](rds_iq_replay.py) | Record IQ or replay it through the production WBFM and RDS receiver. |
| [rds_receiver_replay.py](rds_receiver_replay.py) | Compare strict and experimental RDS paths on identical IQ. |
| [noaa_auxiliary_live.py](noaa_auxiliary_live.py) | Probe live NOAA weather transcription with an auxiliary receiver. |
| [noaa_forecast_subscriber.py](noaa_forecast_subscriber.py) | Monitor NOAA forecasts over ZeroMQ. |
| [noaa_replay.py](noaa_replay.py) | Transcribe a recorded NOAA WAV file. |
| [noaa_transcript_replay.py](noaa_transcript_replay.py) | Reassemble forecasts from saved transcript JSONL. |

Strict CRC-validated groups are the source of trusted RDS/TMC metadata.
Soft-pair and CRC-guided erasure results are for diagnosis.

The related [alignment](rds_alignment_diagnostic.py) and
[framing consensus](rds_framing_consensus.py) scripts keep their existing
paths, which automated tests load directly. See the
[component test guide](../component_test/README.md) for transport checks and
the [diagnostic tools](../component_test/diagnostics/README.md) for RDS
stage analysis, sweeps, and Redsea comparison.
