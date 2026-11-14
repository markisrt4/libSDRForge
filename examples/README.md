# libSDRForge examples

Run examples from the repository root with `PYTHONPATH="$PWD/src"` set.

## Primary radio applications

- `rtl_fm_live.py`: live FM receiver
- `rtl_fm_tui.py`: interactive receiver
- `rtl_fm_record.py`: IQ recording
- `rds_tmc_live.py`: live or recorded-IQ RDS/TMC monitor
- `rds_receiver_replay.py`: reproducible strict/experimental RDS comparison on IQ recordings
- `rds_tmc_scan.py`: offline JSONL RDS group inspection (does not scan RF)
- `fm_station_scan.py`: hardware-based FM signal survey; live scanning is on hold
- `wbfm_signal_survey.py`: RF signal survey
- `rds_iq_replay.py`: lower-level IQ replay diagnostics

## RDS diagnostics (development tools)

The root-level `rds_*_diagnostic.py`, `rds_framing_consensus.py`, and `rds_stage_diagnostic.py` remain at their original locations for compatibility with existing direct imports and test invocations.

The following standalone offline tools are grouped under `diagnostics/`:

- `rds_timing_sweep.py`
- `rds_carrier_sweep.py`
- `rds_extractor_sweep.py`
- `rds_pilot_comparison.py`
- `rds_multiplex_spectrum.py`

For example:

```bash
PYTHONPATH="$PWD/src" python examples/diagnostics/rds_multiplex_spectrum.py "$HOME/rds_947_good.iq"
PYTHONPATH="$PWD/src" python examples/rds_receiver_replay.py "$HOME/rds_947_good.iq" --seconds 20
```

The sweep scripts remain together because carrier and extractor sweeps import `rds_timing_sweep` directly.

## TMC recovery rules

- Strict CRC-validated groups are the only source of trusted RDS/TMC metadata.
- Experimental soft-pair and CRC-guided erasure results are diagnostic only.
- A single CRC-guided recovered group is not evidence of reliable TMC reception.
- Keep synthetic and recorded-IQ regressions available until the strict path is reliably decoding real captures.

## Cleanup policy

Do not remove the remaining diagnostic scripts without verifying direct imports, test references, and any launcher/documentation references. Existing scripts are intentionally preserved until their functionality is replaced by tested alternatives.
