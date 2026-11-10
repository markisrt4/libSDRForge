# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Offline regression tests for shared FM multiplex stereo/RDS pipeline."""

import unittest
import numpy as np

from sdrforge.receivers.channelized_stereo_wbfm_demodulator import ChannelizedStereoWbfmDemodulator
from sdrforge.receivers.multi_mode_radio_receiver import MultiModeRadioReceiver, RadioChannel


class StereoRdsIntegrationTest(unittest.TestCase):
    def test_optional_rds_off_by_default(self):
        demod = ChannelizedStereoWbfmDemodulator()
        self.assertIsNone(demod.rds_status)
        samples = np.ones(4800, dtype=np.complex64)
        audio = demod.process(samples)
        self.assertEqual(audio.shape[1], 2)

    def test_rds_enabled_shares_multiplex_without_changing_audio(self):
        samples = np.exp(1j * np.linspace(0, 4, 9600)).astype(np.complex64)
        plain = ChannelizedStereoWbfmDemodulator()
        with_rds = ChannelizedStereoWbfmDemodulator(rds_enabled=True)
        for chunk in np.array_split(samples, 3):
            a = plain.process(chunk)
            b = with_rds.process(chunk)
            np.testing.assert_allclose(a, b, rtol=0, atol=1e-6)
        self.assertIsNotNone(with_rds.rds_status)
        with_rds.reset()
        self.assertIsNone(with_rds.rds_status.metadata.pi)

    def test_receiver_configuration(self):
        with self.assertRaises(ValueError):
            MultiModeRadioReceiver(rds_wfm=True)
        receiver = MultiModeRadioReceiver(stereo_wfm=True, rds_wfm=True)
        receiver.add_channel(RadioChannel("fm", 104300000, "WFM"))
        self.assertIn("fm", receiver.rds_status)
        receiver.retune_channel("fm", 104700000)
        self.assertIsNone(receiver.rds_status["fm"].metadata.pi)
        receiver.remove_channel("fm")
        self.assertEqual(receiver.rds_status, {})


if __name__ == "__main__":
    unittest.main()
