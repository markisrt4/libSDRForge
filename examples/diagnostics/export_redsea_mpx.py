# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Export the *undecoded* FM multiplex from RTL IQ for independent redsea testing.

The WAV is 240 kHz mono signed PCM16 and retains the 19/38/57 kHz components.
Run: redsea --file output.wav --show-partial --show-raw
"""
from __future__ import annotations

import argparse
import json
import wave
from pathlib import Path

import numpy as np

from sdrforge.dsp.digital_downconverter import DigitalDownconverter
from sdrforge.dsp.fm_multiplex_discriminator import FmMultiplexDiscriminator
from sdrforge.models.iq import IqBlock

RF_RATE = 2_400_000
MPX_RATE = 240_000
BLOCK_BYTES = 262144


def export(input_path: Path, output_path: Path, seconds: float, amplitude: float,\n           channel_bandwidth_hz: int = 180_000) -> None:
    metadata = json.loads(input_path.with_suffix(input_path.suffix + ".json").read_text())
    if metadata.get("format") != "rtl_u8_interleaved_iq" or metadata.get("sample_rate_hz") != RF_RATE:
        raise ValueError("expected 2.4 MSPS unsigned interleaved RTL IQ and sidecar JSON")
    if metadata.get("gaps"):
        raise ValueError("recording contains IQ gaps; use a gap-free capture for comparison")
    if not 0 < amplitude <= 1:
        raise ValueError("amplitude must be in (0, 1]")
    center = int(metadata["center_frequency_hz"])
    ddc = DigitalDownconverter(channel_bandwidth_hz=channel_bandwidth_hz)
    fm = FmMultiplexDiscriminator()
    remaining = min(input_path.stat().st_size // 2, round(seconds * RF_RATE))
    written = 0
    clipped = 0
    with input_path.open("rb") as src, wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(MPX_RATE)
        while remaining:
            raw = src.read(min(BLOCK_BYTES, remaining * 2))
            if not raw:
                break
            if len(raw) % 2:
                raise ValueError("incomplete IQ pair")
            block = IqBlock(samples=raw, center_frequency_hz=center,
                            sample_rate_hz=RF_RATE, timestamp_ns=0)
            mpx = fm.process(ddc.process(block, center))
            scaled = mpx.astype(np.float64) * amplitude
            clipped += int(np.count_nonzero(np.abs(scaled) > 1))
            pcm = (np.clip(scaled, -1, 1) * 32767).astype("<i2")
            wav.writeframesraw(pcm.tobytes())
            written += len(pcm)
            remaining -= len(raw) // 2
    print(json.dumps({"input": str(input_path), "output": str(output_path),
                      "mpx_sample_rate_hz": MPX_RATE, "channel_bandwidth_hz": channel_bandwidth_hz,\n                      "mpx_seconds": written / MPX_RATE,
                      "clipped_samples": clipped, "total_samples": written}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=20)
    parser.add_argument("--amplitude", type=float, default=0.8,
                        help="fixed MPX PCM scaling; no AGC or normalization")
    parser.add_argument("--channel-bandwidth-hz", type=int, default=180_000,\n                        help="RF channel filter bandwidth (default: 180000 Hz)")\n    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    export(args.input.expanduser(), args.output.expanduser(), args.seconds,\n           args.amplitude, args.channel_bandwidth_hz)


if __name__ == "__main__":
    main()
