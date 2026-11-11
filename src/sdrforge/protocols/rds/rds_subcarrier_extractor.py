# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Streaming 57 kHz RDS subcarrier extraction from 240 kSPS FM multiplex."""

from __future__ import annotations

import numpy as np
from scipy import signal


class RdsSubcarrierExtractor:
    """Translate 57 kHz to complex baseband and decimate to 12 kSPS.

    This stage does not recover RDS carrier phase, timing, or bits.
    Complex output retains phase ambiguity for downstream synchronization.
    """

    INPUT_RATE_HZ = 240_000
    OUTPUT_RATE_HZ = 12_000
    DECIMATION = 20

    def __init__(self, *, cutoff_hz: float = 3_000.0) -> None:
        if not 500.0 <= cutoff_hz <= 5_500.0:
            raise ValueError('cutoff_hz must be between 500 and 5500 Hz')
        self.cutoff_hz = float(cutoff_hz)
        # RDS BPSK occupies approximately +/-2.4 kHz around 57 kHz.
        # Reject neighboring stereo multiplex energy before decimation.
        self._sos = signal.butter(
            6, self.cutoff_hz, fs=self.INPUT_RATE_HZ, output="sos")
        self.reset()

    def reset(self) -> None:
        self._filter_state = np.zeros((len(self._sos), 2), dtype=np.complex128)
        self._sample_index = 0
        self._decimation_phase = 0

    def process(self, multiplex: np.ndarray) -> np.ndarray:
        samples = np.asarray(multiplex)
        if samples.ndim != 1 or not np.issubdtype(samples.dtype, np.number):
            raise ValueError("expected one-dimensional numeric FM multiplex")
        if np.iscomplexobj(samples):
            raise ValueError("FM multiplex must be real-valued")
        if not len(samples):
            return np.empty(0, dtype=np.complex64)
        if not np.all(np.isfinite(samples)):
            raise ValueError("FM multiplex must contain finite samples")
        indices = np.arange(len(samples), dtype=np.float64) + self._sample_index
        oscillator = np.exp(-2j * np.pi * 57_000 * indices / self.INPUT_RATE_HZ)
        baseband, self._filter_state = signal.sosfilt(
            self._sos, 2.0 * samples * oscillator, zi=self._filter_state)
        output = baseband[self._decimation_phase::self.DECIMATION]
        self._decimation_phase = (
            self._decimation_phase - len(samples)) % self.DECIMATION
        self._sample_index = (
            self._sample_index + len(samples)) % self.INPUT_RATE_HZ
        result: np.ndarray = output.astype(np.complex64)
        return result
