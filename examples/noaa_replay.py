"""Replay captured 16 kHz mono NOAA WAV through offline transcription.

No USB device, radio source, or network connection is accessed.
"""
from __future__ import annotations

import argparse
import ctypes.util
import os
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import wave

import numpy as np

from sdrforge.weather.forecast_assembler import NoaaForecastAssembler
from sdrforge.weather.transcription import NoaaTranscriptionPipeline
from sdrforge.weather.vosk_native import VoskNativeAdapter


def replay(wav_path, pipeline, *, segment_seconds=10.0, emit=print):
    """Process fixed-duration windows and return the number of emitted events."""
    if segment_seconds <= 0:
        raise ValueError("segment_seconds must be positive")
    count = 0
    assembler = NoaaForecastAssembler()
    with wave.open(str(wav_path), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, 16000, "NONE"):
            raise ValueError("expected uncompressed 16 kHz mono 16-bit WAV")
        frames_per_segment = max(1, round(16000 * segment_seconds))
        while True:
            raw = wav.readframes(frames_per_segment)
            if not raw:
                break
            pcm = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
            result = pipeline.process(pcm, 16000)
            event = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "receiver": "auxiliary-replay",
                "frequency_hz": pipeline.frequency_hz,
                "segment_index": count,
                "start_seconds": round(count * frames_per_segment / 16000, 3),
                "duration_seconds": round(len(pcm) / 16000, 3),
                "transcript": result.transcript,
                "observation": asdict(result.observation),
                "forecasts": [asdict(period) for period in result.forecasts],
                "completed_forecasts": [asdict(item) for item in assembler.feed(result.transcript)],
            }
            emit(json.dumps(event))
            count += 1
    for item in assembler.flush():
        emit(json.dumps({"event": "noaa_forecast_completed", "completed_forecast": asdict(item)}))
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path)
    parser.add_argument("--frequency-hz", type=int, default=162_550_000)
    parser.add_argument("--segment-seconds", type=float, default=10.0)
    parser.add_argument("--output", type=Path, help="Write JSONL events to file")
    parser.add_argument("--model", default=str(Path.home() / "models/vosk-model-small-en-us-0.15"))
    parser.add_argument("--vosk-library", default=None, help="Native Vosk library path (otherwise auto-discover)")
    args = parser.parse_args()
    if args.segment_seconds <= 0 or args.frequency_hz <= 0:
        parser.error("duration and frequency must be positive")
    library = args.vosk_library or os.environ.get("SDRFORGE_VOSK_LIBRARY") or ctypes.util.find_library("vosk")
    if library is None:
        local = Path.home() / ".local/lib/sdrforge-vosk/libvosk.so"
        if local.is_file():
            library = str(local)
    with VoskNativeAdapter(args.model, library) as recognizer:
        pipeline = NoaaTranscriptionPipeline(recognizer, frequency_hz=args.frequency_hz)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("w", encoding="utf-8") as output:
                count = replay(args.wav, pipeline, segment_seconds=args.segment_seconds,
                               emit=lambda line: output.write(line + "\n"))
        else:
            count = replay(args.wav, pipeline, segment_seconds=args.segment_seconds)
    print(json.dumps({"event": "noaa_replay_complete", "segments": count,
                      "output": str(args.output) if args.output else None}))


if __name__ == "__main__":
    main()
