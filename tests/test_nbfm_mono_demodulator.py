# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""Synthetic streaming tests for narrowband FM."""

import unittest

import numpy as np

from sdrforge.models.iq import IqBlock
from sdrforge.receivers.nbfm_mono_demodulator import NbfmMonoDemodulator


def make_tone(count: int = 120_000) -> bytes:
    rate = 2_400_000
    t = np.arange(count) / rate
    phase = (2 * np.pi * 3_000 / 1_000) * (1 - np.cos(2 * np.pi * 1_000 * t))
    iq = np.exp(1j * phase)
    packed = np.empty(count * 2, dtype=np.uint8)
    packed[::2] = np.rint(127.5 + 100 * iq.real).astype(np.uint8)
    packed[1::2] = np.rint(127.5 + 100 * iq.imag).astype(np.uint8)
    return packed.tobytes()


class NbfmMonoDemodulatorTest(unittest.TestCase):
    def test_configured_channel_bandwidths(self) -> None:
        for bandwidth in (7_500, 12_500, 25_000):
            with self.subTest(bandwidth=bandwidth):
                decoder = NbfmMonoDemodulator(channel_bandwidth_hz=bandwidth)
                self.assertEqual(decoder.channel_bandwidth_hz, bandwidth)

    def test_narrower_band_rejects_adjacent_channel_more(self) -> None:
        from scipy import signal

        narrow = NbfmMonoDemodulator(channel_bandwidth_hz=7_500)
        wide = NbfmMonoDemodulator(channel_bandwidth_hz=25_000)
        # Second RF stage operates after decimation to 240 kSPS.
        frequency = [8_000]
        narrow_response = signal.sosfreqz(narrow._rf_stages[1][1], worN=frequency, fs=240_000)[1]
        wide_response = signal.sosfreqz(wide._rf_stages[1][1], worN=frequency, fs=240_000)[1]
        self.assertLess(abs(narrow_response[0]), abs(wide_response[0]) * 0.1)

    def test_rejects_unsupported_channel_bandwidth(self) -> None:
        with self.assertRaises(ValueError):
            NbfmMonoDemodulator(channel_bandwidth_hz=1_234)

    def test_tone_and_output_rate(self) -> None:
        output = NbfmMonoDemodulator().process(
            IqBlock(make_tone(), 162_550_000, 2_400_000, 1)
        )
        self.assertEqual(len(output), 2400)
        self.assertGreater(float(np.std(output[500:])), 0.001)
        spectrum = np.abs(np.fft.rfft(output[500:]))
        frequencies = np.fft.rfftfreq(len(output[500:]), 1 / 48_000)
        self.assertLess(abs(frequencies[np.argmax(spectrum)] - 1_000), 30)

    def test_streaming_matches_single_block(self) -> None:
        packed = make_tone()
        whole = NbfmMonoDemodulator().process(
            IqBlock(packed, 162_550_000, 2_400_000, 1)
        )
        decoder = NbfmMonoDemodulator()
        pieces = [
            decoder.process(IqBlock(packed[i:i + 20_000], 162_550_000, 2_400_000, 1))
            for i in range(0, len(packed), 20_000)
        ]
        np.testing.assert_allclose(np.concatenate(pieces), whole, atol=1e-5)

    def test_invalid_configuration(self) -> None:
        with self.assertRaises(ValueError):
            NbfmMonoDemodulator(sample_rate_hz=1_000_000)
        with self.assertRaises(ValueError):
            NbfmMonoDemodulator(deviation_hz=0)


if __name__ == "__main__":
    unittest.main()
