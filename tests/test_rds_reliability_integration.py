# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Offline tests for metadata preservation and recent RDS pair diagnostics."""

import unittest

import numpy as np

from sdrforge.protocols.rds.rds_biphase_decoder import RdsBiphaseDecoder
from sdrforge.protocols.rds.rds_block_sync import RdsGroup
from sdrforge.protocols.rds.receiver_controller import RdsReceiverController
from sdrforge.receivers.multi_mode_radio_receiver import (
    MultiModeRadioReceiver,
    RadioChannel,
)


class RdsReliabilityIntegrationTest(unittest.TestCase):
    def test_recent_error_fraction_and_reset(self):
        decoder = RdsBiphaseDecoder()
        self.assertIsNone(decoder.recent_invalid_pair_fraction)
        decoder.process(np.array([1, -1, 1, 1, -1, 1], dtype=np.float32))
        self.assertEqual(decoder.total_pairs, 3)
        self.assertEqual(decoder.invalid_pairs, 1)
        self.assertEqual(decoder.recent_pair_count, 3)
        self.assertAlmostEqual(decoder.recent_invalid_pair_fraction, 1 / 3)
        decoder.reset()
        self.assertIsNone(decoder.recent_invalid_pair_fraction)
        self.assertEqual(decoder.recent_pair_count, 0)

    def test_recent_window_excludes_old_errors(self):
        decoder = RdsBiphaseDecoder()
        decoder.process(np.tile([1, 1], 100).astype(np.float32))
        decoder.process(np.tile([1, -1], 2048).astype(np.float32))
        self.assertEqual(decoder.invalid_pairs, 100)
        self.assertEqual(decoder.recent_pair_count, 2048)
        self.assertEqual(decoder.recent_invalid_pair_fraction, 0.0)

    def test_rds_soft_reset_preserves_published_station(self):
        receiver = RdsReceiverController()
        receiver._metadata.process(RdsGroup(0x7ADA, 0, 0, 0x574F, False))
        receiver.reset(preserve_metadata=True)
        self.assertEqual(receiver.status.metadata.pi, 0x7ADA)
        self.assertIsNone(receiver.status.locked_pair_phase)
        self.assertEqual(receiver.status.groups_found, 0)
        receiver.reset()
        self.assertIsNone(receiver.status.metadata.pi)

    def test_channel_reset_preserves_station_but_retune_clears(self):
        receiver = MultiModeRadioReceiver(stereo_wfm=True, rds_wfm=True)
        receiver.add_channel(RadioChannel("fm", 104_300_000, "WFM"))
        receiver._decoders["fm"]._rds._metadata.process(
            RdsGroup(0x7ADA, 0, 0, 0x574F, False))
        receiver.reset(preserve_metadata=True)
        self.assertEqual(receiver.rds_status["fm"].metadata.pi, 0x7ADA)
        receiver.retune_channel("fm", 104_700_000)
        self.assertIsNone(receiver.rds_status["fm"].metadata.pi)

    def test_pi_change_clears_old_station_name(self):
        receiver = RdsReceiverController()
        for _ in range(2):
            for i, pair in enumerate(("WO", "MC", "10", "4 ")):
                receiver._metadata.process(
                    RdsGroup(0x7ADA, i, 0, ord(pair[0]) << 8 | ord(pair[1]), False))
        self.assertEqual(receiver.status.metadata.program_service, "WOMC104")
        receiver.reset(preserve_metadata=True)
        receiver._metadata.process(RdsGroup(0x1234, 0, 0, 0x4142, False))
        self.assertEqual(receiver.status.metadata.pi, 0x1234)
        self.assertIsNone(receiver.status.metadata.program_service)


if __name__ == "__main__":
    unittest.main()
