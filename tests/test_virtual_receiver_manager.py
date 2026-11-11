# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""Tests for independent virtual receivers sharing one IQ capture."""

import unittest

import numpy as np

from sdrforge.core.virtual_receiver_manager import (
    VirtualChannel,
    VirtualReceiverManager,
)
from sdrforge.models.iq import IqBlock

RATE = 2_400_000
CENTER = 104_300_000


def make_block(count: int = 48_000) -> IqBlock:
    t = np.arange(count) / RATE
    iq = (0.28 * np.exp(2j * np.pi * 100_000 * t) +
          0.28 * np.exp(-2j * np.pi * 300_000 * t))
    raw = np.empty(2 * count, dtype=np.uint8)
    raw[::2] = np.clip(np.rint(127.5 + 127.5 * iq.real), 0, 255).astype(np.uint8)
    raw[1::2] = np.clip(np.rint(127.5 + 127.5 * iq.imag), 0, 255).astype(np.uint8)
    return IqBlock(raw.tobytes(), CENTER, RATE, 1)


def configured_manager() -> VirtualReceiverManager:
    manager = VirtualReceiverManager()
    manager.add_channel(VirtualChannel("audio", CENTER + 100_000))
    manager.add_channel(VirtualChannel("metadata", CENTER - 300_000))
    return manager


class VirtualReceiverManagerTest(unittest.TestCase):
    def test_shared_capture_produces_two_channels(self) -> None:
        outputs = configured_manager().process(make_block())
        self.assertEqual(set(outputs), {"audio", "metadata"})
        self.assertEqual(len(outputs["audio"]), 4800)
        self.assertEqual(len(outputs["metadata"]), 4800)
        self.assertGreater(abs(np.mean(outputs["audio"][1000:])), 0.20)
        self.assertGreater(abs(np.mean(outputs["metadata"][1000:])), 0.20)

    def test_chunked_matches_single_capture(self) -> None:
        block = make_block()
        whole = configured_manager().process(block)
        manager = configured_manager()
        chunks = {"audio": [], "metadata": []}
        for index in range(0, len(block.samples), 12_346):
            part = IqBlock(block.samples[index:index + 12_346], CENTER, RATE, 1)
            for name, iq in manager.process(part).items():
                chunks[name].append(iq)
        for name, samples in chunks.items():
            np.testing.assert_allclose(np.concatenate(samples), whole[name],
                                       atol=1e-5)

    def test_invalid_channel_does_not_consume_good_channel_state(self) -> None:
        block = make_block()
        manager = configured_manager()
        manager.retune_channel("metadata", CENTER + 1_150_000)
        with self.assertRaisesRegex(ValueError, "metadata"):
            manager.process(block)
        manager.retune_channel("metadata", CENTER - 300_000)
        reference = configured_manager().process(block)
        actual = manager.process(block)
        for name in reference:
            np.testing.assert_allclose(actual[name], reference[name], atol=1e-5)

    def test_channel_lifecycle(self) -> None:
        manager = configured_manager()
        with self.assertRaises(ValueError):
            manager.add_channel(VirtualChannel("audio", CENTER))
        manager.remove_channel("metadata")
        self.assertEqual(tuple(c.name for c in manager.channels), ("audio",))
        manager.reset()
        self.assertEqual(list(manager.process(make_block())), ["audio"])


if __name__ == "__main__":
    unittest.main()
