# RDS and TMC diagnostics

Run these tools from the repository root with libSDRForge installed.
Use `--help` on the capture-based tools to see their input options.

| Tool | Input and purpose |
| --- | --- |
| [rds_synthetic_diagnostic.py](rds_synthetic_diagnostic.py) | Generated CRC-valid RDS multiplex. Prints group counts and recovered PI. |
| [rds_stage_diagnostic.py](rds_stage_diagnostic.py) | Generated multiplex. Helps locate a failing receive-chain stage. |
| [rds_block_diagnostic.py](rds_block_diagnostic.py) | Recorded IQ. Reports block syndrome and per-second decode quality. |
| [rds_carrier_sweep.py](rds_carrier_sweep.py) and [rds_extractor_sweep.py](rds_extractor_sweep.py) | Recorded IQ. Compare carrier-loop bandwidth and extraction settings. |
| [rds_timing_sweep.py](rds_timing_sweep.py) | Recorded IQ. Compare initial symbol-timing settings. |
| [rds_multiplex_spectrum.py](rds_multiplex_spectrum.py) and [rds_pilot_comparison.py](rds_pilot_comparison.py) | Recorded IQ. Inspect multiplex spectrum or compare pilot-referenced recovery with Costas recovery. |
| [export_redsea_mpx.py](export_redsea_mpx.py) | Recorded IQ. Export the undecoded multiplex for Redsea. |
| [inspect_tmc_8a.py](inspect_tmc_8a.py) and [replay_tmc_receiver.py](replay_tmc_receiver.py) | Redsea JSONL. Inspect ALERT-C group patterns or replay them through the receiver. |

For example:

```bash
python component_test/diagnostics/rds_multiplex_spectrum.py capture.iq
```
