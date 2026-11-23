# libSDRForge component tests

Run from the repository root after installing the library. Record the input,
platform, optional dependencies and observed result when reporting a check.

## Transport without a radio

Install `python -m pip install -e '.[zmq]'`. Start the demo in one terminal:

```bash
python component_test/transport_demo_server.py
```

In another terminal:

```bash
python component_test/rest_test_client.py --start --frequency 101100000
python component_test/zmq_test_client.py --seconds 5
```

Expect an OK REST health response, the requested frequency in the receiver
snapshot, and versioned receiver/spectrum messages on ZeroMQ. The demo binds
REST, rigctl and ZeroMQ to loopback by default and uses a synthetic receiver.
Stop it with Ctrl+C when finished. See the [transport contract](../docs/dual_transport_api.md)
for endpoint and payload details.

## Hardware and recorded inputs

| Check | Setup and expected result |
| --- | --- |
| `python examples/rtl_fm_live.py --frequency 104.3 --seconds 10` | Linux/Raspberry Pi with RTL-SDR access, librtlsdr and FFplay. Choose a local FM station and verify audible audio. See the [Termux launcher](../README.md#android--termux) when testing on Android. |
| `python examples/rds_receiver_replay.py capture.iq --seconds 20` | Recorded IQ from a station with RDS. Compare strict and experimental decoding and record CRC-validated groups separately from diagnostic recoveries. |
| `python examples/noaa_replay.py sample.wav --model /path/to/model` | Native Vosk and an uncompressed 16-bit mono 16 kHz NOAA weather recording. Verify transcript and structured events against the recording. |
| `python examples/noaa_transcript_replay.py transcript.jsonl` | Existing NOAA transcript JSONL. Check completed forecasts against the source transcript without a USB device or recognizer. |

Automated tests under `tests/` already cover DSP, receiver sessions, replay,
protocols and transports. Use these manual checks when success also depends on
local RF, native speech recognition, host audio or command-line setup.
