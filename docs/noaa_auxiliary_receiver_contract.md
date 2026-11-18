# NOAA live monitoring: auxiliary receiver contract

NOAA Weather Radio transcription and SAME decoding are **auxiliary receiver**
services, not features of the primary FM receiver. This applies to live
capture, scheduling, REST/ZMQ telemetry, and OpenRoadCode integration.

## Receiver ownership

- The primary receiver retains ownership of user-selected audio, frequency,
  and playback. NOAA code must never call primary start/stop/tune/mode APIs.
- Live NOAA monitoring is launched only with an explicitly provided auxiliary
  receiver handle/lease. No implicit fallback to the primary device.
- Use `AuxiliaryReceiverManager` for weather/TMC/ADSB scheduling and
  `AuxiliaryReceiverRuntime` for auxiliary tuning. The existing WEATHER
  service profile is NFM at 12,500 Hz.
- An auxiliary **logical** receiver is not necessarily an independent physical
  SDR. If no independent RF resource or explicitly supported simultaneous
  channelization is available, return unavailable/busy. Never silently retune
  the shared RTL-SDR or disrupt the primary station.
- An auxiliary WEATHER lease must be released on normal exit, cancellation,
  decoder exception, and USB disconnect. Release only the acquired lease.
- Speech recognition runs in a separate worker with bounded PCM queues and
  explicit overflow/drop telemetry. No blocking Vosk call on primary RF or
  audio threads.
- SAME alert parsing/decoding is independent of best-effort transcription.
  Only validated SAME decoder output may trigger emergency alert state.

## Initial live RF milestone

1. Confirm an independent auxiliary SDR is available, or an explicitly
   configured shared-IQ channelization path that does not affect primary.
2. Acquire a WEATHER lease on the auxiliary manager.
3. Use the existing auxiliary NFM profile to capture 16 kHz mono PCM.
4. Transcribe bounded segments using `VoskNativeAdapter` on Termux.
5. Emit timestamped JSONL with frequency, transcript, extracted observation,
   signal/queue status, and dropped-block counters.
6. Release the auxiliary lease and verify primary frequency and audio remain
   unchanged before, during, and after the run.

## Required regression checks

- Primary mock receiver receives zero method calls for NOAA start, tune,
  stop, and error cleanup.
- No auxiliary hardware: monitoring refuses to start and primary continues.
- Busy auxiliary resource: monitoring waits or reports busy without takeover.
- Vosk worker stalls: bounded queue drops/reports segments, never stalls RF.
- USB unplug and decoder exceptions: only auxiliary resources are released.
- Weather/TMC/ADSB arbitration remains under auxiliary scheduler control.
