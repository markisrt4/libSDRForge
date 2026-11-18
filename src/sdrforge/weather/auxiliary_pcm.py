"""Stream auxiliary NFM PCM16 into offline NOAA transcription.

Input is *already demodulated* 16 kHz mono signed 16-bit little-endian PCM.
This program never opens an SDR or touches primary receiver controls.

Example:
    nfm-demodulator ... | python -m sdrforge.weather.auxiliary_pcm --model MODEL --vosk-library LIB
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from .auxiliary_transcriber import AuxiliaryNoaaTranscriber
from .transcription import NoaaTranscriptionPipeline
from .vosk_native import VoskNativeAdapter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--vosk-library", type=Path, required=True)
    parser.add_argument("--frequency-hz", type=int, default=162_550_000)
    parser.add_argument("--location")
    parser.add_argument("--segment-seconds", type=float, default=10.0)
    parser.add_argument("--queue-capacity", type=int, default=2)
    parser.add_argument("--jsonl", type=Path, help="optional output file; stdout otherwise")
    args = parser.parse_args(argv)
    output = args.jsonl.open("a", encoding="utf-8") if args.jsonl else sys.stdout
    try:
        with VoskNativeAdapter(args.model, args.vosk_library) as recognizer:
            pipeline = NoaaTranscriptionPipeline(
                recognizer, frequency_hz=args.frequency_hz, location=args.location
            )

            def emit(event: dict) -> None:
                print(json.dumps(event), file=output, flush=True)

            worker = AuxiliaryNoaaTranscriber(
                pipeline, emit, segment_seconds=args.segment_seconds,
                queue_capacity=args.queue_capacity,
            )
            worker.start()
            try:
                while True:
                    data = sys.stdin.buffer.read(8192)
                    if not data:
                        break
                    if len(data) % 2:
                        raise ValueError("PCM16 input must contain complete samples")
                    pcm = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0
                    worker.feed(pcm)
            finally:
                worker.stop()
                if worker.last_error:
                    print(f"NOAA transcription error: {worker.last_error}", file=sys.stderr)
                print(
                    f"NOAA auxiliary: processed={worker.processed_segments} "
                    f"dropped={worker.dropped_segments}",
                    file=sys.stderr,
                )
    finally:
        if args.jsonl:
            output.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
