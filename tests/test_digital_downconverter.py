# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""Synthetic RF tests for independent virtual receiver downconversion."""

import unittest

import numpy as np

from sdrforge.dsp.digital_downconverter import DigitalDownconverter
from sdrforge.models.iq import IqBlock

RATE = 2_400_000
CENTER = 104_300_000


def synthetic_block(count: int = 48_000) -> IqBlock:
    t = np.arange(count) / RATE
    # Two independent stations, separated by 400 kHz.
    iq = (0.30 * np.exp(2j * np.pi * 100_000 * t) +
          0.30 * np.exp(2j * np.pi * -300_000 * t))
    packed = np.empty(count * 2, dtype=np.uint8)
    packed[::2] = np.clip(np.rint(127.5 + 127.5 * iq.real), 0, 255).astype(np.uint8)
    packed[1::2] = np.clip(np.rint(127.5 + 127.5 * iq.imag), 0, 255).astype(np.uint8)
    return IqBlock(packed.tobytes(), CENTER, RATE, 1)


class DigitalDownconverterTest(unittest.TestCase):
    def test_two_virtual_receivers_extract_distinct_channels(self) -> None:
        block = synthetic_block()
        first = DigitalDownconverter().process(block, CENTER + 100_000)
        second = DigitalDownconverter().process(block, CENTER - 300_000)
        self.assertEqual(len(first), 4_800)
        self.assertEqual(len(second), 4_800)
        # Both requested tones are shifted to DC and retain useful energy.
        self.assertGreater(abs(np.mean(first[1000:])), 0.20)
        self.assertGreater(abs(np.mean(second[1000:])), 0.20)

    def test_chunked_processing_matches_whole_block(self) -> None:
        block = synthetic_block()
        whole = DigitalDownconverter().process(block, CENTER + 100_000)
        stream = DigitalDownconverter()
        chunks = []
        for index in range(0, len(block.samples), 12_346):
            part = IqBlock(block.samples[index:index + 12_346], CENTER, RATE, 1)
            chunks.append(stream.process(part, CENTER + 100_000))
        np.testing.assert_allclose(np.concatenate(chunks), whole, atol=1e-5)

    def test_center_tuned_chunking_matches_whole_block(self) -> None:
        block = synthetic_block()
        whole = DigitalDownconverter().process(block, CENTER)
        streaming = DigitalDownconverter()
        chunks = []
        for index in range(0, len(block.samples), 12_346):
            part = IqBlock(block.samples[index:index + 12_346], CENTER, RATE, 1)
            chunks.append(streaming.process(part, CENTER))
        np.testing.assert_allclose(np.concatenate(chunks), whole, atol=1e-5)

    def test_center_tuned_output_matches_original_filter_path(self) -> None:
        block = synthetic_block()
        converter = DigitalDownconverter()
        result = converter.process(block, CENTER)
        raw = np.frombuffer(block.samples, dtype=np.uint8).astype(np.float32)
        iq = ((raw[::2] - 127.5) + 1j * (raw[1::2] - 127.5)) / 127.5
        from scipy import signal
        expected = signal.sosfilt(converter._sos, iq.astype(np.complex128))[::10]
        np.testing.assert_allclose(result, expected.astype(np.complex64), atol=1e-5)

    def test_rejects_out_of_band_channel(self) -> None:
        with self.assertRaises(ValueError):
            DigitalDownconverter().process(synthetic_block(), CENTER + 1_150_000)

    def test_rejects_invalid_rates(self) -> None:
        with self.assertRaises(ValueError):
            DigitalDownconverter(output_rate_hz=250_000)


if __name__ == "__main__":
    unittest.main()
