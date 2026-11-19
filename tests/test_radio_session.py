# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Session lifecycle and discontinuity tests without USB hardware."""

from __future__ import annotations

import unittest

from sdrforge import RadioSession
from sdrforge.models.iq import IqBlock, SdrCapabilities
from sdrforge.telemetry.iq_observer import IqSpectrumObserver


class FakeSource:
    def __init__(self) -> None:
        self.opened = False
        self.running = False
        self.open_calls = 0
        self.close_calls = 0
        self.blocks: list[IqBlock] = []
        self.dropped = 0

    def open(self) -> None:
        self.open_calls += 1
        self.opened = True

    def close(self) -> None:
        self.close_calls += 1
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

    def test_am_nfm_wfm_switching_without_reopening_source(self) -> None:
        source = FakeSource()
        source.blocks = [block(i * 10_000_000) for i in range(5)]
        session = RadioSession(frequency_hz=104_300_000, mode="mono",
                               rf_warmup_seconds=0, source=source)
        with session:
            for mode in ("AM", "NFM", "WFM", "AM", "NFM"):
                session.set_demodulation(mode)
                frame = session.read()
                self.assertEqual(frame.audio.shape, (480,))
                self.assertTrue(source.opened)
                if mode != "WFM":
                    self.assertIsNone(frame.rds)
        self.assertFalse(source.opened)

    def test_live_mode_reports_active_configuration_without_reopening(self) -> None:
        source = FakeSource()
        source.blocks = [block(i * 10_000_000) for i in range(4)]
        session = RadioSession(frequency_hz=104_300_000, mode="mono",
                               rf_warmup_seconds=0, source=source)
        self.assertEqual((session.demodulation, session.channel_bandwidth_hz),
                         ("WFM", 200_000))
        with session:
            for mode, bandwidth in (("AM", 25_000), ("NFM", 25_000),
                                    ("WFM", 180_000), ("WFM", 200_000)):
                session.set_demodulation(mode, bandwidth)
                self.assertEqual((session.demodulation, session.channel_bandwidth_hz),
                                 (mode, bandwidth))
                self.assertEqual(session.read().audio.shape, (480,))
                self.assertTrue(source.opened)
        self.assertFalse(source.opened)

    def test_mode_changes_and_iq_drop_keep_single_source_lifecycle(self) -> None:
        source = FakeSource()
        source.blocks = [block(i * 10_000_000) for i in range(6)]
        session = RadioSession(frequency_hz=104_300_000, mode="mono",
                               rf_warmup_seconds=0, source=source)
        with session:
            for index, mode in enumerate(("WFM", "AM", "NFM", "WFM", "AM")):
                session.set_demodulation(mode)
                frame = session.read()
                self.assertEqual(frame.audio.shape, (480,))
                self.assertEqual(source.open_calls, 1)
                self.assertEqual(source.close_calls, 0)
            source.dropped += 1
            self.assertEqual(session.read().audio.shape, (480,))
            self.assertEqual(session.status.discontinuities, 1)
        self.assertEqual(source.open_calls, 1)
        self.assertEqual(source.close_calls, 1)

    def test_invalid_live_mode_preserves_current_configuration(self) -> None:
        session = RadioSession(frequency_hz=104_300_000, mode="mono",
                               rf_warmup_seconds=0, source=FakeSource())
        session.set_demodulation("AM")
        with self.assertRaises(ValueError):
            session.set_demodulation("NFM", 10_000)
        self.assertEqual((session.demodulation, session.channel_bandwidth_hz),
                         ("AM", 25_000))

    def test_spectrum_continues_across_demodulation_and_iq_drop(self) -> None:
        class SpectrumSink:
            def __init__(self) -> None:
                self.snapshots: list[tuple[int, int, int]] = []

            def submit_spectrum(self, power_db: object, *,
                                center_frequency_hz: int,
                                sample_rate_hz: int,
                                timestamp_ns: int | None = None) -> bool:
                self.snapshots.append((len(power_db), center_frequency_hz,
                                       sample_rate_hz))
                return True

        sink = SpectrumSink()
        observer = IqSpectrumObserver(sink, rate_hz=10, fft_size=256)
        source = FakeSource()
        source.blocks = [block(i * 100_000_000) for i in range(5)]
        session = RadioSession(frequency_hz=104_300_000, mode="mono",
                               rf_warmup_seconds=0, source=source,
                               iq_observer=observer)
        with session:
            for mode in ("WFM", "AM", "NFM", "WFM"):
                session.set_demodulation(mode)
                session.read()
            source.dropped += 1
            session.read()
            self.assertEqual(session.status.discontinuities, 1)
        self.assertEqual(len(sink.snapshots), 5)
        self.assertEqual(sink.snapshots,
                         [(256, 104_300_000, 2_400_000)] * 5)
        self.assertEqual(observer.dropped, 0)

    def test_mono_dropped_iq_recovers(self) -> None:
        source = FakeSource()
        source.blocks = [block(0), block(10_000_000), block(20_000_000)]
        session = RadioSession(frequency_hz=104_300_000, mode="mono",
                               rf_warmup_seconds=0, source=source)
        session.set_demodulation("NFM")
        with session:
            session.read()
            source.dropped = 1
            session.read()
            self.assertEqual(session.status.discontinuities, 1)
            session.read()

    def test_invalid_mode_and_bandwidth_rejected(self) -> None:
        session = RadioSession(frequency_hz=104_300_000, mode="mono",
                               rf_warmup_seconds=0, source=FakeSource())
        with self.assertRaisesRegex(ValueError, "unsupported demodulation"):
            session.set_demodulation("USB")
        with self.assertRaisesRegex(ValueError, "25000"):
            session.set_demodulation("AM", 10_000)

    def test_rejects_read_before_start(self) -> None:
        session = RadioSession(frequency_hz=104_300_000, mode="mono",
                               rf_warmup_seconds=0, source=FakeSource())
        with self.assertRaisesRegex(RuntimeError, "not started"):
            session.read()


if __name__ == "__main__":
    unittest.main()
