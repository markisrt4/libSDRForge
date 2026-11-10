# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""Synthetic AM tone and streaming continuity tests."""

import unittest

import numpy as np

from sdrforge.receivers.channelized_am_demodulator import ChannelizedAmDemodulator


def am_iq(count: int = 48_000) -> np.ndarray:
    t = np.arange(count) / 240_000
    envelope = 0.6 * (1 + 0.5 * np.sin(2 * np.pi * 1_000 * t))
    return (envelope * np.exp(2j * np.pi * 2_000 * t)).astype(np.complex64)


class ChannelizedAmDemodulatorTest(unittest.TestCase):
    def test_recovers_one_khz_tone(self) -> None:
        pcm = ChannelizedAmDemodulator().process(am_iq())
        self.assertEqual(len(pcm), 9_600)
        steady = pcm[2_400:]
        self.assertGreater(float(np.std(steady)), 0.01)
        frequencies = np.fft.rfftfreq(len(steady), 1 / 48_000)
        peak = frequencies[np.argmax(np.abs(np.fft.rfft(steady)))]
        self.assertLess(abs(peak - 1_000), 15)

    def test_streaming_matches_whole_capture(self) -> None:
        iq = am_iq()
        expected = ChannelizedAmDemodulator().process(iq)
        decoder = ChannelizedAmDemodulator()
        parts = [decoder.process(iq[i:i + 1_237]) for i in range(0, len(iq), 1_237)]
        np.testing.assert_allclose(np.concatenate(parts), expected, atol=1e-5)

    def test_reset_reproduces_initial_output(self) -> None:
        decoder = ChannelizedAmDemodulator()
        iq = am_iq()
        first = decoder.process(iq)
        decoder.reset()
        np.testing.assert_allclose(decoder.process(iq), first, atol=1e-5)

    def test_rejects_real_samples(self) -> None:
        with self.assertRaises(ValueError):
            ChannelizedAmDemodulator().process(np.zeros(100))


if __name__ == "__main__":
    unittest.main()
