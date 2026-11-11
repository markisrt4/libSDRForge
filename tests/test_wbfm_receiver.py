# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Hardware-free raw IQ to WFM audio integration tests."""

import unittest

import numpy as np

from sdrforge.models.iq import IqBlock
from sdrforge.receivers import WbfmReceiver


def synthetic_block(count: int = 24_000) -> IqBlock:
    rate = 2_400_000
    t = np.arange(count) / rate
    frequency = 15_000 * np.sin(2 * np.pi * 1_000 * t)
    phase = 2 * np.pi * np.cumsum(frequency) / rate
    iq = 0.6 * np.exp(1j * phase)
    packed = np.empty(count * 2, dtype=np.uint8)
    packed[::2] = np.clip(np.rint(iq.real * 127.5 + 127.5), 0, 255)
    packed[1::2] = np.clip(np.rint(iq.imag * 127.5 + 127.5), 0, 255)
    return IqBlock(packed.tobytes(), 104_300_000, rate, 0)


class WbfmReceiverTest(unittest.TestCase):
    def test_mono_and_stereo_output_shapes(self) -> None:
        block = synthetic_block()
        mono = WbfmReceiver(channel_frequency_hz=104_300_000, mode="mono")
        stereo = WbfmReceiver(channel_frequency_hz=104_300_000)
        self.assertEqual(mono.process(block).shape, (480,))
        self.assertEqual(stereo.process(block).shape, (480, 2))

    def test_rds_optional_and_mode_validation(self) -> None:
        self.assertIsNone(
            WbfmReceiver(channel_frequency_hz=104_300_000).rds_status
        )
        receiver = WbfmReceiver(
            channel_frequency_hz=104_300_000, rds_enabled=True
        )
        self.assertIsNotNone(receiver.rds_status)
        receiver.process(synthetic_block())
        receiver.reset(preserve_metadata=True)
        self.assertIsNotNone(receiver.rds_status)
        with self.assertRaises(ValueError):
            WbfmReceiver(
                channel_frequency_hz=104_300_000, mode="mono", rds_enabled=True
            )

    def test_chunked_matches_whole(self) -> None:
        block = synthetic_block(48_000)
        whole = WbfmReceiver(channel_frequency_hz=104_300_000).process(block)
        receiver = WbfmReceiver(channel_frequency_hz=104_300_000)
        raw = block.samples
        chunks = [
            receiver.process(
                IqBlock(raw[start:start + 4934], 104_300_000, 2_400_000, 0)
            )
            for start in range(0, len(raw), 4934)
        ]
        np.testing.assert_allclose(np.concatenate(chunks), whole, atol=1e-5)


if __name__ == "__main__":
    unittest.main()
