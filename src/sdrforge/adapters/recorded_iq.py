# SPDX-License-Identifier: MIT
"""Offline RTL unsigned-byte IQ source compatible with the live monitor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import BinaryIO

from sdrforge.models.iq import IqBlock


class RecordedIqSource:
    """Read recorded IQ with its original center frequency and gap boundaries."""

    def __init__(self, path: Path, block_bytes: int = 262_144) -> None:
        self.path = path.expanduser()
        self.block_bytes = block_bytes
        self._stream: BinaryIO | None = None
        self._processed = 0
        self._gaps: list[dict[str, int]] = []
        self._next_gap = 0
        self._drops = 0
        self._frequency = 0
        self._rate = 0

    def open(self) -> None:
        metadata = json.loads(self.path.with_suffix(self.path.suffix + ".json").read_text(encoding="utf-8"))
        if metadata.get("format") != "rtl_u8_interleaved_iq":
            raise ValueError("unsupported recording format")
        self._frequency = int(metadata["center_frequency_hz"])
        self._rate = int(metadata["sample_rate_hz"])
        if self._rate <= 0:
            raise ValueError("invalid recording sample rate")
        self._gaps = sorted(metadata.get("gaps", []), key=lambda gap: gap["sample_offset"])
        self._stream = self.path.open("rb")

    def start(self) -> None:
        if self._stream is None:
            raise RuntimeError("recording not opened")

    def get_center_frequency(self) -> int:
        return self._frequency

    def get_sample_rate(self) -> int:
        return self._rate

    def read_iq(self) -> IqBlock | None:
        if self._stream is None:
            raise RuntimeError("recording not opened")
        if self._next_gap < len(self._gaps):
            gap = self._gaps[self._next_gap]
            if self._processed == int(gap["sample_offset"]):
                self._drops += int(gap["dropped_blocks"])
                self._next_gap += 1
        length = self.block_bytes
        if self._next_gap < len(self._gaps):
            remaining = int(self._gaps[self._next_gap]["sample_offset"]) - self._processed
            if remaining < 0:
                raise ValueError("invalid IQ gap offsets")
            length = min(length, remaining * 2)
        data = self._stream.read(length)
        if not data:
            return None
        if len(data) % 2:
            raise ValueError("truncated IQ recording: incomplete I/Q pair")
        self._processed += len(data) // 2
        return IqBlock(samples=data, center_frequency_hz=self._frequency,
                       sample_rate_hz=self._rate, timestamp_ns=0)

    def get_acquisition_stats(self) -> dict[str, int]:
        return {"dropped_blocks": self._drops, "queued_blocks": 0,
                "queue_capacity_blocks": 0}

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None
