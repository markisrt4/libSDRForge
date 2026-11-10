# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Streaming FM stereo multiplex decoder, independent of SDR hardware."""

from __future__ import annotations

import numpy as np
from scipy import signal


class FmStereoDecoder:
    """Decode L+R and pilot-coherent L-R from 240 kSPS FM multiplex.

    Outputs interleaved 48 kHz stereo PCM. A weak pilot selects dual mono.
    """

    def __init__(self, *, sample_rate_hz: int = 240_000,
                 audio_rate_hz: int = 48_000, deemphasis_us: float = 75.0,
                 pilot_threshold: float = 0.015) -> None:
        if sample_rate_hz != 240_000 or audio_rate_hz != 48_000:
            raise ValueError("requires 240 kSPS multiplex and 48 kHz audio")
        if deemphasis_us <= 0 or pilot_threshold < 0:
            raise ValueError("invalid deemphasis or pilot threshold")
        self._pilot_sos = signal.butter(4, [18_700, 19_300], btype="bandpass",
                                        fs=sample_rate_hz, output="sos")
        self._audio_sos = signal.butter(6, 15_000, fs=sample_rate_hz, output="sos")
        self._difference_sos = signal.butter(6, 15_000, fs=sample_rate_hz, output="sos")
        self._alpha = 1 - np.exp(-1 / (audio_rate_hz * deemphasis_us * 1e-6))
        # Compensate the pilot bandpass phase at 19 kHz. The synthetic
        # multiplex convention uses a sine pilot and cosine 38 kHz carrier.
        _, response = signal.sosfreqz(self._pilot_sos, worN=[19_000], fs=sample_rate_hz)
        self._pilot_phase_correction = np.pi / 2 - np.angle(response[0])
        self._pilot_threshold = pilot_threshold
        self.reset()

    def reset(self) -> None:
        self._pilot_state = signal.sosfilt_zi(self._pilot_sos) * 0
        self._sum_state = signal.sosfilt_zi(self._audio_sos) * 0
        self._difference_state = signal.sosfilt_zi(self._difference_sos) * 0
        self._phase = 0
        self._pilot_complex = 0j
        self._pilot_smoothing_state = np.zeros(1, dtype=np.complex128)
        self._pilot_level = 0.0
        self.stereo_blend = 0.0
        self._deemphasis_state = np.zeros(2)
        self._sample_index = 0
        self.stereo_locked = False

    def process(self, multiplex: np.ndarray) -> np.ndarray:
        samples = np.asarray(multiplex, dtype=np.float64)
        if samples.ndim != 1:
            raise ValueError("expected one-dimensional FM multiplex")
        if not len(samples):
            return np.empty((0, 2), dtype=np.float32)
        pilot, self._pilot_state = signal.sosfilt(
            self._pilot_sos, samples, zi=self._pilot_state)
        indices = np.arange(len(samples), dtype=np.float64) + self._sample_index
        oscillator = np.exp(-2j * np.pi * 19_000 * indices / 240_000)
        # Complex pilot reference with an exponential smoothing loop.
        # Bandpass filtering introduces a fixed phase shift; the doubled
        # reference inherits that shift and is calibrated below.
        reference = pilot * oscillator
        alpha = 0.0005
        smooth, self._pilot_smoothing_state = signal.lfilter(
            [alpha], [1, -(1 - alpha)], reference,
            zi=self._pilot_smoothing_state)
        self._pilot_complex = complex(smooth[-1])
        pilot_amplitude = 2 * abs(self._pilot_complex)
        self._pilot_level = pilot_amplitude
        self.stereo_locked = pilot_amplitude >= self._pilot_threshold
        # Use the per-sample pilot envelope rather than a block-wide switch.
        # This avoids stereo jumps at arbitrary SDR callback boundaries.
        # Below threshold: dual mono. Above twice threshold: full stereo.
        if self._pilot_threshold == 0:
            blend = np.ones(len(samples))
        else:
            blend = np.clip((2 * np.abs(smooth) - self._pilot_threshold)
                            / self._pilot_threshold, 0.0, 1.0)
        self.stereo_blend = float(blend[-1])
        # Derive the 38 kHz oscillator from the pilot's phase. A bandpass
        # filter's phase at 19 kHz must be accounted for by calibration.
        phase = np.angle(smooth) + self._pilot_phase_correction
        carrier = np.cos(2 * (2 * np.pi * 19_000 * indices / 240_000 + phase))
        summed, self._sum_state = signal.sosfilt(
            self._audio_sos, samples, zi=self._sum_state)
        difference, self._difference_state = signal.sosfilt(
            self._difference_sos, samples * (2 * carrier), zi=self._difference_state)
        summed = summed[self._phase::5]
        difference = difference[self._phase::5] * blend[self._phase::5]
        self._phase = (self._phase - len(samples)) % 5
        self._sample_index = (self._sample_index + len(samples)) % 240_000
        channels = np.column_stack(((summed + difference) * 0.5,
                                    (summed - difference) * 0.5))
        output = np.empty_like(channels)
        for index in range(2):
            output[:, index], self._deemphasis_state[index:index + 1] = signal.lfilter(
                [self._alpha], [1, -(1 - self._alpha)], channels[:, index],
                zi=self._deemphasis_state[index:index + 1])
        return np.clip(output, -1, 1).astype(np.float32)
