"""Live auxiliary-only NOAA RF transcription probe for Termux.

Run through scripts/run_rtlsdr_termux.sh, never against an already-owned SDR.
Requires an explicit TERMUX_USB_FD handed off by Android. No fallback to device 0.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
import wave
from contextlib import ExitStack

import numpy as np

from sdrforge.adapters.rtl_sdr import RtlSdrSource
from sdrforge.weather.auxiliary_iq import AuxiliaryNoaaIqBridge
from sdrforge.weather.auxiliary_source import AuxiliaryNoaaSourcePump
from sdrforge.weather.auxiliary_transcriber import AuxiliaryNoaaTranscriber
from sdrforge.weather.transcription import NoaaTranscriptionPipeline
from sdrforge.weather.vosk_native import VoskNativeAdapter


class ExclusiveWeatherProbeSession:
    """Standalone ownership guard, not an ORC scheduler lease."""

    def __init__(self, source, transcriber, frequency, wav=None):
        self.source = source
        self.transcriber = transcriber
        self.frequency = frequency
        self.active = False
        self.wav = wav

    def require_weather(self):
        if not self.active or not self.source.is_connected():
            raise RuntimeError("auxiliary NOAA source not active")
        if self.source.get_center_frequency() != self.frequency:
            raise RuntimeError("auxiliary NOAA source retuned")

    def feed(self, pcm):
        self.require_weather()
        if self.wav is not None:
            samples = np.asarray(pcm, dtype=np.float32)
            self.wav.writeframes((np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes())
        self.transcriber.feed(pcm)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frequency-hz", type=int, default=162_550_000)
    parser.add_argument("--seconds", type=float, default=45.0)
    parser.add_argument("--gain-db", type=float, default=30.0,
                        help="Manual tuner gain in dB (default: 30); use --auto-gain for AGC")
    parser.add_argument("--auto-gain", action="store_true",
                        help="Use automatic tuner gain instead of manual gain")
    parser.add_argument("--segment-seconds", type=float, default=10.0)
    parser.add_argument("--wav-output", help="Optional 16 kHz mono WAV capture path")
    parser.add_argument("--model", default=os.path.expanduser(
        "~/models/vosk-model-small-en-us-0.15"))
    parser.add_argument("--vosk-library", default=os.path.expanduser(
        "~/.local/lib/sdrforge-vosk/libvosk.so"))
    args = parser.parse_args()
    if args.seconds <= 0 or args.frequency_hz <= 0:
        parser.error("frequency and duration must be positive")
    fd = os.environ.get("TERMUX_USB_FD")
    if fd is None:
        parser.error("TERMUX_USB_FD is required; launch via USB handoff script")
    try:
        usb_fd = int(fd)
    except ValueError:
        parser.error("TERMUX_USB_FD must be an integer")
    if usb_fd < 0:
        parser.error("TERMUX_USB_FD must be nonnegative")

    with ExitStack() as stack:
        recognizer = stack.enter_context(VoskNativeAdapter(args.model, args.vosk_library))
        wav = None
        if args.wav_output:
            wav = stack.enter_context(wave.open(args.wav_output, 'wb'))
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16_000)
        pipeline = NoaaTranscriptionPipeline(
            recognizer, frequency_hz=args.frequency_hz)
        transcriber = AuxiliaryNoaaTranscriber(
            pipeline, lambda event: print(json.dumps(event), flush=True),
            segment_seconds=args.segment_seconds)
        source = RtlSdrSource(usb_fd=usb_fd, acquisition_mode="async")
        session = ExclusiveWeatherProbeSession(
            source, transcriber, args.frequency_hz, wav=wav)
        bridge = AuxiliaryNoaaIqBridge(session)
        pump = AuxiliaryNoaaSourcePump(
            source, bridge, weather_frequency_hz=args.frequency_hz)
        opened = False
        started = False
        worker_started = False
        try:
            source.open()
            opened = True
            source.set_gain(None if args.auto_gain else args.gain_db)
            source.set_sample_rate(2_400_000)
            source.set_center_frequency(args.frequency_hz)
            source.start()
            started = True
            transcriber.start()
            worker_started = True
            session.active = True
            deadline = time.monotonic() + args.seconds
            while time.monotonic() < deadline:
                pump.pump_once()
        finally:
            session.active = False
            if started:
                source.stop()
            if opened:
                source.close()
            if worker_started:
                transcriber.stop()
            print(json.dumps({
                "event": "noaa_probe_complete",
                "frequency_hz": args.frequency_hz,
                "gain_db": None if args.auto_gain else args.gain_db,
                "iq_blocks": pump.blocks,
                "pcm_samples": pump.samples,
                "pcm_peak": round(bridge.pcm_peak, 6),
                "pcm_rms": round(math.sqrt(bridge.pcm_sum_squares / max(1, pump.samples)), 6),
                "pcm_clipped_samples": bridge.pcm_clipped_samples,
                "processed_segments": transcriber.processed_segments,
                "dropped_segments": transcriber.dropped_segments,
                "transcription_error": transcriber.last_error,
            }), flush=True)


if __name__ == "__main__":
    main()
