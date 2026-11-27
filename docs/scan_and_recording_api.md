# Scanning and recording service design

Scanning and recording belong to libSDRForge. Frontends, including OpenRoadCode,
configure and observe these services but do not implement receiver scan loops,
record audio locally, or own the preset database.

## Scan modes

- **Traditional**: tune across a profile, custom range, or saved preset set;
  pause on squelch-open, play received audio, resume after configured delay
  when the signal closes. Support hold, direction, wrap, cancellation, and
  configurable dwell/squelch/hysteresis. No findings are saved.
- **Seek**: stop permanently at the next qualified signal, useful for
  continuous-carrier FM broadcast.
- **Discovery**: collect deduplicated findings with frequency, mode, quality,
  and optional RDS metadata; present them for review before saving selected
  entries through the canonical preset service. Findings are transient until
  explicitly saved.

A single ScanController coordinates exclusive receiver tuning. A manual tune
request or profile switch cancels an active scan first. Scan state transitions
must be observable, with explicit stopped, cancelled, failed, and completed
outcomes. No hardware access belongs in the scanner policy implementation;
inject receiver control, signal quality, and clock interfaces for unit tests.

## Recording modes

- **Manual**: start/stop audio recording at the currently tuned frequency.
- **Signal-triggered**: create one audio segment per qualifying transmission,
  optionally including a bounded pre-roll buffer.
- **Scheduled**: future milestone; explicit start time and maximum duration.
- **IQ**: reuse existing SDRForge IQ capture rather than duplicating capture.

Recording and playback share samples but must have independent lifecycle
controls. Stopping a recording must not stop the receiver. Frequency changes
during recording follow an explicit policy: stop, segment, or reject retune.
For scan-triggered recording, use segment on signal close. Use bounded queues
and explicit overflow reporting, never block the DSP callback on file I/O.

Use RecordingSinkIf for WAV/PCM and future formats. Store metadata with each
recording: ID, source, frequency, mode, bandwidth, UTC timestamps, file size,
format, signal quality, and stop reason. Use application-data directories
appropriate for Linux and Termux. Validate output paths and storage limits.

## Planned REST contract

- `POST /v1/radio/scans`: start traditional/seek/discovery scan
- `GET /v1/radio/scans/{id}`: progress and discovery findings
- `POST /v1/radio/scans/{id}/stop`: cancel/stop
- `POST /v1/radio/scans/{id}/presets`: persist explicitly selected findings
- `POST /v1/recordings`: start a manual or signal-triggered recording
- `GET /v1/recordings`: list recorded sessions
- `GET /v1/recordings/active`: current recording
- `GET /v1/recordings/{id}`: metadata
- `POST /v1/recordings/{id}/stop`: finalize recording
- `DELETE /v1/recordings/{id}`: delete owned recording

ZMQ publishes scan progress and recording state transitions. REST owns
commands and snapshots. Keep existing receiver REST, rigctl, and IQ capture
endpoints compatible.

## Implementation order

1. Canonical radio catalog and user-preset storage with tests.
2. Factory profiles, migration importer, and REST catalog/preset endpoints.
3. Traditional scanner with hardware-free squelch and resume tests.
4. Discovery findings and explicit save-to-preset flow.
5. Manual WAV audio recording, then scan-triggered segmentation.
6. Recording metadata, quotas, optional pre-roll, and scheduled jobs.
7. ORC UI integration and live device validation.

The implementation should be opt-in at each step. No API is considered live
until its handler, persistence, and tests are actually implemented.
