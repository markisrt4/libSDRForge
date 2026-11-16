# Dual-transport receiver API (design)

libSDRForge exposes the same receiver service through **two first-class transports**.
Neither transport owns the SDR hardware or performs DSP. Existing rigctl remains
a compatibility adapter.

## Shared service contract

- Receiver lifecycle: start, stop, restart, state, last error
- Tuning: frequency, mode, bandwidth
- Status: receiver health and current settings
- Spectrum: versioned frames with center frequency, sample rate, timestamp,
  FFT size, bin width, power unit, and power bins
- Both transports call the same service and observe the same published frames.
- Only the injected receiver service owns hardware; requests are serialized
  by that service, not by individual transport adapters.

## HTTP/REST

- `GET /v1/receiver`: state, frequency, mode, health (planned)
- `POST /v1/receiver/start`, `/stop`, `/restart` (planned)
- `PUT /v1/receiver/tuning`: frequency, mode, bandwidth (planned)
- `GET /v1/spectrum/latest`: latest snapshot in JSON (initial endpoint exists)
- Snapshot reads must **not consume** data needed by another client.
- HTTP error responses must distinguish invalid requests, unavailable
  hardware, and internal errors.
- Bind to loopback by default; remote exposure requires explicit configuration
  and appropriate access controls.

## ZeroMQ

- PUB/SUB: binary spectrum frames, receiver status, future telemetry.
- REQ/REP or ROUTER/DEALER: reliable command/reply semantics for lifecycle
  and tuning; never use PUB/SUB for commands requiring acknowledgement.
- Topic names: `sdrforge.v1.spectrum`, `sdrforge.v1.receiver.status`.
- A versioned binary envelope carries frame metadata; FFT bins are little-endian
  IEEE-754 float32. Define the exact wire schema before exposing a stable API.
- Bound queue depth / high-water mark and drop old spectrum frames for slow
  subscribers. Spectrum is best-effort; control replies are not.
- Use configurable endpoints, not hard-coded ORC service ports.

## Implementation order

1. Replace the consuming HTTP queue with a shared cached latest-frame snapshot.
2. Implement ZeroMQ binary spectrum publisher with an optional `pyzmq` extra.
3. Add receiver control endpoints for both transports using the same service.
4. Add transport-independent contract tests with a simulated receiver.
5. Implement ORC adapters; leave SDR++ fallback until hardware validation.

## Compatibility

HTTP and ZeroMQ are equal public integration options. Neither should be
required to use the other. The core library must remain usable without
installing a network transport. No changes to RDS/TMC are in scope.
