# NOAA RF weather consumer contract

This document describes the existing libSDRForge forecast event consumed by OpenRoadCode. It does not introduce a new wire format.

## Transport

The auxiliary NOAA probe optionally publishes to a dedicated ZeroMQ PUB endpoint (example: `tcp://127.0.0.1:5573`). The topic is `noaa.forecast`. The multipart-like single frame is the ASCII topic, a space, then a JSON envelope with `schema_version: 1` and a `payload` dictionary. The payload event must be `noaa_forecast_completed`. The existing `examples/noaa_forecast_subscriber.py` validates this shape.

## Event fields

The payload from `NoaaForecastProcessor` contains:

- `event`: `noaa_forecast_completed`
- `forecast_area`: observed area or `null`
- `forecast_areas`: list of observed area names
- `source_frequency_hz`: receiver frequency or `null`
- `forecast_cycle`: observed cycle number
- `cycle_boundary_suspected`: warning boolean
- `boundary_evidence`: cycle boundary status
- `deduplication_status`: deduplicator status
- `forecast_revision`: revision counter
- `completed_forecast`: assembled forecast dictionary, including `forecast`

The nested forecast can contain `period`, `conditions`, `high_f`, `low_f`, `precipitation_chance_percent`, `high_description`, and `low_description`. Optional values can be `null`.

## Consumer requirements

1. Validate the topic, schema version, event name, and field types before storing.
2. Do not infer a local geographic match from tuned frequency alone. Missing or ambiguous area information remains unscoped.
3. Keep RF reception time separate from forecast validity time. Reception time alone does not prove forecast freshness.
4. Preserve cycle and revision metadata. Do not assume a revision counter is globally unique across publisher restarts.
5. Never allow an incomplete or unscoped RF forecast to override a fresh, geographically matched online forecast.
6. Keep ZMQ subscription and decoding off the UI thread. A weather provider reads a thread-safe forecast snapshot.
7. Allow an RF preview to show unscoped received forecasts with an explicit warning, even if those forecasts are ineligible for automatic source selection.
8. On disconnect, retain the last received forecast with a stale/cached indicator; do not pretend the receiver remains live.

## Ownership boundary

libSDRForge owns RF acquisition, NOAA transcription, forecast assembly, and publishing. OpenRoadCode owns forecast storage, geographic eligibility, source selection, and weather presentation. The consumer-facing `NoaaRfWeatherProvider` and forecast store therefore belong in OpenRoadCode, not in libSDRForge.

## Hardware-free validation

Consumer tests should cover malformed envelopes, missing area, geographic mismatch, optional forecast fields, duplicate events, cycle/revision changes, publisher restart, stale snapshots, disconnect, and concurrent store reads and writes.
