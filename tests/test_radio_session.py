# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Session lifecycle and discontinuity tests without USB hardware."""

from __future__ import annotations

import unittest

from sdrforge import RadioSession
from sdrforge.models.iq import IqBlock, SdrCapabilities


class FakeSource:
    def __init__(self) -> None:
        self.opened = False
        self.running = False
        self.blocks: list[IqBlock] = []
        self.dropped = 0

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.opened = False

    def is_connected(self) -> bool:
        return self.opened

    def get_capabilities(self) -> SdrCapabilities:
        return SdrCapabilities(24_000_000, 1_766_000_000)

    def set_center_frequency(self, frequency_hz: int) -> None:
        self.frequency = frequency_hz

    def get_center_frequency(self) -> int:
        return self.frequency

    def set_sample_rate(self, sample_rate_hz: int) -> None:
        self.rate = sample_rate_hz

    def get_sample_rate(self) -> int:
        return self.rate

    def set_gain(self, gain_db: float | None) -> None:
        self.gain = gain_db

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def read_iq(self) -> IqBlock:
        return self.blocks.pop(0)

    def get_acquisition_stats(self) -> dict[str, int]:
        return {"dropped_blocks": self.dropped}


def block(timestamp_ns: int) -> IqBlock:
    return IqBlock(bytes([128, 128]) * 24_000, 104_300_000, 2_400_000,
                   timestamp_ns)


class RadioSessionTest(unittest.TestCase):
    def test_context_and_output(self) -> None:
        source = FakeSource()
        source.blocks = [block(0), block(10_000_000)]
        session = RadioSession(frequency_hz=104_300_000, mode="mono",
                               rf_warmup_seconds=0.01, source=source)
        with session:
            frame = session.read()
            self.assertEqual(frame.audio.shape, (480,))
            self.assertEqual(session.status.processed_blocks, 1)
        self.assertFalse(source.opened)
        self.assertFalse(session.status.started)

    def test_timestamp_gap_resets_receiver(self) -> None:
        source = FakeSource()
        source.blocks = [block(0), block(100_000_000)]
        session = RadioSession(frequency_hz=104_300_000, mode="mono",
                               rf_warmup_seconds=0, source=source)
        with session:
            session.read()
            session.read()
            self.assertEqual(session.status.discontinuities, 1)

    def test_dropped_counter_resets_receiver(self) -> None:
        source = FakeSource()
        source.blocks = [block(0), block(10_000_000)]
        session = RadioSession(frequency_hz=104_300_000, mode="mono",
                               rf_warmup_seconds=0, source=source)
        with session:
            session.read()
            source.dropped = 1
            session.read()
            self.assertEqual(session.status.discontinuities, 1)

    def test_rejects_read_before_start(self) -> None:
        session = RadioSession(frequency_hz=104_300_000, mode="mono",
                               rf_warmup_seconds=0, source=FakeSource())
        with self.assertRaisesRegex(RuntimeError, "not started"):
            session.read()


if __name__ == "__main__":
    unittest.main()
