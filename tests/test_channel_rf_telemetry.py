# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

import unittest

import numpy as np

from sdrforge.diagnostics.channel_rf_telemetry import (
    adc_clip_fraction,
    measure_channel_rf,
)


class ChannelRfTelemetryTest(unittest.TestCase):
    def test_stronger_tone_has_higher_power_than_weak_tone(self):
        t = np.arange(4096)
        weak = 0.1 * np.exp(2j * np.pi * 83 * t / 4096)
        strong = 0.5 * np.exp(2j * np.pi * 83 * t / 4096)
        a = measure_channel_rf(weak)
        b = measure_channel_rf(strong)
        self.assertGreater(b.signal_power_dbfs, a.signal_power_dbfs)
        self.assertAlmostEqual(b.signal_power_dbfs - a.signal_power_dbfs, 13.98, places=1)
        self.assertEqual(b.iq_samples, 4096)

    def test_adc_rail_fraction(self):
        self.assertEqual(adc_clip_fraction(bytes([0, 1, 2, 3, 128, 252, 253, 254, 255])), 6 / 9)
        self.assertEqual(adc_clip_fraction(bytes([127, 128])), 0.0)

    def test_empty_iq_rejected(self):
        with self.assertRaises(ValueError):
            measure_channel_rf(np.array([], dtype=np.complex64))

    def test_spectral_contrast_for_tone(self):
        t = np.arange(4096)
        rng = np.random.default_rng(42)
        tone = 0.4 * np.exp(2j * np.pi * 123 * t / 4096)
        noise = 0.02 * (rng.normal(size=4096) + 1j * rng.normal(size=4096))
        telemetry = measure_channel_rf(tone + noise)
        self.assertGreater(telemetry.estimated_snr_db, 20)


if __name__ == "__main__":
    unittest.main()
