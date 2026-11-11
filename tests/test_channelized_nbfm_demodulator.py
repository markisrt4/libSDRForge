# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""Synthetic tone and streaming tests for channelized narrowband FM."""

import unittest

import numpy as np

from sdrforge.receivers.channelized_nbfm_demodulator import ChannelizedNbfmDemodulator


def nfm_iq(count: int = 48_000) -> np.ndarray:
    rate = 240_000
    t = np.arange(count) / rate
    instantaneous_hz = 2_000 * np.sin(2 * np.pi * 1_000 * t)
    phase = 2 * np.pi * np.cumsum(instantaneous_hz) / rate
    return (0.7 * np.exp(1j * phase)).astype(np.complex64)


class ChannelizedNbfmDemodulatorTest(unittest.TestCase):
    def test_recovers_one_khz_audio(self) -> None:
        audio = ChannelizedNbfmDemodulator().process(nfm_iq())
        self.assertEqual(len(audio), 9_600)
        steady = audio[2_400:]
        self.assertGreater(float(np.std(steady)), 0.01)
        frequencies = np.fft.rfftfreq(len(steady), 1 / 48_000)
        peak = frequencies[np.argmax(np.abs(np.fft.rfft(steady)))]
        self.assertLess(abs(peak - 1_000), 15)

    def test_streaming_matches_single_block(self) -> None:
        iq = nfm_iq()
        expected = ChannelizedNbfmDemodulator().process(iq)
        decoder = ChannelizedNbfmDemodulator()
        chunks = [decoder.process(iq[i:i + 1_237]) for i in range(0, len(iq), 1_237)]
        np.testing.assert_allclose(np.concatenate(chunks), expected, atol=1e-5)

    def test_rejects_real_iq(self) -> None:
        with self.assertRaises(ValueError):
            ChannelizedNbfmDemodulator().process(np.zeros(100))

    def test_reset_clears_stream_state(self) -> None:
        decoder = ChannelizedNbfmDemodulator()
        iq = nfm_iq()
        expected = decoder.process(iq)
        decoder.reset()
        np.testing.assert_allclose(decoder.process(iq), expected, atol=1e-5)


if __name__ == "__main__":
    unittest.main()
