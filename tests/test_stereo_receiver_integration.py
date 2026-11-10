# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Offline stereo FM receiver integration regressions."""

import unittest

import numpy as np

from sdrforge.receivers import ChannelizedStereoWbfmDemodulator


class StereoReceiverIntegrationTest(unittest.TestCase):
    @staticmethod
    def modulated_iq(count: int = 48_000) -> np.ndarray:
        rate = 240_000
        t = np.arange(count) / rate
        instantaneous_hz = 15_000 * np.sin(2 * np.pi * 1_000 * t)
        phase = 2 * np.pi * np.cumsum(instantaneous_hz) / rate
        return (0.6 * np.exp(1j * phase)).astype(np.complex64)

    def test_optional_rds_off_by_default(self) -> None:
        receiver = ChannelizedStereoWbfmDemodulator()
        self.assertIsNone(receiver.rds_status)
        audio = receiver.process(self.modulated_iq())
        self.assertEqual(audio.shape, (9_600, 2))
        np.testing.assert_allclose(audio[:, 0], audio[:, 1], atol=1e-6)

    def test_rds_enabled_does_not_change_audio(self) -> None:
        iq = self.modulated_iq()
        plain = ChannelizedStereoWbfmDemodulator()
        with_rds = ChannelizedStereoWbfmDemodulator(rds_enabled=True)
        for start in range(0, len(iq), 1237):
            chunk = iq[start:start + 1237]
            np.testing.assert_allclose(
                plain.process(chunk), with_rds.process(chunk), rtol=0, atol=1e-6
            )
        self.assertIsNotNone(with_rds.rds_status)
        with_rds.reset()
        status = with_rds.rds_status
        self.assertIsNotNone(status)
        assert status is not None
        self.assertIsNone(status.metadata.pi)

    def test_chunked_processing_matches_whole(self) -> None:
        iq = self.modulated_iq()
        expected = ChannelizedStereoWbfmDemodulator().process(iq)
        receiver = ChannelizedStereoWbfmDemodulator()
        pieces = [
            receiver.process(iq[start:start + 1237])
            for start in range(0, len(iq), 1237)
        ]
        np.testing.assert_allclose(np.concatenate(pieces), expected, atol=1e-5)

    def test_reset_restores_fresh_receiver_behavior(self) -> None:
        iq = self.modulated_iq()
        receiver = ChannelizedStereoWbfmDemodulator(rds_enabled=True)
        receiver.process(iq)
        receiver.reset()
        expected = ChannelizedStereoWbfmDemodulator(rds_enabled=True).process(iq)
        np.testing.assert_allclose(receiver.process(iq), expected, atol=1e-5)


if __name__ == "__main__":
    unittest.main()
