# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Hardware-independent RDS receiver orchestration tests."""

import unittest

import numpy as np

from sdrforge.protocols.rds.receiver_controller import RdsReceiverController
from sdrforge.protocols.rds.rds_block_sync import RdsGroup


class RdsReceiverControllerTest(unittest.TestCase):
    def test_empty_input_and_status(self):
        receiver = RdsReceiverController()
        self.assertEqual(receiver.process_multiplex(np.array([], dtype=np.float32)), [])
        self.assertEqual(receiver.process_iq(np.array([], dtype=np.complex64)), [])
        self.assertEqual(receiver.status.groups_found, 0)
        self.assertIsNone(receiver.status.metadata.pi)
        self.assertAlmostEqual(receiver.status.half_bit_samples_per_symbol,
                               12_000 / 2375)

    def test_group_metadata_and_reset_with_stubbed_physical_stages(self):
        """Exercise real bit/group/metadata stages while isolating RF locking.

        This is not an end-to-end RF waveform decoding test.
        """
        receiver = RdsReceiverController(pair_phase=0)
        from sdrforge.protocols.rds.rds_block_sync import encode_block
        words = [encode_block(value, name) for value, name in (
            (0x1234, "A"), (0x0000, "B"), (0, "C"), (0x4F52, "D"))]
        bits = np.array([(word >> shift) & 1
                         for word in words for shift in range(25, -1, -1)],
                        dtype=np.uint8)
        # Isolate the downstream real block synchronizer/metadata decoder.
        groups = receiver._blocks.process(bits)
        for group in groups:
            receiver._metadata.process(group)
        self.assertEqual(len(groups), 1)
        self.assertIsInstance(groups[0], RdsGroup)
        self.assertEqual(receiver.status.metadata.pi, 0x1234)
        self.assertEqual(receiver.status.groups_found, 1)
        receiver.reset()
        self.assertIsNone(receiver.status.metadata.pi)
        self.assertEqual(receiver.status.groups_found, 0)

    def test_auto_phase_acquisition_and_reacquisition(self):
        from sdrforge.protocols.rds.rds_block_sync import encode_block
        words = [encode_block(value, offset) for value, offset in (
            (0x1234, "A"), (0x0000, "B"), (0, "C"), (0x4F52, "D"))]
        payload = np.asarray([(word >> shift) & 1
                              for word in words for shift in range(25, -1, -1)],
                             dtype=np.uint8)
        def halves(bits):
            previous = 0
            result = []
            for bit in bits:
                previous ^= int(bit)
                result.extend((previous * 2 - 1, (previous ^ 1) * 2 - 1))
            return np.asarray(result, dtype=np.float32)
        receiver = RdsReceiverController(loss_timeout_bits=104)
        # Prepend one half-bit, so phase 1 is the correct pair alignment.
        aligned = np.concatenate(([1.0], halves(np.concatenate(([0], payload)))))
        groups = receiver.process_half_bits(aligned)
        self.assertEqual(len(groups), 1)
        self.assertEqual(receiver.status.locked_pair_phase, 1)
        self.assertEqual(receiver.status.metadata.pi, 0x1234)
        receiver.process_half_bits(np.zeros(420, dtype=np.float32))
        self.assertIsNone(receiver.status.locked_pair_phase)
        self.assertEqual(receiver.status.metadata.pi, 0x1234)
        self.assertEqual(receiver.status.sync_confidence, 0)
        receiver.reset()
        self.assertIsNone(receiver.status.metadata.pi)
        self.assertIsNone(receiver.status.locked_pair_phase)

    def test_sync_confidence_requires_multiple_timeouts(self):
        from sdrforge.protocols.rds.rds_block_sync import encode_block
        words = [encode_block(value, offset) for value, offset in (
            (0x1234, "A"), (0x0000, "B"), (0, "C"), (0x4F52, "D"))]
        bits = [(word >> shift) & 1 for word in words for shift in range(25, -1, -1)]
        previous = 0
        halves = []
        for bit in bits:
            previous ^= bit
            halves.extend((previous * 2 - 1, (previous ^ 1) * 2 - 1))
        receiver = RdsReceiverController(loss_timeout_bits=104)
        receiver.process_half_bits(np.asarray(halves * 4, dtype=np.float32))
        self.assertIsNotNone(receiver.status.locked_pair_phase)
        self.assertGreaterEqual(receiver.status.sync_confidence, 1)
        receiver.process_half_bits(np.zeros(420, dtype=np.float32))
        self.assertEqual(receiver.status.metadata.pi, 0x1234)

    def test_invalid_pair_phase_rejected(self):
        with self.assertRaises(ValueError):
            RdsReceiverController(pair_phase=2)

    def test_streamed_multiplex_does_not_require_audio_device(self):
        receiver = RdsReceiverController()
        samples = np.zeros(4_800, dtype=np.float32)
        self.assertEqual(receiver.process_multiplex(samples[:127]), [])
        self.assertEqual(receiver.process_multiplex(samples[127:]), [])
        self.assertEqual(receiver.status.groups_found, 0)


if __name__ == "__main__":
    unittest.main()
