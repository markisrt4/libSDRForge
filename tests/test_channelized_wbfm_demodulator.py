# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""Synthetic WFM tone and streaming tests for channelized IQ."""

import unittest

import numpy as np

from sdrforge.receivers.channelized_wbfm_demodulator import ChannelizedWbfmDemodulator


class ChannelizedWbfmDemodulatorTest(unittest.TestCase):
    @staticmethod
    def modulated_iq(count: int = 48_000) -> np.ndarray:
        rate = 240_000
        t = np.arange(count) / rate
        instantaneous_hz = 15_000 * np.sin(2 * np.pi * 1_000 * t)
        phase = 2 * np.pi * np.cumsum(instantaneous_hz) / rate
        return (0.6 * np.exp(1j * phase)).astype(np.complex64)

    def test_recovers_audio_tone(self) -> None:
        audio = ChannelizedWbfmDemodulator().process(self.modulated_iq())
        self.assertEqual(len(audio), 9_600)
        steady = audio[2_400:]
        self.assertGreater(float(np.std(steady)), 0.01)
        frequencies = np.fft.rfftfreq(len(steady), 1 / 48_000)
        spectrum = np.abs(np.fft.rfft(steady))
        self.assertLess(abs(frequencies[np.argmax(spectrum)] - 1_000), 15)

    def test_chunked_processing_matches_whole(self) -> None:
        iq = self.modulated_iq()
        expected = ChannelizedWbfmDemodulator().process(iq)
        decoder = ChannelizedWbfmDemodulator()
        chunks = [decoder.process(iq[i:i + 1_237]) for i in range(0, len(iq), 1_237)]
        np.testing.assert_allclose(np.concatenate(chunks), expected, atol=1e-5)

    def test_rejects_real_valued_samples(self) -> None:
        with self.assertRaises(ValueError):
            ChannelizedWbfmDemodulator().process(np.zeros(100))


if __name__ == "__main__":
    unittest.main()
