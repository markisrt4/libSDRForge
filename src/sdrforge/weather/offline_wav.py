"""!
@brief Offline NOAA WAV-to-observation runner, no network or SDR required.
"""
from __future__ import annotations

import argparse
import json
import wave
from dataclasses import asdict
from pathlib import Path

import numpy as np

from .transcription import NoaaTranscriptionPipeline, OfflineSpeechRecognizer
from .vosk_adapter import VoskOfflineRecognizer


def read_mono_wav(path: str | Path) -> tuple[np.ndarray, int]:
    """!
    @brief Read uncompressed mono PCM16 WAV without optional audio packages.
    @param path The path value.
    @return The operation result.
    """
    with wave.open(str(path), "rb") as recording:
        if (recording.getnchannels() != 1 or recording.getsampwidth() != 2
                or recording.getcomptype() != "NONE"):
            raise ValueError("expected uncompressed mono 16-bit PCM WAV")
        sample_rate = recording.getframerate()
        if sample_rate <= 0:
            raise ValueError("invalid WAV sample rate")
        frames = recording.readframes(recording.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0, sample_rate


def transcribe_wav(path: str | Path, recognizer: OfflineSpeechRecognizer, *,
                   frequency_hz: int = 162_550_000,
                   location: str | None = None) -> dict[str, object]:
    """!
    @brief Return JSON-ready transcript and explicitly spoken weather values.
    @param path The path value.
    @param recognizer The recognizer value.
    @param frequency_hz The frequency hz value.
    @param location The location value.
    @return The operation result.
    """
    audio, sample_rate = read_mono_wav(path)
    result = NoaaTranscriptionPipeline(
        recognizer, frequency_hz=frequency_hz, location=location
    ).process(audio, sample_rate)
    return {"transcript": result.transcript,
            "observation": asdict(result.observation),
            "sample_rate": sample_rate}


def main(argv: list[str] | None = None) -> int:
    """!
    @brief Provide main behavior.
    @param argv The argv value.
    @return The operation result.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path, help="uncompressed mono PCM16 WAV")
    parser.add_argument("--model", type=Path, required=True,
                        help="existing local Vosk model directory")
    parser.add_argument("--frequency-hz", type=int, default=162_550_000)
    parser.add_argument("--location")
    parser.add_argument("--vosk-library", type=Path,
                        help="use native Vosk C API at this libvosk.so path (no vosk pip package)")
    args = parser.parse_args(argv)
    if not args.wav.is_file():
        parser.error(f"WAV file not found: {args.wav}")
    if args.vosk_library:
        from .vosk_native import VoskNativeAdapter
        with VoskNativeAdapter(args.model, args.vosk_library) as native_recognizer:
            result = transcribe_wav(args.wav, native_recognizer,
                                    frequency_hz=args.frequency_hz,
                                    location=args.location)
    else:
        package_recognizer = VoskOfflineRecognizer(args.model)
        result = transcribe_wav(args.wav, package_recognizer,
                                frequency_hz=args.frequency_hz,
                                location=args.location)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
