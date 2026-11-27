# Receiver control and telemetry

An application can attach REST and rigctl to the same receiver controller.
The application supplies observations to the ZeroMQ telemetry stream as
they become available. See [component tests](../component_test/README.md)
for a loopback setup using a synthetic receiver.

```mermaid
flowchart LR
    HTTP["REST client"] <-->|"JSON request and reply"| REST["REST server"]
    Rig["rigctl client"] <-->|"TCP command and reply"| RigServer["RigctlServer"]
    REST --> Control["Shared ReceiverManager"]
    RigServer --> Control
    Control --> Receiver["Receiver implementation"]
    Receiver --> Producer["Application telemetry producer"]
    Producer --> Stream["TelemetryStream"]
    Stream -->|"ZeroMQ PUB/SUB"| Sub["Telemetry subscriber"]
```

## REST receiver control

| Method and path | Contract |
| --- | --- |
| `GET /v1/health` | Returns `{"status":"ok"}` when the server is responding. |
| `GET /v1/receiver` | Current tuning, mode, bandwidth, lifecycle, signal measurements and RDS. Measurements can be null when unavailable. |
| `POST /v1/receiver/frequency` | JSON `frequency_hz` as a positive integer. |
| `POST /v1/receiver/mode` | JSON `mode` in FM, WFM, NFM or AM and nonnegative integer `bandwidth_hz`. |
| `POST /v1/receiver/start` | Starts the receiver. An async-capable controller returns HTTP 202. Read `/v1/receiver` for startup state. |
| `POST /v1/receiver/stop` | Stops the receiver. |

Successful synchronous commands return `{"ok":true}`. Invalid controls
return HTTP 400 and receiver failures typically return HTTP 503. The
[live server example](../examples/live_transport_server.py) also supports RF
configuration, audio and IQ capture workflows. The demo uses REST port 5570
and rigctl port 4532 on loopback.

## ZeroMQ telemetry

Install the `zmq` extra to enable publication. The demo publishes on
`tcp://127.0.0.1:5571`. Each message is one frame with an ASCII topic,
one space, and a UTF-8 JSON envelope:

```text
receiver {"schema_version":1,"payload":{...}}
```

- `receiver` carries a receiver snapshot with timestamp in nanoseconds,
  channel frequency and bandwidth in Hz, running state, and optional WFM
  stereo and RDS details.
- `spectrum` carries a spectrum snapshot, including center frequency and
  sample rate in Hz, bin geometry and an array of power values in dB.
- The stream publishes observations on a best-effort basis. Use REST or
  rigctl for acknowledged commands.

See the [snapshot builders](../src/sdrforge/telemetry/snapshots.py) for
field names and the [publisher](../src/sdrforge/protocols/zmq/publisher.py)
for the envelope implementation.

### Managed receiver control

Set `SDRFORGE_ACQUISITION_TOKEN` in the live server environment to enable managed
control. Send the same credential in `X-SDRForge-Acquisition-Token` for
receiver start, stop, tuning, mode, pan, recenter, RF configuration, and
server shutdown. Read-only REST and rigctl telemetry remain available.
Rigctl clients can issue hardware mutations in standalone mode. Managed
clients use REST for those operations.

Automated IQ capture that starts or stops acquisition is available in
standalone mode. A managed client can start acquisition through its
coordinator and record IQ from the running receiver.

A stop that is still deferred to the asynchronous startup worker returns HTTP
202. Before handing the device to another process, wait for
`GET /v1/receiver` to report `hardware_released: true` with both `starting`
and `running` false. Treat missing or false confirmation as an unresolved
reservation. Stopping acquisition leaves the transports available.
