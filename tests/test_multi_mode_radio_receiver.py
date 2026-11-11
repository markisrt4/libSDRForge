# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""Mixed-mode SDR integration tests using synthetic shared IQ."""

import unittest

import numpy as np

from sdrforge.models.iq import IqBlock
from sdrforge.receivers.multi_mode_radio_receiver import (
    MultiModeRadioReceiver,
    RadioChannel,
)

RATE = 2_400_000
CENTER = 104_300_000


def mixed_capture(count: int = 120_000) -> IqBlock:
    t = np.arange(count, dtype=np.float64) / RATE
    wfm_phase = 2 * np.pi * (-700_000 * t + 15_000 / (2 * np.pi * 1_000) *
                            (1 - np.cos(2 * np.pi * 1_000 * t)))
    nfm_phase = 2 * np.pi * (700_000 * t + 2_000 / (2 * np.pi * 1_500) *
                            (1 - np.cos(2 * np.pi * 1_500 * t)))
    am = (1 + 0.5 * np.sin(2 * np.pi * 2_000 * t))
    iq = (0.25 * np.exp(1j * wfm_phase) +
          0.20 * np.exp(1j * nfm_phase) +
          0.20 * am * np.exp(2j * np.pi * 250_000 * t))
    raw = np.empty(2 * count, dtype=np.uint8)
    raw[::2] = np.clip(np.rint(127.5 + 127.5 * iq.real), 0, 255).astype(np.uint8)
    raw[1::2] = np.clip(np.rint(127.5 + 127.5 * iq.imag), 0, 255).astype(np.uint8)
    return IqBlock(raw.tobytes(), CENTER, RATE, 1)


def receiver() -> MultiModeRadioReceiver:
    radio = MultiModeRadioReceiver()
    radio.add_channel(RadioChannel("fm", CENTER - 700_000, "WFM"))
    radio.add_channel(RadioChannel("weather", CENTER + 700_000, "NFM"))
    radio.add_channel(RadioChannel("airband", CENTER + 250_000, "AM"))
    return radio


def peak_hz(pcm: np.ndarray) -> float:
    steady = pcm[1_200:]
    spectrum = np.abs(np.fft.rfft(steady))
    return float(np.fft.rfftfreq(len(steady), 1 / 48_000)[np.argmax(spectrum)])


class MultiModeRadioReceiverTest(unittest.TestCase):
    def test_three_modes_from_one_iq_capture(self) -> None:
        outputs = receiver().process(mixed_capture())
        self.assertEqual(set(outputs), {"fm", "weather", "airband"})
        for pcm in outputs.values():
            self.assertEqual(len(pcm), 2_400)
            self.assertTrue(np.all(np.isfinite(pcm)))
        self.assertLess(abs(peak_hz(outputs["fm"]) - 1_000), 50)
        self.assertLess(abs(peak_hz(outputs["weather"]) - 1_500), 50)
        self.assertLess(abs(peak_hz(outputs["airband"]) - 2_000), 50)

    def test_chunked_capture_matches_single_block(self) -> None:
        block = mixed_capture(48_000)
        expected = receiver().process(block)
        streaming = receiver()
        pieces = {name: [] for name in expected}
        for start in range(0, len(block.samples), 12_346):
            chunk = IqBlock(block.samples[start:start + 12_346], CENTER, RATE, 1)
            for name, pcm in streaming.process(chunk).items():
                pieces[name].append(pcm)
        for name in expected:
            np.testing.assert_allclose(np.concatenate(pieces[name]),
                                       expected[name], atol=1e-5)

    def test_retune_one_channel_does_not_reset_others(self) -> None:
        block = mixed_capture(48_000)
        baseline = receiver()
        baseline.process(block)
        expected = baseline.process(block)
        radio = receiver()
        radio.process(block)
        radio.retune_channel("weather", CENTER + 600_000)
        actual = radio.process(block)
        for name in ("fm", "airband"):
            np.testing.assert_allclose(actual[name], expected[name], atol=1e-5)

    def test_mode_validation(self) -> None:
        radio = MultiModeRadioReceiver()
        with self.assertRaises(ValueError):
            radio.add_channel(RadioChannel("unsupported", CENTER, "SSB"))
        with self.assertRaises(ValueError):
            radio.add_channel(RadioChannel("narrow_fm", CENTER, "WFM", 25_000))


if __name__ == "__main__":
    unittest.main()
