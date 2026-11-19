# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""Synthetic AM demodulation and streaming regression tests."""

import unittest

import numpy as np

from sdrforge.models.iq import IqBlock
from sdrforge.receivers.am_mono_demodulator import AmMonoDemodulator


def am_signal(count: int = 120_000, depth: float = 0.6) -> bytes:
    rate = 2_400_000
    t = np.arange(count) / rate
    carrier = (0.55 * (1 + depth * np.sin(2 * np.pi * 1_000 * t))
               * np.exp(1j * 2 * np.pi * 2_000 * t))
    packed = np.empty(count * 2, dtype=np.uint8)
    packed[::2] = np.clip(np.rint(127.5 + 127.5 * carrier.real), 0, 255).astype(np.uint8)
    packed[1::2] = np.clip(np.rint(127.5 + 127.5 * carrier.imag), 0, 255).astype(np.uint8)
    return packed.tobytes()


class AmMonoDemodulatorTest(unittest.TestCase):
    def test_configured_channel_bandwidths(self) -> None:
        for bandwidth in (6_000, 10_000, 12_500, 25_000):
            with self.subTest(bandwidth=bandwidth):
                decoder = AmMonoDemodulator(channel_bandwidth_hz=bandwidth)
                self.assertEqual(decoder.channel_bandwidth_hz, bandwidth)

    def test_narrower_band_rejects_adjacent_channel_more(self) -> None:
        from scipy import signal

        narrow = AmMonoDemodulator(channel_bandwidth_hz=6_000)
        wide = AmMonoDemodulator(channel_bandwidth_hz=25_000)
        frequency = [8_000]
        narrow_response = signal.sosfreqz(narrow._rf_sos, worN=frequency, fs=2_400_000)[1]
        wide_response = signal.sosfreqz(wide._rf_sos, worN=frequency, fs=2_400_000)[1]
        self.assertLess(abs(narrow_response[0]), abs(wide_response[0]) * 0.1)

    def test_rejects_unsupported_channel_bandwidth(self) -> None:
        with self.assertRaises(ValueError):
            AmMonoDemodulator(channel_bandwidth_hz=1_234)

    def test_am_tone_recovery(self) -> None:
        audio = AmMonoDemodulator().process(
            IqBlock(am_signal(), 125_000_000, 2_400_000, 1)
        )
        self.assertEqual(len(audio), 2400)
        self.assertGreater(float(np.std(audio[500:])), 0.01)
        spectrum = np.abs(np.fft.rfft(audio[500:]))
        frequencies = np.fft.rfftfreq(len(audio[500:]), 1 / 48_000)
        self.assertLess(abs(frequencies[np.argmax(spectrum)] - 1_000), 30)

    def test_streaming_matches_single_block(self) -> None:
        data = am_signal()
        whole = AmMonoDemodulator().process(
            IqBlock(data, 125_000_000, 2_400_000, 1)
        )
        decoder = AmMonoDemodulator()
        chunks = [
            decoder.process(IqBlock(data[i:i + 20_000], 125_000_000, 2_400_000, 1))
            for i in range(0, len(data), 20_000)
        ]
        np.testing.assert_allclose(np.concatenate(chunks), whole, atol=1e-5)

    def test_rejects_invalid_settings(self) -> None:
        with self.assertRaises(ValueError):
            AmMonoDemodulator(sample_rate_hz=1_000_000)
        with self.assertRaises(ValueError):
            AmMonoDemodulator(audio_bandwidth_hz=20_000)
        with self.assertRaises(ValueError):
            AmMonoDemodulator(agc_target=0)


if __name__ == "__main__":
    unittest.main()
