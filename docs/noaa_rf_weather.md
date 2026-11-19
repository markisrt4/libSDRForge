# NOAA Weather Radio RF extraction (prototype)

This branch develops an **offline, RF-derived weather information pipeline**.
NOAA Weather Radio channels occupy 162.400 through 162.550 MHz.

## Boundaries

- **SDRForge receiver:** provide NFM-demodulated PCM with channel and timestamp metadata.
- **SAME decoder (future):** detect and validate digital alert headers from PCM,
  preferably using repeated-header agreement before publishing an alert.
- **Transcriber (future):** optional offline speech-to-text adapter; keep its
  dependencies outside the SDR core.
- **Extractor (initial):** parse explicit weather observations from transcripts,
  preserving source text and leaving unknown fields empty.
- **ORC UI (future):** consume a typed weather snapshot, display source,
  age and uncertainty, and distinguish RF weather from internet weather.

## Important limitations

The current parser **does not decode RF or audio**, and the SAME header parser
accepts already-decoded text only. It does not verify authenticity. Never use
speech-extracted text alone to issue a safety-critical alert. NOAA broadcasts
cover multiple places; a location must be verified before displaying values
as local weather.

## Development milestones

1. Hardware-independent models and transcript/SAME text parsing.
2. PCM input contract, recorded-fixture tests, and SAME AFSK demodulation.
3. Offline speech recognition adapter with location-aware extraction.
4. ZMQ weather events and ORC contextual panel integration.
5. Live receiver validation, stale-data handling, and failure recovery.
