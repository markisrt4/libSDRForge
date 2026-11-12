# RDS-TMC discovery

This is a **discovery experiment**, not a traffic-navigation service.

The `TmcDiscovery` observer accepts CRC-validated `RdsGroup` objects
already produced by `RdsReceiverController.process_iq` or
`process_multiplex`. It counts group types, records a bounded number
of raw 8A messages, and reports the current PI. A change in PI resets
the station-specific counters.

Group 8A is a candidate RDS-TMC message. Group 3A can carry ODA
signalling. Neither a TP/TA flag nor an observed 8A group alone proves
that usable, unencrypted, location-resolved traffic data is available.

## Offline inspection

Prepare a JSONL file containing one object per decoded RDS group:

```json
{"pi":"0x1234","block_b":"0x8000","block_c":"0x0001","block_d":"0x0002"}
```

Then run from an installed development environment:

```sh
python examples/rds_tmc_scan.py groups.jsonl
```

The CLI accepts decimal integers or prefixed hex strings and outputs
counts and raw candidate 8A words. Input is **decoded RDS groups**,
not raw IQ, FM multiplex, or an RF recording.

## Next validation gates

1. Add a live RTL-SDR FM-station capture adapter using existing
   libSDRForge receiver APIs, with explicit dwell time and signal diagnostics.
2. Preserve PI, frequency, group counts and RDS sync quality per station.
3. Observe actual group 8A and ODA signalling on receivable stations.
4. Only then evaluate TMC service identification, conditional access,
   event decoding, and region-specific location tables.

Do not infer traffic incidents or map locations from raw 8A words.
