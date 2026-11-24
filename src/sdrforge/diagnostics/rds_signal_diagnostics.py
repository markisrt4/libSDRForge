# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""!
@brief Lightweight diagnostic spectral measurements of the FM multiplex.

RDS occupies sidebands around 57 kHz, so these are relative band powers,
not a calibrated RDS Eb/N0 or decoded-bit SNR.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RdsSignalSnapshot:
    """!
    @brief Provide rds signal snapshot behavior.
    """

    pilot_19khz_dbfs: float
    rds_57khz_band_dbfs: float
    adjacent_noise_dbfs: float
    rds_to_adjacent_db: float


class RdsSignalDiagnostics:
    """!
    @brief Accumulate a rolling FFT window; inspect it only at report intervals.
    """

    def __init__(self, *, sample_rate_hz: int = 240_000, fft_size: int = 16384):
        """!
        @brief Initialize the instance.

        @param self The current instance.
        @param sample_rate_hz The ``sample_rate_hz`` value.
        @param fft_size The ``fft_size`` value.
        """
        if sample_rate_hz <= 0 or fft_size < 1024:
            raise ValueError("invalid spectral configuration")
        self.sample_rate_hz = sample_rate_hz
        self.fft_size = fft_size
        self._samples = np.empty(0, dtype=np.float32)

    def reset(self) -> None:
        """!
        @brief Reset the component.

        @param self The current instance.
        """
        self._samples = np.empty(0, dtype=np.float32)

    def update(self, multiplex: np.ndarray) -> None:
        """!
        @brief Update the component.

        @param self The current instance.
        @param multiplex The ``multiplex`` value.
        """
        values = np.asarray(multiplex, dtype=np.float32)
        if values.ndim != 1:
            raise ValueError("expected one-dimensional FM multiplex")
        if not len(values):
            return
        if len(values) >= self.fft_size:
            self._samples = values[-self.fft_size :].copy()
        else:
            self._samples = np.concatenate((self._samples, values))[-self.fft_size :]

    def snapshot(self) -> RdsSignalSnapshot | None:
        """!
        @brief Return the snapshot.

        @param self The current instance.
        @return The operation result.
        """
        if len(self._samples) < self.fft_size:
            return None
        window = np.hanning(self.fft_size)
        spectrum = np.fft.rfft(self._samples.astype(np.float64) * window)
        # Normalized one-sided power; consistent between spectral bands.
        power = (np.abs(spectrum) / max(window.sum() / 2, 1)) ** 2
        frequencies = np.fft.rfftfreq(self.fft_size, 1 / self.sample_rate_hz)

        def band(lo: float, hi: float) -> float:
            selected = power[(frequencies >= lo) & (frequencies < hi)]
            return float(10 * np.log10(max(float(np.sum(selected)), 1e-15)))

        pilot = band(18_800, 19_200)
        rds = band(54_600, 59_400)
        # Nearby reference bands avoid the nominal RDS sidebands.
        noise = (
            10 ** (band(49_000, 51_400) / 10) + 10 ** (band(62_600, 65_000) / 10)
        ) / 2
        noise_db = float(10 * np.log10(max(noise, 1e-15)))
        return RdsSignalSnapshot(pilot, rds, noise_db, rds - noise_db)
